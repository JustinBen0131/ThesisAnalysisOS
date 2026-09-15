"""The daily brief: what changed, what needs you, nothing else."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from . import atoms as atoms_mod
from . import burn as burn_mod
from . import claims as claims_mod
from . import config as config_mod
from . import decisions as decisions_mod
from . import doctor as doctor_mod
from . import events as events_mod
from . import kernels as kernels_mod
from . import projections as projections_mod
from . import proposals as proposals_mod
from . import tasks as tasks_mod
from . import telemetry as telemetry_mod
from .paths import Paths
from .store import age_hours, atomic_write_json, atomic_write_text, parse_ts, shift_hours, utc_now

NO_ACTION = "No action needed."


def build(paths: Paths, since: Optional[str] = None) -> Dict[str, Any]:
    store = tasks_mod.TaskStore(paths)
    claim_store = claims_mod.ClaimStore(paths)
    now = utc_now()
    window_start = since or shift_hours(now, -24.0)

    open_decisions = decisions_mod.open_decisions(paths)
    stale_claims = claim_store.stale()
    live_claims = claim_store.live()
    hot = projections_mod.hot_work(paths)
    blocked_hot = [item for item in hot if item.get("status") == "blocked" or item.get("blockers")]
    report = doctor_mod.run(paths)
    failing_checks = [c for c in report["checks"] if c["status"] == "fail"]

    changed = []
    for row in events_mod.read(paths, since=window_start):
        if row.get("type") in ("task_transition", "task_create", "handoff_write", "decision_answer", "task_comment"):
            changed.append(
                {
                    "ts": row.get("ts"),
                    "type": row.get("type"),
                    "agent": row.get("agent"),
                    "task_id": row.get("task_id"),
                    "detail": row.get("to_state") or row.get("title") or row.get("answer") or row.get("session") or "",
                }
            )

    needs: List[str] = []
    for decision in open_decisions[:2]:
        needs.append("decide: {0} ({1})".format(decision["question"], decision["id"]))
    for claim in stale_claims[:2]:
        needs.append(
            "stale claim: {0} still marked on {1}".format(claim["agent"], ", ".join(claim["scopes"]))
        )
    for item in blocked_hot[:2]:
        needs.append("blocked: {0} {1} ({2})".format(item["id"], item["title"], ", ".join(item.get("blockers") or [])))
    for check in failing_checks[:2]:
        needs.append("doctor: {0} — {1}".format(check["name"], check["detail"]))

    top_line = NO_ACTION if not needs else "{0} item(s) need you.".format(len(needs))

    atom_results = atoms_mod.check(paths)
    try:
        burn_candidates = len(burn_mod.plan(paths))
    except Exception:
        burn_candidates = 0

    return {
        "generated_at": now,
        "window_start": window_start,
        "project": config_mod.load_soft(paths).get("project", {}).get("name", "project"),
        "top_line": top_line,
        "needs": needs,
        "decisions_owed": open_decisions,
        "changed": changed,
        "hot": hot,
        "blocked": blocked_hot,
        "claims": {"live": live_claims, "stale": stale_claims},
        "kernels": kernels_mod.freshness(paths),
        "atoms": {
            "pass": len([a for a in atom_results if a["ok"]]),
            "fail": [a for a in atom_results if not a["ok"]],
        },
        "burn_candidates": burn_candidates,
        "proposals_open": proposals_mod.open_proposals(paths),
        "doctor": {"ok": report["ok"], "failing": failing_checks},
    }


def render_markdown(brief: Dict[str, Any]) -> str:
    lines = [
        "# {0} — {1}".format(brief["project"], brief["generated_at"][:10]),
        "",
        "**{0}**".format(brief["top_line"]),
        "",
    ]
    if brief["needs"]:
        for item in brief["needs"]:
            lines.append("- {0}".format(item))
        lines.append("")

    lines += ["## Hot work", ""]
    if brief["hot"]:
        for item in brief["hot"]:
            line = "- **{0}** [{1}] {2} — {3}".format(item["id"], item["priority"], item["status"], item["title"])
            lines.append(line)
            if item.get("blockers"):
                lines.append("  - blocked by {0}".format(", ".join(item["blockers"])))
            elif item.get("next_action"):
                lines.append("  - next: {0}".format(item["next_action"]))
            if item.get("owner_agent"):
                lines.append("  - owner: {0}".format(item["owner_agent"]))
    else:
        lines.append("- nothing hot.")

    lines += ["", "## Changed in the last day", ""]
    if brief["changed"]:
        for row in brief["changed"][-20:]:
            lines.append(
                "- {0} {1} {2} {3} {4}".format(
                    row["ts"][11:16], row["agent"], row["type"], row.get("task_id") or "", row.get("detail") or ""
                ).rstrip()
            )
    else:
        lines.append("- nothing.")

    lines += ["", "## Claims", ""]
    if brief["claims"]["live"]:
        for claim in brief["claims"]["live"]:
            lines.append(
                "- {0}: {1} ({2}, {3:.1f}h)".format(
                    claim["agent"],
                    ", ".join(claim["scopes"]),
                    claim["session_label"],
                    age_hours(claim.get("heartbeat_at", claim["claimed_at"])),
                )
            )
    else:
        lines.append("- none live.")
    for claim in brief["claims"]["stale"]:
        lines.append("- STALE {0} on {1}".format(claim["agent"], ", ".join(claim["scopes"])))

    lines += ["", "## OS health", ""]
    lines.append("- doctor: {0}".format("green" if brief["doctor"]["ok"] else "failing"))
    for check in brief["doctor"]["failing"]:
        lines.append("  - {0}: {1}".format(check["name"], check["detail"]))
    lines.append(
        "- kernels: {0}".format(", ".join("{0} {1}".format(k["name"], k["status"]) for k in brief["kernels"]))
    )
    lines.append("- atoms: {0} passing, {1} failing".format(brief["atoms"]["pass"], len(brief["atoms"]["fail"])))
    for atom in brief["atoms"]["fail"]:
        lines.append("  - {0}: {1}".format(atom["id"], atom["detail"]))
    if brief["proposals_open"]:
        lines.append("- proposals waiting on you:")
        for proposal in brief["proposals_open"]:
            lines.append("  - {0} [{1}] {2}".format(proposal["id"], proposal["kind"], proposal["title"]))
    if brief["burn_candidates"]:
        lines.append("- {0} file(s) past their TTL (`taos burn plan`)".format(brief["burn_candidates"]))
    lines.append("")
    return "\n".join(lines)


def write(paths: Paths) -> Any:
    paths.ensure_state()
    data = build(paths)
    text = render_markdown(data)
    atomic_write_json(paths.projections_dir / "brief.json", data)
    atomic_write_text(paths.projections_dir / "brief.md", text)
    atomic_write_text(paths.briefs_dir / "{0}.md".format(data["generated_at"][:10]), text)
    events_mod.emit(paths, "brief_render", "system", needs=len(data["needs"]))
    return paths.projections_dir / "brief.md"


def retro(paths: Paths, days: int = 7) -> Dict[str, Any]:
    now = utc_now()
    window = shift_hours(now, -24.0 * days)
    rows = events_mod.read(paths, since=window)
    store = tasks_mod.TaskStore(paths)

    by_type: Dict[str, int] = {}
    by_agent: Dict[str, int] = {}
    for row in rows:
        by_type[row.get("type", "?")] = by_type.get(row.get("type", "?"), 0) + 1
        by_agent[row.get("agent", "?")] = by_agent.get(row.get("agent", "?"), 0) + 1

    finished = [
        row for row in rows if row.get("type") == "task_transition" and row.get("to_state") in ("done", "canceled")
    ]
    labels = [
        row for row in telemetry_mod.rows(paths) if parse_ts(row.get("ts", now)) >= parse_ts(window)
    ]
    corrections = [row for row in labels if row.get("outcome") in ("corrected", "reworked")]

    stale_hot = []
    for item in projections_mod.hot_work(paths):
        if item.get("updated_at") and age_hours(item["updated_at"]) > 24 * 7:
            stale_hot.append(item)

    suggestions = []
    for item in stale_hot:
        suggestions.append(
            {
                "kind": "retire",
                "title": "{0} has been hot and untouched for a week".format(item["id"]),
                "body": "Either give it a next action and work it, or cool it with "
                "`taos task hot {0} --agent human --off --reason 'not now'`.".format(item["id"]),
            }
        )
    if len(corrections) >= 2:
        suggestions.append(
            {
                "kind": "atom",
                "title": "{0} corrections this week: one of them should become an atom".format(len(corrections)),
                "body": "Pick the correction you gave more than once, write it as a checkable "
                "rule, and propose it with `taos propose --kind atom --atom-json <file>`.",
            }
        )

    return {
        "generated_at": now,
        "days": days,
        "events": len(rows),
        "by_type": by_type,
        "by_agent": by_agent,
        "finished": [row.get("task_id") for row in finished],
        "corrections": len(corrections),
        "stale_hot": [item["id"] for item in stale_hot],
        "suggestions": suggestions,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_brief(args: argparse.Namespace, paths: Paths) -> int:
    if args.json:
        print(json.dumps(build(paths), indent=2, sort_keys=True))
        return 0
    path = write(paths)
    if args.print:
        print(path.read_text(encoding="utf-8"))
    else:
        print("wrote {0}".format(paths.relative(path)))
        print("")
        print(render_markdown(build(paths)).split("\n## ")[0])
    return 0


def _cmd_retro(args: argparse.Namespace, paths: Paths) -> int:
    data = retro(paths, args.days)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    print("last {0} days: {1} events".format(data["days"], data["events"]))
    print("by agent: {0}".format(", ".join("{0} {1}".format(k, v) for k, v in sorted(data["by_agent"].items())) or "none"))
    print("finished: {0}".format(", ".join([t for t in data["finished"] if t]) or "nothing"))
    print("corrections recorded: {0}".format(data["corrections"]))
    if data["stale_hot"]:
        print("hot but untouched for a week: {0}".format(", ".join(data["stale_hot"])))
    for suggestion in data["suggestions"]:
        print("")
        print("[{0}] {1}".format(suggestion["kind"], suggestion["title"]))
        print("    {0}".format(suggestion["body"]))
    return 0


def register(subparsers: Any) -> None:
    brief = subparsers.add_parser("brief", help="render today's brief")
    brief.add_argument("--print", action="store_true")
    brief.add_argument("--json", action="store_true")
    brief.set_defaults(func=_cmd_brief)

    retro_parser = subparsers.add_parser("retro", help="weekly look back, with suggestions")
    retro_parser.add_argument("--days", type=int, default=7)
    retro_parser.add_argument("--json", action="store_true")
    retro_parser.set_defaults(func=_cmd_retro)
