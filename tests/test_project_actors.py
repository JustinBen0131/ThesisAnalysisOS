"""Exercise a project's named roles through its real command-line interface."""

import json
import subprocess
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from helpers import cleanup, example_answers, make_home
from taos_core import bootstrap, control, tasks, usage
from taos_core.store import utc_now


class ProjectActors(unittest.TestCase):
    def setUp(self):
        self.tmp, self.paths = make_home()
        self.addCleanup(cleanup, self.tmp)
        self.answers = example_answers(
            self.tmp, agents=["field-notes"], install_hooks_in_workspaces=False,
            workspaces=[{"path": str(self.tmp / "ws"), "primary": True, "agent": "any"}],
        )
        self.answers_file = self.tmp / "answers.json"
        self.construct(self.answers)

    def construct(self, answers):
        self.answers_file.write_text(json.dumps(answers), encoding="utf-8")
        self.cli("bootstrap", "construct", "--answers", str(self.answers_file), "--agent", "field-notes")

    def cli(self, *args, code=0):
        result = subprocess.run(
            [str(self.paths.launcher), "--home", str(self.paths.home), *args], cwd=self.tmp,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, code, (args, result.stdout, result.stderr))
        return result.stdout if code == 0 else result.stderr

    def data(self, *args):
        return json.loads(self.cli(*args, "--json"))

    def add(self, name):
        return self.data("bootstrap", "add-agent", name, "--by", "human")

    def test_concurrent_enrollment_and_retries(self):
        before = json.loads(self.paths.config_file.read_text())
        with ThreadPoolExecutor(3) as pool:
            receipts = list(pool.map(self.add, ["reader-one", "reader_two", "reader-one"]))
        self.assertEqual(sum(row["added"] for row in receipts), 2)
        roster = self.data("bootstrap", "status")["agents"]
        self.assertCountEqual(roster, ["field-notes", "reader-one", "reader_two"])
        after = json.loads(self.paths.config_file.read_text())
        for key in before.keys() - {"agents"}:
            self.assertEqual(after[key], before[key], key)
        events = self.data("events", "--type", "agent_added")
        self.assertCountEqual([row["name"] for row in events], ["reader-one", "reader_two"])
        self.assertTrue(all(row["agent"] == "human" for row in events))
        for name in ("human", "hUmAn", "SYSTEM", "system", "any", "../reader", "a" * 33):
            self.cli("bootstrap", "add-agent", name, "--by", "human", code=1)
        self.cli("bootstrap", "add-agent", "fourth", "--by", "reader-one", code=2)
        self.construct(self.answers)
        self.assertEqual(self.data("bootstrap", "status")["agents"], roster)
        self.assertIn("reader_two", self.cli("start", "--help"))
        for name in ("codex", "unknown"):
            self.cli("start", "--agent", name, "--task", "CMP-2", "--session", "same", code=2)
        self.assertEqual(self.data("claim", "status")["live"], [])

    def test_named_handoff_and_independent_grade(self):
        self.add("reader-one")
        self.add("reader_two")
        task = "CMP-2"
        start = ("--task", task, "--session", "same")
        self.cli("start", "--agent", "reader-one", *start)
        self.cli("start", "--agent", "reader_two", *start, code=4)
        self.cli("finish", "--agent", "reader_two", *start, "--state", "next", "--reason", "wait", code=4)
        current = self.data("capsule", task)["task"]
        self.assertEqual([s["provider"] for s in current["sessions"]], ["reader-one"])
        self.assertEqual(current["owner_agent"], "reader-one")
        self.cli("gate", "run", "--agent", "reader-one", "--task", task)
        parties = ("--from", "reader-one", "--to", "reader_two", "--session", "same")
        template = self.cli("handoff", "template", task, *parties)
        body = "\n".join("Read the gate record for CMP-2." if line.startswith("<") else line
                         for line in template.splitlines())
        doc = self.tmp / "handoff.md"
        doc.write_text(body.replace("Agent: reader-one", "Agent: human"))
        self.cli("handoff", "write", task, *parties, "--file", str(doc), code=1)
        doc.write_text(body)
        closed = self.data("finish", "--agent", "reader-one", *start, "--state", "review",
                           "--reason", "Check passed", "--evidence", "gate record", "--handoff-file", str(doc),
                           "--to", "reader_two")
        self.assertTrue(closed["released_claims"])
        work = self.data("start", "--agent", "reader_two", *start)
        self.assertEqual(work["handoff_head"].splitlines()[0], "Agent: reader-one")
        self.assertEqual(work["lane"]["workspace"], str(self.tmp / "ws"))
        self.assertEqual([s["provider"] for s in work["task"]["sessions"]], ["reader-one", "reader_two"])
        labels = [json.loads(line) for line in self.paths.labels_file.read_text().splitlines()]
        self.assertEqual([(r["agent"], r["counterpart"]) for r in labels if r["phase"] == "handoff"],
                         [("reader-one", "reader_two")])
        self.cli("propose", "--agent", "reader_two", "--kind", "retire", "--title", "Retire the reminder",
                 "--body", "The fixture exercises this directly.")
        self.cli("change", "register", "--agent", "reader-one", "--title", "Check the interval", "--cost", "delay",
                 "--unit", "seconds", "--baseline", "3", "--predict", "1", "2", "--control", "count",
                 "--control-baseline", "1", "--control-tolerance", "0", "--canary", "fixture", "--rollback", "restore")
        change = self.data("change", "list")["changes"][0]["id"]
        self.cli("change", "seal", change, "--agent", "reader-one")
        self.cli("change", "receipt", change, "--agent", "field-notes", "--value", "2")
        score = ("--observed", "2", "--control-observed", "1")
        self.cli("change", "score", change, "--grader", "reader-one", *score, code=1)
        self.cli("change", "score", change, "--grader", "reader_two", *score)
        self.assertEqual(self.data("change", "list")["changes"][0]["score"]["grader"], "reader_two")

    def test_concurrent_native_usage_does_not_belong_to_a_named_role(self):
        task = tasks.TaskStore(self.paths).get("CMP-2")
        stamp = utc_now()
        concurrent = {"agents": {"codex": {"totals": dict(usage.ZERO, input_tokens=100),
                                          "models": {"example-model": 1}}}}
        with patch.object(usage, "window", return_value=concurrent) as observed:
            named = control.outcome_vector(self.paths, task, stamp, stamp, agent="field-notes")
            observed.assert_not_called()
            native = control.outcome_vector(self.paths, task, stamp, stamp, agent="codex")
        self.assertEqual(native["input_tokens"], 100)
        for key in ("model", "cost", "input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"):
            self.assertIsNone(named[key], key)
            self.assertEqual(named["provenance"][key], "unavailable", key)

    def test_workspace_assignment_and_invalid_setup(self):
        spaces = [{"path": str(self.tmp / "ws"), "agent": "field-notes"}]
        for agents in (["human"], ["SYSTEM"], ["a", "a"], [], "x"):
            self.assertTrue(bootstrap.validate_answers(dict(self.answers, agents=agents), self.paths))
        unknown = [dict(spaces[0], agent="unknown")]
        self.assertTrue(bootstrap.validate_answers(dict(self.answers, workspaces=unknown), self.paths))
        self.construct(dict(self.answers, workspaces=spaces))
        self.add("outside")
        self.cli("start", "--agent", "outside", "--task", "CMP-1", "--session", "unassigned", code=1)
        work = self.data("start", "--agent", "field-notes", "--task", "CMP-1", "--session", "assigned")
        self.assertEqual(work["lane"]["workspace"], spaces[0]["path"])
        self.assertEqual(work["lane"]["workspace_agent"], "field-notes")
