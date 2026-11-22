"""The demo is the first thing a reader runs, so it is tested like anything else."""

from __future__ import annotations

import io
import subprocess
import sys
import unittest

from helpers import REPO

from taos_core import demo

EXAMPLE = REPO / "examples" / "measurement"


class TestDemo(unittest.TestCase):
    def test_it_runs_from_a_clean_copy_and_shows_each_idea_with_real_output(self) -> None:
        out = io.StringIO()
        self.assertEqual(demo.run(out=out), 0)
        text = out.getvalue()
        for phrase in (
            "stale    check fit: analysis changed: data/swings.csv",            # the file that changed is named
            "not rerun: nothing it tested has changed",                         # asked by two tasks, executed once
            "\"Use the tape-measured lengths\"",                                # what governed on the earlier date
            "\"Use the laser-measured lengths\"",                               # and on the later one
            "stale    acceptance:",                                             # a person's acceptance is of one version
            "told:      \"Quote g with its uncertainty, never alone\"",         # delivered to the next agent
            "0 repeated, 0 followed, 1 not judged, of 1 times shown",           # shown is not repeated
            "FAIL  style        exit 2",                                        # it read a file it did not declare
            "A file it could not find is one it did not declare.",              # and the answer says so
            "ok    style        exit 0",                                        # declared, the same check passes
        ):
            self.assertIn(phrase, text)
        self.assertEqual(text.count("PEN-1 stands as recorded."), 2)            # the style edit left the result standing

    def test_the_example_measurement_gives_the_number_the_demo_quotes(self) -> None:
        fit = subprocess.run([sys.executable, str(EXAMPLE / "analysis" / "fit.py")], capture_output=True, text=True)
        self.assertEqual(fit.stdout.strip(), "g = 9.82 +/- 0.02 m/s^2 from 6 swings")
        check = subprocess.run([sys.executable, str(EXAMPLE / "analysis" / "check.py")], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0)


if __name__ == "__main__":
    unittest.main()
