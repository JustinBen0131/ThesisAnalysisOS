"""Standing: what a task's recorded results rest on, and whether each still holds.

A closed task is a statement: this work is finished. It was made on a basis:
checks that passed on particular files, the instructions in force that day,
work products built from particular inputs, and sometimes a person accepting
the result. `taos why` reads those records back against the present and
answers in the vocabulary of `basis`: holds, fails, stale, unknown.

    taos why AZ-7     one task, part by part, with the reason for each
    taos why          everything recorded that no longer holds

It only reads. Nothing here changes a task, runs a check or logs a lesson.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import basis
from . import claims as claims_mod
from . import gates as gates_mod
from . import kernels as kernels_mod
from . import rules as rules_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import age_hours, read_json

CLOSED = ("review", "done")
KERNEL_STATES = {"drifted": basis.STALE, "aged": basis.STALE, "missing": basis.UNKNOWN}


def _part(kind: str, name: Any, state: str, reason: str) -> Dict[str, Any]:
    return {"kind": kind, "name": str(name), "state": state, "reason": reason}


def _closure(paths: Paths, task: Dict[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The statement "this is finished": who made it, and whether the instructions it was made under still govern."""
    closure = (task.get("closures") or [None])[-1]
    if closure is None:
        return _part("closure", task["status"], basis.UNKNOWN,
                     "it was closed before closures were recorded, so nothing says what it stood on")
    who = "{0} moved it to {1} on {2}".format(closure.get("by"), closure.get("to"), str(closure.get("ts"))[:10])
    waived = closure.get("waived")
    if waived and any(check["state"] != basis.HOLDS for check in checks):
        return _part("closure", closure.get("to"), basis.UNKNOWN,
                     "{0} without a holding check ({1})".format(who, waived.get("reason")))
    changed = rules_mod.changes_since(paths, task, closure.get("rules") or {})
    if changed:
        return _part("closure", closure.get("to"), basis.STALE,
                     "{0}; the instructions have changed since: {1}".format(who, "; ".join(changed)))
    later = "; it was closed without a check, and the checks have passed since" if waived else ""
    return _part("closure", closure.get("to"), basis.HOLDS, "{0}; the same instructions govern{1}".format(who, later))


def _acceptance(paths: Paths, task: Dict[str, Any], snap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A person's acceptance is of one version. It does not carry over to the next."""
    given = task.get("acceptance")
    if not isinstance(given, dict):
        return None
    who = "{0} accepted it on {1}".format(given.get("by"), str(given.get("ts"))[:10])
    receipt = read_json(paths.state / "acceptance" / str(given["receipt"]), None) if given.get("receipt") else None
    verdict = basis.compare(given.get("basis") or {}, snap, listed=(receipt or {}).get("snapshot"))
    if verdict["state"] != basis.HOLDS:
        return _part("acceptance", given.get("by"), verdict["state"], "{0}; since then {1}".format(who, verdict["reason"]))
    changed = rules_mod.changes_since(paths, task, given.get("rules") or {})
    if changed:
        return _part("acceptance", given.get("by"), basis.STALE,
                     "{0}; the instructions have changed since: {1}".format(who, "; ".join(changed)))
    return _part("acceptance", given.get("by"), basis.HOLDS, "{0}; nothing has changed since".format(who))


def _artifacts(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A work product is current while the inputs it was built from are the same bytes."""
    out = []
    for row in task.get("evidence", []):
        contract = row.get("artifact")
        if not isinstance(contract, dict):
            continue
        name, gone, recorded = row.get("ref"), contract.get("invalidated"), contract.get("basis")
        if gone:
            out.append(_part("artifact", name, basis.STALE, "{0} invalidated it: {1}".format(gone.get("agent"), gone.get("reason"))))
        elif not contract.get("dependencies_known"):
            out.append(_part("artifact", name, basis.UNKNOWN, "its inputs were never declared, so nothing can say whether it is current"))
        elif not isinstance(recorded, dict):
            out.append(_part("artifact", name, basis.UNKNOWN, "its inputs were named but not fingerprinted; record it again"))
        else:
            root = Path(contract.get("root") or ".")
            moved = []
            for item in sorted(recorded):
                now = basis.fingerprint(root, item)
                if recorded[item] is not None and now != recorded[item]:
                    moved.append("{0} {1}".format(item, "is gone" if now is None else "changed"))
            absent = sorted(item for item in recorded if recorded[item] is None)
            if moved:
                out.append(_part("artifact", name, basis.STALE, "; ".join(moved)))
            elif absent:
                out.append(_part("artifact", name, basis.UNKNOWN, "{0} could not be read when it was recorded".format(", ".join(absent))))
            else:
                out.append(_part("artifact", name, basis.HOLDS, "its {0} declared input(s) are unchanged".format(len(recorded))))
    return out


def _lease(store: claims_mod.ClaimStore, claim: Dict[str, Any]) -> Dict[str, Any]:
    """A lease is the one record whose basis is time: a promise that has to be renewed."""
    beat = claim.get("heartbeat_at") or claim.get("claimed_at")
    label = "{0} as {1!r}".format(claim.get("agent"), claim.get("session_label") or claim.get("id"))
    if store._is_fresh(claim, None):
        return _part("lease", label, basis.HOLDS, "last heartbeat {0}".format(beat))
    return _part("lease", label, basis.STALE, "no heartbeat for {0:.0f} h; the work may have stopped".format(age_hours(beat)))


def _leases(paths: Paths, task: Dict[str, Any]) -> List[Dict[str, Any]]:
    store = claims_mod.ClaimStore(paths)
    scope = "task:{0}".format(task["id"])
    return [_lease(store, claim) for claim in store.all()
            if claim.get("status") == "live" and scope in claim.get("scopes", [])]


def _next(task_id: str, parts: List[Dict[str, Any]]) -> List[str]:
    short = {part["kind"] for part in parts if part["state"] != basis.HOLDS}
    out = []
    if "check" in short:
        out.append("run the checks on the files as they are: taos gate run --task {0} --agent <you>".format(task_id))
    if "artifact" in short:
        out.append("rebuild the work products named above, or record them again with --depends-on")
    if "closure" in short and "check" not in short:
        out.append("read the changed instructions and decide whether the work still satisfies them")
    if "acceptance" in short:
        out.append("ask the person to look at this version: taos task accept {0}".format(task_id))
    if "lease" in short:
        out.append("take the work over with evidence, or release the claim")
    return out


def of_task(paths: Paths, task_id: str, snaps: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Every record this task's status rests on, each judged against the present, and the worst of them."""
    task = tasks_mod.TaskStore(paths).get(task_id)
    root = str(gates_mod._where(paths, task, gates_mod.latest(paths, task["id"])))
    snaps = snaps if snaps is not None else {}
    if root not in snaps:
        snaps[root] = basis.snapshot(Path(root), gates_mod._settings(paths))
    closed = task.get("status") in CLOSED
    checks = [_part("check", verdict["gate"], verdict["state"], verdict["reason"])
              for verdict in gates_mod.standing(paths, task["id"], snaps[root])]
    parts = ([_closure(paths, task, checks)] if closed else []) + checks + _artifacts(task)
    accepted = _acceptance(paths, task, snaps[root]) if closed else None
    if accepted:
        parts.append(accepted)
    parts += _leases(paths, task)
    return {
        "task": task["id"], "title": task.get("title", ""), "status": task.get("status"), "done_when": task.get("done_when", ""),
        "closed": closed, "accepted": accepted is not None, "state": basis.worst(part["state"] for part in parts),
        "parts": parts, "next": _next(task["id"], parts),
        "instructions": [{"id": rule["id"], "quote": rule["quote"], "said_on": rule["said_on"], "scope": rule["scope"],
                          "expires": rule.get("expires")} for rule in rules_mod.for_task(paths, task)],
    }


def everything(paths: Paths) -> Dict[str, Any]:
    """Across the whole home: which closed work, leases and distilled summaries no longer hold."""
    tasks = tasks_mod.TaskStore(paths).load()["tasks"]
    snaps: Dict[str, Dict[str, Any]] = {}
    views = [of_task(paths, task_id, snaps) for task_id in sorted(tasks) if tasks[task_id].get("status") in CLOSED]
    rows = [dict(part, task=view["task"]) for view in views for part in view["parts"] if part["state"] != basis.HOLDS]
    store = claims_mod.ClaimStore(paths)
    for claim in store.stale():
        if not any("task:{0}".format(view["task"]) in claim.get("scopes", []) for view in views):
            rows.append(dict(_lease(store, claim), task=None))
    for kernel in kernels_mod.freshness(paths):
        if kernel.get("status") != "fresh":
            rows.append(dict(_part("summary", kernel.get("name"), KERNEL_STATES.get(kernel.get("status"), basis.UNKNOWN),
                                   "; ".join(kernel.get("reasons") or []) or str(kernel.get("status"))), task=None))
    return {"closed": len(views), "standing": sum(1 for view in views if view["state"] == basis.HOLDS),
            "unaccepted": [view["task"] for view in views if not view["accepted"]], "rows": rows}


# --------------------------------------------------------------------------
# Words
# --------------------------------------------------------------------------


def _label(part: Dict[str, Any]) -> str:
    return part["kind"] if part["kind"] in ("closure", "acceptance") else "{0} {1}".format(part["kind"], part["name"])


def lines(view: Dict[str, Any]) -> List[str]:
    """One line per part: the state first, because that is the answer."""
    return ["{0:<8} {1}: {2}".format(part["state"], _label(part), part["reason"]) for part in view["parts"]]


def text(view: Dict[str, Any]) -> str:
    out = ["{0}  {1}  {2}".format(view["task"], view["status"], view["title"])]
    if view.get("done_when"):
        out.append("  done when: {0}".format(view["done_when"]))
    out.append("")
    out += ["  " + line for line in lines(view)] or ["  nothing is recorded for this task yet"]
    if view["instructions"]:
        out += ["", "  instructions in force today, in the words they were given:"]
        for rule in view["instructions"]:
            until = ", until {0}".format(rule["expires"]) if rule.get("expires") else ""
            out.append("    {0}  \"{1}\"  (said {2}, scope {3}{4})".format(rule["id"], rule["quote"], rule["said_on"], rule["scope"], until))
    out.append("")
    if not view["closed"]:
        out.append("{0} is {1}: nothing is claimed finished yet. The lines above are what closing it would rest on.".format(
            view["task"], view["status"]))
    elif view["state"] == basis.HOLDS:
        out.append("{0} stands as recorded.{1}".format(view["task"], "" if view["accepted"] else " No person has accepted it yet."))
    else:
        out.append("{0} does not stand as recorded: {1}.".format(view["task"], view["state"]))
    out += ["  next: " + step for step in view["next"]]
    return "\n".join(out)


def summary(found: Dict[str, Any]) -> str:
    out = ["{0} of {1} closed task(s) stand as recorded.".format(found["standing"], found["closed"])]
    if found["rows"]:
        out.append("")
    grouped: Dict[Any, List[str]] = {}   # one cause is one line, however many tasks rest on it
    for row in found["rows"]:
        grouped.setdefault((row["state"], _label(row), row["reason"]), []).extend([row["task"]] if row.get("task") else [])
    for (state, label, reason), tasks in grouped.items():
        out.append("  {0:<8} {1}: {2}{3}".format(state, label, reason, "  [{0}]".format(", ".join(tasks)) if tasks else ""))
    if found["unaccepted"]:
        out += ["", "not accepted by a person: {0}".format(", ".join(found["unaccepted"]))]
    if found["rows"]:
        out += ["", "taos why <task> shows every part and what to do next."]
    return "\n".join(out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_why(args: argparse.Namespace, paths: Paths) -> int:
    if args.task_id:
        view = of_task(paths, args.task_id)
        print(json.dumps(view, indent=2, sort_keys=True) if args.json else text(view))
        return 1 if args.check and view["state"] != basis.HOLDS else 0
    found = everything(paths)
    print(json.dumps(found, indent=2, sort_keys=True) if args.json else summary(found))
    return 1 if args.check and found["rows"] else 0


def register(subparsers: Any) -> None:
    why = subparsers.add_parser("why", help="what a result rests on, and whether it still holds")
    why.add_argument("task_id", nargs="?", metavar="TASK", help="one task; leave out to list everything that no longer holds")
    why.add_argument("--json", action="store_true")
    why.add_argument("--check", action="store_true", help="exit 1 when something does not hold, for scripts")
    why.set_defaults(func=_cmd_why)
