"""Durable-file primitives: time, hashing, atomic writes, the single lock."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .util import TaosError

TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_LOCAL = threading.local()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime(TS_FORMAT)


def parse_ts(ts: str) -> datetime:
    try:
        return datetime.strptime(str(ts), TS_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        cleaned = str(ts).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            raise TaosError("unparseable timestamp: {0!r}".format(ts))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


def age_hours(ts: str, now: Optional[str] = None) -> float:
    reference = parse_ts(now) if now else datetime.now(timezone.utc)
    return (reference - parse_ts(ts)).total_seconds() / 3600.0


def age_days(ts: str, now: Optional[str] = None) -> float:
    return age_hours(ts, now) / 24.0


def shift_hours(ts: str, hours: float) -> str:
    return (parse_ts(ts) + timedelta(hours=hours)).strftime(TS_FORMAT)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TaosError("cannot read {0}: {1}".format(path, exc))


def atomic_write_json(path: Path, value: Any, mode: int = 0o600) -> None:
    atomic_write_text(
        Path(path),
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        mode=mode,
    )


def atomic_write_text(path: Path, text: str, mode: int = 0o644) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    path = Path(path)
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise TaosError("{0} line {1} is not valid JSON: {2}".format(path, number, exc))
        if isinstance(row, dict):
            rows.append(row)
    return rows


@contextmanager
def locked(paths, timeout: float = 15.0) -> Iterator[None]:
    """Single-writer lock over the whole state directory.

    Re-entrant within a process: nested `locked()` blocks are no-ops.
    """
    depth = getattr(_LOCAL, "depth", 0)
    if depth:
        _LOCAL.depth = depth + 1
        try:
            yield
        finally:
            _LOCAL.depth -= 1
        return

    paths.ensure_state()
    lock_path = Path(paths.lock_file)
    deadline = time.time() + timeout
    handle = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() > deadline:
                    raise TaosError("state lock is busy: {0}".format(lock_path))
                time.sleep(0.05)
        _LOCAL.depth = 1
        try:
            yield
        finally:
            _LOCAL.depth = 0
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        os.close(handle)
