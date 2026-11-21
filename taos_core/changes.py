"""Registered changes: say what a change will do before making it, then score it.

A change to the system is an experiment. Before it is made, a record names the
cost it targets (with a unit and a baseline), the predicted effect as a range,
a control that must not move, a canary and a rollback. Sealing freezes that
record by hash. After the window, a grader who is not the builder scores the
prediction, and the verdict is kept whether or not it flatters the change.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from . import _science as sci
from . import events as events_mod
from .paths import Paths
from .store import append_jsonl, canonical_json, locked, read_jsonl, sha256_text, utc_now
from .util import TaosError, short_id

SEALED_FIELDS = ("title", "builder", "target", "prediction", "control", "canary", "rollback")
VERDICTS = ("CONFIRMED", "REFUTED", "CONTROL_MOVED")


def _digest(change: Dict[str, Any]) -> str:
    return sha256_text(canonical_json({key: change[key] for key in SEALED_FIELDS}))


def all_changes(paths: Paths) -> List[Dict[str, Any]]:
    return list(sci.load(paths, "changes", "changes")["changes"])


def register_change(
    paths: Paths,
    *,
    title: str,
    builder: str,
    cost: str,
    unit: str,
    baseline: float,
    predict_low: float,
    predict_high: float,
    control: str,
    control_baseline: float,
    control_tolerance: float,
    canary: str,
    rollback: str,
) -> Dict[str, Any]:
    if predict_low > predict_high:
        raise TaosError("the predicted range must run low to high")
    if control_tolerance < 0:
        raise TaosError("the control tolerance cannot be negative")
    change = {
        "id": short_id("chg_"),
        "title": sci.need(title, "a title"),
        "builder": builder,
        "target": {"cost": sci.need(cost, "the cost this change targets"), "unit": sci.need(unit, "a unit"),
                   "baseline": float(baseline)},
        "prediction": {"low": float(predict_low), "high": float(predict_high)},
        "control": {"name": sci.need(control, "a control that must not move"), "baseline": float(control_baseline),
                    "tolerance": float(control_tolerance)},
        "canary": sci.need(canary, "a canary"),
        "rollback": sci.need(rollback, "a rollback rule"),
        "status": "draft",
        "registered_at": utc_now(),
        "seal": None,
        "score": None,
    }
    with locked(paths):
        data = sci.load(paths, "changes", "changes")
        data["changes"].append(change)
        sci.save(paths, "changes", data)
        events_mod.emit(paths, "change_register", builder, change_id=change["id"], title=change["title"])
    return change


def seal(paths: Paths, change_id: str, agent: str) -> Dict[str, Any]:
    """Freeze the record. Nothing in SEALED_FIELDS may change after this."""
    with locked(paths):
        data = sci.load(paths, "changes", "changes")
        change = sci.find(data["changes"], change_id, "change")
        if change["status"] != "draft":
            raise TaosError("{0} is already {1}".format(change_id, change["status"]))
        change["seal"] = {"sha256": _digest(change), "sealed_at": utc_now(), "sealed_by": agent}
        change["status"] = "sealed"
        sci.save(paths, "changes", data)
        events_mod.emit(paths, "change_seal", agent, change_id=change_id, sha256=change["seal"]["sha256"])
    return change


def receipt(paths: Paths, change_id: str, agent: str, value: float, note: Optional[str] = None) -> Dict[str, Any]:
    """One row per use of the changed mechanism, so its effect is counted, not estimated."""
    change = sci.find(all_changes(paths), change_id, "change")
    if change["status"] == "draft":
        raise TaosError("seal {0} before it writes receipts".format(change_id))
    row = {"ts": utc_now(), "change_id": change_id, "agent": agent, "value": float(value), "note": note}
    append_jsonl(sci.science_dir(paths) / "change_receipts.jsonl", row)
    return row


def receipts(paths: Paths, change_id: str) -> List[Dict[str, Any]]:
    rows = read_jsonl(sci.science_dir(paths) / "change_receipts.jsonl")
    return [row for row in rows if row.get("change_id") == change_id]


def score(
    paths: Paths, change_id: str, *, grader: str, observed: float, control_observed: float, note: Optional[str] = None
) -> Dict[str, Any]:
    with locked(paths):
        data = sci.load(paths, "changes", "changes")
        change = sci.find(data["changes"], change_id, "change")
        if change["status"] != "sealed":
            raise TaosError("{0} is {1}; only a sealed change can be scored".format(change_id, change["status"]))
        if grader == change["builder"]:
            raise TaosError("the builder does not grade its own change; ask another agent or the human")
        if _digest(change) != change["seal"]["sha256"]:
            raise TaosError("{0} no longer matches its seal; the record was edited after sealing".format(change_id))
        control = change["control"]
        prediction = change["prediction"]
        control_held = abs(float(control_observed) - control["baseline"]) <= control["tolerance"]
        in_range = prediction["low"] <= float(observed) <= prediction["high"]
        verdict = "CONTROL_MOVED" if not control_held else ("CONFIRMED" if in_range else "REFUTED")
        change["score"] = {
            "verdict": verdict,
            "observed": float(observed),
            "control_observed": float(control_observed),
            "receipts": len(receipts(paths, change_id)),
            "grader": grader,
            "scored_at": utc_now(),
            "note": note,
        }
        change["status"] = "scored"
        sci.save(paths, "changes", data)
        events_mod.emit(paths, "change_score", grader, change_id=change_id, verdict=verdict)
    return change


def track_record(paths: Paths) -> Dict[str, int]:
    """How often predictions held. The method is scored too."""
    tally = {verdict: 0 for verdict in VERDICTS}
    tally.update({"draft": 0, "sealed": 0})
    for change in all_changes(paths):
        if change["status"] == "scored":
            tally[change["score"]["verdict"]] += 1
        else:
            tally[change["status"]] += 1
    return tally


# --------------------------------------------------------------------------


def _cmd_register(args: argparse.Namespace, paths: Paths) -> int:
    change = register_change(
        paths, title=args.title, builder=args.agent, cost=args.cost, unit=args.unit, baseline=args.baseline,
        predict_low=args.predict[0], predict_high=args.predict[1], control=args.control,
        control_baseline=args.control_baseline, control_tolerance=args.control_tolerance,
        canary=args.canary, rollback=args.rollback,
    )
    print("registered {0}. Seal it before you build: taos change seal {0} --agent {1}".format(change["id"], args.agent))
    return 0


def _cmd_seal(args: argparse.Namespace, paths: Paths) -> int:
    change = seal(paths, args.change_id, args.agent)
    print("sealed {0}  sha256 {1}".format(change["id"], change["seal"]["sha256"]))
    return 0


def _cmd_receipt(args: argparse.Namespace, paths: Paths) -> int:
    receipt(paths, args.change_id, args.agent, args.value, args.note)
    print("receipt {0} for {1}".format(len(receipts(paths, args.change_id)), args.change_id))
    return 0


def _cmd_score(args: argparse.Namespace, paths: Paths) -> int:
    change = score(paths, args.change_id, grader=args.grader, observed=args.observed,
                   control_observed=args.control_observed, note=args.note)
    result = change["score"]
    print("{0}: {1}. Predicted {2} to {3} {4}, observed {5}.".format(
        change["id"], result["verdict"], change["prediction"]["low"], change["prediction"]["high"],
        change["target"]["unit"], result["observed"]))
    return 0


def _cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    items = all_changes(paths)
    if args.json:
        print(json.dumps({"changes": items, "track_record": track_record(paths)}, indent=2, sort_keys=True))
        return 0
    if not items:
        print("no registered changes")
        return 0
    for change in items:
        state = change["score"]["verdict"] if change["score"] else change["status"]
        print("{0}  {1:<13}  {2}".format(change["id"], state, change["title"]))
    record = track_record(paths)
    print("predictions: {0} confirmed, {1} refuted, {2} moved their control".format(
        record["CONFIRMED"], record["REFUTED"], record["CONTROL_MOVED"]))
    return 0


def register(subparsers: Any) -> None:
    change = subparsers.add_parser("change", help="register, seal and score a change to the system")
    sub = change.add_subparsers(dest="change_cmd", required=True)
    agents = list(events_mod.AGENTS)

    reg = sub.add_parser("register", help="write the prediction down before the change")
    reg.add_argument("--agent", required=True, choices=agents, help="the builder")
    reg.add_argument("--title", required=True)
    reg.add_argument("--cost", required=True, help="the cost this change targets")
    reg.add_argument("--unit", required=True)
    reg.add_argument("--baseline", required=True, type=float)
    reg.add_argument("--predict", required=True, type=float, nargs=2, metavar=("LOW", "HIGH"))
    reg.add_argument("--control", required=True, help="a quantity that must not move")
    reg.add_argument("--control-baseline", required=True, type=float)
    reg.add_argument("--control-tolerance", required=True, type=float)
    reg.add_argument("--canary", required=True)
    reg.add_argument("--rollback", required=True)
    reg.set_defaults(func=_cmd_register)

    sealer = sub.add_parser("seal", help="freeze the record by hash")
    sealer.add_argument("change_id")
    sealer.add_argument("--agent", required=True, choices=agents)
    sealer.set_defaults(func=_cmd_seal)

    rec = sub.add_parser("receipt", help="one row per use of the changed mechanism")
    rec.add_argument("change_id")
    rec.add_argument("--agent", required=True, choices=agents)
    rec.add_argument("--value", required=True, type=float)
    rec.add_argument("--note")
    rec.set_defaults(func=_cmd_receipt)

    scorer = sub.add_parser("score", help="grade the prediction; the builder may not grade")
    scorer.add_argument("change_id")
    scorer.add_argument("--grader", required=True, choices=agents)
    scorer.add_argument("--observed", required=True, type=float)
    scorer.add_argument("--control-observed", required=True, type=float)
    scorer.add_argument("--note")
    scorer.set_defaults(func=_cmd_score)

    lister = sub.add_parser("list", help="every change and how the predictions have held")
    lister.add_argument("--json", action="store_true")
    lister.set_defaults(func=_cmd_list)
