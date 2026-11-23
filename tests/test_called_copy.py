"""The copy whose `taos` was called answers a folder no copy knows; a linked folder still finds its own copy."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
if str(HOME) not in sys.path:
    sys.path.insert(0, str(HOME))

from taos_core.paths import Paths  # noqa: E402


class CalledCopy(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.pop("TAOS_HOME", None)

    def tearDown(self):
        if self.saved is not None:
            os.environ["TAOS_HOME"] = self.saved

    def test_a_folder_no_copy_knows_is_answered_by_the_copy_that_was_called(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(Paths.discover(Path(folder)).home.resolve(), HOME)

    def test_a_folder_linked_to_another_copy_still_finds_that_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            other, work = Path(folder) / "other-copy", Path(folder) / "work"
            (other / "taos_core").mkdir(parents=True)
            (other / "taos").write_text("", encoding="utf-8")
            work.mkdir()
            (work / ".taos-link.json").write_text(json.dumps({"taos_home": str(other)}), encoding="utf-8")
            self.assertEqual(Paths.discover(work).home.resolve(), other.resolve())


if __name__ == "__main__":
    unittest.main()
