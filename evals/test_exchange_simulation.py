"""Tests for the model of assistants passing results to each other."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("exchange_simulation", ROOT / "evals" / "exchange_simulation.py")
sim = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sim)

SMALL = dict(sim.PARAMETERS, steps=80, files=30, results=20, assistants=6)
WORLDS = 3
COUNTS = ("outdated_uses", "reruns", "needless_reruns")


def row(rows: list, rule: str, setting: int = 0) -> dict:
    return next(item for item in rows if item["rule"] == rule and item["setting"] == setting)


def counts(item: dict) -> list:
    return [item[name] for name in COUNTS]


class Generator(unittest.TestCase):
    def test_matches_the_published_values(self) -> None:
        # The first five outputs for seed 1234567, the usual test values for SplitMix64.
        rng = sim.SplitMix64(1234567)
        self.assertEqual(
            [rng.next() for _ in range(5)],
            [
                6457827717110365317,
                3203168211198807973,
                9817491932198370423,
                4593380528125082431,
                16408922859458223821,
            ],
        )

    def test_a_bounded_draw_covers_its_range_and_no_more(self) -> None:
        rng = sim.SplitMix64(7)
        self.assertEqual({rng.below(6) for _ in range(2000)}, set(range(6)))


class Model(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.uses, cls.rows = sim.run(SMALL, WORLDS)

    def test_the_same_seed_gives_the_same_table(self) -> None:
        self.assertEqual(sim.run(SMALL, WORLDS), (self.uses, self.rows))

    def test_a_different_seed_gives_a_different_table(self) -> None:
        self.assertNotEqual(sim.run(dict(SMALL, seed=1), WORLDS), (self.uses, self.rows))

    def test_rerunning_every_time_is_never_outdated_and_reruns_every_reuse(self) -> None:
        item = row(self.rows, "recheck")
        self.assertEqual(item["outdated_uses"], 0)
        self.assertEqual(item["reruns"], self.uses)

    def test_full_declaration_is_never_outdated(self) -> None:
        self.assertEqual(row(self.rows, "standing", 100)["outdated_uses"], 0)

    def test_repeating_the_copy_is_outdated_sometimes(self) -> None:
        # Otherwise the two tests above would pass on a model in which nothing ever changes.
        self.assertGreater(row(self.rows, "trust")["outdated_uses"], 0)

    def test_no_declaration_is_the_same_as_repeating_the_copy(self) -> None:
        self.assertEqual(counts(row(self.rows, "standing", 0)), counts(row(self.rows, "trust")))

    def test_a_timer_that_always_fires_is_the_same_as_rerunning_every_time(self) -> None:
        _, rows = sim.run(dict(SMALL, timer_steps=[-1]), WORLDS)
        self.assertEqual(counts(row(rows, "timer", -1)), counts(row(rows, "recheck")))

    def test_a_timer_that_never_fires_is_the_same_as_repeating_the_copy(self) -> None:
        _, rows = sim.run(dict(SMALL, timer_steps=[10**9]), WORLDS)
        self.assertEqual(counts(row(rows, "timer", 10**9)), counts(row(rows, "trust")))

    def test_full_declaration_finds_exactly_the_changes_that_rerunning_every_time_finds(self) -> None:
        every, full = row(self.rows, "recheck"), row(self.rows, "standing", 100)
        found_by_rerunning = every["reruns"] - every["needless_reruns"]
        found_by_fingerprints = full["reruns"] - full["needless_reruns"]
        self.assertEqual(found_by_fingerprints, found_by_rerunning)
        self.assertLess(full["reruns"], every["reruns"])

    def test_a_check_is_counted_for_every_reuse_of_a_held_or_received_copy(self) -> None:
        first_runs = row(self.rows, "trust")["reruns"]
        for item in self.rows:
            if item["rule"] == "standing":
                self.assertEqual(item["fingerprint_checks"], self.uses - first_runs)


class Stored(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stored = json.loads(sim.RESULT.read_text(encoding="utf-8"))

    def test_the_stored_result_is_reproduced(self) -> None:
        self.assertEqual(self.stored, sim.build())

    def test_every_prediction_is_reported_with_its_outcome(self) -> None:
        self.assertEqual(len(self.stored["predictions"]), len(sim.PREDICTIONS))
        for item in self.stored["predictions"]:
            self.assertIsInstance(item["held"], bool)

    def test_the_stored_result_holds_whole_numbers_only(self) -> None:
        def walk(value: object) -> None:
            self.assertNotIsInstance(value, float)
            if isinstance(value, dict):
                for inner in value.values():
                    walk(inner)
            elif isinstance(value, list):
                for inner in value:
                    walk(inner)

        walk(self.stored)

    def test_the_result_says_it_is_a_model(self) -> None:
        self.assertEqual(self.stored["kind"], "model, not a measurement")
        self.assertTrue(self.stored["does_not_cover"])


if __name__ == "__main__":
    unittest.main()
