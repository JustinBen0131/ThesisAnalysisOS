# Review

When the human says "check your work", "double check", "look again", or
"did you miss anything", they want one bounded pass, not a redesign.

## The pass

1. Restate the acceptance criteria of the thing under review, in one line.
   If they were never stated, state what you are checking against.
2. Check the deliverable against them, and against the gates.
3. Fix only what changes a decision: a wrong result, an unsafe action, a
   materially inefficient path. P0 and P1.
4. Everything smaller becomes a task:
   `taos task create --agent <you> --title "..." --status backlog`.
5. Stop when the list is closed. Report what you checked, what you fixed,
   and what you filed.

## What a review is not

- Not a second opinion on a stable interface.
- Not a generic scan for things you might do differently.
- Not a reason to reopen frozen work. Reopen only for a reproducible
  failure, a changed requirement, new external evidence, or an explicit ask
  naming the new scope.

## Evidence in the report

"I checked X and it holds" needs the same evidence as any other claim: the
command you ran, the output, the path. A review without evidence is a
feeling.
