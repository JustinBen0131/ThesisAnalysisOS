"""The local panel: one page, loopback only, on when you want it."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from . import atoms as atoms_mod
from . import brief as brief_mod
from . import burn as burn_mod
from . import claims as claims_mod
from . import config as config_mod
from . import decisions as decisions_mod
from . import doctor as doctor_mod
from . import events as events_mod
from . import handoff as handoff_mod
from . import kernels as kernels_mod
from . import projections as projections_mod
from . import proposals as proposals_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import atomic_write_text, utc_now
from .util import TaosError

DEFAULT_PORT = 4331


def _state(paths: Paths) -> Dict[str, Any]:
    store = tasks_mod.TaskStore(paths)
    claim_store = claims_mod.ClaimStore(paths)
    config = config_mod.load_soft(paths)
    report = doctor_mod.run(paths)
    tasks = []
    for task in store.list():
        row = dict(task)
        row["blockers"] = store.blockers(task["id"])
        tasks.append(row)
    try:
        burn_candidates = burn_mod.plan(paths)
    except TaosError:
        burn_candidates = []
    return {
        "server_time": utc_now(),
        "project": config.get("project", {}).get("name", "project"),
        "principal": config.get("principal", {}).get("name", ""),
        "agents": config.get("agents", ["codex", "claude"]),
        "human_only": config.get("human_only", []),
        "tasks": tasks,
        "hot": projections_mod.hot_work(paths),
        "claims": {"live": claim_store.live(), "stale": claim_store.stale()},
        "decisions": decisions_mod.open_decisions(paths),
        "proposals": proposals_mod.open_proposals(paths),
        "handoffs": [
            {"path": paths.relative(p), "name": p.name} for p in reversed(handoff_mod.list_for(paths))
        ][:40],
        "kernels": kernels_mod.freshness(paths),
        "atoms": atoms_mod.check(paths),
        "burn_candidates": burn_candidates,
        "doctor": report,
        "brief": brief_mod.build(paths),
    }


class _Handler(BaseHTTPRequestHandler):
    paths: Paths = None  # type: ignore[assignment]
    token: str = ""

    server_version = "taos"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - quiet
        return

    # -- helpers -----------------------------------------------------------

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
            pass

    def _json(self, value: Any, code: int = 200) -> None:
        self._send(code, json.dumps(value, sort_keys=True).encode("utf-8"), "application/json")

    def _authorized(self) -> bool:
        if self.headers.get("X-TAOS-Token", "") != self.token:
            return False
        origin = self.headers.get("Origin") or ""
        if origin and not (origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:")):
            return False
        return True

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            return {}

    # -- routes ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            if route == "/" or route == "/index.html":
                html = (self.paths.panel_assets / "panel.html").read_text(encoding="utf-8")
                html = html.replace("__TAOS_TOKEN__", self.token)
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                return
            if route == "/api/health":
                self._json({"ok": True, "time": utc_now()})
                return
            if route == "/api/state":
                self._json(_state(self.paths))
                return
            if route.startswith("/api/task/"):
                task_id = route.rsplit("/", 1)[1]
                self._json(tasks_mod.TaskStore(self.paths).get(task_id))
                return
            if route == "/api/brief.md":
                text = brief_mod.render_markdown(brief_mod.build(self.paths))
                self._send(200, text.encode("utf-8"), "text/plain; charset=utf-8")
                return
            if route == "/api/handoff":
                wanted = (parse_qs(parsed.query).get("path") or [""])[0]
                target = (self.paths.home / wanted).resolve()
                if not str(target).startswith(str(self.paths.handoffs_dir.resolve()) + os.sep) or not target.is_file():
                    self._json({"error": "not a handoff"}, 404)
                    return
                self._send(200, target.read_bytes(), "text/plain; charset=utf-8")
                return
        except TaosError as exc:
            self._json({"error": str(exc)}, 400)
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._json({"error": str(exc)}, 500)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if not self._authorized():
            self._json({"error": "forbidden"}, 403)
            return
        body = self._body()
        try:
            if route == "/api/decide":
                decision = decisions_mod.answer(
                    self.paths, decision_id=body.get("id", ""), choice=body.get("choice", ""), note=body.get("note")
                )
                self._json({"ok": True, "decision": decision})
                return
            if route == "/api/task/transition":
                task = tasks_mod.TaskStore(self.paths).transition(
                    body.get("id", ""),
                    body.get("to", ""),
                    body.get("reason", "changed from the panel"),
                    "human",
                    evidence=body.get("evidence"),
                    reopen=bool(body.get("reopen")),
                )
                projections_mod.refresh(self.paths)
                self._json({"ok": True, "task": task})
                return
            if route == "/api/task/hot":
                task = tasks_mod.TaskStore(self.paths).set_hot(
                    body.get("id", ""), bool(body.get("hot")), body.get("reason", "panel"), "human"
                )
                projections_mod.refresh(self.paths)
                self._json({"ok": True, "task": task})
                return
            if route == "/api/proposal/decide":
                proposal = proposals_mod.decide(
                    self.paths, proposal_id=body.get("id", ""), status=body.get("status", ""), note=body.get("note")
                )
                self._json({"ok": True, "proposal": proposal})
                return
            if route == "/api/claim/release":
                claim = claims_mod.ClaimStore(self.paths).release(body.get("id", ""), "human", force=True)
                self._json({"ok": True, "claim": claim})
                return
            if route == "/api/refresh":
                projections_mod.refresh(self.paths)
                brief_mod.write(self.paths)
                kernels_mod.generate_now(self.paths)
                self._json({"ok": True})
                return
        except TaosError as exc:
            self._json({"error": str(exc)}, 400)
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._json({"error": str(exc)}, 500)
            return
        self._json({"error": "not found"}, 404)


def make_server(paths: Paths, port: int, token: str) -> ThreadingHTTPServer:
    handler = type("_BoundHandler", (_Handler,), {"paths": paths, "token": token})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    return server


def serve(paths: Paths, port: int, token: str) -> None:  # pragma: no cover - long running
    server = make_server(paths, port, token)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def status(paths: Paths) -> Dict[str, Any]:
    if not paths.panel_pid.is_file():
        return {"running": False, "pid": None, "port": None, "url": None}
    try:
        raw = paths.panel_pid.read_text(encoding="utf-8").split()
        pid, port = int(raw[0]), int(raw[1])
        os.kill(pid, 0)
    except (ValueError, IndexError, OSError):
        return {"running": False, "pid": None, "port": None, "url": None, "note": "stale pidfile"}
    return {"running": True, "pid": pid, "port": port, "url": "http://127.0.0.1:{0}/".format(port)}


def on(paths: Paths, port: Optional[int] = None, open_browser: Optional[bool] = None) -> Dict[str, Any]:
    existing = status(paths)
    if existing.get("running"):
        return existing

    config = config_mod.load_soft(paths)
    port = int(port or config.get("panel", {}).get("port", DEFAULT_PORT))
    should_open = config.get("panel", {}).get("open_browser", True) if open_browser is None else open_browser

    paths.ensure_state()
    token = secrets.token_hex(16)
    atomic_write_text(paths.panel_token, token + "\n", mode=0o600)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(paths.home) + os.pathsep + env.get("PYTHONPATH", "")
    log = open(str(paths.panel_log), "ab")
    process = subprocess.Popen(
        [sys.executable, "-m", "taos_core.panel", "--serve", "--home", str(paths.home), "--port", str(port)],
        cwd=str(paths.home),
        env=env,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    atomic_write_text(paths.panel_pid, "{0} {1}\n".format(process.pid, port), mode=0o600)

    url = "http://127.0.0.1:{0}/".format(port)
    deadline = time.time() + float(os.environ.get("TAOS_PANEL_START_TIMEOUT", "30"))
    healthy = False
    while time.time() < deadline:
        if process.poll() is not None:
            break
        try:
            with urllib.request.urlopen(url + "api/health", timeout=1.0) as response:
                if response.status == 200:
                    healthy = True
                    break
        except Exception:
            time.sleep(0.2)

    if not healthy:
        try:
            process.terminate()
        except OSError:
            pass
        if paths.panel_pid.exists():
            paths.panel_pid.unlink()
        log.flush()
        tail = ""
        try:
            tail = paths.panel_log.read_text(encoding="utf-8", errors="replace")[-800:]
        except OSError:
            pass
        raise TaosError(
            "the panel did not come up on port {0} (process {1}). Try `taos panel on --port <other>`. "
            "Last log lines:\n{2}".format(
                port, "exited {0}".format(process.returncode) if process.poll() is not None else "still starting", tail
            )
        )

    events_mod.emit(paths, "panel_on", "human", port=port, pid=process.pid)
    if should_open:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:  # pragma: no cover - headless
            pass
    return {"running": True, "pid": process.pid, "port": port, "url": url}


def off(paths: Paths) -> Dict[str, Any]:
    current = status(paths)
    if not current.get("running"):
        if paths.panel_pid.exists():
            paths.panel_pid.unlink()
        return {"running": False, "note": "was not running"}
    pid = current["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except OSError:
            break
    else:  # pragma: no cover - stubborn process
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    if paths.panel_pid.exists():
        paths.panel_pid.unlink()
    events_mod.emit(paths, "panel_off", "human", pid=pid)
    return {"running": False, "pid": pid}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_on(args: argparse.Namespace, paths: Paths) -> int:
    result = on(paths, port=args.port, open_browser=False if args.no_open else None)
    print("panel is on: {0}".format(result["url"]))
    print("turn it off with: taos panel off")
    return 0


def _cmd_off(args: argparse.Namespace, paths: Paths) -> int:
    result = off(paths)
    print("panel is off" if not result["running"] else "panel still running")
    return 0


def _cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    result = status(paths)
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return 0
    print("panel: {0}".format(result.get("url") if result.get("running") else "off"))
    return 0


def register(subparsers: Any) -> None:
    panel = subparsers.add_parser("panel", help="the local dashboard")
    sub = panel.add_subparsers(dest="panel_cmd", required=True)

    on_parser = sub.add_parser("on", help="start it")
    on_parser.add_argument("--port", type=int)
    on_parser.add_argument("--no-open", action="store_true")
    on_parser.set_defaults(func=_cmd_on)

    off_parser = sub.add_parser("off", help="stop it")
    off_parser.set_defaults(func=_cmd_off)

    status_parser = sub.add_parser("status", help="is it running")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=_cmd_status)


def _main() -> int:  # pragma: no cover - subprocess entry point
    parser = argparse.ArgumentParser(description="taos panel server")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--home", required=True)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    paths = Paths(Path(args.home))
    token = paths.panel_token.read_text(encoding="utf-8").strip() if paths.panel_token.is_file() else ""
    serve(paths, args.port, token)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
