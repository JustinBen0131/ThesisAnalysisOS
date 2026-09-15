---
name: taos-handoff
description: Finish a TAOS task correctly (gates, evidence, handoff to the other agent) so the next session can continue without you. Use whenever you stop working on a task that is not done, or when the human asks you to hand work to Codex or Claude.
---

# taos-handoff

1. Run the gates: `./taos gate run --agent <you> --task <ID>`. Fix failures or
   name the failing gate as the blocker.
2. Write the handoff:
   `./taos handoff template <ID> --from <you> --to <them> --session "<label>" > /tmp/h.md`
   Fill every section with facts: State, Changed, Evidence, Risks and open
   questions, Next command (a literal command). Remove every placeholder.
3. Finish:
   `./taos finish --agent <you> --task <ID> --state review --reason "<what happened>"
   --evidence "<path or commit>" --session "<label>" --handoff-file /tmp/h.md --to <them>`
   If the tool refuses the handoff, fix the file; do not skip.
4. Paste the wrapper it prints to the human. End your message with the
   episode marker (`<!-- ep: id=... phase=handoff ... -->`).
