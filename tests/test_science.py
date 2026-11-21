"""The science layer: predictions are sealed, graders are independent, limits survive."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from helpers import cleanup, construct_example, make_home

from taos_core import anchors, bank, changes, lessons, replay, rules
from taos_core import _science as sci
from taos_core.cli import main as cli
from taos_core.util import TaosError


class ScienceCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        construct_example(self.tmp, self.paths)

    def tearDown(self) -> None:
        cleanup(self.tmp)

    def run_cli(self, *argv: str) -> str:
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli(["--home", str(self.paths.home)] + list(argv))
        self.assertEqual(code, 0, out.getvalue())
        return out.getvalue()


class TestChanges(ScienceCase):
    def _register(self) -> str:
        return changes.register_change(
            self.paths, title="cache the inventory", builder="codex", cost="plan time", unit="seconds", baseline=40.0,
            predict_low=2.0, predict_high=8.0, control="files listed", control_baseline=1000.0, control_tolerance=0.0,
            canary="one folder first", rollback="delete the cache file")["id"]

    def test_confirmed_refuted_and_control_moved(self) -> None:
        for observed, control_observed, verdict in ((5.0, 1000.0, "CONFIRMED"), (30.0, 1000.0, "REFUTED"),
                                                    (5.0, 990.0, "CONTROL_MOVED")):
            change_id = self._register()
            changes.seal(self.paths, change_id, "codex")
            scored = changes.score(self.paths, change_id, grader="claude", observed=observed,
                                   control_observed=control_observed)
            self.assertEqual(scored["score"]["verdict"], verdict)
        record = changes.track_record(self.paths)
        self.assertEqual((record["CONFIRMED"], record["REFUTED"], record["CONTROL_MOVED"]), (1, 1, 1))

    def test_builder_cannot_grade_and_draft_cannot_be_scored(self) -> None:
        change_id = self._register()
        with self.assertRaises(TaosError):
            changes.score(self.paths, change_id, grader="claude", observed=5.0, control_observed=1000.0)
        changes.seal(self.paths, change_id, "codex")
        with self.assertRaises(TaosError):
            changes.score(self.paths, change_id, grader="codex", observed=5.0, control_observed=1000.0)

    def test_edit_after_seal_is_caught(self) -> None:
        change_id = self._register()
        changes.seal(self.paths, change_id, "codex")
        data = sci.load(self.paths, "changes", "changes")
        data["changes"][0]["prediction"]["high"] = 99.0  # move the goalposts after sealing
        sci.save(self.paths, "changes", data)
        with self.assertRaises(TaosError):
            changes.score(self.paths, change_id, grader="claude", observed=30.0, control_observed=1000.0)

    def test_receipts_are_counted_into_the_score(self) -> None:
        change_id = self._register()
        with self.assertRaises(TaosError):
            changes.receipt(self.paths, change_id, "codex", 4.0)
        changes.seal(self.paths, change_id, "codex")
        for value in (4.0, 6.0, 5.0):
            changes.receipt(self.paths, change_id, "codex", value)
        scored = changes.score(self.paths, change_id, grader="human", observed=5.0, control_observed=1000.0)
        self.assertEqual(scored["score"]["receipts"], 3)

    def test_bad_prediction_range_is_refused(self) -> None:
        with self.assertRaises(TaosError):
            changes.register_change(
                self.paths, title="x", builder="codex", cost="c", unit="u", baseline=1.0, predict_low=9.0,
                predict_high=2.0, control="k", control_baseline=0.0, control_tolerance=0.0, canary="c", rollback="r")


class TestLessons(ScienceCase):
    def _add(self, **overrides):
        fields = dict(title="name the test before the cause", words="define the problem first", said_on="2026-01-05",
                      mistake="a cause was stated before any test", why="the reply went out wrong",
                      moments=["reply", "statement"], scope="*", detect=[r"\blikely\b"])
        fields.update(overrides)
        return lessons.add(self.paths, **fields)

    def test_reports_only_where_it_applies_and_counts_hits(self) -> None:
        lesson = self._add()
        self.assertEqual(lessons.at(self.paths, "submit", agent="codex", text="likely fine"), [])
        self.assertEqual(lessons.at(self.paths, "reply", agent="codex", text="the fit converged"), [])
        hits = lessons.at(self.paths, "reply", agent="codex", text="The cause is LIKELY the calibration")
        self.assertEqual([hit["id"] for hit in hits], [lesson["id"]])
        lessons.at(self.paths, "statement", agent="claude", text="likely")
        self.assertEqual(lessons.repeats(self.paths)[0]["hits"], 2)

    def test_scope_and_retire(self) -> None:
        lesson = self._add(scope="AZ-7", detect=None)
        self.assertEqual(lessons.at(self.paths, "reply", agent="codex", task_id="AZ-9"), [])
        self.assertEqual(len(lessons.at(self.paths, "reply", agent="codex", task_id="AZ-7")), 1)
        lessons.set_status(self.paths, lesson["id"], "retired")
        self.assertEqual(lessons.at(self.paths, "reply", agent="codex", task_id="AZ-7"), [])

    def test_validation_and_freeze(self) -> None:
        with self.assertRaises(TaosError):
            self._add(moments=["sometime"])
        with self.assertRaises(TaosError):
            self._add(detect=["("])
        with self.assertRaises(TaosError):
            self._add(words="")
        self._add()
        frozen = lessons.freeze(self.paths, "held out 1")
        self.assertEqual(frozen["count"], 1)
        with self.assertRaises(TaosError):
            lessons.freeze(self.paths, "held out 1")

    def test_at_never_blocks_from_the_command_line(self) -> None:
        self._add()
        out = self.run_cli("lesson", "at", "reply", "--agent", "codex", "--text", "this is likely the cause")
        self.assertIn("define the problem first", out)


class TestReplay(unittest.TestCase):
    ROWS = [{"gib": 30.0, "harmful": True}, {"gib": 40.0, "harmful": True}, {"gib": 9.0, "harmful": False},
            {"gib": 12.0, "harmful": False}, {"gib": 2.0, "harmful": False}, {"gib": "n/a", "harmful": False}]

    def test_caught_and_needless(self) -> None:
        tight = replay.replay(self.ROWS, field="gib", op="at-least", threshold=8.0)
        self.assertEqual((tight["caught"], tight["harmful"], tight["needless"], tight["harmless"]), (2, 2, 2, 3))
        self.assertEqual(tight["unreadable"], 1)
        loose = replay.replay(self.ROWS, field="gib", op="at-least", threshold=16.0)
        self.assertEqual((loose["caught"], loose["needless"]), (2, 0))
        self.assertIn("caught 2 of 2 harmful", replay.sentence(loose))

    def test_at_most_and_bad_op(self) -> None:
        low = replay.replay([{"free": 5, "harmful": True}, {"free": 50, "harmful": False}], field="free",
                            op="at-most", threshold=10)
        self.assertEqual((low["caught"], low["needless"], low["missed"]), (1, 0, 0))
        with self.assertRaises(TaosError):
            replay.replay([], field="x", op="near", threshold=1)


class TestBank(ScienceCase):
    def _fill(self):
        ids = []
        for index in range(4):
            ids.append(bank.add_case(self.paths, request="request {0}".format(index), passage="rule {0}".format(index),
                                     source="notes.md", options=["A", "B"], expected="A")["id"])
        controls = [bank.add_case(self.paths, request="control {0}".format(index), passage="obvious", source="c.md",
                                  options=["A", "B"], expected="B", control=True)["id"] for index in range(2)]
        return ids, controls

    def test_prompts_hide_the_answer_and_differ_by_arm(self) -> None:
        self._fill()
        unhinted, named, supplied = (bank.prompts(self.paths, arm)[0] for arm in bank.ARMS)
        self.assertNotIn("expected", json.dumps([unhinted, named, supplied]))
        self.assertNotIn("passage", unhinted)
        self.assertIn("source", named)
        self.assertIn("passage", supplied)

    def test_scoring_needs_sealed_lines_and_qualified_reader(self) -> None:
        ids, controls = self._fill()
        answers = {"U": {ids[0]: "A", ids[1]: "B", ids[2]: "B", ids[3]: "B"},
                   "O": dict({case: "A" for case in ids}, **{case: "B" for case in controls})}
        with self.assertRaises(TaosError):
            bank.score(self.paths, "reader-1", answers)
        bank.seal_lines(self.paths, controls_right=2)
        with self.assertRaises(TaosError):
            bank.add_case(self.paths, request="late", passage="p", source="s", options=["A", "B"], expected="A")
        result = bank.score(self.paths, "reader-1", answers)
        self.assertTrue(result["qualified"])
        self.assertEqual((result["arms"]["U"]["right"], result["arms"]["O"]["right"]), (1, 4))
        self.assertEqual((result["gains"], result["losses"]), (3, 0))
        self.assertAlmostEqual(result["sign_test_p"], 0.25)
        weak = dict(answers, O=dict(answers["O"], **{controls[0]: "A"}))
        self.assertFalse(bank.score(self.paths, "reader-2", weak)["qualified"])

    def test_sign_test(self) -> None:
        self.assertAlmostEqual(bank.sign_test(7, 0), 0.015625)
        self.assertEqual(bank.sign_test(0, 0), 1.0)
        self.assertEqual(bank.sign_test(3, 3), 1.0)

    def test_seal_needs_controls(self) -> None:
        bank.add_case(self.paths, request="r", passage="p", source="s", options=["A", "B"], expected="A")
        with self.assertRaises(TaosError):
            bank.seal_lines(self.paths, controls_right=1)


class TestRules(ScienceCase):
    def test_expiry_scope_and_supersession(self) -> None:
        week = rules.add(self.paths, quote="freeze the plot style this week", said_on="2026-03-02", scope="budget",
                         expires="2026-03-08")
        self.assertEqual(len(rules.governing(self.paths, "budget", on="2026-03-05")), 1)
        self.assertEqual(rules.governing(self.paths, "budget", on="2026-03-09"), [])
        self.assertEqual(rules.governing(self.paths, "plots", on="2026-03-05"), [])
        self.assertEqual(rules.governing(self.paths, "budget", on="2026-03-01"), [])
        broad = rules.add(self.paths, quote="label every axis", said_on="2026-01-01", scope="plots")
        self.assertEqual(len(rules.governing(self.paths, "plots/labels", on="2026-06-01")), 1)
        rules.add(self.paths, quote="label every axis with units", said_on="2026-02-01", scope="plots",
                  supersedes=broad["id"])
        quotes = [rule["quote"] for rule in rules.governing(self.paths, "plots", on="2026-06-01")]
        self.assertEqual(quotes, ["label every axis with units"])
        self.assertTrue(week["sha256"])

    def test_audit_finds_lapsed_replaced_and_edited_originals(self) -> None:
        week = rules.add(self.paths, quote="this week only", said_on="2026-03-02", scope="budget", expires="2026-03-08")
        rules.derive(self.paths, week["id"], "the plot style is frozen")
        self.assertEqual(rules.audit(self.paths, on="2026-03-05"), [])
        lapsed = rules.audit(self.paths, on="2026-03-20")
        self.assertEqual(len(lapsed), 1)
        self.assertIn("lapsed", lapsed[0]["reason"])
        data = sci.load(self.paths, "rules", "rules")
        data["rules"][0]["quote"] = "always"
        sci.save(self.paths, "rules", data)
        self.assertIn("changed", rules.audit(self.paths, on="2026-03-05")[0]["reason"])

    def test_dates_are_checked(self) -> None:
        with self.assertRaises(TaosError):
            rules.add(self.paths, quote="q", said_on="March 2", scope="x")


class TestAnchors(ScienceCase):
    def test_resolve_is_refused_until_both_anchors_and_a_prediction(self) -> None:
        adjustment = anchors.open_adjustment(self.paths, quantity="efficiency ratio", observed=0.80,
                                             proposed="re-tune a threshold", agent="codex")
        with self.assertRaises(TaosError):
            anchors.resolve(self.paths, adjustment["id"], after=1.0, by="human")
        anchors.anchor_method(self.paths, adjustment["id"], reference="reference analysis, section 5",
                              says="keeps the step and corrects downstream")
        anchors.anchor_control(self.paths, adjustment["id"], where="the control sample", value=0.90)
        with self.assertRaises(TaosError):
            anchors.resolve(self.paths, adjustment["id"], after=1.0, by="human")
        anchors.predict(self.paths, adjustment["id"], low=0.85, high=0.95)
        resolved = anchors.resolve(self.paths, adjustment["id"], after=1.0, by="human")
        self.assertFalse(resolved["resolution"]["within_prediction"])
        with self.assertRaises(TaosError):
            anchors.anchor_control(self.paths, adjustment["id"], where="again", value=1.0)

    def test_command_line_walkthrough(self) -> None:
        out = self.run_cli("anchor", "open", "--agent", "codex", "--quantity", "ratio", "--observed", "0.80",
                           "--proposed", "re-fit")
        adjustment_id = out.split()[1].rstrip(".")
        self.run_cli("anchor", "method", adjustment_id, "--reference", "ref", "--says", "does X")
        self.run_cli("anchor", "control", adjustment_id, "--where", "control", "--value", "0.90")
        self.run_cli("anchor", "predict", adjustment_id, "--range", "0.9", "1.0")
        self.assertIn("inside", self.run_cli("anchor", "resolve", adjustment_id, "--after", "0.94", "--by", "human"))


if __name__ == "__main__":
    unittest.main()
