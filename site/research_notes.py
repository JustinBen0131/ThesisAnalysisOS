"""Build research-note examples and check their evidence offline with Python's standard library."""

import argparse
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from shutil import copyfile


FORMAT = "taos-research-note/1"
ISSUES = "https://github.com/JustinBen0131/ThesisAnalysisOS/issues"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _dataset(catalog, study):
    matches = [item for item in catalog["dataset"] if item["identifier"] == study]
    if len(matches) != 1:
        raise ValueError(f"Expected one catalog entry for {study}, found {len(matches)}.")
    return matches[0]


def _resolve(document, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise ValueError("Use a JSON Pointer to an observation, beginning with '/'.")
    row_id = None
    for token in pointer[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(document, list) and re.fullmatch(r"0|[1-9][0-9]*", key) and int(key) < len(document):
            document = document[int(key)]
        elif isinstance(document, dict) and key in document:
            document = document[key]
        else:
            raise ValueError(f"The record contains no observation at {pointer}.")
        if isinstance(document, dict) and "id" in document:
            row_id = document["id"]
    return document, row_id


def validate_note(note, catalog, raw_bytes):
    """Verify one citation against a separately obtained catalog and raw download."""
    required = {"format", "kind", "proposal", "scope", "prediction", "control", "evidence"}
    if not isinstance(note, dict) or set(note) != required or note["format"] != FORMAT:
        raise ValueError("Expected a version 1 research note with the documented fields.")
    if note["kind"] not in ("follow-up", "correction"):
        raise ValueError("Use 'follow-up' or 'correction' for the kind of note.")
    for key in ("proposal", "scope", "prediction", "control"):
        if not isinstance(note[key], str) or not note[key].strip():
            raise ValueError(f"Give a short description for {key}.")
    evidence = note["evidence"]
    keys = {"study", "sha256", "pointer", "observed"}
    if not isinstance(evidence, dict) or set(evidence) not in (keys, keys | {"row_id"}):
        raise ValueError("Expected a study, sha256, pointer and observed value, with an optional row_id.")
    dataset = _dataset(catalog, evidence["study"])
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if digest != dataset["distribution"]["sha256"] or digest != evidence["sha256"]:
        raise ValueError("Download, catalog and note must identify the same raw SHA-256.")
    quoted = evidence["observed"]
    decimal_tag = isinstance(quoted, dict) and set(quoted) == {"decimal"}
    try:
        record = json.loads(raw_bytes, object_pairs_hook=_unique_object, parse_float=Decimal if decimal_tag else float)
    except InvalidOperation as exc:
        raise ValueError("The record has an unrepresentable decimal number.") from exc
    actual, row_id = _resolve(record, evidence["pointer"])
    if row_id != evidence.get("row_id"):
        raise ValueError("The cited row ID differs from the row at the pointer.")
    if decimal_tag and type(actual) in (Decimal, int):
        token = quoted["decimal"]
        if not isinstance(token, str) or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", token):
            raise ValueError("A decimal quote needs a finite JSON number written as a string.")
        try:
            matches = Decimal(token) == actual
        except InvalidOperation as exc:
            raise ValueError("The decimal quote cannot be represented.") from exc
    elif decimal_tag and not isinstance(actual, dict):
        matches = False
    else:
        if decimal_tag and isinstance(actual, dict):
            # This is a literal source object; retain the existing type-sensitive object comparison.
            actual, _ = _resolve(json.loads(raw_bytes, object_pairs_hook=_unique_object), evidence["pointer"])
        matches = json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(quoted, sort_keys=True, allow_nan=False)
    if not matches:
        raise ValueError("The quoted observation differs from the value at the pointer.")


QUESTIONS = (
    ("instrument-imbalance", "model_evaluation", "offsetting-score-corrections", "sensitivity_direction",
     "Would an average that weights both instruments equally reveal a loss that pooling still hides when one group has more faults?",
     "Open follow-up on fictional instrument readings. The saved case has four known faults per instrument.",
     "Add eight faulty readings to B, six detected and two missed. If the same two score corrections again lose one A detection "
     "and gain one B detection, pooled sensitivity should stay at 12/16 while the mean of the two sensitivities drops "
     "from 75% to about 66.7%. A change in the pooled count or no drop in the mean would contradict this prediction.",
     "Keep the decision threshold and original readings fixed. Check the augmented table before either correction, then "
     "apply each correction separately before applying both. Count faults from the reference labels."),
    ("undeclared-calibration", "measurement_audit", "omission-1.02", "retained",
     "Could a calibration file used for just one pendulum reading leave an old pass looking usable after the fitted value changes?",
     "Open follow-up using six teaching measurements. Put a multiplier file in a named project input group called "
     "calibration. The fit reads this file for the longest pendulum. In the first condition, leave calibration off "
     "the fit check’s dependency list while keeping the group registered with the project.",
     "Start with a passing check at 1.00. Change only the multiplier to 1.05. We predict that the old check will "
     "still read holds and that a fresh fit will fall below 9.6 m/s². Either a different standing or a fresh fit "
     "inside the acceptance interval would count against this prediction.",
     "Repeat the same edit with calibration on the check’s dependency list. We predict stale. In a separate "
     "condition, leave the multiplier file outside every project input group. We predict unknown. Start each "
     "condition from its own passing check and hold the CSV, fitting code and acceptance limits fixed."),
)


def write_research_notes(out: Path, catalog: dict) -> None:
    """Write a guide and validated examples after the site's raw record downloads exist."""
    folder = out / "research-notes"
    folder.mkdir(exist_ok=True)
    guide = [
        "# Propose a follow-up or correction", "",
        "Both open questions below have threads in the [research exchange](../exchange/index.md). Each thread "
        "starts with one of these notes. Download an example to inspect the observation or write a reply.", "",
    ]
    for name, stem, row_id, field, proposal, scope, prediction, control in QUESTIONS:
        study = f"evals/results/{stem}.json"
        dataset = _dataset(catalog, study)
        raw_path = out / "records" / f"{stem}.json"
        raw = raw_path.read_bytes()
        record = json.loads(raw, object_pairs_hook=_unique_object, parse_float=Decimal)
        cases = record["cases"]
        indices = [i for i, case in enumerate(cases) if case["id"] == row_id]
        if len(indices) != 1:
            raise ValueError(f"Expected one observation named {row_id} in {study}.")
        index = indices[0]
        row = cases[index]
        if stem == "model_evaluation":
            baseline = [dict(zip(record["cell_order"], record["baseline_counts"][group])) for group in ("A", "B")]
            before = [(counts["tp"], counts["fn"]) for counts in baseline]
            after = [(row["counts"][group]["tp"], row["counts"][group]["fn"]) for group in ("A", "B")]
            if before != [(3, 1), (3, 1)] or after != [(2, 2), (4, 0)]:
                raise ValueError("The group-size follow-up requires the recorded pair of offsetting score corrections.")
        elif (row["cohort"], row["retained"], row["estimate_changed"], row["fresh_exit"]) != ("omitted-input", "holds", True, 1):
            raise ValueError("The calibration follow-up requires a retained pass and a failed fresh fit after an omitted-input change.")
        pointer = f"/cases/{index}/{field}"
        note = {"format": FORMAT, "kind": "follow-up", "proposal": proposal, "scope": scope,
                "prediction": prediction, "control": control,
                "evidence": {"study": study, "sha256": dataset["distribution"]["sha256"], "row_id": row_id,
                             "pointer": pointer, "observed": row[field]}}
        validate_note(note, catalog, raw)
        (folder / f"{name}.json").write_text(json.dumps(note, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if stem == "measurement_audit":
            decimal_pointer = f"/cases/{index}/g"
            decimal_text = str(row["g"])
            decimal_note = dict(note, evidence=dict(note["evidence"], pointer=decimal_pointer, observed={"decimal": decimal_text}))
            validate_note(decimal_note, catalog, raw)
            (folder / "decimal-citation.json").write_text(json.dumps(decimal_note, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        guide += [f"## {proposal}", "", scope, "", prediction, "", control, "",
                  f"[Editable note]({name}.json) · [Raw record](../records/{stem}.json) · "
                  f"Row `{row_id}`, JSON Pointer `{pointer}`.", ""]
    guide += [
        "## Check a note locally", "",
        "Download an editable note, its raw record, the [catalog](../research-catalog.json) and the "
        "[Python checker](check_note.py) to one folder. For example, run the following command there.", "",
        "```sh", "python3 check_note.py instrument-imbalance.json research-catalog.json model_evaluation.json", "```", "",
        "To write your own, set `kind` to `follow-up` or `correction`. Describe your `proposal`, its `scope`, a "
        "`prediction` that could be wrong and a `control` comparison. Keep `format` as `taos-research-note/1`. "
        "Under `evidence`, copy the catalog's `identifier` into `study` and its distribution SHA-256 into `sha256`. "
        "Supply a JSON Pointer into that download and copy its exact JSON value into `observed`. If the containing "
        "row has an `id`, include it as `row_id`. For a correction, quote the existing value in `observed` and "
        "explain the proposed replacement in `proposal`. Keep the catalog and raw bytes with the note for later verification.", "",
        "The checker reads three local files and verifies the citation. A successful check leaves the scientific proposal open.", "",
        "## Quote a decimal measurement", "",
        f"The [decimal example](decimal-citation.json) cites the same calibration question using the recorded gravity "
        f"estimate at `{decimal_pointer}` in the [pendulum observations](../records/measurement_audit.json). "
        f'It quotes `{{"decimal":"{decimal_text}"}}`. The string carries the numeric precision across implementations. '
        "The checker compares it with the original JSON number using exact decimal arithmetic. A JSON string in the "
        "source remains a string, and an object with a `decimal` key can still be quoted literally.", "",
        "```sh", "python3 check_note.py decimal-citation.json research-catalog.json measurement_audit.json", "```", "",
        "## Discuss a question or submit a reply", "",
        "Find the question in the [exchange index](../exchange.json). To reply, put your checked note in the "
        "entry’s `note` field, choose a `stance` such as `refines` or `disputes`, and copy the parent entry’s "
        "`id` into `replies_to`. The parent ID identifies the argument you are answering. The SHA-256 in "
        "`note.evidence` identifies the data you used. The exchange guide shows how another team can download "
        "the entries and recheck the entire reply chain.", "",
        f"For informal public discussion, a person can use [GitHub Issues]({ISSUES}). To request inclusion in the "
        "exchange, attach the checked entry to that same issue or open a pull request containing just the entry file. The maintainer "
        "reviews proposed entries for inclusion in a later build. The published measurements retain their original "
        "values. Teams can also share the files directly and check them offline.", "",
    ]
    (folder / "index.md").write_text("\n".join(guide), encoding="utf-8")
    copyfile(__file__, folder / "check_note.py")


def main():
    parser = argparse.ArgumentParser(description="Check a research note against an archived catalog and raw record, offline.")
    for name in ("note", "catalog", "record"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    try:
        note, catalog = [json.loads(p.read_bytes(), object_pairs_hook=_unique_object) for p in (args.note, args.catalog)]
        validate_note(note, catalog, args.record.read_bytes())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Citation check failed: {exc}\n")
    print(f"Verified {note['evidence']['study']} at {note['evidence']['pointer']}.")


if __name__ == "__main__":
    main()
