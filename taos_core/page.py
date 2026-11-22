"""How a run is written for a person: an opener, then lines that are plain in a pipe and shaded on a terminal.

The opener is the name in a box, the way ROOT greets a physicist. TAOS has
four letters and gives four answers, so each letter takes the shade of one
answer, in the order the promise names them: the mark is also the legend.
Where the stream cannot carry box-drawing characters, the same box is drawn
in plain ones.
"""

from __future__ import annotations

import re
import textwrap
from typing import Any, Dict, List, Optional, Tuple

from . import __version__

ANSWERS = ("holds", "stale", "fails", "unknown")
SHADE = {"holds": "32", "ok": "32", "held": "32", "stale": "33", "fails": "31", "FAIL": "31", "unknown": "2"}
BOLD, DIM = "1", "2"
WIDTH = 80
NAME, HOME = "ThesisAnalysisOS", "whatstillholds.com"
PROMISE = ("Every result is kept with what it stood on.", "Ask it later: holds, stale, fails or unknown, and why.")
MARK = ("╺┳╸ ┏━┓ ┏━┓ ┏━╸",
        " ┃  ┣━┫ ┃ ┃ ┗━┓",
        " ╹  ╹ ╹ ┗━┛ ╺━┛")


class Page(object):
    """Writes for a person. Piped, every line is plain and whole. On a terminal it is folded to the width and shaded."""

    def __init__(self, out: Any, width: Optional[int], color: bool):
        self.out, self.width, self.color = out, width, color

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


def write(record: Dict[str, Any], out: Any, *, full: bool = True, width: Optional[int] = None, color: bool = False,
          closing: Tuple[str, ...] = ()) -> None:
    """The run as a page for a person: the opener, the short page or the transcript, and how it ended."""
    page = Page(out, width, color)
    page.opener()
    page.prose(record["example"])
    (transcript if full else short)(page, record)
    page.line()
    for text in closing:
        page.line(text) if "/" in text else page.prose(text)         # a path is never folded
