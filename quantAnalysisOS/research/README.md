# Research notes

Findings written for a person. Every number in a note comes from a record in
`book/` and names it. The notes are numbered in the order the work was done.

| Note | What it settles |
|---|---|
| [001 Toys](001-toys.md) | What the method does on markets where the truth is known: how much data an edge needs, what a search finds in noise, whether the quoted errors are honest, which test matches which claim. |
| [002 US market timing](002-us-market-timing.md) | QA-1, the first study on real data: do slow rules that move between US stocks and Treasury bills add return beyond their market exposure? |
| [003 Where a trickle can come from](003-agenda.md) | What the first two notes imply for the plan, what is on paper now, and what gets studied next. |

`specs/` holds each study's registration as it was written, before it was
sealed. `figures/` is drawn from the book by `./qaos figures`.

To check a note against the record:

```bash
./qaos toys all --show        # the recorded toy studies, and whether they still hold
./qaos study show QA-1        # registration, trials, freeze, verdict, systematics
./qaos study why QA-1         # holds, stale, fails or unknown
./qaos doctor                 # every ledger and seal
```
