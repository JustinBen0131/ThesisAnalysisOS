"""The front door as a page: it loads, it does what `taos use` does, and it answers only this computer."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from helpers import REPO, cleanup, make_home
from taos_core import welcome


class WelcomePage(unittest.TestCase):
    def setUp(self) -> None:
        tmp, self.paths = make_home()
        self.addCleanup(cleanup, tmp)
        self.work = Path(tempfile.mkdtemp()).resolve() / "my-analysis"
        self.addCleanup(shutil.rmtree, str(self.work.parent), True)
        shutil.copytree(str(REPO / "examples" / "measurement"), str(self.work), ignore=shutil.ignore_patterns("__pycache__"))
        self.server, self.address = welcome.serve(self.paths, open_browser=False)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base, self.key = self.address.split("/?key=")

    def ask(self, route: str, body=None, key=None, host=None):
        headers = {"X-TAOS-Key": self.key if key is None else key, "Content-Type": "application/json"}
        if host:
            headers["Host"] = host
        request = urllib.request.Request(self.base + route, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as got:
                return got.status, got.read().decode("utf-8")
        except urllib.error.HTTPError as refused:
            return refused.code, refused.read().decode("utf-8")

    def test_the_page_opens_on_a_try_asks_two_things_and_loads_nothing_from_outside(self) -> None:
        code, page = self.ask("/?key=" + self.key)
        self.assertEqual(code, 200)
        for shown in ("A result holds until a file under it changes.", "Try it on a practice result", "Now your folder",
                      "Your folder", "Your assistants"):
            self.assertIn(shown, page)
        self.assertLess(page.index('id="try"'), page.index('id="folder"'), "the try comes before any question")
        self.assertNotIn("How do you like to work?", page)
        self.assertNotIn("__KEY__", page)
        self.assertNotIn("http://", page.replace(self.base, ""))
        self.assertNotIn("https://", page)
        self.assertTrue(self.address.startswith("http://127.0.0.1:"))

    def test_the_page_stays_short(self) -> None:
        page = self.ask("/?key=" + self.key)[1]
        shown = re.sub(r"<(style|script)\b.*?</\1>", " ", page, flags=re.S)
        words = re.sub(r"<[^>]+>", " ", shown).split()
        self.assertLess(len(words), 110, "the page a person first sees is a few lines, not a manual: {0} words".format(len(words)))

    def test_it_sets_the_folder_up_offers_the_check_already_there_and_runs_it(self) -> None:
        code, said = self.ask("/api/start", {"folder": str(self.work), "assistants": ["Claude", "ChatGPT"]})
        got = json.loads(said)
        self.assertEqual(code, 200, said)
        self.assertEqual(sorted(got["written"]), [".taos-link.json", "AGENTS.md", "CLAUDE.md"])
        for name in got["written"]:
            self.assertTrue((self.work / name).is_file(), name)
        offered = got["suggested_checks"][0]
        self.assertIn("analysis/check.py", offered["command"])
        copies = [step["copy"] for step in got["next"]]
        taos = welcome._taos(self.paths)
        self.assertEqual(shlex.split(taos), [str(self.paths.launcher)], "this copy is not on the shell's path, so its own path is typed")
        self.assertEqual(copies[-2:], [taos + " why", taos + " welcome"])
        self.assertTrue(any("`{0} why`".format(taos) in text for text in copies), "the pasted start names the command as it runs")
        self.assertTrue(any("four words" in text for text in copies), "ChatGPT gets a start it can be pasted")
        self.assertTrue(any(step["say"].startswith("Claude:") for step in got["next"]))
        code, said = self.ask("/api/start", {"folder": str(self.work), "check": "{0}: {1}".format(offered["name"], offered["command"])})
        self.assertTrue(json.loads(said)["checks"]["ok"], said)

    def test_a_refusal_comes_back_in_plain_words(self) -> None:
        code, said = self.ask("/api/start", {"folder": ""})
        self.assertEqual(json.loads(said), {"refused": "Pick or type a folder first."})
        code, said = self.ask("/api/start", {"folder": str(self.work / "analysis" / "check.py")})
        self.assertIn("refused", json.loads(said))
        self.assertFalse((self.work / ".taos-link.json").exists())

    def test_it_answers_only_this_computer_and_only_with_its_key(self) -> None:
        self.assertEqual(self.ask("/api/start", {"folder": str(self.work)}, key="wrong")[0], 403)
        self.assertEqual(self.ask("/api/start", {"folder": str(self.work)}, host="evil.example")[0], 403)
        self.assertEqual(self.ask("/?key=wrong")[0], 403)
        self.assertEqual(self.ask("/api/folders?key=wrong")[0], 403)
        self.assertFalse((self.work / ".taos-link.json").exists(), "a refused request set nothing up")

    def test_folders_can_be_picked_without_typing(self) -> None:
        code, said = self.ask("/api/folders?key={0}&under={1}".format(self.key, urllib.request.quote(str(self.work))))
        got = json.loads(said)
        self.assertEqual(got["here"], str(self.work))
        self.assertIn("analysis", got["inside"])
        self.assertEqual(got["up"], str(self.work.parent))


    def test_any_assistant_can_be_typed(self) -> None:
        typed = welcome.assistants("claude code, gpt and Cursor; cursor\nMy Lab Bot")
        self.assertEqual([(item["name"], item["reads"]) for item in typed],
                         [("Claude", "CLAUDE.md"), ("ChatGPT", None), ("Cursor", None), ("My Lab Bot", None)])
        self.assertEqual(len(welcome.assistants(", ".join("Agent {0}".format(n) for n in range(30)))), 30, "tens of assistants are fine")
        code, said = self.ask("/api/start", {"folder": str(self.work), "assistants": "Claude, Cursor"})
        steps = json.loads(said)["next"]
        self.assertTrue(any(step["say"].startswith("Claude:") and "CLAUDE.md" in step["say"] for step in steps))
        self.assertTrue(any(step["say"].startswith("Cursor, working in your folder") and step["copy"] == welcome.TELL for step in steps))
        self.assertTrue(any(step["say"].startswith("Cursor, in a chat window") and "four words" in step["copy"] for step in steps))

    def look(self, folder: str, who: str = ""):
        return json.loads(self.ask("/api/look?key={0}&folder={1}&assistants={2}".format(
            self.key, urllib.request.quote(folder), urllib.request.quote(who)))[1])

    def test_looking_at_a_folder_says_what_is_there_and_writes_nothing(self) -> None:
        before = sorted(str(path) for path in self.work.rglob("*"))
        seen = self.look(str(self.work), "Codex, ChatGPT")
        self.assertEqual(sorted(str(path) for path in self.work.rglob("*")), before, "looking wrote nothing")
        self.assertTrue(seen["ok"])
        self.assertFalse(seen["already"])
        self.assertGreater(seen["files"], 0)
        self.assertIn("analysis/check.py", seen["checks"][0]["command"])
        self.assertEqual(seen["says"], "Adds 3 small files to {0}. Nothing else there changes.".format(seen["folder"]))
        self.assertEqual([item["name"] for item in seen["assistants"]], ["Codex", "ChatGPT"])
        self.assertTrue(seen["same_as"].startswith(welcome._taos(self.paths) + " use "))
        self.assertFalse(self.look(str(self.work / "analysis" / "check.py"))["ok"])
        self.assertFalse(self.look(str(self.work / "no-such-folder"))["ok"])
        self.assertFalse(self.look("")["ok"])
        self.assertEqual(self.look(str(Path.home()))["says"], "Pick the folder your work is in.", "never a whole home folder by one tap")
        self.ask("/api/start", {"folder": str(self.work)})
        after = self.look(str(self.work))
        self.assertTrue(after["already"])
        self.assertEqual(after["files"], seen["files"], "the notes TAOS wrote are not counted as the person's files")

    def test_a_second_project_is_turned_away_before_the_button(self) -> None:
        other = self.work.parent / "second-study"
        other.mkdir()
        self.assertTrue(self.look(str(other))["ok"])
        self.ask("/api/start", {"folder": str(self.work)})
        seen = self.look(str(other))
        self.assertFalse(seen["ok"])
        self.assertEqual(seen["elsewhere"], str(self.work))
        self.assertEqual(seen["says"], "This copy of TAOS already keeps {0}. One copy keeps one project.".format(self.work))
        self.assertEqual(sorted(path.name for path in other.iterdir()), [], "nothing was written there")
        self.assertIn("refused", json.loads(self.ask("/api/start", {"folder": str(other)})[1]))
        opened = json.loads(self.ask("/api/folders?key=" + self.key)[1])
        self.assertEqual(opened["here"], str(self.work), "someone coming back lands on the folder this copy keeps")

    def test_half_a_folder_name_lists_the_folders_that_start_that_way(self) -> None:
        got = json.loads(self.ask("/api/folders?key={0}&under={1}".format(self.key, urllib.request.quote(str(self.work / "ana"))))[1])
        self.assertEqual(got["here"], str(self.work))
        self.assertEqual(got["inside"], ["analysis"])

    def test_the_words_on_the_page_follow_the_files(self) -> None:
        first = json.loads(self.ask("/api/start", {"folder": str(self.work)})[1])
        offered = first["suggested_checks"][0]
        self.ask("/api/start", {"folder": str(self.work), "check": "{0}: {1}".format(offered["name"], offered["command"])})

        def parts():
            return json.loads(self.ask("/api/standing?key={0}&task={1}".format(self.key, first["task"]))[1])["parts"]

        def words():
            return {part["name"]: part["state"] for part in parts() if part["kind"] == "check"}
        self.assertEqual(words(), {offered["name"]: "holds"})
        (self.work / "notes.txt").write_text("a file the check has not seen\n")
        self.assertEqual(words(), {offered["name"]: "stale"})
        self.assertEqual(parts()[0]["reason"], "changed since it passed: notes.txt (new)")
        self.assertEqual(welcome._files("workspace changed: +a.txt, -b.txt, c.csv and 2 more"),
                         "changed since it passed: a.txt (new), b.txt (removed), c.csv and 2 more")
        self.assertEqual(welcome._files("never run for this task"), "never run for this task")
        self.assertEqual(welcome._files("reads changed: data/a.csv; figures changed: +plot.png and 3 more"),
                         "changed since it passed: data/a.csv, plot.png (new) and 3 more",
                         "a project that names what its checks read gets the same plain words")
        ran = json.loads(self.ask("/api/check", {"task": first["task"]})[1])
        self.assertEqual([(result["name"], result["exit"]) for result in ran["ran"]], [(offered["name"], 0)])
        self.assertEqual(words(), {offered["name"]: "holds"}, "run again on the changed files, it holds again")
        self.assertEqual(self.ask("/api/check", {"task": first["task"]}, key="wrong")[0], 403)

    def test_a_check_of_your_own_is_a_plain_command(self) -> None:
        got = json.loads(self.ask("/api/start", {"folder": str(self.work), "check": "python3 analysis/check.py",
                                                 "assistants": "Claude, Codex"})[1])
        self.assertTrue(got["checks"]["ok"], got)
        self.assertEqual(len(got["checks"]["results"]), 1)
        self.assertIn("Claude and Codex: open them in this folder. They read AGENTS.md and CLAUDE.md there by themselves.",
                      [step["say"] for step in got["next"]])
        refused = json.loads(self.ask("/api/start", {"folder": str(self.work), "check": "no-such-command-zz --x"})[1])
        self.assertTrue("refused" in refused or not refused["checks"]["ok"], refused)
        self.assertIn("refused", json.loads(self.ask("/api/standing?key={0}&task=NOPE-9".format(self.key))[1]))

    def test_every_command_the_page_tells_a_person_to_copy_exists(self) -> None:
        got = json.loads(self.ask("/api/start", {"folder": str(self.work), "assistants": "Claude, Gemini"})[1])
        told = {step["copy"] for step in got["next"]} | {got["undo"], self.look(str(self.work))["same_as"]}
        taos = welcome._taos(self.paths)
        commands = sorted(shlex.split(text)[:2] for text in told if text.startswith(taos + " "))
        self.assertEqual([verb for _, verb in commands], ["bootstrap", "use", "welcome", "why"])
        for launcher, verb in commands:                              # run as pasted: the launcher the page named, from another folder
            ran = subprocess.run([sys.executable, launcher, verb, "--help"], capture_output=True, text=True, cwd=str(self.work))
            self.assertEqual(ran.returncode, 0, "{0} {1}: {2}".format(launcher, verb, (ran.stdout + ran.stderr)[:200]))

    def test_a_practice_result_goes_stale_fails_and_holds_again_on_real_files(self) -> None:
        def tried(do=None):
            said = self.ask("/api/try?key=" + self.key)[1] if do is None else self.ask("/api/try", {"do": do})[1]
            return json.loads(said)

        first = tried()
        self.assertEqual((first["word"], first["result"], first["data"], first["rounds"]), ("holds", "average = 4.0", "3, 4, 5", 0))
        changed = tried("change")
        self.assertEqual((changed["word"], changed["why"], changed["data"]), ("stale", "changed since it passed: data.csv", "3, 4, 8"))
        self.assertEqual(changed["result"], "average = 4.0", "the result still says the old number: only the word moved")
        checked = tried("check")
        self.assertEqual((checked["word"], checked["said"]), ("fails", "result.txt says 4.0. data.csv gives 5.0."))
        redone = tried("redo")
        self.assertEqual((redone["word"], redone["result"], redone["rounds"]), ("holds", "average = 5.0", 1))
        work = Path(first["folder"])
        (work / "data.csv").write_text("3\n4\n9\n")
        self.assertEqual(tried()["word"], "stale", "a file edited by hand moves the word too")
        self.assertEqual(tried("no such thing")["word"], "stale", "anything else a request names is only a look")
        self.assertEqual(self.ask("/api/try", {"do": "change"}, key="wrong")[0], 403)
        self.assertIsNone(welcome.use_mod._primary(self.paths), "the practice is not this copy's project")
        self.assertFalse(self.paths.state.exists() and any(self.paths.state.iterdir()), "and it left nothing in this copy's record")
        self.assertNotIn(str(self.paths.home), str(work))
        self.server.practice.close()
        self.assertFalse(work.exists(), "closing the page removes the practice folder")

    def test_someone_coming_back_lands_on_their_project_and_nothing_is_run(self) -> None:
        self.assertEqual(json.loads(self.ask("/api/kept?key=" + self.key)[1]), {}, "a new copy keeps nothing yet")
        first = json.loads(self.ask("/api/start", {"folder": str(self.work), "check": "python3 analysis/check.py"})[1])
        record = self.paths.events_file.read_text()
        back = json.loads(self.ask("/api/kept?key={0}&assistants=Cursor".format(self.key))[1])
        self.assertEqual((back["project"], back["task"], back["folder"]), (first["project"], first["task"], str(self.work)))
        self.assertEqual(back["suggested_checks"], [], "it has a check already")
        self.assertTrue(any(step["say"].startswith("Cursor") for step in back["next"]))
        self.assertEqual(back["next"][-1], {"say": "Open this page again:", "copy": welcome._taos(self.paths) + " welcome"})
        self.assertEqual(self.paths.events_file.read_text(), record, "coming back ran no check and wrote no record")

    def test_likely_work_is_offered_by_name_and_guarded_folders_are_left_alone(self) -> None:
        from unittest import mock
        root = self.work.parent / "someone"
        made = {"paper/main.tex": 300, "old-study/run.py": 100, "code/tool/.git/HEAD": 200, "Documents/private/plan.py": 400,
                "holiday-photos/beach.jpg": 500, "thesis/analysis/fit.py": 250, "taxes/2025.pdf": 600}
        for name in made:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text("x")
        for name, age in made.items():
            top = root / Path(name).parts[0] / (Path(name).parts[1] if name.startswith("code/") else "")
            os.utime(str(top), (1000 + age, 1000 + age))
            if name.startswith("code/"):
                os.utime(str(top / ".git"), (1000 + age, 1000 + age))
        with mock.patch.dict(os.environ, {"HOME": str(root)}):
            self.assertEqual(welcome.likely(self.paths), ["~/paper", "~/thesis", "~/code/tool", "~/old-study"],
                             "work by its file names, newest first; photos and papers are not work and Documents is never opened")
            opened = json.loads(self.ask("/api/folders?key=" + self.key)[1])
            self.assertEqual(opened["likely"], ["~/paper", "~/thesis", "~/code/tool", "~/old-study"])
            self.assertEqual(self.look(str(root))["says"], "Pick the folder your work is in.")
            with mock.patch.object(Path, "cwd", return_value=root / "paper"):
                self.assertEqual(json.loads(self.ask("/api/folders?key=" + self.key)[1])["here"], "~/paper",
                                 "run from inside your work, the page starts there")
            with mock.patch.object(Path, "cwd", return_value=self.paths.home / "docs"):
                self.assertEqual(json.loads(self.ask("/api/folders?key=" + self.key)[1])["here"], "~", "never inside a copy of TAOS")
        self.ask("/api/start", {"folder": str(self.work)})
        self.assertNotIn("likely", json.loads(self.ask("/api/folders?key=" + self.key)[1]), "a kept project needs no guesses")

    def test_taos_welcome_serves_the_same_page_and_closes_on_ctrl_c(self) -> None:
        import contextlib
        import io
        from unittest import mock
        from taos_core import cli
        seen = {}

        def visit() -> None:                                        # stands in for waiting on Ctrl-C
            address = out.getvalue().split("TAOS is open at ")[1].split()[0]
            with urllib.request.urlopen(address, timeout=20) as got:
                seen["page"] = got.read().decode("utf-8")
            raise KeyboardInterrupt

        out = io.StringIO()
        with mock.patch.object(cli, "WAIT", visit), mock.patch("webbrowser.open") as browser, \
                contextlib.redirect_stdout(out):
            code = cli.main(["--home", str(self.paths.home), "welcome", "--no-open"])
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().startswith("TAOS is open at http://127.0.0.1:"))
        self.assertIn("<", seen["page"])
        browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
