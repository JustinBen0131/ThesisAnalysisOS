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
| Notes alone do not hold | A correction is printed at the moment it applies. Showing it is logged as an exposure. Whether the mistake was made again is recorded separately, and only that counts as a repeat | `taos lesson at <moment>`, `taos lesson outcome`, `taos lesson repeats` |
| Is the system still faithful? | Past decisions are replayed under three arms; a reader counts only after passing controls; pass lines are sealed first | `taos bank` |
| Predictions from rules are unreliable | A change is registered with a predicted range and a control, sealed by hash, and graded by someone who did not build it | `taos change` |
| Controls set in a scare cost more than they save | A proposed limit is replayed on history first: harmful cases caught against ordinary work stopped | `taos replay` |
| A pleasing number is not evidence | An adjustment needs what the reference method does, what a control reads, and a prediction, before it can be called resolved | `taos anchor` |

## Rules of the method

- **Prediction before change.** If you cannot say what a change will move, by
  how much and in what unit, you are not ready to make it.
- **A control that must not move.** A change that improves its target and
  shifts its control is recorded as `CONTROL_MOVED`, not as a success.
- **The builder does not grade.** `taos change score` refuses the builder, and
  refuses a number that has neither receipts nor a named measurement behind it.
- **Seals are checked.** A record edited after sealing cannot be scored.
- **Refuted predictions stay.** `taos change list` prints how many predictions
  were confirmed and how many were refuted. That line is the method's own
  score.
- **Lessons report; they do not block.** A lesson informs a decision. Whether
  it works is read from judged outcomes, never from how often it was shown.
- **Qualify the instrument first.** A reader that fails known-answer controls
  produces no result, however good its numbers look.
- **Keep the original words.** Summaries are for orientation. Decisions are
  made from the dated passage.

## One error, one answer

In November 2026 three outside reviews of the previous release reported some
twenty defects between them. Read together they are one defect. In every
case a record was true under conditions, and was later read without them.

| The record | What it was true under | How it was read | What happens now |
|---|---|---|---|
| An instruction | a date range and a scope | as in force everywhere, from then on | `taos rule governing <scope> --on <date>` answers for that day and that scope; a replacement governs from its own date, inside its own scope, until it lapses |
| A passed check | the bytes it tested | as a pass for the task, whatever was edited later | the result is filed under the check and a fingerprint of what it read |
| "Done" | a check that holds | reachable by a second route that skipped the check | one place changes a task's state, and it asks |
| A reminder shown | the fact that it was shown | as a mistake made again | showing is an exposure; a repeat needs a judged outcome |
| A recommended setup | the fact that it was recommended | as the setup that ran | credit goes only to what was observed to run |
| A lease on the work | a promise renewed in time | as still held after it lapsed | a lapsed lease is over; the holder asks again |
| A label in a history | a stated value | the text "false" as true, a missing label as harmless | read strictly; unlabelled rows are counted apart |
| A confirmed prediction | a measured number | a number with no source | a score needs receipts or a named measurement |
| A prediction | being made before the result | rewritten afterwards | written once |

So the system has one primitive instead of nine repairs. A statement is
stored with who made it and what it stood on. Asked later, it answers
`holds`, `fails`, `stale` or `unknown`, with the reason
(`taos_core/basis.py`). `taos why <task>` reads back every record a task
rests on: its checks, the instructions it was closed under, its work products
and their inputs, a person's acceptance, the lease on it.

Three checks stand behind this, each one command:

- **The cases.** `tests/test_counterexamples.py` holds 17 cases, written
  against entry points the previous release already had. At commit `071a348`
  all 17 fail. Here all 17 pass. `python3 evals/at_revision.py 071a348`
- **The tests themselves.** `evals/mutations.py` removes 16 protections from
  a copy of the code, one at a time, and runs the tests. The first run caught
  15. The miss was real: nothing tested that a lapsed lease cannot be revived
  by its own heartbeat when nobody else has taken the work. That test was
  added and the run is now 16 of 16. The miss stays in this record.
- **The mechanism under load.** The reuse experiment, below.

## Where the idea comes from

None of this is new as an idea, and it is better for that.

- A truth maintenance system keeps each belief with its justification and
  withdraws the belief when the justification goes (Doyle, "A truth
  maintenance system", *Artificial Intelligence* 12(3), 1979; de Kleer, "An
  assumption-based TMS", *Artificial Intelligence* 28(2), 1986).
- A build system keeps each result with a trace of the inputs it was built
  from and rebuilds only what a change reached (Mokhov, Mitchell and Peyton
  Jones, "Build systems à la carte", *Proc. ACM Program. Lang.* 2(ICFP),
  2018, which names the verifying trace used here).
- A temporal database separates the time a fact was true from the time it was
  recorded (Snodgrass and Ahn, "A taxonomy of time in databases", SIGMOD
  1985). `taos rule governing --on` asks the first question and `--known-by`
  the second.
- The W3C provenance model records what was derived from what, and by whom
  (PROV-DM, W3C Recommendation, 2013).

What a build system does not model is what research also rests on: an
instruction a person gave on a date, in words, for a scope and sometimes for
a week; and a person's acceptance of one exact version of a result. TAOS
treats those as part of the basis, with the same four answers.

## The reuse experiment

Reusing a verified result is only worth having if it is never wrong and it
saves work. `evals/reuse_frontier.py` tests both on TAOS itself. It edits
real files, lets `taos gate run` decide what to execute, and counts real
executions from a log outside the workspace. Whether a reuse was wrong is
judged from that log and from which file was edited, never from TAOS's own
bookkeeping.

The workload: 12 folders, 6 checks that each read 2 neighbouring folders, 60
single-file edits chosen by a seeded generator. After every edit all 6
results are relied on, 360 in total. The same 12 folders are declared to TAOS
at six levels of detail, from one domain holding everything to one domain per
folder.

Six predictions were written into the script before its first run, and it
exits 1 if one fails. All six held.

| Policy | Executions | Stale results relied on |
|---|---|---|
| Rerun everything | 360 | 0 |
| Rerun when older than 2, 4, 8 consultations | 180, 90, 48 | 30, 83, 161 |
| TAOS, 1 domain declared (nothing said about what a check reads) | 360 | 0 |
| TAOS, 2, 3, 4 domains | 180, 120, 120 | 0 |
| TAOS, 6 or 12 domains | 60 | 0 |
| An oracle that knows what every check reads | 60 | 0 |
| TAOS, three tasks asking the same questions | 60 | 0 |
| TAOS, every check hiding one folder it reads | 29 | 150 |

What the table says:

- **An age limit trades one error for the other.** Every window either
  reruns work nothing touched or relies on work something did. The previous
  release used one ("passed in the last 24 hours").
- **A basis does not make that trade.** With what each check reads declared,
  executions equal the oracle's and no stale result is relied on. With
  nothing declared it reruns everything: slower, never wrong.
- **The declaration is the limit.** A check that reads more than it declares
  is reused wrongly, 150 times in 360 here. TAOS reports a change to a file
  nobody declared as `unknown`. It cannot see an input a check has hidden
  inside a domain it did not name.

### What it costs, and the connection to transport networks

Two of the author's papers study branched transport networks with a two-term
ledger on every edge: a transport loss that falls as the conduit is enlarged
and an upkeep cost that rises with it. Minimising the sum fixes how the two
costs split, and makes the cost of carrying a flow concave in the flow, which
favours merging flows into shared conduits (Bennett, "Murray's Law as an
Entropy-per-Information-Cost Extremum", arXiv:2511.04022, 2025; "A
Single-Index Theory of Optimal Branching", arXiv:2511.19915, 2025).

A recorded result has the same two terms. Keeping it costs upkeep: each time
it is consulted, what it stood on is read and fingerprinted again. Having it
saves transport: the check is not executed. The experiment measures both
terms and tests three consequences of that ledger.

1. **Structure lowers transport until it matches what is really read. After
   that it is only upkeep.** Going from 1 declared domain to 6 cut executions
   from 360 to 60. Going from 6 to 12 doubled what has to be declared and
   maintained and saved nothing.
2. **Shared flows merge.** Three tasks that need the same check on the same
   files cost 60 executions, not 180. A result belongs to the bytes it
   tested, not to the task that asked.
3. **A record pays when its upkeep is less than the transport it spares.**
   If asking costs `h`, one execution costs `g`, and a consultation spares
   `s` executions, reuse wins when `h < s * g`. On one laptop a toy check
   cost 5.7 ms and each consultation spared 5 of them. Asking cost 15.5 ms
   for 48 files, 36.9 ms for 480 and 255.6 ms for 4,800. So for these toy
   checks reuse won on the small tree and lost on the large one, where
   asking cost more than running all six again. The break-even check cost
   was 3.1 ms, 7.4 ms and 51 ms. A real test suite takes seconds to
   minutes, so the ledger favours the record by orders of magnitude; the
   point is that the ledger can say no.

What does not transfer is the exponents. The papers derive power laws from
the physics of flow in a pipe. Nothing here shows that agent work obeys such
laws, and this experiment does not test it. What transfers is the ledger and
the question it asks of any structure: does it pay for its upkeep with the
transport it saves? Here that question has a measured answer, in both
directions. The numbers of one run are in `evals/results/reuse_frontier.json`.

The upkeep term has a known weakness. Every consultation reads every file, so
asking grows with the size of the tree, about 0.05 ms per file here. A cache
keyed on file size and modification time would cut it. That is not built.

## What should outlast the models

Agents will get better at judgment. The first measurement above already
found judgment was not the bottleneck. Three things do not improve with the
model, because they are not about how well it thinks. They are about what it
is given.

1. **Validity is the basis, not the age.** No model can tell that a result
   went stale from the result alone. Someone has to keep what it stood on.
2. **The original words outrank any summary of them.** A better summariser
   still drops the expiry date some of the time. Keeping the passage and its
   hash does not depend on the summariser.
3. **An observation has a kind and a source.** A log line that says a lesson
   was shown is not evidence that it was broken, however capable the reader.

## What this does not claim

It does not claim that these mechanisms make agents correct, or that research
done with them comes out better. The evidence above is mechanical: the code
does what it says, on synthetic cases and on one small workload. It claims that
they make an agent system *measurable*, so you can tell when a change helped,
when a lesson failed to hold and when an instruction has quietly outlived its
terms. Nothing here calls a model or a network. The bank writes prompts and
scores answers; who or what answers is up to you.
