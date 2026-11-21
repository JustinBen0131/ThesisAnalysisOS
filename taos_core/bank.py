"""The decision bank: test whether the system still understands you.

A case is a real past request, the earlier instruction that governed it, and
the action that was right. The bank replays every case under three arms:

  U  unhinted         the request alone
  N  source named     the request and the name of the file that holds the rule
  O  passage supplied the request and the governing passage itself

U against O separates two failures that look alike from outside: the reader
could not find the rule, or the reader had the rule and still chose wrong.

The bank never calls a model. It writes the prompts, and it scores answers
that a reader (a person or any model) returns in a file. A reader's results
count only after it passes control cases, and the pass lines are sealed
before any answer is scored.
"""

from __future__ import annotations

import argparse
import json
from math import comb
from pathlib import Path
from typing import Any, Dict, List

from . import _science as sci
from . import events as events_mod
from .paths import Paths
from .store import canonical_json, locked, read_json, sha256_text, utc_now
from .util import TaosError, short_id

ARMS = ("U", "N", "O")


def _load(paths: Paths) -> Dict[str, Any]:
    data = sci.load(paths, "bank", "cases")
    data.setdefault("pass_lines", None)
    data.setdefault("runs", [])
    return data


def add_case(paths: Paths, *, request: str, passage: str, source: str, options: List[str], expected: str,
             control: bool = False, by: str = "human") -> Dict[str, Any]:
    options = [str(option) for option in options]
    if len(options) < 2 or expected not in options:
        raise TaosError("a case needs at least two options, and the expected action must be one of them")
    case = {"id": short_id("case_"), "request": sci.need(request, "the request"),
            "passage": sci.need(passage, "the governing passage"), "source": sci.need(source, "the source name"),
            "options": options, "expected": expected, "control": bool(control), "added_at": utc_now(), "added_by": by}
    with locked(paths):
        data = _load(paths)
        if data["pass_lines"]:
            raise TaosError("the pass lines are sealed; a bank is frozen once its lines are sealed")
        data["cases"].append(case)
        sci.save(paths, "bank", data)
    return case


def prompts(paths: Paths, arm: str) -> List[Dict[str, Any]]:
    """What a reader sees under one arm. The expected action is never included."""
    if arm not in ARMS:
        raise TaosError("arm must be one of: {0}".format(", ".join(ARMS)))
    out = []
    for case in _load(paths)["cases"]:
        prompt = {"case": case["id"], "request": case["request"], "options": case["options"]}
        if arm == "N":
            prompt["source"] = case["source"]
        if arm == "O":
            prompt["passage"] = case["passage"]
        out.append(prompt)
    return out


def seal_lines(paths: Paths, *, controls_right: int, by: str = "human") -> Dict[str, Any]:
    """Fix how a reader qualifies, before any answer is scored. Sealing also freezes the cases."""
    with locked(paths):
        data = _load(paths)
        controls = [case for case in data["cases"] if case["control"]]
        if data["pass_lines"]:
            raise TaosError("the pass lines are already sealed")
        if not controls or not 0 < controls_right <= len(controls):
            raise TaosError("add control cases first; the line must be between 1 and the number of controls")
        lines = {"controls_right": int(controls_right), "controls": len(controls), "sealed_at": utc_now(),
                 "sealed_by": by, "cases_sha256": sha256_text(canonical_json(data["cases"]))}
        data["pass_lines"] = lines
        sci.save(paths, "bank", data)
        events_mod.emit(paths, "bank_seal", by, controls_right=controls_right, cases=len(data["cases"]))
    return lines


def sign_test(gains: int, losses: int) -> float:
    """Exact two-sided sign test on paired outcomes that changed."""
    changed = gains + losses
    if changed == 0:
        return 1.0
    tail = sum(comb(changed, k) for k in range(0, min(gains, losses) + 1))
    return min(1.0, 2.0 * tail / float(2 ** changed))


def score(paths: Paths, reader: str, answers: Dict[str, Dict[str, str]], by: str = "human") -> Dict[str, Any]:
    """Score one reader. `answers` maps arm to {case id: chosen option}."""
    with locked(paths):
        data = _load(paths)
        lines = data["pass_lines"]
        if not lines:
            raise TaosError("seal the pass lines before scoring: taos bank seal --controls-right N")
        if sha256_text(canonical_json(data["cases"])) != lines["cases_sha256"]:
            raise TaosError("the cases changed after the pass lines were sealed")
        by_id = {case["id"]: case for case in data["cases"]}

        def right(arm: str, case_id: str) -> bool:
            return answers.get(arm, {}).get(case_id) == by_id[case_id]["expected"]

        controls = [cid for cid, case in by_id.items() if case["control"]]
        real = [cid for cid, case in by_id.items() if not case["control"]]
        controls_right = sum(1 for cid in controls if right("O", cid))
        qualified = controls_right >= lines["controls_right"]
        per_arm = {arm: {"right": sum(1 for cid in real if right(arm, cid)),
                         "answered": sum(1 for cid in real if cid in answers.get(arm, {}))} for arm in ARMS}
        paired = [cid for cid in real if cid in answers.get("U", {}) and cid in answers.get("O", {})]
        gains = sum(1 for cid in paired if right("O", cid) and not right("U", cid))
        losses = sum(1 for cid in paired if right("U", cid) and not right("O", cid))
        result = {
            "id": short_id("run_"), "reader": sci.need(reader, "a reader name"), "scored_at": utc_now(),
            "controls_right": controls_right, "controls": len(controls), "qualified": qualified, "cases": len(real),
            "arms": per_arm, "paired": len(paired), "gains": gains, "losses": losses,
            "sign_test_p": sign_test(gains, losses),
            "reading": ("counts" if qualified else "does not count: the reader failed its controls"),
        }
        data["runs"].append(result)
        sci.save(paths, "bank", data)
        events_mod.emit(paths, "bank_score", by, run_id=result["id"], reader=result["reader"], qualified=qualified)
    return result


# --------------------------------------------------------------------------


def _cmd_add(args: argparse.Namespace, paths: Paths) -> int:
    case = add_case(paths, request=args.request, passage=args.passage, source=args.source, options=args.option or [],
                    expected=args.expected, control=args.control, by=args.by)
    print("added {0}{1}".format(case["id"], " (control)" if case["control"] else ""))
    return 0


def _cmd_prompts(args: argparse.Namespace, paths: Paths) -> int:
    print(json.dumps({"arm": args.arm, "prompts": prompts(paths, args.arm)}, indent=2, sort_keys=True))
    return 0


def _cmd_seal(args: argparse.Namespace, paths: Paths) -> int:
    lines = seal_lines(paths, controls_right=args.controls_right, by=args.by)
    print("sealed: a reader counts with {0} of {1} controls right".format(lines["controls_right"], lines["controls"]))
    return 0


def _cmd_score(args: argparse.Namespace, paths: Paths) -> int:
    payload = read_json(Path(args.answers).expanduser())
    if not isinstance(payload, dict) or not isinstance(payload.get("arms"), dict):
        raise TaosError("the answers file needs {\"reader\": ..., \"arms\": {\"U\": {...}, \"O\": {...}}}")
    result = score(paths, payload.get("reader") or args.reader or "", payload["arms"], by=args.by)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print("{0}: controls {1} of {2}; this run {3}".format(result["reader"], result["controls_right"],
                                                         result["controls"], result["reading"]))
    for arm in ARMS:
        print("  arm {0}: {1} right of {2} answered".format(arm, result["arms"][arm]["right"], result["arms"][arm]["answered"]))
    print("  U against O on {0} paired cases: {1} gains, {2} losses, exact sign test p = {3:.3f}".format(
        result["paired"], result["gains"], result["losses"], result["sign_test_p"]))
    return 0


def register(subparsers: Any) -> None:
    bank = subparsers.add_parser("bank", help="replay past decisions as a standing test")
    sub = bank.add_subparsers(dest="bank_cmd", required=True)
    agents = list(events_mod.AGENTS)

    adder = sub.add_parser("add", help="add a past decision as a case")
    adder.add_argument("--request", required=True)
    adder.add_argument("--passage", required=True, help="the earlier instruction that governed it, verbatim")
    adder.add_argument("--source", required=True, help="the name of the file that holds the passage")
    adder.add_argument("--option", action="append", help="one possible action; repeat")
    adder.add_argument("--expected", required=True, help="the action that was right")
    adder.add_argument("--control", action="store_true", help="a known-answer case used to qualify readers")
    adder.add_argument("--by", default="human", choices=agents)
    adder.set_defaults(func=_cmd_add)

    prompter = sub.add_parser("prompts", help="what a reader sees under one arm")
    prompter.add_argument("arm", choices=list(ARMS))
    prompter.set_defaults(func=_cmd_prompts)

    sealer = sub.add_parser("seal", help="fix the qualification line before any scoring")
    sealer.add_argument("--controls-right", required=True, type=int)
    sealer.add_argument("--by", default="human", choices=agents)
    sealer.set_defaults(func=_cmd_seal)

    scorer = sub.add_parser("score", help="score a reader's answers file")
    scorer.add_argument("answers")
    scorer.add_argument("--reader")
    scorer.add_argument("--by", default="human", choices=agents)
    scorer.add_argument("--json", action="store_true")
    scorer.set_defaults(func=_cmd_score)
