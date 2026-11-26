# quantAnalysisOS: the contract for an agent working here

You are doing market research with fake money. This file is the contract. It is
short on purpose. `policies/OBJECTIVE.md` says what the work is for;
`policies/METHOD.md` says what counts as evidence.

## Hard stops

Absolute. Full text in `policies/HARD_STOPS.md`.

- Never place, route, or prepare a real order. Never connect to a broker, an
  exchange, or a wallet. Nothing in this repository can, and nothing you add may.
- Never read, print, store, or ask for an API key, a password, or account
  credentials. A data source that needs a key goes through the environment's
  own credential mechanism, where you never see the value.
- Never spend money. Paid data, paid compute, subscriptions: recommend with
  evidence, and the human decides.
- Moving any strategy from paper to real money is the human's act, outside this
  repository. You may write the case for it. You do not make it.
- Never edit anything under `book/` by hand. `./qaos` is the only writer.
- Never call an edge real, proven, safe, or ready. Quote the verdict of a named
  study, with its Z and its trial count, or say `unknown`.

## The rules of evidence

1. **Every look at real data is a trial.** A backtest on real data happens
   inside a registered study (`./qaos study register`) and nowhere else.
   Exploring in a notebook and then registering the winner is the exact failure
   this system exists to prevent.
2. **Develop on the development window. The holdout is sealed.** `scan` cuts
   the holdout off before a strategy sees the data. Do not load the holdout
   rows yourself, plot them, or summarise them.
3. **The box opens once.** `./qaos study unblind ID --by NAME` after `freeze`,
   signed. The verdict is what the registered rule says. A disappointing result
   is a result. Do not re-register the same idea with a moved split.
4. **Toys before data.** A new method, statistic, or strategy family is run on
   toy markets first, where the truth is known: once with nothing in them
   (how often does it cry wolf?) and once with a signal injected (does it find
   it?). `./qaos toys` holds the standing studies.
5. **A number has an error or it is not a number.** Statistical error always;
   systematics (`./qaos study systematics`) before anything is promoted.
6. **Say what you already knew.** `prior_exposure` in a registration records
   what the researcher had seen of this idea and this data. For an AI agent
   that includes everything in its training data: a famous anomaly on famous
   data is never blind to you. Only the future is.
7. **Small samples are counts.** "13 of 400", not "3.2%".

## First reflex

```bash
./qaos status          # studies and their standing, paper accounts, toys on record
./qaos doctor          # every ledger and seal, and the engine's calibration
```

Then place the request:

- A new idea about markets: write the registration first. If you cannot state
  the hypothesis, the grid, and the test before looking, you are not ready to look.
- A change to `qaos_core/engine.py`, `strategies.py` or `stats.py`: every
  recorded result becomes `stale`. Run `./qaos selftest`, then re-run what the
  change touched. A new protection gets a test that fails without it.
- The paper account: `./qaos paper step NAME` after new data arrives. One step
  per market date, never backfilled silently.

## Where things live

| What | Where |
|---|---|
| Studies: registration, trial log, freeze, result | `book/studies/ID/` |
| Paper accounts: ledger and mandate | `book/paper/NAME/` |
| Toy studies on record | `book/toys/` |
| Dataset manifests (fingerprint, provenance) | `data/*.json` (the numbers themselves are not committed) |
| Findings written for a person | `research/` |
| The rules | `policies/` |
| Why a physicist would do it this way | `docs/PHYSICS_TO_MARKETS.md` |

## Commands

```bash
./qaos demo                                  # the idea, working, in a throwaway folder
./qaos selftest                              # the tests
./qaos need --sharpe 0.5                     # how much data a Sharpe ratio needs
./qaos toys all --write                      # the standing toy studies
./qaos data pull french                      # a reproducible dataset (pinned release, hashed)
./qaos data fetch etf --symbols SPY,IEF,GLD  # daily vendor data, where the network allows it
./qaos data qa NAME                          # the golden-period list
./qaos study register SPEC.json              # seal the hypothesis, the grid, the test
./qaos study scan ID                         # development window only
./qaos study freeze ID                       # fix the configuration, account for the search
./qaos study unblind ID --by NAME            # once
./qaos study systematics ID --window holdout
./qaos study why ID                          # holds, stale, fails or unknown
./qaos paper open main --cash 10000          # fake money
./qaos paper mandate main --data etf --strategy ... --stage commissioning
./qaos paper step main                       # one step per new market date
```
