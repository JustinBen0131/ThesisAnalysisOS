"""Reader choices, source evidence and portable links agree across both workshop editions."""
import copy
import json
import sys
import unittest
from html import unescape
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "site"), str(REPO / "evals"), str(REPO)]

from demo_walkthrough import capture
from review_practice import PROJECTS, PROMPT, cases, practice_markdown, render_practice
from taos_core.handoff import REQUIRED_SECTIONS


class ReviewPracticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = capture(REPO)
        cls.audit = json.loads((REPO / "evals/results/measurement_audit.json").read_text())

    def test_native_five_decisions_and_source_results_for_both_entry_points(self):
        decisions = cases(self.record, self.audit)
        self.assertEqual(len(decisions), 5)
        for prefix in ("", "../../"):
            page = unescape(render_practice(self.record, self.audit, prefix=prefix))
            plain = practice_markdown(self.record, self.audit, prefix=prefix)
            self.assertEqual(page.count('<details class="review-choice">'), 15)
            self.assertNotIn('id="standing"', page)
            self.assertNotIn('id="stage"', page)
            self.assertIn(f'<h{1 if prefix else 2}>', page)
            for case in decisions:
                self.assertEqual(len(set(feedback for _, feedback in case.choices)), 3)
                self.assertIn(f'id="review-{case.anchor}"', page)
                for content in (page, plain):
                    for value in (case.question, case.finding, case.source_text):
                        self.assertIn(value, content)
                    for label, feedback in case.choices:
                        self.assertIn(label, content)
                        self.assertIn(feedback, content)
                    for _, url in case.links:
                        self.assertIn(prefix + url, content)
            for content in (page, plain):
                for text in (PROMPT, "9.82 ± 0.02", "9.75 ± 0.02", *REQUIRED_SECTIONS):
                    self.assertIn(text, content)
                for _, _, command in PROJECTS:
                    self.assertIn(command, content)

    def test_wrong_measurement_cannot_reach_either_workshop(self):
        audit = copy.deepcopy(self.audit)
        next(c for c in audit["cases"] if c["id"] == "row-6-1.05")["fresh_exit"] = 0
        for renderer in (render_practice, practice_markdown):
            with self.assertRaisesRegex(ValueError, "larger correction"):
                renderer(self.record, audit)

    def test_only_public_capsule_fields_are_displayed(self):
        packet = ('PEN-2 [P2] active  Plot period against length\ngoal: a figure\nnext: draw it\n'
                  'workspace: /private/reviewer-only\nstands: holds check fit: bases match\n'
                  'told: "Quote g with its uncertainty"\nclaim: local lease')
        for renderer in (render_practice, practice_markdown):
            text = unescape(renderer(self.record, self.audit, capsule_text=packet))
            self.assertIn("Selected lines from ./taos capsule PEN-2", text)
            self.assertIn("stands: holds check fit: bases match", text)
            self.assertNotIn("/private/reviewer-only", text)
            self.assertNotIn("local lease", text)
            with self.assertRaisesRegex(ValueError, "PEN-2"):
                renderer(self.record, self.audit, capsule_text="A different project")
