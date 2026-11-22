"""Verify and publish the observed unequal-group follow-up without running the classifier."""

import csv
import hashlib
import io
import json
from fractions import Fraction
from pathlib import Path
from urllib.parse import urljoin


RECORD = "evals/results/followups/instrument-imbalance.json"
REFERENCE = "evals/results/model_evaluation.json"
RUNNER = "evals/replay_instrument_imbalance.py"
FIXTURE = "examples/model_evaluation/"
CONDITIONS = {
    "augmented-baseline": ("Augmented baseline", ()),
    "a-only": ("Correct A only", ("a.csv",)),
    "b-only": ("Correct B only", ("b.csv",)),
    "both": ("Correct both", ("a.csv", "b.csv")),
    "restored": ("Restore the original scores", ()),
}


def _require(condition, message):
    if not condition:
        raise ValueError(f"Instrument imbalance follow-up: {message}")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _csv_bytes(rows):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=("id", "reference_fault", "score"), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue().encode()


def _counts(rows, threshold):
    counted = dict(tp=0, fn=0, fp=0, tn=0)
    detected = []
    for row in rows:
        _require(row["reference_fault"] in ("0", "1"), f"invalid fault label for {row['id']}")
        fault = row["reference_fault"] == "1"
        flagged = int(row["score"]) >= threshold
        cell = {(True, True): "tp", (True, False): "fn", (False, True): "fp", (False, False): "tn"}[fault, flagged]
        counted[cell] += 1
        if cell == "tp":
            detected.append(row["id"])
    return counted, sorted(detected)


def _verify(repo, record):
    _require(record["schema"] == "instrument-imbalance-replay/1", "unrecognized record format")
    files = {FIXTURE + name for name in ("a.csv", "b.csv", "model.py", "policy.json")} | {RUNNER, REFERENCE}
    _require(set(record["sources"]) == files, "source manifest is incomplete or unexpected")
    sources = {name: (repo / name).read_bytes() for name in files}
    for name, data in sources.items():
        _require(_sha(data) == record["sources"][name], f"source fingerprint changed for {name}")
    policy = json.loads(sources[FIXTURE + "policy.json"])
    _require(record["policy"] == policy, "policy differs from fixture")
    cutoff = policy["flag_if_score_at_least"]
    minimum = Fraction(policy["minimum_sensitivity"]["numerator"], policy["minimum_sensitivity"]["denominator"])
    original = {g: list(csv.DictReader(io.StringIO(sources[FIXTURE + g + ".csv"].decode())))
                for g in ("a", "b")}
    _require(record["original_samples"] == original, "saved baseline differs from the original specimens")
    extra = record["added_b_faults"]
    extra_counts, _ = _counts(extra, cutoff)
    _require(extra_counts == {"tp": 6, "fn": 2, "fp": 0, "tn": 0}, "added readings differ from the forecast design")
    specimens = {"a": original["a"], "b": original["b"] + extra}
    ids = [r["id"] for rows in specimens.values() for r in rows]
    _require(len(ids) == len(set(ids)), "sample identifiers overlap")
    reference = json.loads(sources[REFERENCE])
    for name in ("a.csv", "b.csv", "model.py", "policy.json"):
        _require(reference["sources"][FIXTURE + name] == record["sources"][FIXTURE + name],
                 f"{name} differs from the sources of the original comparison")
    paired = [c for c in reference["cases"] if c["id"] == "offsetting-score-corrections"]
    _require(len(paired) == 1 and record["recorded_edits"] == paired[0]["edits"], "score edits differ from the cited case")
    edits = {e["file"]: e for e in paired[0]["edits"]}
    cases = {c["id"]: c for c in record["cases"]}
    _require(len(record["cases"]) == len(cases) and set(cases) == set(CONDITIONS), "condition missing or duplicated")
    _require(set(record["expected_detected_faults"]) == set(cases), "condition missing in the forecast")
    observed_fractions = {}
    for key, (_, changed) in CONDITIONS.items():
        case = cases[key]
        _require(case["score_edits"] == [edits[f] for f in changed], f"incorrect edits for {key}")
        samples = {}
        for group, originals in specimens.items():
            rows = [row.copy() for row in originals]
            filename = group + ".csv"
            if filename in changed:
                edit = edits[filename]
                targets = [row for row in rows if row["id"] == edit["id"]]
                _require(len(targets) == 1, f"missing correction target for {key}/{group}")
                targets[0]["score"] = str(edit["score"])
            data = sources[FIXTURE + filename] if group == "a" and filename not in changed else _csv_bytes(rows)
            _require(_sha(data) == case["input_sha256"][group], f"input bytes differ for {key}/{group}")
            samples[group.upper()] = rows
        samples["pooled"] = samples["A"] + samples["B"]
        _require(set(case["groups"]) == set(samples), f"incorrect group names for {key}")
        rates = {}
        for group, rows in samples.items():
            counts, detected = _counts(rows, cutoff)
            known = counts["tp"] + counts["fn"]
            rate = rates[group] = Fraction(counts["tp"], known)
            observed = case["groups"][group]
            _require(observed["counts"] == counts and observed["detected_fault_ids"] == detected
                     and observed["reference_faults"] == known and observed["sensitivity"] == str(rate)
                     and observed["checker_exit"] == int(rate < minimum), f"classification mismatch for {key}/{group}")
            if group != "pooled":
                _require(record["expected_detected_faults"][key][group] == counts["tp"], f"forecast missed for {key}/{group}")
        mean = (rates["A"] + rates["B"]) / 2
        _require(case["equal_group_mean"] == str(mean) and case["lowest_group_sensitivity"] == str(min(rates["A"], rates["B"])),
                 f"group summaries differ for {key}")
        observed_fractions[key] = (rates["pooled"], mean)
    baseline, both, restored = (cases[key] for key in ("augmented-baseline", "both", "restored"))
    attributes = ("groups", "input_sha256", "equal_group_mean", "lowest_group_sensitivity")
    _require(all(baseline[field] == restored[field] for field in attributes), "restored control differs from baseline")
    _require(observed_fractions["augmented-baseline"] == (Fraction(3, 4), Fraction(3, 4))
             and observed_fractions["both"] == (Fraction(3, 4), Fraction(2, 3)), "open question's forecast did not hold")
    for case in (baseline, both):
        pooled = case["groups"]["pooled"]
        _require((pooled["counts"]["tp"], pooled["reference_faults"]) == (12, 16), "pooled forecast missed")
    checks = {"all_classifier_process_calls_observed", "equal_group_mean_changes_from_3_4_to_2_3",
              "expected_detections_in_every_condition", "pooled_detects_12_of_16_before_and_after",
              "restored_bytes_and_counts_match_augmented_baseline"}
    _require(record["invocations"] == sum(len(c["groups"]) for c in cases.values()) and set(record["controls"]) == checks
             and all(value is True for value in record["controls"].values()) and record["passed"] is True,
             "recorded control outcomes or execution count differ")
    return cases


def write_followup(out: Path, repo: Path, base_url: str = "") -> dict:
    """Publish the original bytes and a human reading after checking every recorded condition."""
    raw = (repo / RECORD).read_bytes()
    record = json.loads(raw)
    cases = _verify(repo, record)
    url = base_url.rstrip("/") + "/" if base_url else ""
    name = "Can pooled sensitivity stay fixed while the equal-weight mean falls?"
    table = []
    for key, (label, _) in CONDITIONS.items():
        trial = cases[key]
        cells = [f"{trial['groups'][g]['counts']['tp']}/{trial['groups'][g]['reference_faults']}" for g in ("A", "B", "pooled")]
        table.append("| " + " | ".join([label, *cells, trial["equal_group_mean"]]) + " |")
    baseline, both = cases["augmented-baseline"], cases["both"]
    pooled = both["groups"]["pooled"]
    finding = (f"The combined instruments detected {pooled['counts']['tp']} of {pooled['reference_faults']} known faults "
               f"before and after both corrections. Giving each instrument equal weight changed mean sensitivity "
               f"from {baseline['equal_group_mean']} to {both['equal_group_mean']}.")
    text = f"""# {name}

{finding}

The [original forecast](../research-notes/instrument-imbalance.json) proposed adding known faults to instrument B before repeating two score corrections. The experiment used the [original instrument readings and edits](../studies/model-evaluation/), added {len(record['added_b_faults'])} fictional faults to B and kept the inclusive score cutoff at {record['policy']['flag_if_score_at_least']}. The shipped classifier ran {record['invocations']} times. A separate count from the reference labels and sample IDs checked the results.

| Condition | A detected | B detected | Combined | Equal-weight mean |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(table)}

Both single corrections were tested before their effects were compared. Restoring the original scores recovered the augmented baseline files byte for byte. Pooling weights each instrument by its number of known faults. The mean gives each instrument equal weight. The added scores were chosen to test that difference. These counts cannot estimate performance in a population.

[Download the full observations and source fingerprints](../records/instrument-imbalance.json) · [Source checkout](../source/)

From the repository root, run `python3 {RUNNER} --json` to repeat the follow-up. The saved observations are in `{RECORD}`.
"""
    (out / "records").mkdir(parents=True, exist_ok=True)
    (out / "exchange").mkdir(parents=True, exist_ok=True)
    (out / "records/instrument-imbalance.json").write_bytes(raw)
    (out / "exchange/instrument-imbalance.md").write_text(text, encoding="utf-8")
    return {
        "@type": "Dataset", "identifier": RECORD, "name": name, "description": finding + " " + record["scope"],
        "url": urljoin(url, "exchange/instrument-imbalance.md"),
        "distribution": {"@type": "DataDownload", "contentUrl": urljoin(url, "records/instrument-imbalance.json"),
                         "encodingFormat": "application/json", "sha256": _sha(raw)},
    }
