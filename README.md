# ThesisAnalysisOS

A local, zero-dependency operating layer for one engineer who runs two coding
agents (OpenAI Codex and Anthropic Claude Code) as peers on the same work.

It gives the agents one task store with stable ids, scope-local claims so they
never collide, a handoff format so a session can die without losing the work,
gates that must pass before anything is called reviewable, a daily brief and a
local panel so you see truth without reading files, and a small self-iteration
loop (correction atoms, kernels, proposals, burns) so the system gets tighter
instead of heavier. It sets itself up from ten questions.

Everything is plain files under one directory. It runs on the Python standard
library. It never calls a network or a model. Switch the panel on and off at
will; delete the directory to uninstall.

This is an unofficial personal prototype, built by one person for a friend.
It is not affiliated with any employer or product.

## Sixty seconds

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
./taos brief --print         # what changed, what needs you, nothing else
./taos task list             # every task, hot ones first
```

Tell either agent "work on AZ-7". It runs `taos start`, gets its own worktree
and branch, works, runs the gates, and finishes with evidence or a handoff the
other agent can pick up. When it needs you, the question lands in the panel,
not in a stalled chat.

## The parts

| Part | What it does |
|---|---|
| `taos` | the whole command line, stdlib only |
| `AGENTS.md`, `CLAUDE.md` | the contract both agents read, rendered for you at setup |
| `hooks/` | one guard for both agents: no secrets, no force pushes, no writes in the other agent's lane |
| `.taos/` | your state: tasks, claims, events, decisions, handoffs, gate runs |
| `kernels/` | distilled context with a fingerprint and an expiry |
| `atoms/` | corrections a machine can check, run by `taos doctor` |
| `policies/` | the rules, each under a page |
| `MANUAL.md` | the manual for the human |
| `docs/SPEC.md` | the binding spec for anyone changing the OS |

## Lineage

This is the generalized second version of an operating layer that ran a
two-agent physics thesis for a year: hundreds of tasks, both agents in daily
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
