import contextlib
import io
import json
import math
import random
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from paperbot import core_index, evidence, kalshi_maker
from paperbot.__main__ import main
from paperbot.ledger import Ledger

CORE = {
    "contribution_usd_per_week": 100.0,
    "vol_target_annual": 0.16,
    "variance_window_days": 21,
    "rebalance_band": 0.05,
    "cost_bps_per_side": 5.0,
}
KALSHI = {
    "eligible": {"favorite_ask_min": 0.80, "favorite_ask_max": 0.95, "days_to_close_min": 1, "days_to_close_max": 30},
    "order": {"contracts": 10, "max_new_per_run": 50, "max_open": 500, "expire_hours": 24},
    "lambda": 0.5,
}
NOW = 1_800_000_000.0  # 2027-01-15


def business_days(start: str, n: int):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


class FakeSource:
    def __init__(self, markets=(), market_info=None, trades=None):
        self.markets, self.info, self.tr = list(markets), dict(market_info or {}), dict(trades or {})

    def open_markets(self, max_pages=20):
        return self.markets

    def market(self, ticker):
        return self.info.get(ticker, {})

    def trades(self, ticker, min_ts):
        return [t for t in self.tr.get(ticker, []) if t["ts"] >= min_ts]


class LedgerChain(unittest.TestCase):
    def test_edit_to_history_is_detected(self):
        tmp = Path(tempfile.mkdtemp())
        led = Ledger(tmp / "l.jsonl")
        for i in range(3):
            led.append("x", {"i": i})
        self.assertTrue(led.verify()[0])
        lines = (tmp / "l.jsonl").read_text().splitlines()
        lines[1] = lines[1].replace('"i":1', '"i":7')
        (tmp / "l.jsonl").write_text("\n".join(lines) + "\n")
        good, detail = led.verify()
        self.assertFalse(good)
        self.assertIn("record 1", detail)


class Evidence(unittest.TestCase):
    def test_batch_factor_has_mean_one_under_calibrated_prices(self):
        rng = random.Random(3)
        total, n = 0.0, 40000
        for _ in range(n):
            q = rng.uniform(0.8, 0.95)
            y = 1.0 if rng.random() < q else 0.0
            total += evidence.batch_factor([(y, q)], 0.5)
        self.assertAlmostEqual(total / n, 1.0, delta=0.01)

    def test_null_false_alarm_rate_stays_below_alpha(self):
        rng = random.Random(11)
        alarms, paths = 0, 600
        for _ in range(paths):
            log_e, hit = 0.0, False
            for _ in range(300):
                batch = []
                for _ in range(5):
                    q = rng.uniform(0.8, 0.95)
                    batch.append((1.0 if rng.random() < q else 0.0, q))
                log_e = evidence.update(log_e, evidence.batch_factor(batch, 0.5))
                if log_e >= math.log(20):
                    hit = True
                    break
            alarms += hit
        self.assertLessEqual(alarms / paths, 0.05 + 2 * math.sqrt(0.05 * 0.95 / paths))

    def test_planted_edge_is_detected(self):
        rng = random.Random(5)
        log_e = 0.0
        for _ in range(400):
            batch = []
            for _ in range(5):
                q = rng.uniform(0.8, 0.9)
                batch.append((1.0 if rng.random() < q + 0.06 else 0.0, q))
            log_e = evidence.update(log_e, evidence.batch_factor(batch, 0.5))
        self.assertGreater(math.exp(log_e), 20.0)


class CoreTrack(unittest.TestCase):
    def test_weeks_owed(self):
        self.assertEqual(core_index.weeks_between(None, "2026-11-26"), 1)
        self.assertEqual(core_index.weeks_between("2026-W48", "2026-11-27"), 0)
        self.assertEqual(core_index.weeks_between("2026-W48", "2026-12-01"), 1)
        self.assertEqual(core_index.weeks_between("2026-W46", "2026-12-01"), 3)

    def test_target_weight_caps_at_one_and_scales_down_in_high_vol(self):
        calm = [100.0 * (1.0005 ** i) for i in range(30)]
        self.assertEqual(core_index.target_weight(calm, CORE), 1.0)
        wild = [100.0 * (1.04 if i % 2 else 0.96) ** (i % 2) for i in range(30)]
        w = core_index.target_weight(wild, CORE)
        var = core_index.realized_var_annual(wild, 21)
        self.assertAlmostEqual(w, 0.16 ** 2 / var, places=12)
        self.assertLess(w, 0.1)

    def test_contributions_never_count_as_performance(self):
        state, closes = {}, []
        for day in business_days("2026-01-05", 60):
            closes.append({"date": day, "close": 100.0})
            core_index.step(state, list(closes), CORE, halted=False)
        s = state["arms"]["strategy"]
        self.assertAlmostEqual(s["contributed"], 1200.0)  # 12 ISO weeks
        # Flat prices: the only loss is the 5 bp paid to invest each new $100, which
        # dilutes all holders: about 5 bp x (1 + 1/2 + ... + 1/12) = 15.5 bp.
        self.assertLess(state["nav_per_unit"]["strategy"], 1.0)
        self.assertAlmostEqual(state["nav_per_unit"]["strategy"], 1.0 - 5e-4 * sum(1 / k for k in range(1, 13)), delta=2e-4)
        self.assertAlmostEqual(state["e_value"], 1.0, places=6)

    def test_orders_fill_only_at_a_later_close(self):
        state = {}
        core_index.step(state, [{"date": "2026-01-05", "close": 100.0}], CORE, halted=False)
        arm = state["arms"]["benchmark"]
        self.assertEqual(arm["shares"], 0.0)
        self.assertEqual(arm["pending_weight"], 1.0)
        core_index.step(state, [{"date": "2026-01-05", "close": 100.0}, {"date": "2026-01-06", "close": 110.0}], CORE, halted=False)
        self.assertAlmostEqual(arm["cash"], 0.0, places=9)          # fully invested, no borrowing
        self.assertAlmostEqual(arm["costs"], 100.0 * 5e-4 / (1 + 5e-4), places=9)
        self.assertAlmostEqual(arm["shares"] * 110.0 + arm["cash"], 100.0 - arm["costs"], places=9)

    def test_halt_blocks_new_orders(self):
        state = {}
        core_index.step(state, [{"date": "2026-01-05", "close": 100.0}], CORE, halted=True)
        self.assertIsNone(state["arms"]["strategy"]["pending_weight"])


def market(ticker, yes_bid, yes_ask, close_ts, **extra):
    m = {"ticker": ticker, "event_ticker": "EV-" + ticker, "yes_bid": yes_bid, "yes_ask": yes_ask, "close_time": iso(close_ts)}
    m.update(extra)
    return m


class KalshiTrack(unittest.TestCase):
    def test_fee_rounds_up_per_order(self):
        self.assertEqual(kalshi_maker.maker_fee_cents(10, 85.0), 3)   # 2.23 cents -> 3
        self.assertEqual(kalshi_maker.maker_fee_cents(1, 50.0), 1)    # 0.44 cents -> 1
        self.assertEqual(kalshi_maker.maker_fee_cents(100, 50.0), 44)

    def test_candidate_rules(self):
        day = 86400.0
        ok = kalshi_maker.candidate(market("A", 84, 87, NOW + 5 * day), NOW, KALSHI)
        self.assertEqual((ok["side"], ok["price_c"]), ("yes", 85.0))
        no_side = kalshi_maker.candidate(market("B", 10, 14, NOW + 5 * day), NOW, KALSHI)
        self.assertEqual((no_side["side"], no_side["price_c"], no_side["ask_c"]), ("no", 87.0, 90.0))
        self.assertIsNone(kalshi_maker.candidate(market("C", 84, 85, NOW + 5 * day), NOW, KALSHI))   # no room under the ask
        self.assertIsNone(kalshi_maker.candidate(market("D", 50, 52, NOW + 5 * day), NOW, KALSHI))   # not a favorite
        self.assertIsNone(kalshi_maker.candidate(market("E", 84, 87, NOW + 40 * day), NOW, KALSHI))  # too far out
        dollars = {"ticker": "F", "yes_bid_dollars": "0.8400", "yes_ask_dollars": "0.8700", "close_time": iso(NOW + 5 * day)}
        self.assertEqual(kalshi_maker.candidate(dollars, NOW, KALSHI)["price_c"], 85.0)

    def test_fill_needs_a_trade_strictly_through_our_price(self):
        self.assertIsNone(kalshi_maker.filled_by([{"ts": 1, "yes_price": 85}], "yes", 85.0))
        self.assertIsNotNone(kalshi_maker.filled_by([{"ts": 1, "yes_price": 84}], "yes", 85.0))
        self.assertIsNotNone(kalshi_maker.filled_by([{"ts": 1, "yes_price": 14}], "no", 87.0))  # NO printed at 86

    def test_full_cycle_place_fill_settle(self):
        day = 86400.0
        src = FakeSource(markets=[market("A", 84, 87, NOW + 3 * day), market("B", 84, 87, NOW + 2 * day)])
        state = {}
        kalshi_maker.step(state, src, NOW, KALSHI, halted=False)
        self.assertEqual(sorted(state["orders"]), ["A", "B"])
        src.markets = []
        src.tr = {"A": [{"ts": int(NOW + 100), "yes_price": 84}], "B": [{"ts": int(NOW + 100), "yes_price": 85}]}
        kalshi_maker.step(state, src, NOW + 3600, KALSHI, halted=False)
        self.assertIn("A", state["positions"])
        self.assertIn("B", state["orders"])
        src.info = {"A": {"status": "settled", "result": "yes"}}
        kalshi_maker.step(state, src, NOW + 2 * day, KALSHI, halted=False)
        self.assertNotIn("B", state["orders"])          # expired after 24h
        self.assertEqual(state["settled_contracts"], 10)
        self.assertAlmostEqual(state["pnl_usd"], 10 * 1.0 - 10 * 0.85 - 0.03)
        q_eff = (85.0 + 0.3) / 100.0
        self.assertAlmostEqual(state["e_value"], 1.0 + 0.5 * (1.0 / q_eff - 1.0))

    def test_halt_blocks_new_orders(self):
        src = FakeSource(markets=[market("A", 84, 87, NOW + 86400 * 3)])
        state = {}
        kalshi_maker.step(state, src, NOW, KALSHI, halted=True)
        self.assertEqual(state["orders"], {})


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.fx = self.tmp / "fx"
        self.fx.mkdir()
        self.book = self.tmp / "book"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(list(args))
        return code, out.getvalue()

    def test_two_runs_then_verify_and_tamper(self):
        days = business_days("2026-10-01", 40)
        closes = [{"date": d, "close": 600.0 + i} for i, d in enumerate(days)]
        (self.fx / "closes_spy_us.json").write_text(json.dumps(closes[:-1]))
        (self.fx / "markets.json").write_text(json.dumps([market("A", 84, 87, NOW + 86400 * 3)]))
        code, out = self.run_cli("run", "--book", str(self.book), "--fixtures", str(self.fx), "--now", iso(NOW))
        self.assertEqual(code, 0, out)
        (self.fx / "closes_spy_us.json").write_text(json.dumps(closes))
        code, out = self.run_cli("run", "--book", str(self.book), "--fixtures", str(self.fx), "--now", iso(NOW + 3600))
        self.assertEqual(code, 0, out)
        self.assertIn("E-value", out)
        self.assertEqual(self.run_cli("verify", "--book", str(self.book))[0], 0)
        state = json.loads((self.book / "state.json").read_text())
        self.assertGreater(state["core"]["arms"]["benchmark"]["shares"], 0.0)
        ledger = self.book / "ledger.jsonl"
        ledger.write_text(ledger.read_text().replace('"core"', '"c0re"', 1))
        self.assertEqual(self.run_cli("verify", "--book", str(self.book))[0], 1)

    def test_blocked_network_is_recorded_not_fatal_for_the_other_track(self):
        (self.fx / "markets.json").write_text("[]")
        code, out = self.run_cli("run", "--book", str(self.book), "--fixtures", str(self.fx), "--now", iso(NOW))
        self.assertEqual(code, 0)
        self.assertIn("Last core error", out)

    def test_halt_and_resume_are_logged(self):
        self.run_cli("halt", "--book", str(self.book), "--by", "human", "--reason", "drill")
        self.assertTrue((self.book / "HALT").exists())
        self.run_cli("resume", "--book", str(self.book), "--by", "human", "--reason", "drill over")
        kinds = [r["kind"] for r in Ledger(self.book / "ledger.jsonl").read()]
        self.assertEqual(kinds, ["halt", "resume"])


if __name__ == "__main__":
    unittest.main()
