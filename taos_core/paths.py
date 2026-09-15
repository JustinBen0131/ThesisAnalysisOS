"""Where everything lives. One object, resolved once per command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .util import TaosError

STATE_DIRNAME = ".taos"


class Paths(object):
    """Absolute locations for the OS home and its runtime state."""

    def __init__(self, home: Path):
        home = Path(home).expanduser().resolve()
        self.home = home
        self.taos_core = home / "taos_core"
        self.templates_dir = self.taos_core / "templates"
        self.panel_assets = self.taos_core / "panel_assets"
        self.launcher = home / "taos"
        self.hooks_dir = home / "hooks"
        self.policies_dir = home / "policies"
        self.kernels_dir = home / "kernels"
        self.kernel_index = self.kernels_dir / "KERNEL_INDEX.json"
        self.atoms_file = home / "atoms" / "promoted_atoms.json"
        self.bootstrap_dir = home / "bootstrap"
        self.agents_md = home / "AGENTS.md"
        self.claude_md = home / "CLAUDE.md"
        self.tests_dir = home / "tests"

        state = home / STATE_DIRNAME
        self.state = state
        self.config_file = state / "config.json"
        self.tasks_file = state / "tasks.json"
        self.allocator_file = state / "allocator.json"
        self.events_file = state / "events.jsonl"
        self.claims_file = state / "claims.json"
        self.decisions_file = state / "decisions.json"
        self.proposals_dir = state / "proposals"
        self.handoffs_dir = state / "handoffs"
        self.telemetry_dir = state / "telemetry"
        self.labels_file = self.telemetry_dir / "labels.jsonl"
        self.projections_dir = state / "projections"
        self.briefs_dir = state / "briefs"
        self.cold_dir = state / "cold"
        self.scratch_dir = state / "scratch"
        self.panel_pid = state / "panel.pid"
        self.panel_token = state / "panel.token"
        self.panel_log = state / "panel.log"
        self.lock_file = state / ".lock"

    # -- discovery ---------------------------------------------------------

    @classmethod
    def discover(cls, start: Optional[Path] = None) -> "Paths":
        env_home = os.environ.get("TAOS_HOME")
        if env_home:
            candidate = Path(env_home).expanduser()
            if cls._is_home(candidate):
                return cls(candidate)
            raise TaosError("TAOS_HOME is set but {0} is not a TAOS home".format(candidate))

        here = Path(start).expanduser().resolve() if start else Path.cwd().resolve()
        for directory in [here] + list(here.parents):
            if cls._is_home(directory):
                return cls(directory)
            link = directory / ".taos-link.json"
            if link.is_file():
                linked = cls._read_link(link)
                if linked is not None and cls._is_home(linked):
                    return cls(linked)
        raise TaosError(
            "no TAOS home found from {0}. Run commands inside the OS clone, "
            "or set TAOS_HOME to it.".format(here)
        )

    @staticmethod
    def _is_home(directory: Path) -> bool:
        try:
            return (directory / "taos_core").is_dir() and (directory / "taos").is_file()
        except OSError:
            return False

    @staticmethod
    def _read_link(link: Path) -> Optional[Path]:
        import json

        try:
            data = json.loads(link.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        home = data.get("taos_home") if isinstance(data, dict) else None
        return Path(home).expanduser() if isinstance(home, str) else None

    # -- state -------------------------------------------------------------

    def ensure_state(self) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.state, 0o700)
        except OSError:
            pass
        for directory in (
            self.proposals_dir,
            self.handoffs_dir,
            self.telemetry_dir,
            self.projections_dir,
            self.briefs_dir,
            self.cold_dir,
            self.scratch_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def constructed(self) -> bool:
        return self.config_file.is_file()

    def relative(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.home))
        except (ValueError, OSError):
            return str(path)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "Paths(home={0!r})".format(str(self.home))
