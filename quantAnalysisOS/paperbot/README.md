# paperbot

Runs the pre-registered paper strategies of `registration.json` (QAOS-PAPER-1) unattended.
Paper only: there is no broker client and no credential handling in this package.

```bash
cd quantAnalysisOS
python3 -m paperbot run                  # one cycle: fills, $100/week contributions, settlements, new paper orders
python3 -m paperbot status
python3 -m paperbot verify               # ledger hash chain + registration unchanged
python3 -m paperbot halt --by NAME --reason "..."    # kill switch: no new orders or rebalances
python3 -m paperbot resume --by NAME --reason "..."
python3 -B -m unittest paperbot.tests.test_paperbot  # 17 tests, offline
```

Tracks:

- **core**: S&P 500 exposure min(1, 0.16^2 / 21-day realized variance) against always-100%, both fed
  $100 a week, 5 bp per side, fills at the next close. Prices: FRED series SP500 (price only, about a
  day late). E-value = NAV per unit ratio.
- **kalshi**: 10-contract paper maker bids one cent above the favorite side's bid (ask 80-95 cents,
  spread at most 5 cents, 1-7 days to close, one order per event, no parlay combos), filled only when
  a trade prints strictly through the price within the order's 24-hour life, maker fee rounded up.
  E-value = product over settlement batches of mean(1 + 0.5 (Y/q_eff - 1)).

Pass mark: e-value 20 (Ville's inequality, alpha 0.05), checkable at any time.

Environment: the Claude cloud environment `quantAnalysisOS` (repository ThesisAnalysisOS only, no
sPHENIX) allows `api.elections.kalshi.com`, `fred.stlouisfed.org`, `mba.tuck.dartmouth.edu` and
`stooq.com`. The GitHub Actions workflow `paperbot.yml` runs the same cycle daily and commits the
book to the `paperbot-book` branch once it is on the default branch.

Changing any rule in `registration.json` changes its hash, and `run` refuses to continue an existing
book: a changed rule is a new registration and a new book.
