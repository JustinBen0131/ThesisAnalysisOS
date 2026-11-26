"""Strategies: functions from price history to target weights.

The contract every strategy keeps, and `gates.causality` checks:

    weights[..., t, :] depends only on prices[..., :t+1, :]

Prices are (..., T, N), a total-return index per asset, NaN before an asset
exists. Weights are fractions of NAV; whatever is not allocated sits in cash.
Nothing here is clever. Slow, old, published ideas are the right place to
start because their out-of-sample record is longer than any backtest.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional, Sequence

import numpy as np

TIME = -2


def _rolling_sum(x: np.ndarray, window: int):
    finite = np.isfinite(x)
    filled = np.where(finite, x, 0.0)
    total = np.cumsum(filled, axis=TIME)
    count = np.cumsum(finite.astype(float), axis=TIME)
    out = total.copy()
    cnt = count.copy()
    if window < x.shape[TIME]:
        out[..., window:, :] = total[..., window:, :] - total[..., :-window, :]
        cnt[..., window:, :] = count[..., window:, :] - count[..., :-window, :]
    return out, cnt


def rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    """Trailing mean over `window` periods ending at t. NaN until the window is full."""
    total, count = _rolling_sum(np.asarray(x, dtype=float), window)
    with np.errstate(invalid="ignore"):
        return np.where(count >= window, total / window, np.nan)


def rolling_std(x: np.ndarray, window: int) -> np.ndarray:
    """Trailing standard deviation (n-1) over `window` periods ending at t."""
    x = np.asarray(x, dtype=float)
    total, count = _rolling_sum(x, window)
    squares, _ = _rolling_sum(x * x, window)
    with np.errstate(invalid="ignore"):
        var = (squares - total * total / window) / (window - 1)
        return np.where(count >= window, np.sqrt(np.clip(var, 0.0, None)), np.nan)


def lagged(x: np.ndarray, periods: int) -> np.ndarray:
    """x as it was `periods` ago. The first `periods` rows are NaN."""
    x = np.asarray(x, dtype=float)
    if periods <= 0:
        return x.copy()
    out = np.full(x.shape, np.nan)
    out[..., periods:, :] = x[..., :-periods, :]
    return out


def returns_of(prices: np.ndarray) -> np.ndarray:
    prices = np.asarray(prices, dtype=float)
    out = np.full(prices.shape, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[..., 1:, :] = prices[..., 1:, :] / prices[..., :-1, :] - 1.0
    return out


def _base(prices: np.ndarray, base: Optional[Sequence[float]]) -> np.ndarray:
    n = prices.shape[-1]
    if base is None:
        return np.full(n, 1.0 / n)
    arr = np.asarray(base, dtype=float)
    if arr.shape != (n,):
        raise ValueError("base weights need one entry per asset ({0})".format(n))
    return arr


def _only_listed(weights: np.ndarray, prices: np.ndarray) -> np.ndarray:
    return np.where(np.isfinite(prices) & np.isfinite(weights), weights, 0.0)


# ------------------------------------------------------------- the baselines

def hold(prices: np.ndarray, base: Optional[Sequence[float]] = None) -> np.ndarray:
    """Fixed weights, rebalanced whenever the engine is told to. The control sample."""
    prices = np.asarray(prices, dtype=float)
    return _only_listed(np.broadcast_to(_base(prices, base), prices.shape).copy(), prices)


def cash(prices: np.ndarray) -> np.ndarray:
    """Hold nothing. Earns the risk-free rate; the null hypothesis of doing anything at all."""
    return np.zeros(np.asarray(prices).shape)


# ------------------------------------------------------------------- trend

def trend_sma(prices: np.ndarray, window: int = 200, base: Optional[Sequence[float]] = None) -> np.ndarray:
    """Hold an asset while its price is above its own moving average, else cash (Faber 2007)."""
    prices = np.asarray(prices, dtype=float)
    average = rolling_mean(prices, int(window))
    with np.errstate(invalid="ignore"):
        above = prices > average
    return _only_listed(np.where(above, _base(prices, base), 0.0), prices)


def tsmom(prices: np.ndarray, lookback: int = 252, skip: int = 21, vol_window: int = 63,
          target_vol: float = 0.10, max_weight: float = 1.0, allow_short: bool = False,
          periods_per_year: float = 252.0, base: Optional[Sequence[float]] = None) -> np.ndarray:
    """Time-series momentum (Moskowitz, Ooi & Pedersen 2012).

    Long what rose over the past `lookback` periods (skipping the most recent
    `skip`), sized so each position targets the same volatility.
    """
    prices = np.asarray(prices, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        past = lagged(prices, int(skip)) / lagged(prices, int(lookback)) - 1.0
        direction = np.sign(past)
        if not allow_short:
            direction = np.clip(direction, 0.0, None)
        vol = rolling_std(returns_of(prices), int(vol_window)) * math.sqrt(periods_per_year)
        size = np.clip(target_vol / vol, 0.0, max_weight)
    n_assets = prices.shape[-1]
    scale = _base(prices, base) * n_assets
    return _only_listed(direction * size * scale / n_assets, prices)


# -------------------------------------------------------------- risk control

def vol_target(prices: np.ndarray, vol_window: int = 63, target_vol: float = 0.10,
               max_leverage: float = 1.0, periods_per_year: float = 252.0,
               base: Optional[Sequence[float]] = None) -> np.ndarray:
    """Scale each holding down when its recent volatility is high (Moreira & Muir 2017)."""
    prices = np.asarray(prices, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        vol = rolling_std(returns_of(prices), int(vol_window)) * math.sqrt(periods_per_year)
        size = np.clip(target_vol / vol, 0.0, max_leverage)
    return _only_listed(_base(prices, base) * size, prices)


def inverse_vol(prices: np.ndarray, vol_window: int = 63, gross: float = 1.0) -> np.ndarray:
    """Weights proportional to 1/volatility, summing to `gross`. Risk parity without the leverage."""
    prices = np.asarray(prices, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / rolling_std(returns_of(prices), int(vol_window))
    inv = np.where(np.isfinite(inv) & np.isfinite(prices), inv, 0.0)
    total = inv.sum(axis=-1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        weights = np.where(total > 0, gross * inv / total, 0.0)
    return weights


def trend_inverse_vol(prices: np.ndarray, window: int = 200, vol_window: int = 63, gross: float = 1.0) -> np.ndarray:
    """Inverse-volatility weights, with any asset below its moving average moved to cash."""
    prices = np.asarray(prices, dtype=float)
    average = rolling_mean(prices, int(window))
    with np.errstate(invalid="ignore"):
        above = prices > average
    return np.where(above, inverse_vol(prices, vol_window, gross), 0.0)


# --------------------------------------------------------- cross-sectional

def xs_momentum(prices: np.ndarray, lookback: int = 252, skip: int = 21, top: float = 0.3,
                gross: float = 1.0) -> np.ndarray:
    """Hold, equally, the top fraction of assets ranked by past return (Jegadeesh & Titman 1993)."""
    prices = np.asarray(prices, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        past = lagged(prices, int(skip)) / lagged(prices, int(lookback)) - 1.0
    valid = np.isfinite(past) & np.isfinite(prices)
    n_valid = valid.sum(axis=-1, keepdims=True)
    keep = np.maximum(1, np.floor(top * n_valid + 1e-9)).astype(int)
    filled = np.where(valid, past, -np.inf)
    order = np.argsort(np.argsort(-filled, axis=-1, kind="stable"), axis=-1, kind="stable")
    chosen = (order < keep) & valid
    count = chosen.sum(axis=-1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(chosen & (count > 0), gross / np.maximum(count, 1), 0.0)


def pairs_zscore(prices: np.ndarray, window: int = 60, entry: float = 2.0, exit: float = 0.5,
                 gross: float = 1.0) -> np.ndarray:
    """Trade the log spread of two assets back toward its mean. Prices (..., T, 2).

    Short the rich leg and long the cheap one when the spread's z-score passes
    `entry`; flat again inside `exit`. Half the gross on each leg.
    """
    prices = np.asarray(prices, dtype=float)
    if prices.shape[-1] != 2:
        raise ValueError("pairs_zscore needs exactly two assets")
    with np.errstate(divide="ignore", invalid="ignore"):
        spread = np.log(prices[..., 0]) - np.log(prices[..., 1])
    mean = rolling_mean(spread[..., None], int(window))[..., 0]
    sd = rolling_std(spread[..., None], int(window))[..., 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (spread - mean) / sd
    position = np.zeros(spread.shape[:-1])
    weights = np.zeros(prices.shape)
    for t in range(spread.shape[-1]):
        zt = z[..., t]
        ok = np.isfinite(zt)
        position = np.where(ok & (zt > entry), -1.0, position)
        position = np.where(ok & (zt < -entry), 1.0, position)
        position = np.where(ok & (np.abs(zt) < exit), 0.0, position)
        position = np.where(ok, position, 0.0)
        weights[..., t, 0] = 0.5 * gross * position
        weights[..., t, 1] = -0.5 * gross * position
    return weights


# ------------------------------------------------------------------ schedule

def month_ends(dates: np.ndarray) -> np.ndarray:
    """True on the last listed day of each calendar month. The last row is true only if it ends a month.

    A decision made on these days is traded `lag` periods later by the engine.
    """
    dates = np.asarray(dates, dtype="datetime64[D]")
    months = dates.astype("datetime64[M]")
    mask = np.zeros(dates.shape[0], dtype=bool)
    mask[:-1] = months[1:] != months[:-1]
    if dates.shape[0]:
        last = dates[-1]
        next_business = np.busday_offset(last, 1, roll="forward")
        mask[-1] = next_business.astype("datetime64[M]") != last.astype("datetime64[M]")
    return mask


def month_starts(dates: np.ndarray) -> np.ndarray:
    """True on the first listed day of each calendar month (never on the first row).

    Unlike `month_ends`, this is known on the day itself without an exchange
    calendar, so the paper account and a backtest agree on when to decide.
    """
    dates = np.asarray(dates, dtype="datetime64[D]")
    months = dates.astype("datetime64[M]")
    mask = np.zeros(dates.shape[0], dtype=bool)
    mask[1:] = months[1:] != months[:-1]
    return mask


def every(periods: int, step: int, offset: int = 0) -> np.ndarray:
    mask = np.zeros(periods, dtype=bool)
    mask[offset % max(step, 1)::max(step, 1)] = True
    return mask


REGISTRY: Dict[str, Callable[..., np.ndarray]] = {
    "hold": hold,
    "cash": cash,
    "trend_sma": trend_sma,
    "tsmom": tsmom,
    "vol_target": vol_target,
    "inverse_vol": inverse_vol,
    "trend_inverse_vol": trend_inverse_vol,
    "xs_momentum": xs_momentum,
    "pairs_zscore": pairs_zscore,
}

_NEEDS_PPY = {"tsmom", "vol_target"}


def build(name: str, prices: np.ndarray, params: Optional[Dict[str, Any]] = None,
          periods_per_year: float = 252.0) -> np.ndarray:
    """Look a strategy up by name and run it. This is the only entry a study uses."""
    if name not in REGISTRY:
        raise KeyError("unknown strategy '{0}'. Known: {1}".format(name, ", ".join(sorted(REGISTRY))))
    kwargs = dict(params or {})
    if name in _NEEDS_PPY:
        kwargs.setdefault("periods_per_year", periods_per_year)
    return REGISTRY[name](prices, **kwargs)
