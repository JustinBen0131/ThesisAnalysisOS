"""Task-scoped scientific progress from this project's existing evidence and check events."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config, events, hpc, standing
from .store import canonical_json, locked, sha256_text
from .tasks import TaskStore
from .util import TaosError


def snapshot(report):
    counts = dict.fromkeys(hpc.LABELS, 0)
    for output in report["outputs"]:
        counts[output["action"]] += 1
    return {"packet_sha256": report["packet_sha256"], "reviewer_sha256": report["reviewer_sha256"],
            "review_sha256": sha256_text(canonical_json(report)), "outputs": counts,
            "listed": len(report["outputs"]), "manifest_reconciled": not report["manifest_issue"] and not report["unexpected"],
            "accounting": {key: report["accounting"][key] for key in ("worker_seconds", "attempts", "outputs", "sha256")}}


def record(paths, task_id, campaign, actor, report):
    if not paths.constructed():
        raise TaosError("Set up the project before attaching a review. Omit --task for a read-only inspection.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", campaign):
        raise TaosError("Give the campaign a stable name of 1 to 80 letters, digits, dots, dashes or underscores.")
    config.require_actor(paths, actor)
    summary = snapshot(report)
    with locked(paths):
        TaskStore(paths).get(task_id)
        previous = next((row for row in reversed(events.read(paths, types=["hpc_review"]))
                         if row.get("task_id") == task_id and row.get("campaign") == campaign), None)
        if previous and previous["summary"]["review_sha256"] == summary["review_sha256"]:
            return
        events.emit(paths, "hpc_review", actor, task_id=task_id, campaign=campaign, summary=summary)


def latest_reviews(rows, task_id=None):
    latest = {}
    for row in rows:
        if row["type"] == "hpc_review" and (task_id is None or row.get("task_id") == task_id):
            latest[row["task_id"], row["campaign"]] = row
    return latest


def campaign_line(summary):
    counts = summary["outputs"]
    expected = summary["listed"]
    line = f'{counts["keep"]}/{expected} listed outputs reusable at review'
    if not summary["manifest_reconciled"]:
        line += " (manifest needs reconciliation)"
    for key, name in (("inspect", "to inspect"), ("wait", "in flight"), ("retry", "for retry review"), ("pilot", "unstarted")):
        if counts[key]:
            line += f", {counts[key]} {name}"
    measured = summary["accounting"]
    if measured["worker_seconds"] is None:
        return line + ". Worker time unknown."
    return line + ". " + hpc.accounting_line(measured, expected)


def project_view(paths, task_id=None, actor=None):
    if not paths.constructed():
        raise TaosError("For the sample, run ./taos usage progress --packet examples/hpc/campaign.json. Set up a project to see its tasks.")
    if actor:
        config.require_actor(paths, actor)
    store = TaskStore(paths)
    tasks = [store.get(task_id)] if task_id else store.list()
    rows = events.read(paths, types=["hpc_review", "gate_run"])
    latest = latest_reviews(rows, task_id)
    checks = {}
    for row in rows:
        if row["type"] != "gate_run" or (actor and row["agent"] != actor):
            continue
        task_checks = checks.setdefault(row.get("task_id"), {"executed": 0, "reused": 0})
        reused = set(row.get("reused") or [])
        for name in row.get("gates") or []:
            task_checks["reused" if name in reused else "executed"] += 1
    grouped = {}
    for (task, campaign), row in sorted(latest.items()):
        if actor and row["agent"] != actor:
            continue
        grouped.setdefault(task, []).append(dict(row["summary"], campaign=campaign, reviewed_at=row["ts"], filed_by=row["agent"]))
    result = []
    snaps = {}
    for task in tasks:
        ident = task["id"]
        campaigns = grouped.get(ident, [])
        if not (task_id or campaigns or ident in checks or (not actor and task.get("acceptance"))):
            continue
        acceptance = None
        check_standing = []
        closure = None
        if task.get("status") in standing.CLOSED or ident in checks:
            view = standing.of_task(paths, ident, snaps)
            closure = next((part for part in view["parts"] if part["kind"] == "closure"), None)
            check_standing = [part for part in view["parts"] if part["kind"] == "check"]
            acceptance = next((part for part in view["parts"] if part["kind"] == "acceptance"), None)
        result.append({"id": ident, "title": task["title"], "status": task["status"], "acceptance": acceptance,
                       "closure": closure, "check_standing": check_standing, "checks": checks.get(ident, {"executed": 0, "reused": 0}), "campaigns": campaigns})
    return {"format": "taos.usage.progress.v1", "project": config.project_name(paths),
            "principal": config.load(paths)["principal"]["name"], "activity_by": actor, "tasks": result}


def command(args, paths):
    if args.packet:
        if args.actor:
            raise TaosError("--actor filters filed project activity. Omit it when inspecting a packet.")
        report = hpc.review(hpc.read_packet(args.packet), args.packet.parent)
        summary = snapshot(report)
        result = {"format": "taos.usage.progress.v1", "question": report["question"], "campaign": summary,
                  "accounting_note": report["accounting"]["reason"], "next": report["next"]}
        lines = [report["question"], campaign_line(summary), report["accounting"]["reason"], report["next"]]
    else:
        result = project_view(paths, args.task, args.actor)
        lines = [f'{result["project"]} · project principal {result["principal"]}']
        if args.actor:
            lines.append(f"Activity filed by {args.actor}. Current standing covers the whole task.")
        for task in result["tasks"]:
            acceptance = task["acceptance"]
            lines.extend([f'{task["id"]}  {task["title"]}  [{task["status"]}]',
                          f'  Checks executed {task["checks"]["executed"]} · reused {task["checks"]["reused"]}',
                          "  Task workspace and instructions · " + (acceptance["reason"] if acceptance else "no current human acceptance recorded.")])
            if task["closure"]:
                lines.append(f'  Task closure · {task["closure"]["state"]} · {task["closure"]["reason"]}')
            for check in task["check_standing"]:
                lines.append(f'  {check["name"]} · {check["state"]} · {check["reason"]}')
            for campaign in task["campaigns"]:
                lines.append(f'  {campaign["campaign"]} · {campaign["reviewed_at"]} · filed by {campaign["filed_by"]}')
                lines.append("    " + campaign_line(campaign))
        if not result["tasks"]:
            lines.append("No task has a recorded check, compute review or acceptance yet.")
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else "\n".join(line for line in lines if line))


def register(sub):
    parser = sub.add_parser("progress", help="see task checks, human acceptance and recorded worker time")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--packet", type=Path, help="inspect one local HPC packet without setting up a project")
    source.add_argument("--task", help="show just this project task")
    parser.add_argument("--actor", help="show checks run and latest campaign reviews filed by this project actor")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=command)
