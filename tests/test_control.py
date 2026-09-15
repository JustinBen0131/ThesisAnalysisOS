"""The residual control law: deterministic, bounded, replayable, and invisible."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import cleanup, construct_example, make_home

from taos_core import config as config_mod
from taos_core import control as control_mod
from taos_core import doctor as doctor_mod
from taos_core import gates as gates_mod
from taos_core import handoff as handoff_mod
from taos_core import lifecycle as lifecycle_mod
from taos_core import projections as projections_mod
from taos_core import store as store_mod
from taos_core import tasks as tasks_mod
from taos_core import telemetry as telemetry_mod
from taos_core.bootstrap import link_workspace
from taos_core.cli import main as cli


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths)
        self.store = tasks_mod.TaskStore(self.paths)

    def tearDown(self) -> None:
        cleanup(self.tmp)

    def new_task(self, title: str, label: str = "parser") -> str:
        return self.store.create(title=title, actor="human", labels=[label])["id"]

    def run_episode(self, task_id: str, agent: str = "codex", fail_gates: bool = False, state: str = "review", corrected: bool = False) -> dict:
        capsule = lifecycle_mod.start(self.paths, agent=agent, task_id=task_id, session_label="{0} | ep".format(task_id))
        if fail_gates:
            config = config_mod.load(self.paths)
            config["gates"] = [{"name": "boom", "command": "false"}]
            store_mod.atomic_write_json(self.paths.config_file, config)
            gates_mod.run(self.paths, task_id=task_id, agent=agent)
            config["gates"] = [{"name": "ok", "command": "true"}]
            store_mod.atomic_write_json(self.paths.config_file, config)
        gates_mod.run(self.paths, task_id=task_id, agent=agent)
        if corrected:
            telemetry_mod.label(self.paths, agent=agent, task_id="corr-" + task_id.lower(), phase="iterate", outcome="corrected", task="x")
        reason = "blocked by the missing fixture" if state == "blocked" else "episode closed"
        result = lifecycle_mod.finish(self.paths, agent=agent, task_id=task_id, state=state, reason=reason, evidence="e", session_label="s")
        return {"capsule": capsule, "finish": result}


class TestControlLaw(Base):
    def test_cold_start_is_conservative_and_deterministic(self) -> None:
        capsule = lifecycle_mod.start(self.paths, agent="codex", task_id="CMP-1", session_label="CMP-1 | a")
        rec = capsule["control"]
        self.assertEqual(rec["profile"], "careful")  # gates configured -> careful prior
        self.assertEqual(rec["bands"]["exploration"], "exploit")
        self.assertIn("no comparable history", control_mod.control_line(rec))
        state = control_mod.load_state(self.paths)
        z = {"klass": "novel", "priority": "P2", "has_blockers": False, "has_prior_handoff": False, "gates_configured": True}
        a = control_mod.recommend(state, z, control_mod.settings(self.paths))
        b = control_mod.recommend(state, z, control_mod.settings(self.paths))
        self.assertEqual(a, b)

    def test_start_opens_and_finish_closes_with_real_measurements(self) -> None:
        task = self.new_task("Fix parser recovery")
        out = self.run_episode(task, fail_gates=True)
        self.assertIsNotNone(out["capsule"]["control"])
        closed = out["finish"]["control"]
        self.assertIsNotNone(closed)
        self.assertEqual(closed["vector"]["gate_fail"], 1)
        self.assertEqual(closed["vector"]["gate_pass"], 1)
        self.assertFalse(closed["clean"])
        self.assertIsNone(closed["vector"]["input_tokens"])  # unknown stays unknown
        self.assertIsNone(closed["vector"]["cost"])
        state = control_mod.load_state(self.paths)
        self.assertEqual(state["episodes"], 1)
        self.assertEqual(state["open"], {})

    def test_clean_streak_favors_lighter_then_failures_restore_caution(self) -> None:
        cfg = control_mod.settings(self.paths)
        # repeated clean closures on the same class
        for index in range(6):
            task = self.new_task("Parser task {0}".format(index))
            self.run_episode(task)
        state = control_mod.load_state(self.paths)
        self.assertLess(state["params"]["compute_bias"], 0.0)
        z = control_mod.observe_state(self.paths, self.store.get(self.new_task("Parser task next")), [])
        rec = control_mod.recommend(state, z, cfg)
        self.assertIn(rec["profile"], ("lean", "balanced"))
        # an under-sampled admissible profile keeps a bounded chance: bonus > 0 for n=0 profiles
        candidates = {c["profile"]: c for c in rec["basis"]["candidates"]}
        self.assertGreater(candidates["frontier"]["bonus"], 0.0)
        self.assertGreater(candidates["frontier"]["bonus"], candidates["careful"]["bonus"])
        # now failures
        for index in range(4):
            task = self.new_task("Parser task fail {0}".format(index))
            self.run_episode(task, fail_gates=True, corrected=True, state="blocked" if index % 2 else "review")
        state = control_mod.load_state(self.paths)
        self.assertGreater(state["params"]["verify_bias"], 0.0)
        rec = control_mod.recommend(state, control_mod.observe_state(self.paths, self.store.get(self.new_task("Parser task after")), []), cfg)
        self.assertIn(rec["profile"], ("careful", "frontier"))
        for name, value in state["params"].items():
            low, high = control_mod.PARAM_BOUNDS[name]
            self.assertTrue(low <= value <= high)

    def test_replay_is_deterministic_and_doctor_agrees(self) -> None:
        for index in range(4):
            self.run_episode(self.new_task("Replay task {0}".format(index)), fail_gates=(index == 2))
        stored = control_mod.load_state(self.paths)
        rebuilt = control_mod.rebuild(self.paths, write=False)
        for key in ("params", "classes", "episodes", "history"):
            self.assertEqual(stored[key], rebuilt[key])
        self.assertEqual(control_mod.check(self.paths), [])
        names = {c["name"]: c["status"] for c in doctor_mod.run(self.paths)["checks"]}
        self.assertEqual(names["control_state"], "pass")
        # tamper with the derived state: the doctor notices, rebuild repairs
        stored["params"]["beta"] = 5.0
        store_mod.atomic_write_json(self.paths.projections_dir / "control.json", stored)
        self.assertTrue(control_mod.check(self.paths))
        self.assertEqual(cli(["--home", str(self.paths.home), "control", "rebuild"]), 0)
        self.assertEqual(control_mod.check(self.paths), [])

    def test_malformed_events_are_ignored_not_fatal(self) -> None:
        self.run_episode(self.new_task("Good one"))
        store_mod.append_jsonl(self.paths.events_file, {"id": "x", "ts": store_mod.utc_now(), "type": "control_close", "agent": "codex", "episode_id": "ep_missing", "profile": "lean", "vector": {}, "j": "nope", "klass": "parser"})
        store_mod.append_jsonl(self.paths.events_file, {"id": "y", "ts": store_mod.utc_now(), "type": "control_open", "agent": "codex", "task_id": "CMP-1"})
        state = control_mod.rebuild(self.paths, write=True)
        self.assertEqual(state["episodes"], 1)
        self.assertEqual(state["malformed"], 2)
        names = {c["name"]: c["status"] for c in doctor_mod.run(self.paths)["checks"]}
        self.assertEqual(names["control_state"], "warn")

    def test_user_choice_is_observed_not_overridden(self) -> None:
        config = config_mod.load(self.paths)
        config["control"] = dict(config_mod.DEFAULTS["control"], observed_profile="frontier")
        store_mod.atomic_write_json(self.paths.config_file, config)
        task = self.new_task("Observed task")
        out = self.run_episode(task)
        self.assertEqual(out["capsule"]["control"]["observed"], "frontier")
        closes = [r for r in store_mod.read_jsonl(self.paths.events_file) if r.get("type") == "control_close"]
        self.assertEqual(closes[-1]["profile"], "frontier")
        self.assertTrue(closes[-1]["observed"])

    def test_handoff_and_blocker_are_represented(self) -> None:
        task = self.new_task("Handoff task")
        lifecycle_mod.start(self.paths, agent="codex", task_id=task, session_label="s")
        gates_mod.run(self.paths, task_id=task, agent="codex")
        body = handoff_mod.template(self.store.get(task), "codex", "claude", "s")
        for line in body.splitlines():
            if line.startswith("<"):
                body = body.replace(line, "facts")
        handoff_file = self.tmp / "h.md"
        handoff_file.write_text(body, encoding="utf-8")
        result = lifecycle_mod.finish(self.paths, agent="codex", task_id=task, state="blocked", reason="blocked by the missing fixture", evidence="e", session_label="s", handoff_file=handoff_file, to_agent="claude")
        vector = result["control"]["vector"]
        self.assertEqual(vector["handoffs"], 1)
        self.assertEqual(vector["blockers"], 1)
        self.assertEqual(vector["terminal"], "blocked")

    def test_old_config_without_control_still_works_and_can_disable(self) -> None:
        config = config_mod.load(self.paths)
        config.pop("control", None)
        store_mod.atomic_write_json(self.paths.config_file, config)
        self.assertTrue(control_mod.settings(self.paths)["enabled"])
        capsule = lifecycle_mod.start(self.paths, agent="codex", task_id="CMP-2", session_label="s")
        self.assertIsNotNone(capsule["control"])
        config["control"] = {"enabled": False}
        store_mod.atomic_write_json(self.paths.config_file, config)
        capsule = lifecycle_mod.start(self.paths, agent="claude", task_id="CMP-3", session_label="s")
        self.assertIsNone(capsule["control"])

    def test_session_status_carries_one_line_and_pause_suppresses_it(self) -> None:
        text = projections_mod.compact_status(self.paths)
        self.assertIn("Control: v1", text)
        self.assertLessEqual(len(text.splitlines()), 25)
        (self.paths.state / "paused").write_text("{}", encoding="utf-8")
        self.assertNotIn("Control:", projections_mod.compact_status(self.paths))

    def test_guard_denies_hand_edits_to_control_state(self) -> None:
        env = dict(os.environ, TAOS_HOME=str(self.paths.home))
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(self.paths.projections_dir / "control.json")}}
        process = subprocess.run([sys.executable, str(self.paths.home / "hooks" / "guard.py"), "--agent", "codex"], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(process.returncode, 2)

    def test_no_control_metadata_reaches_a_linked_workspace(self) -> None:
        self.run_episode(self.new_task("Leak check"))
        ws = self.tmp / "other"
        ws.mkdir()
        link_workspace(self.paths, ws, install_hooks=True)
        for path in ws.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                for token in ("control_open", "compute_bias", "ep_", "episode"):
                    self.assertNotIn(token, text, "{0} leaked into {1}".format(token, path))

    def test_cli_surface(self) -> None:
        self.run_episode(self.new_task("CLI task"))
        home = str(self.paths.home)
        self.assertEqual(cli(["--home", home, "control", "status"]), 0)
        self.assertEqual(cli(["--home", home, "control", "explain", "CMP-4"]), 0)
        self.assertEqual(cli(["--home", home, "control", "frontier"]), 0)
        self.assertEqual(cli(["--home", home, "control", "status", "--json"]), 0)

    def test_end_to_end_trajectory(self) -> None:
        cfg = control_mod.settings(self.paths)
        first = self.run_episode(self.new_task("Unfamiliar", label="codegen"))
        self.assertEqual(first["capsule"]["control"]["profile"], "careful")
        for index in range(5):
            self.run_episode(self.new_task("Codegen {0}".format(index), label="codegen"))
        state = control_mod.load_state(self.paths)
        lighter = control_mod.recommend(state, {"klass": "codegen", "priority": "P2", "has_blockers": False, "has_prior_handoff": False, "gates_configured": True}, cfg)
        self.assertIn(lighter["profile"], ("lean", "balanced"))
        for index in range(3):
            self.run_episode(self.new_task("Codegen fail {0}".format(index), label="codegen"), fail_gates=True, corrected=True)
        state = control_mod.load_state(self.paths)
        cautious = control_mod.recommend(state, {"klass": "codegen", "priority": "P2", "has_blockers": False, "has_prior_handoff": False, "gates_configured": True}, cfg)
        self.assertIn(cautious["profile"], ("careful", "frontier"))
        probes = [c for c in cautious["basis"]["candidates"] if c["n"] == 0]
        self.assertTrue(all(c["bonus"] > 0 for c in probes))
        before = json.dumps({k: state[k] for k in ("params", "classes", "episodes", "history")}, sort_keys=True)
        after_state = control_mod.rebuild(self.paths, write=True)
        after = json.dumps({k: after_state[k] for k in ("params", "classes", "episodes", "history")}, sort_keys=True)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
