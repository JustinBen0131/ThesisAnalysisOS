"""A local pilot worksheet shared by the interactive form and its plain-text download."""
from html import escape

import hpc_review


TITLE = "Plan a pilot for your own work"
INTRO = ("Pick one input that represents the work you intend to run. This worksheet helps you decide "
         "whether a pilot is needed, agree on its limits and check its output before scaling up.")
TEMPLATE_LINK = "pilot-worksheet.md"
FIELDS = (
    ("sample", "Representative input", "Name a typical input and what makes it representative. Pilot unusually large inputs separately."),
    ("recipe", "Command or workflow version", "Record the code, settings and input version someone else would need."),
    ("output", "Expected output", "Name the file, table or other result the pilot should produce."),
    ("check", "Independent pass condition", "Name an observable test and its expected value or tolerance."),
    ("authority", "Resource limit and approver", "Name who can approve the pilot and the time, memory or spending limit."),
)
MEASURES = (
    ("minutes", "Elapsed minutes per job", "0", "any"),
    ("peak", "Peak memory per job (GiB)", "0", "any"),
    ("output_mib", "Output per job (MiB)", "0", "any"),
    ("jobs", "Independent jobs remaining", "1", "1"),
    ("parallel", "Approved parallel jobs", "1", "1"),
    ("allowance", "Memory limit per job (GiB)", "0", "any"),
    ("space", "Space for new outputs (GiB)", "0", "any"),
)
ESTIMATE_NOTE = ("Use measurements from comparable independent jobs. The estimate assumes one job per input, "
                 "similar durations and enough slots for the stated concurrency. Queue waits, startup delays, "
                 "temporary storage and cloud charges need a separate allowance.")
ENVIRONMENTS = (
    ("shared", "Shared cluster", "Confirm the allocation, queue time limit and allowed parallel jobs with the project or site operator."),
    ("cloud", "Cloud project", "Confirm the maximum spend, timeout and parallel jobs with the project’s budget owner."),
    ("personal", "Personal workstation", "Reserve memory and disk for your other work. You can name yourself as the approver."),
)


def worksheet():
    lines = ["# HPC run review", "", hpc_review.reading(), f"## {TITLE}", "", INTRO, "", "## Before the pilot", "",
             "- Where will this run, and who can authorize it?",
             "- What did you search for, and how did its inputs, code, settings and previous checks compare?",
             "- If an equivalent checked result exists, record its reference and reuse it.", ""]
    lines.extend(f"- {name} — {hint}" for _, name, hint in FIELDS)
    lines.extend(["", "Start with one representative input. A passed pilot and an explicit resource decision are required before expanding.",
                  "", "## After the pilot", "", "- Record the actual command, exit report, location of the output and the observed check result.",
                  "- If the output failed, hold the larger run. Inspect the affected input, log and output before proposing a retry.",
                  "- If the output is unchecked, run the agreed test first.", "", "For a passed pilot, record the following.", ""])
    lines.extend(f"- {name}" for _, name, _, _ in MEASURES)
    lines.extend(["", "Estimate batches of simultaneous jobs by dividing the remaining jobs by the approved concurrency and rounding up. "
                  "Multiply that number by the pilot minutes for an estimated run time. Multiply the MiB per job by the remaining jobs "
                  "and divide by 1,024 for the new output in GiB. Compare peak memory with the per-job limit and new output with available space.",
                  "", ESTIMATE_NOTE, "", "Identify what would make you pause. Record the owner’s decision and a link to the evidence before a larger run.", ""])
    return "\n".join(lines)


def _entry(key, label, note):
    return (f'<label class="pilot-field"><span>{escape(label)}</span>'
            f'<input type="text" autocomplete="off" name="{key}" maxlength="300" required aria-describedby="pilot-{key}-hint">'
            f'<small id="pilot-{key}-hint">{escape(note)}</small></label>')


def _result(key, label):
    return f"""<div class="pilot-result" data-result hidden><h4 tabindex="-1"></h4><div data-reading></div>
<div class="pilot-export"><button type="button" data-copy aria-controls="pilot-{key}-text">Copy {label}</button>
<span role="status" data-copy-status></span></div><details class="pilot-plain"><summary>View plain text</summary>
<pre><code id="pilot-{key}-text"></code></pre></details></div>"""


def render_planner():
    locations = "".join(f'<option value="{key}" data-guidance="{escape(note, quote=True)}">{label}</option>'
                        for key, label, note in ENVIRONMENTS)
    fields = "".join(_entry(*field) for field in FIELDS)
    numbers = "".join(f'<label class="pilot-field"><span>{label}</span>'
                      f'<input type="number" name="{key}" min="{minimum}" step="{step}" required></label>'
                      for key, label, minimum, step in MEASURES)
    return f"""<section class="hpc-section hpc-planner wrap" aria-labelledby="hpc-pilot">
<h2 id="hpc-pilot">Review your own run</h2>{hpc_review.render()}
<details class="compute-manual"><summary>Plan a pilot by hand</summary><p class="hpc-section-intro">{INTRO}</p>
<p class="pilot-local">Entries stay in this tab. <a href="{TEMPLATE_LINK}" download>Download the blank worksheet (Markdown)</a></p>
<div data-planner hidden>
<fieldset class="pilot-form" data-run-sheet aria-labelledby="pilot-before-heading">
<div class="pilot-form-head"><h3 id="pilot-before-heading">Before the pilot</h3><button type="button" class="pilot-example" data-example>Fill with a fictional example</button></div>
<label class="pilot-field"><span>Could you reuse a checked result?</span><select name="reuse">
<option value="unknown">I still need to check</option><option value="match">I found an equivalent checked result</option>
<option value="new">I checked. A new run is needed.</option></select></label>
<label class="pilot-field"><span data-basis-label>Where will you look?</span>
<input name="basis" type="text" autocomplete="off" maxlength="300" aria-describedby="pilot-basis-hint">
<small id="pilot-basis-hint">An earlier run sheet, a results folder or a teammate’s handoff.</small></label>
<fieldset data-new-fields hidden disabled><legend>Define one representative run</legend>
<label class="pilot-field"><span>Where will it run?</span><select name="setting" required><option value="">Choose a setting</option>{locations}</select>
<small data-setting-note>Choose the setting to see which limits to agree on.</small></label>
<div class="pilot-grid">{fields}</div></fieldset>
<button class="pilot-primary" type="button" data-build>Build my run sheet</button>{_result("sheet","run sheet")}</fieldset>
<details class="pilot-after"><summary>After the pilot · Review results and estimate the next batch</summary>
<fieldset class="pilot-form" data-batch-review aria-labelledby="pilot-after-heading">
<div class="pilot-form-head"><h3 id="pilot-after-heading">Review a measured pilot</h3><button type="button" class="pilot-example" data-example>Use sample measurements</button></div>
<label class="pilot-field"><span>Did the output pass the agreed check?</span><select name="outcome">
<option value="unchecked">The output is unchecked</option><option value="failed">The output failed</option><option value="passed">The output passed</option>
</select></label><label class="pilot-field"><span>Observed result or evidence reference</span><input name="evidence" type="text" autocomplete="off" maxlength="300"
aria-describedby="pilot-evidence-hint"><small id="pilot-evidence-hint">For example, the counted records and the input you checked them against.</small></label>
<label class="pilot-toggle" data-estimate-choice hidden><input type="checkbox" name="estimate" disabled>Estimate a larger batch using my measurements</label>
<fieldset data-measurements hidden disabled><legend>Measurements and limits for the proposed batch</legend>
<p>{ESTIMATE_NOTE}</p><div class="pilot-numbers">{numbers}</div></fieldset>
<button class="pilot-primary" type="button" data-build>Review the next step</button>{_result("batch","batch review")}</fieldset></details></div>
<noscript><p>The worksheet includes the reuse check, the run sheet, the output test and the calculations for estimating a larger batch.</p></noscript>
</details></section>"""
