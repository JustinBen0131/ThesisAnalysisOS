"""Handoffs: the durable object that survives a dead session."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import events as events_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import atomic_write_text, parse_ts, utc_now
from .util import TaosError

HEADER_RE = re.compile(
    r"^Agent:\s*(codex|claude|human)\s*\n"
    r"Chat/session:\s*.+\n"
    r"Task:\s*[A-Z][A-Z0-9]{1,7}-[0-9]+\s*\|\s*.+\n"
    r"Claim/scope:\s*.+\n",
    re.MULTILINE,
)

REQUIRED_SECTIONS = (
    "## State",
    "## Changed",
    "## Evidence",
    "## Risks and open questions",
    "## Next command",
)


def template(task: Dict[str, Any], from_agent: str, to_agent: str, session: str) -> str:
    return "\n".join(
        [
            "Agent: {0}".format(from_agent),
            "Chat/session: {0}".format(session),
            "Task: {0} | {1}".format(task["id"], task.get("title", "")),
            "Claim/scope: task:{0}".format(task["id"]),
            "",
            "## State",
            "<where this actually is right now, in two or three sentences>",
            "",
            "## Changed",
            "<files touched, commands run, what now exists that did not before>",
            "",
            "## Evidence",
            "<paths, commit shas, test output, urls. Something {0} can open.>".format(to_agent),
            "",
            "## Risks and open questions",
            "<what might be wrong, what you did not verify, what you assumed>",
            "",
            "## Next command",
            "<the literal next command {0} should run>".format(to_agent),
            "",
        ]
    )


def validate(text: str) -> List[str]:
    problems: List[str] = []
    if not HEADER_RE.search(text or ""):
        problems.append(
            "missing the four-line header (Agent / Chat-session / Task / Claim-scope) at the top"
        )
    for section in REQUIRED_SECTIONS:
        if section not in (text or ""):
            problems.append("missing section {0!r}".format(section))
    placeholder = re.findall(r"<[a-z][^>\n]{10,}>", text or "")
    if placeholder:
        problems.append("template placeholders are still present: {0}".format(placeholder[0]))
    return problems


def _filename(task_id: str, from_agent: str, to_agent: str) -> str:
    stamp = parse_ts(utc_now()).strftime("%Y%m%dT%H%M%SZ")
    return "{0}_{1}_{2}_to_{3}.md".format(stamp, task_id, from_agent, to_agent)


def write(
    paths: Paths,
    *,
    task_id: str,
    from_agent: str,
    to_agent: str,
    body: str,
    session: str,
) -> Path:
    store = tasks_mod.TaskStore(paths)
    task = store.get(task_id)
    problems = validate(body)
    if problems:
        raise TaosError(
            "handoff rejected: {0}. Start from `taos handoff template {1} --from {2} --to {3} --session '{4}'`.".format(
                "; ".join(problems), task_id, from_agent, to_agent, session
            )
        )
    paths.ensure_state()
    path = paths.handoffs_dir / _filename(task["id"], from_agent, to_agent)
    atomic_write_text(path, body if body.endswith("\n") else body + "\n")
    events_mod.emit(
        paths,
        "handoff_write",
        from_agent,
        task_id=task["id"],
        to_agent=to_agent,
        path=paths.relative(path),
    )
    store.comment(
        task["id"],
        "handoff to {0}: {1}".format(to_agent, paths.relative(path)),
        from_agent,
        session,
    )
    return path


def list_for(paths: Paths, task_id: Optional[str] = None) -> List[Path]:
    if not paths.handoffs_dir.is_dir():
        return []
    items = sorted(paths.handoffs_dir.glob("*.md"))
    if task_id:
        items = [p for p in items if "_{0}_".format(task_id) in p.name]
    return items


def latest(paths: Paths, task_id: Optional[str] = None) -> Optional[Path]:
    items = list_for(paths, task_id)
    return items[-1] if items else None


def wrapper(path: Path, to_agent: str, summary_lines: Optional[List[str]] = None) -> str:
    lines = [
        "{0}, please continue from this handoff:".format(to_agent.capitalize()),
        "",
        str(Path(path).resolve()),
        "",
    ]
    if summary_lines:
        lines.append("High-priority summary:")
        for item in summary_lines:
            lines.append("- {0}".format(item))
        lines.append("")
    lines.append("Read the full file first, then run `taos capsule <TASK-ID>` before acting.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_template(args: argparse.Namespace, paths: Paths) -> int:
    task = tasks_mod.TaskStore(paths).get(args.task_id)
    sys.stdout.write(template(task, args.from_agent, args.to_agent, args.session))
    return 0


def _cmd_write(args: argparse.Namespace, paths: Paths) -> int:
    if args.stdin:
        body = sys.stdin.read()
    else:
        body = Path(args.file).read_text(encoding="utf-8")
    path = write(
        paths,
        task_id=args.task_id,
        from_agent=args.from_agent,
        to_agent=args.to_agent,
        body=body,
        session=args.session,
    )
    print("wrote {0}".format(path))
    print("")
    print(wrapper(path, args.to_agent))
    return 0


def _cmd_latest(args: argparse.Namespace, paths: Paths) -> int:
    path = latest(paths, args.task_id)
    if path is None:
        print("no handoff yet for {0}".format(args.task_id))
        return 0
    print(str(path))
    if args.print:
        print("")
        sys.stdout.write(path.read_text(encoding="utf-8"))
    return 0


def _cmd_wrapper(args: argparse.Namespace, paths: Paths) -> int:
    print(wrapper(Path(args.path), args.to_agent, args.summary or []))
    return 0


def register(subparsers: Any) -> None:
    handoff = subparsers.add_parser("handoff", help="hand work to the other agent")
    sub = handoff.add_subparsers(dest="handoff_cmd", required=True)

    template_parser = sub.add_parser("template", help="print a handoff skeleton")
    template_parser.add_argument("task_id")
    template_parser.add_argument("--from", dest="from_agent", required=True, choices=["codex", "claude", "human"])
    template_parser.add_argument("--to", dest="to_agent", required=True, choices=["codex", "claude", "human"])
    template_parser.add_argument("--session", required=True)
    template_parser.set_defaults(func=_cmd_template)

    write_parser = sub.add_parser("write", help="validate and store a handoff")
    write_parser.add_argument("task_id")
    write_parser.add_argument("--from", dest="from_agent", required=True, choices=["codex", "claude", "human"])
    write_parser.add_argument("--to", dest="to_agent", required=True, choices=["codex", "claude", "human"])
    write_parser.add_argument("--session", required=True)
    group = write_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file")
    group.add_argument("--stdin", action="store_true")
    write_parser.set_defaults(func=_cmd_write)

    latest_parser = sub.add_parser("latest", help="show the newest handoff for a task")
    latest_parser.add_argument("task_id")
    latest_parser.add_argument("--print", action="store_true")
    latest_parser.set_defaults(func=_cmd_latest)

    wrapper_parser = sub.add_parser("wrapper", help="paste-ready text pointing at a handoff")
    wrapper_parser.add_argument("path")
    wrapper_parser.add_argument("--to", dest="to_agent", required=True, choices=["codex", "claude", "human"])
    wrapper_parser.add_argument("--summary", action="append")
    wrapper_parser.set_defaults(func=_cmd_wrapper)
