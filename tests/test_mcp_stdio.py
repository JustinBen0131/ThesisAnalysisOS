"""The MCP adapter reads existing verdicts without running or recording work."""

import hashlib
import json
import unittest
from unittest.mock import patch

from helpers import cleanup, construct_example, make_home
from taos_core import gates, lifecycle, mcp_stdio as mcp, rules


class TestMcp(unittest.TestCase):
    def setUp(self):
        tmp, self.paths = make_home()
        self.addCleanup(cleanup, tmp)
        self.tmp = tmp
        self.session = mcp.Session(self.paths)

    def request(self, method, params=None, **extras):
        message = {"jsonrpc": "2.0", "method": method, **extras}
        if params is not None:
            message["params"] = params
        return mcp._reply(self.session, json.dumps(message).encode())

    def initialize(self):
        answer = self.request("initialize", {"protocolVersion": mcp.PROTOCOL}, id=0)
        self.assertEqual(answer["result"]["protocolVersion"], mcp.PROTOCOL)
        self.assertIsNone(self.request("notifications/initialized"))

    def call(self, name, args):
        return self.request("tools/call", {"name": name, "arguments": args}, id=1)

    def value(self, name, args):
        return json.loads(self.call(name, args)["result"]["content"][0]["text"])

    def test_protocol_surface_and_errors(self):
        self.assertEqual(self.request("tools/list", id=1)["error"]["code"], -32600)
        self.initialize()
        tools = self.request("tools/list", id=9)["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["status", "why", "checks", "handoff"])
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))
        self.assertEqual(self.request("ping", id=4)["result"], {})
        self.assertEqual(self.request("other", id=4)["error"]["code"], -32601)
        self.assertIsNone(self.request("notifications/cancelled", {"requestId": 1}))
        self.assertEqual(mcp._reply(self.session, b"{bad")["error"]["code"], -32700)
        self.assertEqual(mcp._reply(self.session, b" " * (mcp.MAX_REQUEST + 1))["error"]["code"], -32600)
        for name, args in (("status", {"path": "/"}), ("why", {}), ("checks", {"task_id": "../*"}),
                           ("why", {"task_id": 7}), ("gate_run", {}),
                           ("handoff", {"task_id": "CMP-1", "cursor": "unrelated"}),
                           ("checks", {"task_id": "CMP-1", "cursor": None})):
            with self.subTest(name=name, args=args):
                self.assertEqual(self.call(name, args)["error"]["code"], -32602)
        self.assertTrue(self.call("why", {"task_id": "AZ-404"})["result"]["isError"])
        self.assertFalse(self.value("status", {})["constructed"])
        self.assertFalse(self.paths.state.exists())

    def test_read_standing_does_not_create_science_dir_or_run_commands(self):
        construct_example(self.tmp, self.paths, gates=[{"name": "example", "command": "true"}])
        self.initialize()
        self.assertFalse((self.paths.state / "science").exists())
        with patch.object(gates, "_execute", side_effect=AssertionError("MCP ran a check")):
            self.assertTrue(self.value("status", {})["constructed"])
            for tool, field in (("why", "parts"), ("checks", "checks")):
                self.assertEqual(self.value(tool, {"task_id": "CMP-1"})[field][0]["state"], "unknown")
            self.assertIn("CMP-1", self.value("handoff", {"task_id": "CMP-1"})["text"])
        self.assertFalse((self.paths.state / "science").exists())

    def test_handoff_matches_terminal_text_and_detects_changes_between_pages(self):
        construct_example(self.tmp, self.paths)
        quote = "Record every missing dispatch entry. " + "é⏱ " * 1000 + "End."
        rules.add(self.paths, quote=quote, said_on="2025-01-01", scope="CMP-1")
        self.initialize()
        args = {"task_id": "CMP-1"}
        first = self.value("handoff", args)
        self.assertIsNotNone(first["next_cursor"])
        text = first["text"]
        page = first
        while page["next_cursor"]:
            page = self.value("handoff", dict(args, cursor=page["next_cursor"]))
            self.assertEqual(page["start_character"], len(text))
            self.assertEqual(page["sha256"], first["sha256"])
            text += page["text"]
        expected = lifecycle.capsule_text(lifecycle.capsule(self.paths, args["task_id"])) + "\n"
        self.assertEqual(text, expected)
        self.assertIn(quote, text)
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), first["sha256"])
        rules.add(self.paths, quote="Bring the dispatch summary to the operator.",
                  said_on="2025-01-02", scope="CMP-1")
        changed = self.call("handoff", dict(args, cursor=first["next_cursor"]))["result"]
        self.assertTrue(changed["isError"])
        self.assertIn("changed", changed["content"][0]["text"])

    def test_large_replies_keep_the_worst_verdict_and_report_total(self):
        parts = [{"kind": "check", "name": str(i), "state": "holds", "reason": "z" * 500} for i in range(30)]
        parts.append({"kind": "check", "name": "failed check", "state": "fails", "reason": "exit 1"})
        view = dict(task="AZ-1", title="example", status="review", closed=True, accepted=False, state="fails", parts=parts)
        self.initialize()
        with patch.object(mcp.standing, "of_task", return_value=view):
            result = self.value("why", {"task_id": "AZ-1"})
        self.assertEqual(result["total"], len(parts))
        self.assertEqual(len(result["parts"]), mcp.MAX_ROWS)
        self.assertEqual(result["parts"][0]["state"], "fails")
        self.assertEqual(len(result["parts"][1]["reason"]), mcp.MAX_CHARS)
