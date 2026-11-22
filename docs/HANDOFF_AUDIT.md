# Which pendulum result can the next task inherit?

Start with one passing fit for six pendulum swings. Three tasks ask the same
check in one shared history as a plot style changes, a revised reading makes
the fit fail, and the original data returns. The check declares the analysis
code and CSV as inputs. Plot styling belongs to a separate domain.

| Request | What changed | Task | Standing before | Gate request | Exit | Standing after |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Original readings | PEN-1 | Unknown | Executed | 0 | Holds |
| 2 | Plot style only | PEN-2 | Holds | Reused request 1 | 0 | Holds |
| 3 | Last period from 2.19 to 2.2995 s | PEN-2 | Stale | Executed | 1 | Fails |
| 4 | Third task starts on the same failed readings | PEN-3 | Fails | Executed | 1 | Fails |
| 5 | Exact original CSV restored, newer style kept | PEN-2 | Holds | Reused request 1 | 0 | Holds |
| 6 | Same reading written as 2.190 s | PEN-2 | Stale | Executed | 0 | Holds |
| 7 | Same revised spelling | PEN-3 | Holds | Reused request 6 | 0 | Holds |

The seven gate requests produced four executions and three reuses. All seven
matched the intended standing, action, exit and originating receipt. The
fresh gate reported 9.44 m/s² on the failing readings, outside its 9.6 to
10.0 m/s² limit. A newly started task could see the failure on those same inputs,
and its own gate request executed again. Exact restoration recovered the first
task’s passing receipt. Preserving the numerical values with different bytes
triggered a fresh pass that another task could then reuse.

## Reproduce

From the repository root, run:

```sh
python3 evals/handoff_audit.py --verify
```

The standard-library runner constructs one temporary TAOS home and one
temporary copy of the shipped pendulum example. It starts tasks through
`lifecycle.start`, reads `gates.standing` immediately before and after each
request, and calls `gates.run(force=False)` to allow ordinary reuse. The
runner supplies the actor labels `codex` and `claude`. Live model calls and
network requests total zero.

The [raw record](../evals/results/handoff_audit.json) includes each task’s
view, exit and gate output, the original execution receipt for every request,
all CSV variants and their hashes, and any expectation mismatches. Receipt
aliases map to chronological request IDs so replay can be compared without
wall-clock times or temporary paths. The built-in demo already covers a
passing handoff and an independent style edit. The added controls here test
failure and recovery in the same history, including the distinction between
returning to exact input bytes and returning only to equal numerical values.

This is one scripted case under an unchanged gate definition with the earlier
receipts still present. Its counts describe this history. They provide no basis
for estimating frequency, speedup or the behavior of independently acting
agents.

## Was the cited run the right one?

The [independent verifier](../evals/review_handoff_audit.py) reconstructs all seven requests from the original readings, checks each file digest and recomputes the fit. The last task reused a pass on the CSV containing `2.190`. An older pass on `2.19` printed the same gravity estimate and had the same exit status. Substituting that older citation left every headline count intact. The verifier rejected it because the input bytes belonged to a different run.

Run `python3 evals/review_handoff_audit.py --self-test` from the repository root to repeat this check. Two additional controls change a reading and change a printed result while preserving the failing exit status.
