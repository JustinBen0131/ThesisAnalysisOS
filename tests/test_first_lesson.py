"""The visitor replay uses the same rows as the current CLI, including in plain text."""
import copy
import json
import sys
import unittest
from html import unescape
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "site"), str(REPO / "evals"), str(REPO)]

from demo_walkthrough import capture
from first_lesson import QUESTIONS, lesson_markdown, render_lesson
from taos_core.page import Page, short


class FirstLessonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = capture(REPO)
        cls.audit = json.loads((REPO / "evals/results/measurement_audit.json").read_text())

    def test_homepage_and_markdown_show_the_four_cli_rows_and_six_commands(self):
        html = unescape(render_lesson(self.record, self.audit))
        markdown = lesson_markdown(self.record, self.audit)
        screen = StringIO()
        short(Page(screen, width=None, color=False), self.record)
        # The one-screen demo starts with these four answers in chronological order.
        rows = [line.strip() for line in screen.getvalue().splitlines()
                if line.startswith("   ") and line.split()[0] in ("holds", "stale", "fails", "unknown")][:4]
        self.assertEqual([row.split()[0] for row in rows], ["holds", "holds", "stale", "holds"])
        self.assertEqual(len(QUESTIONS), 6)
        self.assertEqual(html.count("<details"), 7)
        self.assertNotIn("<details open", html)
        self.assertIn('class="lesson-actions" hidden', html)
        for content in (html, markdown):
            for row in rows:
                self.assertIn(row, content)
            for question, command, answer in QUESTIONS:
                for text in (question, command, answer):
                    self.assertIn(text, content)
            self.assertIn("evidence/#handoff-request-3", content)
            self.assertIn("evidence/pendulum/#readings-row-6-1.05", content)

    def test_a_passing_summary_cannot_quote_a_different_estimate(self):
        record = copy.deepcopy(self.record)
        rerun = next(s for m in record["moments"] for s in m["steps"] if s.get("id") == "rerun")
        rerun["brief"] = rerun["brief"].replace("9.75", "9.82")
        with self.assertRaisesRegex(ValueError, "quoted short row"):
            render_lesson(record, self.audit)

    def test_reused_pass_cannot_be_presented_as_a_fresh_measurement(self):
        record = copy.deepcopy(self.record)
        rerun = next(s for m in record["moments"] for s in m["steps"] if s.get("id") == "rerun")
        rerun["printed"] = ["holds    fit          not run again: nothing it tested has changed"]
        with self.assertRaises(ValueError):
            lesson_markdown(record, self.audit)

    def test_larger_edit_requires_its_own_failing_check(self):
        audit = copy.deepcopy(self.audit)
        trial = next(case for case in audit["cases"] if case["id"] == "row-6-1.05")
        trial["fresh_exit"] = 0
        with self.assertRaisesRegex(ValueError, "larger correction"):
            render_lesson(self.record, audit)
