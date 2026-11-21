# The method: running agents the way you run an experiment

The first version of this system answered one question: how do two coding
agents share one body of work without colliding or losing it? Tasks, claims,
handoffs and gates are that answer.

The science layer answers the next question: **how do you know the system is
getting better, and that the agents are still doing what you meant?** Its
answer is the one an experimental scientist would give. State the prediction
before the change. Name a control that must not move. Let someone other than
the builder grade it. Keep the result when it goes against you.

It came from one research program: a physics measurement run day to day by
two agents under one person's direction, on shared computing, with deadlines
and outside review. Every mechanism here exists because something failed
there first.

## What was measured

In late 2026 the system was studied with its own history as the test set: the
person's dated instructions and corrections, replayed as decisions with known
answers. Hypotheses were written with their falsifiers before any result. The
samples are small. They are counts, not rates, and they describe one person's
system.

1. **Judgment was not the bottleneck.** Given the governing instruction as its
   dated original text, frontier models chose the right action in every case
   tested (16 of 16, 12 of 12 and 48 of 48 across three designs).
2. **Delivery was.** On 26 real requests, ordinary search put the right file
   in front of the reader 8 times and the exact governing passage 3 times.
   Naming the file recovered no further passage.
3. **Saving a lesson strips its limits.** A rule approved for one week lost
   its time limit within seconds of being saved, in a derived excerpt, and was
   then applied outside its window. Readers of extracted fields missed an
   expiry that readers of the dated quotation caught (44 of 48 against 48 of
   48).
4. **Notes alone do not hold.** Of 55 corrections in three days, 20 repeated a
   lesson that was already written down.
5. **A critic trained on simulated mistakes did not transfer.** Validated like
   any classifier (known-truth simulation, independent samples, then real
   data), it caught 0 of 7 later real corrections at its calibrated cut. It
   was dropped.
6. **Predicting a change from its rule alone was unreliable.** Checked against
   recorded history under a plan fixed in advance, such predictions held about
   1 time in 3.

One result is left out of this list on purpose. Supplying the passage raised
right actions from 13 to 20 of 26, with 7 gains and no losses. The pairings in
that test were nominated by the author, the instrument meant to qualify them
independently failed its own controls, and the answers came from one small
local model. It is a ceiling, not an effect size.

## What each finding became

| Finding | Mechanism | Command |
|---|---|---|
| Delivery fails at the passage | Rules are stored as dated quotations with scope, expiry and supersession, and a decision asks for the passages in force | `taos rule governing <scope>` |
| Saving strips limits | A derived note carries its original's hash; an audit finds notes whose original lapsed, changed or was replaced | `taos rule derive`, `taos rule audit` |
| Notes alone do not hold | A correction is printed at the moment it applies, and every match is logged so repeats can be counted | `taos lesson at <moment>`, `taos lesson repeats` |
| Is the system still faithful? | Past decisions are replayed under three arms; a reader counts only after passing controls; pass lines are sealed first | `taos bank` |
| Predictions from rules are unreliable | A change is registered with a predicted range and a control, sealed by hash, and graded by someone who did not build it | `taos change` |
| Controls set in a scare cost more than they save | A proposed limit is replayed on history first: harmful cases caught against ordinary work stopped | `taos replay` |
| A pleasing number is not evidence | An adjustment needs what the reference method does, what a control reads, and a prediction, before it can be called resolved | `taos anchor` |

## Rules of the method

- **Prediction before change.** If you cannot say what a change will move, by
  how much and in what unit, you are not ready to make it.
- **A control that must not move.** A change that improves its target and
  shifts its control is recorded as `CONTROL_MOVED`, not as a success.
- **The builder does not grade.** `taos change score` refuses the builder.
- **Seals are checked.** A record edited after sealing cannot be scored.
- **Refuted predictions stay.** `taos change list` prints how many predictions
  were confirmed and how many were refuted. That line is the method's own
  score.
- **Lessons report; they do not block.** A lesson informs a decision. Whether
  it works is read from its repeats.
- **Qualify the instrument first.** A reader that fails known-answer controls
  produces no result, however good its numbers look.
- **Keep the original words.** Summaries are for orientation. Decisions are
  made from the dated passage.

## What this does not claim

It does not claim that these mechanisms make agents correct. It claims that
they make an agent system *measurable*, so you can tell when a change helped,
when a lesson failed to hold and when an instruction has quietly outlived its
terms. Nothing here calls a model or a network. The bank writes prompts and
scores answers; who or what answers is up to you.
