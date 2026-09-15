#!/usr/bin/env python3
"""PreToolUse guard. Same rules for Codex and Claude.

Fails open on its own bugs (exit 0, no output) and fails closed on its rules.
It is deliberately small and readable: you should be able to audit every rule
here in two minutes, because it is the thing standing between an agent and
your keys.

Invocation: `python3 hooks/guard.py --agent codex|claude`. The agent name is
only used to enforce per-agent workspace lanes from the constructed config.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    emit_decision,
    find_home,
    load_config,
    read_stdin_json,
    secret_patterns,
)

EVENT = "PreToolUse"

SENSITIVE_DIRS = (
    "/.ssh/",
    "/.aws/",
    "/.gnupg/",
    "/.config/gcloud/",
    "/.docker/config.json",
)

STATE_FILES = ("tasks.json", "claims.json", "events.jsonl", "allocator.json", "decisions.json")
CAGE_FILES = (
    "hooks/guard.py",
    "hooks/session_start.py",
    "hooks/stop_labels.py",
    "hooks/_common.py",
    ".claude/settings.json",
    ".codex/hooks.json",
)

DENY_COMMAND_RULES: Tuple[Tuple[str, str], ...] = (
    (r"git\s+push\b[^\n]*(--force\b|(?<!\w)-f(?!\w)|--force-with-lease)",
     "force pushing rewrites history other people may already have. Push normally, or ask the human."),
    (r"git\s+(reset\s+--hard|clean\s+-[a-z]*f)[^\n]*\b(origin/|main\b|master\b)",
     "that discards work on a shared branch. Ask the human."),
    (r"git\s+(filter-branch|filter-repo)\b",
     "rewriting history is a human decision."),
    (r"git\s+branch\s+-D\b",
     "force-deleting a branch can destroy unmerged work. Use -d, or ask the human."),
    (r"git\s+worktree\s+remove\b[^\n]*--force",
     "force-removing a worktree discards uncommitted work. Ask the human."),
    (r"\bsudo\b",
     "sudo is never needed for this work."),
    (r"chmod\s+-R\s+777",
     "world-writable permissions are never the fix."),
    (r"(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba)?sh",
     "piping a download into a shell runs unreviewed code. Download it, read it, then run it."),
    (r"\b(npm|pnpm|yarn)\s+publish\b|\bcargo\s+publish\b|\bdocker\s+push\b|\bgh\s+release\s+create\b|\btwine\s+upload\b",
     "publishing is the human's call."),
    (r"\bterraform\s+(apply|destroy)\b|\bkubectl\s+(apply|delete)\b|\baws\s+\S+\s+(create|delete|put|update)",
     "changing live infrastructure is the human's call."),
    (r"(broadcast|sendRawTransaction|eth_sendTransaction|--broadcast|--private-key|--mnemonic)",
     "signing or broadcasting a transaction is the human's call, always."),
    (r"(?i)\b(buy\s+credits|add\s+payment|auto-?reload|upgrade\s+plan|subscribe\b)",
     "spending money is the human's call, always."),
    (r"\bcrontab\s+-r\b",
     "that deletes every scheduled job with no confirmation."),
)

ASK_COMMAND_RULES: Tuple[Tuple[str, str], ...] = (
    (r"git\s+commit\b[^\n]*--amend", "amending rewrites a commit that may already be shared."),
    (r"git\s+tag\b", "tags are usually releases."),
    (r"\brm\s+-[a-z]*r", "recursive delete."),
    (r"taos\s+burn\s+execute", "a burn deletes files, after archiving them."),
    (r"--takeover\b", "taking over another agent's claim."),
    (r"--skip-gates\b", "finishing without the gates passing."),
    (r"\b(pip|pip3)\s+install\b|\bnpm\s+install\s+-g\b|\bbrew\s+install\b|\bcargo\s+install\b",
     "installing software changes the machine."),
    (r"\b(crontab|launchctl|systemctl)\b", "scheduling changes outlive this session."),
    (r"\b(pkill|killall)\b|\bkill\s+-9\b", "killing processes can interrupt something else."),
)

RM_SAFE_HINTS = ("/.taos/scratch", "worktrees/", "-worktrees/", "/tmp/", "/private/tmp/", "/var/folders/")


def _agent_from_argv() -> str:
    for index, value in enumerate(sys.argv):
        if value == "--agent" and index + 1 < len(sys.argv):
            return sys.argv[index + 1].strip().lower()
    return ""


def _command_text(tool_input: Dict[str, Any]) -> str:
    """Codex may pass argv lists; Claude passes a string. Accept both."""
    command = tool_input.get("command")
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    if isinstance(command, str):
        return command
    for key in ("cmd", "script"):
        value = tool_input.get(key)
        if isinstance(value, str):
            return value
    return ""


def _tool_paths(tool_input: Dict[str, Any]) -> List[str]:
    found = []
    for key in ("file_path", "path", "notebook_path", "filePath"):
        value = tool_input.get(key)
        if isinstance(value, str):
            found.append(value)
    for key in ("edits", "files"):
        value = tool_input.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    for sub in ("file_path", "path"):
                        if isinstance(item.get(sub), str):
                            found.append(item[sub])
    patch = tool_input.get("patch") or tool_input.get("input")
    if isinstance(patch, str) and "*** " in patch:
        for match in re.finditer(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", patch, re.MULTILINE):
            found.append(match.group(1).strip())
    return found


def _looks_secret(text: str, patterns: List[str]) -> Optional[str]:
    lowered = text.replace("\\", "/")
    for directory in SENSITIVE_DIRS:
        if directory in lowered or lowered.endswith(directory.rstrip("/")):
            return directory.strip("/")
    for pattern in patterns:
        try:
            if re.search(pattern, lowered, re.IGNORECASE):
                return pattern
        except re.error:
            continue
    return None


def _touches(text: str, needles: Tuple[str, ...]) -> Optional[str]:
    normalized = text.replace("\\", "/")
    for needle in needles:
        if needle in normalized:
            return needle
    return None


def _rm_is_reckless(command: str) -> bool:
    for match in re.finditer(r"\brm\s+(-[a-zA-Z]+\s+)*(?P<target>[^\s;&|]+)", command):
        target = match.group("target")
        if target in ("/", "~", ".", "..", "*", "/*", "~/", "$HOME", "${HOME}"):
            return True
        if "$" in target:
            return True
    return False


def _current_branch(cwd: Optional[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _lane_violation(paths_touched: List[str], config: Dict[str, Any], agent: str) -> Optional[str]:
    """A workspace reserved for one agent is off limits to the other."""
    if not agent:
        return None
    for workspace in config.get("workspaces") or []:
        owner = str(workspace.get("agent") or "any").lower()
        if owner in ("any", "", agent):
            continue
        root = str(workspace.get("path") or "").rstrip("/")
        if not root:
            continue
        for path in paths_touched:
            candidate = os.path.abspath(os.path.expanduser(path))
            if candidate == root or candidate.startswith(root + os.sep):
                return "{0} is {1}'s lane. You are {2}; work in your own workspace.".format(root, owner, agent)
    return None


def decide(payload: Dict[str, Any], agent: str = "") -> Optional[Tuple[str, str]]:
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    home = find_home()
    config = load_config(home)
    patterns = secret_patterns(config)
    command = _command_text(tool_input)
    targets = _tool_paths(tool_input)

    # 1. Secrets, in either shape.
    for path in targets:
        hit = _looks_secret(path, patterns)
        if hit:
            return ("deny", "that path looks like a secret ({0}). Secrets are never read, copied, or printed.".format(hit))
    if command:
        for match in re.finditer(r"(?:^|[\s;|&])(?:cat|less|more|head|tail|bat|cp|mv|open|code|strings|xxd|base64)\s+(?P<target>[^\s;&|]+)", command):
            hit = _looks_secret(match.group("target"), patterns)
            if hit:
                return ("deny", "that reads something that looks like a secret ({0}).".format(hit))

    # 2. The state store is written only by the taos command; the cage is the human's.
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch", "str_replace_editor"):
        for path in targets:
            if "/.taos/" in path.replace("\\", "/") and _touches(path, STATE_FILES):
                return ("deny", "`.taos/` state is written only by the taos command. Use `taos task ...` instead of editing the file.")
            if _touches(path, CAGE_FILES):
                return ("deny", "the hooks and permission files are the human's to change, not yours.")
    if command:
        for match in re.finditer(r">>?\s*([^\s;&|]+)", command):
            target = match.group(1)
            if "/.taos/" in target.replace("\\", "/") and _touches(target, STATE_FILES):
                return ("deny", "do not redirect into the state store. Use the taos command.")
            if _touches(target, CAGE_FILES):
                return ("deny", "the hooks and permission files are the human's to change, not yours.")
        if re.search(r"\b(sed\s+-i|tee)\b", command) and _touches(command, CAGE_FILES):
            return ("deny", "the hooks and permission files are the human's to change, not yours.")

    # Paused by the human: keep the floor above, skip the workflow policy below.
    if home is not None and (home / ".taos" / "paused").is_file():
        if command:
            for pattern, reason in DENY_COMMAND_RULES:
                if re.search(pattern, command):
                    return ("deny", reason)
            if _rm_is_reckless(command):
                return ("deny", "that delete has an unbounded or variable target. Name the exact path.")
        return None

    # 3. Per-agent lanes: another agent's reserved workspace is read-only for you.
    write_like = tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch", "str_replace_editor")
    lane_paths = list(targets) if write_like else []
    if command:
        for match in re.finditer(r">>?\s*([^\s;&|]+)", command):
            lane_paths.append(match.group(1))
        for match in re.finditer(r"\bgit\s+-C\s+([^\s;&|]+)", command):
            lane_paths.append(match.group(1))
        for match in re.finditer(r"\bcd\s+([^\s;&|]+)", command):
            lane_paths.append(match.group(1))
    violation = _lane_violation(lane_paths, config, agent)
    if violation:
        return ("deny", violation)

    if not command:
        return None

    # 4. Permanent denials.
    for pattern, reason in DENY_COMMAND_RULES:
        if re.search(pattern, command):
            return ("deny", reason)
    if _rm_is_reckless(command):
        return ("deny", "that delete has an unbounded or variable target. Name the exact path.")

    # 5. Git policy from the constructed config.
    git = config.get("git") if isinstance(config.get("git"), dict) else {}
    protected = [str(b) for b in (git.get("protected_branches") or ["main", "master"])]
    autonomy = str(config.get("autonomy") or "edit_branches")
    merge_policy = str(git.get("merge_policy") or "human_pr")

    if re.search(r"\bgit\s+push\b", command):
        for branch in protected:
            if re.search(r"\bgit\s+push\b[^\n]*\b(?:origin|upstream)\s+(?:HEAD:)?{0}\b".format(re.escape(branch)), command):
                return ("deny", "pushing to {0} is the human's call.".format(branch))
        if autonomy == "propose_only":
            return ("deny", "this OS is set to propose-only: agents do not push.")
        if autonomy == "edit_branches":
            return ("ask", "pushing changes a shared remote.")
        # push_branches_open_prs: pushes to non-protected branches are allowed.

    if re.search(r"\bgh\s+pr\s+merge\b|\bgit\s+merge\b[^\n]*\b({0})\b".format("|".join(re.escape(b) for b in protected)), command):
        if merge_policy == "agent_after_gates":
            return ("ask", "merging into a protected branch; the gates must have passed.")
        if merge_policy == "trunk":
            return ("ask", "merging into the trunk.")
        return ("deny", "merging into a protected branch is the human's call. Open a PR and hand over the link.")

    if re.search(r"\bgit\s+(commit|merge|rebase)\b", command) and not re.search(r"\bgit\s+commit\b[^\n]*--amend", command):
        branch = _current_branch(payload.get("cwd") if isinstance(payload.get("cwd"), str) else None)
        if branch and branch in protected and str(git.get("isolation") or "branch") != "trunk":
            return ("ask", "you are on {0}. The convention here is a branch per task; switch first.".format(branch))

    if autonomy == "propose_only" and re.search(r"\bgit\s+commit\b", command):
        return ("ask", "this OS is set to propose-only; committing needs a human nod.")

    # 6. Things the human should see first.
    for pattern, reason in ASK_COMMAND_RULES:
        if re.search(pattern, command):
            if pattern.startswith(r"\brm\s") and any(hint in command for hint in RM_SAFE_HINTS):
                continue
            return ("ask", reason)
    return None


def main() -> int:
    payload = read_stdin_json()
    verdict = decide(payload, _agent_from_argv())
    if verdict is None:
        return 0
    decision, reason = verdict
    emit_decision(EVENT, decision, reason)
    if decision == "deny":
        sys.stderr.write(reason + "\n")
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        # A bug in the guard must never break the agent.
        raise SystemExit(0)
