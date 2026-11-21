"""Lessons: a correction that meets the next agent at the moment it applies.

A note in a memory file is read only by whoever thinks to open it. A lesson
carries the principal's own words, the mistake, why it mattered and where it
applies, and it is printed at the decision point where the mistake would
repeat. Lessons report; they never block. Every match is logged, so whether a
lesson works is counted by its repeats, not assumed.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Optional

from . import _science as sci
from . import events as events_mod
from .paths import Paths
from .store import append_jsonl, atomic_write_json, canonical_json, locked, read_jsonl, sha256_text, utc_now
from .util import TaosError, short_id, slugify

MOMENTS = ("join", "question", "stop", "statement", "reply", "post", "submit", "product", "delete", "install")


def all_lessons(paths: Paths, include_retired: bool = False) -> List[Dict[str, Any]]:
    items = sci.load(paths, "lessons", "lessons")["lessons"]
    return [item for item in items if include_retired or item.get("status") != "retired"]


def add(
    paths: Paths,
    *,
    title: str,
    words: str,
    said_on: str,
    mistake: str,
    why: str,
    moments: List[str],
    scope: str = "*",
    detect: Optional[List[str]] = None,
    by: str = "human",
) -> Dict[str, Any]:
    unknown = [moment for moment in moments if moment not in MOMENTS]
    if unknown or not moments:
        raise TaosError("moments must come from: {0}".format(", ".join(MOMENTS)))
    for pattern in detect or []:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise TaosError("bad detect pattern {0!r}: {1}".format(pattern, exc))
    lesson = {
        "id": short_id("les_"),
        "title": sci.need(title, "a title"),
        "words": sci.need(words, "the principal's own words"),
        "said_on": sci.need(said_on, "the date the words were said"),
        "mistake": sci.need(mistake, "the mistake"),
        "why": sci.need(why, "why it mattered"),
        "moments": list(moments),
        "scope": str(scope or "*"),
        "detect": list(detect or []),
        "status": "candidate",
        "added_at": utc_now(),
        "added_by": by,
    }
    with locked(paths):
        data = sci.load(paths, "lessons", "lessons")
        data["lessons"].append(lesson)
        sci.save(paths, "lessons", data)
        events_mod.emit(paths, "lesson_add", by, lesson_id=lesson["id"], title=lesson["title"])
    return lesson


def _in_scope(lesson: Dict[str, Any], task_id: Optional[str]) -> bool:
    scope = lesson.get("scope") or "*"
    return scope == "*" or (task_id is not None and str(task_id).startswith(scope))


def at(paths: Paths, moment: str, *, agent: str, task_id: Optional[str] = None, text: Optional[str] = None) -> List[Dict[str, Any]]:
    """The lessons that apply at this moment. Logs one hit per match. Never raises on a match."""
    if moment not in MOMENTS:
        raise TaosError("unknown moment {0!r}; use one of: {1}".format(moment, ", ".join(MOMENTS)))
    hits = []
    for lesson in all_lessons(paths):
        if moment not in lesson["moments"] or not _in_scope(lesson, task_id):
            continue
        patterns = lesson.get("detect") or []
        if patterns and not any(re.search(pattern, text or "", flags=re.I) for pattern in patterns):
            continue
        hits.append(lesson)
        append_jsonl(sci.science_dir(paths) / "lesson_hits.jsonl",
                     {"ts": utc_now(), "lesson_id": lesson["id"], "moment": moment, "agent": agent, "task_id": task_id})
    return hits


def repeats(paths: Paths) -> List[Dict[str, Any]]:
    """Hits per lesson. A lesson that keeps firing has not been learned."""
    rows = read_jsonl(sci.science_dir(paths) / "lesson_hits.jsonl")
    table = []
    for lesson in all_lessons(paths, include_retired=True):
        mine = [row for row in rows if row.get("lesson_id") == lesson["id"]]
        table.append({"id": lesson["id"], "title": lesson["title"], "status": lesson["status"], "hits": len(mine),
                      "first": mine[0]["ts"] if mine else None, "last": mine[-1]["ts"] if mine else None})
    return sorted(table, key=lambda row: -row["hits"])


def freeze(paths: Paths, label: str, by: str = "human") -> Dict[str, Any]:
    """Write a hashed copy of the current lessons, to hold out as a test set."""
    lessons = all_lessons(paths)
    digest = sha256_text(canonical_json(lessons))
    target = sci.science_dir(paths) / "frozen" / (slugify(label) + ".json")
    if target.exists():
        raise TaosError("a frozen set named {0} already exists; frozen sets are never rewritten".format(label))
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target, {"label": label, "frozen_at": utc_now(), "sha256": digest, "lessons": lessons})
    events_mod.emit(paths, "lesson_freeze", by, label=label, sha256=digest, count=len(lessons))
    return {"label": label, "sha256": digest, "count": len(lessons), "path": str(target)}


def set_status(paths: Paths, lesson_id: str, status: str, by: str = "human") -> Dict[str, Any]:
    if status not in ("candidate", "active", "retired"):
        raise TaosError("status must be candidate, active or retired")
    with locked(paths):
        data = sci.load(paths, "lessons", "lessons")
        lesson = sci.find(data["lessons"], lesson_id, "lesson")
        lesson["status"] = status
        sci.save(paths, "lessons", data)
        events_mod.emit(paths, "lesson_status", by, lesson_id=lesson_id, status=status)
    return lesson


# --------------------------------------------------------------------------


def _cmd_add(args: argparse.Namespace, paths: Paths) -> int:
    lesson = add(paths, title=args.title, words=args.words, said_on=args.said_on, mistake=args.mistake, why=args.why,
                 moments=args.moment or [], scope=args.scope, detect=args.detect, by=args.by)
    print("added {0} as a candidate: {1}".format(lesson["id"], lesson["title"]))
    return 0


def _cmd_at(args: argparse.Namespace, paths: Paths) -> int:
    text = args.text
    if args.text_file:
        with open(args.text_file, encoding="utf-8") as handle:
            text = handle.read()
    hits = at(paths, args.moment, agent=args.agent, task_id=args.task, text=text)
    if args.json:
        print(json.dumps(hits, indent=2, sort_keys=True))
        return 0
    if not hits:
        print("no lesson applies at {0}".format(args.moment))
    for lesson in hits:
        print("{0}  {1}".format(lesson["id"], lesson["title"]))
        print("    said {0}: \"{1}\"".format(lesson["said_on"], lesson["words"]))
        print("    the mistake: {0}".format(lesson["mistake"]))
        print("    why it mattered: {0}".format(lesson["why"]))
    return 0  # report only: a lesson informs the decision, it does not make it


def _cmd_repeats(args: argparse.Namespace, paths: Paths) -> int:
    table = repeats(paths)
    if args.json:
        print(json.dumps(table, indent=2, sort_keys=True))
        return 0
    for row in table:
        print("{0:>4} hits  {1}  {2}".format(row["hits"], row["id"], row["title"]))
    return 0


def _cmd_freeze(args: argparse.Namespace, paths: Paths) -> int:
    result = freeze(paths, args.label, args.by)
    print("froze {0} lessons as {1}  sha256 {2}".format(result["count"], result["label"], result["sha256"]))
    return 0


def _cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    lesson = set_status(paths, args.lesson_id, args.status, args.by)
    print("{0} is now {1}".format(lesson["id"], lesson["status"]))
    return 0


def register(subparsers: Any) -> None:
    lesson = subparsers.add_parser("lesson", help="corrections that report at the moment they apply")
    sub = lesson.add_subparsers(dest="lesson_cmd", required=True)
    agents = list(events_mod.AGENTS)

    adder = sub.add_parser("add", help="turn a correction into a lesson")
    adder.add_argument("--title", required=True)
    adder.add_argument("--words", required=True, help="the principal's own words, verbatim")
    adder.add_argument("--said-on", required=True, help="YYYY-MM-DD")
    adder.add_argument("--mistake", required=True)
    adder.add_argument("--why", required=True, help="why it mattered")
    adder.add_argument("--moment", action="append", choices=list(MOMENTS))
    adder.add_argument("--scope", default="*", help="task id prefix, or * for everywhere")
    adder.add_argument("--detect", action="append", help="regular expression that must match the text")
    adder.add_argument("--by", default="human", choices=agents)
    adder.set_defaults(func=_cmd_add)

    moment = sub.add_parser("at", help="print the lessons that apply now (always exits 0)")
    moment.add_argument("moment", choices=list(MOMENTS))
    moment.add_argument("--agent", required=True, choices=agents)
    moment.add_argument("--task")
    moment.add_argument("--text")
    moment.add_argument("--text-file")
    moment.add_argument("--json", action="store_true")
    moment.set_defaults(func=_cmd_at)

    rep = sub.add_parser("repeats", help="hits per lesson")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=_cmd_repeats)

    freezer = sub.add_parser("freeze", help="write a hashed held-out copy")
    freezer.add_argument("label")
    freezer.add_argument("--by", default="human", choices=agents)
    freezer.set_defaults(func=_cmd_freeze)

    status = sub.add_parser("status", help="set candidate, active or retired")
    status.add_argument("lesson_id")
    status.add_argument("status", choices=["candidate", "active", "retired"])
    status.add_argument("--by", default="human", choices=agents)
    status.set_defaults(func=_cmd_status)
