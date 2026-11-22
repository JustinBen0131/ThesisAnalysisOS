#!/usr/bin/env python3
"""Replay the unequal-group follow-up on fictional instrument readings in a temporary directory."""

import argparse
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path("examples/model_evaluation")
ORIGINAL = Path("evals/results/model_evaluation.json")
EXTRA_SCORES = (("B09", 60), ("B10", 61), ("B11", 63), ("B12", 65),
                ("B13", 72), ("B14", 79), ("B15", 59), ("B16", 56))
GROUPS = {"A": ("a",), "B": ("b",), "pooled": ("a", "b")}
# Known faults detected in A and B under each scheduled edit.
PREDICTIONS = {"augmented-baseline": (3, 9), "a-only": (2, 9), "b-only": (3, 10),
               "both": (2, 10), "restored": (3, 9)}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=("id", "reference_fault", "score"), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def recount(rows, cutoff):
    ids = {row["id"] for row in rows}
    if len(ids) != len(rows) or any(row["reference_fault"] not in {"0", "1"} for row in rows):
        raise ValueError("Expected distinct sample identifiers with binary reference labels.")
    faults = {row["id"] for row in rows if row["reference_fault"] == "1"}
    flagged = {row["id"] for row in rows if int(row["score"]) >= cutoff}
    counts = {"tp": len(faults & flagged), "fn": len(faults - flagged),
              "fp": len(flagged - faults), "tn": len(ids - (faults | flagged))}
    return counts, sorted(faults & flagged)


def observe(work, policy, case_id):
    samples = {group: read_rows(work / f"{group}.csv") for group in ("a", "b")}
    minimum = Fraction(policy["minimum_sensitivity"]["numerator"], policy["minimum_sensitivity"]["denominator"])
    results, rates = {}, {}
    for name, groups in GROUPS.items():
        rows = [row for group in groups for row in samples[group]]
        reference, detected = recount(rows, policy["flag_if_score_at_least"])
        run = subprocess.run([sys.executable, "-B", "model.py", name, *groups], cwd=work,
                             text=True, capture_output=True)
        if run.returncode not in (0, 1) or run.stderr:
            raise RuntimeError(f"Shipped classifier did not complete {case_id}/{name}: {run.stderr}")
        counts = json.loads(run.stdout)
        known = reference["tp"] + reference["fn"]
        rate = rates[name] = Fraction(reference["tp"], known)
        if counts != reference or run.returncode != int(rate < minimum):
            raise ValueError(f"Classifier counts or exit differ from the sample-ID recount for {case_id}/{name}.")
        results[name] = dict(counts=counts, reference_faults=known, detected_fault_ids=detected,
                             sensitivity=str(rate), checker_exit=run.returncode)
    return dict(id=case_id, groups=results, equal_group_mean=str((rates["A"] + rates["B"]) / 2),
                lowest_group_sensitivity=str(min(rates["A"], rates["B"])),
                input_sha256={group: digest((work / f"{group}.csv").read_bytes()) for group in samples})


def replay():
    record_bytes = (ROOT / ORIGINAL).read_bytes()
    record = json.loads(record_bytes)
    selected = [case for case in record["cases"] if case["id"] == "offsetting-score-corrections"]
    if len(selected) != 1:
        raise ValueError("Expected one recorded offsetting correction.")
    edits = selected[0]["edits"]
    edit_by_file = {e["file"]: e for e in edits}
    if len(edits) != 2 or set(edit_by_file) != {"a.csv", "b.csv"}:
        raise ValueError("Expected one recorded edit for each instrument.")
    inputs = {str(ORIGINAL): digest(record_bytes), str(Path(__file__).resolve().relative_to(ROOT)): digest(Path(__file__).read_bytes())}
    for name in ("a.csv", "b.csv", "model.py", "policy.json"):
        path = FIXTURE / name
        inputs[str(path)] = digest((ROOT / path).read_bytes())
        if inputs[str(path)] != record["sources"][str(path)]:
            raise ValueError(f"The fixture differs from the source of the recorded corrections: {path}")
    extra = [dict(id=name, reference_fault="1", score=str(score)) for name, score in EXTRA_SCORES]
    original = {group: read_rows(ROOT / FIXTURE / f"{group}.csv") for group in ("a", "b")}
    if len(original["a"]) != 8 or len(original["b"]) != 8:
        raise ValueError("Expected eight original specimen rows per instrument.")
    policy = json.loads((ROOT / FIXTURE / "policy.json").read_bytes())
    scenarios = [("augmented-baseline", ()), ("a-only", ("a.csv",)), ("b-only", ("b.csv",)),
                 ("both", ("a.csv", "b.csv")), ("restored", ())]
    cases = []
    with tempfile.TemporaryDirectory(prefix="taos-unequal-instruments-") as tmp:
        work = Path(tmp) / "work"
        work.mkdir()
        for name in ("model.py", "policy.json"):
            shutil.copyfile(ROOT / FIXTURE / name, work / name)
        augmented = {"a.csv": (ROOT / FIXTURE / "a.csv").read_bytes(),
                     "b.csv": csv_bytes(original["b"] + extra)}
        for case_id, changed in scenarios:
            for name, raw in augmented.items():
                (work / name).write_bytes(raw)
            for name in changed:
                rows = read_rows(work / name)
                change = edit_by_file[name]
                matches = [row for row in rows if row["id"] == change["id"]]
                if len(matches) != 1:
                    raise ValueError(f"Expected one sample {change['id']} in {name}.")
                matches[0]["score"] = str(change["score"])
                (work / name).write_bytes(csv_bytes(rows))
            case = observe(work, policy, case_id)
            case["score_edits"] = [edit_by_file[name] for name in changed]
            cases.append(case)

        process_log = (Path(tmp) / "executions.log").read_text(encoding="utf-8").splitlines()
    by_id = {case["id"]: case for case in cases}
    first, both, restored = (by_id[key] for key in ("augmented-baseline", "both", "restored"))
    expected = {case_id: dict(A=a, B=b) for case_id, (a, b) in PREDICTIONS.items()}
    controls = {
        "expected_detections_in_every_condition": all(
            case["groups"][name]["counts"]["tp"] == expected[case["id"]][name]
            for case in cases for name in ("A", "B")),
        "pooled_detects_12_of_16_before_and_after": all(
            case["groups"]["pooled"]["counts"]["tp"] == 12 and case["groups"]["pooled"]["reference_faults"] == 16
            for case in (first, both)),
        "equal_group_mean_changes_from_3_4_to_2_3": (first["equal_group_mean"], both["equal_group_mean"]) == ("3/4", "2/3"),
        "restored_bytes_and_counts_match_augmented_baseline": (
            first["input_sha256"] == restored["input_sha256"] and first["groups"] == restored["groups"]),
        "all_classifier_process_calls_observed": process_log == list(GROUPS) * len(cases),
    }
    return {
        "schema": "instrument-imbalance-replay/1", "question": "research-notes/instrument-imbalance.json",
        "method": "Append eight fictional known faults to instrument B. Run the shipped classifier on A, B and pooled "
                  "readings for the augmented baseline, each score correction alone, both corrections, and exact restoration. "
                  "Independently recount the four classification cells by sample ID and use exact fractions for sensitivities.",
        "scope": "A deterministic arithmetic demonstration on chosen fictional readings. The equal-group mean gives A and B "
                 "equal weight. Pooling weights each group by its count of known faults. The results do not estimate "
                 "population performance or how often these corrections occur.",
        "sources": inputs, "original_samples": original, "added_b_faults": extra, "policy": policy,
        "recorded_edits": edits, "expected_detected_faults": expected, "cases": cases, "controls": controls,
        "invocations": len(process_log), "passed": all(controls.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print full observations, predictions and source digests.")
    args = parser.parse_args()
    report = replay()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("Unequal fault counts in a fictional two-instrument comparison")
        print("Condition          A found   B found   Pooled found   Equal-group mean")
        for case in report["cases"]:
            counts = [f"{v['counts']['tp']}/{v['reference_faults']}" for v in case["groups"].values()]
            print(f"{case['id']:18} {counts[0]:9} {counts[1]:9} {counts[2]:14} {case['equal_group_mean']}")
        print("All controls passed." if report["passed"] else "A control failed.")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
