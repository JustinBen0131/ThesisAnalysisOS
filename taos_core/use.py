"""`taos use <folder>`: keep a record for the work in one folder, set up with no questions.

Everything is taken from the folder. The project is named for it, its task ids
carry a prefix made from that name, the folder is its one workspace, and no
agent has to be present. Each `--check` is a command that passes when the
work is right. It runs in the folder and rests on every file there that is
not ignored, so an edit to any of them turns its answer stale and names the
file. The checks run once, at the end, and their rows are shown.

In the person's folder it writes only what `taos bootstrap link-workspace`
writes: one block between markers in AGENTS.md and in CLAUDE.md, and
.taos-link.json. `taos bootstrap unlink-workspace <folder>` takes out exactly
those, leaving the folder as it was. The record itself lives in this copy.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import basis
from . import bootstrap as bootstrap_mod
from . import config as config_mod
from . import gates as gates_mod
from . import kernels as kernels_mod
from . import tasks as tasks_mod
from .paths import Paths
from .plain import launcher, shell
from .store import atomic_write_json, locked, read_json, utc_now
from .util import TaosError

CLONE = "https://github.com/JustinBen0131/ThesisAnalysisOS.git"
WRITTEN = ("AGENTS.md", "CLAUDE.md", ".taos-link.json")      # what linking writes, so no check rests on it
NAMED = re.compile(r"^([A-Za-z][\w.-]{0,30}):\s+(\S.*)$")      # "fit: python3 analysis/check.py"
PLAIN = re.compile(r"^[\w./~+-]+$")                              # a path or a word, not code in quotes
RUNNER = re.compile(r"^(python[\d.]*|sh|bash|zsh|Rscript|node|ruby|perl|julia|env)$")
CODE = re.compile(r"\.(py|sh|R|r|jl|js|ts|pl|rb|C|cc|cpp|m|ipynb)$")


def answers(paths: Paths, workspace: Path, *, project: str, prefix: str, gates: List[Any], tasks: List[Any],
            stack: str = "python", **more: Any) -> Dict[str, Any]:
    """The setup answers for one project in one folder; what they do not say, the shipped example says."""
    said = json.loads((paths.bootstrap_dir / "answers.example.json").read_text(encoding="utf-8"))
    said.update(
        project_name=project, prefix=prefix, stack=stack, git_isolation="trunk", open_browser=False,
        install_hooks_in_workspaces=False, agent_corrections=[],
        workspaces=[{"name": workspace.name, "path": str(workspace), "primary": True, "agent": "any"}],
        gates=gates, first_tasks=tasks,
    )
    said.update(more)
    return said


# A prefix is on every task id a person reads, so it never spells one of these, whatever the folder is called.
REFUSED = ("ANAL", "ANUS", "ARSE", "ASS", "COCK", "CUM", "CUNT", "DAMN", "DICK", "FAG", "FUC", "FUK", "JIZ", "KKK", "NAZI",
           "NIG", "PISS", "POO", "PORN", "RAPE", "SEX", "SHIT", "SLUT", "TIT", "TWAT", "WANK")


def _fit(prefix: str) -> bool:
    return bool(re.match(r"^[A-Z][A-Z0-9]{1,7}$", prefix)) and not any(stem in prefix for stem in REFUSED)


def prefix_for(name: str) -> str:
    """Task ids for a project: the first letters and digits of its name in capitals ("my-analysis" gives MYAN-1).

    When those spell something nobody wants on their screen ("analysis"), a shorter or sparser form of the same name
    is taken instead: three letters, then the words' initials, then its consonants, then two letters."""
    letters = re.sub(r"[^A-Za-z0-9]", "", name).upper()
    if not letters[:1].isalpha():
        letters = "P" + letters
    words = [word for word in (re.sub(r"[^A-Z0-9]", "", part) for part in re.split(r"[\s_.-]+", name.upper())) if word]
    sparse, seen = letters[:1], set(letters[:1])
    for letter in letters[1:]:
        if letter not in "AEIOU" and letter not in seen:
            sparse, seen = sparse + letter, seen | {letter}
    first = (letters + "X")[:max(2, min(4, len(letters)))]
    initials = "".join(word[0] for word in words)[:4] if len(words) > 1 else ""
    for prefix in (first, letters[:3], initials, sparse[:4], sparse[:3], letters[:2], "PX"):
        if _fit(prefix):
            return prefix
    return "TASK"


def _name_of(command: str) -> str:
    """A check's name when none is given: the script it runs (`python3 analysis/check.py` is `check`), else the last
    plain word it is given (`make test` is `test`), else the program itself; never a piece of quoted code."""
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    after = [word for word in words[1:] if not word.startswith("-") and PLAIN.match(word)]
    scripts = [word for word in after if CODE.search(word)] or [word for word in after if "/" in word]
    program = Path(words[0]).name if words else ""
    word = scripts[0] if scripts else after[-1] if after else "" if RUNNER.match(program) else program
    name = re.sub(r"[^\w.-]", "-", Path(word.rstrip("/")).stem).strip("-.")
    return name if name[:1].isalpha() else "check"


def checks(given: List[str]) -> List[Dict[str, str]]:
    """Each --check as a gate: "name: command", or the command alone and named for what it runs."""
    found, seen = [], set()
    for text in given:
        text = text.strip()
        if not text:
            raise TaosError("A --check needs a command that passes when the work is right, like: "
                            "--check \"python3 analysis/check.py\"")
        named = NAMED.match(text)
        name, command = (named.group(1), named.group(2)) if named else (_name_of(text), text)
        base, count = name, 2
        while name in seen:
            name, count = "{0}-{1}".format(base, count), count + 1
        seen.add(name)
        found.append({"name": name, "command": command})
    return found


def _person() -> str:
    try:
        return getpass.getuser() or "you"
    except Exception:  # pragma: no cover - no login name at all
        return "you"


def _zone() -> str:
    """The reader's time zone by its name, as the clock on this machine has it."""
    named = os.environ.get("TZ", "").lstrip(":")
    if "/" in named and not named.startswith("/"):
        return named
    try:
        target = os.path.realpath("/etc/localtime")
    except OSError:  # pragma: no cover
        return "UTC"
    return target.split("zoneinfo/", 1)[1] if "zoneinfo/" in target else "UTC"


def _primary(paths: Paths) -> Optional[Path]:
    for workspace in config_mod.load_soft(paths).get("workspaces") or []:
        if workspace.get("primary"):
            return Path(workspace["path"]).expanduser().resolve()
    return None


def shown(path: Any, typed: Optional[str] = None) -> str:
    """A folder in a sentence: as the person typed it, else from their home as ~/...; a command keeps the full path."""
    if typed and str(typed).rstrip("/") in (".", ""):
        return "this folder"
    if typed:
        return str(typed)
    path, home = Path(path), Path.home()
    try:
        return "~/" + path.relative_to(home).as_posix() if path != home else "~"
    except ValueError:
        return str(path)


def _refusal(paths: Paths, folder: Path, given: List[str], typed: Optional[str], reads: List[str]) -> str:
    config = config_mod.load_soft(paths)
    project = config.get("project", {}).get("name", "another project")
    where = _primary(paths) or paths.home
    copy = paths.home.parent / "taos-{0}".format(re.sub(r"[^\w.-]+", "-", folder.name).strip("-.") or "project")
    again = "".join(" --check " + shell(text) for text in given) + "".join(" --reads " + shell(read) for read in reads)
    return ("This copy of TAOS already keeps the record for {0}, whose work is in {1}. One copy keeps one project.\n"
            "To add {2} to {0} as one more folder:\n"
            "  {8} bootstrap link-workspace {3}\n"
            "To keep it as a project of its own, start it from a new copy:\n"
            "  git clone {4} {5}\n"
            "  {6} use {3}{7}\n").format(project, shown(where), shown(folder, typed), shell(str(folder)), CLONE,
                                         shell(str(copy)), shell(str(copy / "taos")), again, launcher(paths))


def _config(paths: Paths, change: Any) -> None:
    """Change the home's config in place, under the same lock setup takes."""
    with locked(paths):
        config = json.loads(paths.config_file.read_text(encoding="utf-8"))
        change(config)
        atomic_write_json(paths.config_file, config)


def _hidden(paths: Paths, folder: Path) -> List[str]:
    """No check rests on what linking writes, nor on this copy when it sits inside the folder."""
    hidden = list(WRITTEN)
    if folder in paths.home.resolve().parents:
        hidden.append(paths.home.resolve().relative_to(folder).as_posix() + "/*")
    return hidden


def reading(folder: Path, reads: List[str]) -> Dict[str, List[str]]:
    """What --reads names, as the patterns of one domain, and everything else in the folder, as patterns to ignore.

    A folder is read with all it holds ("data" is data/*), a file as itself. What is not on the way to a named file or
    folder is ignored, so the checks rest on what they read and a large folder need not be fingerprinted whole."""
    named = []
    for read in reads:
        path = Path(read).expanduser()
        path = (path if path.is_absolute() else folder / path).resolve()
        if path != folder and folder not in path.parents:
            raise TaosError("--reads {0} is outside {1}. Name a file or folder inside it.".format(shell(read), shell(str(folder))))
        if not path.exists():
            raise TaosError("There is no {0} in {1}. Name a file or folder the checks read.".format(shell(read), shell(str(folder))))
        if path == folder:
            return {"patterns": ["*"], "elsewhere": []}
        named.append((path.relative_to(folder).as_posix(), path.is_dir()))
    keep = {rel for rel, _ in named}
    elsewhere = []                                                 # type: List[str]

    def walk(rel: str) -> None:
        for entry in sorted(os.listdir(str(folder / rel) if rel else str(folder))):
            inside = "{0}/{1}".format(rel, entry) if rel else entry
            if entry in basis.TRANSIENT or inside in keep:
                continue
            if any(read.startswith(inside + "/") for read in keep):
                walk(inside)
            else:
                elsewhere.append(inside + "/*" if (folder / inside).is_dir() else inside)
    walk("")
    return {"patterns": sorted(rel + "/*" if is_dir else rel for rel, is_dir in named), "elsewhere": elsewhere}


def _too_large(folder: Path, settings: Dict[str, Any]) -> Tuple[Optional[Tuple[int, int]], List[str]]:
    """The files and bytes the checks would rest on, when that is more than one fingerprint takes (basis.MAX_FILES,
    MAX_BYTES), and the listing itself, so that nothing walks the folder twice."""
    names = basis.listing(folder, settings.get("ignore"))
    declared = settings.get("domains") or {}
    if declared:
        named = [pattern for patterns in declared.values() for pattern in patterns]
        names = sorted(set(names) | set(basis.on_disk(folder, named, settings.get("ignore"))))
    if len(names) > basis.MAX_FILES:
        return (len(names), -1), names
    size = sum((folder / name).stat().st_size for name in names)
    return ((len(names), size) if size > basis.MAX_BYTES else None), names


def _sound(linked: Any) -> bool:
    """Is this what link-workspace writes? The same fields it verifies before it will touch a folder."""
    return (isinstance(linked, dict) and linked.get("schema") == "TAOS_LINK_V1"
            and isinstance(linked.get("installed", []), list) and isinstance(linked.get("file_sha256", {}), dict)
            and isinstance(linked.get("blocks", {}), dict)
            and all(isinstance(record, dict) for record in linked.get("blocks", {}).values()))


def _reserve(paths: Paths, folder: Path) -> bool:
    """Take the folder for this copy before anything is set up: its .taos-link.json, naming this copy, created only
    if no such file is there. Of two copies starting at once exactly one creates it; the other finds it and is
    refused with nothing written in itself. True when this call created it."""
    pointer = folder / ".taos-link.json"
    if pointer.exists():
        return False
    draft = folder / ".taos-link.json.{0}.tmp".format(os.getpid())
    try:
        draft.write_text(json.dumps({"schema": "TAOS_LINK_V1", "taos_home": str(paths.home), "linked_at": utc_now(),
                                     "hook_override": False, "hooks_enabled": False, "blocks": {}, "installed": [],
                                     "file_sha256": {}}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.link(str(draft), str(pointer))                          # whole and exclusive: it fails if the file is there
        return True
    except FileExistsError:
        return False
    except OSError as exc:
        raise TaosError("TAOS cannot write in {0} ({1}). It adds AGENTS.md, CLAUDE.md and .taos-link.json there and "
                        "nothing else. Nothing was set up. Make the folder writable, then run this again.".format(
                            shell(str(folder)), exc.strerror or exc))
    finally:
        try:
            draft.unlink()
        except OSError:
            pass


def _release(paths: Paths, folder: Path) -> None:
    """Give back a reservation when setting up failed: only a pointer that is still this copy's and links nothing."""
    pointer = folder / ".taos-link.json"
    linked = read_json(pointer)
    if _sound(linked) and linked.get("taos_home") == str(paths.home) and not linked.get("blocks") and not linked.get("installed"):
        pointer.unlink()


def _owned(paths: Paths, folder: Path, typed: Optional[str], given: List[str], reads: List[str]) -> Optional[str]:
    """Why this copy may not take the folder, when another copy keeps it. The rule is link-workspace's: the folder's
    .taos-link.json names one copy, and only that copy may write there. Asked before anything is written, so a refusal
    leaves this copy as it was and asking again is refused again."""
    pointer = folder / ".taos-link.json"
    if not pointer.exists():
        return None
    linked = read_json(pointer)
    owner = linked.get("taos_home") if _sound(linked) else None
    if not isinstance(owner, str):
        return ("{0} has a .taos-link.json that does not say which copy of TAOS keeps it. Nothing was set up. "
                "Look at that file before using the folder here.".format(shown(folder, typed)))
    if owner == str(paths.home):
        return None
    if not Paths._is_home(Path(owner)):                            # the copy that kept it is gone: say how to go on
        return ("{0} was kept by a copy of TAOS that is no longer there ({1}). Nothing was set up here.\n"
                "To keep it with this copy, remove that copy's link file and run this again:\n"
                "  rm {2}\n"
                "The block that copy left in AGENTS.md and CLAUDE.md is not this copy's to change; it stays until you "
                "take it out by hand.\n").format(shown(folder, typed), shown(owner), shell(str(pointer)))
    again = "".join(" --check " + shell(text) for text in given) + "".join(" --reads " + shell(read) for read in reads)
    other = shell(str(Path(owner) / "taos"))
    return ("{0} is already kept by another copy of TAOS, in {1}. Nothing was set up here.\n"
            "Use that copy:\n"
            "  {2} use {3}{4}\n"
            "Or take the folder out of that copy, then run this again:\n"
            "  {2} bootstrap unlink-workspace {3}\n").format(shown(folder, typed), shown(owner), other, shell(str(folder)), again)


def _settle(paths: Paths, folder: Path, read: Optional[Dict[str, List[str]]]) -> None:
    """Write what the checks rest on. With --reads: only what it names, and every check depends on it."""
    hidden = _hidden(paths, folder) + (read["elsewhere"] if read else [])

    def change(config: Dict[str, Any]) -> None:
        settings = dict(config.get("basis") or {})
        if read:
            settings["ignore"] = sorted(set(hidden))
            settings["domains"] = dict(settings.get("domains") or {}, reads=read["patterns"])
        else:
            settings["ignore"] = sorted(set(settings.get("ignore") or []) | set(hidden))
        config["basis"] = settings
        if "reads" in (settings.get("domains") or {}):             # a check added later rests on the same files
            config["gates"] = [dict(gate, depends_on=["reads"]) if read or not gate.get("depends_on") else gate
                               for gate in config.get("gates") or []]
    _config(paths, change)


def _first_task(paths: Paths) -> str:
    records = tasks_mod.TaskStore(paths).load()["tasks"]
    number = lambda task_id: int(task_id.rsplit("-", 1)[-1]) if task_id.rsplit("-", 1)[-1].isdigit() else 0
    ordered = sorted(records, key=number)
    open_ = [task_id for task_id in ordered if records[task_id].get("status") not in tasks_mod.TERMINAL]
    if not ordered:
        raise TaosError("This project has no task to run its checks under. What it has: taos task list")
    return (open_ or ordered)[0]


def _suggest(folder: Path, gates: List[Dict[str, str]]) -> List[str]:
    """What the checks look like they read: the top folder of each path a check's command names inside the folder."""
    found = []
    for gate in gates:
        try:
            words = shlex.split(gate["command"])
        except ValueError:
            words = gate["command"].split()
        for word in words[1:]:
            top = Path(word).parts[0] if word and not word.startswith("-") and not Path(word).is_absolute() else ""
            if top and top not in found and (folder / top).exists() and (folder / word).exists():
                found.append(top)
    return found


def _too_much(folder: Path, typed: Optional[str], given: List[str], reads: List[str], size: Tuple[int, int],
              gates: List[Dict[str, str]]) -> str:
    count, bytes_ = size
    held = "{0} files".format(count) if bytes_ < 0 else "{0} files, {1} MB".format(count, bytes_ // (1024 * 1024))
    limit = "{0} files and {1} MB".format(basis.MAX_FILES, basis.MAX_BYTES // (1024 * 1024))
    checks_again = "".join(" --check " + shell(text) for text in given) or " --check \"<command>\""
    if reads:
        return ("What --reads names holds {0}, more than a check can rest on ({1}). Nothing was set up. "
                "Name fewer or smaller files and folders.".format(held, limit))
    suggested = _suggest(folder, gates) or ["<file or folder>"]
    return ("{0} holds {1}, more than a check can rest on at once ({2}). Nothing was set up.\n"
            "Name the files or folders the checks read, and run it again:\n"
            "  taos use {3}{4}{5}\n").format(shown(folder, typed), held, limit, shell(str(folder)), checks_again,
                                            "".join(" --reads " + (shell(top) if top[0] != "<" else top) for top in suggested))


MAKE = re.compile(r"^(test|check)[ \t]*:(?!=)", re.M)
SCRIPT = re.compile(r"^(?:[^/]+/)?(check|verify|validate)\.(py|sh)$")
PYTEST = re.compile(r"^tests?/(?:.*/)?test_[^/]*\.py$")


def suggestions(folder: Path, names: List[str]) -> List[Dict[str, str]]:
    """Checks this folder already has, found by name in its listing and in a few small files. Nothing is run.

    At most three, each {"name", "command", "from"}: a name in the project's own words, the command as it would be
    given to --check, and the file that suggested it."""
    names = [name for name in names if not any(part.startswith(".") for part in name.split("/"))]
    top = set(names)

    def text(name: str, limit: int = 200000) -> str:
        try:
            with (folder / name).open(encoding="utf-8", errors="replace") as source:
                return source.read(limit)
        except OSError:
            return ""
    found = []                                                     # type: List[Dict[str, str]]

    def offer(name: str, command: str, source: str, other: str = "") -> None:
        taken = {check["name"] for check in found}
        if command not in {check["command"] for check in found}:
            found.append({"name": name if name not in taken else other or "{0}-{1}".format(name, len(found) + 1),
                          "command": command, "from": source})

    for makefile in ("Makefile", "makefile", "GNUmakefile"):
        if makefile in top:
            for target in MAKE.findall(text(makefile)):
                offer("tests" if target == "test" else "check", "make " + target, makefile, "make-" + target)
            break
    tested = next((name for name in names if PYTEST.match(name)), None)
    named = next((name for name, mark in (("pytest.ini", ""), ("pyproject.toml", "[tool.pytest"), ("setup.cfg", "[tool:pytest]"))
                  if name in top and mark in text(name)), None)
    if tested or named:
        offer("tests", "python3 -m pytest -q", named or tested.split("/")[0] + "/", "pytest")
    if "package.json" in top:
        try:
            script = (json.loads(text("package.json")).get("scripts") or {}).get("test")
        except (ValueError, AttributeError):
            script = None
        if isinstance(script, str) and script.strip() and "no test specified" not in script:
            offer("tests", "npm test", "package.json", "npm-test")
    if "Cargo.toml" in top:
        offer("tests", "cargo test", "Cargo.toml", "cargo-test")
    if "go.mod" in top:
        offer("tests", "go test ./...", "go.mod", "go-test")
    for name in names:
        script = SCRIPT.match(name)
        if script:
            offer(script.group(1), "{0} {1}".format("sh" if script.group(2) == "sh" else "python3", shell(name)), name,
                  re.sub(r"[^\w.-]", "-", name.rsplit(".", 1)[0]))
    for name in [name for name in names if name.endswith(".tex") and name.count("/") <= 1][:5]:
        if "\\documentclass" in text(name, 20000):
            offer("builds", "latexmk -pdf -halt-on-error {0}".format(shell(name)), name, "builds-" + Path(name).stem)
    return found[:3]


def _given(check: Dict[str, str]) -> str:
    """A suggested check as the word after --check, quoted to paste: in double quotes when that is safe."""
    said = "{0}: {1}".format(check["name"], check["command"])
    return '"{0}"'.format(said) if not re.search(r'["$`\\!]', said) else shell(said)


def use(paths: Paths, folder: Path, given: List[str], name: Optional[str] = None, prefix: Optional[str] = None,
        reads: Optional[List[str]] = None, typed: Optional[str] = None,
        drop: Optional[List[str]] = None) -> Dict[str, Any]:
    """Set this copy up for the work in `folder`, or add checks to the project it already keeps there, then run them.

    `reads` narrows what the checks rest on; `typed` is the folder as the person wrote it, for the sentences."""
    folder, reads = Path(folder).expanduser(), list(reads or [])
    if folder.is_file():
        raise TaosError("{0} is a file. Name the folder it is in: taos use {1}".format(
            shell(str(folder)), shell(str(folder.parent))))
    if not folder.is_dir():
        raise TaosError("There is no folder {0}. Name the folder your work is in: taos use <folder>".format(
            shell(str(folder))))
    folder = folder.resolve()
    home = paths.home.resolve()
    if folder == home or home in folder.parents:
        raise TaosError("{0} is inside this copy of TAOS. Name the folder your work is in: taos use <folder>".format(
            shell(str(folder))))
    gates = checks(given)
    project = (name or folder.name).strip() or "project"
    if prefix is not None and not re.match(r"^[A-Za-z][A-Za-z0-9]{1,7}$", prefix):
        raise TaosError("A prefix is 2 to 8 letters or digits, starting with a letter, like AZ or NOIR; not {0}.".format(
            shell(prefix)))
    asked = prefix.upper() if prefix else None

    before = {item: (folder / item).exists() for item in WRITTEN}
    owned = _owned(paths, folder, typed, given, reads)
    if owned:
        raise TaosError(owned)
    again = paths.constructed()
    if again and _primary(paths) != folder:
        raise TaosError(_refusal(paths, folder, given, typed, reads))
    read = reading(folder, reads) if reads else None
    names = None                                                   # type: Optional[List[str]]
    if read or not again:                                          # before anything is written: can the checks rest on it?
        settings = {"ignore": _hidden(paths, folder) + (read["elsewhere"] if read else [])}
        if read:
            settings["domains"] = {"reads": read["patterns"]}
        size, names = _too_large(folder, settings)
        if size:
            raise TaosError(_too_much(folder, typed, given, reads, size, gates))
    reserved = _reserve(paths, folder)                             # from here the folder is this copy's, or it is refused
    owned = _owned(paths, folder, typed, given, reads)
    if owned:
        raise TaosError(owned)
    try:
        return _set_up(paths, folder, gates, read, again, before, name, asked, project, typed, list(drop or []), names)
    except BaseException:
        if reserved:
            _release(paths, folder)
        raise


def _set_up(paths: Paths, folder: Path, gates: List[Dict[str, str]], read: Optional[Dict[str, List[str]]], again: bool,
            before: Dict[str, bool], name: Optional[str], asked: Optional[str], project: str,
            typed: Optional[str], drop: List[str], names: Optional[List[str]] = None) -> Dict[str, Any]:
    home = paths.home.resolve()
    if again:
        kept = config_mod.load_soft(paths).get("project", {})
        for wanted, have, what in ((name, kept.get("name"), "named"), (asked, kept.get("prefix"), "given the prefix")):
            if wanted and wanted != have:
                raise TaosError("This project is already {0} {1}. Leave that out to keep it: taos use {2}".format(
                    what, have, shell(str(folder))))
        project, prefix = kept.get("name", project), kept.get("prefix", "")

        have = [str(gate.get("name")) for gate in config_mod.gates(paths)]
        for gone in drop:
            if gone not in have:
                raise TaosError("There is no check named {0}. {1}".format(shell(gone), "The checks: {0}".format(
                    ", ".join(have)) if have else "This project has no checks yet."))

        def add(config: Dict[str, Any]) -> None:
            mine = {gate["name"]: gate for gate in gates}
            config["gates"] = [mine.pop(str(gate.get("name")), gate) for gate in config.get("gates") or []
                               if str(gate.get("name")) not in drop] + list(mine.values())
        if gates or drop:
            _config(paths, add)
        if not before[".taos-link.json"]:                          # unlinked since: link it again, never with hooks
            linked = [bootstrap_mod.link_workspace(paths, folder, install_hooks=False)]
        else:
            linked = []
    else:
        if drop:
            raise TaosError("Nothing is set up here yet, so there is no check to drop. Start: taos use {0} --check "
                            "\"<command>\"".format(shell(str(folder))))
        prefix = asked or prefix_for(project)
        task = {"title": "Keep {0} passing its checks".format(project), "goal": "every check holds on the files as they are",
                "next_action": "change what the work needs, then run the checks again",
                "done_when": "the work is finished and every check holds"}
        built = bootstrap_mod.construct(paths, answers(
            paths, folder, project=project, prefix=prefix, gates=gates, tasks=[task], stack="generic",
            principal_name=_person(), timezone=_zone()), actor="human")
        linked = built["workspaces_linked"]
    for link in linked:
        if link.get("error"):
            raise TaosError("Could not link {0}: {1}".format(shell(str(folder)), link["error"]))
    _settle(paths, folder, read)

    written = {}
    for link in linked:
        for item, action in sorted(link.get("docs", {}).items()):
            written[item] = "created" if action == "appended" and not before[item] else action
        written[".taos-link.json"] = "updated" if before[".taos-link.json"] else "created"
    task_id = _first_task(paths)
    record = gates_mod.run(paths, task_id=task_id, agent="human") if config_mod.gates(paths) else None
    for kernel in ("PROJECT_KERNEL", "PRINCIPAL_KERNEL"):          # setting up is done: the summaries are of it as set up
        try:
            kernels_mod.index_refresh(paths, kernel, "taos")
        except TaosError:
            pass
    kernels_mod.generate_now(paths)
    domains = (config_mod.load_soft(paths).get("basis") or {}).get("domains") or {}
    return {"project": project, "prefix": prefix, "task": task_id, "folder": str(folder), "shown": shown(folder, typed),
            "home": str(home), "record_in": str(paths.state), "again": again, "written": written,
            "reads": domains.get("reads"), "checks": record,
            "suggested_checks": [] if record else suggestions(
                folder, names if names is not None else basis.listing(folder, _hidden(paths, folder)))}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


SAID = {"created": "a new file holding only the TAOS block",
        "appended": "the TAOS block added at the end, between <!-- taos:begin --> and <!-- taos:end -->",
        "updated": "the TAOS block brought up to date"}


def lines(result: Dict[str, Any], runner: str = "taos") -> List[str]:
    """What `taos use` says: what it set up, what it wrote and how to undo it, the checks' rows, and what to run next.
    A folder in a sentence reads as the person wrote it; in a command it is the full path, quoted to paste."""
    folder, where, task = shell(result["folder"]), result.get("shown") or result["folder"], result["task"]
    said = ["{0} {1}. Its record is kept in this copy, in {2}; its first task is {3}.".format(
        result["project"], "was already set up here" if result["again"] else "is set up", shown(result["record_in"]), task)]
    if result["written"]:
        wide = max(len(item) for item in result["written"])
        said += ["", "In {0} it wrote only this:".format(where)]
        said += ["  {0}  {1}".format(item.ljust(wide), "a new file: where this copy of TAOS is" if item == ".taos-link.json"
                 else SAID.get(action, "left as it was: " + action)) for item, action in result["written"].items()]
        said.append("To take that out again and leave the folder as it was: {1} bootstrap unlink-workspace {0}".format(folder, runner))
    else:
        said += ["", "Nothing new was written in {0}.".format(where)]
    said.append("")
    record = result["checks"]
    if record is None:
        said.append("No checks yet. A check is a command that passes when the work is right.")
        offered = result.get("suggested_checks") or []
        if offered:
            said.append("This folder already has {0} you could use:".format("some" if len(offered) > 1 else "one"))
            said += ["  {2} use {0} --check {1}".format(folder, _given(check), runner) for check in offered]
            said.append("Or name your own: {1} use {0} --check \"<command>\"".format(folder, runner))
        else:
            said.append("Add one, and it runs at once: {1} use {0} --check \"<command>\"".format(folder, runner))
        steps = [("taos task show {0}".format(task), "the task the checks will stand under"),
                 ("taos status", "where everything stands"),
                 ("taos demo", "the idea in a minute, on a small example")]
    else:
        reads = result.get("reads")
        rests = ("The default check covers tracked and non-ignored project files in {0}".format(where) if not reads or reads == ["*"] else
                 "Each check rests on {0} in {1}".format(", ".join(pattern[:-2] if pattern.endswith("/*") else pattern
                                                                    for pattern in reads), where))
        said.append(rests + "; change one and it reads stale, naming the file. Run once now:")
        if not reads or reads == ["*"]:
            said.append("If the check reads a Git-ignored input, include it with --reads alongside its other inputs.")
        said += gates_mod.rows(record)
        failed = [check for check in record["results"] if check["exit"] != 0]
        if failed:
            lost = [check["name"] for check in failed if check["exit"] == 127]
            said += ["", "{0} of {1} checks did not pass; its output is above. {2} is set up all the same.".format(
                len(failed), len(record["results"]), result["project"])]
            if lost:
                said.append("{0}: the program was not found. A check runs in {1}, as typed there.".format(", ".join(lost), where))
            said.append("Give a check again under its name to replace it, or drop it:")
            said += ["  {2} use {0} --check \"{1}: <command>\"".format(folder, failed[0]["name"], runner),
                     "  {2} use {0} --drop {1}".format(folder, shell(failed[0]["name"]), runner)]
        steps = [("taos why {0}".format(task), "what {0} rests on, and whether it holds".format(task)),
                 ("taos gate run --task {0} --agent human".format(task), "run the checks again after an edit"),
                 ("taos status", "where everything stands")]
    steps = [(runner + command[len("taos"):], why) for command, why in steps]
    wide = max(len(command) for command, _ in steps)
    said += ["", "Next:"] + ["  {0}  {1}".format(command.ljust(wide), why) for command, why in steps]
    return said


def _cmd_use(args: argparse.Namespace, paths: Paths) -> int:
    result = use(paths, Path(args.folder), args.check, name=args.name, prefix=args.prefix, reads=args.reads,
                 typed=args.folder, drop=args.drop)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for line in lines(result, launcher(paths)):
            gates_mod._say(line)
    return 0 if result["checks"] is None or result["checks"]["ok"] else 1


def register(subparsers: Any) -> None:
    use_parser = subparsers.add_parser("use", help="keep a record for the work in a folder, set up with no questions")
    use_parser.add_argument("folder", help="the folder your work is in")
    use_parser.add_argument("--check", action="append", default=[], metavar="COMMAND",
                            help="a command that passes when the work is right, run in the folder; "
                                 "\"name: command\" names it; give it again for more")
    use_parser.add_argument("--reads", action="append", default=[], metavar="PATH",
                            help="a file or folder the checks read, inside the folder; give it again for more. "
                                 "Leave it out and they rest on every file there")
    use_parser.add_argument("--drop", action="append", default=[], metavar="NAME",
                            help="take a check out by its name; give it again for more")
    use_parser.add_argument("--name", help="the project's name (default: the folder's)")
    use_parser.add_argument("--prefix", help="its task ids' prefix, 2 to 8 capitals (default: made from the name)")
    use_parser.add_argument("--json", action="store_true", help="the result as a record a program can read")
    use_parser.set_defaults(func=_cmd_use)
