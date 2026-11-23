"""Render the recorded TAOS transit workflow for people and Markdown readers."""

import json
import re
import shlex
from html import escape
from pathlib import Path

from copy_controls import copy_block
from taos_core.lifecycle import transfer_prompt


TITLE = "The morning bus report"
TRANSFER_QUESTION = "In this fictional transit service, can the operator publish Tuesday’s on-time rate? Tell me which records would change your answer."
ADAPTATION_PROMPT = ("Look at the last handoff. Suggest one check that would have caught what we missed. "
                     "Show me a case it catches and a case it misses, then let me decide whether to keep it.")
ADAPTATION_CASES = (
    ("missing", "First handoff"),
    ("repaired", "Missing trips listed"),
    ("holdout_stale", "Schedule changes"),
    ("holdout_repaired", "Handoff updated"),
)
CHAPTERS = (
    ("standard", "Set the standard"),
    ("team", "Divide the work"),
    ("correction", "Save the correction"),
    ("handoff", "Resume the audit"),
    ("change", "Change one thing"),
    ("review", "Review a version"),
)
LABELS = {
    "holds": "Holds",
    "stale": "Stale",
    "fails": "Fails",
    "unknown": "Unknown",
}
REPORT_LABELS = {
    "check": {"holds": "Passed", "stale": "Run again", "fails": "Failed"},
    "artifact": {"holds": "Inputs unchanged", "stale": "Inputs changed"},
    "acceptance": {"holds": "Approved", "stale": "Needs review"},
}
HOSTS = {"claude": "Claude", "codex": "Codex"}
CONTROLS = (
    ("style", "Edit the presentation"),
    ("source", "Correct the dispatch record"),
    ("repaired", "Rebuild and check the report"),
)


def _text(value):
    return escape(str(value))


def _person(value):
    return _text(HOSTS.get(value, value))


def _codes(values):
    return ", ".join(f"<code>{_text(value)}</code>" for value in values)


def _percent(value):
    return "Pending" if value is None else f"{value}%"


def _links(prefix):
    return (
        _text(prefix + "records/transit-workflow.json"),
        _text(prefix + "source/raw/docs/TRANSIT_WORKFLOW.md"),
    )


def _command(entry):
    command = entry["command"]
    return shlex.join(command) if isinstance(command, list) else command


def _print(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def _evidence(record, chapter, links):
    raw, method = links
    observed = []
    for key in record["scenes"][chapter]["evidence"]:
        row = record["records"][key]
        observed.append(f"""
<details class="transit-command">
  <summary><code>{_text(_command(row))}</code><span>Exit {_text(row["exit"])}</span></summary>
  <pre>{_text(_print(row["output"]))}</pre>
</details>""")
    return f"""
<details class="transit-evidence">
  <summary>Inspect the command record</summary>
  {''.join(observed)}
  <p><a href="{raw}">Full workflow record (JSON)</a> · <a href="{method}">Method and reproduction</a></p>
</details>"""


def _monday_card(monday):
    return f"""
<figure class="transit-ledger" aria-labelledby="transit-ledger-title">
  <figcaption id="transit-ledger-title">Monday morning <span>On-time share</span></figcaption>
  <div class="transit-rates">
    <div>
      <strong>{_text(_percent(monday["scheduled_percent"]))}</strong>
      <b>{_text(monday["on_time"])} of {_text(monday["scheduled"])} scheduled trips</b>
      <span>Includes cancellations</span>
    </div>
    <div>
      <strong>{_text(_percent(monday["logged_percent"]))}</strong>
      <b>{_text(monday["on_time"])} of {_text(monday["recorded"])} logged trips</b>
      <span>Rounded to a whole percent</span>
    </div>
  </div>
  <p>{_text(monday["canceled"])} canceled trips · {_codes(monday["canceled_trips"])}</p>
</figure>"""


def _intro(data):
    monday = data["monday"]
    tuesday = data["tuesday"]
    return f"""
<header class="transit-intro">
  <div class="wrap transit-intro-grid">
    <div>
      <p class="kicker">ThesisAnalysisOS (TAOS) · Recorded walkthrough</p>
      <h1>{TITLE}</h1>
      <p class="transit-lead">A transit operator wants an on-time report. Monday’s cancellations change the answer.
        Tuesday’s missing records leave the next report pending.</p>
      <p class="transit-role">The operator sets the rule and reviews each version. Codex prepares the report and Claude audits the logs.</p>
      <p class="transit-boundary">Fictional service data, real TAOS commands. The script supplied the agent and human actions.</p>
    </div>
    <div class="transit-intro-result">
      {_monday_card(monday)}
      <p class="transit-intro-tuesday"><b>Tuesday</b> {_text(_percent(tuesday["scheduled_percent"]))} ·
        Awaiting {_codes(tuesday["missing_trips"])} dispatch records.</p>
    </div>
  </div>
</header>"""


def _chapter_index():
    links = "".join(f'<li><a href="#{anchor}"><span aria-hidden="true">{number:02}</span>{title}</a></li>'
                    for number, (anchor, title) in enumerate(CHAPTERS, 1))
    return f"""
<nav class="wrap transit-nav" aria-label="Walkthrough chapters">
  <ol>{links}</ol>
</nav>"""


def _chapter(record, index, body, links):
    anchor, title = CHAPTERS[index]
    next_link = ""
    if index + 1 < len(CHAPTERS):
        next_anchor, next_title = CHAPTERS[index + 1]
        next_link = f'<a class="transit-next" href="#{next_anchor}">Next · {next_title} <span aria-hidden="true">→</span></a>'
    return f"""
<section class="transit-chapter" id="{anchor}" tabindex="-1" aria-labelledby="transit-{anchor}-heading">
  <div class="transit-chapter-head">
    <span aria-hidden="true">{index + 1:02}</span>
    <h2 id="transit-{anchor}-heading">{title}</h2>
  </div>
  <div class="transit-chapter-body">
    {body}
    {_evidence(record, anchor, links)}
    {next_link}
  </div>
</section>"""


def _rule(rule):
    return f"""<blockquote class="transit-rule">
<p>{_text(rule["quote"])}</p>
<cite><time datetime="{_text(rule["said_on"])}">{_text(rule["said_on"])}</time> ·
<span>Scope</span> <code>{_text(rule["scope"])}</code></cite>
</blockquote>"""


def _standard(data):
    monday = data["monday"]
    return f"""
<p>The operator supplies the reporting instruction. TAOS stores the operator’s words, the date, and the scope.</p>
{_rule(data["rules"]["before"][0])}
<p>On Monday, the operator’s instruction means counting all {_text(monday["scheduled"])} scheduled trips.
The {_text(monday["recorded"])} logged trips cover only the departures.</p>"""


def _team(data):
    tasks = []
    for row in data["team"]:
        tasks.append(f"""
<li><span class="transit-task-id">{_text(row["task"])}</span>
  <h3>{_text(row["title"])}</h3>
  <dl>
    <dt>Owner</dt><dd>{_person(row["owner"])}</dd>
    <dt>Responsible for</dt><dd><code>{_text(row["scope"])}</code></dd>
    <dt>Done when</dt><dd>{_text(row["done_when"])}</dd>
  </dl>
</li>""")
    return f"""
<p>Codex prepares Monday’s report. Claude audits the service logs. Their tasks share the timetable and
dispatch records. The report task links to the audit so the team can see how the work fits together.</p>
<ul class="transit-task-list">{''.join(tasks)}</ul>
<p>When Codex tries to take the same audit, TAOS tells it that Claude already owns that work.</p>"""


def _correction(data):
    rules = data["rules"]
    lesson = data["lesson"]
    proposal = data["proposal"]
    return f"""
<p>The draft uses the logged-trip rate and leaves out {_codes(data["monday"]["canceled_trips"])}.
The numerical check fails. The operator corrects the method and TAOS retrieves the revised instruction
for later work in this reporting scope.</p>
{_rule(rules["after"][0])}
<p>The earlier wording stays available for its date. A fleet maintenance query returns
{_text(len(rules["unrelated"]))} applicable instructions in the replay.</p>
<details class="transit-extra">
  <summary>Read the saved correction</summary>
  <p>{_text(lesson["words"])}</p>
  <dl class="transit-properties">
    <dt>Date</dt><dd>{_text(lesson["said_on"])}</dd>
    <dt>What went wrong</dt><dd>{_text(lesson["mistake"])}</dd>
    <dt>Why it matters</dt><dd>{_text(lesson["why"])}</dd>
    <dt>Scope</dt><dd>{_text(lesson["scope"])}</dd>
    <dt>Lesson status</dt><dd>{_text(lesson["status"])}</dd>
  </dl>
</details>
<details class="transit-extra">
  <summary>Read Claude’s proposed check</summary>
  <p>{_text(proposal["body"])}</p>
  <dl class="transit-properties">
    <dt>Status</dt><dd>{_text(proposal["status"])}</dd>
  </dl>
</details>"""


def transit_transfer(capsule):
    folder = Path(__file__).resolve().parents[1] / "examples" / "transit"
    sources = [folder / "tuesday-schedule.csv", folder / "tuesday-dispatch.csv"]
    return transfer_prompt(capsule, TRANSFER_QUESTION, sources)


def _handoff(data, prefix):
    tuesday = data["tuesday"]
    capsule = data["capsule"]
    task = capsule["task"]
    rule, = capsule["standing"]["instructions"]
    prior, = capsule["related"]
    return f"""
<p>Claude’s shift ends with two Tuesday trips unaccounted for. When Codex takes over the audit
(<code>{_text(task["id"])}</code>), this is the brief it can read.</p>
<article class="transit-brief" aria-labelledby="transit-brief-heading">
  <h3 id="transit-brief-heading">What the next agent receives</h3>
  <dl class="transit-properties">
    <dt>Goal</dt><dd>{_text(task["goal"])}</dd>
    <dt>Reporting rule</dt><dd>{_text(rule["quote"])}</dd>
    <dt>Related report</dt><dd><code>{_text(prior["id"])}</code> · {_text(prior["title"])}</dd>
    <dt>Open dispatch records</dt><dd>{_codes(tuesday["missing_trips"])}</dd>
    <dt>Tuesday rate</dt><dd>{_text(_percent(tuesday["scheduled_percent"]))}</dd>
    <dt>Next action</dt><dd>{_text(capsule["next_action"])}</dd>
  </dl>
</article>
<p>The operator has a completed Monday report. The next useful action is to resolve Tuesday’s two missing
records before reporting a Tuesday rate.</p>
<details class="transit-extra transit-prompt" id="context-packet"><summary>Give another agent this case</summary>
<p>A context packet is the part of the project a reviewer needs for one question. A transfer prompt pairs that packet with the question you want answered.</p>
<p>Ask a smaller model for the missing trip IDs. For a deeper review, give the same prompt and both tables to ChatGPT or another analyst.
Ask which trips belong in the denominator and what it can conclude while records are missing.</p>
<p><a href="{_text(prefix)}source/raw/examples/transit/tuesday-schedule.csv">Tuesday schedule (CSV)</a> ·
<a href="{_text(prefix)}source/raw/examples/transit/tuesday-dispatch.csv">Tuesday dispatch (CSV)</a></p>
<p><a href="transfer.txt">Open the plain-text transfer prompt</a> or copy it here.</p>
{copy_block("transit-transfer", transit_transfer(capsule), "Copy the Tuesday review packet")}
<p class="small">The prompt identifies these two CSVs by their exact bytes. Attach them if you want your reviewer to check the count. A changed file or question needs a fresh review.</p>
</details>
<details class="transit-extra"><summary>Read Claude’s handoff</summary><pre>{_text(data["handoff"])}</pre>
<p><a href="handoff.txt">Open the saved note as plain text</a></p></details>
<details class="transit-extra"><summary>Read the full successor capsule (JSON)</summary><pre>{_text(_print(capsule))}</pre></details>"""


def _state(kind, status):
    label = REPORT_LABELS[kind].get(status, LABELS[status])
    return f'<span class="transit-state" data-standing="{_text(status)}">{_text(label)}</span>'


def _standing(control):
    fields = (("check", "Count check"), ("artifact", "Saved report inputs"), ("acceptance", "Operator’s review"))
    return f"""
<dl class="transit-standing">
  {''.join(f'<div><dt>{label}</dt><dd>{_state(key, control[key])}</dd></div>' for key, label in fields)}
</dl>"""


def _change_paragraphs(controls):
    style, source, repaired = (controls[key] for key, _ in CONTROLS)
    return {
        "style": f'The edit touches <code>{_text(style["edited_file"])}</code>. The saved rate stays at {_text(_percent(style["report_percent"]))}. '
                 'The count used the same records, so its check still applies. The operator reviewed the old layout. The new layout needs review.',
        "source": f'The edit changes trip <code>{_text(source["edited_trip"])}</code> in <code>{_text(source["edited_file"])}</code>. '
                  f'The corrected dispatch gives {_text(_percent(source["source_percent"]))}. The saved report still reads '
                  f'{_text(_percent(source["report_percent"]))}. TAOS marks the earlier check stale. '
                  f'The check {_text(LABELS[controls["failed"]["check"]].lower())} when run on the old report.',
        "repaired": f'The rebuilt report reads {_text(_percent(repaired["report_percent"]))} and the check passes. '
                    'The saved input record and the operator’s approval still refer to the earlier report.',
    }


def _fleet_rule(records):
    fleet, = json.loads(records["fleet-rule"]["output"])
    return fleet


def _change(data, records):
    controls = data["controls"]
    descriptions = _change_paragraphs(controls)
    options = []
    for key, title in CONTROLS:
        options.append(f"""
<details class="transit-case" id="transit-case-{key}">
  <summary>{title}</summary>
  <p>{descriptions[key]}</p>
  {_standing(controls[key])}
</details>""")
    baseline = controls["baseline"]
    fleet = _fleet_rule(records)
    options.insert(1, f"""
<details class="transit-case" id="transit-case-fleet">
  <summary>Add a fleet maintenance rule</summary>
  <p>The operator adds a rule for maintenance. The reporting instruction and the Monday report’s standing stay the same.</p>
  {_rule(fleet)}
  {_standing(baseline)}
</details>""")
    return f"""
<p>Choose a recorded edit to see what TAOS reported. The baseline remains visible for comparison.</p>
<div class="transit-variants">
  <div class="transit-baseline">
    <h3>Original report · {_text(_percent(baseline["report_percent"]))}</h3>
    {_standing(baseline)}
  </div>
  <div class="transit-cases">{''.join(options)}</div>
</div>"""


def _review(data):
    controls = data["controls"]
    reviewed, rebuilt = controls["baseline"], controls["repaired"]
    approval = data["approval"]
    versions = []
    for title, row in (("Original report", reviewed), ("Rebuilt report", rebuilt)):
        versions.append(f"""
<li>
  <h3>{title} · {_text(_percent(row["report_percent"]))}</h3>
  <dl class="transit-properties">
    <dt>Count check</dt><dd>{_state("check", row["check"])}</dd>
    <dt>Operator’s review</dt><dd>{_state("acceptance", row["acceptance"])}</dd>
    <dt>Report SHA-256</dt><dd><code>{_text(row["report_sha256"])}</code></dd>
  </dl>
</li>""")
    return f"""
<p>Once the check passes, Codex moves the Monday report to review. TAOS refuses Codex’s attempt to accept it.
The operator’s recorded acceptance says “{_text(approval["note"])}”</p>
<p>After dispatch changes, a fresh check confirms {_text(_percent(rebuilt["report_percent"]))}.
The operator has reviewed only the {_text(_percent(reviewed["report_percent"]))} report.</p>
<ul class="transit-task-list transit-version-list">{''.join(versions)}</ul>
<p class="transit-decision"><strong>What needs you</strong>
  Review the rebuilt Monday report. Resolve Tuesday’s missing dispatch records before reviewing a Tuesday rate.</p>"""


def _adaptation_examples(observation):
    result = {"passes": "Passed", "fails": "Failed"}
    for key, label in ADAPTATION_CASES:
        case = observation["cases"][key]
        yield (label, ", ".join(case["named_trips"]) or "None listed",
               result[observation["checks"][key]], ", ".join(case["missing_trips"]),
               "Match" if case["matches_dispatch"] else "Differ")


def _adaptation(record, prefix):
    observation = record["observations"]["adaptation"]
    rows = "".join(
        f'<tr><th scope="row">{_text(label)}</th><td>{_text(named)}</td><td>{_text(standing)}</td>'
        f'<td>{_text(actual)}</td><td>{_text(match)}</td></tr>'
        for label, named, standing, actual, match in _adaptation_examples(observation))
    earlier = observation["cases"]["repaired"]
    changed = observation["cases"]["holdout_stale"]
    return f"""
<section class="transit-adaptation" id="adaptation" aria-labelledby="adaptation-heading">
  <h3 id="adaptation-heading">Let the next shift catch the same mistake</h3>
  <p>{_person(observation["proposer"])} suggests that each handoff list the trips still missing from dispatch.
  The operator can decline the suggestion or turn it into a check. A second AI agent,
  <code>{_text(observation["successor"])}</code>, takes over the audit.</p>
  <p>Once the operator enables the check, it catches a handoff that lists no trips.
  It passes when the agent lists {_codes(earlier["named_trips"])}.
  Then the schedule changes. The old list still passes, even though dispatch now shows
  {_codes(changed["missing_trips"])}. Comparing the IDs with dispatch catches the mistake.</p>
  <details class="transit-extra"><summary>Compare the four handoffs</summary>
    <div class="transit-audit-wrap" tabindex="0" role="region" aria-label="Handoff comparison">
    <table class="transit-audit"><caption>What the check saw and what dispatch showed</caption>
    <thead><tr><th scope="col">Handoff</th><th scope="col">Trips in the note</th><th scope="col">Format check</th>
    <th scope="col">Missing in dispatch</th><th scope="col">Do the lists match?</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
    <p>The recorded rule was inactive while it was a suggestion, after the operator declined it and
    after the operator retired it. <a href="{_text(prefix)}records/transit-adaptation.json">Inspect the commands and decisions (JSON)</a>.</p>
  </details>
  <details class="transit-extra transit-prompt"><summary>Ask your agent to try this on your project</summary>
    {copy_block("adaptation-prompt", ADAPTATION_PROMPT, "Copy the handoff review prompt")}
  </details>
</section>"""


def render_transit_exhibit(record, *, prefix="../../", adaptation=None):
    """Return an HTML fragment for the standard site shell."""
    if record.get("schema") != "transit-workflow/1":
        raise ValueError("Unsupported transit workflow record.")
    links = _links(prefix)
    raw, method = links
    data = record["observations"]
    improvement = _adaptation(adaptation, prefix) if adaptation is not None else ""
    bodies = (_standard(data), _team(data), _correction(data) + improvement, _handoff(data, prefix),
              _change(data, record["records"]), _review(data))
    chapters = "".join(_chapter(record, index, body, links) for index, body in enumerate(bodies))
    return f"""
<div class="transit-exhibit">
  {_intro(data)}
  {_chapter_index()}
  <div class="wrap transit-chapters">
    {chapters}
    <aside class="transit-end" aria-labelledby="transit-end-heading">
      <h2 id="transit-end-heading">Run the workflow locally</h2>
      <p><code>python3 evals/transit_workflow.py --verify</code></p>
      <p><a href="{method}">Method and reproduction</a> · <a href="{raw}">Full workflow record (JSON)</a></p>
    </aside>
  </div>
</div>"""


def _fenced(value):
    text = _print(value)
    delimiter = "`" * max(3, 1 + max((len(match) for match in re.findall(r"`+", text)), default=0))
    return f"{delimiter}text\n{text}\n{delimiter}"


def render_transit_markdown(record, *, prefix="../../", adaptation=None):
    """Return the six chapters with their source commands for text-first readers."""
    if record.get("schema") != "transit-workflow/1":
        raise ValueError("Unsupported transit workflow record.")
    raw, method = _links(prefix)
    data = record["observations"]
    monday, tuesday = data["monday"], data["tuesday"]
    rules, controls = data["rules"], data["controls"]
    team = "\n".join(f'- {escape(row["task"])} · {_text(row["title"])} ({_person(row["owner"])}), {_text(row["scope"])}. '
                     f'Done when {_text(row["done_when"])}' for row in data["team"])
    cases = "\n".join(f'- {title}. Saved report {_percent(controls[key]["report_percent"])}. '
                      f'Source {_percent(controls[key]["source_percent"])}. '
                      f'Check {LABELS[controls[key]["check"]]}. Artifact {LABELS[controls[key]["artifact"]]}. '
                      f'Acceptance {LABELS[controls[key]["acceptance"]]}.'
                      for key, title in (("baseline", "Original report"), *CONTROLS))
    before, after = rules["before"][0], rules["after"][0]
    fleet = _fleet_rule(record["records"])
    bodies = (
        f'Monday had {monday["on_time"]} on-time trips out of {monday["scheduled"]} scheduled '
        f'({_percent(monday["scheduled_percent"])}), or {monday["recorded"]} logged trips '
        f'({_percent(monday["logged_percent"])}, rounded). Canceled trips '
        f'{", ".join(_text(value) for value in monday["canceled_trips"])}.\n\n'
        f'Original instruction ({_text(before["said_on"])}, {_text(before["scope"])}).\n\n{_fenced(before["quote"])}',
        team,
        f'Revised instruction ({_text(after["said_on"])}, {_text(after["scope"])}).\n\n{_fenced(after["quote"])}'
        f'\n\nA fleet maintenance query returns {len(rules["unrelated"])} applicable instructions.\n\n'
        f'Saved correction.\n\n{_fenced(data["lesson"]["words"])}',
        f'Tuesday’s rate is {_percent(tuesday["scheduled_percent"]).lower()} while '
        f'{", ".join(_text(value) for value in tuesday["missing_trips"])} remain unresolved.\n\n'
        f'Next action.\n\n{_fenced(data["capsule"]["next_action"])}\n\n'
        f'[Saved handoff (plain text)](handoff.txt)\n\n{_fenced(data["handoff"])}',
        cases + f'\n\nWhen run on the original report with corrected dispatch, the check {LABELS[controls["failed"]["check"]].lower()}.'
        f'\n\nAdding a rule in {_text(fleet["scope"])} leaves the Monday report’s instruction and standing unchanged.\n\n'
        f'{_fenced(fleet["quote"])}',
        f'The original acceptance applies to report `{_text(controls["baseline"]["report_sha256"])}`. '
        f'The rebuilt report `{_text(controls["repaired"]["report_sha256"])}` passes the numerical check '
        'and awaits review.',
    )
    lines = [f"# {TITLE}", "A deterministic walkthrough. The service data is fictional. "
             "The script ran real TAOS commands and supplied the agent and human actions.",
             f"[Full workflow record (JSON)]({raw}) · [Method and reproduction]({method})"]
    for (anchor, title), body in zip(CHAPTERS, bodies):
        lines.extend((f"## {title}", body))
        if anchor == "handoff":
            lines.extend(("### Give another agent this case",
                          "Start with the [transfer prompt](transfer.txt). The context packet gives the reviewer the task, checks and evidence references. "
                          "Ask it to name the missing trip IDs. For a deeper review, supply the two tables and ask which trips belong in the denominator.",
                          f"[Tuesday schedule (CSV)]({prefix}source/raw/examples/transit/tuesday-schedule.csv) · "
                          f"[Tuesday dispatch (CSV)]({prefix}source/raw/examples/transit/tuesday-dispatch.csv)"))
        if anchor == "correction" and adaptation is not None:
            change = adaptation["observations"]["adaptation"]
            rows = "\n".join("| " + " | ".join(row) + " |" for row in _adaptation_examples(change))
            lines.extend(("### Let the next shift catch the same mistake",
                          f'{_person(change["proposer"])} proposes a handoff check. The operator declines one proposal, '
                          f'installs the next and later retires the check. The project role `{_text(change["successor"])}` receives the audit.',
                          "| Handoff | Trips in the note | Format check | Missing in dispatch | Do the lists match? |\n"
                          "| --- | --- | --- | --- | --- |\n" + rows, change["limit"],
                          f"[Inspect the commands and decisions (JSON)]({prefix}records/transit-adaptation.json)",
                          "Ask your agent:", _fenced(ADAPTATION_PROMPT)))
        lines.append("### Command record")
        for key in record["scenes"][anchor]["evidence"]:
            row = record["records"][key]
            lines.append(_fenced(f'$ {_command(row)}\n{_print(row["output"])}\nExit {row["exit"]}'))
    return "\n\n".join(lines) + "\n"
