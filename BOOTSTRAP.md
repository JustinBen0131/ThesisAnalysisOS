# BOOTSTRAP — read this whole file before doing anything

You are Codex or Claude Code, opened inside a fresh clone of ThesisAnalysisOS.
Your job in this session is to set the OS up for the person in front of you,
with one setup interview, then hand control back.

## What you may do in this session

- Read any file in this clone.
- Run the exact commands listed below.
- Write `bootstrap/answers.json`. After a successful first construction,
  tailor the newly generated kernel files as described in step 6.
- Run `./taos start` on the first task if the person asks.

## What you may not do in this session

- Touch anything outside this clone, except that `./taos bootstrap construct`
  links the workspaces the person names and installs hooks according to
  their answers. Step 6 also permits a read-only look at the primary
  workspace.
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

Before the questions, check whether the clone has a remote:

```bash
git remote
```

If it has a remote and the person has not said they own a private copy,
tell them to confirm that any remote they push to is private. A local-only
checkout also works.

Let them choose a private copy or a local-only checkout. The [manual](MANUAL.md#2-install-sixty-seconds)
shows how to use the template, keep the upstream under a separate remote, or
remove the remote for local use. Leave remote changes and any push to them.

The private OS clone holds the task state, rules and runtime. A linked work
repo receives a marked block in its agent instructions and a `.taos-link.json`
pointer, plus hooks or merge snippets if requested. See
[The repo split](policies/REPO_SPLIT.md).

## The pass

1. Verify the runtime. Both must succeed:

   ```bash
   python3 --version        # 3.9 or newer
   ./taos selftest
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
   - `first_tasks` uses the first two fields as `title` and `next_action`.
     If the last optional `::` field is exactly `P0`, `P1`, `P2`, or `P3`,
     map it to `priority`. The other optional field becomes `done_when`.
     The parser example in Q8 becomes:

     ```json
     {
       "title": "Fix the flaky parser tests",
       "next_action": "run cargo test parser",
       "done_when": "parser suite passes twice",
       "priority": "P0"
     }
     ```

     Omit optional fields that were left out. A task without a priority
     starts at P2.
   - For each repo named in Q3, add an entry to `workspaces`. Give it a
     `name`, expand `~` to an absolute `path`, mark one `primary`, and set
     `agent` to `codex`, `claude`, or `any`. If Q3 is blank or the person
     takes its default, leave out `workspaces`. The OS clone itself is the
     workspace and needs no link to itself.
   - `gates`: the person's own commands, or omit the key so the stack default
     is used. If they said which folders a check reads, write `domains` (each
     a `name` and its file `patterns`) and give the gate `depends_on` with
     those names. Add `"isolated": true` to a gate they asked to isolate.
   - For Q9, set `"install_hooks_in_workspaces": false` if the person opts out
     of workspace hooks. The workspaces are still linked so the commands in
     their TAOS blocks work manually.
   - Fill required fields from the answers or their stated defaults. Leave
     other keys out when the person takes their defaults.

4. Validate, and fix anything it names:

   ```bash
   ./taos bootstrap validate
   ```

5. Construct:

   ```bash
   ./taos bootstrap construct --agent codex  # use claude if you are Claude Code
   ```

   Among other things this probes what token telemetry the machine writes
   (Claude transcripts under `~/.claude/projects/`, Codex rollouts under
   `~/.codex/sessions/`) and records the answer in the config. Report what it
   found in one line; do not ask the human about tokens, prices, or quotas.
   If neither is readable, say so plainly: the controller runs on its own
   signals and those fields stay null.

   Setup writes the config, creates missing task titles, prepares the agent
   instructions and kernels, links named workspaces, renders the first brief,
   and runs doctor. Show the doctor output verbatim and report the workspace
   hook outcome. Existing hook settings can require a manual merge. Tell
   the person which snippet or source settings file the output names for
   review. Until the client loads the hooks, start sessions with the status
   command from the workspace's TAOS block.

   If links or doctor checks fail, setup reports an error. Some files or tasks
   may already exist. Fix the reported issue before continuing. Repeating
   setup can refresh unedited generated files and preserves edited kernels
   and customized root instructions. Existing tasks and setup suggestions
   appear once. Once a task has an ID, keep its original prefix in your answers.

6. Sharpen the new kernels after the first successful setup. If construction
   kept an existing kernel, preserve the person's edits. Read
   `policies/OBJECTIVE.md` before editing. Use the workspace's layout, build
   files, CI config, contributing guide, recent commit subjects, and tests
   to write `kernels/PROJECT_KERNEL.md`. Include the actual commands and the
   mistakes a newcomer is likely to make. Use answers #0, #6, #9, and #10
   to write `kernels/PRINCIPAL_KERNEL.md`. Capture what the person reserves
   for themselves, where they want autonomy, and what agents keep getting
   wrong. From the OS clone, refresh the index entries you edited:

   ```bash
   ./taos kernel refresh PROJECT_KERNEL --generator agent
   ./taos kernel refresh PRINCIPAL_KERNEL --generator agent
   ```

7. Briefly report the config, tasks, linked workspaces, and kernels you
   created or updated. If a first task has no completion
   criterion, propose one based on what you read. Then send the block in
   `bootstrap/TIPS.md` verbatim. It is written in your voice on purpose: it
   is the first time the system speaks for itself, and it tells them how to
   let you grow.

8. If they want to begin, start their first task:

   ```bash
   ./taos start --agent codex --task CMP-1 --session "CMP-1 | Fix parser tests"
   ```

   Use your agent name and the actual first task ID in place of `codex` and
   `CMP-1`. `start` claims the task and prints a capsule with its state,
   next action, and the commands to enter its workspace, branch or worktree.
   Run `./taos task show CMP-1` with the same ID to read the completion
   criterion if supplied. Hand control back after reading the capsule.

## If something fails

- `selftest` fails: report the failing test names and stop. Do not patch the
  OS to make them pass.
- `validate` fails: fix `answers.json` from its message and re-run.
- `construct` fails: show the message verbatim and use the reported failure
  to decide what needs correcting. Wait for successful setup before sending
  the tips or starting work.

Next session, read the tailored instructions in the OS clone or the TAOS block
in a linked workspace. If the client loaded the SessionStart hook, it prints
status. Otherwise run the printed `status --compact` command yourself.
