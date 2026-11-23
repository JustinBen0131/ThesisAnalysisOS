"""Independent fixture checks and adverse cases for the public transit recording."""

import copy
import csv
import io
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO
from evals import transit_workflow as transit


class TransitWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = transit.load_record()
        spec = importlib.util.spec_from_file_location("service_count", transit.FIXTURE / "count.py")
        cls.counter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.counter)

    def test_monday_and_tuesday_from_the_individual_rows(self):
        for day in ("monday", "tuesday"):
            def rows(name):
                with (transit.FIXTURE / f"{day}-{name}.csv").open(newline="") as handle:
                    return list(csv.DictReader(handle))
            schedule, dispatch = rows("schedule"), rows("dispatch")
            scheduled = {row["trip"]: row["scheduled_at"] for row in schedule}
            dispositions = {row["trip"]: row["disposition"] for row in dispatch}
            missing = scheduled.keys() - dispositions.keys()
            canceled = {k for k, v in dispositions.items() if v == "canceled"}
            on_time = sum(v == "on_time" for v in dispositions.values())
            departed = sum(v in {"on_time", "late"} for v in dispositions.values())
            obs = self.record["observations"][day]
            self.assertEqual((len(scheduled), len(dispositions)), (len(schedule), len(dispatch)))
            self.assertEqual((len(schedule), departed, on_time), (obs["scheduled"], obs["recorded"], obs["on_time"]))
            self.assertEqual(canceled, set(obs["canceled_trips"]))
            self.assertEqual(missing, set(obs["missing_trips"]))
            if day == "monday":
                self.assertEqual((scheduled["M17"], scheduled["M19"]), ("07:10", "07:22"))
                self.assertEqual(on_time / len(schedule), 0.8)
                self.assertEqual(round(100 * on_time / departed), 89)
            else:
                self.assertEqual(missing, {"T04", "T11"})
                self.assertIsNone(obs["scheduled_percent"])

    def test_one_missing_record_blocks_and_completing_it_permits_a_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tuesday-schedule.csv").write_text("trip,scheduled_at\nT04,06:00\nT11,07:00\n")
            dispatch = root / "tuesday-dispatch.csv"
            dispatch.write_text("trip,disposition\nT04,on_time\n")
            partial = self.counter.reconcile(root, "tuesday")
            self.assertEqual(partial["missing_trips"], ["T11"])
            self.assertIsNone(partial["scheduled_percent"])
            with dispatch.open("a") as handle:
                handle.write("T11,canceled\n")
            complete = self.counter.reconcile(root, "tuesday")
            self.assertEqual((complete["missing_trips"], complete["scheduled_percent"]), ([], 50))
            with dispatch.open("a") as handle:
                handle.write("T11,late\n")
            with self.assertRaisesRegex(ValueError, "duplicate trip"):
                self.counter.reconcile(root, "tuesday")

    def test_resealing_corrupt_display_or_causal_evidence_does_not_validate_it(self):
        for field, substitute in (("source", "holds"), ("repaired", "holds")):
            row = copy.deepcopy(self.record)
            slot = "check" if field == "source" else "acceptance"
            row["observations"]["controls"][field][slot] = substitute
            row["record_sha256"] = transit.record_digest(row)
            with self.assertRaisesRegex(ValueError, field):
                transit.validate(row)
        row = copy.deepcopy(self.record)
        row["records"]["source-dispatch"]["output"] = row["records"]["baseline-dispatch"]["output"]
        row["record_sha256"] = transit.record_digest(row)
        with self.assertRaisesRegex(ValueError, "exactly M18"):
            transit.validate(row)

    def test_source_fingerprint_and_attached_receipt_are_checked(self):
        row = copy.deepcopy(self.record)
        row["sources"]["examples/transit/count.py"] = "0" * 64
        row["record_sha256"] = transit.record_digest(row)
        with self.assertRaisesRegex(ValueError, "sources changed"):
            transit.validate(row)
        row = copy.deepcopy(self.record)
        row["records"]["human-accept"]["output"] = "different"
        with self.assertRaisesRegex(ValueError, "digest"):
            transit.validate(row)

    def test_cli_reproduces_in_a_fresh_home(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-B", str(REPO / "evals/transit_workflow.py"), "--verify"],
                                    cwd=directory, text=True, capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("6 scenes", result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])


class TransitAdaptation(unittest.TestCase):
    def test_successor_handoffs_against_dispatch_rows(self):
        record = transit.load_adaptation_record()
        raw = record["records"]
        cases = record["observations"]["adaptation"]["cases"]
        with (transit.FIXTURE / "tuesday-dispatch.csv").open(newline="") as handle:
            dispatch = {row["trip"] for row in csv.DictReader(handle)}
        for stage, case in cases.items():
            original = stage in ("missing", "repaired")
            schedule = raw["original-timetable" if original else "changed-timetable"]["output"]
            missing = {row["trip"] for row in csv.DictReader(io.StringIO(schedule))} - dispatch
            self.assertEqual(set(case["missing_trips"]), missing)
            self.assertEqual(case["matches_dispatch"], set(case["named_trips"]) == missing)
        self.assertEqual(cases["holdout_stale"]["named_trips"], ["T04", "T11"])
        self.assertEqual(cases["holdout_stale"]["missing_trips"], ["T04", "T27"])
        self.assertFalse(cases["holdout_stale"]["matches_dispatch"])
        self.assertEqual(record["observations"]["adaptation"]["checks"]["holdout_stale"], "passes")

    def test_resealed_change_of_reviewer_or_wrong_holdout_is_rejected(self):
        for key, before, after in (("declined-receipt", '"decided_by": "human"', '"decided_by": "claude"'),
                                   ("holdout_stale-handoff", "T04, T11", "T04, T27")):
            record = transit.load_adaptation_record()
            self.assertIn(before, record["records"][key]["output"])
            record["records"][key]["output"] = record["records"][key]["output"].replace(before, after)
            record["observations"]["adaptation"] = transit.adaptation.observations(record["records"])
            record["record_sha256"] = transit.record_digest(record)
            with self.assertRaises(ValueError):
                transit.validate_adaptation(record)

    def test_adaptation_reproduces_in_a_fresh_home(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-B", str(REPO / "evals/transit_workflow.py"), "--adaptation", "--verify"],
                                    cwd=directory, text=True, capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
