"""Construction: eight answers become a working OS, in one pass."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import brief as brief_mod
from . import config as config_mod
from . import doctor as doctor_mod
from . import events as events_mod
from . import kernels as kernels_mod
from . import projections as projections_mod
from . import proposals as proposals_mod
from . import tasks as tasks_mod
from .paths import Paths
from .store import atomic_write_json, atomic_write_text, locked, read_json, sha256_file, sha256_text, utc_now
from .util import TaosError, validate_json_schema

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
    agents = answers.get("agents", list(config_mod.DEFAULT_AGENTS))
    problems.extend(config_mod.roster_problems(agents))
    for index, workspace in enumerate(answers.get("workspaces") or []):
        if not isinstance(workspace, dict) or not workspace.get("path"):
            problems.append("workspaces[{0}] needs a path".format(index))
            continue
        owner = workspace.get("agent", "any")
        if owner != "any" and (not isinstance(agents, list) or owner not in agents):
            problems.append(f"workspaces[{index}].agent must be any or a name in agents")
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
            dict({"name": str(g.get("name") or g["command"].split()[0]), "command": str(g["command"])},
                 **{key: g[key] for key in ("depends_on", "isolated") if g.get(key)})
            for g in gates
            if isinstance(g, dict) and g.get("command")
        ]
    else:
        config["gates"] = [dict(g) for g in config_mod.STACK_GATES.get(stack, [])]
    domains = answers.get("domains")
    if isinstance(domains, list) and domains:
        # which files each check reads: a check is rerun only when one of them changes
        config["basis"] = dict(config.get("basis") or {}, domains={
            str(d["name"]): [str(pattern) for pattern in d["patterns"]]
            for d in domains if isinstance(d, dict) and d.get("name") and d.get("patterns")})

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
    resources = dict(config_mod.DEFAULTS["resources"])
    if isinstance(answers.get("resources"), dict):
        resources.update({k: v for k, v in answers["resources"].items() if v is not None})
    config["resources"] = resources
    preference = dict(config_mod.DEFAULTS["preference"])
    if isinstance(answers.get("preference"), dict):
        preference.update({k: v for k, v in answers["preference"].items() if v is not None})
    config["preference"] = preference
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


HOOK_FILES = (".codex/hooks.json", ".claude/settings.json")

# These are the untouched, unconstructed files distributed in the public clone.
# A guard marker, heading or file name alone is never proof of ownership.
STARTER_DIGESTS = {
    "AGENTS.md": "f7ff9cad2c36e679eac5727f05d8c021f28de22ca735b40661853cac7bfa1d0f",
    "CLAUDE.md": "99b7f7a1fb2a7041f7deee3659fb53551341d9d67149c549bef60701e9b26378",
    "kernels/PROJECT_KERNEL.md": "999c64dcb56f6147ef5d4474e37ce8a0e0ceb6c587aaa9b520d94d8a8b16a371",
    "kernels/PRINCIPAL_KERNEL.md": "182db639d1d10c59456b85471fbd1ce14e67c4b7c88f1a58c0826752a4bc5db3",
}


def _cli(paths: Paths) -> str:
    return shlex.join([str(paths.launcher), "--home", str(paths.home)])


def _pin_hook(paths: Paths, command: str) -> str:
    for name in ("guard.py", "session_start.py", "stop_labels.py"):
        script = "hooks/" + name
        path = str(paths.home / script)
        # The last spelling was emitted by earlier setups even for paths with spaces.
        prefixes = ("python3 " + script, 'python3 "${CLAUDE_PROJECT_DIR}/' + script + '"', "python3 " + path)
        for prefix in prefixes:
            if command == prefix or command.startswith(prefix + " "):
                return "python3 " + shlex.quote(path) + command[len(prefix):]
    return command


def _hook_payload(paths: Paths, source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    try:
        settings = json.loads(text)
        changed = False
        for groups in settings.get("hooks", {}).values():
            for group in groups:
                for hook in group.get("hooks", []):
                    command = hook.get("command", "")
                    pinned = _pin_hook(paths, command)
                    if pinned != command:
                        hook["command"] = pinned
                        changed = True
        return json.dumps(settings, indent=2, ensure_ascii=False) + "\n" if changed else text
    except (ValueError, AttributeError, TypeError) as exc:
        raise TaosError("check the hook settings in {0}: {1}".format(source, exc))


def _render_home_files(paths: Paths, config: Dict[str, Any], previous: Dict[str, Any],
                       values: Dict[str, str]) -> List[str]:
    generated = {}
    kept = []
    for rel, starter_digest in STARTER_DIGESTS.items():
        target = paths.home / rel
        template = paths.templates_dir / (target.name + ".tmpl")
        if not template.is_file():
            continue
        text = _render(template.read_text(encoding="utf-8"), values)
        if target.parent == paths.home:
            text = _strip_guard(text)
        if target.resolve() != target or (target.exists() and not target.is_file()):
            kept.append(rel)
            continue
        if target.is_file():
            digest = sha256_file(target)
            if digest != previous.get("generated_files", {}).get(rel) and digest != starter_digest:
                kept.append(rel)
                continue
        atomic_write_text(target, text)
        generated[rel] = sha256_text(text)
    config["generated_files"] = generated
    return kept


def construct(paths: Paths, answers: Dict[str, Any], actor: str = "system") -> Dict[str, Any]:
    problems = validate_answers(answers, paths)
    if problems:
        raise TaosError("answers are not usable yet:\n  - " + "\n  - ".join(problems))

    with locked(paths):
        return _construct(paths, answers, actor)


def _construct(paths: Paths, answers: Dict[str, Any], actor: str) -> Dict[str, Any]:
    previous = read_json(paths.config_file, {}) or {}
    if not answers.get("workspaces"):
        answers = dict(answers, workspaces=[{"path": str(paths.home), "primary": True}])
    config = _config_from(answers)
    added_agents = previous.get("added_agents") or []
    if added_agents:
        config["added_agents"] = added_agents
        config["agents"] = list(dict.fromkeys(config["agents"] + added_agents))
    if actor not in config["agents"] + list(config_mod.RESERVED_ACTORS):
        raise TaosError(f"Setup actor {actor!r} is outside the project roster.")

    store = tasks_mod.TaskStore(paths)
    task_records = store.load()["tasks"]
    prefix = config["project"]["prefix"]
    for task_id in task_records:
        if not task_id.startswith(prefix + "-"):
            raise TaosError(f"This project already has task {task_id}. Keep its prefix {task_id.rsplit('-', 1)[0]} "
                            f"in the setup answers. To start a project with prefix {prefix}, use a new copy.")
    allocator = read_json(paths.allocator_file)
    if paths.allocator_file.exists() and (not isinstance(allocator, dict) or type(allocator.get("next")) is not int):
        raise TaosError("The project's ID allocator is unreadable. Restore it before repeating setup.")
    if allocator is None:
        if task_records:
            raise TaosError("Existing tasks have no ID allocator. Restore the project's allocator before repeating setup.")
        atomic_write_json(paths.allocator_file, {"schema": tasks_mod.ALLOCATOR_SCHEMA, "prefix": prefix,
                                                 "next": 1, "updated_at": utc_now()})
    elif allocator.get("prefix") != prefix:
        if task_records or allocator.get("next") != 1:
            raise TaosError(f"The task ID allocator uses prefix {allocator.get('prefix')}. "
                            f"Check the saved allocator before repeating setup with prefix {prefix}.")
        atomic_write_json(paths.allocator_file, dict(allocator, prefix=prefix, updated_at=utc_now()))
    for path, empty in (
        (paths.tasks_file, {"schema": tasks_mod.TASKS_SCHEMA, "tasks": {}}),
        (paths.claims_file, {"schema": "TAOS_CLAIMS_V1", "claims": []}),
        (paths.decisions_file, {"schema": "TAOS_DECISIONS_V1", "decisions": []}),
    ):
        if not path.is_file():
            atomic_write_json(path, empty)

    values = {
        "taos_cli": _cli(paths),
        "principal_name": config["principal"]["name"],
        "project_name": config["project"]["name"],
        "prefix": config["project"]["prefix"],
        "stack": config["project"]["stack"],
        "agents": "see `taos bootstrap status` for the current roster",
        "workspaces_block": _workspace_block(config),
        "human_only_block": _bullets(config["human_only"]),
        "git_block": _git_block(config),
        "gates_block": _gates_block(config),
        "autonomy_block": _autonomy_block(config),
        "attention_block": _attention_block(config),
        "constructed_at": config["constructed_at"],
    }
    kept = _render_home_files(paths, config, previous, values)
    rel = ".codex/hooks.json"
    source = paths.home / rel
    if source.exists() or source.is_symlink():
        # Pin the distributed hook once. Leave a person's own root settings intact.
        original = "1cb6a56af682424f7e054b89e54599381870f6722af1717c95ef8087b593a9ac"
        if source.resolve() == source and source.is_file() and sha256_file(source) in (
                original, previous.get("generated_files", {}).get(rel)):
            pinned = _hook_payload(paths, source)
            if pinned != source.read_text(encoding="utf-8"):
                atomic_write_text(source, pinned)
            config["generated_files"][rel] = sha256_text(pinned)
        else:
            kept.append(rel)
    atomic_write_json(paths.config_file, config)

    existing_titles = {t.get("title") for t in task_records.values()}
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
            done_when=str(item.get("done_when") or ""),
            verification=str(item.get("verification") or ""),
        )
        created.append(task["id"])
        existing_titles.add(title)

    seeded = []
    recorded_suggestions = {p.get("body") for p in proposals_mod.all_proposals(paths)
                            if p.get("kind") == "atom" and p.get("evidence") == ["setup answer 9"]}
    for correction in answers.get("agent_corrections") or []:
        text = str(correction).strip()
        if not text:
            continue
        body = (f"{text}\n\nThis came from the principal at setup. Turn it into a checkable "
                "atom when you have seen it happen once in real work, then propose it "
                "again with --atom-json so `taos doctor` enforces it.")
        if body in recorded_suggestions:
            continue
        proposal = proposals_mod.propose(
            paths,
            kind="atom",
            title=text[:70],
            body=body,
            evidence=["setup answer 9"],
            agent=actor if actor in config["agents"] else "system",
        )
        seeded.append(proposal["id"])
        recorded_suggestions.add(body)

    linked = []
    for workspace in config["workspaces"]:
        target = Path(workspace["path"])
        if target.resolve() == paths.home:
            continue
        try:
            linked.append(link_workspace(paths, target, configured_hooks=config["install_hooks_in_workspaces"]))
        except (OSError, TaosError) as exc:
            linked.append({"path": str(target), "error": str(exc)})

    # What token telemetry this machine actually writes. Evidence, at setup, once.
    telemetry_probe: Dict[str, Any] = {}
    try:
        from . import usage as usage_mod

        primary = None
        for workspace in config.get("workspaces") or []:
            if workspace.get("primary"):
                primary = Path(workspace["path"])
        telemetry_probe = usage_mod.probe(paths, primary)
        config["telemetry"] = {
            "probed_at": telemetry_probe["probed_at"],
            "token_usage": {name: bool(data.get("available")) for name, data in telemetry_probe["adapters"].items()},
        }
        atomic_write_json(paths.config_file, config)
        events_mod.emit(paths, "usage_probe", actor, adapters=config["telemetry"]["token_usage"])
    except Exception:
        telemetry_probe = {}

    for name in ("OS_KERNEL", "PROJECT_KERNEL", "PRINCIPAL_KERNEL"):
        if "kernels/" + name + ".md" in kept:
            continue
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
        "kept": kept,
        "telemetry": telemetry_probe,
        "doctor": report,
    }


def _edit_block(path: Path, block: Optional[str], receipts: Dict[str, Any]) -> str:
    """Change only the exact delimited text we last inserted, including its spacing."""
    previous = receipts.pop(path.name, {})
    existed = path.is_file()
    text = path.read_bytes().decode("utf-8") if existed else ""
    mode = path.stat().st_mode & 0o777 if existed else 0o644
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(END) < text.index(BEGIN):
            return "kept (review the TAOS block markers)"
        gap = previous.get("gap", "")
        if gap not in ("", "\n", "\n\n"):
            return "kept (unverified block)"
        start = text.index(BEGIN) - len(gap)
        end = text.index(END) + len(END) + 1
        if start < 0 or sha256_text(text[start:end]) != previous.get("sha256"):
            return "kept (changed or unverified block)"
        before, after = text[:start], text[end:]
        created = previous.get("created") is True
        action = "updated"
    else:
        if block is None:
            return "no block" if existed else "absent"
        gap = "" if not text or text.endswith("\n\n") else "\n" if text.endswith("\n") else "\n\n"
        before, after, created = text, "", not existed
        action = "appended"
    if block is None:
        if created and not before and not after:
            path.unlink()
            return "removed (the file held only our block)"
        atomic_write_text(path, before + after, mode=mode)
        return "block removed"
    payload = gap + BEGIN + "\n" + block.strip() + "\n" + END + "\n"
    new_text = before + payload + after
    if text != new_text:
        atomic_write_text(path, new_text, mode=mode)
    receipts[path.name] = {"sha256": sha256_text(payload), "gap": gap, "created": created}
    return action


def _safe_target(workspace: Path, rel: str) -> Path:
    target = workspace / rel
    if target.resolve() != target or (target.exists() and not target.is_file()):
        raise TaosError("kept {0}; a link destination must be a regular file inside the workspace".format(target))
    if target.parent.exists() and not target.parent.is_dir():
        raise TaosError("kept {0}; the parent must be a directory".format(target))
    return target


@contextmanager
def _workspace_link(paths: Paths, workspace: Path):
    workspace = Path(workspace).expanduser()
    if workspace.is_symlink() or not workspace.is_dir():
        raise TaosError("workspace does not exist or is a symbolic link: {0}".format(workspace))
    workspace = workspace.resolve()
    if workspace == paths.home:
        raise TaosError("the OS home is already its own workspace; use its root instructions directly")
    # A directory lock serializes two OS homes attempting the first link without
    # leaving another file in the project. Always take the OS lock first.
    with locked(paths):
        fd = os.open(str(workspace), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            pointer = _safe_target(workspace, ".taos-link.json")
            previous = read_json(pointer)
            if pointer.exists():
                if not isinstance(previous, dict) or previous.get("schema") != "TAOS_LINK_V1":
                    raise TaosError("kept {0}; its existing link could not be verified".format(pointer))
                if (not isinstance(previous.get("installed", []), list)
                        or not isinstance(previous.get("file_sha256", {}), dict)
                        or not isinstance(previous.get("blocks", {}), dict)
                        or not all(isinstance(record, dict) for record in previous.get("blocks", {}).values())):
                    raise TaosError("kept {0}; its ownership records could not be verified".format(pointer))
                if previous.get("taos_home") != str(paths.home):
                    raise TaosError("kept {0}; unlink it from its original OS home first".format(pointer))
            yield workspace, pointer, previous or {}
        except TaosError:
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            raise TaosError("workspace {0}: {1}".format(workspace, exc))
        finally:
            os.close(fd)


def _drop_generated(target: Path, digest: Optional[str]) -> str:
    if not target.exists():
        return "absent"
    if digest and sha256_file(target) == digest:
        target.unlink()
        return "removed"
    return "kept (edited or pre-existing)"


def _snippet(rel: str) -> str:
    path = Path(rel)
    return str(path.with_name(path.stem + ".taos-snippet.json"))


def link_workspace(paths: Paths, workspace: Path, install_hooks: Optional[bool] = None,
                   *, configured_hooks: Optional[bool] = None) -> Dict[str, Any]:
    with _workspace_link(paths, workspace) as (workspace, pointer, previous):
        config = config_mod.load_soft(paths)
        # CLI overrides are per workspace. Construction follows its configured
        # preference while retaining any explicit per-workspace opt-out.
        hook_override = install_hooks if install_hooks is not None else previous.get("hook_override")
        if hook_override is None and previous and "hook_override" not in previous and not previous.get("installed"):
            hook_override = False  # an older, possibly docs-only link
        if install_hooks is not None:
            enabled = install_hooks
        elif configured_hooks is not None:
            enabled = configured_hooks and hook_override is not False
        else:
            enabled = previous.get("hooks_enabled", hook_override is not False)

        template = paths.templates_dir / "workspace_block.md.tmpl"
        if not template.is_file():
            raise TaosError("missing template: taos_core/templates/workspace_block.md.tmpl")
        block = _render(template.read_text(encoding="utf-8"), {
            "taos_home": str(paths.home), "taos_cli": _cli(paths),
            "project_name": config.get("project", {}).get("name", "this project"),
            "prefix": config.get("project", {}).get("prefix", "TASK"),
        })
        hashes = dict(previous.get("file_sha256", {}))
        docs = dict(previous.get("blocks", {}))
        # Verify every prospective destination and source before changing this link.
        for name in ("AGENTS.md", "CLAUDE.md"):
            target = _safe_target(workspace, name)
            if target.exists():
                target.read_bytes().decode("utf-8")
        payloads = {}
        for rel in HOOK_FILES:
            for name in (rel, _snippet(rel)):
                if enabled or name in hashes or name in previous.get("installed", []):
                    _safe_target(workspace, name)
            if enabled:
                source = _safe_target(paths.home, rel)
                if source.is_file():
                    payloads[rel] = _hook_payload(paths, source)

        actions = {name: _edit_block(workspace / name, block, docs) for name in ("AGENTS.md", "CLAUDE.md")}
        hooks = {}
        generated = {}
        for rel in HOOK_FILES:
            target = workspace / rel
            snippet = _snippet(rel)
            if not enabled or rel not in payloads:
                hooks[rel] = "hooks disabled" if not enabled else "hook source missing: " + str(paths.home / rel)
                for name in (rel, snippet):
                    if name in hashes or name in previous.get("installed", []):
                        if enabled:
                            hooks[name] = "kept (source missing)"
                            if name in hashes:
                                generated[name] = hashes[name]
                        else:
                            hooks[name] = _drop_generated(workspace / name, hashes.get(name)) + " (hooks disabled)"
                continue
            payload = payloads[rel]
            if not target.exists() or sha256_file(target) == hashes.get(rel):
                atomic_write_text(target, payload)
                generated[rel] = sha256_text(payload)
                hooks[rel] = "written"
                if snippet in hashes:
                    hooks[snippet] = _drop_generated(workspace / snippet, hashes[snippet])
                continue
            suggestion = workspace / snippet
            if not suggestion.exists() or sha256_file(suggestion) == hashes.get(snippet):
                atomic_write_text(suggestion, payload)
                generated[snippet] = sha256_text(payload)
                hooks[rel] = "existing file kept; merge {0} by hand".format(snippet)
            else:
                hooks[rel] = "existing file and {0} kept; review {1} and merge the TAOS hooks by hand".format(
                    snippet, paths.home / rel)

        atomic_write_json(pointer, {"schema": "TAOS_LINK_V1", "taos_home": str(paths.home),
                                   "linked_at": utc_now(), "hook_override": hook_override,
                                   "hooks_enabled": enabled, "blocks": docs,
                                   "installed": [rel for rel in HOOK_FILES if rel in generated],
                                   "file_sha256": generated}, mode=0o644)
        events_mod.emit(paths, "workspace_link", "system", workspace=str(workspace), hooks=enabled)
        return {"path": str(workspace), "docs": actions, "hooks": hooks}


def unlink_workspace(paths: Paths, workspace: Path) -> Dict[str, Any]:
    """Drop out cleanly: remove exactly what link_workspace added, nothing else."""
    with _workspace_link(paths, workspace) as (workspace, pointer, link):
        if not link:
            return {"path": str(workspace), "removed": {}, "already_unlinked": True}
        hashes = link.get("file_sha256", {})
        docs = dict(link.get("blocks", {}))
        removed = {}
        for name in ("AGENTS.md", "CLAUDE.md"):
            try:
                removed[name] = _edit_block(_safe_target(workspace, name), None, docs)
            except (TaosError, UnicodeError) as exc:
                removed[name] = "kept: {0}".format(exc)
        for rel in HOOK_FILES:
            for name in (rel, _snippet(rel)):
                try:
                    target = _safe_target(workspace, name)
                except TaosError as exc:
                    removed[name] = str(exc)
                    continue
                if target.exists():
                    removed[name] = _drop_generated(target, hashes.get(name))
        pointer.unlink()
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
    for name in report["kept"]:
        print("kept {0} (edited or unverified); review it against the setup answers".format(name))
    if not report["workspaces_linked"]:
        print("project workspace: {0} (OS home)".format(paths.home))
    failed_link = False
    for linked in report["workspaces_linked"]:
        if linked.get("error"):
            failed_link = True
            print("link failed for {0}: {1}".format(linked["path"], linked["error"]))
        else:
            print("linked {0}".format(linked["path"]))
            for name, action in {**linked["docs"], **linked["hooks"]}.items():
                print("  {0}: {1}".format(name, action))
    adapters = (report.get("telemetry") or {}).get("adapters") or {}
    for name, data in sorted(adapters.items()):
        if data.get("available"):
            print("token usage: {0} readable ({1} rows in the newest session)".format(name, data.get("sample_rows")))
        else:
            print("token usage: {0} not readable here; those fields stay null".format(name))
    print("")
    print("doctor: {0}".format("green" if report["doctor"]["ok"] else "failing"))
    for check in report["doctor"]["checks"]:
        if check["status"] != "pass":
            print("  {0} {1}: {2}".format(check["status"], check["name"], check["detail"]))
    if failed_link:
        print("Check the workspace path and its existing link, then rerun bootstrap construct with the same answers.")
    if not report["doctor"]["ok"]:
        print("Fix the failing checks above, then run {0} doctor.".format(_cli(paths)))
    return 1 if failed_link or not report["doctor"]["ok"] else 0


def _cmd_link(args: argparse.Namespace, paths: Paths) -> int:
    result = link_workspace(paths, Path(args.path), install_hooks=args.install_hooks)
    print("linked {0}".format(result["path"]))
    for name, action in result["docs"].items():
        print("  {0}: {1}".format(name, action))
    for name, action in result["hooks"].items():
        print("  {0}: {1}".format(name, action))
    return 0


def _cmd_unlink(args: argparse.Namespace, paths: Paths) -> int:
    result = unlink_workspace(paths, Path(args.path))
    print(("already unlinked {0}" if result.get("already_unlinked") else "unlinked {0}").format(result["path"]))
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


def _cmd_add_agent(args: argparse.Namespace, paths: Paths) -> int:
    problem = config_mod.agent_name_problem(args.name)
    if problem:
        raise TaosError(problem)
    config_mod.load(paths)  # refuse an unconstructed home before creating its lock
    with locked(paths):
        config = config_mod.load(paths)
        agents = config_mod.project_agents(paths)
        added = args.name not in agents
        if added:
            agents.append(args.name)
            config["agents"] = agents
            config.setdefault("added_agents", []).append(args.name)
            atomic_write_json(paths.config_file, config)
            events_mod.emit(paths, "agent_added", args.by, name=args.name)
    if args.json:
        print(json.dumps({"agents": agents, "added": added}))
    else:
        print(f"{args.name} is on the project roster. See every name with taos bootstrap status.")
    return 0


def _cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    if not paths.constructed():
        print(json.dumps({"constructed": False, "agents": []}) if args.json else config_mod.NOT_CONSTRUCTED)
        return 0
    config = config_mod.load(paths)
    if args.json:
        print(json.dumps({"constructed": True, "agents": config["agents"], "project": config["project"],
                          "workspaces": config.get("workspaces", [])}, indent=2))
        return 0
    print("project:   {0} ({1}-)".format(config["project"]["name"], config["project"]["prefix"]))
    print("principal: {0}".format(config["principal"]["name"]))
    print("agents:    {0}".format(", ".join(config.get("agents", []))))
    for workspace in config.get("workspaces") or []:
        print("workspace: {0}{1}".format(workspace["path"], " (primary)" if workspace.get("primary") else ""))
    print("constructed {0}".format(config.get("constructed_at")))
    return 0


def register(subparsers: Any) -> None:
    bootstrap = subparsers.add_parser("bootstrap", help="set up a project from a full set of answers")
    sub = bootstrap.add_subparsers(dest="bootstrap_cmd", required=True)

    questions = sub.add_parser("questions", help="print the questions to ask")
    questions.set_defaults(func=_cmd_questions)

    validate = sub.add_parser("validate", help="check an answers file")
    validate.add_argument("--answers")
    validate.set_defaults(func=_cmd_validate)

    construct_parser = sub.add_parser("construct", help="build the OS from answers")
    construct_parser.add_argument("--answers")
    construct_parser.add_argument("--agent", default="system", help="a name from the setup roster, human or system")
    construct_parser.set_defaults(func=_cmd_construct)

    link = sub.add_parser("link-workspace", help="point a repo at this OS")
    link.add_argument("path")
    hook_options = link.add_mutually_exclusive_group()
    hook_options.add_argument("--no-hooks", dest="install_hooks", action="store_false", help="link instructions only")
    hook_options.add_argument("--hooks", dest="install_hooks", action="store_true", help="enable hooks on this link")
    link.set_defaults(install_hooks=None)
    link.set_defaults(func=_cmd_link)

    unlink = sub.add_parser("unlink-workspace", help="remove exactly what link-workspace added")
    unlink.add_argument("path")
    unlink.set_defaults(func=_cmd_unlink)

    status = sub.add_parser("status", help="what was constructed")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=_cmd_status)

    add = sub.add_parser("add-agent", help="add an agent name to this project")
    add.add_argument("name")
    add.add_argument("--by", choices=["human"], required=True, help="the person choosing the name")
    add.add_argument("--json", action="store_true")
    add.set_defaults(func=_cmd_add_agent)

    pause_parser = subparsers.add_parser("pause", help="pause the project workflow and keep its safety checks")
    pause_parser.add_argument("--note")
    pause_parser.set_defaults(func=_cmd_pause)

    resume_parser = subparsers.add_parser("resume", help="resume the paused project workflow")
    resume_parser.set_defaults(func=_cmd_resume)
