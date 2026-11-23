"""Prove the chain from retained worker accounting to a task and the next agent's capsule."""
import hashlib
import json
import shutil
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from helpers import REPO, cleanup, construct_example, make_home
from taos_core import control, events, hpc, lifecycle, progress, telemetry, usage
from taos_core.tasks import TaskStore
from taos_core.util import TaosError, slugify


class TestScientificProgress(unittest.TestCase):
    def setUp(self):
        self.tmp, self.paths = make_home()
        self.addCleanup(cleanup, self.tmp)
        for name in ("CLAUDE_ROOT", "CODEX_ROOT"):
            handle = patch.object(usage, name, self.tmp / name)
            handle.start()
            self.addCleanup(handle.stop)
        construct_example(self.tmp, self.paths)
        self.folder = self.tmp / "campaign"
        shutil.copytree(REPO / "examples/hpc", self.folder)
        self.packet = hpc.read_packet(self.folder / "campaign.json")
        self.store = TaskStore(self.paths)
        self.task = self.store.create(title="Which sensor returned valid readings?", actor="human")["id"]
        self.other = self.store.create(title="Different project question", actor="human")["id"]

    def report(self):
        return hpc.review(self.packet, self.folder)

    def test_measured_accounting_and_unavailable_are_distinct_from_forecast(self):
        result = self.report()
        self.assertEqual(result["accounting"]["worker_seconds"], 220)
        self.assertEqual(result["batch"]["estimates"]["worker_seconds"], 90)
        handle = self.folder / self.packet["accounting"]["file"]
        for attempts, expected in (([{"id": "A.1", "output": "A", "worker_seconds": 0}], 0),
                                   ([{"id": "A.1", "output": "A", "worker_seconds": 17}] * 2, None)):
            handle.write_text(json.dumps({"format": "taos.hpc.accounting.v1", "attempts": attempts}))
            self.packet["accounting"]["sha256"] = hashlib.sha256(handle.read_bytes()).hexdigest()
            self.assertEqual(self.report()["accounting"]["worker_seconds"], expected)
        self.packet.pop("accounting")
        self.assertIsNone(self.report()["accounting"]["worker_seconds"])
        self.assertEqual(self.report()["outputs"][0]["action"], "keep")

    def test_one_current_review_per_task_and_campaign_and_no_stored_packet(self):
        report = self.report()
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _: progress.record(self.paths, self.task, "primary", "codex", report), range(3)))
        rows = events.read(self.paths, types=["hpc_review"])
        self.assertEqual(len(rows), 1)
        self.assertNotIn(self.packet["question"], json.dumps(rows))
        self.assertNotIn(str(self.folder), json.dumps(rows))
        (self.folder / "returns" / "A.json").write_text("changed since review")
        progress.record(self.paths, self.task, "primary", "claude", self.report())
        progress.record(self.paths, self.task, "secondary", "codex", report)
        campaigns = progress.project_view(self.paths, self.task)["tasks"][0]["campaigns"]
        self.assertEqual([(item["campaign"], item["filed_by"], item["outputs"]["keep"]) for item in campaigns],
                         [("primary", "claude", 1), ("secondary", "codex", 2)])
        self.assertEqual(len(events.read(self.paths, types=["hpc_review"])), 3)
        filtered = progress.project_view(self.paths, self.task, "claude")["tasks"][0]
        self.assertEqual([row["campaign"] for row in filtered["campaigns"]], ["primary"])
        self.assertEqual(progress.project_view(self.paths, self.other)["tasks"][0]["campaigns"], [])
        capsule = lifecycle.capsule(self.paths, self.task)
        self.assertIn("1/3 listed outputs", lifecycle.capsule_text(capsule))
        self.assertEqual(len(capsule["compute_reviews"]), 2)
        self.assertEqual({r["campaign"]: r["filed_by"] for r in capsule["compute_reviews"]},
                         {"primary": "claude", "secondary": "codex"})
        with self.assertRaises(TaosError):
            progress.record(self.paths, "UNKNOWN-999", "primary", "human", report)

    def test_gate_history_is_scoped_by_task(self):
        events.emit(self.paths, "gate_run", "codex", task_id=self.task, gates=["shape", "count"], reused=["count"], ok=True)
        events.emit(self.paths, "gate_run", "codex", task_id=self.task, gates=[], reused=[], ok=True)
        events.emit(self.paths, "gate_run", "claude", task_id=self.other, gates=["different"], reused=[], ok=False)
        task = progress.project_view(self.paths, self.task)["tasks"][0]
        self.assertEqual(task["checks"], {"executed": 1, "reused": 1})
        self.assertIsNone(task["acceptance"])

    def test_corrections_and_providers_do_not_leak_between_episodes(self):
        task = self.store.get(self.task)
        start, stop, after = ["2026-01-01T00:0%d:00Z" % i for i in range(3)]
        slug = slugify(task["id"] + "-" + task["title"])
        changes = [dict(ts=t, task_id=key, agent=actor, outcome="corrected") for t, key, actor in
                   [(start, slug, "codex"), (start, self.other, "codex"), (start, slug, "claude"), (after, slug, "codex")]]
        future = dict(ts=after, task_id=self.task, type="gate_run", ok=False)
        actors = {"claude": {"totals": dict(usage.ZERO, input_tokens=999)}, "codex": {"totals": dict(usage.ZERO, input_tokens=17)}}
        with patch.object(telemetry, "rows", return_value=changes), patch.object(events, "read", return_value=[future]), \
             patch.object(usage, "window", return_value={"agents": actors}):
            vector = control.outcome_vector(self.paths, task, start, stop, "codex")
        self.assertEqual((vector["corrections"], vector["gate_fail"]), (1, 0))
        self.assertIsNone(vector["input_tokens"])
        self.assertIsNone(vector["cost"])
        self.assertEqual(vector["provider_window"]["agents"]["codex"]["totals"]["input_tokens"], 17)
        self.assertNotIn("claude", vector["provider_window"]["agents"])

    def test_mixed_model_pricing_and_inclusive_codex_cache(self):
        local = self.tmp / "claude.jsonl"
        rows = [{"timestamp":"2026-01-01T00:00:00Z", "message":{"model":m,"usage":{"input_tokens":1000000}}}
                for m in ("claude-sonnet-5", "claude-opus-5", "claude-sonnet-5")]
        local.write_text("\n".join(map(json.dumps, rows)))
        codex = self.tmp / "rollout-synthetic.jsonl"
        records = [{"type":"session_meta","payload":{"model":"gpt-5.5"}},
                   {"type":"token_usage_record","timestamp":"2026-01-01T00:00:00Z",
                    "payload":{"usage":{"input_tokens":1000000,"cached_input_tokens":1000000}}}]
        codex.write_text("\n".join(map(json.dumps, records)))
        with patch.object(usage, "claude_transcripts", return_value=[local]), patch.object(usage, "codex_sessions", return_value=[codex]):
            agents = usage.window(self.paths, "2025-12-31T00:00:00Z", workspace=self.tmp)["agents"]
        self.assertEqual(agents["claude"]["cost"]["amount"], 21.0)
        self.assertEqual(agents["codex"]["cost"]["amount"], 0.125)
