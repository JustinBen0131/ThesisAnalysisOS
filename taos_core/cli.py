"""The one entry point. Every module registers its own verbs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import atoms as atoms_mod
from . import bootstrap as bootstrap_mod
from . import brief as brief_mod
from . import burn as burn_mod
from . import claims as claims_mod
from . import control as control_mod
from . import decisions as decisions_mod
from . import doctor as doctor_mod
from . import events as events_mod
from . import gates as gates_mod
from . import handoff as handoff_mod
from . import kernels as kernels_mod
from . import lifecycle as lifecycle_mod
from . import panel as panel_mod
from . import policy as policy_mod
from . import projections as projections_mod
from . import proposals as proposals_mod
from . import tasks as tasks_mod
from . import telemetry as telemetry_mod
from .paths import Paths
from .util import TaosError

MODULES = (
    projections_mod,
    doctor_mod,
    tasks_mod,
    claims_mod,
    lifecycle_mod,
    gates_mod,
    handoff_mod,
    decisions_mod,
    proposals_mod,
    telemetry_mod,
    events_mod,
    brief_mod,
    kernels_mod,
    atoms_mod,
    burn_mod,
    policy_mod,
    control_mod,
    panel_mod,
    bootstrap_mod,
)

EPILOG = """\
start here:
  taos status                      where everything stands
  taos task list                   what exists
  taos start --agent codex --task AZ-7 --session "AZ-7 | short label"
  taos finish --agent codex --task AZ-7 --state review --reason "..." --session "..."
  taos panel on                    the dashboard, on when you want it
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taos",
        description="ThesisAnalysisOS: durable work state for a human and two agents.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--home", help="path to the OS clone (default: discovered)")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    for module in MODULES:
        module.register(subparsers)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
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
