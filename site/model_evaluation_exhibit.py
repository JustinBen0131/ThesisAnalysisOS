"""Publish the recorded two-instrument evaluation and its directly inspectable evidence."""
import hashlib
import json
import runpy
from html import escape
from pathlib import Path

RECORD = "evals/results/model_evaluation.json"
FIXTURE = "examples/model_evaluation/"
CHECKER = "evals/review_model_evaluation.py"
DOWNLOAD_NAMES = {
    RECORD: "Raw observations (JSON)",
    FIXTURE + "a.csv": "Instrument A readings (CSV)",
    FIXTURE + "b.csv": "Instrument B readings (CSV)",
    FIXTURE + "policy.json": "Flagging and acceptance rules",
    FIXTURE + "predictions.json": "Predictions made before execution",
    FIXTURE + "model.py": "Classification code",
    "docs/MODEL_EVALUATION.md": "Full method and limits",
    "evals/model_evaluation.py": "Experiment runner",
    CHECKER: "Independent verifier",
    "evals/model_evaluation.schema.json": "Raw record schema",
}
MODEL_DOWNLOADS = {path: "records/model-evaluation/" + path for path in DOWNLOAD_NAMES}
GROUPS = ("A", "B", "pooled")
CELLS = ("tp", "fn", "fp", "tn")
CASE_NAMES = {
    "figure-caption": "Edit the figure caption",
    "correct-a-score": "Correct A03 only",
    "offsetting-score-corrections": "Correct A03 and B04",
    "shared-threshold": "Raise the shared flag cutoff",
}
TITLE = "Can overall sensitivity hide missed faults on one instrument?"
LIMIT = ("These 16 invented instrument readings were chosen to test a specific failure mode. "
         "They establish that cancellation is possible. They give no estimate of its frequency in deployed models.")


def load_model_evaluation(repo):
    root = Path(repo).resolve()
    record = json.loads((root / RECORD).read_text(encoding="utf-8"))
    if record.get("schema") != "instrument-qc-model-evaluation-v1":
        raise ValueError("Unexpected model evaluation schema")
    sources = record.get("sources")
    required = {FIXTURE + name for name in ("a.csv", "b.csv", "policy.json", "predictions.json", "model.py")}
    required.update(("evals/model_evaluation.py", "taos_core/gates.py", "taos_core/basis.py", "taos_core/demo.py"))
    if not isinstance(sources, dict) or not required.issubset(sources):
        raise ValueError("Missing model evaluation source fingerprints")
    for relative, expected in sources.items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Invalid model evaluation source path: {relative}")
        file = (root / relative).resolve()
        file.relative_to(root)
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Model evaluation source missing or changed: {relative}")
    # Reconstruct the recorded edits and counts from the original CSVs; no gates run here.
    verify = runpy.run_path(str(root / CHECKER))["verify"]
    verify(root / FIXTURE, record)
    return record


def detected(counts):
    return f"{counts['tp']} / {counts['tp'] + counts['fn']}"


def contents(record):
    cases = {row["id"]: row for row in record["cases"]}
    control = cases["figure-caption"]
    target = cases["offsetting-score-corrections"]
    before = control["counts"]
    after = target["counts"]
    def score(case, group, identifier):
        return next(row["score"] for row in case["samples"][group] if row["id"] == identifier)

    scores = [f"{sample} went from {score(control, group, sample)} to {score(target, group, sample)}"
              for group, sample in (("a", "A03"), ("b", "B04"))]
    question = ("We tested a classifier on quality-control readings from two fictional instruments. "
                "Correcting two scores left its overall detection rate unchanged. Looking at each instrument "
                "separately revealed a missed fault and a failed check.")
    design = (f"Each instrument has eight readings, including four known faults. A score of {control['threshold']} or "
              "higher raises a flag. The required sensitivity is 75%, meaning the classifier must detect at least three of "
              "every four known faults in its assessment.")
    finding = (f"{scores[0]} and {scores[1]}. Both readings were known faults. A missed one it had caught. "
               f"B caught one it had missed. The combined result stayed at {detected(after['pooled'])} faults detected.")
    matrix = [[display, detected(before[key]), *(str(after[key][cell]) for cell in CELLS), detected(after[key]),
               "Pass" if target["result_after_consultation"][key] == "holds" else "Fail"]
              for key, display in (("A", "Instrument A"), ("B", "Instrument B"), ("pooled", "Both combined"))]
    runs = []
    for case_id, title in CASE_NAMES.items():
        case = cases[case_id]
        failed = [name for name in GROUPS if case["result_after_consultation"][name] == "fails"]
        runs.append([title, ", ".join(case["executed"]) or "None", ", ".join(case["reused"]) or "None",
                     ", ".join(failed) or "None"])
    return question, design, finding, matrix, runs


MATRIX_COLUMNS = ("Readings", "Detected before", "Caught faults", "Missed faults", "False alarms",
                  "Correct negatives", "Detected after", "Fresh check")
RUN_COLUMNS = ("Edit", "Reran", "Reused earlier pass", "Below 75%")
WHY = ("Each instrument check reads its own CSV and the shared flagging rule. The combined check reads both CSVs. "
       "Correcting both files made all three earlier passes stale, even though the combined counts came out exactly "
       "the same. Changing only A's file left B's pass usable.")


def table_html(caption, headings, rows):
    head = "".join(f'<th scope="col">{escape(cell)}</th>' for cell in headings)
    body = "".join('<tr><th scope="row">' + escape(row[0]) + "</th>" +
                   "".join("<td>" + escape(cell) + "</td>" for cell in row[1:]) + "</tr>" for row in rows)
    return (f'<div class="scroll" tabindex="0" role="region" aria-label="{escape(caption)}">'
            f'<table class="claims"><caption>{escape(caption)}</caption><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def model_evaluation_html(record):
    question, design, finding, matrix, runs = contents(record)
    links = "".join(f'<li><a href="../../{MODEL_DOWNLOADS[path]}">{escape(label)}</a></li>'
                    for path, label in DOWNLOAD_NAMES.items())
    return f"""
<section class="hero slim"><div class="wrap">
<p><a href="../#model-evaluation">Back to the evidence</a></p>
<h1>{TITLE}</h1><p class="lead">{escape(question)}</p><p>{escape(design)}</p>
</div></section>
<section><div class="wrap prose"><h2>Two corrections cancel in the pooled result</h2>
<p>{escape(finding)}</p>
{table_html("Fault detection before and after the two score corrections", MATRIX_COLUMNS, matrix)}
<p>The four count columns show the corrected confusion table. The combined table also had these same four
counts before the edit. Each detection fraction uses only the known faults as its denominator.</p>
<h2>Which earlier checks still applied?</h2><p>{escape(WHY)}</p>
{table_html("Observed check executions after each edit", RUN_COLUMNS, runs)}
<p>Each of the four cases started from the same passing baseline in a fresh workspace. A separate log recorded
which check processes actually started. The fresh executions below the 75% requirement are listed in the last column.</p>
<h2>Inspect the evidence</h2><p>{escape(LIMIT)}</p>
<p><a href="../../source/">Download the source for this build</a> and extract the ZIP. From its top-level folder, repeat the experiment with <code>python3 evals/model_evaluation.py --verify</code>.
To check the saved counts and decisions independently from the original readings, run
<code>python3 evals/review_model_evaluation.py</code>.</p><ul>{links}</ul></div></section>"""


def markdown_table(headings, rows):
    return "\n".join("| " + " | ".join(row) + " |" for row in [headings, ["---"] * len(headings), *rows])


def model_evaluation_markdown(record):
    question, design, finding, matrix, runs = contents(record)
    return "\n\n".join(["# " + TITLE, question, design, "## Two corrections cancel in the pooled result", finding,
                       markdown_table(MATRIX_COLUMNS, matrix), "## Which earlier checks still applied?", WHY,
                       markdown_table(RUN_COLUMNS, runs), "## Method, limits and raw evidence", LIMIT,
                       "[Download this build’s source](../../source/), extract the ZIP and run `python3 evals/model_evaluation.py --verify` from its top-level folder. Independently check the saved observations "
                       "with `python3 evals/review_model_evaluation.py`.",
                       "\n".join(f"- [{name}](../../{MODEL_DOWNLOADS[path]})" for path, name in DOWNLOAD_NAMES.items())]) + "\n"
