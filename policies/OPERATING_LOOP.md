# The operating loop

The same five steps every session. They are cheap; skipping them is not.

## 1. Orient

`taos status --compact` is injected at session start. Read it. If a kernel
is drifted, read the kernel anyway and note that it may be stale.

## 2. Place

Map the human's request to exactly one task before working:

- existing task: `taos start`;
- new finite work: `taos task create`, then `taos start`;
- a question: answer it, create nothing.

Umbrella tasks are context, not units of work. If the request is a finite
deliverable inside a broad task, create a child (`--parent`) and start that.
Do this once per session. Do not re-shape the list mid-session unless the
scope genuinely changes.

The human supplies intent; you propose closure. Give every real task a
`done_when` (observable) and, where known, a `verification`. Infer the
narrowest reasonable boundary. Tell them in one line only when it is not
obvious: "I'll treat this as done when X, verified by Y." Ask only when two
plausible readings would change what gets produced, verified, or spent. A
vague task must not silently become an infinite project.

## 3. Work in the lane

The capsule tells you the worktree, the branch, and the commands. Work there.
Record evidence on the task as you go (`taos task evidence`). Update
`next_action` whenever it changes. If you are stuck on a human judgment,
`taos decide ask` and keep going on what does not depend on it.

## 4. Verify

`taos gate run`. If it fails, fix it or finish as `blocked` with the failing
gate named. Never edit a gate command to make it pass.

## 5. Finish

`taos finish` with a state, a reason, and evidence. If another agent or a
later session continues, write the handoff first. Close at the task's
`done_when`, not when you run out of things to say, and make it legible in
four short lines: done (the outcome), verified by (the evidence), durable
result (an artifact or procedure, if one now exists), remaining work (none,
or the named follow-up). End the message with the episode marker. Release
nothing by hand; `finish` does it.

## Sizing

One task per durable deliverable. Not one per command, not one per campaign.
A task is the right size when a single session can move it to `review` with
evidence and the human can tell, from the title alone, whether it matters.
