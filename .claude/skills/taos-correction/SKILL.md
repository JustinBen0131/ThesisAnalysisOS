---
name: taos-correction
description: Turn a repeated human correction into a checkable TAOS atom proposal. Use when the human corrects you on something they have corrected before, or says "propose an atom for this".
---

# taos-correction

1. State the rule in one sentence, in the imperative.
2. Decide how a machine could check it: a regex that must (or must not) match
   a file or the latest handoff, a file that must exist, or a `taos` command
   that must exit zero. If none fits, write one dated line under "Corrections
   observed" in `kernels/PRINCIPAL_KERNEL.md` instead and stop.
3. Write the atom JSON (see `atoms/promoted_atoms.json` for the shape) with
   red and green fixtures so it tests itself.
4. `./taos propose --agent <you> --kind atom --title "<rule>" --body "<why, with the
   two occurrences as evidence>" --evidence "<path>" --atom-json /tmp/atom.json`
5. Tell the human it is queued. Do not promote it yourself.
