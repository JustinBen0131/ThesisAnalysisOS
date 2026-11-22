# Gates

A gate is a command the human said must pass before work is called
reviewable. They are in `.taos/config.json` under `gates`, defaulted from the
stack at setup, edited by the human since.

## The contract

```bash
taos gate list                                 # what is configured
taos gate run --agent <you> --task <ID>        # run what needs running, record the result
taos gate show --task <ID>                     # per gate: holds, fails, stale or unknown, and why
taos why <ID>                                  # the same, with everything else the task rests on
```

`gate run` executes each command in the task's worktree (or the workspace,
if the worktree does not exist yet), captures the exit code and the last
lines of output, writes `.taos/gates/<ID>_<ts>.json`, and attaches it to the
task as evidence.

**A result belongs to the files it tested.** Each result is stored with a
fingerprint of what the gate read. A pass holds while those files are the
same bytes, however old it is, and stops holding the moment one changes,
however recent it is. A gate that already passed on exactly these files is
not run again, whichever task ran it; the record says it was reused, and
`--force` runs it anyway.

**Closure is enforced in one place.** A task moves to `review` or `done` only
if every gate holds on the files as they are now. That is true for
`taos finish`, for `taos task transition` and for the panel, because all
three go through the same function.

## Saying what a gate reads

With nothing declared, any change to the workspace makes every gate stale.
That is safe and it reruns more than it needs to. To be more exact, name the
domains in the config and say which a gate reads:

```json
"basis": {"domains": {"analysis": ["src/*", "data/*"], "figures": ["figs/*"]}, "ignore": ["*.log"]},
"gates": [{"name": "fit", "command": "python3 check.py", "depends_on": ["analysis"]}]
```

Then an edit under `figs/` leaves `fit` alone, an edit under `src/` makes it
stale, and an edit to a file no domain claims makes it `unknown`, because
nobody said whether that file matters. Two limits to keep in mind:

- In the open, the declaration is trusted. A gate that reads a folder it did
  not name will be reused when that folder changes. When in doubt, declare
  more, or isolate the gate (below).
- A domain is what its patterns match on disk, tracked by git or not.
  Measured data that git ignores counts once a domain names it. With no
  domains declared, the workspace is what git lists, and an ignored file is
  not seen.
- TAOS sees files in the workspace. A gate that depends on the network, the
  clock or the environment should set `"max_age_hours"`, after which its pass
  is stale whatever the files say.

## Isolating a gate

```json
"gates": [{"name": "fit", "command": "python3 check.py", "depends_on": ["analysis"], "isolated": true}]
```

An isolated gate runs in an empty folder that holds only the files its
result is filed under: the domains it depends on, and any file no domain
claims. A file it did not declare is not there to be read, so its result
cannot be reused wrongly. A failure ends with a line saying what it could
read. Three things to know:

- What the gate writes is discarded. A gate is a question, not a step that
  produces files.
- Files are placed by hard link where the filesystem allows, and by copy
  otherwise. A gate that rewrites one of its inputs changes the original,
  and that run is reported `unknown`.
- A gate that needs `.git`, an absolute path, the network, or more than
  2,000 files in one domain cannot run this way.

## Rules

- Run the gates as configured. Do not substitute a narrower command because
  it is faster.
- Never edit a gate command to make it pass. Editing a gate makes its earlier
  results stale. If a gate is wrong, propose the change
  (`taos propose --kind policy`) and say why.
- A failing gate is a blocker. Fix it, or finish as `blocked` naming it.
- `--skip-gates` on `finish`, and `--waive "<reason>"` on `task transition`,
  exist for the case where gates genuinely do not apply (a docs-only
  change). The reason is recorded, and `taos why` shows the task as closed
  without a holding check until the gates pass. Using it to dodge a red gate
  is a correction waiting to happen.
- A passing gate is not acceptance. When the human has looked at the result,
  `taos task accept <ID>` records that they accepted that version. An edit
  afterwards does not inherit it.

## Adding gates

Anything the human would run before trusting a change belongs here: tests,
lint, format check, type check, a smoke script. Keep the total under a few
minutes; a gate nobody waits for is a gate nobody runs.
