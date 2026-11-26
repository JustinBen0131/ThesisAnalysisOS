"""The toy studies run, are reproducible, and say what the theory says they must.

These use small samples, so the bands are wide. The recorded full-size runs in
book/toys/ are the measurements; this only guards the machinery.
"""

import math
import unittest

from qaos_core import report, toy_studies


class ToyStudies(unittest.TestCase):
    def test_sensitivity_follows_sharpe_times_root_years(self):
        out = toy_studies.sensitivity(quick=True)
        for row in out["rows"]:
            self.assertAlmostEqual(row["median_z"], row["expected_z"], delta=0.35, msg=str(row))
            self.assertLessEqual(row["power_3sigma"]["k"], row["power_2sigma"]["k"])
        ten = [row for row in out["rows"] if row["years"] == 10]
        self.assertTrue(all(a["power_2sigma"]["rate"] <= b["power_2sigma"]["rate"] + 0.05 for a, b in zip(ten, ten[1:])))
        self.assertAlmostEqual(out["years_for_3_sigma"]["0.5"], 36.0)
        self.assertIn("36", out["headline"])

    def test_the_same_seed_gives_the_same_study(self):
        first = toy_studies.overfit(quick=True, seed=9)
        again = toy_studies.overfit(quick=True, seed=9)
        other = toy_studies.overfit(quick=True, seed=10)
        self.assertEqual(first["rows"], again["rows"])
        self.assertNotEqual(first["rows"], other["rows"])

    def test_a_search_on_noise_inflates_and_the_rotation_test_does_not(self):
        out = toy_studies.look_elsewhere(quick=True)
        wide = [row for row in out["rows"] if row["family"] == "unrelated rules"]
        narrow = [row for row in out["rows"] if row["family"] == "trend windows"]
        self.assertEqual([row["grid"] for row in wide], [1, 5, 20])
        self.assertLess(wide[0]["false_positive"]["naive"]["rate"], 0.2)
        self.assertGreater(wide[-1]["mean_best_sharpe"], 0.3, "twenty unrelated tries find a good-looking Sharpe in noise")
        self.assertGreater(wide[-1]["false_positive"]["naive"]["rate"], 0.4)
        self.assertLess(wide[-1]["false_positive"]["mixed_event"]["rate"], 0.2)
        self.assertLess(wide[-1]["false_positive"]["deflated"]["rate"], 0.25)
        self.assertGreater(wide[-1]["effective_trials"], 10.0)
        self.assertLess(narrow[-1]["effective_trials"], 5.0, "trend windows are near-copies of each other")
        self.assertLess(narrow[-1]["mean_best_sharpe"], wide[-1]["mean_best_sharpe"])
        self.assertIn("unrelated rules", out["headline"])

    def test_pulls_have_unit_width_on_well_behaved_returns(self):
        out = toy_studies.pulls(quick=True)
        normal = out["rows"][0]
        self.assertEqual(normal["market"], "normal, independent")
        for label in ("mertens", "newey_west", "bootstrap"):
            self.assertAlmostEqual(normal["errors"][label]["pull_width"], 1.0, delta=0.2, msg=label)
        self.assertAlmostEqual(normal["true_spread"], 1.0 / math.sqrt(10.0), delta=0.06)

    def test_the_winner_on_noise_does_not_repeat(self):
        out = toy_studies.overfit(quick=True)
        null, signal = out["rows"]
        self.assertEqual(null["r2"], 0.0)
        self.assertGreater(null["development_best"], 0.0)
        self.assertLess(null["holdout_same_config"], null["development_best"])
        self.assertLess(abs(null["holdout_same_config"]), 0.25)
        self.assertGreater(signal["holdout_same_config"], null["holdout_same_config"])

    def test_power_runs_and_counts(self):
        out = toy_studies.power(quick=True)
        for row in out["rows"]:
            for name in ("sharpe", "alpha", "timing"):
                cell = row["confirmed"][name]
                self.assertEqual(cell["n"], 100)
                self.assertTrue(0 <= cell["k"] <= 100)
        null = out["rows"][0]
        self.assertLess(null["confirmed"]["alpha"]["rate"], 0.15)
        self.assertLess(null["confirmed"]["timing"]["rate"], 0.15)

    def test_every_study_renders(self):
        for name, study in toy_studies.STUDIES.items():
            if name in ("look_elsewhere", "pulls", "power"):
                continue    # rendered through the CLI test and the cases above
            text = report.render_toy(study(quick=True))
            self.assertIn(name, text)
            self.assertNotIn("nan", text.lower())


if __name__ == "__main__":
    unittest.main()
