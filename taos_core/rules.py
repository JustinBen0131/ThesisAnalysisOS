"""Dated rules: an instruction keeps its date, its scope and its limits.

Saving a lesson tends to strip what made it valid. "This week" disappears, a
rule for one task is applied to all, and a superseded instruction lives on in
a summary. A rule here is the original quotation with the date it was said,
where it applies, when it lapses and what it replaced.

Whether a rule governs is a question about a scope and a day, and the answer
for a past day never changes because something was said later:

  it governs    its scope covers the one asked about, the day is inside
                [said_on, expires], and no replacement displaces it there
  displaced     a rule that names it in `supersedes` is itself in its
                interval on that day and covers the scope asked about

So a replacement takes effect on its own date and only inside its own scope.
A narrow exception leaves the general rule in force elsewhere, and a
temporary replacement gives the rule back when it lapses.

Anything derived from a rule carries the original's hash, and an audit finds
notes whose original has lapsed, been replaced or changed.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from . import _science as sci
from . import basis
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


def add(paths: Paths, *, quote: str, said_on: str, scope: str, expires: Optional[str] = None,
        supersedes: Optional[str] = None, by: str = "human") -> Dict[str, Any]:
    rule = {"id": short_id("rule_"), "quote": sci.need(quote, "the original quotation"),
            "said_on": basis.day(sci.need(said_on, "the date it was said"), "said_on"),
            "scope": sci.need(scope, "a scope"), "expires": basis.day(expires, "expires") if expires else None,
            "supersedes": supersedes, "added_at": utc_now(), "added_by": by}
    if rule["expires"] and rule["expires"] < rule["said_on"]:
        raise TaosError("a rule cannot lapse before it was said")
    rule["sha256"] = _digest(rule)
    with locked(paths):
        data = _load(paths)
        if supersedes:
            sci.find(data["rules"], supersedes, "rule")   # the replaced rule must exist; it is never edited
        data["rules"].append(rule)
        sci.save(paths, "rules", data)
        events_mod.emit(paths, "rule_add", by, rule_id=rule["id"], scope=rule["scope"], expires=rule["expires"])
    return rule


def covers(rule_scope: str, scope: str) -> bool:
    return rule_scope == "*" or scope == rule_scope or scope.startswith(rule_scope + "/")


def in_force(rule: Dict[str, Any], on: str) -> bool:
    """Is the day inside the rule's own interval? Replacement is a separate question; see `displaced_by`."""
    return basis.within(rule["said_on"], rule.get("expires"), on)


def displaced_by(rule: Dict[str, Any], rules: List[Dict[str, Any]], scope: str, on: str) -> Optional[Dict[str, Any]]:
    """The replacement that governs instead of `rule` for this scope on this day, if there is one."""
    for other in rules:
        if other.get("supersedes") == rule["id"] and in_force(other, on) and covers(other["scope"], scope):
            return other
    return None


def _governing(rules: List[Dict[str, Any]], scope: str, on: str) -> List[Dict[str, Any]]:
    found = [rule for rule in rules
             if covers(rule["scope"], scope) and in_force(rule, on) and displaced_by(rule, rules, scope, on) is None]
    # the most specific scope first, then the most recent
    return sorted(found, key=lambda rule: (rule["scope"] != "*", len(rule["scope"]), rule["said_on"]), reverse=True)


def governing(paths: Paths, scope: str, on: Optional[str] = None, known_by: Optional[str] = None) -> List[Dict[str, Any]]:
    """The passages that govern `scope` on a day: the passage, not the file.

    `known_by` answers a different question, what could have been known on a
    day: rules recorded after it are left out, so a replay of an old decision
    is not shown instructions from its future.
    """
    when = basis.day(on, "on") if on else basis.today()
    rules = _load(paths)["rules"]
    if known_by:
        limit = basis.day(known_by, "known-by")
        rules = [rule for rule in rules if str(rule.get("added_at", ""))[:10] <= limit]
    return _governing(rules, scope, when)


def for_task(paths: Paths, task: Dict[str, Any], on: Optional[str] = None) -> List[Dict[str, Any]]:
    """The rules that govern a task: those scoped to its id, to any of its labels, or to everything."""
    when = basis.day(on, "on") if on else basis.today()
    rules = _load(paths)["rules"]
    found: Dict[str, Dict[str, Any]] = {}
    for scope in [str(task.get("id"))] + [str(label) for label in task.get("labels") or []]:
        for rule in _governing(rules, scope, when):
            found.setdefault(rule["id"], rule)
    return list(found.values())


def binding(paths: Paths, task: Dict[str, Any]) -> Dict[str, str]:
    """What a closure or an acceptance records: which instructions governed, by hash."""
    return {rule["id"]: _digest(rule) for rule in for_task(paths, task)}


def changes_since(paths: Paths, task: Dict[str, Any], bound: Dict[str, str]) -> List[str]:
    """How today's governing instructions differ from a recorded binding, in words."""
    now = {rule["id"]: rule for rule in for_task(paths, task)}
    known = {rule["id"]: rule for rule in _load(paths)["rules"]}
    out = []
    for rule_id in sorted(set(bound) - set(now)):
        rule = known.get(rule_id)
        out.append("{0} no longer governs{1}".format(rule_id, " (\"{0}\")".format(rule["quote"]) if rule else ""))
    for rule_id in sorted(set(now) - set(bound)):
        out.append("{0} governs now and is not one this was recorded under (\"{1}\", said {2})".format(
            rule_id, now[rule_id]["quote"], now[rule_id]["said_on"]))
    for rule_id in sorted(set(now) & set(bound)):
        if _digest(now[rule_id]) != bound[rule_id]:
            out.append("{0} was edited".format(rule_id))
    return out


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
    when = basis.day(on, "on") if on else basis.today()
    data = _load(paths)
    by_id = {rule["id"]: rule for rule in data["rules"]}
    findings = []
    for note in data["notes"]:
        rule = by_id.get(note["rule_id"])
        if rule is None:
            reason = "its original is missing"
        elif _digest(rule) != note["rule_sha256"]:
            reason = "its original changed after the note was made"
        elif not in_force(rule, when):
            reason = ("its original lapsed on {0}".format(rule["expires"]) if rule.get("expires") and when > rule["expires"]
                      else "its original does not apply until {0}".format(rule["said_on"]))
        else:
            narrower = [other for other in data["rules"] if other.get("supersedes") == rule["id"] and in_force(other, when)]
            if not narrower:
                continue
            other = narrower[0]
            whole = covers(other["scope"], rule["scope"])
            reason = "its original was replaced by {0} from {1}{2}".format(
                other["id"], other["said_on"], "" if whole else ", for {0}".format(other["scope"]))
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
    rules = governing(paths, args.scope, args.on, args.known_by)
    if args.json:
        print(json.dumps(rules, indent=2, sort_keys=True))
        return 0
    if not rules:
        print("no rule governs {0}".format(args.scope))
    for rule in rules:
        until = "until {0}".format(rule["expires"]) if rule["expires"] else "no expiry"
        print("{0}  said {1}, {2}, scope {3}".format(rule["id"], rule["said_on"], until, rule["scope"]))
        print("    \"{0}\"".format(rule["quote"]))
    if len(rules) > 1:
        print("{0} passages govern; the most specific is first. If two disagree, record which replaces which.".format(len(rules)))
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
    adder.add_argument("--said-on", required=True, help="YYYY-MM-DD, the day it takes effect")
    adder.add_argument("--scope", required=True, help="where it applies: a topic such as plots or plots/labels, a task id, or *")
    adder.add_argument("--expires", help="YYYY-MM-DD, the last day it is in force")
    adder.add_argument("--supersedes", help="the rule this one replaces, from its own date and inside its own scope")
    adder.add_argument("--by", default="human", choices=agents)
    adder.set_defaults(func=_cmd_add)

    gov = sub.add_parser("governing", help="the passages in force for a scope on a date")
    gov.add_argument("scope")
    gov.add_argument("--on", help="YYYY-MM-DD (default today)")
    gov.add_argument("--known-by", help="YYYY-MM-DD: leave out rules recorded after this day")
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
