# quantAnalysisOS: Foundational Research

Nov 26, 2026 · @Justin Bennett

> Snapshot of the living document at https://claude.ai/artifact/8Z4gbuQ9L4tVCvZCTFd9Gk (2026-11-26). The chart in Section 1.3 is omitted here; `foundations_scripts/` reproduces every computed table (`bounds.py`: goal ceilings, shrinkage, verification time; `dp.py`: the Section 1.4 dynamic program; `eproc.py`: the Section 6.3 e-process simulation).

## Verdict

**No exploitable advantage is established.** Nothing here shows that $100 a week can be turned into extraordinary wealth faster than by saving it. What the work does establish is what an edge must look like to change that, how to measure it, and how long it takes to know.

Five numbers decide almost everything:

1. **With no edge, no strategy can beat money-in divided by goal.** The chance of reaching a goal b is at most (wealth + contributions) / b, and only all-or-nothing betting attains it. $1M from three years of $100 a week: at most 1.6%. *Deduction (optional stopping; Dubins & Savage).*
2. **With an edge, the edge enters only through Sharpe × √years.** The ceiling is Φ(Φ⁻¹(x/b) + θ√T). Even odds of a 10× gain need θ√T ≥ 1.28; 100× needs 2.33. *Deduction (Browne 1999; Föllmer & Leukert 1999).*
3. **Realistic edges in liquid markets are small.** Published equity anomalies net about 4–20 bp a month after costs today (Chen & Velikov 2023). A broad index has a Sharpe ratio near 0.3–0.4. *Established fact.*
4. **Proving an edge takes 2·ln(20)/θ² years of betting on it.** That is 24 years at θ = 0.5, 6 at θ = 1, and 1.5 at θ = 2. Only domains with hundreds of independent bets a year can be verified in months. *Deduction (test martingales, Ville's inequality).*
5. **For the first years, contributions dominate returns.** Year one puts in $5,200. A θ = 0.5 strategy at 10% volatility on the average balance of about $2,600 adds roughly $130. The pool is cheap; the information is expensive. *Deduction.*

**The lowest-level quantity.** An edge is the relative entropy, in nats per bet, between our forecast and the market's price, net of costs. That one number sets the Kelly growth rate (Kelly 1956). It bounds the probability of reaching a goal, which is the power of a Neyman–Pearson test. It is also the rate at which a betting account accumulates evidence against the market. Sizing, goals and validation all run on it, so the system is built around measuring it.

**Where to look.** The plausible places share three features: prices are explicit probabilities or odds, bets are many and nearly independent, and capacity is too small for funds. Section 4 ranks the candidates.

**Most likely outcome.** No durable edge survives costs. The design goal is to reach that answer cheaply and quickly, or to find the exception with evidence that would convince a hostile referee. No live orders, transfers or borrowing are authorized at any stage of this plan; any real-money step is the human's decision.

## How to read this

Every substantive claim carries one of four labels. A claim without a label is framing, not evidence.

| Label | Meaning | What would overturn it |
| --- | --- | --- |
| **Fact** | Established in peer-reviewed work or primary records, with a citation | A failed replication or a corrected source |
| **Deduction** | Follows mathematically from stated assumptions; computed or checked numerically here | A wrong step, or an assumption that does not hold |
| **Hypothesis** | An empirical claim we could test and have not | The pre-registered experiment in Section 6 |
| **Speculation** | A judgment call, kept only because it steers where to look | Anything; it carries no evidential weight |

Scope and limits:

- **Capital.** $100 a week from $0, possibly more later. US resident. Paper and historical capital only.
- **Authority.** No live orders, transfers, borrowing or financial commitments. Data purchases, network access and any move to real money are the human's decisions.
- **Sources.** The literature was gathered by parallel research agents and checked by me. Figures marked "not verified" came from abstracts or summaries and must be checked against the full papers before any analysis is frozen.
- **Computations.** The tables in Section 1 come from scripts kept with this document's working files. They assume Gaussian returns and no costs unless stated, which favours the trader.

## 1. The fundamental mathematical problem

The problem is a controlled diffusion with income: each week, choose exposure to maximize the chance of crossing a wealth target before a deadline, while the size of the edge is itself uncertain. Five results below answer when to concentrate, diversify, go all-in, wait, or scale up.

### 1.1 Wealth as a stochastic system

For continuous assets, with dollar exposures π, contribution rate c ($5,200 a year) and cumulative costs K:

```latex
dW_t = r W_t\,dt + \pi_t^{\top}(\mu - r\mathbf{1})\,dt + \pi_t^{\top}\Sigma^{1/2}\,dB_t + c\,dt - dK_t, \qquad W_t \ge 0
```

The edge is summarized by the maximal Sharpe ratio θ = ‖Σ^(−1/2)(μ − r)‖, which we never know exactly. No borrowing means total long exposure ≤ W; any leverage cap is L·W.

For a binary contract bought at price q when the true probability is p, a stake fraction f gives W' = W(1 + f(Y/q − 1)) with Y ∈ {0, 1}. Both forms reduce to the same quantity in 1.3.

### 1.2 Objectives compared

| Objective | Optimal policy when the edge is known | Behaviour | Failure mode |
| --- | --- | --- | --- |
| Max expected terminal wealth | All-in at maximum leverage on the highest-mean bet | Maximally concentrated | Ruin probability tends to 1 with horizon |
| Max expected log wealth (Kelly) | Constant fraction f\* = Σ⁻¹(μ − r) | Growth r + θ²/2; portfolio volatility equals θ | Halves wealth at some point with probability 1/2 |
| Max P(reach b before T) | Replicate a digital option on the goal | Bold when behind, timid when ahead | All-or-nothing: fails with probability 1 − P\* |
| Min ruin or drawdown | Exposure proportional to the cushion above a floor (Grossman & Zhou 1993) | Cuts risk after losses | Slower growth |
| Expected-shortfall cap | Kelly fraction reduced until the tail constraint binds | Similar to fractional Kelly | Needs tail estimates we cannot trust from short samples |

*Deduction and fact.* Kelly also minimizes the expected time to reach a distant goal asymptotically (Breiman 1961). That makes it the natural default when the deadline is long relative to θ⁻².

### 1.3 The unifying quantity: relative entropy

**Result A (zero-edge ceiling).** If net of costs there is no edge, discounted wealth plus discounted future contributions is a supermartingale. Optional stopping then gives, for any strategy and any goal b:

```latex
P(\text{reach } b \text{ before } T) \;\le\; \frac{x + \mathrm{PV}(\text{contributions})}{b}
```

Bold play (one all-in bet) attains it in a fair game; in a subfair game bold play is still optimal but falls short (Dubins & Savage 1965). *Deduction.*

**Result B (edge ceiling).** In a complete market with maximal Sharpe θ, maximizing the probability of reaching b from x by T is a Neyman–Pearson problem. The real-world measure P is tested against the pricing measure Q at size x/b (Föllmer & Leukert 1999), and the answer is (Browne 1999):

```latex
P^{*} = \Phi\!\left(\Phi^{-1}\!\left(\tfrac{x}{b}\right) + \theta\sqrt{T}\right)
```

It is an upper bound for every strategy, including ones with leverage, options or perfect timing. The edge enters only through θ√T. *Deduction; reproduced numerically.*

**Result C (one number runs everything).** The relative entropy D(P‖Q) of real-world against pricing measure over the horizon equals θ²T/2. It is simultaneously:

- the expected log growth of the Kelly portfolio, whose wealth is the likelihood ratio dP/dQ (Long 1990; Kelly 1956; Cover & Thomas 2006, ch. 6);
- the quantity that sets the Neyman–Pearson power in Result B;
- the expected rate at which a betting account gathers evidence against the market (Section 6).

For a binary contract the Kelly stake is f\* = (p − q)/(1 − q), and the optimal growth per bet is exactly KL(p‖q) = p·ln(p/q) + (1 − p)·ln((1 − p)/(1 − q)). *Deduction.* So the simplest measurable quantity behind any edge is: **out-of-sample nats per bet of our forecast over the market price, after fees.**

&#91;embedded content: Computed from Result B, P\* = Φ(Φ⁻¹(1/M) + θ√T), for goals M = 2, 10, 100, 1000\]

The curves depend only on Sharpe × √years, so a strong edge for one year and a modest one for many years are equivalent. A broad index over a decade sits near 1.26: at best about even odds of a tenfold gain and 14% for a hundredfold, and that ceiling needs unlimited leverage.

### 1.4 What constraints do to the ceiling

**Constraints, not cleverness, set the achievable probability.** Without borrowing, a strategy at 18% volatility cannot reach $1M within 10 years at any edge below θ = 2, and even then the chance is 6%. The table solves the weekly problem exactly by dynamic programming: $100 a week from $0, weekly rebalancing, Gaussian returns, no costs. *Deduction, computed.*

| Goal | Years | Edge θ | Unconstrained ceiling (Result B) | Optimal, up to 3× leverage | Optimal, no borrowing | Always 100% invested | Kelly, capped at 3× |
| --- | --- | --- | --- | --- | --- | --- | --- |
| $100k | 5 | 0 | 26.0% | 3.1% | 0.0% | 0.0% | 0.0% |
| $100k | 5 | 0.4 (an index) | 59.9% | 14.2% | 0.0% | 0.0% | 4.7% |
| $100k | 5 | 1 | 94.4% | 55.6% | 0.1% | 0.1% | 53.2% |
| $100k | 5 | 2 | 100% | 98.6% | 12.6% | 12.2% | 98.3% |
| $100k | 10 | 0 | 52.0% | 30.5% | 4.0% | 3.5% | 0.0% |
| $100k | 10 | 0.4 (an index) | 90.6% | 72.3% | 25.0% | 23.1% | 59.3% |
| $100k | 10 | 1 | 99.9% | 99.0% | 83.2% | 81.7% | 98.1% |
| $1M | 5 | 1 | 61.5% | 0.6% | 0.0% | 0.0% | 0.6% |
| $1M | 5 | 2 | 99.4% | 34.8% | 0.0% | 0.0% | 34.0% |
| $1M | 10 | 0.4 (an index) | 35.9% | 4.1% | 0.0% | 0.0% | 0.6% |
| $1M | 10 | 1 | 93.8% | 50.2% | 0.0% | 0.0% | 48.9% |
| $1M | 10 | 2 | 100% | 99.9% | 6.0% | 5.8% | 99.8% |

Three readings:

- **Capped Kelly is nearly goal-optimal once there is a real edge.** The optimal policy beats it by at most a few points. The gap appears only at θ = 0, where Kelly stays in cash and the optimum gambles. *Deduction.*
- **The unconstrained ceiling is far above anything achievable.** It needs unlimited leverage near the deadline. Real constraints cost most of the probability. *Deduction.*
- **Without a demonstrated edge, the honest baseline is an index fund.** At θ ≈ 0.4 and 100% invested, the chance of $100k in 10 years is about 23%. A proposed strategy must beat that baseline, not cash. *Deduction; θ ≈ 0.4 for a broad index is a historical estimate.*

### 1.5 When to concentrate, diversify, go all-in, wait, or scale up

- **Diversify across genuine edges.** Growth and the goal ceiling depend on θ²\_total = (μ − r)ᵀΣ⁻¹(μ − r). An independent bet with positive net edge always raises it. Concentrate only when the other candidates add no θ, because they are correlated or have no edge, or when costs and lot sizes make them unusable. *Deduction.*
- **Full-pool allocation.** With certain future contributions, log-optimal exposure is f\*·(W + H), where H is their present value (Merton 1971; Bodie, Merton & Samuelson 1992). Early on H is far larger than W, so even a modest Kelly fraction calls for 100% of the pool. The no-borrowing cap binds. This holds only if the edge is real. *Deduction.*
- **Wait instead of trading** whenever the net edge is ≤ 0. Every trade then lowers expected wealth. If a goal must be chased anyway, the optimum is the fewest, largest bets, placed as late as possible, and the ceiling is money-in divided by goal. *Deduction.*
- **Preserving capital for later.** Log utility is myopic: today's bet depends only on today's opportunity (Mossin 1968; Hakansson 1971). No reserve is needed beyond fractional Kelly. Goal objectives are not myopic. When ahead of schedule, or when better opportunities are expected, they hold back. *Deduction.*
- **Scale up only on evidence.** Size at f = k·θ̂/σ with k = θ̂²/(θ̂² + s²), where s is the standard error of θ̂. Full Kelly on an estimate has expected growth (θ² − s²)/2, which is **negative whenever the estimate's error exceeds the true edge.** *Deduction.*

| True Sharpe θ | Track record | Standard error s | Optimal fraction of estimated Kelly | Growth at full Kelly (per yr) | Growth at the optimal fraction |
| --- | --- | --- | --- | --- | --- |
| 0.25 | 5 yr | 0.45 | 0.23 | −0.072 | +0.007 |
| 0.5 | 3 yr | 0.61 | 0.40 | −0.063 | +0.050 |
| 0.5 | 10 yr | 0.34 | 0.69 | +0.069 | +0.086 |
| 1.0 | 3 yr | 0.71 | 0.67 | +0.250 | +0.333 |
| 1.0 | 10 yr | 0.39 | 0.87 | +0.425 | +0.435 |

The standard error uses Lo (2002), s = √((1 + θ²/2)/years). Selection across many tried strategies biases θ̂ upward further; the deflated Sharpe ratio in Section 6 corrects for that.

## 2. The strongest relevant literature

The literature says inefficiencies exist, shrink sharply once published, and survive costs mainly where capacity is small. Each row pairs the best positive result with the strongest evidence against it. Figures come from abstracts and primary-text extracts; the full tables have not yet been checked.

### 2.1 Market evidence

| Area | Strongest positive result | Strongest contrary evidence | What it means for us |
| --- | --- | --- | --- |
| Published anomalies | Most factors replicate across 93 countries (Jensen, Kelly & Pedersen 2023, JF) | Returns 26% lower out of sample, 58% lower after publication (McLean & Pontiff 2016, JF); 65% of 452 anomalies fail t > 1.96 once microcaps are handled (Hou, Xue & Zhang 2020, RFS); about 4 bp a month net of costs today, 20 bp for a combination (Chen & Velikov 2023, JFQA) | Replication is not tradability; plan for half the published size or less |
| Equity premium predictors | Many in-sample predictors | Over a third lose in-sample significance; about half the rest fail out of sample (Goyal, Welch & Zafirov 2024, RFS) | Market timing from ratios is a weak prior |
| Trend / time-series momentum | Net Sharpe about 0.76 over a century of futures (Hurst, Ooi & Pedersen 2017) | CTA index Sharpe about 0.1 from 2009 to 2019 (Babbedge & Kerson 2019); little asset-by-asset predictability (Huang, Li, Wang & Zhou 2020, JFE) | Real but episodic; needs futures we cannot size yet |
| Volatility-managed portfolios | In-sample Sharpe gain about 25% (Moreira & Muir 2017, JF) | Real-time versions generally fail (Cederburg et al. 2020, JFE); market version survives costs, others do not (Barroso & Detzel 2021, JFE) | A clean, low-turnover first test with data we have |
| Variance risk premium | Selling index variance earns a large premium (Carr & Wu 2009, RFS); straddles lose about 3% a week (Coval & Shumway 2001, JF) | A risk premium, not an inefficiency; Feb 2018 wiped out short-volatility products (BIS 2018) | Earned by bearing crash risk; sized for survival only |
| Earnings drift (PEAD) | Historically large | Gone in large caps since 2006 and now in microcaps (Martineau 2022, CFR); contested by two 2025 papers | Not a starting point |
| Index inclusion | About 7.4% in the 1990s | Under 1% in the 2010s (Greenwood & Sammon 2025, JF) | Arbitraged away |
| Merger arbitrage | 10.3% a year before costs | About 4% after costs, with a payoff like selling index puts (Mitchell & Pulvino 2001, JF) | A risk premium |
| Opportunistic insider buying | 82 bp a month value-weighted (Cohen, Malloy & Pomorski 2012, JF) | Post-2012 persistence not checked; equal-weighted version leans on small caps | The most plausible event signal for slow, careful reading |
| Long, complex filings | Changes in 10-K text predict returns for up to 18 months with no announcement effect (Cohen, Malloy & Nguyen 2020, JF) | No published decay study found; effect concentrated in optionable stocks | Where cheap AI reading could matter, if anywhere in equities |

### 2.2 AI and machine learning

| Result | Contrary evidence | Implication |
| --- | --- | --- |
| GPT headline scores: pre-cost Sharpe about 3, about 34 bp a day (Lopez-Lira & Tang, v6 2025) | Sharpe falls to −0.39 at 20 bp a trade; decays from 6.5 (late 2021) to 1.2 (2024) as adoption spreads | Speed and headline sentiment are closed to us |
| ML cross-section: value-weighted Sharpe 1.35 (Gu, Kelly & Xiu 2020, RFS) | Excluding microcaps cuts the payoff by about 62%; costs remove most of the rest (Avramov, Cheng & Metzker 2023, Mgmt Sci) | ML alpha mostly sits where we cannot trade |
| Pretrained LLMs as forecasters | They memorize pre-cutoff prices and index levels; masking and instructions do not stop it (Lopez-Lira, Tang & Zhu 2025); look-ahead bias formally detected (Sarkar & Vafa, ICML 2025); bias can even reverse sign (Glasserman & Lin 2023) | **Any backtest of an LLM signal before the model's training cutoff is contaminated** |
| Live AI trading | The AI-run ETF AIEQ trailed the S&P 500 by roughly half on cumulative return since 2017 (press, not peer-reviewed); 4 of 6 LLMs lost money in a 17-day live crypto contest | Having AI is not an edge |
| Speed of news | Prices react within seconds (Busse & Green 2002, JFE) and within 5 ms for macro releases (Chordia, Green & Kottimukkalur 2018, RFS) | Only slow-to-digest information is left |

### 2.3 Base rates for individuals

- Fewer than 1% of Taiwanese day traders predictably earn net abnormal returns (Barber, Lee, Liu & Odean 2014). *Fact.*
- Of Brazilian day traders who persisted over 300 days, 97% lost money (Chague, De-Losso & Giovannetti 2019). *Fact.*
- The most active US households earned 11.4% a year against the market's 17.9% (Barber & Odean 2000, JF). *Fact.*
- Retail options buyers lose on average, paying spreads near 12.6% on weeklies (Bryzgalova, Pavlova & Sikorskaya 2023, JF), and 5–14% around high-volatility earnings (de Silva, Smith & So 2025). *Fact.*
- Retail 0DTE traders lost about $358k a day after daily expiries began, about 60% of it in costs (Beckmeyer, Branger & Gayda 2023, working paper). *Fact, not peer-reviewed.*
- Options with the most positive skew earn the least, by 10–50% a week across portfolios (Boyer & Vorkink 2014, JF). **Convexity is something retail buys, and buyers overpay.** *Fact.*

### 2.4 The one documented exception

Medallion averaged 66% a year gross and 39% net from 1988 to 2018, with negative market beta (Cornell 2019). The edge reportedly came from a hit rate barely above 50% across enormous numbers of short-horizon trades, with assets capped near $10bn. That is a Sharpe of roughly 2 built from breadth, the opposite of a few concentrated bets. *Fact for the returns; Speculation for the mechanism.*

### 2.5 Mathematics and decision theory

The results in Section 1 rest on: Kelly (1956) and Breiman (1961) on growth; Dubins & Savage (1965) on bold play; Browne (1999) and Föllmer & Leukert (1999) on goal-reaching and quantile hedging; Merton (1971) and Bodie, Merton & Samuelson (1992) on income streams; Mossin (1968) and Hakansson (1971) on myopia; Grossman & Zhou (1993) on drawdown limits; and Shafer & Vovk's testing by betting with Ville's inequality (Section 6). *Fact.*

## 3. Competitive advantages available to one person

Only two advantages are plausibly real: **we can bet where size is impossible, and we can afford patience and many small bets that a fund cannot be bothered with.** Everything else on the list is either shared with every other participant or is a research-process advantage, not a market edge.

| Claimed advantage | Real market edge? | Reasoning |
| --- | --- | --- |
| Small capital, negligible impact | **Yes, conditionally** | Thin order books (prediction markets, small events) cap what funds can deploy. Kalshi and Polymarket books are small enough that a $10M fund cannot use them. *Hypothesis.* |
| Low capacity need | **Yes, conditionally** | Medallion caps itself near $10bn because its edge decays with size; a $5,000 pool has no such problem. The edge still has to exist. *Speculation.* |
| No career risk, long patience | **Weak yes** | We can hold a strategy through a decade of underperformance that would fire a fund manager. That earns risk premia, not inefficiencies. *Hypothesis.* |
| Breadth of many small, independent bets | **Possibly** | The fundamental law says information ratio ≈ skill per bet × √bets. A tiny per-bet edge across thousands of contracts compounds into measurable evidence (Section 1.3). *Deduction.* |
| AI reading of long public documents | **Unproven** | Lazy Prices shows slow uptake of 10-K changes (Cohen, Malloy & Nguyen 2020). Every participant now has the same models, and backtests of LLM signals before the training cutoff are contaminated. Only prospective evidence counts. *Hypothesis.* |
| Speed, latency, news | **No** | Prices absorb news in seconds to milliseconds (Busse & Green 2002; Chordia et al. 2018). |
| Cross-disciplinary mathematics | **Process only** | It protects us from fooling ourselves: look-elsewhere corrections, blinding, calibration. It does not create returns. |
| Continuous autonomous research | **Process only, and a risk** | Cheap iteration multiplies trials. Without a ledger counting every trial, it manufactures false discoveries faster. |
| Independent multi-agent verification | **Process only** | Two models with overlapping training data are not independent witnesses (Section 9). |
| Having powerful AI | **No** | AI-run funds and live LLM trading contests have underperformed simple benchmarks so far (Section 2.2). |

**Where the advantages intersect.** Thin, odds-quoted markets with thousands of contracts a year, where retail takers pay fees and biases are documented. Prices there are explicit probabilities, so the edge in nats per bet is directly measurable. *Hypothesis.*

**The binding cost: fees.** Kalshi charges takers 0.07×P×(1−P) per contract and makers 0.0175×P×(1−P) on eligible series. At a price of 0.50 that is 1.75¢ and 0.44¢. A true 2¢ mispricing at mid-prices yields 0.0008 nats per bet before fees, 0.00001 for a taker, and 0.0005 for a maker. **A taker edge of 2¢ is fully eaten by fees; only maker orders or larger mispricings survive.** At 0.0005 nats per bet, 20:1 evidence takes about 6,000 independent bets. *Deduction from the published fee schedule.*

## 4. Comparative landscape of candidate inefficiencies

Prediction-market biases rank first: they are documented, fee-transparent, free to observe, too small for funds, and verifiable within months. Liquid equity effects rank lower because, even if real, they cannot be proven in under a decade. Ranked by the rate at which a real edge could be confirmed, net of costs, by a small account.

| Rank | Candidate | Mechanism | Plausible net edge | Time to 20:1 evidence if real | Capacity fit | Access and data | Main killer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Prediction-market favourite–longshot and horizon bias (maker side) | Retail takers overpay for longshots; prices far from expiry are compressed (Le 2026); takers lose about 32% on Kalshi (Bürgi, Deng & Whelan 2025) | Small per bet: maker returns on contracts above 50¢ reportedly small but positive (not verified) | Months: thousands of contracts a year | Excellent | Kalshi is CFTC-regulated; free public API; no account needed to observe | Adverse selection on maker fills; fee changes; legal shocks to sports contracts |
| 2 | Cross-venue and combinatorial prediction-market mispricing | Same event priced differently on different venues; inconsistent linked markets (Saguillo et al. 2025: about $40M arbitraged on Polymarket in a year) | Unknown for a slow participant | Months, if fills are real | Good | Free APIs; Polymarket US access only through its regulated venue | Bots get there first; settlement-rule differences across venues |
| 3 | Soccer odds favourite–longshot bias against sharp closing lines | 1X2 odds show a bias even at low-margin books (Hegarty & Whelan) | Real but capped | Months | Poor: winning accounts are limited within weeks | Free historical closing odds (football-data.co.uk) | Account limits; legality varies by state |
| 4 | Opportunistic insider purchases | Insiders buying against their routine (Cohen, Malloy & Pomorski 2012) | Unknown after 2012 | Years | Good | Free SEC Form 4 filings | Decay; small-cap spreads |
| 5 | Slow uptake of long filings (AI-read 10-K changes) | Investors miss text changes (Cohen, Malloy & Nguyen 2020) | Unknown; everyone has LLMs now | Years, and only prospectively | Good | Free EDGAR filings | Look-ahead contamination; crowding |
| 6 | Volatility-managed index exposure | Volatility clusters while expected returns do not rise with it (Moreira & Muir 2017) | 0 to +0.1 Sharpe over buy-and-hold | Decades | Excellent | Data in hand | Real-time failure (Cederburg et al. 2020) |
| 7 | Index trend (long or cash) | Slow diffusion and drawdown avoidance (Moskowitz, Ooi & Pedersen 2012) | Small Sharpe gain; mainly drawdown cut | Decades | Excellent | Data in hand | Whipsaw; evidence mostly pre-1942 |
| 8 | Selling index volatility | Variance risk premium (Carr & Wu 2009) | Positive on average | Years, then one crash | Medium | Options data costs money | It is a crash-risk premium, not an inefficiency |
| 9 | Crypto carry and perpetual basis | Leverage demand pays funding (He, Manela, Ross & von Wachter 2022) | Fell below T-bills in 2026 | — | Poor: institutional now | Free exchange archives; US perpetuals since mid-2026 | Decayed; crash-prone |
| 10 | Buying lottery-like payoffs (0DTE, OTM calls, longshots) | None: this is the side that pays the premium | Negative (Section 2.3) | — | — | — | **Rejected before testing**; kept only as a benchmark of what not to do |

**Two things the table rules out.** Headline-speed AI trading and post-earnings drift are omitted: the evidence says both are gone for us. The "high-upside" instruments in row 10 are rejected outright: buyers of convexity are the counterparty to everyone else's edge.

**Honest base rate for row 1.** Of Polymarket wallets, 69–87% lost money (Galaxy and other analytics firms; not peer-reviewed). Profits are concentrated: the top 1% of profitable users took 76.5% of profits, and their persistence may be selection rather than skill (Akey et al., CEPR DP21615). Being on the right side of a documented bias is necessary, not sufficient.

## 5. The simplest promising hypotheses

Four hypotheses go first: two prediction-market tests that could be settled within a year, one equity control that uses data already in hand, and one AI test that can only be run prospectively. Each is the simplest version of its mechanism. All are *Hypotheses* until Section 6's experiments run.

| Point | H1: Maker-side bias on Kalshi | H2: Kalshi prices are miscalibrated by horizon | H3: Volatility-managed index | H4: AI-read filing changes |
| --- | --- | --- | --- | --- |
| 1. Mechanism | Retail takers pay fees and overpay for longshots; patient makers collect the spread and the bias | Prices far from expiry are compressed toward 50% (Le 2026); traders under-react to slowly arriving information | Volatility clusters, but expected returns do not rise with it, so exposure should fall when volatility is high | Investors do not read long 10-K/10-Q changes; an LLM reads all of them cheaply |
| 2. Formulation | Mean net return per $1 of maker fills on contracts priced ≥ 50¢ | Log-score gain of a two-parameter recalibration, logit(p) = a + b·logit(price), fitted by horizon bucket, over the raw price | Exposure w = min(c / σ̂², 1), with σ̂² the last 21 days' realized variance and c set to the unconditional variance | Long-short on the year-over-year text-change score, value-weighted, microcaps excluded |
| 3. Known at decision time | Order book and own resting orders; settlement rules | Price, time to expiry, category; parameters from earlier data only | Closing prices up to t−1; rebalance at the next close | Filings timestamped by EDGAR acceptance time; model with a training cutoff before the test window |
| 4. Predicted observable | Positive mean net return, clustered by event | Positive out-of-sample log-score gain, measured in nats per contract | Sharpe above buy-and-hold, with shallower drawdowns | Positive spread over 1–18 months after filing, with no announcement-day jump |
| 5. Falsifiable experiment | Prospective paper maker on markets that settle after a registered start date | Recalibration fitted on 2022–2024 settled markets; scored once on sealed 2025–2026 markets; then prospectively | Registered single rule; development 1926–1990; holdout 1991–2026, opened once | Prospective only: forecasts logged and hashed before returns are known |
| 6. Data and compute | Kalshi public API order books and trades; laptop-scale | Kalshi historical markets and candlesticks (free API, Dune); laptop-scale | Ken French daily market and risk-free rate; already in the system | EDGAR (free); LLM tokens cost money, a human decision |
| 7. Execution and costs | Fill only when a later trade prints through our price; maker fee 0.0175·P·(1−P); queue position unknown, so assume the worst | Taker fee 0.07·P·(1−P) rounded up per order; trade only where gain exceeds fees | 3–5 bp per side, stressed at 2×; monthly rebalance | 20 bp per trade minimum; borrow cost on shorts |
| 8. Rejection criteria | Reject if the 95% CI (clustered by event) of net return per $ lies below +0.5¢ after 3,000 settled fills, or 18 months pass without 20:1 evidence | Reject if the sealed-sample log-score gain net of fees is ≤ 0, or its 95% CI includes 0 | Reject if the holdout Sharpe difference is ≤ 0 or its deflated p-value > 0.05 | Reject if the prospective spread after costs is ≤ 0 after 24 months |
| 9. Benchmark | Cash; a placebo maker on the opposite side at the same prices | The raw market price (the null is "the market is calibrated") | 100% index, buy-and-hold | Equal exposure to the market factor |
| 10. Worth pursuing? | **Yes, first.** Fastest to verify and capacity-friendly | **Yes, first.** Pure measurement; costs nothing to run; it also sizes H1 | **Yes, as a control.** It checks the machinery on a well-studied effect; it will not make money that matters | **Later**, once H1–H3 have exercised the protocol; token costs need approval |

**What is deliberately absent.** No neural networks, no indicator libraries, no reinforcement learning. Each would multiply trials before any simple mechanism has been shown to work. Reinforcement learning in particular needs a simulator whose fidelity is itself unproven. Complexity is admitted only when a simpler model is beaten out of sample by a pre-registered margin. *Speculation, held as policy.*

## 6. Statistical experiments

Every claim passes through four data regimes, and the last one is the paper account itself, run as a test martingale. That makes the profit the evidence, and lets us watch it daily without inflating false discoveries.

### 6.1 Four regimes, in order

1. **Discovery.** Anything may be tried, but every trial is appended to the hash-chained ledger. Trials count against the look-elsewhere budget whether or not they are reported.
2. **Development.** Only a pre-registered grid is scanned, on the development window. The holdout rows are cut off before any strategy sees the data. The quantAnalysisOS `register → scan → freeze` commands already enforce this.
3. **Sealed evaluation.** The frozen configuration runs once on the holdout (`unblind`). The registered rule decides the verdict. A disappointing result is recorded, not re-run.
4. **Prospective.** Data that did not exist when the hypothesis was frozen. For any signal touched by an LLM, this is the **only** admissible evidence, because pretrained models memorize pre-cutoff prices and masking does not stop it (Lopez-Lira, Tang & Zhu 2025).

### 6.2 Correcting for search

- **Deflated Sharpe ratio** (Bailey & López de Prado 2014), with the effective number of trials after clustering correlated ones. Kurtosis enters as raw kurtosis (normal = 3); passing excess kurtosis silently changes every result.
- **t > 3** as the single-test bar for a new factor (Harvey, Liu & Zhu 2016), equivalent to a trials factor of about 18.5 at a global 5%.
- **Hansen's SPA test** (2005) for "is the best of these real?", and **Romano–Wolf stepdown** for "which ones?", both on the stationary bootstrap with the Politis–White block length (Patton correction).
- **Probability of backtest overfitting** by combinatorial cross-validation (Bailey, Borwein, López de Prado & Zhu 2017), always reported with its toy-study spread. On pure noise it averaged 0.47 with a per-seed standard deviation of 0.18, so a single value means little.
- **Overlapping returns** inflate naive t-statistics by √h for h-period holds (√5 = 2.24 for weekly holds on daily data). Use HAC errors or non-overlapping samples.
- **Clustering by event.** Contracts on the same election or game are not independent. The effective sample size is the number of events, not contracts.

### 6.3 The prospective test: testing by betting

Under the null that the market is right, the wealth of any bettor at market prices, measured per unit and relative to the benchmark, is a nonnegative supermartingale. Ville's inequality then bounds the chance it ever reaches 1/α (Shafer & Vovk; Ramdas et al. 2023):

```latex
E_t = \prod_{i \le t} \left(1 + f_i\left(\frac{Y_i}{q_i} - 1\right)\right), \qquad P_{H_0}\!\left(\sup_t E_t \ge \tfrac{1}{\alpha}\right) \le \alpha
```

For equity strategies E\_t is NAV per unit divided by the benchmark's NAV per unit, so weekly contributions do not distort it. Fees make E\_t a strict supermartingale under the null, which only makes the test more conservative. Consequences:

- **Peeking is free.** The account can be checked daily and stopped at any time without inflating the false-positive rate. That removes the main way prospective tests get p-hacked.
- **The pass mark is E ≥ 20** (α = 0.05), registered in advance. The expected time to reach it is ln(20) divided by the realized nats per bet (Section 1.3).
- **Several hypotheses at once** are combined with the e-BH procedure (Wang & Ramdas 2022), which stays valid under arbitrary dependence.

Simulated check, 4,000 paths of 8,000 binary bets at prices between 0.15 and 0.85. The bettor claims a 3¢ edge. *Deduction, computed.*

| True edge | Stake | Paths reaching E ≥ 20 | Median bets to reach it |
| --- | --- | --- | --- |
| 0 (null) | ½ Kelly | 4.2% | — |
| 0 (null) | full Kelly | 4.9% | — |
| 1¢ | ½ Kelly | 49.5% | 3,988 |
| 1¢ | full Kelly | 33.2% | 1,827 |
| 2¢ | ½ Kelly | 96.5% | 2,657 |
| 3¢ | ½ Kelly | 100% | 1,626 |

The null rate stays below 5%, as Ville's inequality requires. Overstating the edge costs power, and half Kelly is the more robust stake when the true edge is smaller than believed.

### 6.4 Calibration and degradation

- **Forecast quality** is scored by log score and Brier score against the market price, with reliability diagrams. Differences are tested with Diebold–Mariano statistics clustered by event.
- **Degradation** is watched by a second e-process that bets on "the edge has fallen below half its claimed size". When it reaches 20, the strategy is halted and the claim is re-opened as a new hypothesis.
- **Every machinery change is first validated on toys.** A planted edge must be recovered at the theoretical rate, and the false-alarm rate on nulls must stay at or below α. The existing `qaos toys` command is where these run.

### 6.5 Reference test vectors for the statistics module

| Quantity | Inputs | Expected | Source |
| --- | --- | --- | --- |
| Deflated Sharpe ratio | Annual SR 2.5, 250 periods a year, T = 1250, N = 100, V\[SR\] = 0.5, skew −3, kurtosis 10 | 0.90040 | Bailey & López de Prado 2014 example; reproduced |
| Expected max Sharpe, unit variance | N = 10 / 100 / 1000 | 1.57460 / 2.53060 / 3.25512 | Computed |
| Minimum backtest length | 45 trials, target SR 1 | 4.998 years | Bailey et al. 2014; reproduced |
| Lo annualization factor η(12) | AR(1) monthly, φ = 0 / 0.2 / 0.5 | 3.46410 / 2.87885 / 2.12129 | Lo 2002 formula; computed |
| Stationary-bootstrap block length | AR(1) φ = 0.5, n = 1000 | 12.114 | Politis–White with Patton correction; computed |
| Local to global significance | Local 5σ, 1,000 trials | 3.44σ global | Computed |
| Goal ceiling | x/b = 0.01, θ = 1, T = 3 | 0.276 | Browne 1999 formula; computed |
| Ville false-alarm rate | Table above, null rows | ≤ 0.05 | Computed |

## 7. Data availability and acquisition costs

Everything the first three hypotheses need is free. Two of them need one network host allowed. The environment currently reaches only package registries and GitHub; Yahoo, FRED, Dartmouth (Ken French), CBOE and Treasury are blocked. Reachability below was tested by downloading the files.

| Use | Source | Coverage | Reachable now | Cost | Known defects |
| --- | --- | --- | --- | --- | --- |
| H3: market and factors, monthly | French FF5, momentum, RF, via GitHub mirror `haribharadwaj/FamaFrench` | 1963-07 to 2026-09 | Yes | Free | Unofficial mirror: pin the commit and hash every file; French revises old months |
| H3: daily total return | SPY with dividend factors, QuantConnect Lean sample data | 1998 to 2021-03 | Yes | Free; data terms unclear | Ends 2021 |
| H3: long history | `SteelCerberus/us-market-data` synthetic total return | 1885 to 2025-12 | Yes | Free (MIT) | Spliced pre-1928 Dow data; crude risk-free rate before 1926 |
| Volatility | `datasets/finance-vix` (CBOE history) | 1990 to 2026-09 | Yes | Free | Back-calculated before 2003; not tradable before 2004; closes at 4:15 pm ET, not 4:00 |
| Valuation | Shiller data, `datasets/s-and-p-500` | 1871 to 2023-06 usable | Yes | Free | Monthly averages, not closes; stores 0.0 for missing after 2023-06; lag earnings 3+ months |
| H1, H2: prediction markets | Kalshi public API: markets, trades, candlesticks; Polymarket Gamma/CLOB APIs; Dune tables | Kalshi from 2021 | **No: host must be allowed** | Free, no key for market data | Wash trading in Polymarket volume (about 25%); settlement-rule differences across venues |
| H4: filings | SEC EDGAR full-text and Form 4 | 1994 onward | No: host must be allowed | Free data; LLM tokens cost money | Use acceptance timestamps, not filing dates |
| Index membership | `fja05680/sp500` historical constituents | 1996 to 2026-08 | Yes | Free | Fixes the membership list only; no free prices for delisted stocks |
| Crypto | Bitstamp BTC/USD minutes, `ff137/bitstamp-btcusd-minute-data` | 2012 to now | Yes (about 150 MB) | Free | Missing minutes filled with flat zero-volume bars |
| Options, futures, intraday equities | Commercial vendors | — | — | Paid | Deferred; buying data is a human decision |

**Two rules this forces.**

- **No single-stock backtests.** No free source has prices for delisted stocks, so single-stock studies would be survivorship-biased. Test factor portfolios and index products only. *Fact.*
- **Drop the price-only series.** The `arch` package's S&P 500 has adjusted close equal to close on all 5,031 rows, so about 2 points a year of dividends are missing. Its VIX covers only 2014–2019. quantAnalysisOS should switch to the total-return sources above. *Fact, checked.*

**Hosts worth allowing, in order** (each is a human decision in the environment's network settings):

1. The Kalshi public API host, which unblocks H1 and H2.
2. `mba.tuck.dartmouth.edu`, for official, current and daily French factors.
3. `fred.stlouisfed.org`, for yields and rates.
4. `huggingface.co`, for the Chen–Zimmermann anomaly library.
5. SEC EDGAR, for H4 later.

## 8. Realistic simulation methodology

A simulation is only as honest as its clock and its fills. Every datum carries the time it became knowable, every fill is assumed to be the worst plausible one, and every result is re-run against a world where we know the answer.

### 8.1 Two clocks

- Each record stores **event time** (when it happened) and **knowledge time** (when we could have seen it: an EDGAR acceptance stamp, an API fetch time, a price print). A strategy at decision time t sees only records with knowledge time ≤ t.
- Revised data keeps every vintage. A backtest reads the vintage that existed then, never today's corrected value.
- The existing causality gate stays mandatory: perturb everything after t and confirm that no decision at or before t changes.

### 8.2 Fills and costs

| Venue | Fill rule | Cost model | Stress test |
| --- | --- | --- | --- |
| Liquid ETFs | Next close after the signal, or next open | 3–5 bp per side for the most liquid funds, 10–20 bp for others | 2× costs; one bar of extra delay |
| Binary contracts, taker | At the displayed ask, limited to the displayed size | 0.07·C·P·(1−P), rounded up to the cent per order | Fee schedule changes; 2¢ worse fills |
| Binary contracts, maker | Filled only when a later trade prints at or through our price; queue position assumed last | 0.0175·C·P·(1−P) where maker fees apply | Fill only on trades strictly through our price (adverse selection) |
| Any | Trade size ≤ 10% of displayed depth | — | Halve the allowed size |

Settlement rules, voided markets and disputed resolutions are modeled explicitly, since they are a real loss channel in event contracts.

### 8.3 Accounting

- **NAV per unit.** Each $100 contribution buys units at the current NAV, as in a fund. Returns, Sharpe ratios and e-values use NAV per unit, so contributions never masquerade as performance.
- **Settlement and tax.** T+1 settlement and cash-account good-faith rules for securities. Short-term gains taxed at ordinary rates in the after-tax report. Wash-sale flags for repeated re-entry into the same fund.
- **Reconciliation.** Each paper fill is matched against a shadow backtest run on the same day's data. Daily P&L correlation below 0.9, or any unexplained position mismatch, halts the account.

### 8.4 Worlds where we know the answer

- **Null worlds:** markets that are exactly calibrated, and return series with no predictability. Any strategy must show an edge of zero within error, and the e-process must keep its false-alarm rate ≤ α.
- **Planted worlds:** a known bias of chosen size, for example a horizon compression of 5¢. The pipeline must recover its size and reach E ≥ 20 at the rate ln(20)/KL predicts.
- **Adversarial worlds:** planted look-ahead (a feature that peeks one bar ahead) and survivorship (delisted names removed). The causality gate and data audits must catch each one.

### 8.5 Reproducibility

Every result records the hash of the code, the hash of each input file, the random seed and the registration it answers to. The existing `standing` command re-derives the result and reports it as holds, stale, fails or unknown. A result that cannot be re-derived carries no weight.

## 9. Independent Claude–Codex research protocol

Agreement between two models is not evidence. Their training data overlaps, so their errors correlate. The protocol therefore uses the two agents to produce **independent artifacts** (two implementations, two derivations), and leaves the verdict to data neither of them controls.

### 9.1 Roles for each hypothesis

| Role | Does | Must not |
| --- | --- | --- |
| Proposer | Writes the registration: mechanism, formula, data, grid, test, rejection rule, benchmark | Touch evaluation data before the registration is committed |
| Falsifier | Derives the hypothesis's predictions independently from the registration text alone; writes the attack list (leakage, survivorship, cost, clustering, regime) | Read the proposer's code before writing its own derivation |
| Second implementer | Computes the primary statistic from the frozen spec with code written from scratch | Share code with the proposer; agreement is checked to a stated tolerance before unblinding |
| Human | Approves data purchases, network access, token spend and any real-money step; breaks ties on procedure, never on results | — |

Roles alternate by hypothesis number: Claude proposes odd-numbered hypotheses and Codex even-numbered ones, so each agent spends half its time attacking the other.

### 9.2 Rules that make it independent

1. **Commit before data.** A registration is a git commit whose hash is recorded in the ledger before any evaluation data is read. Git's timestamps and the hash chain make late edits visible.
2. **Two implementations or no unblinding.** The sealed evaluation runs only after both implementations reproduce each other's primary statistic on development data within tolerance (for example, relative difference below 10⁻⁶).
3. **Frozen means frozen.** After `freeze`, neither agent may change the evaluation procedure. A procedural fix becomes a new registration, and the old result stays in the ledger.
4. **Kills are credited.** The ledger records who killed which hypothesis and how. A falsifier that finds nothing on a hypothesis that later fails prospectively is scored against.
5. **Evidence ranks are fixed in advance.** Prospective results outrank sealed evaluations, which outrank independent re-implementation, which outranks development backtests. Agent agreement has zero weight.
6. **No agent marks its own work verified.** The verifier is a different agent, and the verdict comes from the registered rule.

### 9.3 Where this lives

The TAOS conventions already supply what the protocol needs: claims on scopes, handoffs with required sections, evidence references, and a human decision queue. quantAnalysisOS should reuse those conventions rather than copy the TAOS runtime. Registrations, trial logs and verdicts live in quantAnalysisOS's own hash-chained book, which Codex can read because it is plain files in the repository.

## 10. Prioritized roadmap with acceptance criteria

Build the smallest complete loop first: measure a goal, gather evidence, settle one hypothesis. quantAnalysisOS already has the study discipline, the ledger, the backtest engine and a paper account. The roadmap adds only what the four hypotheses need, and each phase ends at a check a script can run.

1. **Consolidate what exists (week 1).**
   - Push the other session's quantAnalysisOS build to a branch and commit this document beside it as the research charter.
   - Accept when: `qaos selftest` passes on a fresh clone, and the ledger hash chain verifies end to end.
2. **Goal calculator (weeks 1–2).** A `qaos goal` command computes the zero-edge ceiling, the Browne ceiling and the dynamic-programming policy for any contribution schedule and leverage cap.
   - Accept when: it reproduces the Section 1.4 table within ±0.5 points; simulated optimal policies match the closed form within Monte Carlo error; no policy beats the zero-edge ceiling on 10,000 null paths.
3. **Evidence monitor (weeks 2–3).** A `qaos evidence` command keeps the e-process for every paper account and bet stream, combines hypotheses with e-BH, and runs the degradation e-process.
   - Accept when: the null false-alarm rate is ≤ 5% on 10,000 toy paths; median detection time on planted edges is within 20% of ln(20)/KL; the Section 6.5 test vectors pass.
4. **H3 control study (weeks 2–4, in parallel).** Run the volatility-managed index study through register, scan, freeze and unblind on data already in the system.
   - Accept when: Codex's independent implementation matches the primary statistic within 10⁻⁶, and the verdict is recorded by the registered rule, whatever it is.
5. **Binary-market data and toys (weeks 3–5).** Ingest Kalshi public market data with knowledge-time stamps; build calibrated, planted-bias and adversarial binary-market toys.
   - Needs a human decision: allowing the Kalshi API host in this environment's network settings.
   - Accept when: two independent pulls hash identically; settled-market counts match the API's totals; the causality gate passes; planted horizon bias is recovered within its standard error.
6. **H2 calibration study (weeks 5–7).** Fit the recalibration on 2022–2024 settled markets; score it once on sealed 2025–2026 markets.
   - Accept when: two implementations agree, and the verdict follows the registered rule. A positive result also fixes the edge sizes used in H1's power calculation.
7. **H1 prospective paper maker (week 8 onward).** Paper-only maker orders on markets settling after the registered start date, with the e-process running from day one.
   - Accept when one of these is reached: E ≥ 20 (pass), the registered rejection rule fires, or 18 months pass. Throughout: shadow reconciliation correlation ≥ 0.9, zero unexplained mismatches, and a kill-switch drill fired successfully at least once.
8. **Shutdown and degradation (week 8).** A single `halt` that freezes every paper account, plus the degradation e-process wired to it.
   - Accept when: a drill halts all accounts within one cycle and the ledger records who halted and why.
9. **Human gate (no date).** Real money is considered only if a hypothesis passes prospectively with costs reconciled. The human chooses the amount. Scaling follows a pre-written rule: double no more than every 6 months, never above half Kelly on a deflated Sharpe ratio.

**Deferred until the loop works:** H4 (LLM-read filings; token spend needs approval), anything needing options or futures data (costs money), and any machine learning beyond two-parameter recalibration.

**Stop rule for the whole program.** If after 18 months no hypothesis has reached E ≥ 20 prospectively, the honest conclusion is that this setup has no demonstrable edge. The default then is the index baseline from Section 1.4, and the research continues only on new mechanisms, never on re-tuned old ones.

## References

Gathered by research agents through web search; most network hosts for the full papers were blocked, so figures come from abstracts and primary-text extracts. Verify against the published tables before any analysis is frozen.

**Mathematics and decision theory.** Kelly (1956) Bell System Technical Journal; Breiman (1961) Fourth Berkeley Symposium; Dubins & Savage (1965) *How to Gamble If You Must*; Mossin (1968) J. Business; Hakansson (1971) J. Finance; Merton (1971) J. Economic Theory; Long (1990) JFE; Bodie, Merton & Samuelson (1992) J. Econ. Dynamics & Control; Grossman & Zhou (1993) Math. Finance; Browne (1999) Adv. Applied Probability, "Reaching goals by a deadline"; Föllmer & Leukert (1999) Finance & Stochastics, "Quantile hedging"; Cover & Thomas (2006) *Elements of Information Theory*, ch. 6 and 16; MacLean, Thorp & Ziemba (2010) Quantitative Finance; Shafer & Vovk (2019) *Game-Theoretic Foundations for Probability and Finance*; Ramdas, Grünwald, Vovk & Shafer (2023) Statistical Science, "Game-theoretic statistics and safe anytime-valid inference"; Wang & Ramdas (2022) JRSS-B, e-BH.

**Statistics of backtests.** Lo (2002) FAJ; White (2000) Econometrica; Hansen (2005) JBES; Romano & Wolf (2005) Econometrica; Politis & Romano (1994) JASA; Politis & White (2004) and Patton, Politis & White (2009) Econometric Reviews; Bailey & López de Prado (2012) J. Risk and (2014) JPM; Bailey, Borwein, López de Prado & Zhu (2014) Notices AMS and (2017) J. Computational Finance; Harvey, Liu & Zhu (2016) RFS; Magdon-Ismail et al. (2004) J. Applied Probability.

**Anomalies and replication.** McLean & Pontiff (2016) JF; Hou, Xue & Zhang (2020) RFS; Jensen, Kelly & Pedersen (2023) JF; Chen & Velikov (2023) JFQA; Goyal, Welch & Zafirov (2024) RFS; Moskowitz, Ooi & Pedersen (2012) JFE; Hurst, Ooi & Pedersen (2017) JPM; Huang, Li, Wang & Zhou (2020) JFE; Moreira & Muir (2017) JF; Cederburg, O'Doherty, Wang & Yan (2020) JFE; Barroso & Detzel (2021) JFE; Barroso & Santa-Clara (2015) JFE; Ehsani & Linnainmaa (2022) JF; Fama & French (2021) RAPS; Frazzini & Pedersen (2014) JFE; Novy-Marx & Velikov (2022) JFE.

**Options, events, retail.** Carr & Wu (2009) RFS; Bakshi & Kapadia (2003) RFS; Coval & Shumway (2001) JF; BIS Quarterly Review (March 2018); Savor & Wilson (2016) JF; Frazzini & Lamont (2007) NBER; Martineau (2022) Critical Finance Review; Greenwood & Sammon (2025) JF; Mitchell & Pulvino (2001) JF; Cohen, Malloy & Pomorski (2012) JF; Lou, Polk & Skouras (2019) JFE; Boehmer, Jones, Zhang & Zhang (2021) JF; Bali, Cakici & Whitelaw (2011) JFE; Boyer & Vorkink (2014) JF; Bryzgalova, Pavlova & Sikorskaya (2023) JF; de Silva, Smith & So (2025) Review of Finance; Beckmeyer, Branger & Gayda (2023) SSRN; Barber & Odean (2000) JF; Barber, Lee, Liu & Odean (2014) J. Financial Markets; Chague, De-Losso & Giovannetti (2019) SSRN; Cornell (2019) SSRN, "Medallion Fund: the ultimate counterexample?"

**AI and text.** Lopez-Lira & Tang, arXiv 2304.07619 (v6, 2025); Glasserman & Lin, arXiv 2309.17322; Sarkar & Vafa (2025) ICML; Lopez-Lira, Tang & Zhu, arXiv 2504.14765; He, Lv, Manela & Wu, arXiv 2502.21206; Ke, Kelly & Xiu, NBER w26186; Cohen, Malloy & Nguyen (2020) JF; Loughran & McDonald (2011) JF; Tetlock (2011) RFS; Gu, Kelly & Xiu (2020) RFS; Avramov, Cheng & Metzker (2023) Management Science; Jiang, Kelly & Xiu (2023) JF; Kelly, Malamud & Zhou (2024) JF; Nagel, NBER w34104; Busse & Green (2002) JFE; Chordia, Green & Kottimukkalur (2018) RFS.

**Prediction markets, betting, crypto.** Bürgi, Deng & Whelan (2025) CEPR DP20631, "Makers and Takers"; Le, arXiv 2602.19520; Saguillo et al., arXiv 2508.03474; Sirolly, Kanoria, Ma & Sethi (2025) SSRN; Akey et al., CEPR DP21615; Clinton & Huang (2024); Hegarty & Whelan, CEPR DP17949; Kaunitz, Zhong & Kreiner, arXiv 1710.02824; Makarov & Schoar (2020) JFE; He, Manela, Ross & von Wachter, arXiv 2212.06888; Liu & Tsyvinski (2021) RFS; Liu, Tsyvinski & Wu (2022) JF; Schmeling, Schrimpf & Todorov, BIS WP 1087; BIS Bulletin 69 (2023); Kalshi published fee schedule (taker 0.07, maker 0.0175 coefficients).

**Rules and costs.** FINRA Regulatory Notice 26-10 (pattern-day-trader rule replaced, effective June 4 2026); SEC T+1 settlement (May 28 2024); 26 USC §1091 (wash sales) and §1211 (loss limits).
