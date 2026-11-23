"""A five-decision workshop shared by the interactive and text editions."""
from html import escape
from io import StringIO
from typing import NamedTuple

from copy_controls import copy_block
from demo_walkthrough import chapters, only
from first_lesson import lesson
from taos_core.demo import write as write_terminal_demo
from taos_core.handoff import REQUIRED_SECTIONS


class Case(NamedTuple):
    anchor: str
    title: str
    question: str
    choices: tuple
    finding: str
    source_text: str
    links: tuple


TITLE = "What would you check next?"
INTRO = ("A pendulum was timed at six lengths to estimate gravity. Take the reviewer’s seat. "
         "Choose a move, see what the record supports, then try the same question on your own work.")
PROMPT = """Help me review one result in my project.

1. Identify the claim, the check, and the inputs the check read. Tell me which earlier result still holds, went stale, failed, or has unknown standing. Give the reason.
2. Make a context packet for a second reviewer. Include my question, my exact instruction, the current evidence, the open question and the source material the reviewer can actually read.
3. With my permission, ask a second reviewer for up to three possible explanations. For each, ask for a prediction and the observation that would distinguish it. Show which checks we can run before adopting an explanation.
4. For a hands-on handoff, record the state, what changed, evidence, risks and open questions, and the literal next command with its working directory.
5. If a new project rule would help, propose it with a case it catches and one it misses. Let me decide whether to enable it.

When using TAOS, start with ./taos why TASK and ./taos capsule TASK. Use ./taos handoff --help to prepare a handoff and ./taos propose --help to draft a rule for my review.

Worked examples
https://whatstillholds.com/records/demo.json
https://whatstillholds.com/evidence/model-evaluation/
https://whatstillholds.com/workflows/transit/#adaptation"""
PROJECTS = (
    ("Research or analysis", "Can the corrected readings reproduce the reported estimate?",
     './taos use ../analysis --check "fit: python3 analysis/check.py"'),
    ("Code", "Which test would catch the bug if it returned?",
     './taos use ../app --check "tests: python3 -m unittest discover"'),
    ("Writing", "Can a reader follow every citation in this draft to a source?",
     './taos use ../paper --check "references: python3 check_references.py"'),
    ("Schoolwork", "Do the numbers in the science fair report match the spreadsheet?",
     './taos use ../science-fair --check "numbers: python3 compare.py"'),
    ("Model evaluation", "Does each instrument meet its threshold after the labels change?",
     './taos use ../evaluation --check "groups: python3 check_groups.py"'),
)
PROJECT_NOTE = ("From a fresh ThesisAnalysisOS copy, ./taos use ../my-project suggests checks it recognizes. "
                "Choose one, or supply your own with --check. The commands below are examples. "
                "Each copy keeps one project’s record.")


def cases(record, audit, capsule_text=None):
    scenes = {scene.anchor: scene for scene in chapters(record, audit)}
    prior = dict(scenes["run-1"].facts)["Gravity ± standard error"]
    revised = dict(scenes["run-4"].facts)["Revised gravity ± standard error"]
    timing = dict(scenes["run-3"].facts)
    told = only((step for moment in record["moments"] for step in moment["steps"]
                 if step.get("id") == "told"), "instruction at the next start")
    instruction = only((line.strip() for line in told["printed"] if line.lstrip().startswith("told:")),
                       "dated instruction in the new session")
    packet_size = ""
    if capsule_text:
        transcript = StringIO()
        write_terminal_demo(record, transcript, full=True, width=None, color=False)
        full_size = len(("\ufeff" + transcript.getvalue()).encode("utf-8"))
        packet_size = (f" In this run, the published task brief is {len(capsule_text.encode('utf-8')):,} bytes "
                       f"and the printed transcript is {full_size:,} bytes. Those are UTF-8 file sizes.")
        fields = ("goal:", "next:", "told:")
        excerpt = [line for line in capsule_text.splitlines() if line.startswith(fields)
                   or (line.startswith("stands:") and "check fit:" in line)]
        if not capsule_text.startswith("PEN-2 ") or not all(any(line.startswith(key) for line in excerpt)
                                                            for key in fields):
            raise ValueError("Expected the goal, next step and dated instruction in the PEN-2 context packet")
        packet = "Selected lines from ./taos capsule PEN-2\n" + "\n".join(excerpt)
    else:
        packet = f"Instruction shown to the next researcher in the demo\n{instruction}"
    handoff = "\n".join(REQUIRED_SECTIONS)
    rows, *_ = lesson(record, audit)
    return (
        Case("standing", "Which edit matters?",
             f"The first estimate was {prior}. The plot colours changed, then one timing changed "
             f"from {timing['Earlier timing']} to {timing['Corrected timing']}. May the lab reuse its first pass?",
             (("Keep the pass because the timing correction is small.",
               "The size of the edit tells you nothing about whether the check still passes. Compare the inputs and repeat the affected check."),
              ("Repeat the entire analysis after each edit.",
               "A repeat could recover the answer. The plot colour was outside the fit’s recorded inputs, so its earlier pass still holds."),
              ("Find which edit touched a fit input. Recheck after that edit.",
               "The timing file was an input. The colour file was outside the fit. The fit needed a fresh check only after the timing correction.")),
             f"The first pass went stale when the timing changed. The rerun passed at {revised}.",
             "Terminal demo, selected rows\n" + "\n".join(rows) + "\n\n"
             "holds · the saved basis still matches\nstale · a recorded dependency changed\n"
             "fails · the check ran on these inputs and failed\nunknown · the record cannot establish an answer\n\n"
             "A check can pass even if the experiment asks the wrong question. With isolated: true, a check runs "
             "in a temporary folder containing its declared project files. If it needs a missing file, its read fails. "
             "Use isolated: strict to require every isolation control.",
             (("Compare the two timing corrections", "evidence/pendulum/#readings-row-6-1.05"),
              ("Open the terminal run (JSON)", "records/demo.json"))),
        Case("context-packet", "What goes in the context packet?",
             "Another agent will review the revised fit without access to your laptop. What would let it question the estimate?",
             (("Send your full chat with links to the files on your machine.",
               "The history may explain your choices. A reviewer without your filesystem still needs readable copies of the inputs."),
              ("Send the question, dated instruction, six readings, fit method and current check.",
               "That packet gives the reviewer a question, a decision rule and material for an independent calculation. Identify anything you could not include."),
              ("Send the new value, its uncertainty and the passing verdict.",
               "That describes the outcome. A reviewer cannot independently recover the fit or inspect a timing error from those three items.")),
             "TAOS can assemble the task record. Include the source rows and method your reviewer needs to test its claims." + packet_size,
             packet,
             (("Read the full task brief", "records/pendulum-capsule.txt"),
              ("Read the full terminal transcript", "records/demo-transcript.txt"),
              ("Inspect the recorded instruction", "records/demo.json"),
              ("Open a worked reviewer prompt", "workflows/review/reviewer-prompt.txt"),
              ("Inspect its source attachments", "workflows/review/reviewer-sources.md"))),
        Case("hypotheses", "What would distinguish two explanations?",
             "A larger timing correction puts gravity below the example’s limit. You have a context packet and a small model or ChatGPT. What do you ask it to do?",
             (("Suggest explanations and name an observation that would separate them.",
               "For example, a transcription error could change one row. A timing-unit error could affect every row. Compare the source entries and refit before choosing."),
              ("Rank the explanations and use the most confident one in the report.",
               "A ranking can guide which row to inspect first. It supplies no measurement of how that row was recorded."),
              ("Ask several models separately and take the most common explanation.",
               "Agreement gives you a candidate to test. The models can share the same blind spot when they read the same packet.")),
             "Use the model to generate testable ideas. The six-row comparison measures the effect of a changed input. It cannot establish what caused the timing change.",
             f"Larger correction in the audit\nChanged timing: {scenes['run-3'].comparisons[1][1]}\n"
             f"Fresh estimate: {scenes['run-3'].comparisons[1][2]}\nCheck: {scenes['run-3'].comparisons[1][3]}",
             (("Inspect the larger correction", "evidence/pendulum/#readings-row-6-1.05"),
              ("Read the raw measurements (JSON)", "records/measurement_audit.json"))),
        Case("transfer-prompt", "What should the transfer prompt ask?",
             "First you want an independent opinion. Tomorrow another agent with project access will pick up the work. What changes between the two requests?",
             (("Send both agents the fitted value and ask for their next step.",
               "The reviewer needs inputs to challenge the value. The person continuing the work also needs to know where to resume."),
              ("Send both the handoff file path and the last command.",
               "A teammate with access can open it. An outside reviewer cannot inspect a path on your machine, and needs a concrete question."),
              ("Give the reviewer an evidence packet. Give the successor the saved handoff and the literal next command.",
               "Ask the reviewer to challenge a particular claim. Tell the successor what changed, what remains open and which command to run from which folder.")),
             "For example, ask whether a passing pooled rate justifies using every instrument. The study reports A dropping from 3/4 to 2/4 while the pooled result stays at 6/8. Omit B’s corrected rows and the reviewer cannot independently check that pooled count.",
             'Independent review, from the configured example project\n'
             './taos capsule QC-1 --transfer "Does each instrument meet the requirement?"\n\n'
             f"Headings in a saved handoff\n{handoff}\n\n"
             "Prepare a wrapper in the project that holds the saved handoff. Replace HANDOFF.md with its path.\n"
             "./taos handoff wrapper HANDOFF.md --to claude\n\n"
             "Example next command from the configured TAOS folder\n./taos why QC-1 --check",
             (("Try the reviewer prompt", "workflows/review/reviewer-prompt.txt"),
              ("Check the instrument readings", "evidence/model-evaluation/"),
              ("Read a saved transit handoff", "workflows/transit/#handoff"),
              ("Open the transit run (JSON)", "records/transit-workflow.json"))),
        Case("project-rule", "When should a suggestion become a rule?",
             "A transit team loses track of missing bus trips between shifts. An AI agent proposes requiring a list of trip IDs in each handoff. What would you want to see before enabling it?",
             (("Install the check as soon as it catches the empty list.",
               "That catches one omission. A filled-in list from yesterday can still pass while naming the wrong trips."),
              ("Try an empty list and an outdated list, then let the operator decide.",
               "The recorded check caught the empty handoff and accepted an outdated list. An operator can see exactly what that check covers before promoting it."),
              ("Decline the idea until a check can guarantee a correct report.",
               "A narrow check can still help. Name the missing comparison with dispatch so the operator can decide whether the narrower check is worthwhile.")),
             "In the recorded transit exercise, the agent could propose the check. The operator could reject it, promote it or retire it. Comparing IDs with current dispatch exposed the stale list.",
             "The operator’s promotion step, with the proposal ID as a placeholder\n"
             "./taos atoms promote PROPOSAL_ID --by human\n\n"
             "The check verified that a list was present. The reviewer compared its contents with dispatch.",
             (("Compare the four handoffs", "workflows/transit/#adaptation"),
              ("Inspect the commands and decisions (JSON)", "records/transit-adaptation.json"))),
    )


def case_html(case, number, prefix):
    actions = "".join(
        f'<details class="review-choice"><summary>{escape(label)}</summary>'
        f'<p>{escape(feedback)}</p></details>' for label, feedback in case.choices)
    links = "".join(f'<li><a href="{escape(prefix + url)}">{escape(label)}</a></li>' for label, url in case.links)
    return f"""
<details id="review-{case.anchor}" class="review-case">
<summary><span class="review-number">Decision {number} / 5</span><span>{escape(case.title)}</span></summary>
<div class="review-body"><p class="review-question">{escape(case.question)}</p>
<div class="review-choices" role="group" aria-label="Choose a response">{actions}</div>
<details class="review-proof"><summary>Exactly how · check the evidence</summary>
<p>{escape(case.finding)}</p><pre>{escape(case.source_text)}</pre><ul>{links}</ul></details>
</div></details>"""


def render_practice(demo_record, audit, *, prefix="../../", capsule_text=None):
    heading = "h1" if prefix else "h2"
    decisions = "".join(case_html(case, num, prefix) for num, case in enumerate(cases(demo_record, audit, capsule_text), 1))
    projects = "".join(f'<details><summary>{escape(name)}</summary><p>{escape(question)}</p>'
                       f'<pre>{escape(command)}</pre></details>' for name, question, command in PROJECTS)
    return f"""
<div class="review-workshop wrap">
<header class="review-head"><p class="review-kicker">Reviewer workshop</p>
<{heading}>{TITLE}</{heading}><p class="lead">{escape(INTRO)}</p>
<div class="review-actions"><a class="review-start" href="#review-standing">Try the first decision</a>
<a href="#review-takeaway">Get the reusable prompt</a>
<button type="button" class="review-depth" aria-pressed="false" hidden>Full detail</button></div></header>
<div class="review-cases">{decisions}</div>
<section id="review-takeaway" class="review-takeaway"><h2>Take the review prompt with you</h2>
<p>Paste this into a conversation with your AI agent, then add one result you want it to review.</p>
{copy_block("review-takeaway-prompt", PROMPT, "Copy the review prompt")}</section>
<section class="review-projects"><h2>Try it on your project</h2><p>{escape(PROJECT_NOTE)}</p>
{projects}</section></div>"""


def practice_markdown(demo_record, audit, *, prefix="../../", capsule_text=None):
    lines = [f"# {TITLE}", "", INTRO, ""]
    for number, case in enumerate(cases(demo_record, audit, capsule_text), 1):
        lines.extend([f"## Decision {number}. {case.title}", "", case.question, ""])
        for choice, feedback in case.choices:
            lines.extend([f"- **{choice}** {feedback}"])
        lines.extend(["", case.finding, "", "```text", case.source_text, "```", ""])
        lines.extend(f"- [{label}]({prefix}{url})" for label, url in case.links)
        lines.append("")
    lines.extend(["## Take the review prompt with you", "", "```text", PROMPT, "```", "",
                  "## Try it on your project", "", PROJECT_NOTE, ""])
    for name, question, command in PROJECTS:
        lines.extend([f"### {name}", "", question, "", "```sh", command, "```", ""])
    return "\n".join(lines)
