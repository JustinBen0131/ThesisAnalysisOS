"""The constructed configuration: who the principal is and what is forbidden."""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from .paths import Paths
from .store import read_json
from .util import TaosError

SCHEMA = "TAOS_CONFIG_V1"

NOT_CONSTRUCTED = "TAOS not constructed. Read BOOTSTRAP.md and follow it."

DEFAULT_SECRET_PATTERNS = [
    r"\.env$",
    r"\.env\.",
    r"\.pem$",
    r"id_rsa",
    r"id_ed25519",
    r"\.key$",
    r"keystore",
    r"mnemonic",
    r"seed[-_ ]?phrase",
    r"\.secret",
    r"credentials",
]

DEFAULT_HUMAN_ONLY = [
    "deploy or release",
    "merge to main",
    "sign or broadcast a transaction",
    "touch keys, seed phrases, or secrets",
    "spend money",
    "message people on my behalf",
]

ISOLATION_MODES = ("branch", "worktree", "fork", "trunk")
MERGE_POLICIES = ("human_pr", "agent_after_gates", "trunk")
AUTONOMY_LEVELS = ("propose_only", "edit_branches", "push_branches_open_prs")
CADENCES = ("daily", "weekly", "manual")

DEFAULT_GIT = {
    "isolation": "worktree",
    "branch_pattern": "{prefix_lower}/{id_lower}-{slug}",
    "protected_branches": ["main", "master"],
    "worktree_root": None,
    "merge_policy": "human_pr",
}

STACK_GATES: Dict[str, List[Dict[str, str]]] = {
    "rust-cargo": [
        {"name": "test", "command": "cargo test"},
        {"name": "fmt", "command": "cargo fmt --all -- --check"},
        {"name": "clippy", "command": "cargo clippy --all-targets -- -D warnings"},
    ],
    "node": [
        {"name": "test", "command": "npm test"},
        {"name": "lint", "command": "npm run lint --if-present"},
    ],
    "python": [
        {"name": "test", "command": "python3 -m pytest -q"},
    ],
    "go": [
        {"name": "test", "command": "go test ./..."},
        {"name": "vet", "command": "go vet ./..."},
    ],
    "generic": [],
}

DEFAULTS: Dict[str, Any] = {
    "schema": SCHEMA,
    "agents": ["codex", "claude"],
    "human_only": list(DEFAULT_HUMAN_ONLY),
    "secret_patterns": list(DEFAULT_SECRET_PATTERNS),
    "planning_surface": "none",
    "brief_time": "08:30",
    "panel": {"port": 4331, "open_browser": True},
    "ttl_days": {"handoffs": 30, "briefs": 14, "scratch": 7, "proposals_closed": 30},
    "claim_stale_hours": 6,
    "install_hooks_in_workspaces": True,
    "git": dict(DEFAULT_GIT),
    "gates": [],
    "autonomy": "edit_branches",
    "attention": {"max_decisions_per_day": 3, "quiet_hours": None},
    "self_iteration": {"cadence": "weekly", "auto_promote_atoms": False},
    "control": {
        "enabled": True,
        "min_evidence": 3,
        "step": 0.1,
        "observed_profile": None,
    },
    # The human's boundary conditions. Priors for the controller, limits for the agents.
    "resources": {
        "agents_available": None,
        "compute": "normal",            # constrained | normal | abundant
        "context_available": None,      # M_available, if known
        "context_working": None,        # M_working: what to occupy normally
        "context_reserve": None,        # M_reserve: headroom to keep
        "protect": [],                  # resources to spare
    },
    "preference": {
        "exploration": "balanced",      # conservative | balanced | exploratory
        "priorities": ["verified quality", "user intent", "human attention", "resources", "exploration"],
    },
}


def git_settings(paths: Paths) -> Dict[str, Any]:
    values = dict(DEFAULT_GIT)
    provided = load_soft(paths).get("git")
    if isinstance(provided, dict):
        values.update({k: v for k, v in provided.items() if v is not None})
    return values


def gates(paths: Paths) -> List[Dict[str, str]]:
    provided = load_soft(paths).get("gates")
    if not isinstance(provided, list):
        return []
    return [g for g in provided if isinstance(g, dict) and g.get("command")]


def autonomy(paths: Paths) -> str:
    value = str(load_soft(paths).get("autonomy") or "edit_branches")
    return value if value in AUTONOMY_LEVELS else "edit_branches"


def attention(paths: Paths) -> Dict[str, Any]:
    values = dict(DEFAULTS["attention"])
    provided = load_soft(paths).get("attention")
    if isinstance(provided, dict):
        values.update(provided)
    return values


def self_iteration(paths: Paths) -> Dict[str, Any]:
    values = dict(DEFAULTS["self_iteration"])
    provided = load_soft(paths).get("self_iteration")
    if isinstance(provided, dict):
        values.update(provided)
    return values


def defaults() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULTS)


def load(paths: Paths) -> Dict[str, Any]:
    data = read_json(paths.config_file)
    if not isinstance(data, dict):
        raise TaosError(NOT_CONSTRUCTED)
    return data


def load_soft(paths: Paths) -> Dict[str, Any]:
    """Config when constructed, defaults otherwise. Never raises."""
    try:
        return load(paths)
    except TaosError:
        return defaults()


def validate(config: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    if not isinstance(config, dict):
        return ["config must be an object"]
    if config.get("schema") != SCHEMA:
        problems.append("config.schema must be {0}".format(SCHEMA))
    principal = config.get("principal")
    if not isinstance(principal, dict) or not principal.get("name"):
        problems.append("config.principal.name is required")
    project = config.get("project")
    if not isinstance(project, dict):
        problems.append("config.project is required")
    else:
        import re

        if not project.get("name"):
            problems.append("config.project.name is required")
        prefix = project.get("prefix", "")
        if not re.match(r"^[A-Z][A-Z0-9]{1,7}$", str(prefix)):
            problems.append("config.project.prefix must be 2-8 uppercase alphanumerics")
    if not isinstance(config.get("agents"), list) or not config.get("agents"):
        problems.append("config.agents must be a non-empty list")
    if not isinstance(config.get("human_only"), list) or not config.get("human_only"):
        problems.append("config.human_only must be a non-empty list")
    if not isinstance(config.get("secret_patterns"), list):
        problems.append("config.secret_patterns must be a list")
    workspaces = config.get("workspaces")
    if workspaces is not None and not isinstance(workspaces, list):
        problems.append("config.workspaces must be a list")
    panel = config.get("panel", {})
    if not isinstance(panel, dict) or not isinstance(panel.get("port", 4331), int):
        problems.append("config.panel.port must be an integer")
    git = config.get("git", {})
    if isinstance(git, dict):
        if git.get("isolation") not in (None,) + ISOLATION_MODES:
            problems.append("config.git.isolation must be one of {0}".format(", ".join(ISOLATION_MODES)))
        if git.get("merge_policy") not in (None,) + MERGE_POLICIES:
            problems.append("config.git.merge_policy must be one of {0}".format(", ".join(MERGE_POLICIES)))
    elif git is not None:
        problems.append("config.git must be an object")
    if config.get("autonomy") not in (None,) + AUTONOMY_LEVELS:
        problems.append("config.autonomy must be one of {0}".format(", ".join(AUTONOMY_LEVELS)))
    gates_value = config.get("gates", [])
    if not isinstance(gates_value, list) or any(not isinstance(g, dict) or not g.get("command") for g in gates_value):
        problems.append("config.gates must be a list of {name, command}")
    return problems


def prefix(paths: Paths) -> str:
    return str(load(paths).get("project", {}).get("prefix", "TASK"))


def project_name(paths: Paths) -> str:
    return str(load(paths).get("project", {}).get("name", "project"))


def secret_patterns(paths: Paths) -> List[str]:
    config = load_soft(paths)
    patterns = config.get("secret_patterns")
    if not isinstance(patterns, list) or not patterns:
        return list(DEFAULT_SECRET_PATTERNS)
    merged = list(DEFAULT_SECRET_PATTERNS)
    for pattern in patterns:
        if isinstance(pattern, str) and pattern not in merged:
            merged.append(pattern)
    return merged


def ttl_days(paths: Paths) -> Dict[str, int]:
    config = load_soft(paths)
    values = dict(DEFAULTS["ttl_days"])
    provided = config.get("ttl_days")
    if isinstance(provided, dict):
        for key, value in provided.items():
            if isinstance(value, int):
                values[key] = value
    return values


def claim_stale_hours(paths: Paths) -> float:
    config = load_soft(paths)
    value = config.get("claim_stale_hours", DEFAULTS["claim_stale_hours"])
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(DEFAULTS["claim_stale_hours"])
