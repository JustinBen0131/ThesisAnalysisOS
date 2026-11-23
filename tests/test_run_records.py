"""Two cases the lifetime lab found: checks that share one command, and many runs in one second."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import REPO, cleanup, make_home
from taos_core import basis, gates, use

COMMAND = "python3 analysis/check.py"


class RunRecords(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        self.addCleanup(cleanup, self.tmp)
        self.work = Path(tempfile.mkdtemp()).resolve() / "my-analysis"
        self.addCleanup(shutil.rmtree, str(self.work.parent), True)
        shutil.copytree(str(REPO / "examples" / "measurement"), str(self.work), ignore=shutil.ignore_patterns("__pycache__"))

    def states(self, task: str):
        return {verdict["gate"]: verdict["state"] for verdict in gates.standing(self.paths, task)}

    def test_two_checks_that_share_one_command_each_keep_their_own_name(self) -> None:
        task = use.use(self.paths, self.work, ["first: " + COMMAND, "second: " + COMMAND])["task"]
        again = gates.run(self.paths, task_id=task, agent="human")
        self.assertEqual([result["name"] for result in again["results"]], ["first", "second"])
        self.assertEqual(self.states(task), {"first": basis.HOLDS, "second": basis.HOLDS})
        (self.work / "notes.txt").write_text("a file the checks have not seen\n")
        self.assertEqual(self.states(task), {"first": basis.STALE, "second": basis.STALE},
                         "a changed file makes both stale; neither is 'not part of the latest run'")

    def test_a_run_recorded_under_the_other_name_still_answers_for_both(self) -> None:
        task = use.use(self.paths, self.work, ["first: " + COMMAND, "second: " + COMMAND])["task"]
        newest = gates.latest(self.paths, task)
        folder = self.paths.state / "gates"
        for path in folder.glob("{0}_*.json".format(task)):       # the record as the earlier program wrote it
            record = json.loads(path.read_text())
            for result in record["results"]:
                result["name"] = "first"
            path.write_text(json.dumps(record))
        self.assertIsNotNone(newest)
        (self.work / "notes.txt").write_text("a file the checks have not seen\n")
        self.assertEqual(self.states(task), {"first": basis.STALE, "second": basis.STALE})

    def test_the_latest_of_eleven_runs_in_one_second_is_the_eleventh(self) -> None:
        task = use.use(self.paths, self.work, ["check: " + COMMAND])["task"]
        with mock.patch("taos_core.gates.utc_now", return_value="2099-01-01T00:00:00Z"):      # after the set-up run
            for _ in range(10):
                gates.run(self.paths, task_id=task, agent="human", force=True)
            (self.work / "notes.txt").write_text("written before the eleventh run\n")
            eleventh = gates.run(self.paths, task_id=task, agent="human", force=True)
        self.assertTrue(eleventh["path"].endswith("_11.json"), eleventh["path"])
        self.assertEqual(gates.latest(self.paths, task)["results"][0]["basis"], eleventh["results"][0]["basis"])
        names = ["T-1_20260101T000000Z.json"] + ["T-1_20260101T000000Z_{0}.json".format(n) for n in (10, 2, 9, 11)]
        ordered = sorted((Path(name) for name in names + ["T-1_20260101T000001Z.json"]), key=gates._run_order)
        self.assertEqual([path.stem.split("Z")[1] for path in ordered[:-1]], ["", "_2", "_9", "_10", "_11"])
        self.assertEqual(ordered[-1].name, "T-1_20260101T000001Z.json")


if __name__ == "__main__":
    unittest.main()
