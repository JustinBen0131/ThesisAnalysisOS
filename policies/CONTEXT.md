# Context

Read the smallest thing that answers the question. Every file you load costs
the rest of the session.

## Order of operations

1. `taos status --compact`: injected at session start. Ten lines.
2. `taos policy route "<request>"`: the two or three policies that apply.
3. `taos capsule <ID>`: the compiled answer for one task: state, blockers,
   evidence, decisions, the last handoff's head, where to work.
4. The kernel for the subject (`kernels/`), knowing its freshness.
5. Only then, the source files the capsule and kernel point at.

Do not open the event log, the whole task store, or every policy "to be
safe". That is not safety; it is the opposite.

## Kernels rot, and say so

`taos kernel freshness` marks each kernel `fresh`, `aged`, `drifted`, or
`missing`. A drifted kernel is a hint about where to look, never a fact to
repeat. If you catch a kernel being wrong, that is worth fixing:
`taos kernel regen-prompt <NAME>` tells you how.

## Memory is on the task, not in the chat

Anything you learn that a later session needs goes on the task:
`taos task comment`, `taos task evidence`. Chat is not durable. The
handoff is. The kernel is. The task is.

## When the human says "catch me up"

`taos brief --print` is the answer for the day. `taos capsule <ID>` is the
answer for a task. Do not narrate the event log.
