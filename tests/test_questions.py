"""The human sees exactly what the ASK block says, and no internals."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QUESTIONS = REPO / "bootstrap" / "QUESTIONS.md"
ASK = re.compile(r"<!-- ASK:.*?-->(?P<body>.*?)<!-- /ASK -->", re.DOTALL)


class TestQuestions(unittest.TestCase):
    def setUp(self) -> None:
        text = QUESTIONS.read_text(encoding="utf-8")
        match = ASK.search(text)
        self.assertIsNotNone(match, "QUESTIONS.md must contain one ASK block")
        self.ask = match.group("body")
        self.after = text.split("<!-- /ASK -->", 1)[1]

    def test_ten_numbered_questions_in_order(self) -> None:
        numbers = [int(n) for n in re.findall(r"^\*\*(\d+)\.", self.ask, re.MULTILINE)]
        self.assertEqual(numbers, list(range(0, 11)))
        self.assertIn("N/A", self.ask)

    def test_every_question_but_eight_shows_a_default(self) -> None:
        blocks = re.split(r"^\*\*(\d+)\.", self.ask, flags=re.MULTILINE)[1:]
        pairs = list(zip(blocks[0::2], blocks[1::2]))
        self.assertEqual(len(pairs), 11)
        for number, body in pairs:
            if number == "8":
                self.assertIn("No default", body)
            elif number == "0":
                self.assertIn("N/A", body)
            else:
                self.assertIn("Default", body, "question {0} has no default".format(number))

    def test_no_internals_leak_into_what_the_human_sees(self) -> None:
        forbidden = [
            "principal_name", "project_name", "workspaces[", "git_isolation",
            "branch_pattern", "protected_branches", "worktree_root", "merge_policy",
            "secret_patterns", "first_tasks", "agent_corrections", "self_iteration",
            "max_decisions_per_day", "install_hooks_in_workspaces", "answers.schema.json",
            "Fills ", "{prefix_lower}", "{id_lower}",
        ]
        for token in forbidden:
            self.assertNotIn(token, self.ask, "the ASK block leaks {0!r} at the human".format(token))

    def test_the_reference_half_is_not_asked(self) -> None:
        self.assertIn("do not send this part", self.after)
        self.assertIn("answers.schema.json", self.after)

    def test_ask_block_is_short_enough_to_read(self) -> None:
        self.assertLess(len(self.ask.split()), 800, "the ask is too long to read in one sitting")

    def test_tips_block_exists_and_is_clean(self) -> None:
        text = (REPO / "bootstrap" / "TIPS.md").read_text(encoding="utf-8")
        match = re.search(r"<!-- TIPS:.*?-->(?P<body>.*?)<!-- /TIPS -->", text, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertEqual(len(re.findall(r"^\*\*\d\.", body, re.MULTILINE)), 5)
        for token in ("self_iteration", "push_branches_open_prs", "answers.json"):
            self.assertNotIn(token, body)
        self.assertLess(len(body.split()), 500)
        self.assertIn("TIPS.md", (REPO / "BOOTSTRAP.md").read_text(encoding="utf-8"))

    def test_bootstrap_tells_the_agent_to_send_it_verbatim(self) -> None:
        text = (REPO / "BOOTSTRAP.md").read_text(encoding="utf-8")
        self.assertIn("verbatim", text)
        self.assertIn("ASK", text)


if __name__ == "__main__":
    unittest.main()
