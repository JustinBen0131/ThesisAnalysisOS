"""The demo is the first thing a reader runs, so it is tested like anything else."""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import unittest
from unittest import mock

from helpers import REPO

from taos_core import demo
from taos_core.util import TaosError

EXAMPLE = REPO / "examples" / "measurement"
IDEAS = ["standing", "reuse", "instructions", "acceptance", "reminder", "isolation"]


def played(**how) -> str:
    out = io.StringIO()
    assert demo.run(out=out, **how) == 0
    return out.getvalue()


class TestDemo(unittest.TestCase):
    def test_it_runs_from_a_clean_copy_and_shows_each_idea_with_real_output(self) -> None:
        text = played()
        for phrase in (
            "g = 9.82 +/- 0.02 m/s^2 from 6 swings",                            # the number the task closes on
            "stale    check fit: analysis changed: data/swings.csv",            # the file that changed is named
            "g = 9.75 +/- 0.02 m/s^2 from 6 swings",                            # and the flag was right: g moved
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
        self.assertEqual([line[:2] for line in text.splitlines() if re.match(r"\d\. ", line)],
                         ["{0}.".format(number) for number in range(1, 7)])     # six ideas, in order

    def test_a_terminal_gets_one_screen_led_by_the_answers_the_record_gave(self) -> None:
        lines = played(full=False).splitlines()
        self.assertLessEqual(len(lines), 36)                                    # it fits a 40-row window
        self.assertLessEqual(max(len(line) for line in lines), 80)
        for answer, about in (("holds", "the plot style is edited"), ("stale", "one swing is measured again"),
                              ("held", "not run twice"), ("stale", "the acceptance was of the old version"),
                              ("FAIL", "declared only the analysis"), ("ok", "the same check passes")):
            self.assertTrue(any(line.split()[0] == answer and about in line for line in lines if line.strip()), about)
        shaded = played(full=False, color=True)
        self.assertIn("\x1b[33mstale", shaded)                                  # the answer is shaded, the words are not
        timed = re.compile(r"\d+\.\d s")
        self.assertEqual(timed.sub("", re.sub(r"\x1b\[\d+m", "", shaded)), timed.sub("", "\n".join(lines) + "\n"))
        readme = (REPO / "README.md").read_text(encoding="utf-8")                # and the front page shows this page
        for line in lines:
            self.assertIn(timed.split(line)[0].rstrip(), readme)

    def test_the_same_run_is_a_record_a_program_can_read(self) -> None:
        record = json.loads(played(as_json=True))
        self.assertEqual(record["schema"], "TAOS_DEMO_V1")
        self.assertEqual([moment["id"] for moment in record["moments"]], IDEAS)
        runs = [step for moment in record["moments"] for step in moment["steps"] if step["kind"] == "run"]
        named = {step["id"]: step for step in runs if "id" in step}
        self.assertEqual([named[name]["answer"] for name in ("baseline", "style-only", "timing-edited")],
                         ["holds", "holds", "stale"])
        fits = [step["measured"] for step in runs if "measured" in step]
        self.assertEqual([(fit["g"], fit["standard_error"], fit["swings"]) for fit in fits], [(9.82, 0.02, 6), (9.75, 0.02, 6)])
        self.assertEqual([fit["rows"][-1] for fit in fits],
                         [{"length_m": 1.2, "period_s": 2.19}, {"length_m": 1.2, "period_s": 2.21}])
        self.assertEqual((record["commands"], record["checked"]), (len(runs), sum(len(step["expected"]) for step in runs)))
        for step in runs:                                                       # nothing is expected that was not printed
            for words in step["expected"]:
                self.assertIn(words, "\n".join(step["printed"]))

    def test_it_stops_when_the_record_answers_differently(self) -> None:
        script = demo.script

        def hoping_for_another_number(paths, work):
            moments = script(paths, work)
            moments[0].steps[0] = demo.ask("python3", "analysis/fit.py", expect=("g = 9.81",))
            return moments

        with mock.patch.object(demo, "script", hoping_for_another_number), self.assertRaises(TaosError) as stopped:
            played()
        self.assertIn("was expected to answer 'g = 9.81'", str(stopped.exception))
        self.assertIn("g = 9.82 +/- 0.02 m/s^2 from 6 swings", str(stopped.exception))

    def test_the_example_measurement_gives_the_number_the_demo_quotes(self) -> None:
        fit = subprocess.run([sys.executable, str(EXAMPLE / "analysis" / "fit.py")], capture_output=True, text=True)
        self.assertEqual(fit.stdout.strip(), "g = 9.82 +/- 0.02 m/s^2 from 6 swings")
        check = subprocess.run([sys.executable, str(EXAMPLE / "analysis" / "check.py")], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0)


if __name__ == "__main__":
    unittest.main()
