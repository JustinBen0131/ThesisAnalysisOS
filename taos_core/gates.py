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

A gate may say `"isolated": true`. Then it runs in an empty folder that holds
only the files its result is filed under. A file it did not declare is not
there to be read, so the result cannot be reused wrongly, and what the check
writes is discarded. It also sees a fixed environment, and where the machine
can do it (macOS today) the network and the rest of the workspace are closed
to it. The record says which of these were in force. A gate that says
`"isolated": "strict"` does not run where they cannot all be.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def _isolation(gate: Dict[str, Any]) -> Any:
    """How far a gate asks to be closed off: None, True, or "strict"."""
    value = gate.get("isolated")
    return value if value is True or value == "strict" else None


def _definition(gate: Dict[str, Any], settings: Dict[str, Any]) -> str:
    said: Dict[str, Any] = {"command": str(gate["command"]), "depends_on": _depends(gate), "basis": settings}
    if _isolation(gate):
        said["isolated"] = _isolation(gate)     # a run in the open workspace does not answer for an isolated check
    return sha256_text(canonical_json(said))


def _execute(command: str, cwd: Path, timeout: int, env: Optional[Dict[str, str]] = None,
             prefix: Optional[List[str]] = None) -> Tuple[int, str]:
    try:
        if prefix:
            process = subprocess.run(prefix + ["/bin/sh", "-c", command], cwd=str(cwd), env=env, capture_output=True,
                                     text=True, timeout=timeout)
        else:
            process = subprocess.run(command, shell=True, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timed out after {0}s".format(timeout)
    return process.returncode, "\n".join((process.stdout + process.stderr).splitlines()[-TAIL_LINES:])


KEPT = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "SYSTEMROOT", "COMSPEC", "PATHEXT")   # what a command needs in order to start
SANDBOX = "/usr/bin/sandbox-exec"
_CLOSES: Dict[str, bool] = {}


def _fixed_environment(home: Path, tmp: Path) -> Dict[str, str]:
    """What an isolated check sees of the environment: where programs are, the locale, an empty home.

    A variable the check needs is written into its command (`SEED=7 python3 fit.py`),
    where it is part of what the check is, so changing it asks the question again.
    """
    env = {name: os.environ[name] for name in KEPT if name in os.environ}
    env.update({"HOME": str(home), "TMPDIR": str(tmp), "TMP": str(tmp), "TEMP": str(tmp)})
    return env


def _closed(workspace: Path, scratch: Path) -> Optional[List[str]]:
    """The command prefix that closes the network and the workspace outside `scratch`, where this machine has one.

    macOS has one. The interpreter and the folders on PATH may lie inside the
    workspace (a virtual environment), so those stay readable.
    """
    if sys.platform != "darwin" or not os.access(SANDBOX, os.X_OK):
        return None
    real = os.path.realpath
    shut = real(str(workspace))
    opened = {real(str(scratch))}
    for entry in [sys.prefix, sys.base_prefix] + os.environ.get("PATH", "").split(os.pathsep):
        path = real(entry) if entry else ""
        if path.startswith(shut + os.sep):
            opened.add(path)
            if os.path.dirname(path) != shut:
                opened.add(os.path.dirname(path))      # `.venv/bin` needs `.venv`
    quoted = lambda path: '(subpath "{0}")'.format(path.replace("\\", "\\\\").replace('"', '\\"'))  # noqa: E731
    return [SANDBOX, "-p", "(version 1)(allow default)(deny network*)(deny file-read-data {0})(allow file-read-data {1})".format(
        quoted(shut), " ".join(quoted(path) for path in sorted(opened)))]


TRIAL = """import socket, sys
reached = []
try:
    open(sys.argv[1]).read()
    reached.append("file")
except OSError:
    pass
try:
    socket.create_connection(("127.0.0.1", int(sys.argv[2])), timeout=2).close()
    reached.append("network")
except OSError:
    pass
print("reached", *reached)
"""


def closes() -> bool:
    """Whether that prefix really closes both, found once by trying: a file outside, and a socket that is listening."""
    if "answer" not in _CLOSES:
        outside, inside = Path(tempfile.mkdtemp(prefix="taos-outside-")), Path(tempfile.mkdtemp(prefix="taos-inside-"))
        listener = socket.socket()
        try:
            prefix = _closed(outside, inside)
            (outside / "canary").write_text("canary\n", encoding="utf-8")
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            done = prefix and subprocess.run(
                prefix + [sys.executable, "-c", TRIAL, str(outside / "canary"), str(listener.getsockname()[1])],
                cwd=str(inside), capture_output=True, text=True, timeout=30)
            _CLOSES["answer"] = bool(done) and done.returncode == 0 and done.stdout.strip() == "reached"
        except (OSError, subprocess.SubprocessError):
            _CLOSES["answer"] = False
        finally:
            listener.close()
            shutil.rmtree(str(outside), ignore_errors=True)
            shutil.rmtree(str(inside), ignore_errors=True)
    return _CLOSES["answer"]


def _isolated(cwd: Path, snap: Dict[str, Any], filed: Dict[str, str], command: str, timeout: int,
              strict: bool = False) -> Tuple[int, str, List[str]]:
    """Run a check where only the files its result is filed under exist.

    A result is reused for as long as the bytes it is filed under are the
    same. That is sound only if the check could read nothing else. Here it is
    made true: those files are placed in an empty folder, by hard link where
    the filesystem allows and by copy otherwise, and the check runs there. A
    file it did not declare is not there to be read. What it writes is
    discarded: a check is a question, not a step that produces files.

    Three more ways to read something else are closed where they can be. The
    environment is fixed everywhere. The network and the rest of the workspace
    (reached by its absolute path) are closed where the machine has a way,
    which `closes()` finds by trying. Returns the exit code, the tail, and
    what was closed, so the record never says more than was in force.
    """
    if not snap.get("complete"):
        return 125, "cannot isolate: {0}".format(snap.get("reason") or "the workspace could not be read"), []
    names: List[str] = []
    for domain in filed:
        entry = (snap.get("domains") or {}).get(domain)
        if entry and entry.get("files") is None:
            return 125, "cannot isolate: {0} holds {1} files, too many to place; split the domain".format(domain, entry.get("count")), []
        names.extend((entry or {}).get("files") or {})
    root = Path(tempfile.mkdtemp(prefix="taos-isolated-"))
    scratch, home, tmp = root / "work", root / "home", root / "tmp"
    prefix = _closed(cwd, root) if closes() else None
    if prefix is None and strict:
        shutil.rmtree(str(root), ignore_errors=True)
        return 125, "cannot isolate strictly: this machine has no way to close the network and the rest of the workspace", []
    closed = ["files", "environment"] + (["network", "workspace"] if prefix else [])
    try:
        for folder in (scratch, home, tmp):
            folder.mkdir()
        for name in sorted(set(names)):
            target = scratch / name
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(str(cwd / name), str(target))
            except OSError:
                shutil.copy2(str(cwd / name), str(target))
        code, tail = _execute(command, scratch, timeout, env=_fixed_environment(home, tmp), prefix=prefix)
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
    if code != 0:
        called = {basis.UNDECLARED: "the files no domain claims", basis.WORKSPACE: "the files git lists in the workspace"}
        there = [name for name in sorted(filed, key=lambda name: (name in called, name))
                 if ((snap.get("domains") or {}).get(name) or {}).get("count")]
        named = ", ".join(name for name in there if name not in called)
        rest = " and ".join(called[name] for name in there if name in called)
        tail = (tail + "\n" if tail else "") + ("isolated: it could read only {0}. A file it could not find is one "
                                                "it did not declare.").format(" and ".join(part for part in (named, rest) if part) or "nothing")
        tail += "\nalso closed to it: " + ", ".join(["the environment"] + (["the network", "the rest of the workspace"] if prefix else []))
    return code, tail, closed


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
    how = " with only the files it declared present" if result.get("isolated") else ""
    if "network" in (result.get("closed") or []):
        how += ", and the network and the rest of the workspace closed"
    return basis.verdict(basis.HOLDS, "passed {0}{1}{2}; nothing it tested has changed".format(result["ran_at"], whose, how))


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
        filed = basis.digests(before, _depends(gate))
        closed: List[str] = []
        if _isolation(gate):
            code, tail, closed = _isolated(cwd, before, filed, command, timeout, strict=_isolation(gate) == "strict")
        else:
            code, tail = _execute(command, cwd, timeout)
        result = {"name": name, "command": command, "exit": code, "tail": tail, "ran_at": utc_now(),
                  "depends_on": _depends(gate), "definition": _definition(gate, settings), "basis": filed}
        if _isolation(gate):
            result["isolated"] = True
            result["closed"] = closed
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
        print("{0:<12} {1}{2}{3}".format(gate.get("name") or "-", gate["command"],
                                        "   depends on: " + ", ".join(depends) if depends else "",
                                        "   isolated" + (" (strict)" if _isolation(gate) == "strict" else "") if _isolation(gate) else ""))
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
