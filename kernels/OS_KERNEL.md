# OS_KERNEL — how this operating layer works

Advisory. A cold session that reads only this should understand the machine.
The task store, the claims, and `policies/HARD_STOPS.md` are canonical; this
file authorizes nothing.

## Shape

One directory is the OS home. Everything durable is a plain file under
`.taos/`, written only by the `taos` command. Everything a human or an agent
looks at is a projection of those files: the panel, the brief, the hot rail,
the compact status injected at session start.

## Stores

- `tasks.json`: every task, with stable ids `PREFIX-N` allocated by the tool.
  Statuses: backlog, next, active, blocked, waiting, review, done, canceled,
  archived. `done` needs evidence; `blocked` needs a named blocker.
- `events.jsonl`: append-only; every mutation lands here first.
- `claims.json`: scope-local leases (`task:`, `path:`, `repo:`, …) with a
  heartbeat. A live claim by the other agent is do-not-touch; stale ones can
  be taken over with a logged reason. Reading never needs a claim.
- `decisions.json`: questions queued for the human. Agents ask here instead
  of stalling.
- `proposals/`: changes to the OS itself, waiting for a human yes or no.
- `handoffs/`: what a session leaves behind so the next one can continue.
  Refused unless it has the header and all five sections.
- `telemetry/labels.jsonl`: one sanitized row per episode boundary. Slugs and
  enums only.

## Verbs

`start` claims, activates, maps the session, marks hot, prints the capsule.
`finish` transitions, writes the handoff if given, releases the claim, labels.
`capsule` is everything needed to resume. `decide ask` queues a human
decision. `propose` queues an OS change. `brief` renders the day. `doctor`
checks mechanical health. `kernel now` regenerates NOW from state. `atoms
check` runs every promoted correction. `burn plan/execute/recall` archives,
verifies, then deletes expired soma. `panel on/off` runs the loopback UI.

## Learning loop

Correction twice -> atom proposal -> human accepts -> `atoms promote` -> the
rule runs in `doctor` forever. Kernels carry a fingerprint of their sources
and an age limit; `kernel freshness` shows rot; `kernel regen-prompt` tells
an agent how to rewrite one. Weekly `retro` surfaces stale hot work and
repeated corrections.

## Hooks

The same three scripts serve Codex and Claude. PreToolUse denies secrets,
force pushes, direct edits to the store and to the hooks themselves, and asks
before pushes, recursive deletes, installs, and takeovers. SessionStart
injects `taos status --compact`. Stop turns the episode marker into a label.

## What it is not

It is not a scheduler, not a model runner, and not an authority on the work.
It never calls a network or a model. It runs on the Python standard library.
