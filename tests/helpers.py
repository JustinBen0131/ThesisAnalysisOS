"""Test helpers: a throwaway OS home constructed from the example answers."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from taos_core import bootstrap as bootstrap_mod  # noqa: E402
from taos_core.paths import Paths  # noqa: E402

COPY = (
    "taos",
    "taos_core",
    "hooks",
    "kernels",
    "atoms",
    "policies",
    "bootstrap",
    "AGENTS.md",
    "CLAUDE.md",
    ".claude",
    ".codex",
    ".agents",
)


def _ignore(directory: str, names: Any) -> set:
    return {n for n in names if n in (".taos", "__pycache__", ".git", "tests")}


def make_home() -> Tuple[Path, Paths]:
    """Copy the repo into a temp dir. Caller removes it."""
    tmp = Path(tempfile.mkdtemp(prefix="taos-test-"))
    home = tmp / "home"
    home.mkdir()
    for name in COPY:
        source = REPO / name
        target = home / name
        if source.is_dir():
            shutil.copytree(str(source), str(target), ignore=_ignore)
        elif source.is_file():
            shutil.copy2(str(source), str(target))
    os.chmod(str(home / "taos"), 0o755)
    return tmp, Paths(home)


def example_answers(tmp: Path, **overrides: Any) -> Dict[str, Any]:
    answers = json.loads((REPO / "bootstrap" / "answers.example.json").read_text(encoding="utf-8"))
    ws = tmp / "ws"
    ws_claude = tmp / "ws-claude"
    ws.mkdir(exist_ok=True)
    ws_claude.mkdir(exist_ok=True)
    (ws / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")
    answers["workspaces"] = [
        {"name": "ws", "path": str(ws), "primary": True, "agent": "any"},
        {"name": "ws-claude", "path": str(ws_claude), "primary": False, "agent": "claude"},
    ]
    answers["gates"] = [{"name": "ok", "command": "true"}]
    answers["open_browser"] = False
    answers.update(overrides)
    return answers


def construct_example(tmp: Path, paths: Paths, **overrides: Any) -> Dict[str, Any]:
    answers = example_answers(tmp, **overrides)
    (paths.bootstrap_dir / "answers.json").write_text(json.dumps(answers, indent=2), encoding="utf-8")
    return bootstrap_mod.construct(paths, answers, actor="system")


def cleanup(tmp: Path) -> None:
    shutil.rmtree(str(tmp), ignore_errors=True)
