"""What a recorded measurement stood on: the bytes of the code it measured.

The numbers this repository quotes about itself are records too. Each is
written with a fingerprint of the files it was measured on, and
`evals/claims.py` asks of it the question TAOS asks of any result: does it
still hold for the files as they are? The comparison is `taos_core.basis`,
the same one a check result goes through.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from taos_core import basis  # noqa: E402

CODE = "the code it measured"


def _snapshot(patterns: List[str]) -> Dict[str, Any]:
    return basis.snapshot(REPO, {"domains": {CODE: sorted(patterns)}})


def stamp(patterns: List[str]) -> Dict[str, Any]:
    """To be stored with a result: which files it was measured on, and their bytes."""
    return {"patterns": sorted(patterns), "files": _snapshot(patterns)["domains"][CODE]}


def standing(record: Any) -> Dict[str, Any]:
    """holds while the files a result was measured on are the same bytes; stale names the one that changed."""
    said = record.get("measured_on") if isinstance(record, dict) else None
    if not isinstance(said, dict) or not isinstance(said.get("files"), dict):
        return basis.verdict(basis.UNKNOWN, "no recorded run says what it was measured on")
    verdict = basis.compare({CODE: said["files"].get("sha256")}, _snapshot(said.get("patterns") or []),
                            listed={"domains": {CODE: said["files"]}}, declared=True)
    if verdict["state"] == basis.HOLDS:
        verdict["reason"] = "measured on these bytes"
    return verdict
