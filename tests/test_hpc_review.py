"""Cross-check the independent output manifest, receipt bytes and proposed resource envelope."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from taos_core import hpc
from taos_core.util import TaosError

ROOT = Path(__file__).resolve().parents[1] / "examples/hpc"


class CampaignReviewTests(unittest.TestCase):
    def setUp(self):
        self.data = hpc.read_packet(ROOT / "campaign.json")

    def report(self):
        return hpc.review(self.data, ROOT)

    def test_checked_and_partial_outputs_remain_distinct(self):
        rows = self.report()["outputs"]
        self.assertEqual([(r["id"], r["action"], r["reported_count"], r["expected_count"]) for r in rows],
                         [("A", "keep", 2, 2), ("B", "keep", 3, 3), ("C", "retry", 0, 2)])
        for row in self.data["returns"]:
            receipt = row["receipt"]
            data = json.loads((ROOT / receipt["file"]).read_text())
            self.assertEqual(len(data["returned_readings"]), receipt["count"])
            self.assertEqual(data["returned_readings"] == data["expected_readings"], receipt["passed"])
        self.assertEqual(self.report()["batch"]["ids"], ["C"])

    def test_two_passing_versions_retain_distinct_packet_identities(self):
        previous = self.report()
        for row in self.data["expected"]:
            row["basis"]["recipe"] = "second-verified-version"
        for row in self.data["returns"]:
            row["receipt"]["basis"]["recipe"] = "second-verified-version"
        current = self.report()
        self.assertNotEqual(previous["packet_sha256"], current["packet_sha256"])
        self.assertEqual(previous["reviewer_sha256"], current["reviewer_sha256"])
        self.assertEqual(current["outputs"][0]["action"], "keep")
        self.assertEqual(current["outputs"][0]["basis"]["recipe"], "second-verified-version")
        self.assertEqual(current["packet_sha256"], self.report()["packet_sha256"])

    def test_changed_inputs_and_current_criteria_are_scoped(self):
        for field in hpc.BASIS:
            with self.subTest(field=field):
                self.data["expected"][0]["basis"][field] += "-revision"
                rows = self.report()["outputs"]
                self.assertEqual([r["action"] for r in rows], ["inspect", "keep", "retry"])
                self.assertIn(field, rows[0]["reason"].lower())
                self.assertEqual(rows[0]["recorded_basis"][field], self.data["returns"][0]["receipt"]["basis"][field])
                self.assertEqual(rows[0]["basis"][field], self.data["expected"][0]["basis"][field])
                self.assertIn(rows[0]["recorded_basis"][field], rows[0]["reason"])
                self.assertIn(rows[0]["basis"][field], rows[0]["reason"])
                self.assertEqual(self.report()["batch"]["state"], "hold")
                self.data["expected"][0]["basis"][field] = self.data["returns"][0]["receipt"]["basis"][field]

    def test_missing_live_or_uncertain_attempt_never_suggests_retry(self):
        for state, action in (("queued","wait"), ("running","wait"), ("unknown","inspect"), ("finished","inspect")):
            with self.subTest(state=state):
                self.data["returns"][2] = {"id":"C", "state":state, "source":"recorded attempt"}
                self.assertEqual(self.report()["outputs"][2]["action"], action)
                self.assertEqual(self.report()["batch"]["state"], "hold")
        self.data["returns"].pop()
        self.assertEqual(self.report()["outputs"][2]["action"], "inspect")

    def test_changed_or_unreadable_receipts_and_unproved_diagnosis(self):
        self.data["returns"][0]["receipt"]["sha256"] = "0" * 64
        self.data["returns"][1]["receipt"]["file"] = "missing.json"
        self.data["returns"][2]["diagnosis"]["sha256"] = "f" * 64
        self.assertEqual([r["action"] for r in self.report()["outputs"]], ["inspect"] * 3)
        self.assertEqual(self.report()["batch"]["state"], "hold")

    def test_failed_comparison_needs_a_cause(self):
        r = self.data["returns"][2]
        r.pop("diagnosis")
        self.assertEqual(self.report()["outputs"][2]["action"], "inspect")
        r["receipt"].update(count=2, passed=False)
        self.assertIn("independent output check failed", self.report()["outputs"][2]["reason"])
        r["state"] = "failed"
        self.assertEqual(self.report()["outputs"][2]["action"], "inspect")

    def test_manifest_disagreement_preserves_checked_rows_and_holds_expansion(self):
        self.data["manifest"]["total"] = 4
        report = self.report()
        self.assertIn("declares 4", report["next"])
        self.assertEqual(report["outputs"][0]["action"], "keep")
        self.assertEqual(report["batch"]["state"], "hold")
        self.data["manifest"]["total"] = 3
        self.data["returns"].append({"id":"other", "state":"finished"})
        self.assertEqual(self.report()["unexpected"], ["other"])
        self.assertEqual(self.report()["batch"]["state"], "hold")

    def test_duplicate_ids_or_json_keys_are_ambiguous(self):
        for field in ("expected", "returns"):
            self.data[field].append(self.data[field][0])
            with self.assertRaisesRegex(TaosError, "Conflicting"):
                self.report()
            self.data[field].pop()
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "packet.json"
            for bad in ('{"count":1,"count":2}', '{"count":NaN}'):
                file.write_text(bad)
                with self.assertRaises(TaosError):
                    hpc.read_packet(file)

    def test_hashes_are_restricted_to_the_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "packet"
            root.mkdir()
            outside = parent / "elsewhere.json"
            outside.write_bytes(b"other")
            (root / "escape").symlink_to(outside)
            named = hpc.EvidenceFiles(root)
            digest = hashlib.sha256(b"other").hexdigest()
            for ref in (str(outside), "../elsewhere.json", "escape"):
                self.assertIn("inside", named.check(ref, digest))
            self.assertEqual(named.used, 0)

    def configure_two_new_jobs(self):
        for name in ("D", "E"):
            row = copy.deepcopy(self.data["expected"][0])
            row["id"] = name
            row["basis"]["input"] = "source-" + name
            self.data["expected"].append(row)
            self.data["returns"].append({"id":name, "state":"unstarted", "source":"reconciled job inventory"})
        self.data["manifest"]["total"] = 5
        self.data["batch"].update(ids=["D","E"], parallel=2)
        return self.data["batch"]

    def test_batch_accounts_for_files_scratch_and_exact_limit(self):
        batch = self.configure_two_new_jobs()
        caps = batch["limits"]
        caps.update(free_mib=50, free_files=6, parallel=2, memory_mib=256, wall_seconds=90)
        report = self.report()["batch"]
        self.assertEqual(report["state"], "owner_review")
        self.assertEqual(report["estimates"], dict(jobs=2, concurrent=2, waves=1, elapsed_seconds=90,
                          worker_seconds=180, space_mib=50, files=6))
        self.assertTrue(any("all 50 MiB of storage" in warning for warning in report["warnings"]))
        for key in ("free_mib","free_files","parallel","memory_mib","wall_seconds"):
            with self.subTest(key=key):
                caps[key] -= 1
                self.assertEqual(self.report()["batch"]["state"], "hold")
                caps[key] += 1
        caps["min_job_seconds"] = 91
        self.assertIn("Group short jobs", self.report()["batch"]["issues"][0])

    def test_different_profile_unchecked_pilot_and_occupied_scope_hold(self):
        self.data["expected"][2]["profile"] = "heavy inputs"
        self.assertEqual(self.report()["batch"]["state"], "hold")
        self.data["batch"]["ids"] = ["A"]
        self.assertEqual(self.report()["batch"]["state"], "hold")
        self.data["batch"]["pilot_id"] = "missing"
        self.assertEqual(self.report()["batch"]["state"], "hold")

    def test_cloud_budget_and_workstation_aggregate_memory(self):
        batch = self.configure_two_new_jobs()
        self.data["setting"] = "aws"
        self.assertEqual(self.report()["batch"]["state"], "hold")
        batch["measured"]["cost_minor"] = 12
        batch["limits"].update(currency="USD", budget_minor=23)
        batch["measured"]["currency"] = "EUR"
        different = self.report()["batch"]
        self.assertEqual(different["state"], "hold")
        self.assertNotIn("cost_minor", different["estimates"])
        self.assertTrue(any("different currencies" in problem for problem in different["issues"]))
        batch["measured"]["currency"] = "USD"
        self.assertEqual(self.report()["batch"]["state"], "hold")
        batch["limits"]["budget_minor"] = 24
        self.assertEqual(self.report()["batch"]["state"], "owner_review")
        self.data["setting"] = "local"
        batch["limits"]["shared_memory_mib"] = 511
        self.assertEqual(self.report()["batch"]["state"], "hold")
        batch["limits"]["shared_memory_mib"] = 512
        self.assertEqual(self.report()["batch"]["state"], "owner_review")

    def test_zero_measurement_is_distinct_from_an_unknown(self):
        self.data["batch"]["measured"].update(output_mib=0, scratch_mib=0)
        self.data["batch"]["limits"]["free_mib"] = 0
        self.assertEqual(self.report()["batch"]["state"], "owner_review")
        for value in (None, True, -1, 1.5, "1"):
            self.data["batch"]["measured"]["scratch_mib"] = value
            self.assertEqual(self.report()["batch"]["state"], "hold")

    def test_local_brief_quotes_researcher_question_as_data(self):
        message = hpc.brief("What about {guidance} for B?", "slurm")
        self.assertIn("What about {guidance} for B?", message)
        self.assertIn("accounting record", message)
        self.assertIn("./taos hpc review campaign.json --json", message)
