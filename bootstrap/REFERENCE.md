# Reference frame — for the agent only

Read this before the questions. Never send any of it to the human. It exists
because you are about to build an operating system for a person who has never
run one, and you have never seen one running. This file is the missing
experience: what the reference instance looked like at full scale, what it
taught, and what each artifact you will produce looks like when it is good.

## Who knows what

The human in front of you has never built or run an agent operating system.
They will answer ten questions from the outside, in their own words, without
knowing which answers are load-bearing. **You are the one who knows.** That
means:

- Read every answer for what it implies about their workflow, not just what
  it says. "I keep a second checkout for Claude" implies lanes, worktree
  roots beside that checkout, and a guard rule. They will not say that.
- When an answer would produce a system that fights them, say so before
  building, in one sentence, with the alternative. Do not silently comply
  with a bad configuration and do not silently override it either.
- Defaults are not neutral. Each default below was chosen because it failed
  the other way in the reference instance. Prefer them unless the human's
  workflow gives you a specific reason not to.
- Build with the caution you would want if this were a shared production
  system, because for them it is: their repos, their colleagues' history,
  their keys are all one wrong guard rule away.

## THIS IS REFERENCE, NOT TEMPLATE

The reference instance ran a physics thesis. This human is not a physicist,
does not have that project, and does not work the way its principal did.
Nothing below is to be copied into their instance: no vocabulary, no task
names, no policy text, no assumptions about their domain. What transfers is
the **shape**: the mechanisms, the failure modes, the level of care, and the
judgement about what is worth a rule. Their instance must be built from
their answers and their repo, at the same standard, with none of the
reference's content.

## What the reference instance looked like at full scale

One human, two agents (Codex and Claude Code), daily for a year, on one
private repository holding the operating system and one public repository
holding the work. By the end:

- **~350 tasks** with stable ids, ~3,000 attributed comments, every task
  carrying its evidence pointers, its session mappings, and its history.
- **Claims as the only coordination.** Each agent acquired a scope-local
  lease before mutating anything; the other agent read freely and never
  wrote inside a live claim. Stale takeover happened a few dozen times, each
  logged with a reason. Without this, the two agents edited the same files
  within the first week.
- **A hot-work rail** that was selective on entry and persistent on
  lifecycle: a task became hot when a human or agent started it and stayed
  hot until finished. Rails that filled themselves were tried and abandoned
  as noise.
- **Handoffs as files with a fixed shape.** Several hundred of them. Chat
  history did not survive session death; the files did. The header (agent,
  session, task, scope) is what made provenance reconstructable months
  later.
- **Kernels**: four distilled documents (how the OS works, the project, how
  to work with the principal, live state) with a source fingerprint and an
  age limit, regenerated when they drifted. Cold sessions read them first
  and stopped re-deriving the world.
- **Atoms**: corrections encoded as machine checks with red/green fixtures,
  run by the doctor. Roughly forty by the end. The only lessons that stopped
  repeating were the ones a validator enforced.
- **A deterministic daily brief** whose top line read "No action needed"
  most mornings. That line was the product.
- **A decision queue** so agents asked in one place and kept working.
  Before it, the human answered questions in five chats and was the
  bottleneck.
- **Burns**: expired working files archived, the archive verified by
  restore, then deleted. Never lost a file.
- **One guard script** under both agents: no secrets, no force pushes, no
  hand-edits to the store, no edits to the guard itself.

And the parts that were built and then cut, because they did not earn their
weight: a second task store that drifted from the first; an external tracker
as the source of truth; a capability broker with grants and packets that was
right for a shared supercomputer and wrong for a laptop; execution
governors; model-driven scheduled automations that burned budget and taught
nothing; fifty policy files. The instance you are building is what survived.

## What a day looked like

Morning: the human read one page. It said what changed overnight, what was
blocked and why, and which one or two decisions they owed. They answered
those in the panel. Then they told an agent "work on X-47". The agent ran
`start`, got its worktree and branch and the last handoff, and worked. When
it needed a judgement it queued a decision and kept going on what did not
depend on it. It ran the gates, wrote a handoff if another session would
continue, and finished with evidence. The other agent picked the task up from
the handoff without the human re-explaining anything. Evening: nothing. The
state was on disk.

What made that possible was not any one mechanism. It was that every
mechanism refused vague input: a handoff without sections, a done without
evidence, a claim on a held scope, a blocked without a blocker. The refusals
were the system working.

## Worked examples of what you will produce

The templates give you skeletons. These show what a *filled* one looks like
for an invented Rust project. Match the density and specificity, not the
content.

### A good PROJECT_KERNEL (excerpt)

```
## What an agent should know before touching code

Build and test: `cargo build --workspace`, `cargo test --workspace` (~90s,
the `integration` feature adds 6 min, CI runs both). `just check` is the
pre-push gate the team actually uses; it runs fmt, clippy with -D warnings,
and the fast tests. There is no `make`.

Layout: `crates/parser` (hand-written, no generator; grammar.md is the
spec and is authoritative over the code), `crates/ir` (the SSA form; the
verifier in `ir/verify.rs` is the only documentation of the invariants),
`crates/backend` (three targets behind one trait; `wasm` is the reference,
the others are checked against it in `tests/cross/`).

Load-bearing and easy to break: `ir/verify.rs` (every pass runs it in debug;
a passing test suite with the verifier disabled means nothing),
`parser/recovery.rs` (error recovery order is deliberate; reordering
changes diagnostics that downstream tooling parses).

Looks wrong, is correct: the parser allocates every node in an arena and
never frees; this is intentional for the LSP hot path. `unsafe` in
`backend/x64/emit.rs` is reviewed and fenced; do not "fix" it.

Newcomer mistakes seen in the log: adding a crate dependency (the tree is
deliberately thin; ask), running only the fast tests before claiming green,
editing generated `tests/fixtures/*.expected` by hand instead of
regenerating with `UPDATE_EXPECT=1`.
```

Every sentence there came from reading the repo: the justfile, CI, the
verifier, the last fifty commit subjects. None of it is generic. If you
cannot find a fact, do not invent one; write "not yet known" and leave a
note for the first real session to fill it.

### A good PRINCIPAL_KERNEL (excerpt)

```
## The dials they set
- Rope: branches. Commit freely on task branches; every push asks. They
  said "I want to see pushes for the first couple of weeks", so do not
  propose raising this before then.
- Merges: theirs only, via PR. Put the PR link on the task and stop.
- Attention: three queued decisions a day, none between 22:00 and 07:00.

## Default posture
- Terse. Their answers were one line each; match that. Lead with the
  result, then the evidence path, then nothing.
- They correct by restating the rule, not by explaining. Take the
  restatement as the rule.

## Corrections observed
- 2026-09-15: "don't add a crate without asking" (from setup, #10).
  Proposal prop_… queued; promote to an atom after the first real occurrence.
```

Notice what is absent: nothing about who they are, where they work, or
anything they did not say to you. Working model, not dossier.

### A good handoff

```
Agent: codex
Chat/session: CMP-7 | parser recovery
Task: CMP-7 | Fix error recovery on unclosed generics
Claim/scope: task:CMP-7, branch:cmp/cmp-7-fix-error-recovery

## State
Failing test written and confirmed failing (tests/parser/recovery_generics.rs).
Root cause located in parser/recovery.rs:212, the sync set omits `>`. Fix not
applied because changing the sync set reorders three existing diagnostics.

## Changed
tests/parser/recovery_generics.rs (new). No source changes.

## Evidence
cargo test -p parser recovery_generics → 1 failed, as intended.
Gate run .taos/gates/CMP-7_20260915T031200Z.json: fmt ok, clippy ok, test
FAIL (expected, the new test).

## Risks and open questions
Adding `>` to the sync set changes diagnostics in tests/parser/diag_*.expected;
downstream tooling parses those. Decision dec_… asks whether reordering is
acceptable or the fix must preserve order. Do not apply until answered.

## Next command
cargo test -p parser diag_ 2>&1 | head -40
```

A bad handoff says "made progress on the parser fix, tests mostly pass,
continue from here". The tool refuses that one, and it should.

### A good atom

```json
{"id": "no-hand-edited-expected-files",
 "rule": "Generated *.expected fixtures are regenerated, never edited by hand.",
 "why": "Two hand edits in one week produced diffs nobody could review.",
 "check": {"type": "regex_must_not_match", "target": "latest_handoff",
           "pattern": "edited .*\\.expected by hand"},
 "fixtures": {"red": "I edited tests/a.expected by hand",
              "green": "regenerated with UPDATE_EXPECT=1"}}
```

An atom is a lesson with a check. "Be careful with fixtures" is not an atom.

### A good decision

```
taos decide ask --agent codex --task CMP-7 \
  --question "Adding '>' to the parser sync set reorders three diagnostics that tests/parser/diag_*.expected pin. Keep the current order (larger fix, ~2h) or accept the new order (update fixtures, 10 min)?" \
  --option "keep order" --option "accept new order"
```

It names what was observed, what each option costs, and offers two concrete
choices. A bad decision asks "how should I handle the diagnostics?".

### Good first tasks vs bad

Good: "Cut monomorphisation time on the large fixture below 10s :: profile
the pass on tests/fixtures/large.src and list the top three costs :: the
fixture compiles under 10s on CI three runs running". Finite, has a literal
next step, and says what done looks like.

Bad: "Improve compiler performance". That is an umbrella. If the human
gives you one, keep it as a parent and ask for, or propose, the first finite
child under it.

### Turning intent into a closure contract

The human says: "I need to fix the login race condition." They should not
have to say more. You produce, without ceremony:

```
title:        Fix the login race
done_when:    the reproduction no longer occurs and the auth tests pass
verification: tests/auth/login_race.rs (the reproducer) plus the auth suite
next_action:  reproduce and locate the competing state transitions
```

If closure is obvious, proceed without a word. If two readings would change
what you build ("fix the race" vs "redesign session handling"), say one
line: "I'm treating this as done when the reproducer passes; if you meant
the broader redesign, say so." If, mid-task, you find the shared session
serializer is broken across five paths, that has its own closure: create the
child, block the parent on it, and explain the split once in plain words.
When you finish: "Done: race eliminated. Verified by: login_race passes,
auth suite green. Durable result: the reproducer stays as a regression test.
Remaining: none." Four lines, then stop.

## Teaching without a manual

The human never reads `MANUAL.md` to learn how to state a task; you are the
interface. At setup, say only: tell me the outcome you want, tell me what
done means if you know, otherwise I'll propose it, give me the next step if
it's obvious, and I'll split out independent blockers myself; you can
override any boundary I infer. In the first few real tasks, teach at the
point of need: when they say "make the parser better", reply with the
concrete boundary you chose and let them correct it. When they already give
a clear endpoint, say nothing about task theory. When they have shown they
know the pattern, stop explaining. The best onboarding disappears.

## Reading question 0

They may push back on the model itself. Three patterns and how to respond:

- **"I don't use worktrees, I just branch."** Set isolation to `branch`,
  say so, move on. Their workflow wins.
- **"Why would the agents need separate checkouts?"** Explain in two lines:
  a reserved checkout is a hard boundary the guard enforces, useful when two
  agents run at once; unnecessary if they run one at a time. Recommend `any`
  for a single-agent user. Do not oversell lanes.
- **"This is a lot of ceremony."** Point at `taos pause` and the defaults:
  answering "defaults" plus three tasks is ninety seconds, and the ceremony
  is what makes a dead session cost nothing. Then let them decide.

If they describe something the schema cannot represent, do not force it into
the nearest enum. Build with the closest safe default, state the mismatch in
one line, and leave a proposal (`taos propose --kind policy`) describing what
would need to change.

## The standard

The reference instance earned its keep by being right when it refused and
quiet when it worked. Build theirs so that the first time it refuses
something, the refusal is obviously correct, and the first morning brief
says "No action needed." Everything else is detail.
