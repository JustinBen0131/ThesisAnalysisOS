"""Token usage adapters. Both hosts write it to disk; we read it, never guess.

Claude Code writes one JSONL transcript per session under
`~/.claude/projects/<slugged-cwd>/<session-uuid>.jsonl`; every assistant row
carries `message.usage` with `input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `cache_creation_input_tokens`, and `message.model`.
Hooks are handed the same file as `transcript_path`.

Codex writes a rollout per session under
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`; rows of type
`token_usage_record` carry `payload.usage` with `input_tokens`,
`cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`,
`reasoning_output_tokens`, and `total_tokens`. Reasoning is already inside
`output_tokens` there, so it is reported but never added again.

Both hosts record per-response deltas, verified: summing Codex's
`payload.usage` across a rollout reproduces its own `thread_token_usage`
exactly. Note what that means. Every response resends the conversation, so
summed `input_tokens` and `cached_tokens` are the billing-shaped quantity,
not a measure of unique content: a long session legitimately reports
hundreds of millions of cached tokens. Do not read them as "text processed".

Nothing here is estimated except money, which is tokens times a published
rate table and is labelled `estimated` for exactly that reason. If a host
changes its format, the probe reports the adapter as unavailable and the
controller carries on with nulls rather than inventing numbers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import Paths
from .store import parse_ts, read_json, utc_now
from .util import TaosError

CLAUDE_ROOT = Path.home() / ".claude" / "projects"
CODEX_ROOT = Path.home() / ".codex" / "sessions"
RATES_FILE = "bootstrap/rates.json"

ZERO = {"input_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}


MAX_BYTES = 8 * 1024 * 1024        # never read more than this from one session file
MAX_FILES = 40                     # never open more than this in one window


def _slug_for(path: Path) -> str:
    """Claude's project directory name: the absolute path with separators as dashes."""
    return str(path.resolve()).replace("/", "-")


def _touched_since(path: Path, since: Optional[str]) -> bool:
    """A cheap stat beats opening a file that cannot contain the window."""
    if not since:
        return True
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    try:
        return mtime >= parse_ts(since).timestamp()
    except TaosError:
        return True


def _tail(path: Path) -> List[str]:
    """The last MAX_BYTES of a session file, whole lines only."""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > MAX_BYTES:
                handle.seek(size - MAX_BYTES)
                handle.readline()      # drop the partial line
            data = handle.read()
    except OSError:
        return []
    return data.decode("utf-8", errors="replace").splitlines()


# --------------------------------------------------------------------------
# Claude Code
# --------------------------------------------------------------------------


def claude_transcripts(workspace: Optional[Path] = None) -> List[Path]:
    if not CLAUDE_ROOT.is_dir():
        return []
    if workspace is not None:
        directory = CLAUDE_ROOT / _slug_for(Path(workspace))
        directories = [directory] if directory.is_dir() else []
    else:
        directories = [d for d in CLAUDE_ROOT.iterdir() if d.is_dir()]
    found: List[Path] = []
    for directory in directories:
        found.extend(sorted(directory.glob("*.jsonl")))
    return found


def read_claude(path: Path, since: Optional[str] = None, until: Optional[str] = None) -> Dict[str, Any]:
    totals = dict(ZERO)
    models: Dict[str, int] = {}
    rows = 0
    for line in _tail(path):
        if '"usage"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        stamp = row.get("timestamp") or row.get("ts")
        if stamp and not _in_window(stamp, since, until):
            continue
        message = row.get("message") if isinstance(row.get("message"), dict) else {}
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        rows += 1
        totals["input_tokens"] += int(usage.get("input_tokens") or 0)
        totals["output_tokens"] += int(usage.get("output_tokens") or 0)
        totals["cached_tokens"] += int(usage.get("cache_read_input_tokens") or 0)
        totals["cache_write_tokens"] += int(usage.get("cache_creation_input_tokens") or 0)
        model = str(message.get("model") or "unknown")
        models[model] = models.get(model, 0) + 1
    return {"ok": rows > 0, "rows": rows, "totals": totals, "models": models}


# --------------------------------------------------------------------------
# Codex
# --------------------------------------------------------------------------


def codex_sessions(limit_days: int = 30) -> List[Path]:
    if not CODEX_ROOT.is_dir():
        return []
    found = sorted(CODEX_ROOT.rglob("rollout-*.jsonl"))
    return found[-400:] if len(found) > 400 else found


def read_codex(path: Path, since: Optional[str] = None, until: Optional[str] = None) -> Dict[str, Any]:
    totals = dict(ZERO)
    models: Dict[str, int] = {}
    rows = 0
    for line in _tail(path):
        if '"token_usage_record"' not in line and '"session_meta"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        kind = row.get("type")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if kind == "session_meta":
            model = payload.get("model") or (payload.get("turn_context") or {}).get("model")
            if model:
                models[str(model)] = models.get(str(model), 0) + 1
            continue
        if kind != "token_usage_record":
            continue
        stamp = row.get("timestamp")
        if stamp and not _in_window(stamp, since, until):
            continue
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            continue
        rows += 1
        totals["input_tokens"] += int(usage.get("input_tokens") or 0)
        totals["output_tokens"] += int(usage.get("output_tokens") or 0)
        totals["cached_tokens"] += int(usage.get("cached_input_tokens") or 0)
        totals["cache_write_tokens"] += int(usage.get("cache_write_input_tokens") or 0)
        # Already inside output_tokens for this host: reported, never re-added.
        totals["reasoning_tokens"] += int(usage.get("reasoning_output_tokens") or 0)
    return {"ok": rows > 0, "rows": rows, "totals": totals, "models": models}


def _in_window(stamp: str, since: Optional[str], until: Optional[str]) -> bool:
    try:
        when = parse_ts(str(stamp).replace(".000Z", "Z").split(".")[0] + "Z" if "." in str(stamp) else str(stamp))
    except TaosError:
        return True
    if since and when < parse_ts(since):
        return False
    if until and when > parse_ts(until):
        return False
    return True


# --------------------------------------------------------------------------
# Probe: what can this machine actually see
# --------------------------------------------------------------------------


def probe(paths: Paths, workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Run at bootstrap. Reports, with evidence, which adapters work here."""
    result: Dict[str, Any] = {"probed_at": utc_now(), "adapters": {}}

    transcripts = claude_transcripts(workspace) or claude_transcripts(None)
    transcripts = sorted(transcripts, key=lambda p: p.stat().st_mtime if p.exists() else 0)
    claude: Dict[str, Any] = {"available": False, "root": str(CLAUDE_ROOT), "files": len(transcripts)}
    for path in reversed(transcripts[-3:]):
        sample = read_claude(path)
        if sample["ok"]:
            claude.update({
                "available": True,
                "sample_file": path.name,
                "sample_rows": sample["rows"],
                "fields": ["input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens"],
                "models_seen": sorted(sample["models"]),
            })
            break
    result["adapters"]["claude"] = claude

    sessions = codex_sessions()
    codex: Dict[str, Any] = {"available": False, "root": str(CODEX_ROOT), "files": len(sessions)}
    for path in reversed(sessions[-3:]):
        sample = read_codex(path)
        if sample["ok"]:
            codex.update({
                "available": True,
                "sample_file": path.name,
                "sample_rows": sample["rows"],
                "fields": ["input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens", "reasoning_tokens"],
                "models_seen": sorted(sample["models"]),
                "note": "reasoning tokens are already inside output_tokens on this host",
            })
            break
    result["adapters"]["codex"] = codex
    result["any"] = bool(claude["available"] or codex["available"])
    return result


# --------------------------------------------------------------------------
# Windowed totals and money
# --------------------------------------------------------------------------


def window(paths: Paths, since: str, until: Optional[str] = None, workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Tokens observed between two timestamps, per agent. Empty means unseen, not zero."""
    out: Dict[str, Any] = {"since": since, "until": until or utc_now(), "agents": {}}
    # Only files whose mtime falls in the window can contain the window. One
    # stat each beats opening hundreds of historical sessions: the controller
    # has to be cheaper than what it saves.
    claude_files = [p for p in (claude_transcripts(workspace) or claude_transcripts(None)) if _touched_since(p, since)]
    codex_files = [p for p in codex_sessions() if _touched_since(p, since)]
    for path in claude_files[-MAX_FILES:]:
        sample = read_claude(path, since, until)
        if sample["rows"]:
            _merge(out["agents"].setdefault("claude", {"totals": dict(ZERO), "rows": 0, "models": {}}), sample)
    for path in codex_files[-MAX_FILES:]:
        sample = read_codex(path, since, until)
        if sample["rows"]:
            _merge(out["agents"].setdefault("codex", {"totals": dict(ZERO), "rows": 0, "models": {}}), sample)
    out["files_scanned"] = len(claude_files[-MAX_FILES:]) + len(codex_files[-MAX_FILES:])
    for agent, data in out["agents"].items():
        data["cost"] = estimate_cost(paths, data["totals"], data["models"])
    return out


def _merge(target: Dict[str, Any], sample: Dict[str, Any]) -> None:
    for key, value in sample["totals"].items():
        target["totals"][key] = target["totals"].get(key, 0) + value
    target["rows"] += sample["rows"]
    for model, count in sample["models"].items():
        target["models"][model] = target["models"].get(model, 0) + count


def rates(paths: Paths) -> Dict[str, Any]:
    data = read_json(paths.home / RATES_FILE)
    return data if isinstance(data, dict) else {"schema": "TAOS_RATES_V1", "models": {}, "default": None}


def estimate_cost(paths: Paths, totals: Dict[str, int], models: Dict[str, int]) -> Optional[Dict[str, Any]]:
    """Tokens times a published rate. Estimated, never billed, and null without a rate."""
    table = rates(paths)
    entries = table.get("models") or {}
    model = max(models.items(), key=lambda item: item[1])[0] if models else None
    rate = None
    if model:
        rate = entries.get(model)
        if rate is None:
            for name, value in entries.items():
                if name and (name in model or model in name):
                    rate = value
                    break
    if rate is None:
        rate = table.get("default")
    if not isinstance(rate, dict):
        return None
    million = 1_000_000.0
    amount = (
        int(totals.get("input_tokens") or 0) / million * float(rate.get("input", 0))
        + int(totals.get("cached_tokens") or 0) / million * float(rate.get("cached", rate.get("input", 0)))
        + int(totals.get("cache_write_tokens") or 0) / million * float(rate.get("cache_write", rate.get("input", 0)))
        + int(totals.get("output_tokens") or 0) / million * float(rate.get("output", 0))
    )
    return {"amount": round(amount, 4), "currency": table.get("currency", "USD"),
            "basis": model or "default", "rates_as_of": table.get("as_of"), "provenance": "estimated"}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_probe(args: argparse.Namespace, paths: Paths) -> int:
    result = probe(paths)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    for agent, data in sorted(result["adapters"].items()):
        if data["available"]:
            print("{0:<7} readable: {1} file(s), {2} usage rows in the newest, fields: {3}".format(
                agent, data["files"], data["sample_rows"], ", ".join(data["fields"])))
            if data.get("models_seen"):
                print("        models seen: {0}".format(", ".join(data["models_seen"])))
            if data.get("note"):
                print("        note: {0}".format(data["note"]))
        else:
            print("{0:<7} not readable here ({1} file(s) under {2})".format(agent, data["files"], data["root"]))
    if not result["any"]:
        print("\nNo token telemetry on this machine. The controller runs on its own signals; token fields stay null.")
    return 0


def _cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    from .store import shift_hours

    since = args.since or shift_hours(utc_now(), -24.0 * args.days)
    result = window(paths, since)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print("since {0}".format(since))
    if not result["agents"]:
        print("nothing observed in this window")
        return 0
    for agent, data in sorted(result["agents"].items()):
        totals = data["totals"]
        line = "{0:<7} in {1:,}  cached {2:,}  out {3:,}".format(
            agent, totals["input_tokens"], totals["cached_tokens"], totals["output_tokens"])
        if totals.get("reasoning_tokens"):
            line += "  (reasoning {0:,}, inside out)".format(totals["reasoning_tokens"])
        if data.get("cost"):
            line += "  ~{0} {1} (estimated)".format(data["cost"]["amount"], data["cost"]["currency"])
        print(line)
    return 0


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("usage", help="token telemetry the hosts already write to disk")
    sub = parser.add_subparsers(dest="usage_cmd", required=True)
    prober = sub.add_parser("probe", help="what this machine can actually see")
    prober.add_argument("--json", action="store_true")
    prober.set_defaults(func=_cmd_probe)
    shower = sub.add_parser("show", help="tokens observed in a window")
    shower.add_argument("--days", type=float, default=1.0)
    shower.add_argument("--since")
    shower.add_argument("--json", action="store_true")
    shower.set_defaults(func=_cmd_show)
