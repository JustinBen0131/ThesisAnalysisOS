# Handoffs

A handoff is the object that lets a session die without losing the work.
Chat history is not a handoff. Memory is not a handoff.

## Shape

```
Agent: codex
Chat/session: AZ-7 | fix ssa pass
Task: AZ-7 | Fix the panic on empty generic bounds
Claim/scope: task:AZ-7, branch:az/az-7-fix

## State
Where this actually is, in two or three sentences. Not where you hoped.

## Changed
Files touched, commands run, what exists now that did not before.

## Evidence
Paths, commit shas, gate runs, test output. Things the receiver can open.

## Risks and open questions
What might be wrong. What you did not verify. What you assumed.

## Next command
The literal command the receiver should run first.
```

`taos handoff template` prints it with the header filled. `taos handoff write`
and `taos finish --handoff-file` refuse a handoff missing the header, missing
any section, or still containing template placeholders.

## When

- Whenever the other agent continues the work.
- Whenever you stop with the task not in `done`, and the next session might
  not be you.
- Whenever the human asks one agent to "talk to" the other: the file is the
  message; chat carries only the wrapper `taos handoff wrapper` prints.

## Receiving

`taos capsule <ID>` shows the latest handoff's first forty lines along with
the task, blockers, claims, and decisions. Read the whole file, then run the
next command it names. Do not redo completed effects.
