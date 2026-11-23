# Documentation map

Find a guide by task. Pick the row that matches what you came to do.

> [!TIP]
> New here? Run `./taos demo` first. It runs a temporary example, touches nothing of yours, and shows the four
> answers a result can get: `holds`, `stale`, `fails` or `unknown`.

## Start

| You want to | Read | Time |
|---|---|---|
| See what it does | [The front page](../README.md), then [the playable version](https://whatstillholds.com/) | 2 min |
| Use it on your own folder | [The manual](../MANUAL.md) | 10 min |
| Set up the full system with an AI agent | [BOOTSTRAP.md](../BOOTSTRAP.md), given to the agent as its first message | 15 min |
| Plan work on a workstation, a cluster or a cloud budget | [Decide what needs to run](../policies/HPC.md) | 10 min |

## Work with AI agents

| You want to | Read |
|---|---|
| Give a planner, a builder and a reviewer their own names | [Bring another agent into a project](AGENT_ROLES.md) |
| Let a web assistant review a handoff you choose to share | [Bring another assistant into a research task](AGENT_INTERFACES.md) |
| Read a project from an MCP client | [Read a TAOS project from an MCP client](MCP.md) |
| Know the six rules every screen follows | [The interface, in six rules](INTERFACE.md) |

## Check the evidence

Each study is a small controlled example with its saved run in `evals/results/` and one command that reproduces it.

| Question | Read |
|---|---|
| Which claims are tested, and by what? | [Claims](CLAIMS.md) |
| Does the old receipt still support the measurement? | [Measurement audit](MEASUREMENT_AUDIT.md) |
| Which pendulum result can the next task inherit? | [Handoff audit](HANDOFF_AUDIT.md) |
| Can an unchanged pooled score hide a failure on one instrument? | [Model evaluation](MODEL_EVALUATION.md) |
| What happens when assistants pass results to each other? | [Exchange simulation](EXCHANGE_SIMULATION.md) |
| How does a morning service report continue across shifts? | [Transit workflow](TRANSIT_WORKFLOW.md) |

## Understand or change the system

| You want to | Read |
|---|---|
| Find where each idea lives in the code | [Architecture](ARCHITECTURE.md), "Reading this repository cold" |
| Know why it is built this way, with the measurements | [The method](METHOD.md) |
| Follow the binding specification | [Build specification](SPEC.md) |
| See what carried over from the first version | [Lineage](LINEAGE.md) |
| Propose a change | [Contributing](../CONTRIBUTING.md) |
| Report a security concern, or share a research record safely | [Security](../SECURITY.md) |

## If you are an AI agent

Do not set the system up before reading. [AGENTS.md](../AGENTS.md) says so in its first section.
[The guide for AI agents](https://whatstillholds.com/llms.txt) lists the same documents with the commands
that verify each claim.
