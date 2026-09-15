"""Proposals: how the OS changes itself, with a human in the loop."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from . import events as events_mod
from .paths import Paths
from .store import atomic_write_json, locked, read_json, utc_now
from .util import TaosError, short_id

KINDS = ("atom", "policy", "kernel", "retire", "cleanup", "other")
STATUSES = ("proposed", "accepted", "rejected")


def all_proposals(paths: Paths) -> List[Dict[str, Any]]:
    if not paths.proposals_dir.is_dir():
        return []
    items = []
    for path in sorted(paths.proposals_dir.glob("prop_*.json")):
        data = read_json(path)
        if isinstance(data, dict):
            items.append(data)
    items.sort(key=lambda p: p.get("proposed_at", ""))
    return items


def open_proposals(paths: Paths) -> List[Dict[str, Any]]:
    return [p for p in all_proposals(paths) if p.get("status") == "proposed"]


def get(paths: Paths, proposal_id: str) -> Dict[str, Any]:
    path = paths.proposals_dir / "{0}.json".format(proposal_id)
    data = read_json(path)
    if not isinstance(data, dict):
        raise TaosError("no such proposal: {0}".format(proposal_id))
    return data


def propose(
    paths: Paths,
    *,
    kind: str,
    title: str,
    body: str,
    evidence: Optional[List[str]],
    agent: str,
    atom: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if kind not in KINDS:
        raise TaosError("proposal kind must be one of {0}".format(", ".join(KINDS)))
    if not str(title or "").strip():
        raise TaosError("a proposal needs a title")
    if not str(body or "").strip():
        raise TaosError("a proposal needs a body saying what changes and why")
    if kind == "atom" and atom is not None:
        from . import atoms as atoms_mod

        problems = atoms_mod.validate_atom(atom)
        if problems:
            raise TaosError("atom is not checkable: {0}".format("; ".join(problems)))
    with locked(paths):
        paths.ensure_state()
        proposal = {
            "id": short_id("prop_"),
            "kind": kind,
            "title": str(title).strip(),
            "body": str(body).strip(),
            "evidence": [str(e) for e in (evidence or [])],
            "proposed_by": agent,
            "proposed_at": utc_now(),
            "status": "proposed",
            "decided_by": None,
            "decided_at": None,
            "note": None,
            "atom": atom,
        }
        atomic_write_json(paths.proposals_dir / "{0}.json".format(proposal["id"]), proposal)
        events_mod.emit(paths, "proposal_create", agent, proposal_id=proposal["id"], kind=kind, title=proposal["title"])
        return proposal


def decide(paths: Paths, *, proposal_id: str, status: str, by: str = "human", note: Optional[str] = None) -> Dict[str, Any]:
    if status not in ("accepted", "rejected"):
        raise TaosError("a proposal is accepted or rejected")
    with locked(paths):
        proposal = get(paths, proposal_id)
        if proposal.get("status") != "proposed":
            raise TaosError("proposal {0} is already {1}".format(proposal_id, proposal.get("status")))
        proposal["status"] = status
        proposal["decided_by"] = by
        proposal["decided_at"] = utc_now()
        proposal["note"] = str(note) if note else None
        atomic_write_json(paths.proposals_dir / "{0}.json".format(proposal["id"]), proposal)
        events_mod.emit(paths, "proposal_decide", by, proposal_id=proposal["id"], status=status)
        return proposal


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_propose(args: argparse.Namespace, paths: Paths) -> int:
    atom = None
    if args.atom_json:
        atom = read_json(args.atom_json)
        if not isinstance(atom, dict):
            raise TaosError("--atom-json must point at a JSON object")
    proposal = propose(
        paths,
        kind=args.kind,
        title=args.title,
        body=args.body,
        evidence=args.evidence or [],
        agent=args.agent,
        atom=atom,
    )
    print("proposed {0}: {1}".format(proposal["id"], proposal["title"]))
    return 0


def _cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    items = all_proposals(paths) if args.all else open_proposals(paths)
    if args.json:
        print(json.dumps(items, indent=2, sort_keys=True))
        return 0
    if not items:
        print("no proposals")
        return 0
    for proposal in items:
        print("{0}  {1:<8} {2:<9} {3}".format(proposal["id"], proposal["kind"], proposal["status"], proposal["title"]))
    return 0


def _cmd_decide(args: argparse.Namespace, paths: Paths) -> int:
    proposal = decide(paths, proposal_id=args.proposal_id, status=args.status, note=args.note)
    print("{0} {1}".format(proposal["id"], proposal["status"]))
    if proposal["status"] == "accepted" and proposal.get("kind") == "atom" and proposal.get("atom"):
        print("promote it into the checker with: taos atoms promote {0} --by human".format(proposal["id"]))
    return 0


def register(subparsers: Any) -> None:
    propose_parser = subparsers.add_parser("propose", help="propose a change to the OS itself")
    propose_parser.add_argument("--agent", required=True, choices=list(events_mod.AGENTS))
    propose_parser.add_argument("--kind", required=True, choices=list(KINDS))
    propose_parser.add_argument("--title", required=True)
    propose_parser.add_argument("--body", required=True)
    propose_parser.add_argument("--evidence", action="append")
    propose_parser.add_argument("--atom-json", dest="atom_json", help="file holding a checkable atom")
    propose_parser.set_defaults(func=_cmd_propose)

    proposals = subparsers.add_parser("proposals", help="review proposals")
    sub = proposals.add_subparsers(dest="proposals_cmd", required=True)

    listing = sub.add_parser("list", help="list proposals")
    listing.add_argument("--all", action="store_true")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(func=_cmd_list)

    decider = sub.add_parser("decide", help="accept or reject a proposal")
    decider.add_argument("proposal_id")
    decider.add_argument("--status", required=True, choices=["accepted", "rejected"])
    decider.add_argument("--note")
    decider.set_defaults(func=_cmd_decide)
