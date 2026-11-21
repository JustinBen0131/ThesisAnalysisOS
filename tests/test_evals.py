"""The evaluations are code too. A small run of each keeps them from rotting."""

from __future__ import annotations

import importlib.util
import unittest

from helpers import REPO


def load(name: str):
    spec = importlib.util.spec_from_file_location("evals_" + name, str(REPO / "evals" / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestEvals(unittest.TestCase):
    def test_the_reuse_predictions_hold_on_a_small_run(self) -> None:
        reuse = load("reuse_frontier")
        result = reuse.experiment(edits=8, seed=3, ks=(1, 6, 12), timing=False)
        self.assertEqual({key: item["held"] for key, item in result["predictions"].items()},
                         {key: True for key in reuse.PREDICTIONS})
        rows = {row["policy"]: row for row in result["rows"]}
        self.assertEqual(rows["TAOS, 12 domain(s) declared"]["executions"], rows["oracle (knows what every check reads)"]["executions"])
        self.assertEqual(rows["TAOS, 1 domain(s) declared"]["executions"], rows["rerun everything"]["executions"])

    def test_a_seeded_fault_is_caught_and_every_fault_still_applies(self) -> None:
        mutations = load("mutations")
        self.assertGreaterEqual(len(mutations.FAULTS), 12)
        self.assertEqual(len({fault[0] for fault in mutations.FAULTS}), len(mutations.FAULTS))
        for name, relative, protection, _, module in mutations.FAULTS:
            self.assertEqual((REPO / relative).read_text(encoding="utf-8").count(protection), 1, name)
            self.assertTrue((REPO / "tests" / (module + ".py")).is_file(), name)
        self.assertTrue(mutations.caught(mutations.FAULTS[0]))


if __name__ == "__main__":
    unittest.main()
