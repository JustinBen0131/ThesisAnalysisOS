"""The append-only event log. Every mutation lands here before the store."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from .paths import Paths
from .store import append_jsonl, canonical_json, parse_ts, read_jsonl, sha256_text, utc_now

AGENTS = ("codex", "claude", "human", "system")


def emit(paths: Paths, type: str, agent: str, **fields: Any) -> Dict[str, Any]:
    paths.ensure_state()
    row: Dict[str, Any] = {"ts": utc_now(), "type": str(type), "agent": str(agent)}
    for key, value in fields.items():
        if value is not None:
            row[key] = value
    row["id"] = sha256_text(canonical_json(row))[:12]
    append_jsonl(paths.events_file, row)
    return row


def read(
    paths: Paths,
    since: Optional[str] = None,
    types: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    rows = read_jsonl(paths.events_file)
    if since:
        boundary = parse_ts(since)
        rows = [row for row in rows if "ts" in row and parse_ts(row["ts"]) >= boundary]
    if types:
        wanted = set(types)
        rows = [row for row in rows if row.get("type") in wanted]
    if limit:
        rows = rows[-int(limit) :]
    return rows


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_events(args: argparse.Namespace, paths: Paths) -> int:
    rows = read(paths, since=args.since, types=args.type or None, limit=args.limit)
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("no events")
        return 0
    for row in rows:
        extra = {k: v for k, v in row.items() if k not in ("ts", "type", "agent", "id")}
        detail = " ".join("{0}={1}".format(k, v) for k, v in sorted(extra.items()))
        print("{0}  {1:<20} {2:<7} {3}".format(row.get("ts", ""), row.get("type", ""), row.get("agent", ""), detail))
    return 0


def _cmd_note(args: argparse.Namespace, paths: Paths) -> int:
    row = emit(paths, "note", args.agent, text=args.text, task_id=args.task)
    print("noted {0}".format(row["id"]))
    return 0


def register(subparsers: Any) -> None:
    events = subparsers.add_parser("events", help="read the event log")
    events.add_argument("--since", help="ISO timestamp lower bound")
    events.add_argument("--type", action="append", help="filter by event type (repeatable)")
    events.add_argument("--limit", type=int, help="show only the last N events")
    events.add_argument("--json", action="store_true")
    events.set_defaults(func=_cmd_events)

    event = subparsers.add_parser("event", help="write a small event")
    event_sub = event.add_subparsers(dest="event_cmd", required=True)
    note = event_sub.add_parser("note", help="append a free-text note event")
    note.add_argument("--agent", required=True, choices=list(AGENTS))
    note.add_argument("--text", required=True)
    note.add_argument("--task", help="task id this note belongs to")
    note.set_defaults(func=_cmd_note)
