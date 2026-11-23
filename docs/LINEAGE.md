# Lineage

<sub><b>Understand or change the system · 4 of 4</b> &nbsp;·&nbsp; [← Build specification](SPEC.md) &nbsp;·&nbsp; [All documents](README.md) &nbsp;·&nbsp; [Contributing →](../CONTRIBUTING.md)</sub>

The original physics project used Codex and Claude over a
year of daily work. One researcher coordinated several hundred tasks and
recorded the conflicting edits and lost handoffs that shaped this design.
Today's project roster gives each participating session its own role name.
[Configuring project roles](AGENT_ROLES.md)

## Kept, because it worked

- **Stable ids allocated only by the tool.** A hand-written id once pointed at
  a task that did not exist anywhere else. Never again.
- **Scope-local claims with heartbeats and logged takeover.** The only thing
  that helped prevent overlapping edits in the original project.
- **Hot work selective on entry, persistent on lifecycle.** A rail that fills
  itself is noise; a rail you have to opt into stays meaningful.
- **Handoffs as files with a fixed shape.** Chat transcripts did not survive
  session death; files did.
- **The attribution header on every comment.** The one line that made
  provenance tractable.
- **Kernels with fingerprints and expiry.** Distilled context that is allowed
  to rot visibly beat re-deriving the world every session.
- **Atoms: corrections a machine checks.** The only lessons that stopped
  repeating were the ones a validator enforced.
- **Archive, verify restore, then delete.** Burns never lost a file.
- **Decision cards, with a daily budget.** Agents stalling in chat waiting
  for a human answer was the largest hidden cost.
- **Evidence over memory.** `done` without an artifact was always wrong.
- **Agent brand as provenance, never authority.** Every rule that branched on
  which agent was acting eventually produced an asymmetry that had to be
  unwound.
- **Zero-token loops.** Model heartbeats that polled state burned budget and
  taught nothing. Deterministic scripts replaced every one of them.

## Cut, because it did not

- **Two stores for the same work** (a catalogue and a register). They drifted.
  One event-sourced store, projections for everything else.
- **An external task tracker as the source of truth.** Retired; local files
  with a projection to a panel.
- **A capability-firewall broker with grants, packets, and matrices.** Right
  for a shared supercomputer; wrong for one engineer's laptop. Replaced by one
  readable guard script and the human-only list.
- **Execution governors, admission receipts, and parallel-lane queues.**
  Mechanism that outgrew its justification. Cut entirely.
- **Provider-specific wrappers for every remote action.** Nothing here is
  remote.
- **Dream lanes, night briefs, scheduled model automations.** Replaced by
  `taos retro`, run by the human when they want it.
- **Dozens of policy files.** Six, each under a page.

## Changed

- Gates are new: the thesis OS validated artifacts scientifically; an
  engineer's equivalent is the test suite, so it became a first-class gate
  that `finish` enforces.
- Lanes are new: reserving a workspace for one agent was the principal's own
  practice, so the guard enforces it rather than a policy line asking for it.
- The daily brief lost its human-formatting layer (Google Docs, colour bands)
  and kept only the part that mattered: the top line and what needs you.

## How to compare the record with other tools

- **Which work needs doing again?** GNU Make compares a target with its prerequisites. In the pendulum example, the plot colour changes while the six timing inputs stay the same. TAOS can reuse the recorded fit. [How GNU Make works](https://www.gnu.org/software/make/manual/html_node/How-Make-Works.html)
- **Where did a number come from?** W3C PROV describes entities, activities and responsible agents. AiiDA connects scientific data and processes in a provenance graph. For the two-instrument study, trace the pooled count back to each instrument’s rows. [W3C PROV-DM](https://www.w3.org/TR/prov-dm/) · [AiiDA provenance](https://aiida.readthedocs.io/projects/aiida-core/en/stable/topics/provenance/concepts.html)
- **Where should the next session begin?** LangGraph saves a thread’s state in checkpoints. An incoming TAOS reviewer can ask which checks still hold, read the researcher’s dated instruction and find the next action in a task packet. The transit walkthrough also shows which report version the operator accepted. [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
