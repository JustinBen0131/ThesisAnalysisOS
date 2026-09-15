#!/usr/bin/env python3
"""Stop hook: turn an episode marker into one sanitized row. Costs nothing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import find_home, read_stdin_json  # noqa: E402


def _text_from(payload: dict) -> str:
    for key in ("last_assistant_message", "final_message", "assistant_message", "response"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    transcript = payload.get("transcript_path")
    if isinstance(transcript, str):
        path = Path(transcript)
        if path.is_file():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                return ""
            for line in reversed(lines[-400:]):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                message = row.get("message") if isinstance(row.get("message"), dict) else row
                if str(message.get("role", "")) != "assistant":
                    continue
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content
                if isinstance(content, list):
                    parts = [c.get("text", "") for c in content if isinstance(c, dict)]
                    joined = "\n".join(p for p in parts if p)
                    if joined.strip():
                        return joined
    return ""


def main() -> int:
    payload = read_stdin_json()
    home = find_home()
    if home is None:
        return 0
    text = _text_from(payload)
    if not text:
        return 0
    try:
        sys.path.insert(0, str(home))
        from taos_core.paths import Paths
        from taos_core.telemetry import label, parse_marker

        marker = parse_marker(text)
        if not marker:
            return 0
        agent = "claude" if "claude" in " ".join(sys.argv).lower() else "codex"
        for index, value in enumerate(sys.argv):
            if value == "--agent" and index + 1 < len(sys.argv):
                agent = sys.argv[index + 1]
        label(
            Paths(home),
            agent=agent,
            task_id=marker.get("id"),
            phase=marker.get("phase"),
            outcome=marker.get("outcome", "unknown"),
            modality=marker.get("modality", "unknown"),
            task=marker.get("task") or marker.get("id"),
            counterpart=marker.get("counterpart"),
        )
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(0)
