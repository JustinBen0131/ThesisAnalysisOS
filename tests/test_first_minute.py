"""The first minute at the command line: what `taos` says when asked nothing, asked for help, asked wrongly, or asked
where things stand, on a terminal of any width, into a pipe, and when nobody is reading."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import REPO  # noqa: F401  (puts the repository on the path, as its sibling tests do)

from taos_core import __version__, cli, demo, page, projections, usage


def said(*argv: str):
    """Run `taos` with these words into a pipe. Returns (exit code, what it printed, what it complained of)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as stopped:                               # argparse leaves this way for --help and --version
            code = stopped.code
    return code, out.getvalue(), err.getvalue()


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def seen(*argv: str, columns: int = 80, **env: str):
    """Run `taos` as a person at a terminal this wide, started as ./taos. Returns (exit code, the screen)."""
    out = Terminal()
    settings = dict({"COLUMNS": str(columns), "NO_COLOR": "1"}, **env)
    if not settings["NO_COLOR"]:
        del settings["NO_COLOR"]
    with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, settings, clear=False), \
            mock.patch.object(page, "launcher", return_value="./taos"):
        if "NO_COLOR" not in settings:
            os.environ.pop("NO_COLOR", None)
        code = cli.main(list(argv))
    return code, out.getvalue()


class Project(unittest.TestCase):
    """A small project that is set up: the demo's, before its story plays."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="taos-first-minute-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        with mock.patch.object(usage, "CLAUDE_ROOT", self.tmp / "claude"), mock.patch.object(usage, "CODEX_ROOT", self.tmp / "codex"):
            self.paths = demo.build(self.tmp)
        self.home = str(self.paths.home)


class LocalReads(Project):
    def test_first_minute_reads_run_without_network_or_external_programs(self):
        # Each command runs in a fresh interpreter. Catch swallowed attempts as well as uncaught ones.
        runner = """import runpy, sys
attempts = []
def guard(event, args):
    if event == 'subprocess.Popen':
        argv = args[1]
        listing = ['-C', workspace, 'ls-files', '-co', '--exclude-standard', '-z']
        if argv in (['git', *listing], ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', *listing]):
            raise FileNotFoundError('git unavailable')  # exercise the file-listing fallback
    if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.fork'):
        attempts.append(event)
        raise PermissionError(event)
workspace, script, *arguments = sys.argv[1:]
sys.argv = [script] + arguments
sys.addaudithook(guard)
try:
    runpy.run_path(script, run_name='__main__')
finally:
    if attempts:
        raise RuntimeError('read attempted ' + ', '.join(attempts))
"""
        env = {"TAOS_HOME": self.home, "HOME": str(self.tmp), "PATH": "", "NO_COLOR": "1"}

        def run(script, *args, expected=0):
            process = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", runner, str(self.tmp / "pendulum"),
                                      str(script), *args], input=b"{}", capture_output=True, cwd=self.home, env=env,
                                     timeout=30)
            self.assertEqual(process.returncode, expected, process.stderr.decode("utf-8"))
            return (process.stdout if expected == 0 else process.stderr).decode("utf-8")

        def command(*args):
            return run(self.paths.launcher, "--home", self.home, *args)
        # The hook records attempts even when the command catches the denial.
        control = self.tmp / "attempt.py"
        control.write_text("import socket\ntry: socket.socket()\nexcept PermissionError: pass\n")
        self.assertIn("read attempted socket.", run(control, expected=1))

        status = command("status", "--compact")
        self.assertIn("TAOS Pendulum", status)
        self.assertIn("Doctor: green", status)
        hook = json.loads(run(self.paths.home / "hooks/session_start.py"))["hookSpecificOutput"]
        self.assertEqual(hook["hookEventName"], "SessionStart")
        # The independent reads can straddle UTC midnight.
        current_date = r"^(TAOS Pendulum \| )\d{4}-\d{2}-\d{2}"
        self.assertEqual(re.sub(current_date, "", hook["additionalContext"]), re.sub(current_date, "", status[:-1]))
        self.assertIn("policies/REVIEW.md", command("policy", "route", "review my work"))
        self.assertIn("unknown  check fit", command("why", "PEN-1"))
        self.assertIn("Measure g from the six swings", command("capsule", "PEN-1"))


class FirstMinute(Project):
    def test_asked_nothing_in_a_fresh_copy_it_points_at_the_demo_and_not_at_an_empty_status(self):
        code, out, err = said()
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("┌") and lines[4].startswith("└"), "the name comes first, in its box")
        for command, does in cli.FRESH:
            self.assertIn(command, out)
            self.assertIn(does, out)
        self.assertNotIn("taos status", out)
        self.assertLessEqual(len(lines), 12, "a greeting is short")

    def test_asked_nothing_in_a_project_it_points_at_where_things_stand(self):
        code, out, _ = said("--home", self.home)
        self.assertEqual(code, 0)
        for command, does in cli.START:
            self.assertIn(command, out)
            self.assertIn(does, out)

    def test_a_command_is_shown_the_way_the_person_started_taos(self):
        _, screen = seen()
        self.assertIn("  ./taos demo ", screen)
        self.assertNotRegex(screen, r"(?m)^  taos ")
        _, piped, _ = said()
        self.assertIn("  taos demo ", piped, "a pipe is not rewritten: what an agent reads stays as it was")
        code, screen = seen("--home", self.home, "status")
        for command in ("./taos why", "./taos doctor", "./taos kernel freshness", "./taos status --full"):
            self.assertIn(command, screen)
        rewrite = page.commands(["status", "why"])
        self.assertEqual(rewrite.sub("./taos", "run taos status, not ../os/taos why; taos is paused"),
                         "run ./taos status, not ../os/taos why; taos is paused")

    def test_a_narrow_terminal_is_never_overrun(self):
        for columns in (30, 40, 60):
            for argv in ((), ("--home", self.home), ("--home", self.home, "status")):
                _, screen = seen(*argv, columns=columns)
                self.assertLessEqual(max(len(line) for line in screen.splitlines()), columns, (columns, argv))
        _, screen = seen("--home", self.home, "status", columns=40)
        for command in ("./taos why", "./taos doctor", "./taos kernel freshness"):
            self.assertIn(command, screen, "folding never splits a command to paste")

    def test_every_command_is_in_the_help_under_exactly_one_heading(self):
        verbs = cli.build_parser().get_default("verbs")
        named = [verb for _, group in cli.GROUPS for verb in group.split()]
        self.assertEqual(sorted(named), sorted(verbs), "a new command needs a heading in cli.GROUPS")
        code, out, _ = said("--help")
        self.assertEqual(code, 0)
        self.assertNotIn("\nMore\n", out)
        self.assertEqual(out.splitlines()[0], "usage: taos [--home HOME] <command> ...")
        for title, group in cli.GROUPS:
            self.assertLess(out.index(title), out.index("\n  {0} ".format(group.split()[0])), "each heading leads its commands")
        core = out[out.index(cli.GROUPS[0][0]):out.index(cli.LAYERS)].splitlines()[1:]
        self.assertEqual([line.split()[0] for line in core if line.strip()], cli.GROUPS[0][1].split(),
                         "the core commands come first, then a line says the rest is optional")
        self.assertLess(len(cli.GROUPS[0][1].split()), 8, "the core stays small enough to hold in the head")
        self.assertTrue(out.rstrip().endswith("Asked nothing, taos says where to start."))
        self.assertIn(" ".join(page.PROMISE[:1]), out, "the help opens with the promise, in the words of the opener")
        self.assertEqual(said("help")[:2], (0, out), "`taos help` is the help")
        self.assertTrue(said("status", "--help")[1].startswith("usage: taos status "), "a command keeps its own usage line")

    def test_the_doctor_answers_in_the_words_every_answer_uses(self):
        _, out, _ = said("--home", self.home, "doctor")
        rows = [line for line in out.splitlines() if line.startswith("  ")]
        self.assertGreater(len(rows), 5, "a row for each of its checks")
        for row in rows:
            self.assertRegex(row, r"^  (holds|warn |fails)  \S", "led by an answer, or by warn for a caution")
        self.assertNotRegex(out, r"(?m)^\s*(ok|FAIL)\b", "the two words it used before are gone")
        self.assertEqual(sorted(page.SHADE), sorted(page.ANSWERS), "four answers take a shade, and nothing else does")

    def test_a_mistyped_command_is_answered_in_a_line(self):
        code, out, err = said("statsu")
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, "taos has no command 'statsu'. Did you mean 'status'? Every command: taos --help\n")
        self.assertIn("Did you mean 'status'?", said("stat")[2], "a word a command begins with means that command")
        code, _, err = said("--home", "elsewhere", "frobnicate")
        self.assertEqual(code, 2)
        self.assertEqual(err, "taos has no command 'frobnicate'. Every command: taos --help\n")

    def test_the_folder_option_may_be_shortened_as_before(self):
        code, out, err = said("--hom", self.home, "status", "--compact")
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("TAOS Pendulum |"))
        self.assertEqual(said("--home=" + self.home, "status", "--compact")[1], out)

    def test_it_says_its_version(self):
        code, out, _ = said("--version")
        self.assertEqual((code, out), (0, "taos {0}\n".format(__version__)))


class NobodyReading(Project):
    def test_a_closed_stream_is_not_an_error(self):
        for argv in ([], ["--home", self.home, "status"]):
            with mock.patch.object(sys, "stdout", None), mock.patch.object(sys, "stderr", None):
                self.assertEqual(cli.main(list(argv)), 0)

    def test_a_reader_that_went_away_is_not_an_error(self):
        class Gone(io.StringIO):
            def write(self, text):
                raise BrokenPipeError()

            def flush(self):
                raise BrokenPipeError()

        for argv in ([], ["--home", self.home, "status"], ["--home", self.home, "why"]):
            with contextlib.redirect_stdout(Gone()):
                self.assertEqual(cli.main(list(argv)), 0, "`taos status | head -1` ends quietly")


class Shades(unittest.TestCase):
    def test_a_line_led_by_an_answer_takes_its_shade_and_no_other_line_does(self):
        plain = io.StringIO()
        shaded = page.Shaded(plain)
        shaded.write("  stale    closure: the instructions changed\nthe word stale inside a line\n  unknown")
        self.assertEqual(plain.getvalue(), "  \x1b[33mstale\x1b[0m    closure: the instructions changed\n"
                                           "the word stale inside a line\n", "a line is held until it ends")
        shaded.write("  no record\n")
        self.assertTrue(plain.getvalue().endswith("  \x1b[2munknown\x1b[0m  no record\n"))
        shaded.write("           stale\n")
        self.assertTrue(plain.getvalue().endswith("           stale\n"), "a word a fold left alone is not a row's lead")

    def test_a_line_shown_before_it_ends_keeps_the_shade_of_its_lead(self):
        plain = io.StringIO()
        shaded = page.Shaded(plain)
        print("  stale", end="", file=shaded, flush=True)
        print("    closure", file=shaded)
        self.assertEqual(plain.getvalue(), "  \x1b[33mstale\x1b[0m    closure\n")

    def test_only_a_terminal_that_can_show_them_is_shaded_and_never_against_the_persons_wish(self):
        with mock.patch.dict(os.environ, clear=True):
            self.assertTrue(page.shades(Terminal()))
            self.assertFalse(page.shades(io.StringIO()), "a pipe gets plain text")
        with mock.patch.dict(os.environ, {"TERM": "dumb"}, clear=True):
            self.assertFalse(page.shades(Terminal()))
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}, clear=True):
            self.assertFalse(page.shades(Terminal()))

    def test_a_command_run_at_a_terminal_is_shaded_end_to_end(self):
        tmp = Path(tempfile.mkdtemp(prefix="taos-shades-"))
        self.addCleanup(shutil.rmtree, str(tmp), True)
        home = str(demo.build(tmp).home)
        _, screen = seen("--home", home, "status", NO_COLOR="", TERM="xterm")
        self.assertIn("  \x1b[32mholds\x1b[0m    nothing is closed yet", screen)
        _, plain = seen("--home", home, "status", NO_COLOR="", TERM="dumb")
        self.assertNotIn("\x1b[", plain)


class Status(Project):
    """`taos status` at a terminal answers first. A pipe, and `--full`, get what an agent is told."""

    def test_a_person_gets_answers_first_then_the_work_then_what_waits_for_them(self):
        code, out = seen("--home", self.home, "status")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("Pendulum  "))
        answers = [line.split()[0] for line in lines[2:lines.index("In hand") - 1] if not line.startswith("   ")]
        self.assertTrue(answers and set(answers) <= set(page.ANSWERS), "every row above the work is led by one of the four words")
        self.assertEqual(out.count(" More: ./taos "), len(answers), "each answer ends with the command that says more")
        self.assertLess(lines.index("In hand"), lines.index("Waiting for you"))
        self.assertTrue(lines[-1].endswith("./taos status --full"))
        self.assertLessEqual(len(lines), 24, "it fits one screen")
        self.assertLessEqual(max(len(line) for line in lines), 80, "and one width")

    def test_a_new_project_holds_and_a_changed_input_makes_its_closed_task_stale(self):
        _, before = seen("--home", self.home, "status")
        self.assertIn("  holds    nothing is closed yet, so nothing has gone stale. More: ./taos why", before)
        self.assertIn("  holds    every summary matches its sources.", before, "a project just set up starts clean")
        demo.play(self.paths)                                       # closes PEN-1, then measures one swing again
        _, after = seen("--home", self.home, "status")
        self.assertIn("  stale    1 of 1 closed task(s) no longer stand as recorded: PEN-1.", after)

    def test_what_is_left_out_is_counted(self):
        data = projections.status(self.paths)
        task = {"id": "PEN-9", "title": "one of many", "owner_agent": "codex", "next_action": "the next thing"}
        data["hot"], data["decisions"] = [task] * 30, [{"id": "D-1", "question": "which?"}] * 10
        lines = [line.replace(projections.NBSP, " ") for line in projections.person_status(self.paths, data)]
        self.assertIn("  and 24 more: taos task list", lines)
        self.assertIn("  and 6 more: taos decide list", lines)
        data["kernels"] = []
        self.assertIn("unknown", " ".join(projections.person_status(self.paths, data)), "no summaries listed is not `holds`")

    def test_nothing_set_up_is_said_in_plain_words(self):
        empty = tempfile.mkdtemp(prefix="taos-empty-")
        self.addCleanup(shutil.rmtree, empty, True)
        _, screen = seen("--home", empty, "status")
        self.assertTrue(screen.startswith("Nothing is set up here yet"))
        self.assertIn("./taos demo", screen)

    def test_a_pipe_and_full_get_what_an_agent_is_told(self):
        _, piped, _ = said("--home", self.home, "status")
        _, full = seen("--home", self.home, "status", "--full")
        self.assertEqual(full.replace("./taos", "taos"), piped.replace("./taos", "taos"), "the same text, however taos was started")
        self.assertTrue(piped.startswith("TAOS Pendulum |"), "the agent's text is untouched")
        self.assertNotEqual(piped, seen("--home", self.home, "status")[1])


if __name__ == "__main__":
    unittest.main()
