"""Derived views. Never authority: delete these and they rebuild."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List, Optional

from . import claims as claims_mod
from . import config as config_mod
from . import decisions as decisions_mod
from . import kernels as kernels_mod
from . import page, plain
from . import proposals as proposals_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import age_hours, atomic_write_json, utc_now
from .util import TaosError


def hot_work(paths: Paths) -> List[Dict[str, Any]]:
    store = tasks_mod.TaskStore(paths)
    rows = []
    for task in store.list(hot=True):
        rows.append(
            {
                "id": task["id"],
                "title": task.get("title", ""),
                "status": task.get("status"),
                "priority": task.get("priority"),
                "owner_agent": task.get("owner_agent"),
                "next_action": task.get("next_action", ""),
                "goal": task.get("goal", ""),
                "blockers": store.blockers(task["id"]),
                "hot": True,
                "hot_since": task.get("hot_since"),
                "updated_at": task.get("updated_at"),
            }
        )
    return rows


def status(paths: Paths) -> Dict[str, Any]:
    store = tasks_mod.TaskStore(paths)
    claim_store = claims_mod.ClaimStore(paths)
    all_tasks = store.list()
    by_status: Dict[str, int] = {}
    for task in all_tasks:
        by_status[task["status"]] = by_status.get(task["status"], 0) + 1
    return {
        "generated_at": utc_now(),
        "project": config_mod.load_soft(paths).get("project", {}).get("name", "project"),
        "counts": by_status,
        "hot": hot_work(paths),
        "decisions": decisions_mod.open_decisions(paths),
        "claims": {"live": claim_store.live(), "stale": claim_store.stale()},
        "kernels": kernels_mod.freshness(paths),
        "proposals_open": len(proposals_mod.open_proposals(paths)),
    }


def refresh(paths: Paths) -> Dict[str, Any]:
    paths.ensure_state()
    data = status(paths)
    atomic_write_json(paths.projections_dir / "hot_work.json", {"generated_at": data["generated_at"], "items": data["hot"]})
    atomic_write_json(paths.projections_dir / "status.json", data)
    return data


def compact_status(paths: Paths, max_lines: int = 25) -> str:
    if not paths.constructed():
        return config_mod.NOT_CONSTRUCTED
    if (paths.state / "paused").is_file():
        return (
            "TAOS is paused by the human. Work normally without task ceremony. "
            "The hard stops still apply (secrets, force pushes, the store, the cage). Resume with `taos resume`."
        )
    try:
        data = status(paths)
    except TaosError as exc:
        return "TAOS state is unreadable: {0}".format(exc)

    lines: List[str] = []
    header = "TAOS {0} | {1}".format(data["project"], utc_now()[:10])
    config = config_mod.load_soft(paths)
    if config.get("constructed_at"):
        header += " | constructed {0}".format(str(config["constructed_at"])[:10])
    lines.append(header)

    if data["hot"]:
        for index, item in enumerate(data["hot"][:6]):
            prefix = "Hot: " if index == 0 else "     "
            line = '{0}{1} {2} {3} {4} "{5}"'.format(
                prefix,
                item["id"],
                item.get("priority", ""),
                item.get("status", ""),
                item.get("owner_agent") or "-",
                str(item.get("title", ""))[:48],
            )
            if item.get("blockers"):
                line += " blocked_by: {0}".format(",".join(item["blockers"]))
            elif item.get("next_action"):
                line += " next: {0}".format(str(item["next_action"])[:60])
            lines.append(line)
    else:
        lines.append("Hot: nothing. Pick from `taos task list --status next`.")

    decisions = data["decisions"]
    if decisions:
        first = decisions[0]
        lines.append(
            "Decisions owed: {0} ({1}: \"{2}\")".format(len(decisions), first["id"], str(first["question"])[:60])
        )
    else:
        lines.append("Decisions owed: 0")

    live = data["claims"]["live"]
    stale = data["claims"]["stale"]
    if live:
        rendered = " | ".join(
            "{0} {1} ({2:.0f}m)".format(
                c["agent"], ",".join(c["scopes"])[:34], age_hours(c.get("heartbeat_at", c["claimed_at"])) * 60
            )
            for c in live[:3]
        )
    else:
        rendered = "none"
    lines.append("Claims live: {0} | stale: {1}".format(rendered, len(stale) if stale else "none"))

    lines.append(
        "Kernels: {0}".format(
            ", ".join("{0} {1}".format(k["name"].replace("_KERNEL", ""), k["status"]) for k in data["kernels"])
        )
    )

    from . import doctor as doctor_mod

    report = doctor_mod.run(paths)
    failures = [c for c in report["checks"] if c["status"] == "fail"]
    lines.append(
        "Doctor: {0} | Proposals open: {1}".format(
            "green" if report["ok"] else "{0} failing ({1})".format(len(failures), failures[0]["name"] if failures else ""),
            data["proposals_open"],
        )
    )
    try:
        from . import standing as standing_mod

        short = sorted({row["task"] for row in standing_mod.everything(paths)["rows"] if row.get("task")})
        if short:
            lines.append("Closed work that no longer stands as recorded: {0}. Ask `taos why`.".format(", ".join(short[:6])))
    except Exception:   # orientation must never fail because one record cannot be read
        pass
    try:
        from . import control as control_mod

        if control_mod.settings(paths).get("enabled", True):
            lines.append(control_mod.status_line(paths))
    except Exception:
        pass
    lines.append(
        'Rule: map the prompt to a task, then `./taos start --agent <you> --task <ID> --session "<ID> | <label>"`.'
    )
    return "\n".join(lines[:max_lines])


def answers(paths: Paths, data: Dict[str, Any]) -> List[List[str]]:
    """Where everything stands as rows a person can scan: the answer, what it is about, and the command that says more."""
    from . import doctor as doctor_mod
    from . import standing as standing_mod

    closed, fallen, found = 0, None, {}                             # type: int, Optional[List[str]], Dict[str, Any]
    try:
        found = standing_mod.everything(paths)
        closed, fallen = found["closed"], sorted({row["task"] for row in found["rows"] if row.get("task")})
    except Exception:   # a record that cannot be read is an answer too, and it is not "holds"
        pass
    if fallen is None:
        rows = [["unknown", "whether closed work still stands: its record could not be read", "taos why"]]
    elif fallen:
        rows = [["stale", "{0} of {1} closed task(s) no longer stand as recorded: {2}".format(len(fallen), closed, ", ".join(fallen[:6])),
                 "taos why"]]
    else:
        rows = [["holds", "all closed work stands as recorded" if closed else "nothing is closed yet, so nothing has gone stale",
                 "taos why"]]
    work = found.get("open") or {}
    for row in work.get("rows", []):                                # open work: each check that no longer holds, by name
        rows.append([row["state"], "{0} {1}: {2}".format(row["task"], standing_mod._label(row), plain.local(row["reason"])),
                     "taos why {0}".format(row["task"])])
    if work.get("holding"):
        rows.append(["holds", "{0}{1} check(s) on open work".format("the other " if work["rows"] else "all ", work["holding"]),
                     "taos why"])
    report = doctor_mod.run(paths)
    failing = [check["name"] for check in report["checks"] if check["status"] == "fail"]
    rows.append(["holds", "the system's own {0} checks pass".format(len(report["checks"])), "taos doctor"] if report["ok"]
                else ["fails", "{0} of the system's own checks: {1}".format(len(failing), ", ".join(failing[:3])), "taos doctor"])
    look = "taos kernel freshness"
    if not data["kernels"]:
        rows.append(["unknown", "no summaries are listed", look])
        return rows + lapsed(data)
    named = {state: [kernel["name"].replace("_KERNEL", "") for kernel in data["kernels"] if kernel["status"] == state]
             for state in ("drifted", "missing", "aged")}       # only a changed source makes a summary stale; age alone does not
    if named["drifted"]:
        rows.append(["stale", "{0} of {1} summaries were written before their sources changed: {2}".format(
            len(named["drifted"]), len(data["kernels"]), ", ".join(named["drifted"])), look])
    if named["missing"]:
        rows.append(["unknown", "{0} summaries are not there to read: {1}".format(len(named["missing"]), ", ".join(named["missing"])), look])
    if not named["drifted"] and not named["missing"]:
        rows.append(["holds", "every summary matches its sources" + (
            ", though {0} are past the date to read them again".format(len(named["aged"])) if named["aged"] else ""), look])
    return rows + lapsed(data)


def lapsed(data: Dict[str, Any]) -> List[List[str]]:
    gone = data["claims"]["stale"]
    return [["stale", "{0} claim(s) lapsed with no sign of life".format(len(gone)), "taos claim status"]] if gone else []


NBSP = "\u00a0"                    # holds a command together while a line is folded; written as a space
NOTHING_YET = ("Nothing is set up here yet, so there is nothing to report.\n"
               "See the idea in a minute: taos demo\n"
               "Set it up for your own work: taos use <folder> --check \"<command>\"")


def person_status(paths: Paths, data: Dict[str, Any], me: str = "taos") -> List[str]:
    """`taos status` for a person at a terminal: the answers first, then the work in hand, then what waits for them.
    A command keeps its words together with NBSP, so that folding a line never splits something to paste."""
    def run(words: str) -> str:                                     # a command as this person types it, kept in one piece
        return (me + " " + words).replace(" ", NBSP)

    lines = ["{0}  {1}".format(data["project"], time.strftime("%Y-%m-%d")), ""]
    lines += ["  {0} {1}. More: {2}".format(answer.ljust(8), about, run(command[5:])) for answer, about, command in answers(paths, data)]
    lines += ["", "In hand"]
    for item in data["hot"][:6]:
        lines.append("  {0}  {1}  {2}".format(item["id"], (item.get("owner_agent") or "nobody").ljust(6), str(item.get("title", ""))[:56]))
        if item.get("blockers"):
            lines.append("           waits on: {0}".format(", ".join(item["blockers"])))
        elif item.get("next_action"):
            lines.append("           next: {0}".format(str(item["next_action"])[:64]))
    if len(data["hot"]) > 6:
        lines.append("  and {0} more: {1}".format(len(data["hot"]) - 6, run("task list")))
    if not data["hot"]:
        lines.append("  nothing. Pick from: {0}".format(run("task list")))
    lines += ["", "Waiting for you"]
    for decision in data["decisions"][:4]:
        lines.append("  {0}  {1}".format(decision["id"], str(decision["question"])[:68]))
    if len(data["decisions"]) > 4:
        lines.append("  and {0} more: {1}".format(len(data["decisions"]) - 4, run("decide list")))
    lines.append("  answer with: {0}".format(run("decide answer")) if data["decisions"] else "  nothing")
    counts = ", ".join("{0} {1}".format(count, state) for state, count in sorted(data["counts"].items()))
    return lines + ["", "Tasks: {0}. Everything an agent is told: {1}".format(counts or "none", run("status --full"))]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    if args.compact:
        print(compact_status(paths))
        return 0
    person = page.terminal(sys.stdout) and not args.full
    if not paths.constructed():
        print(NOTHING_YET if person else config_mod.NOT_CONSTRUCTED)
        return 0
    if person and not args.json and not (paths.state / "paused").is_file():
        kernels_mod.generate_now(paths)                             # a person asking where things stand gets NOW written anew
    data = refresh(paths)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    if person and not (paths.state / "paused").is_file():
        folder = page.Page.to(sys.stdout)
        for line in person_status(paths, data, page.launcher()):
            for part in folder.fold(line, hang=11 if (folder.width or page.WIDTH) >= 56 else 4):
                print(part.replace(NBSP, " "))
        return 0
    print(compact_status(paths))
    print("")
    counts = ", ".join("{0} {1}".format(v, k) for k, v in sorted(data["counts"].items()))
    print("Tasks: {0}".format(counts or "none"))
    return 0


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("status", help="where everything stands")
    parser.add_argument("--compact", action="store_true", help="the version injected into agent sessions")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--full", action="store_true", help="everything an agent is told (what a pipe gets)")
    parser.set_defaults(func=_cmd_status)
