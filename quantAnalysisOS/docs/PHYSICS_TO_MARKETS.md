# From the detector to the market

quantAnalysisOS is what happens when the habits of an experimental physics
analysis are applied, without adjustment, to market research. This page is the
dictionary. Each row names the habit, what it becomes here, and where it lives
in the code.

## The dictionary

| In the experiment | Here | Where |
|---|---|---|
| **Blinding.** The signal region is hidden until the analysis is frozen. | The holdout is cut off before a strategy sees the data. It opens once, after `freeze`, signed. | `study.scan`, `study.unblind` |
| **Analysis note before unblinding.** Selection, systematics and the statistical method are written down and reviewed first. | The registration: hypothesis, data fingerprint, split, grid, test, bar, costs. Sealed. | `study.register` |
| **Look-elsewhere effect.** Scan a mass range and the largest bump is not a discovery; the trials factor must be paid. | Scan a parameter grid and the best Sharpe is not an edge. Paid two ways: the deflated Sharpe ratio (closed form) and the mixed-event global p (empirical). | `stats.deflated_sharpe`, `engine.mixed_event_null` |
| **Toy Monte Carlo.** Pseudo-experiments with known truth give the distribution of the test statistic under the null, and the coverage of the intervals. | Toy markets: GARCH noise with fat tails as the null, a hidden drift of dialable strength as the signal. | `toys.py`, `toy_studies.py` |
| **Closure test.** Run the full chain on simulation; get back what was put in. | Inject a Sharpe ratio, recover it, and check the pull distribution has width 1. | `gates.calibration`, `toy_studies.pulls` |
| **Signal injection.** Add a known signal to data-like background and measure the efficiency of the whole procedure. | Inject a timing signal of known r2; count how often scan, freeze, unblind confirms it. | `toy_studies.power` |
| **Mixed events.** Pair particles from different events to build the combinatorial background with the right acceptance and no physics. | Rotate the weights in time against the returns: the same exposures, turnover and costs, the same market, no alignment. | `engine.run(shifts=...)` |
| **Underlying-event subtraction.** Remove what would be there anyway before measuring the jet. | Regress on the benchmark and test what is left: alpha, with an autocorrelation-robust error. | `stats.alpha_beta` |
| **Standard candles.** Calibrate on something whose value is known: the pi0 mass, the Z peak. | Holding the asset must reproduce the asset. Holding cash must reproduce the risk-free rate. A round trip must cost what the cost model says. | `gates.calibration` |
| **Two independent analyses.** Different code, same answer, or neither is trusted. | The backtest engine (weights and returns) and the paper broker (shares and dollars) are held to agree to rounding. | `tests/test_paper.py` |
| **Golden run list.** Decide which runs are fit to analyse by rules fixed in advance. | Golden periods: prices present, positive, no gaps inside a series; jumps flagged and never removed. | `data.quality` |
| **Conditions database tag.** A result names the calibration it used. | A result names the fingerprint of the data and the code it was computed with, and reads `stale` when either moves. | `study.standing` |
| **Statistical and systematic errors, quoted separately.** | Statistical: bootstrap and Newey-West. Systematic: costs doubled, one more period of delay, parameter neighbours, sub-periods. | `study.systematics` |
| **Integrated luminosity.** Significance grows like the square root of the data. | Z = Sharpe x sqrt(years). There is no accelerator upgrade: the data arrives at one year per year. | `stats.expected_z`, `./qaos need` |
| **Expected sensitivity.** Before unblinding, say what the analysis could see. | The freeze reports how many sigma the holdout would show if the development estimate were exactly true, and after the search haircut. | `study.freeze` |
| **3 sigma is evidence, 5 sigma is observation.** | 2 sigma buys time on paper. Real money is the human's call, and the bar an agent can argue for is 3 sigma after every trial is counted (Harvey, Liu and Zhu reach the same number from the finance side). | `policies/LADDER.md` |
| **Test beam.** Put the detector in a known beam before trusting it on collisions. | Paper trading: real dates, real prices, fake money. A `commissioning` mandate runs a plain baseline first, to test the machinery and nothing else. | `paper.py` |
| **Logbook.** Append-only, signed, dated. | Hash-chained ledgers for trials and for the paper account. | `store.ChainLog` |

## Where the analogy breaks, and what to do about it

**The detector does not read your paper.** A particle's mass does not change
because you measured it. A market inefficiency can disappear because it was
published, or because enough capital found it. Past data is evidence about a
system that is not stationary. This is why the ladder ends in paper trading
and not in a longer backtest: the forward record is the only sample taken
from the system as it is now.

**You cannot rerun the collision.** There is one history. No amount of compute
makes a second 2008. Toys help with the method and do nothing for the sample
size. `./qaos need --sharpe 0.5` prints the consequence: 36 years for 3 sigma.
The only honest accelerators are breadth (many unrelated bets, each small) and
long histories that were not tuned on.

**The backgrounds are not known from first principles.** There is no Standard
Model of returns. The null here is built from the data itself (rotation,
bootstrap) or from a toy that reproduces the features that matter (volatility
clusters, fat tails). Each is a model; `toy_studies.pulls` measures where a
quoted error stops being honest.

**The researcher has seen the answer.** A blind analysis assumes nobody has
looked in the box. Anyone who has read the literature has looked in most of
them, and an AI agent has read all of it up to its training cutoff. A famous
anomaly on famous data is never blind to the one studying it. The registration
has a `prior_exposure` field for exactly this, and the only sample no one has
seen is the one that has not happened yet.

**The tails are the experiment.** A detector's rare failure is a nuisance to
be masked. A market's rare event is where the money is lost. Jumps are flagged
and kept, the drawdown is reported next to every Sharpe ratio, and the paper
account has a brake.

## What carries over exactly

The four words. A result `holds`, is `stale`, `fails`, or is `unknown`, and
`unknown` is never written as a number. That is the one comparison
ThesisAnalysisOS makes for research results, applied here to a registration, a
frozen configuration, an unblinded verdict and a ledger.
