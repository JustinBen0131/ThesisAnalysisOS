"""The demo is the first thing a reader runs, so it is tested like anything else."""

from __future__ import annotations

import io
import json
import re
import shlex
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import REPO

from taos_core import demo, page
from taos_core.util import TaosError

EXAMPLE = REPO / "examples" / "measurement"
IDEAS = ["standing", "reuse", "instructions", "acceptance", "reminder", "isolation"]


def played(**how) -> str:
    out = io.StringIO()
    with mock.patch.object(demo, "launcher", return_value="./taos"):   # as a reader who typed ./taos sees it
        assert demo.run(out=out, **how) == 0
    return out.getvalue()


class TestDemo(unittest.TestCase):
    def test_it_runs_from_a_clean_copy_and_shows_each_idea_with_real_output(self) -> None:
        text = played(full=True)
        for phrase in (
            "g = 9.82 +/- 0.02 m/s^2 from 6 swings",                            # the number the task closes on
            "stale    check fit: analysis changed: data/swings.csv",            # the file that changed is named
            "g = 9.75 +/- 0.02 m/s^2 from 6 swings",                            # and the flag was right: g moved
            "not run again: nothing it tested has changed",                     # asked by two tasks, executed once
            "\"Use the tape-measured lengths\"",                                # what governed on the earlier date
            "\"Use the laser-measured lengths\"",                               # and on the later one
            "stale    acceptance:",                                             # a person's acceptance is of one version
            "told:      \"Quote g with its uncertainty, never alone\"",         # delivered to the next agent
            "0 repeated, 0 followed, 1 not judged, of 1 times shown",           # shown is not repeated
            "fails    style        ran now and failed (exit 2)",                # it read a file it did not declare
            "A file it could not find is one it did not declare.",              # and the answer says so
            "holds    style        ran now and passed (exit 0)",                # declared, the same check passes
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
                              ("holds", "not run twice"), ("stale", "the acceptance was of the old version"),
                              ("fails", "declared only the analysis"), ("holds", "the same check passes")):
            self.assertTrue(any(line.split()[0] == answer and about in line for line in lines if line.strip()), about)
        shaded = played(full=False, color=True)
        self.assertIn("\x1b[33mstale", shaded)                                  # the answer is shaded, the words are not
        timed = re.compile(r"\d+\.\d s")
        self.assertEqual(timed.sub("", re.sub(r"\x1b\[\d+m", "", shaded)), timed.sub("", "\n".join(lines) + "\n"))
        readme = (REPO / "README.md").read_text(encoding="utf-8")                # and the front page shows this page
        for line in lines:
            self.assertIn(timed.split(line)[0].rstrip(), readme)

    def test_the_opener_draws_the_name_in_a_box_and_falls_back_to_plain_letters(self) -> None:
        lines = played(full=False).splitlines()
        self.assertEqual([len(line) for line in lines[:5]], [80] * 5)           # a box, closed on every side
        self.assertEqual((lines[0][0], lines[0][-1], lines[4][0], lines[4][-1]), ("┌", "┐", "└", "┘"))
        self.assertEqual([line[3:18] for line in lines[1:4]], list(page.MARK))  # the mark, three rows high
        self.assertIn("holds, stale, fails or unknown", lines[3])               # beside the four answers it stands for
        shaded = played(full=False, color=True).splitlines()[1]
        self.assertEqual(re.findall(r"\x1b\[(\d+)m[╺┏]", shaded), ["32", "33", "31", "2"])   # one shade for each letter
        narrow = played(full=False, width=60).splitlines()                      # a narrow window gets it without the box
        self.assertEqual((narrow[0], max(len(line) for line in narrow) <= 60), (page.MARK[0], True))
        plain = io.TextIOWrapper(io.BytesIO(), encoding="ascii")                # a stream that cannot draw the box
        self.assertEqual(demo.run(out=plain, full=False), 0)
        plain.flush()
        self.assertIn("|  TAOS ", plain.buffer.getvalue().decode("ascii"))

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

    def test_kept_it_ends_with_lines_a_reader_can_paste_and_each_shows_what_it_says(self) -> None:
        text = played(keep=True, width=80, color=False)
        printed = [line[2:] for line in text.split("\n\n")[-1].splitlines()]    # the block the reader is told to paste
        kept = Path(shlex.split(printed[0])[1])
        self.addCleanup(shutil.rmtree, str(kept.parent), ignore_errors=True)
        self.assertEqual((printed[0].split()[0], printed[1:]), ("cd", [command for command, _ in demo.BY_HAND]),
                         "bare lines: pasting one, or all of them, runs exactly what is shown")
        said = []
        for command in printed[1:]:                                             # each line as printed, through a shell
            self.assertLessEqual(len(command) + 2, 80, "a line to paste fits the screen")
            done = subprocess.run(command, shell=True, cwd=str(kept), capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            said.append(done.stdout + done.stderr)
        fit = [re.search(r"^\s+(\w+)\s+fit\s", output, re.M) for output in said]      # the answer leads the row
        self.assertEqual((fit[0].group(1), fit[2].group(1)), ("holds", "stale"), "one swing by hand turns the fit stale")
        self.assertRegex(said[3], r"holds\s+fit\s+ran now and passed", "run by hand, the fit passes again")
        self.assertEqual(subprocess.run("../os/taos gate show --task PEN-2", shell=True, cwd=str(kept), capture_output=True,
                                        text=True).stdout.count("holds"), 2, "run again, both checks hold on the new data")
        self.assertIn("PEN-1 does not stand as recorded", said[4])


if __name__ == "__main__":
    unittest.main()
