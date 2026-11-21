# ThesisAnalysisOS

A local, zero-dependency operating layer for research done with AI agents.

It keeps tasks, instructions, checks and handoffs in plain files, so the work
survives the end of a session and a second agent can pick it up. And it keeps,
with every recorded result, what that result stood on, so it can say later
whether the result still holds.

Everything is plain files under one directory. It runs on the Python standard
library. It never calls a network or a model. Delete the directory to
uninstall.

This is an unofficial personal prototype, built by one person for a friend.
It is not affiliated with any employer or product.

## See it in a minute

```bash
git clone https://github.com/JustinBen0131/ThesisAnalysisOS.git
cd ThesisAnalysisOS
./taos demo
```

The demo builds a throwaway copy of a small measurement (six pendulum swings,
a fit for g, a check) and runs real commands against it. Nothing of yours is
touched. Part of what it prints:

```text
$ taos why PEN-1
    holds    closure: codex moved it to done on 2026-11-21; the same instructions govern
    holds    check fit: passed 2026-11-21T22:26:19Z; nothing it tested has changed
    PEN-1 stands as recorded. No person has accepted it yet.

One swing is measured again, and data/swings.csv changes.
$ taos why PEN-1
    stale    check fit: analysis changed: data/swings.csv
    PEN-1 does not stand as recorded: stale.

Another task needs the same check on the same files. It is not run twice.
$ taos gate run --task PEN-2 --agent claude
    held  fit          not rerun: nothing it tested has changed since 2026-11-21T22:26:19Z
```

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

The idea is old, and `docs/METHOD.md` says where it comes from: build systems
and truth maintenance systems have kept results with their justifications for
decades. What is added here are the things research rests on that a build
system does not model: dated human instructions, and a person's acceptance of
one exact version.

## What is tested

Every claim in this repository is listed in `docs/CLAIMS.md` with the code
that implements it, the test that checks it, and its status. The short form:

| Claim | Evidence | Run it yourself |
|---|---|---|
| The previous release had 17 distinct cases of a record read without its conditions; each is now refused or reported | 17 of 17 tests fail at commit `071a348`, 17 of 17 pass here | `python3 evals/at_revision.py 071a348` |
| The tests check what they say they check | 16 protections removed one at a time; 16 of 16 removals are caught | `python3 evals/mutations.py` |
| Reusing a result by its basis never relies on a stale one, and reruns only what an edit reached | 60 edits, 360 results relied on: 60 executions and 0 wrong reuses, the same as an oracle; age limits gave 180 to 48 executions with 30 to 161 wrong reuses | `python3 evals/reuse_frontier.py` |
| The whole suite passes | 142 tests, Python 3.9 and 3.12, Linux and macOS | `./taos selftest` |

## What it does not do

- **It trusts what a check declares.** A check that reads a folder it did not
  declare is reused when that folder changes. The reuse experiment measures
  this on purpose: 150 wrong reuses in 360 when every check hid one input.
  With nothing declared, TAOS reruns everything, which is safe and slow.
- **It cannot see outside the workspace.** A check that depends on the
  network, the clock or the environment has to say so with `max_age_hours`.
- **Asking has a cost.** Every answer re-reads the files. On one laptop that
  was 16 ms for 48 files and 256 ms for 4,800. Reuse pays when a check costs
  more than a few milliseconds per file set, and does not pay for a trivial
  check on a very large tree.
- **The evidence is mechanical.** These tests show the mechanism does what it
  says. They do not show that research done with it comes out better. That
  needs a study this repository does not contain.

## Use it for your own work

Clone it, then make it yours. This is meant to be a repo you rewrite, not one
you track.

```bash
git clone https://github.com/JustinBen0131/ThesisAnalysisOS.git ~/my-os
cd ~/my-os
rm -rf .git && git init -b main && git add -A && git commit -m "my OS"
gh repo create <you>/<your-os-repo> --private --source=. --remote=origin --push
codex        # or: claude
```

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
evidence or a handoff the other agent can pick up. A task cannot be moved to
review or done unless its checks hold on the files as they are, by any route.
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
| `evals/` | the three evaluations above, each one command |
| `examples/measurement/` | the small measurement the demo uses |
| `MANUAL.md` | the manual for the human |
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

PolyForm Noncommercial 1.0.0, with additional permissions. In plain words:

- Use it, change it, share it, for yourself, for research, for study, and to
  organize your own work, including at your job. Free.
- Keep the copyright notice with every copy and every derivative.
- Do not sell it, sublicense it, host it as a service, or ship a product built
  on it. That needs a separate written license from the author.

Full text and the exact additional permissions are in `LICENSE`.
