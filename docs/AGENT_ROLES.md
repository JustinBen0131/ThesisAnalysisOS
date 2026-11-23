# Bring another agent into a project

Choose a distinct project role name for each session that needs its own
task ownership and handoffs. One person can coordinate many roles across
Claude, Codex, ChatGPT or other tools. Local assistants can read the project
through the CLI. A web-chat reviewer reads the material you provide.
[Assistant interfaces](AGENT_INTERFACES.md)

You might use
`field-notes` for the assistant collecting observations and `reader-two`
for the one reviewing them. Both use the same local TAOS executable and
project home. Each reads the current task, claims work and leaves a record
under its own name.

At setup, put the names in the `agents` list in your bootstrap answers.
The default team is `codex` and `claude`. After setup, the person running
the project can add one name at a time.

```sh
./taos bootstrap add-agent field-notes --by human
./taos bootstrap add-agent reader-two --by human
./taos bootstrap status --json
```

Use 1–32 lowercase letters, digits, hyphens or underscores, starting with
a letter. TAOS reserves `human` and `system` for their existing roles
and `any` for a shared workspace. Repeating an addition is harmless.
`--json` on the add command returns the full roster and whether it changed.
Repeating setup retains names added this way. If an older installation has
a customized handoff check that matches only Codex and Claude, inspect that
check and update it to recognize the header written by your named roles.

For a client-specific connection or a review in an ordinary web chat, see the
[assistant interface guide](AGENT_INTERFACES.md).

## Continue a task

Run these commands in a terminal or give them to the assistant you already
use. Replace `AZ-7` with a task from `./taos task list`.

```sh
./taos start --agent field-notes --task AZ-7 --session "AZ-7 observations"
./taos handoff template AZ-7 --from field-notes --to reader-two --session "AZ-7 observations"
```

Save the printed handoff as `handoff.md` and fill in its five sections. Give
the reviewer a concrete observation, the evidence to open, and the first
command to run. Run the gate command when the project has configured checks.

```sh
./taos gate run --agent field-notes --task AZ-7
./taos finish --agent field-notes --task AZ-7 --state review \
  --reason "Observations are ready for review" --session "AZ-7 observations" \
  --handoff-file handoff.md --to reader-two
./taos start --agent reader-two --task AZ-7 --session "AZ-7 review"
./taos capsule AZ-7 --json
```

The second start shows the note and the task's recorded workspace. For a
new task, TAOS prefers the workspace assigned to the agent, then a shared
workspace. Choose a shared workspace for work every participant should open.

## Ask another reviewer a specific question

```sh
./taos capsule AZ-7 --transfer "Could a changed calibration explain the discrepancy?"
```

This prints a transfer prompt on your computer. Its context packet contains the
task, its completion condition, recorded results, applicable instructions, open
decisions and up to five recent evidence references. Its packet ID is the SHA-256 of the
printed JSON in UTF-8, excluding the final newline. Two reviewers can use it
to verify they received the same recorded facts. Read the packet and choose the
source rows or method excerpts the reviewer should see. A reviewer in a web
chat needs you to provide those materials. A reviewer with workspace access can
open the referenced files itself.

Use a smaller model to identify the missing input or suggest a quick check.
If the scientific interpretation is still in doubt, send the same packet
and the selected measurements to a deeper reviewer. Ask what observation
would distinguish the explanations. Compare its prediction with the actual
check before proposing a change to the project's rules. The command makes
no model call and sends no files.

### Check a returned review

A review can come back after a row was corrected or another question was asked.
Give the original question and the same source files to both commands.

```sh
./taos capsule AZ-7 --transfer "Did both sensors meet the limit?" --source readings.csv
./taos capsule AZ-7 --transfer "Did both sensors meet the limit?" --source readings.csv --check-review reply.json
```

The first command prints a reply form with two identifiers. The packet ID identifies
the recorded project facts. The request ID also covers the question and the names
and exact bytes of the files you selected. Attach those files yourself if you want
the reviewer to read them. You can repeat `--source` for more than one file.
Save the filled JSON as `reply.json`. The second command checks it against the
current task. A changed question, task record or selected file prevents a match.
A reviewer who lacks necessary evidence can return `uncertain` and name the missing
measurement. A supported or contradicted finding must cite evidence.

A match establishes which request a reply refers to. Anyone can copy the IDs.
The operator still checks the cited rows, judges the conclusion and decides
whether to act. Checking a reply reads local files and records no acceptance.

## What a name records

Anyone with write access to the same TAOS home can declare a role, including
`human`. Separate names preserve attribution and let TAOS refuse a builder's
attempt to grade its own change. The record alone cannot establish who
operated a terminal or whether two names represent independent people
or models.

Adding a name updates the roster. Hook installation, model access, vendor
accounts, token-use adapters and the project's human-only decisions have
their own settings. A named agent can use the CLI and record an episode
without a native adapter. The historical `provider` field on a task session
records the declared session lane. Token usage requires a supported source.
`./taos start --help` shows the names accepted in the current home. Use
`--home PATH` before the verb to select another.
