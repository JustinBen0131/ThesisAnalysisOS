"""Replay four decisions from the terminal demo and show six questions a visitor can ask."""

from html import escape
from io import StringIO

from demo_walkthrough import chapters, only, require
from taos_core.page import Page, short


QUESTIONS = (
    ("What needs my attention?", "../os/taos status",
     "A project summary with task counts, decisions you owe and warnings about work that needs another look."),
    ("Why is this result stale?", "../os/taos why TASK-1",
     "The task’s saved checks and what changed. In the timing example it names data/swings.csv."),
    ("Check it again.", "../os/taos gate run --task TASK-1 --agent human",
     "A row for each check says whether it ran or reused a pass. After a timing edit the fit runs again."),
    ("I’ve reviewed this version. Can I sign off?",
     '../os/taos task accept TASK-1 --by human --note "I reviewed the fit"',
     "Once the task is in review or done, run this yourself to record your acceptance for its current files and instructions."),
    ("Use the laser-measured lengths from March 1.",
     '../os/taos rule add --quote "Use the laser-measured lengths" --said-on 2026-03-01 --scope TASK-1 --by human',
     "It saves your words with that date and prints the instruction’s ID and the task it applies to."),
    ("How do I start with my own project?",
     '../os/taos --home ../os use . --prefix TASK --check "python3 analysis/check.py" --reads analysis --reads data',
     "In the toy folder this creates TASK-1, lists the setup files it wrote, runs the check and prints its result."),
)

INTRO = ("This example estimates gravity from a pendulum timed at six lengths. "
         "Which edit would make you check the estimate again?")
GUIDE = ("These examples use a disposable copy of examples/measurement called toy, beside a fresh ThesisAnalysisOS folder "
         "called os. Run the setup in the last answer from inside toy first. Then the other commands work there.")
AUDIENCE = ("If you return to an analysis, a report or a piece of software after the files change, "
            "The system shows which earlier results you can keep and which checks need to run again.")
REQUIREMENTS = ("On macOS or Linux you need Git and Python 3.9 or newer. Type the commands yourself or ask an AI agent "
                "that can run them. Reading the notebook locally needs no account, network connection or model call.")


def conversation(original, corrected):
    return (
        ("What changed in the gravity estimate?", "taos why",
         f"The recorded estimate was {original}. One swing time changed in data/swings.csv, so that estimate needs a new check."),
        ("Run the check on the corrected timing.", "taos gate run",
         f"The new estimate is {corrected}. It passes the example’s check."),
        ("I’ve read the new result. I accept this version.", "taos task accept",
         "Your acceptance is recorded for the version you reviewed. A later edit shows up when someone checks that acceptance."),
    )


STEPS = ("baseline", "style-only", "timing-edited", "rerun")
ACTIONS = ("Starting result", "Change the plot colour", "Correct one timing", "Run the check again")


def lesson(record, audit):
    scenes = chapters(record, audit)
    runs = [step for moment in record["moments"] for step in moment["steps"] if step["kind"] == "run"]
    rows = []
    short_view = StringIO()
    short(Page(short_view, width=None, color=False), record)
    printed_rows = short_view.getvalue().splitlines()
    for key, expected in zip(STEPS, ("holds", "holds", "stale", "holds")):
        step = only((run for run in runs if run.get("id") == key), key)
        require(step.get("answer") == expected and step.get("brief"), f"missing short answer for {key}")
        # Match the program's own unwrapped rendering, including its column spacing.
        row = only((line.strip() for line in printed_rows if line.strip().endswith(step["brief"])), key + " terminal row")
        require(row.split(None, 1) == [expected, step["brief"]], f"inconsistent short answer for {key}")
        rows.append(row)
    for index, moment in ((0, "standing"), (3, "reuse")):
        steps = only((m["steps"] for m in record["moments"] if m["id"] == moment), moment)
        fit = only((s for s in steps if s.get("command") == "python3 analysis/fit.py"), moment + " fit")
        value = fit["printed"][0].split(" m/s^2")[0]
        require(rows[index].endswith(value), "the quoted short row disagrees with the measured estimate")
    original = scenes[0].facts[1][1]
    terminal, larger = scenes[2].comparisons
    old_period = scenes[2].facts[0][1]
    explanations = (
        "The original six timings passed the fit check.",
        "Only the plot colour changed. The gravity calculation still uses the same six timings.",
        f"One timing changed from {old_period} to {terminal[1]}. The displayed estimate used the old timing.",
        f"The fit ran on the corrected timing and passed. Its new gravity estimate is {terminal[2]}.",
    )
    contrast = (f"The terminal example changes the timing to {terminal[1]} and passes. "
                f"A separate audit changes the same timing to {larger[1]}, "
                f"giving {larger[2]}. That fit fails the check.")
    return rows, explanations, original, terminal[2], contrast, larger[4]


def render_lesson(record, audit):
    rows, stories, original, revised, contrast, readings_link = lesson(record, audit)
    row_list = "".join(
        f'<li data-step="{key}" data-state="{escape(row.split()[0])}" data-value="{escape(value)}">'
        f'<strong>{title}</strong><p>{escape(story)}</p><code>{escape(row)}</code></li>'
        for key, title, row, story, value in zip(STEPS, ACTIONS, rows, stories, [original] * 3 + [revised]))
    buttons = "".join(f'<button type="button" data-pick="{key}">{title}</button>'
                      for key, title in zip(STEPS[1:], ACTIONS[1:]))
    questions = "".join(f'<details><summary>{escape(question)}</summary><code>{escape(command)}</code>'
                        f'<p>{escape(answer)}</p></details>' for question, command, answer in QUESTIONS)
    exchange = "".join(f'<li><p class="lesson-ask"><b>You</b> {escape(ask)}</p>'
                       f'<p class="lesson-reply"><b>AI agent</b> {escape(answer)} '
                       f'<code>{escape(command)}</code></p></li>'
                       for ask, command, answer in conversation(original, revised))
    return f'''<section id="first-lesson" aria-labelledby="first-lesson-title">
<h2 id="first-lesson-title">A pendulum, a stopwatch and one corrected number</h2>
<p>{INTRO}</p>
<div class="lesson-bench">
<div class="lesson-reading">
<span class="lesson-instrument" aria-hidden="true"><i></i></span>
<div><small>Estimated gravity ± standard error</small>
<strong data-display="value">{escape(original)}</strong><span data-display="state">holds</span></div></div>
<p data-display="reason" aria-live="polite" aria-atomic="true">{stories[0]}</p>
<p class="small">Plot colour <i class="lesson-swatch" aria-hidden="true"></i></p>
<div class="lesson-actions" hidden>{buttons}<button type="button" data-pick="reset">Start over</button></div>
<ol class="lesson-log" aria-label="Replayed terminal output" hidden></ol>
<details class="lesson-transcript"><summary>Read the four terminal rows</summary><ol>{row_list}</ol></details>
</div>
<p class="small">Replay of a recorded run. <a href="records/demo.json">Inspect the command record</a>
 · <a href="#run-1">See every step</a></p>
<p class="small">{escape(contrast)} <a href="{escape(readings_link)}">Compare the timings</a>
 · <a href="evidence/#handoff-request-3">See the failed handoff check</a></p></section>
<section id="ask-taos" aria-labelledby="ask-taos-title">
<h2 id="ask-taos-title">How you talk to it</h2>
<p>Here’s an example conversation about the corrected timing. The numbers come from the recorded run.</p>
<ol class="lesson-exchange" aria-label="Example conversation">{exchange}</ol>
<h3>Six things you can ask</h3>
<p>Ask in your own words. Open a question to see the command and what comes back.</p>
<div class="lesson-questions">{questions}</div>
<p class="small">{GUIDE}</p>
<h3>Is it for me?</h3><p class="lesson-audience">{AUDIENCE}</p>
<p class="small lesson-audience">{REQUIREMENTS}</p></section>'''


def lesson_markdown(record, audit):
    rows, stories, original, revised, contrast, readings_link = lesson(record, audit)
    lines = ["## A pendulum, a stopwatch and one corrected number", "", INTRO, ""]
    for title, story, row in zip(ACTIONS, stories, rows):
        lines.extend([f"**{title}.** {story}", "", "```text", row, "```", ""])
    lines.extend(["[Inspect the command record](records/demo.json)", "", contrast,
                  f"[Compare the timings]({readings_link}) · [See the failed handoff check](evidence/#handoff-request-3)",
                  "", "## How you talk to it", "", "An example conversation about the corrected timing.", ""])
    for ask, command, answer in conversation(original, revised):
        lines.extend([f"**You** · {ask}", "", f"**AI agent** · {answer} (`{command}`)", ""])
    lines.extend(["### Six things you can ask", "", GUIDE, ""])
    for question, command, answer in QUESTIONS:
        lines.extend([f"**{question}**", "", "```sh", command, "```", "", answer, ""])
    lines.extend(["### Is it for me?", "", AUDIENCE, "", REQUIREMENTS, ""])
    return "\n".join(lines)
