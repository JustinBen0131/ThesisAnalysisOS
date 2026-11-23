"""Plain words for a mistake: what was wrong, the nearest real thing, and the command to run next.

Interface rule 6 (docs/INTERFACE.md). Two kinds of mistake reach a person:
a command typed incompletely or with a wrong value, which argparse catches
(`Parser`), and a name that does not exist, which a module catches
(`missing`). Both answer in a sentence and end with a way forward.
"""

from __future__ import annotations

import argparse
import difflib
import re
import shlex
import shutil
import textwrap
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional, Sequence

REQUIRED = re.compile(r"the following arguments are required: (?P<names>.+)$")
CHOICE = re.compile(r"argument (?P<arg>[^:]+): invalid choice: (?P<value>.+?) \(choose from (?P<choices>.*)\)$")
TYPED = re.compile(r"argument (?P<arg>[^:]+): invalid (?P<kind>\w+) value: (?P<value>.+)$")
ONE = re.compile(r"argument (?P<arg>[^:]+): expected (?P<count>.+?) arguments?$")
EXTRA = re.compile(r"unrecognized arguments: (?P<words>.+)$")
AMBIGUOUS = re.compile(r"ambiguous option: (?P<word>\S+) could match (?P<options>.+)$")
KINDS = {"int": "a whole number", "float": "a number"}


STAMP = re.compile(r"\b(\d{4}-\d\d-\d\d)T(\d\d:\d\d)(?::\d\d(?:\.\d+)?)?(?:Z|\+00:00)")


def _clock(date: str, minute: str = "00:00") -> Optional[datetime]:
    try:
        return datetime.strptime(date + " " + minute, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).astimezone()
    except ValueError:
        return None


def local(text: str) -> str:
    """Times as the reader's own clock shows them: each recorded UTC stamp becomes a local date and minute."""
    def swap(found: Any) -> str:
        moment = _clock(found.group(1), found.group(2))
        return moment.strftime("%Y-%m-%d %H:%M") if moment else found.group(0)
    return STAMP.sub(swap, text)


def day(stamp: Any) -> str:
    """The reader's local date of a recorded UTC stamp; the stamp's own date if it carries no time."""
    found = STAMP.search(str(stamp))
    moment = _clock(found.group(1), found.group(2)) if found else None
    return moment.strftime("%Y-%m-%d") if moment else str(stamp)[:10]


LED = re.compile(r"^(\s*)(holds|stale|fails|unknown)(\s+)")
COMMAND = re.compile(r"(?<=: )taos \S.*$")


def fold(text: str, width: Optional[int] = None) -> str:
    """Each line folded to the screen under its own reason, never inside a command a person may copy."""
    width = max(40, width or shutil.get_terminal_size((80, 24)).columns)
    out = []
    for line in text.split("\n"):
        if len(line) <= width:
            out.append(line)
            continue
        led = LED.match(line)
        hang = led.end() if led else len(line) - len(line.lstrip()) + (6 if line.lstrip().startswith("next:") else 2)
        whole = COMMAND.search(line)
        kept = line[:whole.start()] + whole.group(0).replace(" ", "\x00") if whole else line
        wrapped = textwrap.wrap(kept, width, subsequent_indent=" " * min(hang, width // 2),
                                break_long_words=False, break_on_hyphens=False)
        out.extend(part.replace("\x00", " ") for part in wrapped or [line])
    return "\n".join(out)


def shell(word: Any) -> str:
    """A word as a shell reads it: a path with a space stays one word when pasted."""
    return shlex.quote(str(word))


def launcher(paths) -> str:
    """A command for this exact copy that is safe to paste into the current shell."""
    found = shutil.which("taos")
    if found and Path(found).resolve() == paths.launcher:
        return "taos"
    if Path.cwd().resolve() == paths.home:
        return "./taos"
    return shell(paths.launcher)


def nearest(word: str, known: Iterable[str]) -> Optional[str]:
    """The one real name a person most likely meant: the same name in another case first, then the closest spelling."""
    names, typed = [str(name) for name in known], str(word).lower()
    for name in names:
        if name.lower() == typed:
            return name
    begun = [name for name in names if typed and name.lower().startswith(typed)]
    if len(begun) == 1:
        return begun[0]
    lowered = {name.lower(): name for name in names}
    close = difflib.get_close_matches(typed, list(lowered), 1, 0.6)
    return lowered[close[0]] if close else None


def missing(what: str, name: str, known: Iterable[str], every: str) -> str:
    """There is no such thing: say so, offer the nearest real one, and say how to see them all."""
    near = nearest(name, known)
    return "There is no {0} '{1}'.{2} Every {0}: {3}".format(
        what, name, " Did you mean '{0}'?".format(near) if near else "", every)


def _unquote(text: str) -> str:
    text = text.strip()
    return text[1:-1] if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"" else text


def _either(words: Sequence[str]) -> str:
    words = list(words)
    return words[0] if len(words) == 1 else "{0} or {1}".format(", ".join(words[:-1]), words[-1])


def _both(words: Sequence[str]) -> str:
    words = list(words)
    return words[0] if len(words) == 1 else "{0} and {1}".format(", ".join(words[:-1]), words[-1])


class Parser(argparse.ArgumentParser):
    """An argument parser that answers a mistake in plain words, never with a usage dump. Exit code stays 2."""

    def parse_known_args(self, args: Any = None, namespace: Any = None) -> Any:
        self.typed = list(args) if args is not None else None
        return super().parse_known_args(args, namespace)

    # -- what the parser knows about itself ---------------------------------

    def _verbs(self) -> Optional[argparse._SubParsersAction]:
        return next((action for action in self._actions if isinstance(action, argparse._SubParsersAction)), None)

    def _named(self, arg: str) -> Optional[argparse.Action]:
        for action in self._actions:
            if arg in action.option_strings or arg in (action.dest, action.metavar) or arg == "/".join(action.option_strings):
                return action
        return None

    def _blank(self, action: argparse.Action) -> str:
        """What a person fills in for one argument: its choices, or its name in angle brackets."""
        if action.choices and not isinstance(action, argparse._SubParsersAction):
            return "<{0}>".format("|".join(str(choice) for choice in action.choices))
        return "<{0}>".format(str(action.metavar or action.dest).lower().replace("_", "-"))

    def _shown(self, action: argparse.Action) -> str:
        return action.option_strings[0] if action.option_strings else "<{0}>".format(
            str(action.metavar or action.dest).lower().replace("_", "-"))

    def _strays(self) -> List[str]:
        """Options typed here that this command does not take, each with the nearest one it does."""
        options = [option for action in self._actions for option in action.option_strings]
        lines = []
        for word in self.typed or []:
            if word.startswith("-") and word.split("=")[0] not in options:
                near = nearest(word.split("=")[0], options)
                lines.append("{0} does not take '{1}'.{2}".format(self.prog, word, " Did you mean {0}?".format(near) if near else ""))
        return lines

    def template(self) -> str:
        """This command with every required piece as a blank to fill in."""
        words = [self.prog]
        for action in self._actions:
            if action.option_strings and action.required:
                words += [action.option_strings[0], self._blank(action)]
        for action in self._actions:
            if not action.option_strings and not isinstance(action, argparse._SubParsersAction) and action.nargs not in ("?", "*"):
                words.append(self._blank(action))
        return " ".join(words)

    def commands(self) -> List[str]:
        """This command's own commands, one per line, each with what it does."""
        verbs = self._verbs()
        if verbs is None:
            return []
        does = {choice.dest: choice.help or "" for choice in verbs._choices_actions}
        wide = max(len(name) for name in verbs.choices)
        return ["  {0}  {1}".format(name.ljust(wide), does.get(name, "")).rstrip() for name in verbs.choices]

    def _options(self) -> List[str]:
        """Every option this command, or the deepest command named in what was typed, accepts."""
        parser: Parser = self
        for word in self.typed or []:
            verbs = parser._verbs()
            if verbs is not None and word in verbs.choices and isinstance(verbs.choices[word], Parser):
                parser = verbs.choices[word]
        self.deepest = parser
        return [option for action in parser._actions for option in action.option_strings]

    # -- the answer ------------------------------------------------------------

    def explain(self, message: str) -> str:
        more = "Everything it takes: {0} --help".format(self.prog)
        found = REQUIRED.match(message)
        if found:
            names = [name.strip() for name in found.group("names").split(",")]
            actions = [self._named(name) for name in names]
            if any(isinstance(action, argparse._SubParsersAction) for action in actions):
                return "{0} needs one of its commands:\n{1}\n{0} <command> --help says what one takes.".format(
                    self.prog, "\n".join(self.commands()))
            shown = [self._shown(action) if action else name for action, name in zip(actions, names)]
            return "\n".join(self._strays() + ["{0} needs {1}:".format(self.prog, _both(shown)),
                                                "  " + self.template(), more])
        found = CHOICE.match(message)
        if found:
            value, choices = _unquote(found.group("value")), [_unquote(c) for c in found.group("choices").split(",")]
            near = nearest(value, choices)
            mean = " Did you mean '{0}'?".format(near) if near else " " + more
            action = self._named(found.group("arg"))
            if isinstance(action, argparse._SubParsersAction):
                return "{0} has no command '{1}'.{2}".format(
                    self.prog, value, " Did you mean '{0}'?".format(near) if near else "") + " Its commands: {0} --help".format(self.prog)
            if action is not None and not action.option_strings:
                return "{0} takes {1}, not '{2}'.{3}".format(self.prog, _either(choices), value, mean)
            return "{0} {1} takes {2}, not '{3}'.{4}".format(
                self.prog, self._shown(action) if action else found.group("arg"), _either(choices), value, mean)
        found = TYPED.match(message)
        if found:
            action = self._named(found.group("arg"))
            return "{0} {1} takes {2}, not {3}. {4}".format(self.prog, self._shown(action) if action else found.group("arg"),
                                                            KINDS.get(found.group("kind"), "a " + found.group("kind")),
                                                            found.group("value"), more)
        found = ONE.match(message)
        if found:
            return "{0} {1} needs a value after it. {2}".format(self.prog, found.group("arg").split("/")[0], more)
        found = EXTRA.match(message)
        if found:
            options, lines = self._options(), []
            for word in found.group("words").split():
                near = nearest(word.split("=")[0], options) if word.startswith("-") else None
                lines.append("{0} does not take '{1}'.{2}".format(self.deepest.prog, word,
                                                                   " Did you mean {0}?".format(near) if near else ""))
            return "\n".join(lines + ["Everything it takes: {0} --help".format(self.deepest.prog)])
        found = AMBIGUOUS.match(message)
        if found:
            return "{0} could be {1}; type it in full. {2}".format(
                found.group("word"), _either([option.split("=")[0].strip() for option in found.group("options").split(",")]),
                more)
        return "{0}: {1}. {2}".format(self.prog, message, more)

    def error(self, message: str) -> Any:  # type: ignore[override]
        self.exit(2, self.explain(message) + "\n")
