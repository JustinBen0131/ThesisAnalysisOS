# The manual

For the human. The agents read `AGENTS.md`; you read this.

## 1. What you get

- One task list both agents share, with ids that never change.
- Claims: a lease on a task, a branch, a worktree, or a path. While one agent
  holds it, the other cannot write there. Reading is always free.
- Lanes: a workspace reserved for one agent is off limits to the other, enforced
  by the guard, not by asking nicely.
- Worktrees or branches per task, computed and printed for the agent by
  `taos start`, so context stays bounded and nothing lands on main by accident.
- Gates: your test and lint commands, run and recorded before anything may be
  called reviewable.
- Handoffs: a file with a fixed shape that the tool refuses if it is vague.
- Decisions: agents queue questions for you instead of stalling.
- A brief: what changed, what needs you. Top line reads `No action needed.`
  most mornings, and that is the goal.
- A panel: one local page, on when you want it, off when you do not.
- Self-iteration: corrections become checkable atoms; kernels expire; a weekly
  retro says what went stale; burns archive-verify-delete old working files.

## 2. Install (sixty seconds)

Clone it, then re-home it as your own private repo. You are meant to rewrite
the policies, the questions, and the guard rules; that is easier when the
history is yours.

```bash
git clone https://github.com/JustinBen0131/ThesisAnalysisOS.git ~/my-os
cd ~/my-os
rm -rf .git && git init -b main && git add -A && git commit -m "my OS"
gh repo create <you>/<your-os-repo> --private --source=. --remote=origin --push
codex        # or: claude
```

(To keep pulling upstream improvements instead: `git remote rename origin
upstream`, then create your own `origin`.)

First message to the agent:

```
Read BOOTSTRAP.md in this repo and follow it exactly. Ask me the ten bootstrap questions in one message, then construct the OS from my answers. Do not touch anything outside this directory until I have answered.
```

Requirements: macOS or Linux, Python 3.9+, git. Nothing is installed.

### The repo split

Two repos, two failure domains:

- **This one, private.** The runtime, your `AGENTS.md`, your policies,
  kernels, atoms, hooks. `.taos/` (tasks, claims, events, handoffs, gate runs)
  is git-ignored, so your working state stays on your disk.
- **Your work repos, shared.** They receive a four-line block in `AGENTS.md`
  and `CLAUDE.md`, a `.taos-link.json`, and the hook files only if they did
  not already exist. Nothing else, ever.

If you do not want even those three in your team's history, exclude them
locally rather than in `.gitignore`:

```bash
printf '.taos-link.json\n.codex/hooks.json\n' >> <work-repo>/.git/info/exclude
```

Full rules: `policies/REPO_SPLIT.md`.

## 3. Day 1

After construction:

```bash
./taos status            # ten lines: hot work, decisions owed, claims, health
./taos panel on          # opens http://127.0.0.1:4331
```

Then open a workspace repo (or this clone) in Codex or Claude and say:

```
work on <PREFIX>-1
```

The agent runs `taos start`, reads the capsule, creates its worktree and
branch as instructed, and works. When it is done it runs the gates and
`taos finish`. You will see the task move in the panel.

Two things to check on day one:

1. `./taos doctor` is green. Warnings are fine; failures are not.
2. Open one of your linked workspaces and confirm `AGENTS.md` ends with the
   `<!-- taos:begin -->` block. Your original content is untouched above it.

## 4. The daily loop

Morning:

```bash
./taos brief --print
```

Read the top line. If it says `N item(s) need you.`, the items are listed
right under it: decisions to answer, stale claims to release, blocked work.
Answer decisions in the panel (Decisions tab) or:

```bash
./taos decide answer dec_xxxx --choice yes --note "..."
```

Working: talk to the agents as you already do. Say the task id when you know
it. If you do not, say the work and the agent will find or create the task.

Evening: nothing. The brief regenerates on demand; the state is already on disk.

## 5. Working with two agents

They are peers. Give either of them any task. What keeps them apart:

- `taos start` claims the task, its branch, and its worktree. The other agent's
  `start` on the same task fails with exit code 4 and a message saying who
  holds it.
- A workspace you reserved for one agent (Q3) is write-protected against the
  other by the guard.
- A claim goes stale after 6 hours without a heartbeat. The other agent may
  then take it over with a reason; the guard asks you first.

Handing work across: the finishing agent writes a handoff file with five
sections and the tool refuses it if any is missing. The receiving agent
runs `taos capsule <ID>` and gets the state, the evidence, and the literal
next command.

To move work yourself:

```bash
./taos claim status
./taos claim release --agent human --id clm_xxxx --force
./taos task transition <ID> --agent human --to next --reason "reassigning"
```

## 6. Git discipline

What you chose in Q4 is enforced:

- Worktree mode: each task gets `<workspace>-worktrees/<id>-<slug>` on branch
  `<pattern>`. The agent is told the exact `git worktree add` command.
- Branch mode: a branch per task in the workspace.
- Fork mode: each agent already has its own checkout; branches inside it.
- Protected branches: the guard asks before any commit made while on them and
  refuses pushes to them outright.
- Merge policy: with `human_pr` the agents open PRs and stop. Only you merge.

Cleaning up worktrees after a merge is yours to do (`git worktree remove`);
the guard refuses `--force` removal from agents.

## 7. Gates

`taos gate list` shows them. `taos gate run --agent <a> --task <ID>` runs them
in the task's worktree and records the result as evidence on the task. Without
a passing run in the last 24 hours, `taos finish --state review|done` refuses.
Agents can pass `--skip-gates` with a reason; the guard asks you, and the skip
is recorded as evidence so it never hides.

Change the gates by editing `.taos/config.json` under `"gates"`.

## 8. Correcting an agent so it compounds

When an agent does something wrong, correct it as you normally would. When it
happens a second time, say: "propose an atom for this". The agent writes a
checkable rule (a regex over a file, a file that must exist, or a `taos`
command that must exit zero) and queues it. You see it under Atlas in the
panel, or:

```bash
./taos proposals list
./taos proposals decide prop_xxxx --status accepted
./taos atoms promote prop_xxxx --by human
```

From then on `taos doctor` and every brief check it. Lessons that cannot be
checked go into `kernels/PRINCIPAL_KERNEL.md` instead, by the agent, as one
line each.

## 9. The panel

`./taos panel on` / `./taos panel off` / `./taos panel status`. Loopback only,
token-protected writes, no external requests. Tabs, always in this order:

- Today: the top line, decisions (at most two), what changed, the hot rail.
- Work: columns by status. Cards wrap; nothing animates.
- Claims: who holds what, for how long, with a release button.
- Decisions: every open question with its options.
- Handoffs: the files, viewable in place.
- Atlas: doctor, kernels, atoms, proposals (accept/reject), files past their
  TTL, and the list of things only you may do.

Every element is a row in `.taos/`. There are no scores, streaks, or badges.

## 10. Weekly

```bash
./taos retro             # what went stale, which corrections repeated, suggestions
./taos kernel freshness  # which distilled context has rotted
./taos burn plan         # working files past their TTL
./taos burn execute --date YYYY-MM-DD --approve
./taos burn recall  --date YYYY-MM-DD      # undo, from the verified archive
```

A burn archives the files, verifies the archive restores byte for byte, and
only then deletes. Tasks, claims, events, config, atoms, and kernels are
never burn fuel.

## 11. Turning it off and on

Three levels, all reversible, none of which touch your state:

- `./taos pause` drops the ceremony: agents stop being asked to map tasks,
  claim, or run gates, and the guard keeps only the safety floor (secrets,
  force pushes, the store, the cage). `./taos resume` brings it back. Use it
  for a quick fix or a day off.
- `./taos panel off` stops the only process the OS ever runs. There are no
  daemons, timers, or scheduled jobs.
- `./taos bootstrap unlink-workspace <path>` removes exactly what linking
  added to a repo: the marked block, the link file, and the hook files if the
  OS wrote them. Your own files are never touched.

Everything else is a file that does nothing until you run `taos`.

## 12. What lives where

| Path | What | Yours to edit? |
|---|---|---|
| `.taos/config.json` | your answers, as config | yes, carefully |
| `.taos/tasks.json`, `claims.json`, `events.jsonl` | the state | no, use `taos` |
| `.taos/handoffs/`, `.taos/gates/`, `.taos/briefs/` | evidence | read |
| `AGENTS.md`, `CLAUDE.md` | the agents' contract | yes |
| `policies/` | the rules | yes |
| `kernels/` | distilled context | agents maintain; you may edit |
| `atoms/promoted_atoms.json` | checkable corrections | through proposals |
| `hooks/`, `.claude/settings.json`, `.codex/hooks.json` | the cage | only you |

`.taos/` is git-ignored. Your state never leaves your machine unless you copy it.

## 13. Uninstall

```bash
./taos panel off
rm -rf ~/ThesisAnalysisOS
```

In each linked workspace: delete the block between `<!-- taos:begin -->` and
`<!-- taos:end -->` in `AGENTS.md` and `CLAUDE.md`, delete `.taos-link.json`,
and delete `.codex/hooks.json` and `.claude/settings.json` if they were
installed by the OS (if they existed before, the OS wrote a `*.taos-snippet.json`
next to them instead and touched nothing).

## 14. Troubleshooting

- `TAOS not constructed`: run the bootstrap (section 2).
- `no TAOS home found`: run from inside the clone or a linked workspace, or
  set `TAOS_HOME=/path/to/ThesisAnalysisOS`.
- `scope is held by another agent` (exit 4): the other agent has it. Wait,
  hand off, or release it as a human with `--force`.
- `has no passing gate run`: run `taos gate run`, or fix the gates.
- `the panel did not come up`: another process owns the port. `--port 4332`.
- Doctor `fail` on `task_ids_valid` or `allocator_monotonic`: someone edited
  `.taos/` by hand. Restore from git or from a burn archive; never patch the
  numbers.
- An agent ignores the contract: check that `AGENTS.md` in the workspace ends
  with the TAOS block, and that the hooks are installed there.

## 15. FAQ

**Does it need the internet?** No. Nothing here calls a network.

**Does it call a model?** No. Briefs, kernels, doctor, panel: all deterministic.

**Can I use only one agent?** Yes. Everything works with one; claims just never
conflict.

**Can I edit the questions or the templates?** Yes. `bootstrap/QUESTIONS.md`
and `taos_core/templates/`. Re-run `taos bootstrap construct` to re-render;
it is idempotent and keeps your tasks.

**How do I update the OS itself?** `git pull` in the clone. Your state is in
`.taos/` and is ignored by git. If `.codex/hooks.json` conflicts, keep yours.

**Where is the spec?** `docs/SPEC.md`. Any agent changing the OS reads it first.
