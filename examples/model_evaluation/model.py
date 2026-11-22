"""Report fault-detection counts for selected fictional instrument QC records."""
import csv
import json
import sys
from pathlib import Path


def evaluate(groups):
    policy = json.loads(Path("policy.json").read_text(encoding="utf-8"))
    counts = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    for group in groups:
        with Path(group + ".csv").open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source):
                positive = row["reference_fault"] == "1"
                flagged = int(row["score"]) >= policy["flag_if_score_at_least"]
                cell = ("tp" if flagged else "fn") if positive else ("fp" if flagged else "tn")
                counts[cell] += 1
    minimum = policy["minimum_sensitivity"]
    positives = counts["tp"] + counts["fn"]
    passed = positives > 0 and counts["tp"] * minimum["denominator"] >= positives * minimum["numerator"]
    return counts, passed


if __name__ == "__main__":
    label, *groups = sys.argv[1:]
    counts, passed = evaluate(groups)
    # An outside observer can count real processes even when TAOS reuses a receipt.
    with Path("../executions.log").open("a", encoding="utf-8") as stream:
        stream.write(label + "\n")
    print(json.dumps(counts, sort_keys=True))
    sys.exit(0 if passed else 1)
