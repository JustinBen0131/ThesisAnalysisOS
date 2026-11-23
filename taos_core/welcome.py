"""The front door as a page: try the idea on a practice result, then name a folder and it is set up.

`python3 -m taos_core.welcome` serves one self-contained page on this computer only (127.0.0.1), opens it in the
browser, and does through `use.use` exactly what `taos use <folder>` does at a terminal. Someone new first changes a
practice file and watches a practice result stop holding: a real TAOS project in a temporary folder, removed on close.
Before anything of theirs is written the page says what TAOS sees in the folder and what the button will do;
afterwards it shows the four words live. A copy that already keeps a project opens on that project's word.
Nothing leaves the machine: the page loads no outside file, and the server refuses any request that is not for this
computer or does not carry the key printed in its own address.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import secrets
import shlex
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from . import config as config_mod
from . import demo as demo_mod
from . import gates as gates_mod
from . import standing as standing_mod
from . import use as use_mod
from .paths import Paths
from .util import TaosError

OFFERED = ("Claude", "Codex", "ChatGPT", "Gemini")      # offered for one tap; any other name can be typed
# How a typed name is written back, and the note in the folder that assistant reads by itself (None: not known to).
KNOWN = {"claude": ("Claude", "CLAUDE.md"), "claude code": ("Claude", "CLAUDE.md"),
         "codex": ("Codex", "AGENTS.md"), "codex cli": ("Codex", "AGENTS.md"),
         "chatgpt": ("ChatGPT", None), "chat gpt": ("ChatGPT", None), "gpt": ("ChatGPT", None),
         "gemini": ("Gemini", None)}
LOOK_AT_MOST = 4000                                     # names read when looking at a folder before anything is written
SKIPPED = ("node_modules", "__pycache__")
TELL = "Read AGENTS.md in this folder before you do anything, and follow it."
# Where likely work is looked for, by name only: beside this copy, in the home folder, and on these usual shelves under it.
SHELVES = ("code", "dev", "git", "github", "GitHub", "projects", "Projects", "repos", "research", "src", "work")
GUARDED = ("Applications", "Desktop", "Documents", "Downloads", "Library", "Movies", "Music", "Pictures", "Public")
WORK = re.compile(r"^(\.git|Makefile|pyproject\.toml|requirements\.txt|environment\.yml|README(\..*)?|src|scripts|analysis|notebooks|tests?"
                  r"|.*\.(py|ipynb|R|Rmd|qmd|jl|tex|m|C|cc|cpp|rs|go|do))$")
# The practice project: three numbers, the result written from them, and a check that the two still agree.
PRACTICE = (("data.csv", "3\n4\n5\n"), ("result.txt", "average = 4.0\n"), ("check.py", '''"""Passes when result.txt says what data.csv gives."""
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
numbers = [float(line) for line in (here / "data.csv").read_text().split()]
gives = "{0:.1f}".format(sum(numbers) / len(numbers))
says = (here / "result.txt").read_text().split("=")[-1].strip()
if says != gives:
    print("result.txt says {0}. data.csv gives {1}.".format(says, gives))
    sys.exit(1)
print("average = " + gives)
'''))


def assistants(typed: Any) -> List[Dict[str, Any]]:
    """The assistants a person typed, in their order, each with the note it reads in the folder (None when not known).

    Any name is accepted. Names are split on commas, semicolons, new lines, slashes, "+", "&" and the word "and"."""
    if isinstance(typed, (list, tuple)):
        typed = ", ".join(str(item) for item in typed)
    out: List[Dict[str, Any]] = []
    for raw in re.split(r"[,;\n/+&]|\band\b", str(typed or ""), flags=re.IGNORECASE):
        name = " ".join(raw.split())[:40]
        if not name:
            continue
        shown, reads = KNOWN.get(name.lower(), (name, None))
        if shown.lower() not in {item["name"].lower() for item in out}:
            out.append({"name": shown, "reads": reads})
    return out[:40]


def _and(names: List[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _short(path: Path) -> str:
    """A folder the way a person writes it: `~/work` when it is under their home, the whole path otherwise."""
    for home in (Path.home(), Path.home().resolve()):
        try:
            inside = path.relative_to(home)
        except ValueError:
            continue
        return "~" if str(inside) == "." else "~/" + inside.as_posix()
    return str(path)


def _typed(folder: str) -> str:
    """The folder as it can be typed at a shell: short when it is under home, quoted where it has to be."""
    short = _short(Path(folder))
    if short == "~":
        return short
    return "~/" + shlex.quote(short[2:]) if short.startswith("~/") else shlex.quote(folder)


def _taos(paths: Paths) -> str:
    """How this copy's launcher is typed so that a pasted command runs: `taos` when the shell finds this copy by that
    name, the launcher's own path otherwise."""
    found = shutil.which("taos")
    try:
        if found and Path(found).resolve() == paths.launcher.resolve():
            return "taos"
    except OSError:
        pass
    return _typed(str(paths.launcher))


def _started(paths: Optional[Paths]) -> Optional[Path]:
    """The folder the command was run from, when that can be someone's work: not home, and not in or around a copy of TAOS."""
    try:
        here = Path.cwd().resolve()
    except OSError:
        return None
    own = paths.home.resolve() if paths else None
    if here == Path.home().resolve() or any(Paths._is_home(folder) for folder in [here] + list(here.parents)):
        return None
    if own is not None and here in own.parents:
        return None
    return here if here.is_dir() else None


def likely(paths: Paths, at_most: int = 4) -> List[str]:
    """Folders that look like someone's work, the most recently changed first, for one tap in place of typing.

    It looks beside this copy of TAOS, in the home folder and on a few usual shelves under it (~/code, ~/projects ...).
    It reads names only and opens no file, it stays out of the folders macOS guards (Documents, Desktop, Downloads ...),
    and it stops after half a second, so a slow disk costs a person nothing."""
    home, own, began = Path.home().resolve(), paths.home.resolve(), time.monotonic()
    found = {}                                               # type: Dict[Path, float]
    seen = set()
    for shelf in [own.parent, home] + [home / name for name in SHELVES]:
        try:
            shelf = shelf.resolve()
            if shelf in seen or not shelf.is_dir():
                continue
            seen.add(shelf)
            inside = sorted(shelf.iterdir())[:300]
        except OSError:
            continue
        for folder in inside:
            if time.monotonic() - began > 0.5:
                break
            if folder.name.startswith(".") or (shelf == home and (folder.name in GUARDED or folder.name in SHELVES)):
                continue
            try:
                if not folder.is_dir() or folder.resolve() == own or Paths._is_home(folder):
                    continue
                with os.scandir(str(folder)) as entries:
                    names = [entry.name for entry, _ in zip(entries, range(200))]
                if any(WORK.match(name) for name in names):
                    changed = [folder.stat().st_mtime] + ([(folder / ".git").stat().st_mtime] if ".git" in names else [])
                    found[folder.resolve()] = max(changed)
            except OSError:
                continue
    return [_short(folder) for folder in sorted(found, key=lambda folder: found[folder], reverse=True)[:at_most]]


def folders(under: Optional[str] = None, paths: Optional[Paths] = None) -> Dict[str, Any]:
    """The folders inside `under`, for picking one without typing a path.

    With no folder named it starts where this copy's project already is, else in the folder the command was run from
    when that can be someone's work, else at the person's home; and it offers the folders that look like work. A name
    that is only half typed lists the folders beside it that start the same way."""
    kept = use_mod._primary(paths) if paths else None
    typed = Path(under).expanduser() if under else (kept or _started(paths) or Path.home())
    here, starts = typed, ""
    if not here.is_dir():
        here, starts = (typed.parent, typed.name.lower()) if typed.parent.is_dir() else (Path.home(), "")
    try:
        inside = sorted((p.name for p in here.iterdir() if p.is_dir() and not p.name.startswith(".")
                         and p.name.lower().startswith(starts)), key=str.lower)
    except OSError:
        inside = []
    out = {"here": _short(here), "up": _short(here.parent) if here.parent != here else None, "inside": inside[:200]}
    if not under and paths is not None and kept is None:
        out["likely"] = likely(paths)
    return out


def _listing(folder: Path) -> Tuple[List[str], bool]:
    """The files in a folder by name, hidden folders left out, never more than LOOK_AT_MOST. Reads names only."""
    names: List[str] = []
    for root, inside, files in os.walk(str(folder)):
        inside[:] = sorted(name for name in inside if not name.startswith(".") and name not in SKIPPED)
        for name in sorted(files):
            names.append((Path(root) / name).relative_to(folder).as_posix())
            if len(names) >= LOOK_AT_MOST:
                return names, True
    return names, False


def look(paths: Paths, folder: Any, typed: Any = "") -> Dict[str, Any]:
    """What TAOS sees in a folder and what the button would do, in plain words. It reads; it writes nothing."""
    helpers = assistants(typed)
    text = str(folder or "").strip()
    here = Path(text).expanduser() if text else None
    if here is None:
        return {"ok": False, "says": "Pick or type the folder your work is in.", "assistants": helpers}
    if here.is_file():
        return {"ok": False, "says": "That is a file. Name the folder it is in.", "assistants": helpers}
    if not here.is_dir():
        return {"ok": False, "says": "There is no folder with that name.", "assistants": helpers}
    if here.resolve() == Path.home().resolve():           # one tap must never set a whole home folder up
        return {"ok": False, "says": "Pick the folder your work is in.", "assistants": helpers}
    kept = use_mod._primary(paths)
    if kept is not None and kept != here.resolve():       # `taos use` would refuse: say so before the button, in one line
        return {"ok": False, "elsewhere": _short(kept), "assistants": helpers,
                "says": "This copy of TAOS already keeps {0}. One copy keeps one project.".format(_short(kept)),
                "also": "For a separate project, use a second copy of TAOS."}
    try:
        names, more = _listing(here)
        names = [name for name in names if name not in use_mod.WRITTEN]      # the person's files, not the notes TAOS wrote
        found = use_mod.suggestions(here, names)
    except OSError:
        names, more, found = [], False, []
    already = (here / ".taos-link.json").is_file()
    where = _short(here)
    says = ("Already set up in {0}. Nothing new is added." if already else
            "Adds 3 small files to {0}. Nothing else there changes.").format(where)
    return {"ok": True, "folder": where, "files": len(names), "more": more, "already": already, "checks": found,
            "assistants": helpers, "says": says, "same_as": _taos(paths) + " use " + _typed(str(here))}


def live(paths: Paths, task: Any) -> Dict[str, Any]:
    """Where a task stands right now: one of the four words for each thing it rests on, judged against the files as they are."""
    try:
        view = standing_mod.for_person(paths, standing_mod.of_task(paths, str(task or "")), "parts")
    except TaosError as refused:
        return {"refused": str(refused)}
    parts = [{key: part.get(key) for key in ("kind", "name", "state", "reason")} for part in view["parts"]]
    for part in parts:
        part["reason"] = _files(str(part["reason"] or ""))
    return {"task": view["task"], "state": view["state"], "parts": parts}


CHANGED = re.compile(r"^[\w.-]+ changed: (.+)$")          # "workspace changed: a, b", or the name a project gave what its checks read


def _files(reason: str) -> str:
    """The program's "workspace changed: +a, -b, c and 2 more" as a person reads it; any other reason is left as it is."""
    found = [CHANGED.match(piece) for piece in reason.split("; ")]
    if not all(found):
        return reason
    told = []
    for match in found:
        names, _, more = match.group(1).partition(" and ")
        told.extend(name[1:] + " (new)" if name.startswith("+") else name[1:] + " (removed)" if name.startswith("-") else name
                    for name in names.split(", "))
        if more:
            told[-1] += " and " + more
    return "changed since it passed: " + ", ".join(told)


def again(paths: Paths, task: Any) -> Dict[str, Any]:
    """Run the task's checks again, as `taos gate run` does, then say where it stands and what each check printed."""
    try:
        record = gates_mod.run(paths, task_id=str(task or ""), agent="human")
    except TaosError as refused:
        return {"refused": str(refused)}
    got = live(paths, task)
    got["ran"] = [{"name": result.get("name"), "exit": result.get("exit"), "tail": result.get("tail", "")}
                  for result in record.get("results", [])]
    return got


def next_steps(result: Dict[str, Any], helpers: List[Dict[str, Any]], taos: str = "taos") -> List[Dict[str, str]]:
    """What to do next, for the assistants the person named. Each step is a few words and text to copy.

    `taos` is how this copy's launcher is typed, so that every command copied from the page runs as pasted."""
    folder = result.get("folder", "")
    steps: List[Dict[str, str]] = []
    reads = [item for item in helpers if item["reads"]]
    if reads:
        one = len(reads) == 1
        steps.append({"say": "{0}: open {1} in this folder. {2} {3} there by {4}.".format(
            _and([item["name"] for item in reads]), "it" if one else "them", "It reads" if one else "They read",
            _and(sorted({item["reads"] for item in reads})), "itself" if one else "themselves"),
            "copy": "cd " + _typed(folder)})
    others = [item["name"] for item in helpers if not item["reads"]]
    if others:
        steps.append({"say": "{0}, working in your folder: say this first.".format(_and(others)), "copy": TELL})
        steps.append({"say": "{0}, in a chat window: paste this first. Not tried on every product yet.".format(_and(others)),
                      "copy": prompt_for(result, taos)})
    steps.append({"say": "The same word in a terminal:", "copy": taos + " why"})
    steps.append({"say": "Open this page again:", "copy": taos + " welcome"})
    return steps


def prompt_for(result: Dict[str, Any], taos: str = "taos") -> str:
    """A short plain-text start for an assistant that cannot read the folder: what the project is and the four words."""
    return ("I work on the project \"{0}\" in the folder {1}. Its record is kept by TAOS; the first task is {2}.\n"
            "Before you call any result of mine current, ask me to run `{3} why` and paste what it prints. It answers in "
            "four words: holds (still stands), stale (something it rested on changed), fails (a check does not pass), "
            "unknown (never checked). Treat anything that is not `holds` as not established, and say so."
            ).format(result.get("project", ""), _short(Path(result.get("folder", ""))), result.get("task", ""), taos)


def start(paths: Paths, body: Dict[str, Any]) -> Dict[str, Any]:
    """Set the folder up (or add one check to it) and say what to do next. A refusal comes back in its own words."""
    folder = str(body.get("folder") or "").strip()
    if not folder:
        return {"refused": "Pick or type a folder first."}
    check = str(body.get("check") or "").strip()
    try:
        result = use_mod.use(paths, Path(folder).expanduser(), [check] if check else [])
    except TaosError as refused:
        return {"refused": str(refused)}
    return _told(paths, json.loads(json.dumps(result, default=str)), body.get("assistants"))


def _told(paths: Paths, result: Dict[str, Any], typed: Any) -> Dict[str, Any]:
    """Add what the page shows beside a result: the folder as a person writes it, the way out, and the next steps."""
    helpers, taos = assistants(typed), _taos(paths)
    result["folder_short"] = _short(Path(result.get("folder", "")))
    result["undo"] = taos + " bootstrap unlink-workspace " + _typed(result.get("folder", ""))
    result["assistants"] = helpers
    result["next"] = next_steps(result, helpers, taos)
    return result


def kept(paths: Paths, typed: Any = "") -> Dict[str, Any]:
    """The project this copy already keeps, for someone coming back. It reads: no check is run and nothing is written."""
    folder = use_mod._primary(paths)
    if folder is None or not folder.is_dir():
        return {}
    try:
        task = use_mod._first_task(paths)
        names = [name for name in _listing(folder)[0] if name not in use_mod.WRITTEN]
        found = [] if config_mod.gates(paths) else use_mod.suggestions(folder, names)
    except (TaosError, OSError):
        return {}
    project = (config_mod.load_soft(paths).get("project") or {}).get("name") or folder.name
    return _told(paths, {"project": project, "task": task, "folder": str(folder), "again": True, "written": {},
                         "suggested_checks": found}, typed)


class Practice(object):
    """A throwaway project, so a person changes a file and watches the word before anything of theirs is touched.

    It is a real TAOS home in a temporary folder, built the way `taos demo` builds its own, so the word on the page is
    the program's own answer about real files. Nothing of the person's is read or written, and it is removed on close."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tmp = None                                      # type: Optional[Path]
        self.paths = None                                    # type: Optional[Paths]
        self.work = Path()
        self.task = ""
        self.said = ""                                       # what the check last printed, in one line
        self.rounds = 0                                      # times the result was redone and held again

    def _open(self) -> None:
        if self.paths is not None:
            return
        tmp = Path(tempfile.mkdtemp(prefix="taos-practice-"))
        try:
            work = tmp / "practice"
            work.mkdir()
            for name, text in PRACTICE:
                (work / name).write_text(text, encoding="utf-8")
            check = {"name": "average", "command": "\"{0}\" check.py".format(sys.executable)}
            paths = demo_mod.scratch_home(tmp, workspace=work, project="Practice", prefix="TRY", gates=[check], tasks=[
                {"title": "Report the average", "goal": "result.txt says what data.csv gives", "next_action": "change data.csv"}])
            demo_mod.configure(paths, basis={"domains": {"work": [name for name, _ in PRACTICE]}, "ignore": list(use_mod.WRITTEN)},
                               gates=[dict(check, depends_on=["work"])])
            self.tmp, self.work, self.task, self.paths = tmp, work, use_mod._first_task(paths), paths
            self._check()
        except BaseException:
            self.tmp = self.paths = None
            shutil.rmtree(str(tmp), ignore_errors=True)
            raise

    def _check(self) -> None:
        record = gates_mod.run(self.paths, task_id=self.task, agent="human")
        printed = [str(result.get("tail") or "").strip() for result in record.get("results", [])]
        self.said = printed[-1].splitlines()[-1] if printed and printed[-1] else ""

    def _numbers(self) -> List[str]:
        return (self.work / "data.csv").read_text(encoding="utf-8").split()

    def now(self, do: str = "") -> Dict[str, Any]:
        """Where the practice result stands, after one of the three things a person can do: change, check, redo."""
        with self.lock:
            try:
                self._open()
                if do == "change":
                    numbers = self._numbers()
                    numbers[-1] = str(int(float(numbers[-1])) + 3)
                    (self.work / "data.csv").write_text("\n".join(numbers) + "\n", encoding="utf-8")
                elif do == "check":
                    self._check()
                elif do == "redo":
                    numbers = [float(number) for number in self._numbers()]
                    (self.work / "result.txt").write_text("average = {0:.1f}\n".format(sum(numbers) / len(numbers)), encoding="utf-8")
                    self._check()
                    self.rounds += 1
                parts = [part for part in live(self.paths, self.task).get("parts", []) if part["kind"] == "check"]
                word = parts[0]["state"] if parts else "unknown"
                return {"word": word, "why": parts[0]["reason"] if parts else "", "said": self.said if word == "fails" else "",
                        "result": (self.work / "result.txt").read_text(encoding="utf-8").strip(),
                        "data": ", ".join(self._numbers()), "folder": str(self.work), "rounds": self.rounds}
            except (TaosError, OSError, ValueError, IndexError) as broken:      # a person may edit the practice files by hand
                return {"refused": "The practice files no longer read as numbers: {0}".format(broken)}

    def close(self) -> None:
        with self.lock:
            if self.tmp is not None:
                shutil.rmtree(str(self.tmp), ignore_errors=True)
            self.tmp = self.paths = None


class Door(BaseHTTPRequestHandler):
    paths: Paths
    key: str
    practice: Practice

    def log_message(self, *args: Any) -> None:
        return

    def _local(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data: Dict[str, Any]) -> None:
        self._send(code, json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        split = urlsplit(self.path)
        asked = {name: values[-1] for name, values in parse_qs(split.query, keep_blank_values=True).items()}
        if not self._local() or asked.get("key") != self.key:
            return self._json(403, {"refused": "This page answers only on this computer, at the address TAOS printed."})
        if split.path == "/":
            return self._send(200, PAGE.replace("__KEY__", self.key).encode("utf-8"), "text/html; charset=utf-8")
        if split.path == "/api/folders":
            return self._json(200, folders(asked.get("under") or None, self.paths))
        if split.path == "/api/look":
            return self._json(200, look(self.paths, asked.get("folder"), asked.get("assistants")))
        if split.path == "/api/standing":
            return self._json(200, live(self.paths, asked.get("task")))
        if split.path == "/api/kept":
            return self._json(200, kept(self.paths, asked.get("assistants")))
        if split.path == "/api/try":
            return self._json(200, self.practice.now())
        self._json(404, {"refused": "No such page."})

    def do_POST(self) -> None:
        if not self._local() or self.headers.get("X-TAOS-Key") != self.key:
            return self._json(403, {"refused": "This page answers only on this computer, at the address TAOS printed."})
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 65536)) or b"{}")
        except ValueError:
            return self._json(400, {"refused": "That was not something this page sent."})
        if self.path == "/api/start" and isinstance(body, dict):
            return self._json(200, start(self.paths, body))
        if self.path == "/api/check" and isinstance(body, dict):
            return self._json(200, again(self.paths, body.get("task")))
        if self.path == "/api/try" and isinstance(body, dict):
            do = str(body.get("do") or "")
            return self._json(200, self.practice.now(do if do in ("change", "check", "redo") else ""))
        self._json(404, {"refused": "No such page."})


def serve(paths: Paths, port: int = 0, open_browser: bool = True) -> Tuple[ThreadingHTTPServer, str]:
    """Start the page on this computer only. Returns the server and the one address that reaches it."""
    practice = Practice()
    handler = type("BoundDoor", (Door,), {"paths": paths, "key": secrets.token_urlsafe(16), "practice": practice})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    setattr(server, "practice", practice)                    # so whoever closes the page can remove the practice folder
    atexit.register(practice.close)
    address = "http://127.0.0.1:{0}/?key={1}".format(server.server_address[1], handler.key)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if open_browser:
        webbrowser.open(address)
    return server, address


PAGE = (Path(__file__).with_name("welcome.html").read_text(encoding="utf-8")
        if Path(__file__).with_name("welcome.html").is_file() else "<!doctype html><title>TAOS</title><p>welcome.html is missing.")


if __name__ == "__main__":
    made, where = serve(Paths.discover())
    print("TAOS is open at {0}\nIt answers only on this computer. Press Ctrl-C to close it.".format(where))
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        made.shutdown()
