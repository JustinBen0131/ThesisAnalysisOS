# The manual

Start here if you want to see what TAOS can tell you about a result or a compute campaign. From a downloaded or cloned copy, run either command with Python 3.9 or later. Both work offline before you set up a project.

| What do you want to know? | Try it from the repository root |
| --- | --- |
| A measurement changed. Which earlier results still hold? | `python3 taos demo` |
| Three sensor outputs came back from a compute run. Which can I use? | `python3 taos usage progress --packet examples/hpc/campaign.json` |

The demo changes one pendulum reading and shows why the fit needs checking again. In the sensor example, two outputs pass their supplied checks and one has no readings. Its recorded worker time still counts. To use the same tools on your own project, continue to [Set up a private project](#2-set-up-a-private-project).

## 1. What you get

- One task list all project agents share, with stable IDs.
- Claims record which agent has taken responsibility for a task, branch,
  worktree or path. Other tools with write access can still change its files.
- Lanes: reserve a workspace for one agent. When the guard is active,
  it blocks writes by other agents through the configured hooks.
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

<a name="2-install-sixty-seconds"></a>

## 2. Set up a private project

Make a private copy from the template. Change the example GitHub owner and
repository name in the first two lines.

```bash
taos_owner="YOUR_GITHUB_USERNAME"
taos_repo="my-private-taos"
gh repo create "$taos_owner/$taos_repo" --private --clone --template JustinBen0131/ThesisAnalysisOS &&
  cd "$taos_repo" &&
  codex  # or: claude
```

On github.com the same thing is the **Use this template** button. Two other
ways, if you prefer them:

- To keep pulling upstream improvements, `git clone` this repository, then
  `git remote rename origin upstream` and create your own private `origin`.
- For a local-only copy, clone it and run `git remote remove origin` in
  your clone. You can use the OS with no remote and keep the original history.

First message to the agent:

```
Read BOOTSTRAP.md in this repo and follow it exactly. Ask me the ten bootstrap questions in one message, then construct the OS from my answers. Do not touch anything outside this directory until I have answered.
```

For this assisted setup, use macOS or Linux, Python 3.9 or later, Git, and
Codex or Claude Code. The command above also uses the GitHub CLI (`gh`). Run the manual's
`./taos` commands from the root of your private OS clone. If the launcher
isn't executable, run `python3 taos` there instead.

### The repo split

Two repos, two failure domains:

- **This one, private.** The runtime, your `AGENTS.md`, your policies,
  kernels, atoms, hooks. `.taos/` (tasks, claims, events, handoffs, gate runs)
  is git-ignored, so your working state stays on your disk.
- **Your work repos, shared.** Each workspace named in setup gets a marked
  block in `AGENTS.md` and `CLAUDE.md` and a `.taos-link.json` pointer. TAOS
  can also install hooks. It keeps existing settings and can write a
  separate snippet for you to review and merge.

The block, pointer and hooks can contain the absolute path to your OS.
Review those changes before staging them in a shared repo. A local Git
exclude can keep new files out of the index. It has no effect on already
tracked files such as an existing `AGENTS.md`.

See [The repo split](policies/REPO_SPLIT.md).

## 3. Day 1

After successful construction, check the setup and list your task IDs:

```bash
./taos doctor
./taos status --compact
./taos task list
```

If doctor reports a failure, read the named check before starting work. If
you want the local panel, run `./taos panel on`. Its default address is
`http://127.0.0.1:4331`.

If you left question 3 blank, open the OS clone in Codex or Claude. It is
your first workspace and needs no link to itself. If you named another repo,
open that workspace and look for the TAOS block between `<!-- taos:begin -->`
and `<!-- taos:end -->` in `AGENTS.md` or `CLAUDE.md`. It includes a command
with the absolute path to the OS launcher and its home. Copy that command as
printed when running from a workspace or its worktree.

Give the agent a task ID from `./taos task list`, for example `work on CMP-1`.
`taos start` claims the task and prints a capsule with its next action,
workspace assignment, and the commands for its branch or worktree. Use
`./taos task show CMP-1` with the same ID to see any completion criterion.
The agent follows the capsule's commands to begin. When it finishes, it runs
the gates and records the outcome for you to review.

If you opted out of workspace hooks or setup reported a settings conflict,
the workspace stays linked. Run the status command in its TAOS block at the
start of each session until any hook entries you want are merged and enabled.

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

### Follow the evidence behind your compute

A backup of `.taos/` preserves filed summaries. To repeat a compute review, keep the original packet and the files it cites alongside your project backup. If you open a report in the browser, keep its JSON file to reopen it after refreshing the page.

Run `./taos usage progress` to see which tasks have run checks, reused checks or received a compute review. Add `--task TASK-ID` for one question. The view identifies each campaign, its last review, recorded worker time, and the current standing of the task checks and acceptance. Use `./taos usage show` separately for the token usage your local tools expose. [Try the three-output example](policies/HPC.md)

## 5. Working with multiple AI agents

One person can assign separate tasks to many agent sessions. Give sessions
distinct role names when their claims and handoffs need separate attribution.
For example, a planner can prepare a run, a builder can carry it out and a
reviewer can check the result. Several sessions can use one tool, or you can
share a selected handoff with an assistant in another tool. You choose what
each receives and which decisions need your approval.
[Set up the roster](docs/AGENT_ROLES.md) · [Use a local or web assistant](docs/AGENT_INTERFACES.md)

The following rules apply to each named role.

- `taos start` claims the task, its branch, and its worktree. Another agent’s
  `start` on the same task fails with exit code 4 and a message saying who
  holds it.
- When a workspace is reserved for one agent (Q3), the configured guard
  blocks other agents’ writes through its hooks.
- A claim goes stale after 6 hours without a heartbeat. Another agent may
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
- Protected branches: the guard checks the branch or destination it can identify.
  Use hosting-service branch protection when all pushes require review.
- Merge policy: with `human_pr`, agents are instructed to open a PR and leave
  the merge decision to you.

Cleaning up worktrees after a merge is yours to do (`git worktree remove`);
the guard refuses `--force` removal from agents.

## 7. Gates

`taos gate list` shows them. `taos gate run --agent <a> --task <ID>` runs them
in the task's worktree and records the result as evidence on the task. Each
result is kept with a fingerprint of the files the gate read. A task cannot
move to review or done, by any route, unless every gate holds on the files as
they are now: an old pass on unchanged files counts, a fresh pass on files
edited since does not. Agents can pass `--skip-gates` with a reason; the guard
asks you, and the task is shown as closed without a holding check until the
gates pass.

`taos why <ID>` shows everything a task rests on and whether each part still
holds: its checks, the instructions it was closed under, its work products
and their inputs, your acceptance. `taos why` alone lists what no longer
holds across all closed work. When you have looked at a result and accept it,
run `taos task accept <ID> --by human`. The acceptance records the supplied
reviewer label, input state and applicable instructions. An edit to the
recorded inputs changes its standing. See `policies/GATES.md`.

Change the checks under `"gates"` in `.taos/config.json`. Record who reviewed
the proposed definition and why. After changing a check, review the new
calculation and record a fresh sign-off. The local acceptance record alone
does not establish who edited the check or approved that definition.

**Say what a check reads.** By default TAOS uses files Git tracks or would
track, and ordinary project files outside Git. An undeclared workspace with
no visible inputs reports `unknown`. Name the folders a check reads to
include scientific data that Git ignores.

```json
"basis": {"domains": {"analysis": ["src/*", "data/*"], "figures": ["figs/*"]}},
"gates": [{"name": "fit", "command": "python3 check.py", "depends_on": ["analysis"]}]
```

An edit under `figs/` now leaves `fit` standing, and two tasks that ask for
`fit` on the same files share one run. A domain is what its patterns match on
disk, so measured data that git ignores counts once a domain names it.

**Give a check a private copy of its inputs.** With `"isolated": true`,
the runner copies the selected inputs into a temporary folder, verifies
their fingerprints and runs the check there with a fixed environment. Writes
through those copies leave the originals intact. On supported macOS systems,
TAOS also probes network and workspace-read restrictions and records which
restrictions were available. Commands still run under your operating-system
account. Use trusted commands. Strict mode requires the probed restrictions.

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

The recorded decision belongs to that proposal ID. A later proposal can ask
the same question. Review the change on its merits each time. A person with
write access can also edit the local configuration and promoted rules.
From then on `taos doctor` and every brief check the promoted rule. Lessons that cannot be
checked go into `kernels/PRINCIPAL_KERNEL.md` instead, by the agent, as one
line each.

## 8a. Changing the system like an experiment

Six commands turn "I think this helped" into a record. The reasons are in
`docs/METHOD.md`; the binding rules are in `policies/SCIENCE.md`.

| When | Run |
|---|---|
| Before you change how the system works | `taos change register`, then `taos change seal` |
| After the change has run for its window | `taos change score` (another agent, or you) |
| You corrected the same thing twice | `taos lesson add`, with your words and the moment it applies |
| An agent is about to reply, submit, delete or install | `taos lesson at <moment>` |
| You want a new limit or brake | `taos replay` on your own history first |
| You saved an instruction that has a deadline or a scope | `taos rule add --expires ... --scope ...` |
| A number looks wrong, or suspiciously right | `taos anchor open`, then both anchors and a prediction |
| A new model, or a big change to the system | `taos bank score` on your past decisions |

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
- `./taos panel off` stops the local panel. The optional setup page has its own
  local server. An MCP connection uses a separate process started by its client.
- To detach a workspace, run `./taos bootstrap unlink-workspace` with its
  quoted path, for example `./taos bootstrap unlink-workspace "$HOME/code/My Project"`.
  Read the output to see what was removed and what was kept. TAOS uses the
  link's ownership record to remove its unchanged generated files. Edited
  hooks, unrelated snippets and files it cannot attribute are kept.

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

From the OS clone, run `./taos panel off` and unlink each linked workspace
as described in section 11. Review any settings you merged or edited and
remove the TAOS entries yourself if you no longer want them. Once you have
saved any tasks, evidence and kernels you want to keep, remove the private
OS clone if you no longer need it.

## 14. Troubleshooting

- `TAOS not constructed`: run the bootstrap (section 2).
- `no TAOS home found`: use the full command from your workspace's TAOS
  block, including `--home` and the printed quotes. In the OS clone, use
  `./taos`.
- `scope is held by another agent` (exit 4): the other agent has it. Wait,
  hand off, or release it as a human with `--force`.
- `has no passing gate run`: run `taos gate run`, or fix the gates.
- `the panel did not come up`: another process owns the port. `--port 4332`.
- Doctor `fail` on `task_ids_valid` or `allocator_monotonic`: check that the
  setup answers still use your original task prefix. If task state was
  damaged, use a known-good backup of `.taos/`.
- A session starts without a TAOS status message: read the workspace's
  TAOS block and run the status command shown there. If you chose to use
  hooks, check whether the settings were merged and your client loaded them.
- Setup returned an error: read the failed link or doctor check in its output.
  Fix the named issue before retrying. Setup may have already written the
  config, seeded tasks, or linked other workspaces.

## 15. FAQ

**Does it need the internet?** The TAOS CLI runs locally. Your agent client,
Git remotes or project checks may need a connection.

**Does it call a model?** No. Briefs, kernels, doctor, panel: all deterministic.

**Can I use only one agent?** Yes. Everything works with one; claims just never
conflict.

**Can I edit the questions or the templates?** Yes. They live in
`bootstrap/QUESTIONS.md` and `taos_core/templates/`. From the OS clone,
revisit your answers, keep your original task prefix, and run
`./taos bootstrap validate`, then
`./taos bootstrap construct`. Construction updates config from those answers,
adds missing task titles, and can refresh unedited generated files. It keeps
existing tasks, edited kernels and customized root instructions. To apply a
new template to a file you customized, merge the changes yourself.

**How do I update the OS itself?** `git pull` in the clone. Your state is in
`.taos/` and is ignored by git. If `.codex/hooks.json` conflicts, keep yours.

**Where is the spec?** `docs/SPEC.md`. Any agent changing the OS reads it first.
