"""The run-board example must distinguish a completed job from a checked output."""

import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
import hpc_exhibit


class TransferText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reading = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "figure" and dict(attrs).get("class") == "transfer-slip":
            self.reading = True

    def handle_endtag(self, tag):
        if tag == "figure":
            self.reading = False

    def handle_data(self, data):
        if self.reading and data.strip():
            self.parts.append(data.strip())


class PilotBoardTest(unittest.TestCase):
    def test_deliveries_preserve_the_failed_attempt_across_all_three_readings(self):
        trace = hpc_exhibit.run_trace()
        self.assertEqual(trace["first_attempt_inputs"]["C"], [])
        self.assertEqual(trace["inputs"]["C"], [1, 5])
        handout = hpc_exhibit.hpc_markdown()
        for stage, frame in zip(hpc_exhibit.STAGES, trace["stages"]):
            with self.subTest(stage=stage.key):
                parser = TransferText()
                parser.feed(hpc_exhibit._frame_html(stage))
                receipt = frame["handoff"]["transfer_receipt"]
                if stage.key in ("plan", "returned"):
                    self.assertIsNone(receipt)
                    self.assertEqual(parser.parts, [])
                    continue
                attempts = [0, 2] if stage.key in ("retry", "resolved") else [0]
                state = {"retry": "pending", "resolved": "pass"}.get(stage.key, "review")
                self.assertEqual(receipt, {"sample": "C", "source_count": 2, "received_counts": attempts,
                                           "output_status": state, "first_delivery_record": hpc_exhibit.TRANSFER_RECORD})
                expected = ["Transfer receipt", "File C", "Original file", "2", "First delivery", "0"]
                if len(attempts) == 2:
                    expected.extend(["After retry", "2"])
                self.assertEqual(parser.parts, expected + ["Reading counts ·", "First delivery log"])
                section = handout.split(f"### {stage.label} ·", 1)[1].split("\n### ", 1)[0]
                self.assertIn("- Original file: 2\n- First delivery: 0", section)
                self.assertEqual("- After retry: 2" in section, len(attempts) == 2)
                self.assertIn(hpc_exhibit.TRANSFER_LINK, section)

    def test_only_the_failed_output_gets_a_second_attempt(self):
        trace = hpc_exhibit.run_trace()
        stages = {stage["id"]: stage for stage in trace["stages"]}
        self.assertTrue(all(row["output_check"] == "Unchecked" for row in stages["returned"]["samples"]))
        checked = stages["checked"]["samples"]
        self.assertEqual([row["status"] for row in checked], ["pass", "pass", "review"])
        self.assertEqual(stages["held"]["samples"], checked)
        resolved = stages["resolved"]["samples"]
        self.assertEqual(resolved[:2], checked[:2])
        self.assertEqual([row["sample"] for row in resolved if row["backend"] == "Finished twice"], ["C"])
        for row in resolved:
            expected = len(trace["inputs"][row["sample"]])
            self.assertEqual(row["output_check"], f"Pass · {expected} of {expected}")

    def test_every_choice_and_output_is_in_the_portable_reading(self):
        trace = hpc_exhibit.run_trace()
        html, handout = hpc_exhibit.render_hpc(), hpc_exhibit.hpc_markdown()
        keys = {stage["id"] for stage in trace["stages"]}
        for stage in trace["stages"]:
            self.assertIn(stage["title"], html)
            self.assertIn(stage["title"], handout)
            for choice in stage["choices"]:
                self.assertIn(choice["next"], keys)
                self.assertIn(choice["label"], html)
                self.assertIn(choice["label"], handout)
            for row in stage["samples"]:
                self.assertIn(row["output_check"], html)
                self.assertIn(row["output_check"], handout)

    def test_named_handoffs_preserve_the_retry_boundary(self):
        stages = {s["id"]: s for s in hpc_exhibit.run_trace()["stages"]}
        for stage, owner, recipient in (
            ("plan", "Planner", "Run operator"),
            ("returned", "Run operator", "Reviewer"),
            ("checked", "Reviewer", "You"),
            ("held", "You", "Reviewer"),
            ("retry", "Run operator", "Reviewer"),
            ("resolved", "Reviewer", "You"),
        ):
            frame = stages[stage]
            self.assertEqual(frame["task_owner"], owner)
            packet = frame["handoff"]
            self.assertEqual((packet["from"], packet["to"]), (owner, recipient))
            self.assertIn(packet["record"], hpc_exhibit.render_hpc())
            self.assertIn(packet["record"], hpc_exhibit.hpc_markdown())
        self.assertEqual([r["reported_count"] for r in stages["returned"]["samples"]], [2, 3, 0])
        self.assertEqual([r["reported_count"] for r in stages["retry"]["samples"]], [2, 3, 2])
        self.assertEqual(stages["retry"]["samples"][-1]["output_check"], "Unchecked")
        self.assertEqual(stages["checked"]["choices"][0]["next"], "retry")
        self.assertEqual(stages["retry"]["choices"][0]["next"], "resolved")

    def test_reader_can_inspect_each_return_before_the_review(self):
        for stage in hpc_exhibit.STAGES:
            html = hpc_exhibit._frame_html(stage)
            if stage.key != "returned":
                self.assertNotIn("data-inspect=", html)
                continue
            for name, original, delivered in hpc_exhibit.SAMPLES:
                match = str(len(original) == len(delivered)).lower()
                self.assertIn(f'data-inspect="{name}"', html)
                self.assertIn(f'data-match="{match}" aria-label="Inspect sample {name}"', html)
            self.assertIn('role="status"', html)
            self.assertIn('data-go="checked"', html)
