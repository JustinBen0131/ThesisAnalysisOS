"""The doctor: mechanical health. Green does not mean the work is right."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List

from . import atoms as atoms_mod
from . import claims as claims_mod
from . import config as config_mod
from . import kernels as kernels_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import age_days, read_json, read_jsonl
from .util import TaosError

VERSION = "1.0.0"


def _check(name: str, status: str, detail: str) -> Dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def run(paths: Paths) -> Dict[str, Any]:
    checks: List[Dict[str, str]] = []

    if not paths.constructed():
        return {
            "ok": False,
            "checks": [_check("config", "fail", config_mod.NOT_CONSTRUCTED)],
        }

    try:
        config = config_mod.load(paths)
        problems = config_mod.validate(config)
        checks.append(
            _check("config", "pass" if not problems else "fail", "; ".join(problems) or "valid")
        )
    except TaosError as exc:
        return {"ok": False, "checks": [_check("config", "fail", str(exc))]}

    # stores parse
    try:
        store = tasks_mod.TaskStore(paths)
        data = store.load()
        read_jsonl(paths.events_file)
        claims_mod.ClaimStore(paths).all()
        checks.append(_check("stores_parse", "pass", "{0} task(s)".format(len(data["tasks"]))))
    except TaosError as exc:
        return {"ok": False, "checks": checks + [_check("stores_parse", "fail", str(exc))]}

    # allocator
    allocator = read_json(paths.allocator_file, {}) or {}
    numbers = []
    for task_id in data["tasks"]:
        try:
            numbers.append(int(str(task_id).rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            pass
    high = max(numbers) if numbers else 0
    next_number = int(allocator.get("next", 1))
    checks.append(
        _check(
            "allocator_monotonic",
            "pass" if next_number > high else "fail",
            "next={0} highest={1}".format(next_number, high),
        )
    )

    # task ids
    prefix = str(config.get("project", {}).get("prefix", ""))
    bad_ids = [t for t in data["tasks"] if not tasks_mod.ID_RE.match(str(t))]
    wrong_prefix = [t for t in data["tasks"] if prefix and not str(t).startswith(prefix + "-")]
    checks.append(
        _check(
            "task_ids_valid",
            "pass" if not bad_ids and not wrong_prefix else "fail",
            "malformed: {0}; wrong prefix: {1}".format(bad_ids or "none", wrong_prefix or "none"),
        )
    )

    # relations resolve
    dangling = []
    for task_id, task in data["tasks"].items():
        for kind, others in (task.get("relations") or {}).items():
            for other in others:
                if other not in data["tasks"]:
                    dangling.append("{0} {1} {2}".format(task_id, kind, other))
        parent = task.get("parent_id")
        if parent and parent not in data["tasks"]:
            dangling.append("{0} parent {1}".format(task_id, parent))
    checks.append(
        _check("relations_resolve", "pass" if not dangling else "fail", "; ".join(dangling) or "all resolve")
    )

    # done needs evidence
    undocumented = [t for t, task in data["tasks"].items() if task.get("status") == "done" and not task.get("evidence")]
    checks.append(
        _check(
            "terminal_done_evidence",
            "pass" if not undocumented else "fail",
            "done without evidence: {0}".format(undocumented or "none"),
        )
    )

    # claims
    claim_store = claims_mod.ClaimStore(paths)
    malformed = []
    for claim in claim_store.all():
        for field in ("id", "agent", "scopes", "claimed_at", "heartbeat_at", "status"):
            if field not in claim:
                malformed.append("{0} missing {1}".format(claim.get("id", "?"), field))
    checks.append(_check("claims_schema", "pass" if not malformed else "fail", "; ".join(malformed) or "ok"))
    stale = claim_store.stale()
    checks.append(
        _check(
            "claims_stale",
            "pass" if not stale else "warn",
            "; ".join("{0} on {1}".format(c["agent"], ",".join(c["scopes"])) for c in stale) or "none",
        )
    )

    # hot work consistency
    bad_hot = [
        t
        for t, task in data["tasks"].items()
        if task.get("hot") and task.get("status") in tasks_mod.TERMINAL
    ]
    checks.append(
        _check("hot_work_consistent", "pass" if not bad_hot else "fail", "terminal but hot: {0}".format(bad_hot or "none"))
    )

    # kernels
    kernel_states = kernels_mod.freshness(paths)
    unfresh = [k["name"] for k in kernel_states if k["status"] != "fresh"]
    checks.append(
        _check("kernels_fresh", "pass" if not unfresh else "warn", "needs refresh: {0}".format(", ".join(unfresh) or "none"))
    )

    # atoms
    atom_results = atoms_mod.check(paths)
    failing = [a["id"] for a in atom_results if not a["ok"]]
    checks.append(
        _check(
            "atoms",
            "pass" if not failing else "fail",
            "{0} atom(s), failing: {1}".format(len(atom_results), ", ".join(failing) or "none"),
        )
    )

    # panel
    panel_detail = "off"
    if paths.panel_pid.is_file():
        try:
            pid = int(paths.panel_pid.read_text(encoding="utf-8").split()[0])
            os.kill(pid, 0)
            panel_detail = "running (pid {0})".format(pid)
        except (ValueError, OSError, IndexError):
            panel_detail = "stale pidfile"
    checks.append(
        _check("panel_process", "pass" if panel_detail != "stale pidfile" else "warn", panel_detail)
    )

    # hooks installed
    hook_files = [paths.hooks_dir / name for name in ("guard.py", "session_start.py", "stop_labels.py")]
    missing_hooks = [h.name for h in hook_files if not h.is_file()]
    settings = paths.home / ".claude" / "settings.json"
    codex_hooks = paths.home / ".codex" / "hooks.json"
    if not settings.is_file():
        missing_hooks.append(".claude/settings.json")
    if not codex_hooks.is_file():
        missing_hooks.append(".codex/hooks.json")
    checks.append(
        _check("hooks_installed", "pass" if not missing_hooks else "warn", "missing: {0}".format(", ".join(missing_hooks) or "none"))
    )

    # policy layer resolves
    from . import policy as policy_mod

    policy_problems = policy_mod.check(paths)
    checks.append(
        _check(
            "policies_resolve",
            "pass" if not policy_problems else "fail",
            "; ".join(policy_problems) or "every route reaches a real file, every policy is routed",
        )
    )

    # secrets in state
    patterns = [re.compile(p, re.IGNORECASE) for p in config_mod.secret_patterns(paths)]
    leaks = []
    for path in (paths.tasks_file, paths.claims_file, paths.decisions_file, paths.labels_file):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in patterns:
            if pattern.search(text):
                leaks.append("{0} matches {1}".format(path.name, pattern.pattern))
                break
    checks.append(_check("secrets_in_state", "pass" if not leaks else "fail", "; ".join(leaks) or "clean"))

    # soma ttl
    from . import burn as burn_mod

    try:
        candidates = burn_mod.plan(paths)
    except TaosError:
        candidates = []
    checks.append(
        _check(
            "soma_ttl",
            "pass" if len(candidates) < 50 else "warn",
            "{0} file(s) past their TTL; run `taos burn plan`".format(len(candidates)),
        )
    )

    ok = all(c["status"] != "fail" for c in checks)
    return {"ok": ok, "checks": checks}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_doctor(args: argparse.Namespace, paths: Paths) -> int:
    report = run(paths)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ok"] else 3
    for check in report["checks"]:
        marker = {"pass": "ok  ", "warn": "warn", "fail": "FAIL"}[check["status"]]
        print("{0}  {1:<24} {2}".format(marker, check["name"], check["detail"]))
    print("")
    print("doctor: {0}".format("green" if report["ok"] else "failing"))
    return 0 if report["ok"] else 3


def _cmd_selftest(args: argparse.Namespace, paths: Paths) -> int:
    process = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "tests", "-p", "test_*.py"],
        cwd=str(paths.home),
    )
    return process.returncode


def _cmd_version(args: argparse.Namespace, paths: Paths) -> int:
    print("taos {0} (python {1})".format(VERSION, sys.version.split()[0]))
    return 0


def register(subparsers: Any) -> None:
    doctor = subparsers.add_parser("doctor", help="mechanical health of the OS")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=_cmd_doctor)

    selftest = subparsers.add_parser("selftest", help="run the test suite")
    selftest.set_defaults(func=_cmd_selftest)

    version = subparsers.add_parser("version", help="print the version")
    version.set_defaults(func=_cmd_version)
