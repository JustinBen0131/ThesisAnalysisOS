# The panel

One page, served on the loopback interface only, on when the human wants it.

## Laws it obeys

1. Every element maps to a row in `.taos/`. Nothing is computed by a model.
2. Stale is shown as stale. A card older than three days carries a badge; the
   panel never interpolates or hides age.
3. At most two decisions on Today. The rest wait in Decisions.
4. Fixed geography: tabs in the same order, columns in the same order, cards
   do not move under the pointer. New cards fade in over 150 ms; nothing else
   animates.
5. Two clicks to truth: every card links to its raw JSON.
6. No points, streaks, badges, levels, or scores of people or agents.

## Security

- Binds `127.0.0.1` only.
- Writes require a per-launch token injected into the page and an
  `Origin` from localhost. No other endpoints exist; unknown paths 404.
- The handoff viewer refuses any path outside `.taos/handoffs/`.
- Actor on every write is `human`.

## Off

`taos panel off` sends SIGTERM to the recorded pid and removes the pidfile.
Nothing else runs in the background, ever.
