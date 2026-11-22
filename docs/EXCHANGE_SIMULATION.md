# What happens when assistants pass results to each other?

This simulation asks how a recipient checks whether a copied result still
holds. Each copy records the versions of its declared input files. The
recipient can compare them with the current versions before using the result.
The assistants, edits, and requests were all simulated.

## The short answer

The 40 simulated worlds made 57,364 requests. Of those, 12,378 required a
first computation and 44,986 started with a copy an assistant held or received.
The percentages below use all 57,364 requests.

- Repeating the copy produced 12,345 outdated results, or 21.52%.
- Computing from scratch on every request produced zero outdated results. It
  ran 57,364 computations, including 44,986 refreshes of copies. Of those
  refreshes, 39,090 found the result unchanged.
- Comparing fingerprints with every input declared also produced zero outdated
  results by construction. It made 44,986 comparisons and 20,419 computations,
  including 8,041 refreshes. Those refreshes found 5,896 changes, the same count
  as computing from scratch on every request.
- With a 90% chance of declaring each input, 2.61% of requests returned
  outdated results. That rose to 5.54% at a 75% declaration chance, 10.47% at
  50%, 15.49% at 25%, and 21.52% with no inputs declared. Edits to omitted
  inputs alone cannot trigger a refresh through a fingerprint comparison.
- The 160-step timer produced 7,881 outdated results with 18,580 computations.
  Fingerprint comparisons at a 75% declaration chance produced 3,177 with
  18,565 computations. Both round to 32.4 computations per 100 requests.
  The fingerprint rule also made 44,986 comparisons.

## The table

| Rule for checking a copy | Outdated results (% of all requests) | Computations per 100 requests | Refreshes that found no change |
| --- | --- | --- | --- |
| Repeat the copy | 12,345 (21.52%) | 21.6 | 0 |
| Rerun when the copy is older than 5 steps | 53 (0.09%) | 90.4 | 33,588 |
| Rerun when older than 10 steps | 192 (0.33%) | 83.6 | 29,741 |
| Rerun when older than 20 steps | 552 (0.96%) | 73.4 | 23,989 |
| Rerun when older than 40 steps | 1,601 (2.79%) | 60.3 | 16,808 |
| Rerun when older than 80 steps | 3,716 (6.48%) | 45.8 | 9,338 |
| Rerun when older than 160 steps | 7,881 (13.74%) | 32.4 | 3,373 |
| Compare fingerprints, 100% chance per input | 0 (0.00%) | 35.6 | 2,145 |
| Compare fingerprints, 90% chance per input | 1,500 (2.61%) | 34.1 | 1,883 |
| Compare fingerprints, 75% chance per input | 3,177 (5.54%) | 32.4 | 1,559 |
| Compare fingerprints, 50% chance per input | 6,005 (10.47%) | 29.2 | 1,062 |
| Compare fingerprints, 25% chance per input | 8,888 (15.49%) | 25.6 | 570 |
| Compare fingerprints, 0% chance per input | 12,345 (21.52%) | 21.6 | 0 |
| Compute from scratch every time | 0 (0.00%) | 100.0 | 39,090 |

Every rule made the same 12,378 first computations, or 21.6 per 100 requests.

Repeating the copy left between 10.69% and 32.08% of requests outdated across the
40 worlds. At a 90% declaration chance, the range was 0% to 12.34%.

## When do the comparisons pay for themselves?

At full declaration, checking fingerprints avoided 36,945 computations and
added 44,986 comparisons relative to computing from scratch every time. Let
`C` be a constant cost per computation and `F` a constant cost per comparison.
The break-even point in this simple cost model is
`F / C = (57,364 - 20,419) / 44,986 = 82.13%` (rounded). Checking first costs
less below that ratio. This arithmetic uses the saved counts and assumes these
are the only two costs. The simulation did not time either operation.

## Passing copies along

Two variations change the chance of taking a first copy from another
assistant. Their counts use 10 worlds each and separate request totals.

| First-copy policy | Requests | Repeat the copy | Compare fingerprints, all inputs declared |
| --- | --- | --- | --- |
| No copy is taken from another assistant | 14,196 | 14.40% outdated, 39.7 computations per 100 requests | 0% outdated, 50.1 computations per 100 requests |
| A first copy is always taken from another assistant when one exists | 14,485 | 31.90% outdated, 4.1 computations per 100 requests | 0% outdated, 21.5 computations per 100 requests |

Accepting first copies more often lowered computation counts in both policies.
Without checking copies, it also increased the share of outdated results.

## Other variations

Each row changes one setting and simulates 10 worlds. The cells give the share
of all requests that returned outdated results. Policies within each variation
share the same edits and requests. A different setting can change the order of
random draws, so comparisons between variations can use different requests.

| One setting changed | Requests | Repeat the copy | Timer, 160 steps | Fingerprints, 90% declaration chance | Fingerprints, 50% declaration chance |
| --- | --- | --- | --- | --- | --- |
| Files change half as often | 14,424 | 11.18% | 7.18% | 1.00% | 5.28% |
| Files change twice as often | 14,506 | 35.43% | 24.11% | 2.93% | 14.95% |
| Every edit changes the result | 14,239 | 29.41% | 19.41% | 2.18% | 11.95% |
| Four edits in ten change the result | 14,239 | 16.02% | 9.40% | 0.63% | 5.34% |
| Requests are spread approximately evenly across results | 14,315 | 19.97% | 12.77% | 1.66% | 8.89% |

With every input declared, comparing fingerprints produced zero outdated results
in any variation.

## Predictions written before the first run

The simulation author reported setting these five predictions before the first
run. The saved record preserves all five outcomes.

1. Held. With every input declared, comparing fingerprints never repeats an
   outdated result. Every change to a result also increments a version the rule
   checks, so a failure would have flagged a model error.
2. Held. With every input declared, it computes less than half as often as
   computing every time (35.6 against 100 per 100 requests).
3. Held. At a 50% declaration chance per input, it repeats fewer than half as many
   outdated results as repeating the copy (6,005 against 12,345).
4. Held. At a 75% declaration chance, none of the six tested timers did as well
   on both counts and better on at least one.
5. Failed. The prediction was that at a 25% declaration chance, at least one
   tested timer would do as well on both counts and better on at least one.
   No tested timer did.

The six timer thresholds were 5, 10, 20, 40, 80, and 160 steps.

## What this does not cover

- Editing and request rates are settings of the model. The results describe
  these synthetic worlds.
- The model assumes a fresh computation is always correct and each copy
  truthfully reports the versions of its declared inputs.
- The model represents fingerprints with counters that advance when files change.
  It uses no real file hashing and does not model restoring earlier file bytes.
- Each input independently has the stated chance of being declared. Individual
  results can have more or fewer declared inputs than that percentage.
- The overall 21.52% for repeating copies belongs to runs of 240 steps. That
  policy never refreshes its copies.

## How the model works

A world has 80 files, 60 results and 12 assistants, and runs for 240 steps.
Each result uses one to six files. At every step each file changes with a
chance of 15 in 10,000, and a change alters each result that uses the file 7
times in 10. Each assistant has a 50% chance of requesting a result at each
step. A few results are requested far more often than the rest. The first time
an assistant needs a result that another already holds, it takes a copy half
the time and otherwise computes it. Copies carry the versions of their
declared inputs and the time of their last computation.

Every rule in a world uses the same edits and requests. Each random draw is a
whole number from the SplitMix64 generator, whose first outputs are checked
against its published test values, so the table can be reproduced in another
language.

## Repeat it

```
python3 evals/exchange_simulation.py            # print the table
python3 evals/exchange_simulation.py --verify   # recompute and compare with the stored result
python3 -m unittest evals.test_exchange_simulation
```

The runner uses only the Python 3.9 standard library. The stored result is
`evals/results/exchange_simulation.json`. Its `uses` field counts all requests,
and `reruns` counts all computations, including initial ones. The
`fingerprint_checks` field counts comparisons, and `needless_reruns` counts
refreshes that found no change. In the saved record, a label such as
`75% of inputs declared` means a 75% declaration chance per input.
