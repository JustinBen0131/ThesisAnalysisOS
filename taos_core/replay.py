"""Replay before install: size a control against your own history.

A limit set in a scare can cost more than the failure it prevents. Before a
control that acts on every lane is installed, replay it on recorded history
and read two numbers: the harmful cases it would have caught, and the times
it would have fired on ordinary work.

History is a JSONL file, one row per past case, with a measured value and a
flag saying whether that case did harm.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from .paths import Paths
from .store import read_jsonl
from .util import TaosError

OPS = ("at-least", "at-most")


def replay(rows: List[Dict[str, Any]], *, field: str, op: str, threshold: float, harmful_field: str = "harmful") -> Dict[str, Any]:
    if op not in OPS:
        raise TaosError("op must be one of: {0}".format(", ".join(OPS)))
    harmful = harmless = caught = needless = unreadable = 0
    for row in rows:
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            unreadable += 1
            continue
        fires = value >= threshold if op == "at-least" else value <= threshold
        if bool(row.get(harmful_field)):
            harmful += 1
            caught += int(fires)
        else:
            harmless += 1
            needless += int(fires)
    return {"field": field, "op": op, "threshold": float(threshold), "harmful": harmful, "harmless": harmless,
            "caught": caught, "missed": harmful - caught, "needless": needless, "unreadable": unreadable}


def sweep(rows: List[Dict[str, Any]], *, field: str, op: str, thresholds: List[float], harmful_field: str = "harmful") -> List[Dict[str, Any]]:
    return [replay(rows, field=field, op=op, threshold=value, harmful_field=harmful_field) for value in thresholds]


def sentence(result: Dict[str, Any]) -> str:
    return "{0} {1} {2}: would have caught {3} of {4} harmful cases, and fired on {5} of {6} harmless ones".format(
        result["field"], result["op"].replace("-", " "), result["threshold"], result["caught"], result["harmful"],
        result["needless"], result["harmless"])


# --------------------------------------------------------------------------


def _cmd_replay(args: argparse.Namespace, paths: Paths) -> int:
    history = Path(args.history).expanduser()
    if not history.is_file():
        raise TaosError("no history file at {0}".format(history))
    rows = read_jsonl(history)
    thresholds = [float(value) for value in args.threshold]
    results = sweep(rows, field=args.field, op=args.op, thresholds=thresholds, harmful_field=args.harmful_field)
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    for result in results:
        print(sentence(result))
    if results and results[0]["unreadable"]:
        print("note: {0} rows had no numeric {1} and were skipped".format(results[0]["unreadable"], args.field))
    return 0


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("replay", help="replay a proposed control on history before installing it")
    parser.add_argument("--history", required=True, help="JSONL file, one past case per row")
    parser.add_argument("--field", required=True, help="the measured value the control reads")
    parser.add_argument("--op", default="at-least", choices=list(OPS))
    parser.add_argument("--threshold", required=True, action="append", help="repeat to compare several limits")
    parser.add_argument("--harmful-field", default="harmful")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=_cmd_replay)
