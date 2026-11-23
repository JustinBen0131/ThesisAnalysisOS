# Can an unchanged pooled score hide an instrument-specific failure?

The fixture represents two fictional instruments with eight quality-control readings each. It supplies hand-set scores and reference labels for four faults and four nonfaults per instrument. The program flags readings whose supplied score is at least 60. A check passes when it flags at least three quarters of the known faults. The study checks each instrument on its own and also checks their readings pooled together.

## What happened

Correcting two scores left the entire pooled confusion table unchanged. The cutoff rule still flagged six of eight faults overall. Instrument A dropped from three of four to two of four, while instrument B rose from three of four to four of four. The pooled check passed and instrument A failed.

| Edit in a fresh workspace | Faults detected by A | By B | Pooled | Checks executed after edit | Checks below 75% |
|---|---:|---:|---:|---|---|
| Caption only | 3/4 | 3/4 | 6/8 | None | None |
| Correct A03 from 70 to 50 | 2/4 | 3/4 | 5/8 | A, pooled | A, pooled |
| Also correct B04 from 50 to 70 | 2/4 | 4/4 | 6/8 | A, B, pooled | A |
| Raise the shared flag cutoff from 60 to 75 | 2/4 | 2/4 | 4/8 | A, B, pooled | A, B, pooled |

Eight checks executed after the four edits in total. Each case starts from the same small fixture. The three baseline runs in each case are excluded from those counts.

## How the checks worked

Each instrument check declared its own CSV, the shared cutoff file and the calculation code as inputs. The pooled check declared both CSVs and both shared inputs. The caption had its own input group and was used by none of the checks. Thus an A-only correction changed two sets of recorded inputs. Correcting scores on both instruments changed all three sets, including the one for the pooled calculation whose numerical answer happened to stay the same.

Each case began in a temporary TAOS home with three observed passing checks. The runner applied the specified edit, asked `gates.standing` about each earlier pass, then called ordinary `gates.run` without forcing execution. A log outside the workspace counted each check process that actually started. For a reused result the runner took the original observed counts from its earlier stdout. TAOS keeps the reused exit status and input digests, and omits stdout from its shared cache. A final standing inquiry records the status after consultation.

## How to check the conclusion

The design records the expected confusion table, sensitivity direction, old passes expected to become stale, checks expected to execute and failed checks for each edit. Its SHA-256, `3c558dae1dabe8e9a451b4867da305a040a324e6b00e6956cbfe6df2ebdf025c`, identifies the exact design used by the saved record. The design and observations first appear together in public commit `910ae72`. [Design](../examples/model_evaluation/predictions.json) · [First public commit](https://github.com/JustinBen0131/ThesisAnalysisOS/commit/910ae726e749c69173e88cfd1dc84f5c024a097c)

The input files give every original reference label and score. [Instrument A](../examples/model_evaluation/a.csv) · [Instrument B](../examples/model_evaluation/b.csv)

The gate increments a count as it applies the cutoff to each row. A separate calculation intersects the set of IDs with known faults and the set of IDs above or at the cutoff. Both calculations have to agree with the hand-specified count table. Read counts in the order true positives, false negatives, false positives, true negatives. The baseline and the offsetting-corrections case both give the pooled table **(6, 2, 2, 6)**. In the latter case A gives (2, 2, 1, 3) and B gives (4, 0, 1, 3).

Run `python3 evals/model_evaluation.py --verify` from the repository root to repeat all four cases in temporary directories and compare the full result with the [saved observations](../evals/results/model_evaluation.json). The [record schema](../evals/model_evaluation.schema.json) describes the fields. The record includes the edited samples, source and input hashes, before-and-after check status, fresh executions and reused passes. The recorded source manifest includes the runner, fixtures, TAOS modules loaded by the scratch-home constructor and its setup inputs.

The standalone verifier independently computes the counts from the original IDs, scores and labels. Run `python3 evals/review_model_evaluation.py --self-test` to check the counts and confirm that it rejects an altered count, swapped instrument states and a changed observation. [Verifier](../evals/review_model_evaluation.py)

The scores and reference labels were chosen to test aggregate cancellation and input tracking. They describe 16 invented instrument readings. This experiment provides an exact counterexample to relying on a pooled result alone. It does not estimate how often this disagreement occurs in a population, quantify deployed model performance or establish independence between subgroups. Population p-values would not answer the question tested here.
