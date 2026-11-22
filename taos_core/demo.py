"""`taos demo`: the idea in about a minute, on a small measurement, with nothing of yours touched.

It builds a throwaway TAOS home and a copy of `examples/measurement` in a
temporary folder and runs real commands against them. A line that starts
with `$` is a command that was run; the lines under it are what it printed,
or the lines of that which matter. Any other line says what the demo did to
the files or the record in between.

The script is data: six ideas, each a few steps. A command carries the words
the record should answer with, and the demo stops if the record answers
differently, so the demo is a check as well as a show.

One run, three readers. A person at a terminal gets one screen: a line for
each thing that happened, led by the answer the record gave. `--full`, or a
pipe, gets every command and what it printed. `--json` gets the same run as
a record a program can read.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import bootstrap as bootstrap_mod
from . import lessons as lessons_mod
from . import rules as rules_mod
from .paths import Paths
from .util import TaosError

REPO = Path(__file__).resolve().parents[1]
OS_PARTS = ("taos", "taos_core", "hooks", "kernels", "atoms", "policies", "bootstrap", "AGENTS.md", "CLAUDE.md",
            ".claude", ".codex", ".agents")
STATES = ("holds", "fails", "stale", "unknown")
SCHEMA = "TAOS_DEMO_V1"
EXAMPLE = "Here: six pendulum swings, a fit for g, and a check that the fit is sane."
PROMISE = "TAOS keeps every result with what it stood on. Asked later, it answers holds, stale, fails or unknown, and says why."
FIT = re.compile(r"g = (\S+) \+/- (\S+) (\S+) from (\d+) swings")
SHADE = {"holds": "32", "ok": "32", "held": "32", "stale": "33", "fails": "31", "FAIL": "31", "unknown": "2"}
BOLD, DIM = "1", "2"


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
        basis={"domains": {"analysis": ["analysis/*", "data/*"], "figures": ["figures/*"]},
               "ignore": ["README.md", "AGENTS.md", "CLAUDE.md", ".taos-link.json"]},
        gates=[{"name": "fit", "command": "\"{0}\" analysis/check.py".format(sys.executable), "depends_on": ["analysis"]}],
    )
    return paths


@dataclass
class Step(object):
    """One line of the script: words the demo says, a change it makes, a command it runs, or the first two together."""
    say: str = ""                                    # what a person reads
    do: Optional[Callable[[], Any]] = None           # a change to the files or the record, made before anything is run
    argv: Tuple[str, ...] = ()                       # a real command: `taos ...`, or the example's own python3
    keep: Optional[Callable[[str], bool]] = None     # which printed lines to show; every line when None
    expect: Tuple[str, ...] = ()                     # words the shown lines must contain
    brief: str = ""                                  # the one line this answer gets on the short page
    id: str = ""                                     # a stable name a program can find this answer by


@dataclass
class Moment(object):
    """One idea: a name a program can rely on, the idea in a line, what the record answered, and the steps that show it."""
    id: str
    idea: str
    answered: str
    steps: List[Step]


def say(text: str) -> Step:
    return Step(say=text)


def change(text: str, action: Callable[[], Any]) -> Step:
    return Step(say=text, do=action)


def ask(*argv: str, keep: Optional[Callable[[str], bool]] = None, expect: Tuple[str, ...] = (), brief: str = "",
        id: str = "") -> Step:
    return Step(argv=argv, keep=keep, expect=expect, brief=brief, id=id)


def _has(*words: str) -> Callable[[str], bool]:
    return lambda line: any(word in line for word in words)


def _starts(*words: str) -> Callable[[str], bool]:
    return lambda line: line.strip().startswith(words)


def _verdicts(line: str) -> bool:
    words = line.split()
    return bool(words) and (words[0] in STATES or "as recorded" in line)


def script(paths: Paths, work: Path) -> List[Moment]:
    """The six ideas, in the order they are shown."""
    data, source, style = work / "data" / "swings.csv", work / "analysis" / "fit.py", work / "figures" / "style.txt"
    checks = json.loads(paths.config_file.read_text(encoding="utf-8"))["gates"]
    undeclared = {"name": "style", "command": "grep -c pt figures/style.txt", "depends_on": ["analysis"], "isolated": True}
    fit, why = ("python3", "analysis/fit.py"), ("why", "PEN-1")
    fit_check = _has("check fit", "as recorded")

    def check(task: str, agent: str) -> Tuple[str, ...]:
        return ("gate", "run", "--task", task, "--agent", agent)

    def restyle() -> None:
        style.write_text("line: blue, 1.2 pt\nmarkers: open circles\nfont: 10 pt\n", encoding="utf-8")

    def remeasure() -> None:
        data.write_text(data.read_text(encoding="utf-8").replace("1.20,2.19", "1.20,2.21"), encoding="utf-8")

    def instruct() -> None:
        first = rules_mod.add(paths, quote="Use the tape-measured lengths", said_on="2026-01-05", scope="PEN-1")
        rules_mod.add(paths, quote="Use the laser-measured lengths", said_on="2026-03-01", scope="PEN-1",
                      supersedes=first["id"])

    def comment() -> None:
        with source.open("a", encoding="utf-8") as handle:
            handle.write("\n# the stand was moved before swing 6\n")

    def teach() -> None:
        rules_mod.add(paths, quote="Quote g with its uncertainty, never alone", said_on="2026-01-05", scope="*")
        lessons_mod.add(paths, title="Drop the swing that hit the stand", words="you fitted the swing that hit the stand again",
                        said_on="2026-02-03", mistake="fitted a disturbed swing", why="it moved g by more than its error",
                        moments=["join"], scope="PEN")

    return [
        Moment("standing", "A result holds until what it stood on changes", "holds, holds, stale", [
            ask(*fit, expect=("g = 9.82 +/- 0.02 m/s^2 from 6 swings",)),
            ask(*check("PEN-1", "codex"), keep=_has("exit"), expect=("ok    fit",)),
            ask("task", "transition", "PEN-1", "--to", "done", "--agent", "codex", "--reason", "g = 9.82 +/- 0.02",
                expect=("PEN-1 -> done",)),
            ask(*why, keep=_verdicts, expect=("holds    check fit", "PEN-1 stands as recorded."), id="baseline",
                brief="the fit passes its check and the task closes: g = 9.82 +/- 0.02"),
            change("The plot style is edited. The check never read it.", restyle),
            ask(*why, keep=fit_check, expect=("holds    check fit", "PEN-1 stands as recorded."), id="style-only",
                brief="the plot style is edited, which the check never read"),
            change("One swing is measured again, and data/swings.csv changes.", remeasure),
            ask(*why, keep=fit_check, id="timing-edited", brief="one swing is measured again: data/swings.csv changed",
                expect=("stale    check fit: analysis changed: data/swings.csv", "PEN-1 does not stand as recorded: stale.")),
        ]),
        Moment("reuse", "A pass belongs to the files, not to the task", "ran once, shared once", [
            say("The flag was right. On the new swing the same fit gives a different g."),
            ask(*fit, expect=("g = 9.75 +/- 0.02 m/s^2 from 6 swings",)),
            ask(*check("PEN-1", "codex"), keep=_has("exit"), expect=("ok    fit",), id="rerun",
                brief="the check runs again on the new swing: g = 9.75 +/- 0.02"),
            say("Another task needs the same check on the same files. It is not run twice."),
            ask(*check("PEN-2", "claude"), keep=_has("not rerun"), id="shared",
                brief="a second task asks the same check of the same files: not run twice",
                expect=("held  fit", "not rerun: nothing it tested has changed")),
        ]),
        Moment("instructions", "An instruction keeps its date", "February tape, March laser", [
            change("On January 5 the person says to use the tape-measured lengths. On March 1, the laser-measured ones.",
                   instruct),
            ask("rule", "governing", "PEN-1", "--on", "2026-02-10", keep=_starts("\""), id="february",
                expect=("\"Use the tape-measured lengths\"",), brief="February 10: \"Use the tape-measured lengths\" is in force"),
            ask("rule", "governing", "PEN-1", "--on", "2026-03-02", keep=_starts("\""), id="march",
                expect=("\"Use the laser-measured lengths\"",), brief="March 2: \"Use the laser-measured lengths\" is in force"),
            say("PEN-1 was closed before either instruction was recorded, and its closure says so."),
            ask(*why, keep=_has("closure:", "as recorded"), id="closure",
                brief="the task closed before either was recorded, and its closure says so",
                expect=("stale    closure:", "the instructions have changed since")),
        ]),
        Moment("acceptance", "Acceptance is of one version", "stale after one comment", [
            ask("task", "accept", "PEN-1", "--note", "read the fit and the residuals", expect=("PEN-1 accepted by human",),
                id="accepted", brief="a person reads the fit and accepts the result"),
            change("A comment is added to analysis/fit.py after the person looked.", comment),
            ask(*why, keep=_has("acceptance:"), expect=("stale    acceptance:", "analysis changed: analysis/fit.py"),
                id="edited-after", brief="the code is edited afterwards: the acceptance was of the old version"),
        ]),
        Moment("reminder", "A reminder shown is not a mistake repeated", "shown 1, repeated 0", [
            change("A different agent starts the second task. It is told what governs and what was learned, "
                   "in the words the person used.", teach),
            ask("start", "--agent", "claude", "--task", "PEN-2", "--session", "PEN-2 | figure", keep=_starts("told:", "lesson:"),
                id="told", brief="a new agent starts and is told the lesson in the person's own words",
                expect=("told:      \"Quote g with its uncertainty, never alone\"", "lesson:    Drop the swing that hit the stand")),
            ask("lesson", "repeats", expect=("0 repeated, 0 followed, 1 not judged, of 1 times shown",), id="repeats",
                brief="asked later: 0 repeated, 0 followed, 1 not judged, of 1 times shown"),
            say("The reminder was shown once and nobody has judged that case yet: one exposure, no repeat. "
                "Unknown stays unknown."),
        ]),
        Moment("isolation", "A check passes only on what it declared", "fails, then holds", [
            change("A second check reads figures/style.txt but declares only the analysis. It runs isolated: "
                   "in an empty folder that holds only the files it declared.",
                   lambda: configure(paths, gates=checks + [undeclared])),
            ask(*check("PEN-2", "claude"), keep=_has("style", "isolated:"), id="undeclared",
                brief="a check reads figures/style.txt but declared only the analysis",
                expect=("FAIL  style        exit 2", "A file it could not find is one it did not declare.")),
            change("The declaration is corrected to name the figures, and the same check passes.",
                   lambda: configure(paths, gates=checks + [dict(undeclared, depends_on=["figures"])])),
            ask(*check("PEN-2", "claude"), keep=_has("style", "isolated:"), expect=("ok    style        exit 0",),
                id="declared", brief="the declaration is corrected and the same check passes"),
        ]),
    ]


def _plain(word: str) -> bool:
    return word.replace("-", "").replace("_", "").replace("/", "").replace(".", "").isalnum()


def _run(paths: Paths, work: Path, step: Step) -> Dict[str, Any]:
    """Run one real command, keep the lines the step shows, and stop if they lack the words it expects."""
    command = " ".join(word if _plain(word) else json.dumps(word) for word in step.argv)
    if step.argv[0] == "python3":
        done = subprocess.run([sys.executable] + list(step.argv[1:]), cwd=str(work), capture_output=True, text=True)
        code, text = done.returncode, done.stdout
    else:
        from .cli import main

        command, printed = "taos " + command, io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = main(["--home", str(paths.home)] + list(step.argv))
        text = printed.getvalue()
    if code not in (0, 1):
        raise TaosError("the demo stopped: `{0}` exited {1}".format(command, code))
    shown = [line.strip() for line in text.splitlines() if line.strip() and (step.keep is None or step.keep(line))]
    for words in step.expect:
        if words not in "\n".join(shown):
            raise TaosError("the demo stopped: `{0}` was expected to answer {1!r} and printed:\n{2}".format(
                command, words, text.rstrip() or "(nothing)"))
    ran = {"kind": "run", "command": command, "printed": shown, "expected": list(step.expect)}
    answer = next((line.split()[0] for line in shown if line.split()[0] in SHADE), "")
    for name, value in (("id", step.id), ("brief", step.brief), ("answer", answer)):
        if value:
            ran[name] = value
    measured = FIT.search(text)
    if measured:
        with (work / "data" / "swings.csv").open(newline="", encoding="utf-8") as handle:
            rows = [{name: float(value) for name, value in row.items()} for row in csv.DictReader(handle)]
        ran["measured"] = {"g": float(measured.group(1)), "standard_error": float(measured.group(2)),
                           "unit": measured.group(3), "swings": int(measured.group(4)), "rows": rows}
    return ran


def play(paths: Paths) -> Dict[str, Any]:
    """Run the script against a built home. The run comes back as a record: what was said, run, printed and expected."""
    work = Path(json.loads(paths.config_file.read_text(encoding="utf-8"))["workspaces"][0]["path"])
    moments = []
    for number, moment in enumerate(script(paths, work), 1):
        steps: List[Dict[str, Any]] = []
        for step in moment.steps:
            if step.do:
                step.do()
            if step.say:
                steps.append({"kind": "say", "text": step.say})
            if step.argv:
                steps.append(_run(paths, work, step))
        moments.append({"number": number, "id": moment.id, "idea": moment.idea, "answered": moment.answered, "steps": steps})
    runs = [step for moment in moments for step in moment["steps"] if step["kind"] == "run"]
    return {"schema": SCHEMA, "example": EXAMPLE, "promise": PROMISE, "moments": moments,
            "commands": len(runs), "checked": sum(len(step["expected"]) for step in runs)}


class Page(object):
    """Writes for a person. Piped, every line is plain and whole. On a terminal it is folded to the width and shaded."""

    def __init__(self, out: Any, width: Optional[int], color: bool):
        self.out, self.width, self.color = out, width, color

    def ink(self, code: str, text: str) -> str:
        return "\x1b[{0}m{1}\x1b[0m".format(code, text) if self.color and code else text

    def states(self, text: str) -> str:
        return re.sub(r"\b({0})\b".format("|".join(STATES)), lambda found: self.ink(SHADE[found.group(1)], found.group(1)), text)

    def fold(self, text: str, hang: int = 0) -> List[str]:
        if not self.width or len(text) <= self.width:
            return [text]
        return textwrap.wrap(text, self.width, subsequent_indent=" " * hang, break_long_words=False, break_on_hyphens=False)

    def line(self, text: str = "") -> None:
        self.out.write(text + "\n")

    def prose(self, text: str, code: str = "", states: bool = False) -> None:
        for part in self.fold(text):
            self.line(self.states(part) if states else self.ink(code, part))

    def printed(self, text: str) -> None:
        """A line a command printed: indented, its continuation under its second word, its leading answer shaded."""
        lead = re.match(r"\S+\s+", text)
        parts = self.fold("    " + text, hang=4 + min(len(lead.group(0)), 11) if lead else 6)
        answer = re.match(r"(\s+)({0})(\s)".format("|".join(SHADE)), parts[0])
        if answer:
            parts[0] = answer.group(1) + self.ink(SHADE[answer.group(2)], answer.group(2)) + parts[0][answer.end(2):]
        for part in parts:
            self.line(part)


def short(page: Page, record: Dict[str, Any]) -> None:
    """One screen: each idea, and under it a row for each answer, led by the word the record gave."""
    for moment in record["moments"]:
        page.line()
        page.line(page.ink(BOLD, "{0}  {1}".format(moment["number"], moment["idea"])))
        for step in moment["steps"]:
            if step.get("brief"):
                answer = step.get("answer", "")
                page.line("   {0} {1}".format(page.ink(SHADE.get(answer, ""), answer.ljust(7)), step["brief"]))


def transcript(page: Page, record: Dict[str, Any]) -> None:
    """Everything: each command as it was run and what it printed, then the six ideas with what the record answered."""
    for moment in record["moments"]:
        page.line()
        page.prose("{0}. {1}".format(moment["number"], moment["idea"]), BOLD)
        page.line()
        for index, step in enumerate(moment["steps"]):
            if step["kind"] == "say":
                if index:
                    page.line()
                page.prose(step["text"])
            else:
                page.line(page.ink(DIM, "$ " + step["command"]))
                for text in step["printed"]:
                    page.printed(text)
    page.line()
    page.prose("What the record answered", BOLD)
    page.line()
    pad = max(len(moment["idea"]) for moment in record["moments"])
    for moment in record["moments"]:
        page.line("  {0}  {1}  {2}".format(moment["number"], moment["idea"].ljust(pad), page.states(moment["answered"])))


def write(record: Dict[str, Any], out: Any, *, full: bool = True, width: Optional[int] = None, color: bool = False,
          closing: Tuple[str, ...] = ()) -> None:
    """The run as a page for a person: the promise, the short page or the transcript, and how it ended."""
    page = Page(out, width, color)
    page.prose(record["promise"], states=True)
    page.prose(record["example"])
    (transcript if full else short)(page, record)
    page.line()
    for text in closing:
        page.line(text)


def run(out: Any = None, keep: bool = False, as_json: bool = False, full: Optional[bool] = None,
        width: Optional[int] = None, color: Optional[bool] = None) -> int:
    """Play the demo. Left to itself it writes the short page to a terminal and the transcript to anything else."""
    out = out or sys.stdout
    terminal = bool(getattr(out, "isatty", lambda: False)())
    full = not terminal if full is None else full
    if width is None and (terminal or not full):           # the short page is set for 80 columns wherever it goes
        width = max(80, min(shutil.get_terminal_size().columns, 100)) if terminal else 80
    if color is None:
        color = (terminal or bool(os.environ.get("FORCE_COLOR"))) and not os.environ.get("NO_COLOR")
    tmp = Path(tempfile.mkdtemp(prefix="taos-demo-"))
    try:
        paths = build(tmp)
        began = time.perf_counter()
        record = play(paths)
        seconds = time.perf_counter() - began
        if as_json:
            out.write(json.dumps(dict(record, kept=str(tmp) if keep else None), indent=2) + "\n")
            return 0
        closing = ("{0} commands ran in {1:.1f} s, and the record gave all {2} answers expected of it.".format(
            record["commands"], seconds, record["checked"]),)
        if not full:
            closing += ("Each row is a real command and its answer. See them all: taos demo --full",)
        if keep:
            closing += ("Kept for you to look around: {0}".format(tmp), "  try: {0}/os/taos --home {0}/os why".format(tmp))
        else:
            closing += ("Nothing of yours was touched. `taos demo --keep` leaves the folder in place.",)
        write(record, out, full=full, width=width, color=color, closing=closing)
        return 0
    finally:
        if not keep:
            shutil.rmtree(str(tmp), ignore_errors=True)


def _cmd_demo(args: argparse.Namespace, paths: Paths) -> int:
    return run(keep=args.keep, as_json=args.json, full=True if args.full else False if args.brief else None)


def register(subparsers: Any) -> None:
    demo = subparsers.add_parser("demo", help="see the idea in a minute, on a small example, touching nothing")
    demo.add_argument("--keep", action="store_true", help="leave the temporary folder in place afterwards")
    view = demo.add_mutually_exclusive_group()
    view.add_argument("--full", action="store_true", help="every command and what it printed (what a pipe gets)")
    view.add_argument("--brief", action="store_true", help="one line per answer (what a terminal gets)")
    view.add_argument("--json", action="store_true", help="the run as a record a program can read")
    demo.set_defaults(func=_cmd_demo)
