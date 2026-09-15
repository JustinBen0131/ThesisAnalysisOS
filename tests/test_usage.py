"""Token telemetry: read what the hosts write, sum it correctly, invent nothing."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from helpers import cleanup, construct_example, make_home

from taos_core import config as config_mod
from taos_core import control as control_mod
from taos_core import lifecycle as lifecycle_mod
from taos_core import store as store_mod
from taos_core import usage as usage_mod
from taos_core.cli import main as cli


def claude_row(ts: str, model: str, inp: int, out: int, cached: int, write: int) -> str:
    return json.dumps({
        "timestamp": ts, "type": "assistant",
        "message": {"role": "assistant", "model": model, "usage": {
            "input_tokens": inp, "output_tokens": out,
            "cache_read_input_tokens": cached, "cache_creation_input_tokens": write}},
    })


def codex_row(ts: str, inp: int, out: int, cached: int, reasoning: int) -> str:
    return json.dumps({
        "timestamp": ts, "type": "token_usage_record",
        "payload": {"usage": {
            "input_tokens": inp, "cached_input_tokens": cached, "cache_write_input_tokens": 0,
            "output_tokens": out, "reasoning_output_tokens": reasoning,
            "total_tokens": inp + out}},
    })


class TestAdapters(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths)

    def tearDown(self) -> None:
        cleanup(self.tmp)

    def test_claude_transcript_parsing(self) -> None:
        path = self.tmp / "session.jsonl"
        path.write_text("\n".join([
            claude_row("2026-09-15T01:00:00Z", "claude-opus-5", 100, 10, 5000, 200),
            "not json at all",
            json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
            claude_row("2026-09-15T02:00:00Z", "claude-opus-5", 150, 20, 6000, 0),
        ]) + "\n", encoding="utf-8")
        result = usage_mod.read_claude(path)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["totals"]["input_tokens"], 250)
        self.assertEqual(result["totals"]["output_tokens"], 30)
        self.assertEqual(result["totals"]["cached_tokens"], 11000)
        self.assertEqual(result["totals"]["cache_write_tokens"], 200)
        self.assertEqual(result["models"], {"claude-opus-5": 2})
        windowed = usage_mod.read_claude(path, since="2026-09-15T01:30:00Z")
        self.assertEqual(windowed["rows"], 1)
        self.assertEqual(windowed["totals"]["input_tokens"], 150)

    def test_codex_rollout_parsing_and_reasoning_not_double_counted(self) -> None:
        path = self.tmp / "rollout-x.jsonl"
        path.write_text("\n".join([
            json.dumps({"type": "session_meta", "payload": {"model": "gpt-5.5"}}),
            codex_row("2026-09-15T01:00:00Z", 38158, 178, 0, 40),
            codex_row("2026-09-15T02:00:00Z", 47217, 230, 100, 60),
        ]) + "\n", encoding="utf-8")
        result = usage_mod.read_codex(path)
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["totals"]["input_tokens"], 85375)
        self.assertEqual(result["totals"]["output_tokens"], 408)
        self.assertEqual(result["totals"]["reasoning_tokens"], 100)
        # reasoning lives inside output on this host: it is reported, never added
        self.assertLess(result["totals"]["reasoning_tokens"], result["totals"]["output_tokens"])
        self.assertEqual(result["models"], {"gpt-5.5": 1})

    def test_malformed_and_missing_files_are_not_fatal(self) -> None:
        broken = self.tmp / "broken.jsonl"
        broken.write_text('{"message": {"usage": "not a dict"}}\n{oh no\n', encoding="utf-8")
        self.assertFalse(usage_mod.read_claude(broken)["ok"])
        self.assertFalse(usage_mod.read_codex(self.tmp / "nope.jsonl")["ok"])

    def test_cost_is_estimated_from_a_public_table_or_null(self) -> None:
        totals = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cached_tokens": 0, "cache_write_tokens": 0}
        cost = usage_mod.estimate_cost(self.paths, totals, {"claude-opus-5": 1})
        self.assertIsNotNone(cost)
        self.assertEqual(cost["provenance"], "estimated")
        self.assertEqual(cost["currency"], "USD")
        self.assertAlmostEqual(cost["amount"], 90.0)         # 15 + 75 per million
        self.assertTrue(cost["rates_as_of"])
        self.assertIsNone(usage_mod.estimate_cost(self.paths, totals, {"some-model-nobody-priced": 1}))
        self.assertIsNone(usage_mod.estimate_cost(self.paths, totals, {}))

    def test_probe_reports_with_evidence_and_never_asks(self) -> None:
        result = usage_mod.probe(self.paths)
        self.assertIn("claude", result["adapters"])
        self.assertIn("codex", result["adapters"])
        for data in result["adapters"].values():
            self.assertIn("available", data)
            self.assertIn("root", data)
            if data["available"]:
                self.assertTrue(data["fields"])
                self.assertGreater(data["sample_rows"], 0)
        self.assertEqual(cli(["--home", str(self.paths.home), "usage", "probe"]), 0)
        self.assertEqual(cli(["--home", str(self.paths.home), "usage", "show", "--days", "1"]), 0)

    def test_bootstrap_records_the_probe_in_config(self) -> None:
        config = config_mod.load(self.paths)
        self.assertIn("telemetry", config)
        self.assertIn("token_usage", config["telemetry"])
        self.assertEqual(set(config["telemetry"]["token_usage"]), {"claude", "codex"})
        for value in config["telemetry"]["token_usage"].values():
            self.assertIsInstance(value, bool)
        events = [r for r in store_mod.read_jsonl(self.paths.events_file) if r.get("type") == "usage_probe"]
        self.assertEqual(len(events), 1)

    def test_control_vector_carries_tokens_when_visible_and_nulls_when_not(self) -> None:
        capsule = lifecycle_mod.start(self.paths, agent="codex", task_id="CMP-1", session_label="s")
        result = lifecycle_mod.finish(self.paths, agent="codex", task_id="CMP-1", state="review",
                                      reason="r", evidence="e", session_label="s", skip_gates=True)
        vector = result["control"]["vector"]
        for field in ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "cost", "model"):
            self.assertIn(field, vector)
            self.assertIn(vector["provenance"][field], ("observed", "estimated", "unavailable"))
            if vector["provenance"][field] == "unavailable":
                self.assertIsNone(vector[field])
        self.assertEqual(vector["provenance"]["gate_fail"], "observed")
        self.assertEqual(vector["provenance"]["reuse"], "unavailable")


if __name__ == "__main__":
    unittest.main()
