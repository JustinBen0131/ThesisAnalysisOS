# Self-iteration

The OS is supposed to get tighter, not heavier. Every mechanism must earn its
place; every lesson must become something a machine can check or it decays.

## The loop

1. The human corrects an agent. The agent fixes the artifact and writes one
   line in `kernels/PRINCIPAL_KERNEL.md` under Corrections observed, dated.
2. The same correction happens again. The agent proposes an atom:
   `taos propose --kind atom --atom-json <file>`. An atom carries a check
   (`regex_must_match`, `regex_must_not_match`, `file_must_exist`,
   `taos_command_exit_zero`) and, ideally, red/green fixtures so the atom
   tests itself.
3. The human accepts the proposal and promotes it: `taos atoms promote`.
4. `taos doctor` and every brief run the atom forever. The agent may stop
   remembering the lesson.

Atoms are never promoted without the human. Rejected proposals are kept for
30 days, then burned.

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

## Burns

Handoffs, old briefs, scratch, and closed proposals have a TTL. `taos burn
plan` lists what is past it. `taos burn execute --approve` archives to
`.taos/cold/<date>.tar.gz`, writes a sha256 manifest, verifies the archive
restores byte for byte, and only then deletes. `taos burn recall` restores.
Tasks, claims, events, config, atoms, and kernels are never burn fuel.

## Cadence

The human chose `daily`, `weekly`, or `manual` at setup. Respect it. Nagging
about proposals outside the cadence is itself a correction waiting to happen.
