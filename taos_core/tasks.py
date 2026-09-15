"""The task store: stable ids, statuses, relations, evidence, hot state.

This is the only writer of `.taos/tasks.json` and `.taos/allocator.json`.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Optional

from . import config as config_mod
from . import events as events_mod
from .paths import Paths
from .store import atomic_write_json, locked, read_json, utc_now
from .util import TaosError

TASKS_SCHEMA = "TAOS_TASKS_V1"
ALLOCATOR_SCHEMA = "TAOS_ALLOCATOR_V1"

STATUSES = (
    "backlog",
    "next",
    "active",
    "blocked",
    "waiting",
    "review",
    "done",
    "canceled",
    "archived",
)
TERMINAL = ("done", "canceled", "archived")
PRIORITIES = ("P0", "P1", "P2", "P3")
ID_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}-[1-9][0-9]*$")
RELATION_TYPES = ("blocks", "blockedBy", "relatedTo")
INVERSE = {"blocks": "blockedBy", "blockedBy": "blocks", "relatedTo": "relatedTo"}
MUTABLE_FIELDS = ("title", "goal", "next_action", "priority", "parent_id", "labels", "branch", "done_when", "verification")
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _task_number(task_id: str) -> int:
    try:
        return int(str(task_id).rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


class TaskStore(object):
    def __init__(self, paths: Paths):
        self.paths = paths

    # -- raw access --------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        data = read_json(self.paths.tasks_file)
        if not isinstance(data, dict) or "tasks" not in data:
            return {"schema": TASKS_SCHEMA, "tasks": {}}
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        data["schema"] = TASKS_SCHEMA
        atomic_write_json(self.paths.tasks_file, data)

    def _allocator(self) -> Dict[str, Any]:
        data = read_json(self.paths.allocator_file)
        if not isinstance(data, dict) or "next" not in data:
            try:
                prefix = config_mod.prefix(self.paths)
            except TaosError:
                prefix = "TASK"
            data = {"schema": ALLOCATOR_SCHEMA, "prefix": prefix, "next": 1}
        return data

    def _allocate(self) -> str:
        allocator = self._allocator()
        number = int(allocator.get("next", 1))
        task_id = "{0}-{1}".format(allocator.get("prefix", "TASK"), number)
        allocator["next"] = number + 1
        allocator["schema"] = ALLOCATOR_SCHEMA
        allocator["updated_at"] = utc_now()
        atomic_write_json(self.paths.allocator_file, allocator)
        return task_id

    # -- reads -------------------------------------------------------------

    def get(self, task_id: str) -> Dict[str, Any]:
        task = self.load()["tasks"].get(str(task_id))
        if task is None:
            raise TaosError("no such task: {0}".format(task_id))
        return task

    def exists(self, task_id: str) -> bool:
        return str(task_id) in self.load()["tasks"]

    def list(self, status: Optional[str] = None, hot: Optional[bool] = None) -> List[Dict[str, Any]]:
        tasks = list(self.load()["tasks"].values())
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        if hot is not None:
            tasks = [t for t in tasks if bool(t.get("hot")) is bool(hot)]
        tasks.sort(
            key=lambda t: (
                0 if t.get("hot") else 1,
                _PRIORITY_ORDER.get(t.get("priority", "P2"), 2),
                _task_number(t.get("id", "")),
            )
        )
        return tasks

    def find(self, query: str) -> List[Dict[str, Any]]:
        needle = str(query).lower()
        hits = []
        for task in self.list():
            haystack = " ".join(
                [
                    str(task.get("id", "")),
                    str(task.get("title", "")),
                    str(task.get("goal", "")),
                    " ".join(task.get("labels") or []),
                ]
            ).lower()
            if needle in haystack:
                hits.append(task)
        return hits

    def blockers(self, task_id: str) -> List[str]:
        data = self.load()["tasks"]
        task = data.get(str(task_id))
        if task is None:
            return []
        open_blockers = []
        for other in task.get("relations", {}).get("blockedBy", []):
            candidate = data.get(other)
            if candidate is None or candidate.get("status") not in TERMINAL:
                open_blockers.append(other)
        parent = task.get("parent_id")
        if parent:
            parent_task = data.get(parent)
            if parent_task is not None and parent_task.get("status") == "blocked":
                open_blockers.append(parent)
        return sorted(set(open_blockers))

    # -- writes ------------------------------------------------------------

    def create(
        self,
        *,
        title: str,
        actor: str,
        goal: str = "",
        next_action: str = "",
        priority: str = "P2",
        parent_id: Optional[str] = None,
        labels: Optional[List[str]] = None,
        status: str = "next",
        done_when: str = "",
        verification: str = "",
    ) -> Dict[str, Any]:
        title = str(title).strip()
        if not title:
            raise TaosError("a task needs a title")
        if priority not in PRIORITIES:
            raise TaosError("priority must be one of {0}".format(", ".join(PRIORITIES)))
        if status not in STATUSES:
            raise TaosError("status must be one of {0}".format(", ".join(STATUSES)))
        with locked(self.paths):
            data = self.load()
            if parent_id and str(parent_id) not in data["tasks"]:
                raise TaosError("parent {0} does not exist".format(parent_id))
            task_id = self._allocate()
            now = utc_now()
            task = {
                "id": task_id,
                "title": title,
                "status": status,
                "priority": priority,
                "goal": str(goal or ""),
                "next_action": str(next_action or ""),
                "done_when": str(done_when or ""),
                "verification": str(verification or ""),
                "parent_id": str(parent_id) if parent_id else None,
                "labels": sorted(set(labels or [])),
                "branch": None,
                "workspace": None,
                "worktree": None,
                "relations": {"blocks": [], "blockedBy": [], "relatedTo": []},
                "owner_agent": None,
                "hot": False,
                "hot_since": None,
                "hot_reason": None,
                "created_at": now,
                "updated_at": now,
                "created_by": actor,
                "evidence": [],
                "comments": [],
                "sessions": [],
                "history": [{"ts": now, "from": None, "to": status, "reason": "created", "agent": actor}],
                "done_at": None,
                "canceled_at": None,
                "archived_at": None,
            }
            events_mod.emit(self.paths, "task_create", actor, task_id=task_id, title=title, status=status, priority=priority)
            data["tasks"][task_id] = task
            self._save(data)
            return task

    def update(self, task_id: str, fields: Dict[str, Any], actor: str) -> Dict[str, Any]:
        unknown = sorted(set(fields) - set(MUTABLE_FIELDS))
        if unknown:
            raise TaosError("not updatable: {0}. Allowed: {1}".format(", ".join(unknown), ", ".join(MUTABLE_FIELDS)))
        with locked(self.paths):
            data = self.load()
            task = data["tasks"].get(str(task_id))
            if task is None:
                raise TaosError("no such task: {0}".format(task_id))
            for key, value in fields.items():
                if key == "priority" and value not in PRIORITIES:
                    raise TaosError("priority must be one of {0}".format(", ".join(PRIORITIES)))
                if key == "parent_id":
                    if value in ("", "none", "null", None):
                        value = None
                    elif str(value) not in data["tasks"]:
                        raise TaosError("parent {0} does not exist".format(value))
                    elif str(value) == str(task_id):
                        raise TaosError("a task cannot be its own parent")
                if key == "labels" and isinstance(value, str):
                    value = [part.strip() for part in value.split(",") if part.strip()]
                if key == "labels":
                    value = sorted(set(value or []))
                task[key] = value
            task["updated_at"] = utc_now()
            events_mod.emit(self.paths, "task_update", actor, task_id=task["id"], fields=sorted(fields))
            self._save(data)
            return task

    def transition(
        self,
        task_id: str,
        to: str,
        reason: str,
        actor: str,
        evidence: Optional[str] = None,
        reopen: bool = False,
    ) -> Dict[str, Any]:
        if to not in STATUSES:
            raise TaosError("status must be one of {0}".format(", ".join(STATUSES)))
        if not str(reason or "").strip():
            raise TaosError("a transition needs a reason")
        with locked(self.paths):
            data = self.load()
            task = data["tasks"].get(str(task_id))
            if task is None:
                raise TaosError("no such task: {0}".format(task_id))
            current = task.get("status", "next")
            if current == to:
                raise TaosError("{0} is already {1}".format(task_id, to))
            if current in TERMINAL and not reopen:
                if not (current in ("done", "canceled") and to == "archived"):
                    raise TaosError(
                        "{0} is {1}. Reopen explicitly with --reopen --to next.".format(task_id, current)
                    )
            if current in TERMINAL and reopen and to not in ("next", "active", "backlog"):
                raise TaosError("reopening moves a task to next/active/backlog")
            if to == "archived" and current not in ("done", "canceled") and not reopen:
                raise TaosError("archive only a done or canceled task")
            if evidence:
                task.setdefault("evidence", []).append(
                    {"ts": utc_now(), "agent": actor, "ref": str(evidence), "note": str(reason)}
                )
            if to == "done" and not task.get("evidence"):
                raise TaosError(
                    "done needs evidence. Pass --evidence <path, commit, url or note>."
                )
            if to == "blocked" and len(str(reason).strip()) < 8:
                raise TaosError("a blocked reason must name the blocker")

            now = utc_now()
            task["status"] = to
            task["updated_at"] = now
            if to == "done":
                task["done_at"] = now
            if to == "canceled":
                task["canceled_at"] = now
            if to == "archived":
                task["archived_at"] = now
            if to in TERMINAL:
                task["hot"] = False
                task["hot_reason"] = "terminal:{0}".format(to)
            task.setdefault("history", []).append(
                {"ts": now, "from": current, "to": to, "reason": str(reason), "agent": actor}
            )
            events_mod.emit(
                self.paths,
                "task_transition",
                actor,
                task_id=task["id"],
                from_state=current,
                to_state=to,
                reason=str(reason),
                evidence=evidence,
            )
            self._save(data)
            return task

    def comment(
        self,
        task_id: str,
        body: str,
        agent: str,
        session: str,
        evidence: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not str(body or "").strip():
            raise TaosError("a comment needs a body")
        with locked(self.paths):
            data = self.load()
            task = data["tasks"].get(str(task_id))
            if task is None:
                raise TaosError("no such task: {0}".format(task_id))
            now = utc_now()
            task.setdefault("comments", []).append(
                {"ts": now, "agent": agent, "session": str(session or ""), "body": str(body)}
            )
            if evidence:
                task.setdefault("evidence", []).append(
                    {"ts": now, "agent": agent, "ref": str(evidence), "note": "comment"}
                )
            task["updated_at"] = now
            events_mod.emit(self.paths, "task_comment", agent, task_id=task["id"], session=str(session or ""))
            self._save(data)
            return task

    def add_evidence(
        self,
        task_id: str,
        ref: str,
        agent: str,
        note: str = "",
        depends_on: Optional[List[str]] = None,
        artifact: bool = False,
    ) -> Dict[str, Any]:
        if not str(ref or "").strip():
            raise TaosError("evidence needs a reference")
        with locked(self.paths):
            data = self.load()
            task = data["tasks"].get(str(task_id))
            if task is None:
                raise TaosError("no such task: {0}".format(task_id))
            now = utc_now()
            row: Dict[str, Any] = {"ts": now, "agent": agent, "ref": str(ref), "note": str(note or "")}
            if artifact or depends_on:
                # A reusable work product carries a small validity contract. Unknown
                # dependencies stay unknown: an empty list means "none declared", not "none".
                row["artifact"] = {
                    "depends_on": sorted(set(depends_on or [])),
                    "dependencies_known": bool(depends_on),
                    "valid": True,
                    "invalidated": None,
                    "producer": task["id"],
                }
            task.setdefault("evidence", []).append(row)
            task["updated_at"] = now
            events_mod.emit(self.paths, "task_update", agent, task_id=task["id"], fields=["evidence"])
            self._save(data)
            return task

    def invalidate_artifact(self, task_id: str, ref: str, reason: str, agent: str) -> Dict[str, Any]:
        """A known dependency changed: the artifact's consequences must be reconsidered."""
        if not str(reason or "").strip():
            raise TaosError("invalidation needs a reason naming what changed")
        with locked(self.paths):
            data = self.load()
            task = data["tasks"].get(str(task_id))
            if task is None:
                raise TaosError("no such task: {0}".format(task_id))
            hit = None
            for row in task.get("evidence", []):
                if row.get("ref") == str(ref) and isinstance(row.get("artifact"), dict):
                    hit = row
            if hit is None:
                raise TaosError("no artifact evidence {0!r} on {1}".format(ref, task_id))
            now = utc_now()
            hit["artifact"]["valid"] = False
            hit["artifact"]["invalidated"] = {"ts": now, "agent": agent, "reason": str(reason)}
            task["updated_at"] = now
            events_mod.emit(self.paths, "artifact_invalidate", agent, task_id=task["id"], ref=str(ref), reason=str(reason))
            self._save(data)
            return task

    def relate(
        self,
        task_id: str,
        kind: str,
        other_id: str,
        actor: str,
        remove: bool = False,
    ) -> Dict[str, Any]:
        if kind not in RELATION_TYPES:
            raise TaosError("relation must be one of {0}".format(", ".join(RELATION_TYPES)))
        if str(task_id) == str(other_id):
            raise TaosError("a task cannot relate to itself")
        with locked(self.paths):
            data = self.load()
            task = data["tasks"].get(str(task_id))
            other = data["tasks"].get(str(other_id))
            if task is None:
                raise TaosError("no such task: {0}".format(task_id))
            if other is None:
                raise TaosError("no such task: {0}".format(other_id))
            inverse = INVERSE[kind]
            forward = task.setdefault("relations", {}).setdefault(kind, [])
            backward = other.setdefault("relations", {}).setdefault(inverse, [])
            if remove:
                task["relations"][kind] = [x for x in forward if x != str(other_id)]
                other["relations"][inverse] = [x for x in backward if x != str(task_id)]
            else:
                if str(other_id) not in forward:
                    forward.append(str(other_id))
                    task["relations"][kind] = sorted(forward)
                if str(task_id) not in backward:
                    backward.append(str(task_id))
                    other["relations"][inverse] = sorted(backward)
            now = utc_now()
            task["updated_at"] = now
            other["updated_at"] = now
            events_mod.emit(
                self.paths,
                "task_relate",
                actor,
                task_id=task["id"],
                other_id=other["id"],
                kind=kind,
                removed=bool(remove),
            )
            self._save(data)
            return task

    def map_session(
        self,
        task_id: str,
        provider: str,
        session_key: str,
        title: str,
        actor: str,
    ) -> Dict[str, Any]:
        if not re.match(r"^[a-z0-9][a-z0-9._-]{2,79}$", str(session_key)):
            raise TaosError(
                "session key must be a slug like 'az7-fix-ssa' (lowercase, no spaces)"
            )
        with locked(self.paths):
            data = self.load()
            task = data["tasks"].get(str(task_id))
            if task is None:
                raise TaosError("no such task: {0}".format(task_id))
            sessions = task.setdefault("sessions", [])
            existing = [s for s in sessions if s.get("session_key") == str(session_key)]
            if not existing:
                sessions.append(
                    {
                        "ts": utc_now(),
                        "provider": str(provider),
                        "session_key": str(session_key),
                        "title": str(title),
                    }
                )
            task["owner_agent"] = str(provider)
            task["updated_at"] = utc_now()
            events_mod.emit(
                self.paths,
                "task_session_map",
                actor,
                task_id=task["id"],
                provider=str(provider),
                session_key=str(session_key),
            )
            self._save(data)
            return task

    def set_lane(
        self,
        task_id: str,
        *,
        workspace: Optional[str],
        worktree: Optional[str],
        actor: str,
    ) -> Dict[str, Any]:
        """Record where the work physically happens. Set once, then stable."""
        with locked(self.paths):
            data = self.load()
            task = data["tasks"].get(str(task_id))
            if task is None:
                raise TaosError("no such task: {0}".format(task_id))
            changed = []
            if workspace and not task.get("workspace"):
                task["workspace"] = str(workspace)
                changed.append("workspace")
            if worktree and not task.get("worktree"):
                task["worktree"] = str(worktree)
                changed.append("worktree")
            if changed:
                task["updated_at"] = utc_now()
                events_mod.emit(self.paths, "task_update", actor, task_id=task["id"], fields=changed)
                self._save(data)
            return task

    def set_hot(self, task_id: str, hot: bool, reason: str, actor: str) -> Dict[str, Any]:
        with locked(self.paths):
            data = self.load()
            task = data["tasks"].get(str(task_id))
            if task is None:
                raise TaosError("no such task: {0}".format(task_id))
            now = utc_now()
            if hot and task.get("status") in TERMINAL:
                raise TaosError("a {0} task cannot be hot".format(task.get("status")))
            task["hot"] = bool(hot)
            task["hot_reason"] = str(reason)
            task["hot_since"] = now if hot else None
            task["updated_at"] = now
            events_mod.emit(self.paths, "task_hot", actor, task_id=task["id"], hot=bool(hot), reason=str(reason))
            self._save(data)
            return task


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _print_task(task: Dict[str, Any], store: TaskStore) -> None:
    print("{0}  [{1}] {2}  {3}".format(task["id"], task["priority"], task["status"], task["title"]))
    if task.get("goal"):
        print("  goal:        {0}".format(task["goal"]))
    if task.get("next_action"):
        print("  next:        {0}".format(task["next_action"]))
    if task.get("done_when"):
        print("  done when:   {0}".format(task["done_when"]))
    if task.get("verification"):
        print("  verified by: {0}".format(task["verification"]))
    if task.get("parent_id"):
        print("  parent:      {0}".format(task["parent_id"]))
    if task.get("branch"):
        print("  branch:      {0}".format(task["branch"]))
    blockers = store.blockers(task["id"])
    if blockers:
        print("  blocked by:  {0}".format(", ".join(blockers)))
    if task.get("owner_agent"):
        print("  owner:       {0}".format(task["owner_agent"]))
    if task.get("labels"):
        print("  labels:      {0}".format(", ".join(task["labels"])))
    if task.get("hot"):
        print("  hot since:   {0} ({1})".format(task.get("hot_since"), task.get("hot_reason")))
    for item in task.get("evidence", [])[-5:]:
        print("  evidence:    {0}  {1}".format(item.get("ref"), item.get("note", "")))
    for item in task.get("comments", [])[-5:]:
        print("  {0} {1}: {2}".format(item.get("ts"), item.get("agent"), item.get("body")))


def _cmd_create(args: argparse.Namespace, paths: Paths) -> int:
    store = TaskStore(paths)
    task = store.create(
        title=args.title,
        actor=args.agent,
        goal=args.goal or "",
        next_action=args.next_action or "",
        priority=args.priority,
        parent_id=args.parent,
        labels=args.label or [],
        status=args.status,
        done_when=args.done_when or "",
        verification=args.verification or "",
    )
    print(task["id"] if args.json else "created {0}: {1}".format(task["id"], task["title"]))
    return 0


def _cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    store = TaskStore(paths)
    task = store.get(args.task_id)
    if args.json:
        print(json.dumps(task, indent=2, sort_keys=True))
    else:
        _print_task(task, store)
    return 0


def _cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    store = TaskStore(paths)
    tasks = store.list(status=args.status, hot=True if args.hot else None)
    if args.json:
        print(json.dumps(tasks, indent=2, sort_keys=True))
        return 0
    if not tasks:
        print("no tasks")
        return 0
    for task in tasks:
        flag = "*" if task.get("hot") else " "
        print(
            "{0}{1:<10} {2:<3} {3:<9} {4}".format(
                flag, task["id"], task["priority"], task["status"], task["title"]
            )
        )
    return 0


def _cmd_find(args: argparse.Namespace, paths: Paths) -> int:
    store = TaskStore(paths)
    tasks = store.find(args.query)
    if args.json:
        print(json.dumps(tasks, indent=2, sort_keys=True))
        return 0
    for task in tasks:
        print("{0:<10} {1:<9} {2}".format(task["id"], task["status"], task["title"]))
    if not tasks:
        print("nothing matched {0!r}".format(args.query))
    return 0


def _cmd_update(args: argparse.Namespace, paths: Paths) -> int:
    fields: Dict[str, Any] = {}
    for pair in args.set:
        if "=" not in pair:
            raise TaosError("--set takes key=value, got {0!r}".format(pair))
        key, value = pair.split("=", 1)
        fields[key.strip()] = value
    task = TaskStore(paths).update(args.task_id, fields, args.agent)
    print("updated {0}".format(task["id"]))
    return 0


def _cmd_transition(args: argparse.Namespace, paths: Paths) -> int:
    task = TaskStore(paths).transition(
        args.task_id, args.to, args.reason, args.agent, evidence=args.evidence, reopen=args.reopen
    )
    print("{0} -> {1}".format(task["id"], task["status"]))
    return 0


def _cmd_comment(args: argparse.Namespace, paths: Paths) -> int:
    TaskStore(paths).comment(args.task_id, args.body, args.agent, args.session, evidence=args.evidence)
    print("commented on {0}".format(args.task_id))
    return 0


def _cmd_evidence(args: argparse.Namespace, paths: Paths) -> int:
    TaskStore(paths).add_evidence(
        args.task_id, args.ref, args.agent, note=args.note or "",
        depends_on=args.depends_on or None, artifact=bool(args.artifact),
    )
    print("evidence added to {0}".format(args.task_id))
    return 0


def _cmd_invalidate(args: argparse.Namespace, paths: Paths) -> int:
    TaskStore(paths).invalidate_artifact(args.task_id, args.ref, args.reason, args.agent)
    print("artifact {0} on {1} marked invalid".format(args.ref, args.task_id))
    return 0


def _cmd_relate(args: argparse.Namespace, paths: Paths) -> int:
    TaskStore(paths).relate(args.task_id, args.kind, args.other_id, args.agent, remove=args.remove)
    verb = "unlinked" if args.remove else "linked"
    print("{0} {1} {2} {3}".format(verb, args.task_id, args.kind, args.other_id))
    return 0


def _cmd_map_session(args: argparse.Namespace, paths: Paths) -> int:
    TaskStore(paths).map_session(args.task_id, args.provider, args.session_key, args.title, args.agent)
    print("mapped {0} -> {1}/{2}".format(args.task_id, args.provider, args.session_key))
    return 0


def _cmd_hot(args: argparse.Namespace, paths: Paths) -> int:
    hot = bool(args.on)
    TaskStore(paths).set_hot(args.task_id, hot, args.reason, args.agent)
    print("{0} hot={1}".format(args.task_id, hot))
    return 0


def register(subparsers: Any) -> None:
    task = subparsers.add_parser("task", help="create and move work")
    sub = task.add_subparsers(dest="task_cmd", required=True)

    create = sub.add_parser("create", help="create a task")
    create.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    create.add_argument("--title", required=True)
    create.add_argument("--goal", help="what finishing this unlocks")
    create.add_argument("--next-action", dest="next_action", help="the exact next step")
    create.add_argument("--priority", default="P2", choices=list(PRIORITIES))
    create.add_argument("--parent", help="parent task id")
    create.add_argument("--label", action="append")
    create.add_argument("--status", default="next", choices=["next", "backlog"])
    create.add_argument("--done-when", dest="done_when", help="the observable closure condition")
    create.add_argument("--verification", help="how closure will be established")
    create.add_argument("--json", action="store_true")
    create.set_defaults(func=_cmd_create)

    show = sub.add_parser("show", help="show one task")
    show.add_argument("task_id")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=_cmd_show)

    listing = sub.add_parser("list", help="list tasks")
    listing.add_argument("--status", choices=list(STATUSES))
    listing.add_argument("--hot", action="store_true")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(func=_cmd_list)

    find = sub.add_parser("find", help="search tasks")
    find.add_argument("query")
    find.add_argument("--json", action="store_true")
    find.set_defaults(func=_cmd_find)

    update = sub.add_parser("update", help="edit task fields")
    update.add_argument("task_id")
    update.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    update.add_argument("--set", action="append", required=True, metavar="key=value",
                        help="keys: title goal next_action priority parent_id labels branch")
    update.set_defaults(func=_cmd_update)

    transition = sub.add_parser("transition", help="change status")
    transition.add_argument("task_id")
    transition.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    transition.add_argument("--to", required=True, choices=list(STATUSES))
    transition.add_argument("--reason", required=True)
    transition.add_argument("--evidence")
    transition.add_argument("--reopen", action="store_true")
    transition.set_defaults(func=_cmd_transition)

    comment = sub.add_parser("comment", help="add an attributed comment")
    comment.add_argument("task_id")
    comment.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    comment.add_argument("--session", required=True)
    comment.add_argument("--body", required=True)
    comment.add_argument("--evidence")
    comment.set_defaults(func=_cmd_comment)

    evidence = sub.add_parser("evidence", help="attach evidence")
    evidence.add_argument("task_id")
    evidence.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    evidence.add_argument("--ref", required=True)
    evidence.add_argument("--note")
    evidence.add_argument("--artifact", action="store_true", help="a reusable work product, with a validity contract")
    evidence.add_argument("--depends-on", dest="depends_on", action="append", help="a known input the artifact depends on")
    evidence.set_defaults(func=_cmd_evidence)

    invalidate = sub.add_parser("invalidate", help="mark an artifact invalid because a dependency changed")
    invalidate.add_argument("task_id")
    invalidate.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    invalidate.add_argument("--ref", required=True)
    invalidate.add_argument("--reason", required=True)
    invalidate.set_defaults(func=_cmd_invalidate)

    relate = sub.add_parser("relate", help="link two tasks")
    relate.add_argument("task_id")
    relate.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    relate.add_argument("kind", choices=list(RELATION_TYPES))
    relate.add_argument("other_id")
    relate.add_argument("--remove", action="store_true")
    relate.set_defaults(func=_cmd_relate)

    mapping = sub.add_parser("map-session", help="bind a chat session to a task")
    mapping.add_argument("task_id")
    mapping.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    mapping.add_argument("--provider", required=True, choices=["codex", "claude"])
    mapping.add_argument("--session-key", dest="session_key", required=True)
    mapping.add_argument("--title", required=True)
    mapping.set_defaults(func=_cmd_map_session)

    hot = sub.add_parser("hot", help="add or remove a task from the hot rail")
    hot.add_argument("task_id")
    hot.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    group = hot.add_mutually_exclusive_group(required=True)
    group.add_argument("--on", action="store_true")
    group.add_argument("--off", action="store_true")
    hot.add_argument("--reason", required=True)
    hot.set_defaults(func=_cmd_hot)
