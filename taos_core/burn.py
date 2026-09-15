"""Burns: the OS deletes its own waste, but only after proving it can restore it."""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config as config_mod
from . import events as events_mod
from .paths import Paths
from .store import age_days, atomic_write_json, locked, read_json, sha256_file, utc_now
from .util import TaosError

def _extract(tar: tarfile.TarFile, destination: str) -> None:
    """Safe extraction on every Python from 3.9 to 3.14+."""
    try:
        tar.extractall(destination, filter="data")
    except TypeError:
        tar.extractall(destination)


# Never burn fuel, whatever their age.
GERMLINE_NAMES = (
    "config.json",
    "tasks.json",
    "allocator.json",
    "events.jsonl",
    "claims.json",
    "decisions.json",
    "labels.jsonl",
)


def _candidates(paths: Paths) -> List[Dict[str, Any]]:
    ttl = config_mod.ttl_days(paths)
    found: List[Dict[str, Any]] = []

    def consider(path: Path, category: str, days: int) -> None:
        if not path.is_file() or path.name in GERMLINE_NAMES:
            return
        try:
            mtime_days = (Path(path).stat().st_mtime)
        except OSError:
            return
        import time

        age = (time.time() - mtime_days) / 86400.0
        if age <= days:
            return
        found.append(
            {
                "path": paths.relative(path),
                "category": category,
                "age_days": round(age, 1),
                "ttl_days": days,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )

    for path in sorted(paths.handoffs_dir.glob("*.md")) if paths.handoffs_dir.is_dir() else []:
        consider(path, "handoff", int(ttl.get("handoffs", 30)))
    for path in sorted(paths.briefs_dir.glob("*.md")) if paths.briefs_dir.is_dir() else []:
        consider(path, "brief", int(ttl.get("briefs", 14)))
    if paths.scratch_dir.is_dir():
        for path in sorted(paths.scratch_dir.rglob("*")):
            consider(path, "scratch", int(ttl.get("scratch", 7)))
    if paths.proposals_dir.is_dir():
        for path in sorted(paths.proposals_dir.glob("prop_*.json")):
            data = read_json(path, {}) or {}
            if data.get("status") in ("accepted", "rejected"):
                consider(path, "proposal", int(ttl.get("proposals_closed", 30)))
    return found


def plan(paths: Paths, now: Optional[str] = None) -> List[Dict[str, Any]]:
    if not paths.state.is_dir():
        return []
    return _candidates(paths)


def execute(paths: Paths, date: str, approve: bool) -> Dict[str, Any]:
    if not approve:
        raise TaosError(
            "a burn deletes files. Re-run with --approve after reading `taos burn plan`."
        )
    items = plan(paths)
    if not items:
        return {"date": date, "burned": 0, "archive": None, "note": "nothing past its TTL"}

    with locked(paths):
        paths.cold_dir.mkdir(parents=True, exist_ok=True)
        archive = paths.cold_dir / "{0}.tar.gz".format(date)
        manifest_path = paths.cold_dir / "{0}.manifest.json".format(date)
        if archive.exists():
            raise TaosError("a burn archive already exists for {0}".format(date))

        with tarfile.open(str(archive), "w:gz") as tar:
            for item in items:
                tar.add(str(paths.home / item["path"]), arcname=item["path"])

        manifest = {
            "schema": "TAOS_BURN_MANIFEST_V1",
            "date": date,
            "created_at": utc_now(),
            "archive_sha256": sha256_file(archive),
            "items": items,
        }
        atomic_write_json(manifest_path, manifest, mode=0o644)

        # Prove the archive restores before deleting anything.
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(str(archive), "r:gz") as tar:
                _extract(tar, tmp)
            for item in items:
                restored = Path(tmp) / item["path"]
                if not restored.is_file() or sha256_file(restored) != item["sha256"]:
                    archive.unlink()
                    manifest_path.unlink()
                    raise TaosError(
                        "restore verification failed for {0}; nothing was deleted".format(item["path"])
                    )

        deleted = []
        for item in items:
            target = paths.home / item["path"]
            if target.is_file() and sha256_file(target) == item["sha256"]:
                target.unlink()
                deleted.append(item["path"])
                events_mod.emit(paths, "burn_execute", "system", path=item["path"], sha256=item["sha256"], date=date)

        events_mod.emit(paths, "burn_plan", "system", date=date, count=len(deleted), archive=paths.relative(archive))
        return {
            "date": date,
            "burned": len(deleted),
            "archive": paths.relative(archive),
            "manifest": paths.relative(manifest_path),
            "paths": deleted,
        }


def recall(paths: Paths, date: str) -> Dict[str, Any]:
    archive = paths.cold_dir / "{0}.tar.gz".format(date)
    manifest_path = paths.cold_dir / "{0}.manifest.json".format(date)
    if not archive.is_file() or not manifest_path.is_file():
        raise TaosError("no burn archive for {0}".format(date))
    manifest = read_json(manifest_path, {}) or {}
    if sha256_file(archive) != manifest.get("archive_sha256"):
        raise TaosError("burn archive for {0} does not match its manifest".format(date))

    restored, conflicts = [], []
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(str(archive), "r:gz") as tar:
            _extract(tar, tmp)
        for item in manifest.get("items", []):
            source = Path(tmp) / item["path"]
            target = paths.home / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and sha256_file(target) != item["sha256"]:
                target = Path(str(target) + ".recalled")
                conflicts.append(paths.relative(target))
            shutil.copy2(str(source), str(target))
            restored.append(paths.relative(target))
    events_mod.emit(paths, "burn_recall", "human", date=date, restored=len(restored))
    return {"date": date, "restored": restored, "conflicts": conflicts}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_plan(args: argparse.Namespace, paths: Paths) -> int:
    items = plan(paths)
    if args.json:
        print(json.dumps(items, indent=2, sort_keys=True))
        return 0
    if not items:
        print("nothing is past its TTL")
        return 0
    total = sum(item["bytes"] for item in items)
    for item in items:
        print("{0:<10} {1:>6.1f}d  {2}".format(item["category"], item["age_days"], item["path"]))
    print("")
    print("{0} file(s), {1:.1f} KB. Archive and delete with:".format(len(items), total / 1024.0))
    print("  taos burn execute --date {0} --approve".format(utc_now()[:10]))
    return 0


def _cmd_execute(args: argparse.Namespace, paths: Paths) -> int:
    result = execute(paths, args.date, args.approve)
    print("burned {0} file(s)".format(result["burned"]))
    if result.get("archive"):
        print("archive: {0}".format(result["archive"]))
        print("undo with: taos burn recall --date {0}".format(args.date))
    return 0


def _cmd_recall(args: argparse.Namespace, paths: Paths) -> int:
    result = recall(paths, args.date)
    print("restored {0} file(s)".format(len(result["restored"])))
    for path in result["conflicts"]:
        print("conflict kept aside: {0}".format(path))
    return 0


def register(subparsers: Any) -> None:
    burn = subparsers.add_parser("burn", help="archive and delete expired working files")
    sub = burn.add_subparsers(dest="burn_cmd", required=True)

    planner = sub.add_parser("plan", help="what is past its TTL")
    planner.add_argument("--json", action="store_true")
    planner.set_defaults(func=_cmd_plan)

    executor = sub.add_parser("execute", help="archive, verify the restore, then delete")
    executor.add_argument("--date", required=True)
    executor.add_argument("--approve", action="store_true")
    executor.set_defaults(func=_cmd_execute)

    recaller = sub.add_parser("recall", help="restore a burn")
    recaller.add_argument("--date", required=True)
    recaller.set_defaults(func=_cmd_recall)
