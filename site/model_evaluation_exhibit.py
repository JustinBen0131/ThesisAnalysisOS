"""Publish the recorded two-instrument evaluation and its directly inspectable evidence."""
import csv
import hashlib
import io
import json
import runpy
from html import escape
from pathlib import Path

RECORD = "evals/results/model_evaluation.json"
FIXTURE = "examples/model_evaluation/"
CHECKER = "evals/review_model_evaluation.py"
DOWNLOAD_NAMES = {
    RECORD: "Raw observations (JSON)",
    "evals/results/followups/instrument-paths.json": "Both correction orders and their reversals (JSON)",
    "evals/replay_instrument_paths.py": "Rerun the correction-order experiment",
    FIXTURE + "a.csv": "Instrument A readings (CSV)",
    FIXTURE + "b.csv": "Instrument B readings (CSV)",
    FIXTURE + "policy.json": "Flagging and acceptance rules",
    FIXTURE + "predictions.json": "Saved predictions for all four edits",
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


PATH_RECORD = "evals/results/followups/instrument-paths.json"
PATH_RUNNER = "evals/replay_instrument_paths.py"
PATH_HEADINGS = ("Order", "At the start", "After one edit", "After both", "Undo the second", "Undo both")
PATH_TITLE = "Does the order of corrections matter?"


def load_instrument_paths(repo):
    record = json.loads((repo / PATH_RECORD).read_text(encoding="utf-8"))
    if record["schema"] != "instrument-correction-paths/1":
        raise ValueError("Unrecognized instrument replay")
    for name in ("a.csv", "b.csv", "policy.json", "model.py", "predictions.json"):
        raw = (repo / FIXTURE / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["source_sha256"][name]:
            raise ValueError("Instrument replay source changed: " + name)
    routes = record["routes"]
    if ([r["order"] for r in routes] != [["A", "B"], ["B", "A"]]
            or not all(r["restored_fixture_bytes"] for r in routes)):
        raise ValueError("Expected both correction orders and byte-for-byte restoration")
    return record


def path_findings(record):
    rows = []
    for route in record["routes"]:
        readings = [step["native_sensitivity"] for step in route["steps"]]
        if len(readings) != 5 or readings[0] != readings[-1]:
            raise ValueError("The five-step replay did not return to its initial readings")
        rows.append([" then ".join(route["order"])] + [r["pooled"] for r in readings])
    first, second = record["routes"]
    both = first["steps"][2]["native_sensitivity"]
    if both != second["steps"][2]["native_sensitivity"]:
        raise ValueError("The two edit orders differ at the same data state")
    finding = (f"Both routes end up with exactly the same corrected data. A catches {both['A']} known faults and "
               f"B catches {both['B']}. Their combined {both['pooled']} hides A’s decline. Undoing the edits "
               "restores the original files byte for byte and returns both instruments to their starting counts.")
    effort = (f"TAOS started {first['native_executions']} checks when A changed first and "
              f"{second['native_executions']} when B changed first. A check that failed runs again when asked. "
              f"A previous pass can be reused when its inputs match. Freshly running all three checks at "
              f"each step took {record['rerun_all_executions']} executions, and gave the same answers throughout.")
    return rows, finding, effort


def replay_html(record):
    rows, finding, effort = path_findings(record)
    return (f'<h2 id="replay-the-edits">{PATH_TITLE}</h2>'
            '<p>Start with the same eight known faults. Correct one instrument, then the other. '
            'Walk the edits back in reverse. The table counts how many faults the two instruments catch together.</p>'
            + table_html("Known faults caught out of eight", PATH_HEADINGS, rows) +
            f'<p>{escape(finding)}</p><details><summary>See which checks actually ran</summary><p>{escape(effort)}</p>'
            '<p>A separate count from the raw CSV rows checked every step. Reproduce both routes with '
            f'<code>python3 evals/replay_instrument_paths.py --verify</code>. '
            f'<a href="../../{MODEL_DOWNLOADS[PATH_RECORD]}">Read all ten observations (JSON)</a>.</p></details>')


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
    question = ("A team corrects one score on each of two fictional instruments. One instrument now misses "
                "a fault it had caught. The other catches one it had missed. Their combined detection rate stays the same.")
    design = (f"Each instrument had eight scored readings, four of them known faults. "
              f"The program flags a reading when its score is {control['threshold']} or higher. "
              "An instrument passes its check when it flags at least three of its four known faults (75%).")
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


def model_evaluation_html(record, replay=None):
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
{replay_html(replay) if replay else ""}
<h2>Inspect the evidence</h2><p>{escape(LIMIT)}</p>
<p><a href="../../workflows/review/reviewer-prompt.txt">Give a second reviewer the results</a> ·
<a href="../../workflows/review/reviewer-sources.md">Supply the source rows and acceptance rule</a></p>
<p><a href="../../source/">Download the source for this build</a> and extract the ZIP. From its top-level folder, repeat the experiment with <code>python3 evals/model_evaluation.py --verify</code>.
To check the saved counts and decisions independently from the original readings, run
<code>python3 evals/review_model_evaluation.py</code>.</p><ul>{links}</ul></div></section>"""


def reviewer_materials(record, repo):
    """A short first review and the actual rows needed for an independent count."""
    _, design, _, matrix, _ = contents(record)
    table = "\n".join(f"{row[0]}: {row[1]} before, {row[-2]} after ({row[-1].lower()})" for row in matrix)
    prompt = ("Review these fictional instrument results. Can the team rely on both instruments after the corrections?\n\n"
              + design + "\n\nKnown faults detected\n" + table +
              "\n\nExplain what the pooled rate hides. Name the source material you would need to verify the counts "
              "independently and one observation that could change your conclusion.\n")
    cases = {case["id"]: case for case in record["cases"]}
    sources = ["# Source rows for the two-instrument review", "",
               "These readings are fictional. A reference fault of 1 means a known fault. "
               "Apply the flagging threshold to each score, then count hits, missed faults, false alarms and correct negatives "
               "for A, B and both instruments together. Compare each instrument with the minimum sensitivity.", ""]
    columns = ("id", "reference_fault", "score")
    for phase, case in (("Before", cases["figure-caption"]), ("After", cases["offsetting-score-corrections"])):
        for group in ("a", "b"):
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(case["samples"][group])
            sources.extend((f"## {phase} · Instrument {group.upper()}", "", "```csv",
                            output.getvalue().rstrip("\n"), "```", ""))
    policy = (Path(repo) / FIXTURE / "policy.json").read_text(encoding="utf-8")
    sources.extend(("## Acceptance policy", "", "```json", policy.rstrip(), "```", "",
                    "[Recorded observations](../../records/model_evaluation.json) · "
                    "[Calculation and method](../../evidence/model-evaluation/)", ""))
    return prompt, "\n".join(sources)


def markdown_table(headings, rows):
    return "\n".join("| " + " | ".join(row) + " |" for row in [headings, ["---"] * len(headings), *rows])


def model_evaluation_markdown(record, replay=None):
    question, design, finding, matrix, runs = contents(record)
    supplement = []
    if replay:
        rows, conclusion, effort = path_findings(replay)
        supplement = ["## " + PATH_TITLE, markdown_table(PATH_HEADINGS, rows), conclusion, effort,
                      "Repeat with `python3 evals/replay_instrument_paths.py --verify`."]
    return "\n\n".join(["# " + TITLE, question, design, "## Two corrections cancel in the pooled result", finding,
                       markdown_table(MATRIX_COLUMNS, matrix), "## Which earlier checks still applied?", WHY,
                       markdown_table(RUN_COLUMNS, runs), *supplement, "## Method, limits and raw evidence", LIMIT,
                       "[Download this build’s source](../../source/), extract the ZIP and run `python3 evals/model_evaluation.py --verify` from its top-level folder. Independently check the saved observations "
                       "with `python3 evals/review_model_evaluation.py`.",
                       "\n".join(f"- [{name}](../../{MODEL_DOWNLOADS[path]})" for path, name in DOWNLOAD_NAMES.items())]) + "\n"
