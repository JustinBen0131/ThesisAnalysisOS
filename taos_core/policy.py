"""The policy layer, routed and executable.

A stack of rules nobody can navigate is decoration. `policies/ROUTING.yaml`
maps request shapes to the two or three files that actually apply, and this
module resolves it: `taos policy route "<what the human asked>"`.

The YAML subset parsed here is deliberately tiny (mappings, lists, scalars,
inline `[a, b]` lists) so the OS keeps its no-dependency promise.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import Paths
from .util import TaosError

ROUTING_FILE = "policies/ROUTING.yaml"
_WORD = re.compile(r"[a-z0-9']+")


# --------------------------------------------------------------------------
# A very small YAML subset: enough for ROUTING.yaml, no dependency.
# --------------------------------------------------------------------------


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for char in line:
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            continue
        if char == "#":
            break
        out.append(char)
    return "".join(out)


def _scalar(text: str) -> Any:
    text = text.strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in inner.split(",")]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text in ("true", "false"):
        return text == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def parse_yaml(text: str) -> Dict[str, Any]:
    """Mappings, block lists, inline lists, and scalars, two-space indented.

    A key with no inline value opens a mapping; if its first child line is a
    `- ` item, the mapping becomes a list in place. That is the whole grammar.
    """
    root: Dict[str, Any] = {}
    # (indent of the opening key, container, parent container, key in parent)
    stack: List[Tuple[int, Any, Any, Optional[str]]] = [(-1, root, None, None)]

    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        top_indent, container, parent, key = stack[-1]

        if body.startswith("- "):
            if isinstance(container, dict):
                if container or parent is None:
                    continue  # a list item under a populated mapping: malformed, skip
                container = []
                parent[key] = container
                stack[-1] = (top_indent, container, parent, key)
            container.append(_scalar(body[2:]))
            continue

        if ":" not in body or not isinstance(container, dict):
            continue
        name, _, rest = body.partition(":")
        name = name.strip()
        rest = rest.strip()
        if rest:
            container[name] = _scalar(rest)
            continue
        child: Dict[str, Any] = {}
        container[name] = child
        stack.append((indent, child, container, name))

    return root


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------


def load_routing(paths: Paths) -> Dict[str, Any]:
    path = paths.home / ROUTING_FILE
    if not path.is_file():
        raise TaosError("missing {0}".format(ROUTING_FILE))
    data = parse_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("routes"), dict):
        raise TaosError("{0} has no routes".format(ROUTING_FILE))
    return data


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def route(paths: Paths, request: str, limit: int = 3) -> Dict[str, Any]:
    data = load_routing(paths)
    text = " " + str(request).lower().strip() + " "
    scored: List[Tuple[int, str, Dict[str, Any]]] = []

    for name, spec in data["routes"].items():
        if not isinstance(spec, dict):
            continue
        score = 0
        matched = []
        for trigger in _as_list(spec.get("triggers")):
            needle = str(trigger).lower()
            if needle in text:
                score += len(needle.split()) * 2 + 1
                matched.append(trigger)
        if score:
            scored.append((score, name, {"matched": matched, **spec}))

    scored.sort(key=lambda item: (-item[0], item[1]))
    chosen = scored[:limit]

    load: List[str] = []
    for path in _as_list(data.get("always")):
        if path not in load:
            load.append(path)
    for _, _, spec in chosen:
        for path in _as_list(spec.get("load")):
            if path not in load:
                load.append(path)

    actions: List[str] = []
    for _, _, spec in chosen:
        for action in _as_list(spec.get("first_actions")):
            if action not in actions:
                actions.append(action)

    missing = [p for p in load if not (paths.home / p).is_file()]
    return {
        "request": request,
        "routes": [{"name": name, "score": score, "matched": spec["matched"]} for score, name, spec in chosen],
        "load": load,
        "first_actions": actions,
        "missing": missing,
    }


def check(paths: Paths) -> List[str]:
    """Every file the map names must exist, and every route must be usable."""
    problems: List[str] = []
    try:
        data = load_routing(paths)
    except TaosError as exc:
        return [str(exc)]
    for path in _as_list(data.get("always")):
        if not (paths.home / path).is_file():
            problems.append("always references a missing file: {0}".format(path))
    for name, spec in data["routes"].items():
        if not isinstance(spec, dict):
            problems.append("route {0} is malformed".format(name))
            continue
        if not _as_list(spec.get("triggers")):
            problems.append("route {0} has no triggers".format(name))
        loads = _as_list(spec.get("load"))
        if not loads:
            problems.append("route {0} loads nothing".format(name))
        for path in loads:
            if not (paths.home / path).is_file():
                problems.append("route {0} references a missing file: {1}".format(name, path))
        if not _as_list(spec.get("first_actions")):
            problems.append("route {0} has no first actions".format(name))
    orphans = []
    referenced = set()
    for path in _as_list(data.get("always")):
        referenced.add(path)
    for spec in data["routes"].values():
        if isinstance(spec, dict):
            referenced.update(_as_list(spec.get("load")))
    for path in sorted(paths.policies_dir.glob("*.md")):
        rel = "policies/{0}".format(path.name)
        if rel not in referenced:
            orphans.append(rel)
    for orphan in orphans:
        problems.append("{0} is never routed to; route it or retire it".format(orphan))
    return problems


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_route(args: argparse.Namespace, paths: Paths) -> int:
    result = route(paths, args.request, limit=args.limit)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if result["routes"]:
        print("routes: {0}".format(", ".join(r["name"] for r in result["routes"])))
    else:
        print("no specific route matched; the always-read set applies")
    print("")
    print("read:")
    for path in result["load"]:
        print("  {0}".format(path))
    if result["first_actions"]:
        print("")
        print("first actions:")
        for action in result["first_actions"]:
            print("  - {0}".format(action))
    for path in result["missing"]:
        print("  MISSING: {0}".format(path))
    return 0


def _cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    data = load_routing(paths)
    print("always:")
    for path in _as_list(data.get("always")):
        print("  {0}".format(path))
    print("")
    for name, spec in sorted(data["routes"].items()):
        if not isinstance(spec, dict):
            continue
        print("{0}".format(name))
        print("  when:  {0}".format(", ".join(_as_list(spec.get("triggers"))[:8])))
        print("  read:  {0}".format(", ".join(_as_list(spec.get("load")))))
    return 0


def _cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    candidate = args.name if args.name.endswith(".md") else "{0}.md".format(args.name.upper())
    path = paths.policies_dir / Path(candidate).name
    if not path.is_file():
        raise TaosError("no such policy: {0}".format(candidate))
    print(path.read_text(encoding="utf-8"))
    return 0


def _cmd_check(args: argparse.Namespace, paths: Paths) -> int:
    problems = check(paths)
    if not problems:
        print("policy layer resolves: every route reaches a real file, every file is routed")
        return 0
    for problem in problems:
        print("- {0}".format(problem))
    return 1


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("policy", help="which rules apply, and where they are")
    sub = parser.add_subparsers(dest="policy_cmd", required=True)

    router = sub.add_parser("route", help="what to read for a given request")
    router.add_argument("request")
    router.add_argument("--limit", type=int, default=3)
    router.add_argument("--json", action="store_true")
    router.set_defaults(func=_cmd_route)

    lister = sub.add_parser("list", help="the whole routing map")
    lister.set_defaults(func=_cmd_list)

    shower = sub.add_parser("show", help="print one policy")
    shower.add_argument("name")
    shower.set_defaults(func=_cmd_show)

    checker = sub.add_parser("check", help="does the policy layer resolve")
    checker.set_defaults(func=_cmd_check)
