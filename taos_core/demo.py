"""`taos demo`: the idea in about a minute, on a small measurement, with nothing of yours touched.

It builds a throwaway TAOS home and a copy of `examples/measurement` in a
temporary folder and runs real commands against them. A line that starts
with `$` is a command that was run; the lines under it are what it printed.
After the first full answer, later answers show only the lines that matter.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional

from . import bootstrap as bootstrap_mod
from . import lessons as lessons_mod
from . import rules as rules_mod
from .paths import Paths
from .util import TaosError

REPO = Path(__file__).resolve().parents[1]
OS_PARTS = ("taos", "taos_core", "hooks", "kernels", "atoms", "policies", "bootstrap", "AGENTS.md", "CLAUDE.md",
            ".claude", ".codex", ".agents")
STATES = ("holds", "fails", "stale", "unknown")


def scratch_home(tmp: Path, *, workspace: Path, project: str, prefix: str, gates: List[Any], tasks: List[Any]) -> Paths:
    """A constructed TAOS home under `tmp`, pointed at one workspace. The demo and the evaluations both start here."""
    home = tmp / "os"
    home.mkdir()
    for name in OS_PARTS:
        source = REPO / name
        if source.is_dir():
            shutil.copytree(str(source), str(home / name), ignore=shutil.ignore_patterns(".taos", "__pycache__", ".git"))
        elif source.is_file():
            shutil.copy2(str(source), str(home / name))
    answers = json.loads((REPO / "bootstrap" / "answers.example.json").read_text(encoding="utf-8"))
    answers.update(
        project_name=project, prefix=prefix, stack="python", git_isolation="trunk", open_browser=False,
        install_hooks_in_workspaces=False, agent_corrections=[],
        workspaces=[{"name": workspace.name, "path": str(workspace), "primary": True, "agent": "any"}],
        gates=gates, first_tasks=tasks,
    )
    paths = Paths(home)
    bootstrap_mod.construct(paths, answers, actor="system")
    return paths


def configure(paths: Paths, **changes: Any) -> None:
    """Set top-level keys of the home's config, the way a person would by editing the file."""
    config = json.loads(paths.config_file.read_text(encoding="utf-8"))
    config.update(changes)
    paths.config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")


def build(tmp: Path) -> Paths:
    """The demo's home: a copy of the example measurement, with a check that says what it reads."""
    work = tmp / "pendulum"
    shutil.copytree(str(REPO / "examples" / "measurement"), str(work), ignore=shutil.ignore_patterns("__pycache__"))
    paths = scratch_home(
        tmp, workspace=work, project="Pendulum", prefix="PEN",
        gates=[{"name": "fit", "command": "\"{0}\" analysis/check.py".format(sys.executable)}],
        tasks=[
            {"title": "Measure g from the six swings", "goal": "a value of g with an honest uncertainty",
             "next_action": "run analysis/fit.py", "done_when": "the fit passes its check and g is quoted with its error"},
            {"title": "Plot period against length", "goal": "a figure for the write-up",
             "next_action": "draw T^2 against L with the fitted line"},
        ],
    )
    configure(
        paths,
        basis={"domains": {"analysis": ["analysis/*", "data/*"], "figures": ["figures/*"]}, "ignore": ["README.md"]},
        gates=[{"name": "fit", "command": "\"{0}\" analysis/check.py".format(sys.executable), "depends_on": ["analysis"]}],
    )
    return paths


class Show(object):
    def __init__(self, paths: Paths, out: Any):
        self.paths, self.out = paths, out

    def say(self, text: str = "") -> None:
        self.out.write(text + "\n")

    def run(self, *argv: str, keep: Optional[Callable[[str], bool]] = None) -> str:
        """Run one real command and print what it printed, or only the lines `keep` picks."""
        from .cli import main

        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = main(["--home", str(self.paths.home)] + list(argv))
        self.say("$ taos " + " ".join(item if item.replace("-", "").replace("_", "").replace("/", "").replace(".", "").isalnum()
                                       else json.dumps(item) for item in argv))
        for line in printed.getvalue().splitlines():
            if line.strip() and (keep is None or keep(line)):
                self.say("    " + line.strip())
        if code not in (0, 1):
            raise TaosError("the demo stopped: `taos {0}` exited {1}".format(" ".join(argv), code))
        return printed.getvalue()


def _verdicts(line: str) -> bool:
    words = line.split()
    return bool(words) and (words[0] in STATES or "stand as recorded" in line or "stands as recorded" in line)


def _delivered(line: str) -> bool:
    return line.startswith(("stands:", "told:", "lesson:"))


def play(paths: Paths, out: Any) -> None:
    show = Show(paths, out)
    work = Path(json.loads(paths.config_file.read_text(encoding="utf-8"))["workspaces"][0]["path"])
    say, run = show.say, show.run

    say("A small measurement: six pendulum swings, a fit for g, and a check that the fit is sane.")
    say("TAOS keeps, with every result, what that result stood on. Asked later, it answers")
    say("holds, fails, stale or unknown, and says why.")
    say()
    say("1. A result holds until what it stood on changes")
    say()
    run("gate", "run", "--task", "PEN-1", "--agent", "codex", keep=lambda line: "exit" in line)
    run("task", "transition", "PEN-1", "--to", "done", "--agent", "codex",
        "--reason", "g = 9.82 +/- 0.02 from six swings", "--evidence", "analysis/fit.py")
    run("why", "PEN-1")
    say()
    say("The plot style is edited. The check never read it.")
    (work / "figures" / "style.txt").write_text("line: blue, 1.2 pt\nmarkers: open circles\nfont: 10 pt\n", encoding="utf-8")
    run("why", "PEN-1", keep=_verdicts)
    say()
    say("One swing is measured again, and data/swings.csv changes.")
    data = work / "data" / "swings.csv"
    data.write_text(data.read_text(encoding="utf-8").replace("1.20,2.19", "1.20,2.21"), encoding="utf-8")
    run("why", "PEN-1", keep=_verdicts)
    say()
    say("2. A result belongs to the files it tested, not to the task that asked")
    say()
    run("gate", "run", "--task", "PEN-1", "--agent", "codex", keep=lambda line: "exit" in line)
    say("Another task needs the same check on the same files. It is not run twice.")
    run("gate", "run", "--task", "PEN-2", "--agent", "claude", keep=lambda line: "not rerun" in line)
    say()
    say("3. An instruction keeps its date")
    say()
    run("rule", "add", "--quote", "Use the tape-measured lengths", "--said-on", "2026-01-05", "--scope", "PEN-1")
    first = rules_mod.governing(paths, "PEN-1", on="2026-01-06")[0]["id"]
    run("rule", "add", "--quote", "Use the laser-measured lengths", "--said-on", "2026-03-01", "--scope", "PEN-1",
        "--supersedes", first)
    run("rule", "governing", "PEN-1", "--on", "2026-02-10")
    run("rule", "governing", "PEN-1", "--on", "2026-03-02")
    say("PEN-1 was closed before either instruction was recorded, and its closure says so.")
    run("why", "PEN-1", keep=_verdicts)
    say()
    say("4. Accepted means this version. Shown does not mean repeated.")
    say()
    run("task", "accept", "PEN-1", "--note", "read the fit and the residuals")
    say("A comment is added to analysis/fit.py after the person looked.")
    with (work / "analysis" / "fit.py").open("a", encoding="utf-8") as handle:
        handle.write("\n# the stand was moved before swing 6\n")
    run("why", "PEN-1", keep=lambda line: line.split()[:2] == ["stale", "acceptance:"])
    say()
    rules_mod.add(paths, quote="Quote g with its uncertainty, never alone", said_on="2026-01-05", scope="*")
    lessons_mod.add(paths, title="Drop the swing that hit the stand", words="you fitted the swing that hit the stand again",
                    said_on="2026-02-03", mistake="fitted a disturbed swing", why="it moved g by more than its error",
                    moments=["join"], scope="PEN")
    say("A different agent starts the second task. It is told what governs and what was learned,")
    say("in the words the person used.")
    run("start", "--agent", "claude", "--task", "PEN-2", "--session", "PEN-2 | figure", keep=_delivered)
    run("lesson", "repeats")
    say()
    say("The reminder was shown once, and nobody has judged that case yet. So it counts as one")
    say("exposure and no repeat. Shown is not repeated, and unknown stays unknown.")


def run(out: Any = None, keep: bool = False) -> int:
    out = out or sys.stdout
    tmp = Path(tempfile.mkdtemp(prefix="taos-demo-"))
    try:
        play(build(tmp), out)
        out.write("\n")
        if keep:
            out.write("Kept for you to look around: {0}\n  try: {1}/os/taos --home {1}/os why\n".format(tmp, tmp))
        else:
            out.write("Nothing of yours was touched. `taos demo --keep` leaves the folder so you can look around.\n")
        return 0
    finally:
        if not keep:
            shutil.rmtree(str(tmp), ignore_errors=True)


def _cmd_demo(args: argparse.Namespace, paths: Paths) -> int:
    return run(keep=args.keep)


def register(subparsers: Any) -> None:
    demo = subparsers.add_parser("demo", help="see the idea in a minute, on a small example, touching nothing")
    demo.add_argument("--keep", action="store_true", help="leave the temporary folder in place afterwards")
    demo.set_defaults(func=_cmd_demo)
