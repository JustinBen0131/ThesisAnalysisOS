"""The residual control law: bounded, replayable policy improvement.

Every task episode is an experiment. `start` records the compact state A and
the allocation envelope recommended for it; `finish` records state B and the
raw outcome vector. From the append-only event log, this module derives
per-class statistics, recommends an allocation profile with a deterministic
exploration bonus, and moves a handful of bounded parameters. Nothing here
can touch a hard stop: the admissible action set is fixed by policy; the
controller only chooses within it.

Canonical evidence: `control_open` / `control_close` rows in events.jsonl.
Derived state: `.taos/projections/control.json`, rebuilt from those rows by
`taos control rebuild` and, for determinism, by every close as well.
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any, Dict, List, Optional, Tuple

from . import config as config_mod
from . import events as events_mod
from .paths import Paths
from .store import age_hours, atomic_write_json, parse_ts, read_json, sha256_text, utc_now
from .util import TaosError, slugify

CONTROL_VERSION = 1
STATE_SCHEMA = "TAOS_CONTROL_STATE_V1"

# The action space. Coarse, provider-neutral, ordered from lightest to heaviest.
PROFILES: Dict[str, Dict[str, str]] = {
    "lean": {"compute": "economical", "reasoning": "light", "verification": "normal", "context": "narrow"},
    "balanced": {"compute": "balanced", "reasoning": "normal", "verification": "normal", "context": "normal"},
    "careful": {"compute": "balanced", "reasoning": "normal", "verification": "strong", "context": "normal"},
    "frontier": {"compute": "frontier", "reasoning": "deep", "verification": "strong", "context": "expanded"},
}
PROFILE_ORDER = ("careful", "balanced", "lean", "frontier")  # deterministic tie-break
LIGHTNESS = {"lean": 0, "balanced": 1, "careful": 1, "frontier": 2}
STRONG_VERIFY = {"lean": 0, "balanced": 0, "careful": 1, "frontier": 1}

PARAM_BOUNDS = {
    "beta": (0.1, 1.0),
    "compute_bias": (-0.5, 0.5),
    "verify_bias": (0.0, 0.5),
}
PROGRESS = {"done": 1.0, "review": 0.8, "waiting": 0.3, "next": 0.3, "active": 0.2, "blocked": 0.0, "canceled": 0.0}


# --------------------------------------------------------------------------
# Config and state
# --------------------------------------------------------------------------


def settings(paths: Paths) -> Dict[str, Any]:
    values = dict(config_mod.DEFAULTS["control"])
    provided = config_mod.load_soft(paths).get("control")
    if isinstance(provided, dict):
        values.update({k: v for k, v in provided.items() if v is not None})
    return values


def _state_path(paths: Paths):
    return paths.projections_dir / "control.json"


def priors_from_answers(paths: Paths) -> Dict[str, float]:
    """The human's resource envelope and preference seed the parameters. Priors, not truths."""
    config = config_mod.load_soft(paths)
    preference = config.get("preference") if isinstance(config.get("preference"), dict) else {}
    resources = config.get("resources") if isinstance(config.get("resources"), dict) else {}
    beta = {"conservative": 0.25, "balanced": 0.5, "exploratory": 0.8}.get(str(preference.get("exploration") or "balanced"), 0.5)
    compute_bias = {"constrained": -0.1, "normal": 0.0, "abundant": 0.1}.get(str(resources.get("compute") or "normal"), 0.0)
    return {"beta": beta, "compute_bias": compute_bias, "verify_bias": 0.0}


def empty_state(paths: Paths) -> Dict[str, Any]:
    cfg = settings(paths)
    seeded = priors_from_answers(paths)
    if "beta" in (config_mod.load_soft(paths).get("control") or {}):
        seeded["beta"] = float(cfg["beta"])
    return {
        "schema": STATE_SCHEMA,
        "control_version": CONTROL_VERSION,
        "generated_at": utc_now(),
        "params": {k: _clamp(k, v) for k, v in seeded.items()},
        "classes": {},          # klass -> {n, clean, profiles: {profile -> {n, sum_j, sum_progress, sum_cost, recent: [...]}}}
        "open": {},             # episode_id -> open row (unclosed)
        "episodes": 0,
        "malformed": 0,
        "last_event_id": None,
        "history": [],          # bounded list of parameter movements
    }


def _clamp(name: str, value: float) -> float:
    low, high = PARAM_BOUNDS[name]
    return max(low, min(high, round(value, 4)))


# --------------------------------------------------------------------------
# Observable state and outcome vector
# --------------------------------------------------------------------------


def task_class(task: Dict[str, Any]) -> str:
    labels = task.get("labels") or []
    if labels:
        return slugify(str(labels[0]), 30)
    words = [w for w in slugify(task.get("title", ""), 60).split("-") if len(w) > 3]
    return words[0] if words else "general"


def observe_state(paths: Paths, task: Dict[str, Any], blockers: List[str]) -> Dict[str, Any]:
    from . import handoff as handoff_mod

    return {
        "klass": task_class(task),
        "priority": task.get("priority", "P2"),
        "has_blockers": bool(blockers),
        "has_prior_handoff": handoff_mod.latest(paths, task["id"]) is not None,
        "gates_configured": bool(config_mod.gates(paths)),
        "evidence_count": len(task.get("evidence") or []),
        "status": task.get("status"),
    }


def outcome_vector(paths: Paths, task: Dict[str, Any], opened_at: str, closed_at: str) -> Dict[str, Any]:
    """Only what TAOS can actually observe. Everything else stays null."""
    since = parse_ts(opened_at)
    gate_pass = gate_fail = decisions = handoffs = corrections = blockers = 0
    for row in events_mod.read(paths, since=opened_at):
        if row.get("task_id") not in (task["id"], None) and row.get("type") not in ("label",):
            continue
        kind = row.get("type")
        if kind == "gate_run" and row.get("task_id") == task["id"]:
            if row.get("ok"):
                gate_pass += 1
            else:
                gate_fail += 1
        elif kind == "decision_ask" and row.get("task_id") == task["id"]:
            decisions += 1
        elif kind == "handoff_write" and row.get("task_id") == task["id"]:
            handoffs += 1
        elif kind == "task_transition" and row.get("task_id") == task["id"] and row.get("to_state") == "blocked":
            blockers += 1
    try:
        from . import telemetry as telemetry_mod

        for row in telemetry_mod.rows(paths):
            if parse_ts(row.get("ts", closed_at)) >= since and row.get("outcome") in ("corrected", "reworked"):
                corrections += 1
    except Exception:
        pass
    wall = max(0.0, (parse_ts(closed_at) - since).total_seconds())
    vector: Dict[str, Any] = {
        "terminal": task.get("status"),
        "wall_seconds": round(wall, 1),
        "gate_pass": gate_pass,
        "gate_fail": gate_fail,
        "decisions": decisions,
        "handoffs": handoffs,
        "blockers": blockers,
        "corrections": corrections,
        "evidence": len(task.get("evidence") or []),
        "input_tokens": None,
        "cached_tokens": None,
        "cache_write_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
        "cost": None,
        "model": None,
        "retries": None,
        "reuse": None,
        "controller_seconds": None,
        "provenance": dict(PROVENANCE),
    }

    # Both hosts write token usage to disk. Read it if it is there; stay null if not.
    try:
        from . import usage as usage_mod

        observed = usage_mod.window(paths, since=opened_at, until=closed_at, scoped=True)
        agents = observed.get("agents") or {}
        if agents:
            totals = dict(usage_mod.ZERO)
            models: Dict[str, int] = {}
            cost_amount = 0.0
            cost_seen = False
            for data in agents.values():
                for key, value in data["totals"].items():
                    totals[key] = totals.get(key, 0) + value
                for name, count in (data.get("models") or {}).items():
                    models[name] = models.get(name, 0) + count
                if data.get("cost"):
                    cost_amount += float(data["cost"]["amount"])
                    cost_seen = True
            vector.update({
                "input_tokens": totals["input_tokens"],
                "cached_tokens": totals["cached_tokens"],
                "cache_write_tokens": totals["cache_write_tokens"],
                "output_tokens": totals["output_tokens"],
                # Reported by Codex and already inside output_tokens: never added again.
                "reasoning_tokens": totals["reasoning_tokens"] or None,
                "model": max(models.items(), key=lambda item: item[1])[0] if models else None,
                "cost": round(cost_amount, 4) if cost_seen else None,
            })
            for field in ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "model"):
                vector["provenance"][field] = "observed"
            if vector["reasoning_tokens"] is not None:
                vector["provenance"]["reasoning_tokens"] = "observed"
            if cost_seen:
                vector["provenance"]["cost"] = "estimated"
            # Coarse by construction: a concurrent session in the same window and
            # scope is counted here too. Say so rather than implying exactness.
            vector["token_attribution"] = observed.get("attribution")
    except Exception:
        pass   # a host that changed its format must never break a close
    return vector


def utility(vector: Dict[str, Any], lam: float = 0.0) -> Tuple[float, float, float]:
    """One-step scalar u - resource_cost. Returns (J, progress, cost).

    Reuse and other future value are NOT added here: they belong to the
    continuation value of the successor state, which this version does not
    yet estimate. Adding them as a separate term would double count once it
    does. `lam` is accepted for config compatibility and unused.
    """
    progress = float(PROGRESS.get(str(vector.get("terminal")), 0.3))
    wall = float(vector.get("wall_seconds") or 0.0)
    cost = (
        min(1.0, wall / 3600.0) * 0.2
        + int(vector.get("gate_fail") or 0) * 0.15
        + int(vector.get("decisions") or 0) * 0.05
        + int(vector.get("handoffs") or 0) * 0.05
        + int(vector.get("corrections") or 0) * 0.2
        + int(vector.get("blockers") or 0) * 0.1
        + min(1.0, float(vector.get("controller_seconds") or 0.0) / 60.0) * 0.05
    )
    return (round(progress - cost, 4), progress, round(cost, 4))


PROVENANCE = {
    "terminal": "observed", "wall_seconds": "observed", "gate_pass": "observed", "gate_fail": "observed",
    "decisions": "observed", "handoffs": "observed", "blockers": "observed", "corrections": "observed",
    "evidence": "observed", "controller_seconds": "observed",
    # Filled by the host adapters when this machine writes them; null otherwise.
    "input_tokens": "unavailable", "cached_tokens": "unavailable", "cache_write_tokens": "unavailable",
    "output_tokens": "unavailable", "reasoning_tokens": "unavailable", "model": "unavailable",
    "cost": "unavailable", "retries": "unavailable", "reuse": "unavailable",
}


def is_clean(vector: Dict[str, Any]) -> bool:
    return (
        str(vector.get("terminal")) in ("done", "review")
        and int(vector.get("gate_fail") or 0) == 0
        and int(vector.get("corrections") or 0) == 0
    )


# --------------------------------------------------------------------------
# Recommendation
# --------------------------------------------------------------------------


def _priors(gates_configured: bool) -> Dict[str, float]:
    return {"lean": 0.5, "balanced": 0.6, "careful": 0.65 if gates_configured else 0.55, "frontier": 0.55}


def recommend(state: Dict[str, Any], z: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic: same state, same z, same config -> same answer."""
    klass = z.get("klass", "general")
    klass_stats = state["classes"].get(klass, {"n": 0, "clean": 0, "profiles": {}})
    n_klass = int(klass_stats.get("n", 0))
    params = state["params"]
    beta = float(params["beta"])
    priors = _priors(bool(z.get("gates_configured")))
    min_evidence = int(cfg["min_evidence"])

    # After a failing window, recover on the proven route before probing again:
    # the exploration bonus is quartered until the class is stable.
    recent = klass_stats.get("recent", [])[-min_evidence:]
    unstable = len(recent) >= min_evidence and sum(1 for c in recent if not c) * 2 >= len(recent)
    bonus_scale = 0.25 if unstable else 1.0

    scored = []
    for profile in PROFILE_ORDER:
        stats = klass_stats.get("profiles", {}).get(profile, {"n": 0, "sum_j": 0.0})
        n_profile = int(stats.get("n", 0))
        mean_j = (float(stats["sum_j"]) / n_profile) if n_profile else priors[profile]
        bonus = bonus_scale * beta * math.sqrt(math.log(1.0 + n_klass) / (1.0 + n_profile)) if n_klass else 0.0
        # negative compute_bias favours lighter profiles, positive favours heavier
        bias = float(params["compute_bias"]) * (LIGHTNESS[profile] - 1) + float(params["verify_bias"]) * STRONG_VERIFY[profile]
        if z.get("has_blockers") or z.get("has_prior_handoff"):
            bias += 0.05 * STRONG_VERIFY[profile]
        scored.append((round(mean_j + bonus + bias, 6), profile, {"n": n_profile, "mean_j": round(mean_j, 4), "bonus": round(bonus, 4), "bias": round(bias, 4)}))
    scored.sort(key=lambda item: (-item[0], PROFILE_ORDER.index(item[1])))
    best_score, best, detail = scored[0]
    probe = detail["n"] < min_evidence and n_klass >= min_evidence
    clean_rate = (int(klass_stats.get("clean", 0)) / n_klass) if n_klass else None
    return {
        "profile": best,
        "bands": dict(PROFILES[best], exploration="probe" if probe else "exploit",
                      decomposition="decompose" if z.get("priority") == "P0" and not z.get("has_prior_handoff") else "direct",
                      handoff="consider" if z.get("has_blockers") else "stay"),
        "score": best_score,
        "basis": {"klass": klass, "n_klass": n_klass, "clean_rate": None if clean_rate is None else round(clean_rate, 3),
                  "candidates": [{"profile": p, "score": s, **d} for s, p, d in scored], "params": dict(params)},
    }


def control_line(rec: Dict[str, Any]) -> str:
    bands = rec["bands"]
    basis = rec["basis"]
    if basis["n_klass"]:
        evidence = "{0} comparable, {1:.0%} clean".format(basis["n_klass"], basis["clean_rate"] or 0.0)
    else:
        evidence = "no comparable history, conservative baseline"
    return "control:   {0} | {1} compute, {2} reasoning, {3} verify | {4} | basis: {5}".format(
        rec["profile"], bands["compute"], bands["reasoning"], bands["verification"], bands["exploration"], evidence
    )


# --------------------------------------------------------------------------
# Episodes (events are canonical)
# --------------------------------------------------------------------------


def load_state(paths: Paths) -> Dict[str, Any]:
    data = read_json(_state_path(paths))
    if not isinstance(data, dict) or data.get("schema") != STATE_SCHEMA:
        return rebuild(paths, write=True)
    return data


def open_episode(paths: Paths, task: Dict[str, Any], blockers: List[str], agent: str) -> Optional[Dict[str, Any]]:
    cfg = settings(paths)
    if not cfg.get("enabled", True):
        return None
    state = load_state(paths)
    z = observe_state(paths, task, blockers)
    rec = recommend(state, z, cfg)
    observed = cfg.get("observed_profile") if cfg.get("observed_profile") in PROFILES else None
    episode_id = "ep_" + sha256_text(task["id"] + "|" + utc_now() + "|" + agent)[:10]
    events_mod.emit(
        paths, "control_open", agent,
        episode_id=episode_id, task_id=task["id"], z=z,
        recommended=rec["profile"], bands=rec["bands"], observed=observed,
        evidence_kind="probe" if rec["bands"]["exploration"] == "probe" else "observational",
        params=dict(state["params"]), control_version=CONTROL_VERSION,
    )
    rebuild(paths, write=True)
    rec["episode_id"] = episode_id
    rec["observed"] = observed
    return rec


def close_episode(paths: Paths, task: Dict[str, Any], agent: str) -> Optional[Dict[str, Any]]:
    cfg = settings(paths)
    if not cfg.get("enabled", True):
        return None
    state = load_state(paths)
    open_rows = [row for row in state["open"].values() if row.get("task_id") == task["id"]]
    if not open_rows:
        return None
    open_row = sorted(open_rows, key=lambda r: r.get("ts", ""))[-1]
    closed_at = utc_now()
    vector = outcome_vector(paths, task, open_row["ts"], closed_at)
    # The controller pays for itself: the last rebuild's cost is charged to this episode.
    vector["controller_seconds"] = float(state.get("overhead_seconds") or 0.0)
    j, progress, cost = utility(vector)
    events_mod.emit(
        paths, "control_close", agent,
        episode_id=open_row["episode_id"], task_id=task["id"], klass=open_row["z"]["klass"],
        profile=open_row.get("observed") or open_row["recommended"], observed=bool(open_row.get("observed")),
        evidence_kind=open_row.get("evidence_kind", "observational"),
        vector=vector, j=j, progress=progress, cost=cost, clean=is_clean(vector),
        control_version=CONTROL_VERSION,
    )
    new_state = rebuild(paths, write=True)
    return {"episode_id": open_row["episode_id"], "j": j, "clean": is_clean(vector), "params": new_state["params"], "vector": vector}


# --------------------------------------------------------------------------
# Replay: the only way state is produced
# --------------------------------------------------------------------------


def _valid_open(row: Dict[str, Any]) -> bool:
    return isinstance(row.get("z"), dict) and row.get("recommended") in PROFILES and isinstance(row.get("episode_id"), str)


def _valid_close(row: Dict[str, Any]) -> bool:
    return (
        isinstance(row.get("vector"), dict) and row.get("profile") in PROFILES
        and isinstance(row.get("j"), (int, float)) and isinstance(row.get("episode_id"), str)
        and isinstance(row.get("klass"), str)
    )


def _tune(state: Dict[str, Any], klass_stats: Dict[str, Any], cfg: Dict[str, Any], event_id: str) -> None:
    """Bounded, deterministic parameter movement from the last min_evidence outcomes."""
    min_evidence = int(cfg["min_evidence"])
    step = float(cfg["step"])
    recent = klass_stats.get("recent", [])[-min_evidence:]
    if len(recent) < min_evidence:
        return
    before = dict(state["params"])
    fails = sum(1 for clean in recent if not clean)
    if fails == 0:
        # lightness is earned slowly
        state["params"]["compute_bias"] = _clamp("compute_bias", state["params"]["compute_bias"] - step)
        state["params"]["verify_bias"] = _clamp("verify_bias", state["params"]["verify_bias"] - step / 2)
    elif fails * 2 >= len(recent):
        # caution is cheap and failure is expensive: a failing window cancels any
        # accumulated lightness at once, then adds one step of caution
        state["params"]["compute_bias"] = _clamp("compute_bias", max(0.0, state["params"]["compute_bias"]) + step)
        state["params"]["verify_bias"] = _clamp("verify_bias", state["params"]["verify_bias"] + step)
    total = int(state["episodes"])
    beta0 = float(priors_from_answers_cached(cfg))
    state["params"]["beta"] = _clamp("beta", beta0 / math.sqrt(1.0 + total / 10.0))
    if before != state["params"]:
        state["history"].append({"event_id": event_id, "from": before, "to": dict(state["params"]), "recent_fails": fails})
        state["history"] = state["history"][-50:]


def priors_from_answers_cached(cfg: Dict[str, Any]) -> float:
    return float(cfg.get("_beta0", cfg.get("beta", 0.5)))


def rebuild(paths: Paths, write: bool = False) -> Dict[str, Any]:
    import time as _time

    started = _time.perf_counter()
    cfg = settings(paths)
    state = empty_state(paths)
    cfg["_beta0"] = state["params"]["beta"]
    for row in events_mod.read(paths, types=["control_open", "control_close"]):
        kind = row.get("type")
        if kind == "control_open":
            if not _valid_open(row):
                state["malformed"] += 1
                continue
            state["open"][row["episode_id"]] = row
        elif kind == "control_close":
            if not _valid_close(row) or row["episode_id"] not in state["open"]:
                state["malformed"] += 1
                continue
            state["open"].pop(row["episode_id"], None)
            klass = state["classes"].setdefault(row["klass"], {"n": 0, "clean": 0, "profiles": {}, "recent": []})
            prof = klass["profiles"].setdefault(row["profile"], {"n": 0, "sum_j": 0.0, "sum_progress": 0.0, "sum_cost": 0.0})
            klass["n"] += 1
            klass["clean"] += 1 if row.get("clean") else 0
            klass["recent"] = (klass.get("recent", []) + [bool(row.get("clean"))])[-20:]
            prof["n"] += 1
            prof["sum_j"] = round(prof["sum_j"] + float(row["j"]), 6)
            prof["sum_progress"] = round(prof["sum_progress"] + float(row.get("progress") or 0.0), 6)
            prof["sum_cost"] = round(prof["sum_cost"] + float(row.get("cost") or 0.0), 6)
            klass["comparative"] = int(klass.get("comparative", 0)) + (1 if row.get("evidence_kind") == "probe" else 0)
            state["episodes"] += 1
            _tune(state, klass, cfg, row.get("id", ""))
        state["last_event_id"] = row.get("id")
    state["generated_at"] = utc_now()
    state["overhead_seconds"] = round(_time.perf_counter() - started, 4)
    if write:
        paths.ensure_state()
        atomic_write_json(_state_path(paths), state)
    return state


def check(paths: Paths) -> List[str]:
    """Doctor: derived state agrees with replay, params legal, no malformed growth."""
    problems: List[str] = []
    stored = read_json(_state_path(paths))
    fresh = rebuild(paths, write=False)
    if isinstance(stored, dict):
        if stored.get("schema") != STATE_SCHEMA or stored.get("control_version") != CONTROL_VERSION:
            problems.append("control state schema/version mismatch; run `taos control rebuild`")
        for key in ("params", "classes", "episodes"):
            if stored.get(key) != fresh.get(key):
                problems.append("control state {0} disagrees with replay; run `taos control rebuild`".format(key))
                break
    for name, value in fresh["params"].items():
        low, high = PARAM_BOUNDS[name]
        if not (low <= float(value) <= high):
            problems.append("control parameter {0}={1} outside [{2}, {3}]".format(name, value, low, high))
    if fresh["malformed"]:
        problems.append("{0} malformed control episode(s) ignored".format(fresh["malformed"]))
    return problems


def frontier(state: Dict[str, Any], klass: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = []
    for name, stats in state["classes"].items():
        if klass and name != klass:
            continue
        for profile, prof in stats.get("profiles", {}).items():
            n = int(prof.get("n", 0))
            if not n:
                continue
            rows.append({"klass": name, "profile": profile, "n": n,
                         "progress": round(prof["sum_progress"] / n, 3), "cost": round(prof["sum_cost"] / n, 3)})
    for row in rows:
        row["dominated"] = any(
            o["klass"] == row["klass"] and o is not row
            and o["progress"] >= row["progress"] and o["cost"] <= row["cost"]
            and (o["progress"] > row["progress"] or o["cost"] < row["cost"])
            for o in rows
        )
    return sorted(rows, key=lambda r: (r["klass"], r["dominated"], -r["progress"], r["cost"]))


def status_line(paths: Paths) -> str:
    try:
        state = load_state(paths)
    except TaosError:
        return "Control: unavailable"
    params = state["params"]
    total = state["episodes"]
    clean = sum(int(c.get("clean", 0)) for c in state["classes"].values())
    comparative = sum(int(c.get("comparative", 0)) for c in state["classes"].values())
    return "Control: v{0} | {1} observed episode(s){2}, {3} probe(s) | beta {4:.2f}, compute bias {5:+.2f}, verify bias {6:+.2f}".format(
        CONTROL_VERSION, total, " ({0:.0%} clean)".format(clean / total) if total else "", comparative,
        params["beta"], params["compute_bias"], params["verify_bias"],
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    state = load_state(paths)
    if args.json:
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    print(status_line(paths))
    for klass, stats in sorted(state["classes"].items()):
        print("  {0:<20} n={1} clean={2}".format(klass, stats["n"], stats["clean"]))
        for profile, prof in sorted(stats["profiles"].items()):
            print("    {0:<10} n={1} mean_j={2:.3f}".format(profile, prof["n"], prof["sum_j"] / prof["n"]))
    if state["open"]:
        print("  open episodes: {0}".format(", ".join(r["task_id"] for r in state["open"].values())))
    for move in state["history"][-3:]:
        print("  moved {0} -> {1} (recent fails {2})".format(move["from"], move["to"], move["recent_fails"]))
    return 0


def _cmd_explain(args: argparse.Namespace, paths: Paths) -> int:
    rows = [r for r in events_mod.read(paths, types=["control_open", "control_close"]) if r.get("task_id") == args.task_id]
    if not rows:
        print("no control episodes for {0}".format(args.task_id))
        return 0
    for row in rows[-4:]:
        if row["type"] == "control_open":
            print("{0} open  {1} -> {2} because:".format(row["ts"], row["episode_id"], row["recommended"]))
            print("  state: {0}".format(json.dumps(row["z"], sort_keys=True)))
            print("  params: {0}".format(json.dumps(row.get("params"), sort_keys=True)))
            if row.get("observed"):
                print("  observed (user-set) profile: {0}".format(row["observed"]))
        else:
            print("{0} close {1} j={2} clean={3} vector={4}".format(row["ts"], row["episode_id"], row["j"], row.get("clean"), json.dumps(row["vector"], sort_keys=True)))
    return 0


def _cmd_rebuild(args: argparse.Namespace, paths: Paths) -> int:
    state = rebuild(paths, write=True)
    print("rebuilt from {0} episode(s), {1} malformed ignored".format(state["episodes"], state["malformed"]))
    print(status_line(paths))
    return 0


def _cmd_frontier(args: argparse.Namespace, paths: Paths) -> int:
    rows = frontier(load_state(paths), args.klass)
    if not rows:
        print("no closed episodes yet")
        return 0
    for row in rows:
        print("{0:<20} {1:<10} n={2:<3} progress={3:.2f} cost={4:.2f} {5}".format(
            row["klass"], row["profile"], row["n"], row["progress"], row["cost"], "dominated" if row["dominated"] else "on frontier"))
    return 0


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("control", help="the residual control law: inspect, explain, rebuild")
    sub = parser.add_subparsers(dest="control_cmd", required=True)
    status = sub.add_parser("status", help="parameters and per-class statistics")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=_cmd_status)
    explain = sub.add_parser("explain", help="why a task got its envelope")
    explain.add_argument("task_id")
    explain.set_defaults(func=_cmd_explain)
    rebuild_parser = sub.add_parser("rebuild", help="derive state from the event log")
    rebuild_parser.set_defaults(func=_cmd_rebuild)
    frontier_parser = sub.add_parser("frontier", help="nondominated allocations per class")
    frontier_parser.add_argument("--class", dest="klass")
    frontier_parser.set_defaults(func=_cmd_frontier)
