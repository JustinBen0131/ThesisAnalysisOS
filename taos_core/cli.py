"""The one entry point. Every module registers its own verbs."""

from __future__ import annotations

import argparse
import difflib
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import __version__, page, plain
from . import anchors as anchors_mod
from . import atoms as atoms_mod
from . import bank as bank_mod
from . import bootstrap as bootstrap_mod
from . import brief as brief_mod
from . import burn as burn_mod
from . import changes as changes_mod
from . import claims as claims_mod
from . import config as config_mod
from . import control as control_mod
from . import decisions as decisions_mod
from . import demo as demo_mod
from . import doctor as doctor_mod
from . import events as events_mod
from . import gates as gates_mod
from . import handoff as handoff_mod
from . import hpc as hpc_mod
from . import kernels as kernels_mod
from . import lessons as lessons_mod
from . import lifecycle as lifecycle_mod
from . import mcp_stdio as mcp_stdio_mod
from . import panel as panel_mod
from . import policy as policy_mod
from . import projections as projections_mod
from . import proposals as proposals_mod
from . import replay as replay_mod
from . import rules as rules_mod
from . import standing as standing_mod
from . import tasks as tasks_mod
from . import telemetry as telemetry_mod
from . import usage as usage_mod
from . import use as use_mod
from . import welcome as welcome_mod
from .paths import Paths
from .util import TaosError

MODULES = (
    demo_mod,
    use_mod,
    projections_mod,
    standing_mod,
    doctor_mod,
    tasks_mod,
    claims_mod,
    lifecycle_mod,
    gates_mod,
    handoff_mod,
    hpc_mod,
    decisions_mod,
    proposals_mod,
    telemetry_mod,
    events_mod,
    brief_mod,
    kernels_mod,
    mcp_stdio_mod,
    atoms_mod,
    burn_mod,
    policy_mod,
    control_mod,
    usage_mod,
    changes_mod,
    lessons_mod,
    replay_mod,
    bank_mod,
    rules_mod,
    anchors_mod,
    panel_mod,
    bootstrap_mod,
)

# The last words of the help: how to go one level down, and what `taos` alone does.
EPILOG = "taos <command> --help says what one command takes.\nAsked nothing, taos says where to start.\n"


# What `taos` says when asked nothing, under its name: in a project that is set up, and in a fresh copy.
START = (("taos demo", "the idea in a minute, on a small example"),
         ("taos status", "where everything stands"),
         ("taos why", "what no longer holds, and why"),
         ("taos --help", "every command"))
FRESH = (("taos demo", "the idea in a minute, on a small example"),
         ("taos demo --keep", "then do it by hand, in a folder it leaves you"),
         ("taos use <folder>", "your own work, set up with no questions"),
         ("taos --help", "every command"))

# Every command, under what a person would be doing when they reach for it. The first group is the whole idea: a
# result, what it stood on, and the question asked of it later. Each group after it is a layer the first works without.
GROUPS = (("The core", "demo use welcome task gate why status"),
          ("When agents share the work", "start finish claim capsule handoff pause resume"),
          ("A person's words, kept as said", "rule lesson decide"),
          ("What agents read", "kernel policy control atoms mcp"),
          ("Evidence before a change", "anchor change replay bank hpc"),
          ("Looking back", "brief retro events event panel usage label"),
          ("Upkeep of the system itself", "doctor selftest version bootstrap propose proposals burn"))
LAYERS = "Everything below is optional: a layer to add when the work calls for it."


class Verbs(object):
    """Stands in for the subparsers while modules register, and keeps what each verb said it does."""

    def __init__(self, subparsers: Any, agents: List[str]):
        self.agents = agents
        self.actors = agents + list(config_mod.RESERVED_ACTORS)
        self.subparsers, self.does = subparsers, {}                 # type: Any, Dict[str, str]

    def add_parser(self, name: str, **said: Any) -> argparse.ArgumentParser:
        self.does[name] = said.get("help") or ""
        return self.subparsers.add_parser(name, **said)


def guide(does: Dict[str, str]) -> str:
    """The commands in their groups: the core, a line saying the rest is optional, then each layer. A verb no group
    names is listed last, so none can go missing from the help."""
    named = {verb for _, verbs in GROUPS for verb in verbs.split()}
    groups = GROUPS + ((("More", " ".join(verb for verb in does if verb not in named)),) if set(does) - named else ())
    wide = max(len(verb) for verb in does)
    blocks = ["{0}\n{1}".format(title, "\n".join("  {0}  {1}".format(verb.ljust(wide), does[verb])
                                                 for verb in verbs.split() if verb in does)) for title, verbs in groups]
    return "\n\n".join(blocks[:1] + [LAYERS] + blocks[1:] + [EPILOG])


def _welcome(args: argparse.Namespace, paths: Paths) -> int:
    """`taos welcome`: the front door as a page, served on this computer only until Ctrl-C."""
    server, address = welcome_mod.serve(paths, port=args.port, open_browser=not args.no_open)
    print("TAOS is open at {0}\nIt answers only on this computer. Press Ctrl-C to close it.".format(address), flush=True)
    try:
        WAIT()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


WAIT = threading.Event().wait                                       # how `taos welcome` waits for Ctrl-C (a test replaces it)


def register_welcome(verbs: Any) -> None:
    said = verbs.add_parser("welcome", help="try a practice result, then set up your folder and agents on a local page")
    said.add_argument("--port", type=int, default=0, help="the port on this computer (default: any free one)")
    said.add_argument("--no-open", action="store_true", help="print the address but do not open the browser")
    said.set_defaults(func=_welcome)


def build_parser(agents: Optional[List[str]] = None) -> argparse.ArgumentParser:
    parser = plain.Parser(
        prog="taos",
        description="{0}. {1}\n{2}".format(page.NAME, *page.PROMISE),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--home", help="the copy of TAOS to use (default: the one found from the folder you are in)")
    parser.add_argument("--version", action="version", version="taos {0}".format(__version__))
    verbs = Verbs(parser.add_subparsers(dest="command", required=True, metavar="<command>", help=argparse.SUPPRESS),
                  list(config_mod.DEFAULT_AGENTS) if agents is None else agents)
    for module in MODULES:
        module.register(verbs)
    register_welcome(verbs)
    parser.epilog = guide(verbs.does)
    if verbs.agents and "codex" not in verbs.agents:
        parser.epilog = parser.epilog.replace("--agent codex", "--agent " + verbs.agents[0])
    parser.usage = "taos [--home HOME] <command> ..."               # set last, so no command's own usage line inherits it
    parser.set_defaults(verbs=tuple(verbs.does))
    return parser


def command_target(argv: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Read the global home and command before building their project-specific help."""
    home = None
    words = iter(argv)
    for word in words:
        flag, equals, value = word.partition("=")
        if len(flag) > 3 and "--home".startswith(flag):
            home = value if equals else next(words, None)
        elif not word.startswith("-"):
            return home, word
    return home, None


def nearest(verb: str, verbs: Any) -> Optional[str]:
    """The command a mistyped word most likely meant: one it begins, before one it merely resembles."""
    begun = sorted((known for known in verbs if known.startswith(verb)), key=len)
    near = begun or difflib.get_close_matches(verb, verbs, 1)
    return near[0] if near else None


def quiet(stream: Any) -> None:
    """The reader of a pipe went away (`taos status | head -1`). That is not an error: say nothing more to it."""
    try:
        os.dup2(os.open(os.devnull, os.O_WRONLY), stream.fileno())
    except (AttributeError, OSError, ValueError):
        pass


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    nowhere = {}                                                    # type: Dict[str, Any]
    for name in ("stdout", "stderr"):                               # a closed stream is not an error: write to nowhere
        if getattr(sys, name) is None:
            nowhere[name] = open(os.devnull, "w")
            setattr(sys, name, nowhere[name])
    home, _ = command_target(argv)
    try:
        selected = Paths(Path(home)) if home else Paths.discover()
    except TaosError:
        agents = list(config_mod.DEFAULT_AGENTS)
    else:
        try:
            agents = config_mod.project_agents(selected)
        except TaosError:
            agents = []  # keep help and doctor available while the roster is being repaired
    parser = build_parser(agents)
    verbs = parser.get_default("verbs")
    plain, errors = sys.stdout, sys.stderr
    me, said = page.launcher(), page.commands(verbs)
    if page.terminal(plain):                                        # a person: answers take their shade, commands their spelling
        sys.stdout = page.Shaded(plain, shade=page.shades(plain), said=said, me=me)
    if page.terminal(errors):
        sys.stderr = page.Shaded(errors, shade=False, said=said, me=me)
    try:
        return run(parser, argv, me)
    except BrokenPipeError:
        quiet(plain)
        return 0
    finally:
        for stream, was in ((sys.stdout, plain), (sys.stderr, errors)):
            try:
                stream.flush()
            except BrokenPipeError:
                quiet(was)
            except (OSError, ValueError):
                pass
        sys.stdout, sys.stderr = plain, errors
        for name, opened in nowhere.items():                        # leave a closed stream as it was found
            setattr(sys, name, None)
            opened.close()


def fresh(home: Optional[str]) -> bool:
    """Is there no project set up here yet? Then the greeting points at the demo, not at a status with nothing in it."""
    try:
        paths = Paths(Path(home)) if home else Paths.discover()
    except TaosError:
        return True
    return not paths.constructed()


def run(parser: argparse.ArgumentParser, argv: List[str], me: str) -> int:
    home, verb = command_target(argv)
    verbs = parser.get_default("verbs")
    if verb is None and not any(word.startswith("-") and not "--home".startswith(word) for word in argv):
        page.greet(sys.stdout, FRESH if fresh(home) else START, me if page.terminal(sys.stdout) else "taos")
        return 0
    if verb == "help":
        parser.print_help()
        return 0
    if verb is not None and verb not in verbs:
        near = nearest(verb, verbs)
        sys.stderr.write("taos has no command '{0}'.{1} Every command: taos --help\n".format(
            verb, " Did you mean '{0}'?".format(near) if near else ""))
        return 2
    args = parser.parse_args(argv)
    try:
        paths = Paths(Path(args.home)) if args.home else Paths.discover()
    except TaosError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1

    func = getattr(args, "func", None)
    if func is None:  # pragma: no cover - argparse guards this
        parser.print_help()
        return 2
    try:
        return int(func(args, paths) or 0)
    except claims_mod.ClaimConflict as exc:
        sys.stderr.write(str(exc) + "\n")
        return 4
    except TaosError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        sys.stderr.write("interrupted\n")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
