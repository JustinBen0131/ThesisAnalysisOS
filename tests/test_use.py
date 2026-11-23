"""`taos use`: a person's folder gets a record with no questions asked, and can be given back exactly as it was."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Dict, Tuple

from unittest import mock

from helpers import REPO, cleanup, make_home
from taos_core import basis, gates, projections, standing, use
from taos_core.util import TaosError

EXAMPLE = REPO / "examples" / "measurement"
CHECK = "\"{0}\" analysis/check.py".format(sys.executable)
WRITTEN = {"AGENTS.md", "CLAUDE.md", ".taos-link.json"}


class TestUse(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        self.addCleanup(cleanup, self.tmp)
        self.work = self.tmp / "Alex's first analysis"                     # a space and an apostrophe in the name
        shutil.copytree(str(EXAMPLE), str(self.work), ignore=shutil.ignore_patterns("__pycache__"))
        (self.work / "AGENTS.md").write_text("# Notes for whoever works here\n\nKeep the raw swings as measured.\n",
                                             encoding="utf-8")            # the person's own file, which must survive
        self.before = self.files()

    def files(self) -> Dict[str, bytes]:
        return {path.relative_to(self.work).as_posix(): path.read_bytes()
                for path in sorted(self.work.rglob("*")) if path.is_file() and "__pycache__" not in path.parts}

    def taos(self, *argv: str) -> Tuple[int, str, str]:
        """taos as a person starts it, with no input at all: stdin is closed, so a question would fail, not wait."""
        env = {key: value for key, value in os.environ.items() if key != "TAOS_HOME"}
        env["NO_COLOR"] = "1"
        done = subprocess.run([sys.executable, str(self.paths.home / "taos")] + list(argv), cwd=str(self.paths.home),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=300,
                              preexec_fn=lambda: os.close(0))
        return done.returncode, done.stdout, done.stderr

    def started(self, *more: str) -> str:
        code, out, err = self.taos("use", str(self.work), "--check", CHECK, *more)
        self.assertEqual(code, 0, out + err)
        return out

    def test_a_folder_named_with_a_space_and_an_apostrophe_is_set_up_without_a_question(self) -> None:
        out = self.started()
        self.assertIn("Alex's first analysis is set up.", out)
        self.assertIn("its first task is ALEX-1", out)
        self.assertRegex(out, r"\n  holds\s+check\s+ran now and passed \(exit 0\)\n")     # the check, run once, holds
        after = self.files()
        self.assertEqual(set(after) - set(self.before), WRITTEN - {"AGENTS.md"}, "only the link's own files are new")
        for name, data in self.before.items():                                 # and no file of theirs changed but one
            if name != "AGENTS.md":
                self.assertEqual(after[name], data, name)
        self.assertTrue(after["AGENTS.md"].startswith(self.before["AGENTS.md"]), "their words stay, the block follows")
        said = out.split("it wrote only this:\n", 1)[1].split("\n\n", 1)[0].splitlines()
        self.assertEqual([line.split()[0] for line in said[:-1]], ["AGENTS.md", "CLAUDE.md", ".taos-link.json"])
        self.assertIn("added at the end", said[0])
        self.assertIn("a new file holding only the TAOS block", said[1])

    def test_it_ends_with_three_commands_to_run_next(self) -> None:
        nexts = self.started().split("\nNext:\n", 1)[1].splitlines()
        self.assertEqual(len(nexts), 3)
        self.assertEqual([line.split()[:2] for line in nexts], [["./taos", "why"], ["./taos", "gate"], ["./taos", "status"]])
        for line in nexts:                                                     # each is a real command, as printed
            argv = shlex.split(line.strip().split("  ", 1)[0])
            done = subprocess.run(argv, cwd=self.paths.home, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, line + "\n" + done.stderr)

    def test_an_edited_data_file_turns_the_row_stale_names_the_file_and_why_says_so(self) -> None:
        self.started()
        with (self.work / "data" / "swings.csv").open("a", encoding="utf-8") as data:
            data.write("1.20,2.21\n")
        code, out, _ = self.taos("gate", "show", "--task", "ALEX-1")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"\n  stale\s+check\s+.*data/swings\.csv")
        code, out, _ = self.taos("why", "ALEX-1")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"\n  stale\s+check: workspace changed: data/swings\.csv")    # the kind word once
        code, out, _ = self.taos("why")                                        # and asked about everything, it says so too
        self.assertRegex(out, r"\n  stale\s+check: workspace changed: data/swings\.csv  \[ALEX-1\]")
        data = projections.refresh(self.paths)                                # as does the page a person reads for status
        self.assertIn(["stale", "ALEX-1 check: workspace changed: data/swings.csv", "taos why ALEX-1"],
                      projections.answers(self.paths, data))
        code, out, _ = self.taos("status")                                     # while what a pipe reads is as it was
        self.assertNotIn("Open work", out)
        self.assertNotIn("data/swings.csv", out)

    def test_the_undo_it_prints_leaves_the_folder_as_it_was(self) -> None:
        out = self.started()
        undo = re.search(r"leave the folder as it was: (.+)$", out, re.M).group(1)
        argv = shlex.split(undo)                                               # pasted, the quoted path is one word
        self.assertEqual(argv[1:3] + [Path(argv[3]).resolve()], ["bootstrap", "unlink-workspace", self.work.resolve()])
        self.assertEqual(argv[0], "./taos")
        done = subprocess.run(argv, cwd=self.paths.home, capture_output=True, text=True)
        code, err = done.returncode, done.stderr
        self.assertEqual(code, 0, err)
        self.assertEqual(self.files(), self.before)

    def test_another_folder_is_refused_in_plain_words_with_the_command_to_run_instead(self) -> None:
        self.started()
        other = self.tmp / "second study"
        other.mkdir()
        code, out, err = self.taos("use", str(other), "--check", CHECK)
        self.assertEqual(code, 1)
        self.assertIn("This copy of TAOS already keeps the record for Alex's first analysis", err)
        self.assertIn("  ./taos bootstrap link-workspace " + shlex.quote(str(other.resolve())), err)
        self.assertIn("  git clone " + use.CLONE, err)
        self.assertEqual(list(other.iterdir()), [], "a refused folder is not touched")

    def test_run_again_on_its_own_folder_it_adds_a_check_and_writes_nothing(self) -> None:
        self.started()
        code, out, err = self.taos("use", str(self.work), "--check", "fit: \"{0}\" analysis/fit.py".format(sys.executable))
        self.assertEqual(code, 0, err)
        self.assertIn("was already set up here", out)
        self.assertIn("Nothing new was written in", out)
        self.assertRegex(out, r"\n  holds\s+check\s+not run again: nothing it tested has changed")
        self.assertRegex(out, r"\n  holds\s+fit\s+ran now and passed")
        code, _, err = self.taos("use", str(self.work), "--prefix", "XY")
        self.assertEqual(code, 1)
        self.assertIn("already given the prefix ALEX", err)

    def test_names_and_prefixes_come_from_what_was_typed(self) -> None:
        self.assertEqual([use.prefix_for(name) for name in ("my-analysis", "Alex's analysis", "9 lives", "a")],
                         ["MYAN", "ALEX", "P9LI", "AX"])
        self.assertEqual([check["name"] for check in use.checks([
            CHECK, "fit: python3 analysis/fit.py", "make test", "python3 -m pytest", "pytest -q", "python3 analysis/check.py",
        ])], ["check", "fit", "test", "pytest", "pytest-2", "check-2"])

    def test_with_no_check_it_says_how_to_add_one(self) -> None:
        code, out, err = self.taos("use", str(self.work))
        self.assertEqual(code, 0, err)
        self.assertIn("No checks yet.", out)
        self.assertIn("taos use " + shlex.quote(str(self.work.resolve())) + " --check \"<command>\"", out)

    def test_straight_after_setup_nothing_reads_stale(self) -> None:
        self.started()
        code, out, _ = self.taos("why")
        self.assertEqual(code, 0)
        self.assertNotIn("stale", out, "the summaries were written of the project as set up")
        self.assertRegex(out, r"\n  holds\s+all 1 check\(s\)")

    def test_sentences_name_the_folder_as_typed_and_commands_the_full_path(self) -> None:
        code, out, err = self.taos("use", "../Alex's first analysis", "--check", CHECK)   # typed from inside the copy
        self.assertEqual(code, 0, err)
        self.assertIn("In ../Alex's first analysis it wrote only this:", out)
        self.assertIn("unlink-workspace " + shlex.quote(str(self.work.resolve())), out)

    def test_a_person_at_a_terminal_is_not_asked_who_they_are(self) -> None:
        stale = [{"kind": "check", "state": "stale"}]
        with mock.patch.object(gates, "_by_hand", return_value=True):
            self.assertEqual(standing._next("ALEX-1", stale), ["run the checks on the files as they are: taos gate run --task ALEX-1"])
        with mock.patch.object(gates, "_by_hand", return_value=False):
            self.assertIn("--agent <you>", standing._next("ALEX-1", stale)[0])

    def test_reads_narrows_what_the_checks_rest_on(self) -> None:
        self.started("--reads", "analysis", "--reads", "data/swings.csv")
        settings = projections.config_mod.load_soft(self.paths)["basis"]
        self.assertEqual(settings["domains"]["reads"], ["analysis/*", "data/swings.csv"])
        self.assertIn("figures/*", settings["ignore"])
        (self.work / "README.md").write_text("notes, not read by the check\n", encoding="utf-8")
        _, out, _ = self.taos("gate", "show", "--task", "ALEX-1")
        self.assertRegex(out, r"\n  holds\s+check")
        with (self.work / "data" / "swings.csv").open("a", encoding="utf-8") as data:
            data.write("1.20,2.21\n")
        _, out, _ = self.taos("gate", "show", "--task", "ALEX-1")
        self.assertRegex(out, r"\n  stale\s+check\s+.*data/swings\.csv")

    def test_a_folder_too_large_to_fingerprint_is_refused_with_the_command_to_run_again(self) -> None:
        with mock.patch.object(basis, "MAX_FILES", 3), self.assertRaises(TaosError) as refused:
            use.use(self.paths, self.work, [CHECK], typed="my folder")
        said = str(refused.exception)
        self.assertIn("my folder holds 5 files, more than a check can rest on at once", said)
        self.assertIn("Nothing was set up.", said)
        self.assertIn(" --reads analysis\n", said)
        self.assertFalse(self.paths.constructed())
        self.assertEqual(self.files(), self.before)
        with mock.patch.object(basis, "MAX_FILES", 3):                          # named, the same folder can be used
            result = use.use(self.paths, self.work, [CHECK], reads=["analysis", "data"])
        self.assertTrue(result["checks"]["ok"])

    def test_with_nothing_set_up_status_points_at_taos_use(self) -> None:
        self.assertIn("taos use <folder> --check \"<command>\"", projections.NOTHING_YET)

    def test_a_folder_another_copy_keeps_is_refused_before_anything_is_written(self) -> None:
        self.started()                                                         # copy A keeps the folder
        tmp, other = make_home()                                               # copy B, never set up
        self.addCleanup(cleanup, tmp)
        kept = self.files()
        for attempt in range(2):                                               # refused, and refused again on a retry
            with self.assertRaises(TaosError) as refused:
                use.use(other.__class__(other.home), self.work, [CHECK])
            self.assertIn("is already kept by another copy of TAOS", str(refused.exception))
            self.assertIn("bootstrap unlink-workspace " + shlex.quote(str(self.work.resolve())), str(refused.exception))
            self.assertFalse(other.constructed(), attempt)
            self.assertEqual(self.files(), kept)
        code, _, err = self.taos("bootstrap", "unlink-workspace", str(self.work))   # A lets it go, B takes it
        self.assertEqual(code, 0, err)
        self.assertTrue(use.use(other, self.work, [CHECK])["checks"]["ok"])
        code, _, err = self.taos("use", str(self.work), "--check", CHECK)       # and A, which kept it before, is refused
        self.assertEqual(code, 1)
        self.assertIn("is already kept by another copy of TAOS", err)

    def test_two_copies_starting_at_once_leave_one_owner_and_the_other_untouched(self) -> None:
        tmp, other = make_home()
        self.addCleanup(cleanup, tmp)
        env = {key: value for key, value in os.environ.items() if key != "TAOS_HOME"}
        both = [subprocess.Popen([sys.executable, str(paths.home / "taos"), "--home", str(paths.home), "use", str(self.work),
                                  "--check", CHECK], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True) for paths in (self.paths, other)]
        said = [process.communicate(timeout=120) for process in both]
        self.assertEqual(sorted(process.returncode for process in both), [0, 1], said)
        for paths, process in zip((self.paths, other), both):
            self.assertEqual(paths.constructed(), process.returncode == 0, "only the owner is set up")
            self.assertEqual(paths.tasks_file.exists(), process.returncode == 0)
        self.assertEqual([name for name in self.files() if ".tmp" in name], [], "no draft is left in the folder")

    def test_a_link_file_that_cannot_be_verified_is_refused_before_setup(self) -> None:
        (self.work / ".taos-link.json").write_text(
            '{"schema": "TAOS_LINK_V1", "taos_home": "%s", "blocks": []}' % self.paths.home, encoding="utf-8")
        kept = self.files()
        with self.assertRaises(TaosError) as refused:
            use.use(self.paths, self.work, [CHECK])
        self.assertIn("does not say which copy of TAOS keeps it", str(refused.exception))
        self.assertFalse(self.paths.constructed())
        self.assertEqual(self.files(), kept)

    def test_a_setup_that_fails_gives_the_folder_back(self) -> None:
        with mock.patch.object(use.bootstrap_mod, "construct", side_effect=TaosError("no")), self.assertRaises(TaosError):
            use.use(self.paths, self.work, [CHECK])
        self.assertEqual(self.files(), self.before)

    # -- a first run that fits the folder it is given ---------------------------------------------------------------

    def folder(self, name: str, files: Dict[str, str]) -> Path:
        made = self.tmp / name
        for path, text in files.items():
            (made / path).parent.mkdir(parents=True, exist_ok=True)
            (made / path).write_text(text, encoding="utf-8")
        return made

    def offered(self, name: str, files: Dict[str, str]) -> list:
        made = self.folder(name, files)
        return [(check["name"], check["command"], check["from"]) for check in use.suggestions(made, basis.listing(made))]

    def test_each_kind_of_check_a_folder_already_has_is_suggested_in_its_own_words(self) -> None:
        for name, files, expected in (
            ("make", {"Makefile": "all:\n\ttrue\ntest:\n\ttrue\ncheck :\n\ttrue\n"},
             [("tests", "make test", "Makefile"), ("check", "make check", "Makefile")]),
            ("pytest-folder", {"tests/test_scores.py": "def test_x():\n    pass\n"},
             [("tests", "python3 -m pytest -q", "tests/")]),
            ("pytest-named", {"pyproject.toml": "[tool.pytest.ini_options]\n"}, [("tests", "python3 -m pytest -q", "pyproject.toml")]),
            ("node", {"package.json": '{"scripts": {"test": "jest"}}'}, [("tests", "npm test", "package.json")]),
            ("node-default", {"package.json": '{"scripts": {"test": "echo \\"Error: no test specified\\" && exit 1"}}'}, []),
            ("rust", {"Cargo.toml": "[package]\n"}, [("tests", "cargo test", "Cargo.toml")]),
            ("go", {"go.mod": "module x\n"}, [("tests", "go test ./...", "go.mod")]),
            ("script", {"analysis/check.py": "", "verify.py": "", "deep/er/check.py": ""},
             [("check", "python3 analysis/check.py", "analysis/check.py"), ("verify", "python3 verify.py", "verify.py")]),
            ("shell", {"check.sh": ""}, [("check", "sh check.sh", "check.sh")]),
            ("paper", {"paper.tex": "\\documentclass{article}\n", "part.tex": "\\section{x}\n"},
             [("builds", "latexmk -pdf -halt-on-error paper.tex", "paper.tex")]),
            ("nothing", {"notes.txt": "x\n"}, []),
        ):
            self.assertEqual(self.offered(name, files), expected, name)
        both = self.offered("many", {"Makefile": "test:\n\ttrue\n", "tests/test_a.py": "", "Cargo.toml": "", "check.py": ""})
        self.assertEqual(len(both), 3, "at most three")
        self.assertEqual(len({name for name, _, _ in both}), 3, "each under a name of its own, so adding two keeps two")

    def test_a_suggested_check_is_printed_to_paste_and_nothing_is_run(self) -> None:
        made = self.folder("toy", {"Makefile": "test:\n\ttouch ran.txt\n", "analysis/check.py": "open('ran-too.txt', 'w')\n"})
        code, out, err = self.taos("use", str(made))
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(path.name for path in made.iterdir() if path.name.startswith("ran")), [], "nothing was run")
        where = shlex.quote(str(made.resolve()))
        self.assertIn("This folder already has some you could use:\n"
                      "  ./taos use {0} --check \"tests: make test\"\n"
                      "  ./taos use {0} --check \"check: python3 analysis/check.py\"\n"
                      "Or name your own: ./taos use {0} --check \"<command>\"".format(where), out)
        line = next(line for line in out.splitlines() if "check: python3" in line)      # pasted, it is that check by name
        code, out, err = self.taos(*shlex.split(line)[1:])
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r"\n  holds\s+check\s+ran now and passed")

    def test_json_carries_the_suggestions_for_an_agent_to_recommend(self) -> None:
        code, out, err = self.taos("use", str(self.work), "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["suggested_checks"],
                         [{"name": "check", "command": "python3 analysis/check.py", "from": "analysis/check.py"}])
        code, out, _ = self.taos("use", str(self.work), "--check", CHECK, "--json")
        self.assertEqual(json.loads(out)["suggested_checks"], [], "a project with a check is offered none")

    def test_with_nothing_closed_a_person_reads_the_open_work_first(self) -> None:
        self.started()
        found = standing.everything(self.paths)
        self.assertTrue(standing.summary(found).startswith("0 of 0 closed task(s) stand as recorded."), "a pipe, as before")
        self.assertTrue(standing.summary(found, person=True).startswith("Open work, each check on the files as they are now:"))

    # -- what a broad run of people will give it ---------------------------------------------------------------------

    def test_a_file_or_a_folder_that_cannot_be_written_is_refused_in_plain_words(self) -> None:
        code, _, err = self.taos("use", str(self.work / "README.md"))
        self.assertEqual(code, 1)
        self.assertIn("is a file. Name the folder it is in: taos use ", err)
        if os.geteuid() == 0:                                                  # root writes anywhere
            return
        os.chmod(str(self.work), 0o555)
        self.addCleanup(os.chmod, str(self.work), 0o755)
        code, _, err = self.taos("use", str(self.work), "--check", CHECK)
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("TAOS cannot write in", err)
        self.assertIn("Nothing was set up.", err)
        self.assertFalse(self.paths.constructed())

    def test_a_check_that_fails_at_setup_says_how_to_replace_or_drop_it(self) -> None:
        code, out, _ = self.taos("use", str(self.work), "--check", "no-such-program --flag")
        self.assertEqual(code, 1)
        where = shlex.quote(str(self.work.resolve()))
        self.assertIn("1 of 1 checks did not pass", out)
        self.assertIn("no-such-program: the program was not found.", out)
        self.assertIn("  ./taos use {0} --drop no-such-program".format(where), out)
        code, out, err = self.taos("use", str(self.work), "--drop", "no-such-program", "--check", CHECK)
        self.assertEqual(code, 0, err)
        self.assertNotIn("no-such-program", out)
        self.assertRegex(out, r"\n  holds\s+check\s+ran now and passed")
        code, _, err = self.taos("use", str(self.work), "--drop", "nope")
        self.assertEqual(code, 1)
        self.assertIn("There is no check named nope. The checks: check", err)

    def test_code_in_quotes_is_never_a_check_s_name(self) -> None:
        self.assertEqual([check["name"] for check in use.checks(["python3 -c 'import sys; sys.exit(0)'", "sh -c \"exit 0\"",
                                                                 "no-such-program --flag"])],
                         ["check", "check-2", "no-such-program"])
        self.assertEqual(use.shown(self.work, "."), "this folder")

    def test_a_folder_whose_copy_is_gone_says_how_to_go_on(self) -> None:
        self.started()
        tmp, other = make_home()
        self.addCleanup(cleanup, tmp)
        shutil.rmtree(str(self.paths.home))                                    # the copy that kept the folder is deleted
        with self.assertRaises(TaosError) as refused:
            use.use(other, self.work, [CHECK])
        said = str(refused.exception)
        self.assertIn("was kept by a copy of TAOS that is no longer there", said)
        self.assertIn("  rm " + shlex.quote(str(self.work.resolve() / ".taos-link.json")), said)
        self.assertFalse(other.constructed())
        (self.work / ".taos-link.json").unlink()                               # done as told, the folder can be used
        result = use.use(other, self.work, [CHECK])
        self.assertTrue(result["checks"]["ok"])
        self.assertIn("kept", result["written"]["AGENTS.md"], "the old copy's block is left, and that is said")

    def test_a_prefix_never_spells_a_word_nobody_wants_on_their_screen(self) -> None:
        made = {name: use.prefix_for(name) for name in ("analysis", "assessment", "cumulative", "shipping", "title-work",
                                                        "document", "Sextant data", "class notes", "passport")}
        self.assertEqual(made, {"analysis": "ANA", "assessment": "ASMN", "cumulative": "CMLT", "shipping": "SHIP",
                                "title-work": "TW", "document": "DOCU", "Sextant data": "SD", "class notes": "CLAS",
                                "passport": "PAS"})
        for prefix in made.values():
            self.assertRegex(prefix, r"^[A-Z][A-Z0-9]{1,7}$")
            self.assertFalse(any(stem in prefix for stem in use.REFUSED), prefix)

    def test_with_nothing_to_suggest_the_next_rows_keep_their_words_and_no_trailing_space(self) -> None:
        made = self.folder("writing", {"notes.md": "# notes\n", "draft.md": "# draft\n"})
        code, out, err = self.taos("use", str(made))
        self.assertEqual(code, 0, err)
        self.assertNotIn("This folder already has", out)
        self.assertIn("Add one, and it runs at once: ./taos use {0} --check \"<command>\"".format(shlex.quote(str(made.resolve()))), out)
        self.assertEqual(out.split("\nNext:\n", 1)[1].splitlines(), [
            "  ./taos task show WRIT-1  the task the checks will stand under",
            "  ./taos status            where everything stands",
            "  ./taos demo              the idea in a minute, on a small example"])
        self.assertEqual([line for line in out.splitlines() if line != line.rstrip()], [], "no line ends in spaces")


if __name__ == "__main__":
    unittest.main()
