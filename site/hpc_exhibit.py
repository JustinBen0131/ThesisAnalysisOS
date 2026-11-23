"""Portable research-computing policy and a fictional, replayable run board."""

import json
from html import escape
from pathlib import Path
from typing import NamedTuple

from hpc_planner import TEMPLATE_LINK, render_planner, worksheet


PAGE_TITLE = "HPC run policy · ThesisAnalysisOS"
TITLE = "Decide what needs to run"
DESCRIPTION = (
    "Plan, check and reuse work on a workstation, a shared cluster or a cloud budget. "
    "Follow a researcher's decisions and the compute backend's replies in a fictional pilot."
)
OPENING = (
    "ThesisAnalysisOS records which inputs, code and settings produced a result and how it was checked. "
    "When one part of a project changes, you can trace which jobs need to run again and which results you can reuse."
)
BENEFIT = (
    "Reusing a checked result can spare a lab another wait for a cluster slot, a team a repeat cloud charge, "
    "or an individual another night on a workstation."
)
EXAMPLE = "A typo in a figure title"
FIGURE_STEPS = (("Input data", "Unchanged"), ("Checked calculation", "Reuse"), ("Figure", "Redraw"))
FIGURE_DECISION = (
    "Correct the title and redraw the figure from the saved calculation. If the formula changes instead, "
    "rerun the calculation and update the figures that use it."
)
POLICY_TITLE = "How to plan and verify a run"
POLICY = (
    ("Before you start", "What changed?",
     "Compare the inputs, code and settings with the last checked result. Reuse it when they still match. "
     "If you can’t trace what it depended on, check it again."),
    ("Before you scale up", "What does one job need?",
     "Try one representative input. Measure its run time, peak memory and output size. Use those readings "
     "to set limits on the larger run with whoever owns the machine or budget."),
    ("When the jobs finish", "Did the outputs pass?",
     "Open the files you expected and test something that matters, such as the number of records. "
     "Keep the outputs that pass. Trace a failure to its cause before deciding what to retry."),
)
SOFTWARE = (
    "One person can coordinate multiple AI agents through a shared project record. A planning agent can draft "
    "the run sheet, a reviewer can check the returned files, and another agent can pick up the next batch. "
    "Use a local tool such as Claude Code or Codex, or share a selected handoff with a ChatGPT conversation. "
    "You or your operator approve and submit work through your usual compute tools."
)
SITES_TITLE = "What changes with the setting?"
SITES_INTRO = "The same decisions apply wherever the work runs. The resource at stake and the person who can commit it change."
SITES = (
    ("A shared cluster", "University, institute or computing center",
     "Several groups share a queue and an allocation.",
     "Use one sample to set time and memory requests with the project lead. Limit how many jobs run together. "
     "Keep each job’s completion record alongside the output it produced."),
    ("A cloud project", "Research or engineering team",
     "Every repeat can add compute and storage charges.",
     "Agree on a spending limit with the budget owner. Estimate the next batch from a small run. "
     "Verify the saved objects before paying to repeat any work."),
    ("A personal workstation", "An individual researcher",
     "A long job competes with your other work for memory, disk and time.",
     "Try one input and leave room for your other applications. Save the command and the checked output "
     "so you can pick up later."),
)
SCHEDULER_DOCS = (
    ("AWS Batch job states", "https://docs.aws.amazon.com/batch/latest/userguide/job_states.html"),
    ("Slurm job accounting", "https://slurm.schedmd.com/sacct.html"),
    ("HTCondor job history", "https://htcondor.readthedocs.io/en/main/man-pages/condor_history.html"),
)
RECORD_PATH = "evals/results/reuse_frontier.json"
RECORD_LINK = "../records/reuse_frontier.json"
METHOD_LINK = "../evidence/#reuse-full"
STUDY_TITLE = "How many checks needed to run again?"
BOARD_TITLE = "Would you trust this batch?"
BOARD_INTRO = (
    "Three sensor files hold seven readings. "
    "Each job counts the values in one file. Your agents check the results, and you decide what goes into the report."
)
BOARD_SCOPE = "Pilot run board · fictional example"
TRACE_LINK = "example-run.json"
TRANSFER_RECORD = "examples/hpc/returns/C-transfer.txt"
TRANSFER_LINK = "https://github.com/JustinBen0131/ThesisAnalysisOS/blob/main/" + TRANSFER_RECORD
TEAM = {"Planner": "Define the check", "Run operator": "Run approved jobs", "Reviewer": "Verify the outputs"}


class Stage(NamedTuple):
    key: str
    label: str
    title: str
    owner: str
    person: str
    framework: str
    backend: str
    recipient: str
    record: str
    actions: tuple


STAGES = (
    Stage("plan", "Run plan", "How many readings should come back?", "Planner",
          "Approve one job per file, with at most two running at once.",
          "The planner counts the entries in each original file. These counts are the reference when the jobs return.",
          "Waiting for your approval. No jobs have run.",
          "Run operator", "The plan allows one job per file and two jobs at a time.",
          (("returned", "Approve three jobs"),)),
    Stage("returned", "Jobs finished", "Which file needs a second look?", "Run operator",
          "Choose a sample to inspect, or ask the reviewer to check the full packet.",
          "Picks up the approved run sheet, sends the three jobs within the limit and matches each summary to its input.",
          "All three jobs finished and returned a summary.",
          "Reviewer", "The reviewer gets the three summaries and the counts from the original files.",
          (("checked", "See the reviewer’s finding"),)),
    Stage("checked", "Outputs checked", "C’s job finished with an empty file.", "Reviewer",
          "You can approve one more job for C or hold it while you review the evidence.",
          "Opens the result packet. A and B match the originals. C reports zero of two readings. Its transfer log shows an incomplete input.",
          "Each sample ran once. A complete copy of C is available for a retry.",
          "You", "Keep A and B. Only C needs another delivery.",
          (("retry", "Retry C only"), ("held", "Hold for review"))),
    Stage("held", "On hold", "C is on hold.", "You",
          "You hold C and keep the two passing results.",
          "The reviewer saves the failed comparison and the incomplete transfer record together.",
          "No additional job has run.",
          "Reviewer", "A and B stay in the report. C stays on hold until you decide.",
          (("checked", "Reopen the reviewer’s check"),)),
    Stage("retry", "Retry returned", "C is back. Does it match?", "Run operator",
          "You authorized a retry of C alone.",
          "Uses the reviewer’s exception report and the complete input. Attaches C’s second completion report to the original attempt.",
          "C ran a second time and returned 2 readings. A and B each ran once.",
          "Reviewer", "The replacement arrived. Check its count before adding C to the report.",
          (("resolved", "Verify the retry"),)),
    Stage("resolved", "Retry checked", "All seven readings accounted for.", "Reviewer",
          "Keep all three checked results. Only C needed another job.",
          "Compares the replacement summary with C’s original two readings. Keeps the earlier checks for A and B.",
          "Four jobs finished across three samples. The queue has no further work for this pilot.",
          "You", "Use all three counts. A and B each ran once. Only C ran twice.",
          (("plan", "Replay the pilot"),)),
)
def _sample_inputs():
    directory = (Path(__file__).resolve().parents[1] / TRANSFER_RECORD).parent
    samples = []
    for name in ("A", "B", "C"):
        record = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
        samples.append((record["sample"], tuple(record["expected_readings"]), tuple(record["returned_readings"])))
    return tuple(samples)


SAMPLES = _sample_inputs()


def _sample_rows(stage):
    rows = []
    for name, original, delivered in SAMPLES:
        expected = len(original)
        if stage == "plan":
            rows.append((name, "Waiting", f"Expect {expected}", "pending"))
            continue
        rerun = stage in ("retry", "resolved") and delivered != original
        backend = "Finished twice" if rerun else "Finished once"
        if stage == "returned" or (stage == "retry" and rerun):
            rows.append((name, backend, "Unchecked", "pending"))
            continue
        count = len(original if rerun else delivered)
        status = "pass" if count == expected else "review"
        verdict = "Pass" if status == "pass" else "Review"
        rows.append((name, backend, f"{verdict} · {count} of {expected}", status))
    return rows


def _returned_counts(stage):
    if stage == "plan":
        return {}
    return {name: len(original if stage in ("retry", "resolved") else delivered)
            for name, original, delivered in SAMPLES}


def _receipt(backend, count):
    return backend if count is None else f"{backend} · {count} readings"


def _transfer_receipt(stage):
    """The reviewer opens the job's input record after comparing the three outputs."""
    if stage.key in ("plan", "returned"):
        return None
    name, original, first_delivery = next(row for row in SAMPLES if row[1] != row[2])
    deliveries = [len(first_delivery)]
    if stage.key in ("retry", "resolved"):
        deliveries.append(len(original))
    status = next(status for sample, _, _, status in _sample_rows(stage.key) if sample == name)
    return {"sample": name, "source_count": len(original), "received_counts": deliveries, "output_status": status,
            "first_delivery_record": TRANSFER_RECORD}


def _receipt_lines(receipt):
    yield "Original file", receipt["source_count"]
    for attempt, count in enumerate(receipt["received_counts"], 1):
        yield ("First delivery" if attempt == 1 else "After retry"), count


def _transfer_html(receipt):
    if receipt is None:
        return ""
    columns = []
    for i, (label, count) in enumerate(_receipt_lines(receipt)):
        state = "source" if i == 0 else ("complete" if count == receipt["source_count"] else "short")
        columns.append(f'<div data-delivery="{state}"><dt>{label}</dt><dd>{count}</dd></div>')
    return (f'<figure class="transfer-slip"><figcaption>Transfer receipt <strong>File {receipt["sample"]}</strong></figcaption>'
            f'<dl aria-label="Number of readings">{"".join(columns)}</dl>'
            f'<p>Reading counts · <a href="{TRANSFER_LINK}">First delivery log</a></p></figure>')


def run_trace():
    return {
        "kind": "fictional run-board example",
        "task": "Count the readings in each sample.",
        "team": TEAM,
        "inputs": {name: list(values) for name, values, _ in SAMPLES},
        "first_attempt_inputs": {name: list(delivered) for name, _, delivered in SAMPLES},
        "stages": [{
            "id": s.key, "label": s.label, "title": s.title, "person": s.person,
            "task_owner": s.owner, "handoff": {"from": s.owner, "to": s.recipient, "record": s.record,
                                              "transfer_receipt": _transfer_receipt(s)},
            "framework_and_assistant": s.framework, "compute_backend": s.backend,
            "samples": [{"sample": n, "backend": b, "reported_count": _returned_counts(s.key).get(n), "output_check": c, "status": v}
                        for n, b, c, v in _sample_rows(s.key)],
            "choices": [{"label": label, "next": target} for target, label in s.actions],
        } for s in STAGES],
    }


def _study():
    record = json.loads((Path(__file__).resolve().parents[1] / RECORD_PATH).read_text(encoding="utf-8"))
    rows = {row["policy"]: row for row in record["rows"]}
    full = rows["rerun everything"]
    scoped = rows["TAOS, checks isolated, declared correctly"]
    hidden = rows["TAOS, each check hides one folder it reads"]
    setup = (
        f"A reproducible software test requested {record['checks']} checks after each of {record['edits']} "
        "edits to synthetic files. Each edit affected the inputs of one check."
    )
    finding = (
        f"With all inputs recorded and each check isolated, {scoped['wrong']} out-of-date results were reused. "
        f"In a second version, checks could read an unlisted input. An out-of-date result was reused "
        f"{hidden['wrong']} times. Knowing what each check reads makes selective reruns possible."
    )
    return setup, (("Rerun every check", full["executions"]), ("Rerun affected checks", scoped["executions"])), finding


def _sample_heading(name, expected, count, inspect):
    if not inspect:
        return f'<th scope="col">{name}</th>'
    matches = count == expected
    message = (f"{name} matches. All {expected} readings came back." if matches else
               f"{name} is the discrepancy. The file has {expected} readings and the summary returned {count}.")
    return f"""<th scope="col" class="inspectable"><span class="static-name">{name}</span>
<button type="button" data-inspect="{name}" data-feedback="{escape(message, quote=True)}"
data-match="{str(matches).lower()}" aria-label="Inspect sample {name}" aria-pressed="false" hidden>{name}</button></th>"""


def _sample_comparison(stage):
    counts = _returned_counts(stage.key)
    samples = _sample_rows(stage.key)
    headings, sources, expected, returned, verdicts = [], [], [], [], []
    for (name, values, _), (_, _, check, status) in zip(SAMPLES, samples):
        count = counts.get(name)
        headings.append(_sample_heading(name, len(values), count, stage.key == "returned"))
        marks = "".join(f'<b style="--reading:{v}"><i aria-hidden="true"></i>{v}</b>' for v in values)
        sources.append(f'<td><span class="sample-signal">{marks}</span></td>')
        expected.append(f'<td title="{check if count is None else "Expected readings"}">{len(values)}</td>')
        returned.append(f'<td title="{check}" data-count-status="{status}">{count}</td>')
        label = {"pass": "Verified", "review": "Set aside", "pending": "Unchecked"}[status]
        verdicts.append(f'<td data-status="{status}" title="{check}">{label}</td>')

    rows = [("Sensor values", sources), ("Expected count", expected)]
    if counts:
        rows.append(("Returned count", returned))
    if stage.key not in ("plan", "returned"):
        rows.append(("Output check", verdicts))
    body = "".join(f'<tr><th scope="row">{label}</th>{"".join(cells)}</tr>' for label, cells in rows)
    return f"""<table class="sample-comparison" aria-label="Readings in each sample">
<thead><tr><th scope="col">Sample</th>{"".join(headings)}</tr></thead><tbody>{body}</tbody></table>"""


def _frame_html(stage):
    roster = "".join(
        f'<li data-role="{name}" class="hpc-seat{" active-seat" if name == stage.owner else ""}" '
        f'aria-label="{name}. {task}.{" Owns this task." if name == stage.owner else ""}">'
        f'<strong>{name}</strong>{"<small>Owner</small>" if name == stage.owner else ""}</li>'
        for name, task in TEAM.items()
    )
    actions = "".join(
        f'<button type="button" data-go="{target}">{escape(label)}</button>' for target, label in stage.actions
    )
    inspection = ('<p class="sample-feedback" data-feedback-line role="status" hidden>'
                  'Pick A, B or C to inspect its count.</p>' if stage.key == "returned" else '')
    return f"""<section class="hpc-frame" data-stage="{stage.key}" aria-labelledby="frame-{stage.key}">
<ul class="hpc-team" aria-label="Agent assignments">{roster}</ul>
<div class="hpc-scene"><div class="hpc-evidence">
<p class="scene-phase">{stage.label}{" · You own this decision" if stage.owner == "You" else ""}</p>
<h3 id="frame-{stage.key}" tabindex="-1">{escape(stage.title)}</h3>
{_sample_comparison(stage)}
{inspection}<details class="pilot-log"><summary>Read the run log</summary>
<p><strong>{stage.owner if stage.owner != "You" else "Reviewer"}</strong> {stage.framework}</p>
<p><strong>Backend</strong> {stage.backend}</p><p><strong>Your decision</strong> {stage.person}</p></details></div>
<div class="hpc-handoff"><p class="hand-label">Handoff</p><div class="hand-route">
<strong>{stage.owner}</strong><span aria-hidden="true">→</span><strong>{stage.recipient}</strong></div>
{_transfer_html(_transfer_receipt(stage))}<p class="hand-record">{stage.record}</p>
<div class="hpc-actions" hidden>{actions}</div></div></div></section>"""


def render_hpc() -> str:
    figure = "".join(f'<div><dt>{item}</dt><dd>{state}</dd></div>' for item, state in FIGURE_STEPS)
    stages = "".join(f'<li><p class="hpc-phase">{phase}</p><h3>{title}</h3><p>{text}</p></li>'
                     for phase, title, text in POLICY)
    environments = "".join(
        f'<tr><th scope="row">{name}<small>{who}</small></th>'
        f'<td><span class="hpc-mobile-label" aria-hidden="true">What’s at stake</span>{stake}</td>'
        f'<td><span class="hpc-mobile-label" aria-hidden="true">How to apply it</span>{action}</td></tr>'
        for name, who, stake, action in SITES
    )
    manuals = "".join(f'<a href="{url}">{label}</a>' for label, url in SCHEDULER_DOCS)
    setup, measures, finding = _study()
    maximum = max(value for _, value in measures)
    bars = "".join(
        f'<div><dt>{label}</dt><dd><strong>{value}</strong> runs'
        f'<span class="hpc-track" aria-hidden="true"><i style="width:{value / maximum:.2%}"></i></span></dd></div>'
        for label, value in measures
    )
    frames = "".join(_frame_html(stage) for stage in STAGES)
    return f"""<article class="hpc-policy" aria-labelledby="hpc-heading">
<header class="hpc-hero wrap"><div class="hpc-intro"><p class="hpc-eyebrow">High-performance computing</p>
<h1 id="hpc-heading">{TITLE}</h1><p class="hpc-lead">{OPENING}</p><p class="hpc-benefit">{BENEFIT}</p>
<p class="hpc-references"><a href="#hpc-pilot">Review your own run</a></p></div>
<figure class="hpc-record"><figcaption>Worked example</figcaption><h2>{EXAMPLE}</h2>
<dl class="hpc-figure-steps">{figure}</dl><p>{FIGURE_DECISION}</p></figure></header>
<section class="hpc-section wrap" aria-labelledby="hpc-policy"><h2 id="hpc-policy">{POLICY_TITLE}</h2>
<ol class="hpc-stages">{stages}</ol><p class="hpc-scope"><strong>Who does what</strong> {SOFTWARE}</p></section>
<section class="hpc-section wrap" aria-labelledby="hpc-environments"><h2 id="hpc-environments">{SITES_TITLE}</h2>
<p class="hpc-section-intro">{SITES_INTRO}</p>
<table class="hpc-environments" role="table" aria-labelledby="hpc-environments"><thead><tr>
<th scope="col">Where you work</th><th scope="col">What’s at stake</th><th scope="col">How to apply it</th>
</tr></thead><tbody>{environments}</tbody></table><p class="hpc-references">Scheduler references {manuals}</p></section>
<section class="hpc-section hpc-study wrap" aria-labelledby="hpc-study">
<div><h2 id="hpc-study">{STUDY_TITLE}</h2><p>{setup}</p></div>
<div><dl class="hpc-measures">{bars}</dl><p>{finding}</p>
<p class="hpc-sources"><a href="{METHOD_LINK}">Study method</a><a href="{RECORD_LINK}">Test results (JSON)</a></p></div></section>
<section class="hpc-section hpc-practice wrap" aria-labelledby="hpc-replay">
<header><p class="pilot-caption">{BOARD_SCOPE}</p><h2 id="hpc-replay">{BOARD_TITLE}</h2><p class="hpc-section-intro">{BOARD_INTRO}</p></header>
<div class="hpc-board" data-hpc-board>{frames}</div>
<p class="hpc-sources"><a href="{TRACE_LINK}">Example inputs, checks and decisions (JSON)</a></p>
</section>{render_planner()}</article>"""


def hpc_markdown() -> str:
    lines = [f"# {TITLE}", "", OPENING, "", BENEFIT, "", "[Review your own run](./#hpc-pilot)", "",
             f"## Worked example · {EXAMPLE}", ""]
    lines.extend(f"- {item} — {state}" for item, state in FIGURE_STEPS)
    lines.extend(["", FIGURE_DECISION, "", f"## {POLICY_TITLE}", ""])
    for phase, title, text in POLICY:
        lines.extend([f"### {phase} · {title}", "", text, ""])
    lines.extend(["**Who does what**", "", SOFTWARE, "", f"## {SITES_TITLE}", "", SITES_INTRO, ""])
    for name, who, stake, action in SITES:
        lines.extend([f"### {name} · {who}", "", stake, "", action, ""])
    lines.extend(["Scheduler references", "", " · ".join(f"[{label}]({url})" for label, url in SCHEDULER_DOCS), ""])
    setup, measures, finding = _study()
    lines.extend([f"## {STUDY_TITLE}", "", setup, ""])
    lines.extend(f"- {label} — {value} runs" for label, value in measures)
    lines.extend(["", finding, "", f"[Study method]({METHOD_LINK}) · [Test results (JSON)]({RECORD_LINK})", "",
                  f"## {BOARD_TITLE}", "", BOARD_INTRO, "", BOARD_SCOPE, ""])
    for stage in STAGES:
        reported = _returned_counts(stage.key)
        lines.extend([f"### {stage.label} · {stage.title}", "", f"**You** — {stage.person}", "",
                      f"**Task owner** — {stage.owner}", "", f"**Agent action** — {stage.framework}", "", f"**Compute backend** — {stage.backend}",
                      "", "| Input | Backend report | Output check |", "| --- | --- | --- |"])
        lines.extend(f"| Sample {name} | {_receipt(state, reported.get(name))} | {check} |" for name, state, check, _ in _sample_rows(stage.key))
        lines.extend(["", f"**Handoff · {stage.owner} to {stage.recipient.lower()}** — {stage.record}", ""])
        receipt = _transfer_receipt(stage)
        if receipt:
            lines.extend([f"**Transfer receipt · File {receipt['sample']}** (readings)", ""])
            lines.extend(f"- {label}: {count}" for label, count in _receipt_lines(receipt))
            lines.extend(["", f"[First delivery log]({TRANSFER_LINK})", ""])
        lines.extend(["**Available choices** — " + " / ".join(label for _, label in stage.actions) + ".", ""])
    lines.extend([f"[Example inputs, checks and decisions (JSON)]({TRACE_LINK})", "", worksheet().replace("# ", "## ", 1), f"[Download the blank worksheet]({TEMPLATE_LINK})", ""])
    return "\n".join(lines)
