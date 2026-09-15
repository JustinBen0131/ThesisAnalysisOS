"""The decision queue: the only correct way for an agent to ask the human."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from . import events as events_mod
from .paths import Paths
from .store import atomic_write_json, locked, read_json, utc_now
from .util import TaosError, short_id

DECISIONS_SCHEMA = "TAOS_DECISIONS_V1"


def _load(paths: Paths) -> Dict[str, Any]:
    data = read_json(paths.decisions_file)
    if not isinstance(data, dict) or "decisions" not in data:
        return {"schema": DECISIONS_SCHEMA, "decisions": []}
    return data


def _save(paths: Paths, data: Dict[str, Any]) -> None:
    data["schema"] = DECISIONS_SCHEMA
    atomic_write_json(paths.decisions_file, data)


def all_decisions(paths: Paths) -> List[Dict[str, Any]]:
    return list(_load(paths)["decisions"])


def open_decisions(paths: Paths, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    items = [d for d in all_decisions(paths) if d.get("status") == "open"]
    if task_id:
        items = [d for d in items if d.get("task_id") == str(task_id)]
    return items


def ask(paths: Paths, *, task_id: Optional[str], question: str, options: List[str], agent: str) -> Dict[str, Any]:
    question = str(question or "").strip()
    if not question:
        raise TaosError("a decision needs a question")
    from . import config as config_mod

    budget = int(config_mod.attention(paths).get("max_decisions_per_day") or 0)
    with locked(paths):
        data = _load(paths)
        today = utc_now()[:10]
        asked_today = [d for d in data["decisions"] if str(d.get("asked_at", "")).startswith(today)]
        over_budget = bool(budget) and len(asked_today) >= budget
        decision = {
            "id": short_id("dec_"),
            "task_id": str(task_id) if task_id else None,
            "question": question,
            "options": [str(o) for o in (options or [])],
            "asked_by": agent,
            "asked_at": utc_now(),
            "status": "open",
            "answer": None,
            "answered_by": None,
            "answered_at": None,
            "note": None,
            "over_budget": over_budget,
        }
        events_mod.emit(paths, "decision_ask", agent, decision_id=decision["id"], task_id=decision["task_id"], question=question, over_budget=over_budget)
        data["decisions"].append(decision)
        _save(paths, data)
        return decision


def answer(paths: Paths, *, decision_id: str, choice: str, by: str = "human", note: Optional[str] = None) -> Dict[str, Any]:
    with locked(paths):
        data = _load(paths)
        for decision in data["decisions"]:
            if decision.get("id") != str(decision_id):
                continue
            if decision.get("status") != "open":
                raise TaosError("decision {0} is already {1}".format(decision_id, decision.get("status")))
            options = decision.get("options") or []
            if options and str(choice) not in options:
                raise TaosError("choice must be one of: {0}".format(", ".join(options)))
            decision["status"] = "answered"
            decision["answer"] = str(choice)
            decision["answered_by"] = by
            decision["answered_at"] = utc_now()
            decision["note"] = str(note) if note else None
            events_mod.emit(paths, "decision_answer", by, decision_id=decision["id"], answer=str(choice))
            _save(paths, data)
            return decision
    raise TaosError("no such decision: {0}".format(decision_id))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_ask(args: argparse.Namespace, paths: Paths) -> int:
    decision = ask(paths, task_id=args.task, question=args.question, options=args.option or [], agent=args.agent)
    print("asked {0}: {1}".format(decision["id"], decision["question"]))
    print("answer it in the panel, or: taos decide answer {0} --choice <option>".format(decision["id"]))
    if decision.get("over_budget"):
        print("note: the daily decision budget is already spent. This one is queued below the line; "
              "keep working on what does not depend on it.")
    return 0


def _cmd_answer(args: argparse.Namespace, paths: Paths) -> int:
    decision = answer(paths, decision_id=args.decision_id, choice=args.choice, by=args.by, note=args.note)
    print("{0} answered: {1}".format(decision["id"], decision["answer"]))
    return 0


def _cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    items = open_decisions(paths, args.task)
    if args.json:
        print(json.dumps(items, indent=2, sort_keys=True))
        return 0
    if not items:
        print("no open decisions")
        return 0
    for decision in items:
        options = " | ".join(decision.get("options") or []) or "(free text)"
        print("{0}  {1}  {2}".format(decision["id"], decision.get("task_id") or "-", decision["question"]))
        print("    options: {0}".format(options))
    return 0


def register(subparsers: Any) -> None:
    decide = subparsers.add_parser("decide", help="ask the human, or answer")
    sub = decide.add_subparsers(dest="decide_cmd", required=True)

    asker = sub.add_parser("ask", help="queue a decision for the human")
    asker.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    asker.add_argument("--task")
    asker.add_argument("--question", required=True)
    asker.add_argument("--option", action="append")
    asker.set_defaults(func=_cmd_ask)

    answerer = sub.add_parser("answer", help="answer a queued decision")
    answerer.add_argument("decision_id")
    answerer.add_argument("--choice", required=True)
    answerer.add_argument("--note")
    answerer.add_argument("--by", default="human", choices=list(events_mod.AGENTS))
    answerer.set_defaults(func=_cmd_answer)

    listing = sub.add_parser("list", help="show open decisions")
    listing.add_argument("--task")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(func=_cmd_list)
