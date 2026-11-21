"""Two anchors: no adjustment because a number looks wrong, or right.

A diagnostic that lands on a pleasing value is not evidence for the treatment
that put it there. Before a treatment changes, or an anomaly is called
resolved, an adjustment needs two anchors and a prediction:

  method anchor   what the validated reference method does with this effect
  control anchor  what the same quantity reads where nothing is in question
  prediction      the range the quantity should land in, written beforehand

`resolve` is refused until all three exist, and it records whether the result
fell inside the prediction.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from . import _science as sci
from . import events as events_mod
from .paths import Paths
from .store import locked, utc_now
from .util import TaosError, short_id


def all_adjustments(paths: Paths) -> List[Dict[str, Any]]:
    return list(sci.load(paths, "anchors", "adjustments")["adjustments"])


def open_adjustment(paths: Paths, *, quantity: str, observed: float, proposed: str, agent: str,
                    task_id: Optional[str] = None) -> Dict[str, Any]:
    adjustment = {"id": short_id("adj_"), "task_id": task_id, "quantity": sci.need(quantity, "the quantity"),
                  "observed": float(observed), "proposed": sci.need(proposed, "the proposed treatment"),
                  "opened_by": agent, "opened_at": utc_now(), "method_anchor": None, "control_anchor": None,
                  "prediction": None, "status": "open", "resolution": None}
    with locked(paths):
        data = sci.load(paths, "anchors", "adjustments")
        data["adjustments"].append(adjustment)
        sci.save(paths, "anchors", data)
        events_mod.emit(paths, "anchor_open", agent, adjustment_id=adjustment["id"], quantity=adjustment["quantity"])
    return adjustment


def _update(paths: Paths, adjustment_id: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
    with locked(paths):
        data = sci.load(paths, "anchors", "adjustments")
        adjustment = sci.find(data["adjustments"], adjustment_id, "adjustment")
        if adjustment["status"] != "open":
            raise TaosError("{0} is already resolved".format(adjustment_id))
        adjustment[key] = value
        sci.save(paths, "anchors", data)
    return adjustment


def anchor_method(paths: Paths, adjustment_id: str, *, reference: str, says: str) -> Dict[str, Any]:
    return _update(paths, adjustment_id, "method_anchor",
                   {"reference": sci.need(reference, "the reference"), "says": sci.need(says, "what the reference does")})


def anchor_control(paths: Paths, adjustment_id: str, *, where: str, value: float) -> Dict[str, Any]:
    return _update(paths, adjustment_id, "control_anchor",
                   {"where": sci.need(where, "where the control was read"), "value": float(value)})


def predict(paths: Paths, adjustment_id: str, *, low: float, high: float) -> Dict[str, Any]:
    if low > high:
        raise TaosError("the predicted range must run low to high")
    return _update(paths, adjustment_id, "prediction", {"low": float(low), "high": float(high), "made_at": utc_now()})


def missing(adjustment: Dict[str, Any]) -> List[str]:
    names = {"method_anchor": "the method anchor", "control_anchor": "the control anchor", "prediction": "a prediction"}
    return [label for key, label in names.items() if not adjustment.get(key)]


def resolve(paths: Paths, adjustment_id: str, *, after: float, by: str) -> Dict[str, Any]:
    with locked(paths):
        data = sci.load(paths, "anchors", "adjustments")
        adjustment = sci.find(data["adjustments"], adjustment_id, "adjustment")
        if adjustment["status"] != "open":
            raise TaosError("{0} is already resolved".format(adjustment_id))
        gaps = missing(adjustment)
        if gaps:
            raise TaosError("{0} cannot be resolved without {1}".format(adjustment_id, " and ".join(gaps)))
        prediction = adjustment["prediction"]
        adjustment["resolution"] = {"after": float(after), "by": by, "resolved_at": utc_now(),
                                    "within_prediction": prediction["low"] <= float(after) <= prediction["high"]}
        adjustment["status"] = "resolved"
        sci.save(paths, "anchors", data)
        events_mod.emit(paths, "anchor_resolve", by, adjustment_id=adjustment_id,
                        within_prediction=adjustment["resolution"]["within_prediction"])
    return adjustment


# --------------------------------------------------------------------------


def _cmd_open(args: argparse.Namespace, paths: Paths) -> int:
    adjustment = open_adjustment(paths, quantity=args.quantity, observed=args.observed, proposed=args.proposed,
                                 agent=args.agent, task_id=args.task)
    print("opened {0}. It needs a method anchor, a control anchor and a prediction before it can be resolved.".format(
        adjustment["id"]))
    return 0


def _cmd_method(args: argparse.Namespace, paths: Paths) -> int:
    anchor_method(paths, args.adjustment_id, reference=args.reference, says=args.says)
    print("method anchor recorded")
    return 0


def _cmd_control(args: argparse.Namespace, paths: Paths) -> int:
    anchor_control(paths, args.adjustment_id, where=args.where, value=args.value)
    print("control anchor recorded")
    return 0


def _cmd_predict(args: argparse.Namespace, paths: Paths) -> int:
    predict(paths, args.adjustment_id, low=args.range[0], high=args.range[1])
    print("prediction recorded")
    return 0


def _cmd_resolve(args: argparse.Namespace, paths: Paths) -> int:
    adjustment = resolve(paths, args.adjustment_id, after=args.after, by=args.by)
    inside = adjustment["resolution"]["within_prediction"]
    print("{0} resolved; the result fell {1} the prediction".format(adjustment["id"], "inside" if inside else "OUTSIDE"))
    return 0


def _cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    items = all_adjustments(paths)
    if args.json:
        print(json.dumps(items, indent=2, sort_keys=True))
        return 0
    for adjustment in items:
        gaps = missing(adjustment)
        state = adjustment["status"] if not gaps or adjustment["status"] != "open" else "needs " + ", ".join(gaps)
        print("{0}  {1}  [{2}]".format(adjustment["id"], adjustment["quantity"], state))
    if not items:
        print("no adjustments on record")
    return 0


def register(subparsers: Any) -> None:
    anchor = subparsers.add_parser("anchor", help="two anchors and a prediction before any adjustment")
    sub = anchor.add_subparsers(dest="anchor_cmd", required=True)
    agents = list(events_mod.AGENTS)

    opener = sub.add_parser("open", help="record an anomaly and the treatment proposed for it")
    opener.add_argument("--agent", required=True, choices=agents)
    opener.add_argument("--task")
    opener.add_argument("--quantity", required=True)
    opener.add_argument("--observed", required=True, type=float)
    opener.add_argument("--proposed", required=True)
    opener.set_defaults(func=_cmd_open)

    method = sub.add_parser("method", help="what the validated reference method does")
    method.add_argument("adjustment_id")
    method.add_argument("--reference", required=True)
    method.add_argument("--says", required=True)
    method.set_defaults(func=_cmd_method)

    control = sub.add_parser("control", help="the same quantity where nothing is in question")
    control.add_argument("adjustment_id")
    control.add_argument("--where", required=True)
    control.add_argument("--value", required=True, type=float)
    control.set_defaults(func=_cmd_control)

    predictor = sub.add_parser("predict", help="where the quantity should land, written beforehand")
    predictor.add_argument("adjustment_id")
    predictor.add_argument("--range", required=True, type=float, nargs=2, metavar=("LOW", "HIGH"))
    predictor.set_defaults(func=_cmd_predict)

    resolver = sub.add_parser("resolve", help="refused until both anchors and the prediction exist")
    resolver.add_argument("adjustment_id")
    resolver.add_argument("--after", required=True, type=float)
    resolver.add_argument("--by", required=True, choices=agents)
    resolver.set_defaults(func=_cmd_resolve)

    lister = sub.add_parser("list", help="every adjustment and what it still needs")
    lister.add_argument("--json", action="store_true")
    lister.set_defaults(func=_cmd_list)
