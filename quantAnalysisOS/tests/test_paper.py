import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from qaos_core import engine, paper, store, strategies, toys
from qaos_core.data import Dataset

NO_BRAKE = {"drawdown_brake": None}


def three_assets(periods=300, seed=42):
    corr = np.array([[1.0, 0.3, -0.2], [0.3, 1.0, 0.1], [-0.2, 0.1, 1.0]])
    raw = toys.correlated(1, periods, [0.07, 0.03, 0.05], [0.16, 0.06, 0.15], corr, rng=toys.generator(seed))
    returns, prices = toys.as_market(raw)
    dates = np.busday_offset(np.datetime64("2020-01-01"), np.arange(periods + 1), roll="forward")
    return Dataset("three", dates, ["A", "B", "C"], prices[0], 252.0, np.full(periods + 1, 0.04 / 252))


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.dir = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def open(self, name="t", cash=10000.0, **limits):
        return paper.PaperAccount.open(self.dir, name, cash, limits=limits or None)


class Opening(Base):
    def test_open_and_reopen(self):
        account = self.open()
        self.assertEqual(account.nav, 10000.0)
        self.assertEqual(account.status()["money"], "paper")
        again = paper.PaperAccount(self.dir, "t")
        self.assertEqual(again.cash, 10000.0)
        with self.assertRaises(paper.PaperError):
            self.open()
        with self.assertRaises(paper.PaperError):
            self.open("zero", cash=0.0)
        with self.assertRaises(paper.PaperError):
            paper.PaperAccount(self.dir, "nobody")

    def test_the_paper_broker_does_not_lend(self):
        with self.assertRaises(paper.PaperError):
            self.open("levered", max_gross=2.0)
        with self.assertRaises(paper.PaperError):
            self.open("short", allow_short=True)
        self.assertFalse((self.dir / "levered").exists() or (self.dir / "short").exists())


class Steps(Base):
    def test_an_order_fills_at_the_next_mark_not_this_one(self):
        account = self.open(trade_bps=0.0)
        account.step("2024-01-02", {"X": 100.0}, targets={"X": 1.0})
        self.assertEqual(account.shares, {})
        self.assertEqual(account.status()["pending_order"]["targets"], {"X": 1.0})
        account.step("2024-01-03", {"X": 125.0})
        self.assertAlmostEqual(account.shares["X"], 80.0, places=12)        # bought at 125, not at 100
        account.step("2024-01-04", {"X": 150.0})
        self.assertAlmostEqual(account.nav, 12000.0, places=9)

    def test_costs_and_interest(self):
        account = self.open(trade_bps=10.0)
        account.step("2024-01-02", {"X": 100.0}, targets={"X": 0.5})
        account.step("2024-01-03", {"X": 100.0}, rf_period=0.001)
        self.assertAlmostEqual(account.interest_earned, 10.0, places=9)
        self.assertAlmostEqual(account.costs_paid, 10010.0 * 0.5 * 0.001, places=9)
        self.assertAlmostEqual(account.nav, 10010.0 - 5.005, places=9)
        self.assertAlmostEqual(account.weights()["X"], 0.5, places=12)

    def test_the_ledger_only_moves_forward(self):
        account = self.open()
        account.step("2024-01-03", {"X": 100.0})
        for date in ("2024-01-03", "2024-01-02"):
            with self.assertRaises(paper.PaperError):
                account.step(date, {"X": 100.0})
        with self.assertRaises(paper.PaperError, msg="deciding on a day that was not marked"):
            account.order("2024-01-04", {"X": 1.0})

    def test_a_holding_needs_a_price(self):
        account = self.open()
        account.step("2024-01-02", {"X": 100.0}, targets={"X": 1.0})
        account.step("2024-01-03", {"X": 100.0})
        for bad in ({}, {"X": float("nan")}, {"X": 0.0}):
            with self.assertRaises(paper.PaperError):
                account.step("2024-01-04", bad)
        account.step("2024-01-04", {"X": 101.0})
        with self.assertRaises(paper.PaperError, msg="an order for something never priced"):
            account.order("2024-01-04", {"Y": 0.5})
            account.step("2024-01-05", {"X": 101.0})

    def test_limits_refuse(self):
        account = self.open(max_weight=0.6)
        account.mark("2024-01-02", {"X": 100.0, "Y": 50.0})
        for targets in ({"X": 0.7}, {"X": 0.6, "Y": 0.6}, {"X": -0.2}, {"X": float("nan")}):
            with self.assertRaises(paper.PaperError, msg=str(targets)):
                account.order("2024-01-02", targets)
        account.order("2024-01-02", {"X": 0.6, "Y": 0.4})

    def test_nothing_to_do_is_not_a_fill(self):
        account = self.open(trade_bps=0.0)
        account.step("2024-01-02", {"X": 100.0}, targets={"X": 1.0})
        account.step("2024-01-03", {"X": 100.0}, targets={"X": 1.0})
        account.step("2024-01-04", {"X": 110.0}, targets={"X": 1.0})
        self.assertEqual(account.fills, 1)
        self.assertIsNotNone(account.status()["pending_order"])


class Brake(Base):
    def test_a_deep_drawdown_goes_to_cash_until_a_human_resumes(self):
        account = self.open(drawdown_brake=0.20, trade_bps=0.0)
        account.step("2024-01-02", {"X": 100.0}, targets={"X": 1.0})
        account.step("2024-01-03", {"X": 100.0}, targets={"X": 1.0})
        account.step("2024-01-04", {"X": 79.0}, targets={"X": 1.0})
        self.assertTrue(account.braked)
        account.step("2024-01-05", {"X": 79.0}, targets={"X": 1.0})
        self.assertEqual(account.shares, {})
        account.step("2024-01-08", {"X": 200.0}, targets={"X": 1.0})
        self.assertEqual(account.shares, {}, "still in cash while braked")
        self.assertAlmostEqual(account.nav, 7900.0, places=9)
        with self.assertRaises(paper.PaperError):
            account.resume(by="")
        account.resume(by="the human", note="reviewed")
        self.assertFalse(account.braked)
        self.assertEqual(account.drawdown(), 0.0)
        reopened = paper.PaperAccount(self.dir, "t")
        self.assertFalse(reopened.braked)
        self.assertEqual(reopened.high_water, reopened.nav)
        reopened.step("2024-01-09", {"X": 200.0})
        self.assertIn("X", reopened.shares)


class AgainstTheEngine(Base):
    """Two implementations, one answer."""

    def compare(self, weights_of, rebalance=None, band=0.0, bps=5.0):
        data = three_assets()
        weights = weights_of(data.prices)
        reference = engine.run(data.returns, weights, rf=data.rf, costs=engine.Costs(bps, 0, 0, 0), lag=1,
                               rebalance=rebalance, band=band)
        account = self.open(trade_bps=bps, band=band, drawdown_brake=None)
        paper.run_through(account, data.dates, data.symbols, data.prices, data.rf, weights, rebalance=rebalance)
        _, nav = account.nav_series()
        np.testing.assert_allclose(nav / 10000.0, reference.nav(), rtol=1e-11)
        self.assertTrue(account.ledger.verify()[0])
        self.assertAlmostEqual(account.costs_paid / 10000.0, float((reference.turnover * bps * 1e-4 * np.concatenate([[1.0], reference.nav()[:-1] * (1 + reference.gross[1:])])).sum()), places=9)
        return account

    def test_daily_rebalance(self):
        self.compare(lambda p: strategies.inverse_vol(p, 20))

    def test_weekly_rebalance_with_drift_in_between(self):
        account = self.compare(lambda p: strategies.trend_inverse_vol(p, 50, 20), rebalance=strategies.every(301, 5))
        self.assertGreater(account.fills, 20)

    def test_a_rebalance_band(self):
        self.compare(lambda p: strategies.hold(p, [0.4, 0.4, 0.2]), band=0.02)

    def test_free_trading(self):
        self.compare(lambda p: strategies.trend_sma(p, 30), bps=0.0)


class Mandates(Base):
    def setUp(self):
        super().setUp()
        self.data = three_assets()
        self.mandate = {"dataset": "three", "strategy": "inverse_vol", "params": {"vol_window": 20},
                        "rebalance": {"every": 5}, "stage": "commissioning"}

    def test_a_mandate_is_validated_sealed_and_noted(self):
        account = self.open()
        for bad in ({"strategy": ""}, {"strategy": "alchemy"}, {"stage": "yolo"}, {"stage": "promoted"}):
            with self.assertRaises(paper.PaperError, msg=str(bad)):
                paper.set_mandate(account, dict(self.mandate, **bad))
        sealed = paper.set_mandate(account, self.mandate)
        self.assertTrue(store.seal_holds(sealed))
        self.assertIn("mandate set", account.entries[-1]["text"])
        paper.set_mandate(account, dict(self.mandate, stage="promoted", study="QA-1"))

    def test_a_new_account_starts_today_not_in_the_past(self):
        account = self.open(**NO_BRAKE)
        paper.set_mandate(account, self.mandate)
        steps = paper.advance(account, self.data)
        self.assertEqual(len(steps), 1)
        self.assertEqual(account.last_date, str(self.data.dates[-1]))
        self.assertEqual(account.shares, {})
        self.assertIsNotNone(account.pending, "the first target is decided and waits for tomorrow's close")
        self.assertEqual(paper.advance(account, self.data), [], "no new data, nothing to do")

    def test_advancing_in_pieces_equals_advancing_at_once_and_the_engine(self):
        whole = self.open("whole", **NO_BRAKE)
        paper.set_mandate(whole, self.mandate)
        start = str(self.data.dates[200])
        paper.advance(whole, self.data, from_date=start)
        pieces = self.open("pieces", **NO_BRAKE)
        paper.set_mandate(pieces, self.mandate)
        paper.advance(pieces, self.data.head(240), from_date=start)
        paper.advance(pieces, self.data.head(270))
        paper.advance(pieces, self.data)
        self.assertAlmostEqual(whole.nav, pieces.nav, places=8)
        self.assertEqual(whole.fills, pieces.fills)
        weights = strategies.inverse_vol(self.data.prices, 20)[200:]
        mask = strategies.every(301, 5)[200:].copy()
        mask[0] = True                                  # the account's first day always decides
        reference = engine.run(self.data.returns[200:], weights, rf=self.data.rf[200:], lag=1, rebalance=mask)
        self.assertAlmostEqual(whole.nav / 10000.0, reference.nav()[-1], places=10)
        self.assertIn("replay", whole.entries[2]["source"])

    def test_a_vendor_rescaling_history_does_not_cost_the_account_its_dividend(self):
        account = self.open(trade_bps=0.0, drawdown_brake=None)
        paper.set_mandate(account, dict(self.mandate, strategy="hold", params={"base": [1.0, 0.0, 0.0]}, rebalance="every"))
        paper.advance(account, self.data.head(250), from_date=str(self.data.dates[240]))
        before = account.nav
        self.assertAlmostEqual(account.weights()["A"], 1.0, places=9)
        # the vendor pays a 2% dividend on A and rescales every earlier adjusted close; the next day's return is +1%
        prices = self.data.prices[:251].copy()
        prices[:250, 0] *= 0.98
        prices[250, 0] = prices[249, 0] * 1.01
        revised = Dataset("three", self.data.dates[:251], self.data.symbols, prices, 252.0, np.zeros(251))
        paper.advance(account, revised)
        self.assertAlmostEqual(account.nav / before, 1.01, places=9)
        self.assertEqual(account.last_date, str(self.data.dates[250]))

    def test_data_that_skips_the_last_mark_is_refused(self):
        account = self.open(**NO_BRAKE)
        paper.set_mandate(account, self.mandate)
        paper.advance(account, self.data.head(250))
        gapped = Dataset("three", np.delete(self.data.dates, 249), self.data.symbols, np.delete(self.data.prices, 249, axis=0),
                         252.0, np.delete(self.data.rf, 249))
        with self.assertRaises(paper.PaperError):
            paper.advance(account, gapped)

    def test_the_first_decision_is_made_once_then_the_schedule_rules(self):
        account = self.open(**NO_BRAKE)
        paper.set_mandate(account, dict(self.mandate, strategy="cash", params={}, rebalance={"every": 50}))
        paper.advance(account, self.data.head(210))
        paper.advance(account, self.data.head(240))
        orders = [entry for entry in account.entries if entry["kind"] == "order"]
        self.assertEqual([entry["date"] for entry in orders], [str(self.data.dates[209])],
                         "an all-cash first decision is still a decision; it is not retried every day")

    def test_an_edited_mandate_is_refused(self):
        account = self.open()
        paper.set_mandate(account, self.mandate)
        path = account.dir / "mandate.json"
        record = json.loads(path.read_text())
        record["params"]["vol_window"] = 5
        path.write_text(json.dumps(record))
        with self.assertRaises(paper.PaperError):
            paper.advance(paper.PaperAccount(self.dir, "t"), self.data)

    def test_no_mandate_no_steps(self):
        with self.assertRaises(paper.PaperError):
            paper.advance(self.open(), self.data)


class Tampering(Base):
    def test_an_edited_ledger_fails(self):
        account = self.open(**NO_BRAKE)
        data = three_assets(60)
        paper.run_through(account, data.dates, data.symbols, data.prices, data.rf, strategies.hold(data.prices))
        self.assertEqual(account.status()["ledger"], "holds")
        lines = account.ledger.path.read_text().splitlines()
        entry = json.loads(lines[10])
        entry["nav"] = 99999.0
        lines[10] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        account.ledger.path.write_text("\n".join(lines) + "\n")
        self.assertEqual(paper.PaperAccount(self.dir, "t").status()["ledger"], "fails")


if __name__ == "__main__":
    unittest.main()
