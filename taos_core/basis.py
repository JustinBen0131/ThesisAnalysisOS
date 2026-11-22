"""Basis: what a recorded result stood on, and whether it still stands.

A result is true under conditions: the bytes it tested, the instruction in
force, the day it was asked about. TAOS records those conditions with the
result and answers one question about it later, in one vocabulary:

  holds    the conditions are the same
  fails    it was checked on these conditions and did not pass
  stale    a condition changed, and the reason says which
  unknown  a condition cannot be established: never checked, not recorded,
           or something changed whose effect nobody declared

Unknown is a value. It is never rounded to holds, to fails or to zero.

The idea is old. A build system calls it a verifying trace; a truth
maintenance system calls it a justification. This module is the one place
TAOS implements it. Gates, artifacts, closures and acceptance all ask here.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .store import sha256_file, sha256_text
from .util import TaosError

HOLDS, FAILS, STALE, UNKNOWN = "holds", "fails", "stale", "unknown"
STATES = (HOLDS, UNKNOWN, STALE, FAILS)   # mildest first
WORKSPACE = "workspace"                   # the only domain when none are declared
UNDECLARED = "(undeclared)"               # files no declared domain claims
TRANSIENT = (".git", ".taos", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store")
MAX_FILES = 20000
MAX_BYTES = 512 * 1024 * 1024
KEEP_LISTING = 2000
NAMED = 4
WILD = "*?["


def verdict(state: str, reason: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"state": state, "reason": reason}
    out.update(extra)
    return out


def worst(states: Iterable[str]) -> str:
    """The state of a whole is the worst state of its parts. Nothing to rely on holds."""
    rank = max([STATES.index(state) for state in states] or [0])
    return STATES[rank]


# --------------------------------------------------------------------------
# Days
# --------------------------------------------------------------------------


def day(value: Any, what: str) -> str:
    """A real calendar date, YYYY-MM-DD. 2026-02-30 has the right shape and is refused."""
    text = str(value or "").strip()
    try:
        if len(text) != 10:
            raise ValueError(text)
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise TaosError("{0} must be a real date written YYYY-MM-DD, not {1!r}".format(what, text))


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def within(start: str, end: Optional[str], on: str) -> bool:
    """Is `on` inside the closed interval? Dates compare as text because they are ISO."""
    return start <= on and (end is None or on <= end)


# --------------------------------------------------------------------------
# Bytes
# --------------------------------------------------------------------------


def _hidden(relative: str, ignore: List[str]) -> bool:
    if any(part in TRANSIENT for part in relative.split("/")):
        return True
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in ignore)


def listing(root: Path, ignore: Optional[List[str]] = None) -> List[str]:
    """The files that could matter when nobody has said: what git tracks or would track, every file where there is no git.

    Git's ignore rules decide this list. They do not decide what a declared
    domain holds: see `on_disk`.
    """
    root = Path(root)
    ignore = list(ignore or [])
    names: List[str] = []
    try:
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
                                capture_output=True, timeout=60)
        if listed.returncode == 0:
            names = [name for name in listed.stdout.decode("utf-8", "surrogateescape").split("\0") if name]
        else:
            names = []
            listed = None
    except (OSError, subprocess.SubprocessError):
        listed = None
    if listed is None:
        for folder, folders, files in os.walk(str(root)):
            folders[:] = sorted(name for name in folders if name not in TRANSIENT)
            for name in files:
                names.append(os.path.relpath(os.path.join(folder, name), str(root)).replace(os.sep, "/"))
    return sorted({name for name in names if not _hidden(name, ignore) and (root / name).is_file()})


def _folder(pattern: str) -> str:
    """The folder a pattern can only match inside: what comes before its first wildcard, cut at the last slash."""
    cut = min([pattern.index(mark) for mark in WILD if mark in pattern] or [len(pattern)])
    return pattern[:cut].rpartition("/")[0]


def on_disk(root: Path, patterns: Iterable[str], ignore: Optional[List[str]] = None) -> List[str]:
    """Every file a declared pattern names, read from the disk and not from git.

    Git's ignore rules say what is versioned. A declared domain says what a
    check reads, and research inputs are very often read and not versioned.
    So a domain holds what its patterns match on disk, ignored by git or not.
    """
    root, ignore = Path(root), list(ignore or [])
    patterns = [pattern for pattern in patterns if pattern and not pattern.startswith("/") and ".." not in pattern.split("/")]
    wild = [pattern for pattern in patterns if any(mark in pattern for mark in WILD)]
    found = {pattern for pattern in patterns if pattern not in wild and not _hidden(pattern, ignore)}
    folders = {_folder(pattern) for pattern in wild}
    for start in ([""] if "" in folders else sorted(folders)):
        for folder, inner, files in os.walk(str(root / start)):
            inner[:] = sorted(name for name in inner if name not in TRANSIENT)
            for name in files:
                relative = os.path.relpath(os.path.join(folder, name), str(root)).replace(os.sep, "/")
                if not _hidden(relative, ignore) and any(fnmatch.fnmatchcase(relative, pattern) for pattern in wild):
                    found.add(relative)
    return sorted(name for name in found if (root / name).is_file())


def fingerprint(root: Path, name: str) -> Optional[str]:
    """One declared input, hashed: a file by its bytes, a folder by its listing. None when it is not there."""
    path = Path(name).expanduser()
    path = path if path.is_absolute() else Path(root) / name
    if path.is_file():
        return sha256_file(path)
    if path.is_dir():
        return sha256_text("\n".join("{0}\0{1}".format(item, sha256_file(path / item)) for item in listing(path)))
    return None


def snapshot(root: Path, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Hash the workspace, grouped by declared domain.

    `settings` is the "basis" block of the config: {"domains": {name: [patterns]},
    "ignore": [patterns]}. Patterns are shell-style and `*` crosses directories.
    A file may belong to several domains. A file that no domain claims is
    filed under UNDECLARED, so that its change is reported and never ignored.
    A declared domain is read from the disk, so an input git ignores is part
    of it; with no domains declared, the workspace is what git lists.
    """
    settings = settings if isinstance(settings, dict) else {}
    declared = settings.get("domains") if isinstance(settings.get("domains"), dict) else {}
    root = Path(root)
    out: Dict[str, Any] = {"root": str(root), "complete": True, "reason": "", "domains": {}}
    if not root.is_dir():
        out.update(complete=False, reason="the workspace {0} does not exist".format(root))
        return out
    names = listing(root, settings.get("ignore"))
    if declared:
        named = [pattern for patterns in declared.values() for pattern in patterns or []]
        names = sorted(set(names) | set(on_disk(root, named, settings.get("ignore"))))
    size = sum((root / name).stat().st_size for name in names)
    if len(names) > MAX_FILES or size > MAX_BYTES:
        out.update(complete=False, reason="the workspace is too large to fingerprint ({0} files, {1} MB); declare "
                   "basis.domains or basis.ignore in the config".format(len(names), size // (1024 * 1024)))
        return out
    grouped: Dict[str, Dict[str, str]] = {name: {} for name in declared}
    for name in names:
        digest = sha256_file(root / name)
        homes = [domain for domain, patterns in declared.items()
                 if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns or [])]
        for domain in homes or [UNDECLARED if declared else WORKSPACE]:
            grouped.setdefault(domain, {})[name] = digest
    for domain, files in grouped.items():
        text = "\n".join("{0}\0{1}".format(name, files[name]) for name in sorted(files))
        out["domains"][domain] = {"sha256": sha256_text(text), "count": len(files),
                                  "files": files if len(files) <= KEEP_LISTING else None}
    return out


def digests(snap: Dict[str, Any], domains: Optional[List[str]] = None) -> Dict[str, str]:
    """The part of a snapshot a result stands on: one digest per domain it depends on."""
    have = snap.get("domains") or {}
    if domains is None:
        return {name: entry["sha256"] for name, entry in have.items()}
    wanted = list(domains) + [UNDECLARED]
    empty = sha256_text("")
    return {name: (have[name]["sha256"] if name in have else empty) for name in wanted}


def differences(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> List[str]:
    """Which files differ between two listings of one domain, for the reason a person reads."""
    old = (before or {}).get("files")
    new = (after or {}).get("files")
    if old is None or new is None:
        return []
    names = [name for name in sorted(set(old) | set(new)) if old.get(name) != new.get(name)]
    return [("+" if name not in old else "-" if name not in new else "") + name for name in names]


def _named(names: List[str]) -> str:
    if not names:
        return ""
    more = len(names) - NAMED
    return ": " + ", ".join(names[:NAMED]) + (" and {0} more".format(more) if more > 0 else "")


def compare(recorded: Dict[str, str], current: Dict[str, Any], *, listed: Optional[Dict[str, Any]] = None,
            declared: bool = False) -> Dict[str, Any]:
    """Does a result recorded on `recorded` digests still stand on the `current` snapshot?

    `listed` is the snapshot kept with the record, used only to name the files
    that differ. `declared` says the result named the domains it depends on;
    then a change outside every domain is unknown, not harmless.
    """
    if not current.get("complete"):
        return verdict(UNKNOWN, current.get("reason") or "the workspace could not be read")
    now = digests(current, [name for name in recorded if name != UNDECLARED] if declared else None)
    kept = (listed or {}).get("domains") or {}
    stale, unknown = [], []
    for name in sorted(set(recorded) | (set(now) if not declared else set())):
        if recorded.get(name) == now.get(name):
            continue
        named = _named(differences(kept.get(name), (current.get("domains") or {}).get(name)))
        if name == UNDECLARED:
            unknown.append("a file outside every declared domain changed{0}".format(named))
        elif name not in recorded:
            unknown.append("{0} was not recorded when this was checked".format(name))
        else:
            stale.append("{0} changed{1}".format(name, named))
    if stale:
        return verdict(STALE, "; ".join(stale + unknown))
    if unknown:
        return verdict(UNKNOWN, "; ".join(unknown))
    return verdict(HOLDS, "nothing it stood on has changed")
