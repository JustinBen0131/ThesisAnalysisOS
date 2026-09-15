# Git

The specifics (isolation mode, branch pattern, protected branches, merge
policy) are in `.taos/config.json` under `git`, chosen by the human at setup
and enforced by the guard. This is the discipline around them.

## Where you work

`taos start` prints the lane: the workspace, the worktree if the mode is
worktree, the branch name, and the exact commands. Run those commands. Work
there. Nowhere else.

- **worktree**: `git worktree add <path> -b <branch>` from the workspace. The
  worktree path is your claim; the other agent cannot write there.
- **branch**: `git switch -c <branch>` in the workspace.
- **fork**: you already have your own checkout (your lane). Branch inside it.
- **trunk**: small commits on the main branch, each independently revertible.

## Protected branches

Never commit on one. The guard asks if it catches you there. Never push to
one; the guard refuses. If you find yourself on `main` with changes, stash,
switch to the task branch, pop.

## Commits

Small, one concern each, message says what and why. In a collaborator-facing
repo, no task ids from this OS, no model names, no agent names. Provenance
lives in the OS, not in the shared history.

## Pushing and merging

What is allowed depends on the autonomy level the human chose:

- `propose_only`: no pushes; commits ask.
- `edit_branches`: every push asks.
- `push_branches_open_prs`: push task branches freely; open PRs; stop there.

Merge policy `human_pr` means you open the PR, put the link on the task as
evidence, and stop. Only the human merges.

## Never

Force push, rewrite published history, force-delete branches or worktrees,
`reset --hard` against a shared branch. Listed in `HARD_STOPS.md`; repeated
here because git is where it happens.

## After a merge

Worktree cleanup (`git worktree remove`) is the human's. Tell them the
worktree is done; do not remove it yourself.
