"""Run one chronological pendulum handoff using three tasks in a scratch home."""

import argparse
import csv
import hashlib
import io
import json
import shlex
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))

from taos_core import demo, gates, lifecycle, tasks


DEFAULT_RECORD = Path("evals/results/handoff_audit.json")
# Predictions apply to the requesting task. Receipt aliases are step IDs.
# ID, task, edit, before, execution, exit, after, original execution receipt.
DESIGN = (
    ("baseline", "PEN-1", "none", "unknown", "execute", 0, "holds", "baseline"),
    ("style-only", "PEN-2", "style", "holds", "reuse", 0, "holds", "baseline"),
    ("measurement-fails", "PEN-2", "material", "stale", "execute", 1, "fails", "measurement-fails"),
    ("new-task-sees-failure", "PEN-3", "none", "fails", "execute", 1, "fails", "new-task-sees-failure"),
    ("restore-exact-bytes", "PEN-2", "restore", "holds", "reuse", 0, "holds", "baseline"),
    ("same-values-new-bytes", "PEN-2", "respell", "stale", "execute", 0, "holds", "same-values-new-bytes"),
    ("share-respelled-pass", "PEN-3", "none", "holds", "reuse", 0, "holds", "same-values-new-bytes"),
)
ACTORS = {"PEN-1": "codex", "PEN-2": "claude", "PEN-3": "codex"}
SESSIONS = {"PEN-1": "PEN-1 | Measure", "PEN-2": "PEN-2 | Plot", "PEN-3": "PEN-3 | Review"}
CSV_PATH = "data/swings.csv"
STYLE_PATH = "figures/style.txt"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def declared_sources():
    sources = [Path("bootstrap/answers.example.json")]
    sources.extend(sorted(Path("taos_core").glob("*.py")))
    sources.extend(sorted(p for p in Path("examples/measurement").rglob("*")
                          if p.is_file() and "__pycache__" not in p.parts))
    fingerprints = {p.as_posix(): digest(p.read_bytes()) for p in sources}
    fingerprints["evals/handoff_audit.py"] = digest(Path(__file__).read_bytes())
    return fingerprints


def numeric_rows(raw):
    records = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    return [(Decimal(r["length_m"]), Decimal(r["period_s"])) for r in records]


def replace_last_period(original, replacement):
    old_row = b"1.20,2.19"
    if original.count(old_row) != 1:
        raise ValueError("Expected one original reading of 2.19 s at 1.20 m")
    return original.replace(old_row, b"1.20," + replacement)


def read_view(paths, task, receipts):
    result, = gates.standing(paths, task)
    origin = (result.get("result") or {}).get("receipt")
    reason = result["reason"]
    if result.get("ran_at"):
        reason = reason.replace(result["ran_at"], "<recorded time>")
    return {"state": result["state"], "reason": reason, "pass_origin": receipts.get(origin)}


def flags(row, predicted):
    return {key: {"expected": expected, "observed": row[key]}
            for key, expected in predicted.items() if row[key] != expected}


def trial():
    observations = []
    discrepancies = []
    receipts = {}
    tails = {}
    with tempfile.TemporaryDirectory(prefix="taos-handoff-audit-") as directory:
        scratch = Path(directory)
        paths = demo.build(scratch)
        work = scratch / "pendulum"
        demo.configure(paths, gates=[{"name": "fit", "depends_on": ["analysis"],
                                     "command": shlex.quote(sys.executable) + " -B analysis/check.py"}])
        active = []
        data, style = work / CSV_PATH, work / STYLE_PATH
        original = data.read_bytes()
        original_rows = numeric_rows(original)
        for number, (step, task, edit, before, action, gate_exit, after, origin) in enumerate(DESIGN, 1):
            actor = ACTORS[task]
            joined = task not in active
            if joined:
                if task == "PEN-3":
                    new_task = tasks.TaskStore(paths).create(
                        title="Review the measurements after the failed fit", actor=actor)
                    if new_task["id"] != task:
                        raise ValueError("Unexpected task ID from scratch setup")
                lifecycle.start(paths, agent=actor, task_id=task, session_label=SESSIONS[task])
                active.append(task)
            if edit == "style":
                style.write_bytes(style.read_bytes() + b"\n# change presentation only\n")
            elif edit == "material":
                data.write_bytes(replace_last_period(original, b"2.2995"))
            elif edit == "restore":
                data.write_bytes(original)
            elif edit == "respell":
                data.write_bytes(replace_last_period(original, b"2.190"))

            prior = {current: read_view(paths, current, receipts) for current in active}
            record = gates.run(paths, task_id=task, agent=actor, force=False)
            fit, = record["results"]
            mode = "reuse" if fit["name"] in record["reused"] else "execute"
            if mode == "execute":
                receipts[record["path"]] = step
                tails[step] = fit["tail"]
                carried = step
            else:
                carried = receipts.get(fit.get("receipt"))
            subsequent = {current: read_view(paths, current, receipts) for current in active}
            data_bytes = data.read_bytes()
            row = {
                "sequence": number, "id": step, "task": task, "actor_label": actor,
                "task_started": joined, "edit": edit, "before": prior[task]["state"],
                "execution": mode, "exit": fit["exit"], "after": subsequent[task]["state"],
                "execution_origin": carried, "output_from_origin": tails.get(carried),
                "views_before": prior, "views_after": subsequent, "reused_gates": record["reused"],
                "data_sha256": digest(data_bytes), "style_sha256": digest(style.read_bytes()),
                "basis_sha256": fit["basis"], "csv_exact_original": data_bytes == original,
                "csv_same_numbers": numeric_rows(data_bytes) == original_rows,
                "csv_text": data_bytes.decode("utf-8"),
            }
            predicted = {"before": before, "execution": action, "exit": gate_exit, "after": after,
                         "execution_origin": origin}
            deviations = flags(row, predicted)
            if deviations:
                discrepancies.append({"id": step, "fields": deviations})
            row["prediction"] = predicted
            observations.append(row)
    return {
        "schema": "pendulum-handoff-audit/1",
        "sources": declared_sources(),
        "scope": "One local scratch history with three task IDs and supplied actor labels. No model calls.",
        "observations": observations,
        "expectation_mismatches": discrepancies,
        "counts": {
            "gate_requests": len(observations),
            "executions": sum(row["execution"] == "execute" for row in observations),
            "reused": sum(row["execution"] == "reuse" for row in observations),
            "exit_1": sum(row["exit"] == 1 for row in observations),
        },
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
        print("Handoff audit differs from the retained record.", file=sys.stderr)
        print(json.dumps(observed, sort_keys=True, indent=2))
        return 1
    else:
        print(f'{len(observed["observations"])} handoff steps match the retained record.')
    return int(bool(observed["expectation_mismatches"]))


if __name__ == "__main__":
    raise SystemExit(main())
