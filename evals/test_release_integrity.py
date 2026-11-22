"""Checks for the policy applied to generated pages and the integrity of a saved release."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
from film_player import PUBLIC_MEDIA_DIR, film_files, opening_link, render_player
from release_integrity import browser_policy, script_hash, verify_homepage_film, verify_manifest, write_manifest
from build import broken, GITHUB


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

    def test_source_listings_and_public_reporting_have_separate_permissions(self):
        listing = '<script type="application/ld+json">{"name":"example"}</script>'
        self.assertIn("script-src 'none'", browser_policy(listing, "source/index.html", set(), False))
        analytics = '<script src="assets/interactions.js"></script>'
        with self.assertRaisesRegex(ValueError, "Unregistered script"):
            browser_policy(analytics, "index.html", set(), False)
        page = '<script src="assets/site.js"></script>'
        self.assertIn("api.github.com", browser_policy(page, "index.html", set(), False))


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
