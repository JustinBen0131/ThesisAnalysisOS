# Does the old receipt still support the measurement?

This experiment asks when an existing pass can be retained after an edit to a pendulum analysis. It measures three different outcomes for each edit: the standing of the original fit receipt, the numerical change in the fitted estimate or its standard error, and the exit status of a fresh execution. The scientific question is whether the six observations still support the same estimate. The software question is what the recorded evidence can establish before anyone repeats the fit.

## Reproduce or inspect

From the project root, run `python3 evals/measurement_audit.py --verify` to reconstruct every case and compare its readings with the checked-in observations. Run `python3 evals/measurement_audit.py --case scale-1.02` for one case as JSON. The runner requires only Python's standard library. It executes the ordinary fit gate in temporary local workspaces.

To audit another series, run `python3 evals/measurement_audit.py --input path/to/swings.csv`. The two columns must be `length_m,period_s`, with finite positive decimal values and at least five observations. The initial series must pass the example's fit check. The source file is read only. Results go to standard output. This is a tool for the example's pendulum model and gate criteria.

## Fixed design

Each case begins with the same input in a fresh workspace and one observed, passing PEN-1 gate receipt. In the declared cohort the gate reads analysis scripts and data, and its basis covers both. The perturbations are fixed in the runner before execution.

- Controls leave the workspace alone, change only the figure style, change the decimal spelling of a datum, reverse the row order, or append a comment to the fit.
- Three calibration perturbations multiply every period by 0.98, 1.001, or 1.02.
- Each individual period is scaled by 0.95, 0.99, 1.01, and 1.05 in turn, holding the other observations fixed.
- In a separate sensitivity control the same gate runs in open mode. Its declared analysis domain deliberately omits the CSV. Multiply all periods by 0.98 or 1.02 and look for a retained pass that a fresh execution contradicts.

Read the old receipt's standing immediately after the edit, **before** forcing a fresh execution. Then run the shipped estimator at full precision and force the ordinary gate to execute the shipped check. Its stdout and exit code are recorded. An independently coded decimal calculation expresses the through-origin slope as the weighted mean of the individual T²/L ratios, with weights L². Compute the slope uncertainty from the residual sum of squares divided by (n−1)ΣL², then propagate it to g. The check requires at least five swings, 9.6 < g < 10.0 m/s² and a standard error of at most 0.2 m/s². Both the estimate and its standard error are compared to the shipped estimator with absolute tolerance 1e−10 in m/s². For uniformly scaled periods the independent analytic prediction is that both g and its error divide by the scale squared.

## Additional control after first readback

In the initial run, removing the CSV from every domain produced an unknown verdict on both edits. We kept those observations as the unclassified-input cohort and specified a second pair before executing it. The CSV now belongs to a named measurements domain, while the gate still declares only analysis. These cases separate a detectable unmapped file from a mapped input whose use the gate omitted. Both use open execution.

## Interpreting the observations

A stale receipt can accompany an unchanged numerical result, as with a comment. A changed estimate can still pass the check. A retained pass followed by a failed fresh check is an obsolete decision. Each raw row includes the exact inputs, standing, fresh check output, fitted quantities, independent comparison and hashes. The omitted-input controls test whether this experiment can expose an obsolete decision. They are counted separately from the ordinarily configured system.

The edits reuse one small teaching dataset. Their frequencies describe this fixed grid. They do not estimate a population failure probability or establish the accuracy of a physical measurement of gravity. This audit provides a second implementation and reproducible records. External replication by another research group is a separate undertaking.
