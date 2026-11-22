"""Checks for the policy applied to generated pages and the integrity of a saved release."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
from release_integrity import browser_policy, script_hash, verify_manifest, write_manifest


class TestBrowserPolicy(unittest.TestCase):
    def test_only_approved_private_inline_code_gets_a_hash(self):
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
