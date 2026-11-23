# Read a TAOS project from an MCP client

<sub><b>Work with AI agents · 3 of 4</b> &nbsp;·&nbsp; [← Outside assistants](AGENT_INTERFACES.md) &nbsp;·&nbsp; [All documents](README.md) &nbsp;·&nbsp; [Interface rules →](INTERFACE.md)</sub>

A local Model Context Protocol client can pick up a project brief and inspect its evidence over standard input and output. The server exits when the client closes its pipe. It runs with Python 3.9 or later and the standard library.

| Tool | Arguments | Answer |
| --- | --- | --- |
| `status` | `{}` | Whether the project is set up or paused, counts by task state, and up to six tasks with their next actions |
| `why` | `{"task_id":"AZ-1"}` | The task’s standing, whether it was closed or accepted, and what each verdict rests on |
| `checks` | `{"task_id":"AZ-1"}` | Each recorded check’s standing on the current files, its reason and its last run time when available |
| `handoff` | `{"task_id":"AZ-1"}`, then optionally `cursor` | The same brief a terminal user reads with `./taos capsule AZ-1`, including the next action, applicable instructions and available handoff |

Use an ID from `status` or `./taos task list`. Each tool returns one JSON object as text. In `status`, `why` and `checks`, `total` counts all rows. The first six appear. For `why` and `checks`, failed, stale and unknown results appear ahead of those that hold. Long fields in those tools are shortened to 180 characters. Read the full record with `./taos why AZ-1 --json` or `./taos gate show --task AZ-1 --json`.

`handoff` returns up to 2,400 Unicode characters at a time. Append each `text` to the previous page and pass `next_cursor` with the same task ID until it is null. Read the assembled brief before acting on an instruction. The SHA-256 covers the whole UTF-8 brief. If the brief changes between reads, the server asks the client to start again.

## Connect a client

For VS Code, open the TAOS project directory as the workspace. In its `.vscode/mcp.json`, add this server, then start `taos` from the MCP server list.

```json
{
  "servers": {
    "taos": {
      "type": "stdio",
      "command": "python3",
      "args": ["-B", "${workspaceFolder}/taos", "--home", "${workspaceFolder}", "mcp"]
    }
  }
}
```

For another stdio client, set the executable to `python3` and use the arguments `-B /absolute/path/to/taos --home /absolute/path/to/project mcp`, passing each argument as its own array element. Absolute paths work from any client working directory. Use `python` if that is the name of your Python 3 interpreter. The `-B` flag also keeps Python from writing bytecode in the checkout.

The server advertises MCP version `2025-06-18` and marks its tools read-only. It compares the project's recorded evidence with the files on disk through the same readers as the CLI. In a Git workspace that comparison uses a fixed `git ls-files` invocation. Check execution, task edits and project setup belong to the CLI. Connect a project whose handoff text, tasks, instructions and evidence references you intend the client to read.
