#!/usr/bin/env python3
"""Count three reproducible text reads from the freshly constructed pendulum demo."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
import measured

from taos_core import demo, usage

SCHEMA = "taos-session-footprint-v1"
LABEL = "Reading one demo session"
RECORD = ROOT / "evals/results/session_footprint.json"
STANDS_ON = ["evals/session_footprint.py", "evals/measured.py", "taos", "taos_core/*.py",
             "taos_core/templates/*.tmpl", "bootstrap/answers.example.json", "bootstrap/answers.schema.json",
             "AGENTS.md", "CLAUDE.md", "kernels/*.md", "kernels/KERNEL_INDEX.json", "atoms/promoted_atoms.json",
             "policies/*.md", "policies/ROUTING.yaml", ".claude/settings.json", ".codex/hooks.json", ".codex/config.toml",
             "hooks/*.py", "examples/measurement/*"]
DELIVERY = {
    "compact_status": "The enabled SessionStart hook sends compact status. The CLI adds a final newline.",
    "task_capsule": "On demand with taos capsule PEN-1. Starting a task also prints its capsule.",
    "agents_md": "The rendered instructions in the demo OS root. Automatic loading depends on the agent host.",
}


def surface(text, delivery):
    raw = text.encode("utf-8")
    return {"text": text, "bytes": len(raw), "lines": len(text.splitlines()),
            "sha256": hashlib.sha256(raw).hexdigest(), "delivery": delivery}


def normalized(text, root):
    # Bootstrap renders each command argument with shlex.quote, including when the temp path has spaces.
    for suffix in ("os/taos", "os"):
        text = text.replace(shlex.quote(str(root / suffix)), "<DEMO>/" + suffix)
    text = text.replace(str(root), "<DEMO>").replace(sys.executable, "<PYTHON>")
    return re.sub(r"^(TAOS Pendulum \| )\d{4}-\d{2}-\d{2}( \| constructed )\d{4}-\d{2}-\d{2}$",
                  r"\g<1>YYYY-MM-DD\g<2>YYYY-MM-DD", text, flags=re.MULTILINE)


def observe(root):
    # The example bootstrap normally probes for agent usage logs. Give this fixture empty adapter roots.
    with patch.object(usage, "CLAUDE_ROOT", root / "claude"), patch.object(usage, "CODEX_ROOT", root / "codex"):
        paths = demo.build(root)
    env = {"HOME": str(root), "PATH": os.defpath, "TAOS_HOME": str(paths.home), "PYTHONIOENCODING": "utf-8"}

    def cli(*args):
        output = subprocess.check_output([sys.executable, "-B", str(paths.launcher), "--home", str(paths.home), *args],
                                         cwd=paths.home, env=env, timeout=30)
        return output.decode("utf-8")

    text = {"compact_status": cli("status", "--compact"), "task_capsule": cli("capsule", "PEN-1"),
            "agents_md": (paths.home / "AGENTS.md").read_bytes().decode("utf-8")}
    return {name: surface(normalized(value, root), DELIVERY[name]) for name, value in text.items()}


def experiment():
    with tempfile.TemporaryDirectory(prefix="taos-footprint-") as tmp:
        surfaces = observe(Path(tmp).resolve())
    return {"schema": SCHEMA, "surfaces": surfaces, "measured_on": measured.stamp(STANDS_ON)}


def verify(data):
    if (data.get("schema") != SCHEMA or not isinstance(data.get("surfaces"), dict)
            or set(data["surfaces"]) != set(DELIVERY)):
        raise ValueError("expected the three demo reading surfaces")
    for name, delivery in DELIVERY.items():
        row = data["surfaces"][name]
        if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"]:
            raise ValueError(f"missing saved text for {name}")
        if row != surface(row["text"], delivery) or type(row["lines"]) != int or type(row["bytes"]) != int:
            raise ValueError(f"saved counts, digest or delivery disagree with {name}")
    stamp = data.get("measured_on", {})
    if not isinstance(stamp, dict) or stamp.get("patterns") != sorted(STANDS_ON):
        raise ValueError("source declaration differs from the session measurement")
    sources = stamp["files"]
    files = sources["files"]
    if not isinstance(files, dict) or not files or not all(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value)
                                                           for value in files.values()):
        raise ValueError("missing source fingerprints for session measurement")
    manifest = "\n".join(f"{path}\0{digest}" for path, digest in sorted(files.items()))
    if (type(sources["count"]) != int or sources["count"] != len(files)
            or sources["sha256"] != hashlib.sha256(manifest.encode("utf-8")).hexdigest()):
        raise ValueError("session source manifest differs from its aggregate")


def quote(data):
    verify(data)
    labels = {"compact_status": "compact status", "task_capsule": "PEN-1 capsule", "agents_md": "root AGENTS.md"}
    return ", ".join(f"{label} {data['surfaces'][key]['bytes']:,} bytes / {data['surfaces'][key]['lines']} lines"
                     for key, label in labels.items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="save the demo measurement")
    mode.add_argument("--output", type=Path, help="save the demo measurement to this path")
    mode.add_argument("--verify", action="store_true", help="compare a fresh demo with the saved text and sources")
    args = parser.parse_args()
    data = experiment()
    verify(data)
    if args.verify:
        if json.loads(RECORD.read_bytes()) != data:
            parser.exit(1, "The fresh measurement differs from the saved session footprint.\n")
        print(quote(data))
    else:
        text = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if args.write or args.output:
            (args.output or RECORD).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
