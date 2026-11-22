"""Project a real command-line demo into reader decisions and check its numerical evidence."""
import html
import json
import re
import subprocess
import sys
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import NamedTuple

from review_measurement_audit import estimate, expected_gate


class Scene(NamedTuple):
    anchor: str
    short: str
    title: str
    story: str
    facts: tuple
    code: str
    lines: list
    comparisons: tuple = ()


def require(condition, reason):
    if not condition:
        raise ValueError("Demo walkthrough: " + reason)


def capture(repo):
    run = subprocess.run([sys.executable, str(repo / "taos"), "demo", "--json"], cwd=repo,
                         capture_output=True, text=True, encoding="utf-8")
    if run.returncode:
        raise ValueError("The demo could not produce its run record: " + run.stderr[-800:])
    return json.loads(run.stdout)


def only(items, name):
    items = list(items)
    require(len(items) == 1, f"expected one {name}, found {len(items)}")
    return items[0]


def transcript(events):
    lines = []
    for event in events:
        if event["kind"] == "say":
            lines.append(event["text"])
        else:
            lines.append("$ " + event["command"])
            lines.extend("    " + line for line in event["printed"])
    return lines


def fit_verdicts(scenes):
    def find(scene, state):
        return only((line for line in scene.lines if re.match(r"^\s*" + state + r"\s+check fit\b", line)),
                    f"{state} fit verdict in {scene.anchor}")
    return find(scenes[0], "holds"), find(scenes[2], "stale")


def checked_fit(steps):
    run = only((e for e in steps if e.get("command") == "python3 analysis/fit.py"), "fit measurement")
    result = run["measured"]
    rows = [(Fraction(str(row["length_m"])), Fraction(str(row["period_s"]))) for row in result["rows"]]
    require(len(rows) == result["swings"] >= 2 and result["unit"] == "m/s^2", "fit needs its units and input rows")
    gravity, error = estimate(rows)
    require((Decimal(str(result["g"])), Decimal(str(result["standard_error"]))) ==
            (round(gravity, 2), round(error, 2)), "reported fit disagrees with the independent fit of the six rows")
    measured_line = f'g = {gravity:.2f} +/- {error:.2f} m/s^2 from {len(rows)} swings'
    require(measured_line in run["printed"], "the fit in the record differs from the command output")
    require(expected_gate(rows, gravity, error)[0] == 0, "these demo rows must pass the example's check")
    return rows, f"{gravity:.2f} ± {error:.2f} m/s²"


def chapters(record, audit):
    require(record.get("schema") == "TAOS_DEMO_V1", "unsupported run record")
    moments = record["moments"]
    ids = [m["id"] for m in moments]
    require(ids == ["standing", "reuse", "instructions", "acceptance", "reminder", "isolation"],
            "the site's chapters must cover each CLI moment in order")
    require([m["number"] for m in moments] == list(range(1, len(moments) + 1)), "moment numbers are out of order")
    events = {m["id"]: m["steps"] for m in moments}
    all_events = [e for m in moments for e in m["steps"]]
    require(all(e["kind"] in ("say", "run") for e in all_events), "unknown event in run record")
    runs = [e for e in all_events if e["kind"] == "run"]
    require(record["commands"] == len(runs) and record["checked"] == sum(len(e["expected"]) for e in runs),
            "run totals do not match the recorded commands")
    require(all(e["expected"] and all(s in "\n".join(e["printed"]) for s in e["expected"]) for e in runs),
            "a command's stated expectation is missing from its output")
    keyed = {e["id"]: e for e in runs if e.get("id")}
    require(len(keyed) == sum(bool(e.get("id")) for e in runs), "duplicate decision id")
    for key, answer, subject in (("baseline", "holds", "check fit"), ("style-only", "holds", "check fit"),
                                 ("timing-edited", "stale", "check fit"), ("rerun", "ok", "fit"),
                                 ("shared", "held", "fit"), ("edited-after", "stale", "acceptance"),
                                 ("undeclared", "FAIL", "style"), ("declared", "ok", "style")):
        step = keyed[key]
        answers = [re.match(r"^(\S+)\s+" + subject + r"\b", line) for line in step["printed"]]
        require(step.get("answer") == answer and any(match and match[1] == answer for match in answers),
                f"{key} does not support its reader-facing decision")

    standing = events["standing"]
    first = standing.index(keyed["baseline"]) + 1
    second = standing.index(keyed["style-only"]) + 1
    require(first < second < len(standing) and standing[-1] == keyed["timing-edited"], "standing decisions out of order")
    old, initial_fit = checked_fit(standing)
    new, updated_fit = checked_fit(events["reuse"])
    baseline_rows = [(Fraction(a), Fraction(b)) for a, b in audit["baseline_rows"]]
    require(old == baseline_rows and [a for a, _ in new] == [a for a, _ in old],
            "the demo and the animation need the same starting readings")
    row = only((i for i in range(len(old)) if old[i] != new[i]), "corrected timing")
    length, original = old[row]
    corrected = new[row][1]
    large = only((c for c in audit["cases"] if c["id"] == "row-6-1.05"), "animation trial")
    audit_rows = [(Fraction(a), Fraction(b)) for a, b in large["rows"]]
    require(len(audit_rows) == len(old) and [i for i in range(len(old)) if old[i] != audit_rows[i]] == [row]
            and audit_rows[row][0] == length and original < corrected < audit_rows[row][1],
            "the two examples must correct the same period by different amounts")
    large_g, large_error = estimate(audit_rows)
    require(all(abs(Decimal(str(value)) - calculated) <= Decimal("1e-12")
                for value, calculated in ((large["g"], large_g), (large["se"], large_error))),
            "the animation trial disagrees with the independent fit of its readings")
    require(large["retained"] == "stale" and large["fresh_exit"] == expected_gate(audit_rows, large_g, large_error)[0] == 1
            and large_g < Decimal("9.6"),
            "the larger correction must invalidate the earlier pass and fall below the example's limit")
    old_period, new_period = f"{float(original):.2f} s", f"{float(corrected):.2f} s"
    at_length = f"{float(length):.2f} m"
    number = str(len(old))
    trials = (("Terminal demo", new_period, updated_fit, "Passes", "records/demo.json"),
              ("Opening animation", large["rows"][row][1] + " s", f"{large_g:.2f} ± {large_error:.2f} m/s²",
               "Below 9.6 m/s²", "evidence/pendulum/#readings-row-6-1.05"))

    instructions = []
    for key in ("february", "march"):
        step = keyed[key]
        when = date.fromisoformat(step["command"].split("--on ")[-1])
        quote = only((p for p in step["printed"] if p.startswith('"') and p.endswith('"')), "dated instruction")
        instructions.append((f"{when.strftime('%B')} {when.day}", quote[1:-1]))
    reminder = only((re.search(r"(\d+) repeated, (\d+) followed, (\d+) not judged, of (\d+) times shown", p)
                     for p in keyed["repeats"]["printed"] if "times shown" in p), "reminder follow-up")
    require(reminder and reminder.groups() == ("0", "0", "1", "1"), "the reminder's outcome must still be unknown")
    require(any("figures/style.txt" in line for line in keyed["undeclared"]["printed"]), "missing file is not identified")

    return [
        Scene("run-1", "First fit", "Save the first gravity estimate",
              "The six timings give a value for gravity. The check passes, and the project saves which files it checked.",
              (("Timings used", number), ("Gravity ± standard error", initial_fit), ("Fit check", "Passed")),
              "taos_core/gates.py", transcript(standing[:first])),
        Scene("run-2", "Edit the plot", "Keep the fit after a plot edit",
              "The plot style changed. The fit uses the timing data and analysis code. Those files still match its saved check.",
              (("File edited", "figures/style.txt"), ("Gravity estimate", initial_fit), ("Earlier pass", "Still usable")),
              "taos_core/basis.py", transcript(standing[first:second])),
        Scene("run-3", "Correct a timing", "Set the old pass aside",
              f"The {at_length} pendulum took {new_period}, up from {old_period}. The saved check used the earlier timing. "
              "Run the check on the corrected data before using the result.",
              (("Earlier timing", old_period), ("Corrected timing", new_period), ("Earlier pass", "Check again")),
              "taos_core/basis.py", transcript(standing[second:]), trials),
        Scene("run-4", "Hand it on", "Hand the checked result to the next researcher",
              "The corrected fit passes. When the second task asks for the same check on the same files, it receives that pass.",
              (("Revised gravity ± standard error", updated_fit), ("First request", "Ran the fit check"),
               ("Second request", "Reused that pass")), "taos_core/gates.py", transcript(events["reuse"])),
        Scene("run-5", "Date a rule", "Recover the instruction for each date",
              "The length measurement method changed. A researcher reopening an older analysis can look up the instruction in force that day.",
              instructions, "taos_core/rules.py", transcript(events["instructions"])),
        Scene("run-6", "Review", "Keep a person's approval with the version they saw",
              "A researcher accepted the fit. Someone then edited the analysis file. A new reviewer can see exactly which version was approved.",
              (("Reviewed", "Fit and residuals"), ("Later edit", "analysis/fit.py"), ("Approval applies to", "Earlier version")),
              "taos_core/tasks.py", transcript(events["acceptance"])),
        Scene("run-reminder", "Reminder", "Find out whether a reminder helped",
              "The next assistant saw a reminder about a disturbed swing. Nobody recorded what happened afterwards, so its effect is unknown.",
              (("Times shown", reminder[4]), ("Outcomes judged", str(int(reminder[1]) + int(reminder[2])))),
              "taos_core/lessons.py", transcript(events["reminder"])),
        Scene("run-7", "Missing file", "Find the file a check forgot to list",
              "The style check runs with only the folders it listed. Adding the figures folder gives it the file it needs.",
              (("Missing input", "figures/style.txt"), ("Before listing it", "Check failed"), ("After listing it", "Check passed")),
              "taos_core/gates.py", transcript(events["isolation"])),
    ]


COMPARE_TITLE = "Would a larger timing correction still pass?"
COMPARE_NOTE = ("Both corrections set aside the original pass. The fresh check tests the new estimate. "
                "For these six readings, the estimate must be above 9.6 and below 10.0 m/s², "
                "with a standard error of 0.20 m/s² or less.")


def comparison_html(trials):
    rows = "".join(f'<tr><th scope="row"><a href="{html.escape(url)}">{html.escape(name)}</a></th>'
                   f'<td>{html.escape(period)}</td><td>{html.escape(fit)}</td><td>{html.escape(answer)}</td></tr>'
                   for name, period, fit, answer, url in trials)
    return (f'<details class="demo-comparison"><summary>{COMPARE_TITLE}</summary><p>{COMPARE_NOTE}</p>'
            '<table><caption>Two corrections to the same swing</caption><thead><tr><th scope="col">Run</th>'
            '<th scope="col">New timing</th><th scope="col">Gravity ± standard error</th>'
            '<th scope="col">Fresh check</th></tr></thead><tbody>' + rows + '</tbody></table></details>')


def comparison_markdown(trials):
    rows = [f"| [{name}]({url}) | {period} | {fit} | {answer} |" for name, period, fit, answer, url in trials]
    return "\n".join([f"**{COMPARE_TITLE}**", "", COMPARE_NOTE, "",
                      "| Run | New timing | Gravity ± standard error | Fresh check |", "| --- | --- | --- | --- |", *rows])
