# The ten questions

Ask all ten in one message, numbered, each with its default shown. Accept
"defaults" for everything, or "default" for any single one. Do not ask them
one at a time. Every answer changes how the OS is built: the questions are
ordered from "who" to "how much rope", and the ones that matter most for an
engineer who runs two agents are 3, 4, 5 and 6.

---

**1. Your name, and your timezone.**
Fills `principal_name`, `timezone`.
*Default: your shell username, and the machine's timezone.*

**2. Project name, and the task prefix.**
Fills `project_name`, `prefix`. Ids become `PREFIX-1`, `PREFIX-2`, forever, so
pick something short you will type often. 2 to 8 uppercase characters.
*Default: the primary repo's folder name, and its first letters.*

**3. Where do the agents work, and does any agent get its own lane?**
Fills `workspaces`. Absolute paths. Mark one primary. If you keep separate
forks or checkouts so that each agent has a bounded context (for example
`~/code/noir` for Codex and `~/code/noir-claude` for Claude), say which path
belongs to which agent: the guard will then refuse the other agent's writes
there, and `taos start` sends each agent to its own lane automatically.
Each workspace gets a short block appended to its `AGENTS.md` and `CLAUDE.md`
(between markers, never overwriting yours) plus the hooks if you say yes in Q9.
*Default: none, meaning the agents work inside the OS clone itself.*

**4. How is work isolated in git, and how does it reach main?**
Fills `git_isolation`, `branch_pattern`, `protected_branches`, `worktree_root`,
`merge_policy`.
- Isolation: `worktree` (a `git worktree` per task, the agent is sent to it
  and claims that path), `branch` (a branch per task in the workspace),
  `fork` (each agent already has its own checkout; branch inside it), or
  `trunk` (small commits on main).
- Branch pattern. Placeholders: `{prefix_lower}`, `{id_lower}`, `{slug}`,
  `{agent}`. Example: `mv/{id_lower}-{slug}`.
- Protected branches the guard asks before committing on and refuses to
  push to.
- Merge policy: `human_pr` (agents open PRs, only you merge), `agent_after_gates`
  (an agent may merge once the gates pass, with an ask), or `trunk`.
*Default: worktree, `{prefix_lower}/{id_lower}-{slug}`, main and master,
worktrees beside the workspace in `<name>-worktrees/`, human_pr.*

**5. What must pass before an agent may call work reviewable?**
Fills `gates` and `stack`. Each gate is a name and a command run in the
task's worktree or workspace. `taos gate run` records the result on the task
as evidence, and `taos finish --state review|done` refuses without a passing
run in the last 24 hours. Give real commands, the ones you would run yourself.
*Default by stack: rust-cargo = `cargo test`, `cargo fmt --all -- --check`,
`cargo clippy --all-targets -- -D warnings`; node = `npm test`; python =
`python3 -m pytest -q`; go = `go test ./...`, `go vet ./...`. Stack is detected
from the primary workspace when you do not say.*

**6. How much rope do the agents get?**
Fills `autonomy` and `human_only`.
- `propose_only`: agents edit, but commits need a nod and pushes are refused.
- `edit_branches`: agents commit freely on task branches; every push asks.
- `push_branches_open_prs`: agents push task branches and open PRs without
  asking; protected branches and merges stay yours.
And confirm or edit what only you may ever do:
deploy or release; merge to main; sign or broadcast a transaction; touch keys,
seed phrases, or secrets; spend money; message people on my behalf.
*Default: edit_branches, and exactly that list.*

**7. Anything else that must never be read, beyond the usual secrets?**
Fills `secret_patterns`. The guard already denies `.env`, `.pem`, `.key`,
`id_rsa`, `id_ed25519`, keystores, mnemonics, seed phrases, and credential
files, and the `~/.ssh`, `~/.aws`, `~/.gnupg` directories. Add project-specific
substrings or regexes, for example `wallet`, `fixtures/private`.
*Default: none beyond the built-in list.*

**8. Your first three to seven real tasks.**
Fills `first_tasks`. One per line as `title :: next action`, optionally
`:: P0..P3`. The next action is the literal next step, not a summary. These
are what the agents will pick up first, so make them work you actually have.
*No default. At least one is required.*

**9. Daily rhythm and attention.**
Fills `brief_time`, `panel_port`, `open_browser`, `install_hooks_in_workspaces`,
`agents`, `max_decisions_per_day`, `quiet_hours`.
- Brief time (local)? *08:30*
- Panel port? *4331*
- Open the browser when the panel starts? *yes*
- Install the safety hooks into the workspaces from Q3? *yes. Existing hook
  files are never overwritten; you get a snippet to merge instead.*
- Which agents? *both Codex and Claude*
- How many decisions per day may the agents queue at you before the rest
  wait below the line? *3*
- Quiet hours, e.g. `22:00-07:00`, or none. *none*

**10. How should the OS improve itself, and what do agents keep getting wrong?**
Fills `self_iteration_cadence` and `agent_corrections`.
- Cadence: `daily` (proposals and failing atoms appear in every brief),
  `weekly` (only `taos retro` nags), or `manual` (nothing nags; you run
  `taos proposals list` when you feel like it). Atoms are never promoted
  without your yes.
- Corrections: each thing agents keep getting wrong for you becomes a
  proposal in the queue, not a rule, because a rule nobody can check is a
  wish. When an agent sees it happen in real work it turns the proposal into
  a checkable atom, and once you accept it `taos doctor` enforces it forever.
*Default: weekly, and no corrections yet.*
