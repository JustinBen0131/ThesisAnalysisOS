"""Local MCP tools over standard input and output. The tool surface has no writer."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import Any, Dict

from . import __version__, basis, config, gates, lifecycle, standing, tasks
from .paths import Paths
from .util import TaosError

PROTOCOL = "2025-06-18"
MAX_ROWS = 6
MAX_CHARS = 180
MAX_REQUEST = 65536
HANDOFF_PAGE = 2400
CURSOR = re.compile(r"^[0-9a-f]{64}:[1-9][0-9]{0,11}$")
DESCRIPTIONS = {
    "status": "See project setup, task counts, and the first six tasks in priority order.",
    "why": "See what one task rests on and whether its recorded results still hold.",
    "checks": "Read one task's check verdicts against the current files.",
    "handoff": "Read the same brief as taos capsule TASK. Follow next_cursor to assemble a long brief before acting on it.",
}


def _tool(name: str) -> dict:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    if name != "status":
        schema["properties"]["task_id"] = {"type": "string", "pattern": tasks.ID_RE.pattern, "maxLength": 64}
        schema["required"] = ["task_id"]
    if name == "handoff":
        schema["properties"]["cursor"] = {"type": "string", "pattern": CURSOR.pattern,
                                          "description": "The next_cursor from the preceding page of this task's brief."}
    return {"name": name, "description": DESCRIPTIONS[name], "inputSchema": schema,
            "annotations": {"readOnlyHint": True, "openWorldHint": False}}


def _short(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_CHARS:
        return value[:MAX_CHARS - 1] + "…"
    return value


def _rows(items: list, fields: tuple) -> list:
    return [{key: _short(row.get(key)) for key in fields} for row in items[:MAX_ROWS]]


def _status(paths: Paths) -> dict:
    if not paths.constructed():
        return {"constructed": False, "message": config.NOT_CONSTRUCTED}
    items = tasks.TaskStore(paths).list()
    counts: Dict[str, int] = {}
    for item in items:
        state = item["status"]
        counts[state] = counts.get(state, 0) + 1
    return {"constructed": True, "project": _short(config.load(paths)["project"]["name"]),
            "paused": (paths.state / "paused").is_file(), "counts": counts,
            "tasks": _rows(items, ("id", "title", "status", "hot", "next_action")), "total": len(items)}


def _handoff(paths: Paths, task_id: str, cursor: str) -> dict:
    brief = lifecycle.capsule_text(lifecycle.capsule(paths, task_id)) + "\n"
    stamp = hashlib.sha256(brief.encode("utf-8")).hexdigest()
    start = 0
    if cursor:
        previous, offset = cursor.split(":")
        if previous != stamp:
            raise TaosError("This brief changed. Read the handoff again without a cursor.")
        start = int(offset)
        if start >= len(brief):
            raise TaosError("The cursor is past the end of this handoff.")
    end = min(len(brief), start + HANDOFF_PAGE)
    return {"task": task_id, "text": brief[start:end], "sha256": stamp, "start_character": start,
            "total_characters": len(brief), "next_cursor": f"{stamp}:{end}" if end < len(brief) else None}


def _answer(paths: Paths, name: str, args: dict) -> dict:
    if name == "status":
        return _status(paths)
    task_id = args["task_id"]
    if name == "handoff":
        return _handoff(paths, task_id, args.get("cursor", ""))
    if name == "why":
        view = standing.of_task(paths, task_id)
        items = view["parts"]
        answer = {key: _short(view[key]) for key in ("task", "title", "status", "closed", "accepted", "state")}
        fields, label = ("kind", "name", "state", "reason"), "parts"
    else:
        tasks.TaskStore(paths).get(task_id)  # Even an empty gate list belongs to an existing task.
        items = gates.standing(paths, task_id)
        answer = {"task": task_id}
        fields, label = ("gate", "state", "reason", "ran_at"), "checks"
    ordered = sorted(items, key=lambda row: basis.STATES.index(row["state"]), reverse=True)
    return dict(answer, **{label: _rows(ordered, fields), "total": len(items)})


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _call(paths: Paths, params: dict) -> dict:
    name, args = params.get("name"), params.get("arguments", {})
    if not isinstance(name, str) or name not in DESCRIPTIONS:
        raise RpcError(-32602, "Unknown tool. Available tools: " + ", ".join(DESCRIPTIONS) + ".")
    if not isinstance(args, dict):
        raise RpcError(-32602, "Tool arguments must be an object.")
    if name == "status":
        if args:
            raise RpcError(-32602, "status takes no arguments.")
    else:
        allowed = {"task_id", "cursor"} if name == "handoff" else {"task_id"}
        task_id = args.get("task_id")
        if (set(args) - allowed or not isinstance(task_id, str)
                or len(task_id) > 64 or not tasks.ID_RE.fullmatch(task_id)):
            raise RpcError(-32602, "Supply a task_id, for example AZ-1.")
        if "cursor" in args and (not isinstance(args["cursor"], str) or not CURSOR.fullmatch(args["cursor"])):
            raise RpcError(-32602, "Use the next_cursor returned by the previous handoff page.")
    try:
        result = _answer(paths, name, args)
    except (TaosError, OSError) as exc:
        return {"isError": True, "content": [{"type": "text", "text": _short(str(exc))}]}
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}


class Session:
    def __init__(self, paths: Paths):
        self.paths = paths
        self.phase = "new"

    def dispatch(self, message: dict) -> Any:
        method, params = message.get("method"), message.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            raise RpcError(-32600, "Expected an MCP method and an object for params.")
        if "id" not in message:
            if method == "notifications/initialized" and self.phase == "initializing":
                self.phase = "ready"
            return None
        if method == "initialize":
            if self.phase != "new":
                raise RpcError(-32600, "This session already initialized.")
            if not isinstance(params.get("protocolVersion"), str):
                raise RpcError(-32602, "initialize needs a protocolVersion.")
            self.phase = "initializing"
            return {"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "taos", "version": __version__}}
        if method == "ping":
            return {}
        if self.phase != "ready":
            raise RpcError(-32600, "Initialize the session first.")
        if method == "tools/list":
            return {"tools": [_tool(name) for name in DESCRIPTIONS]}
        if method == "tools/call":
            return _call(self.paths, params)
        raise RpcError(-32601, "Method not found.")


def _reply(session: Session, line: bytes) -> Any:
    identifier = None
    try:
        if len(line) > MAX_REQUEST:
            raise RpcError(-32600, "Request exceeds 64 KiB.")
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            raise RpcError(-32700, "Invalid JSON.")
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise RpcError(-32600, "Expected a JSON-RPC 2.0 request.")
        if "id" in message:
            if type(message["id"]) not in (int, str):
                raise RpcError(-32600, "Request id must be a string or integer.")
            identifier = message["id"]
        result = session.dispatch(message)
        if result is None:
            return None
        return {"jsonrpc": "2.0", "id": identifier, "result": result}
    except RpcError as exc:
        return {"jsonrpc": "2.0", "id": identifier, "error": {"code": exc.code, "message": str(exc)}}
    except (KeyError, ValueError, TypeError, AttributeError, RecursionError):
        return {"jsonrpc": "2.0", "id": identifier,
                "error": {"code": -32603, "message": "Unreadable project record."}}


def serve(paths: Paths) -> int:
    session = Session(paths)
    stream = sys.stdin.buffer
    while True:
        line = stream.readline(MAX_REQUEST + 1)
        if not line:
            return 0
        reply = _reply(session, line)
        if len(line) > MAX_REQUEST:
            while line and not line.endswith(b"\n"):
                line = stream.readline(MAX_REQUEST + 1)
        if reply is not None:
            print(json.dumps(reply, separators=(",", ":")), flush=True)


def register(verbs: Any) -> None:
    parser = verbs.add_parser("mcp", help="let a local MCP client read task briefs, status and checks")
    parser.set_defaults(func=lambda args, paths: serve(paths))
