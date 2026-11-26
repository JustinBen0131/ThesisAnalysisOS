import math
import unittest

import numpy as np

from qaos_core import stats, toys


class Normal(unittest.TestCase):
    def test_three_sigma_is_the_usual_p(self):
        self.assertAlmostEqual(stats.z_from_p(0.0013498980316301), 3.0, places=6)
        self.assertAlmostEqual(stats.p_from_z(5.0), 2.866515718791933e-07, places=15)
        self.assertAlmostEqual(stats.z_from_p(0.5), 0.0, places=12)
        self.assertEqual(stats.z_from_p(0.0), float("inf"))

    def test_far_tail_does_not_round_to_zero(self):
        self.assertGreater(stats.p_from_z(10.0), 0.0)
        self.assertAlmostEqual(stats.z_from_p(stats.p_from_z(7.5)), 7.5, places=6)

    def test_wilson_interval_behaves_at_the_edges(self):
        lo, hi = stats.wilson_interval(0, 50)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.0)
        lo, hi = stats.wilson_interval(50, 50)
        self.assertEqual(hi, 1.0)
        lo, hi = stats.wilson_interval(20, 100)
        self.assertTrue(lo < 0.2 < hi)


class SharpeRatio(unittest.TestCase):
    def test_value_and_annualisation(self):
        x = np.array([0.01, -0.01, 0.02, 0.0, 0.01])
        expected = x.mean() / x.std(ddof=1) * math.sqrt(252)
        self.assertAlmostEqual(float(stats.sharpe(x, 252)), expected, places=12)
        self.assertTrue(np.isnan(stats.sharpe(np.zeros(10))))

    def test_standard_error_reduces_to_the_textbook_one(self):
        self.assertAlmostEqual(stats.sharpe_se(0.0, 101), 0.1, places=12)
        self.assertAlmostEqual(stats.sharpe_se(0.2, 1001), math.sqrt((1 + 0.5 * 0.04) / 1000), places=12)
        self.assertGreater(stats.sharpe_se(0.1, 500, skew=-1.0, kurt=8.0), stats.sharpe_se(0.1, 500))

    def test_psr_and_track_record(self):
        self.assertAlmostEqual(stats.psr(0.0, 0.0, 500), 0.5, places=12)
        self.assertGreater(stats.psr(0.1, 0.0, 2000), stats.psr(0.1, 0.0, 200))
        n = stats.min_track_record(0.05, 0.0, z=1.645)
        self.assertAlmostEqual(stats.psr(0.05, 0.0, int(round(n))), 0.95, places=2)
        self.assertEqual(stats.min_track_record(0.0, 0.1), float("inf"))

    def test_expected_max_matches_a_direct_simulation(self):
        rng = np.random.default_rng(5)
        for trials in (5, 50, 500):
            simulated = rng.standard_normal((20000, trials)).max(axis=1).mean()
            self.assertAlmostEqual(stats.expected_max_sharpe(trials, 1.0), simulated, delta=0.04)
        self.assertEqual(stats.expected_max_sharpe(1, 1.0), 0.0)
        self.assertEqual(stats.expected_max_sharpe(50, 0.0), 0.0)

    def test_deflation_only_ever_lowers_the_claim(self):
        alone = stats.deflated_sharpe(0.08, 2520, 0.0, 3.0, 1, 0.0)
        searched = stats.deflated_sharpe(0.08, 2520, 0.0, 3.0, 100, 1.0 / 2520)
        self.assertAlmostEqual(alone["dsr"], stats.psr(0.08, 0.0, 2520), places=12)
        self.assertLess(searched["dsr"], alone["dsr"])
        self.assertLess(searched["z"], alone["z"])

    def test_effective_trials(self):
        rng = np.random.default_rng(1)
        same = np.tile(rng.standard_normal(500), (8, 1))
        self.assertAlmostEqual(stats.effective_trials(same), 1.0, places=6)
        independent = rng.standard_normal((8, 20000))
        self.assertAlmostEqual(stats.effective_trials(independent), 8.0, delta=0.1)
        self.assertEqual(stats.effective_trials(np.zeros((3, 10))), 0.0)


class Robust(unittest.TestCase):
    def test_hac_with_no_lags_is_the_ordinary_t(self):
        x = np.random.default_rng(2).standard_normal(400) + 0.1
        t, se = stats.hac_tstat(x, lags=0)
        ordinary = x.mean() / (x.std(ddof=0) / math.sqrt(400))
        self.assertAlmostEqual(t, ordinary, places=10)

    def test_hac_widens_for_positive_autocorrelation(self):
        rng = np.random.default_rng(3)
        e = rng.standard_normal(5000)
        x = np.empty(5000)
        x[0] = e[0]
        for t in range(1, 5000):
            x[t] = 0.6 * x[t - 1] + e[t]
        self.assertGreater(stats.hac_tstat(x)[1], stats.hac_tstat(x, lags=0)[1] * 1.5)

    def test_batch_equals_one_at_a_time(self):
        x = np.random.default_rng(4).standard_normal((6, 300)) + 0.05
        t, se = stats.hac_tstat(x)
        for row in range(6):
            one_t, one_se = stats.hac_tstat(x[row])
            self.assertAlmostEqual(t[row], one_t, places=12)
            self.assertAlmostEqual(se[row], one_se, places=12)

    def test_alpha_beta_recovers_what_was_put_in(self):
        rng = np.random.default_rng(6)
        market = rng.standard_normal(20000) * 0.01
        y = 0.0002 + 0.7 * market + rng.standard_normal(20000) * 0.002
        out = stats.alpha_beta(y, market, 252)
        self.assertAlmostEqual(out["beta"], 0.7, delta=0.01)
        self.assertAlmostEqual(out["alpha_ann"], 0.0002 * 252, delta=0.01)
        self.assertGreater(out["t_alpha"], 8.0)

    def test_alpha_beta_matches_a_plain_sandwich(self):
        rng = np.random.default_rng(7)
        x = toys.garch(1, 1500, mu_ann=0.05, rng=toys.generator(8))[0]
        y = 0.4 * x + rng.standard_normal(1500) * 0.004
        out = stats.alpha_beta(y, x)
        n = 1500
        design = np.column_stack([np.ones(n), x])
        inv = np.linalg.inv(design.T @ design)
        coef = inv @ design.T @ y
        resid = y - design @ coef
        lags = stats.default_lags(n)
        score = design * resid[:, None]
        meat = score.T @ score
        for k in range(1, lags + 1):
            cross = score[k:].T @ score[:-k]
            meat += (1 - k / (lags + 1)) * (cross + cross.T)
        cov = inv @ meat @ inv
        self.assertAlmostEqual(out["t_alpha"], coef[0] / math.sqrt(cov[0, 0]), places=8)
        self.assertAlmostEqual(out["se_beta"], math.sqrt(cov[1, 1]), places=10)


class Bootstrap(unittest.TestCase):
    def test_indices_are_blocks(self):
        rng = np.random.default_rng(9)
        idx = stats.stationary_bootstrap_indices(1000, 20, 200, rng)
        self.assertEqual(idx.shape, (200, 1000))
        self.assertTrue(idx.min() >= 0 and idx.max() < 1000)
        steps = (np.diff(idx, axis=1) % 1000) == 1
        self.assertAlmostEqual(1.0 / (1.0 - steps.mean()), 20.0, delta=1.5)

    def test_interval_brackets_the_estimate_and_scales(self):
        x = toys.gaussian(1, 2520, mu_ann=0.08, vol_ann=0.16, rng=toys.generator(10))[0]
        out = stats.bootstrap_sharpe(x, 252, n_boot=800, rng=np.random.default_rng(1))
        self.assertTrue(out["lo95"] < out["lo68"] < out["sr"] < out["hi68"] < out["hi95"])
        self.assertAlmostEqual(out["se"], 1.0 / math.sqrt(10.0), delta=0.06)
        self.assertTrue(0.0 < out["p_le_zero"] <= 1.0)


class Path(unittest.TestCase):
    def test_max_drawdown_by_hand(self):
        net = np.array([0.10, -0.50, 0.20, 0.50, -0.10])
        nav = np.cumprod(1 + net)
        self.assertAlmostEqual(float(stats.max_drawdown(net)), nav[1] / nav[0] - 1.0, places=12)
        self.assertEqual(float(stats.max_drawdown(np.array([0.01, 0.02]))), 0.0)
        self.assertAlmostEqual(float(stats.max_drawdown(np.array([-0.1, 0.0]))), -0.1, places=12)

    def test_summary_is_complete_and_finite(self):
        x = toys.garch(1, 2000, mu_ann=0.06, rng=toys.generator(11))[0]
        out = stats.summarize(x, 0.02 / 252, 252)
        for key in ("sharpe", "sharpe_se", "t_hac", "cagr", "vol_ann", "max_drawdown", "skew", "kurt", "psr0"):
            self.assertTrue(math.isfinite(out[key]), key)
        self.assertEqual(out["n"], 2000)
        self.assertLessEqual(out["max_drawdown"], 0.0)

    def test_sensitivity_law(self):
        self.assertAlmostEqual(stats.expected_z(0.5, 36.0), 3.0, places=12)
        self.assertAlmostEqual(stats.years_for_z(0.5, 3.0), 36.0, places=12)
        self.assertEqual(stats.years_for_z(0.0), float("inf"))


if __name__ == "__main__":
    unittest.main()
