"""`taos why`: every record a task rests on, read back against the present."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from helpers import cleanup, construct_example, make_home

from taos_core import basis, gates, lessons, lifecycle, rules, standing
from taos_core import tasks as tasks_mod
from taos_core.cli import main as cli
from taos_core.util import TaosError


def part(view: dict, kind: str) -> dict:
    return [item for item in view["parts"] if item["kind"] == kind][0]


class Home(unittest.TestCase):
    GATES = [{"name": "ok", "command": "true"}]

    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths, gates=self.GATES)
        self.store = tasks_mod.TaskStore(self.paths)
        self.ws = self.tmp / "ws"

    def tearDown(self) -> None:
        cleanup(self.tmp)

    def close(self, task_id: str = "CMP-1") -> None:
        gates.run(self.paths, task_id=task_id, agent="codex")
        self.store.transition(task_id, "done", "the fixture compiles fast", "codex", evidence="commit abc")

    def say(self, *argv: str) -> str:
        out = io.StringIO()
        with redirect_stdout(out):
            self.code = cli(["--home", str(self.paths.home)] + list(argv))
        return out.getvalue()


class TestWhy(Home):
    def test_an_open_task_claims_nothing(self) -> None:
        view = standing.of_task(self.paths, "CMP-1")
        self.assertFalse(view["closed"])
        self.assertEqual((part(view, "check")["state"], part(view, "check")["reason"]), (basis.UNKNOWN, "never run for this task"))
        self.assertIn("nothing is claimed finished yet", standing.text(view))

    def test_closed_work_stands_until_a_file_changes_and_the_reason_names_the_file(self) -> None:
        self.close()
        view = standing.of_task(self.paths, "CMP-1")
        self.assertEqual((view["state"], [item["kind"] for item in view["parts"]]), (basis.HOLDS, ["closure", "check"]))
        self.assertIn("stands as recorded. No person has accepted it yet.", standing.text(view))
        (self.ws / "Cargo.toml").write_text("edited after the check", encoding="utf-8")
        view = standing.of_task(self.paths, "CMP-1")
        self.assertEqual(view["state"], basis.STALE)
        self.assertIn("Cargo.toml", part(view, "check")["reason"])
        self.assertTrue(any("taos gate run --task CMP-1" in step for step in view["next"]))
        self.assertEqual(part(view, "closure")["state"], basis.HOLDS)   # who closed it, and under which instructions, is unchanged

    def test_acceptance_is_of_one_version_and_does_not_carry_over(self) -> None:
        self.close()
        with self.assertRaises(TaosError):
            self.store.accept("CMP-1", "codex")                         # a check passing is not a person accepting
        self.store.accept("CMP-1", "human", note="looked at the timing table")
        self.assertEqual(part(standing.of_task(self.paths, "CMP-1"), "acceptance")["state"], basis.HOLDS)
        (self.ws / "Cargo.toml").write_text("edited after acceptance", encoding="utf-8")
        gates.run(self.paths, task_id="CMP-1", agent="codex")           # the checks pass again on the new version
        view = standing.of_task(self.paths, "CMP-1")
        self.assertEqual(part(view, "check")["state"], basis.HOLDS)
        self.assertEqual(part(view, "acceptance")["state"], basis.STALE)
        self.assertIn("Cargo.toml", part(view, "acceptance")["reason"])
        self.assertEqual(view["state"], basis.STALE)
        self.store.accept("CMP-1", "human")
        self.assertEqual(standing.of_task(self.paths, "CMP-1")["state"], basis.HOLDS)

    def test_a_waived_closure_is_unverified_until_the_check_runs(self) -> None:
        self.store.transition("CMP-1", "done", "shipping", "codex", evidence="commit abc", waive="CI is down")
        closure = part(standing.of_task(self.paths, "CMP-1"), "closure")
        self.assertEqual(closure["state"], basis.UNKNOWN)
        self.assertIn("without a holding check (CI is down)", closure["reason"])
        gates.run(self.paths, task_id="CMP-1", agent="codex")
        closure = part(standing.of_task(self.paths, "CMP-1"), "closure")
        self.assertEqual(closure["state"], basis.HOLDS)
        self.assertIn("the checks have passed since", closure["reason"])

    def test_a_new_instruction_makes_the_closure_stale_and_is_quoted(self) -> None:
        rules.add(self.paths, quote="Benchmark on the large fixture", said_on="2026-01-01", scope="CMP-1")
        self.close()
        view = standing.of_task(self.paths, "CMP-1")
        self.assertEqual(view["state"], basis.HOLDS)
        self.assertEqual([rule["quote"] for rule in view["instructions"]], ["Benchmark on the large fixture"])
        rules.add(self.paths, quote="Report the median of five runs", said_on=basis.today(), scope="CMP-1")
        closure = part(standing.of_task(self.paths, "CMP-1"), "closure")
        self.assertEqual(closure["state"], basis.STALE)
        self.assertIn("Report the median of five runs", closure["reason"])
        self.assertIn("governs now and is not one this was recorded under", closure["reason"])

    def test_a_work_product_is_current_while_its_declared_inputs_are_the_same_bytes(self) -> None:
        (self.ws / "bench.csv").write_text("run,seconds\n1,9.2\n", encoding="utf-8")
        self.store.add_evidence("CMP-1", "plots/timing.png", "codex", depends_on=["bench.csv", "Cargo.toml"])
        self.store.add_evidence("CMP-1", "notes/summary.md", "codex", artifact=True)
        self.store.add_evidence("CMP-1", "plots/later.png", "codex", depends_on=["not-there-yet.csv"])
        states = {item["name"]: item for item in standing.of_task(self.paths, "CMP-1")["parts"] if item["kind"] == "artifact"}
        self.assertEqual(states["plots/timing.png"]["state"], basis.HOLDS)
        self.assertEqual(states["notes/summary.md"]["state"], basis.UNKNOWN)      # inputs never declared: unknown, not fine
        self.assertEqual(states["plots/later.png"]["state"], basis.UNKNOWN)       # an input that could not be read then
        (self.ws / "bench.csv").write_text("run,seconds\n1,11.8\n", encoding="utf-8")
        timing = [item for item in standing.of_task(self.paths, "CMP-1")["parts"] if item["name"] == "plots/timing.png"][0]
        self.assertEqual((timing["state"], timing["reason"]), (basis.STALE, "bench.csv changed"))
        (self.ws / "bench.csv").unlink()
        timing = [item for item in standing.of_task(self.paths, "CMP-1")["parts"] if item["name"] == "plots/timing.png"][0]
        self.assertEqual(timing["reason"], "bench.csv is gone")

    def test_a_lapsed_lease_is_stale(self) -> None:
        lifecycle.start(self.paths, agent="codex", task_id="CMP-1", session_label="CMP-1 | speed")
        self.assertEqual(part(standing.of_task(self.paths, "CMP-1"), "lease")["state"], basis.HOLDS)
        data = json.loads(self.paths.claims_file.read_text(encoding="utf-8"))
        for claim in data["claims"]:
            claim["heartbeat_at"] = "2020-01-01T00:00:00Z"
        self.paths.claims_file.write_text(json.dumps(data), encoding="utf-8")
        lease = part(standing.of_task(self.paths, "CMP-1"), "lease")
        self.assertEqual(lease["state"], basis.STALE)
        self.assertIn("the work may have stopped", lease["reason"])
        self.assertTrue(any(row["kind"] == "lease" for row in standing.everything(self.paths)["rows"]))

    def test_the_whole_home_lists_only_what_no_longer_holds(self) -> None:
        self.close()
        found = standing.everything(self.paths)
        self.assertEqual((found["closed"], found["standing"], found["unaccepted"]), (1, 1, ["CMP-1"]))
        self.assertEqual([row for row in found["rows"] if row["task"]], [])
        self.say("why", "CMP-1", "--check")
        self.assertEqual(self.code, 0)
        (self.ws / "Cargo.toml").write_text("edited", encoding="utf-8")
        text = self.say("why", "--check")
        self.assertEqual(self.code, 1)
        self.assertIn("0 of 1 closed task(s) stand as recorded.", text)
        self.assertIn("CMP-1", text)
        self.assertEqual(json.loads(self.say("why", "CMP-1", "--json"))["state"], basis.STALE)


class TestSharedResult(Home):
    """A check result belongs to the bytes it tested, not to the task that asked."""

    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        self.count = self.tmp / "count"                       # outside the workspace: it counts real executions
        construct_example(self.tmp, self.paths, gates=[{"name": "count", "command": "echo x >> '{0}'".format(self.count)}])
        self.store = tasks_mod.TaskStore(self.paths)
        self.ws = self.tmp / "ws"
        self.other = self.store.create(title="Trim the allocator", actor="codex")["id"]

    def executions(self) -> int:
        return len(self.count.read_text(encoding="utf-8").splitlines()) if self.count.exists() else 0

    def test_two_tasks_share_one_verified_result_while_the_files_are_the_same(self) -> None:
        gates.run(self.paths, task_id="CMP-1", agent="codex")
        shared = gates.standing(self.paths, self.other)[0]
        self.assertEqual(shared["state"], basis.HOLDS)
        self.assertIn("for CMP-1", shared["reason"])
        record = gates.run(self.paths, task_id=self.other, agent="claude")
        self.assertEqual((record["reused"], self.executions()), (["count"], 1))     # asked twice, executed once
        self.store.transition(self.other, "done", "trimmed", "claude", evidence="commit def")

    def test_a_change_makes_both_stale_and_one_run_restores_both(self) -> None:
        gates.run(self.paths, task_id="CMP-1", agent="codex")
        (self.ws / "Cargo.toml").write_text("edited", encoding="utf-8")
        self.assertEqual([gates.standing(self.paths, task)[0]["state"] for task in ("CMP-1", self.other)],
                         [basis.STALE, basis.UNKNOWN])                             # one ran before the change, one never ran
        with self.assertRaises(TaosError):
            self.store.transition(self.other, "done", "trimmed", "claude", evidence="commit def")
        gates.run(self.paths, task_id=self.other, agent="claude")
        self.assertEqual([gates.standing(self.paths, task)[0]["state"] for task in ("CMP-1", self.other)],
                         [basis.HOLDS, basis.HOLDS])
        self.assertEqual(self.executions(), 2)

    def test_force_reruns_and_a_failure_on_these_bytes_is_shared_too(self) -> None:
        gates.run(self.paths, task_id="CMP-1", agent="codex")
        gates.run(self.paths, task_id="CMP-1", agent="codex", force=True)
        self.assertEqual(self.executions(), 2)
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        config["gates"] = [{"name": "count", "command": "false"}]
        self.paths.config_file.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(gates.standing(self.paths, "CMP-1")[0]["reason"], "the check itself changed since it ran")
        gates.run(self.paths, task_id="CMP-1", agent="codex")
        self.assertEqual(gates.standing(self.paths, self.other)[0]["state"], basis.FAILS)


class TestDelivery(Home):
    """What governs a task and what was learned reach the agent in the task view, in the original words."""

    def test_start_shows_what_stands_what_was_told_and_what_was_learned(self) -> None:
        rules.add(self.paths, quote="Benchmark on the large fixture", said_on="2026-01-01", scope="CMP-1")
        rules.add(self.paths, quote="Never touch the parser", said_on="2026-01-01", scope="CMP-2")
        lesson = lessons.add(self.paths, title="Warm the cache first", words="you timed a cold cache again",
                             said_on="2026-02-03", mistake="timed a cold cache", why="the number was 4x too slow",
                             moments=["join"], scope="CMP")
        data = lifecycle.start(self.paths, agent="codex", task_id="CMP-1", session_label="CMP-1 | speed")
        text = lifecycle.capsule_text(data)
        self.assertIn("stands:    unknown  check ok: never run for this task", text)
        self.assertIn("told:      \"Benchmark on the large fixture\"", text)
        self.assertNotIn("Never touch the parser", text)                           # another task's instruction is not delivered
        self.assertIn("lesson:    Warm the cache first: \"you timed a cold cache again\"", text)
        self.assertIn(data["lessons"][0]["case"], text)
        lifecycle.capsule(self.paths, "CMP-1")                                      # reading the view again is not a new exposure
        row = [item for item in lessons.repeats(self.paths) if item["id"] == lesson["id"]][0]
        self.assertEqual((row["exposures"], row["repeats"], row["unknown"]), (1, 0, 1))

    def test_finish_reports_what_the_closure_stands_on(self) -> None:
        lifecycle.start(self.paths, agent="codex", task_id="CMP-1", session_label="CMP-1 | speed")
        gates.run(self.paths, task_id="CMP-1", agent="codex")
        result = lifecycle.finish(self.paths, agent="codex", task_id="CMP-1", state="review", reason="ready to look at",
                                  evidence="commit abc", session_label="CMP-1 | speed")
        self.assertEqual(result["standing"]["state"], basis.HOLDS)
        self.assertEqual([item["kind"] for item in result["standing"]["parts"]], ["closure", "check"])


class TestDomains(unittest.TestCase):
    """Declaring what a check reads lets an unrelated change leave it alone, and keeps an undeclared change visible."""

    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths)
        self.ws = self.tmp / "ws"
        for name in ("src/fit.py", "figs/style.txt", "notes.md"):
            (self.ws / name).parent.mkdir(exist_ok=True)
            (self.ws / name).write_text("first", encoding="utf-8")
        self.configure({"domains": {"analysis": ["src/*"], "figures": ["figs/*"]}})
        gates.run(self.paths, task_id="CMP-1", agent="codex")

    def tearDown(self) -> None:
        cleanup(self.tmp)

    def configure(self, settings: dict) -> None:
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        config["basis"] = settings
        config["gates"] = [{"name": "fit", "command": "true", "depends_on": ["analysis"]}]
        self.paths.config_file.write_text(json.dumps(config), encoding="utf-8")

    def fit(self) -> dict:
        return gates.standing(self.paths, "CMP-1")[0]

    def test_a_presentation_change_does_not_rerun_numerical_work(self) -> None:
        (self.ws / "figs" / "style.txt").write_text("second", encoding="utf-8")
        self.assertEqual(self.fit()["state"], basis.HOLDS)

    def test_a_change_to_what_it_reads_makes_it_stale(self) -> None:
        (self.ws / "src" / "fit.py").write_text("second", encoding="utf-8")
        self.assertEqual((self.fit()["state"], self.fit()["reason"]), (basis.STALE, "analysis changed: src/fit.py"))

    def test_a_change_nobody_declared_is_unknown_and_never_rounded_to_fine(self) -> None:
        (self.ws / "notes.md").write_text("second", encoding="utf-8")
        self.assertEqual(self.fit()["state"], basis.UNKNOWN)
        self.assertIn("outside every declared domain", self.fit()["reason"])

    def test_an_isolated_check_sees_only_what_it_declared_and_leaves_nothing_behind(self) -> None:
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        config["gates"] = [{"name": "fit", "depends_on": ["analysis"], "isolated": True,
                            "command": "test -f src/fit.py && test ! -e figs/style.txt && touch made.txt"}]
        self.paths.config_file.write_text(json.dumps(config), encoding="utf-8")
        self.assertTrue(gates.run(self.paths, task_id="CMP-1", agent="codex")["ok"])
        self.assertFalse((self.ws / "made.txt").exists())
        self.assertIn("with only the files it declared present", self.fit()["reason"])
        self.assertEqual(gates.run(self.paths, task_id="CMP-1", agent="codex")["reused"], ["fit"])
        (self.ws / "figs" / "style.txt").write_text("second", encoding="utf-8")
        self.assertEqual(self.fit()["state"], basis.HOLDS)

    def test_a_failure_in_isolation_says_what_was_present(self) -> None:
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        config["gates"] = [{"name": "fit", "depends_on": ["analysis"], "isolated": True, "command": "cat figs/style.txt"}]
        self.paths.config_file.write_text(json.dumps(config), encoding="utf-8")
        record = gates.run(self.paths, task_id="CMP-1", agent="codex")
        self.assertFalse(record["ok"])
        self.assertIn("it could read only analysis and the files no domain claims.", record["results"][0]["tail"])

    def test_a_check_that_names_an_undeclared_domain_is_refused_not_trusted_forever(self) -> None:
        from taos_core import config as config_mod

        self.configure({"domains": {"figures": ["figs/*"]}})
        self.assertEqual(self.fit()["state"], basis.UNKNOWN)
        self.assertIn("does not declare", self.fit()["reason"])
        problems = config_mod.validate(config_mod.load(self.paths))
        self.assertTrue(any("depends_on names analysis" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
