# ThesisAnalysisOS

[![What ./taos demo prints first: the name TAOS in a box, each letter shaded as one of the four answers a result can get: holds, stale, fails or unknown.](docs/opener.svg)](#see-it-in-a-minute)

**When a dataset changes, which earlier checks still apply?** ThesisAnalysisOS (TAOS)
helps a team using AI agents answer that question. It records a check's result with
the files the check says it reads. After an edit, it compares those files with the
saved fingerprints and identifies earlier passes that need another look.

[Follow a six-swing measurement in the browser](https://whatstillholds.com/) ·
[Read the audit protocol](docs/MEASUREMENT_AUDIT.md) · [Run the demo locally](#see-it-in-a-minute)

[![A researcher and an example team of AI assistants share one project record of tasks, instructions, checks and approvals.](site/assets/social.png)](https://whatstillholds.com/)

The same project directory stores tasks, the researcher's original instructions,
check results and handoffs. A second agent can see what was checked, which inputs
were used, and whether a person accepted that version. The command-line program
uses the Python standard library and works locally without a model or network call.

This is an independent research prototype, generalized from the operating
layer of a physics thesis analysis run with two AI agents. It is not
affiliated with any employer or product.

```mermaid
flowchart LR
    P["A person<br/>instructions, acceptance"] --> R
    A["Agents<br/>work, check runs, handoffs"] --> R
    R["A record<br/>the statement, who made it,<br/>what it stood on"] --> Q{"Asked later:<br/>does it still stand?"}
    Q --> H["holds<br/>what it stood on is the same"]
    Q --> F["fails<br/>checked as things are now"]
    Q --> S["stale<br/>something changed, and it is named"]
    Q --> U["unknown<br/>cannot be established"]
```

## Audit a measurement

A fit to six pendulum swings estimated the acceleration due to gravity. We
changed one period or the calibration and inspected the saved pass (called a
*receipt*) before we ran the fit again. We compared the new fit and its
standard error with a separate calculation. An earlier pass can become stale
even when the updated fit still meets the acceptance limits.

With all inputs listed, the earlier pass became stale for all 27 edits that
changed the fitted result in 32 cases. Three more edits changed the input
files while preserving the fitted numbers. In four additional controls we
changed how the software classified the data. When no group included the
data, both edits returned `unknown`. When the fit left an existing data
group off its input list, it kept the old pass on both edits, although both
fresh checks failed. The two implementations agreed on both the estimate and its standard error within
1e−10 m/s² across all 36 cases.
The frequencies describe selected edits to one teaching dataset.

Read the [experiment and its limits](docs/MEASUREMENT_AUDIT.md) or inspect the [case-level observations](evals/results/measurement_audit.json). Reproduce the checked-in readings with the first command. The second independently reconstructs the edits and uncertainties from the raw records using exact rational sums. The third accepts your own measurements.

```bash
python3 evals/measurement_audit.py --verify
python3 evals/review_measurement_audit.py
python3 evals/measurement_audit.py --input path/to/swings.csv
```

## What the next task can reuse

Three tasks asked the same pendulum fit check over one sequence of edits. The third task saw a failure on the current readings and reran the check. Restoring the exact earlier CSV recovered the original pass. Writing the same reading with different decimal spelling required a new pass.

[Handoff method and results](docs/HANDOFF_AUDIT.md) · [Raw observations](evals/results/handoff_audit.json). Reproduce with `python3 evals/handoff_audit.py --verify`.

## Can two corrections conceal a failure?

After two fictional instrument scores were corrected, the classifier still detected six of eight known faults overall. Instrument A fell from three of four to two of four and failed its check. Instrument B rose to four of four. Both corrections changed files used by the pooled check. It ran again and gave the same answer.

[Four controlled edits](docs/MODEL_EVALUATION.md) · [Original readings and predictions](examples/model_evaluation/) · [Saved observations](evals/results/model_evaluation.json). Run the experiment with `python3 evals/model_evaluation.py --verify` or reconstruct the counts without running the model with `python3 evals/review_model_evaluation.py --self-test`.

## See it in a minute

```bash
git clone https://github.com/JustinBen0131/ThesisAnalysisOS.git
cd ThesisAnalysisOS
./taos demo
```

The demo builds a temporary project, fits the acceleration due to gravity
(`g`) from six pendulum swings, and asks the record about that result as the
files and instructions around it change. This is everything it prints.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  ╺┳╸ ┏━┓ ┏━┓ ┏━╸   ThesisAnalysisOS 1.1.0                whatstillholds.com  │
│   ┃  ┣━┫ ┃ ┃ ┗━┓   Every result is kept with what it stood on.               │
│   ╹  ╹ ╹ ┗━┛ ╺━┛   Ask it later: holds, stale, fails or unknown, and why.    │
└──────────────────────────────────────────────────────────────────────────────┘
Here: six pendulum swings, a fit for g, and a check that the fit is sane.

1  A result holds until what it stood on changes
   holds   the fit passes its check and the task closes: g = 9.82 +/- 0.02
   holds   the plot style is edited, which the check never read
   stale   one swing is measured again: data/swings.csv changed

2  A pass belongs to the files, not to the task
   ok      the check runs again on the new swing: g = 9.75 +/- 0.02
   held    a second task asks the same check of the same files: not run twice

3  An instruction keeps its date
           February 10: "Use the tape-measured lengths" is in force
           March 2: "Use the laser-measured lengths" is in force
   stale   the task closed before either was recorded, and its closure says so

4  Acceptance is of one version
           a person reads the fit and accepts the result
   stale   the code is edited afterwards: the acceptance was of the old version

5  A reminder shown is not a mistake repeated
           a new agent starts and is told the lesson in the person's own words
           asked later: 0 repeated, 0 followed, 1 not judged, of 1 times shown

6  A check passes only on what it declared
   FAIL    a check reads figures/style.txt but declared only the analysis
   ok      the declaration is corrected and the same check passes

18 commands ran in 0.5 s, and the record gave all 26 answers expected of it.
Each row is a real command and its answer. See them all: taos demo --full
Nothing of yours was touched. `taos demo --keep` leaves the folder in place.
```

`./taos demo --full` shows each command and what it printed, and
`./taos demo --json` gives the same run to a program. Every command in the
script carries the words the record should answer with. If the record answers
differently, the demo stops and says so.

## The idea

The failures this system was built to stop have one shape: a record was
consulted without the conditions it was true under. A check passed, and the
files were edited afterwards. An instruction was given, and later replaced.
A reminder was shown, and the count of times shown was read as a count of
mistakes. Each record was true. Each was true of something that had changed.

So TAOS stores a statement together with who made it and what it stood on,
and answers one question about it later:

| Answer | Meaning |
|---|---|
| `holds` | what it stood on is the same |
| `fails` | it was checked on things as they are now, and did not pass |
| `stale` | something it stood on changed, and the answer names it |
| `unknown` | it cannot be established: never checked, not recorded, or a change nobody declared the effect of |

`unknown` is an answer. It is never rounded to true, to false or to zero.

Three rules follow. None of them depends on which models are in use.

1. **Validity is the basis, not the age.** A pass is good for the bytes it
   tested, for as long as they are those bytes. An hour-old pass on edited
   files is worth nothing; a month-old pass on unchanged files is still a pass.
2. **The original words outrank any summary of them.** An instruction is kept
   as it was said, with its date, scope and expiry, and is delivered in those
   words. A summary carries the hash of its original and goes stale with it.
3. **An observation has a kind and a source.** Shown is not violated.
   Recommended is not executed. Missing is not false. A check passing is not
   a person accepting the result.

**Why this matters more as agents do more.** A project run by agents piles up
earlier results faster than anyone can recheck them. Rerunning everything
does not scale, and trusting by age is wrong in both directions at once: in
the experiment below, every age limit either reran work that nothing had
touched or relied on work that something had. A result kept with its basis
was rerun exactly when an edit reached it, and was never relied on wrongly.

The idea is old, and `docs/METHOD.md` says where it comes from: build systems
and truth maintenance systems have kept results with their justifications for
decades. What is added here are the things research rests on that a build
system does not model: dated human instructions, and a person's acceptance of
one exact version.

## What is tested

The [claim register](docs/CLAIMS.md) links the software's claims to named tests
or recorded experiments. The table summarizes the public checks.

| Claim | Evidence | Run it yourself |
|---|---|---|
| Earlier releases had 22 distinct cases of a record read without its conditions; each is now refused or reported | 22 of 22 fail at `071a348`, 5 of 22 fail at `89f36ce`, 22 of 22 pass here | `python3 evals/at_revision.py` |
| The tests detect each of the 20 seeded faults in this run | 20 protections removed one at a time; 20 of 20 removals are caught | `python3 evals/mutations.py` |
| Tracking the folders each check read avoided stale reuse on this synthetic workload | 60 edits, 360 results relied on: 60 executions and 0 wrong reuses, the same as an oracle; age limits gave 180 to 48 executions with 30 to 161 wrong reuses | `python3 evals/reuse_frontier.py` |
| Omitting an input folder allowed obsolete reuse in the open run and prevented the check from passing in the isolated run | 150 wrong reuses in 360 in the open; isolated, 0 of 366 runs passed, so nothing was reused | same |
| The whole suite passes | 155 tests, Python 3.9 and 3.12, Linux and macOS | `./taos selftest` |
| This page says what the recorded runs say | every row of `docs/CLAIMS.md` and every number above, read back against the code as it is | `python3 evals/claims.py` |

**How to verify the numbers.** Each run is stored in `evals/results/`
with a fingerprint of the code it measured. `python3 evals/claims.py` asks of
every claim what TAOS asks of any result, and answers `holds`, `stale`,
`fails` or `unknown`. Edit `taos_core/gates.py` and the reuse numbers are
`stale` until they are measured again. CI fails until then.

The isolation result was a prediction first. It was committed on its own
before the code existed, so the history shows the order (`docs/METHOD.md`,
"A seventh prediction").

## What it does not do

- **In the open, it trusts what a check declares.** A check that reads a
  folder it did not declare is reused when that folder changes. Marking the
  check `"isolated": true` runs it in a fresh directory containing its declared
  files, with a fixed environment. In our missing-folder experiment the check
  then failed. On macOS the network and the rest of the workspace are closed
  to it too; elsewhere the record says they were open. Placing the files takes
  time, and a file outside the workspace can still be read by its absolute path.
- **Ignored files need a declared input group.** A *domain* is a named group
  of files. Include a Git-ignored data file in a domain and declare that
  domain as an input to the check if a change to the file should be detected.
- **It cannot see outside the workspace.** A check that depends on the
  network, the clock or the environment has to say so with `max_age_hours`.
- **Asking has a cost.** Every answer re-reads the files, and the time grows
  with the tree (measured in `docs/CLAIMS.md`). Reuse pays when a check costs
  more than a few milliseconds per file set, and does not pay for a trivial
  check on a very large tree.
- **The evidence is mechanical.** These tests show the mechanism does what it
  says. They do not show that research done with it comes out better. That
  needs a study this repository does not contain.

## Reading this repository

| If you have | Start with |
|---|---|
| one minute | `./taos demo` |
| five minutes | this page, then `docs/CLAIMS.md` |
| twenty minutes | `taos_core/basis.py` (the comparison, about 250 lines), `tests/test_counterexamples.py`, then `docs/METHOD.md` from "One error, one answer" |
| an agent with you | `docs/ARCHITECTURE.md`, "Reading this repository cold": where each idea lives, the commands that verify it, and what to keep true when changing it |

An agent asked to examine or change TAOS should not set it up first.
`AGENTS.md` says so in its first section.

## Use it for your own work

Make your own private copy from the template. This is meant to be a repo you
rewrite, not one you track.

```bash
gh repo create <you>/<your-os-repo> --private --clone --template JustinBen0131/ThesisAnalysisOS
cd <your-os-repo>
codex        # or: claude
```

On github.com the same thing is the **Use this template** button. `MANUAL.md`
has two other ways, for keeping the upstream or for working without GitHub.

Paste as the first message to the agent:

```
Read BOOTSTRAP.md in this repo and follow it exactly. Ask me the ten bootstrap questions in one message, then construct the OS from my answers. Do not touch anything outside this directory until I have answered.
```

Answer the questions. The agent validates, constructs, runs the doctor, and
starts your first task. Then, in your own terminal:

```bash
./taos panel on
```

**The split that matters:** this private repo holds the OS and your operating
state (`.taos/` is git-ignored, so your tasks never leave your disk). Your
actual work repos receive only a four-line block in `AGENTS.md`, a
`.taos-link.json`, and optionally the hook files. Nothing else crosses, so
nothing your colleagues review ever contains your agent bookkeeping. See
`policies/REPO_SPLIT.md`.

## What a day looks like

```bash
./taos status                # where everything stands, in ten lines
./taos why                   # what was recorded and no longer holds, and why
./taos brief --print         # what changed, what needs you, nothing else
./taos task list             # every task, hot ones first
```

Tell either agent "work on AZ-7". It runs `taos start` and is shown what
stands, which of your instructions govern the task in your own words, and
what was learned the last time. It works, runs the checks, and finishes with
evidence or a handoff the other agent can pick up. To move a task to review
or done, its checks must still hold or a waiver and its reason must be recorded.
When you have looked at the result, `./taos task accept AZ-7` records that you
accepted that version; a later edit does not inherit it.

## The parts

| Part | What it does |
|---|---|
| `taos` | the whole command line, stdlib only |
| `taos_core/basis.py` | the one place a result is compared with what it stood on |
| `taos why`, `taos_core/standing.py` | every record a task rests on, read back against the present |
| `AGENTS.md`, `CLAUDE.md` | the contract both agents read, rendered for you at setup |
| `hooks/` | one guard for both agents: no secrets, no force pushes, no writes in the other agent's lane |
| `.taos/` | your state: tasks, claims, events, decisions, handoffs, check results |
| `kernels/` | distilled context with a fingerprint and an expiry |
| `atoms/` | corrections a machine can check, run by `taos doctor` |
| `policies/` | the rules, each under a page |
| `taos change`, `lesson`, `replay`, `bank`, `rule`, `anchor` | how you know the system is getting better (`docs/METHOD.md`) |
| `evals/` | the four evaluations above, each one command, and the runs they recorded |
| `examples/measurement/` | the small measurement the demo uses |
| `MANUAL.md` | the manual for the human |
| `docs/ARCHITECTURE.md` | the map for anyone, person or agent, reading the code |
| `docs/SPEC.md` | the binding spec for anyone changing the OS |

## The science layer

The parts above keep two agents from colliding. These keep the system honest
about itself. Each came from a measured failure; the measurements are in
`docs/METHOD.md`.

```bash
./taos change register ...   # say what a change will move, and a control that must not, before making it
./taos change score ...      # graded by someone who did not build it, from receipts or a named measurement
./taos lesson at reply ...   # your past corrections, printed at the moment they apply; that is an exposure
./taos lesson outcome ...    # whether the mistake was made again in that case; only this counts as a repeat
./taos replay --history h.jsonl --field gib --threshold 8 --threshold 16
                             # size a new limit on your own history; rows with no label are counted apart
./taos bank score answers.json   # replay past decisions; a reader counts only after passing controls
./taos rule governing plots --on 2026-03-02   # the instructions in force on a date, as their original words
./taos anchor resolve ...    # refused without a reference, a control and a prediction made beforehand
```

## Lineage

This is the generalized second version of an operating layer that ran a
two-agent physics thesis through 2026: hundreds of tasks, both agents in daily
use, every collision and every lost handoff paid for once. What survived is
here; what did not is in `docs/LINEAGE.md`.

## License

ThesisAnalysisOS is open source under the [Apache License 2.0](LICENSE).
You can use, modify, and distribute the software, including in commercial products.
When redistributing it, include the license, retain applicable notices, and mark
the files you changed. The [NOTICE](NOTICE) identifies Justin Bennett as the
author. Section 4 of the license gives the attribution requirements.
