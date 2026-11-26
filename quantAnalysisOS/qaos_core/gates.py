"""Gates: checks a strategy or the engine must pass before its numbers are quoted.

    causality     a strategy's weights at t do not change when the future does
    calibration   the engine reproduces things whose answer is known exactly
                  (the standard candles), and the Sharpe estimator recovers a
                  Sharpe ratio that was put in by hand

Each gate returns a verdict in the same four words used everywhere else.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from . import engine, stats, strategies, toys


def causality(name: str, params: Optional[Dict[str, Any]], prices: np.ndarray,
              periods_per_year: float = 252.0, cuts: int = 6, seed: int = 0,
              tolerance: float = 1e-10) -> Dict[str, Any]:
    """Does the strategy look ahead?

    Two probes at several cut points c. Truncation: computed on prices[:c+1]
    alone, the weights up to c must equal the ones computed on the full
    history. Scrambling: with every price after c replaced by noise, the
    weights up to c must not move. A strategy that normalises by a full-sample
    mean, or picks parameters using the whole series, fails here.
    """
    prices = np.asarray(prices, dtype=float)
    periods = prices.shape[-2]
    rng = np.random.default_rng(seed)
    full = strategies.build(name, prices, params, periods_per_year)
    low = max(2, periods // 4)
    if periods - 2 <= low:
        return {"gate": "causality", "verdict": "unknown", "reason": "series too short to probe"}
    points = sorted(set(int(c) for c in rng.integers(low, periods - 1, size=cuts)))
    worst = 0.0
    where = None
    for cut in points:
        truncated = strategies.build(name, prices[..., :cut + 1, :], params, periods_per_year)
        scrambled_prices = prices.copy()
        tail = scrambled_prices[..., cut + 1:, :]
        scrambled_prices[..., cut + 1:, :] = tail * np.exp(rng.standard_normal(tail.shape) * 0.5)
        scrambled = strategies.build(name, scrambled_prices, params, periods_per_year)
        for label, other in (("truncation", truncated), ("scrambling", scrambled[..., :cut + 1, :])):
            diff = float(np.max(np.abs(np.nan_to_num(full[..., :cut + 1, :]) - np.nan_to_num(other))))
            if diff > worst:
                worst, where = diff, {"cut": cut, "probe": label}
    verdict = "holds" if worst <= tolerance else "fails"
    return {"gate": "causality", "strategy": name, "params": params or {}, "verdict": verdict,
            "worst_difference": worst, "where": where, "cuts": points}


def calibration(seed: int = 11, toys_n: int = 4000, periods: int = 2520) -> Dict[str, Any]:
    """The standard candles: quantities whose true value is known without a market."""
    rng = toys.generator(seed)
    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "verdict": "holds" if ok else "fails", "detail": detail})

    # 1. Fully invested, free trading, no delay: the NAV is the asset.
    r, p = toys.as_market(toys.garch(1, periods, mu_ann=0.07, rng=rng))
    held = engine.run(r[0], strategies.hold(p[0]), rf=0.0, costs=engine.Costs(0, 0, 0, 0), lag=0)
    error = abs(held.nav()[-1] / (p[0, -1, 0] / p[0, 0, 0]) - 1.0)
    check("holding the asset reproduces the asset", error < 1e-10, "relative error {0:.1e}".format(error))

    # 2. All cash: the NAV is the risk-free account.
    rate = 0.04 / 252.0
    cash = engine.run(r[0], strategies.cash(p[0]), rf=rate)
    error = abs(cash.nav()[-1] / (1.0 + rate) ** periods - 1.0)
    check("holding cash reproduces the risk-free rate", error < 1e-10, "relative error {0:.1e}".format(error))

    # 3. One round trip at 10 bps costs 20 bps and nothing else.
    flat = np.zeros((8, 1))
    target = np.zeros((8, 1))
    target[1:4] = 1.0
    trip = engine.run(flat, target, costs=engine.Costs(10.0, 0, 0, 0), lag=1)
    paid = 1.0 - trip.nav()[-1]
    expected = 1.0 - (1.0 - 0.001) ** 2
    check("a round trip costs what the cost model says", abs(paid - expected) < 1e-12,
          "paid {0:.6f}, expected {1:.6f}".format(paid, expected))

    # 4. A target decided at t earns nothing from the return of t or t+1 (lag 1).
    noise = toys.gaussian(1, periods, rng=rng)
    rn, pn = toys.as_market(noise)
    peek = np.sign(rn[0])                      # known at the close of t
    for lag in (0, 1):
        sneaky = engine.run(rn[0], peek, costs=engine.Costs(0, 0, 0, 0), lag=lag)
        value = float(sneaky.sharpe())
        check("no return is earned before the trade (lag {0})".format(lag), abs(value) < 1.5,
              "Sharpe of trading yesterday's sign on independent noise: {0:.2f} (a look-ahead bug reads above 10)".format(value))

    # 5. Put a Sharpe ratio in, get it back, with honest errors (independent normal returns).
    truth = 0.6
    sample = toys.gaussian(toys_n, periods, mu_ann=truth * 0.16, vol_ann=0.16, rng=rng)
    estimates = stats.sharpe(sample, 252.0, axis=1)
    mean, sd, skew, kurt = stats.moments(sample, axis=1)
    se = np.array([stats.sharpe_se(m / s, periods, k, q) for m, s, k, q in zip(mean, sd, skew, kurt)]) * math.sqrt(252.0)
    pulls = (estimates - truth) / se
    bias = float(estimates.mean() - truth)
    bias_error = float(estimates.std(ddof=1) / math.sqrt(toys_n))
    width = float(pulls.std(ddof=1))
    check("an injected Sharpe ratio is recovered", abs(bias) < 4.0 * bias_error,
          "bias {0:+.4f} +/- {1:.4f} on a true {2}".format(bias, bias_error, truth))
    check("its quoted error is the real spread (pull width 1)", 0.93 < width < 1.07,
          "pull width {0:.3f} over {1} toys".format(width, toys_n))

    verdict = "holds" if all(item["verdict"] == "holds" for item in checks) else "fails"
    return {"gate": "calibration", "verdict": verdict, "checks": checks, "seed": seed}
