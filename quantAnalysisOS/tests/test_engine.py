import math
import unittest

import numpy as np

from qaos_core import engine, gates, strategies, toys

FREE = engine.Costs(0.0, 0.0, 0.0, 0.0)


def impulse(periods, at, value=1.0):
    out = np.zeros((periods, 1))
    out[at, 0] = value
    return out


class Candles(unittest.TestCase):
    """Things whose answer is known without a market."""

    def test_calibration_gate_holds(self):
        out = gates.calibration(toys_n=1200)
        self.assertEqual(out["verdict"], "holds", [c for c in out["checks"] if c["verdict"] != "holds"])

    def test_holding_is_the_asset_and_cash_is_the_rate(self):
        r, p = toys.as_market(toys.garch(1, 800, mu_ann=0.05, rng=toys.generator(1)))
        held = engine.run(r[0], strategies.hold(p[0]), costs=FREE, lag=0)
        self.assertAlmostEqual(held.nav()[-1], p[0, -1, 0] / p[0, 0, 0], places=10)
        cash = engine.run(r[0], strategies.cash(p[0]), rf=0.0001)
        self.assertAlmostEqual(cash.nav()[-1], 1.0001 ** 800, places=10)

    def test_costs_are_charged_on_what_was_traded(self):
        target = np.zeros((6, 1))
        target[1:3] = 1.0
        out = engine.run(np.zeros((6, 1)), target, costs=engine.Costs(10.0, 0, 0, 0), lag=1)
        np.testing.assert_allclose(out.turnover, [0, 0, 1, 0, 1, 0], atol=1e-15)
        np.testing.assert_allclose(out.net, [0, 0, -0.001, 0, -0.001, 0], atol=1e-15)

    def test_half_weight_earns_half_plus_interest_on_the_rest(self):
        r = np.zeros((3, 1))
        r[2, 0] = 0.10
        out = engine.run(r, np.full((3, 1), 0.5), rf=0.01, costs=FREE, lag=0)
        self.assertAlmostEqual(out.net[2], 0.5 * 0.10 + 0.5 * 0.01, places=15)


class Lag(unittest.TestCase):
    """A target decided at s first earns the return of s + lag + 1. Never earlier."""

    def test_the_return_earned_is_the_one_after_the_trade(self):
        periods = 12
        for lag in (0, 1, 2):
            for spike in range(1, periods):
                returns = impulse(periods, spike, 0.05)
                weights = impulse(periods, 4)            # in the market for exactly one decision, at s=4
                weights[5:, 0] = 0.0
                earned = engine.run(returns, weights, costs=FREE, lag=lag).net.sum()
                expected = 0.05 if spike == 4 + lag + 1 else 0.0
                self.assertAlmostEqual(earned, expected, places=15, msg="lag {0}, spike at {1}".format(lag, spike))

    def test_negative_lag_is_refused(self):
        with self.assertRaises(ValueError):
            engine.run(np.zeros((4, 1)), np.zeros((4, 1)), lag=-1)

    def test_knowing_todays_return_today_earns_nothing(self):
        r = toys.as_market(toys.gaussian(1, 5000, rng=toys.generator(2)))[0][0]
        peek = np.sign(r)
        self.assertLess(abs(float(engine.run(r, peek, costs=FREE, lag=0).sharpe())), 1.0)
        cheat = np.roll(peek, -1, axis=0)                # tomorrow's sign: what a look-ahead bug looks like
        self.assertGreater(float(engine.run(r, cheat, costs=FREE, lag=0).sharpe()), 10.0)


class Mechanics(unittest.TestCase):
    def test_weights_drift_between_rebalances(self):
        r = np.zeros((4, 2))
        r[2] = [0.20, 0.0]
        target = np.tile([0.5, 0.5], (4, 1))
        mask = np.array([True, False, False, False])
        out = engine.run(r, target, costs=FREE, lag=0, rebalance=mask, keep_weights=True)
        np.testing.assert_allclose(out.held[3], [0.6 / 1.1, 0.5 / 1.1], atol=1e-15)
        self.assertEqual(float(out.turnover.sum()), 1.0)

    def test_rebalancing_trades_the_drift_back(self):
        r = np.zeros((4, 2))
        r[2] = [0.20, 0.0]
        target = np.tile([0.5, 0.5], (4, 1))
        out = engine.run(r, target, costs=FREE, lag=0)
        self.assertAlmostEqual(out.turnover[2], abs(0.5 - 0.6 / 1.1) + abs(0.5 - 0.5 / 1.1), places=15)

    def test_band_skips_small_trades(self):
        r = np.zeros((4, 2))
        r[2] = [0.02, 0.0]
        target = np.tile([0.5, 0.5], (4, 1))
        self.assertEqual(float(engine.run(r, target, costs=FREE, lag=0, band=0.05).turnover[1:].sum()), 0.0)
        self.assertGreater(float(engine.run(r, target, costs=FREE, lag=0, band=0.001).turnover[1:].sum()), 0.0)

    def test_borrowing_and_shorting_cost_what_they_say(self):
        flat = np.zeros((3, 1))
        levered = engine.run(flat, np.full((3, 1), 2.0), rf=0.0, costs=engine.Costs(0, 0.252, 0, 0), lag=0, periods_per_year=252)
        self.assertAlmostEqual(levered.net[2], -1.0 * 0.001, places=15)
        short = engine.run(flat, np.full((3, 1), -1.0), rf=0.0, costs=engine.Costs(0, 0, 0.252, 0), lag=0, periods_per_year=252)
        self.assertAlmostEqual(short.net[2], -0.001, places=15)

    def test_ruin_is_absorbing(self):
        r = np.zeros((5, 1))
        r[2, 0] = -0.6
        out = engine.run(r, np.full((5, 1), 2.0), costs=FREE, lag=0)
        self.assertEqual(out.net[2], -1.0)
        self.assertEqual(out.nav()[-1], 0.0)
        self.assertEqual(float(out.turnover[3:].sum()), 0.0)

    def test_a_position_without_a_price_is_a_bug(self):
        r = np.zeros((4, 1))
        r[2, 0] = np.nan
        with self.assertRaises(ValueError):
            engine.run(r, np.ones((4, 1)), lag=0)
        engine.run(r, np.zeros((4, 1)), lag=0)  # no position, no problem

    def test_shapes_must_agree(self):
        with self.assertRaises(ValueError):
            engine.run(np.zeros((4, 2)), np.zeros((4, 1)))
        with self.assertRaises(ValueError):
            engine.run(np.zeros((4, 1)), np.zeros((4, 1)), rebalance=np.ones(3, dtype=bool))


class Batches(unittest.TestCase):
    def setUp(self):
        raw = toys.garch(5, 600, mu_ann=0.05, rng=toys.generator(3))
        self.returns, self.prices = toys.as_market(raw)
        self.weights = strategies.trend_sma(self.prices, 50)

    def test_a_batch_is_the_same_as_one_at_a_time(self):
        batch = engine.run(self.returns, self.weights, rf=0.0001)
        for b in range(5):
            single = engine.run(self.returns[b], self.weights[b], rf=0.0001)
            np.testing.assert_allclose(batch.net[b], single.net, atol=1e-15)
            np.testing.assert_allclose(batch.turnover[b], single.turnover, atol=1e-15)

    def test_lean_keeps_the_same_returns(self):
        full = engine.run(self.returns, self.weights)
        lean = engine.run(self.returns, self.weights, lean=True)
        np.testing.assert_array_equal(full.net, lean.net)
        self.assertIsNone(lean.turnover)
        with self.assertRaises(ValueError):
            engine.Result(lean.net[0], None, None, None, lean.rf, 252.0).summary()

    def test_a_shift_of_zero_changes_nothing(self):
        plain = engine.run(self.returns[0], self.weights[0])
        shifted = engine.run(self.returns[0], self.weights[0], shifts=np.array([0, 601]))
        np.testing.assert_allclose(shifted.net[0], plain.net, atol=1e-15)
        np.testing.assert_allclose(shifted.net[1], plain.net, atol=1e-15)

    def test_a_shift_is_a_rotation_of_the_weights(self):
        k = 137
        rolled = np.roll(self.weights[0], k, axis=0)
        direct = engine.run(self.returns[0], rolled)
        shifted = engine.run(self.returns[0], self.weights[0], shifts=np.array([k]))
        np.testing.assert_allclose(shifted.net[0], direct.net, atol=1e-15)

    def test_shifts_rotate_the_rebalance_mask_too(self):
        mask = strategies.every(601, 7)
        k = 40
        direct = engine.run(self.returns[0], np.roll(self.weights[0], k, axis=0), rebalance=np.roll(mask, k))
        shifted = engine.run(self.returns[0], self.weights[0], rebalance=mask, shifts=np.array([k]))
        np.testing.assert_allclose(shifted.net[0], direct.net, atol=1e-15)


class MixedEvent(unittest.TestCase):
    def test_noise_has_no_timing_and_an_oracle_has_plenty(self):
        raw, signal = toys.latent_drift(1, 2520, mu_ann=0.0, r2=0.05, rng=toys.generator(4), return_signal=True)
        returns, prices = toys.as_market(raw)
        oracle = np.zeros_like(returns[0])
        oracle[:-1, 0] = (signal[0] > 0).astype(float)      # at close t, the drift of t+1: real skill
        found = engine.mixed_event_null(returns[0], oracle, costs=FREE, lag=0, n_shifts=150, rng=np.random.default_rng(1))
        self.assertLessEqual(found["p_global"], 0.02)
        self.assertGreater(found["z_global"], 2.0)
        noise = toys.as_market(toys.garch(1, 2520, rng=toys.generator(5)))
        blind = strategies.trend_sma(noise[1][0], 100)
        nothing = engine.mixed_event_null(noise[0][0], blind, n_shifts=150, rng=np.random.default_rng(1))
        self.assertGreater(nothing["p_global"], 0.05)
        self.assertEqual(nothing["null"].shape[0], 150)
        self.assertFalse(nothing["at_floor"])
        self.assertAlmostEqual(found["p_floor"], 1.0 / 151.0, places=12)
        self.assertAlmostEqual(found["z_resolution"], 2.477, places=2)
        self.assertEqual(found["at_floor"], found["p_global"] <= found["p_floor"] * 1.000001)

    def test_rotations_available(self):
        self.assertEqual(engine.rotations_available(2520, 252.0), 2000)
        self.assertEqual(engine.rotations_available(1008, 252.0), 505)
        self.assertEqual(engine.rotations_available(587, 12.0), 564)
        self.assertEqual(engine.rotations_available(3, 252.0), 0)

    def test_p_values_are_uniform_under_the_null(self):
        raw = toys.garch(120, 1500, rng=toys.generator(6))
        returns, prices = toys.as_market(raw)
        weights = strategies.trend_sma(prices, 60)
        ps = []
        for b in range(120):
            out = engine.mixed_event_null(returns[b], weights[b], costs=FREE, n_shifts=60, rng=np.random.default_rng(b))
            ps.append(out["p_global"])
        ps = np.asarray(ps)
        self.assertTrue(0.35 < ps.mean() < 0.65, ps.mean())
        self.assertLess((ps < 0.05).mean(), 0.15)

    def test_the_global_p_pays_for_the_search(self):
        raw = toys.garch(1, 2000, rng=toys.generator(7))
        returns, prices = toys.as_market(raw)
        stack = np.stack([strategies.trend_sma(prices[0], w) for w in (10, 20, 40, 80, 160)], axis=0)
        out = engine.mixed_event_null(returns[0], stack, costs=FREE, n_shifts=120, rng=np.random.default_rng(2))
        self.assertEqual(out["p"].shape, (5,))
        self.assertGreaterEqual(out["p_global"], float(out["p"].min()) - 1e-12)

    def test_too_short_a_series_is_refused(self):
        with self.assertRaises(ValueError):
            engine.mixed_event_null(np.zeros((3, 1)), np.zeros((3, 1)), min_shift=5)


if __name__ == "__main__":
    unittest.main()
