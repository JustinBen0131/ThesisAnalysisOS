"""Recalculate the fictional instrument audit from its CSVs, policy and declared edits.

Usage: python3 evals/review_model_evaluation.py [--self-test]
Reads the saved observation record only. No TAOS commands or model code run.
"""

import argparse
import csv
import json
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = {"A": "a.csv", "B": "b.csv"}
CHECKS = ("A", "B", "pooled")
CELLS = ("tp", "fn", "fp", "tn")
CASES = {"figure-caption", "correct-a-score", "offsetting-score-corrections", "shared-threshold"}


def require(got, expected, field):
    if got != expected:
        raise ValueError(f"{field}: expected {expected!r}, found {got!r}")


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def classify(rows, threshold):
    """Count intersections of reference-positive IDs and independently flagged IDs."""
    all_ids = {row["id"] for row in rows}
    positive = {row["id"] for row in rows if row["reference_fault"] == "1"}
    flagged = {row["id"] for row in rows if int(row["score"]) >= threshold}
    return dict(zip(CELLS, (len(positive & flagged), len(positive - flagged),
                            len(flagged - positive), len(all_ids - (positive | flagged)))))


def counts(rows, threshold):
    result = {group: classify(rows[group], threshold) for group in FILES}
    combined = classify(rows["A"] + rows["B"], threshold)
    totals = {cell: result["A"][cell] + result["B"][cell] for cell in CELLS}
    require(combined, totals, "pooled cells equal A + B")
    return dict(result, pooled=combined)


def sensitivity(cells):
    return Fraction(cells["tp"], cells["tp"] + cells["fn"])


def changed_rows(baseline, baseline_cutoff, edits):
    rows = deepcopy(baseline)
    cutoff = baseline_cutoff
    for edit in edits:
        name = edit["file"]
        if name in FILES.values():
            group = next(g for g, filename in FILES.items() if filename == name)
            matches = [row for row in rows[group] if row["id"] == edit["id"]]
            require(len(matches), 1, f"{name} contains edited ID {edit['id']}")
            matches[0]["score"] = str(edit["score"])
        elif name == "policy.json":
            cutoff = edit["threshold"]
        elif name != "caption.txt":
            raise ValueError(f"unrecognized edit file: {name}")
    return rows, cutoff


def verify(fixture, record):
    design_path = fixture / "predictions.json"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    policy = json.loads((fixture / "policy.json").read_text(encoding="utf-8"))
    minimum = policy["minimum_sensitivity"]
    minimum = Fraction(minimum["numerator"], minimum["denominator"])
    cutoff = policy["flag_if_score_at_least"]
    baseline = {}
    for group, filename in FILES.items():
        with (fixture / filename).open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        expected_ids = {f"{group}{i:02}" for i in range(1, 9)}
        require({row["id"] for row in rows}, expected_ids, f"{group} specimen identities")
        require(len(rows), len(expected_ids), f"{group} specimen count")
        require({row["reference_fault"] for row in rows}, {"0", "1"}, f"{group} binary reference labels")
        baseline[group] = rows

    require(record["design_sha256"], file_hash(design_path), "prediction design fingerprint")
    for name in ("a.csv", "b.csv", "policy.json", "predictions.json"):
        require(record["sources"]["examples/model_evaluation/" + name], file_hash(fixture / name), name)
    require(record["cell_order"], list(CELLS), "observed cell order")
    require(design["cell_order"], list(CELLS), "predicted cell order")
    require(design["checks"], list(CHECKS), "prediction order")
    base_counts = counts(baseline, cutoff)
    baseline_vectors = {name: list(cells.values()) for name, cells in base_counts.items()}
    require(record["baseline_counts"], baseline_vectors, "measured baseline")
    require(design["baseline_counts"], baseline_vectors, "predicted baseline")
    predictions = {item["id"]: item for item in design["cases"]}
    observations = {item["id"]: item for item in record["cases"]}
    for label, items, original in (("predictions", predictions, design), ("observations", observations, record)):
        require(set(items), CASES, f"{label} case identities")
        require(len(original["cases"]), len(items), f"unique {label} IDs")

    executions = failures = 0
    for name, planned in predictions.items():
        case = observations[name]
        require(case["edits"], planned["edits"], f"{name} recorded edits")
        rows, threshold = changed_rows(baseline, cutoff, planned["edits"])
        require(case["threshold"], threshold, f"{name} cutoff")
        require(case["samples"], {g.lower(): rows[g] for g in FILES}, f"{name} raw observations")
        edits = {edit["file"] for edit in planned["edits"]}
        before, after = case["before_sha256"], case["after_sha256"]
        require(set(before), {*FILES.values(), "caption.txt", "policy.json"}, f"{name} baseline files")
        require(set(after), set(before), f"{name} final files")
        for filename in (*FILES.values(), "policy.json"):
            require(before[filename], file_hash(fixture / filename), f"{name} baseline {filename}")
        require({f for f in before if before[f] != after[f]}, edits, f"{name} changed files")

        matrix = counts(rows, threshold)
        require(case["counts"], matrix, f"{name} observed confusion counts")
        require(case["independent_counts"], matrix, f"{name} recorded comparator")
        require(planned["counts"], {g: list(matrix[g].values()) for g in CHECKS}, f"{name} predicted counts")
        if name == "shared-threshold":
            require(threshold, 75, "equality-control threshold")
            ties = [r for r in rows["A"] if int(r["score"]) == threshold]
            require([(r["id"], r["reference_fault"]) for r in ties], [("A05", "0")], "cutoff tie")
            require(matrix["A"]["fp"] - classify(rows["A"], threshold + 1)["fp"], 1,
                    "the score equal to 75 counts as a false positive")

        # The A and B checks read their own CSV and the policy. The pooled check reads both.
        affected = {g for g, filename in FILES.items() if {filename, "policy.json"} & edits}
        if affected:
            affected.add("pooled")
        rerun = [g for g in CHECKS if g in affected]
        reuse = [g for g in CHECKS if g not in affected]
        fail = [g for g in CHECKS if sensitivity(matrix[g]) < minimum]
        directions = {}
        for g in CHECKS:
            delta = sensitivity(matrix[g]) - sensitivity(base_counts[g])
            directions[g] = "up" if delta > 0 else "down" if delta < 0 else "same"
        require(case["sensitivity_direction"], directions, f"{name} direction")
        require(planned["sensitivity_direction"], [directions[g] for g in CHECKS], f"{name} predicted direction")
        require(case["old_receipts"], {g: "stale" if g in affected else "holds" for g in CHECKS}, f"{name} old receipts")
        require(case["result_after_consultation"], {g: "fails" if g in fail else "holds" for g in CHECKS},
                f"{name} final verdicts")
        for label, got, expected in (("execution", case["executed"], rerun), ("reuse", case["reused"], reuse),
                                     ("predicted stale", planned["old_stale"], rerun), ("predicted executions", planned["execute"], rerun),
                                     ("predicted failures", planned["fail"], fail)):
            require(sorted(got), sorted(expected), f"{name} {label} identities")
        executions += len(rerun)
        failures += len(fail)
    requests = len(observations) * len(CHECKS)
    return (f"{len(observations)} cases, {requests} result requests, {executions} recorded executions, "
            f"{requests - executions} reuses, {failures} failed check results")


def rejection_checks(fixture, record):
    for error in ("metric cell", "A/B invalidation", "raw observation"):
        corrupted = deepcopy(record)
        case = next(c for c in corrupted["cases"] if c["id"] == "correct-a-score")
        if error == "metric cell":
            case["counts"]["A"]["tp"] += 1
        elif error == "A/B invalidation":
            states = case["old_receipts"]
            states["A"], states["B"] = states["B"], states["A"]
        else:
            case["samples"]["a"][0]["score"] = "0"
        try:
            verify(fixture, corrupted)
        except ValueError:
            continue
        raise ValueError(f"review incorrectly accepted a corrupted {error}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "examples/model_evaluation")
    parser.add_argument("--record", type=Path, default=ROOT / "evals/results/model_evaluation.json")
    parser.add_argument("--self-test", action="store_true", help="also require three corrupted records to fail")
    args = parser.parse_args()
    record = json.loads(args.record.read_text(encoding="utf-8"))
    print(verify(args.fixture, record))
    if args.self_test:
        rejection_checks(args.fixture, record)
        print("Rejected a changed count, swapped group invalidations, and a changed raw observation.")


if __name__ == "__main__":
    main()
