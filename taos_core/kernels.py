"""Comprehension kernels: distilled understanding with a visible expiry date."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import claims as claims_mod
from . import decisions as decisions_mod
from . import events as events_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import age_days, atomic_write_json, atomic_write_text, read_json, sha256_file, sha256_text, utc_now
from .util import TaosError

INDEX_SCHEMA = "TAOS_KERNEL_INDEX_V1"
NAMES = ("OS_KERNEL", "PROJECT_KERNEL", "PRINCIPAL_KERNEL", "NOW_KERNEL")


def load_index(paths: Paths) -> Dict[str, Any]:
    data = read_json(paths.kernel_index)
    if not isinstance(data, dict) or "kernels" not in data:
        raise TaosError("kernels/KERNEL_INDEX.json is missing or malformed")
    return data


def expand_sources(paths: Paths, patterns: List[str]) -> List[Path]:
    found = set()
    for pattern in patterns or []:
        for hit in glob.glob(str(paths.home / pattern), recursive=True):
            candidate = Path(hit)
            if candidate.is_file():
                found.add(candidate)
    return sorted(found)


def fingerprint(paths: Paths, patterns: List[str]) -> str:
    parts = []
    for path in expand_sources(paths, patterns):
        parts.append(paths.relative(path))
        parts.append(sha256_file(path))
    return sha256_text("\n".join(parts))


def freshness(paths: Paths) -> List[Dict[str, Any]]:
    try:
        index = load_index(paths)
    except TaosError as exc:
        return [{"name": "KERNEL_INDEX", "status": "missing", "reasons": [str(exc)]}]
    results = []
    for entry in index.get("kernels", []):
        name = entry.get("name", "?")
        path = paths.home / entry.get("path", "")
        result: Dict[str, Any] = {"name": name, "status": "fresh", "reasons": []}
        if not path.is_file():
            result["status"] = "missing"
            result["reasons"].append("kernel file absent: {0}".format(entry.get("path")))
            results.append(result)
            continue
        current = fingerprint(paths, entry.get("sources", []))
        if entry.get("fingerprint") and current != entry.get("fingerprint"):
            result["status"] = "drifted"
            result["reasons"].append("sources changed since this kernel was written")
        generated = entry.get("generated_at")
        max_age = entry.get("max_age_days")
        if generated and isinstance(max_age, int):
            days = age_days(generated)
            if days > max_age:
                if result["status"] == "fresh":
                    result["status"] = "aged"
                result["reasons"].append("{0:.1f} days old, limit {1}".format(days, max_age))
        result["generated_at"] = generated
        results.append(result)
    return results


def index_refresh(paths: Paths, name: str, generator: str = "agent") -> Dict[str, Any]:
    index = load_index(paths)
    for entry in index.get("kernels", []):
        if entry.get("name") != name:
            continue
        entry["fingerprint"] = fingerprint(paths, entry.get("sources", []))
        entry["generated_at"] = utc_now()
        entry["generator"] = generator
        index["schema"] = INDEX_SCHEMA
        atomic_write_json(paths.kernel_index, index, mode=0o644)
        events_mod.emit(paths, "kernel_index", generator if generator in events_mod.AGENTS else "system", kernel=name)
        return entry
    raise TaosError("unknown kernel: {0}. Known: {1}".format(name, ", ".join(NAMES)))


def generate_now(paths: Paths) -> Path:
    """NOW_KERNEL is written by the machine, from state, with no model involved."""
    store = tasks_mod.TaskStore(paths)
    claim_store = claims_mod.ClaimStore(paths)
    hot = store.list(hot=True)
    blocked = [t for t in store.list() if t.get("status") == "blocked"]
    review = [t for t in store.list() if t.get("status") == "review"]
    waiting = [t for t in store.list() if t.get("status") == "waiting"]
    open_decisions = decisions_mod.open_decisions(paths)
    live = claim_store.live()
    stale = claim_store.stale()

    lines = [
        "# NOW_KERNEL — live state",
        "",
        "Generated deterministically by `taos kernel now` at {0}. Volatile:".format(utc_now()),
        "re-read the task store before acting on anything here.",
        "",
        "## Hot work",
        "",
    ]
    if hot:
        for task in hot:
            blockers = store.blockers(task["id"])
            lines.append(
                "- {0} [{1}] {2} — {3}".format(task["id"], task["priority"], task["status"], task["title"])
            )
            if task.get("next_action"):
                lines.append("  - next: {0}".format(task["next_action"]))
            if blockers:
                lines.append("  - blocked by: {0}".format(", ".join(blockers)))
            if task.get("owner_agent"):
                lines.append("  - owner: {0}".format(task["owner_agent"]))
    else:
        lines.append("- nothing is hot. Pick from `taos task list --status next`.")

    lines += ["", "## Needs a human", ""]
    if open_decisions:
        for decision in open_decisions:
            lines.append("- {0} ({1}): {2}".format(decision["id"], decision.get("task_id") or "-", decision["question"]))
    else:
        lines.append("- nothing.")

    lines += ["", "## Claims", ""]
    if live:
        for claim in live:
            lines.append("- {0} holds {1} ({2})".format(claim["agent"], ", ".join(claim["scopes"]), claim["session_label"]))
    else:
        lines.append("- none live.")
    if stale:
        for claim in stale:
            lines.append("- STALE: {0} still marked on {1}; take over with a reason if you need it".format(claim["agent"], ", ".join(claim["scopes"])))

    lines += ["", "## Waiting, blocked, in review", ""]
    for label, group in (("review", review), ("blocked", blocked), ("waiting", waiting)):
        if group:
            lines.append("- {0}: {1}".format(label, ", ".join(t["id"] for t in group)))
    if not (review or blocked or waiting):
        lines.append("- none.")

    lines += [
        "",
        "## Standing rules this kernel does not override",
        "",
        "- The task store, claims, and `policies/HARD_STOPS.md` are canonical.",
        "- This file authorizes nothing. It is a fast orientation only.",
        "",
    ]

    path = paths.kernels_dir / "NOW_KERNEL.md"
    atomic_write_text(path, "\n".join(lines))
    try:
        index_refresh(paths, "NOW_KERNEL", "taos")
    except TaosError:
        pass
    events_mod.emit(paths, "kernel_now", "system", hot=len(hot), decisions=len(open_decisions))
    return path


def regen_prompt(paths: Paths, name: str) -> str:
    if name not in NAMES:
        raise TaosError("unknown kernel: {0}. Known: {1}".format(name, ", ".join(NAMES)))
    if name == "NOW_KERNEL":
        return "NOW_KERNEL is machine-generated. Run `taos kernel now` instead of writing it."
    index = load_index(paths)
    entry = next((e for e in index.get("kernels", []) if e.get("name") == name), {})
    sources = ", ".join(entry.get("sources", []))
    return "\n".join(
        [
            "Regenerate {0} for this OS.".format(name),
            "",
            "1. Read these sources completely: {0}".format(sources),
            "2. Read the current kernel at {0}.".format(entry.get("path")),
            "3. Rewrite the kernel so a cold session that reads only it understands",
            "   the subject as well as one that read every source. Keep it under",
            "   1500 tokens. State facts, not intentions. Mark anything you could",
            "   not verify as unverified rather than guessing.",
            "4. The kernel is advisory: it must not claim authority over the task",
            "   store, the claims, or policies/HARD_STOPS.md.",
            "5. Write the file, then run:",
            "   taos kernel refresh {0} --generator agent".format(name),
            "",
            "Do not change any other file while doing this.",
        ]
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_freshness(args: argparse.Namespace, paths: Paths) -> int:
    results = freshness(paths)
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    for item in results:
        print("{0:<18} {1}".format(item["name"], item["status"]))
        for reason in item.get("reasons", []):
            print("    {0}".format(reason))
    return 0


def _cmd_now(args: argparse.Namespace, paths: Paths) -> int:
    path = generate_now(paths)
    print("wrote {0}".format(paths.relative(path)))
    return 0


def _cmd_regen_prompt(args: argparse.Namespace, paths: Paths) -> int:
    print(regen_prompt(paths, args.name))
    return 0


def _cmd_refresh(args: argparse.Namespace, paths: Paths) -> int:
    entry = index_refresh(paths, args.name, args.generator)
    print("{0} marked fresh at {1}".format(entry["name"], entry["generated_at"]))
    return 0


def register(subparsers: Any) -> None:
    kernel = subparsers.add_parser("kernel", help="distilled understanding and its expiry")
    sub = kernel.add_subparsers(dest="kernel_cmd", required=True)

    fresh = sub.add_parser("freshness", help="which kernels have rotted")
    fresh.add_argument("--json", action="store_true")
    fresh.set_defaults(func=_cmd_freshness)

    now = sub.add_parser("now", help="regenerate NOW_KERNEL from state (no model)")
    now.set_defaults(func=_cmd_now)

    prompt = sub.add_parser("regen-prompt", help="print the prompt an agent should run")
    prompt.add_argument("name", choices=list(NAMES))
    prompt.set_defaults(func=_cmd_regen_prompt)

    refresh = sub.add_parser("refresh", help="record that a kernel was rewritten")
    refresh.add_argument("name", choices=list(NAMES))
    refresh.add_argument("--generator", default="agent", choices=["agent", "human", "taos"])
    refresh.set_defaults(func=_cmd_refresh)
