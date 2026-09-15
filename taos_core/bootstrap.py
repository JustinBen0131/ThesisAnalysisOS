"""Construction: eight answers become a working OS, in one pass."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import atoms as atoms_mod
from . import brief as brief_mod
from . import config as config_mod
from . import doctor as doctor_mod
from . import events as events_mod
from . import kernels as kernels_mod
from . import projections as projections_mod
from . import proposals as proposals_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import atomic_write_json, atomic_write_text, locked, read_json, utc_now
from .util import TaosError, slugify, validate_json_schema

BEGIN = "<!-- taos:begin -->"
END = "<!-- taos:end -->"
GUARD_BEGIN = "<!-- taos:bootstrap-guard -->"
GUARD_END = "<!-- /taos:bootstrap-guard -->"

QUESTION_KEYS = (
    "principal_name",
    "timezone",
    "project_name",
    "prefix",
    "workspaces",
    "stack",
    "human_only",
    "secret_patterns",
    "planning_surface",
    "brief_time",
    "panel_port",
    "open_browser",
    "install_hooks_in_workspaces",
    "first_tasks",
    "agent_corrections",
    "agents",
)


def _schema(paths: Paths) -> Dict[str, Any]:
    schema = read_json(paths.bootstrap_dir / "answers.schema.json")
    if not isinstance(schema, dict):
        raise TaosError("bootstrap/answers.schema.json is missing")
    return schema


def validate_answers(answers: Any, paths: Optional[Paths] = None) -> List[str]:
    problems: List[str] = []
    if paths is not None:
        try:
            problems.extend(validate_json_schema(answers, _schema(paths), "answers"))
        except TaosError as exc:
            problems.append(str(exc))
    if not isinstance(answers, dict):
        return problems or ["answers must be a JSON object"]
    if not str(answers.get("principal_name", "")).strip():
        problems.append("principal_name is required (question 1)")
    if not str(answers.get("project_name", "")).strip():
        problems.append("project_name is required (question 2)")
    prefix = str(answers.get("prefix", ""))
    if not re.match(r"^[A-Z][A-Z0-9]{1,7}$", prefix):
        problems.append("prefix must be 2-8 uppercase letters or digits, like AZ or NOIR (question 2)")
    tasks = answers.get("first_tasks")
    if not isinstance(tasks, list) or not tasks:
        problems.append("first_tasks needs at least one task (question 7)")
    else:
        for index, task in enumerate(tasks):
            if not isinstance(task, dict) or not str(task.get("title", "")).strip():
                problems.append("first_tasks[{0}] needs a title".format(index))
    for index, workspace in enumerate(answers.get("workspaces") or []):
        if not isinstance(workspace, dict) or not workspace.get("path"):
            problems.append("workspaces[{0}] needs a path".format(index))
            continue
        if not str(workspace["path"]).startswith("/"):
            problems.append("workspaces[{0}].path must be absolute".format(index))
    return [p for p in problems if p]


def _render(template: str, values: Dict[str, str]) -> str:
    text = template
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _strip_guard(text: str) -> str:
    if GUARD_BEGIN in text and GUARD_END in text:
        head, rest = text.split(GUARD_BEGIN, 1)
        _, tail = rest.split(GUARD_END, 1)
        return (head.rstrip() + "\n" + tail.lstrip("\n")).lstrip("\n")
    return text


def _detect_stack(workspaces: List[Dict[str, Any]]) -> str:
    for workspace in workspaces:
        root = Path(str(workspace.get("path", ""))).expanduser()
        if not root.is_dir():
            continue
        if (root / "Cargo.toml").is_file():
            return "rust-cargo"
        if (root / "package.json").is_file():
            return "node"
        if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
            return "python"
        if (root / "go.mod").is_file():
            return "go"
    return "generic"


def _config_from(answers: Dict[str, Any]) -> Dict[str, Any]:
    config = config_mod.defaults()
    config["constructed_at"] = utc_now()
    config["principal"] = {
        "name": str(answers["principal_name"]).strip(),
        "timezone": str(answers.get("timezone") or "UTC"),
    }
    workspaces = []
    for workspace in answers.get("workspaces") or []:
        workspaces.append(
            {
                "name": str(workspace.get("name") or Path(workspace["path"]).name),
                "path": str(Path(workspace["path"]).expanduser()),
                "primary": bool(workspace.get("primary")),
                "agent": str(workspace.get("agent") or "any"),
            }
        )
    if workspaces and not any(w["primary"] for w in workspaces):
        workspaces[0]["primary"] = True
    config["workspaces"] = workspaces

    stack = str(answers.get("stack") or "").strip() or _detect_stack(workspaces)
    config["project"] = {
        "name": str(answers["project_name"]).strip(),
        "prefix": str(answers["prefix"]).strip(),
        "stack": stack,
    }

    gates = answers.get("gates")
    if isinstance(gates, list) and gates:
        config["gates"] = [
            {"name": str(g.get("name") or g["command"].split()[0]), "command": str(g["command"])}
            for g in gates
            if isinstance(g, dict) and g.get("command")
        ]
    else:
        config["gates"] = [dict(g) for g in config_mod.STACK_GATES.get(stack, [])]

    git = dict(config_mod.DEFAULT_GIT)
    if answers.get("git_isolation"):
        git["isolation"] = str(answers["git_isolation"])
    if answers.get("branch_pattern"):
        git["branch_pattern"] = str(answers["branch_pattern"])
    if isinstance(answers.get("protected_branches"), list) and answers["protected_branches"]:
        git["protected_branches"] = [str(b) for b in answers["protected_branches"]]
    if answers.get("worktree_root"):
        git["worktree_root"] = str(Path(answers["worktree_root"]).expanduser())
    if answers.get("merge_policy"):
        git["merge_policy"] = str(answers["merge_policy"])
    config["git"] = git

    if answers.get("autonomy"):
        config["autonomy"] = str(answers["autonomy"])
    config["attention"] = {
        "max_decisions_per_day": int(answers.get("max_decisions_per_day", 3) or 0),
        "quiet_hours": answers.get("quiet_hours") or None,
    }
    config["self_iteration"] = {
        "cadence": str(answers.get("self_iteration_cadence") or "weekly"),
        "auto_promote_atoms": False,
    }
    if answers.get("agents"):
        config["agents"] = list(answers["agents"])
    if answers.get("human_only"):
        config["human_only"] = list(answers["human_only"])
    if answers.get("secret_patterns"):
        merged = list(config_mod.DEFAULT_SECRET_PATTERNS)
        for pattern in answers["secret_patterns"]:
            if pattern not in merged:
                merged.append(pattern)
        config["secret_patterns"] = merged
    if answers.get("planning_surface"):
        config["planning_surface"] = str(answers["planning_surface"])
    if answers.get("brief_time"):
        config["brief_time"] = str(answers["brief_time"])
    config["panel"] = {
        "port": int(answers.get("panel_port") or 4331),
        "open_browser": bool(answers.get("open_browser", True)),
    }
    config["install_hooks_in_workspaces"] = bool(answers.get("install_hooks_in_workspaces", True))
    return config


def _workspace_block(config: Dict[str, Any]) -> str:
    workspaces = config.get("workspaces") or []
    if not workspaces:
        return "- No separate workspace: the agents work inside this OS clone."
    lines = []
    for workspace in workspaces:
        notes = []
        if workspace.get("primary"):
            notes.append("primary")
        owner = workspace.get("agent") or "any"
        if owner != "any":
            notes.append("reserved for {0}; the other agent may read but never write here".format(owner))
        suffix = " ({0})".format("; ".join(notes)) if notes else ""
        lines.append("- `{0}`{1}".format(workspace["path"], suffix))
    return "\n".join(lines)


def _git_block(config: Dict[str, Any]) -> str:
    git = config.get("git") or {}
    isolation = git.get("isolation", "worktree")
    protected = ", ".join(git.get("protected_branches") or ["main", "master"])
    policy = git.get("merge_policy", "human_pr")
    lines = []
    if isolation == "worktree":
        lines.append(
            "- One `git worktree` per task. `taos start` prints the exact `git worktree add` "
            "command and the path; work there and nowhere else. The worktree path is your claim."
        )
    elif isolation == "branch":
        lines.append("- One branch per task in the workspace. `taos start` prints the `git switch -c` command.")
    elif isolation == "fork":
        lines.append("- Each agent works in its own checkout (see workspaces). Branch inside it per task.")
    else:
        lines.append("- Trunk-based: small commits on the main branch. Keep each commit independently revertible.")
    lines.append("- Branch names follow `{0}`; `taos start` computes the name for you.".format(git.get("branch_pattern")))
    lines.append("- Protected branches: {0}. Never commit on them, never push to them.".format(protected))
    if policy == "human_pr":
        lines.append("- Work reaches the trunk only through a PR the human merges. Open the PR, put the link on the task, stop.")
    elif policy == "agent_after_gates":
        lines.append("- You may merge once every gate passes and the human nods (the guard asks).")
    else:
        lines.append("- Merges to the trunk are allowed with an ask.")
    return "\n".join(lines)


def _gates_block(config: Dict[str, Any]) -> str:
    gates = config.get("gates") or []
    if not gates:
        return "- No gates configured. `taos finish --state review` needs only a reason and evidence."
    lines = ["- Before `review` or `done`, run `taos gate run --agent <you> --task <ID>`. It runs:"]
    for gate in gates:
        lines.append("  - `{0}`  ({1})".format(gate["command"], gate.get("name", "")))
    lines.append("- A failing or missing gate run blocks `finish`. `--skip-gates` exists, is logged, and the guard asks the human about it.")
    return "\n".join(lines)


def _autonomy_block(config: Dict[str, Any]) -> str:
    level = config.get("autonomy", "edit_branches")
    if level == "propose_only":
        return ("- Propose-only: edit freely on task branches, but every commit asks the human "
                "and pushes are refused. Your output is diffs and handoffs.")
    if level == "push_branches_open_prs":
        return ("- You may push task branches and open PRs without asking. Protected branches, "
                "merges, releases, and anything in the human-only list stay with the human.")
    return ("- Commit freely on task branches. Every `git push` asks the human first. "
            "Never push to a protected branch.")


def _attention_block(config: Dict[str, Any]) -> str:
    attention = config.get("attention") or {}
    budget = int(attention.get("max_decisions_per_day") or 0)
    quiet = attention.get("quiet_hours")
    lines = []
    if budget:
        lines.append(
            "- The human answers at most {0} queued decisions a day. Beyond that, yours waits below the line; "
            "keep working on what does not depend on it.".format(budget)
        )
    else:
        lines.append("- Queue decisions freely, but only for judgments a machine genuinely cannot make.")
    if quiet:
        lines.append("- Quiet hours {0}: nothing you do should expect a human answer then.".format(quiet))
    cadence = (config.get("self_iteration") or {}).get("cadence", "weekly")
    if cadence == "daily":
        lines.append("- Proposals and failing atoms surface in every daily brief.")
    elif cadence == "weekly":
        lines.append("- Proposals are reviewed at the weekly `taos retro`; do not nag about them daily.")
    else:
        lines.append("- Proposals wait until the human runs `taos proposals list`. Never nag.")
    return "\n".join(lines)


def _bullets(items: List[str]) -> str:
    return "\n".join("- {0}".format(item) for item in items)


def _absolutize_codex_hooks(paths: Paths) -> None:
    """Codex runs hook commands relative to its cwd; pin them to this clone."""
    source = paths.home / ".codex" / "hooks.json"
    if not source.is_file():
        return
    text = source.read_text(encoding="utf-8")
    pinned = text.replace('"python3 hooks/', '"python3 {0}/hooks/'.format(paths.home))
    if pinned != text:
        atomic_write_text(source, pinned)


def construct(paths: Paths, answers: Dict[str, Any], actor: str = "system") -> Dict[str, Any]:
    problems = validate_answers(answers, paths)
    if problems:
        raise TaosError("answers are not usable yet:\n  - " + "\n  - ".join(problems))

    with locked(paths):
        paths.ensure_state()
        config = _config_from(answers)
        atomic_write_json(paths.config_file, config)

        if not paths.allocator_file.is_file():
            atomic_write_json(
                paths.allocator_file,
                {"schema": tasks_mod.ALLOCATOR_SCHEMA, "prefix": config["project"]["prefix"], "next": 1, "updated_at": utc_now()},
            )
        for path, empty in (
            (paths.tasks_file, {"schema": tasks_mod.TASKS_SCHEMA, "tasks": {}}),
            (paths.claims_file, {"schema": "TAOS_CLAIMS_V1", "claims": []}),
            (paths.decisions_file, {"schema": "TAOS_DECISIONS_V1", "decisions": []}),
        ):
            if not path.is_file():
                atomic_write_json(path, empty)

        values = {
            "principal_name": config["principal"]["name"],
            "project_name": config["project"]["name"],
            "prefix": config["project"]["prefix"],
            "stack": config["project"]["stack"],
            "agents": ", ".join(config["agents"]),
            "workspaces_block": _workspace_block(config),
            "human_only_block": _bullets(config["human_only"]),
            "git_block": _git_block(config),
            "gates_block": _gates_block(config),
            "autonomy_block": _autonomy_block(config),
            "attention_block": _attention_block(config),
            "constructed_at": config["constructed_at"],
        }
        _absolutize_codex_hooks(paths)
        for template_name, target in (
            ("AGENTS.md.tmpl", paths.agents_md),
            ("CLAUDE.md.tmpl", paths.claude_md),
        ):
            template_path = paths.templates_dir / template_name
            if template_path.is_file():
                atomic_write_text(target, _strip_guard(_render(template_path.read_text(encoding="utf-8"), values)))

        for template_name, target in (
            ("PROJECT_KERNEL.md.tmpl", paths.kernels_dir / "PROJECT_KERNEL.md"),
            ("PRINCIPAL_KERNEL.md.tmpl", paths.kernels_dir / "PRINCIPAL_KERNEL.md"),
        ):
            template_path = paths.templates_dir / template_name
            if template_path.is_file():
                atomic_write_text(target, _render(template_path.read_text(encoding="utf-8"), values))

        store = tasks_mod.TaskStore(paths)
        existing_titles = {t.get("title") for t in store.list()}
        created = []
        for item in answers.get("first_tasks") or []:
            title = str(item.get("title", "")).strip()
            if not title or title in existing_titles:
                continue
            task = store.create(
                title=title,
                actor=actor,
                goal=str(item.get("goal") or ""),
                next_action=str(item.get("next_action") or ""),
                priority=str(item.get("priority") or "P2"),
                status="next",
            )
            created.append(task["id"])

        seeded = []
        for correction in answers.get("agent_corrections") or []:
            text = str(correction).strip()
            if not text:
                continue
            proposal = proposals_mod.propose(
                paths,
                kind="atom",
                title=text[:70],
                body=(
                    "{0}\n\nThis came from the principal at setup. Turn it into a checkable "
                    "atom when you have seen it happen once in real work, then propose it "
                    "again with --atom-json so `taos doctor` enforces it.".format(text)
                ),
                evidence=["setup answer 9"],
                agent="system" if actor not in ("codex", "claude") else actor,
            )
            seeded.append(proposal["id"])

    linked = []
    if config.get("install_hooks_in_workspaces") is not None:
        for workspace in config.get("workspaces") or []:
            try:
                linked.append(link_workspace(paths, Path(workspace["path"]), install_hooks=config["install_hooks_in_workspaces"]))
            except TaosError as exc:
                linked.append({"path": workspace["path"], "error": str(exc)})

    for name in ("OS_KERNEL", "PROJECT_KERNEL", "PRINCIPAL_KERNEL"):
        try:
            kernels_mod.index_refresh(paths, name, "taos")
        except TaosError:
            pass
    kernels_mod.generate_now(paths)
    projections_mod.refresh(paths)
    brief_mod.write(paths)
    report = doctor_mod.run(paths)

    events_mod.emit(
        paths,
        "bootstrap_construct",
        actor,
        project=config["project"]["name"],
        prefix=config["project"]["prefix"],
        tasks=len(created),
        workspaces=len(config.get("workspaces") or []),
    )
    return {
        "config": paths.relative(paths.config_file),
        "tasks_created": created,
        "proposals_seeded": seeded,
        "workspaces_linked": linked,
        "doctor": report,
    }


def _upsert_block(path: Path, block: str) -> str:
    """Add or replace our marked block without touching anything else."""
    if path.is_file():
        text = path.read_text(encoding="utf-8")
    else:
        text = ""
    payload = "{0}\n{1}\n{2}".format(BEGIN, block.strip(), END)
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        new_text = head + payload + tail
        action = "updated"
    else:
        separator = "\n\n" if text.strip() else ""
        new_text = text.rstrip() + separator + payload + "\n"
        action = "appended"
    atomic_write_text(path, new_text if new_text.endswith("\n") else new_text + "\n")
    return action


def link_workspace(paths: Paths, workspace: Path, install_hooks: bool = True) -> Dict[str, Any]:
    workspace = Path(workspace).expanduser()
    if not workspace.is_dir():
        raise TaosError("workspace does not exist: {0}".format(workspace))

    template_path = paths.templates_dir / "workspace_block.md.tmpl"
    if not template_path.is_file():
        raise TaosError("missing template: taos_core/templates/workspace_block.md.tmpl")
    config = config_mod.load_soft(paths)
    block = _render(
        template_path.read_text(encoding="utf-8"),
        {
            "taos_home": str(paths.home),
            "project_name": config.get("project", {}).get("name", "this project"),
            "prefix": config.get("project", {}).get("prefix", "TASK"),
        },
    )

    actions = {
        "AGENTS.md": _upsert_block(workspace / "AGENTS.md", block),
        "CLAUDE.md": _upsert_block(workspace / "CLAUDE.md", block),
    }

    installed: List[str] = []
    hooks: Dict[str, str] = {}
    if install_hooks:
        for source_rel, target_rel in (
            (".codex/hooks.json", ".codex/hooks.json"),
            (".claude/settings.json", ".claude/settings.json"),
        ):
            source = paths.home / source_rel
            if not source.is_file():
                continue
            payload = source.read_text(encoding="utf-8").replace("${CLAUDE_PROJECT_DIR}", str(paths.home))
            payload = payload.replace('"python3 hooks/', '"python3 {0}/hooks/'.format(paths.home))
            target = workspace / target_rel
            previous = read_json(workspace / ".taos-link.json", {}) or {}
            ours_before = target_rel in (previous.get("installed") or [])
            if target.exists() and not ours_before:
                snippet = target.with_name(target.stem + ".taos-snippet.json")
                atomic_write_text(snippet, payload)
                hooks[target_rel] = "existing file kept; merge {0} by hand".format(snippet.name)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(target, payload)
                hooks[target_rel] = "written"
                installed.append(target_rel)

    atomic_write_json(
        workspace / ".taos-link.json",
        {"schema": "TAOS_LINK_V1", "taos_home": str(paths.home), "linked_at": utc_now(), "installed": installed},
        mode=0o644,
    )
    events_mod.emit(paths, "workspace_link", "system", workspace=str(workspace), hooks=bool(install_hooks))
    return {"path": str(workspace), "docs": actions, "hooks": hooks}


def _remove_block(path: Path) -> str:
    if not path.is_file():
        return "absent"
    text = path.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        return "no block"
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    new_text = (head.rstrip() + "\n" + tail.lstrip("\n")).strip("\n")
    if new_text.strip():
        atomic_write_text(path, new_text + "\n")
        return "block removed"
    path.unlink()
    return "removed (the file held only our block)"


def unlink_workspace(paths: Paths, workspace: Path) -> Dict[str, Any]:
    """Drop out cleanly: remove exactly what link_workspace added, nothing else."""
    workspace = Path(workspace).expanduser()
    if not workspace.is_dir():
        raise TaosError("workspace does not exist: {0}".format(workspace))
    link = read_json(workspace / ".taos-link.json", {}) or {}
    removed: Dict[str, str] = {
        "AGENTS.md": _remove_block(workspace / "AGENTS.md"),
        "CLAUDE.md": _remove_block(workspace / "CLAUDE.md"),
    }
    for rel in link.get("installed") or []:
        target = workspace / rel
        if target.is_file():
            target.unlink()
            removed[rel] = "removed"
    for snippet in workspace.glob("*/*.taos-snippet.json"):
        snippet.unlink()
        removed[str(snippet.relative_to(workspace))] = "removed"
    if (workspace / ".taos-link.json").is_file():
        (workspace / ".taos-link.json").unlink()
        removed[".taos-link.json"] = "removed"
    events_mod.emit(paths, "workspace_unlink", "human", workspace=str(workspace))
    return {"path": str(workspace), "removed": removed}


PAUSE_FILE = "paused"


def pause(paths: Paths, note: Optional[str] = None) -> Dict[str, Any]:
    """Drop out. The safety floor in the guard stays; the workflow stops asking."""
    paths.ensure_state()
    atomic_write_json(paths.state / PAUSE_FILE, {"paused_at": utc_now(), "note": note or ""}, mode=0o644)
    events_mod.emit(paths, "os_pause", "human", note=note)
    return {"paused": True}


def resume(paths: Paths) -> Dict[str, Any]:
    flag = paths.state / PAUSE_FILE
    if flag.is_file():
        flag.unlink()
    events_mod.emit(paths, "os_resume", "human")
    return {"paused": False}


def is_paused(paths: Paths) -> bool:
    return (paths.state / PAUSE_FILE).is_file()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _answers_path(paths: Paths, given: Optional[str]) -> Path:
    return Path(given) if given else (paths.bootstrap_dir / "answers.json")


def _cmd_questions(args: argparse.Namespace, paths: Paths) -> int:
    path = paths.bootstrap_dir / "QUESTIONS.md"
    if not path.is_file():
        raise TaosError("bootstrap/QUESTIONS.md is missing")
    print(path.read_text(encoding="utf-8"))
    return 0


def _cmd_validate(args: argparse.Namespace, paths: Paths) -> int:
    path = _answers_path(paths, args.answers)
    answers = read_json(path)
    if answers is None:
        raise TaosError("no answers file at {0}. Write one first (see bootstrap/answers.example.json).".format(path))
    problems = validate_answers(answers, paths)
    if problems:
        for problem in problems:
            print("- {0}".format(problem))
        return 1
    print("answers look good. Construct with: taos bootstrap construct")
    return 0


def _cmd_construct(args: argparse.Namespace, paths: Paths) -> int:
    path = _answers_path(paths, args.answers)
    answers = read_json(path)
    if answers is None:
        raise TaosError("no answers file at {0}".format(path))
    report = construct(paths, answers, actor=args.agent)
    print("constructed {0}".format(report["config"]))
    if report["tasks_created"]:
        print("tasks: {0}".format(", ".join(report["tasks_created"])))
    for linked in report["workspaces_linked"]:
        if linked.get("error"):
            print("workspace {0}: {1}".format(linked.get("path"), linked["error"]))
        else:
            print("linked {0} ({1})".format(linked["path"], ", ".join("{0} {1}".format(k, v) for k, v in linked["hooks"].items()) or "docs only"))
    print("")
    print("doctor: {0}".format("green" if report["doctor"]["ok"] else "failing"))
    for check in report["doctor"]["checks"]:
        if check["status"] != "pass":
            print("  {0} {1}: {2}".format(check["status"], check["name"], check["detail"]))
    return 0


def _cmd_link(args: argparse.Namespace, paths: Paths) -> int:
    result = link_workspace(paths, Path(args.path), install_hooks=not args.no_hooks)
    print("linked {0}".format(result["path"]))
    for name, action in result["docs"].items():
        print("  {0}: {1}".format(name, action))
    for name, action in result["hooks"].items():
        print("  {0}: {1}".format(name, action))
    return 0


def _cmd_unlink(args: argparse.Namespace, paths: Paths) -> int:
    result = unlink_workspace(paths, Path(args.path))
    print("unlinked {0}".format(result["path"]))
    for name, action in result["removed"].items():
        print("  {0}: {1}".format(name, action))
    return 0


def _cmd_pause(args: argparse.Namespace, paths: Paths) -> int:
    pause(paths, args.note)
    print("paused. Agents keep the safety floor (secrets, force pushes, the store, the cage) and drop the ceremony.")
    print("resume with: taos resume")
    return 0


def _cmd_resume(args: argparse.Namespace, paths: Paths) -> int:
    resume(paths)
    print("resumed.")
    return 0


def _cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    if not paths.constructed():
        print(config_mod.NOT_CONSTRUCTED)
        return 0
    config = config_mod.load(paths)
    print("project:   {0} ({1}-)".format(config["project"]["name"], config["project"]["prefix"]))
    print("principal: {0}".format(config["principal"]["name"]))
    print("agents:    {0}".format(", ".join(config.get("agents", []))))
    for workspace in config.get("workspaces") or []:
        print("workspace: {0}{1}".format(workspace["path"], " (primary)" if workspace.get("primary") else ""))
    print("constructed {0}".format(config.get("constructed_at")))
    return 0


def register(subparsers: Any) -> None:
    bootstrap = subparsers.add_parser("bootstrap", help="set this OS up for one person")
    sub = bootstrap.add_subparsers(dest="bootstrap_cmd", required=True)

    questions = sub.add_parser("questions", help="print the questions to ask")
    questions.set_defaults(func=_cmd_questions)

    validate = sub.add_parser("validate", help="check an answers file")
    validate.add_argument("--answers")
    validate.set_defaults(func=_cmd_validate)

    construct_parser = sub.add_parser("construct", help="build the OS from answers")
    construct_parser.add_argument("--answers")
    construct_parser.add_argument("--agent", default="system", choices=list(events_mod.AGENTS))
    construct_parser.set_defaults(func=_cmd_construct)

    link = sub.add_parser("link-workspace", help="point a repo at this OS")
    link.add_argument("path")
    link.add_argument("--no-hooks", action="store_true")
    link.set_defaults(func=_cmd_link)

    unlink = sub.add_parser("unlink-workspace", help="remove exactly what link-workspace added")
    unlink.add_argument("path")
    unlink.set_defaults(func=_cmd_unlink)

    status = sub.add_parser("status", help="what was constructed")
    status.set_defaults(func=_cmd_status)

    pause_parser = subparsers.add_parser("pause", help="drop out: keep the safety floor, stop the ceremony")
    pause_parser.add_argument("--note")
    pause_parser.set_defaults(func=_cmd_pause)

    resume_parser = subparsers.add_parser("resume", help="drop back in")
    resume_parser.set_defaults(func=_cmd_resume)
