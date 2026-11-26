"""Estimators and tests. Pure functions of arrays; numpy and the standard library only.

Units. A Sharpe ratio is computed per period (mean over sd of excess returns)
and annualised by sqrt(periods per year). Standard errors and the selection
corrections are worked out per period, where the formulas are exact, and only
then annualised. Significance is one-sided and quoted in sigma, as in physics:
Z = Phi^-1(1 - p).

References, by the name used in the code:
  Mertens (2002), Lo (2002)            standard error of a Sharpe ratio
  Bailey & Lopez de Prado (2012, 2014)  probabilistic and deflated Sharpe ratio
  Politis & Romano (1994)               stationary bootstrap
  Newey & West (1987)                   autocorrelation-robust variance
  Harvey, Liu & Zhu (2016)              why the bar is t > 3 once you count the searches
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

_NORMAL = NormalDist()
EULER_GAMMA = 0.5772156649015329
_SQRT2 = math.sqrt(2.0)


# ---------------------------------------------------------------- the normal

def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-float(x) / _SQRT2)


def norm_sf(x: float) -> float:
    """Upper tail, accurate far out where 1 - cdf would round to zero."""
    return 0.5 * math.erfc(float(x) / _SQRT2)


def norm_ppf(p: float) -> float:
    p = float(p)
    if not (p == p):
        return float("nan")
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    return _NORMAL.inv_cdf(p)


def z_from_p(p: float) -> float:
    """One-sided significance in sigma for a p-value. p = 0.00135 is 3 sigma."""
    return -norm_ppf(p)


def p_from_z(z: float) -> float:
    return norm_sf(z)


def wilson_interval(k: int, n: int, z: float = 1.0) -> Tuple[float, float]:
    """Interval for a binomial rate that behaves at k = 0 and k = n."""
    if n <= 0:
        return (float("nan"), float("nan"))
    rate = k / n
    denom = 1.0 + z * z / n
    centre = (rate + z * z / (2 * n)) / denom
    half = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


# ------------------------------------------------------------------ moments

def moments(x: np.ndarray, axis: int = -1) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """mean, sd (n-1), skewness, kurtosis (a normal has 3)."""
    x = np.asarray(x, dtype=float)
    n = x.shape[axis]
    mean = x.mean(axis=axis)
    d = x - np.expand_dims(mean, axis)
    m2 = (d * d).mean(axis=axis)
    with np.errstate(divide="ignore", invalid="ignore"):
        sd = np.sqrt(m2 * n / max(n - 1, 1))
        skew = (d ** 3).mean(axis=axis) / np.power(m2, 1.5)
        kurt = (d ** 4).mean(axis=axis) / (m2 * m2)
    return mean, sd, skew, kurt


def sharpe(excess: np.ndarray, periods_per_year: float = 252.0, axis: int = -1) -> np.ndarray:
    """Annualised Sharpe ratio of excess returns."""
    excess = np.asarray(excess, dtype=float)
    mean = excess.mean(axis=axis)
    sd = excess.std(axis=axis, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(sd > 0, mean / sd, np.nan) * math.sqrt(periods_per_year)


def sharpe_se(sr: float, n: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Standard error of a per-period Sharpe ratio (Mertens 2002).

    Assumes returns are not serially dependent. Under volatility clustering it
    is too small; `toys.pull_study` measures by how much.
    """
    if n < 3:
        return float("nan")
    var = (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr) / (n - 1)
    return math.sqrt(var) if var > 0 else float("nan")


def psr(sr: float, sr_star: float, n: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Probabilistic Sharpe ratio: P(true SR > sr_star), per-period units."""
    se = sharpe_se(sr, n, skew, kurt)
    if not (se == se) or se <= 0:
        return float("nan")
    return norm_cdf((sr - sr_star) / se)


def min_track_record(sr: float, sr_star: float = 0.0, skew: float = 0.0, kurt: float = 3.0, z: float = 1.645) -> float:
    """Observations needed before sr is distinguishable from sr_star at z sigma."""
    if sr <= sr_star:
        return float("inf")
    return 1.0 + (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr) * (z / (sr - sr_star)) ** 2


def expected_max_sharpe(n_trials: float, var_trials: float) -> float:
    """Expected best Sharpe among n_trials unskilled tries (per-period units).

    This is the look-elsewhere effect in closed form: search N places and the
    largest fluctuation you will meet grows like sqrt(2 ln N).
    """
    if n_trials is None or n_trials <= 1 or not (var_trials == var_trials) or var_trials <= 0:
        return 0.0
    n = float(n_trials)
    a = norm_ppf(1.0 - 1.0 / n)
    b = norm_ppf(1.0 - 1.0 / (n * math.e))
    return math.sqrt(var_trials) * ((1.0 - EULER_GAMMA) * a + EULER_GAMMA * b)


def deflated_sharpe(sr: float, n: int, skew: float, kurt: float, n_trials: float, var_trials: float) -> Dict[str, float]:
    """Deflated Sharpe ratio: PSR against the best an unskilled search would find."""
    sr0 = expected_max_sharpe(n_trials, var_trials)
    prob = psr(sr, sr0, n, skew, kurt)
    p_value = 1.0 - prob if prob == prob else float("nan")
    return {"sr0": sr0, "dsr": prob, "p": p_value, "z": z_from_p(p_value) if p_value == p_value else float("nan")}


def effective_trials(trial_returns: np.ndarray) -> float:
    """How many independent searches a set of correlated trials is worth.

    The participation ratio of the correlation spectrum, (sum l)^2 / sum l^2:
    1 when every trial is the same bet, K when all K are unrelated.
    """
    x = np.asarray(trial_returns, dtype=float)
    if x.ndim != 2 or x.shape[0] == 0:
        return 0.0
    keep = x.std(axis=1) > 0
    x = x[keep]
    if x.shape[0] <= 1:
        return float(x.shape[0])
    corr = np.corrcoef(x)
    eig = np.clip(np.linalg.eigvalsh(corr), 0.0, None)
    total = eig.sum()
    return float(total * total / (eig * eig).sum()) if total > 0 else 0.0


# ------------------------------------------------ serial dependence, robustly

def default_lags(n: int) -> int:
    return max(1, int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))


def hac_tstat(x: np.ndarray, lags: Optional[int] = None):
    """t-statistic of the mean with a Newey-West variance, along the last axis.

    Returns (t, se): floats for one series, arrays for a batch.
    """
    x = np.asarray(x, dtype=float)
    n = x.shape[-1]
    if n < 3:
        nan = np.full(x.shape[:-1], np.nan)
        return (float("nan"), float("nan")) if x.ndim == 1 else (nan, nan)
    lags = default_lags(n) if lags is None else int(lags)
    lags = min(lags, n - 1)
    mean = x.mean(axis=-1)
    d = x - mean[..., None]
    lrv = (d * d).sum(axis=-1) / n
    for k in range(1, lags + 1):
        weight = 1.0 - k / (lags + 1.0)
        lrv = lrv + 2.0 * weight * (d[..., k:] * d[..., :-k]).sum(axis=-1) / n
    with np.errstate(divide="ignore", invalid="ignore"):
        se = np.sqrt(np.where(lrv > 0, lrv, np.nan) / n)
        t = mean / se
    if x.ndim == 1:
        return float(t), float(se)
    return t, se


def alpha_beta(y: np.ndarray, x: np.ndarray, periods_per_year: float = 252.0, lags: Optional[int] = None) -> Dict[str, Any]:
    """Regress excess returns y on benchmark excess returns x, along the last axis.

    Alpha is what is left after the market is subtracted, the same move as
    subtracting the underlying event before measuring the jet. Its t-statistic
    uses a Newey-West sandwich, so volatility clusters do not flatter it.
    Floats for one series, arrays for a batch.
    """
    y = np.asarray(y, dtype=float)
    x = np.broadcast_to(np.asarray(x, dtype=float), y.shape)
    n = y.shape[-1]
    lags = default_lags(n) if lags is None else int(lags)
    lags = min(lags, n - 1)
    sx = x.sum(axis=-1)
    sy = y.sum(axis=-1)
    sxx = (x * x).sum(axis=-1)
    sxy = (x * y).sum(axis=-1)
    det = n * sxx - sx * sx
    with np.errstate(divide="ignore", invalid="ignore"):
        beta = np.where(det > 0, (n * sxy - sx * sy) / det, np.nan)
        alpha = (sy - beta * sx) / n
        resid = y - alpha[..., None] - beta[..., None] * x
        u1 = resid
        u2 = resid * x
        m11 = (u1 * u1).sum(axis=-1)
        m22 = (u2 * u2).sum(axis=-1)
        m12 = (u1 * u2).sum(axis=-1)
        for k in range(1, lags + 1):
            weight = 1.0 - k / (lags + 1.0)
            m11 = m11 + 2.0 * weight * (u1[..., k:] * u1[..., :-k]).sum(axis=-1)
            m22 = m22 + 2.0 * weight * (u2[..., k:] * u2[..., :-k]).sum(axis=-1)
            m12 = m12 + weight * ((u1[..., k:] * u2[..., :-k]).sum(axis=-1) + (u2[..., k:] * u1[..., :-k]).sum(axis=-1))
        v1 = sxx / det
        v2 = -sx / det
        var_alpha = v1 * v1 * m11 + 2.0 * v1 * v2 * m12 + v2 * v2 * m22
        w1 = -sx / det
        w2 = n / det
        var_beta = w1 * w1 * m11 + 2.0 * w1 * w2 * m12 + w2 * w2 * m22
        se_alpha = np.sqrt(np.where(var_alpha > 0, var_alpha, np.nan))
        se_beta = np.sqrt(np.where(var_beta > 0, var_beta, np.nan))
        resid_sd = np.sqrt((resid * resid).sum(axis=-1) / max(n - 2, 1))
        out = {
            "alpha_ann": alpha * periods_per_year,
            "beta": beta,
            "t_alpha": alpha / se_alpha,
            "se_beta": se_beta,
            "info_ratio": np.where(resid_sd > 0, alpha / resid_sd, np.nan) * math.sqrt(periods_per_year),
        }
    if y.ndim == 1:
        return {key: float(value) for key, value in out.items()}
    return out


# ----------------------------------------------------------------- bootstrap

def stationary_bootstrap_indices(n: int, mean_block: float, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Index arrays (n_boot, n) for the stationary bootstrap.

    Blocks start at a random place and have geometric length with the given
    mean, wrapping around the end, so each resample keeps short-range structure
    (volatility clusters) and loses long-range alignment.
    """
    mean_block = max(1.0, float(mean_block))
    jumps = rng.random((n_boot, n)) < (1.0 / mean_block)
    jumps[:, 0] = True
    starts = rng.integers(0, n, size=(n_boot, n))
    position = np.arange(n)
    last_jump = np.maximum.accumulate(np.where(jumps, position, 0), axis=1)
    base = np.take_along_axis(starts, last_jump, axis=1)
    return (base + (position - last_jump)) % n


def default_block(n: int) -> int:
    return max(5, int(round(n ** (1.0 / 3.0))))


def bootstrap_sharpe(excess: np.ndarray, periods_per_year: float = 252.0, n_boot: int = 2000,
                     mean_block: Optional[float] = None, rng: Optional[np.random.Generator] = None) -> Dict[str, float]:
    """Sharpe ratio with a stationary-bootstrap interval.

    `p_le_zero` is the share of resamples with a Sharpe at or below zero: the
    bootstrap's answer to "could this be nothing?".
    """
    excess = np.asarray(excess, dtype=float)
    n = excess.shape[0]
    rng = rng if rng is not None else np.random.default_rng(0)
    block = default_block(n) if mean_block is None else mean_block
    idx = stationary_bootstrap_indices(n, block, n_boot, rng)
    resampled = sharpe(excess[idx], periods_per_year, axis=1)
    resampled = resampled[np.isfinite(resampled)]
    point = float(sharpe(excess, periods_per_year))
    if resampled.size == 0:
        nan = float("nan")
        return {"sr": point, "se": nan, "lo68": nan, "hi68": nan, "lo95": nan, "hi95": nan, "p_le_zero": nan, "n_boot": 0, "mean_block": float(block)}
    lo68, hi68, lo95, hi95 = np.quantile(resampled, [0.1587, 0.8413, 0.0228, 0.9772])
    return {
        "sr": point,
        "se": float(resampled.std(ddof=1)),
        "lo68": float(lo68), "hi68": float(hi68),
        "lo95": float(lo95), "hi95": float(hi95),
        "p_le_zero": float((1 + np.sum(resampled <= 0.0)) / (1 + resampled.size)),
        "n_boot": int(resampled.size),
        "mean_block": float(block),
    }


# ------------------------------------------------------------------ the path

def drawdown_curve(net: np.ndarray, axis: int = -1) -> np.ndarray:
    nav = np.cumprod(1.0 + np.asarray(net, dtype=float), axis=axis)
    peak = np.maximum.accumulate(np.maximum(nav, 1.0), axis=axis)
    return nav / peak - 1.0


def max_drawdown(net: np.ndarray, axis: int = -1) -> np.ndarray:
    """Worst peak-to-trough loss, as a negative fraction."""
    return drawdown_curve(net, axis=axis).min(axis=axis)


def summarize(net: np.ndarray, rf: Any = 0.0, periods_per_year: float = 252.0) -> Dict[str, Any]:
    """Everything quoted about one return series, with its statistical error."""
    net = np.asarray(net, dtype=float)
    n = int(net.shape[0])
    rf_arr = np.broadcast_to(np.asarray(rf, dtype=float), net.shape)
    excess = net - rf_arr
    years = n / periods_per_year
    nan = float("nan")
    if n < 3:
        return {"n": n, "years": years, "sharpe": nan}
    mean, sd, skew, kurt = (float(v) for v in moments(excess))
    sr_pp = mean / sd if sd > 0 else nan
    root = math.sqrt(periods_per_year)
    se_pp = sharpe_se(sr_pp, n, skew, kurt) if sr_pp == sr_pp else nan
    t_hac, _ = hac_tstat(excess)
    growth = float(np.prod(1.0 + net))
    cagr = growth ** (1.0 / years) - 1.0 if growth > 0 and years > 0 else nan
    rf_growth = float(np.prod(1.0 + rf_arr))
    return {
        "n": n,
        "years": years,
        "cagr": cagr,
        "rf_cagr": rf_growth ** (1.0 / years) - 1.0 if years > 0 else nan,
        "mean_excess_ann": mean * periods_per_year,
        "vol_ann": float(net.std(ddof=1)) * root,
        "sharpe": sr_pp * root if sr_pp == sr_pp else nan,
        "sharpe_se": se_pp * root if se_pp == se_pp else nan,
        "sharpe_pp": sr_pp,
        "t_hac": t_hac,
        "skew": skew,
        "kurt": kurt,
        "max_drawdown": float(max_drawdown(net)),
        "worst_period": float(net.min()),
        "best_period": float(net.max()),
        "hit_rate": float((net > 0).mean()),
        "psr0": psr(sr_pp, 0.0, n, skew, kurt) if sr_pp == sr_pp else nan,
    }


# -------------------------------------------------------------- sensitivity

def expected_z(sharpe_ann: float, years: float) -> float:
    """Expected significance of a true annual Sharpe after `years` of data.

    Z = SR * sqrt(T). Years of data are this field's integrated luminosity,
    and they arrive at one year per year.
    """
    return float(sharpe_ann) * math.sqrt(max(float(years), 0.0))


def years_for_z(sharpe_ann: float, z: float = 3.0) -> float:
    if sharpe_ann <= 0:
        return float("inf")
    return (float(z) / float(sharpe_ann)) ** 2


def fmt_pm(value: float, error: float, digits: int = 2) -> str:
    if value != value:
        return "unknown"
    if error != error:
        return "{0:.{1}f}".format(value, digits)
    return "{0:.{2}f} +/- {1:.{2}f}".format(value, error, digits)
