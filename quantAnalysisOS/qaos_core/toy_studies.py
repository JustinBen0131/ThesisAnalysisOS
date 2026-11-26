"""Toy studies: run the method where the truth is known.

Each study is a function of a seed. It returns rows, the settings that made
them, and a headline that states the result in a sentence. Nothing here reads
a market. These are the pseudo-experiments that say what the procedure does
before it is pointed at something where being wrong costs money.

    sensitivity     how much history a true Sharpe ratio needs to be seen
    look_elsewhere  what a search finds in pure noise, and which corrections hold
    pulls           whether the quoted error on a Sharpe ratio is its real spread
    overfit         what the best-in-sample configuration earns afterwards
    power           how often the full procedure confirms an injected signal
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from . import engine, stats, strategies, toys

PPY = 252.0
VOL = 0.16


def _rate(count: int, total: int) -> Dict[str, Any]:
    lo, hi = stats.wilson_interval(count, total)
    return {"k": int(count), "n": int(total), "rate": count / total if total else float("nan"), "lo": lo, "hi": hi}


def _windows(count: int, low: int = 10, high: int = 400) -> List[int]:
    return [int(v) for v in np.unique(np.linspace(low, high, count).round())]


def _trend_weights(prices: np.ndarray, windows: Sequence[int]) -> np.ndarray:
    """(K, B, T, 1) long-or-cash weights for each moving-average window."""
    return np.stack([strategies.trend_sma(prices, window) for window in windows], axis=0)


# ------------------------------------------------------------- sensitivity

def sensitivity(seed: int = 1, toys_n: int = 2000, sharpes: Sequence[float] = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5),
                years: Sequence[int] = (1, 3, 5, 10, 20, 40), quick: bool = False) -> Dict[str, Any]:
    """Significance reached by a real, constant Sharpe ratio after T years.

    Returns are GARCH with fat tails, the drift set so the true Sharpe is
    exact. Z is the autocorrelation-robust t-statistic of the mean excess
    return, the same statistic a study's `sharpe` test uses. The rows with a
    true Sharpe of zero are the test's size: how often it reaches 2 or 3 sigma
    on nothing (a normal Z would, 2.3% and 0.13% of the time).
    """
    if quick:
        toys_n, years = 300, tuple(y for y in years if y <= 10)
    longest = int(max(years) * PPY)
    rows = []
    for index, true_sharpe in enumerate(sharpes):
        x = toys.garch(toys_n, longest, mu_ann=true_sharpe * VOL, vol_ann=VOL, rng=toys.generator(seed, index))
        for horizon in years:
            z, _ = stats.hac_tstat(x[:, :int(horizon * PPY)])
            z = z[np.isfinite(z)]
            rows.append({
                "true_sharpe": true_sharpe, "years": horizon,
                "expected_z": stats.expected_z(true_sharpe, horizon),
                "median_z": float(np.median(z)),
                "power_2sigma": _rate(int((z >= 2.0).sum()), z.size),
                "power_3sigma": _rate(int((z >= 3.0).sum()), z.size),
            })
    need = {str(s): stats.years_for_z(s, 3.0) for s in sharpes if s > 0}
    size = [row for row in rows if row["true_sharpe"] == 0.0]
    return {
        "study": "sensitivity", "seed": seed,
        "settings": {"toys": toys_n, "market": "GARCH(1,1), Student-t(6) shocks, 16% volatility", "statistic": "Newey-West t of mean excess return"},
        "rows": rows,
        "years_for_3_sigma": need,
        "size_at_2_sigma": {str(row["years"]): row["power_2sigma"] for row in size},
        "headline": "Z grows like Sharpe x sqrt(years). A true Sharpe of 0.5 needs {0:.0f} years to reach 3 sigma half the time; "
                    "a true 1.0 needs {1:.0f}.".format(need.get("0.5", float("nan")), need.get("1.0", float("nan"))),
    }


# ---------------------------------------------------------- look elsewhere

def _lag_weights(returns: np.ndarray, count: int) -> np.ndarray:
    """(K, B, T, 1): rule k is long when the return k days ago was positive and short when it was negative.

    Fifty of these are fifty unrelated bets, which is what a wide search
    through unrelated ideas looks like. Fifty trend windows are barely two.
    """
    rules = []
    for k in range(1, count + 1):
        rules.append(np.nan_to_num(np.sign(strategies.lagged(returns, k - 1))))
    return np.stack(rules, axis=0)


def look_elsewhere(seed: int = 2, toys_n: int = 400, years: int = 10, grid_sizes: Sequence[int] = (1, 5, 20, 50),
                   n_shifts: int = 100, alpha: float = 0.05, quick: bool = False) -> Dict[str, Any]:
    """Search a family of rules on markets that contain nothing, and count discoveries.

    The market is GARCH noise with zero drift and trading is free, so every
    rule's true Sharpe is exactly zero and any 'discovery' is false. Two
    families are searched: trend windows, which are near-copies of each other,
    and lagged-sign rules, which are nearly unrelated. Four ways of judging
    the best rule found:

      naive        its own t-statistic, as if it were the only one tried
      deflated     deflated Sharpe ratio, counting the N rules
      deflated_eff the same, counting effective (decorrelated) rules
      mixed_event  rotate the whole family's weights against the returns and
                   compare the best with the best of each rotation
    """
    if quick:
        toys_n, n_shifts, grid_sizes = 60, 60, tuple(g for g in grid_sizes if g <= 20)
    largest = max(grid_sizes)
    windows = _windows(largest)
    warmup = max(max(windows), largest) + 3
    periods = int(years * PPY)
    z_alpha = stats.norm_ppf(1.0 - alpha)
    free = engine.Costs(0.0, 0.0, 0.0, 0.0)
    subsets = {size: np.unique(np.linspace(0, largest - 1, size).round().astype(int)) for size in grid_sizes}
    families = {
        "trend windows": lambda returns, prices: _trend_weights(prices, windows),
        "unrelated rules": lambda returns, prices: _lag_weights(returns, largest),
    }
    shifts = np.sort(toys.generator(seed, 999).choice(np.arange(int(PPY), periods - int(PPY)), size=n_shifts, replace=False))
    methods = ("naive", "deflated", "deflated_eff", "mixed_event")
    rows = []
    for family_index, (family, make) in enumerate(families.items()):
        counts = {size: dict.fromkeys(methods, 0) for size in grid_sizes}
        best_sharpes = {size: [] for size in grid_sizes}
        n_eff_seen = {size: [] for size in grid_sizes}
        chunk, done, stream = 4, 0, 0
        while done < toys_n:
            size_now = min(chunk, toys_n - done)
            raw = toys.garch(size_now, periods + warmup, mu_ann=0.0, vol_ann=VOL, rng=toys.generator(seed, stream))
            stream += 1                          # the same markets for both families
            returns, prices = toys.as_market(raw)
            weights = make(returns, prices)[:, :, warmup:, :]                      # (K, b, T, 1)
            r = returns[:, warmup:, :]
            excess = engine.run(r, weights, costs=free, lag=1, lean=True).net[..., 1:]   # (K, b, T-1)
            sharpes = stats.sharpe(excess, PPY)                                     # (K, b)
            null = engine.run(r, weights, costs=free, lag=1, shifts=shifts, lean=True).sharpe()  # (S, K, b)
            t_all, _ = stats.hac_tstat(excess)
            n = excess.shape[-1]
            for size, index in subsets.items():
                pick = np.where(np.isfinite(sharpes[index]), sharpes[index], -np.inf).argmax(axis=0)
                for b in range(size_now):
                    k = index[pick[b]]
                    best = float(sharpes[k, b])
                    best_sharpes[size].append(best)
                    if t_all[k, b] >= z_alpha:
                        counts[size]["naive"] += 1
                    mean, sd, skew, kurt = (float(v) for v in stats.moments(excess[k, b]))
                    per_period = sharpes[index, b] / math.sqrt(PPY)
                    per_period = per_period[np.isfinite(per_period)]
                    var_trials = float(per_period.var(ddof=1)) if per_period.size > 1 else 0.0
                    n_eff = stats.effective_trials(excess[index, b]) if len(index) > 1 else 1.0
                    n_eff_seen[size].append(n_eff)
                    if stats.deflated_sharpe(mean / sd, n, skew, kurt, len(index), var_trials)["p"] < alpha:
                        counts[size]["deflated"] += 1
                    if stats.deflated_sharpe(mean / sd, n, skew, kurt, n_eff, var_trials)["p"] < alpha:
                        counts[size]["deflated_eff"] += 1
                    best_null = np.where(np.isfinite(null[:, index, b]), null[:, index, b], -np.inf).max(axis=1)
                    if (1.0 + (best_null >= best).sum()) / (1.0 + best_null.size) < alpha:
                        counts[size]["mixed_event"] += 1
            done += size_now
        for size in grid_sizes:
            rows.append({
                "family": family, "grid": int(len(subsets[size])),
                "effective_trials": float(np.mean(n_eff_seen[size])),
                "mean_best_sharpe": float(np.mean(best_sharpes[size])),
                "false_positive": {name: _rate(counts[size][name], toys_n) for name in methods},
            })
    wide = [row for row in rows if row["family"] == "unrelated rules"][-1]
    narrow = [row for row in rows if row["family"] == "trend windows"][-1]
    return {
        "study": "look_elsewhere", "seed": seed,
        "settings": {"toys": toys_n, "years": years, "market": "GARCH noise, zero drift, free trading",
                     "families": "trend windows of {0} to {1} days; long or short on the sign of the return k days ago, k = 1 to {2}".format(
                         windows[0], windows[-1], largest),
                     "nominal_alpha": alpha, "n_shifts": n_shifts},
        "rows": rows,
        "headline": "On pure noise the best of {0} unrelated rules shows a Sharpe of {1:+.2f} and passes as significant in {2:.0%} of markets "
                    "when judged alone (nominal {3:.0%}); rotated against the whole family it passes in {4:.0%}. "
                    "{5} trend windows are worth only {6:.1f} independent rules: best {7:+.2f}, {8:.0%} alone, {9:.0%} rotated.".format(
                        wide["grid"], wide["mean_best_sharpe"], wide["false_positive"]["naive"]["rate"], alpha,
                        wide["false_positive"]["mixed_event"]["rate"], narrow["grid"], narrow["effective_trials"],
                        narrow["mean_best_sharpe"], narrow["false_positive"]["naive"]["rate"],
                        narrow["false_positive"]["mixed_event"]["rate"]),
    }


# -------------------------------------------------------------------- pulls

def pulls(seed: int = 3, toys_n: int = 1000, years: int = 10, truth: float = 0.5, n_boot: int = 300,
          quick: bool = False) -> Dict[str, Any]:
    """Put a known Sharpe ratio in; check the estimate and each quoted error.

    A pull is (estimate - truth) / quoted error. If the error is honest, pulls
    have mean 0 and width 1, and 68% of them fall inside +/-1. Three error
    estimates are tested on three kinds of market.
    """
    if quick:
        toys_n, n_boot = 200, 120
    periods = int(years * PPY)
    mu = truth * VOL
    markets: Dict[str, Callable[[np.random.Generator], np.ndarray]] = {
        "normal, independent": lambda rng: toys.gaussian(toys_n, periods, mu, VOL, rng=rng),
        "fat tails, t(4)": lambda rng: toys.gaussian(toys_n, periods, mu, VOL, nu=4.0, rng=rng),
        "GARCH + t(6)": lambda rng: toys.garch(toys_n, periods, mu, VOL, rng=rng),
        "strong GARCH (0.15, 0.84)": lambda rng: toys.garch(toys_n, periods, mu, VOL, alpha=0.15, beta=0.84, burn=3000, rng=rng),
    }
    rows = []
    root = math.sqrt(PPY)
    for index, (name, make) in enumerate(markets.items()):
        x = make(toys.generator(seed, index))
        estimate = stats.sharpe(x, PPY, axis=1)
        mean, sd, skew, kurt = stats.moments(x, axis=1)
        per_period = mean / sd
        mertens = np.sqrt(np.clip(1.0 - skew * per_period + (kurt - 1.0) / 4.0 * per_period ** 2, 0, None) / (periods - 1)) * root
        _, se_mean = stats.hac_tstat(x)
        hac = se_mean / sd * root
        boot = np.empty(toys_n)
        rng = toys.generator(seed, 100 + index)
        block = stats.default_block(periods)
        for b in range(toys_n):
            idx = stats.stationary_bootstrap_indices(periods, block, n_boot, rng)
            boot[b] = np.nanstd(stats.sharpe(x[b][idx], PPY, axis=1), ddof=1)
        entry: Dict[str, Any] = {
            "market": name,
            "bias": float(estimate.mean() - truth),
            "bias_error": float(estimate.std(ddof=1) / math.sqrt(toys_n)),
            "true_spread": float(estimate.std(ddof=1)),
            "errors": {},
        }
        for label, quoted in (("mertens", mertens), ("newey_west", hac), ("bootstrap", boot)):
            pull = (estimate - truth) / quoted
            pull = pull[np.isfinite(pull)]
            entry["errors"][label] = {
                "mean_quoted": float(np.mean(quoted[np.isfinite(quoted)])),
                "pull_mean": float(pull.mean()),
                "pull_width": float(pull.std(ddof=1)),
                "pull_width_error": float(pull.std(ddof=1) / math.sqrt(2.0 * max(pull.size - 1, 1))),
                "coverage_68": _rate(int((np.abs(pull) < 1.0).sum()), pull.size),
                "coverage_95": _rate(int((np.abs(pull) < 1.96).sum()), pull.size),
            }
        rows.append(entry)
    widths = [row["errors"][label]["pull_width"] for row in rows for label in ("mertens", "newey_west", "bootstrap")]
    biased = [row for row in rows if abs(row["bias"]) > 4.0 * row["bias_error"]]
    headline = ("Over {0} years the error on a Sharpe ratio is about {1:.2f}. All three quoted errors are close to honest: "
                "pull widths {2:.2f} to {3:.2f}.".format(years, rows[0]["true_spread"], min(widths), max(widths)))
    if biased:
        worst = max(biased, key=lambda row: abs(row["bias"]))
        headline += (" The estimate itself reads {0:+.2f} away from the truth on '{1}': most decades are calmer than the "
                     "long-run volatility, and a calm decade flatters.".format(worst["bias"], worst["market"]))
    return {
        "study": "pulls", "seed": seed,
        "settings": {"toys": toys_n, "years": years, "true_sharpe": truth, "n_boot": n_boot},
        "rows": rows,
        "headline": headline,
    }


# ------------------------------------------------------------------ overfit

def overfit(seed: int = 4, toys_n: int = 1000, years_dev: int = 10, years_hold: int = 10, grid: int = 50,
            r2s: Sequence[float] = (0.0, 0.004), quick: bool = False) -> Dict[str, Any]:
    """Pick the best configuration on one decade, then run it on the next.

    The asset has no risk premium, so a Sharpe ratio above zero has to come
    from timing. With r2 = 0 there is no timing to find and the search still
    returns a winner; with r2 > 0 a slow hidden drift is really there.
    """
    if quick:
        toys_n, grid = 200, 20
    windows = _windows(grid)
    warmup = max(windows) + 3
    dev = int(years_dev * PPY)
    hold = int(years_hold * PPY)
    rows = []
    for index, r2 in enumerate(r2s):
        best_dev, then_hold, median_pick = [], [], []
        chunk = 50
        for start in range(0, toys_n, chunk):
            size = min(chunk, toys_n - start)
            raw = toys.latent_drift(size, warmup + dev + hold, mu_ann=0.0, vol_ann=VOL, r2=r2,
                                    rng=toys.generator(seed, 1000 * index + start))
            returns, prices = toys.as_market(raw)
            weights = _trend_weights(prices, windows)
            result = engine.run(returns, weights, lag=1, lean=True)
            dev_sharpe = stats.sharpe(result.net[..., warmup + 1:warmup + 1 + dev], PPY)
            hold_sharpe = stats.sharpe(result.net[..., warmup + 1 + dev:], PPY)
            pick = np.where(np.isfinite(dev_sharpe), dev_sharpe, -np.inf).argmax(axis=0)
            cols = np.arange(size)
            best_dev.extend(dev_sharpe[pick, cols])
            then_hold.extend(hold_sharpe[pick, cols])
            median_pick.extend(np.asarray(windows)[pick])
        best_dev_arr, then_hold_arr = np.asarray(best_dev), np.asarray(then_hold)
        rows.append({
            "r2": r2, "grid": len(windows), "oracle_sharpe": math.sqrt(r2 * PPY),
            "development_best": float(best_dev_arr.mean()),
            "holdout_same_config": float(then_hold_arr.mean()),
            "holdout_error": float(then_hold_arr.std(ddof=1) / math.sqrt(toys_n)),
            "correlation": float(np.corrcoef(best_dev_arr, then_hold_arr)[0, 1]),
            "holdout_positive": _rate(int((then_hold_arr > 0).sum()), toys_n),
            "median_window": float(np.median(median_pick)),
        })
    null = rows[0]
    return {
        "study": "overfit", "seed": seed,
        "settings": {"toys": toys_n, "years_development": years_dev, "years_holdout": years_hold,
                     "market": "no premium; hidden drift with half-life 120 days carrying a share r2 of daily variance",
                     "costs": "5 bps per trade"},
        "rows": rows,
        "headline": "With nothing to find, the best of {0} rules earned a Sharpe of {1:+.2f} on the decade it was chosen on "
                    "and {2:+.2f} +/- {3:.2f} on the next.".format(null["grid"], null["development_best"],
                                                                 null["holdout_same_config"], null["holdout_error"]),
    }


# -------------------------------------------------------------------- power

def power(seed: int = 5, toys_n: int = 400, years_dev: int = 10, years_hold: int = 10,
          r2s: Sequence[float] = (0.0, 0.001, 0.002, 0.004, 0.008), grid: int = 12, z_min: float = 2.0,
          n_shifts: int = 200, premium: float = 0.05, quick: bool = False) -> Dict[str, Any]:
    """Inject a timing signal of known size and count how often the procedure confirms it.

    The asset now pays an equity-like premium, as real ones do. The procedure
    is the one a study follows: scan a registered grid on the development
    decade, freeze the best, open the holdout decade once. Three registered
    tests are compared at the same bar.

      sharpe   is the strategy's holdout Sharpe above zero?
      alpha    is there return left after regressing on buy-and-hold?
      timing   does the real alignment beat the mixed-event rotations?

    At r2 = 0 there is no timing skill, so a confirmation there is a false one.
    """
    if quick:
        toys_n, n_shifts, r2s = 100, 100, tuple(r2s[:3])
    windows = _windows(grid, 20, 300)
    warmup = max(windows) + 3
    dev = int(years_dev * PPY)
    hold = int(years_hold * PPY)
    p_bar = stats.p_from_z(z_min)
    shifts = np.sort(toys.generator(seed, 999).choice(np.arange(int(PPY), hold - int(PPY)), size=n_shifts, replace=False))
    rows = []
    for index, r2 in enumerate(r2s):
        confirm = {"sharpe": 0, "alpha": 0, "timing": 0}
        strat_sharpe, hold_sharpe = [], []
        chunk = 25
        for start in range(0, toys_n, chunk):
            size = min(chunk, toys_n - start)
            raw = toys.latent_drift(size, warmup + dev + hold, mu_ann=premium, vol_ann=VOL, r2=r2,
                                    rng=toys.generator(seed, 1000 * index + start))
            returns, prices = toys.as_market(raw)
            weights = _trend_weights(prices, windows)
            result = engine.run(returns, weights, lag=1, lean=True)
            dev_sharpe = stats.sharpe(result.net[..., warmup + 1:warmup + 1 + dev], PPY)
            pick = np.where(np.isfinite(dev_sharpe), dev_sharpe, -np.inf).argmax(axis=0)
            cols = np.arange(size)
            first = warmup + 1 + dev
            chosen_net = result.net[pick, cols][:, first:]
            market = returns[:, first:, 0]
            z_sharpe, _ = stats.hac_tstat(chosen_net)
            z_alpha = stats.alpha_beta(chosen_net, market)["t_alpha"]
            chosen_weights = weights[pick, cols][:, first - 1:, :]
            cut_returns = returns[:, first - 1:, :]
            observed = engine.run(cut_returns, chosen_weights, lag=1, lean=True).sharpe()
            null = engine.run(cut_returns, chosen_weights, lag=1, shifts=shifts, lean=True).sharpe()
            p_timing = (1.0 + (np.where(np.isfinite(null), null, -np.inf) >= observed).sum(axis=0)) / (1.0 + null.shape[0])
            confirm["sharpe"] += int(np.sum(z_sharpe >= z_min))
            confirm["alpha"] += int(np.sum(z_alpha >= z_min))
            confirm["timing"] += int(np.sum(p_timing <= p_bar))
            strat_sharpe.extend(stats.sharpe(chosen_net, PPY))
            hold_sharpe.extend(stats.sharpe(market, PPY))
        rows.append({
            "r2": r2, "oracle_sharpe": math.sqrt(r2 * PPY),
            "holdout_sharpe_strategy": float(np.mean(strat_sharpe)),
            "holdout_sharpe_buy_and_hold": float(np.mean(hold_sharpe)),
            "confirmed": {name: _rate(confirm[name], toys_n) for name in ("sharpe", "alpha", "timing")},
        })
    null_row = rows[0]
    strongest = rows[-1]
    return {
        "study": "power", "seed": seed,
        "settings": {"toys": toys_n, "years_development": years_dev, "years_holdout": years_hold, "grid": len(windows),
                     "premium": premium, "z_min": z_min, "n_shifts": n_shifts,
                     "market": "5% premium, 16% volatility, hidden drift with half-life 120 days"},
        "rows": rows,
        "headline": "With no timing skill in the market, the 'sharpe' test still confirms {0:.1%} of the time (nominal {7:.1%}) because the asset pays a premium; "
                    "'alpha' confirms {1:.1%} and 'timing' {2:.1%}. With a signal that would give a perfect forecaster a Sharpe of {3:.1f}, "
                    "ten years of holdout confirm it {5:.0%} of the time by 'alpha' and {6:.0%} by 'timing'.".format(
                        null_row["confirmed"]["sharpe"]["rate"], null_row["confirmed"]["alpha"]["rate"], null_row["confirmed"]["timing"]["rate"],
                        strongest["oracle_sharpe"], strongest["confirmed"]["sharpe"]["rate"], strongest["confirmed"]["alpha"]["rate"],
                        strongest["confirmed"]["timing"]["rate"], p_bar),
    }


STUDIES: Dict[str, Callable[..., Dict[str, Any]]] = {
    "sensitivity": sensitivity,
    "look_elsewhere": look_elsewhere,
    "pulls": pulls,
    "overfit": overfit,
    "power": power,
}
