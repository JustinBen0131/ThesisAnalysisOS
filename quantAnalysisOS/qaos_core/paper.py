"""The paper account: fake money, real bookkeeping.

A hash-chained ledger of marks, orders and fills. Nothing in this module can
reach a broker; there is no code path that places a real order, by design. The
only thing a paper account spends is time, and the record of how the strategy
behaved while nobody could have known the answer is the product.

One step per market date, in this order, which is the engine's lag of one:

    mark     price the holdings at today's close; cash earns today's interest
    fill     execute the order decided at the previous step, at today's close
    order    decide the next target from data up to today

A test replays a strategy through this broker and through the backtest engine
and holds the two NAV paths to agree to rounding.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from . import store

DEFAULT_LIMITS = {
    "max_gross": 1.0,        # no leverage
    "max_weight": 1.0,       # largest single position
    "allow_short": False,
    "drawdown_brake": 0.20,  # at this loss from the high-water mark, go to cash and wait for a human
    "trade_bps": 5.0,
    "band": 0.0,             # skip a rebalance smaller than this in every weight
}


class PaperError(Exception):
    """A refusal by the paper broker."""


class PaperAccount:
    def __init__(self, book_paper_dir: Path, name: str, clock: Optional[Callable[[], str]] = None) -> None:
        self.name = name
        self.dir = Path(book_paper_dir) / name
        self.ledger = store.ChainLog(self.dir / "ledger.jsonl", clock=clock)
        self._replay()

    # ----------------------------------------------------------------- open
    @staticmethod
    def open(book_paper_dir: Path, name: str, cash: float, currency: str = "USD",
             limits: Optional[Dict[str, Any]] = None, note: str = "",
             clock: Optional[Callable[[], str]] = None) -> "PaperAccount":
        directory = Path(book_paper_dir) / name
        if (directory / "ledger.jsonl").exists():
            raise PaperError("paper account '{0}' already exists".format(name))
        if not cash > 0:
            raise PaperError("an account opens with a positive amount of fake money")
        merged = dict(DEFAULT_LIMITS)
        merged.update(limits or {})
        if float(merged["max_gross"]) > 1.0 or merged.get("allow_short"):
            raise PaperError("the paper broker does not lend: no leverage and no shorts. It has no model of financing costs, "
                             "and a number it cannot cost is a number it will not print.")
        log = store.ChainLog(directory / "ledger.jsonl", clock=clock)
        log.append({"kind": "open", "account": name, "currency": currency, "cash": float(cash),
                    "limits": merged, "money": "paper", "note": note})
        return PaperAccount(book_paper_dir, name, clock=clock)

    # --------------------------------------------------------------- replay
    def _replay(self) -> None:
        """Rebuild the account from the ledger. The ledger is the account."""
        self.entries = self.ledger.read()
        if not self.entries or self.entries[0].get("kind") != "open":
            raise PaperError("no paper account '{0}' at {1}".format(self.name, self.dir))
        first = self.entries[0]
        self.currency = first["currency"]
        self.limits = dict(DEFAULT_LIMITS)
        self.limits.update(first.get("limits") or {})
        self.start_cash = float(first["cash"])
        self.cash = float(first["cash"])
        self.shares: Dict[str, float] = {}
        self.prices: Dict[str, float] = {}
        self.last_date: Optional[str] = None
        self.nav = float(first["cash"])
        self.high_water = self.nav
        self.pending: Optional[Dict[str, Any]] = None
        self.braked = False
        self.history: List[Tuple[str, float]] = []
        self.costs_paid = 0.0
        self.interest_earned = 0.0
        self.fills = 0
        self.orders = 0
        for entry in self.entries[1:]:
            self._apply(entry)

    def _apply(self, entry: Dict[str, Any]) -> None:
        kind = entry.get("kind")
        if kind == "mark":
            self.cash = float(entry["cash"])
            self.prices.update({symbol: float(price) for symbol, price in entry["prices"].items()})
            self.nav = float(entry["nav"])
            self.high_water = max(self.high_water, self.nav)
            self.last_date = entry["date"]
            self.interest_earned += float(entry.get("interest", 0.0))
            self.history.append((entry["date"], self.nav))
        elif kind == "order":
            self.pending = entry
            self.orders += 1
        elif kind == "fill":
            self.cash = float(entry["cash_after"])
            self.shares = {symbol: float(amount) for symbol, amount in entry["shares_after"].items() if abs(float(amount)) > 0}
            self.nav = float(entry["nav_after"])
            self.costs_paid += float(entry["cost"])
            self.fills += 1
            self.pending = None
            if self.history and self.history[-1][0] == entry["date"]:
                self.history[-1] = (entry["date"], self.nav)
        elif kind == "cancel":
            self.pending = None
        elif kind == "brake":
            self.braked = bool(entry.get("on", True))
            if not self.braked:
                self.high_water = self.nav  # a human resumed: drawdown is measured from here

    def _write(self, record: Dict[str, Any]) -> Dict[str, Any]:
        entry = self.ledger.append(record)
        self.entries.append(entry)
        self._apply(entry)
        return entry

    # ----------------------------------------------------------------- view
    def weights(self) -> Dict[str, float]:
        if not self.nav > 0:
            return {}
        return {symbol: amount * self.prices[symbol] / self.nav for symbol, amount in self.shares.items()}

    def drawdown(self) -> float:
        return self.nav / self.high_water - 1.0 if self.high_water > 0 else 0.0

    def status(self) -> Dict[str, Any]:
        ok, detail = self.ledger.verify()
        return {
            "account": self.name, "money": "paper", "currency": self.currency,
            "opened_with": self.start_cash, "nav": self.nav, "cash": self.cash,
            "return_since_open": self.nav / self.start_cash - 1.0,
            "drawdown": self.drawdown(), "high_water": self.high_water,
            "weights": self.weights(), "shares": dict(self.shares),
            "last_mark": self.last_date, "marks": len(self.history), "fills": self.fills,
            "costs_paid": self.costs_paid, "interest_earned": self.interest_earned,
            "pending_order": None if self.pending is None else {"decided": self.pending["date"], "targets": self.pending["targets"]},
            "braked": self.braked, "limits": dict(self.limits),
            "ledger": "holds" if ok else "fails", "ledger_detail": detail,
        }

    # ----------------------------------------------------------------- step
    def _check_date(self, date: str) -> None:
        if self.last_date is not None and str(date) <= self.last_date:
            raise PaperError("{0} is not after the last mark ({1}); the ledger only moves forward".format(date, self.last_date))

    def mark(self, date: str, prices: Dict[str, float], rf_period: float = 0.0, source: str = "") -> Dict[str, Any]:
        """Price the account at `date`. Cash earns `rf_period` for the period just ended."""
        self._check_date(date)
        for symbol in self.shares:
            price = prices.get(symbol)
            if price is None or not math.isfinite(float(price)) or float(price) <= 0:
                raise PaperError("cannot mark {0}: no usable price for {1}, which the account holds".format(date, symbol))
        clean = {symbol: float(price) for symbol, price in prices.items()
                 if price is not None and math.isfinite(float(price)) and float(price) > 0}
        interest = self.cash * float(rf_period) if self.history else 0.0
        cash = self.cash + interest
        nav = cash + sum(amount * clean[symbol] for symbol, amount in self.shares.items())
        entry = self._write({"kind": "mark", "date": str(date), "prices": clean, "rf_period": float(rf_period),
                             "interest": interest, "cash": cash, "nav": nav, "source": source})
        limit = self.limits.get("drawdown_brake")
        if limit and not self.braked and self.drawdown() <= -float(limit):
            self._write({"kind": "brake", "on": True, "date": str(date),
                         "detail": "drawdown {0:.1%} reached the {1:.0%} brake; going to cash until a human resumes".format(
                             self.drawdown(), float(limit))})
        return entry

    def _vet(self, targets: Dict[str, float]) -> Dict[str, float]:
        for symbol, weight in targets.items():
            if not math.isfinite(float(weight)):
                raise PaperError("target for {0} is not a number".format(symbol))
        cleaned = {symbol: float(weight) for symbol, weight in targets.items() if abs(float(weight)) > 0}
        for symbol, weight in cleaned.items():
            if weight < 0 and not self.limits.get("allow_short"):
                raise PaperError("target for {0} is short and this account does not short".format(symbol))
            if abs(weight) > float(self.limits["max_weight"]) + 1e-12:
                raise PaperError("target for {0} is {1:.3f}, above the limit of {2}".format(symbol, weight, self.limits["max_weight"]))
        gross = sum(abs(weight) for weight in cleaned.values())
        if gross > float(self.limits["max_gross"]) + 1e-9:
            raise PaperError("targets add up to {0:.3f} gross, above the limit of {1}".format(gross, self.limits["max_gross"]))
        return cleaned

    def order(self, date: str, targets: Dict[str, float], reason: str = "", strategy: str = "") -> Dict[str, Any]:
        """Decide the next target. It fills at the next mark, not this one."""
        if self.last_date != str(date):
            raise PaperError("mark {0} before deciding on it".format(date))
        cleaned = self._vet(targets)
        return self._write({"kind": "order", "date": str(date), "targets": cleaned,
                            "reason": reason, "strategy": strategy})

    def fill_pending(self) -> Optional[Dict[str, Any]]:
        """Execute the pending order at the prices of the latest mark."""
        if self.pending is None:
            return None
        if self.last_date is None or self.pending["date"] >= self.last_date:
            raise PaperError("an order decided on {0} cannot fill on {1}".format(self.pending["date"], self.last_date))
        targets = {} if self.braked else dict(self.pending["targets"])
        for symbol in targets:
            if symbol not in self.prices:
                raise PaperError("cannot fill: no price for {0} at {1}".format(symbol, self.last_date))
        nav_before = self.nav
        current = self.weights()
        symbols = sorted(set(current) | set(targets))
        deltas = {symbol: targets.get(symbol, 0.0) - current.get(symbol, 0.0) for symbol in symbols}
        band = float(self.limits.get("band") or 0.0)
        if band > 0 and all(abs(delta) <= band for delta in deltas.values()):
            return self._write({"kind": "cancel", "date": self.last_date, "order_seq": self.pending["seq"],
                                "detail": "inside the {0} rebalance band".format(band)})
        traded = sum(abs(delta) for delta in deltas.values())
        if traded <= 1e-12:
            return self._write({"kind": "cancel", "date": self.last_date, "order_seq": self.pending["seq"],
                                "detail": "already at target"})
        cost = float(self.limits["trade_bps"]) * 1e-4 * traded * nav_before
        nav_after = nav_before - cost
        shares_after = {symbol: targets[symbol] * nav_after / self.prices[symbol] for symbol in targets}
        cash_after = nav_after * (1.0 - sum(targets.values()))
        trades = []
        for symbol in symbols:
            change = shares_after.get(symbol, 0.0) - self.shares.get(symbol, 0.0)
            if abs(change) > 0:
                trades.append({"symbol": symbol, "shares": change, "price": self.prices[symbol],
                               "notional": change * self.prices[symbol]})
        return self._write({
            "kind": "fill", "date": self.last_date, "order_seq": self.pending["seq"], "decided": self.pending["date"],
            "trades": trades, "turnover": traded, "cost": cost, "nav_before": nav_before, "nav_after": nav_after,
            "cash_after": cash_after, "shares_after": shares_after, "braked": self.braked,
        })

    def step(self, date: str, prices: Dict[str, float], rf_period: float = 0.0,
             targets: Optional[Dict[str, float]] = None, reason: str = "", strategy: str = "",
             source: str = "") -> Dict[str, Any]:
        """One market date: mark, fill what was decided before, decide what comes next."""
        self.mark(date, prices, rf_period, source=source)
        filled = self.fill_pending()
        if targets is not None:
            self.order(date, targets, reason=reason, strategy=strategy)
        return {"date": str(date), "nav": self.nav, "filled": filled is not None and filled.get("kind") == "fill"}

    def resume(self, by: str, note: str = "") -> None:
        """Release the drawdown brake. A human decision; it is signed."""
        if not str(by).strip():
            raise PaperError("releasing the brake is signed: say who")
        self._write({"kind": "brake", "on": False, "by": by, "note": note,
                     "detail": "resumed; high-water mark reset to {0:.2f}".format(self.nav)})

    def note(self, text: str) -> None:
        self._write({"kind": "note", "text": str(text)})

    # -------------------------------------------------------------- derived
    def nav_series(self) -> Tuple[np.ndarray, np.ndarray]:
        dates = np.asarray([date for date, _ in self.history], dtype="datetime64[D]")
        values = np.asarray([value for _, value in self.history], dtype=float)
        return dates, values


def run_through(account: PaperAccount, dates: np.ndarray, symbols: List[str], prices: np.ndarray,
                rf: np.ndarray, weights: np.ndarray, rebalance: Optional[np.ndarray] = None,
                strategy: str = "", source: str = "replay") -> None:
    """Step an account through a table of prices with precomputed target weights.

    weights[t] is the target decided at the close of t. This is how history is
    replayed for commissioning and how the engine and the broker are compared.
    """
    for t in range(dates.shape[0]):
        row = {symbol: float(prices[t, column]) for column, symbol in enumerate(symbols) if math.isfinite(prices[t, column])}
        decide = rebalance is None or bool(rebalance[t])
        targets = None
        if decide:
            targets = {symbol: float(weights[t, column]) for column, symbol in enumerate(symbols)
                       if math.isfinite(weights[t, column]) and abs(weights[t, column]) > 0}
        account.step(str(dates[t]), row, float(rf[t]) if t > 0 else 0.0, targets=targets, strategy=strategy, source=source)


def set_mandate(account: PaperAccount, mandate: Dict[str, Any]) -> Dict[str, Any]:
    """Record what this account is allowed to run. Sealed, and noted in the ledger."""
    from . import strategies as _strategies

    for key in ("dataset", "strategy", "rebalance", "stage"):
        if not mandate.get(key):
            raise PaperError("a mandate needs '{0}'".format(key))
    if mandate["strategy"] not in _strategies.REGISTRY:
        raise PaperError("unknown strategy '{0}'".format(mandate["strategy"]))
    if mandate["stage"] not in ("commissioning", "promoted"):
        raise PaperError("stage is 'commissioning' (a baseline, to test the machinery) or 'promoted' (it passed a study)")
    if mandate["stage"] == "promoted" and not mandate.get("study"):
        raise PaperError("a promoted mandate names the study that confirmed it")
    sealed = store.seal({"dataset": mandate["dataset"], "symbols": list(mandate.get("symbols") or []),
                         "strategy": mandate["strategy"], "params": dict(mandate.get("params") or {}),
                         "rebalance": mandate["rebalance"], "stage": mandate["stage"],
                         "study": mandate.get("study", ""), "note": mandate.get("note", "")})
    store.write_json_atomic(account.dir / "mandate.json", sealed)
    account.note("mandate set: {0} {1} on {2}, {3} [{4}]".format(
        sealed["strategy"], sealed["params"], sealed["dataset"], sealed["stage"], sealed["seal"][:12]))
    return sealed


def advance(account: PaperAccount, dataset: Any, mandate: Optional[Dict[str, Any]] = None,
            from_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Step the account through every date in `dataset` after its last mark.

    The target for date t is computed from prices up to t and nothing later:
    the price table is cut at t before the strategy sees it. A new account
    starts at the dataset's last date (today, not the past) unless `from_date`
    asks for a replay, which is then labelled as one in the ledger.

    The account is marked on returns, not on price levels. A vendor rescales
    every past adjusted close when a dividend is paid, so today's level and the
    level in yesterday's ledger entry are not on the same scale. Each mark
    therefore chains the ledger's own price by the return the current data
    reports for that day. The dividend is earned, not lost.
    """
    from . import strategies as _strategies
    from .study import rebalance_mask

    mandate = mandate or store.read_json(account.dir / "mandate.json")
    if mandate is None:
        raise PaperError("account '{0}' has no mandate; set one first".format(account.name))
    if "seal" in mandate and not store.seal_holds(mandate):
        raise PaperError("fails: the mandate of '{0}' was edited after it was sealed".format(account.name))
    symbols = list(mandate.get("symbols") or dataset.symbols)
    table = dataset.select(symbols)
    dates = table.dates
    if account.last_date is not None:
        last = np.datetime64(account.last_date, "D")
        start = int(np.searchsorted(dates, last, side="right"))
        if start < dates.shape[0] and (start == 0 or dates[start - 1] != last):
            raise PaperError("the data does not contain the account's last mark ({0}), so today's return cannot be "
                             "chained to it".format(account.last_date))
        source = "live"
    elif from_date is not None:
        start = table.index_at_or_after(from_date)
        source = "replay from {0}".format(from_date)
    else:
        start = dates.shape[0] - 1
        source = "live"
    mask = rebalance_mask(mandate["rebalance"], dates)
    label = "{0}:{1}".format(mandate["strategy"], mandate.get("stage", ""))
    fingerprint = table.fingerprint()[:12]
    steps = []
    for t in range(start, dates.shape[0]):
        row = {}
        for column, symbol in enumerate(symbols):
            level = float(table.prices[t, column])
            if not math.isfinite(level):
                continue
            known = account.prices.get(symbol)
            before = float(table.prices[t - 1, column]) if t > 0 else float("nan")
            if known is not None and account.last_date is not None and math.isfinite(before) and before > 0:
                row[symbol] = known * (level / before)
            else:
                row[symbol] = level
        targets = None
        if account.orders == 0 or mask is None or bool(mask[t]):
            weights = _strategies.build(mandate["strategy"], table.prices[:t + 1], mandate.get("params"), table.periods_per_year)[-1]
            targets = {symbol: float(weights[column]) for column, symbol in enumerate(symbols)
                       if math.isfinite(weights[column]) and abs(weights[column]) > 0}
        steps.append(account.step(str(dates[t]), row, float(table.rf[t]), targets=targets, strategy=label,
                                  source="{0} data {1}".format(source, fingerprint)))
    return steps
