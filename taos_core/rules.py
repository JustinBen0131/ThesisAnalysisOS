"""Dated rules: an instruction keeps its date, its scope and its limits.

Saving a lesson tends to strip what made it valid. "This week" disappears, a
rule for one task is applied to all, and a superseded instruction lives on in
a summary. A rule here is the original quotation with the date it was said,
where it applies, when it lapses and what it replaced. Anything derived from
it carries the original's hash, and an audit finds notes whose original has
lapsed, been replaced or changed. A program that acts on a rule asks for the
rules in force on a date; it never reads a summary.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from . import _science as sci
from . import events as events_mod
from .paths import Paths
from .store import canonical_json, locked, sha256_text, utc_now
from .util import TaosError, short_id


def _digest(rule: Dict[str, Any]) -> str:
    return sha256_text(canonical_json({key: rule[key] for key in ("quote", "said_on", "scope", "expires")}))


def _load(paths: Paths) -> Dict[str, Any]:
    data = sci.load(paths, "rules", "rules")
    data.setdefault("notes", [])
    return data


def _date(value: Optional[str], what: str) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value)
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise TaosError("{0} must be YYYY-MM-DD".format(what))
    return text


def add(paths: Paths, *, quote: str, said_on: str, scope: str, expires: Optional[str] = None,
        supersedes: Optional[str] = None, by: str = "human") -> Dict[str, Any]:
    rule = {"id": short_id("rule_"), "quote": sci.need(quote, "the original quotation"),
            "said_on": _date(sci.need(said_on, "the date it was said"), "said_on"),
            "scope": sci.need(scope, "a scope"), "expires": _date(expires, "expires"),
            "supersedes": supersedes, "superseded_by": None, "added_at": utc_now(), "added_by": by}
    rule["sha256"] = _digest(rule)
    with locked(paths):
        data = _load(paths)
        if supersedes:
            sci.find(data["rules"], supersedes, "rule")["superseded_by"] = rule["id"]
        data["rules"].append(rule)
        sci.save(paths, "rules", data)
        events_mod.emit(paths, "rule_add", by, rule_id=rule["id"], scope=rule["scope"], expires=rule["expires"])
    return rule


def in_force(rule: Dict[str, Any], on: str) -> bool:
    if rule.get("superseded_by") or rule["said_on"] > on:
        return False
    return rule["expires"] is None or on <= rule["expires"]


def _covers(rule_scope: str, scope: str) -> bool:
    return rule_scope == "*" or scope == rule_scope or scope.startswith(rule_scope + "/")


def governing(paths: Paths, scope: str, on: Optional[str] = None) -> List[Dict[str, Any]]:
    """The passages that govern `scope` on a date: the passage, not the file."""
    day = _date(on, "on") or utc_now()[:10]
    rules = [rule for rule in _load(paths)["rules"] if _covers(rule["scope"], scope) and in_force(rule, day)]
    return sorted(rules, key=lambda rule: rule["said_on"], reverse=True)


def derive(paths: Paths, rule_id: str, text: str, by: str = "human") -> Dict[str, Any]:
    """A note made from a rule. It carries the original's hash, date and expiry."""
    with locked(paths):
        data = _load(paths)
        rule = sci.find(data["rules"], rule_id, "rule")
        note = {"id": short_id("note_"), "rule_id": rule_id, "rule_sha256": rule["sha256"], "said_on": rule["said_on"],
                "expires": rule["expires"], "text": sci.need(text, "the note text"), "made_at": utc_now(), "made_by": by}
        data["notes"].append(note)
        sci.save(paths, "rules", data)
    return note


def audit(paths: Paths, on: Optional[str] = None) -> List[Dict[str, Any]]:
    """Derived notes that can no longer be trusted, each with the reason."""
    day = _date(on, "on") or utc_now()[:10]
    data = _load(paths)
    by_id = {rule["id"]: rule for rule in data["rules"]}
    findings = []
    for note in data["notes"]:
        rule = by_id.get(note["rule_id"])
        if rule is None:
            reason = "its original is missing"
        elif _digest(rule) != note["rule_sha256"]:
            reason = "its original changed after the note was made"
        elif rule.get("superseded_by"):
            reason = "its original was replaced by {0}".format(rule["superseded_by"])
        elif not in_force(rule, day):
            reason = "its original lapsed on {0}".format(rule["expires"])
        else:
            continue
        findings.append({"note": note["id"], "rule": note["rule_id"], "reason": reason, "text": note["text"]})
    return findings


# --------------------------------------------------------------------------


def _cmd_add(args: argparse.Namespace, paths: Paths) -> int:
    rule = add(paths, quote=args.quote, said_on=args.said_on, scope=args.scope, expires=args.expires,
               supersedes=args.supersedes, by=args.by)
    print("added {0} for {1}{2}".format(rule["id"], rule["scope"],
                                        ", in force until {0}".format(rule["expires"]) if rule["expires"] else ""))
    return 0


def _cmd_governing(args: argparse.Namespace, paths: Paths) -> int:
    rules = governing(paths, args.scope, args.on)
    if args.json:
        print(json.dumps(rules, indent=2, sort_keys=True))
        return 0
    if not rules:
        print("no rule governs {0}".format(args.scope))
    for rule in rules:
        until = "until {0}".format(rule["expires"]) if rule["expires"] else "no expiry"
        print("{0}  said {1}, {2}".format(rule["id"], rule["said_on"], until))
        print("    \"{0}\"".format(rule["quote"]))
    return 0


def _cmd_derive(args: argparse.Namespace, paths: Paths) -> int:
    note = derive(paths, args.rule_id, args.text, args.by)
    print("made {0} from {1}; it carries the original's hash".format(note["id"], note["rule_id"]))
    return 0


def _cmd_audit(args: argparse.Namespace, paths: Paths) -> int:
    findings = audit(paths, args.on)
    if args.json:
        print(json.dumps(findings, indent=2, sort_keys=True))
    elif not findings:
        print("every derived note still stands on a rule in force")
    else:
        for finding in findings:
            print("{0}: {1}".format(finding["note"], finding["reason"]))
    return 1 if findings else 0


def register(subparsers: Any) -> None:
    rule = subparsers.add_parser("rule", help="instructions that keep their date, scope and limits")
    sub = rule.add_subparsers(dest="rule_cmd", required=True)
    agents = list(events_mod.AGENTS)

    adder = sub.add_parser("add", help="save an instruction as its original words")
    adder.add_argument("--quote", required=True)
    adder.add_argument("--said-on", required=True, help="YYYY-MM-DD")
    adder.add_argument("--scope", required=True, help="where it applies, e.g. plots or plots/labels, or *")
    adder.add_argument("--expires", help="YYYY-MM-DD, the last day it is in force")
    adder.add_argument("--supersedes", help="the rule this one replaces")
    adder.add_argument("--by", default="human", choices=agents)
    adder.set_defaults(func=_cmd_add)

    gov = sub.add_parser("governing", help="the passages in force for a scope on a date")
    gov.add_argument("scope")
    gov.add_argument("--on", help="YYYY-MM-DD (default today)")
    gov.add_argument("--json", action="store_true")
    gov.set_defaults(func=_cmd_governing)

    deriver = sub.add_parser("derive", help="make a note that carries its original's hash")
    deriver.add_argument("rule_id")
    deriver.add_argument("--text", required=True)
    deriver.add_argument("--by", default="human", choices=agents)
    deriver.set_defaults(func=_cmd_derive)

    auditor = sub.add_parser("audit", help="find notes whose original lapsed, changed or was replaced")
    auditor.add_argument("--on", help="YYYY-MM-DD (default today)")
    auditor.add_argument("--json", action="store_true")
    auditor.set_defaults(func=_cmd_audit)
