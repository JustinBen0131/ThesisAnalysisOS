# Science

How the system is changed and checked. The reasons are in `docs/METHOD.md`.

1. **Register before you change.** A change to how the system works gets a
   `taos change register` record first: the cost it targets with a unit and a
   baseline, a predicted range, a control that must not move, a canary and a
   rollback. Seal it before building.
2. **Do not grade your own change.** Scoring is done by the other agent or the
   human. Report the verdict as it is: `CONFIRMED`, `REFUTED` or
   `CONTROL_MOVED`.
3. **Replay a control before installing it.** Any new limit, brake or guard
   that acts on every lane is run through `taos replay` on recorded history.
   Report both numbers: harmful cases caught, and ordinary work stopped.
4. **Run the lessons.** Before a reply to an outside reader, a stated cause, a
   submission, a deletion or an install, run `taos lesson at <moment>` and
   read what it prints. A lesson does not block; ignoring one is a decision
   you own.
5. **Save instructions as their original words.** Use `taos rule add` with the
   date, the scope and the expiry. Before acting on an instruction, ask
   `taos rule governing <scope>`. Never act on a summary of a rule.
6. **Two anchors before an adjustment.** Do not change a treatment, or call an
   anomaly resolved, because a number moved to a pleasing value. Record what
   the reference method does, what a control reads and a prediction, with
   `taos anchor`.
7. **Qualify the reader.** A decision-bank run counts only if the reader passed
   its controls and the pass lines were sealed first.
8. **Small samples are counts.** Write "3 of 26", not a percentage.
