"""Sanitized episode labels. Slugs and enums only, never prose or secrets."""

from __future__ import annotations

import argparse
import re
from typing import Any, Dict, List, Optional

from . import config as config_mod
from .paths import Paths
from .store import append_jsonl, utc_now
from .util import TaosError, strip_secrets, truncate

MARKER_RE = re.compile(r"<!--\s*ep:\s*(?P<body>.*?)\s*-->", re.DOTALL)
FIELD_RE = re.compile(r"(?P<key>[a-z_]+)=(?P<value>[^\s<>\"']+)")

PHASES = ("start", "iterate", "handoff", "done", "abandoned")
OUTCOMES = ("landed", "reworked", "corrected", "blocked", "unknown")
MODALITIES = ("code", "docs", "planning", "review", "ops", "mixed", "unknown")
AGENTS = ("codex", "claude")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,60}$")

ALLOWED_KEYS = {"id", "phase", "outcome", "modality", "counterpart", "task"}


def parse_marker(text: str) -> Optional[Dict[str, str]]:
    if not text:
        return None
    match = None
    for match in MARKER_RE.finditer(text):
        pass
    if match is None:
        return None
    fields: Dict[str, str] = {}
    for field in FIELD_RE.finditer(match.group("body")):
        key = field.group("key")
        if key in ALLOWED_KEYS:
            fields[key] = field.group("value")
    if "id" not in fields or "phase" not in fields:
        return None
    return fields


def sanitize(row: Dict[str, Any], secret_patterns: Optional[List[str]] = None) -> Dict[str, Any]:
    task_id = str(row.get("task_id") or row.get("id") or "").strip().lower()
    if not SLUG_RE.match(task_id):
        raise TaosError("label task_id must be a slug like 'az7-fix-ssa'")
    phase = str(row.get("phase") or "").strip()
    if phase not in PHASES:
        raise TaosError("label phase must be one of {0}".format(", ".join(PHASES)))
    outcome = str(row.get("outcome") or "unknown").strip()
    if outcome not in OUTCOMES:
        raise TaosError("label outcome must be one of {0}".format(", ".join(OUTCOMES)))
    modality = str(row.get("modality") or "unknown").strip()
    if modality not in MODALITIES:
        raise TaosError("label modality must be one of {0}".format(", ".join(MODALITIES)))
    counterpart = row.get("counterpart")
    if counterpart in ("", "null", "none"):
        counterpart = None
    if counterpart is not None and counterpart not in AGENTS:
        raise TaosError("label counterpart must be codex or claude")
    agent = str(row.get("agent") or "").strip()
    if agent not in AGENTS:
        raise TaosError("label agent must be codex or claude")
    descriptor = truncate(strip_secrets(str(row.get("task") or task_id), secret_patterns), 80)
    return {
        "ts": utc_now(),
        "agent": agent,
        "task_id": task_id,
        "phase": phase,
        "outcome": outcome,
        "modality": modality,
        "task": descriptor,
        "counterpart": counterpart,
    }


def label(paths: Paths, **fields: Any) -> Dict[str, Any]:
    paths.ensure_state()
    row = sanitize(fields, config_mod.secret_patterns(paths))
    append_jsonl(paths.labels_file, row)
    return row


def rows(paths: Paths) -> List[Dict[str, Any]]:
    from .store import read_jsonl

    return read_jsonl(paths.labels_file)


def _cmd_label(args: argparse.Namespace, paths: Paths) -> int:
    row = label(
        paths,
        agent=args.agent,
        task_id=args.task_id,
        phase=args.phase,
        outcome=args.outcome,
        modality=args.modality,
        task=args.task,
        counterpart=args.counterpart,
    )
    print("labeled {0} {1}/{2}".format(row["task_id"], row["phase"], row["outcome"]))
    return 0


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("label", help="record one sanitized episode label")
    parser.add_argument("--agent", required=True, choices=list(AGENTS))
    parser.add_argument("--task-id", dest="task_id", required=True)
    parser.add_argument("--phase", required=True, choices=list(PHASES))
    parser.add_argument("--outcome", default="unknown", choices=list(OUTCOMES))
    parser.add_argument("--modality", default="unknown", choices=list(MODALITIES))
    parser.add_argument("--task", help="short sanitized descriptor")
    parser.add_argument("--counterpart", choices=list(AGENTS))
    parser.set_defaults(func=_cmd_label)
