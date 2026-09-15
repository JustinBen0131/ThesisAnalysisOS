# The ten questions

**Send the block between the two ASK markers below verbatim, as one message.**
Do not paraphrase it, do not reorder it, do not add questions of your own, and
do not show the human anything else from this file. Everything after the
closing marker is reference for you, not for them.

Substitute only where a line contains `<...>`: fill those from what you can
see on the machine (the shell username, the timezone, the folder name of the
repo you are in). If you cannot tell, leave the bracket text as it is.

<!-- ASK: send everything between these markers verbatim -->

I'll set this up around how you actually work. Here is the whole process:

1. Answer the questions below in one reply. Number your answers to match.
   Say **defaults** to take every default, or **default** for any single
   one. Only #8 has no default.
2. I'll read your answers and look at your repos. If something is unclear or
   contradicts what I see on disk, I'll ask you at most three follow-ups,
   each tied to something specific I found. If you'd rather skip that,
   write **proceed** anywhere in your reply and I'll build with what I have.
3. I build it, run the checks, show you the result, and give you five tips
   on getting the most out of me. About a minute.
4. You say **start** and I pick up your first task.

**0. Does anything below need more explanation, or not fit how you work?**
Say so here in your own words and I'll reshape it before building anything.
Otherwise leave this blank or write N/A.

**1. What's your name, and what timezone are you in?**
Default: `<shell username>`, `<machine timezone>`

**2. What should I call this project, and what should task IDs look like?**
IDs become PREFIX-1, PREFIX-2, and they never change, so pick something short
you won't mind typing. 2 to 8 letters.
Default: `<repo folder name>`, prefix `<FIRST LETTERS>`

**3. Which repos will you and the agents actually work in? Full paths.**
If you keep a separate checkout per agent, say which path belongs to which
one and I'll make it a hard boundary: the other agent can read there but
never write. Example: `~/code/noir` is mine, `~/code/noir-claude` is Claude's.
Default: no separate repos, everything happens in this folder

**4. How do you want work isolated in git, and how does it get to main?**
Three things:
- A worktree per task, a branch per task, a checkout per agent, or just
  commits on main?
- Which branches should I never commit on or push to?
- Who merges? You only, via PR, or may an agent merge once tests pass?
Default: a worktree per task, branches named like `nr/nr-7-short-title`,
never touch main or master, and only you merge

**5. What has to pass before an agent is allowed to say something is ready?**
Give me the real commands you'd run yourself. Anything that fails these can't
be marked reviewable, and I'll record every run.
Default (Rust): `cargo test`, `cargo fmt --all -- --check`,
`cargo clippy --all-targets -- -D warnings`

**6. How much rope do the agents get?**
- **propose only**: they edit, but every commit needs your nod and pushes are refused
- **branches**: they commit freely on task branches, every push asks you first
- **branches and PRs**: they push task branches and open PRs without asking
And these stay yours no matter what: deploying or releasing, merging to main,
signing or broadcasting a transaction, touching keys or seed phrases, spending
money, messaging people as you. Add or remove anything.
Default: **branches**, and that list as written

**7. Anything I should never read, beyond the obvious?**
Already blocked: `.env`, `.pem`, `.key`, `id_rsa`, keystores, mnemonics, seed
phrases, `~/.ssh`, `~/.aws`. Add anything project-specific, like `wallet` or
`fixtures/private`.
Default: nothing extra

**8. What are you actually working on? Three to seven real things.**
One per line: `what you want :: the literal next step :: what done looks like`.
The last part is optional; leave it off and I'll propose a finish condition
after I've looked at the repo, and you can correct it. Add `P0` if urgent.
Example: `fix the flaky parser tests :: reproduce under cargo test :: full
parser suite passes twice in a row`.
No default. This is the one I need from you.

**9. What resources should I assume I can use?** Rough answers, no token
counts or prices.
- Which agents or model families you actually have, if you know
- Does compute or quota feel constrained, normal, or abundant
- How much context to occupy in normal work, and how much to keep in reserve
- Anything scarce you want protected
- Mechanics, only if you care: which agents (both), hooks into the repos from
  #3 (yes, existing hook files untouched), dashboard port (4331), brief time
  (8:30am), questions queued per day (3), quiet hours (none)
Default: your configured agents, normal availability, lean context with a
third in reserve, mechanics as listed

**10. When things trade off, how should I lean, and what do agents keep
getting wrong for you?**
- Exploration: conservative (stick to what works), balanced, or exploratory
  (try heavier or unfamiliar approaches when they might pay off later)
- What you care about unusually strongly: verified quality, your attention,
  speed, money or quota, reusable capability, room to experiment
- Corrections you keep giving agents. Each becomes a proposal; once an agent
  sees it happen it writes a check so the machine enforces it. And how often
  to bring those up: daily, weekly, or only when you ask
Default: balanced; quality and your intent first, then your attention, then
resources, with bounded room to experiment; no corrections yet; weekly

<!-- /ASK -->

---

## Reference (do not send this part)

What each answer fills in `.taos/config.json`, and what it changes:

| Q | Keys | What changes |
|---|---|---|
| 1 | `principal_name`, `timezone` | the rendered docs, the brief header |
| 2 | `project_name`, `prefix` | the allocator; ids are permanent |
| 3 | `workspaces[].path/primary/agent` | lanes: the guard denies the other agent's writes in a reserved path; `taos start` routes each agent to its own |
| 4 | `git_isolation` (`worktree`/`branch`/`fork`/`trunk`), `branch_pattern` (`{prefix_lower}`, `{id_lower}`, `{slug}`, `{agent}`), `protected_branches`, `worktree_root`, `merge_policy` (`human_pr`/`agent_after_gates`/`trunk`) | what `taos start` prints and claims; what the guard asks and denies around commit, push, and merge |
| 5 | `gates[]`, `stack` | `taos gate run`; `finish --state review\|done` refuses without a pass in 24 h. Stack is auto-detected from the primary workspace (Cargo.toml, package.json, pyproject, go.mod) when unstated |
| 6 | `autonomy` (`propose_only`/`edit_branches`/`push_branches_open_prs`), `human_only[]` | the guard's push and commit verdicts; the list shown in AGENTS.md and the panel |
| 7 | `secret_patterns[]` | merged with the built-in deny list in the guard |
| 8 | `first_tasks[]` | `{title, next_action, done_when?, verification?, priority}`; created as `next`, none hot. If `done_when` is absent, propose one in the sharpen step after reading the repo |
| 9 | `resources.{agents_available, compute, context_available, context_working, context_reserve, protect[]}`; mechanics `agents[]`, `install_hooks_in_workspaces`, `panel.port`, `brief_time`, `attention.max_decisions_per_day`, `attention.quiet_hours` | the controller's compute prior; limits the agents respect; the panel and brief mechanics |
| 10 | `preference.{exploration, priorities[]}`, `agent_corrections[]`, `self_iteration.cadence` | the controller's exploration prior (initial `beta`); each correction becomes a `kind: atom` proposal, unpromoted; cadence shapes how often proposals surface |

Parsing #8: `title :: next action :: done when`, any trailing `P0`..`P3`
token is the priority; two parts means no closure was given. Parsing #9 and
#10: map their words onto the enums (`constrained|normal|abundant`,
`conservative|balanced|exploratory`); free text for context sizes is kept as
given. These are priors and limits, never performance truths; measured
outcomes refine the numbers without asking again.

Shape: `bootstrap/answers.schema.json`. Worked example:
`bootstrap/answers.example.json`. Omit any key the human said "default" for.

Parsing #4 and #6: map their words onto the enum values in the table above;
if they say something you cannot map, ask that one thing back, and nothing
else.
