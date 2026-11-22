"""Render the sequential pendulum handoff from the saved measurements."""

import csv
import hashlib
import json
import runpy
from decimal import Decimal, InvalidOperation
from html import escape
from io import StringIO
from pathlib import Path

HANDOFF_RECORD = "evals/results/handoff_audit.json"
HANDOFF_METHOD = "docs/HANDOFF_AUDIT.md"
HANDOFF_RUNNER = "evals/handoff_audit.py"
LABELS = {
    "baseline": "Original six swings",
    "style-only": "Edit the plot style",
    "measurement-fails": "Change period {number} from {before} s to {after} s",
    "new-task-sees-failure": "A third task starts on those readings",
    "restore-exact-bytes": "Restore the original CSV",
    "same-values-new-bytes": "Write {after} s instead of {before} s for period {number}",
    "share-respelled-pass": "Ask from another task on the same CSV",
}
STATES = {"holds": "Earlier pass holds", "stale": "Earlier result is stale",
          "fails": "Known failure", "unknown": "No applicable result"}
AFTER = {"holds": "Holds", "stale": "Stale", "fails": "Fails", "unknown": "Unknown"}


def load_handoff(repo):
    """Check that every recorded source still matches before showing the results."""
    root = repo.resolve()
    record = json.loads((root / HANDOFF_RECORD).read_text(encoding="utf-8"))
    if record.get("schema") != "pendulum-handoff-audit/1":
        raise ValueError("Unsupported pendulum handoff record.")
    expected = {HANDOFF_RUNNER, "bootstrap/answers.example.json"}
    expected.update(p.relative_to(root).as_posix() for p in (root / "taos_core").glob("*.py"))
    expected.update(p.relative_to(root).as_posix() for p in (root / "examples/measurement").rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts)
    sources = record.get("sources")
    if not isinstance(sources, dict) or set(sources) != expected:
        raise ValueError("Pendulum handoff sources do not match the input roster.")
    for name, fingerprint in sources.items():
        source = (root / name).resolve()
        source.relative_to(root)
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != fingerprint:
            raise ValueError(f"Pendulum handoff source missing or changed: {name}")

    rows = record["observations"]
    if [row["id"] for row in rows] != list(LABELS):
        raise ValueError("Pendulum handoff steps differ from the recorded design.")
    seen = set()
    for number, row in enumerate(rows, 1):
        if (row["sequence"] != number or row["before"] not in STATES or row["after"] not in AFTER
                or row["execution"] not in ("execute", "reuse")):
            raise ValueError(f"Invalid pendulum handoff step: {row['id']}")
        if row["execution"] == "execute" and row["execution_origin"] == row["id"]:
            seen.add(row["id"])
        elif row["execution"] != "reuse" or row["execution_origin"] not in seen:
            raise ValueError(f"Invalid pendulum handoff receipt: {row['id']}")
    counts = {
        "gate_requests": len(rows), "executions": len(seen), "reused": len(rows) - len(seen),
        "exit_1": sum(row["exit"] == 1 for row in rows),
    }
    if counts != record["counts"]:
        raise ValueError("Pendulum handoff counts disagree with the recorded requests.")
    runpy.run_path(str(root / "evals/review_handoff_audit.py"))["verify"](root, record)
    return record


def _labels(observations):
    labels = dict(LABELS)
    if ([row["id"] for row in observations] != list(labels)
            or [row["sequence"] for row in observations] != list(range(1, len(labels) + 1))):
        raise ValueError("Expected the recorded handoff steps in chronological order.")
    for previous, current in zip(observations, observations[1:]):
        step = current["id"]
        if step not in ("measurement-fails", "same-values-new-bytes"):
            continue
        tables = []
        for observation in (previous, current):
            table = list(csv.reader(StringIO(observation["csv_text"]), strict=True))
            if not table or table[0] != ["length_m", "period_s"] or any(len(row) != 2 for row in table[1:]):
                raise ValueError(f"{step}: expected length_m and period_s columns.")
            tables.append(table[1:])
        old, new = tables
        if [row[0] for row in old] != [row[0] for row in new]:
            raise ValueError(f"{step}: pendulum lengths or row order changed.")
        changes = [(n, left[1], right[1]) for n, (left, right) in enumerate(zip(old, new), 1) if left[1] != right[1]]
        if len(changes) != 1:
            raise ValueError(f"{step}: expected exactly one period cell to change.")
        number, before, after = changes[0]
        try:
            a, b = Decimal(before), Decimal(after)
        except InvalidOperation as exc:
            raise ValueError(f"{step}: expected numeric periods.") from exc
        if not (a.is_finite() and b.is_finite() and a > 0 and b > 0):
            raise ValueError(f"{step}: expected finite positive periods.")
        if (a != b) != (step == "measurement-fails"):
            raise ValueError(f"{step}: period values disagree with the recorded kind of edit.")
        labels[step] = labels[step].format(number=number, before=before, after=after)
    return labels


def _summary(record):
    counts = record["counts"]
    message = (f'Across {counts["gate_requests"]} requests, the fit ran {counts["executions"]} times '
               f'and reused an earlier result {counts["reused"]} times.')
    if record["expectation_mismatches"]:
        message += " The raw record lists differences from the predictions."
    return message


def _request(row, numbers):
    if row["execution"] == "reuse":
        result = 'pass' if row['exit'] == 0 else 'failure'
        return f'Reused the {result} from request {numbers[row["execution_origin"]]}'
    result = "passed" if row["exit"] == 0 else "failed"
    return f'Ran and {result} (exit {row["exit"]})'


def handoff_section(record):
    observations = record["observations"]
    labels = _labels(observations)
    numbers = {row["id"]: row["sequence"] for row in observations}
    rows = []
    for row in observations:
        number, task = row["sequence"], row["task"]
        label = escape(labels[row["id"]])
        reason = escape(row["views_before"][task]["reason"].replace("<recorded time>", "in an earlier check"))
        output = escape(row["output_from_origin"])
        note = "Check output from the cited request" if row["execution"] == "reuse" else "Fresh check output"
        rows.append(f"""
<tr id="handoff-request-{number}"><th scope="row" aria-label="{number}. {label}">
<details><summary>{number}. {label}</summary>
<p>The software reported: {reason}</p>
<p>{note}</p><pre>{output}</pre>
<p>Actor label <code>{escape(row['actor_label'])}</code></p>
</details></th><td>{escape(task)}</td><td>{STATES[row['before']]}</td>
<td>{escape(_request(row, numbers))}</td><td><span class="chip {row['after']}">{AFTER[row['after']]}</span></td></tr>""")

    return f"""
<section id="handoff-audit" class="measurement-audit" aria-labelledby="handoff-heading"><div class="wrap prose">
<h2 id="handoff-heading">Which result can the next task use?</h2>
<p>Three tasks share one pendulum analysis. Each asks the same fit check as the plot style changes,
one reading makes the fit fail, and the original data returns.</p>
<p>{_summary(record)} These counts describe one scripted history. The runner supplied the actor labels and made no live model calls.</p>
<figure class="experiment">
<figcaption id="handoff-table-label"><strong>Seven requests in one history.</strong> Expand an event to see the reported reason and check output.</figcaption>
<div class="scroll" role="region" aria-labelledby="handoff-table-label" tabindex="0">
<table class="claims case-table" aria-labelledby="handoff-table-label"><thead><tr>
<th scope="col">Event</th><th scope="col">Task</th><th scope="col">What the task found</th>
<th scope="col">When it requested the check</th><th scope="col">Standing afterward</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table></div></figure>
<p>Two passes printed the same gravity estimate. Only one used the exact CSV the last task received.
An independent check reconstructed each fit and its input files. It rejected a copy of the record
that pointed to the other pass, even though the numbers and the total run count still matched.</p>
<p><a href="../records/handoff_audit.json">Raw observations (JSON)</a> ·
<a href="../source/">Complete source for this build</a> · <a href="../records/handoff-method.md">Handoff method</a> · <a href="../records/review_handoff_audit.py">Independent verifier</a> ·
<a href="../records/handoff_audit.py">Reproduction script</a></p>
<p>Reproduce from the repository root with <code>python3 evals/handoff_audit.py --verify</code>.</p>
</div></section>"""


def handoff_markdown(record):
    rows = record["observations"]
    labels = _labels(rows)
    numbers = {row["id"]: row["sequence"] for row in rows}
    lines = ["## Which result can the next task use?", "", _summary(record),
             "The runner supplied the actor labels and made no live model calls.", "",
             "| Event | Task | What the task found | Check request | Standing afterward |",
             "|---|---|---|---|---|"]
    lines.extend(f'| {row["sequence"]}. {labels[row["id"]]} | {row["task"]} | {STATES[row["before"]]} | '
                 f'{_request(row, numbers)} | {AFTER[row["after"]]} |' for row in rows)
    lines.extend(["", "[Raw observations](../records/handoff_audit.json) · [Handoff method](../records/handoff-method.md) · "
                  "[Reproduction script](../records/handoff_audit.py)", "",
                  "Reproduce with `python3 evals/handoff_audit.py --verify`.", ""])
    return lines
