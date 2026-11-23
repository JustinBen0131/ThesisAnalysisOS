# Architecture

## Reading this repository cold

For a person or an agent who has to understand, test or change TAOS itself.
Nothing here needs setup, and none of it should be bootstrapped first.

**The idea.** A recorded result is kept with who made it and what it stood
on, and is answered later as `holds`, `fails`, `stale` or `unknown`, with the
reason. Everything below is that one comparison applied to a different kind
of record.

| To understand | Read | Its tests |
|---|---|---|
| the one comparison | `taos_core/basis.py` | `tests/test_standing.py` |
| check results, sharing between tasks, isolation | `taos_core/gates.py` | `tests/test_standing.py`, `tests/test_counterexamples.py` |
| the single point of closure, and acceptance | `TaskStore.transition` and `TaskStore.accept` in `taos_core/tasks.py` | `tests/test_closure.py` |
| instructions by date and scope | `taos_core/rules.py` | `tests/test_counterexamples.py` |
| what an agent is handed when it starts | `taos_core/lifecycle.py` | `tests/test_standing.py` |
| `taos why` | `taos_core/standing.py` | `tests/test_standing.py` |
| every case that once went wrong | `tests/test_counterexamples.py` | `python3 evals/at_revision.py` |
| what the repository claims, and whether it still does | `docs/CLAIMS.md` | `python3 evals/claims.py` |

**Verify, cheapest first.**

The historical replay requires a Git checkout containing the revisions named by the study. The local CLI and saved-evidence checks also work in the source ZIP.

```bash
./taos demo                      # the idea working on a small measurement, in a throwaway folder
./taos selftest                  # the whole suite, about a minute
python3 evals/claims.py          # every claim in docs/CLAIMS.md against the code as it is
python3 evals/at_revision.py     # today's counterexamples against the two earlier releases
python3 evals/reuse_frontier.py  # the reuse experiment, about two minutes
python3 evals/mutations.py       # removes each protection in turn, about three minutes
```

**For a program.** `taos why [TASK] --json` and `taos gate show --task ID
--json` return the verdicts as data, `taos why --check` exits 1 when
something does not hold, and `python3 evals/claims.py --json --strict` does the same
for the repository's own claims.

**Changing it.**

- A change under `taos_core/` or `tests/` makes the recorded measurements
  stale. Rerun the three evaluations with `--write`, and propose the change
  once `python3 evals/claims.py --strict` passes. CI runs the same command.
- A new protection gets a case in `tests/test_counterexamples.py` and an
  entry in `evals/mutations.py`, so that removing it is noticed.
- A new claim gets a row in `docs/CLAIMS.md`, or is not made.
- `docs/SPEC.md` is binding. Section 11c covers the basis.
- The root `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/` and `hooks/` are
  part of the product: the contract and the guard a constructed OS gives its
  agents. They are live in this checkout too, so the guard will refuse an
  agent's edit to the hooks or the settings themselves.

## The moving parts

```
 human ──── taos panel on ───► http://127.0.0.1:4331  (projection)
   │                                   ▲
   │  taos brief / status / doctor     │ reads
   ▼                                   │
 ┌──────────────── .taos/ ─────────────┴────────────────┐
 │ tasks.json   allocator.json   claims.json            │  canonical
 │ events.jsonl (append-only)    decisions.json         │  written only by `taos`
 │ handoffs/    gates/    proposals/    telemetry/      │
 └──────────────────────────────────────────────────────┘
   ▲                          ▲
   │ taos start/finish/…      │ taos start/finish/…
 ┌─┴────────┐             ┌───┴──────┐
 │  codex   │             │  claude  │   peers; same contract (AGENTS.md)
 └─┬────────┘             └───┬──────┘
   │ PreToolUse ─► hooks/guard.py ◄─ PreToolUse │   one guard for both
   │ SessionStart ─► status --compact           │
   │ Stop ─► episode label                      │
   ▼                                            ▼
 workspace (worktree per task, or a reserved lane per agent)
```

## Flow of one task

Run the commands from a configured TAOS home with an existing task `AZ-7`.

1. The human asks Codex to work on AZ-7.
2. Codex starts the task.

   ```sh
   ./taos start --agent codex --task AZ-7 --session "AZ-7 | prepare result"
   ```

   The store maps the session and claims the task and any configured
   branch or worktree. It marks the task active and hot, refreshes the
   projections and prints the capsule with the workspace commands.
3. Codex works in the worktree. Evidence and comments land on the task.
4. Codex runs the checks. TAOS saves the check record in `.taos/gates/`
   and adds it to the task's evidence.

   ```sh
   ./taos gate run --agent codex --task AZ-7
   ```

5. Codex generates the handoff and fills in `h.md` before finishing.

   ```sh
   ./taos handoff template AZ-7 --from codex --to claude --session "AZ-7 | prepare result" > h.md
   ```

   After the checks pass, this validates and saves the handoff, moves the
   task to review and releases the claims.

   ```sh
   ./taos finish --agent codex --task AZ-7 --state review --session "AZ-7 | prepare result" \
     --reason "Checks passed. Ready for review." --handoff-file h.md --to claude
   ```

6. Claude starts the same task and sees the handoff in the capsule.

   ```sh
   ./taos start --agent claude --task AZ-7 --session "AZ-7 | review result"
   ```

7. The human sees the task move in the panel and answers any queued decision.

## Modules

| Module | Owns |
|---|---|
| `paths` | where everything lives; discovery from env, cwd, or `.taos-link.json` |
| `store` | atomic writes, jsonl, one lock, hashing, time |
| `config` | the constructed config, defaults, the dials |
| `events` | the append-only log |
| `tasks` | the task store and every task mutation |
| `claims` | scope-local leases |
| `lifecycle` | `start`, `finish`, `capsule`, lanes |
| `basis` | the one comparison: a recorded result against what it stood on (`holds`, `fails`, `stale`, `unknown`) |
| `gates` | run the must-pass commands; file each result under the check and the bytes it read |
| `standing` | `taos why`: every record a task rests on, read back against the present |
| `rules`, `lessons`, `changes`, `replay`, `bank`, `anchors` | the science layer (`docs/METHOD.md`) |
| `demo` | `taos demo`, and the scratch home the evaluations use |
| `page` | how a run is written for a person: the opener, plain in a pipe, shaded on a terminal |
| `handoff` | template, validate, write, wrapper |
| `decisions`, `proposals` | the human queues |
| `telemetry` | sanitized labels |
| `projections`, `brief` | derived views, the daily brief, retro |
| `kernels`, `atoms`, `burn`, `doctor` | the self-iteration and health layer |
| `panel` | the loopback server and the single-file UI |
| `bootstrap` | ten answers → a constructed OS; workspace linking |
| `cli` | aggregation only |

Every module registers its own subcommands; `cli.py` never knows the verbs.

## Invariants the tests hold

- Ids are monotonic across concurrent creators.
- `done` needs evidence; `blocked` needs a blocker.
- Overlapping live claims by different agents conflict; same-agent re-acquire
  refreshes; takeover needs stale plus reason.
- A handoff without the header or a section is refused.
- No route moves a task to `review` or `done` unless every gate holds on the
  files as they are; a pass on files edited since does not count.
- `unknown` is never reported as `holds`, as `fails` or as zero.
- A declared domain is read from the disk, so an input git ignores is part of
  what a check stood on.
- An isolated check can read only the files its result is filed under.
- The guard denies secret reads, force pushes, store edits, cage edits, and
  writes into the other agent's lane; asks on push; allows `ls`; never crashes.
- Panel writes without the token are 403; path traversal on handoffs is 404.
- Construct is idempotent and never truncates a workspace's existing docs.
- A burn restores byte for byte before it deletes.
