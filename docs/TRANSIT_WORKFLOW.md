# Continuing a morning service report

<sub><b>Check the evidence · 6 of 6</b> &nbsp;·&nbsp; [← Exchange simulation](EXCHANGE_SIMULATION.md) &nbsp;·&nbsp; [All documents](README.md) &nbsp;·&nbsp; [Architecture →](ARCHITECTURE.md)</sub>

A transit operator asks for the share of scheduled buses that left on time. Monday's departure log contains 18 departures and 16 left on time. Two other buses, M17 at 07:10 and M19 at 07:22, were scheduled and canceled. Monday's draft rounds 16/18 to 89%. Accounting for the full timetable gives 16/20, or 80%. On Tuesday, T04 and T11 lack dispatch records. The example leaves Tuesday's rate pending.

The two cancellations, the missing trip identifiers and the Monday counts appear in the [film illustration](https://whatstillholds.com/#field-film). The machine-readable timetable, dispatch rows, dates, owners, operator dialogue and later M18 edit in this study are fictional. One local Python process scripts the actor choices and starts the public TAOS commands in fresh subprocesses. The study measures the behavior of that workflow. It contains no human-subject observations, agent inference, or service performance measurements.

## Reproduce the recording

Use Python 3.9 or later in a checkout. The commands create a temporary TAOS home and a separate copy of the fixture workspace. They require no setup, network, provider account, or project data.

```sh
python3 evals/transit_workflow.py --verify
python3 -m unittest discover -s tests -p test_transit_workflow.py
```

`--verify` checks the source fingerprints, runs the actual commands and compares the full normalized recording. Without flags the recorder writes its JSON to standard output. `--write` explicitly regenerates [examples/transit/workflow.json](../examples/transit/workflow.json). The static reader can call `load_record()` to validate the saved file without running any checks or modifying any state.

To inspect the fixture independently, run `python3 -B count.py count monday` and `python3 -B count.py count tuesday` from the folder containing the [transit counter](../examples/transit/count.py). The counter joins dispatch to the timetable by trip ID. A recorded departure has a dispatch disposition of `on_time` or `late`. A cancellation has a dispatch entry but no departure. A missing dispatch entry has an unknown disposition. Percentages are rounded to the nearest whole percent for display. The two exact counts remain available.

## What the commands establish

| Scene | Evidence to open in the JSON |
| --- | --- |
| Set the standard | `standard-rule` returns the human actor's original quotation, scope and effective date. |
| Divide the work | `report-task` and `audit-task` show separate finish conditions. `claims` shows two concurrent leases. `overlap` exits 4 and names the current owner. The numerical result uses the same timetable and dispatch records as the audit. |
| Correct the denominator | `draft-check` rejects the 18-trip draft. `old-day` and `current-rule` return different governing quotes. `unrelated` returns no service rule in the maintenance scope. The stored lesson records the mistake in the operator's words. The separate proposal to extend the check to each new day remains proposed. |
| Resume in another session | `save-handoff` releases the audit claim. `resume` claims it for the successor and prints the actual brief, rule and lesson. `capsule` returns the recorded task, evidence, next action and handoff. The lesson's exposure documents delivery. `tuesday-refusal` exits 3 and leaves no Tuesday report. |
| Change one input | Restyling the heading in `style.txt` changes the presentation input alone. TAOS reuses the Monday count check. Restoring the original bytes restores the original acceptance. Then only M18 changes from late to on time. The previous check is stale. Running it against the unchanged report fails. Rebuilding changes the report to 17/20, or 85%. |
| Review a version | A passing gate leaves the task without acceptance. An agent's attempt to accept is refused. The scripted human accepts the 80% version. The receipt fingerprints the workspace and governing rules. After the source correction, the 85% report passes a fresh check. The recorded acceptance and the artifact registered under the original inputs both remain stale. |

The Monday numerical gate declares its script, Monday data and saved numerical report as inputs. The report artifact declares its source inputs. Human acceptance covers the whole configured workspace, including the separate presentation file. The examples of selective reuse depend on those concrete declarations. The gate is a local command with declared inputs. This recording does not test isolation. The heading change edits a presentation input. The recorder does not render a PDF or a styled report.

## When the operator changes the handoff check

The optional branch starts from the same Tuesday audit. The first session hands over a note saying that some trips lack dispatch records. The operator registers a new local actor, `service-auditor`, to take the next shift. A single Python script plays both assistants and the operator. Local commands carry out their decisions.

The offered check looks for a line like `Open trips: T04, T11` in the latest handoff. The first offer is declined. The note passes the existing checks. The same assistant offers the rule again in a separate proposal so both operator choices can be observed. After the operator accepts and activates it, the check flags the unchanged note. The successor claims the task, reads the handoff and sees the failed check. It runs the note’s next command, fills the line from its count and passes the check.

Now change the timetable’s 06:34 trip from T11 to T27 and leave the note alone. The line still passes. Rejoining the timetable to dispatch returns T04 and T27. The successor writes those IDs, and its note agrees with the data again. The operator retires the check. The same note with the line omitted passes the remaining checks. Tuesday’s service rate stays pending throughout.

```sh
python3 evals/transit_workflow.py --adaptation --verify
```

Inspect `records` for the exact commands, exit codes and native output. The `checks` field reports what the approved rule did. Each entry in `cases` compares the named trips with the independent source count and links to both observations. `--adaptation --write` refreshes just this recording. [Adaptation recording](../examples/transit/adaptation/workflow.json) · [Proposed rule](../examples/transit/adaptation/trip-line.json)

## Inspect the six-scene recording

An independent instruction control adds a tire-inspection rule in the fleet-maintenance scope. `fleet-rule` retrieves that quotation there. `report-after-fleet-rule` returns exactly the same Monday report standing, instructions and acceptance as `baseline-why`.

The `scenes` entries name evidence IDs. `records` stores the commands, combined stdout/stderr and return codes. The public `task`, `start`, `claim`, `rule`, `lesson`, `propose`, `finish`, `capsule`, `gate` and `why` operations use the TAOS engine. The fixture's separate `count.py` calculates the rates. The `observations` entries retain the corresponding machine-readable values, including the actual successor capsule, the human actor's acceptance receipt, and the four main version comparisons. The recorder additionally saves the exact-byte restoration and the executed failure.

The commands substitute `<scratch>` for the temporary directory, stable aliases for generated IDs and gate filenames, and placeholders for wall-clock timestamps and the controller's elapsed-time-dependent episode score. These substitutions happen after execution. They preserve source hashes, report hashes, outcomes, fixture dates and the connections between records. Listings and snapshots can be inspected in the receipt. A digest protects the saved recording from unnoticed edits. The independent test rejoins the individual rows and checks missing, resolved and duplicate dispatch records, altered evidence, staleness and full public CLI reproduction.
