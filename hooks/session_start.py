#!/usr/bin/env python3
"""SessionStart hook: the agent begins the session already oriented."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import emit_context, find_home, read_stdin_json  # noqa: E402

EVENT = "SessionStart"
FALLBACK = "TAOS not constructed. Read BOOTSTRAP.md and follow it."


def main() -> int:
    read_stdin_json()
    home = find_home()
    if home is None:
        return 0
    try:
        sys.path.insert(0, str(home))
        from taos_core.paths import Paths
        from taos_core.projections import compact_status

        text = compact_status(Paths(home))
    except Exception:
        text = FALLBACK
    emit_context(EVENT, text)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(0)
