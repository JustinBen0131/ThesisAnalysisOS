"""Researcher intake and report reading for the same local reviewer used by the CLI."""
from html import escape
from pathlib import Path

from taos_core import hpc

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/hpc/campaign.json"
SOURCES = ("policies/HPC.md", "taos_core/hpc.py", "tests/test_hpc_review.py", "examples/hpc/campaign.json",
           "examples/hpc/returns/A.json", "examples/hpc/returns/B.json", "examples/hpc/returns/C.json",
           "examples/hpc/returns/C-transfer.txt", "examples/hpc/returns/worker-accounting.json", "taos_core/progress.py")
BLANK = "Which outputs can I reuse, and what still needs a run?"
BRIEF_LINK = "inspection-brief.txt"
REPORT_LINK = "sample-review.json"


def sample_review():
    return hpc.review(hpc.read_packet(EXAMPLE), EXAMPLE.parent)


def default_brief():
    return hpc.brief(BLANK, "other")


def reading():
    return (f"## Review your own run\n\nStart with your research question and the expected outputs. "
            f"[Download the inspection brief]({BRIEF_LINK}) and give it to your agent. "
            "It works from your local manifest, run records and output checks. "
            "Use `./taos hpc review campaign.json --json` in the downloaded project to produce the review. "
            "For recorded worker time and output coverage, run `./taos usage progress --packet campaign.json`. "
            f"[Read the fictional three-sample report]({REPORT_LINK}) or "
            "[inspect its three recorded run times](../source/files/examples/hpc/returns/worker-accounting.json.html).\n\n")


def render():
    report = sample_review()
    settings = "".join(f'<option value="{key}" data-guidance="{escape(guidance, quote=True)}">{escape(label)}</option>'
                       for key, (label, guidance) in hpc.SETTINGS.items())
    example_rows = "".join(f'<li><strong>{escape(row["id"])} · {escape(hpc.LABELS[row["action"]])}</strong>'
                           f'<p>{escape(row["reason"])}</p><small>{escape(row["reference"])}</small></li>'
                           for row in report["outputs"])
    return f"""<div class="compute-intake" data-compute-intake data-format="{hpc.REPORT}">
<p class="hpc-section-intro">Which results can you keep? Give your agent a question and bring back a review of the files it found.</p>
<fieldset class="pilot-form" data-question-panel aria-label="Prepare an agent brief" hidden>
<label class="pilot-field"><span>Your research question</span><input name="question" maxlength="500" required placeholder="Which samples need another run after the transfer?"></label>
<label class="pilot-field"><span>Where does the work run?</span><select name="platform"><option value="">Choose an environment</option>{settings}</select></label>
<button type="button" class="pilot-primary" data-make-brief>Prepare my agent brief</button>
<p role="status" data-brief-status></p>
<div class="pilot-result" data-brief-result hidden><h3 tabindex="-1">Your inspection brief</h3>
<p>Give these instructions to the agent that can read your project folder. It will return a review you can open below.</p>
<div class="pilot-export"><button type="button" data-copy-brief>Copy brief</button>
<button type="button" data-save-brief>Save as text</button></div>
<details class="pilot-plain"><summary>Read the instructions</summary><pre data-brief-body></pre></details></div></fieldset>
<template data-brief-template>{escape(hpc.BRIEF)}</template>
<p class="pilot-local"><a href="{BRIEF_LINK}" download>Download a blank inspection brief</a> · <a href="../source/files/policies/HPC.md.html">Read the policy</a> · <a href="../source/">Get the matching project source</a></p>
<div class="pilot-form compute-read">
<h3>Read a review</h3><p>Open the JSON returned by <code>taos hpc review</code>. Your file stays in this browser.</p>
<label class="pilot-field" data-import-label hidden><span>Review file</span><input type="file" data-review-file accept=".json,application/json"></label>
<p role="status" data-report-status></p><div aria-live="polite" data-imported></div>
<details class="compute-example"><summary>Read the fictional three-sample review</summary>
<p>{escape(hpc.accounting_line(report["accounting"], len(report["outputs"])))} <a href="../source/files/examples/hpc/returns/worker-accounting.json.html">See the three recorded run times</a>.</p>
<p>{escape(report["next"])}</p><ul class="compute-rows">{example_rows}</ul>
<p><a href="{REPORT_LINK}" download>Download this review (JSON)</a></p></details>
<p>In your project, use <code>./taos hpc review campaign.json --task TASK-ID</code> to file your review. Open <code>./taos usage progress --task TASK-ID</code> to see it beside your checks and approvals.</p>
<noscript><p>Read the example here. For your own project, the command prints every finding in plain text.</p></noscript>
</div></div>"""
