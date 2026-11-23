# Bring another assistant into a research task

<sub><b>Work with AI agents · 2 of 4</b> &nbsp;·&nbsp; [← Agent roles](AGENT_ROLES.md) &nbsp;·&nbsp; [All documents](README.md) &nbsp;·&nbsp; [MCP client →](MCP.md)</sub>

Start with one task ID, one question and the evidence the reviewer needs.
Use the terminal for local inspection, opt into MCP for a client's read-only
tools, or share a plain-text context packet when the reviewer has no tools.

## 1. Read a task in the terminal

From a configured project, replace `AZ-7` with an ID from `./taos task list`.

```sh
./taos capsule AZ-7
./taos why AZ-7 --json
./taos gate show --task AZ-7 --json
```

Before relying on a check, read its current standing for that task and
workspace. Check the recorded basis and run time against the inputs you
intend to use. `holds` means the recorded check still applies. `fails` means
the check found a failure. `stale` means its basis changed. `unknown` means
there is insufficient evidence. Keep the failed or stale record and record
any approved rerun as a new result. See the [evidence and acceptance rules](SPEC.md).

A task claim names the work the agent is taking on. A local role name records
declared attribution. Authenticate people and establish reviewer independence
separately. Ask the operator before sharing selected project material externally
or taking any action that needs approval. [Local agent roles](AGENT_ROLES.md)

## 2. Let a local client read through MCP

Opt in on the client side. Choose a project whose tasks, instructions and
evidence references the client may see. A local stdio server runs on your
machine. The host's model may still receive tool results under the host's
data policies. Inspect the project's content and the destination before
connecting. The TAOS adapter bounds its own tool surface. The host's shell,
file access, other tools and network permissions are governed separately.

Use `python3` with these separate arguments for the local server. Substitute
absolute paths to the TAOS executable and the selected project. `-B` prevents
Python bytecode writes.

```text
-B /path/to/taos --home /path/to/project mcp
```

| Host | Where to add that stdio command |
| --- | --- |
| Codex CLI | Run `codex mcp add taos -- python3 -B /path/to/taos --home /path/to/project mcp`. Codex documents `.codex/config.toml` for trusted project-scoped configuration. [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) |
| Claude Code | From the intended project run `claude mcp add --transport stdio taos -- python3 -B /path/to/taos --home /path/to/project mcp`. The default local scope applies in that project. [Claude Code MCP](https://code.claude.com/docs/en/mcp) |
| Gemini CLI | Add `taos` under `mcpServers` in the project's `.gemini/settings.json`. Set `command` to `python3`, keep each argument in its own `args` array entry and keep tool confirmations enabled. [Gemini CLI MCP](https://geminicli.com/docs/tools/mcp-server/) |
| VS Code with GitHub Copilot | Run **MCP: Add Server** and choose **Command (stdio)**. Use the workspace scope and review the server before starting it. [VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers) · [TAOS workspace example](MCP.md#connect-a-client) |
| Cursor | Add `taos` under `mcpServers` in the project's `.cursor/mcp.json`. Use `command` and `args` as above and keep tool approvals enabled. [Cursor MCP](https://cursor.com/docs/mcp) |

Start with `status`, then give `why`, `checks` or `handoff` a task ID.
The first three tools show up to six rows with counts and abbreviated
fields. Use the terminal for full records. When `handoff` returns a cursor,
read all pages for the same task and verify the SHA-256 of the assembled
UTF-8 text. Start over if the brief changed. The adapter reads existing
records. Running checks, editing tasks and approving work use separate
routes. [MCP tool reference](MCP.md)

The table records vendor-documented transports. A separate fixture run used
the official Python MCP SDK 2.3.0 over stdio with protocol `2025-06-18`. It
read the four advertised tools, observed a recorded check go from `holds`
to `stale` after a fixture change, matched a paged handoff to the terminal
output byte for byte and observed unchanged file manifests during reads.
Actual operation in each named host's native interface remains unverified.
[Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk) · [Stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)

From the TAOS checkout, reproduce the adapter's protocol, bounded reads and
handoff tests with Python's standard library. The tests use temporary
project fixtures.

```sh
python3 -B -m unittest discover -s tests -p test_mcp_stdio.py -v
```

## 3. Send a context packet to a chat without tools

For example, in a regular ChatGPT conversation, paste a reviewed packet as
an ordinary message. This also works with another text-only reviewer.
TAOS prints a draft in your terminal for you to inspect and send.
[ChatGPT prompting guide](https://help.openai.com/en/articles/10032626-prompt-engineering-best-practices-for-chatgpt)

```sh
./taos capsule AZ-7 --transfer 'Which source rows support this conclusion?' --source observations.csv
```

The packet carries the question, current records and source references.
Explicit `--source` files contribute filenames and SHA-256 hashes. Share
only approved excerpts or files the reviewer needs, using their own
approval route. Read the full packet first because existing instructions
and evidence references can include private details. Use a shareable
project record if the recipient needs a redacted version with a verifiable
identity. Ask the reviewer to treat quoted records as data, cite what they
actually saw and report missing evidence as uncertainty.

Save the returned JSON locally and check it using the same question and
selected source files. Use a freshly checked reply for each decision.

```sh
./taos capsule AZ-7 --transfer 'Which source rows support this conclusion?' --source observations.csv --check-review review.json
```

A matching reply identifies the current packet, question and selected source
bytes. Changed records, mismatched identities or malformed replies are
rejected. A supported, contradicted or uncertain finding is the reviewer's
assessment. Recheck the observations and method before the operator accepts
a finding. The check cannot authenticate the reviewer or prove the conclusion.
On older checkouts without `--transfer`, assemble a shareable packet from
`capsule` and the selected sources, and compare the reply manually.

## When a review matches and the answer is wrong

We gave the same task two questions, two source selections and two recorded versions. That made eight distinct requests. We tried each reply against all eight requests. The checker accepted all eight original pairings and rejected the 56 crossed pairings. Twelve additional cases cover missing sources, revised files, reordered sources and other common handoff mistakes.

One reviewer reported 3 of 4 from the cited table. Counting the rows gave 2 of 4. The checker accepted the reply's identity because the question and source matched. The operator's approval stayed unchanged. A person reviewing that result can go straight to the four rows and decide whether the conclusion holds.

[Read the recorded pairings and controls](../evals/results/followups/review-transfer.json) or [inspect the local experiment](../evals/review_transfer.py). Run it from the repository with `python3 -B evals/review_transfer.py --verify`. The experiment uses locally constructed replies.

## How this relates to research standards

In W3C PROV terms, a source or packet is an **entity**, a check is an
**activity**, and a recorded operator or tool is an **agent** in the
provenance account. The mapping helps a reviewer trace what a check used.
[W3C PROV Data Model](https://www.w3.org/TR/prov-dm/)

Named references and recorded provenance support finding and reusing evidence.
The FAIR principles also allow authorized access where necessary. A hash can
identify the bytes you used. A reusable research deposit additionally needs
appropriate access, metadata, methods, licensing and community standards.
Scientific acceptance still depends on independent review and relevant evidence.
[Original FAIR principles](https://www.nature.com/articles/sdata201618)
