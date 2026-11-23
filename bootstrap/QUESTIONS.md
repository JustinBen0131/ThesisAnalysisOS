# The ten questions

**Send the block between the two ASK markers below verbatim, as one message.**
Do not paraphrase it, do not reorder it, do not add questions of your own, and
do not show the human anything else from this file. Everything after the
closing marker is reference for you, not for them.

Substitute only where a line contains `<...>`: fill those from what you can
see on the machine (the shell username, the timezone, the folder name of the
repo you are in). If you cannot tell, leave the bracket text as it is.

<!-- ASK: send everything between these markers verbatim -->

Reply once, using the question numbers. Say **defaults** for all defaults
or **default** for one. I need an answer to #8.

I'll check your repos and ask up to three specific follow-ups if needed.
Say **proceed** to skip them. I'll build, run the checks, show the result,
and give you five tips. Say **start** to pick up your first task.

**0. Does anything need explaining or adapting?**
Say what to change, leave it blank, or write N/A.

**1. What's your name and timezone?**
Default — `<shell username>`, `<machine timezone>`

**2. What's the project name and its task ID prefix?**
Pick 2 to 8 letters. IDs like PREFIX-1 stay fixed.
Default — `<repo folder name>`, prefix `<FIRST LETTERS>`

**3. Which repos will the agents work in?**
Give full paths, name the primary repo, and mark any checkout reserved for
one agent. You can name each repo. With the guard active, other agents can
read a reserved checkout but cannot write there.
Default — use this OS clone as the workspace

**4. How should Git work be isolated and merged?**
Choose a worktree or branch per task, a checkout per agent, or commits on
main. Name protected branches and say whether you merge through a PR or an
agent can merge after checks pass.
Default — worktree per task, branches like `nr/nr-7-short-title`, protect
main and master, and only you merge

**5. What must pass before work is ready for review?**
Give the commands you run. I record each run. For each check, you can name
the paths it reads so unchanged inputs can reuse a result. Say "isolate it"
to run with only those paths present.
Default (Rust) — `cargo test`, `cargo fmt --all -- --check`,
`cargo clippy --all-targets -- -D warnings`

**6. What can agents do without you?**
- **propose only** — agents edit, ask before every commit, and cannot push
- **branches** — agents commit on task branches and ask before pushing
- **branches and PRs** — agents push task branches and open PRs

By default, you own deploys and releases, merges to main, signing or
broadcasting transactions, handling keys and seed phrases, spending money,
and messaging people as you. Tell me what to adjust.
Default — **branches** and the reserved actions above

**7. What else should I never read?**
TAOS already blocks `.env`, `.pem`, `.key`, `id_rsa`, keystores, mnemonics,
seed phrases, `~/.ssh`, and `~/.aws`. Add project paths such as `fixtures/private`.
Default — nothing extra

**8. What are three to seven real tasks?**
Give one per line as `what you want :: the literal next step`. The fields
`:: what done looks like` and a final priority (`:: P0` through `:: P3`)
are optional. P0 is urgent and P2 is usual. I can propose a finish condition
after reading the repo.

`Fix the flaky parser tests :: run cargo test parser :: parser suite passes twice :: P0`

No default.

**9. What resources should I plan around?**
Name available agents or models, whether compute is constrained, normal, or
abundant, how much context is available and how much to use or hold in
reserve, and anything scarce to protect.
Default — configured agents, normal compute, lean context with a third in reserve

Optional setup choices and defaults — the `codex` and `claude` role names, hooks enabled in the
repos from #3 (existing settings may need a manual merge), dashboard at port
4331, brief at 8:30 am, three queued decisions per day, and no quiet hours.

**10. What should I prioritize, and what mistakes keep recurring?**
Choose conservative, balanced, or exploratory. Name tradeoffs that matter
(quality, your attention, speed, resources, reusable capability, or room
to experiment). Tell me recurring corrections to propose as checks and how
often to review them (daily, weekly, or on request).
Default — balanced, quality and your intent first, then attention, then
resources, with bounded exploration, no corrections yet, and weekly review

<!-- /ASK -->

---

## Reference (do not send this part)

What each answer fills in `.taos/config.json`, and what it changes:

| Q | Keys | What changes |
|---|---|---|
| 1 | `principal_name`, `timezone` | the rendered docs, the brief header |
| 2 | `project_name`, `prefix` | the allocator; ids are permanent |
| 3 | `workspaces[].name/path/primary/agent` | named lanes, or the OS clone itself if omitted. The active guard denies other agents’ writes in a reserved path. `taos start` uses the agent's lane or a shared workspace |
| 4 | `git_isolation` (`worktree`/`branch`/`fork`/`trunk`), `branch_pattern` (`{prefix_lower}`, `{id_lower}`, `{slug}`, `{agent}`), `protected_branches`, `worktree_root`, `merge_policy` (`human_pr`/`agent_after_gates`/`trunk`) | what `taos start` prints and claims; what the guard asks and denies around commit, push, and merge |
| 5 | `gates[]` (each may carry `depends_on` and `isolated`), `domains[]`, `stack` | `taos gate run`; `finish --state review\|done` refuses unless every gate holds on the files as they are now. Stack is auto-detected from the primary workspace (Cargo.toml, package.json, pyproject, go.mod) when unstated |
| 6 | `autonomy` (`propose_only`/`edit_branches`/`push_branches_open_prs`), `human_only[]` | the guard's push and commit verdicts; the list shown in AGENTS.md and the panel |
| 7 | `secret_patterns[]` | merged with the built-in deny list in the guard |
| 8 | `first_tasks[]` | `{title, next_action, done_when?, verification?, priority}`; created as `next`, none hot. If `done_when` is absent, propose one in the sharpen step after reading the repo |
| 9 | `resources.{agents_available, compute, context_available, context_working, context_reserve, protect[]}`; mechanics `agents[]`, `install_hooks_in_workspaces`, `panel.port`, `brief_time`, `attention.max_decisions_per_day`, `attention.quiet_hours` | the controller's compute prior; limits the agents respect; the panel and brief mechanics |
| 10 | `preference.{exploration, priorities[]}`, `agent_corrections[]`, `self_iteration.cadence` | the controller's exploration prior (initial `beta`); each correction becomes a `kind: atom` proposal, unpromoted; cadence shapes how often proposals surface |

Parsing #8: split on `::` and trim each field. The first two fields are
`title` and `next_action`. A final optional field consisting of exactly
`P0`, `P1`, `P2`, or `P3` is `priority`. Any remaining third field is
`done_when`. For example, `Document the parser :: list the error cases :: P3`
sets a priority and leaves `done_when` out.

Parsing #9 and #10: map their words onto the enums (`constrained|normal|abundant`,
`conservative|balanced|exploratory`); free text for context sizes is kept as
given. These are priors and limits, never performance truths; measured
outcomes refine the numbers without asking again.

Shape: `bootstrap/answers.schema.json`. Worked example:
`bootstrap/answers.example.json`. Fill required fields from the answers or
their stated defaults. Omit other keys when the person takes the default.

Parsing #4 and #6: map their words onto the enum values in the table above;
if they say something you cannot map, ask that one thing back, and nothing
else.
