"""The backtest engine: one loop over time, vectorised over everything else.

Conventions, stated once because every bug in this field is an off-by-one here:

  returns[..., t, i]   simple return of asset i over the period (t-1, t]
  weights[..., t, i]   target weight decided at the close of t, from data up to t
  lag                  periods between deciding and trading. lag=1 (the default)
                       means a target decided at the close of t is traded at
                       the close of t+1 and first earns the return of t+2.
  cash                 1 - sum(weights). Earns rf; borrowing pays rf + a spread.

Between rebalances weights drift with prices, exactly. A trade moves the
drifted weights to the target and pays `trade_bps` on the weight it moved,
measured on the NAV just before the trade; the NAV after the trade is smaller
by that cost and holds the target weights exactly. The paper broker in
`paper.py` does the same arithmetic in shares and dollars, and a test holds the
two to agree to rounding.

A leading batch dimension is free: 5,000 toy markets cost one pass.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

import numpy as np

from . import stats


@dataclass(frozen=True)
class Costs:
    """What trading costs. Defaults suit liquid ETFs at a retail broker."""

    trade_bps: float = 5.0            # one way, per unit of notional traded
    borrow_spread_ann: float = 0.015  # paid above rf on negative cash
    short_fee_ann: float = 0.01       # paid on short notional
    cash_drag_ann: float = 0.0        # cash earns rf minus this

    def scaled(self, factor: float) -> "Costs":
        return Costs(self.trade_bps * factor, self.borrow_spread_ann * factor,
                     self.short_fee_ann * factor, self.cash_drag_ann * factor)

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    @staticmethod
    def from_dict(values: Optional[Dict[str, Any]]) -> "Costs":
        values = values or {}
        known = {key: float(values[key]) for key in ("trade_bps", "borrow_spread_ann", "short_fee_ann", "cash_drag_ann") if key in values}
        return Costs(**known)


@dataclass
class Result:
    net: np.ndarray        # (..., T) return after costs; net[..., 0] is the cost of a trade at t=0, if any
    gross: Optional[np.ndarray]     # (..., T) return before trading costs
    turnover: Optional[np.ndarray]  # (..., T) notional traded at the close of t, as a fraction of NAV
    exposure: Optional[np.ndarray]  # (..., T) sum of |weights| held over the period ending at t
    rf: np.ndarray         # (T,) the risk-free return used
    periods_per_year: float
    held: Optional[np.ndarray] = None  # (..., T, N) weights held over the period ending at t

    @property
    def excess(self) -> np.ndarray:
        return self.net - self.rf

    def nav(self) -> np.ndarray:
        return np.cumprod(1.0 + self.net, axis=-1)

    def sharpe(self) -> np.ndarray:
        return stats.sharpe(self.excess[..., 1:], self.periods_per_year)

    def summary(self, start: int = 1, stop: Optional[int] = None) -> Dict[str, Any]:
        """Statistics of one run (no batch) over periods [start, stop)."""
        if self.net.ndim != 1:
            raise ValueError("summary is for a single run; index the batch first")
        if self.turnover is None or self.exposure is None:
            raise ValueError("summary needs a full run, not a lean one")
        window = slice(max(1, start), stop)
        out = stats.summarize(self.net[window], self.rf[window], self.periods_per_year)
        turnover = self.turnover[window]
        out["turnover_ann"] = float(turnover.mean() * self.periods_per_year)
        out["avg_exposure"] = float(self.exposure[window].mean())
        out["trades"] = int(np.count_nonzero(turnover > 1e-12))
        return out


def _rf_array(rf: Any, periods: int) -> np.ndarray:
    arr = np.array(np.broadcast_to(np.asarray(rf, dtype=float), (periods,)), dtype=float)
    arr[~np.isfinite(arr)] = 0.0
    arr[0] = 0.0  # element 0 describes no period
    return arr


def run(returns: np.ndarray, weights: np.ndarray, rf: Any = 0.0, costs: Optional[Costs] = None,
        lag: int = 1, rebalance: Optional[np.ndarray] = None, band: float = 0.0,
        periods_per_year: float = 252.0, keep_weights: bool = False,
        shifts: Optional[np.ndarray] = None, lean: bool = False) -> Result:
    """Run target weights through returns. See the module docstring for the conventions.

    rebalance   boolean (..., T): a target decided at t is adopted only where
                rebalance[..., t] is true. None means every period.
    band        skip a rebalance when no weight is further than this from target.
    shifts      integer offsets (S,). Adds a leading dimension S in which the
                weights (and the rebalance mask) are rotated in time by each
                offset against the same returns. This is the mixed-event
                background: same exposures, same returns, alignment destroyed.
    lean        keep only the net returns (large batches of toys).
    """
    costs = costs or Costs()
    if lag < 0:
        raise ValueError("lag must be 0 or more; a negative lag trades on the future")
    R = np.asarray(returns, dtype=float)
    W = np.asarray(weights, dtype=float)
    if R.ndim < 2 or W.ndim < 2:
        raise ValueError("returns and weights need a time axis and an asset axis")
    if R.shape[-2:] != W.shape[-2:]:
        raise ValueError("returns {0} and weights {1} disagree on (time, assets)".format(R.shape[-2:], W.shape[-2:]))
    T, N = R.shape[-2:]
    missing = ~np.isfinite(R)
    R = np.where(missing, 0.0, R)
    W = np.where(np.isfinite(W), W, 0.0)
    reb = None if rebalance is None else np.asarray(rebalance, dtype=bool)
    if reb is not None and reb.shape[-1] != T:
        raise ValueError("rebalance mask has {0} periods, expected {1}".format(reb.shape[-1], T))
    batch = np.broadcast_shapes(R.shape[:-2], W.shape[:-2], () if reb is None else reb.shape[:-1])
    if shifts is not None:
        shifts = np.asarray(shifts, dtype=int).reshape(-1)
        batch = (shifts.shape[0],) + tuple(batch)
    rf_arr = _rf_array(rf, T)
    pp = float(periods_per_year)
    fee = costs.trade_bps * 1e-4
    borrow = costs.borrow_spread_ann / pp
    short_fee = costs.short_fee_ann / pp
    drag = costs.cash_drag_ann / pp
    any_missing = missing.any(axis=tuple(range(missing.ndim - 2))) if missing.ndim > 2 else missing

    w = np.zeros(batch + (N,))
    alive = np.ones(batch, dtype=bool)
    net = np.zeros(batch + (T,))
    gross = None if lean else np.zeros(batch + (T,))
    turnover = None if lean else np.zeros(batch + (T,))
    exposure = None if lean else np.zeros(batch + (T,))
    held = np.zeros(batch + (T, N)) if keep_weights else None

    for t in range(T):
        if t == 0:
            growth = np.ones(batch)
            g = np.zeros(batch)
            drifted = w
        else:
            r = R[..., t, :]
            if any_missing[t].any() and np.any((w != 0) & missing[..., t, :]):
                raise ValueError("period {0}: a position is held in an asset with no price".format(t))
            if held is not None:
                held[..., t, :] = w
            if exposure is not None:
                exposure[..., t] = np.abs(w).sum(axis=-1)
            cash = 1.0 - w.sum(axis=-1)
            cash_rate = np.where(cash >= 0, rf_arr[t] - drag, rf_arr[t] + borrow)
            g = (w * r).sum(axis=-1) + cash * cash_rate
            if short_fee:
                g = g - np.clip(-w, 0.0, None).sum(axis=-1) * short_fee
            growth = 1.0 + g
            ruined = alive & (growth <= 0.0)
            if ruined.any():
                alive = alive & ~ruined
            safe = np.where(growth > 1e-12, growth, 1.0)
            drifted = w * (1.0 + r) / safe[..., None]
            drifted = np.where(alive[..., None], drifted, 0.0)
            growth = np.where(growth > 0.0, growth, 0.0)

        s = t - lag
        cost = 0.0
        w = drifted
        if s >= 0:
            if shifts is None:
                target = W[..., s, :]
                adopt = None if reb is None else reb[..., s]
            else:
                source = (s - shifts) % T
                target = np.moveaxis(W[..., source, :], -2, 0)
                adopt = None if reb is None else np.moveaxis(reb[..., source], -1, 0)
            target = np.broadcast_to(target, batch + (N,))
            trade = alive if adopt is None else (alive & np.broadcast_to(adopt, batch))
            if band > 0.0:
                trade = trade & (np.abs(target - drifted).max(axis=-1) > band)
            if np.any(trade):
                target = np.where(trade[..., None], target, drifted)
                traded = np.abs(target - drifted).sum(axis=-1)
                cost = fee * traded
                if turnover is not None:
                    turnover[..., t] = traded
                w = target
        if gross is not None:
            gross[..., t] = g
        net[..., t] = growth * (1.0 - cost) - 1.0

    return Result(net=net, gross=gross, turnover=turnover, exposure=exposure, rf=rf_arr,
                  periods_per_year=pp, held=held)


def mixed_event_null(returns: np.ndarray, weights: np.ndarray, rf: Any = 0.0, costs: Optional[Costs] = None,
                     lag: int = 1, rebalance: Optional[np.ndarray] = None, band: float = 0.0,
                     periods_per_year: float = 252.0, n_shifts: int = 200, min_shift: Optional[int] = None,
                     rng: Optional[np.random.Generator] = None, chunk: int = 64) -> Dict[str, Any]:
    """Timing skill against the mixed-event background.

    The weights are rotated in time against the returns. Every rotation keeps
    the strategy's own exposure pattern, its turnover and its costs, and keeps
    the market exactly as it was; only the alignment between them is lost. If
    the real alignment is no better than the rotated ones, the strategy has no
    timing skill, whatever its Sharpe ratio is.

    With a leading batch of K trials in `weights`, each rotation is applied to
    all K together and the best is kept, so `p_global` already pays for the
    search (the look-elsewhere effect, done the way a physicist would).

    Returns observed and null Sharpe ratios, p-values and Z.
    """
    rng = rng if rng is not None else np.random.default_rng(0)
    W = np.asarray(weights, dtype=float)
    T = W.shape[-2]
    if min_shift is None:
        min_shift = max(2, min(int(periods_per_year), T // 4))
    candidates = np.arange(min_shift, T - min_shift + 1)
    if candidates.size == 0:
        raise ValueError("series too short for a mixed-event null: {0} periods".format(T))
    if candidates.size > n_shifts:
        candidates = np.sort(rng.choice(candidates, size=n_shifts, replace=False))
    observed = run(returns, W, rf=rf, costs=costs, lag=lag, rebalance=rebalance, band=band,
                   periods_per_year=periods_per_year).sharpe()
    parts = []
    for start in range(0, candidates.size, chunk):
        part = run(returns, W, rf=rf, costs=costs, lag=lag, rebalance=rebalance, band=band,
                   periods_per_year=periods_per_year, shifts=candidates[start:start + chunk], lean=True).sharpe()
        parts.append(part)
    null = np.concatenate(parts, axis=0)  # (S, ...trials)
    observed = np.asarray(observed, dtype=float)
    finite = np.isfinite(null)
    null_filled = np.where(finite, null, -np.inf)
    count = null.shape[0]
    p_each = (1.0 + (null_filled >= observed).sum(axis=0)) / (1.0 + count)
    out: Dict[str, Any] = {
        "observed": observed,
        "null_mean": np.nanmean(null, axis=0),
        "null_sd": np.nanstd(null, axis=0, ddof=1),
        "p": p_each,
        "n_shifts": int(count),
        "min_shift": int(min_shift),
        "null": null,
    }
    if observed.ndim >= 1 and observed.size > 1:
        flat_null = null_filled.reshape(count, -1)
        best_null = flat_null.max(axis=1)
        best_obs = float(np.nanmax(observed))
        out["best_observed"] = best_obs
        out["best_null"] = best_null
        out["p_global"] = float((1.0 + (best_null >= best_obs).sum()) / (1.0 + count))
    else:
        out["p_global"] = float(np.asarray(p_each).reshape(-1)[0])
    out["z_global"] = stats.z_from_p(out["p_global"])
    # with n rotations the smallest p the test can report is 1/(n+1); a result at that floor means "at least"
    out["p_floor"] = 1.0 / (1.0 + count)
    out["z_resolution"] = stats.z_from_p(out["p_floor"])
    out["at_floor"] = bool(out["p_global"] <= out["p_floor"] * (1.0 + 1e-12))
    return out


def rotations_available(periods: int, periods_per_year: float, cap: int = 2000) -> int:
    """How many distinct rotations a series of this length allows (see mixed_event_null)."""
    min_shift = max(2, min(int(periods_per_year), periods // 4))
    return max(0, min(cap, periods - 2 * min_shift + 1))


def simple_returns(prices: np.ndarray) -> np.ndarray:
    """(..., T, N) prices to simple returns. The first period is zero; gaps stay NaN."""
    prices = np.asarray(prices, dtype=float)
    out = np.full(prices.shape, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[..., 1:, :] = prices[..., 1:, :] / prices[..., :-1, :] - 1.0
    out[..., 0, :] = 0.0
    return out


def years(periods: int, periods_per_year: float) -> float:
    return periods / float(periods_per_year)


def sqrt_time(periods_per_year: float) -> float:
    return math.sqrt(periods_per_year)
