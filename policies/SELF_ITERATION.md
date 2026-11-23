# Self-iteration

The OS is supposed to get tighter, not heavier. Every mechanism must earn its
place; every lesson must become something a machine can check or it decays.

## The loop

1. The human corrects an agent. The agent fixes the artifact and writes one
   line in `kernels/PRINCIPAL_KERNEL.md` under Corrections observed, dated.
2. The same correction happens again. The agent proposes an atom:
   `taos propose --agent <agent> --kind atom --title <title> --body <why> --atom-json <file>`. An atom carries a check
   (`regex_must_match`, `regex_must_not_match`, `file_must_exist`,
   `taos_command_exit_zero`) and, ideally, red/green fixtures so the atom
   tests itself.
3. The human reviews the proposal. Accept with
   `taos proposals decide <proposal-id> --status accepted --by human`
   and install with `taos atoms promote <proposal-id> --by human`.
   The human can also promote a pending proposal directly, which records
   acceptance and installs the check. Decline with
   `taos proposals decide <proposal-id> --status rejected --by human`.
4. `taos atoms check` and `taos doctor` run the installed check until it
   is retired. Pending, accepted but uninstalled, and declined proposals
   leave the running checks as they were.

The CLI's `human` actor label records the caller's role. It does not
authenticate a person with access to the local account. Rejected proposals
are kept for 30 days, then eligible for a burn.

Command atoms may run the read-only readers `taos policy check`,
`taos policy list`, `taos policy show`, `taos task list`, `taos task show`,
and `taos why`. The checker reports older command atoms outside this set
as failed without running them. Retire such an atom and propose an equivalent
file, regex, or supported command check with a new ID if it is still needed.

## Kernels

`OS_KERNEL` (how this works), `PROJECT_KERNEL` (the codebase), `PRINCIPAL_KERNEL`
(how to work with the human), `NOW_KERNEL` (live state, machine-written).
Each carries a fingerprint of its sources and a maximum age. `taos kernel
freshness` reports `drifted` or `aged`. Regenerate with the prompt from
`taos kernel regen-prompt <NAME>`, then `taos kernel refresh <NAME>`. Kernels
are advisory. They never authorize anything.

## Retro

`taos retro` (weekly by default) reports: events by agent, tasks finished,
corrections recorded, hot tasks untouched for a week, and suggestions: cool
stale work, or turn repeated corrections into atoms. It proposes; it changes
nothing.

## Retirement

A mechanism nobody uses is a cost. When a policy line, an atom, a gate, or a
kernel section stops earning its keep, propose retiring it
(`--kind retire`). Removing is as valuable as adding.

The human can retire a specific atom with
`taos atoms retire <atom-id> --by human --reason <reason>`.
The command stops future checks and keeps the atom ID, decision, and reason
on record. Retired atom IDs cannot be reused.

## Burns

Handoffs, old briefs, scratch, and closed proposals have a TTL. `taos burn
plan` lists what is past it. `taos burn execute --approve` archives to
`.taos/cold/<date>.tar.gz`, writes a sha256 manifest, verifies the archive
restores byte for byte, and only then deletes. `taos burn recall` restores.
Tasks, claims, events, config, atoms, and kernels are never burn fuel.

## Three kinds of learning, kept apart

- **Semantic lessons** (a thing that keeps going wrong) become atoms through
  proposals the human accepts. This section.
- **Quantitative operating choices** (how much verification, compute, and
  exploration a class of task deserves) are calibrated automatically by the
  control law in `policies/CONTROL.md`, within fixed bounds, from measured
  outcomes. No approval is needed for those bounded numbers, and they cannot
  reach anything a proposal or a hard stop protects.
- **Structural changes** (a new rule, a retired mechanism, a widened
  permission) remain proposals. The controller may not make them, and tuning
  is never a route around them.

## Cadence

The human chose `daily`, `weekly`, or `manual` at setup. Respect it. Nagging
about proposals outside the cadence is itself a correction waiting to happen.
