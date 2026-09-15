"""Derived views. Never authority: delete these and they rebuild."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from . import claims as claims_mod
from . import config as config_mod
from . import decisions as decisions_mod
from . import kernels as kernels_mod
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
        from . import control as control_mod

        if control_mod.settings(paths).get("enabled", True):
            lines.append(control_mod.status_line(paths))
    except Exception:
        pass
    lines.append(
        'Rule: map the prompt to a task, then `./taos start --agent <you> --task <ID> --session "<ID> | <label>"`.'
    )
    return "\n".join(lines[:max_lines])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    if args.compact:
        print(compact_status(paths))
        return 0
    if not paths.constructed():
        print(config_mod.NOT_CONSTRUCTED)
        return 0
    data = refresh(paths)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
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
    parser.set_defaults(func=_cmd_status)
