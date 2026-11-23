"""Lessons: a correction that meets the next agent at the moment it applies.

A note in a memory file is read only by whoever thinks to open it. A lesson
carries the principal's own words, the mistake, why it mattered and where it
applies, and it is printed at the decision point where the mistake would
repeat. Lessons report; they never block.

Two different things are recorded, and never added together. Showing a
lesson is an exposure. Making the mistake again is a repeat, and it is
counted only when someone records it with evidence. Whether a lesson works
is read from its repeats over its exposures, not from how often it fired.
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


RESULTS = ("followed", "violated")


def _lineage(paths: Paths, task_id: str) -> List[str]:
    """A task id and its ancestors, nearest first. An id TAOS does not know has no ancestors."""
    from . import tasks as tasks_mod

    tasks = tasks_mod.TaskStore(paths).load()["tasks"]
    chain, seen = [], set()
    current: Optional[str] = str(task_id)
    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        current = (tasks.get(current) or {}).get("parent_id")
    return chain


def _in_scope(paths: Paths, lesson: Dict[str, Any], task_id: Optional[str]) -> bool:
    """`*`, one task, an ancestor of the task, or a project prefix (`AZ` covers `AZ-7`). Never a bare string prefix."""
    scope = lesson.get("scope") or "*"
    if scope == "*":
        return True
    if task_id is None:
        return False
    lineage = _lineage(paths, task_id)
    return scope in lineage or any(item.startswith(scope + "-") for item in lineage)


def _case(moment: str, task_id: Optional[str], text: Optional[str]) -> str:
    """One situation, however many times it is looked at: the same moment, task and text."""
    return "case_" + sha256_text(canonical_json([moment, task_id, text or ""]))[:12]


def at(paths: Paths, moment: str, *, agent: str, task_id: Optional[str] = None, text: Optional[str] = None,
       case: Optional[str] = None) -> List[Dict[str, Any]]:
    """The lessons that apply at this moment. Never raises on a match.

    Showing a lesson is an exposure and is logged as one, once per case. It
    says the lesson was delivered. It says nothing about whether the work
    was right; that is recorded separately with `outcome`.
    """
    if moment not in MOMENTS:
        raise TaosError("unknown moment {0!r}; use one of: {1}".format(moment, ", ".join(MOMENTS)))
    case = str(case or _case(moment, task_id, text))
    log = sci.science_dir(paths) / "lesson_hits.jsonl"
    seen = {(row.get("lesson_id"), row.get("case")) for row in read_jsonl(log)}
    hits = []
    for lesson in all_lessons(paths):
        if moment not in lesson["moments"] or not _in_scope(paths, lesson, task_id):
            continue
        patterns = lesson.get("detect") or []
        if patterns and not any(re.search(pattern, text or "", flags=re.I) for pattern in patterns):
            continue
        hits.append(dict(lesson, case=case))
        if (lesson["id"], case) not in seen:
            append_jsonl(log, {"ts": utc_now(), "lesson_id": lesson["id"], "moment": moment, "agent": agent,
                               "task_id": task_id, "case": case})
    return hits


def outcome(paths: Paths, lesson_id: str, case: str, result: str, *, by: str, evidence: str) -> Dict[str, Any]:
    """Record what happened in a case where a lesson applied: it was followed, or the mistake was made again.

    A violation needs evidence and counts whoever reports it. "Followed" is
    counted only when someone other than the agent that did the work says
    so; an agent's word about its own work is kept, and labelled as that.
    """
    if result not in RESULTS:
        raise TaosError("result must be one of: {0}".format(", ".join(RESULTS)))
    sci.find(all_lessons(paths, include_retired=True), lesson_id, "lesson")
    shown = [row for row in read_jsonl(sci.science_dir(paths) / "lesson_hits.jsonl")
             if row.get("lesson_id") == lesson_id and row.get("case") == str(case)]
    actor = shown[0].get("agent") if shown else None
    row = {"ts": utc_now(), "lesson_id": lesson_id, "case": str(case), "result": result, "by": by,
           "evidence": sci.need(evidence, "the evidence for this outcome"), "was_shown": bool(shown),
           "source": "self-reported" if by == actor else "adjudicated"}
    append_jsonl(sci.science_dir(paths) / "lesson_outcomes.jsonl", row)
    events_mod.emit(paths, "lesson_outcome", by, lesson_id=lesson_id, case=str(case), result=result)
    return row


def repeats(paths: Paths) -> List[Dict[str, Any]]:
    """Per lesson: how often it was shown, and how often the mistake was confirmed again.

    `repeats` counts confirmed violations only. `exposures` is the number of
    distinct cases the lesson was shown in, and `unknown` is how many of
    those nobody has adjudicated. A lesson shown a hundred times for correct
    work has a hundred exposures and no repeats.
    """
    shown = read_jsonl(sci.science_dir(paths) / "lesson_hits.jsonl")
    judged = read_jsonl(sci.science_dir(paths) / "lesson_outcomes.jsonl")
    table = []
    for lesson in all_lessons(paths, include_retired=True):
        mine = [row for row in shown if row.get("lesson_id") == lesson["id"]]
        cases = {row.get("case") or "legacy_{0}".format(index) for index, row in enumerate(mine)}
        latest: Dict[str, Dict[str, Any]] = {}
        for row in judged:
            if row.get("lesson_id") == lesson["id"]:
                latest[row["case"]] = row
        violated = [row for row in latest.values() if row["result"] == "violated"]
        followed = [row for row in latest.values() if row["result"] == "followed" and row.get("source") == "adjudicated"]
        table.append({"id": lesson["id"], "title": lesson["title"], "status": lesson["status"],
                      "exposures": len(cases), "repeats": len(violated), "followed": len(followed),
                      "self_reported": sum(1 for row in latest.values() if row.get("source") == "self-reported" and row["result"] == "followed"),
                      "unknown": len(cases - set(latest)),
                      "first": mine[0]["ts"] if mine else None, "last": mine[-1]["ts"] if mine else None})
    return sorted(table, key=lambda row: (-row["repeats"], -row["exposures"]))


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
    hits = at(paths, args.moment, agent=args.agent, task_id=args.task, text=text, case=args.case)
    if args.json:
        print(json.dumps(hits, indent=2, sort_keys=True))
        return 0
    if not hits:
        print("no lesson applies at {0}".format(args.moment))
    for lesson in hits:
        print("{0}  {1}  [{2}, {3}]".format(lesson["id"], lesson["title"], lesson["status"], lesson["case"]))
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
        print("{0:>3} repeated, {1} followed, {2} not judged, of {3} times shown  {4}  {5}".format(
            row["repeats"], row["followed"], row["unknown"], row["exposures"], row["id"], row["title"]))
    return 0


def _cmd_outcome(args: argparse.Namespace, paths: Paths) -> int:
    row = outcome(paths, args.lesson_id, args.case, args.result, by=args.by, evidence=args.evidence)
    print("{0} in {1}: {2} ({3})".format(args.lesson_id, args.case, row["result"], row["source"]))
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
    lesson = subparsers.add_parser("lesson", help="turn a correction into a reminder shown when it applies")
    sub = lesson.add_subparsers(dest="lesson_cmd", required=True)
    agents = subparsers.actors

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
    moment.add_argument("--case", help="a stable id for this situation; by default it is derived from the moment, task and text")
    moment.add_argument("--json", action="store_true")
    moment.set_defaults(func=_cmd_at)

    rep = sub.add_parser("repeats", help="per lesson: times shown, and times the mistake was confirmed again")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=_cmd_repeats)

    judged = sub.add_parser("outcome", help="record whether a lesson was followed or violated in one case")
    judged.add_argument("lesson_id")
    judged.add_argument("--case", required=True, help="the case id printed by `lesson at`")
    judged.add_argument("--result", required=True, choices=list(RESULTS))
    judged.add_argument("--by", required=True, choices=agents)
    judged.add_argument("--evidence", required=True)
    judged.set_defaults(func=_cmd_outcome)

    freezer = sub.add_parser("freeze", help="write a hashed held-out copy")
    freezer.add_argument("label")
    freezer.add_argument("--by", default="human", choices=agents)
    freezer.set_defaults(func=_cmd_freeze)

    status = sub.add_parser("status", help="set candidate, active or retired")
    status.add_argument("lesson_id")
    status.add_argument("status", choices=["candidate", "active", "retired"])
    status.add_argument("--by", default="human", choices=agents)
    status.set_defaults(func=_cmd_status)
