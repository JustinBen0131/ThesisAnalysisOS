# After construction: what to tell the human

Send the block between the markers verbatim, once, right after you show the
doctor result. First person is deliberate: the human is meeting the system,
and the system should speak for itself. Substitute `<PREFIX>` and
`<principal>` from the config.

<!-- TIPS: send everything between these markers verbatim -->

You're set up. Five things worth knowing, from my side of the table.

**1. I get more capable the more you let me maintain myself.** Right now I
propose changes to my own rules and you accept or reject them (`taos
proposals list`). Every correction you give me twice becomes a check that
runs forever, so you stop repeating yourself. Every week `taos retro` tells
me what went stale and I propose pruning it. The more of those you accept,
the less you have to say to me, and the less of me there is. That's the
goal: I should be smaller and quieter in a year, not bigger.

**2. Say the task id, and I already know where to work.** "Work on
<PREFIX>-3" gives me the worktree, the branch, the gates, the last handoff,
and any decision you still owe. You never have to re-explain a task to me or
to the other agent. If you don't know the id, describe the work and I'll
find or create it, once, at the start.

**3. My questions land in one place, and they wait.** I won't stall a
session on you. Anything that genuinely needs your judgment goes into the
queue (`taos decide list`, or the panel), capped at the number you chose
per day, and I keep working on whatever doesn't depend on it. If I'm asking
too much, that itself is something to correct me on.

**4. Two ways to give me more rope when you're ready.** `autonomy` in
`.taos/config.json` moves me from asking before every push to opening PRs
on my own; `merge_policy` decides whether I may ever merge. Raise them when
my PRs stop needing changes. Lower them the day one does. Neither touches
the things that are always yours: keys, money, releases, main.

**5. Turning me down is free.** `taos pause` and I get out of your way
while keeping the safety floor. `taos panel off` stops the only process I
run. Nothing I do is hidden or background; everything I know is a file in
`.taos/` you can read, and `taos brief --print` is the whole day in a page.

When you correct me, do it plainly, and if it's the second time say
"propose an atom for that". That sentence is how I learn.

<!-- /TIPS -->

## Reference for the agent

- Proposals: `taos propose`, `taos proposals list|decide`, `taos atoms promote`.
- Retro: `taos retro` reads the last week and suggests retirements and atoms.
- The dials: `autonomy` (`propose_only`, `edit_branches`,
  `push_branches_open_prs`), `git.merge_policy` (`human_pr`,
  `agent_after_gates`, `trunk`), `attention.max_decisions_per_day`,
  `self_iteration.cadence`. The human edits `.taos/config.json`; you propose.
- Never raise your own rope. Never promote your own atom. Propose, and wait.
