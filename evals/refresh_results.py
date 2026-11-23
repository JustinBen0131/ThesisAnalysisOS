#!/usr/bin/env python3
"""Check the saved evidence, or refresh the items whose declared inputs changed."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "site"))
from plot_pendulum import figure_issue
RESULTS = Path("evals/results")
FIGURE = Path("site/assets/pendulum-sensitivity.png")
CLAIMS = Path("docs/CLAIMS.md")
README = Path("README.md")
OPENER = Path("docs/opener.svg")
MEASUREMENT = RESULTS / "measurement_audit.json"
MODEL = RESULTS / "model_evaluation.json"
REUSE = RESULTS / "reuse_frontier.json"
SESSION = RESULTS / "session_footprint.json"


@dataclass
class Item:
    path: Path
    check: Callable[[Path], Optional[str]]
    write: Callable[[Path], None]
    needs: tuple = ()


def record(path):
    data = json.loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measured_reason(path, study, verify=None):
    import measured
    data = record(path)
    stamp = data.get("measured_on")
    if not isinstance(stamp, dict) or stamp.get("patterns") != sorted(study.STANDS_ON):
        return "source declaration differs from the generator"
    verdict = measured.standing(data)
    if verdict["state"] != "holds":
        return verdict["reason"]
    if verify:
        verify(data)
    return None


def source_reason(path, current):
    saved = record(path).get("sources")
    if not isinstance(saved, dict) or not saved:
        return "missing source fingerprints"
    expected = current(saved)
    for name in sorted(saved.keys() | expected.keys()):
        if name not in saved:
            return f"new source {name}"
        if name not in expected:
            return f"source no longer declared: {name}"
        if expected[name] != saved[name]:
            return f"source changed: {name}"
    return None


def fingerprint(paths):
    return {path.as_posix(): digest(path) for path in sorted(paths)}


def model_sources(saved):
    # The study seals the Python modules actually loaded during its cases.
    # Other engine modules can exist without participating in this study.
    from taos_core import cli  # loaded by demo.scratch_home in the model study
    paths = {Path(name) for name in saved if Path(name).parent == Path("taos_core")
             and Path(name).suffix == ".py"}
    paths.update(Path(module.__file__).resolve().relative_to(ROOT) for name, module in sys.modules.items()
                 if name.startswith("taos_core") and getattr(module, "__file__", None))
    paths.update(Path(name) for name in (".codex/hooks.json", "bootstrap/answers.example.json",
                                         "bootstrap/answers.schema.json", "evals/model_evaluation.py"))
    paths.update(Path("taos_core/templates").glob("*.tmpl"))
    paths.update(p for p in Path("examples/model_evaluation").iterdir() if p.is_file())
    return fingerprint(paths)


def replay_sources(_saved):
    from replay_instrument_imbalance import FIXTURE, ORIGINAL
    paths = [ORIGINAL, Path("evals/replay_instrument_imbalance.py")]
    paths.extend(FIXTURE / name for name in ("a.csv", "b.csv", "model.py", "policy.json"))
    return fingerprint(paths)


def review_transfer_sources(saved):
    # The review transfer record seals its own script, the launcher, two engine modules and the fixture it replays.
    return fingerprint(Path(name) for name in saved)


def instrument_paths_reason(path):
    # The correction-paths record names the fixture bytes it replayed; the full replay is `--verify`, run in CI.
    from replay_instrument_paths import FILES
    from model_evaluation import EXAMPLE
    saved = record(path).get("source_sha256")
    if not isinstance(saved, dict) or sorted(saved) != sorted(FILES):
        return "fixture declaration differs from the generator"
    for name in FILES:
        if digest(EXAMPLE / name) != saved[name]:
            return f"source changed: {EXAMPLE.name}/{name}"
    return None


def figure_reason(path):
    return figure_issue(path, MEASUREMENT.read_bytes(), Path("site/plot_pendulum.py"))


def timing_text():
    from claims import UPKEEP_LABEL, ISOLATION_LABEL, timing_claims
    rows = timing_claims(record(REUSE))
    if not rows:
        raise ValueError(f"{REUSE} contains no timing claims")
    # Older checkouts used these labels. Rename the row on its first refresh.
    aliases = {
        UPKEEP_LABEL: "Asking costs time that grows with the tree",
        ISOLATION_LABEL: (
            "Isolating a check costs milliseconds. Measured in pairs that differ only in the isolation, order alternating"),
    }
    return replace_rows(CLAIMS.read_bytes().decode("utf-8"), rows, aliases)


def replace_rows(text, rows, aliases):
    lines = text.splitlines(keepends=True)
    for label, phrase in rows.items():
        prefixes = tuple("| " + name + " |" for name in (label, aliases.get(label, label)))
        matches = [i for i, line in enumerate(lines) if line.startswith(prefixes)]
        if len(matches) != 1:
            raise ValueError(f"expected one timing row for {label!r} in {CLAIMS}")
        i = matches[0]
        cells = lines[i].split("|")
        if len(cells) != 6 or not cells[4].strip().startswith("measured"):
            raise ValueError(f"unexpected timing row in {CLAIMS}: {label}")
        cells[1:3] = [" " + label + " ", " " + phrase + " "]
        lines[i] = "|".join(cells)
    return "".join(lines)


def suite_count_row(text, label):
    from claims import collected_tests
    pattern = r"^(\| " + re.escape(label) + r" \| )\d+(?= tests\b)"
    updated, matches = re.subn(pattern, lambda match: match[1] + str(collected_tests()), text, flags=re.MULTILINE)
    if matches != 1:
        raise ValueError(f"Expected one test-count row named {label!r}")
    return updated


def readme_rows():
    return suite_count_row(README.read_text(encoding="utf-8"), "Cases in the self-test suite")


def measurement_rows():
    from session_footprint import LABEL, quote
    timed = replace_rows(timing_text(), {LABEL: quote(record(SESSION))}, {})
    return suite_count_row(timed, "Cases collected by the self-test suite")


def different_text(path, text, why):
    return None if path.read_bytes() == text().encode("utf-8") else why


def writer(script, *args, output_attribute=None, stdout=False):
    """Run the shipped CLI in a fresh interpreter, directing its output to a candidate."""
    def write(candidate):
        command = [sys.executable, "-B", script, *args]
        if output_attribute:
            # These CLIs expose --write with one fixed module-level destination.
            # Redirect only that path, so a failed prediction cannot overwrite a good run.
            command = [sys.executable, "-B", "-c", """
import importlib, sys
from pathlib import Path
script, attribute, output = sys.argv[1:4]
sys.path.insert(0, str(Path(script).parent))
module = importlib.import_module(Path(script).stem)
setattr(module, attribute, Path(output).resolve())
sys.argv = [script] + sys.argv[4:]
raise SystemExit(module.main())
""", script, output_attribute, str(candidate), *args]
        elif not stdout:
            command += ["--output", str(candidate)]
        if stdout:
            with candidate.open("wb") as stream:
                subprocess.run(command, stdout=stream, check=True)
        else:
            subprocess.run(command, check=True)
    return write


def items():
    import at_revision
    import handoff_audit
    import measurement_audit
    import mutations
    import reuse_frontier
    import session_footprint
    import transit_workflow
    from docs.opener import picture

    def sources(current):
        return lambda path: source_reason(path, current)

    def recorded(loader):
        def check(path):
            loader(path)
            return None
        return check

    return [
        Item(RESULTS / "at_revision.json", lambda p: measured_reason(p, at_revision),
             writer("evals/at_revision.py", "--write", output_attribute="RECORD")),
        Item(RESULTS / "mutations.json", lambda p: measured_reason(p, mutations),
             writer("evals/mutations.py", "--write", output_attribute="RECORD")),
        Item(REUSE, lambda p: measured_reason(p, reuse_frontier, reuse_frontier.verify_timing),
             writer("evals/reuse_frontier.py", "--write", output_attribute="RECORD")),
        Item(SESSION, lambda p: measured_reason(p, session_footprint, session_footprint.verify),
             writer("evals/session_footprint.py")),
        Item(Path("examples/transit/workflow.json"), recorded(transit_workflow.load_record),
             writer("evals/transit_workflow.py", stdout=True)),
        Item(Path("examples/transit/adaptation/workflow.json"), recorded(transit_workflow.load_adaptation_record),
             writer("evals/transit_workflow.py", "--adaptation", stdout=True)),
        Item(MEASUREMENT, sources(lambda _: measurement_audit.sources()),
             writer("evals/measurement_audit.py", stdout=True)),
        Item(RESULTS / "handoff_audit.json", sources(lambda _: handoff_audit.declared_sources()),
             writer("evals/handoff_audit.py", stdout=True)),
        Item(MODEL, sources(model_sources),
             writer("evals/model_evaluation.py", "--write", output_attribute="RECORD")),
        Item(RESULTS / "followups/instrument-imbalance.json", sources(replay_sources),
             writer("evals/replay_instrument_imbalance.py", "--json", stdout=True), (MODEL,)),
        Item(RESULTS / "followups/review-transfer.json", sources(review_transfer_sources),
             writer("evals/review_transfer.py")),
        Item(RESULTS / "followups/instrument-paths.json", instrument_paths_reason,
             writer("evals/replay_instrument_paths.py", "--write", output_attribute="RECORD")),
        Item(FIGURE, figure_reason, writer("site/plot_pendulum.py"), (MEASUREMENT,)),
        Item(OPENER, lambda p: different_text(p, picture, "saved picture differs from the CLI opener"),
             lambda p: p.write_text(picture(), encoding="utf-8")),
        Item(CLAIMS, lambda p: different_text(p, measurement_rows, "quoted measurements differ from the saved records"),
             lambda p: p.write_text(measurement_rows(), encoding="utf-8"), (REUSE, SESSION)),
        Item(README, lambda p: different_text(p, readme_rows, "self-test count differs from discovery"),
             lambda p: p.write_text(readme_rows(), encoding="utf-8")),
    ]


def reason(item, path):
    if not path.is_file():
        return "missing saved file"
    try:
        return item.check(path)
    except (ArithmeticError, LookupError, OSError, TypeError, ValueError) as error:
        return f"cannot verify: {error}"


def refresh(entries, write):
    pending = set()
    for item in entries:
        waiting = [str(path) for path in item.needs if path in pending]
        if waiting:
            print(f"RECHECK {item.path} after {', '.join(waiting)}")
            pending.add(item.path)
            continue
        issue = reason(item, item.path)
        if not issue:
            print(f"CURRENT {item.path}")
            continue
        print(f"STALE   {item.path} ({issue})", flush=True)
        if not write:
            pending.add(item.path)
            continue
        try:
            before = item.path.read_bytes() if item.path.exists() else None
            item.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=item.path.parent) as tmp:
                candidate = Path(tmp) / item.path.name
                item.write(candidate)
                issue = reason(item, candidate)
                if issue:
                    raise ValueError(f"generated file did not verify: {issue}")
                if (item.path.read_bytes() if item.path.exists() else None) != before:
                    raise ValueError("saved file changed during refresh")
                candidate.replace(item.path)
        except (KeyError, OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
            detail = f"generator exited {error.returncode}" if isinstance(error, subprocess.CalledProcessError) else str(error)
            print(f"FAILED  {item.path} ({detail})", file=sys.stderr)
            return 2
        print(f"UPDATED {item.path}")
    return 1 if pending else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report stale items without running studies or writing files")
    mode.add_argument("--write", action="store_true", help="regenerate stale items in dependency order")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(ROOT))
    try:
        return refresh(items(), args.write)
    except (ImportError, OSError, ValueError) as error:
        print(f"Could not check saved evidence: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
