# Claims

A claim is a scope-local mutex with a heartbeat. It is how two agents share a
codebase without a coordinator.

## Scopes

`task:AZ-7`, `branch:az/az-7-fix`, `path:src/parser`, `path:/abs/worktree`,
`repo:name`, `policy:name`, `panel`, `kernel:NAME`, `atoms`, `burn`. Exact
strings only. Two `path:` scopes conflict when one is inside the other.

## Rules

- `taos start` claims the task, its branch, and its worktree or lane. Add
  `--scope path:...` for areas you will touch outside them.
- A live claim by the other agent on an overlapping scope blocks yours with
  exit code 4. Do not work around it. Work on something disjoint, or hand off.
- Re-acquiring your own overlapping claim refreshes its heartbeat.
- Claims go stale after `claim_stale_hours` (default 6) without a heartbeat.
  On long work, `taos claim heartbeat`.
- A stale claim may be taken over with `--takeover --reason "..."`. It is
  logged, and the guard asks the human.
- `taos finish` releases every claim of yours on that task. Release extra
  scopes yourself if you claimed them separately.
- Reading never needs a claim. Neither does answering a question.

## Lanes

A workspace reserved for one agent in the config is that agent's lane. The
guard denies the other agent's writes there. Lanes are for bounding context:
an agent in its own checkout sees only its own state and cannot trample the
other's.

## Humans

The human may release any claim with `--force`. The panel's Claims tab has a
button for it.
