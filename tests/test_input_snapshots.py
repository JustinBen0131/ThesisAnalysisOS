"""Research inputs must have identifiable bytes before a saved check can be reused."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from taos_core import basis, gates


class InputSnapshots(unittest.TestCase):
    def test_ignored_workspace_can_name_the_scientific_input_explicitly(self):
        with TemporaryDirectory() as folder:
            parent = Path(folder)
            subprocess.run(["git", "init", "-q", str(parent)], check=True)
            (parent / ".gitignore").write_text("experiment/\n", encoding="utf-8")
            work = parent / "experiment"
            work.mkdir()
            reading = work / "reading.csv"
            reading.write_text("2.19\n", encoding="utf-8")
            empty = basis.snapshot(work)
            self.assertFalse(empty["complete"])
            self.assertIn("basis.domains", empty["reason"])
            self.assertEqual(basis.compare({}, empty)["state"], basis.UNKNOWN)
            settings = {"domains": {"timing": ["reading.csv"]}}
            initial = basis.snapshot(work, settings)
            self.assertTrue(initial["complete"])
            self.assertEqual(basis.compare({}, initial)["state"], basis.UNKNOWN)
            saved = basis.digests(initial)
            self.assertEqual(basis.compare(saved, initial)["state"], basis.HOLDS)
            reading.write_text("2.2995\n", encoding="utf-8")
            self.assertEqual(basis.compare(saved, basis.snapshot(work, settings))["state"], basis.STALE)

    def test_isolated_check_receives_its_own_verified_copy(self):
        with TemporaryDirectory() as folder:
            work = Path(folder)
            reading = work / "reading.csv"
            reading.write_text("2.19\n", encoding="utf-8")
            snap = basis.snapshot(work, {"domains": {"timing": ["reading.csv"]}})
            filed = basis.digests(snap, ["timing"])

            def inspect(command, scratch, timeout, **kwargs):
                staged = scratch / "reading.csv"
                self.assertEqual(staged.read_bytes(), reading.read_bytes())
                self.assertFalse(staged.samefile(reading))
                return 0, "counted one row"

            with patch.object(gates, "closes", return_value=False), patch.object(gates, "_execute", side_effect=inspect) as run:
                self.assertEqual(gates._isolated(work, snap, filed, "count", 5)[0], 0)
                reading.write_text("2.2995\n", encoding="utf-8")
                code, reason, _ = gates._isolated(work, snap, filed, "count", 5)
                self.assertEqual(code, 125)
                self.assertIn("reading.csv", reason)
                run.assert_called_once()
