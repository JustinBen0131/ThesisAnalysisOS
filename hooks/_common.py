"""Shared helpers for the hook scripts.

Hooks run inside someone else's agent process. They must never raise, never
block on IO, and never take longer than a moment.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_SECRET_PATTERNS = [
    r"\.env$",
    r"\.env\.",
    r"\.pem$",
    r"id_rsa",
    r"id_ed25519",
    r"\.key$",
    r"keystore",
    r"mnemonic",
    r"seed[-_ ]?phrase",
    r"\.secret",
    r"credentials",
]


def read_stdin_json() -> Dict[str, Any]:
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def find_home() -> Optional[Path]:
    """Locate the OS clone: env, project dir, this file's parent, or a link."""
    candidates: List[Path] = []
    for key in ("TAOS_HOME", "CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR"):
        value = os.environ.get(key)
        if value:
            candidates.append(Path(value))
    candidates.append(Path(__file__).resolve().parent.parent)
    try:
        cwd = Path.cwd().resolve()
        candidates.append(cwd)
        candidates.extend(cwd.parents)
    except OSError:
        pass

    for candidate in candidates:
        try:
            if (candidate / "taos_core").is_dir() and (candidate / "taos").is_file():
                return candidate
            link = candidate / ".taos-link.json"
            if link.is_file():
                data = json.loads(link.read_text(encoding="utf-8"))
                home = Path(data.get("taos_home", ""))
                if (home / "taos_core").is_dir():
                    return home
        except (OSError, ValueError):
            continue
    return None


def load_config(home: Optional[Path]) -> Dict[str, Any]:
    if home is None:
        return {}
    try:
        return json.loads((home / ".taos" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def secret_patterns(config: Dict[str, Any]) -> List[str]:
    patterns = list(DEFAULT_SECRET_PATTERNS)
    for pattern in config.get("secret_patterns") or []:
        if isinstance(pattern, str) and pattern not in patterns:
            patterns.append(pattern)
    return patterns


def emit_decision(event: str, decision: str, reason: str) -> None:
    """Both runtimes accept this shape on stdout."""
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.stdout.write("\n")


def emit_context(event: str, text: str) -> None:
    sys.stdout.write(
        json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})
    )
    sys.stdout.write("\n")
