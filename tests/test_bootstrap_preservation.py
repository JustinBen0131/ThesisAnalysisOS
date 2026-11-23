"""Exercise construction and linking against disposable projects through the CLI."""

import io
import json
import shlex
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from helpers import cleanup, example_answers, make_home
from taos_core.cli import main
from taos_core.paths import Paths


class BootstrapPreservation(unittest.TestCase):
    def setUp(self):
        tmp, paths = make_home()
        self.addCleanup(cleanup, tmp)
        self.tmp = tmp.resolve()
        self.home = self.tmp / "Ada's project OS"
        paths.home.rename(self.home)
        self.paths = Paths(self.home)
        self.workspace = self.tmp / "Project with spaces"
        self.workspace.mkdir()
        self.answers = example_answers(self.tmp, workspaces=[{"name": "lab", "path": str(self.workspace)}],
                                      agent_corrections=[], worktree_root=str(self.tmp / "worktrees"))
        self.answers_path = self.tmp / "answers.json"
        probe = patch("taos_core.usage.probe", return_value={"adapters": {}, "probed_at": "2026-01-01T00:00:00Z"})
        probe.start()
        self.addCleanup(probe.stop)

    def cli(self, *args, success=True):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = main(["--home", str(self.home), *map(str, args)])
        if success:
            self.assertEqual(code, 0, out.getvalue())
        else:
            self.assertNotEqual(code, 0, out.getvalue())
        return out.getvalue()

    def construct(self, success=True):
        self.answers_path.write_text(json.dumps(self.answers))
        return self.cli("bootstrap", "construct", "--answers", self.answers_path, success=success)

    def link(self, *args, success=True):
        return self.cli("bootstrap", "link-workspace", self.workspace, *args, success=success)

    def unlink(self, success=True):
        return self.cli("bootstrap", "unlink-workspace", self.workspace, success=success)

    def test_reconstruction_preserves_authored_files_and_refreshes_pristine_files(self):
        self.construct()
        files = [self.paths.agents_md, self.paths.claude_md, self.paths.kernels_dir / "PROJECT_KERNEL.md"]
        for item in files:
            with item.open("ab") as stream:
                stream.write(b"\n\nInstruction for this project.\r\n")
        expected = {item: item.read_bytes() for item in files}
        self.answers["principal_name"] = "Different Name"
        for _ in range(2):
            report = self.construct()
            for item, data in expected.items():
                self.assertEqual(item.read_bytes(), data)
                self.assertIn("kept " + str(item.relative_to(self.home)), report)
            self.assertIn("Different Name", (self.paths.kernels_dir / "PRINCIPAL_KERNEL.md").read_text())

    def test_unrecorded_edits_survive_first_and_legacy_setup(self):
        kernel = self.paths.kernels_dir / "PRINCIPAL_KERNEL.md"
        edited = kernel.read_bytes() + b"\nA rule agreed before setup.\n"
        kernel.write_bytes(edited)
        self.construct()
        self.assertEqual(kernel.read_bytes(), edited)
        config = json.loads(self.paths.config_file.read_text())
        config.pop("generated_files")
        self.paths.config_file.write_text(json.dumps(config))
        old_files = [self.paths.agents_md, self.paths.claude_md, self.paths.kernels_dir / "PROJECT_KERNEL.md"]
        for item in old_files:
            item.write_bytes(item.read_bytes() + b"\nKeep a locally agreed rule.\n")
        expected = {item: item.read_bytes() for item in old_files}
        self.construct()
        self.assertEqual(kernel.read_bytes(), edited)
        for item, data in expected.items():
            self.assertEqual(item.read_bytes(), data)

    def test_link_unlink_only_owned_unchanged_bytes(self):
        doc = self.workspace / "AGENTS.md"
        original = b"\n# Local rules\r\n\r\nKeep trailing spaces  \r\n\r\n"
        doc.write_bytes(original)
        unrelated = self.workspace / "notes" / "local.taos-snippet.json"
        unrelated.parent.mkdir()
        unrelated.write_bytes(b'{"belongs": "to the project"}')
        self.link()
        tail = b"\n\nMore project rules after setup.  "
        with doc.open("ab") as stream:
            stream.write(tail)
        target = self.workspace / ".codex/hooks.json"
        target.write_bytes(target.read_bytes() + b"\n  ")
        edited = target.read_bytes()
        for _ in range(2):
            self.assertIn("merge .codex/hooks.taos-snippet.json by hand", self.link())
            self.assertEqual(target.read_bytes(), edited)
        snippet = self.workspace / ".codex/hooks.taos-snippet.json"
        self.assertTrue(snippet.is_file())
        result = self.unlink()
        self.assertIn(".codex/hooks.json: kept", result)
        self.assertEqual(doc.read_bytes(), original + tail)
        self.assertFalse((self.workspace / "CLAUDE.md").exists())
        self.assertFalse((self.workspace / ".claude/settings.json").exists())
        self.assertFalse(snippet.exists())
        self.assertEqual(target.read_bytes(), edited)
        self.assertEqual(unrelated.read_bytes(), b'{"belongs": "to the project"}')

    def test_unowned_and_edited_conflict_snippets_are_preserved(self):
        codex = self.workspace / ".codex"
        codex.mkdir()
        target, snippet = codex / "hooks.json", codex / "hooks.taos-snippet.json"
        target.write_text("my hook")
        snippet.write_text("my earlier snippet")
        result = self.link()
        self.assertIn("hooks.taos-snippet.json kept", result)
        self.unlink()
        self.assertEqual(snippet.read_text(), "my earlier snippet")
        snippet.unlink()
        self.link()
        snippet.write_text("my edited suggestion")
        self.link()
        self.unlink()
        self.assertEqual(snippet.read_text(), "my edited suggestion")
        self.assertEqual(target.read_text(), "my hook")

    def test_edited_workspace_block_and_root_hook_keep_exact_bytes(self):
        source = self.paths.home / ".codex/hooks.json"
        original = source.read_bytes() + b" \r\n"
        source.write_bytes(original)
        self.assertIn("kept .codex/hooks.json", self.construct())
        self.assertEqual(source.read_bytes(), original)
        doc = self.workspace / "CLAUDE.md"
        edited = doc.read_bytes().replace(b"<!-- taos:end -->", b"A local change.\r\n<!-- taos:end -->")
        doc.write_bytes(edited)
        self.assertIn("unverified block", self.construct())
        self.assertIn("unverified block", self.unlink())
        self.assertEqual(doc.read_bytes(), edited)

    def test_legacy_receipt_with_unverified_entries(self):
        self.link()
        pointer = self.workspace / ".taos-link.json"
        old = json.loads(pointer.read_text())
        outside = self.tmp / "keep.txt"
        outside.write_text("Keep my file")
        old = {key: old[key] for key in ("schema", "taos_home", "linked_at", "installed")}
        old["installed"] += ["../keep.txt", str(outside)]
        pointer.write_text(json.dumps(old))
        hook = self.workspace / ".codex/hooks.json"
        pristine = hook.read_bytes()
        self.link()
        self.unlink()
        self.assertEqual(outside.read_text(), "Keep my file")
        self.assertEqual(hook.read_bytes(), pristine)

    def test_docs_only_link_stays_docs_only_and_reports_edited_hooks(self):
        self.link("--no-hooks")
        self.assertIn("hooks disabled", self.link())
        self.assertIn("hooks disabled", self.construct())
        hook = self.workspace / ".codex/hooks.json"
        self.assertFalse(hook.exists())
        self.link("--hooks")
        hook.write_text("My variant")
        self.answers["install_hooks_in_workspaces"] = False
        self.assertIn(".codex/hooks.json: kept", self.construct())
        self.assertEqual(hook.read_text(), "My variant")
        self.assertFalse((self.workspace / ".claude/settings.json").exists())

    def test_home_workspace_and_commands_with_spaces(self):
        self.answers["workspaces"] = []
        marker = "Command for this check: "
        for name in ("CLAUDE.md.tmpl", "workspace_block.md.tmpl"):
            with (self.paths.templates_dir / name).open("a") as stream:
                stream.write("\n" + marker + "{{taos_cli}} status --compact\n")
        result = self.construct()
        self.assertIn("project workspace: " + str(self.home), result)
        self.assertFalse((self.home / ".taos-link.json").exists())
        self.assertNotIn("<not constructed yet>", self.paths.agents_md.read_text())
        self.assertIn(self.answers["project_name"], (self.paths.kernels_dir / "PROJECT_KERNEL.md").read_text())
        config = json.loads(self.paths.config_file.read_text())
        self.assertEqual(config["workspaces"], [{"agent": "any", "primary": True, "name": self.home.name,
                                                 "path": str(self.home)}])
        self.assertIn(str(self.home), self.cli("start", "--task", "CMP-1", "--agent", "codex", "--session", "first"))
        self.link()
        for file in (self.paths.claude_md, self.workspace / "AGENTS.md"):
            command = next(line[len(marker):] for line in file.read_text().splitlines() if line.startswith(marker))
            self.assertEqual(shlex.split(command), [str(self.paths.launcher), "--home", str(self.home),
                                                   "status", "--compact"])
            result = subprocess.run(command, shell=True, cwd=self.workspace, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        for rel in (".codex/hooks.json", ".claude/settings.json"):
            settings = json.loads((self.workspace / rel).read_text())
            cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
            self.assertEqual(shlex.split(cmd), ["python3", str(self.paths.hooks_dir / "session_start.py")])
        self.cli("bootstrap", "link-workspace", self.home, success=False)

    def test_foreign_pointer_and_symlinks_are_kept(self):
        pointer = self.workspace / ".taos-link.json"
        foreign = '{"schema": "TAOS_LINK_V1", "taos_home": "/another/project"}'
        pointer.write_text(foreign)
        self.assertIn("original OS home", self.link(success=False))
        self.assertIn("original OS home", self.unlink(success=False))
        self.assertEqual(pointer.read_text(), foreign)
        pointer.unlink()
        external = self.tmp / "external"
        external.mkdir()
        external_hook = external / "hooks.json"
        external_hook.write_text("Keep the outside file")
        symlink = self.workspace / ".codex"
        symlink.symlink_to(external, target_is_directory=True)
        self.assertIn("inside the workspace", self.link(success=False))
        self.assertFalse(pointer.exists())
        self.assertEqual(external_hook.read_text(), "Keep the outside file")
        symlink.unlink()
        self.link()
        doc = self.workspace / "AGENTS.md"
        doc.unlink()
        doc.symlink_to(external_hook)
        self.unlink()
        self.assertTrue(doc.is_symlink())
        self.assertEqual(external_hook.read_text(), "Keep the outside file")

    def test_setup_failure_reports_links_and_health(self):
        self.answers["workspaces"][0]["path"] = str(self.tmp / "missing project")
        result = self.construct(success=False)
        self.assertIn("link failed", result)
        self.assertIn("rerun bootstrap construct", result)
        self.answers["workspaces"] = []
        allocator = json.loads(self.paths.allocator_file.read_text())
        allocator["next"] = 1
        self.paths.allocator_file.write_text(json.dumps(allocator))
        result = self.construct(success=False)
        self.assertIn("doctor: failing", result)
        self.assertIn("allocator_monotonic", result)
        self.assertIn("Fix the failing checks", result)

    def test_prefix_on_repeat_setup_preserves_an_existing_project(self):
        self.construct()
        protected = [self.paths.config_file, self.paths.allocator_file, self.paths.tasks_file, self.paths.agents_md]
        previous = {path: path.read_bytes() for path in protected}
        self.answers["prefix"] = "NEW"
        self.assertIn("already has task", self.construct(success=False))
        for path, data in previous.items():
            self.assertEqual(path.read_bytes(), data)
        self.cli("doctor")

    def test_setup_can_retry_before_the_first_task_id_was_issued(self):
        self.paths.ensure_state()
        self.paths.allocator_file.write_text(json.dumps({"schema": "TAOS_ALLOCATOR_V1", "prefix": "OLD", "next": 1}))
        self.answers.update(prefix="NEW", first_tasks=[{"title": "Check the calibration"}] * 2)
        self.construct()
        self.assertEqual(set(json.loads(self.paths.tasks_file.read_text())["tasks"]), {"NEW-1"})

    def test_setup_keeps_each_suggestion_and_decision_once(self):
        self.answers["agent_corrections"] = ["Record the raw measurement."] * 2
        self.construct()
        first, = self.paths.proposals_dir.glob("prop_*.json")
        decision = json.loads(first.read_text())
        decision["status"] = "rejected"
        first.write_text(json.dumps(decision))
        self.answers["agent_corrections"].append("Record the units.")
        self.construct()
        self.construct()
        self.assertEqual(len(list(self.paths.proposals_dir.glob("prop_*.json"))), 2)
        self.assertEqual(json.loads(first.read_text()), decision)
