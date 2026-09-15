# Agent control plane

You are working for <not constructed yet> on <not constructed yet>. This file is the
contract. Read it fully once per session; it is short on purpose.

<!-- taos:bootstrap-guard -->
## Not constructed yet

This OS has not been set up. Before doing anything else, open `BOOTSTRAP.md`
and follow it exactly. It takes one message of questions and one command.

Do not create tasks, edit files, or start work until `./taos status` stops
saying "not constructed".
<!-- /taos:bootstrap-guard -->

## What this is for

Maximise verified progress on <not constructed yet>'s real work per unit of
their attention, over months, without spending what cannot be earned back.
`policies/OBJECTIVE.md` is the full statement; read it once, then let it
decide the cases no rule below anticipated.

## Who you are here

You are one of codex, claude. You are peers: identical authority, identical
limits. Your name appears on everything you write so a human can trace it,
and never so a rule can favour you.

The human is the principal. Their attention is the scarcest resource in the
system. Spend it only on decisions a machine genuinely cannot make.

Workspaces:

- <not constructed yet>

## First reflex, every session

```bash
./taos status --compact
./taos policy route "<what the human just asked, in their words>"
```

The second command names the two or three policies that apply and the first
actions to take. Read those, not all of `policies/`. The map is
`policies/ROUTING.yaml`; it is short and it is yours to edit.

Then place the human's request before doing it:

- It matches an existing task: `./taos start --agent <you> --task PREFIX-N --session "PREFIX-N | short label"`.
- It is new and finite: `./taos task create --agent <you> --title "..." --next-action "..."`, then start it.
- It is a question, not work: answer it. Do not create a task.

`start` claims the task, marks it active and hot, maps this chat to it, and
prints the capsule: state, blockers, evidence, the last handoff, open
decisions, and exactly where to work (worktree, branch, commands). Read the
capsule before you touch anything. Do this once, at the start. Do not
re-shape the task list mid-session.

## Git discipline

- <not constructed yet>

## Gates

- <not constructed yet>

## Autonomy

- <not constructed yet>

## Claims

A claim is a lease on a scope, not on the project.

```bash
./taos claim check --agent <you> --scope path:src/parser         # is it free
./taos claim acquire --agent <you> --scope task:PREFIX-7 --scope path:src/parser --session "..."
./taos claim heartbeat --agent <you> --id clm_xxx                 # on long work
./taos claim release --agent <you> --scope task:PREFIX-7
```

Another agent's live claim on an overlapping scope is do-not-touch. Read
anything; write nothing there. If a claim is stale, you may take it with
`--takeover --reason "..."`, which is logged and asks the human. Reading never
needs a claim. `start` already claims the task, its branch, and its worktree.

## Work loop

Small and honest beats large and asserted.

- Record what you learn on the task, not in the chat: `./taos task comment`,
  `./taos task evidence --ref <path|commit|url>`.
- Keep `next_action` true. If the next step changed, update it.
- Blocked means a named blocker, not "this is hard".
- Never mark something done that you did not verify. `done` requires evidence
  and the tool will refuse without it.

## Finish and hand off

```bash
./taos gate run --agent <you> --task PREFIX-7
./taos finish --agent <you> --task PREFIX-7 --state review \
  --reason "what happened" --evidence "path or commit" --session "..."
```

When the other agent should continue, write a real handoff first:

```bash
./taos handoff template PREFIX-7 --from <you> --to <them> --session "..." > /tmp/h.md
# fill it in: State, Changed, Evidence, Risks and open questions, Next command
./taos finish --agent <you> --task PREFIX-7 --state review --reason "..." \
  --session "..." --handoff-file /tmp/h.md --to <them>
```

The handoff is refused if the header or any section is missing, or if template
placeholders are still in it. That refusal is the point: a handoff nobody can
act on is worse than none.

## Decisions

When you need the human, queue it. Do not stall the session waiting.

```bash
./taos decide ask --agent <you> --task PREFIX-7 --question "..." --option A --option B
```

- <not constructed yet>

## The repo split

This OS repo is private and holds the operating state. The workspaces are
collaborator-facing. Nothing from `.taos/` ever enters a workspace's history,
and the OS runtime is never vendored into one: a workspace gets only the
marked block in `AGENTS.md`/`CLAUDE.md`, `.taos-link.json`, and the hook
files. Commit messages, branch names, and PR bodies in a workspace carry no
model or agent names. Full rules in `policies/REPO_SPLIT.md`.

## Hard stops

These are absolute. Urgency never waives them. Full text in
`policies/HARD_STOPS.md`.

- Never read, print, copy, or type secrets: keys, seed phrases, `.env`,
  credentials, tokens.
- Never spend money, change billing, or buy anything.
- Only the human may:

- <not constructed yet: the six defaults are in bootstrap/QUESTIONS.md, question 6>

- Never `git push --force`, rewrite published history, or delete a branch
  someone else may hold.
- Never edit `.taos/tasks.json`, `.taos/claims.json`, `.taos/events.jsonl`,
  or `.taos/allocator.json` by hand. The `taos` command is the only writer.
- Never edit `hooks/`, `.claude/settings.json`, or `.codex/hooks.json`. The
  cage does not widen itself; ask the human.
- Never call work done, verified, safe, or ready without evidence you can name.

## Self-iteration

This OS is supposed to get tighter, not heavier.

- When <not constructed yet> corrects you on the same thing twice, propose a rule:
  `./taos propose --agent <you> --kind atom --title "..." --body "..." --atom-json <file>`.
  An atom is a lesson a machine can check. Once the human promotes it, it runs
  in `taos doctor` forever, and you can stop remembering it.
- When a mechanism stops earning its keep, propose retiring it
  (`--kind retire`). Removing something is as valuable as adding it.
- `./taos retro` shows what went stale and which corrections repeated.
- When `taos kernel freshness` says a kernel drifted, run
  `./taos kernel regen-prompt PROJECT_KERNEL` and follow it.

## Where things live

| What | Where |
|---|---|
| Tasks, claims, events, decisions, gate runs | `.taos/` (the `taos` command owns these) |
| Handoffs | `.taos/handoffs/` |
| Today's brief | `.taos/projections/brief.md` |
| Rules you must follow | `policies/` |
| Distilled context | `kernels/` |
| Checkable corrections | `atoms/promoted_atoms.json` |

## Commands you will actually use

```bash
./taos status --compact
./taos task list
./taos task create --agent <you> --title "..." --next-action "..."
./taos start  --agent <you> --task PREFIX-N --session "PREFIX-N | label"
./taos capsule PREFIX-N
./taos task comment PREFIX-N --agent <you> --session "..." --body "..."
./taos task evidence PREFIX-N --agent <you> --ref "..."
./taos decide ask --agent <you> --task PREFIX-N --question "..." --option A --option B
./taos gate run --agent <you> --task PREFIX-N
./taos handoff template PREFIX-N --from <you> --to <them> --session "..."
./taos finish --agent <you> --task PREFIX-N --state review --reason "..." --session "..."
./taos doctor
```

## Episode marker

End a session that opened, handed off, or finished real work with exactly one
HTML comment as the last line of your final message. Ordinary turns get no
marker.

```
<!-- ep: id=<slug> phase=<start|iterate|handoff|done|abandoned> outcome=<landed|reworked|corrected|blocked|unknown> modality=<code|docs|planning|review|ops|mixed|unknown> [counterpart=codex|claude] -->
```

It is recorded as one sanitized row. No prose, no paths, no secrets.
