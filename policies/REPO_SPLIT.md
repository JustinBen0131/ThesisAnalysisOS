# The repo split

Two failure domains, never one. This is the boundary that keeps private
operating state out of collaborator-facing history, and it is the first thing
to get right because it is the most annoying to fix later.

## The two sides

**Your OS repo** (this clone, re-homed as your own private repository).
Holds: the runtime, `AGENTS.md` and `CLAUDE.md` as rendered for you, your
policies, your kernels, your atoms, your hooks. `.taos/` is git-ignored, so
your tasks, claims, events, handoffs, and gate runs stay on your disk and in
no history at all unless you choose to commit them.

Make it private. Mutate it freely: the policies, the questions, the templates,
the guard rules are all yours to change. That is the point.

**Your work repos** (the codebase your colleagues also push to).
They receive exactly three things, and nothing else:

1. a short block in `AGENTS.md` and `CLAUDE.md`, between
   `<!-- taos:begin -->` and `<!-- taos:end -->`, pointing at your OS home;
2. `.taos-link.json`, one line naming that path;
3. optionally `.codex/hooks.json` and `.claude/settings.json`, only if those
   files did not already exist.

Nothing else from the OS ever lands there. No tasks, no claims, no events, no
handoffs, no kernels, no private paths.

## Rules

- Never commit `.taos/` anywhere. It is git-ignored in the OS repo; if you
  ever see it staged in a work repo, something is wrong.
- Never commit the OS runtime into a work repo. Link, do not vendor.
- The three linked files are yours, not your team's. If your team does not
  want them in the shared history, add them to that repo's
  `.git/info/exclude` (local, uncommitted) instead of `.gitignore`:

  ```bash
  printf '.taos-link.json\n.codex/hooks.json\n' >> <work-repo>/.git/info/exclude
  ```

  The block in `AGENTS.md` is usually fine to share: it is four lines and it
  tells any agent, yours or a colleague's, where the work is tracked. Drop it
  with `taos bootstrap unlink-workspace <path>` if you would rather not.
- Commit messages, branch names, and PR bodies in a work repo carry no task
  ids from a private tracker unless you want colleagues to see them, and no
  model or agent names. That provenance belongs in your OS repo.
- If you ever open-source a work repo, run
  `taos bootstrap unlink-workspace <path>` first and check `git log -p` for
  the block.

## Why it is set up this way

An operating layer that lives inside the codebase it manages cannot be
changed without touching that codebase's history, cannot be shared across
repos, and leaks your working state into every review. Keeping them separate
means you can rewrite your own rules daily and your colleagues never see a
diff.
