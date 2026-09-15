"""Scope-local claims: the mutex that keeps two agents out of each other's way."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Optional

from . import config as config_mod
from . import events as events_mod
from .paths import Paths
from .store import age_hours, atomic_write_json, locked, read_json, utc_now
from .util import TaosError, short_id

CLAIMS_SCHEMA = "TAOS_CLAIMS_V1"
SCOPE_KINDS = ("task", "path", "branch", "repo", "policy", "panel", "kernel", "atoms", "burn")
_FORBIDDEN = re.compile(r"[*?\[\]{}$`\x00\s]")


class ClaimConflict(TaosError):
    def __init__(self, message: str, claims: Optional[List[Dict[str, Any]]] = None):
        TaosError.__init__(self, message)
        self.claims = claims or []


def normalize_scopes(scopes: List[str]) -> List[str]:
    cleaned = []
    for raw in scopes or []:
        scope = str(raw).strip()
        if not scope:
            continue
        if ":" not in scope:
            raise TaosError("a scope needs a kind, like task:AZ-7 or path:compiler/ssa")
        kind, value = scope.split(":", 1)
        if kind not in SCOPE_KINDS:
            raise TaosError("scope kind must be one of {0}".format(", ".join(SCOPE_KINDS)))
        if not value or _FORBIDDEN.search(value):
            raise TaosError("scope {0!r} must be exact: no globs, spaces, or shell characters".format(scope))
        if kind == "path":
            value = value.strip("/")
        cleaned.append("{0}:{1}".format(kind, value))
    if not cleaned:
        raise TaosError("at least one --scope is required")
    return sorted(set(cleaned))


def scopes_conflict(left: str, right: str) -> bool:
    if left == right:
        return True
    if left.startswith("path:") and right.startswith("path:"):
        a = left[5:].strip("/")
        b = right[5:].strip("/")
        return a.startswith(b + "/") or b.startswith(a + "/")
    return False


class ClaimStore(object):
    def __init__(self, paths: Paths):
        self.paths = paths

    def _load(self) -> Dict[str, Any]:
        data = read_json(self.paths.claims_file)
        if not isinstance(data, dict) or "claims" not in data:
            return {"schema": CLAIMS_SCHEMA, "claims": []}
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        data["schema"] = CLAIMS_SCHEMA
        atomic_write_json(self.paths.claims_file, data)

    def all(self) -> List[Dict[str, Any]]:
        return list(self._load()["claims"])

    def get(self, claim_id: str) -> Dict[str, Any]:
        for claim in self.all():
            if claim.get("id") == str(claim_id):
                return claim
        raise TaosError("no such claim: {0}".format(claim_id))

    def _is_fresh(self, claim: Dict[str, Any], now: Optional[str]) -> bool:
        if claim.get("status") != "live":
            return False
        limit = float(claim.get("stale_after_hours") or config_mod.claim_stale_hours(self.paths))
        return age_hours(claim.get("heartbeat_at", claim.get("claimed_at", utc_now())), now) <= limit

    def live(self, now: Optional[str] = None) -> List[Dict[str, Any]]:
        return [c for c in self.all() if self._is_fresh(c, now)]

    def stale(self, now: Optional[str] = None) -> List[Dict[str, Any]]:
        return [c for c in self.all() if c.get("status") == "live" and not self._is_fresh(c, now)]

    def check(self, scopes: List[str], agent: str, now: Optional[str] = None) -> List[Dict[str, Any]]:
        wanted = normalize_scopes(scopes)
        blocking = []
        for claim in self.live(now):
            if claim.get("agent") == agent:
                continue
            for mine in wanted:
                if any(scopes_conflict(mine, theirs) for theirs in claim.get("scopes", [])):
                    blocking.append(claim)
                    break
        return blocking

    def acquire(
        self,
        *,
        agent: str,
        scopes: List[str],
        session_label: str,
        stale_after_hours: Optional[float] = None,
        takeover: bool = False,
        reason: Optional[str] = None,
        now: Optional[str] = None,
    ) -> Dict[str, Any]:
        wanted = normalize_scopes(scopes)
        hours = float(stale_after_hours or config_mod.claim_stale_hours(self.paths))
        with locked(self.paths):
            data = self._load()
            timestamp = now or utc_now()

            blocking = []
            for claim in data["claims"]:
                if not self._is_fresh(claim, timestamp) or claim.get("agent") == agent:
                    continue
                for mine in wanted:
                    if any(scopes_conflict(mine, theirs) for theirs in claim.get("scopes", [])):
                        blocking.append(claim)
                        break
            if blocking:
                owners = ", ".join(
                    "{0} holds {1} ({2})".format(c.get("agent"), ",".join(c.get("scopes", [])), c.get("session_label"))
                    for c in blocking
                )
                raise ClaimConflict(
                    "scope is held by another agent: {0}. Work elsewhere, or take over once it goes stale.".format(owners),
                    blocking,
                )

            taken_over = []
            if takeover:
                if not str(reason or "").strip():
                    raise TaosError("a takeover needs --reason")
                for claim in data["claims"]:
                    if claim.get("status") != "live" or claim.get("agent") == agent:
                        continue
                    if self._is_fresh(claim, timestamp):
                        continue
                    for mine in wanted:
                        if any(scopes_conflict(mine, theirs) for theirs in claim.get("scopes", [])):
                            claim["status"] = "taken_over"
                            claim["released_at"] = timestamp
                            taken_over.append(claim["id"])
                            break
                if not taken_over:
                    raise TaosError("nothing stale to take over on those scopes")
                events_mod.emit(
                    self.paths,
                    "claim_takeover",
                    agent,
                    scopes=wanted,
                    reason=str(reason),
                    taken_over=taken_over,
                )

            for claim in data["claims"]:
                if claim.get("agent") != agent or claim.get("status") != "live":
                    continue
                if set(claim.get("scopes", [])) >= set(wanted):
                    claim["heartbeat_at"] = timestamp
                    claim["session_label"] = str(session_label)
                    events_mod.emit(self.paths, "claim_heartbeat", agent, claim_id=claim["id"], scopes=claim["scopes"])
                    self._save(data)
                    return claim

            claim = {
                "id": short_id("clm_"),
                "agent": agent,
                "scopes": wanted,
                "session_label": str(session_label),
                "claimed_at": timestamp,
                "heartbeat_at": timestamp,
                "stale_after_hours": hours,
                "status": "live",
                "released_at": None,
                "takeover_of": taken_over or None,
            }
            events_mod.emit(
                self.paths,
                "claim_acquire",
                agent,
                claim_id=claim["id"],
                scopes=wanted,
                session_label=str(session_label),
            )
            data["claims"].append(claim)
            self._save(data)
            return claim

    def heartbeat(self, claim_id: str, agent: str, now: Optional[str] = None) -> Dict[str, Any]:
        with locked(self.paths):
            data = self._load()
            for claim in data["claims"]:
                if claim.get("id") != str(claim_id):
                    continue
                if claim.get("agent") != agent:
                    raise TaosError("claim {0} belongs to {1}".format(claim_id, claim.get("agent")))
                if claim.get("status") != "live":
                    raise TaosError("claim {0} is {1}".format(claim_id, claim.get("status")))
                claim["heartbeat_at"] = now or utc_now()
                events_mod.emit(self.paths, "claim_heartbeat", agent, claim_id=claim["id"], scopes=claim.get("scopes"))
                self._save(data)
                return claim
        raise TaosError("no such claim: {0}".format(claim_id))

    def release(
        self,
        claim_id: str,
        agent: str,
        now: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        with locked(self.paths):
            data = self._load()
            for claim in data["claims"]:
                if claim.get("id") != str(claim_id):
                    continue
                if claim.get("agent") != agent and not force:
                    raise TaosError(
                        "claim {0} belongs to {1}; only the holder releases it (or a human with --force)".format(
                            claim_id, claim.get("agent")
                        )
                    )
                claim["status"] = "released"
                claim["released_at"] = now or utc_now()
                events_mod.emit(self.paths, "claim_release", agent, claim_id=claim["id"], scopes=claim.get("scopes"))
                self._save(data)
                return claim
        raise TaosError("no such claim: {0}".format(claim_id))

    def release_by_scope(self, scope: str, agent: str) -> List[Dict[str, Any]]:
        target = normalize_scopes([scope])[0]
        released = []
        with locked(self.paths):
            data = self._load()
            for claim in data["claims"]:
                if claim.get("status") != "live" or claim.get("agent") != agent:
                    continue
                if any(scopes_conflict(target, held) for held in claim.get("scopes", [])):
                    claim["status"] = "released"
                    claim["released_at"] = utc_now()
                    events_mod.emit(self.paths, "claim_release", agent, claim_id=claim["id"], scopes=claim.get("scopes"))
                    released.append(claim)
            if released:
                self._save(data)
        return released


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _describe(claim: Dict[str, Any], fresh: bool) -> str:
    return "{0}  {1:<7} {2:<28} {3}  age {4:.1f}h{5}".format(
        claim.get("id"),
        claim.get("agent"),
        ",".join(claim.get("scopes", []))[:28],
        claim.get("session_label", "")[:34],
        age_hours(claim.get("heartbeat_at", claim.get("claimed_at", utc_now()))),
        "" if fresh else "  STALE",
    )


def _cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    store = ClaimStore(paths)
    live = store.live()
    stale = store.stale()
    if args.json:
        print(json.dumps({"live": live, "stale": stale}, indent=2, sort_keys=True))
        return 0
    if not live and not stale:
        print("no live claims")
        return 0
    for claim in live:
        print(_describe(claim, True))
    for claim in stale:
        print(_describe(claim, False))
    return 0


def _cmd_acquire(args: argparse.Namespace, paths: Paths) -> int:
    claim = ClaimStore(paths).acquire(
        agent=args.agent,
        scopes=args.scope,
        session_label=args.session,
        stale_after_hours=args.stale_after_hours,
        takeover=args.takeover,
        reason=args.reason,
    )
    print("claimed {0}: {1}".format(claim["id"], ", ".join(claim["scopes"])))
    return 0


def _cmd_heartbeat(args: argparse.Namespace, paths: Paths) -> int:
    claim = ClaimStore(paths).heartbeat(args.id, args.agent)
    print("heartbeat {0} at {1}".format(claim["id"], claim["heartbeat_at"]))
    return 0


def _cmd_release(args: argparse.Namespace, paths: Paths) -> int:
    store = ClaimStore(paths)
    if args.id:
        claim = store.release(args.id, args.agent, force=args.force)
        print("released {0}".format(claim["id"]))
        return 0
    released = store.release_by_scope(args.scope, args.agent)
    print("released {0} claim(s)".format(len(released)))
    return 0


def _cmd_check(args: argparse.Namespace, paths: Paths) -> int:
    blocking = ClaimStore(paths).check(args.scope, args.agent)
    if not blocking:
        print("free")
        return 0
    for claim in blocking:
        print("held by {0}: {1} ({2})".format(claim.get("agent"), ",".join(claim.get("scopes", [])), claim.get("session_label")))
    return 4


def register(subparsers: Any) -> None:
    claim = subparsers.add_parser("claim", help="hold or release a scope")
    sub = claim.add_subparsers(dest="claim_cmd", required=True)

    status = sub.add_parser("status", help="show live and stale claims")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=_cmd_status)

    acquire = sub.add_parser("acquire", help="take a scope")
    acquire.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    acquire.add_argument("--scope", action="append", required=True)
    acquire.add_argument("--session", required=True)
    acquire.add_argument("--stale-after-hours", dest="stale_after_hours", type=float)
    acquire.add_argument("--takeover", action="store_true")
    acquire.add_argument("--reason")
    acquire.set_defaults(func=_cmd_acquire)

    heartbeat = sub.add_parser("heartbeat", help="keep a claim alive")
    heartbeat.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    heartbeat.add_argument("--id", required=True)
    heartbeat.set_defaults(func=_cmd_heartbeat)

    release = sub.add_parser("release", help="give a scope back")
    release.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    group = release.add_mutually_exclusive_group(required=True)
    group.add_argument("--id")
    group.add_argument("--scope")
    release.add_argument("--force", action="store_true", help="human override for another agent's claim")
    release.set_defaults(func=_cmd_release)

    check = sub.add_parser("check", help="is a scope free for me")
    check.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    check.add_argument("--scope", action="append", required=True)
    check.set_defaults(func=_cmd_check)
