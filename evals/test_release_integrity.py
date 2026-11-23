"""Checks for the policy applied to generated pages and the integrity of a saved release."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
from film_player import PUBLIC_MEDIA_DIR, film_files, opening_link, render_player
from release_integrity import PageScripts, version_assets
from reading_navigation import THEME_INTEGRITY
from release_integrity import browser_policy, script_hash, verify_homepage_film, verify_manifest, write_manifest
from build import broken, GITHUB, REPO, load_audit
import demo_walkthrough


class TestBrowserPolicy(unittest.TestCase):
    def test_only_approved_homepage_inline_code_gets_a_hash(self):
        sample = "/* trusted project template */"
        tag = "<script>" + sample + "</script>"
        trusted = {script_hash(sample)}
        self.assertIn(script_hash(sample), browser_policy(tag, "index.html", trusted, False))
        with self.assertRaisesRegex(ValueError, "Unregistered inline"):
            browser_policy(tag, "exchange/index.html", trusted, False)
        with self.assertRaisesRegex(ValueError, "Unregistered inline"):
            browser_policy(tag, "index.html", set(), False)

    def test_local_assets_are_pinned_while_inline_and_external_content_is_preserved(self):
        markup = ('<link rel="stylesheet" href="../assets/style.css">\n'
                  '<script defer src="../assets/site.js"></script>\n'
                  '<script src="https://example.org/bg.js"></script>'
                  '<pre>&lt;script src="../assets/site.js"&gt;</pre>')
        resources = PageScripts(markup).resources
        versions = {"assets/site.js": "old-script", "assets/style.css": "same-style"}
        first = version_assets(markup, "hpc/index.html", resources, versions)
        self.assertIn('href="../assets/style.css?v=same-style"', first)
        self.assertIn('src="../assets/site.js?v=old-script"', first)
        self.assertIn('<script src="https://example.org/bg.js">', first)
        self.assertIn('<pre>&lt;script src="../assets/site.js"&gt;</pre>', first)
        versions["assets/site.js"] = "new-script"
        second = version_assets(markup, "hpc/index.html", resources, versions)
        self.assertEqual(first.replace("v=old-script", "v=new-script"), second)

    def test_source_listings_and_public_reporting_have_separate_permissions(self):
        listing = '<script type="application/ld+json">{"name":"example"}</script>'
        self.assertIn("script-src 'none'", browser_policy(listing, "source/index.html", set(), False))
        analytics = '<script src="assets/interactions.js"></script>'
        with self.assertRaisesRegex(ValueError, "Unregistered script"):
            browser_policy(analytics, "index.html", set(), False)
        live = browser_policy(analytics, "index.html", set(), True)
        self.assertIn("https://static.cloudflareinsights.com/beacon.min.js", live)
        self.assertIn("https://whatstillholds-interactions.", live)
        theme = f'<script src="../assets/theme.js" integrity="{THEME_INTEGRITY}"></script>'
        source_policy = browser_policy(theme, "source/index.html", set(), True)
        self.assertIn(f"script-src '{THEME_INTEGRITY}'", source_policy)
        self.assertIn("connect-src 'none'", source_policy)
        with self.assertRaisesRegex(ValueError, "Unexpected script in source viewer"):
            browser_policy(theme.replace("assets/theme.js", "assets/site.js"), "source/index.html", set(), True)
        with self.assertRaisesRegex(ValueError, "Unexpected script in source viewer"):
            browser_policy(theme.replace(THEME_INTEGRITY, "sha256-wrong"), "source/index.html", set(), True)
        project_review = '<script src="../assets/hpc-review.js"></script>'
        self.assertIn("script-src 'self'", browser_policy(project_review, "hpc/index.html", set(), False))
        with self.assertRaisesRegex(ValueError, "Unregistered script"):
            browser_policy(project_review, "exchange/index.html", set(), False)
        page = '<script src="assets/site.js"></script>'
        self.assertIn("api.github.com", browser_policy(page, "index.html", set(), False))


class TestDemoWalkthrough(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = demo_walkthrough.capture(REPO)
        cls.audit = load_audit(REPO)

    def test_all_commands_survive_changes_to_the_narration(self):
        record = copy.deepcopy(self.record)
        for moment in record["moments"]:
            moment["idea"] = "An independently edited heading"
            for step in moment["steps"]:
                if step["kind"] == "say":
                    step["text"] = "An independently edited explanation"
        scenes = demo_walkthrough.chapters(record, self.audit)
        original = [step["command"] for m in record["moments"] for step in m["steps"] if step["kind"] == "run"]
        rendered = [line[2:] for scene in scenes for line in scene.lines if line.startswith("$ ")]
        self.assertEqual(rendered, original)
        self.assertEqual([s.anchor for s in scenes], ["run-1", "run-2", "run-3", "run-4", "run-5", "run-6",
                                                      "run-reminder", "run-7"])
        self.assertEqual([row[1:4] for row in scenes[2].comparisons],
                         [("2.21 s", "9.75 ± 0.02 m/s²", "Passes"),
                          ("2.2995 s", "9.44 ± 0.18 m/s²", "Below 9.6 m/s²")])

    def test_a_plausible_reported_fit_must_agree_with_the_readings(self):
        record = copy.deepcopy(self.record)
        fit = next(step for step in record["moments"][0]["steps"] if "measured" in step)
        fit["measured"]["g"] = 9.81
        fit["expected"] = [s.replace("9.82", "9.81") for s in fit["expected"]]
        fit["printed"] = [s.replace("9.82", "9.81") for s in fit["printed"]]
        with self.assertRaisesRegex(ValueError, "independent fit"):
            demo_walkthrough.chapters(record, self.audit)
        audit = copy.deepcopy(self.audit)
        next(case for case in audit["cases"] if case["id"] == "row-6-1.05")["se"] = 0.17
        with self.assertRaisesRegex(ValueError, "independent fit"):
            demo_walkthrough.chapters(self.record, audit)

    def test_the_saved_pass_and_the_fresh_check_are_checked_separately(self):
        record = copy.deepcopy(self.record)
        stale = next(s for s in record["moments"][0]["steps"] if s.get("id") == "timing-edited")
        stale["answer"] = "holds"
        with self.assertRaisesRegex(ValueError, "timing-edited"):
            demo_walkthrough.chapters(record, self.audit)
        audit = copy.deepcopy(self.audit)
        comparison = next(case for case in audit["cases"] if case["id"] == "row-6-1.05")
        comparison["fresh_exit"] = 0
        with self.assertRaisesRegex(ValueError, "larger correction"):
            demo_walkthrough.chapters(self.record, audit)

    def test_a_new_execution_cannot_be_reported_as_a_reused_pass(self):
        record = copy.deepcopy(self.record)
        runs = {s["id"]: s for moment in record["moments"] for s in moment["steps"] if s.get("id")}
        # Both requests say "holds" in the current terminal. Show a fresh execution
        # in the second request, with a consistent answer and expectation.
        for field in ("answer", "printed", "expected"):
            runs["shared"][field] = runs["rerun"][field]
        record["checked"] = sum(len(s["expected"]) for moment in record["moments"] for s in moment["steps"]
                                if s["kind"] == "run")
        with self.assertRaisesRegex(ValueError, "shared does not support"):
            demo_walkthrough.chapters(record, self.audit)


class TestHomepageFilm(unittest.TestCase):
    def test_release_requires_the_reviewed_film_and_a_working_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = film_files(None, root, release=True)
            entry = opening_link(files)
            player = render_player(files, root, PUBLIC_MEDIA_DIR)
            home = root / "index.html"
            home.write_text(entry + player, encoding="utf-8")
            verify_homepage_film(root)
            home.write_text(entry + player.replace('kind="captions"', 'kind="metadata"'), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "English captions"):
                verify_homepage_film(root)
            home.write_text(player, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "link to the film"):
                verify_homepage_film(root)
            home.write_text(entry, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dispatch record"):
                verify_homepage_film(root)
            home.write_text(entry + player.replace('preload="none"', 'autoplay'), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "wait for the reader"):
                verify_homepage_film(root)
            home.write_text(entry + player, encoding="utf-8")
            (root / PUBLIC_MEDIA_DIR / "reduced-motion.mp4").write_bytes(b"another cut")
            with self.assertRaisesRegex(ValueError, "reduced-motion.mp4"):
                verify_homepage_film(root)
            with self.assertRaisesRegex(SystemExit, "private film preview"):
                film_files(root, root, release=True)


class TestSourceNavigation(unittest.TestCase):
    def test_exchange_source_and_nested_error_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ("source", "exchange"):
                (root / folder).mkdir()
            (root / "source/index.html").write_text('<h1 id="files">Source files</h1>')
            exchange = root / "exchange/index.html"
            error = root / "404.html"
            revision = "a" * 40
            exchange.write_text(f'<a href="{GITHUB}/commit/{revision}">Source for this build</a>')
            error.write_text('<a href="source/">Source for this build</a>')
            self.assertEqual(len(broken(root, revision=revision)), 2)
            exchange.write_text('<a href="../source/#files">Source for this build</a>')
            error.write_text('<a href="/source/">Source for this build</a>')
            self.assertEqual(broken(root, revision=revision), [])


class TestReleaseInventory(unittest.TestCase):
    def test_fingerprint_checks_file_names_and_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            (tree / "standing.json").write_text(json.dumps({"revision": "example"}), encoding="utf-8")
            (tree / ".nojekyll").touch()
            reading = tree / "reading.txt"
            reading.write_bytes(b"original")
            write_manifest(tree, "example")
            receipt = verify_manifest(tree)
            self.assertEqual([x["path"] for x in receipt["files"]], [".nojekyll", "reading.txt", "standing.json"])
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                verify_manifest(tree, "0" * 64)
            reading.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "differ"):
                verify_manifest(tree)
            reading.write_bytes(b"original")
            reading.rename(tree / "renamed.txt")
            with self.assertRaisesRegex(ValueError, "differ"):
                verify_manifest(tree)
