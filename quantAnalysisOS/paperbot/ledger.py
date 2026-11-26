"""Append-only, hash-chained ledger and atomic state files.

Every record carries the hash of the record before it, so any edit to history
breaks `verify`. State files are rewritten atomically and are always
re-derivable from the ledger's story, never the other way round.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

GENESIS = "0" * 64


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with open(path) as handle:
        return json.load(handle)


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path) as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def head(self) -> str:
        rows = self.read()
        return rows[-1]["hash"] if rows else GENESIS

    def append(self, kind: str, body: Dict[str, Any], at: str = "") -> Dict[str, Any]:
        prev = self.head()
        entry = {"at": at or now_iso(), "kind": kind, "body": body, "prev": prev}
        entry["hash"] = sha256(canonical(entry))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as handle:
            handle.write(canonical(entry) + "\n")
        return entry

    def verify(self) -> Tuple[bool, str]:
        prev = GENESIS
        for index, entry in enumerate(self.read()):
            claimed = entry.get("hash")
            body = {k: v for k, v in entry.items() if k != "hash"}
            if entry.get("prev") != prev:
                return False, f"record {index}: chain broken (prev does not match)"
            if sha256(canonical(body)) != claimed:
                return False, f"record {index}: content changed after it was written"
            prev = claimed
        return True, f"{len(self.read())} records, chain intact"
