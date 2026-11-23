"""Replay one declared setting changing after its check passed, in a scratch home.

The stand-in project in examples/instrument_setting keeps one setting in
model/settings.json. A check that declares the model folder passes and the task
closes. The setting is then switched, and TAOS is asked what still stands, what
an agent picking the task up is shown, and what a second run of the check gives.
Every answer is the output of a real command. The readings are made up and no
model is called. This shows how a declared input is handled today. It is not a
record of the project the homepage story comes from.

Run python3 evals/replay_setting_change.py --verify from the checkout.
"""
import argparse
import contextlib
import hashlib
import io
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))

from taos_core import __version__ as taos_version, demo
from taos_core.cli import main as taos_main


DEFAULT_RECORD = Path("evals/results/followups/setting-change.json")
FIXTURE = Path("examples/instrument_setting")
SETTINGS = "model/settings.json"
CHECK_FILE = "model/check_response.py"
NOTES = "notes/lab_notes.txt"
TASK = "INS-1"
CHECK = "response"
FIRST, SECOND = "codex", "claude"
CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?")
# What the record is expected to answer for the check, in order.
EXPECTED = {"before": "holds", "control": "holds", "after": "stale", "rerun": "holds",
            "reason": "model changed: " + SETTINGS, "changed": SETTINGS}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def declared_sources():
    sources = [Path("bootstrap/answers.example.json")]
    sources.extend(sorted(Path("taos_core").glob("*.py")))
    sources.extend(sorted(p for p in FIXTURE.rglob("*") if p.is_file() and "__pycache__" not in p.parts))
    fingerprints = {p.as_posix(): digest(p.read_bytes()) for p in sources}
    fingerprints["evals/replay_setting_change.py"] = digest(Path(__file__).read_bytes())
    return fingerprints


def ask(paths, *argv):
    """Run one real TAOS command and return its exit code and what it printed."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = taos_main(["--home", str(paths.home)] + list(argv))
    return code, printed.getvalue()


def step(paths, name, argv, keep):
    """Keep the lines that carry the answer. Dates and times are replaced so the record repeats exactly."""
    code, text = ask(paths, *argv)
    lines = [CLOCK.sub("<time>", line.strip()) for line in text.splitlines() if line.strip()]
    return {"id": name, "command": "taos " + shlex.join(argv), "exit": code,
            "printed": [line for line in lines if any(word in line for word in keep)]}


def reading(work, name):
    done = subprocess.run([sys.executable, "-B", CHECK_FILE], cwd=str(work), capture_output=True, text=True)
    return {"id": name, "command": "python3 " + CHECK_FILE, "exit": done.returncode,
            "printed": [done.stdout.strip()]}


def trial():
    with tempfile.TemporaryDirectory(prefix="taos-setting-change-") as directory:
        tmp = Path(directory)
        work = tmp / "instrument"
        shutil.copytree(str(ROOT / FIXTURE), str(work), ignore=shutil.ignore_patterns("__pycache__", "README.md"))
        command = shlex.join([sys.executable, "-B", CHECK_FILE])
        paths = demo.scratch_home(tmp, workspace=work, project="Instrument model", prefix="INS",
                                  gates=[{"name": CHECK, "command": command}],
                                  tasks=[{"title": "Test the instrument model's response",
                                          "next_action": "run the response check"}])
        demo.configure(paths, basis={"domains": {"model": ["model/*"], "notes": ["notes/*"]}},
                       gates=[{"name": CHECK, "command": command, "depends_on": ["model"]}])
        settings = work / SETTINGS
        before = json.loads(settings.read_text(encoding="utf-8"))
        answer = ("check " + CHECK, "as recorded")
        steps = [
            reading(work, "reading-before"),
            step(paths, "first-pass", ("gate", "run", "--task", TASK, "--agent", FIRST), (CHECK,)),
            step(paths, "closed", ("task", "transition", TASK, "--to", "done", "--agent", FIRST,
                                   "--reason", "the response check passed"), (TASK,)),
            step(paths, "before", ("why", TASK), answer),
        ]
        notes = work / NOTES
        notes.write_text(notes.read_text(encoding="utf-8") + "One more line of notes.\n", encoding="utf-8")
        steps.append({"id": "notes-edited", "file": NOTES})
        steps.append(step(paths, "control", ("why", TASK), answer))
        after = dict(before, correction="off")
        settings.write_text(json.dumps(after) + "\n", encoding="utf-8")
        steps.append({"id": "setting-switched", "file": SETTINGS, "before": before, "after": after})
        steps.append(step(paths, "after", ("why", TASK), answer + ("next:",)))
        code, text = ask(paths, "why", TASK, "--json")
        told = json.loads(text)
        part = next(row for row in told["parts"] if row["kind"] == "check" and row["name"] == CHECK)
        standing = {"task": told["task"], "state": told["state"], "check": part, "next": told["next"]}
        steps.append(step(paths, "pickup", ("capsule", TASK), ("check " + CHECK,)))
        steps.append(step(paths, "status", ("status",), ("no longer stands",)))
        steps.append(reading(work, "reading-after"))
        steps.append(step(paths, "second-pass", ("gate", "run", "--task", TASK, "--agent", SECOND), (CHECK,)))
        steps.append(step(paths, "rerun", ("why", TASK), answer))

    def state_at(name):
        row = next(item for item in steps if item["id"] == name)
        return next(line for line in row["printed"] if "check " + CHECK in line).split()[0]

    def printed(name):
        return next(item for item in steps if item["id"] == name)["printed"][0]

    handoff = {
        "task": TASK, "check": CHECK,
        "before": state_at("before"), "control": state_at("control"), "after": part["state"], "rerun": state_at("rerun"),
        "reason": part["reason"], "changed": part["reason"].rsplit(": ", 1)[-1],
        "next": told["next"][0] if told["next"] else "",
        "readings": {"before": printed("reading-before"), "after": printed("reading-after")},
    }
    return {
        "schema": "setting-change-replay/1",
        "taos_version": taos_version,
        "sources": declared_sources(),
        "scope": ("One local scratch history of a stand-in project with made-up readings and supplied agent "
                  "labels. No model calls. Not a record of the project in the homepage story."),
        "steps": steps,
        "standing": standing,
        "handoff": handoff,
        "expectation_mismatches": [{"field": key, "expected": value, "observed": handoff[key]}
                                   for key, value in EXPECTED.items() if handoff[key] != value],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", nargs="?", const=DEFAULT_RECORD, type=Path,
                        help="reproduce and compare with the retained raw record")
    args = parser.parse_args()
    observed = trial()
    if args.verify is None:
        # Always retain discrepancies when collecting a new record.
        print(json.dumps(observed, sort_keys=True, indent=2))
    elif observed != json.loads(args.verify.read_text(encoding="utf-8")):
        print("The setting-change replay differs from the retained record.", file=sys.stderr)
        print(json.dumps(observed, sort_keys=True, indent=2))
        return 1
    else:
        print(f'{len(observed["steps"])} setting-change steps match the retained record.')
    return int(bool(observed["expectation_mismatches"]))


if __name__ == "__main__":
    raise SystemExit(main())
