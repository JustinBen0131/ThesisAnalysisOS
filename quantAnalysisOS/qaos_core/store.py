"""Atomic writes, fingerprints, and append-only hash-chained logs.

The book (trials, studies, the paper ledger) is the scientific record. A line
in a chained log carries the hash of the line before it, so an edit to history
is noticed by `verify` instead of by nobody.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:  # POSIX only; the log still works without it, just without the lock.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore

GENESIS = "0" * 64


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean(value: Any) -> Any:
    """Turn numpy scalars/arrays into plain JSON values. NaN and inf become None.

    `unknown` must never be written as a number, so a missing value is null.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    # numpy without importing it here
    kind = type(value).__module__
    if kind == "numpy":
        if hasattr(value, "tolist") and getattr(value, "ndim", 0) > 0:
            return clean(value.tolist())
        if hasattr(value, "item"):
            return clean(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def canonical(value: Any) -> str:
    """One spelling per value, so equal content always hashes the same."""
    return json.dumps(clean(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_obj(value: Any) -> str:
    return sha256_bytes(canonical(value).encode("ascii"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_files(paths: Iterable[Path], root: Optional[Path] = None) -> str:
    """Fingerprint of a set of files: names and bytes, order independent."""
    digest = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        name = path.relative_to(root).as_posix() if root is not None else path.name
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_text_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def write_json_atomic(path: Path, value: Any) -> None:
    write_text_atomic(Path(path), json.dumps(clean(value), indent=2, sort_keys=True) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.is_file():
        return default
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def seal(content: Dict[str, Any]) -> Dict[str, Any]:
    """Return content with a `seal`: the hash of everything else in it."""
    body = {key: item for key, item in clean(content).items() if key != "seal"}
    body["seal"] = sha256_obj(body)
    return body


def seal_holds(content: Dict[str, Any]) -> bool:
    if not isinstance(content, dict) or "seal" not in content:
        return False
    body = {key: item for key, item in content.items() if key != "seal"}
    return sha256_obj(body) == content["seal"]


class ChainLog:
    """Append-only JSONL. Each entry names the hash of the entry before it."""

    def __init__(self, path: Path, clock: Optional[Callable[[], str]] = None) -> None:
        self.path = Path(path)
        self.clock = clock or now_iso
        self._tail: Optional[Tuple[int, int, str]] = None  # (file size, entries, head) after our own last append

    @staticmethod
    def _entry_hash(entry: Dict[str, Any]) -> str:
        return sha256_obj({key: item for key, item in entry.items() if key != "hash"})

    def read(self) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        entries = []
        with open(self.path, "r", encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def head(self) -> str:
        entries = self.read()
        return entries[-1]["hash"] if entries else GENESIS

    def append(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+", encoding="utf-8") as stream:
            if fcntl is not None:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                size = os.fstat(stream.fileno()).st_size
                if self._tail is not None and self._tail[0] == size:
                    count, prev = self._tail[1], self._tail[2]
                else:  # first append, or someone else wrote: read the file to find the head
                    stream.seek(0)
                    last = None
                    count = 0
                    for line in stream:
                        line = line.strip()
                        if line:
                            last = line
                            count += 1
                    prev = json.loads(last)["hash"] if last else GENESIS
                entry = dict(clean(record))
                for reserved in ("seq", "ts", "prev", "hash"):
                    entry.pop(reserved, None)
                entry["seq"] = count
                entry["ts"] = self.clock()
                entry["prev"] = prev
                entry["hash"] = self._entry_hash(entry)
                stream.seek(0, os.SEEK_END)
                stream.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                self._tail = (os.fstat(stream.fileno()).st_size, count + 1, entry["hash"])
            finally:
                if fcntl is not None:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return entry

    def verify(self) -> Tuple[bool, str]:
        """(True, 'n entries') when every link holds, else (False, where it broke)."""
        try:
            entries = self.read()
        except (OSError, ValueError) as error:
            return False, "unreadable: {0}".format(error)
        prev = GENESIS
        for index, entry in enumerate(entries):
            if entry.get("seq") != index:
                return False, "entry {0}: sequence number is {1}".format(index, entry.get("seq"))
            if entry.get("prev") != prev:
                return False, "entry {0}: does not follow the entry before it".format(index)
            if self._entry_hash(entry) != entry.get("hash"):
                return False, "entry {0}: content does not match its hash".format(index)
            prev = entry["hash"]
        return True, "{0} entries".format(len(entries))
