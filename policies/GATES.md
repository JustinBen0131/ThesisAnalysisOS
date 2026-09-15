# Gates

A gate is a command the human said must pass before work is called
reviewable. They are in `.taos/config.json` under `gates`, defaulted from the
stack at setup, edited by the human since.

## The contract

```bash
taos gate list                                 # what is configured
taos gate run --agent <you> --task <ID>        # run them all, record the result
taos gate show --task <ID>                     # the latest run
```

`gate run` executes each command in the task's worktree (or the workspace,
if the worktree does not exist yet), captures the exit code and the last
lines of output, writes `.taos/gates/<ID>_<ts>.json`, and attaches it to the
task as evidence.

`taos finish --state review` and `--state done` refuse without a passing run
in the last 24 hours.

## Rules

- Run the gates as configured. Do not substitute a narrower command because
  it is faster.
- Never edit a gate command to make it pass. If a gate is wrong, propose the
  change (`taos propose --kind policy`) and say why.
- A failing gate is a blocker. Fix it, or finish as `blocked` naming it.
- `--skip-gates` exists for the case where gates genuinely do not apply (a
  docs-only change). It records the reason as evidence and the guard asks the
  human. Using it to dodge a red gate is a correction waiting to happen.

## Adding gates

Anything the human would run before trusting a change belongs here: tests,
lint, format check, type check, a smoke script. Keep the total under a few
minutes; a gate nobody waits for is a gate nobody runs.
