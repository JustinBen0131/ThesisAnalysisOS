"""Toy markets: pseudo-experiments where the truth is known because we wrote it.

A toy answers the two questions a real market never will: "what would my
method say if there were nothing there?" and "would it find something if there
were?". Every generator takes a numpy Generator, so a seed reproduces a study.

Shapes: single-asset generators return simple returns (B, T); element 0 is a
real draw (callers that need the engine's convention put a zero in front with
`as_market`).
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple

import numpy as np


def generator(seed: int, stream: int = 0) -> np.random.Generator:
    """Independent, reproducible streams from one seed."""
    return np.random.default_rng(np.random.SeedSequence(entropy=int(seed), spawn_key=(int(stream),)))


def student_t(rng: np.random.Generator, nu: float, size: Tuple[int, ...]) -> np.ndarray:
    """Student-t draws scaled to unit variance (nu > 2)."""
    if nu is None or nu == float("inf"):
        return rng.standard_normal(size)
    if nu <= 2:
        raise ValueError("nu must exceed 2 for the variance to exist")
    return rng.standard_t(nu, size=size) * math.sqrt((nu - 2.0) / nu)


def gaussian(batch: int, periods: int, mu_ann: float = 0.0, vol_ann: float = 0.16,
             periods_per_year: float = 252.0, nu: Optional[float] = None,
             rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """Independent returns with constant drift and volatility. `nu` adds fat tails."""
    rng = rng if rng is not None else generator(0)
    mu = mu_ann / periods_per_year
    sd = vol_ann / math.sqrt(periods_per_year)
    return mu + sd * student_t(rng, nu if nu else float("inf"), (batch, periods))


def garch(batch: int, periods: int, mu_ann: float = 0.0, vol_ann: float = 0.16,
          alpha: float = 0.08, beta: float = 0.90, nu: Optional[float] = 6.0,
          periods_per_year: float = 252.0, burn: int = 500,
          rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """GARCH(1,1) with Student-t shocks: volatility clusters, tails are fat, the mean is flat.

    This is the default null. It looks like a market to the eye (calm spells,
    storms, crashes) and contains nothing that predicts the next return's sign.
    """
    if alpha + beta >= 1.0:
        raise ValueError("alpha + beta must be below 1 for a finite variance")
    rng = rng if rng is not None else generator(0)
    mu = mu_ann / periods_per_year
    var_bar = vol_ann * vol_ann / periods_per_year
    omega = var_bar * (1.0 - alpha - beta)
    shocks = student_t(rng, nu if nu else float("inf"), (batch, periods + burn))
    out = np.empty((batch, periods + burn))
    var = np.full(batch, var_bar)
    for t in range(periods + burn):
        eps = np.sqrt(var) * shocks[:, t]
        out[:, t] = eps
        var = omega + alpha * eps * eps + beta * var
    return mu + out[:, burn:]


def regime(batch: int, periods: int, mu_ann: Sequence[float] = (0.12, -0.20),
           vol_ann: Sequence[float] = (0.12, 0.28), stay: Sequence[float] = (0.996, 0.985),
           periods_per_year: float = 252.0, rng: Optional[np.random.Generator] = None,
           return_states: bool = False):
    """Two hidden regimes, calm-and-rising and wild-and-falling.

    Persistent regimes are what a trend rule can earn from. The default spends
    about four fifths of the time in the good state; a bad spell lasts about
    three months.
    """
    rng = rng if rng is not None else generator(0)
    mu = np.asarray(mu_ann, dtype=float) / periods_per_year
    sd = np.asarray(vol_ann, dtype=float) / math.sqrt(periods_per_year)
    stay = np.asarray(stay, dtype=float)
    p_good = (1.0 - stay[1]) / ((1.0 - stay[0]) + (1.0 - stay[1]))
    state = (rng.random(batch) > p_good).astype(int)
    uniform = rng.random((batch, periods))
    noise = rng.standard_normal((batch, periods))
    out = np.empty((batch, periods))
    states = np.empty((batch, periods), dtype=np.int8)
    for t in range(periods):
        switch = uniform[:, t] > stay[state]
        state = np.where(switch, 1 - state, state)
        states[:, t] = state
        out[:, t] = mu[state] + sd[state] * noise[:, t]
    return (out, states) if return_states else out


def latent_drift(batch: int, periods: int, mu_ann: float = 0.04, vol_ann: float = 0.16,
                 r2: float = 0.002, half_life: float = 120.0, periods_per_year: float = 252.0,
                 rng: Optional[np.random.Generator] = None, return_signal: bool = False):
    """Returns with a slow hidden expected return: r_t = mu + x_t + noise.

    x is AR(1) with the given half-life and carries a share `r2` of the return
    variance. r2 = 0 is the null. This is the signal-injection model: the
    amount of predictability is a dial, so a method's efficiency can be
    measured against it.
    """
    rng = rng if rng is not None else generator(0)
    mu = mu_ann / periods_per_year
    var = vol_ann * vol_ann / periods_per_year
    phi = 0.5 ** (1.0 / half_life)
    var_x = r2 * var
    sd_eta = math.sqrt(var_x * (1.0 - phi * phi))
    sd_eps = math.sqrt(var - var_x)
    x = rng.standard_normal(batch) * math.sqrt(var_x)
    eta = rng.standard_normal((batch, periods)) * sd_eta
    eps = rng.standard_normal((batch, periods)) * sd_eps
    out = np.empty((batch, periods))
    signal = np.empty((batch, periods))
    for t in range(periods):
        signal[:, t] = x          # known before the return of t is drawn
        out[:, t] = mu + x + eps[:, t]
        x = phi * x + eta[:, t]
    return (out, signal) if return_signal else out


def correlated(batch: int, periods: int, mu_ann: Sequence[float], vol_ann: Sequence[float],
               corr: np.ndarray, periods_per_year: float = 252.0, nu: Optional[float] = None,
               rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """Several assets with a fixed correlation matrix. Returns (B, T, N)."""
    rng = rng if rng is not None else generator(0)
    mu = np.asarray(mu_ann, dtype=float) / periods_per_year
    sd = np.asarray(vol_ann, dtype=float) / math.sqrt(periods_per_year)
    chol = np.linalg.cholesky(np.asarray(corr, dtype=float))
    z = student_t(rng, nu if nu else float("inf"), (batch, periods, mu.shape[0]))
    return mu + (z @ chol.T) * sd


def ou_pair(batch: int, periods: int, vol_ann: float = 0.20, spread_vol: float = 0.04,
            half_life: float = 15.0, periods_per_year: float = 252.0,
            rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """Two prices sharing one random walk, apart by a mean-reverting spread. Returns prices (B, T, 2)."""
    rng = rng if rng is not None else generator(0)
    sd = vol_ann / math.sqrt(periods_per_year)
    common = np.cumsum(rng.standard_normal((batch, periods)) * sd, axis=1)
    phi = 0.5 ** (1.0 / half_life)
    shock = rng.standard_normal((batch, periods)) * spread_vol * math.sqrt(1.0 - phi * phi)
    spread = np.empty((batch, periods))
    s = rng.standard_normal(batch) * spread_vol
    for t in range(periods):
        s = phi * s + shock[:, t]
        spread[:, t] = s
    log_a = common + 0.5 * spread
    log_b = common - 0.5 * spread
    return 100.0 * np.exp(np.stack([log_a, log_b], axis=-1))


def as_market(returns: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Turn generator output into what the engine and strategies eat.

    Returns (returns, prices) shaped (B, T+1, N): a zero first return, and
    prices that start at 100.
    """
    r = np.asarray(returns, dtype=float)
    if r.ndim == 2:
        r = r[..., None]
    lead = np.zeros(r.shape[:-2] + (1, r.shape[-1]))
    full = np.concatenate([lead, r], axis=-2)
    prices = 100.0 * np.cumprod(1.0 + full, axis=-2)
    return full, prices


def block_resample(returns: np.ndarray, batch: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """Data-driven toys: stationary-bootstrap resamples of real returns (T, N) to (B, T, N).

    Cross-asset correlation and volatility clusters survive. Structure longer
    than a block does not.
    """
    from .stats import stationary_bootstrap_indices

    r = np.asarray(returns, dtype=float)
    if r.ndim == 1:
        r = r[:, None]
    idx = stationary_bootstrap_indices(r.shape[0], mean_block, batch, rng)
    return r[idx]


GENERATORS: Dict[str, object] = {
    "gaussian": gaussian,
    "garch": garch,
    "regime": regime,
    "latent_drift": latent_drift,
}
