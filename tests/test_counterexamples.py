"""Counterexamples: each test is a case where a record was once relied on without its conditions.

Every test here fails at commit 071a348 and passes on this one. The last two
were found after the release that followed, so they also fail at 89f36ce.
They use only entry points that exist in all three, so the same file can be
run against any of them: `python3 evals/at_revision.py 071a348 89f36ce`.

The common shape: something true under conditions (a date, a scope, the bytes
it tested, an action that was observed) was read later as simply true.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import unittest

from helpers import REPO, cleanup, construct_example, make_home

from taos_core import anchors, bootstrap, changes, claims, control, gates, lessons, lifecycle, replay, rules
from taos_core import tasks as tasks_mod
from taos_core.util import TaosError


def repeat_count(row: dict) -> int:
    """Confirmed repeats of a mistake. The previous release had no such number and reported `hits` as repeats."""
    return row["repeats"] if "repeats" in row else row["hits"]


class Counterexample(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths)
        self.store = tasks_mod.TaskStore(self.paths)
        self.ws = self.tmp / "ws"

    def tearDown(self) -> None:
        cleanup(self.tmp)

    def quotes(self, scope: str, on: str) -> list:
        return [rule["quote"] for rule in rules.governing(self.paths, scope, on=on)]


class TestInstructionsKeepTheirTime(Counterexample):
    def test_a_later_replacement_does_not_erase_the_earlier_answer(self) -> None:
        first = rules.add(self.paths, quote="Use reference A", said_on="2026-01-01", scope="calibration")
        rules.add(self.paths, quote="Use reference B", said_on="2026-02-01", scope="calibration", supersedes=first["id"])
        self.assertEqual(self.quotes("calibration", "2026-01-15"), ["Use reference A"])
        self.assertEqual(self.quotes("calibration", "2026-02-15"), ["Use reference B"])
        self.assertEqual(self.quotes("calibration", "2025-12-31"), [])

    def test_a_replacement_dated_in_the_future_does_not_govern_yet(self) -> None:
        first = rules.add(self.paths, quote="Use reference A", said_on="2026-01-01", scope="calibration")
        rules.add(self.paths, quote="Use reference B", said_on="2099-01-01", scope="calibration", supersedes=first["id"])
        self.assertEqual(self.quotes("calibration", "2026-06-01"), ["Use reference A"])

    def test_a_narrow_exception_leaves_the_general_rule_in_force_elsewhere(self) -> None:
        general = rules.add(self.paths, quote="Label every axis", said_on="2026-01-01", scope="plots")
        rules.add(self.paths, quote="Insets may omit axis labels", said_on="2026-01-10", scope="plots/insets",
                  supersedes=general["id"])
        self.assertEqual(self.quotes("plots/insets", "2026-02-01"), ["Insets may omit axis labels"])
        self.assertEqual(self.quotes("plots/main", "2026-02-01"), ["Label every axis"])

    def test_a_temporary_replacement_gives_the_rule_back_when_it_lapses(self) -> None:
        standing = rules.add(self.paths, quote="Two reviewers", said_on="2026-01-01", scope="release")
        rules.add(self.paths, quote="One reviewer this week", said_on="2026-03-02", scope="release", expires="2026-03-08",
                  supersedes=standing["id"])
        self.assertEqual(self.quotes("release", "2026-03-05"), ["One reviewer this week"])
        self.assertEqual(self.quotes("release", "2026-03-09"), ["Two reviewers"])

    def test_a_date_that_is_not_on_the_calendar_is_refused(self) -> None:
        with self.assertRaises(TaosError):
            rules.add(self.paths, quote="Use reference A", said_on="2026-02-30", scope="calibration")


class TestShownIsNotViolated(Counterexample):
    def _lesson(self, scope: str = "*") -> dict:
        return lessons.add(self.paths, title="Report units", words="Always give the unit.", said_on="2026-01-01",
                           mistake="a bare number", why="a number without a unit cannot be checked", moments=["reply"],
                           scope=scope)

    def test_a_reminder_shown_for_correct_work_is_not_a_repeated_mistake(self) -> None:
        self._lesson()
        for text in ("Distance: 3 m", "Time: 2 s", "Energy: 5 GeV"):
            self.assertEqual(len(lessons.at(self.paths, "reply", agent="codex", text=text)), 1)   # still delivered
        self.assertEqual(sum(repeat_count(row) for row in lessons.repeats(self.paths)), 0)

    def test_a_lesson_for_one_task_does_not_reach_a_task_whose_id_merely_starts_the_same(self) -> None:
        self._lesson(scope="CMP-1")
        self.assertEqual(len(lessons.at(self.paths, "reply", agent="codex", task_id="CMP-1")), 1)
        self.assertEqual(lessons.at(self.paths, "reply", agent="codex", task_id="CMP-10"), [])


class TestAPassIsForWhatItTested(Counterexample):
    def test_a_pass_does_not_cover_a_file_edited_afterwards(self) -> None:
        task = self.store.create(title="Measure the mean", actor="codex")
        self.assertTrue(gates.run(self.paths, task_id=task["id"], agent="codex", workspace=str(self.ws))["ok"])
        self.assertIsNotNone(gates.fresh_pass(self.paths, task["id"]))   # unchanged: the pass may be reused
        (self.ws / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.2.0"\n', encoding="utf-8")
        self.assertIsNone(gates.fresh_pass(self.paths, task["id"]))

    def test_done_cannot_be_reached_by_a_route_that_skips_the_check(self) -> None:
        task = self.store.create(title="Measure the mean", actor="codex")
        with self.assertRaises(TaosError):
            self.store.transition(task["id"], "done", "finished", "codex", evidence="unverified statement")
        gates.run(self.paths, task_id=task["id"], agent="codex", workspace=str(self.ws))
        done = self.store.transition(task["id"], "done", "finished", "codex", evidence="gate run")
        self.assertEqual(done["status"], "done")   # checked work still closes


class TestRecommendedIsNotExecuted(Counterexample):
    def test_an_unobserved_profile_earns_no_credit(self) -> None:
        task = self.store.create(title="Probe", actor="human")
        lifecycle.start(self.paths, agent="codex", task_id=task["id"], session_label="s")
        lifecycle.finish(self.paths, agent="codex", task_id=task["id"], state="review", reason="r", evidence="e",
                         session_label="s", skip_gates=True)
        state = control.rebuild(self.paths)
        credited = sum(profile["n"] for klass in state["classes"].values() for profile in klass["profiles"].values())
        self.assertEqual(credited, 0)
        self.assertEqual(state["episodes"], 1)   # the episode itself is still counted


class TestALeaseEnds(Counterexample):
    def test_a_lapsed_owner_cannot_come_back_after_reassignment(self) -> None:
        store = claims.ClaimStore(self.paths)
        old = store.acquire(agent="codex", scopes=["task:CMP-1"], session_label="a", stale_after_hours=1,
                            now="2026-01-01T00:00:00Z")
        store.acquire(agent="claude", scopes=["task:CMP-1"], session_label="b", now="2026-01-01T05:00:00Z")
        with self.assertRaises(TaosError):
            store.heartbeat(old["id"], "codex", now="2026-01-01T05:01:00Z")
        holders = [claim["agent"] for claim in store.live(now="2026-01-01T05:02:00Z") if "task:CMP-1" in claim["scopes"]]
        self.assertEqual(holders, ["claude"])

    def test_a_lapsed_lease_is_over_even_when_nobody_else_took_the_work(self) -> None:
        store = claims.ClaimStore(self.paths)
        old = store.acquire(agent="codex", scopes=["task:CMP-1"], session_label="a", stale_after_hours=1,
                            now="2026-01-01T00:00:00Z")
        with self.assertRaises(TaosError):                       # a heartbeat renews a promise; it cannot restart a broken one
            store.heartbeat(old["id"], "codex", now="2026-01-01T05:00:00Z")
        self.assertEqual(store.live(now="2026-01-01T05:01:00Z"), [])
        again = store.acquire(agent="codex", scopes=["task:CMP-1"], session_label="a", now="2026-01-01T05:02:00Z")
        self.assertNotEqual(again["id"], old["id"])              # asking again is how the work is taken back up

    def test_a_refused_start_takes_nothing(self) -> None:
        parent = self.store.create(title="Fix the race", actor="codex")
        child = self.store.create(title="Repair the serializer", actor="codex")
        self.store.relate(parent["id"], "blockedBy", child["id"], "codex")
        self.store.transition(parent["id"], "blocked", "blocked by " + child["id"], "codex")
        with self.assertRaises(TaosError):
            lifecycle.start(self.paths, agent="claude", task_id=parent["id"], session_label="s")
        self.assertEqual([c for c in claims.ClaimStore(self.paths).live() if c["agent"] == "claude"], [])


class TestMissingIsNotFalse(Counterexample):
    def test_the_text_false_is_not_read_as_true(self) -> None:
        result = replay.replay([{"load": 9, "harmful": "false"}], field="load", op="at-least", threshold=5)
        self.assertEqual(result["harmful"], 0)

    def test_an_unlabelled_case_is_not_counted_as_harmless(self) -> None:
        result = replay.replay([{"load": 9}], field="load", op="at-least", threshold=5)
        self.assertEqual(result["harmless"], 0)

    def test_a_change_is_not_confirmed_by_a_number_from_nowhere(self) -> None:
        change_id = changes.register_change(
            self.paths, title="cache the inventory", builder="codex", cost="plan time", unit="seconds", baseline=40.0,
            predict_low=2.0, predict_high=8.0, control="files listed", control_baseline=1000.0, control_tolerance=0.0,
            canary="one folder first", rollback="delete the cache file")["id"]
        changes.seal(self.paths, change_id, "codex")
        with self.assertRaises(TaosError):
            changes.score(self.paths, change_id, grader="claude", observed=5.0, control_observed=1000.0)

    def test_a_prediction_cannot_be_rewritten_once_made(self) -> None:
        adjustment = anchors.open_adjustment(self.paths, quantity="ratio", observed=0.9, proposed="rescale", agent="codex")
        anchors.predict(self.paths, adjustment["id"], low=0.95, high=1.05)
        with self.assertRaises(TaosError):
            anchors.predict(self.paths, adjustment["id"], low=0.85, high=0.95)


class TestTheBasisIsWhatWasRead(Counterexample):
    """A result is filed under some bytes. These are two ways the check could read others."""

    def check(self, **said: object) -> None:
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        config["basis"] = {"domains": {"inputs": ["data/*"], "code": ["src/*"]}}
        config["gates"] = [dict({"name": "fit", "command": "cat data/run.csv", "depends_on": ["inputs"]}, **said)]
        self.paths.config_file.write_text(json.dumps(config), encoding="utf-8")
        for name, text in (("data/run.csv", "9.79\n"), ("src/scale.txt", "1.002\n")):
            (self.ws / name).parent.mkdir(exist_ok=True)
            if not (self.ws / name).exists():
                (self.ws / name).write_text(text, encoding="utf-8")

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_an_input_git_ignores_is_still_part_of_what_a_check_stood_on(self) -> None:
        subprocess.run(["git", "init", "-q"], cwd=str(self.ws), check=True, capture_output=True)
        (self.ws / ".gitignore").write_text("data/\n", encoding="utf-8")     # as measured data usually is
        self.check()
        self.assertTrue(gates.run(self.paths, task_id="CMP-1", agent="codex")["ok"])
        self.assertIsNotNone(gates.fresh_pass(self.paths, "CMP-1"))
        (self.ws / "data" / "run.csv").write_text("9.81\n", encoding="utf-8")
        self.assertIsNone(gates.fresh_pass(self.paths, "CMP-1"))

    def test_a_check_cannot_pass_on_a_file_it_did_not_declare(self) -> None:
        self.check(command="cat data/run.csv src/scale.txt", isolated=True)
        self.assertFalse(gates.run(self.paths, task_id="CMP-1", agent="codex")["ok"])
        self.check(command="cat data/run.csv src/scale.txt", isolated=True, depends_on=["inputs", "code"])
        self.assertTrue(gates.run(self.paths, task_id="CMP-1", agent="codex")["ok"])

    def test_an_isolated_check_does_not_see_the_environment(self) -> None:
        os.environ["TAOS_TUNING"] = "1"
        self.addCleanup(os.environ.pop, "TAOS_TUNING", None)
        reads_it = 'test -n "$TAOS_TUNING" && cat data/run.csv'
        self.check(command=reads_it)
        self.assertTrue(gates.run(self.paths, task_id="CMP-1", agent="codex")["ok"])      # in the open, the variable is there
        self.check(command=reads_it, isolated=True)
        self.assertFalse(gates.run(self.paths, task_id="CMP-1", agent="codex")["ok"])     # isolated, it is not
        self.check(command="TAOS_TUNING=1; " + reads_it, isolated=True)
        self.assertTrue(gates.run(self.paths, task_id="CMP-1", agent="codex")["ok"])      # written into the command, it is the check

    def test_the_record_says_what_was_closed_and_it_was(self) -> None:
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        self.check(isolated=True)
        closed = gates.run(self.paths, task_id="CMP-1", agent="codex")["results"][0]["closed"]
        self.assertEqual(closed[:2], ["files", "environment"])
        self.assertEqual("network" in closed, gates.closes())                   # the record says no more than was in force
        by_absolute_path = "cat '{0}'".format(self.ws / "src" / "scale.txt")       # in the workspace, and not declared
        over_the_network = "\"{0}\" -c \"import socket; socket.create_connection(('127.0.0.1', {1}), timeout=2)\"".format(
            sys.executable, listener.getsockname()[1])
        for reach in (by_absolute_path, over_the_network):
            self.check(command="cat data/run.csv && " + reach, isolated=True)
            self.assertEqual(gates.run(self.paths, task_id="CMP-1", agent="codex")["ok"], not gates.closes())
        self.check(isolated="strict")                                            # strict does not run where they stay open
        self.assertEqual(gates.run(self.paths, task_id="CMP-1", agent="codex")["ok"], gates.closes())

    def test_setup_can_say_what_a_check_reads(self) -> None:
        answers = json.loads((REPO / "bootstrap" / "answers.example.json").read_text(encoding="utf-8"))
        answers["domains"] = [{"name": "analysis", "patterns": ["src/*", "data/*"]}]
        answers["gates"] = [{"name": "fit", "command": "python3 check.py", "depends_on": ["analysis"], "isolated": True}]
        about_these = [problem for problem in bootstrap.validate_answers(answers, self.paths)
                       if any(word in problem for word in ("domains", "gates", "depends_on", "isolated"))]
        self.assertEqual(about_these, [])
        config = bootstrap._config_from(answers)
        self.assertEqual(config["basis"]["domains"], {"analysis": ["src/*", "data/*"]})
        self.assertEqual(config["gates"][0]["depends_on"], ["analysis"])
        self.assertIs(config["gates"][0]["isolated"], True)


if __name__ == "__main__":
    unittest.main()
