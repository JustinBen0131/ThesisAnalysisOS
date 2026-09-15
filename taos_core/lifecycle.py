"""start / finish / capsule: the three verbs an agent actually uses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import claims as claims_mod
from . import config as config_mod
from . import decisions as decisions_mod
from . import events as events_mod
from . import gates as gates_mod
from . import handoff as handoff_mod
from . import kernels as kernels_mod
from . import projections as projections_mod
from . import tasks as tasks_mod
from . import telemetry as telemetry_mod
from .paths import Paths
from .util import TaosError, slugify

START_STATES = ("backlog", "next", "waiting", "review", "blocked")


def _safe_label(paths: Paths, **fields: Any) -> None:
    try:
        telemetry_mod.label(paths, **fields)
    except TaosError:
        pass


def _pick_workspace(paths: Paths, agent: str) -> Optional[Dict[str, Any]]:
    """The workspace this agent should use: its own lane first, then primary."""
    workspaces = config_mod.load_soft(paths).get("workspaces") or []
    for workspace in workspaces:
        if workspace.get("agent") == agent:
            return workspace
    for workspace in workspaces:
        if workspace.get("primary") and workspace.get("agent") in (None, "", "any"):
            return workspace
    for workspace in workspaces:
        if workspace.get("agent") in (None, "", "any"):
            return workspace
    return None


def lane_for(paths: Paths, task: Dict[str, Any], agent: str) -> Dict[str, Any]:
    """Where the agent works for this task, per the configured git discipline."""
    git = config_mod.git_settings(paths)
    prefix = config_mod.load_soft(paths).get("project", {}).get("prefix", "TASK")
    slug = slugify(task.get("title", ""), 34)
    if len(slug) >= 34 and "-" in slug:
        slug = slug.rsplit("-", 1)[0]
    branch = task.get("branch") or str(git.get("branch_pattern") or "{prefix_lower}/{id_lower}-{slug}").format(
        prefix=prefix,
        prefix_lower=prefix.lower(),
        id=task["id"],
        id_lower=task["id"].lower(),
        slug=slug,
        agent=agent,
    )
    workspace = _pick_workspace(paths, agent)
    workspace_path = task.get("workspace") or (workspace["path"] if workspace else None)
    isolation = str(git.get("isolation") or "branch")
    worktree = task.get("worktree")
    commands: List[str] = []

    if isolation == "worktree" and workspace_path:
        root = git.get("worktree_root") or str(Path(workspace_path).parent / (Path(workspace_path).name + "-worktrees"))
        worktree = worktree or str(Path(root) / "{0}-{1}".format(task["id"].lower(), slug))
        commands.append("git -C {0} worktree add {1} -b {2}".format(workspace_path, worktree, branch))
        commands.append("cd {0}".format(worktree))
    elif isolation == "branch" and workspace_path:
        commands.append("cd {0}".format(workspace_path))
        commands.append("git switch -c {0}".format(branch))
    elif isolation == "fork" and workspace_path:
        commands.append("cd {0}".format(workspace_path))
        commands.append("git switch -c {0}".format(branch))
    elif isolation == "trunk" and workspace_path:
        commands.append("cd {0}".format(workspace_path))
        branch = None

    return {
        "isolation": isolation,
        "workspace": workspace_path,
        "workspace_agent": (workspace or {}).get("agent"),
        "branch": branch,
        "worktree": worktree,
        "protected_branches": list(git.get("protected_branches") or []),
        "merge_policy": git.get("merge_policy"),
        "commands": commands,
    }


def start(
    paths: Paths,
    *,
    agent: str,
    task_id: str,
    session_label: str,
    extra_scopes: Optional[List[str]] = None,
    stale_after_hours: Optional[float] = None,
    takeover: bool = False,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    store = tasks_mod.TaskStore(paths)
    task = store.get(task_id)

    session_key = slugify(session_label)
    if len(session_key) < 3:
        session_key = slugify("{0}-{1}".format(task["id"], session_key or agent))
    store.map_session(task["id"], agent, session_key, session_label, agent)

    lane = lane_for(paths, task, agent)
    scopes = ["task:{0}".format(task["id"])] + list(extra_scopes or [])
    if lane.get("branch"):
        scopes.append("branch:{0}".format(lane["branch"]))
    if lane.get("worktree"):
        scopes.append("path:{0}".format(lane["worktree"]))
    elif lane.get("workspace") and lane.get("workspace_agent") in (agent,):
        scopes.append("path:{0}".format(lane["workspace"]))

    claims_mod.ClaimStore(paths).acquire(
        agent=agent,
        scopes=scopes,
        session_label=session_label,
        stale_after_hours=stale_after_hours,
        takeover=takeover,
        reason=reason,
    )

    fields: Dict[str, Any] = {}
    if lane.get("branch") and not task.get("branch"):
        fields["branch"] = lane["branch"]
    if fields:
        store.update(task["id"], fields, agent)
    # worktree/workspace are recorded outside MUTABLE_FIELDS on purpose: set directly, evented.
    if (lane.get("worktree") and not task.get("worktree")) or (lane.get("workspace") and not task.get("workspace")):
        store.set_lane(task["id"], workspace=lane.get("workspace"), worktree=lane.get("worktree"), actor=agent)

    task = store.get(task["id"])
    if task.get("status") in START_STATES and task.get("status") != "active":
        blockers = store.blockers(task["id"])
        if task.get("status") == "blocked" and blockers:
            raise TaosError(
                "{0} is blocked by {1}. Clear or re-point the blocker before starting.".format(
                    task["id"], ", ".join(blockers)
                )
            )
        store.transition(task["id"], "active", "started by {0}".format(agent), agent)

    store.set_hot(task["id"], True, "started by {0}".format(agent), agent)
    from . import control as control_mod

    control = None
    try:
        control = control_mod.open_episode(paths, store.get(task["id"]), store.blockers(task["id"]), agent)
    except TaosError:
        control = None
    projections_mod.refresh(paths)
    _safe_label(
        paths,
        agent=agent,
        task_id=slugify(task["id"] + "-" + task.get("title", "")),
        phase="start",
        modality="code",
        task=task.get("title", ""),
    )
    data = capsule(paths, task["id"])
    data["lane"] = lane
    data["control"] = control
    return data


def finish(
    paths: Paths,
    *,
    agent: str,
    task_id: str,
    state: str,
    reason: str,
    evidence: Optional[str],
    session_label: str,
    handoff_file: Optional[Path] = None,
    to_agent: Optional[str] = None,
    comment: Optional[str] = None,
    skip_gates: bool = False,
) -> Dict[str, Any]:
    store = tasks_mod.TaskStore(paths)
    task = store.get(task_id)

    if state in ("review", "done") and config_mod.gates(paths):
        if not gates_mod.fresh_pass(paths, task["id"]):
            if not skip_gates:
                raise TaosError(
                    "{0} has no passing gate run in the last {1:.0f}h. Run `taos gate run --agent {2} --task {0}` "
                    "first, or pass --skip-gates with a reason that names why.".format(
                        task["id"], gates_mod.FRESH_HOURS, agent
                    )
                )
            store.add_evidence(task["id"], "gates skipped", agent, note=reason)

    if comment:
        store.comment(task["id"], comment, agent, session_label, evidence=None)

    handoff_path = None
    if handoff_file is not None:
        if not to_agent:
            raise TaosError("--handoff-file needs --to <codex|claude>")
        body = Path(handoff_file).read_text(encoding="utf-8")
        handoff_path = handoff_mod.write(
            paths,
            task_id=task["id"],
            from_agent=agent,
            to_agent=to_agent,
            body=body,
            session=session_label,
        )

    task = store.transition(task["id"], state, reason, agent, evidence=evidence)

    from . import control as control_mod

    control_result = None
    try:
        control_result = control_mod.close_episode(paths, task, agent)
    except TaosError:
        control_result = None

    claim_store = claims_mod.ClaimStore(paths)
    released = claim_store.release_by_scope("task:{0}".format(task["id"]), agent)

    if task.get("status") in tasks_mod.TERMINAL:
        phase = "done"
    elif handoff_path is not None:
        phase = "handoff"
    else:
        phase = "iterate"
    _safe_label(
        paths,
        agent=agent,
        task_id=slugify(task["id"] + "-" + task.get("title", "")),
        phase=phase,
        outcome="landed" if task.get("status") == "done" else "unknown",
        modality="code",
        task=task.get("title", ""),
        counterpart=to_agent if to_agent in ("codex", "claude") else None,
    )
    projections_mod.refresh(paths)

    return {
        "task": task,
        "state": task.get("status"),
        "released_claims": [c.get("id") for c in released],
        "handoff": str(handoff_path) if handoff_path else None,
        "wrapper": handoff_mod.wrapper(handoff_path, to_agent) if handoff_path and to_agent else None,
        "control": control_result,
    }


def capsule(paths: Paths, task_id: str) -> Dict[str, Any]:
    store = tasks_mod.TaskStore(paths)
    task = store.get(task_id)
    all_tasks = store.load()["tasks"]

    live_claims = [
        claim
        for claim in claims_mod.ClaimStore(paths).live()
        if any(scope == "task:{0}".format(task["id"]) for scope in claim.get("scopes", []))
    ]
    handoff_path = handoff_mod.latest(paths, task["id"])
    handoff_head = ""
    if handoff_path is not None:
        lines = handoff_path.read_text(encoding="utf-8").splitlines()
        handoff_head = "\n".join(lines[:40])

    related = []
    for kind in tasks_mod.RELATION_TYPES:
        for other in task.get("relations", {}).get(kind, []):
            other_task = all_tasks.get(other)
            related.append(
                {
                    "kind": kind,
                    "id": other,
                    "title": other_task.get("title", "") if other_task else "(missing)",
                    "status": other_task.get("status", "") if other_task else "missing",
                }
            )

    return {
        "task": task,
        "blockers": store.blockers(task["id"]),
        "claims": live_claims,
        "decisions": decisions_mod.open_decisions(paths, task["id"]),
        "related": related,
        "handoff_path": str(handoff_path) if handoff_path else None,
        "handoff_head": handoff_head,
        "kernels": kernels_mod.freshness(paths),
        "gates": {"configured": [g.get("name") or g["command"] for g in config_mod.gates(paths)], "latest": gates_mod.latest(paths, task["id"])},
        "next_action": task.get("next_action", ""),
    }


def capsule_text(data: Dict[str, Any]) -> str:
    task = data["task"]
    lines = [
        "{0}  [{1}] {2}  {3}".format(task["id"], task["priority"], task["status"], task["title"]),
    ]
    if task.get("goal"):
        lines.append("goal:      {0}".format(task["goal"]))
    lines.append("next:      {0}".format(data.get("next_action") or "(none recorded, set one)"))
    lane = data.get("lane") or {}
    if lane.get("workspace") or task.get("workspace"):
        lines.append("workspace: {0}".format(lane.get("workspace") or task.get("workspace")))
    if lane.get("worktree") or task.get("worktree"):
        lines.append("worktree:  {0}".format(lane.get("worktree") or task.get("worktree")))
    if lane.get("branch") or task.get("branch"):
        lines.append("branch:    {0}".format(lane.get("branch") or task.get("branch")))
    if lane.get("commands"):
        lines.append("work here:")
        for command in lane["commands"]:
            lines.append("  {0}".format(command))
        if lane.get("protected_branches"):
            lines.append("  never commit on: {0}".format(", ".join(lane["protected_branches"])))
    if data.get("control"):
        from . import control as control_mod

        lines.append(control_mod.control_line(data["control"]))
    gates = data.get("gates") or {}
    if gates.get("configured"):
        latest = gates.get("latest")
        if latest:
            lines.append("gates:     last run {0} {1}".format(latest.get("ran_at"), "passed" if latest.get("ok") else "FAILED"))
        else:
            lines.append("gates:     {0} (not run yet; required before review)".format(", ".join(gates["configured"])))
    if data.get("blockers"):
        lines.append("blocked by: {0}".format(", ".join(data["blockers"])))
    for claim in data.get("claims", []):
        lines.append("claim:     {0} by {1} ({2})".format(claim.get("id"), claim.get("agent"), claim.get("session_label")))
    for decision in data.get("decisions", []):
        lines.append("DECISION OWED: {0} {1}".format(decision.get("id"), decision.get("question")))
    for item in data.get("related", []):
        lines.append("{0:<10} {1} {2} ({3})".format(item["kind"], item["id"], item["title"], item["status"]))
    for item in task.get("evidence", [])[-5:]:
        lines.append("evidence:  {0}  {1}".format(item.get("ref"), item.get("note", "")))
    for item in task.get("comments", [])[-5:]:
        lines.append("{0} {1}: {2}".format(item.get("ts"), item.get("agent"), item.get("body")))
    stale_kernels = [k["name"] for k in data.get("kernels", []) if k.get("status") != "fresh"]
    if stale_kernels:
        lines.append("kernels needing refresh: {0}".format(", ".join(stale_kernels)))
    if data.get("handoff_path"):
        lines.append("")
        lines.append("latest handoff: {0}".format(data["handoff_path"]))
        lines.append(data.get("handoff_head", ""))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_start(args: argparse.Namespace, paths: Paths) -> int:
    data = start(
        paths,
        agent=args.agent,
        task_id=args.task,
        session_label=args.session,
        extra_scopes=args.scope or [],
        takeover=args.takeover,
        reason=args.reason,
    )
    print(capsule_text(data))
    return 0


def _cmd_finish(args: argparse.Namespace, paths: Paths) -> int:
    result = finish(
        paths,
        agent=args.agent,
        task_id=args.task,
        state=args.state,
        reason=args.reason,
        evidence=args.evidence,
        session_label=args.session,
        handoff_file=Path(args.handoff_file) if args.handoff_file else None,
        to_agent=args.to,
        comment=args.comment,
        skip_gates=args.skip_gates,
    )
    print("{0} -> {1}".format(result["task"]["id"], result["state"]))
    if result.get("released_claims"):
        print("released claims: {0}".format(", ".join(result["released_claims"])))
    if result.get("control"):
        control = result["control"]
        print("control:   episode closed, j={0} {1}".format(control["j"], "clean" if control["clean"] else "not clean"))
    if result.get("wrapper"):
        print("")
        print(result["wrapper"])
    return 0


def _cmd_capsule(args: argparse.Namespace, paths: Paths) -> int:
    data = capsule(paths, args.task_id)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(capsule_text(data))
    return 0


def register(subparsers: Any) -> None:
    start_parser = subparsers.add_parser("start", help="claim a task and begin work")
    start_parser.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    start_parser.add_argument("--task", required=True)
    start_parser.add_argument("--session", required=True, help='label like "AZ-7 | fix ssa pass"')
    start_parser.add_argument("--scope", action="append", help="extra claim scope, e.g. path:compiler/ssa")
    start_parser.add_argument("--takeover", action="store_true")
    start_parser.add_argument("--reason")
    start_parser.set_defaults(func=_cmd_start)

    finish_parser = subparsers.add_parser("finish", help="close out and release the claim")
    finish_parser.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    finish_parser.add_argument("--task", required=True)
    finish_parser.add_argument(
        "--state", required=True, choices=["review", "done", "blocked", "waiting", "next"]
    )
    finish_parser.add_argument("--reason", required=True)
    finish_parser.add_argument("--evidence")
    finish_parser.add_argument("--session", required=True)
    finish_parser.add_argument("--handoff-file", dest="handoff_file")
    finish_parser.add_argument("--to", choices=["codex", "claude", "human"])
    finish_parser.add_argument("--comment")
    finish_parser.add_argument("--skip-gates", dest="skip_gates", action="store_true",
                               help="finish without a passing gate run; the reason is recorded as evidence")
    finish_parser.set_defaults(func=_cmd_finish)

    capsule_parser = subparsers.add_parser("capsule", help="everything you need to resume a task")
    capsule_parser.add_argument("task_id")
    capsule_parser.add_argument("--json", action="store_true")
    capsule_parser.set_defaults(func=_cmd_capsule)
