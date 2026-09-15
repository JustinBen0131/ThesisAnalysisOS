# The residual control law

Reuse what remains valid. Spend computation where it can improve what the
system can reliably decide or accomplish. Choose among allowed actions by
their expected long-run value to the human, net of every resource they
consume. Preserve bounded exploration, because the current value model may
not know the stepping stones to a better future.

The safety floor is law. The operating policy is empirical. The estimator may
be wrong. A task ends at a verified closure state, not when an agent runs out
of things to say. The asset is never the artifact itself; it is the
improvement in future achievable work that a valid artifact enables.

## For the agent, in five lines

- Hard stops and the human's explicit choices bound what you may do. Inside
  that, follow the `control:` line `taos start` prints. It is the default
  allocation, not authority to override the human.
- Do not redo work whose validity conditions still hold: verified evidence,
  passing gates, a valid artifact. Spend new computation on the residual
  work the goal still needs, whether that is reasoning, search, a proof, a
  tool, a verifier, or gathering a fact.
- `probe` means a bounded experiment is wanted; `exploit` means use what
  has worked. Neither is permission to spend past the human's limits.
- You cannot change the host's model or reasoning setting; the human can.
  Their choice is an observation, never something to argue with.
- Every task you close is an observation the next one learns from. Close it
  at its stated `done_when`, with the evidence named, or not at all.

## The problem being solved

Over the human's whole workload, choose the policy that maximises
accomplishment they value minus the resources it costs:

```
pi* = argmax over feasible policies of  E[ U_G(trajectory) - lambda^T C(trajectory) ]
V(z) = max over allowed a of  E[ u(z, a, o) - resource_cost(z, a, o) + V(z') ]
```

- `U_G` is user-valued accomplishment; `C` is the vector of resources:
  inference, context, tools, verification, retries, repair, human attention,
  quota pressure, and the controller's own overhead.
- The feasible set is fixed by hard stops, user intent, permissions, claims,
  and provenance. The controller chooses within it and can never enlarge it.
- The successor state `z'` includes not just task progress but durable
  changes in what TAOS can afterwards believe (epistemic capability: a
  verified fact, an accepted decision, a calibrated parameter) and do
  (computational capability: a test, a verifier, a script, a proof, an
  atom, a reusable decomposition). Reusable work products create value by
  improving `V(z')`, not by existing.

## What is implemented today (the lowest coherent order)

Continuation value is not yet estimated, so the implemented scalar per
episode is one step, with no separate reuse term (adding one would double
count the day `V(z')` is modelled):

```
J = progress(terminal) - cost(wall, gate failures, corrections, decisions, handoffs, blockers, controller overhead)
score(a) = mean_J(class, a)  or prior(a) at n=0
         + beta * sqrt(ln(1 + N_class) / (1 + N_a))        # exploration heuristic
         + compute_bias * (lightness(a) - 1) + verify_bias * strong(a)
a* = argmax score, ties broken in fixed order
```

Profiles are coarse and provider-neutral: `lean`, `balanced`, `careful`,
`frontier` (bundles of compute, reasoning, verification, context bands).
Cold start: `careful` when gates exist, else `balanced`. After
`min_evidence` comparable outcomes, `compute_bias` steps toward lighter on
a clean streak and heavier on failures, `verify_bias` rises on failures and
relaxes on success, `beta` decays with total evidence; every parameter is
clamped to a fixed range. The human's setup answers seed the priors:
exploration posture sets the initial `beta`, the compute envelope sets the
initial `compute_bias`.

The exploration bonus is a conservative heuristic standing in for value the
estimator cannot see (stepping stones, tools, representation changes). It is
not a law and novelty is never rewarded for its own sake. After a failing
window the bonus is quartered: recover on the proven route first, probe
again once the class is stable. Whether a probe
created capital is decided later by evidence: reuse, lower cost on related
work, a promoted atom.

## Observation, not experiment

Every closed task is an observed state transition. It becomes comparative
evidence only when there was defensible variation: an episode opened as a
`probe` is tagged so, and the statistics keep that count apart from the
observational ones. Observational history predicts and recommends
conservatively; it does not prove that a heavier allocation caused a better
outcome, because harder tasks may be routed heavier to begin with. Do not
describe a correlation as an improvement.

## What is measured, estimated, learned, and unknown

| Kind | Fields |
|---|---|
| Directly observed | terminal state, wall time, gate passes and failures, decisions queued, handoffs, blocker transitions, corrections in labels, evidence count, controller overhead seconds |
| Heuristically estimated | the scalar `J` weights, the priors, the exploration bonus |
| Observationally learned | per-class, per-profile mean `J`; the three biases |
| Comparative | episodes tagged `probe` (counted separately; no causal claim beyond that) |
| Unavailable, recorded as null | input, cached, output, and reasoning tokens; monetary cost; retries; artifact reuse; the model and effort the host actually used |

Every vector carries a `provenance` map naming which of these each field
is. Null is a first-class value. Nothing is estimated from billing
categories, and the human is never asked to supply a number.

## Closure contracts

`A -> B` is only meaningful when `B` is stated. Every task can carry
`done_when` (the observable closure condition) and `verification` (how it
will be established). **The human supplies intent; the agent proposes
closure.** Infer the narrowest reasonable boundary; say it in one line only
when it is not obvious ("I'll treat this as done when X, verified by Y");
ask only when two readings would change what gets built or spent. A
discovered problem becomes a child task when it has its own independently
verifiable closure; otherwise it is a next action, evidence, a blocker, or a
comment.

## Artifacts as validity contracts

A reusable work product recorded as evidence can carry a small contract:
known dependencies, whether they are known at all, validity, and who
produced it. `taos task invalidate` marks it invalid when a known dependency
changes. Unknown dependencies stay unknown; an empty list means "none
declared", never "none". Reuse established consequences while their known
conditions hold; reconsider them when those conditions change.

## What is fixed and what adapts

Never on any gradient: hard stops, secret boundaries, human authority and
explicit intent, permissions, provenance, the evidence requirement for
closure, claim ownership, destructive-operation protection.

Adapts within bounds: the three parameters, and through them the recommended
verification, compute, exploration, decomposition, and handoff hints.

## Evidence and replay

`control_open` and `control_close` rows in the event log are canonical.
`.taos/projections/control.json` is derived and rebuilt from them on every
close and by `taos control rebuild`; the same history and config produce the
same state. `taos control explain <ID>` answers "why this envelope" from
recorded observations. `taos control frontier` shows nondominated
allocations on (progress, cost). The doctor checks that stored state agrees
with replay, parameters are within bounds, and malformed episodes are
ignored. Nothing runs in the background; `pause` suppresses the line and
leaves the safety floor untouched; control telemetry never enters a linked
workspace.

## Relation to self-iteration

Semantic lessons become atoms through proposals. Quantitative operating
choices are calibrated here. Structural changes remain proposals. Tuning is
not a route around any of them.
