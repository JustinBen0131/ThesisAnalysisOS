# The objective

Everything else in `policies/` is a constraint. This is what the work is for.

## The function

Grow the principal's real wealth slowly and survivably, by finding the few
market claims that are true after costs, and by not acting on the many that
are not. Until a claim has earned it, the money is fake.

Every term matters.

- **Slowly.** The target is a trickle: something above the risk-free rate,
  repeatable, with drawdowns the principal can sit through. A strategy that
  needs to be right this month is the wrong shape for this system.
- **Survivably.** Not losing is worth more than winning. A 50% loss needs a
  100% gain. Leverage is off by default, the drawdown brake is on by default,
  and both are the human's to change.
- **True after costs.** A claim is a number with an error, tested once on data
  it was not built on, with every other thing that was tried counted against
  it. Before costs it is not a claim about money.
- **Not acting on the many.** Most backtested edges are the best of a search
  through noise. The system's main output, most weeks, should be a recorded
  "not confirmed". That is the product working, and each one is counted.
- **Fake until earned.** Paper trading costs nothing but time, and time is the
  one thing the evidence cannot be had without (see `./qaos need`).

## What it implies

1. **The risk-free rate is the null hypothesis.** Cash already trickles. Every
   strategy is measured in excess of it, and a strategy that cannot beat it
   after costs is a way of taking risk for free.
2. **Premium first, skill second.** Holding a diversified set of risky assets
   has paid for a century and needs no forecast. Timing them is a claim of
   skill and needs the higher bar. Keep the two apart: the `alpha` and `timing`
   tests exist because the `sharpe` test cannot tell them apart.
3. **Breadth beats cleverness.** Significance grows like the square root of
   independent bets. One clever rule on one asset cannot be confirmed in a
   working lifetime at a realistic Sharpe ratio. Many small, unrelated, boring
   ones can.
4. **Spend the holdout like money.** Data you have not tuned on is the scarce
   resource. Every unblinding spends some forever. Register carefully, grid
   narrowly, open once.
5. **Compound the method, not just the account.** A check that caught an error
   becomes a gate or a test. A result that surprised becomes a toy study that
   says how surprised to be.
6. **Get smaller.** A strategy that stops earning its place is retired. So is a
   rule in this folder.

## How to know it is working

Studies are registered before they are run. The trial count goes up faster
than the count of confirmations. The paper account's realised path sits inside
the band its backtest predicted. `./qaos doctor` says `nothing fails.` The
principal can read any number in `research/` and find the study it came from.

## How to know it is not

A result is quoted without a study id. A holdout was looked at "just to
check". A study was re-registered until it confirmed. The paper account holds
something no study promoted and nobody labelled as commissioning. A backtest
is described as a track record. If any of these is true, stop and repair the
record before doing anything else.
