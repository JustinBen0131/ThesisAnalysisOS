"""Datasets, their fingerprints, and data quality.

A dataset is a table of total-return prices on a shared calendar, plus the
risk-free return for each period. Every result records the fingerprint of the
data it read. Vendors revise history (a dividend rescales every adjusted close
before it), so "the same data" is something to check, not assume.

`quality` is the golden-run-list step: before any physics, decide which
periods are fit to analyse, with rules written down in advance.
"""

from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from . import store

RF_COLUMN = "__rf__"


def to_dates(values: Iterable[Any]) -> np.ndarray:
    return np.asarray(list(values), dtype="datetime64[D]")


@dataclass
class Dataset:
    name: str
    dates: np.ndarray                 # (T,) datetime64[D], strictly increasing
    symbols: List[str]
    prices: np.ndarray                # (T, N) total-return index; NaN before an asset exists
    periods_per_year: float = 252.0
    rf: Optional[np.ndarray] = None   # (T,) simple risk-free return over (t-1, t]; rf[0] unused
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.dates = np.asarray(self.dates, dtype="datetime64[D]")
        self.prices = np.asarray(self.prices, dtype=float)
        if self.prices.ndim == 1:
            self.prices = self.prices[:, None]
        self.symbols = [str(symbol) for symbol in self.symbols]
        periods = self.dates.shape[0]
        if self.prices.shape != (periods, len(self.symbols)):
            raise ValueError("prices {0} do not match {1} dates x {2} symbols".format(
                self.prices.shape, periods, len(self.symbols)))
        if self.rf is None:
            self.rf = np.zeros(periods)
        self.rf = np.asarray(self.rf, dtype=float)
        if self.rf.shape != (periods,):
            raise ValueError("rf needs one value per date")

    # ------------------------------------------------------------ identity
    def fingerprint(self) -> str:
        """Hash of the numbers an analysis reads: symbols, calendar, prices, rf, frequency."""
        digest = hashlib.sha256()
        digest.update(("\n".join(self.symbols) + "\n" + repr(float(self.periods_per_year)) + "\n").encode("utf-8"))
        digest.update(self.dates.astype("datetime64[D]").astype("int64").tobytes())
        digest.update(np.where(np.isnan(self.prices), np.nan, self.prices).astype("<f8").tobytes())
        digest.update(np.where(np.isnan(self.rf), np.nan, self.rf).astype("<f8").tobytes())
        return digest.hexdigest()

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "fingerprint": self.fingerprint(),
            "symbols": list(self.symbols),
            "periods": int(self.dates.shape[0]),
            "periods_per_year": float(self.periods_per_year),
            "first": str(self.dates[0]) if self.dates.size else None,
            "last": str(self.dates[-1]) if self.dates.size else None,
        }

    # -------------------------------------------------------------- slicing
    def index_at_or_after(self, date: Any) -> int:
        return int(np.searchsorted(self.dates, np.datetime64(str(date), "D"), side="left"))

    def window(self, start: Any = None, end: Any = None) -> "Dataset":
        """Rows with start <= date <= end. Either bound may be None."""
        lo = 0 if start is None else self.index_at_or_after(start)
        hi = self.dates.shape[0] if end is None else int(
            np.searchsorted(self.dates, np.datetime64(str(end), "D"), side="right"))
        return Dataset(self.name, self.dates[lo:hi].copy(), list(self.symbols), self.prices[lo:hi].copy(),
                       self.periods_per_year, self.rf[lo:hi].copy(), dict(self.meta))

    def head(self, periods: int) -> "Dataset":
        return Dataset(self.name, self.dates[:periods].copy(), list(self.symbols), self.prices[:periods].copy(),
                       self.periods_per_year, self.rf[:periods].copy(), dict(self.meta))

    def select(self, symbols: Sequence[str]) -> "Dataset":
        index = [self.symbols.index(symbol) for symbol in symbols]
        return Dataset(self.name, self.dates.copy(), list(symbols), self.prices[:, index].copy(),
                       self.periods_per_year, self.rf.copy(), dict(self.meta))

    @property
    def returns(self) -> np.ndarray:
        out = np.full(self.prices.shape, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[1:] = self.prices[1:] / self.prices[:-1] - 1.0
        out[0] = 0.0
        return out

    # ------------------------------------------------------------------ io
    def to_csv(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [",".join(["date"] + self.symbols + [RF_COLUMN])]
        for t in range(self.dates.shape[0]):
            cells = [str(self.dates[t])]
            cells += ["" if not math.isfinite(value) else repr(float(value)) for value in self.prices[t]]
            cells.append(repr(float(self.rf[t])))
            lines.append(",".join(cells))
        store.write_text_atomic(path, "\n".join(lines) + "\n")
        meta = dict(self.meta)
        meta.update(self.describe())
        store.write_json_atomic(path.with_suffix(".json"), meta)

    @staticmethod
    def from_csv(path: Path, name: Optional[str] = None) -> "Dataset":
        path = Path(path)
        meta = store.read_json(path.with_suffix(".json"), {}) or {}
        with open(path, "r", encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        header = rows[0]
        has_rf = header[-1] == RF_COLUMN
        symbols = header[1:-1] if has_rf else header[1:]
        dates, prices, rf = [], [], []
        for row in rows[1:]:
            if not row or not row[0]:
                continue
            dates.append(row[0])
            cells = row[1:1 + len(symbols)]
            prices.append([float(cell) if cell not in ("", "nan", "NaN") else float("nan") for cell in cells])
            rf.append(float(row[1 + len(symbols)]) if has_rf and row[1 + len(symbols)] != "" else 0.0)
        return Dataset(name or meta.get("name") or path.stem, to_dates(dates), symbols,
                       np.asarray(prices, dtype=float).reshape(len(dates), len(symbols)),
                       float(meta.get("periods_per_year", 252.0)), np.asarray(rf, dtype=float), meta)


# ---------------------------------------------------------------- assembly

def align(series: Dict[str, Tuple[np.ndarray, np.ndarray]], how: str = "inner",
          fill_limit: int = 0) -> Tuple[np.ndarray, List[str], np.ndarray]:
    """Put several (dates, values) series on one calendar.

    how="inner" keeps dates every series has; "union" keeps any date and leaves
    gaps NaN, then carries a value forward at most `fill_limit` periods (a
    carried price is a stale price, so the default is not to).
    """
    symbols = list(series)
    calendars = [np.asarray(series[symbol][0], dtype="datetime64[D]") for symbol in symbols]
    if how == "inner":
        dates = calendars[0]
        for calendar in calendars[1:]:
            dates = np.intersect1d(dates, calendar)
    elif how == "union":
        dates = np.unique(np.concatenate(calendars))
    else:
        raise ValueError("how must be 'inner' or 'union'")
    table = np.full((dates.shape[0], len(symbols)), np.nan)
    for column, symbol in enumerate(symbols):
        own_dates = calendars[column]
        values = np.asarray(series[symbol][1], dtype=float)
        position = np.searchsorted(dates, own_dates)
        ok = (position < dates.shape[0])
        ok[ok] &= dates[position[ok]] == own_dates[ok]
        table[position[ok], column] = values[ok]
        if fill_limit > 0:
            run = 0
            for t in range(1, table.shape[0]):
                if math.isnan(table[t, column]) and not math.isnan(table[t - 1, column]) and run < fill_limit:
                    table[t, column] = table[t - 1, column]
                    run += 1
                else:
                    run = 0
    return dates, symbols, table


def rf_from_yield(dates: np.ndarray, yield_pct: np.ndarray) -> np.ndarray:
    """Per-period risk-free return from an annualised yield in percent.

    The return over (t-1, t] uses the yield quoted at t-1, the rate you could
    actually have locked in, and the calendar days in between.
    """
    dates = np.asarray(dates, dtype="datetime64[D]")
    y = np.asarray(yield_pct, dtype=float) / 100.0
    out = np.zeros(dates.shape[0])
    if dates.shape[0] > 1:
        days = (dates[1:] - dates[:-1]).astype(int)
        prior = np.where(np.isfinite(y[:-1]), y[:-1], 0.0)
        out[1:] = np.power(1.0 + np.clip(prior, -0.99, None), days / 365.0) - 1.0
    return out


def carry_forward(dates: np.ndarray, source_dates: np.ndarray, source_values: np.ndarray) -> np.ndarray:
    """Latest known source value at each date (for a yield published on another calendar)."""
    dates = np.asarray(dates, dtype="datetime64[D]")
    source_dates = np.asarray(source_dates, dtype="datetime64[D]")
    values = np.asarray(source_values, dtype=float)
    keep = np.isfinite(values)
    source_dates, values = source_dates[keep], values[keep]
    position = np.searchsorted(source_dates, dates, side="right") - 1
    out = np.full(dates.shape[0], np.nan)
    ok = position >= 0
    out[ok] = values[position[ok]]
    return out


# ----------------------------------------------------------------- quality

def quality(dataset: Dataset, stale_run: int = 5, jump_sigma: float = 12.0) -> Dict[str, Any]:
    """Data quality, with the rules fixed before looking.

    verdict   holds   the calendar is ordered, prices are positive, no gaps inside a series
              fails   something structural is wrong; do not analyse
    golden    one flag per period: every listed asset has a price and none
              made a jump beyond `jump_sigma` robust standard deviations.
              A jump is flagged, never removed: crashes are data.
    """
    dates = dataset.dates
    prices = dataset.prices
    periods = dates.shape[0]
    problems: List[str] = []
    day_gaps = (dates[1:] - dates[:-1]).astype(int) if periods > 1 else np.zeros(0, dtype=int)
    if np.any(day_gaps <= 0):
        problems.append("calendar is not strictly increasing ({0} places)".format(int(np.sum(day_gaps <= 0))))
    golden = np.ones(periods, dtype=bool)
    per_symbol: Dict[str, Any] = {}
    for column, symbol in enumerate(dataset.symbols):
        series = prices[:, column]
        finite = np.isfinite(series)
        if not finite.any():
            per_symbol[symbol] = {"valid": 0}
            problems.append("{0}: no prices at all".format(symbol))
            golden[:] = False
            continue
        first = int(np.argmax(finite))
        last = int(periods - 1 - np.argmax(finite[::-1]))
        inside = finite[first:last + 1]
        gaps_inside = int((~inside).sum())
        nonpositive = int(np.sum(series[finite] <= 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            logret = np.diff(np.log(np.where(series > 0, series, np.nan)))
        ok = np.isfinite(logret)
        centre = float(np.median(logret[ok])) if ok.any() else 0.0
        mad = float(np.median(np.abs(logret[ok] - centre))) if ok.any() else 0.0
        robust_sd = 1.4826 * mad
        jumps = np.zeros(periods, dtype=bool)
        if robust_sd > 0:
            jumps[1:] = ok & (np.abs(logret - centre) > jump_sigma * robust_sd)
        unchanged = np.zeros(periods, dtype=bool)
        unchanged[1:] = ok & (logret == 0.0)
        stale = np.zeros(periods, dtype=bool)
        run = 0
        for t in range(periods):
            run = run + 1 if unchanged[t] else 0
            if run >= stale_run:
                stale[t - run + 1:t + 1] = True
        golden[first:last + 1] &= inside
        golden &= ~jumps
        golden[:first] = False
        if gaps_inside:
            problems.append("{0}: {1} missing prices inside the series".format(symbol, gaps_inside))
        if nonpositive:
            problems.append("{0}: {1} prices at or below zero".format(symbol, nonpositive))
        per_symbol[symbol] = {
            "first": str(dates[first]), "last": str(dates[last]), "valid": int(finite.sum()),
            "gaps_inside": gaps_inside, "nonpositive": nonpositive,
            "jumps": int(jumps.sum()), "jump_dates": [str(d) for d in dates[jumps][:20]],
            "stale_periods": int(stale.sum()),
            "max_abs_return": float(np.nanmax(np.abs(np.expm1(logret[ok])))) if ok.any() else None,
            "robust_sd": robust_sd,
        }
    return {
        "dataset": dataset.describe(),
        "verdict": "fails" if problems else "holds",
        "problems": problems,
        "largest_gap_days": int(day_gaps.max()) if day_gaps.size else 0,
        "golden_periods": int(golden.sum()),
        "golden_fraction": float(golden.mean()) if periods else 0.0,
        "per_symbol": per_symbol,
        "rules": {"stale_run": stale_run, "jump_sigma": jump_sigma},
        "golden": golden,
    }
