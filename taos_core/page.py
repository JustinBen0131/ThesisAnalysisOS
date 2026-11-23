"""How a run is written for a person: an opener, then lines that are plain in a pipe and shaded on a terminal.

The opener is the name in a box, the way ROOT greets a physicist. TAOS has
four letters and gives four answers, so each letter takes the shade of one
answer, in the order the promise names them: the mark is also the legend.
Where the stream cannot carry box-drawing characters, the same box is drawn
in plain ones.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
import textwrap
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import __version__

ANSWERS = ("holds", "stale", "fails", "unknown")
SHADE = {"holds": "32", "stale": "33", "fails": "31", "unknown": "2"}       # the four answers, and nothing else
BOLD, DIM = "1", "2"
WIDTH = 80
NAME, HOME = "ThesisAnalysisOS", "whatstillholds.com"
PROMISE = ("Every result is kept with what it stood on.", "Ask it later: holds, stale, fails or unknown, and why.")
MARK = ("╺┳╸ ┏━┓ ┏━┓ ┏━╸",
        " ┃  ┣━┫ ┃ ┃ ┗━┓",
        " ╹  ╹ ╹ ┗━┛ ╺━┛")


def terminal(out: Any) -> bool:
    return bool(getattr(out, "isatty", lambda: False)())


def shades(out: Any) -> bool:
    """Does this stream take shades? A terminal that can show them does, unless the person has said NO_COLOR."""
    if os.environ.get("NO_COLOR"):
        return False
    return bool(os.environ.get("FORCE_COLOR")) or (terminal(out) and os.environ.get("TERM") != "dumb")


def launcher() -> str:
    """How this person started taos, so that a command shown to them can be pasted: `taos` when it is on their PATH,
    else the path they typed (`./taos`, `../os/taos`)."""
    typed = sys.argv[0] if sys.argv and sys.argv[0] else ""
    found = shutil.which("taos")
    if os.path.basename(typed) == "taos" and os.sep in typed:
        if found and os.path.realpath(found) == os.path.realpath(typed):
            return "taos"
        return shlex.quote(typed)
    return "taos" if found else "./taos"


def commands(verbs: Sequence[str]) -> Any:
    """Finds `taos` where a line names a command to run (`taos status`, `taos --help`): not `./taos`, not the word in prose."""
    known = "|".join(sorted((re.escape(verb) for verb in verbs), key=len, reverse=True))
    return re.compile(r"(?<![\w./-])taos(?= (?:" + known + r")\b| --help\b| --version\b)")


class Page(object):
    """Writes for a person. Piped, every line is plain and whole. On a terminal it is folded to the width and shaded."""

    def __init__(self, out: Any, width: Optional[int], color: bool):
        self.out, self.width, self.color = out, width, color

    @classmethod
    def to(cls, out: Any, width: Optional[int] = None, color: Optional[bool] = None, whole: bool = False) -> "Page":
        """A page for this stream. A terminal gets its own width; a pipe gets 80 columns, or every line whole if asked."""
        if width is None and (terminal(out) or not whole):
            width = min(shutil.get_terminal_size().columns, 100) if terminal(out) else WIDTH
        return cls(out, width, shades(out) if color is None else color)

    def ink(self, code: str, text: str) -> str:
        return "\x1b[{0}m{1}\x1b[0m".format(code, text) if self.color and code else text

    def states(self, text: str) -> str:
        return re.sub(r"\b({0})\b".format("|".join(ANSWERS)), lambda found: self.ink(SHADE[found.group(1)], found.group(1)), text)

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

    def draws(self) -> bool:
        """Can this stream carry the box and the mark as drawn?"""
        try:
            "".join(MARK + ("┌─┐│└┘",)).encode(getattr(self.out, "encoding", None) or "utf-8")
            return True
        except (UnicodeError, LookupError):
            return False

    def mark(self, drawn: bool) -> List[str]:
        """TAOS, three rows high. Four letters for four answers: each letter is shaded as the answer it stands for."""
        if not drawn:
            letters = "".join(self.ink(SHADE[answer], letter) for answer, letter in zip(ANSWERS, "TAOS"))
            return [letters + " " * (len(MARK[0]) - 4)] + [" " * len(MARK[0])] * 2
        return [" ".join(self.ink(SHADE[answer], row[4 * at:4 * at + 3]) for at, answer in enumerate(ANSWERS)) for row in MARK]

    def opener(self) -> None:
        """The name in a box: the mark, the version and where it lives, and the promise with its four answers."""
        drawn = self.draws()
        if (self.width or WIDTH) < WIDTH:                   # a narrow window: the mark without its box, the words under it
            beside = ["", self.ink(BOLD, NAME) + " " + self.ink(DIM, __version__), self.ink(DIM, HOME)]
            if self.width < len(MARK[0]) + 3 + len(NAME) + 1 + len(__version__):   # narrower still: the words under the mark too
                for mark in self.mark(drawn):
                    self.line(mark.rstrip())
                for text in beside[1:]:
                    self.line(text)
            else:
                for mark, text in zip(self.mark(drawn), beside):
                    self.line((mark + "   " + text).rstrip())
            self.prose(PROMISE[0])
            self.prose(PROMISE[1], states=True)
            return
        room = WIDTH - len(MARK[0]) - 9
        gap = room - len(NAME) - len(__version__) - len(HOME) - 1
        said = [self.ink(BOLD, NAME) + " " + self.ink(DIM, __version__) + " " * gap + self.ink(DIM, HOME),
                PROMISE[0].ljust(room),
                self.states(PROMISE[1]) + " " * (room - len(PROMISE[1]))]
        side, flat = ("│", "─") if drawn else ("|", "-")
        self.line(self.ink(DIM, ("┌{0}┐" if drawn else " {0}").format(flat * (WIDTH - 2))))
        for mark, text in zip(self.mark(drawn), said):
            self.line("{0}  {1}   {2}  {0}".format(self.ink(DIM, side), mark, text))
        self.line(self.ink(DIM, ("└{0}┘" if drawn else " {0}").format(flat * (WIDTH - 2))))


def short(page: Page, record: Dict[str, Any]) -> None:
    """One screen: each idea, and under it a row for each answer, led by the word the record gave."""
    for moment in record["moments"]:
        page.line()
        page.line(page.ink(BOLD, "{0}  {1}".format(moment["number"], moment["idea"])))
        for step in moment["steps"]:
            if step.get("brief"):
                answer = step.get("answer", "").ljust(7)
                parts = page.fold("   {0} {1}".format(answer, step["brief"]), hang=11)
                page.line("   " + page.ink(SHADE.get(answer.strip(), ""), answer) + parts[0][10:])
                for part in parts[1:]:
                    page.line(part)


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


class Shaded(object):
    """A terminal with a person at it. A line led by holds, stale, fails or unknown takes its shade, and a command a
    line names is written the way this person started taos, so that it can be pasted."""

    LED = re.compile(r"^(\s{1,4})(" + "|".join(SHADE) + r")(?=\s\s|$)")     # a row's lead, not a word a fold left alone

    def __init__(self, out: Any, shade: bool = True, said: Any = None, me: str = "taos"):
        self.out, self.rest, self.begun = out, "", False
        self.shade, self.said, self.me = shade, said, me

    def dressed(self, text: str) -> str:
        if self.said is not None and self.me != "taos":
            text = self.said.sub(lambda _: self.me, text)
        if self.shade and not self.begun:
            text = self.LED.sub(lambda led: "{0}\x1b[{1}m{2}\x1b[0m".format(led.group(1), SHADE[led.group(2)], led.group(2)), text)
        return text

    def write(self, text: str) -> int:
        *lines, self.rest = (self.rest + text).split("\n")
        for line in lines:
            self.out.write(self.dressed(line) + "\n")
            self.begun = False
        return len(text)

    def flush(self) -> None:
        if self.rest:                                               # a line shown before it ends keeps its lead's shade
            self.out.write(self.dressed(self.rest))
            self.rest, self.begun = "", True
        self.out.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.out, name)


def greet(out: Any, start: Sequence[Tuple[str, str]], me: Optional[str] = None) -> None:
    """What `taos` says when asked nothing: the name in a box, then where to start, as this person can type it."""
    page = Page.to(out)
    me = launcher() if me is None else me
    start = [(me + command[4:] if command.startswith("taos") else command, does) for command, does in start]
    page.opener()
    page.line()
    wide = max(len(command) for command, _ in start)
    for command, does in start:
        if page.width and 2 + wide + 3 + len(does) > page.width:    # a narrow window: the command, and under it what it does
            page.line("  " + page.ink(BOLD, command))
            for part in page.fold("      " + does, hang=6):
                page.line(page.ink(DIM, part))
        else:
            page.line("  {0}   {1}".format(page.ink(BOLD, command.ljust(wide)), page.ink(DIM, does)))


def write(record: Dict[str, Any], out: Any, *, full: bool = True, width: Optional[int] = None, color: Optional[bool] = None,
          closing: Tuple[str, ...] = ()) -> None:
    """The run as a page for a person: the opener, the short page or the transcript, and how it ended."""
    page = Page.to(out, width, color, whole=full)
    page.opener()
    page.prose(record["example"])
    (transcript if full else short)(page, record)
    page.line()
    for text in closing:
        page.line(text) if text.startswith("  ") else page.prose(text)   # a line to paste is never folded
