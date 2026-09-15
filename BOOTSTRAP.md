# BOOTSTRAP — read this whole file before doing anything

You are Codex or Claude Code, opened inside a fresh clone of ThesisAnalysisOS.
Your job in this session is to set the OS up for the person in front of you,
in one pass, and then stop. Nothing else.

## What you may do in this session

- Read any file in this clone.
- Run the exact commands listed below.
- Write exactly one file: `bootstrap/answers.json`.
- After construction, run `./taos start` on the first task if the person asks.

## What you may not do in this session

- Touch anything outside this clone, except that `./taos bootstrap construct`
  appends a marked block to `AGENTS.md`/`CLAUDE.md` in the workspaces the
  person names, and installs hooks there if they say yes.
- Install anything, change global config, or run `taos panel on` (the person
  starts the panel themselves; it is theirs).
- Create tasks by hand, edit `.taos/`, or improvise structure.

## Before anything: load the reference frame

Read `bootstrap/REFERENCE.md` in full, then `policies/OBJECTIVE.md`, then
`policies/CONTROL.md`. They are for you, never for the human. You are about to
build an operating system for someone who has never run one, and you have
never seen one run; those three files are the missing experience: what the
reference instance looked like at scale, what each artifact looks like when
it is good, what the system optimises for, and how it regulates itself.
Nothing in them is a template for this person. Everything in them is the
standard you build to.

## Step zero: make this repo theirs

Before the questions, check whether this clone still points at someone else's
remote:

```bash
git remote -v
```

If it shows a remote that is not the person's own, say this to them, plainly:

> This clone still points at the original repository. This OS is meant to be
> yours to rewrite: the policies, the questions, the guard rules, all of it.
> Make it your own private repo first, so your operating state never mixes
> with the codebases your colleagues see.

Then give them these commands and let them run them (do not run them
yourself, the repo name and visibility are theirs to choose):

```bash
rm -rf .git && git init -b main
git add -A && git commit -m "ThesisAnalysisOS: my instance"
gh repo create <their-name>/<their-os-repo> --private --source=. --remote=origin --push
```

If they would rather keep the upstream to pull improvements, this instead:

```bash
git remote rename origin upstream
gh repo create <their-name>/<their-os-repo> --private --source=. --remote=origin --push
```

The boundary that matters, and you should state it once: **this repo is
private and holds the OS; their work repos receive only a four-line block in
`AGENTS.md`, a `.taos-link.json`, and optionally the hook files.** Nothing
else crosses. `policies/REPO_SPLIT.md` has the detail. If they ask you to
vendor the OS into their work repo, say no and point at that file.

## The pass

1. Verify the runtime. Both must succeed:

   ```bash
   python3 --version        # 3.9 or newer
   ./taos selftest          # under a minute; every test passes
   ```

   If `./taos` is not executable, use `python3 taos` everywhere below.

2. Open `bootstrap/QUESTIONS.md` and send the block between the `ASK` markers
   **verbatim**, as one message. Do not paraphrase it, do not reorder it, do
   not drip the questions one at a time, do not add questions of your own,
   and do not show them anything else from that file. The only substitutions
   are the `<...>` placeholders, which you fill from the machine (shell
   username, timezone, the folder name of the repo you are in); leave a
   bracket as-is if you cannot tell.

   If they answered #0 with anything but blank or N/A, that comes first:
   explain what they asked about in plain words, propose how you would
   reshape the setup to fit what they described, and re-ask only the
   questions that changed. Their workflow wins over the defaults every time.
   You may ask up to three follow-up questions of your own when an answer is
   ambiguous or when you can see something on the machine that contradicts it
   (a `justfile` with a `test` recipe when they gave you `cargo test`, a repo
   path that does not exist, a branch pattern that will not parse). Ground
   every follow-up in something you actually observed. If their reply
   contains the word **proceed**, ask nothing and build with what you have,
   stating the assumptions you made in one line each. Then stop asking.

3. Turn the answers into `bootstrap/answers.json`. The shape is
   `bootstrap/answers.schema.json`; a complete example is
   `bootstrap/answers.example.json`. Rules:
   - `first_tasks`: each `title :: next action [:: P0..P3]` line becomes
     `{"title", "next_action", "priority"}`.
   - `workspaces`: absolute paths, expand `~`, mark one `primary`, and set
     `agent` to `codex`, `claude`, or `any` per the person's answer to Q3.
   - `gates`: the person's own commands, or omit the key so the stack default
     is used.
   - Leave out any key the person answered "default" for.

4. Validate, and fix anything it names:

   ```bash
   ./taos bootstrap validate
   ```

5. Construct:

   ```bash
   ./taos bootstrap construct --agent <codex|claude>
   ```

   This writes `.taos/config.json`, renders `AGENTS.md` and `CLAUDE.md` for
   this person, writes the project and principal kernels, creates the first
   tasks, links the workspaces, pins the Codex hook paths, renders the first
   brief, and runs the doctor. Show the person the doctor output verbatim.

6. Sharpen. Construction gives you a skeleton; this step gives it a mind.
   You have licence, read-only, to look at the primary workspace: its layout,
   build files, CI config, contributing guide, the last fifty commit subjects,
   and the tests. From that, rewrite `kernels/PROJECT_KERNEL.md` so a cold
   session knows what is load-bearing, what looks wrong but is correct, the
   real commands, and the mistakes a newcomer makes. Rewrite
   `kernels/PRINCIPAL_KERNEL.md` from their answers to #0, #6, #9 and #10:
   how much rope they gave, what they reserve, what agents get wrong for
   them, and the tone of their answers (terse people want terse agents).
   Then `taos kernel refresh PROJECT_KERNEL --generator agent` and the same
   for PRINCIPAL_KERNEL. Read `policies/OBJECTIVE.md` before you write a
   word of either: it is what this OS is optimising for, and the kernels are
   where that starts.

7. Tell them, in three lines, what changed on disk: the config, the tasks,
   the workspace blocks, the two kernels you wrote and one thing in each they
   should correct if you got it wrong. Then send the block in
   `bootstrap/TIPS.md` verbatim. It is written in your voice on purpose: it
   is the first time the system speaks for itself, and it tells them how to
   let you grow.

8. If they want to begin, start their first task:

   ```bash
   ./taos start --agent <you> --task <PREFIX>-1 --session "<PREFIX>-1 | <short label>"
   ```

   Read the capsule it prints. It tells you where to work (worktree, branch,
   commands). Then stop and hand control back.

## If something fails

- `selftest` fails: report the failing test names and stop. Do not patch the
  OS to make them pass.
- `validate` fails: fix `answers.json` from its message and re-run.
- `construct` fails: report the message verbatim. It is designed to be
  actionable. Do not partially construct by hand.

When you are done, the person's next session, in this clone or in any linked
workspace, starts with `AGENTS.md` already tailored to them and
`taos status --compact` already injected by the SessionStart hook.
