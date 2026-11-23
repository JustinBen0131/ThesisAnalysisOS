"""Interface rule 6: a mistake is answered in plain words, with the nearest real thing and the command to run next."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shlex
import subprocess
import time
import unittest
from typing import Iterator, List, Tuple
from unittest import mock

from helpers import cleanup, construct_example, make_home
from taos_core import cli, lifecycle, plain
from taos_core import tasks as tasks_mod


def said(*argv: str) -> Tuple[int, str, str]:
    """Run `taos` with these words. Returns (exit code, what it printed, what it complained of)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as stopped:
            code = stopped.code
    return code, out.getvalue(), err.getvalue()


def incomplete(parser: argparse.ArgumentParser, words: Tuple[str, ...] = ()) -> Iterator[Tuple[str, ...]]:
    """Every command that cannot run as typed with nothing after it: it needs a sub-command, a value or an option."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                needs = any(isinstance(a, argparse._SubParsersAction) or (a.required and a.option_strings)
                            or (not a.option_strings and a.nargs not in ("?", "*")) for a in sub._actions
                            if not isinstance(a, argparse._HelpAction))
                if needs:
                    yield words + (name,)
                yield from incomplete(sub, words + (name,))


class Typed(unittest.TestCase):
    def assertPlain(self, argv: Tuple[str, ...], *expected: str) -> str:
        code, out, err = said(*argv)
        self.assertEqual(code, 2, "a mistake keeps exit code 2: " + " ".join(argv))
        for noise in ("usage:", "error:", "Traceback", "the following arguments"):
            self.assertNotIn(noise, err, " ".join(argv))
        for words in expected:
            self.assertIn(words, err)
        return err

    def test_no_incomplete_command_answers_with_argparse_noise(self):
        typed = list(incomplete(cli.build_parser()))
        self.assertGreater(len(typed), 50, "every verb and sub-verb that needs something is walked")
        for argv in typed:
            err = self.assertPlain(argv, "taos " + " ".join(argv))
            self.assertTrue(err.rstrip().splitlines()[-1].startswith(("Everything it takes: taos", "taos ")), err)

    def test_a_command_with_commands_lists_them(self):
        err = self.assertPlain(("gate",), "taos gate needs one of its commands:", "taos gate <command> --help")
        for verb in ("run", "show", "list"):
            self.assertRegex(err, r"\n  {0}\s+\w".format(verb), "each command with what it does")

    def test_a_missing_option_is_named_with_a_line_to_fill_in(self):
        self.assertPlain(("task", "create"), "taos task create needs --agent and --title:",
                         "  taos task create --agent <codex|claude|human|system> --title <title>",
                         "Everything it takes: taos task create --help")
        self.assertPlain(("task", "show"), "taos task show needs <task-id>:", "  taos task show <task-id>")

    def test_a_wrong_value_gets_the_nearest_right_one(self):
        self.assertPlain(("task", "create", "--agent", "claud", "--title", "x"),
                         "taos task create --agent takes codex, claude, human or system, not 'claud'. Did you mean 'claude'?")
        self.assertPlain(("kernel", "refresh", "os"), "not 'os'. Did you mean 'OS_KERNEL'?")
        self.assertPlain(("lesson", "status", "L-1", "activ"), "Did you mean 'active'?")
        self.assertPlain(("anchor", "control", "A-1", "--where", "x", "--value", "abc"),
                         "taos anchor control --value takes a number, not 'abc'.")

    def test_a_mistyped_sub_command_or_option(self):
        self.assertPlain(("task", "craete"), "taos task has no command 'craete'. Did you mean 'create'? Its commands: taos task --help")
        self.assertPlain(("gate", "show", "--task", "X", "--jsn"), "taos gate show does not take '--jsn'. Did you mean --json?")
        self.assertPlain(("gate", "show", "--tsk", "X"), "taos gate show does not take '--tsk'. Did you mean --task?",
                         "taos gate show needs --task:")
        self.assertPlain(("gate", "show", "--task"), "taos gate show --task needs a value after it.")

    def test_help_is_untouched(self):
        code, out, _ = said("gate", "show", "--help")
        self.assertEqual(code, 0)
        self.assertIn("usage: taos gate show", out)


class Nearest(unittest.TestCase):
    def test_case_then_prefix_then_spelling(self):
        self.assertEqual(plain.nearest("pen-1", ["PEN-1", "PEN-2"]), "PEN-1")
        self.assertEqual(plain.nearest("os", ["OS_KERNEL", "NOW_KERNEL"]), "OS_KERNEL")
        self.assertEqual(plain.nearest("PEN-12", ["PEN-1", "XYZ-9"]), "PEN-1")
        self.assertIsNone(plain.nearest("zzz", ["PEN-1"]))

    def test_a_missing_name_says_where_every_one_is(self):
        self.assertEqual(tasks_mod.no_task("pen-1", {"PEN-1": {}}),
                         "There is no task 'pen-1'. Did you mean 'PEN-1'? Every task: taos task list")
        self.assertEqual(plain.missing("claim", "c1", [], "taos claim status"), "There is no claim 'c1'. Every claim: taos claim status")

    def test_recorded_utc_reads_on_the_local_clock(self):
        before = os.environ.get("TZ")
        os.environ["TZ"] = "America/New_York"
        time.tzset()
        try:
            self.assertEqual(plain.local("passed 2026-11-23T00:18:19Z for PEN-2"), "passed 2026-11-22 19:18 for PEN-2")
            self.assertEqual(plain.day("2026-11-23T00:18:19Z"), "2026-11-22")
            self.assertEqual(plain.day("2026-11-23"), "2026-11-23", "a bare date has no clock to move")
        finally:
            if before is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = before
            time.tzset()

    def test_a_long_row_folds_under_its_reason_and_never_inside_a_command(self):
        row = "  stale    closure: " + "the instructions have changed since " * 4
        folded = plain.fold(row, 60).splitlines()
        self.assertTrue(len(folded) > 1 and all(len(line) <= 60 for line in folded))
        self.assertTrue(all(line.startswith(" " * 11) and line[11] != " " for line in folded[1:]), folded)
        step = "  next: run the checks on the files as they are now: taos gate run --task CMP-2 --agent <you>"
        self.assertTrue(plain.fold(step, 60).splitlines()[-1].strip().startswith("taos gate run --task CMP-2"))

    def test_a_shell_word_survives_a_space(self):
        self.assertEqual(shlex.split("cd " + plain.shell("/tmp/my work")), ["cd", "/tmp/my work"])
        self.assertEqual(plain.shell("/tmp/plain"), "/tmp/plain", "a plain path is printed as it always was")


class Built(unittest.TestCase):
    def setUp(self):
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths)

    def tearDown(self):
        cleanup(self.tmp)

    def taos(self, *argv: str, by_hand: bool = False) -> Tuple[int, str, str]:
        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return by_hand

        with mock.patch("sys.stdin", Terminal()), mock.patch("taos_core.page.terminal", lambda out: by_hand), \
                mock.patch("taos_core.page.launcher", lambda: "taos"), \
                mock.patch.dict("os.environ", {"NO_COLOR": "1"}):     # as typed on the PATH: commands keep their spelling
            return said("--home", str(self.paths.home), *argv)

    def test_an_unknown_task_offers_the_nearest(self):
        code, _, err = self.taos("task", "show", "cmp-2")
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "There is no task 'cmp-2'. Did you mean 'CMP-2'? Every task: taos task list")

    def test_other_wrong_names_get_the_nearest(self):
        code, _, err = self.taos("task", "update", "CMP-2", "--agent", "human", "--set", "titel=x")
        self.assertEqual(code, 1)
        self.assertIn("taos task update cannot change titel. Did you mean 'title'?", err)
        code, _, err = self.taos("claim", "check", "--agent", "codex", "--scope", "tsk:CMP-2")
        self.assertIn("not 'tsk'. Did you mean 'task:CMP-2'?", err)
        code, _, err = self.taos("burn", "recall", "--date", "2026-01-01")
        self.assertIn("There is no burn archive for 2026-01-01. No burn has been archived yet", err)

    def test_gate_run_by_hand_needs_no_agent_and_a_pipe_does(self):
        code, _, err = self.taos("gate", "run", "--task", "CMP-2")
        self.assertEqual(code, 2)
        self.assertIn("taos gate run needs --agent: who is running the checks.", err)
        self.assertIn("--agent human is assumed", err)
        code, out, _ = self.taos("gate", "run", "--task", "CMP-2", by_hand=True)
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        self.assertRegex(lines[0], r"^  holds    ok\s+ran now and passed \(exit 0\)$", "a run answers in the four words")
        self.assertEqual(lines[-2], "Every check passes. What CMP-2 rests on now: taos why CMP-2")
        self.assertTrue(lines[-1].startswith("Recorded in .taos/gates/CMP-2_"), "the record's path comes last, after the next step")
        newest = sorted((self.paths.state / "gates").glob("CMP-2_*.json"))[-1]
        self.assertEqual(json.loads(newest.read_text(encoding="utf-8"))["agent"], "human")
        code, out, _ = self.taos("gate", "run", "--task", "CMP-2", "--agent", "codex")
        self.assertRegex(out.splitlines()[0], r"^  holds    ok\s+not run again: nothing it tested has changed since \S+Z$")

    def test_gate_show_leads_with_the_answer_and_ends_with_what_to_do(self):
        code, out, _ = self.taos("gate", "show", "--task", "CMP-2")
        lines = out.splitlines()
        self.assertEqual(lines[0], "CMP-2, each check on the files as they are now:")
        self.assertRegex(lines[1], r"^  unknown  ok\s+never run for this task$")
        self.assertEqual(lines[-1], "CMP-2 has not been checked yet. Check it: taos gate run --task CMP-2 --agent <you>")
        self.taos("gate", "run", "--task", "CMP-2", "--agent", "codex")
        code, out, _ = self.taos("gate", "show", "--task", "CMP-2", by_hand=True)
        lines = out.splitlines()
        self.assertRegex(lines[1], r"^  holds    ok\s+passed ")
        ending = " ".join(out.split()).split("Last run ")[-1]
        self.assertTrue("Last run " in out and "taos gate run" not in ending, "nothing to do when all hold")

    def test_why_quotes_an_instruction_for_a_person_and_keeps_the_id_for_a_program(self):
        from taos_core import rules as rules_mod
        self.taos("gate", "run", "--task", "CMP-2", "--agent", "codex")
        self.taos("task", "transition", "CMP-2", "--to", "done", "--agent", "codex", "--reason", "fixed")
        rule = rules_mod.add(self.paths, quote="Never cut the generic bounds", said_on="2026-01-05", scope="CMP-2")
        _, piped, _ = self.taos("why", "CMP-2")
        self.assertIn(rule["id"] + " governs now and is not one this was recorded under", piped, "a pipe keeps today's words")
        self.assertIn("    {0}  \"Never cut the generic bounds\"".format(rule["id"]), piped)
        _, person, _ = self.taos("why", "CMP-2", by_hand=True)
        self.assertNotIn(rule["id"], person, "a person reads the words, not the id")
        self.assertIn("\"Never cut the generic bounds\" (said 2026-01-05) governs now", " ".join(person.split()))
        self.assertIn("    \"Never cut the generic bounds\"  (said 2026-01-05, scope CMP-2)", person)
        _, full, _ = self.taos("why", "CMP-2", "--full", by_hand=True)
        self.assertEqual(full, piped, "--full is what an agent reads")
        _, summary, _ = self.taos("why", by_hand=True)
        self.assertNotIn(rule["id"], summary)

    def test_printed_workspace_commands_survive_a_space(self):
        spaced = self.tmp / "my work"
        spaced.mkdir()
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        config["workspaces"] = [{"name": "mine", "path": str(spaced), "primary": True, "agent": "any"}]
        self.paths.config_file.write_text(json.dumps(config), encoding="utf-8")
        lane = lifecycle.lane_for(self.paths, tasks_mod.TaskStore(self.paths).get("CMP-2"), "codex")
        add, cd = (shlex.split(command) for command in lane["commands"])
        self.assertEqual(add[:3], ["git", "-C", str(spaced)])
        self.assertEqual(cd, ["cd", lane["worktree"]])
        self.assertIn("my work", lane["worktree"])
        capsule = lifecycle.start(self.paths, agent="codex", task_id="CMP-2", session_label="CMP-2 | spaced")
        self.assertIn("path:" + lane["worktree"].strip("/"), [s for c in capsule["claims"] for s in c["scopes"]],
                      "a project folder with a space in its name can be started and claimed")

    def test_the_printed_commands_run_when_pasted_in_a_folder_named_with_a_space_and_an_apostrophe(self):
        named = self.tmp / "Justin's work dir"
        named.mkdir()
        quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "check": True}
        subprocess.run(["git", "init", "-q", str(named)], **quiet)
        subprocess.run(["git", "-C", str(named), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "--allow-empty", "-m", "first"], **quiet)
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        config["workspaces"] = [{"name": "mine", "path": str(named), "primary": True, "agent": "any"}]
        self.paths.config_file.write_text(json.dumps(config), encoding="utf-8")
        capsule = lifecycle.start(self.paths, agent="claude", task_id="CMP-1", session_label="CMP-1 | named")
        pasted = subprocess.run(["bash", "-c", "set -e; " + "; ".join(capsule["lane"]["commands"]) + "; pwd -P"],
                                capture_output=True, text=True)
        self.assertEqual(pasted.returncode, 0, pasted.stderr)
        self.assertEqual(pasted.stdout.strip().splitlines()[-1], os.path.realpath(capsule["lane"]["worktree"]))

    def test_a_path_scope_may_hold_a_space_and_nothing_looser(self):
        from taos_core.claims import normalize_scopes
        from taos_core.util import TaosError
        self.assertEqual(normalize_scopes(["path:/tmp/my work/"]), ["path:tmp/my work"])
        self.assertEqual(normalize_scopes(["path:/tmp/Justin's work"]), ["path:tmp/Justin's work"])
        for loose in ("path:/tmp/my*", "path:/tmp/a\tb", "task:CMP 2", "branch:my branch"):
            with self.assertRaises(TaosError, msg=loose):
                normalize_scopes([loose])

    def test_an_install_with_no_workspace_works_in_the_os_home(self):
        config = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        config["workspaces"] = []
        self.paths.config_file.write_text(json.dumps(config), encoding="utf-8")
        lane = lifecycle.lane_for(self.paths, tasks_mod.TaskStore(self.paths).get("CMP-2"), "codex")
        self.assertEqual(lane["workspace"], str(self.paths.home))
        self.assertTrue(lane["worktree"] and lane["commands"], "a worktree lane, with the commands to enter it")


if __name__ == "__main__":
    unittest.main()
