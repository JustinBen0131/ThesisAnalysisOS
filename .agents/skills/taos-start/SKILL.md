---
name: taos-start
description: Map the human's request to one TAOS task and start it properly (claim, lane, capsule). Use at the beginning of any session that will do real work in a TAOS-managed repo.
---

# taos-start

1. Run `./taos status --compact` (or `<TAOS_HOME>/taos status --compact` from a
   linked workspace) and read it.
2. Find the task: `./taos task find "<two or three words from the request>"`.
   - Found: use its id.
   - Not found and the work is finite: `./taos task create --agent <you>
     --title "<imperative title>" --next-action "<literal first step>"`.
   - It is a question, not work: answer it and stop here.
3. `./taos start --agent <you> --task <ID> --session "<ID> | <short label>"`.
   - Exit code 4 means the other agent holds it. Do not work around it. Tell
     the human who holds it and offer to work on something disjoint.
4. Read the capsule. Run the "work here" commands exactly (worktree, branch).
   Never commit on a protected branch.
5. Begin. Record evidence on the task as you go.
