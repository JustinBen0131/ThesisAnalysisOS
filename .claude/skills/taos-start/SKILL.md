---
name: taos-start
description: Map the human's request to one TAOS task and start it properly (claim, lane, capsule). Use at the beginning of any session that will do real work in a TAOS-managed repo.
---

# taos-start

Use the full shell command prefix printed in the TAOS block of the workspace
instructions or in the OS home's `AGENTS.md`. It includes the launcher and
`--home`. Keep it exactly as printed when running each subcommand below,
including from a task worktree.

1. Run `status --compact` and read it.
2. Find the task with `task find "<two or three words from the request>"`.
   - Found: use its id.
   - Not found and the work is finite: `task create --agent <you>
     --title "<imperative title>" --next-action "<literal first step>"`.
   - It is a question, not work: answer it and stop here.
3. Run `start --agent <you> --task <ID> --session "<ID> | <short label>"`
   with your agent name (`codex` or `claude`), the actual task ID, and a
   short label.
   - Exit code 4 means the other agent holds it. Do not work around it. Tell
     the human who holds it and offer to work on something disjoint.
4. Read the capsule. Run the "work here" commands exactly (worktree, branch).
   Never commit on a protected branch.
5. Begin. Record evidence on the task as you go.
