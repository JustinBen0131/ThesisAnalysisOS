"""Correction atoms: a lesson is only learned when a machine can check it."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Optional

from . import events as events_mod
from . import proposals as proposals_mod
from .paths import Paths
from .store import atomic_write_json, locked, read_json, utc_now
from .util import TaosError

ATOMS_SCHEMA = "TAOS_ATOMS_V1"
CHECK_TYPES = ("regex_must_match", "regex_must_not_match", "file_must_exist", "taos_command_exit_zero")
VIRTUAL_TARGETS = ("latest_handoff", "agents_md", "claude_md")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,60}$")
# Only readers that do not write state, execute gates, or invoke atoms again.
READ_ONLY_COMMANDS = (
    ("policy", "check"),
    ("policy", "list"),
    ("policy", "show"),
    ("task", "list"),
    ("task", "show"),
    ("why",),
)


def load(paths: Paths) -> Dict[str, Any]:
    data = read_json(paths.atoms_file)
    if not isinstance(data, dict) or "atoms" not in data:
        return {"schema": ATOMS_SCHEMA, "atoms": []}
    return data


def save(paths: Paths, data: Dict[str, Any]) -> None:
    data["schema"] = ATOMS_SCHEMA
    atomic_write_json(paths.atoms_file, data, mode=0o644)


def validate_atom(atom: Any) -> List[str]:
    problems: List[str] = []
    if not isinstance(atom, dict):
        return ["atom must be an object"]
    if not ID_RE.match(str(atom.get("id", ""))):
        problems.append("atom id must be a slug like 'handoff-header-required'")
    if not str(atom.get("rule", "")).strip():
        problems.append("atom needs a one-line rule")
    check = atom.get("check")
    if not isinstance(check, dict):
        problems.append("atom needs a check object")
        return problems
    kind = check.get("type")
    if kind not in CHECK_TYPES:
        problems.append("check.type must be one of {0}".format(", ".join(CHECK_TYPES)))
        return problems
    if kind in ("regex_must_match", "regex_must_not_match"):
        if not check.get("target"):
            problems.append("check.target is required")
        pattern = check.get("pattern")
        if not pattern:
            problems.append("check.pattern is required")
        else:
            try:
                re.compile(pattern)
            except re.error as exc:
                problems.append("check.pattern is not a valid regex: {0}".format(exc))
    if kind == "file_must_exist" and not check.get("target"):
        problems.append("check.target is required")
    if kind == "taos_command_exit_zero":
        argv = check.get("argv")
        if not isinstance(argv, list) or not argv or argv[0] != "taos" or not all(isinstance(arg, str) for arg in argv):
            problems.append("check.argv must be a list starting with 'taos'")
        elif not any(tuple(argv[1:1 + len(command)]) == command for command in READ_ONLY_COMMANDS):
            commands = ", ".join("taos " + " ".join(command) for command in READ_ONLY_COMMANDS)
            problems.append("command atoms can only run these readers: {0}".format(commands))
    return problems


def _resolve_target(paths: Paths, target: str) -> Optional[str]:
    if target == "latest_handoff":
        from . import handoff as handoff_mod

        path = handoff_mod.latest(paths)
        return path.read_text(encoding="utf-8") if path else None
    if target == "agents_md":
        return paths.agents_md.read_text(encoding="utf-8") if paths.agents_md.is_file() else None
    if target == "claude_md":
        return paths.claude_md.read_text(encoding="utf-8") if paths.claude_md.is_file() else None
    path = paths.home / target
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _run_check(paths: Paths, atom: Dict[str, Any]) -> Dict[str, Any]:
    check = atom.get("check", {})
    kind = check.get("type")
    result = {"id": atom.get("id"), "ok": True, "detail": ""}

    if kind == "file_must_exist":
        exists = (paths.home / check.get("target", "")).exists()
        result["ok"] = exists
        result["detail"] = "present" if exists else "missing {0}".format(check.get("target"))
        return result

    if kind == "taos_command_exit_zero":
        import contextlib
        import io

        from .cli import main as cli_main

        argv = [str(part) for part in check.get("argv", [])][1:]
        sink = io.StringIO()
        try:
            # The command's own output belongs to nobody here; hooks that call
            # the doctor must emit exactly one JSON line on stdout.
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                code = cli_main(["--home", str(paths.home)] + argv)
        except SystemExit as exc:  # pragma: no cover - argparse escape hatch
            code = int(exc.code or 0)
        except Exception as exc:  # pragma: no cover - defensive
            result["ok"] = False
            result["detail"] = "command raised: {0}".format(exc)
            return result
        result["ok"] = code == 0
        result["detail"] = "exit {0}".format(code)
        return result

    text = _resolve_target(paths, check.get("target", ""))
    if text is None:
        result["detail"] = "no target yet ({0})".format(check.get("target"))
        return result

    pattern = check.get("pattern", "")
    flags = re.MULTILINE
    hit = re.search(pattern, text, flags) is not None
    if kind == "regex_must_match":
        result["ok"] = hit
        result["detail"] = "matched" if hit else "pattern not found in {0}".format(check.get("target"))
    else:
        result["ok"] = not hit
        result["detail"] = "clean" if not hit else "forbidden pattern found in {0}".format(check.get("target"))

    fixtures = atom.get("fixtures") or {}
    if result["ok"] and isinstance(fixtures, dict) and fixtures.get("red") and fixtures.get("green"):
        red_hit = re.search(pattern, str(fixtures["red"]), flags) is not None
        green_hit = re.search(pattern, str(fixtures["green"]), flags) is not None
        if kind == "regex_must_match" and (red_hit or not green_hit):
            result["ok"] = False
            result["detail"] = "atom self-test failed: fixtures do not discriminate"
        if kind == "regex_must_not_match" and (not red_hit or green_hit):
            result["ok"] = False
            result["detail"] = "atom self-test failed: fixtures do not discriminate"
    return result


def check(paths: Paths) -> List[Dict[str, Any]]:
    results = []
    for atom in load(paths).get("atoms", []):
        if atom.get("status") not in (None, "active"):
            continue
        problems = validate_atom(atom)
        if problems:
            results.append({"id": atom.get("id", "?"), "ok": False, "detail": "; ".join(problems)})
            continue
        results.append(_run_check(paths, atom))
    return results


def _record_atom_event(paths: Paths, kind: str, by: str, retry: bool, **fields: Any) -> None:
    expected = {key: value for key, value in fields.items() if value is not None}
    if retry and any(
        row.get("agent") == by and all(row.get(key) == value for key, value in expected.items())
        for row in events_mod.read(paths, types=[kind])
    ):
        return
    events_mod.emit(paths, kind, by, **expected)


def promote(paths: Paths, proposal_id: str, by: str = "human") -> Dict[str, Any]:
    if by != "human":
        raise TaosError("the human must promote the atom")
    with locked(paths):
        proposal = proposals_mod.get(paths, proposal_id)
        status = proposal.get("status")
        if status not in ("proposed", "accepted") or (status == "accepted" and proposal.get("decided_by") != by):
            raise TaosError("proposal {0} is {1} and cannot be promoted without human approval".format(proposal_id, status))
        payload = proposal.get("atom")
        if proposal.get("kind") != "atom" or not isinstance(payload, dict):
            raise TaosError("proposal {0} does not carry an atom".format(proposal_id))
        problems = validate_atom(payload)
        if problems:
            raise TaosError("atom is not checkable: {0}".format("; ".join(problems)))
        if payload.get("status") not in (None, "active"):
            raise TaosError("only an active atom definition can be installed")

        atom_id = payload["id"]
        data = load(paths)
        atom = next((item for item in data["atoms"] if item.get("id") == atom_id), None)
        retry = atom is not None
        if retry:
            if atom.get("status") not in (None, "active"):
                raise TaosError("atom {0} is {1}; its id cannot be reused".format(atom_id, atom["status"]))
            if atom.get("proposal_id") != proposal_id:
                raise TaosError("atom {0} already exists".format(atom_id))
        # Write the human decision before making the check visible. Both the
        # atom and the audit event can be completed on retry under the same lock.
        proposals_mod.decide(paths, proposal_id=proposal_id, status="accepted", by=by, note="promoted to atom")
        if not retry:
            atom = dict(payload, status="active", proposal_id=proposal_id, promoted_at=utc_now(), promoted_by=by)
            for field in ("retired_by", "retired_at", "retirement_reason"):
                atom.pop(field, None)
            atom.setdefault("why", proposal.get("title", ""))
            data["atoms"].append(atom)
            save(paths, data)
        _record_atom_event(paths, "proposal_decide", by, retry, proposal_id=proposal_id, status="promoted", atom=atom_id)
        return atom


def retire(paths: Paths, atom_id: str, reason: str, by: str = "human") -> Dict[str, Any]:
    if by != "human":
        raise TaosError("the human must retire the atom")
    reason = str(reason or "").strip()
    if not reason:
        raise TaosError("retiring an atom needs a reason")
    with locked(paths):
        data = load(paths)
        atom = next((item for item in data["atoms"] if item.get("id") == atom_id), None)
        if atom is None:
            raise TaosError("no atom {0}".format(atom_id))
        retry = atom.get("status") == "retired"
        if retry and not atom.get("retired_by"):
            return atom  # A retirement from an older store has no audit fields to repair.
        if not retry:
            atom.update(status="retired", retired_by=by, retired_at=utc_now(), retirement_reason=reason)
            save(paths, data)
        _record_atom_event(
            paths, "atom_retire", atom["retired_by"], retry,
            atom=atom_id, proposal_id=atom.get("proposal_id"), reason=atom["retirement_reason"],
        )
        return atom


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_check(args: argparse.Namespace, paths: Paths) -> int:
    results = check(paths)
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    if not results:
        print("no atoms yet")
        return 0
    for item in results:
        print("{0}  {1:<36} {2}".format("ok  " if item["ok"] else "FAIL", item["id"], item["detail"]))
    return 0 if all(item["ok"] for item in results) else 1


def _cmd_promote(args: argparse.Namespace, paths: Paths) -> int:
    atom = promote(paths, args.proposal_id, by=args.by)
    print("promoted atom {0}".format(atom["id"]))
    return 0


def _cmd_retire(args: argparse.Namespace, paths: Paths) -> int:
    atom = retire(paths, args.atom_id, reason=args.reason, by=args.by)
    print("retired atom {0}".format(atom["id"]))
    return 0


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("atoms", help="past corrections written as checks the doctor runs")
    sub = parser.add_subparsers(dest="atoms_cmd", required=True)

    checker = sub.add_parser("check", help="run every active atom")
    checker.add_argument("--json", action="store_true")
    checker.set_defaults(func=_cmd_check)

    promoter = sub.add_parser("promote", help="install a human-reviewed atom proposal")
    promoter.add_argument("proposal_id")
    promoter.add_argument("--by", default="human", choices=subparsers.actors)
    promoter.set_defaults(func=_cmd_promote)

    retire_parser = sub.add_parser("retire", help="stop running an atom and keep its record")
    retire_parser.add_argument("atom_id")
    retire_parser.add_argument("--by", required=True, choices=["human"])
    retire_parser.add_argument("--reason", required=True)
    retire_parser.set_defaults(func=_cmd_retire)
