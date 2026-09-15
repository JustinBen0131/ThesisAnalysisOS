# Architecture

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

1. Human: "work on AZ-7".
2. Agent: `taos start --agent codex --task AZ-7 --session "AZ-7 | ..."`.
   The store maps the session, acquires `task:AZ-7`, `branch:...`,
   `path:<worktree>`, transitions to active, marks hot, refreshes projections,
   writes a label, prints the capsule with the exact git commands.
3. Agent works in the worktree. Evidence and comments land on the task.
4. Agent: `taos gate run` → gate record under `.taos/gates/`, evidence row.
5. Agent: `taos finish --state review --handoff-file h.md --to claude`.
   Handoff validated and stored; transition; claims released; label written.
6. Claude: `taos start` on the same task now succeeds; the capsule shows the
   handoff.
7. Human: sees the task move in the panel; answers any decision queued.

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
| `gates` | run and record the must-pass commands |
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
- `finish --state review` without a fresh gate pass is refused when gates exist.
- The guard denies secret reads, force pushes, store edits, cage edits, and
  writes into the other agent's lane; asks on push; allows `ls`; never crashes.
- Panel writes without the token are 403; path traversal on handoffs is 404.
- Construct is idempotent and never truncates a workspace's existing docs.
- A burn restores byte for byte before it deletes.
