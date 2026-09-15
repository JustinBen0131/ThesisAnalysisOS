# Decomposition

A task is the right size when one session can move it to `review` with
evidence, and the human can tell from the title alone whether it matters.

## Umbrellas are context, not work

A broad task ("make the compiler faster", "the parser rewrite") is an
umbrella. It holds the goal, the children, and the campaign-level decisions.
It is never the thing you `start`.

When the request is a finite deliverable inside an umbrella, create the child
and start that:

```bash
taos task create --agent <you> --title "<the finite thing>" --parent <UMBRELLA-ID> \
  --next-action "<literal first step>"
taos start --agent <you> --task <CHILD-ID> --session "<CHILD-ID> | <label>"
```

Split when all of these are true:

- finishing this deliverable would not finish the parent;
- it has its own artifact, its own evidence, its own done condition;
- the other agent could own it without owning the whole campaign.

Do not split when the child would be one command. Record that as evidence on
the existing task instead.

## Blockers are edges, not adjectives

If B cannot start until A is done, say so in the store:

```bash
taos task relate <B> --agent <you> blockedBy <A>
```

`taos start <B>` will refuse while A is open, and the capsule will name it.
"Blocked" without a named blocker is a status the tool rejects.

## Once per session

Map the request at the start. Do not re-shape the task tree mid-session
unless the scope genuinely changes or the task proves too broad to finish
truthfully. Constant re-bifurcation is its own kind of noise.
