"""Replay the visitor download from this repository's trusted release build."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zipfile import BadZipFile, ZipFile


RENDER = """
import io
import json
import sys

from taos_core.page import write

record = json.load(sys.stdin)
views = {}
for name, full in (("demo.txt", False), ("demo-transcript.txt", True)):
    output = io.StringIO()
    write(record, output, full=full, width=None if full else 80, color=False)
    views[name] = output.getvalue()
print(json.dumps(views))
"""


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def decisions(record):
    """Compare the checks and observations, leaving run-specific output in the transcript."""
    fields = ("command", "id", "answer", "measured", "expected")
    moments = [
        (moment["id"], [tuple(step.get(field) for field in fields)
                        for step in moment["steps"] if step["kind"] == "run"])
        for moment in record["moments"]
    ]
    return record["schema"], record["commands"], record["checked"], moments


def run(command, cwd, *, data=None):
    result = subprocess.run(command, cwd=cwd, input=data, capture_output=True,
                            encoding="utf-8", timeout=60)
    if result.returncode:
        raise ValueError(f"{command[0]} exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def verify(root):
    root = root.resolve()
    revision = read_json(root / "release.json")["revision"]
    source = read_json(root / "source/index.json")
    if (not re.fullmatch(r"[0-9a-f]{40}", revision)
            or source["revision"] != revision or source["provenance"] != "commit"):
        raise ValueError("release and source index must name the same Git revision")
    suffix = revision[:12]
    archive_path = root / "source" / f"thesisanalysisos-{suffix}.zip"
    with ZipFile(archive_path) as archive:
        if archive.comment != revision.encode("ascii"):
            raise ValueError("source ZIP belongs to a different Git revision")
    saved = read_json(root / "records/demo.json")
    # Use a normal unzip so the test also checks the executable bit a reader receives.
    with tempfile.TemporaryDirectory(prefix="taos visitor ") as directory:
        temp = Path(directory)
        run(["unzip", "-q", str(archive_path), "-d", str(temp)], temp)
        package = temp / f"ThesisAnalysisOS-{suffix}"
        if not os.access(package / "taos", os.X_OK):
            raise ValueError("the downloaded taos launcher is missing or lacks execute permission")
        welcome = package / "taos_core" / "welcome.py"
        if welcome.is_file():
            template = welcome.with_suffix(".html")
            if not template.is_file() or "__KEY__" not in template.read_text(encoding="utf-8"):
                raise ValueError("the downloaded setup page is missing its interactive template")
        replay = json.loads(run(["./taos", "demo", "--json"], package))
        if decisions(replay) != decisions(saved):
            raise ValueError("downloaded demo decisions or measurements differ from records/demo.json")
        views = json.loads(run([sys.executable, "-c", RENDER], package, data=json.dumps(saved)))
        for name, expected in views.items():
            actual = (root / "records" / name).read_text(encoding="utf-8-sig")
            if actual != expected:
                raise ValueError(f"the downloaded renderer and records/{name} disagree")
    return revision, saved["commands"], saved["checked"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="a trusted site built with site/build.py --release")
    args = parser.parse_args()
    try:
        revision, commands, checks = verify(args.directory)
    except (OSError, ValueError, KeyError, BadZipFile, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Visitor download check failed: {error}\n")
    print(f"{revision[:12]}: downloaded demo matched {commands} commands, {checks} checks and both text views")


if __name__ == "__main__":
    main()
