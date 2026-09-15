# Duplicate work

The most expensive mistake an agent makes is not a wrong answer. It is the
right answer, produced a second time, at full cost, because nobody checked
whether it already existed.

## The rule

Before any work that produces an artifact (a build, a benchmark, a migration,
a generated file, a report, a long computation, a retrained model), search
for the artifact first:

```bash
taos task find "<two words from the request>"
taos task show <ID>            # read the evidence list
```

If equivalent work exists, stop and report three things:

1. where it is (the task id, the evidence path, the commit);
2. what, if anything, differs between what exists and what was asked;
3. the options: reuse it, compare against it, or deliberately redo it with
   a stated reason.

Then wait for the human, or, if the request already named a reason to redo,
record that reason on the task and proceed.

## What counts as equivalent

Same inputs, same command, same intent. A different flag is a different run
only if the flag changes the output. When unsure, ask; the ask costs seconds
and the rerun costs the afternoon.

## Why it is a hard rule and not advice

In the system this OS came from, one silent rerun cost a day of shared
compute and produced a second artifact that later had to be reconciled with
the first. The check that prevents it is one search. Do the search.
