# ThesisAnalysisOS — Build Specification (v1)

This is the binding contract for every file in this repository. Builders,
reviewers, and future agents modifying the OS read this first. Where prose
elsewhere disagrees with this file, this file wins until it is amended.

## 0. What this is, in one paragraph

ThesisAnalysisOS ("TAOS") is a local-first, zero-dependency operating layer
that lets one human ("the principal") run two coding agents (OpenAI Codex and
Anthropic Claude Code) as interchangeable peers over the same durable work
state. It gives the agents one task store with stable IDs, scope-local claims
so they never collide, a handoff format so a session can die without losing
the work, a daily brief and a local panel so the human sees truth without
reading files, and a small self-iteration loop (correction atoms, kernels,
proposals, burns) so the system gets tighter instead of heavier over time. It
was distilled from a year of running the same design on a physics thesis with
both agents in daily use. Everything is plain files under one directory; the
human can switch the panel on and off at will and delete the directory to
uninstall.

## 1. Design laws (binding)

1. **Files are canonical; every surface is a projection.** The panel, the
   brief, the hot-work rail, and anything an agent says are projections of
   `.taos/`. A projection may never be edited to fix a defect in the store.
2. **The tool allocates identity.** Task IDs (`<PREFIX>-<N>`) are allocated
   only by `taos_core.tasks`. Hand-written IDs are phantoms and the doctor
   flags them.
3. **One store, event-sourced.** Tasks live in `tasks.json`; every mutation
   appends to `events.jsonl` first. There is no second "register" that can
   drift from the catalogue. (Lesson: two stores produced phantom rows.)
4. **Claims are scope-local mutexes with heartbeats.** A live claim held by
   the other agent on an overlapping scope is do-not-touch. Reading is free.
   Stale takeover is explicit, requires a reason, and is logged.
5. **Agent brand is provenance, never authority.** `agent: codex|claude` on
   every event, comment, claim, and label. No rule may branch on brand.
6. **Evidence over memory.** `done`, `review`, and `blocked` transitions
   require a reason; `done` requires at least one evidence pointer. Nothing is
   "finished" because a chat said so.
7. **Hot Work is selective on entry, persistent on lifecycle.** A task becomes
   hot when a human or agent starts it; it stays hot until done, canceled,
   archived, or explicitly cooled.
8. **Decision cards only for real human judgments.** Agents ask through the
   decision queue, not by stalling in chat. The brief shows at most two.
9. **Death by default for soma.** Handoffs, proposals, old briefs, and
   scratch carry a TTL. Burns archive, verify the archive by restore, and only
   then delete. Germline (code, policies, tasks, claims, events, atoms,
   kernels, config) is never burn fuel. Uncertainty means keep.
10. **Corrections compound.** When the principal corrects an agent twice for
    the same thing, the agent proposes an atom (a checkable rule). Promoted
    atoms run in `taos doctor`. Prose lessons that cannot be checked are
    written into the relevant kernel instead.
11. **Truth is two clicks away and nothing animates.** Every panel element
    maps to a store row; stale data is shown as stale ("fog"), never
    interpolated; no points, XP, streaks, badges, or scores of people/agents.
12. **Hard stops are symmetric and never waived by urgency.** See
    `policies/HARD_STOPS.md`.
13. **Zero tokens for the loop.** Brief, doctor, projections, NOW kernel,
    freshness, burns, and the panel are deterministic Python. No scheduled
    model calls, no polling agents.
14. **stdlib only, Python 3.9+.** No pip, no network, no third-party imports
    anywhere in `taos_core/`, `hooks/`, or `tests/`. Every module starts with
    `from __future__ import annotations`; no `match` statements; no
    `X | Y` runtime unions; use `typing.Optional`/`List`/`Dict`.

## 2. Repository layout

```
ThesisAnalysisOS/                # the OS home (this clone)
  taos                           # launcher: #!/usr/bin/env python3 -> taos_core.cli.main
  taos_core/                     # the runtime (stdlib only)
    __init__.py  paths.py  store.py  config.py  events.py  tasks.py  util.py
    claims.py  lifecycle.py  handoff.py  decisions.py  proposals.py
    telemetry.py  projections.py  brief.py  doctor.py  kernels.py  atoms.py
    burn.py  panel.py  bootstrap.py  cli.py
    panel_assets/panel.html      # single-file UI (inline CSS/JS, no CDN)
    templates/AGENTS.md.tmpl  CLAUDE.md.tmpl  workspace_block.md.tmpl
              PROJECT_KERNEL.md.tmpl  PRINCIPAL_KERNEL.md.tmpl
  hooks/                         # shared by Codex and Claude (same contract)
    guard.py                     # PreToolUse: deny/ask/allow
    session_start.py             # SessionStart: inject `taos status --compact`
    stop_labels.py               # Stop: parse `<!-- ep: ... -->` -> label row
  .claude/settings.json          # hooks + deny/ask permissions for Claude Code
  .claude/skills/<name>/SKILL.md # Claude skills (identical content to .agents)
  .codex/hooks.json              # hooks for Codex
  .codex/config.toml             # minimal project config for Codex
  .agents/skills/<name>/SKILL.md # Codex skills
  AGENTS.md                      # agent control plane (<= 12 KB); Codex reads it
  CLAUDE.md                      # `@AGENTS.md` import + Claude notes
  BOOTSTRAP.md                   # the single-pass setup an agent follows
  MANUAL.md                      # the human's instruction manual
  README.md  LICENSE  .gitignore
  bootstrap/QUESTIONS.md         # the 8 questions, each with a default
  bootstrap/answers.schema.json  # JSON Schema (draft 2020-12 subset)
  bootstrap/answers.example.json # a complete example answer file
  bootstrap/presets/<stack>.json # rust-cargo, node, python, generic
  policies/HARD_STOPS.md  OPERATING_LOOP.md  CLAIMS.md  HANDOFFS.md
           SELF_ITERATION.md  EVIDENCE.md  PANEL.md
  kernels/KERNEL_INDEX.json      # fingerprints + max ages
  kernels/OS_KERNEL.md           # how TAOS works (static, shipped)
  kernels/PROJECT_KERNEL.md      # generated at bootstrap, agent-maintained
  kernels/PRINCIPAL_KERNEL.md    # generated at bootstrap, sanitized prefs
  kernels/NOW_KERNEL.md          # regenerated deterministically by `taos kernel now`
  atoms/promoted_atoms.json      # checkable correction rules (seeded)
  docs/SPEC.md (this file)  docs/ARCHITECTURE.md  docs/LINEAGE.md
  tests/test_*.py                # unittest; `./taos selftest`
  .github/workflows/ci.yml       # unittest on ubuntu + macos, py3.9 + py3.12
  .taos/                         # RUNTIME STATE, git-ignored, created by bootstrap
```

`.taos/` layout (all created lazily; all JSON pretty-printed, sorted keys):

```
.taos/config.json                # from bootstrap answers (schema below)
.taos/tasks.json                 # {"schema":"TAOS_TASKS_V1","tasks":{id:Task}}
.taos/allocator.json             # {"schema":"TAOS_ALLOCATOR_V1","prefix":"AZ","next":1}
.taos/events.jsonl               # append-only; one JSON object per line
.taos/claims.json                # {"schema":"TAOS_CLAIMS_V1","claims":[Claim]}
.taos/decisions.json             # {"schema":"TAOS_DECISIONS_V1","decisions":[Decision]}
.taos/proposals/<id>.json        # Proposal objects
.taos/handoffs/<ts>_<task>_<from>_to_<to>.md
.taos/telemetry/labels.jsonl     # sanitized episode labels
.taos/projections/hot_work.json  # derived
.taos/projections/status.json    # derived
.taos/projections/brief.json     # derived
.taos/projections/brief.md       # derived
.taos/briefs/<date>.md           # history (soma, TTL 14 d)
.taos/cold/<date>.tar.gz + <date>.manifest.json   # burn archives
.taos/scratch/                   # agent scratch (soma, TTL 7 d)
.taos/panel.pid  .taos/panel.token  .taos/panel.log
.taos/.lock                      # single writer lock (fcntl)
```

## 3. Identity and time

- `utc_now()` returns `YYYY-MM-DDTHH:MM:SSZ` (second precision, UTC).
- Every event has `id` = first 12 hex of sha256(canonical json of the event
  without `id`), `ts`, `type`, `agent`, plus type-specific fields.
- Task IDs match `^[A-Z][A-Z0-9]{1,7}-[1-9][0-9]*$`.
- Claim IDs: `clm_` + 10 hex. Decision IDs: `dec_` + 10 hex. Proposal IDs:
  `prop_` + 10 hex. Handoff filenames use `%Y%m%dT%H%M%SZ`.
- Agents: `codex`, `claude`, `human`, `system`. Sessions are free text
  labels of the form `<TASK-ID> | <short label>` when a task is known.

## 4. Store schemas

### 4.1 config.json (TAOS_CONFIG_V1)

```json
{
  "schema": "TAOS_CONFIG_V1",
  "constructed_at": "2026-09-15T00:00:00Z",
  "principal": {"name": "Max", "timezone": "America/New_York"},
  "project": {"name": "Noir", "prefix": "AZ", "stack": "rust-cargo"},
  "workspaces": [{"name": "noir", "path": "/abs/path", "primary": true}],
  "agents": ["codex", "claude"],
  "human_only": ["deploy or release", "merge to main", "sign or broadcast a transaction", "touch keys, seed phrases, or secrets", "spend money", "message people on my behalf"],
  "secret_patterns": ["\\.env$", "\\.pem$", "id_rsa", "id_ed25519", "\\.key$", "keystore", "seed", "mnemonic", "\\.secret"],
  "planning_surface": "none",
  "brief_time": "08:30",
  "panel": {"port": 4331, "open_browser": true},
  "ttl_days": {"handoffs": 30, "briefs": 14, "scratch": 7, "proposals_closed": 30},
  "claim_stale_hours": 6,
  "install_hooks_in_workspaces": true
}
```

### 4.2 Task (in tasks.json under `tasks[id]`)

```json
{
  "id": "AZ-7", "title": "…", "status": "active", "priority": "P1",
  "goal": "…", "next_action": "…", "parent_id": null, "labels": [],
  "relations": {"blocks": [], "blockedBy": [], "relatedTo": []},
  "owner_agent": "codex", "hot": true, "hot_since": "…", "hot_reason": "started",
  "created_at": "…", "updated_at": "…", "created_by": "human",
  "evidence": [{"ts": "…", "agent": "codex", "ref": "path-or-url-or-note", "note": "…"}],
  "comments": [{"ts": "…", "agent": "codex", "session": "AZ-7 | …", "body": "…"}],
  "sessions": [{"ts": "…", "provider": "codex", "session_key": "az7-fix-ssa", "title": "AZ-7 | fix ssa"}],
  "history": [{"ts": "…", "from": "next", "to": "active", "reason": "…", "agent": "codex"}],
  "done_at": null, "canceled_at": null, "archived_at": null
}
```

Statuses: `backlog`, `next`, `active`, `blocked`, `waiting`, `review`,
`done`, `canceled`, `archived`. Terminal: `done`, `canceled`, `archived`.
Priorities: `P0`..`P3` (default `P2`).

Allowed transitions (from -> to): any non-terminal -> any non-terminal;
non-terminal -> `done|canceled`; `done|canceled` -> `archived`; any terminal
-> `next` only with `--reopen`. `done` requires `evidence` non-empty (the
transition may add one via `--evidence`). `blocked` requires reason naming the
blocker. Every transition appends to `history` and emits `task_transition`.

### 4.3 Claim

```json
{"id": "clm_…", "agent": "codex", "scopes": ["task:AZ-7", "path:compiler/noirc_evaluator"],
 "session_label": "AZ-7 | fix ssa", "claimed_at": "…", "heartbeat_at": "…",
 "stale_after_hours": 6, "status": "live", "released_at": null, "takeover_of": null}
```

Scope grammar: `<kind>:<value>` with kind in `task`, `path`, `repo`, `policy`,
`panel`, `kernel`, `atoms`, `burn`. Values are exact strings; no globs or
shell metacharacters (`*?[]{}$\``). Two scopes conflict when equal, or when
both are `path:` and one is a prefix directory of the other.
A claim is **live** while `status == "live"` and `heartbeat_at + stale_after_hours >= now`.
A claim is **stale** when live-by-status but past heartbeat. Acquire fails
(`ClaimConflict`) when any scope conflicts with a live claim of a *different*
agent; the same agent re-acquiring overlapping scopes returns the existing
claim after refreshing its heartbeat. `--takeover --reason "…"` succeeds only
against stale claims: it marks them `taken_over`, emits `claim_takeover`, and
records `takeover_of`. Release emits `claim_release`. Reading never needs a
claim.

### 4.4 Event (events.jsonl)

Required: `id`, `ts`, `type`, `agent`. Types used by the core:
`task_create`, `task_update`, `task_transition`, `task_comment`,
`task_relate`, `task_session_map`, `task_hot`, `claim_acquire`,
`claim_heartbeat`, `claim_release`, `claim_takeover`, `decision_ask`,
`decision_answer`, `proposal_create`, `proposal_decide`, `handoff_write`,
`label`, `brief_render`, `kernel_now`, `kernel_index`, `burn_plan`,
`burn_execute`, `burn_recall`, `panel_on`, `panel_off`, `bootstrap_construct`,
`workspace_link`, `doctor`, `note`. Unknown types are allowed.

### 4.5 Decision

```json
{"id": "dec_…", "task_id": "AZ-7", "question": "…", "options": ["a", "b"],
 "asked_by": "codex", "asked_at": "…", "status": "open",
 "answer": null, "answered_by": null, "answered_at": null, "note": null}
```

### 4.6 Proposal

```json
{"id": "prop_…", "kind": "atom|policy|kernel|retire|cleanup|other",
 "title": "…", "body": "…", "evidence": ["…"], "proposed_by": "claude",
 "proposed_at": "…", "status": "proposed|accepted|rejected", "decided_by": null,
 "decided_at": null, "note": null, "atom": null}
```
`atom` optionally carries a complete Atom object (4.8) so acceptance can
promote it with `taos atoms promote <prop_id>`.

### 4.7 Label (telemetry/labels.jsonl) — sanitized only

```json
{"ts": "…", "agent": "claude", "task_id": "az7-fix-ssa", "phase": "start|iterate|handoff|done|abandoned",
 "outcome": "landed|reworked|corrected|blocked|unknown", "modality": "code|docs|planning|review|ops|mixed|unknown",
 "task": "short sanitized descriptor", "counterpart": "codex|claude|null"}
```
`task_id` must match `^[a-z0-9][a-z0-9-]{2,60}$`; `task` is truncated to 80
chars and stripped of URLs and anything matching `secret_patterns`. Rows with
unknown keys are rejected.

### 4.8 Atom (atoms/promoted_atoms.json)

```json
{"schema": "TAOS_ATOMS_V1", "atoms": [{
  "id": "handoff-header-required", "status": "active",
  "rule": "Every handoff starts with the four-line attribution header.",
  "why": "…", "review_date": "2026-12-31",
  "check": {"type": "regex_must_match", "target": "latest_handoff", "pattern": "^Agent: (codex|claude)\\n"},
  "fixtures": {"red": "…text that must FAIL…", "green": "…text that must PASS…"}
}]}
```
Check types: `regex_must_match`, `regex_must_not_match` (target = a repo
relative file path, or the virtual targets `latest_handoff`, `agents_md`,
`claude_md`), `file_must_exist`, `taos_command_exit_zero` (argv list; first
element must be `taos`; executed in-process, never via a shell). `fixtures`
are optional; when present `taos atoms check` also verifies red fails and
green passes against the pattern (self-test of the atom). A virtual target
that does not exist yet (no handoff written) counts as `ok` with detail
`no target yet`.

### 4.9 KERNEL_INDEX.json

```json
{"schema": "TAOS_KERNEL_INDEX_V1", "kernels": [
 {"name": "OS_KERNEL", "path": "kernels/OS_KERNEL.md", "sources": ["taos_core/*.py", "policies/*.md", "AGENTS.md"], "max_age_days": 30, "fingerprint": "sha256…", "generated_at": "…", "generator": "shipped|agent|taos"},
 {"name": "PROJECT_KERNEL", "path": "kernels/PROJECT_KERNEL.md", "sources": [".taos/config.json"], "max_age_days": 30, …},
 {"name": "PRINCIPAL_KERNEL", "path": "kernels/PRINCIPAL_KERNEL.md", "sources": [".taos/config.json"], "max_age_days": 60, …},
 {"name": "NOW_KERNEL", "path": "kernels/NOW_KERNEL.md", "sources": [".taos/tasks.json", ".taos/claims.json", ".taos/decisions.json"], "max_age_days": 1, …}
]}
```
Fingerprint = sha256 over sorted (relative path + file sha256) of expanded
sources (globs via `glob.glob(recursive=True)`; missing files skipped).
Freshness statuses: `fresh`, `drifted` (fingerprint mismatch), `aged`
(older than max_age_days), `missing`.

## 5. Python API (module by module)

All functions raise `TaosError(message)` (subclass of `RuntimeError`,
defined in `taos_core/util.py`) on user-facing failures; the CLI maps it to
exit 1 with the message on stderr. `ClaimConflict(TaosError)` carries
`.claims` (the blocking claims) and maps to exit 4.

**Every module that owns CLI verbs exposes `register(subparsers) -> None`**
adding its subcommands and setting `parser.set_defaults(func=<callable>)`
where the callable has signature `func(args: argparse.Namespace, paths: Paths) -> int`.
`cli.py` only aggregates: it builds the top-level parser, resolves `Paths`,
calls every module's `register`, dispatches, and maps exceptions to exit
codes. Read-only verbs must work without `--agent`.

### util.py
```python
class TaosError(RuntimeError): ...
def validate_json_schema(value, schema: dict, path: str = "$") -> List[str]
    # supports: type (incl. list of types), required, properties, additionalProperties(False),
    # enum, const, pattern, minLength, maxLength, minItems, maxItems, uniqueItems, items, minimum, maximum
def short_id(prefix: str) -> str        # prefix + 10 hex from secrets.token_hex
def slugify(text: str, max_len: int = 60) -> str
def strip_secrets(text: str, patterns: List[str]) -> str   # also strips URLs
```

### paths.py
```python
class Paths:  # plain class; all attributes are pathlib.Path
    home; state; config_file; tasks_file; allocator_file; events_file
    claims_file; decisions_file; proposals_dir; handoffs_dir; telemetry_dir
    labels_file; projections_dir; briefs_dir; cold_dir; scratch_dir
    panel_pid; panel_token; panel_log; lock_file; kernels_dir; kernel_index
    atoms_file; policies_dir; agents_md; claude_md; templates_dir
    def __init__(self, home: Path)
    @classmethod
    def discover(cls, start: Optional[Path] = None) -> "Paths"
        # order: $TAOS_HOME env -> walk up from start (default cwd) looking for a dir
        # containing both the `taos` launcher and `taos_core/`; else TaosError.
    def ensure_state(self) -> None   # mkdir -p every state dir (0o700 for state root)
    def constructed(self) -> bool    # config_file exists
```

### store.py
```python
def utc_now() -> str
def parse_ts(ts: str) -> datetime            # aware UTC
def canonical_json(value) -> str             # sort_keys, compact separators
def sha256_text(text: str) -> str
def sha256_file(path: Path) -> str
def read_json(path: Path, default=None) -> Any   # default returned when missing; TaosError on malformed
def atomic_write_json(path: Path, value, mode: int = 0o600) -> None   # tmp + fsync + os.replace
def atomic_write_text(path: Path, text: str, mode: int = 0o644) -> None
def append_jsonl(path: Path, row: dict) -> None
def read_jsonl(path: Path) -> List[dict]     # skips blank lines; TaosError on bad row
@contextmanager
def locked(paths: Paths, timeout: float = 15.0)   # fcntl.flock on lock_file; re-entrant within a process; TaosError on timeout
```

### config.py
```python
DEFAULTS: dict                                # the 4.1 shape without principal/project/workspaces
def load(paths: Paths) -> dict                # TaosError("TAOS not constructed. Read BOOTSTRAP.md and follow it.") when missing
def validate(config: dict) -> List[str]       # returns problems (empty = ok)
def prefix(paths: Paths) -> str
def secret_patterns(paths: Paths) -> List[str]   # config value or DEFAULTS when not constructed
```

### events.py
```python
def emit(paths: Paths, type: str, agent: str, **fields) -> dict   # appends; returns row with id/ts
def read(paths: Paths, since: Optional[str] = None, types: Optional[List[str]] = None, limit: Optional[int] = None) -> List[dict]
def register(subparsers) -> None   # `taos events`, `taos event note`
```

### tasks.py
```python
STATUSES, TERMINAL, PRIORITIES, ID_RE, MUTABLE_FIELDS
class TaskStore:
    def __init__(self, paths: Paths)
    def load(self) -> dict                    # tasks.json content (creates empty store + allocator on first use, prefix from config)
    def get(self, task_id: str) -> dict       # TaosError if missing
    def list(self, status: Optional[str] = None, hot: Optional[bool] = None) -> List[dict]  # order: hot first, then priority, then numeric id
    def find(self, query: str) -> List[dict]  # case-insensitive substring on id/title/goal/labels
    def create(self, *, title, actor, goal="", next_action="", priority="P2", parent_id=None, labels=None, status="next") -> dict
    def update(self, task_id, fields: dict, actor) -> dict     # only MUTABLE_FIELDS = title, goal, next_action, priority, parent_id, labels
    def transition(self, task_id, to: str, reason: str, actor, evidence: Optional[str] = None, reopen: bool = False) -> dict
    def comment(self, task_id, body: str, agent: str, session: str, evidence: Optional[str] = None) -> dict
    def add_evidence(self, task_id, ref: str, agent: str, note: str = "") -> dict
    def relate(self, task_id, kind: str, other_id: str, actor, remove: bool = False) -> dict   # symmetric
    def map_session(self, task_id, provider: str, session_key: str, title: str, actor) -> dict
    def set_hot(self, task_id, hot: bool, reason: str, actor) -> dict
    def blockers(self, task_id) -> List[str]  # open blockedBy ids (+ parent id if parent is blocked)
def register(subparsers) -> None   # `taos task …`
```
Every mutating method: takes `locked(paths)`, emits the event **before**
writing the store, validates, writes atomically, returns the fresh task dict.
`create` allocates the id via allocator.json inside the same lock.

### claims.py
```python
class ClaimConflict(TaosError): claims: List[dict]
class ClaimStore:
    def __init__(self, paths: Paths)
    def all(self) -> List[dict]
    def live(self, now: Optional[str] = None) -> List[dict]
    def stale(self, now: Optional[str] = None) -> List[dict]
    def acquire(self, *, agent, scopes: List[str], session_label: str, stale_after_hours: Optional[float] = None, takeover: bool = False, reason: Optional[str] = None, now: Optional[str] = None) -> dict
    def heartbeat(self, claim_id: str, agent: str, now=None) -> dict
    def release(self, claim_id: str, agent: str, now=None, force: bool = False) -> dict   # holder only unless force (human)
    def release_by_scope(self, scope: str, agent: str) -> List[dict]
    def check(self, scopes: List[str], agent: str, now=None) -> List[dict]  # blocking live claims of other agents
def normalize_scopes(scopes: List[str]) -> List[str]   # validates grammar, sorts, dedups
def scopes_conflict(a: str, b: str) -> bool
def register(subparsers) -> None   # `taos claim …`
```

### lifecycle.py
```python
def start(paths, *, agent, task_id, session_label, extra_scopes=None, stale_after_hours=None, takeover=False, reason=None) -> dict
    # 1 map_session 2 acquire claim [task:<id>]+extra 3 transition to active if in backlog/next/waiting/review (reason "started by <agent>") 4 set_hot 5 projections.refresh 6 telemetry label phase=start 7 return capsule(paths, task_id)
def finish(paths, *, agent, task_id, state: str, reason: str, evidence: Optional[str], session_label: str, handoff_file: Optional[Path] = None, to_agent: Optional[str] = None, comment: Optional[str] = None) -> dict
    # 1 optional comment 2 transition 3 optional handoff.write 4 release claims held by agent whose scopes include task:<id> 5 if terminal: set_hot False 6 refresh 7 label phase=done|handoff|iterate 8 return summary
def capsule(paths, task_id) -> dict   # task, blockers, live claims on it, open decisions for it, latest handoff path + first 40 lines, related task titles, next_action, kernel freshness summary
def capsule_text(capsule: dict) -> str
def register(subparsers) -> None   # `taos start`, `taos finish`, `taos capsule`
```

### handoff.py
```python
HEADER_RE  # ^Agent: (codex|claude|human)\nChat/session: .+\nTask: [A-Z][A-Z0-9]{1,7}-[0-9]+ \| .+\nClaim/scope: .+\n
REQUIRED_SECTIONS = ["## State", "## Changed", "## Evidence", "## Risks and open questions", "## Next command"]
def template(task: dict, from_agent, to_agent, session) -> str
def validate(text: str) -> List[str]         # problems
def write(paths, *, task_id, from_agent, to_agent, body: str, session: str) -> Path   # validates; emits handoff_write; adds task comment "handoff -> <path>"
def latest(paths, task_id) -> Optional[Path]
def wrapper(path: Path, to_agent: str, summary_lines: List[str]) -> str   # the paste-ready text box
def register(subparsers) -> None   # `taos handoff …`
```

### decisions.py / proposals.py
```python
def ask(paths, *, task_id, question, options: List[str], agent) -> dict
def answer(paths, *, decision_id, choice, by="human", note=None) -> dict   # choice must be in options unless options empty
def open_decisions(paths, task_id=None) -> List[dict]
def register(subparsers) -> None   # `taos decide …`
# proposals.py
def propose(paths, *, kind, title, body, evidence: List[str], agent, atom: Optional[dict] = None) -> dict
def decide(paths, *, proposal_id, status, by="human", note=None) -> dict
def open_proposals(paths) -> List[dict]
def all_proposals(paths) -> List[dict]
def register(subparsers) -> None   # `taos propose`, `taos proposals …`
```

### telemetry.py
```python
MARKER_RE = r"<!--\s*ep:\s*(.*?)\s*-->"
def parse_marker(text: str) -> Optional[dict]
def sanitize(row: dict, secret_patterns: List[str]) -> dict   # TaosError on invalid
def label(paths, **fields) -> dict
def register(subparsers) -> None   # `taos label`
```

### projections.py / brief.py
```python
def refresh(paths) -> dict        # writes hot_work.json, status.json; returns status
def compact_status(paths, max_lines: int = 25) -> str   # for SessionStart injection
def hot_work(paths) -> List[dict]
def register(subparsers) -> None   # `taos status`
# brief.py
def build(paths, since: Optional[str] = None) -> dict   # {generated_at, top_line, decisions_owed, changed[], hot[], blocked[], claims{live,stale}, kernels[], atoms{pass,fail}, burn_candidates, proposals_open, doctor_summary}
def render_markdown(brief: dict) -> str
def write(paths) -> Path          # writes brief.json + brief.md + briefs/<date>.md; emits brief_render
def register(subparsers) -> None   # `taos brief`, `taos retro`
```
`top_line` is exactly `No action needed.` when there are zero open decisions,
zero stale claims, zero blocked hot tasks, and doctor is green; otherwise
`N item(s) need you.` followed by the items.

### kernels.py / atoms.py / burn.py / doctor.py
```python
def freshness(paths) -> List[dict]           # per kernel: name, status, reasons
def index_refresh(paths, name: str, generator: str) -> dict   # recompute fingerprint + generated_at for one kernel
def generate_now(paths) -> Path              # deterministic NOW_KERNEL.md from state; refreshes its index row
def regen_prompt(paths, name: str) -> str    # prompt an agent runs to regenerate PROJECT/PRINCIPAL/OS kernel
def register(subparsers) -> None             # `taos kernel …`
# atoms.py
def load(paths) -> dict
def check(paths) -> List[dict]               # id, ok, detail
def promote(paths, proposal_id, by) -> dict  # copies proposal.atom into atoms file (status active), marks proposal accepted
def register(subparsers) -> None             # `taos atoms …`
# burn.py
def plan(paths, now=None) -> List[dict]      # candidates: path, category, age_days, ttl_days, sha256
def execute(paths, date: str, approve: bool) -> dict   # refuses unless approve; archive -> manifest -> restore-verify in temp -> delete
def recall(paths, date: str) -> dict         # restore; conflicts to <path>.recalled
def register(subparsers) -> None             # `taos burn …`
# doctor.py
def run(paths) -> dict                       # {"ok": bool, "checks": [{"name","status":"pass|warn|fail","detail"}]}
def register(subparsers) -> None             # `taos doctor`, `taos selftest`, `taos version`
```
Doctor checks (names fixed): `config`, `stores_parse`, `allocator_monotonic`,
`task_ids_valid`, `relations_resolve`, `terminal_done_evidence`, `claims_schema`,
`claims_stale`, `hot_work_consistent`, `kernels_fresh`, `atoms`, `panel_process`,
`hooks_installed`, `secrets_in_state`, `soma_ttl`. `fail` makes `ok` false;
`warn` does not. When not constructed, doctor returns ok=False with a single
`config` fail whose detail is the bootstrap line.

### panel.py
```python
def on(paths, port: Optional[int] = None, open_browser: Optional[bool] = None) -> dict   # spawns `python3 -m taos_core.panel --serve --home <home> --port N` detached (start_new_session=True, cwd=home, PYTHONPATH=home); writes pid + token (secrets.token_hex(16), mode 0600); waits until /api/health answers (<= 5 s); emits panel_on
def off(paths) -> dict                       # SIGTERM pid, wait <= 5 s, SIGKILL fallback, remove pidfile; emits panel_off
def status(paths) -> dict                    # running, pid, port, url
def serve(paths, port: int, token: str) -> None   # ThreadingHTTPServer bound to 127.0.0.1 only
def register(subparsers) -> None             # `taos panel …`
```
HTTP: `GET /` -> panel.html with the token injected as `window.TAOS_TOKEN`;
`GET /api/health`; `GET /api/state` (tasks, hot, claims, decisions, proposals,
handoffs list, kernels, atoms, brief, doctor summary, config subset, server
time); `GET /api/task/<id>`; `GET /api/handoff?path=<rel>` (only under
handoffs_dir); `GET /api/brief.md`; `POST /api/decide` `{id, choice, note}`;
`POST /api/task/transition` `{id, to, reason, evidence}`; `POST /api/task/hot`
`{id, hot, reason}`; `POST /api/proposal/decide` `{id, status, note}`;
`POST /api/claim/release` `{id}`; `POST /api/refresh` (runs projections + brief).
All POSTs require header `X-TAOS-Token: <token>` and, when present, an
`Origin` starting with `http://127.0.0.1:` or `http://localhost:`; actor is
`human`. No other endpoints; unknown paths 404; never serve arbitrary files.

### bootstrap.py
```python
QUESTION_KEYS = ["principal_name", "timezone", "project_name", "prefix", "workspaces", "stack", "human_only", "secret_patterns", "planning_surface", "brief_time", "panel_port", "open_browser", "install_hooks_in_workspaces", "first_tasks", "agent_corrections", "agents"]
def validate_answers(answers: dict) -> List[str]
def construct(paths, answers: dict, *, actor="system") -> dict
    # idempotent. writes .taos/config.json; allocator with prefix; empty stores;
    # renders AGENTS.md + CLAUDE.md from templates (removing the bootstrap guard block);
    # writes kernels PROJECT/PRINCIPAL from answers + index rows; NOW via generate_now;
    # seeds agent_corrections as proposals of kind atom (not promoted); creates first_tasks
    # (all status next, none hot) unless a task with the same title exists;
    # links workspaces (install_hooks per answer); runs projections.refresh + brief.write + doctor;
    # emits bootstrap_construct; returns report {config_path, tasks_created, workspaces_linked, doctor}
def link_workspace(paths, workspace: Path, *, install_hooks: bool) -> dict
    # appends (idempotently, between markers `<!-- taos:begin -->`/`<!-- taos:end -->`) a short block to AGENTS.md and CLAUDE.md in the workspace (creating the files if absent, never truncating existing content); if install_hooks: writes .codex/hooks.json and .claude/settings.json ONLY when absent, otherwise writes .taos-hooks.snippet.json next to them and reports "merge manually"; writes `.taos-link.json` with the absolute OS home; emits workspace_link
def register(subparsers) -> None   # `taos bootstrap …`
```

### cli.py
```python
def main(argv: Optional[List[str]] = None) -> int
```
Global flags: `--home PATH` (overrides discovery), `--json` (machine output
where supported), `--agent {codex,claude,human,system}` (required by mutating
task/claim commands; not required by read-only commands). Exit codes: 0 ok,
1 user error (TaosError), 2 usage error (argparse), 3 doctor failed (for
`doctor`), 4 claim conflict.

## 6. CLI grammar (exact)

```
taos status [--compact] [--json]
taos doctor [--json]
taos selftest                                # python -m unittest discover -s tests
taos version

taos task create --agent A --title T [--goal G] [--next-action N] [--priority P0..P3] [--parent ID] [--label L]... [--status next|backlog]
taos task show ID [--json]
taos task list [--status S] [--hot] [--json]
taos task find QUERY [--json]
taos task update ID --agent A --set key=value...        # keys: title goal next_action priority parent_id labels(csv)
taos task transition ID --agent A --to STATE --reason R [--evidence E] [--reopen]
taos task comment ID --agent A --session S --body B [--evidence E]
taos task evidence ID --agent A --ref REF [--note N]
taos task relate ID --agent A blocks|blockedBy|relatedTo OTHER [--remove]
taos task map-session ID --agent A --provider codex|claude --session-key KEY --title T
taos task hot ID --agent A (--on | --off) --reason R

taos claim status [--json]
taos claim acquire --agent A --scope S... --session S [--stale-after-hours H] [--takeover --reason R]
taos claim heartbeat --agent A --id CLM
taos claim release --agent A (--id CLM | --scope S) [--force]
taos claim check --agent A --scope S...

taos start --agent A --task ID --session S [--scope S]... [--takeover --reason R]
taos finish --agent A --task ID --state review|done|blocked|waiting|next --reason R [--evidence E] --session S [--handoff-file F --to codex|claude] [--comment C]
taos capsule ID [--json]

taos handoff template ID --from A --to B --session S       # prints template to stdout
taos handoff write ID --from A --to B --session S (--file F | --stdin)
taos handoff latest ID [--print]
taos handoff wrapper PATH --to B [--summary LINE]...

taos decide ask --agent A --task ID --question Q [--option O]...
taos decide answer DEC --choice C [--note N] [--by human]
taos decide list [--task ID] [--json]

taos propose --agent A --kind K --title T --body B [--evidence E]... [--atom-json FILE]
taos proposals list [--all] [--json]
taos proposals decide PROP --status accepted|rejected [--note N]

taos label --agent A --task-id SLUG --phase P [--outcome O] [--modality M] [--task TEXT] [--counterpart A2]
taos event note --agent A --text T [--task ID]
taos events [--since TS] [--type T]... [--limit N] [--json]

taos brief [--print] [--json]
taos retro [--days 7] [--json]           # stats + auto-proposals (kind retire/cleanup)
taos kernel freshness [--json]
taos kernel now
taos kernel regen-prompt PROJECT_KERNEL|PRINCIPAL_KERNEL|OS_KERNEL
taos kernel refresh NAME --generator agent|human
taos atoms check [--json]
taos atoms promote PROP --by human
taos burn plan [--json]
taos burn execute --date YYYY-MM-DD --approve
taos burn recall --date YYYY-MM-DD

taos panel on [--port N] [--no-open]
taos panel off
taos panel status [--json]

taos bootstrap questions                 # prints QUESTIONS.md
taos bootstrap validate [--answers F]     # default bootstrap/answers.json
taos bootstrap construct [--answers F]
taos bootstrap link-workspace PATH [--no-hooks]
taos bootstrap status
```

`taos status --compact` output (used by SessionStart hooks), max 25 lines:

```
TAOS <project> | <today UTC> | constructed <date>
Hot: AZ-7 P1 active codex "title" next: …
     AZ-9 P0 blocked - "title" blocked_by: AZ-4
Decisions owed: 1 (dec_ab12: "…")
Claims live: codex task:AZ-7 (age 12m) | stale: none
Kernels: OS fresh, PROJECT fresh, PRINCIPAL fresh, NOW aged
Doctor: green | Proposals open: 2 | Latest brief: 2026-09-15
Rule: map the prompt to a task, then `./taos start --agent <you> --task <ID> --session "<ID> | <label>"`.
```
When not constructed: exactly `TAOS not constructed. Read BOOTSTRAP.md and follow it.`

## 7. Hooks (shared Codex/Claude contract)

Both agents send PreToolUse JSON on stdin with `tool_name` and `tool_input`
(`tool_input.command` for shell). Both accept on stdout
`{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow|deny|ask", "permissionDecisionReason": "…"}}`
and treat exit code 2 as a block with the reason on stderr. The scripts must
work with either runtime and must never crash the agent: any internal error
-> exit 0 with no output (fail-open on hook bugs, fail-closed on rules).
Scripts locate the OS home via `$TAOS_HOME`, then `$CLAUDE_PROJECT_DIR`, then
their own file location (`hooks/..`), then `.taos-link.json` in cwd or its
parents (a linked workspace). If no home is found they still enforce the
default deny list.

`hooks/guard.py` decisions (evaluated in order; first match wins):

DENY (permanent):
- reading, printing, catting, copying, or editing any path matching
  `secret_patterns` from config (fallback to the default list when config is
  missing) or `~/.ssh`, `~/.aws`, `~/.gnupg`, `.env*`, `*.pem`, `*.key`,
  `id_rsa*`, `id_ed25519*`, `keystore*`, `*mnemonic*`, `*seed*phrase*`;
- `git push --force`, `git push -f`, `--force-with-lease`, `git reset --hard`
  when the command also names `origin/` or `main|master`, `git branch -D`,
  `git filter-branch`; any `rm -rf` whose target is `/`, `~`, `.`, `..`,
  `*`, contains `$`, or is outside the OS home's `.taos/scratch` or a
  `worktrees/` dir; `sudo`, `chmod -R 777`, `curl … | sh`, `wget … | sh`;
  `docker push`, `npm publish`, `cargo publish`, `gh release create`,
  `terraform apply`, `kubectl apply`, `aws ` mutations; anything matching
  `broadcast|sendRawTransaction|eth_sendTransaction|--broadcast`; billing
  verbs (`buy credits|purchase|subscribe|upgrade plan|add payment`).
- editing `.taos/tasks.json`, `.taos/claims.json`, `.taos/events.jsonl`,
  `.taos/allocator.json` directly (tool_name Edit/Write/MultiEdit/apply_patch
  with those paths, or shell redirection into them). The CLI is the only writer.
- editing `hooks/guard.py`, `hooks/session_start.py`, `hooks/stop_labels.py`,
  `.claude/settings.json`, `.codex/hooks.json` (the cage does not widen
  itself; the human edits these).

ASK:
- `git push` (non-force), `git commit --amend`, `git merge` into
  `main|master`, `git tag`; `rm -r`/`rm -rf` on anything not denied above;
  `taos burn execute`; `taos claim acquire --takeover` and `taos start …
  --takeover`; writes to files under a workspace's `.github/`; `pip install`,
  `npm install -g`, `brew install`, `cargo install`; `crontab`, `launchctl`;
  `kill`/`pkill` except `taos panel off`.

ALLOW: everything else, with no output (so the runtime's own permission
system applies).

`hooks/session_start.py`: imports `taos_core.projections.compact_status`
(sys.path insert of the OS home; never a shell) and prints
`{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<text>"}}`.
If not constructed, the text is the bootstrap line.

`hooks/stop_labels.py`: reads stdin JSON; takes `last_assistant_message`, or
`final_message`, or the last assistant text in `transcript_path` if present;
parses the marker; appends one sanitized label row via `telemetry.label`; exits 0
always. Marker format (documented in AGENTS.md):
`<!-- ep: id=<slug> phase=<start|iterate|handoff|done|abandoned> outcome=<landed|reworked|corrected|blocked|unknown> modality=<code|docs|planning|review|ops|mixed|unknown> [counterpart=codex|claude] -->`

`.claude/settings.json`: `permissions.deny` for secret reads and the store
files; `permissions.ask` for git push, rm -r; hooks: PreToolUse (matcher
`Bash|Edit|Write|MultiEdit`) -> guard.py, SessionStart -> session_start.py,
Stop -> stop_labels.py. Commands use `python3 "$CLAUDE_PROJECT_DIR/hooks/…"`.

`.codex/hooks.json`: same three events with the same scripts, commands
relative to the repo (`python3 hooks/guard.py`), `timeout` 20.
`.codex/config.toml`: `[features]` with `hooks = true` and
`project_doc_max_bytes = 65536`, with a comment explaining each key.

## 8. Bootstrap (single pass)

`bootstrap/QUESTIONS.md` has exactly 8 numbered questions. Each shows the
key it fills, a one-line reason, and a default. The agent asks all 8 in one
message and accepts `defaults` (or `default` for a single item). Questions:

1. Your name and timezone. (`principal_name`, `timezone`; default: from `$USER`, system tz)
2. Project name and task prefix. (`project_name`, `prefix`; default: name of the primary workspace folder; prefix = first 2-4 letters upper)
3. Workspaces: absolute paths of the repos the agents will work in, and which is primary. (`workspaces`; default: none, meaning the OS home itself)
4. Stack preset: rust-cargo | node | python | generic. (`stack`; default: auto-detect from the primary workspace: Cargo.toml -> rust-cargo, package.json -> node, pyproject/requirements -> python)
5. Human-only actions: confirm or edit the default list. (`human_only`; default list in 4.1)
6. Secret patterns to permanently deny, beyond the default list. (`secret_patterns`; default: the list in 4.1)
7. Your first 3 to 7 tasks, one per line as `title :: next action`. (`first_tasks`; no default; at least 1)
8. Daily rhythm: brief time (local), panel port, auto-open browser, install hooks into workspaces, agents you use. (`brief_time` 08:30, `panel_port` 4331, `open_browser` true, `install_hooks_in_workspaces` true, `agents` ["codex","claude"])

Optional 9 (only if the principal volunteers it): "Things AI agents keep
getting wrong for you" -> `agent_corrections` (seeded as proposals of kind
`atom`).

`answers.schema.json` is a draft-2020-12 subset that `util.validate_json_schema`
enforces. `answers.example.json` validates and constructs cleanly in tests.
`first_tasks` items are objects `{"title": "…", "next_action": "…", "priority": "P2"}`.
`workspaces` items are `{"name": "…", "path": "/abs", "primary": true}`.

`BOOTSTRAP.md` is written for the agent, imperative, and short (< 6 KB):
verify (`python3 --version`, `./taos selftest`), ask, write answers,
validate, construct, show doctor + MANUAL "Day 1", start the first task, stop.
It states what the agent must not do during bootstrap.

## 9. Documents

- `AGENTS.md` (<= 12 KB, rendered from `taos_core/templates/AGENTS.md.tmpl`
  with `{{principal_name}}`, `{{project_name}}`, `{{prefix}}`,
  `{{workspaces_block}}`, `{{human_only_block}}`, `{{agents}}` placeholders;
  the shipped pre-construct `AGENTS.md` is the template rendered with
  placeholders shown as `<not constructed yet>` and the guard block present).
  Sections in order: `Bootstrap guard` (only present before construct),
  `Who you are here`, `First reflex` (status, map, start), `Claims`, `Work
  loop`, `Finish and handoff`, `Decisions`, `Hard stops` (summary + link),
  `Self-iteration` (corrections -> proposals; weekly retro), `Where things
  live`, `Commands you will use` (the 10 most common, exact), `Episode marker`.
- `CLAUDE.md`: first line `@AGENTS.md`, then a 10-line Claude section: hooks
  are installed; skills available; if imports are unsupported read AGENTS.md
  first.
- `MANUAL.md` (the human's manual, <= 30 KB): What you get; Install (60
  seconds); Day 1; The daily loop (morning/working/evening); Working with two
  agents; Correcting an agent so it compounds; The panel (each tab); The
  brief; Weekly (retro, kernels, burns); Turning it off and on; What lives
  where; Uninstall; Troubleshooting; FAQ.
- `README.md` (<= 8 KB): what/why/for whom (unofficial personal prototype,
  not affiliated with any employer), 60-second start, the paste-for-your-agent
  block, architecture sketch, lineage paragraph, license.
- `policies/*.md`: each <= 4 KB, imperative, no project-specific content.
- `docs/ARCHITECTURE.md`: reader-facing tour; `docs/LINEAGE.md`: what was
  kept, what was cut, and why (from the thesis OS), no private details.
- `kernels/OS_KERNEL.md`: <= 1.5k tokens, advisory, how TAOS works.

## 10. Panel (`taos_core/panel_assets/panel.html`)

Single file, inline CSS/JS, no external requests, works at 400 px. Tabs in
fixed order: Today, Work, Claims, Decisions, Handoffs, Atlas. Polls
`/api/state` every 5 s; renders diffs without moving existing cards (fixed
geography). Light and dark via `prefers-color-scheme`. Every card: id, title,
priority chip, status chip, owner chip, next action, blockers, stale badge
when `updated_at` older than 3 days, and a `raw` link to `/api/task/<id>`.
Cards wrap: `min-width:0; overflow-wrap:anywhere; word-break:break-word`.
Today = top line + decisions (max 2) + changed since last brief + hot rail.
Work = columns next/active/blocked/waiting/review (+ backlog and done
collapsed). Claims = table with age and stale flag and a release button (ask
confirm). Decisions = cards with option buttons + note. Handoffs = list, view,
"copy wrapper" button. Atlas = kernels freshness, atoms check, proposals with
accept/reject, burn candidates, doctor checks, config subset. No metrics of
people. No animation except a 150 ms fade on new cards.

## 11. Tests (unittest, `tests/`)

Each test uses a temp dir as OS home: copy the repo's `taos` launcher,
`taos_core/`, `hooks/`, `kernels/`, `atoms/`, `policies/`, `bootstrap/`,
`AGENTS.md`, `CLAUDE.md` into the temp dir (helper `tests/helpers.py`
`make_home(tmp) -> Paths` and `construct_example(paths) -> dict`; the
`lifecycle` lane owns `tests/helpers.py`). Required test files and minimum
coverage:

- `test_store.py`: atomic write, jsonl append/read, lock timeout.
- `test_tasks.py`: allocation monotonic across threads, transitions incl.
  done-requires-evidence, relations symmetric, find, order.
- `test_claims.py`: conflict by exact scope and path prefix, same-agent
  re-acquire, heartbeat, stale detection, takeover requires stale + reason,
  release by holder only.
- `test_lifecycle.py`: start creates session map + claim + active + hot;
  finish releases, transitions, writes handoff, labels; capsule content.
- `test_handoff.py`: template validates; missing header rejected; wrapper text.
- `test_decisions_proposals.py`.
- `test_projections_brief.py`: hot ordering, top line exact strings.
- `test_kernels_atoms_burn.py`: fingerprint drift, NOW generation, atom
  check with fixtures red/green, burn plan/execute/recall round trip with
  sha256 verification and protected paths refused.
- `test_doctor.py`: green on fresh construct; phantom task id -> fail;
  stale claim -> warn.
- `test_bootstrap.py`: example answers validate; construct twice is
  idempotent; AGENTS.md rendered without the guard block and within size;
  link_workspace appends idempotently and never truncates; hooks written
  only when absent.
- `test_panel.py`: serve on port 0 in a thread; health; state; POST without
  token -> 403; with token -> decision answered; unknown path 404; path
  traversal on handoff endpoint refused.
- `test_hooks.py`: guard denies secret read, force push, store edits, cage
  edits; asks on git push; allows `ls`; malformed stdin -> exit 0 no output;
  session_start prints bootstrap line when not constructed; stop_labels
  appends one row for a valid marker and nothing for none.
- `test_cli.py`: `taos status --compact` before/after construct; `--json`
  outputs parse; exit codes 1/4.

`./taos selftest` must pass on macOS and Linux with Python 3.9 and 3.12 in
under 60 s.

## 11a. Amendments in v1.0 (binding)

Added after the first end-to-end run, all driven by the principal's answers:

- **Lanes.** `workspaces[].agent` is `codex`, `claude`, or `any`. The guard
  (`hooks/guard.py --agent <name>`) denies the other agent's writes, redirects,
  `git -C`, and `cd` into a reserved workspace. `lifecycle.lane_for` sends an
  agent to its own lane first, then the primary workspace.
- **Git discipline.** `config.git = {isolation: worktree|branch|fork|trunk,
  branch_pattern, protected_branches, worktree_root, merge_policy:
  human_pr|agent_after_gates|trunk}`. `start` computes the branch (and worktree
  path in worktree mode), records `task.branch/worktree/workspace`, claims
  `branch:<name>` and `path:<worktree>`, and prints the exact git commands in
  the capsule. The guard refuses pushes to protected branches, asks before a
  commit made while on one, and applies the merge policy to `git merge` and
  `gh pr merge`.
- **Gates.** `config.gates = [{name, command}]`, defaulted per stack.
  `taos gate run --agent A --task ID [--workspace P]` runs them in the task's
  worktree (or workspace when the worktree does not exist yet), writes
  `.taos/gates/<ID>_<ts>.json`, and attaches evidence. `finish --state
  review|done` refuses without a passing run in the last 24 h unless
  `--skip-gates` (recorded as evidence; the guard asks).
- **Autonomy.** `config.autonomy = propose_only|edit_branches|push_branches_open_prs`
  changes the guard: pushes denied / asked / allowed to non-protected branches;
  `propose_only` also asks on every commit.
- **Attention.** `config.attention.max_decisions_per_day`; decisions beyond it
  carry `over_budget: true`. `config.self_iteration.cadence` shapes the brief
  and AGENTS.md wording; atoms are never auto-promoted.
- **Drop-out.** `taos pause [--note]` / `taos resume` write or remove
  `.taos/paused`; the compact status and SessionStart hook then tell agents to
  work without ceremony, and the guard applies only the permanent denials.
  `taos bootstrap unlink-workspace PATH` removes exactly what linking added
  (`.taos-link.json.installed` records which hook files were ours).
- **Codex hook paths** are pinned to the absolute clone path at construct.
- **Codex argv lists** in `tool_input.command` are accepted by the guard.
- **Routed policies.** `policies/ROUTING.yaml` (`always` + `routes.<name>.
  {triggers, load, first_actions}`) is the index; `taos_core/policy.py`
  parses it with a minimal YAML subset (mappings, block lists, inline lists,
  scalars; no dependency) and exposes `taos policy route|list|show|check`.
  `check` fails on a missing target or an orphan policy file; the doctor
  runs it as `policies_resolve`, and the atom `policy-layer-resolves` pins it.
  AGENTS.md's first reflex is `status --compact`, then `policy route`, then
  place the request. The policy set is: HARD_STOPS, OPERATING_LOOP, CLAIMS,
  HANDOFFS, EVIDENCE, SELF_ITERATION, PANEL, REPO_SPLIT, DUPLICATE_WORK,
  DECOMPOSITION, CONTEXT, REVIEW, GIT, GATES; each under a page.
- **Repo split.** The OS is re-homed as the person's private repo (BOOTSTRAP
  step zero); a work repo receives only the marked block, `.taos-link.json`,
  and hook files written only when absent. `policies/REPO_SPLIT.md`.

## 11b. Amendments in v1.1: reference frame and the control law

- **Reference frame.** `bootstrap/REFERENCE.md` is agent-only, first on the
  bootstrap read order, never sent to the human. It carries the sanitized
  picture of the reference instance at scale, the day it produced, what was
  cut and why, worked examples of every artifact the agent must write
  (project and principal kernels, handoff, atom, decision, first tasks), how
  to read question-0 pushback, and the explicit statement that it is
  reference, not template. Tests forbid private paths, physics vocabulary,
  and real names in it.
- **Control law.** `taos_core/control.py`, `policies/CONTROL.md` (in the
  `always` read set). Config `control = {enabled, beta, lambda, min_evidence,
  step, observed_profile}`; old configs get defaults. `start` opens an
  episode (`control_open` event: compact state z, recommended profile, bands,
  params, version) and prints a `control:` line in the capsule; `finish`
  closes it (`control_close` event: raw outcome vector with nulls for
  unobservable telemetry, J, progress, cost, clean flag). Profiles `lean`,
  `balanced`, `careful`, `frontier`. Recommendation = mean J per (class,
  profile) with priors at cold start + beta * sqrt(ln(1+N_class)/(1+N_profile))
  + bounded biases; deterministic tie-break. Addendum: J = progress − cost
  with no separate reuse term (continuation value is not yet modelled, and a
  reuse term would double count when it is); the vector carries a
  `provenance` map (observed / unavailable) and the controller's own
  overhead; the bonus is documented as a heuristic; episodes opened as
  `probe` are tagged `evidence_kind: probe` and counted apart from
  observational ones, with no causal claim from observation. Setup answers
  seed priors (`preference.exploration` → beta, `resources.compute` →
  compute_bias). Tasks carry optional `done_when` and `verification`;
  evidence rows may carry an artifact validity contract (`depends_on`,
  `dependencies_known`, `valid`, `invalidated`); `taos task invalidate`
  flips it.
- **Token telemetry** (`taos_core/usage.py`, `bootstrap/rates.json`). Adapters
  read what the hosts already write: Claude `message.usage` per assistant row
  in `~/.claude/projects/<slug>/<session>.jsonl`; Codex `payload.usage` in
  `token_usage_record` rows under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
  (reasoning already inside `output_tokens`, reported never re-added). Both
  are per-response deltas, verified against Codex's own `thread_token_usage`.
  `probe()` runs at construct, records `config.telemetry.token_usage` per
  agent and emits `usage_probe`; `window()` fills the control vector's token
  fields with `observed` provenance and cost with `estimated`, or leaves
  nulls. Scanning is bounded by mtime filter, `MAX_FILES` 40, `MAX_BYTES` 8 MiB
  tail. `taos usage probe|show`. Tuning moves `compute_bias`,
  `verify_bias` by a fixed step after `min_evidence` comparable outcomes;
  `beta` decays with total evidence; all clamped. Derived state
  `.taos/projections/control.json` is produced only by replay of the event
  log (`rebuild`, also on every close), guarded against hand edits, checked
  by the doctor (`control_state`). `taos control status|explain|rebuild|
  frontier`. SessionStart injects one status line. `pause` suppresses it.
  Never written into a linked workspace.

## 12. Builder ownership (parallel build)

| Lane | Owns exactly these files |
|---|---|
| core | `taos_core/__init__.py`, `paths.py`, `store.py`, `config.py`, `events.py`, `util.py`, `tasks.py`, `tests/test_store.py`, `tests/test_tasks.py` |
| claims | `taos_core/claims.py`, `telemetry.py`, `decisions.py`, `proposals.py`, `tests/test_claims.py`, `tests/test_decisions_proposals.py` |
| lifecycle | `taos_core/lifecycle.py`, `handoff.py`, `cli.py`, `taos` (launcher), `tests/helpers.py`, `tests/test_lifecycle.py`, `tests/test_handoff.py`, `tests/test_cli.py` |
| projections | `taos_core/projections.py`, `brief.py`, `doctor.py`, `kernels.py`, `atoms.py`, `burn.py`, `tests/test_projections_brief.py`, `tests/test_kernels_atoms_burn.py`, `tests/test_doctor.py` |
| panel | `taos_core/panel.py`, `taos_core/panel_assets/panel.html`, `policies/PANEL.md`, `tests/test_panel.py` |
| bootstrap | `taos_core/bootstrap.py`, `taos_core/templates/*`, `bootstrap/*`, `BOOTSTRAP.md`, `tests/test_bootstrap.py` |
| docs | `AGENTS.md`, `CLAUDE.md`, `MANUAL.md`, `README.md`, `LICENSE`, `.gitignore`, `policies/*.md` except PANEL.md, `kernels/OS_KERNEL.md`, `kernels/KERNEL_INDEX.json`, `kernels/PROJECT_KERNEL.md` + `PRINCIPAL_KERNEL.md` + `NOW_KERNEL.md` placeholders, `atoms/promoted_atoms.json`, `docs/ARCHITECTURE.md`, `docs/LINEAGE.md`, `.github/workflows/ci.yml` |
| hooks | `hooks/guard.py`, `hooks/session_start.py`, `hooks/stop_labels.py`, `.claude/settings.json`, `.codex/hooks.json`, `.codex/config.toml`, `.claude/skills/*`, `.agents/skills/*`, `tests/test_hooks.py` |

Rules: never write a file another lane owns; import only the signatures in
§5; every shipped module must import cleanly when the other lanes' real
modules are present; run `python3 -m py_compile` on every file you write and
run your own tests before returning (a test that fails only because another
lane's module is not yet present is reported, not hidden). The integrator
runs the full suite and fixes cross-lane seams.
