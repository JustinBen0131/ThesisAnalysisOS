# The ladder

A claim climbs one rung at a time. Each rung has a bar that was fixed before
the claim arrived, and each spends something that cannot be had back.

| Rung | Name | The bar to stand here | What it spends |
|---|---|---|---|
| 0 | idea | A hypothesis you can state in a sentence, and what would count against it. | Nothing. |
| 1 | toy | The strategy passes the causality gate. The procedure that will judge it cries wolf at or below its nominal rate on toys with nothing in them, and finds an injected signal. | Compute. |
| 2 | registered | A sealed registration: data and its fingerprint, the split, every configuration that may be tried, the test, the bar, the costs, and what the researcher already knew. | Nothing yet. |
| 3 | frozen | The grid was scanned on the development window only. One configuration is fixed. The search is accounted for: trial count, deflated Sharpe ratio, mixed-event global p. The freeze says how many sigma the holdout could show even if the development estimate were exactly right. | The development data. |
| 4 | confirmed | The holdout, opened once, clears the registered bar (2 sigma or higher on the registered test) and stays positive at twice the costs. Systematics are quoted. | The holdout, forever. |
| 5 | paper | A `promoted` mandate naming the study. Fake money, real dates, one step per market day. To stay: the realised path within 2 sigma of what the study predicts. | Time. |
| 6 | real | **The human's decision, outside this repository.** Evidence an agent can assemble: the combined significance after every trial is counted, at least a year of paper record consistent with the study, and the worst drawdown the toys say to expect at that Sharpe ratio. | Real money. |

## Rules of the climb

- **No skipping.** Nothing reaches paper without a study, except a
  `commissioning` mandate: a plain baseline run to test the machinery, which
  claims nothing and is labelled so in the ledger.
- **2 sigma is evidence, not discovery.** It is the bar for spending time on
  paper. With N studies run, about N/44 will clear 2 sigma on nothing at all.
  The bar for the last rung is higher because the count of studies is part of
  the look-elsewhere effect too. `./qaos status` shows the count.
- **A holdout that cannot decide should not be opened.** If the freeze says the
  holdout would show under 1 sigma even with the development Sharpe taken as
  truth, the study cannot confirm anything. Get more history or more breadth
  first; the data is still unspent.
- **Not confirmed is a rung too.** The study stays in the book and is counted.
  The same idea may be registered again only on data the first study did not
  touch, and the new registration says what the first one found.

## Coming down

- A study whose data or code changed reads `stale`. Nothing relies on it until
  it is re-run.
- A paper account whose realised return is more than 2 sigma below its study's
  prediction is evidence against the study. Record it, and move the mandate
  back to a baseline.
- The drawdown brake moves an account to cash at the configured loss from its
  high-water mark. Only a human releases it, and the release is signed.
- A strategy at rung 6 is the human's to stop at any time, for any reason.
