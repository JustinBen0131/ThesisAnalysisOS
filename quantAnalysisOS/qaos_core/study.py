"""A study: register, search in the open, freeze, open the box once.

    register   write the hypothesis, the data, every configuration that may be
               tried, the test and the bar. Sealed before any number is seen.
    scan       evaluate the registered grid on the development window only.
               The holdout rows are cut off before a strategy sees the data.
               Every evaluation is appended to the study's trial log.
    freeze     pick one configuration, and say what the search cost: the trial
               count, the deflated Sharpe ratio, the mixed-event global p, and
               how much the holdout could possibly tell us.
    unblind    run the frozen configuration on the holdout. Once. The verdict
               is whatever the registered rule says it is.

A result stands on the data it read, the code that computed it and the sealed
registration. `standing` reads those back and answers in one word: holds,
stale, fails or unknown.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from . import engine, stats, store, strategies
from .data import Dataset

CODE_FILES = ("engine.py", "strategies.py", "stats.py", "study.py")
TOY_CODE_FILES = CODE_FILES + ("toys.py", "toy_studies.py")
TESTS = ("sharpe", "timing", "alpha")
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")
WARMUP_KEYS = ("window", "lookback", "vol_window")


class StudyError(Exception):
    """A refusal. The message says what was refused and why."""


def code_fingerprint(files: Tuple[str, ...] = CODE_FILES) -> str:
    """Hash of the code a recorded number depends on. A change makes the record stale."""
    here = Path(__file__).resolve().parent
    return store.sha256_files([here / name for name in files], root=here)


def toy_code_fingerprint() -> str:
    return code_fingerprint(TOY_CODE_FILES)


class Book:
    """Where the record lives: studies, toy runs, paper accounts."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def studies(self) -> Path:
        return self.root / "studies"

    @property
    def paper(self) -> Path:
        return self.root / "paper"

    @property
    def toys(self) -> Path:
        return self.root / "toys"

    def study_ids(self) -> List[str]:
        if not self.studies.is_dir():
            return []
        return sorted(path.name for path in self.studies.iterdir() if (path / "prereg.json").is_file())


def _config_hash(entry: Dict[str, Any]) -> str:
    return store.sha256_obj({"strategy": entry["strategy"], "params": entry.get("params") or {}})[:16]


def _normalise_grid(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    default = spec.get("strategy")
    grid = []
    for raw in spec.get("grid") or []:
        if "strategy" in raw or "params" in raw:
            entry = {"strategy": raw.get("strategy", default), "params": dict(raw.get("params") or {})}
        else:
            entry = {"strategy": default, "params": dict(raw)}
        if entry["strategy"] not in strategies.REGISTRY:
            raise StudyError("grid names an unknown strategy: {0}".format(entry["strategy"]))
        grid.append(entry)
    hashes = [_config_hash(entry) for entry in grid]
    if len(set(hashes)) != len(hashes):
        raise StudyError("the grid lists the same configuration twice")
    return grid


def default_warmup(grid: List[Dict[str, Any]], lag: int) -> int:
    longest = 0
    for entry in grid:
        for key in WARMUP_KEYS:
            value = (entry.get("params") or {}).get(key)
            if isinstance(value, (int, float)):
                longest = max(longest, int(value))
    return longest + int(lag) + 2


def rebalance_mask(rule: Any, dates: np.ndarray) -> Optional[np.ndarray]:
    if rule in (None, "every"):
        return None
    if rule == "month_end":
        return strategies.month_ends(dates)
    if rule == "month_start":
        return strategies.month_starts(dates)
    if isinstance(rule, dict) and "every" in rule:
        return strategies.every(dates.shape[0], int(rule["every"]), int(rule.get("offset", 0)))
    raise StudyError("unknown rebalance rule: {0!r}".format(rule))


class Study:
    def __init__(self, book: Book, study_id: str, clock: Optional[Callable[[], str]] = None) -> None:
        self.book = book
        self.id = study_id
        self.dir = book.studies / study_id
        self.clock = clock or store.now_iso
        self.prereg = store.read_json(self.dir / "prereg.json")
        if self.prereg is None:
            raise StudyError("no study {0} in {1}".format(study_id, book.studies))
        self.trials = store.ChainLog(self.dir / "trials.jsonl", clock=self.clock)

    # ------------------------------------------------------------ register
    @staticmethod
    def register(book: Book, spec: Dict[str, Any], dataset: Dataset,
                 clock: Optional[Callable[[], str]] = None) -> "Study":
        clock = clock or store.now_iso
        study_id = str(spec.get("id") or "")
        if not ID_PATTERN.match(study_id):
            raise StudyError("a study id looks like QA-1, got {0!r}".format(study_id))
        target = book.studies / study_id
        if (target / "prereg.json").exists():
            raise StudyError("{0} is already registered. A registration is not edited; register a new study.".format(study_id))
        for key in ("title", "hypothesis", "holdout_start"):
            if not str(spec.get(key) or "").strip():
                raise StudyError("registration needs '{0}'".format(key))
        grid = _normalise_grid(spec)
        if not grid:
            raise StudyError("registration needs a grid: every configuration that may be tried")
        decision = dict(spec.get("decision") or {})
        decision.setdefault("test", "sharpe")
        decision.setdefault("z_min", 2.0)
        decision.setdefault("cost_stress", 2.0)
        if decision["test"] not in TESTS:
            raise StudyError("decision.test must be one of {0}".format(", ".join(TESTS)))
        settings = dict(spec.get("engine") or {})
        settings.setdefault("lag", 1)
        settings.setdefault("rebalance", "every")
        settings.setdefault("band", 0.0)
        settings["costs"] = engine.Costs.from_dict(settings.get("costs")).to_dict()
        settings.setdefault("warmup", default_warmup(grid, settings["lag"]))
        rebalance_mask(settings["rebalance"], dataset.dates)
        split = dataset.index_at_or_after(spec["holdout_start"])
        periods = dataset.dates.shape[0]
        if split <= settings["warmup"] + 2 or split >= periods - 2:
            raise StudyError("holdout_start {0} leaves no room: development has {1} periods, holdout {2}".format(
                spec["holdout_start"], split, periods - split))
        benchmark = spec.get("benchmark") or {"strategy": "hold", "params": {}}
        if benchmark.get("strategy") not in strategies.REGISTRY:
            raise StudyError("unknown benchmark strategy")
        if decision["test"] == "timing":
            rotations = engine.rotations_available(periods - split, dataset.periods_per_year)
            reach = stats.z_from_p(1.0 / (1.0 + rotations)) if rotations else float("-inf")
            if reach < float(decision["z_min"]):
                raise StudyError("the timing test cannot reach {0} sigma on this holdout: {1} rotations resolve at most {2:.2f} sigma. "
                                 "Register the alpha test, or a lower bar.".format(decision["z_min"], rotations, reach))
        dev = dataset.head(split)
        holdout_first, holdout_last = str(dataset.dates[split]), str(dataset.dates[-1])
        seen_by = []
        for other_id in book.study_ids():
            other = store.read_json(book.studies / other_id / "prereg.json") or {}
            opened = (book.studies / other_id / "result.json").is_file()
            same_data = (other.get("dataset") or {}).get("name") == dataset.name
            other_holdout = other.get("holdout") or {}
            overlaps = other_holdout.get("start", "9999") <= holdout_last and other_holdout.get("last", "0000") >= holdout_first
            if opened and same_data and overlaps:
                seen_by.append(other_id)
        if seen_by and not str(spec.get("prior_exposure") or "").strip():
            raise StudyError("this holdout was already opened by {0}. Say in prior_exposure what was found there; "
                             "the new study is not blind to it.".format(", ".join(seen_by)))
        prereg = store.seal({
            "id": study_id,
            "title": spec["title"],
            "hypothesis": spec["hypothesis"],
            "prior_exposure": spec.get("prior_exposure", ""),
            "notes": [str(note) for note in (spec.get("notes") or [])],
            "registered_at": clock(),
            "registered_by": spec.get("registered_by", ""),
            "dataset": dataset.describe(),
            "development": {"first": str(dev.dates[0]), "last": str(dev.dates[-1]),
                            "periods": int(split), "fingerprint": dev.fingerprint()},
            "holdout": {"start": holdout_first, "last": holdout_last, "periods": int(periods - split),
                        "already_opened_by": seen_by},
            "holdout_start": str(spec["holdout_start"]),
            "grid": grid,
            "selection": spec.get("selection", "best development Sharpe"),
            "engine": settings,
            "benchmark": {"strategy": benchmark["strategy"], "params": dict(benchmark.get("params") or {})},
            "decision": decision,
            "code": code_fingerprint(),
        })
        store.write_json_atomic(target / "prereg.json", prereg)
        study = Study(book, study_id, clock=clock)
        study.trials.append({"kind": "registered", "seal": prereg["seal"]})
        return study

    # --------------------------------------------------------------- state
    @property
    def frozen(self) -> Optional[Dict[str, Any]]:
        return store.read_json(self.dir / "frozen.json")

    @property
    def result(self) -> Optional[Dict[str, Any]]:
        return store.read_json(self.dir / "result.json")

    def state(self) -> str:
        if self.result is not None:
            return "unblinded"
        if self.frozen is not None:
            return "frozen"
        if any(entry.get("kind") == "trial" for entry in self.trials.read()):
            return "developing"
        return "registered"

    def grid(self) -> List[Dict[str, Any]]:
        grid = list(self.prereg["grid"])
        for entry in self.trials.read():
            if entry.get("kind") == "amendment":
                grid.extend(entry["added"])
        return grid

    # ---------------------------------------------------------------- data
    def _registered_data(self, dataset: Dataset) -> Dataset:
        """The dataset cut to the registered span, refused if its numbers changed."""
        registered = self.prereg["dataset"]
        cut = dataset.window(registered["first"], registered["last"])
        if cut.fingerprint() != registered["fingerprint"]:
            raise StudyError(
                "stale: the data no longer matches what {0} was registered on "
                "(registered {1}..., now {2}...). A vendor revision counts. "
                "Restore the registered snapshot or register a new study.".format(
                    self.id, registered["fingerprint"][:12], cut.fingerprint()[:12]))
        return cut

    def _dev(self, dataset: Dataset) -> Dataset:
        full = self._registered_data(dataset)
        return full.head(int(self.prereg["development"]["periods"]))

    def _run(self, ds: Dataset, entries: List[Dict[str, Any]], costs: Optional[engine.Costs] = None,
             lag: Optional[int] = None, shifts: Optional[np.ndarray] = None) -> engine.Result:
        settings = self.prereg["engine"]
        weights = np.stack([strategies.build(entry["strategy"], ds.prices, entry.get("params"), ds.periods_per_year)
                            for entry in entries], axis=0)
        return engine.run(ds.returns, weights, rf=ds.rf,
                          costs=costs or engine.Costs.from_dict(settings["costs"]),
                          lag=int(settings["lag"]) if lag is None else lag,
                          rebalance=rebalance_mask(settings["rebalance"], ds.dates),
                          band=float(settings["band"]), periods_per_year=ds.periods_per_year, shifts=shifts)

    @staticmethod
    def _one(result: engine.Result, index: int) -> engine.Result:
        return engine.Result(net=result.net[index], gross=result.gross[index], turnover=result.turnover[index],
                             exposure=result.exposure[index], rf=result.rf, periods_per_year=result.periods_per_year)

    # ---------------------------------------------------------------- scan
    def amend(self, added: List[Dict[str, Any]], reason: str) -> None:
        """Add configurations after registration. Allowed, logged, and counted."""
        if self.state() in ("frozen", "unblinded"):
            raise StudyError("{0} is {1}; the search is over".format(self.id, self.state()))
        if not str(reason).strip():
            raise StudyError("an amendment needs a reason")
        entries = _normalise_grid({"strategy": self.prereg["grid"][0]["strategy"], "grid": added})
        known = {_config_hash(entry) for entry in self.grid()}
        entries = [entry for entry in entries if _config_hash(entry) not in known]
        if entries:
            self.trials.append({"kind": "amendment", "added": entries, "reason": reason})

    def scan(self, dataset: Dataset) -> List[Dict[str, Any]]:
        """Evaluate every registered configuration on the development window."""
        if self.state() in ("frozen", "unblinded"):
            raise StudyError("{0} is {1}; no more development evaluations".format(self.id, self.state()))
        dev = self._dev(dataset)
        grid = self.grid()
        result = self._run(dev, grid)
        warmup = int(self.prereg["engine"]["warmup"])
        rows = []
        for index, entry in enumerate(grid):
            summary = self._one(result, index).summary(start=warmup)
            row = {"kind": "trial", "index": index, "strategy": entry["strategy"], "params": entry["params"],
                   "config": _config_hash(entry), "window": [str(dev.dates[warmup]), str(dev.dates[-1])],
                   "data": dev.fingerprint(), "code": code_fingerprint()}
            row.update({key: summary[key] for key in (
                "n", "years", "sharpe", "sharpe_se", "cagr", "vol_ann", "max_drawdown", "turnover_ann", "avg_exposure")})
            self.trials.append(row)
            rows.append(row)
        return rows

    def trial_rows(self) -> List[Dict[str, Any]]:
        """Latest development evaluation of each configuration."""
        latest: Dict[str, Dict[str, Any]] = {}
        for entry in self.trials.read():
            if entry.get("kind") == "trial":
                latest[entry["config"]] = entry
        return sorted(latest.values(), key=lambda row: row["index"])

    # -------------------------------------------------------------- freeze
    def freeze(self, dataset: Dataset, choice: Optional[int] = None, n_shifts: int = 500,
               seed: int = 20260101) -> Dict[str, Any]:
        """Fix the configuration and account for the search that found it."""
        if self.state() == "unblinded":
            raise StudyError("{0} is already unblinded".format(self.id))
        if self.frozen is not None:
            raise StudyError("{0} is already frozen".format(self.id))
        grid = self.grid()
        rows = self.trial_rows()
        if len(rows) < len(grid):
            raise StudyError("scan first: {0} of {1} registered configurations have been evaluated".format(len(rows), len(grid)))
        dev = self._dev(dataset)
        warmup = int(self.prereg["engine"]["warmup"])
        ppy = dev.periods_per_year
        result = self._run(dev, grid)
        excess = result.excess[:, warmup:]
        sharpes = stats.sharpe(excess, ppy, axis=-1)
        finite = np.isfinite(sharpes)
        if choice is None:
            if not finite.any():
                raise StudyError("no configuration produced a finite Sharpe ratio")
            choice = int(np.nanargmax(np.where(finite, sharpes, -np.inf)))
            selection = "best development Sharpe of {0}".format(len(grid))
        else:
            selection = "declared by the researcher (index {0} of {1})".format(choice, len(grid))
        chosen = grid[choice]
        summary = self._one(result, choice).summary(start=warmup)
        n = int(summary["n"])
        per_period = sharpes[finite] / math.sqrt(ppy)
        var_trials = float(per_period.var(ddof=1)) if per_period.size > 1 else 0.0
        n_eff = stats.effective_trials(excess[finite]) if finite.sum() > 1 else float(finite.sum())
        deflated = stats.deflated_sharpe(summary["sharpe_pp"], n, summary["skew"], summary["kurt"], len(grid), var_trials)
        deflated_eff = stats.deflated_sharpe(summary["sharpe_pp"], n, summary["skew"], summary["kurt"], n_eff, var_trials)
        rng = np.random.default_rng(seed)
        scored = dev.dates.shape[0] - warmup
        null = self._mixed_event(dev, grid, warmup, n_shifts, rng) if scored >= 8 * 2 else None
        bench = self._benchmark(dev, warmup)
        alpha = stats.alpha_beta(excess[choice], bench.excess[warmup:], ppy)
        holdout_periods = int(self.prereg["holdout"]["periods"])
        holdout_years = holdout_periods / ppy
        sr = float(summary["sharpe"])
        sr0_ann = deflated["sr0"] * math.sqrt(ppy)
        se_holdout = math.sqrt((1.0 + 0.5 * sr * sr / ppy) / max(holdout_years, 1e-9))
        frozen = store.seal({
            "study": self.id,
            "frozen_at": self.clock(),
            "chosen": {"index": int(choice), "strategy": chosen["strategy"], "params": chosen["params"],
                       "config": _config_hash(chosen)},
            "selection": selection,
            "development": summary,
            "trials": {"n": len(grid), "n_effective": n_eff, "sharpes": [float(v) if np.isfinite(v) else None for v in sharpes],
                       "var_per_period": var_trials},
            "deflated": {"sr0_ann": sr0_ann, "dsr": deflated["dsr"], "p": deflated["p"], "z": deflated["z"],
                         "sr0_ann_effective": deflated_eff["sr0"] * math.sqrt(ppy), "z_effective": deflated_eff["z"]},
            "mixed_event": null,
            "benchmark": {"summary": bench.summary(start=warmup), "alpha": alpha},
            "holdout_outlook": {
                "periods": holdout_periods, "years": holdout_years,
                "expected_z_if_development_is_truth": stats.expected_z(sr, holdout_years),
                "expected_z_after_haircut": stats.expected_z(max(sr - sr0_ann, 0.0), holdout_years),
                "sharpe_68_band_if_development_is_truth": [sr - se_holdout, sr + se_holdout],
                "years_for_3_sigma_at_development_sharpe": stats.years_for_z(sr, 3.0),
            },
            "data": dev.fingerprint(),
            "code": code_fingerprint(),
            "prereg": self.prereg["seal"],
        })
        store.write_json_atomic(self.dir / "frozen.json", frozen)
        self.trials.append({"kind": "frozen", "seal": frozen["seal"], "chosen": frozen["chosen"]})
        return frozen

    def _mixed_event(self, ds: Dataset, entries: List[Dict[str, Any]], start: int, n_shifts: int,
                     rng: np.random.Generator) -> Dict[str, Any]:
        settings = self.prereg["engine"]
        cut = Dataset(ds.name, ds.dates[start:], ds.symbols, ds.prices[start:], ds.periods_per_year, ds.rf[start:])
        weights = np.stack([strategies.build(entry["strategy"], ds.prices, entry.get("params"), ds.periods_per_year)[start:]
                            for entry in entries], axis=0)
        mask = rebalance_mask(settings["rebalance"], ds.dates)
        null = engine.mixed_event_null(cut.returns, weights, rf=cut.rf, costs=engine.Costs.from_dict(settings["costs"]),
                                       lag=int(settings["lag"]), rebalance=None if mask is None else mask[start:],
                                       band=float(settings["band"]), periods_per_year=ds.periods_per_year,
                                       n_shifts=n_shifts, rng=rng)
        observed = np.atleast_1d(null["observed"])
        return {
            "n_shifts": null["n_shifts"], "min_shift": null["min_shift"],
            "observed": [float(v) if np.isfinite(v) else None for v in observed],
            "p_each": [float(v) for v in np.atleast_1d(null["p"])],
            "null_mean": [float(v) if np.isfinite(v) else None for v in np.atleast_1d(null["null_mean"])],
            "null_sd": [float(v) if np.isfinite(v) else None for v in np.atleast_1d(null["null_sd"])],
            "p_global": null["p_global"], "z_global": null["z_global"],
            "z_resolution": null["z_resolution"], "at_floor": null["at_floor"],
        }

    def _benchmark(self, ds: Dataset, start: int) -> engine.Result:
        bench = self.prereg["benchmark"]
        return self._one(self._run(ds, [bench]), 0)

    # ------------------------------------------------------------- unblind
    def unblind(self, dataset: Dataset, by: str, n_boot: int = 4000, n_shifts: int = 2000,
                seed: int = 20260102) -> Dict[str, Any]:
        """Open the box. Refused unless frozen, and refused a second time."""
        if not str(by).strip():
            raise StudyError("unblinding is signed: pass who is opening the box")
        if self.result is not None:
            raise StudyError("{0} was unblinded on {1}. The box opens once.".format(self.id, self.result.get("opened_at")))
        frozen = self.frozen
        if frozen is None:
            raise StudyError("{0} is not frozen. Freeze the configuration before looking at the holdout.".format(self.id))
        if not store.seal_holds(frozen) or not store.seal_holds(self.prereg):
            raise StudyError("fails: a sealed record of {0} has been edited".format(self.id))
        full = self._registered_data(dataset)
        split = int(self.prereg["development"]["periods"])
        ppy = full.periods_per_year
        chosen = frozen["chosen"]
        entry = {"strategy": chosen["strategy"], "params": chosen["params"]}
        nominal = self._one(self._run(full, [entry]), 0)
        summary = nominal.summary(start=split)
        excess = nominal.excess[split:]
        rng = np.random.default_rng(seed)
        boot = stats.bootstrap_sharpe(excess, ppy, n_boot=n_boot, rng=rng)
        bench = self._benchmark(full, split)
        alpha = stats.alpha_beta(excess, bench.excess[split:], ppy)
        timing = self._mixed_event(full, [entry], split, n_shifts, rng) if excess.shape[0] >= 16 else None
        decision = self.prereg["decision"]
        stress = float(decision.get("cost_stress", 2.0))
        stressed = self._one(self._run(full, [entry], costs=engine.Costs.from_dict(self.prereg["engine"]["costs"]).scaled(stress)), 0)
        stressed_sharpe = float(stats.sharpe(stressed.excess[split:], ppy))
        z_by_test = {
            "sharpe": summary["t_hac"],
            "timing": timing["z_global"] if timing else float("nan"),
            "alpha": alpha["t_alpha"],
        }
        z = z_by_test[decision["test"]]
        z_min = float(decision["z_min"])
        reasons = []
        if not (z == z):
            verdict = "unknown"
            reasons.append("the registered test could not be computed")
        elif z >= z_min and stressed_sharpe > 0:
            verdict = "confirmed"
        else:
            verdict = "not_confirmed"
            if z < z_min:
                reasons.append("Z = {0:.2f} is below the registered bar of {1:.1f}".format(z, z_min))
            if not stressed_sharpe > 0:
                reasons.append("Sharpe is not positive at {0:g}x costs".format(stress))
        dev = frozen["development"]
        se_dev = dev.get("sharpe_se") or float("nan")
        se_hold = boot["se"]
        pull = (summary["sharpe"] - dev["sharpe"]) / math.sqrt(se_dev ** 2 + se_hold ** 2) if se_dev == se_dev and se_hold == se_hold else float("nan")
        result = store.seal({
            "study": self.id,
            "opened_at": self.clock(),
            "opened_by": by,
            "window": [str(full.dates[split]), str(full.dates[-1])],
            "holdout": summary,
            "bootstrap": boot,
            "benchmark": {"summary": bench.summary(start=split), "alpha": alpha},
            "timing": timing,
            "cost_stress": {"factor": stress, "sharpe": stressed_sharpe},
            "z_by_test": z_by_test,
            "decision": {"test": decision["test"], "z": z, "z_min": z_min},
            "verdict": verdict,
            "reasons": reasons,
            "pull_vs_development": pull,
            "trials_counted": frozen["trials"]["n"],
            "data": full.fingerprint(),
            "code": code_fingerprint(),
            "prereg": self.prereg["seal"],
            "frozen": frozen["seal"],
        })
        store.write_json_atomic(self.dir / "result.json", result)
        self.trials.append({"kind": "unblinded", "seal": result["seal"], "by": by, "verdict": verdict})
        return result

    # --------------------------------------------------------- systematics
    def systematics(self, dataset: Dataset, window: str = "development") -> Dict[str, Any]:
        """How far the frozen configuration's Sharpe moves under choices we could have made otherwise."""
        frozen = self.frozen
        if frozen is None:
            raise StudyError("freeze before quoting systematics")
        if window == "holdout" and self.result is None:
            raise StudyError("holdout systematics exist only after unblinding")
        full = self._registered_data(dataset)
        split = int(self.prereg["development"]["periods"])
        warmup = int(self.prereg["engine"]["warmup"])
        if window == "development":
            ds, start = full.head(split), warmup
        elif window == "holdout":
            ds, start = full, split
        else:
            raise StudyError("window is 'development' or 'holdout'")
        ppy = ds.periods_per_year
        entry = {"strategy": frozen["chosen"]["strategy"], "params": frozen["chosen"]["params"]}
        base_costs = engine.Costs.from_dict(self.prereg["engine"]["costs"])
        lag = int(self.prereg["engine"]["lag"])

        def score(**kwargs: Any) -> float:
            return float(stats.sharpe(self._one(self._run(ds, [entry], **kwargs), 0).excess[start:], ppy))

        nominal = score()
        variations = {
            "costs x0": score(costs=base_costs.scaled(0.0)),
            "costs x2": score(costs=base_costs.scaled(2.0)),
            "costs x4": score(costs=base_costs.scaled(4.0)),
            "one more period of delay": score(lag=lag + 1),
        }
        grid = self.grid()
        same = [g for g in grid if g["strategy"] == entry["strategy"]]
        neighbours = stats.sharpe(self._run(ds, same).excess[:, start:], ppy, axis=-1) if len(same) > 1 else np.array([nominal])
        neighbours = neighbours[np.isfinite(neighbours)]
        half = start + (ds.dates.shape[0] - start) // 2
        single = self._one(self._run(ds, [entry]), 0).excess
        halves = [float(stats.sharpe(single[start:half], ppy)), float(stats.sharpe(single[half:], ppy))]
        components = {
            "costs": abs(variations["costs x2"] - nominal),
            "execution delay": abs(variations["one more period of delay"] - nominal),
            "parameter choice": float(neighbours.std(ddof=1)) if neighbours.size > 1 else 0.0,
        }
        out = {
            "study": self.id, "window": window, "nominal": nominal, "variations": variations,
            "parameter_neighbours": {"n": int(neighbours.size), "min": float(neighbours.min()), "max": float(neighbours.max())},
            "halves": halves, "components": components,
            "total": math.sqrt(sum(value * value for value in components.values())),
            "data": ds.fingerprint(), "code": code_fingerprint(),
        }
        store.write_json_atomic(self.dir / "systematics-{0}.json".format(window), out)
        return out

    # --------------------------------------------------------------- curves
    def curves(self, dataset: Dataset) -> Dict[str, Any]:
        """NAV paths of the frozen configuration and the benchmark, for a figure.

        Before the unblinding this returns the development window only: a
        picture of the holdout is a look at the holdout.
        """
        frozen = self.frozen
        if frozen is None:
            raise StudyError("freeze before drawing curves")
        full = self._registered_data(dataset)
        split = int(self.prereg["development"]["periods"])
        ds = full if self.result is not None else full.head(split)
        warmup = int(self.prereg["engine"]["warmup"])
        entry = {"strategy": frozen["chosen"]["strategy"], "params": frozen["chosen"]["params"]}
        strategy = self._one(self._run(ds, [entry]), 0)
        benchmark = self._benchmark(ds, warmup)
        scored = slice(warmup, None)
        return {
            "dates": ds.dates[scored],
            "strategy": np.cumprod(1.0 + strategy.net[scored]),
            "benchmark": np.cumprod(1.0 + benchmark.net[scored]),
            "cash": np.cumprod(1.0 + ds.rf[scored]),
            "strategy_drawdown": stats.drawdown_curve(strategy.net[scored]),
            "benchmark_drawdown": stats.drawdown_curve(benchmark.net[scored]),
            "holdout_start": ds.dates[split] if self.result is not None else None,
            "unblinded": self.result is not None,
        }

    # ------------------------------------------------------------ standing
    def standing(self, dataset: Optional[Dataset] = None) -> Tuple[str, List[str]]:
        """holds, stale, fails or unknown: does this study's latest record still stand?"""
        reasons: List[str] = []
        ok, detail = self.trials.verify()
        if not ok:
            return "fails", ["trial log: " + detail]
        if not store.seal_holds(self.prereg):
            return "fails", ["the registration was edited after it was sealed"]
        logged = {entry.get("seal") for entry in self.trials.read() if entry.get("seal")}
        if self.prereg["seal"] not in logged:
            return "fails", ["the registration on file is not the one in the trial log"]
        latest = self.prereg
        for name in ("frozen", "result"):
            record = store.read_json(self.dir / (name + ".json"))
            if record is None:
                continue
            if not store.seal_holds(record):
                return "fails", ["{0}.json was edited after it was sealed".format(name)]
            if record["seal"] not in logged:
                return "fails", ["{0}.json is not the record in the trial log".format(name)]
            latest = record
        if latest.get("code") != code_fingerprint():
            reasons.append("the code that computes results changed since this was computed")
        if dataset is None:
            if reasons:
                return "stale", reasons
            return "unknown", ["the data was not supplied, so it could not be compared"]
        try:
            self._registered_data(dataset)
        except StudyError as error:
            reasons.append(str(error))
        return ("stale", reasons) if reasons else ("holds", [])
