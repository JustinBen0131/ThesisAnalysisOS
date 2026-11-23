"""Focused checks for the independent homepage game."""

import re
import unittest
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))

from first_game import game_markdown, render_game


class GameHTML(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class FirstGameTests(unittest.TestCase):
    def setUp(self):
        self.page = render_game()
        self.text = game_markdown()
        self.tags = GameHTML(self.page).tags

    def test_initial_disclosure_and_readable_fallback(self):
        details = [attrs for tag, attrs in self.tags if tag == "details"]
        self.assertEqual(details, [{"class": "first-game", "id": "first-game", "data-first-game": None}])
        reading = next(attrs for _, attrs in self.tags if "data-game-reading" in attrs)
        content = next(attrs for _, attrs in self.tags if "data-game-content" in attrs)
        self.assertNotIn("hidden", reading)
        self.assertIn("hidden", content)
        self.assertIn("Your flight moved. Which plans need another look?", self.page)

    def test_all_rounds_and_verdicts_in_plain_reading(self):
        journey = ("The flight", "2:30 PM at arrivals", "What happened when you checked again?",
                   "You still arrive by 6:30 PM.", "The report", "colors.txt", "No source recorded",
                   "Now imagine a month of work.", "37 of 400", "The stories and counts are fictional.",
                   "The recorded conditions still match.", "Something the result depended on changed.",
                   "current conditions and did not pass", "too little recorded evidence")
        for part in journey:
            with self.subTest(part=part):
                self.assertIn(part, self.page)
                self.assertIn(part, self.text)
        self.assertIn('href="#run"', self.page)
        self.assertIn("](./#run)", self.text)

    def test_local_choices_and_illustrative_count(self):
        rounds = [attrs for _, attrs in self.tags if "data-choice" in attrs]
        self.assertEqual([attrs["data-reveal"] for attrs in rounds], ["flight-results", "report-results"])
        self.assertEqual(sum(tag == "fieldset" for tag, _ in self.tags), len(rounds))
        self.assertEqual(sum(tag == "legend" for tag, _ in self.tags), len(rounds))
        buttons = [attrs for tag, attrs in self.tags if tag == "button" and "data-reveal-choice" in attrs]
        self.assertEqual([button["type"] for button in buttons], ["button", "button"])
        self.assertFalse(any(tag == "form" for tag, _ in self.tags))
        choices = [attrs for tag, attrs in self.tags if tag == "input"]
        self.assertEqual(len(choices), 8)
        self.assertTrue(all(attrs["type"] == "checkbox" and "checked" not in attrs for attrs in choices))
        self.assertEqual(len(re.findall(r'class="first-game__dot\b', self.page)), 400)
        self.assertEqual(self.page.count("first-game__dot--initial"), 4)
        self.assertEqual(self.page.count("first-game__dot--affected"), 37)


if __name__ == "__main__":
    unittest.main()
