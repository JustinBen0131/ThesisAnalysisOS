"""Gates: the commands that must pass before work is called reviewable.

The human configures them once (tests, lint, format). An agent runs them
with `taos gate run`; the result is recorded as evidence on the task, and
`taos finish --state review|done` refuses without a fresh pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config as config_mod
from . import events as events_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import age_hours, atomic_write_json, parse_ts, read_json, utc_now
from .util import TaosError

FRESH_HOURS = 24.0
TAIL_LINES = 25


def _gates_dir(paths: Paths) -> Path:
    directory = paths.state / "gates"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _workspace_for(paths: Paths, task: Dict[str, Any], override: Optional[str]) -> Path:
    """The task's worktree when it exists, else its workspace, else primary, else home."""
    if override:
        return Path(override).expanduser()
    if task.get("worktree") and Path(task["worktree"]).is_dir():
        return Path(task["worktree"])
    if task.get("workspace") and Path(task["workspace"]).is_dir():
        return Path(task["workspace"])
    config = config_mod.load_soft(paths)
    for workspace in config.get("workspaces") or []:
        if workspace.get("primary") and Path(workspace["path"]).is_dir():
            return Path(workspace["path"])
    return paths.home


def run(paths: Paths, *, task_id: str, agent: str, workspace: Optional[str] = None, timeout: int = 1800) -> Dict[str, Any]:
    gates = config_mod.gates(paths)
    if not gates:
        raise TaosError("no gates are configured. Add them to .taos/config.json under \"gates\".")
    store = tasks_mod.TaskStore(paths)
    task = store.get(task_id)
    cwd = _workspace_for(paths, task, workspace)
    if not cwd.is_dir():
        raise TaosError("gate workspace does not exist: {0}".format(cwd))

    results: List[Dict[str, Any]] = []
    ok = True
    for gate in gates:
        command = str(gate["command"])
        try:
            process = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            code = process.returncode
            tail = "\n".join((process.stdout + process.stderr).splitlines()[-TAIL_LINES:])
        except subprocess.TimeoutExpired:
            code = 124
            tail = "timed out after {0}s".format(timeout)
        results.append({"name": gate.get("name") or command, "command": command, "exit": code, "tail": tail})
        if code != 0:
            ok = False

    record = {
        "schema": "TAOS_GATE_RUN_V1",
        "task_id": task["id"],
        "agent": agent,
        "ran_at": utc_now(),
        "workspace": str(cwd),
        "ok": ok,
        "results": results,
    }
    stamp = parse_ts(record["ran_at"]).strftime("%Y%m%dT%H%M%SZ")
    path = _gates_dir(paths) / "{0}_{1}.json".format(task["id"], stamp)
    atomic_write_json(path, record)
    store.add_evidence(
        task["id"],
        paths.relative(path),
        agent,
        note="gates {0}".format("passed" if ok else "FAILED: " + ", ".join(r["name"] for r in results if r["exit"] != 0)),
    )
    events_mod.emit(paths, "gate_run", agent, task_id=task["id"], ok=ok, gates=[r["name"] for r in results])
    record["path"] = paths.relative(path)
    return record


def latest(paths: Paths, task_id: str) -> Optional[Dict[str, Any]]:
    directory = paths.state / "gates"
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("{0}_*.json".format(task_id)))
    if not files:
        return None
    data = read_json(files[-1], None)
    return data if isinstance(data, dict) else None


def fresh_pass(paths: Paths, task_id: str, hours: float = FRESH_HOURS) -> Optional[Dict[str, Any]]:
    record = latest(paths, task_id)
    if not record or not record.get("ok"):
        return None
    if age_hours(record.get("ran_at", utc_now())) > hours:
        return None
    return record


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace, paths: Paths) -> int:
    record = run(paths, task_id=args.task, agent=args.agent, workspace=args.workspace, timeout=args.timeout)
    for result in record["results"]:
        print("{0}  {1:<12} exit {2}".format("ok  " if result["exit"] == 0 else "FAIL", result["name"], result["exit"]))
        if result["exit"] != 0 and result["tail"]:
            print("    " + result["tail"].replace("\n", "\n    "))
    print("")
    print("gates {0} -> {1}".format("passed" if record["ok"] else "failed", record["path"]))
    return 0 if record["ok"] else 1


def _cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    record = latest(paths, args.task)
    if record is None:
        print("no gate runs for {0}".format(args.task))
        return 0
    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True))
        return 0
    print("{0}  {1}  {2}".format(record["ran_at"], "ok" if record["ok"] else "FAILED", record["workspace"]))
    for result in record["results"]:
        print("  {0:<12} exit {1}".format(result["name"], result["exit"]))
    return 0


def _cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    gates = config_mod.gates(paths)
    if not gates:
        print("no gates configured")
        return 0
    for gate in gates:
        print("{0:<12} {1}".format(gate.get("name") or "-", gate["command"]))
    return 0


def register(subparsers: Any) -> None:
    gate = subparsers.add_parser("gate", help="the commands that must pass before review")
    sub = gate.add_subparsers(dest="gate_cmd", required=True)

    runner = sub.add_parser("run", help="run every gate and record the result on the task")
    runner.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    runner.add_argument("--task", required=True)
    runner.add_argument("--workspace", help="run somewhere other than the task's worktree or the primary workspace")
    runner.add_argument("--timeout", type=int, default=1800)
    runner.set_defaults(func=_cmd_run)

    shower = sub.add_parser("show", help="the latest gate run for a task")
    shower.add_argument("--task", required=True)
    shower.add_argument("--json", action="store_true")
    shower.set_defaults(func=_cmd_show)

    lister = sub.add_parser("list", help="which gates are configured")
    lister.set_defaults(func=_cmd_list)
