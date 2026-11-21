"""Gates: the commands that must pass before work is called reviewable.

The human configures them once (tests, lint, a numerical check). An agent
runs them with `taos gate run`. Each result is recorded with what it stood
on: the files it depends on and its own definition. Later, the result holds
for exactly as long as those are the same. A pass from last month still holds
if nothing it tested has changed; a pass from a minute ago is stale if a file
was edited since.

A gate may name the domains it depends on (`"depends_on": ["inputs", "code"]`,
with the domains declared under `"basis"` in the config). Then a change
elsewhere leaves it standing, and a change that no domain claims makes it
unknown. A gate that depends on something no file records (a service, the
clock) can say `"max_age_hours"`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import basis
from . import config as config_mod
from . import events as events_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import age_hours, atomic_write_json, canonical_json, locked, parse_ts, read_json, sha256_text, utc_now
from .util import TaosError

TAIL_LINES = 25
KNOWN = "gate_results.json"   # every check result, filed under the check and the bytes it read
KEEP_KNOWN = 500


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


def _settings(paths: Paths) -> Dict[str, Any]:
    value = config_mod.load_soft(paths).get("basis")
    return value if isinstance(value, dict) else {}


def _name(gate: Dict[str, Any]) -> str:
    return str(gate.get("name") or gate["command"])


def _depends(gate: Dict[str, Any]) -> Optional[List[str]]:
    value = gate.get("depends_on")
    return sorted({str(item) for item in value}) if isinstance(value, list) and value else None


def _definition(gate: Dict[str, Any], settings: Dict[str, Any]) -> str:
    return sha256_text(canonical_json({"command": str(gate["command"]), "depends_on": _depends(gate), "basis": settings}))


def _where(paths: Paths, task: Dict[str, Any], record: Optional[Dict[str, Any]]) -> Path:
    """Where the work is now: the task's own lane, else where it was last checked."""
    own = task.get("worktree") or task.get("workspace")
    if own and Path(own).is_dir():
        return Path(own)
    if record and record.get("workspace") and Path(record["workspace"]).is_dir():
        return Path(record["workspace"])
    return _workspace_for(paths, task, None)


def _key(definition: str, digests: Dict[str, str]) -> str:
    """A check and the exact bytes it reads. Two tasks asking the same question of the same files share the answer."""
    return sha256_text(canonical_json([definition, digests]))


def _known(paths: Paths) -> Dict[str, Any]:
    data = read_json(paths.state / KNOWN, None)
    return data if isinstance(data, dict) else {}


def _judge(gate: Dict[str, Any], result: Dict[str, Any], own: bool) -> Dict[str, Any]:
    """A result that ran on the files as they are now: is it a pass, and is it inside any limit the gate sets?"""
    limit = gate.get("max_age_hours")
    if isinstance(limit, (int, float)) and age_hours(result["ran_at"]) > float(limit):
        return basis.verdict(basis.STALE, "older than its limit of {0:g} h".format(limit))
    if result.get("exit") != 0:
        return basis.verdict(basis.FAILS, "exit {0} on the files as they are now".format(result.get("exit")))
    whose = "" if own or not result.get("task") else " for {0}".format(result["task"])
    return basis.verdict(basis.HOLDS, "passed {0}{1}; nothing it tested has changed".format(result["ran_at"], whose))


def latest(paths: Paths, task_id: str) -> Optional[Dict[str, Any]]:
    directory = paths.state / "gates"
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("{0}_*.json".format(task_id)))
    if not files:
        return None
    data = read_json(files[-1], None)
    return data if isinstance(data, dict) else None


def standing(paths: Paths, task_id: str, snap: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """One verdict per configured gate: has it passed on the files as they are now?

    A result belongs to the bytes it tested, not to the task that asked. When
    this exact check has run on exactly these files, that result is the
    answer, whichever task ran it. Otherwise the task's own last run says
    what has changed since.
    """
    gates = config_mod.gates(paths)
    if not gates:
        return []
    task = tasks_mod.TaskStore(paths).get(task_id)
    record = latest(paths, task["id"])
    settings = _settings(paths)
    if snap is None:
        snap = basis.snapshot(_where(paths, task, record), settings)
    results = {result.get("name"): result for result in (record or {}).get("results", [])}
    kept = (record or {}).get("snapshot") or {}
    known = _known(paths) if snap.get("complete") else {}
    out = []
    for gate in gates:
        shared = known.get(_key(_definition(gate, settings), basis.digests(snap, _depends(gate)))) if known else None
        result = shared or results.get(_name(gate))
        undeclared = sorted(set(_depends(gate) or []) - set(settings.get("domains") or {}))
        if undeclared:
            verdict = basis.verdict(basis.UNKNOWN, "it depends on {0}, which basis.domains in the config does not declare".format(
                ", ".join(undeclared)))
        elif shared is not None:
            verdict = _judge(gate, shared, shared.get("task") == task["id"])
        elif record is None:
            verdict = basis.verdict(basis.UNKNOWN, "never run for this task")
        elif result is None:
            verdict = basis.verdict(basis.UNKNOWN, "not part of the latest run")
        elif "basis" not in result:
            verdict = basis.verdict(basis.UNKNOWN, "recorded before results were bound to what they tested; run it again")
        elif not kept.get("complete", True):
            verdict = basis.verdict(basis.UNKNOWN, kept.get("reason") or "the workspace could not be read when it ran")
        elif result.get("definition") != _definition(gate, settings):
            verdict = basis.verdict(basis.STALE, "the check itself changed since it ran")
        else:
            verdict = basis.compare(result["basis"], snap, listed=kept, declared=_depends(gate) is not None)
            if verdict["state"] != basis.HOLDS:
                pass
            elif result.get("changed_during_run"):
                verdict = basis.verdict(basis.UNKNOWN, "files it depends on changed while it ran: {0}".format(
                    ", ".join(result["changed_during_run"][:basis.NAMED])))
            else:
                verdict = _judge(gate, result, True)
        verdict["gate"] = _name(gate)
        verdict["ran_at"] = result.get("ran_at") if result else None
        verdict["result"] = result if verdict["state"] == basis.HOLDS else None
        out.append(verdict)
    return out


def fresh_pass(paths: Paths, task_id: str, hours: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """The latest run, if every configured gate still holds. `hours` is accepted and ignored: age is not validity."""
    verdicts = standing(paths, task_id)
    if not verdicts or any(verdict["state"] != basis.HOLDS for verdict in verdicts):
        return None
    return latest(paths, task_id)


def run(paths: Paths, *, task_id: str, agent: str, workspace: Optional[str] = None, timeout: int = 1800,
        force: bool = False) -> Dict[str, Any]:
    """Run the gates that need running. A gate whose last pass still holds is reused, and the record says so."""
    gates = config_mod.gates(paths)
    if not gates:
        raise TaosError("no gates are configured. Add them to .taos/config.json under \"gates\".")
    store = tasks_mod.TaskStore(paths)
    task = store.get(task_id)
    cwd = _workspace_for(paths, task, workspace)
    if not cwd.is_dir():
        raise TaosError("gate workspace does not exist: {0}".format(cwd))

    settings = _settings(paths)
    before = basis.snapshot(cwd, settings)
    held = {} if force else {v["gate"]: v["result"] for v in standing(paths, task["id"], snap=before) if v.get("result")}

    results: List[Dict[str, Any]] = []
    ran: List[Dict[str, Any]] = []
    for gate in gates:
        name = _name(gate)
        if name in held:
            result = dict(held[name])   # this exact check already ran on exactly these files
            result.setdefault("tail", "")
            result["reused_from"] = result.get("reused_from") or result["ran_at"]
            results.append(result)
            continue
        command = str(gate["command"])
        try:
            process = subprocess.run(command, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
            code = process.returncode
            tail = "\n".join((process.stdout + process.stderr).splitlines()[-TAIL_LINES:])
        except subprocess.TimeoutExpired:
            code = 124
            tail = "timed out after {0}s".format(timeout)
        result = {"name": name, "command": command, "exit": code, "tail": tail, "ran_at": utc_now(),
                  "depends_on": _depends(gate), "definition": _definition(gate, settings),
                  "basis": basis.digests(before, _depends(gate))}
        results.append(result)
        ran.append(result)

    if ran:
        after = basis.snapshot(cwd, settings)
        for result in ran:
            moved: List[str] = []
            for domain in result["basis"]:
                old, new = before["domains"].get(domain), after["domains"].get(domain)
                if (old or {}).get("sha256") != (new or {}).get("sha256"):
                    moved.extend(basis.differences(old, new) or [domain])
            if moved:
                result["changed_during_run"] = sorted(set(moved))

    ok = all(result["exit"] == 0 for result in results)
    reused = [result["name"] for result in results if result not in ran]
    record = {
        "schema": "TAOS_GATE_RUN_V2",
        "task_id": task["id"],
        "agent": agent,
        "ran_at": utc_now(),
        "workspace": str(cwd),
        "ok": ok,
        "results": results,
        "reused": reused,
        "snapshot": before,
    }
    stamp = parse_ts(record["ran_at"]).strftime("%Y%m%dT%H%M%SZ")
    path = _gates_dir(paths) / "{0}_{1}.json".format(task["id"], stamp)
    serial = 1
    while path.exists():   # two runs in one second must not overwrite each other
        serial += 1
        path = _gates_dir(paths) / "{0}_{1}_{2}.json".format(task["id"], stamp, serial)
    atomic_write_json(path, record)
    if ran and before.get("complete"):
        with locked(paths):
            known = _known(paths)
            for result in ran:
                if not result.get("changed_during_run"):
                    entry = {key: value for key, value in result.items() if key != "tail"}
                    entry.update(task=task["id"], receipt=paths.relative(path))
                    known[_key(result["definition"], result["basis"])] = entry
            newest = sorted(known, key=lambda key: str(known[key].get("ran_at")))[-KEEP_KNOWN:]
            atomic_write_json(paths.state / KNOWN, {key: known[key] for key in newest})
    note = "gates {0}".format("passed" if ok else "FAILED: " + ", ".join(r["name"] for r in results if r["exit"] != 0))
    if reused:
        note += " (reused, unchanged: {0})".format(", ".join(reused))
    store.add_evidence(task["id"], paths.relative(path), agent, note=note)
    events_mod.emit(paths, "gate_run", agent, task_id=task["id"], ok=ok, gates=[r["name"] for r in results], reused=reused)
    record["path"] = paths.relative(path)
    return record


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace, paths: Paths) -> int:
    record = run(paths, task_id=args.task, agent=args.agent, workspace=args.workspace, timeout=args.timeout, force=args.force)
    for result in record["results"]:
        if result["name"] in record["reused"]:
            print("held  {0:<12} not rerun: nothing it tested has changed since {1}".format(result["name"], result["reused_from"]))
            continue
        print("{0}  {1:<12} exit {2}".format("ok  " if result["exit"] == 0 else "FAIL", result["name"], result["exit"]))
        if result["exit"] != 0 and result["tail"]:
            print("    " + result["tail"].replace("\n", "\n    "))
    print("")
    print("gates {0} -> {1}".format("passed" if record["ok"] else "failed", record["path"]))
    return 0 if record["ok"] else 1


def _cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    record = latest(paths, args.task)
    verdicts = standing(paths, args.task)
    if args.json:
        lean = [{key: value for key, value in verdict.items() if key != "result"} for verdict in verdicts]
        print(json.dumps({"latest": record, "standing": lean}, indent=2, sort_keys=True))
        return 0
    if record is None:
        print("no gate runs for {0}".format(args.task))
    else:
        print("{0}  {1}  {2}".format(record["ran_at"], "ok" if record["ok"] else "FAILED", record["workspace"]))
    for verdict in verdicts:
        print("  {0:<12} {1:<8} {2}".format(verdict["gate"], verdict["state"], verdict["reason"]))
    return 0


def _cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    gates = config_mod.gates(paths)
    if not gates:
        print("no gates configured")
        return 0
    for gate in gates:
        depends = _depends(gate)
        print("{0:<12} {1}{2}".format(gate.get("name") or "-", gate["command"],
                                     "   depends on: " + ", ".join(depends) if depends else ""))
    return 0


def register(subparsers: Any) -> None:
    gate = subparsers.add_parser("gate", help="the commands that must pass before review")
    sub = gate.add_subparsers(dest="gate_cmd", required=True)

    runner = sub.add_parser("run", help="run the gates that need it and record what each result stood on")
    runner.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    runner.add_argument("--task", required=True)
    runner.add_argument("--workspace", help="run somewhere other than the task's worktree or the primary workspace")
    runner.add_argument("--timeout", type=int, default=1800)
    runner.add_argument("--force", action="store_true", help="rerun even the gates whose last pass still holds")
    runner.set_defaults(func=_cmd_run)

    shower = sub.add_parser("show", help="the latest gate run for a task, and whether each result still holds")
    shower.add_argument("--task", required=True)
    shower.add_argument("--json", action="store_true")
    shower.set_defaults(func=_cmd_show)

    lister = sub.add_parser("list", help="which gates are configured")
    lister.set_defaults(func=_cmd_list)
