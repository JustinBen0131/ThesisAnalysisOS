# Claims

Every claim this repository makes about itself, with the code that
implements it, the test that checks it, and its status. A claim with no row
here should not appear anywhere else.

This file is checked. `python3 evals/claims.py` reads every row back against
the repository as it is: a row that names code or a test that is not there,
or a number the recorded run does not contain, `fails`; a number measured on
code that has changed since is `stale`. CI runs it with `--strict`.

Status words: **tested** means a test in `tests/` fails if the claim stops
being true. **measured** means a number from one recorded run, kept in
`evals/results/` with the bytes of the code it was measured on, and the
command that reproduces it. **reported** means a result from the private
system this was generalized from; the data is not in this repository and you
cannot rerun it. **not claimed** is listed so nobody has to guess.

(Leases on work are also called claims here. Those are in
`policies/CLAIMS.md`.)

## What a record stood on

| Claim | Code | Check | Status |
|---|---|---|---|
| A recorded result is answered `holds`, `fails`, `stale` or `unknown`, with a reason; `unknown` is never turned into another answer | `taos_core/basis.py` | `tests/test_standing.py` | tested |
| A passed check holds for the bytes it tested and stops holding when one changes, however recent it is | `gates.standing` | `test_a_pass_does_not_cover_a_file_edited_afterwards` | tested |
| The answer names the file that changed | `basis.compare` | `test_closed_work_stands_until_a_file_changes_and_the_reason_names_the_file` | tested |
| No route moves a task to review or done unless every check holds, or a waiver with a reason is recorded and shown | `TaskStore.transition` | `test_done_cannot_be_reached_by_a_route_that_skips_the_check`, `test_a_waived_closure_is_unverified_until_the_check_runs` | tested |
| A result is shared by every task whose files are the same bytes, and is executed once | `gates._key`, `.taos/gate_results.json` | `tests/test_standing.py::TestSharedResult` | tested |
| A change to a file no domain claims is `unknown`; a check naming an undeclared domain is `unknown` | `basis.compare`, `gates.standing` | `tests/test_standing.py::TestDomains` | tested |
| A declared domain holds what its patterns match on disk, so an input git ignores is part of what a check stood on | `basis.on_disk`, `basis.snapshot` | `test_an_input_git_ignores_is_still_part_of_what_a_check_stood_on` | tested |
| A check marked isolated can read only the files its result is filed under, and what it writes is discarded | `gates._isolated` | `test_a_check_cannot_pass_on_a_file_it_did_not_declare`, `test_an_isolated_check_sees_only_what_it_declared_and_leaves_nothing_behind` | tested |
| Only a person accepts a result, and the acceptance is of one version | `TaskStore.accept` | `test_acceptance_is_of_one_version_and_does_not_carry_over` | tested |
| A work product is current while its declared inputs are the same bytes; with none declared it is `unknown` | `add_evidence`, `standing._artifacts` | `test_a_work_product_is_current_while_its_declared_inputs_are_the_same_bytes` | tested |
| A new or lapsed instruction makes work closed under the old ones `stale` | `rules.binding`, `rules.changes_since` | `test_a_new_instruction_makes_the_closure_stale_and_is_quoted` | tested |

## Instructions, lessons and the other records

| Claim | Code | Check | Status |
|---|---|---|---|
| The instruction that governed a scope on a past day is still answerable after it was replaced | `rules.governing` | `test_a_later_replacement_does_not_erase_the_earlier_answer` | tested |
| A replacement governs from its own date, inside its own scope, until it lapses | `rules.displaced_by` | the four other tests in `TestInstructionsKeepTheirTime` | tested |
| What governs a task and what was learned reach the agent at start, in the original words | `lifecycle.start`, `capsule_text` | `tests/test_standing.py::TestDelivery` | tested |
| A reminder shown is an exposure; only a judged outcome is a repeat | `lessons.at`, `lessons.outcome`, `lessons.repeats` | `test_a_reminder_shown_for_correct_work_is_not_a_repeated_mistake` | tested |
| A setup is credited only when it was observed to run | `control.rebuild` | `test_an_unobserved_profile_earns_no_credit` | tested |
| A lapsed lease is over | `ClaimStore.heartbeat`, `acquire` | `tests/test_counterexamples.py::TestALeaseEnds` | tested |
| A refused start takes nothing | `lifecycle.start` | `test_a_refused_start_takes_nothing` | tested |
| A label is read strictly and a missing one is counted apart | `replay.label` | `test_the_text_false_is_not_read_as_true`, `test_an_unlabelled_case_is_not_counted_as_harmless` | tested |
| A decision-bank run keeps the answers it scored and their hash, so the score can be recomputed | `bank.score` | the bank test in `tests/test_science.py` | tested |
| A change is not confirmed by a number with no source, and a prediction is written once | `changes.score`, `anchors.predict` | `test_a_change_is_not_confirmed_by_a_number_from_nowhere`, `test_a_prediction_cannot_be_rewritten_once_made` | tested |

## The repository's own numbers

| Claim | Code | Check | Status |
|---|---|---|---|
| A number quoted here is stale once the code it was measured on changes, and the answer names the file | `evals/measured.py` | `test_a_recorded_number_goes_stale_when_the_code_it_measured_changes` | tested |
| No row of this file names code or a test that is not there, or a number its recorded run does not contain | `evals/claims.py` | `test_no_claim_names_something_that_is_not_there_or_misquotes_a_recorded_run` | tested |
| The demo runs from a clean copy and prints each idea with real output | `taos_core/demo.py` | `test_it_runs_from_a_clean_copy_and_shows_each_idea_with_real_output` | tested |

## Measurements

| Claim | Number | Reproduce | Status |
|---|---|---|---|
| Earlier releases had the counterexample cases: every one at the first, two at the second | 19 of 19 fail at `071a348`; 2 of 19 fail at `89f36ce`; 19 of 19 pass here | `python3 evals/at_revision.py` | measured |
| The tests notice when a protection is removed. The first run, with 16 faults, caught 15; the missing test was added | 18 of 18 seeded faults caught | `python3 evals/mutations.py` | measured |
| Reuse by basis relied on no stale result and executed what an oracle would | 60 executions, 0 wrong, in 360 results relied on | `python3 evals/reuse_frontier.py` | measured, one workload |
| Age limits trade reruns against stale reuse | 180, 90, 48 executions with 30, 83, 161 wrong | same | measured, one workload |
| In the open, under-declared inputs are reused wrongly | 150 wrong in 360 when every check hid one folder | same | measured, one workload |
| Isolated, a check that reads what it did not declare never passes, and correct declarations cost no extra executions. Predicted before the code was written | 0 of 366 runs passed when every check hid one folder and ran isolated; 60 executions, 0 wrong with everything declared | same | measured, one workload |
| Asking costs time that grows with the tree | 17.8, 47.1, 326.4 ms for 48, 480, 4,800 files | same | measured, one laptop |
| The suite passes on Python 3.9 and 3.12, Linux and macOS | 148 tests | `./taos selftest`, and CI | tested |

## Reported, not reproducible here

The six findings under "What was measured" in `docs/METHOD.md` come from the
private research system this repository was generalized from. They are
counts from small samples of one person's work. The data is not public. Read
them as the reasons the mechanisms exist, not as results you can check.

## Not claimed

- That research done with this system comes out more correct. Nothing here
  measures research outcomes.
- That the cost laws of physical transport networks apply to agent work.
  `docs/METHOD.md` says what is shared with that work (a two-term ledger and
  the question it asks) and what is not (the exponents).
- That the controller in `policies/CONTROL.md` allocates effort optimally. It
  is a bounded one-step rule, and it credits only what it observed.
- That an open check's declaration of what it reads is verified. It is
  trusted, unless the check is marked isolated.
- That an isolated check is a correct check. Isolation makes its result
  depend only on the files it is filed under. It does not reach an absolute
  path, the network or the environment.
- That anything outside the workspace is seen: the network, the clock, the
  environment, another machine.
