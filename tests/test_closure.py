"""Closure contracts, validity-aware artifacts, priors from answers, and the guidance a first-timer gets."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from helpers import cleanup, construct_example, make_home, REPO

from taos_core import config as config_mod
from taos_core import control as control_mod
from taos_core import lifecycle as lifecycle_mod
from taos_core import store as store_mod
from taos_core import tasks as tasks_mod
from taos_core.cli import main as cli
from taos_core.util import TaosError


class TestClosureAndArtifacts(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths)
        self.store = tasks_mod.TaskStore(self.paths)

    def tearDown(self) -> None:
        cleanup(self.tmp)

    def test_task_carries_closure_contract_and_old_tasks_stay_valid(self) -> None:
        seeded = self.store.get("CMP-1")
        self.assertEqual(seeded["done_when"], "the large fixture compiles in under 10s on CI, three runs in a row")
        self.assertTrue(seeded["verification"])
        bare = self.store.create(title="Fix the login race", actor="codex")
        self.assertEqual(bare["done_when"], "")
        self.store.update(bare["id"], {"done_when": "the reproduction no longer occurs and the auth tests pass", "verification": "tests/auth/login_race.rs"}, "codex")
        self.assertIn("reproduction", self.store.get(bare["id"])["done_when"])
        # a pre-contract task row (no fields at all) still loads and prints
        data = self.store.load()
        data["tasks"][bare["id"]].pop("done_when")
        data["tasks"][bare["id"]].pop("verification")
        store_mod.atomic_write_json(self.paths.tasks_file, data)
        self.assertEqual(cli(["--home", str(self.paths.home), "task", "show", bare["id"]]), 0)
        self.assertEqual(cli(["--home", str(self.paths.home), "task", "create", "--agent", "codex", "--title", "x", "--done-when", "y", "--verification", "z"]), 0)

    def test_child_from_independent_blocker_keeps_parent_blocked(self) -> None:
        parent = self.store.create(title="Fix the login race", actor="codex", done_when="reproducer passes")
        child = self.store.create(title="Repair the shared session serializer", actor="codex", parent_id=parent["id"], done_when="all five call sites round-trip")
        self.store.relate(parent["id"], "blockedBy", child["id"], "codex")
        self.assertEqual(self.store.blockers(parent["id"]), [child["id"]])
        with self.assertRaises(TaosError):
            self.store.transition(parent["id"], "blocked", "blocked by " + child["id"], "codex")
            lifecycle_mod.start(self.paths, agent="claude", task_id=parent["id"], session_label="s")
        self.store.transition(child["id"], "done", "fixed", "codex", evidence="commit abc")
        self.assertEqual(self.store.blockers(parent["id"]), [])

    def test_artifact_validity_contract(self) -> None:
        task = self.store.create(title="Build the reproducer", actor="codex")
        self.store.add_evidence(task["id"], "tests/auth/login_race.rs", "codex", note="reproducer", artifact=True)
        row = self.store.get(task["id"])["evidence"][-1]
        self.assertTrue(row["artifact"]["valid"])
        self.assertFalse(row["artifact"]["dependencies_known"])   # unknown stays unknown
        self.assertEqual(row["artifact"]["depends_on"], [])
        self.store.add_evidence(task["id"], "scripts/bench.sh", "codex", depends_on=["Cargo.toml", "tests/fixtures/large.src"])
        row = self.store.get(task["id"])["evidence"][-1]
        self.assertTrue(row["artifact"]["dependencies_known"])
        self.store.invalidate_artifact(task["id"], "scripts/bench.sh", "large.src regenerated", "claude")
        row = self.store.get(task["id"])["evidence"][-1]
        self.assertFalse(row["artifact"]["valid"])
        self.assertEqual(row["artifact"]["invalidated"]["reason"], "large.src regenerated")
        with self.assertRaises(TaosError):
            self.store.invalidate_artifact(task["id"], "nope", "x", "claude")
        # reuse is never counted as causal benefit: the controller records it as unavailable
        capsule = lifecycle_mod.start(self.paths, agent="codex", task_id=task["id"], session_label="s")
        result = lifecycle_mod.finish(self.paths, agent="codex", task_id=task["id"], state="review", reason="r", evidence="e", session_label="s", skip_gates=True)
        vector = result["control"]["vector"]
        self.assertIsNone(vector["reuse"])
        self.assertEqual(vector["provenance"]["reuse"], "unavailable")
        self.assertEqual(vector["provenance"]["gate_fail"], "observed")
        self.assertIsNotNone(vector["controller_seconds"])   # the controller charges itself

    def test_priors_come_from_answers_and_probe_is_tagged(self) -> None:
        config = config_mod.load(self.paths)
        self.assertEqual(config["resources"]["compute"], "normal")
        self.assertEqual(config["preference"]["exploration"], "balanced")
        self.assertIsNone(config["resources"]["context_available"])       # never invented
        self.assertNotEqual(config["resources"]["context_working"], config["resources"]["context_reserve"])
        config["preference"]["exploration"] = "exploratory"
        config["resources"]["compute"] = "constrained"
        store_mod.atomic_write_json(self.paths.config_file, config)
        state = control_mod.rebuild(self.paths, write=True)
        self.assertAlmostEqual(state["params"]["beta"], 0.8)
        self.assertAlmostEqual(state["params"]["compute_bias"], -0.1)
        # drive a class until an under-sampled profile is probed; that episode is tagged comparative
        for index in range(4):
            task = self.store.create(title="Probe task {0}".format(index), actor="human", labels=["probe"])
            lifecycle_mod.start(self.paths, agent="codex", task_id=task["id"], session_label="s")
            lifecycle_mod.finish(self.paths, agent="codex", task_id=task["id"], state="review", reason="r", evidence="e", session_label="s", skip_gates=True)
        opens = [r for r in store_mod.read_jsonl(self.paths.events_file) if r.get("type") == "control_open"]
        self.assertIn("evidence_kind", opens[-1])
        kinds = {r["evidence_kind"] for r in opens}
        self.assertTrue(kinds <= {"observational", "probe"})
        self.assertIn("probe(s)", control_mod.status_line(self.paths))

    def test_old_config_without_resources_or_preference(self) -> None:
        config = config_mod.load(self.paths)
        config.pop("resources", None)
        config.pop("preference", None)
        store_mod.atomic_write_json(self.paths.config_file, config)
        state = control_mod.rebuild(self.paths, write=True)
        self.assertAlmostEqual(state["params"]["beta"], 0.5)
        self.assertAlmostEqual(state["params"]["compute_bias"], 0.0)
        self.assertEqual(config_mod.validate(config_mod.load(self.paths)), [])

    def test_bootstrap_seeds_done_when_optionally(self) -> None:
        answers = json.loads((REPO / "bootstrap" / "answers.example.json").read_text(encoding="utf-8"))
        with_closure = [t for t in answers["first_tasks"] if t.get("done_when")]
        without = [t for t in answers["first_tasks"] if not t.get("done_when")]
        self.assertTrue(with_closure and without)
        for task in self.store.list():
            self.assertIn("done_when", task)


class TestFirstTimerGuidance(unittest.TestCase):
    def test_guidance_exists_at_point_of_need_not_as_a_manual(self) -> None:
        questions = (REPO / "bootstrap" / "QUESTIONS.md").read_text(encoding="utf-8")
        ask = re.search(r"<!-- ASK:.*?-->(.*?)<!-- /ASK -->", questions, re.DOTALL).group(1)
        self.assertIn("what done looks like", ask)
        self.assertIn("optional", ask)
        for jargon in ("done_when", "blockedBy", "parent_id", "closure contract"):
            self.assertNotIn(jargon, ask)
        reference = (REPO / "bootstrap" / "REFERENCE.md").read_text(encoding="utf-8")
        self.assertIn("Turning intent into a closure contract", reference)
        self.assertIn("Teaching without a manual", reference)
        template = (REPO / "taos_core" / "templates" / "AGENTS.md.tmpl").read_text(encoding="utf-8")
        self.assertIn("supplies intent; you propose closure", template)
        control = (REPO / "policies" / "CONTROL.md").read_text(encoding="utf-8")
        self.assertIn("observed state transition", control)
        self.assertNotIn("Every completed task is an experiment", control)
        self.assertIn("Unavailable, recorded as null", control)


if __name__ == "__main__":
    unittest.main()
