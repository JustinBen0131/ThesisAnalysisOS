"""The behaviours the OS promises. Each test is a claim in docs/SPEC.md."""

from __future__ import annotations

import json
import os
import threading
import time
import unittest
from pathlib import Path

from helpers import cleanup, construct_example, make_home

from taos_core import atoms as atoms_mod
from taos_core import brief as brief_mod
from taos_core import burn as burn_mod
from taos_core import claims as claims_mod
from taos_core import decisions as decisions_mod
from taos_core import doctor as doctor_mod
from taos_core import gates as gates_mod
from taos_core import handoff as handoff_mod
from taos_core import kernels as kernels_mod
from taos_core import lifecycle as lifecycle_mod
from taos_core import projections as projections_mod
from taos_core import proposals as proposals_mod
from taos_core import store as store_mod
from taos_core import tasks as tasks_mod
from taos_core import telemetry as telemetry_mod
from taos_core.bootstrap import link_workspace, unlink_workspace, validate_answers
from taos_core.cli import main as cli
from taos_core.util import TaosError


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        self.report = construct_example(self.tmp, self.paths)
        self.store = tasks_mod.TaskStore(self.paths)

    def tearDown(self) -> None:
        cleanup(self.tmp)

    def run_cli(self, *argv: str) -> int:
        return cli(["--home", str(self.paths.home)] + list(argv))


class TestConstruct(Base):
    def test_constructs_green_and_idempotent(self) -> None:
        self.assertTrue(self.report["doctor"]["ok"], self.report["doctor"])
        self.assertEqual(self.report["tasks_created"], ["CMP-1", "CMP-2", "CMP-3"])
        again = construct_example(self.tmp, self.paths)
        self.assertEqual(again["tasks_created"], [])
        self.assertEqual(len(self.store.list()), 3)

    def test_agents_md_rendered_without_guard(self) -> None:
        text = self.paths.agents_md.read_text(encoding="utf-8")
        self.assertNotIn("bootstrap-guard", text)
        self.assertIn("Alex", text)
        self.assertIn("CMP-", text)
        self.assertIn("do-not-touch", text)
        self.assertLess(len(text.encode("utf-8")), 12 * 1024)
        self.assertTrue(self.paths.claude_md.read_text(encoding="utf-8").startswith("@AGENTS.md"))

    def test_workspace_link_preserves_and_unlink_restores(self) -> None:
        ws = self.tmp / "ws"
        original = "# mine\nkeep this\n"
        (ws / "AGENTS.md").write_text(original, encoding="utf-8")
        link_workspace(self.paths, ws, install_hooks=True)
        link_workspace(self.paths, ws, install_hooks=True)  # idempotent
        text = (ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(original))
        self.assertEqual(text.count("<!-- taos:begin -->"), 1)
        self.assertTrue((ws / ".taos-link.json").is_file())
        self.assertTrue((ws / ".codex" / "hooks.json").is_file())
        self.assertIn(str(self.paths.home), (ws / ".codex" / "hooks.json").read_text(encoding="utf-8"))
        unlink_workspace(self.paths, ws)
        self.assertEqual((ws / "AGENTS.md").read_text(encoding="utf-8"), original)
        self.assertFalse((ws / ".taos-link.json").exists())
        self.assertFalse((ws / ".codex" / "hooks.json").exists())

    def test_existing_hooks_are_never_overwritten(self) -> None:
        ws = self.tmp / "other-repo"
        (ws / ".codex").mkdir(parents=True, exist_ok=True)
        (ws / ".codex" / "hooks.json").write_text('{"mine": true}', encoding="utf-8")
        result = link_workspace(self.paths, ws, install_hooks=True)
        self.assertIn("merge", result["hooks"][".codex/hooks.json"])
        self.assertEqual((ws / ".codex" / "hooks.json").read_text(encoding="utf-8"), '{"mine": true}')

    def test_answers_validation(self) -> None:
        problems = validate_answers({"principal_name": "", "project_name": "x", "prefix": "bad", "first_tasks": []}, self.paths)
        self.assertTrue(any("prefix" in p for p in problems))
        self.assertTrue(any("first_tasks" in p for p in problems))

    def test_codex_hooks_are_pinned_to_home(self) -> None:
        text = (self.paths.home / ".codex" / "hooks.json").read_text(encoding="utf-8")
        self.assertIn('"python3 {0}/hooks/guard.py'.format(self.paths.home), text)


class TestTasks(Base):
    def test_ids_monotonic_under_threads(self) -> None:
        created = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            task = self.store.create(title="t{0}".format(index), actor="codex")
            with lock:
                created.append(task["id"])

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        numbers = sorted(int(t.split("-")[1]) for t in created)
        self.assertEqual(numbers, list(range(4, 12)))

    def test_done_requires_evidence_and_blocked_requires_blocker(self) -> None:
        with self.assertRaises(TaosError):
            self.store.transition("CMP-1", "done", "finished", "codex")
        with self.assertRaises(TaosError):
            self.store.transition("CMP-1", "blocked", "hard", "codex")
        task = self.store.transition("CMP-1", "done", "finished", "codex", evidence="commit abc")
        self.assertEqual(task["status"], "done")
        self.assertFalse(task["hot"])
        with self.assertRaises(TaosError):
            self.store.transition("CMP-1", "active", "again", "codex")
        task = self.store.transition("CMP-1", "next", "reopen", "codex", reopen=True)
        self.assertEqual(task["status"], "next")

    def test_relations_symmetric_and_blockers(self) -> None:
        self.store.relate("CMP-2", "blockedBy", "CMP-1", "codex")
        self.assertEqual(self.store.get("CMP-1")["relations"]["blocks"], ["CMP-2"])
        self.assertEqual(self.store.blockers("CMP-2"), ["CMP-1"])
        self.store.transition("CMP-1", "done", "x", "codex", evidence="e")
        self.assertEqual(self.store.blockers("CMP-2"), [])
        self.store.relate("CMP-2", "blockedBy", "CMP-1", "codex", remove=True)
        self.assertEqual(self.store.get("CMP-1")["relations"]["blocks"], [])

    def test_find_and_order(self) -> None:
        self.assertEqual([t["id"] for t in self.store.find("panic")], ["CMP-2"])
        self.store.set_hot("CMP-3", True, "test", "human")
        self.assertEqual(self.store.list()[0]["id"], "CMP-3")

    def test_events_first(self) -> None:
        rows = store_mod.read_jsonl(self.paths.events_file)
        self.assertTrue(any(r["type"] == "task_create" and r["task_id"] == "CMP-1" for r in rows))
        self.assertTrue(all("id" in r and "ts" in r and "agent" in r for r in rows))


class TestClaims(Base):
    def test_conflict_and_prefix_paths(self) -> None:
        store = claims_mod.ClaimStore(self.paths)
        store.acquire(agent="codex", scopes=["task:CMP-1", "path:src/typeck"], session_label="a")
        with self.assertRaises(claims_mod.ClaimConflict):
            store.acquire(agent="claude", scopes=["path:src/typeck/infer"], session_label="b")
        with self.assertRaises(claims_mod.ClaimConflict):
            store.acquire(agent="claude", scopes=["task:CMP-1"], session_label="b")
        free = store.acquire(agent="claude", scopes=["path:src/parser"], session_label="b")
        self.assertEqual(free["agent"], "claude")
        same = store.acquire(agent="codex", scopes=["task:CMP-1"], session_label="a2")
        self.assertEqual(len(store.live()), 2)
        self.assertEqual(same["session_label"], "a2")

    def test_stale_and_takeover(self) -> None:
        store = claims_mod.ClaimStore(self.paths)
        old = store.acquire(agent="codex", scopes=["task:CMP-2"], session_label="a", now="2026-01-01T00:00:00Z")
        self.assertEqual([c["id"] for c in store.stale()], [old["id"]])
        with self.assertRaises(TaosError):
            store.acquire(agent="claude", scopes=["task:CMP-2"], session_label="b", takeover=True)
        taken = store.acquire(agent="claude", scopes=["task:CMP-2"], session_label="b", takeover=True, reason="stale")
        self.assertEqual(taken["takeover_of"], [old["id"]])
        self.assertEqual(store.get(old["id"])["status"], "taken_over")

    def test_release_holder_only(self) -> None:
        store = claims_mod.ClaimStore(self.paths)
        claim = store.acquire(agent="codex", scopes=["task:CMP-1"], session_label="a")
        with self.assertRaises(TaosError):
            store.release(claim["id"], "claude")
        store.release(claim["id"], "human", force=True)
        self.assertEqual(store.live(), [])

    def test_scope_grammar(self) -> None:
        with self.assertRaises(TaosError):
            claims_mod.normalize_scopes(["path:src/*"])
        with self.assertRaises(TaosError):
            claims_mod.normalize_scopes(["nonsense"])


class TestLifecycle(Base):
    def test_start_finish_handoff_roundtrip(self) -> None:
        capsule = lifecycle_mod.start(self.paths, agent="codex", task_id="CMP-2", session_label="CMP-2 | fix")
        task = capsule["task"]
        self.assertEqual(task["status"], "active")
        self.assertTrue(task["hot"])
        self.assertEqual(task["sessions"][0]["provider"], "codex")
        self.assertTrue(task["branch"].startswith("cmp/cmp-2-"))
        self.assertIn("worktree add", " ".join(capsule["lane"]["commands"]))
        self.assertTrue(any("branch:" in s for c in capsule["claims"] for s in c["scopes"]))

        with self.assertRaises(claims_mod.ClaimConflict):
            lifecycle_mod.start(self.paths, agent="claude", task_id="CMP-2", session_label="CMP-2 | dup")

        # gates are required before review
        with self.assertRaises(TaosError):
            lifecycle_mod.finish(self.paths, agent="codex", task_id="CMP-2", state="review", reason="r", evidence=None, session_label="s")
        record = gates_mod.run(self.paths, task_id="CMP-2", agent="codex")
        self.assertTrue(record["ok"])

        body = handoff_mod.template(self.store.get("CMP-2"), "codex", "claude", "CMP-2 | fix")
        for placeholder in ("<where this actually is", "<files touched", "<paths, commit", "<what might be", "<the literal next"):
            self.assertIn(placeholder, body)
        with self.assertRaises(TaosError):
            handoff_mod.write(self.paths, task_id="CMP-2", from_agent="codex", to_agent="claude", body=body, session="s")
        filled = body
        for line in body.splitlines():
            if line.startswith("<"):
                filled = filled.replace(line, "real content")
        handoff_file = self.tmp / "h.md"
        handoff_file.write_text(filled, encoding="utf-8")

        result = lifecycle_mod.finish(
            self.paths, agent="codex", task_id="CMP-2", state="review", reason="done", evidence="commit abc",
            session_label="CMP-2 | fix", handoff_file=handoff_file, to_agent="claude",
        )
        self.assertEqual(result["state"], "review")
        self.assertTrue(result["handoff"])
        self.assertIn("Claude, please continue", result["wrapper"])
        self.assertEqual(claims_mod.ClaimStore(self.paths).live(), [])

        capsule = lifecycle_mod.start(self.paths, agent="claude", task_id="CMP-2", session_label="CMP-2 | next")
        self.assertIn("Agent: codex", capsule["handoff_head"])
        self.assertEqual(capsule["task"]["status"], "active")
        rows = telemetry_mod.rows(self.paths)
        self.assertEqual([r["phase"] for r in rows], ["start", "handoff", "start"])
        self.assertEqual(rows[1]["counterpart"], "claude")

    def test_claude_gets_its_own_lane(self) -> None:
        capsule = lifecycle_mod.start(self.paths, agent="claude", task_id="CMP-1", session_label="CMP-1 | perf")
        self.assertTrue(capsule["lane"]["workspace"].endswith("ws-claude"))
        codex = lifecycle_mod.start(self.paths, agent="codex", task_id="CMP-3", session_label="CMP-3 | docs")
        self.assertTrue(codex["lane"]["workspace"].endswith("ws"))

    def test_skip_gates_is_recorded(self) -> None:
        lifecycle_mod.start(self.paths, agent="codex", task_id="CMP-3", session_label="s")
        lifecycle_mod.finish(self.paths, agent="codex", task_id="CMP-3", state="review", reason="no tests apply",
                             evidence="doc", session_label="s", skip_gates=True)
        refs = [e["ref"] for e in self.store.get("CMP-3")["evidence"]]
        self.assertIn("gates skipped", refs)


class TestQueuesAndProjections(Base):
    def test_decisions_and_budget(self) -> None:
        for index in range(4):
            decision = decisions_mod.ask(self.paths, task_id="CMP-1", question="q{0}".format(index), options=["a", "b"], agent="codex")
        self.assertTrue(decision["over_budget"])
        self.assertEqual(len(decisions_mod.open_decisions(self.paths)), 4)
        with self.assertRaises(TaosError):
            decisions_mod.answer(self.paths, decision_id=decision["id"], choice="c")
        answered = decisions_mod.answer(self.paths, decision_id=decision["id"], choice="a", note="n")
        self.assertEqual(answered["status"], "answered")

    def test_proposals_and_atom_promotion(self) -> None:
        seeded = proposals_mod.open_proposals(self.paths)
        self.assertEqual(len(seeded), 2)
        atom = {
            "id": "no-todo-in-agents-md",
            "rule": "AGENTS.md has no TODO.",
            "check": {"type": "regex_must_not_match", "target": "agents_md", "pattern": "TODO"},
            "fixtures": {"red": "a TODO here", "green": "clean"},
        }
        proposal = proposals_mod.propose(self.paths, kind="atom", title="t", body="b", evidence=[], agent="claude", atom=atom)
        promoted = atoms_mod.promote(self.paths, proposal["id"], by="human")
        self.assertEqual(promoted["status"], "active")
        results = {r["id"]: r for r in atoms_mod.check(self.paths)}
        self.assertTrue(results["no-todo-in-agents-md"]["ok"])
        self.assertTrue(all(r["ok"] for r in results.values()), results)
        with self.assertRaises(TaosError):
            proposals_mod.propose(self.paths, kind="atom", title="t", body="b", evidence=[], agent="claude", atom={"id": "bad"})

    def test_brief_top_line_and_status(self) -> None:
        brief = brief_mod.build(self.paths)
        self.assertEqual(brief["top_line"], "No action needed.")
        decisions_mod.ask(self.paths, task_id="CMP-1", question="q", options=[], agent="codex")
        brief = brief_mod.build(self.paths)
        self.assertEqual(brief["top_line"], "1 item(s) need you.")
        text = projections_mod.compact_status(self.paths)
        self.assertIn("Decisions owed: 1", text)
        self.assertIn("Doctor: green", text)
        self.assertLessEqual(len(text.splitlines()), 25)
        path = brief_mod.write(self.paths)
        self.assertTrue(path.is_file())
        retro = brief_mod.retro(self.paths, 7)
        self.assertGreater(retro["events"], 0)

    def test_kernels_freshness_and_now(self) -> None:
        states = {k["name"]: k["status"] for k in kernels_mod.freshness(self.paths)}
        self.assertEqual(states["OS_KERNEL"], "fresh")
        self.paths.agents_md.write_text(self.paths.agents_md.read_text(encoding="utf-8") + "\nchange\n", encoding="utf-8")
        states = {k["name"]: k["status"] for k in kernels_mod.freshness(self.paths)}
        self.assertEqual(states["OS_KERNEL"], "drifted")
        kernels_mod.index_refresh(self.paths, "OS_KERNEL", "agent")
        states = {k["name"]: k["status"] for k in kernels_mod.freshness(self.paths)}
        self.assertEqual(states["OS_KERNEL"], "fresh")
        lifecycle_mod.start(self.paths, agent="codex", task_id="CMP-1", session_label="s")
        text = kernels_mod.generate_now(self.paths).read_text(encoding="utf-8")
        self.assertIn("CMP-1", text)
        self.assertIn("machine-generated", kernels_mod.regen_prompt(self.paths, "NOW_KERNEL"))

    def test_burn_roundtrip_and_protection(self) -> None:
        old = self.paths.handoffs_dir / "20200101T000000Z_CMP-1_codex_to_claude.md"
        old.write_text("Agent: codex\nold handoff\n", encoding="utf-8")
        ancient = time.time() - 90 * 86400
        os.utime(str(old), (ancient, ancient))
        os.utime(str(self.paths.tasks_file), (ancient, ancient))  # germline must never burn
        plan = burn_mod.plan(self.paths)
        self.assertEqual([p["path"] for p in plan], [self.paths.relative(old)])
        with self.assertRaises(TaosError):
            burn_mod.execute(self.paths, "2026-01-01", approve=False)
        result = burn_mod.execute(self.paths, "2026-01-01", approve=True)
        self.assertEqual(result["burned"], 1)
        self.assertFalse(old.exists())
        self.assertTrue(self.paths.tasks_file.exists())
        recalled = burn_mod.recall(self.paths, "2026-01-01")
        self.assertTrue(old.exists())
        self.assertEqual(recalled["conflicts"], [])

    def test_doctor_catches_phantoms_and_stale_claims(self) -> None:
        self.assertTrue(doctor_mod.run(self.paths)["ok"])
        data = self.store.load()
        data["tasks"]["CMP-99"] = dict(data["tasks"]["CMP-1"], id="CMP-99")
        store_mod.atomic_write_json(self.paths.tasks_file, data)
        report = doctor_mod.run(self.paths)
        self.assertFalse(report["ok"])
        names = {c["name"]: c["status"] for c in report["checks"]}
        self.assertEqual(names["allocator_monotonic"], "fail")
        data["tasks"].pop("CMP-99")
        store_mod.atomic_write_json(self.paths.tasks_file, data)
        claims_mod.ClaimStore(self.paths).acquire(agent="codex", scopes=["task:CMP-1"], session_label="s", now="2026-01-01T00:00:00Z")
        names = {c["name"]: c["status"] for c in doctor_mod.run(self.paths)["checks"]}
        self.assertEqual(names["claims_stale"], "warn")


class TestCli(Base):
    def test_status_json_and_exit_codes(self) -> None:
        self.assertEqual(self.run_cli("status", "--compact"), 0)
        self.assertEqual(self.run_cli("task", "list", "--json"), 0)
        self.assertEqual(self.run_cli("start", "--agent", "codex", "--task", "CMP-1", "--session", "CMP-1 | a"), 0)
        self.assertEqual(self.run_cli("start", "--agent", "claude", "--task", "CMP-1", "--session", "CMP-1 | b"), 4)
        self.assertEqual(self.run_cli("task", "show", "CMP-404"), 1)
        self.assertEqual(self.run_cli("claim", "check", "--agent", "claude", "--scope", "task:CMP-1"), 4)
        self.assertEqual(self.run_cli("doctor"), 0)
        self.assertEqual(self.run_cli("pause", "--note", "x"), 0)
        self.assertIn("paused", projections_mod.compact_status(self.paths))
        self.assertEqual(self.run_cli("resume"), 0)

    def test_not_constructed(self) -> None:
        tmp, paths = make_home()
        try:
            self.assertEqual(cli(["--home", str(paths.home), "status", "--compact"]), 0)
            self.assertIn("not constructed", projections_mod.compact_status(paths))
            self.assertFalse(doctor_mod.run(paths)["ok"])
        finally:
            cleanup(tmp)


if __name__ == "__main__":
    unittest.main()
