# The method

What counts as evidence here, and why. Each rule is backed by a toy study whose
recorded result is in `book/toys/` and can be re-run with `./qaos toys NAME`.
The numbers quoted on this page are those records, summarised in
`research/001-toys.md`.

## 1. Count every look

A backtest is a measurement, and the best of many measurements is biased
upward. So the unit of work is a **study**, registered before it runs:

```bash
./qaos study register research/specs/QA-1.json
```

The registration seals the hypothesis, the data fingerprint, the split, every
configuration that may be tried, the test and the bar. Configurations can be
added later with a reason; they are logged and counted. Nothing is removed.

Real data is never backtested outside a study. Exploration happens on toys,
which cost nothing, or on the development window through `scan`, which is
counted.

## 2. Keep the holdout sealed, and open it once

`scan` cuts the dataset at the split before any strategy sees it. `freeze`
fixes one configuration. `unblind` runs it on the holdout, once, signed. A
second attempt is refused.

The toy study `overfit` is the reason. With nothing in the market to find, the
best of a grid of trend rules still shows a positive Sharpe ratio on the
decade it was chosen on, and nothing on the next one.

## 3. Pay for the search

At `freeze` the search is accounted for in two independent ways.

- **Deflated Sharpe ratio.** The chosen configuration's Sharpe ratio is tested
  against the best an unskilled search of that size would be expected to find,
  not against zero. Closed form; assumes the trials are comparable.
- **Mixed-event global p.** Every configuration's weights are rotated in time
  against the returns, the same rotation for the whole grid, and the best of
  each rotation is kept. The real best is compared with those. No formula, no
  independence assumption, and the strategy's exposure, turnover and costs are
  identical in every rotation.

The toy study `look_elsewhere` measures both on markets that contain nothing.
Judged alone, the best rule passes far more often than its nominal rate, and
more so the larger the grid. The rotation test stays at its nominal rate.

## 4. Choose the test that matches the claim

Three tests can be registered. They answer different questions.

| Test | The question | Use it when |
|---|---|---|
| `sharpe` | Does the strategy earn more than cash? | The asset has no premium of its own, or earning the premium is the claim. |
| `alpha` | Is there return left after regressing on the benchmark? | The claim is skill on top of an asset that already pays. |
| `timing` | Does the real alignment of weights and returns beat rotated ones? | The claim is timing, and no benchmark model is wanted. |

The toy study `power` is the reason this table exists. On a market that pays a
premium and contains no timing signal at all, the `sharpe` test confirms a
trend rule a large share of the time: the rule is long much of the time and
the asset goes up. It is confirming the premium. The `alpha` and `timing`
tests stay near their nominal rate on the same markets. A claim of skill
registered under the `sharpe` test is a claim that cannot fail for the right
reason.

## 5. Quote the error, and know when it is honest

Every Sharpe ratio is printed with a standard error. Three are available: the
closed form (Mertens), Newey-West, and the stationary bootstrap. The toy study
`pulls` injects a known Sharpe ratio and measures whether each quoted error is
the real spread, on normal returns, fat tails, and volatility clusters.

Decisions use the Newey-West t-statistic. Intervals in reports use the
bootstrap. When the three disagree, say so, and believe the widest.

## 6. Say what the data can and cannot show

Significance grows like Sharpe times the square root of years. `freeze` prints
how many sigma the holdout would show if the development estimate were exactly
the truth, and again after subtracting what the search alone would produce. If
that number is below the registered bar, the study is under-powered and a
"not confirmed" is the expected outcome whether or not the idea is true. That
is a statement about the sample, and the note in `research/` says it in those
words.

`./qaos need --sharpe S` is the calculator. The toy study `sensitivity`
checks the law on fat-tailed, clustered returns.

## 7. Systematics

After the statistical error, the choices that could have been made otherwise:

- costs at zero, double and four times the registered figure
- one more period between deciding and trading
- every other configuration of the same strategy in the registered grid
- the first and second half of the window, separately

`./qaos study systematics ID --window holdout` prints each shift and the
quadrature sum of costs, delay and parameter choice. A result whose sign
depends on one of them is reported as depending on it.

## 8. What a verdict means

`confirmed` means the registered test cleared the registered bar on data the
configuration was not chosen on, and the Sharpe ratio stayed positive at the
stressed cost. It does not mean the effect is real, will persist, or is worth
real money. Among studies of true nulls, about one in 44 clears 2 sigma.

`not confirmed` means it did not. It does not mean the idea is false. Read it
next to the holdout's expected sensitivity.

`unknown` means the test could not be computed. It is never rounded to either
of the others.

## 9. What stands, and until when

Every record names the fingerprint of the data it read and of the code that
computed it. `./qaos study why ID` reads them back:

- `holds`: the data and the code are what they were, and every seal and log is intact
- `stale`: the data was revised or the code changed; re-run before relying on it
- `fails`: a sealed record or a log was edited
- `unknown`: the data is not on this machine, so nothing could be compared
