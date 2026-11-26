import unittest

import numpy as np

from qaos_core import gates, strategies, toys


def market(assets=3, periods=900, seed=1):
    corr = np.full((assets, assets), 0.3) + 0.7 * np.eye(assets)
    raw = toys.correlated(1, periods, [0.06] * assets, [0.15, 0.20, 0.10][:assets] + [0.12] * max(0, assets - 3), corr, rng=toys.generator(seed))
    return toys.as_market(raw)[1][0]


class Rolling(unittest.TestCase):
    def test_rolling_mean_and_std_match_the_slow_way(self):
        x = market()
        mean = strategies.rolling_mean(x, 20)
        sd = strategies.rolling_std(x, 20)
        self.assertTrue(np.isnan(mean[:19]).all())
        for t in (19, 20, 137, 899):
            np.testing.assert_allclose(mean[t], x[t - 19:t + 1].mean(axis=0), rtol=1e-10)
            np.testing.assert_allclose(sd[t], x[t - 19:t + 1].std(axis=0, ddof=1), rtol=1e-7)

    def test_an_asset_that_starts_late_waits_for_a_full_window(self):
        x = market()
        x[:100, 1] = np.nan
        mean = strategies.rolling_mean(x, 20)
        self.assertTrue(np.isnan(mean[:119, 1]).all())
        self.assertTrue(np.isfinite(mean[119:, 1]).all())
        self.assertTrue(np.isfinite(mean[19:, 0]).all())

    def test_lagged(self):
        x = np.arange(10.0).reshape(10, 1)
        out = strategies.lagged(x, 3)
        self.assertTrue(np.isnan(out[:3]).all())
        np.testing.assert_array_equal(out[3:, 0], np.arange(7.0))


class Rules(unittest.TestCase):
    def test_trend_matches_the_definition(self):
        x = market(1)
        w = strategies.trend_sma(x, 50)
        for t in (10, 49, 50, 300, 899):
            expected = 1.0 if t >= 49 and x[t, 0] > x[t - 49:t + 1, 0].mean() else 0.0
            self.assertEqual(w[t, 0], expected, t)

    def test_weights_respect_their_budget(self):
        x = market(4)
        for name, params in (("hold", {}), ("trend_sma", {"window": 40}), ("inverse_vol", {"vol_window": 30}),
                             ("trend_inverse_vol", {"window": 40, "vol_window": 30}), ("xs_momentum", {"lookback": 120, "skip": 10, "top": 0.5}),
                             ("vol_target", {"vol_window": 30}), ("tsmom", {"lookback": 120, "skip": 10, "vol_window": 30})):
            w = strategies.build(name, x, params)
            self.assertEqual(w.shape, x.shape, name)
            self.assertTrue(np.isfinite(w).all(), name)
            self.assertTrue((w >= -1e-12).all(), name)
            self.assertLessEqual(w.sum(axis=1).max(), 1.0 + 1e-9, name)

    def test_inverse_vol_gives_the_calm_asset_more(self):
        x = market(3)
        w = strategies.inverse_vol(x, 60)[-1]
        self.assertAlmostEqual(w.sum(), 1.0, places=12)
        self.assertGreater(w[2], w[1])       # 10% vol against 20% vol

    def test_cross_sectional_momentum_holds_the_top_fraction(self):
        x = market(4)
        w = strategies.xs_momentum(x, lookback=120, skip=10, top=0.5)
        self.assertTrue((np.count_nonzero(w[200:], axis=1) == 2).all())
        t = 500
        past = x[t - 10] / x[t - 120] - 1.0
        self.assertEqual(set(np.argsort(-past)[:2]), set(np.nonzero(w[t])[0]))

    def test_no_weight_where_there_is_no_price(self):
        x = market(3)
        x[:300, 2] = np.nan
        for name in ("hold", "trend_sma", "inverse_vol", "vol_target", "tsmom", "xs_momentum", "trend_inverse_vol"):
            w = strategies.build(name, x, {})
            self.assertTrue((w[:300, 2] == 0).all(), name)

    def test_pairs_trade_is_dollar_neutral_and_reverts(self):
        prices = toys.ou_pair(1, 1500, rng=toys.generator(2))[0]
        w = strategies.pairs_zscore(prices, window=60, entry=1.5, exit=0.3)
        np.testing.assert_allclose(w.sum(axis=1), 0.0, atol=1e-12)
        self.assertGreater(np.count_nonzero(w[:, 0]), 50)
        with self.assertRaises(ValueError):
            strategies.pairs_zscore(market(3))

    def test_unknown_strategy_is_named(self):
        with self.assertRaises(KeyError):
            strategies.build("alchemy", market(1))


class Schedules(unittest.TestCase):
    def test_month_starts_and_ends(self):
        dates = np.arange("2024-01-29", "2024-03-06", dtype="datetime64[D]")
        dates = dates[np.is_busday(dates)]
        starts = strategies.month_starts(dates)
        self.assertEqual([str(d) for d in dates[starts]], ["2024-02-01", "2024-03-01"])
        ends = strategies.month_ends(dates)
        self.assertEqual([str(d) for d in dates[ends]], ["2024-01-31", "2024-02-29"])
        self.assertFalse(starts[0])

    def test_every(self):
        np.testing.assert_array_equal(np.nonzero(strategies.every(10, 3, 1))[0], [1, 4, 7])


class Causality(unittest.TestCase):
    def test_every_registered_strategy_is_causal(self):
        x = market(4, 700)
        pair = toys.ou_pair(1, 700, rng=toys.generator(3))[0]
        for name in strategies.REGISTRY:
            prices = pair if name == "pairs_zscore" else x
            out = gates.causality(name, {}, prices)
            self.assertEqual(out["verdict"], "holds", "{0}: {1}".format(name, out))

    def test_a_strategy_that_looks_ahead_is_caught(self):
        def cheat(prices, **_):
            return (prices > np.nanmean(prices, axis=-2, keepdims=True)).astype(float)   # full-sample mean

        def tomorrow(prices, **_):
            out = np.zeros(prices.shape)
            out[:-1] = (prices[1:] > prices[:-1]).astype(float)
            return out

        strategies.REGISTRY["cheat"] = cheat
        strategies.REGISTRY["tomorrow"] = tomorrow
        try:
            self.assertEqual(gates.causality("cheat", {}, market(1))["verdict"], "fails")
            self.assertEqual(gates.causality("tomorrow", {}, market(1))["verdict"], "fails")
        finally:
            del strategies.REGISTRY["cheat"], strategies.REGISTRY["tomorrow"]

    def test_too_short_to_probe_is_unknown_not_a_pass(self):
        self.assertEqual(gates.causality("hold", {}, market(1)[:4])["verdict"], "unknown")


if __name__ == "__main__":
    unittest.main()
