@AGENTS.md

# Claude Code notes

`AGENTS.md` above is the contract. Everything in it applies to you exactly as
it applies to Codex. This file only covers what is specific to this runtime.

- Hooks are installed in `.claude/settings.json`. A PreToolUse guard denies
  secrets, force pushes, direct edits to the state files, and edits to the
  cage itself; it asks before `git push` and recursive deletes. A SessionStart
  hook has already injected `taos status --compact` into this session, so you
  begin knowing what is hot.
- If your runtime does not support the `@AGENTS.md` import on the first line,
  read `AGENTS.md` yourself before doing anything.
- Skills live in `.claude/skills/`. `taos-start` and `taos-handoff` cover the
  two flows you will use most.
- Run `./taos` from the OS clone root, or from a linked workspace where
  `.taos-link.json` points back here.
