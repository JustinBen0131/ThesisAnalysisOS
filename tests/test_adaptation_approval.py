"""Human-reviewed checks take effect only after promotion and stop on retirement."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from helpers import REPO, cleanup, construct_example, make_home

from taos_core import atoms, events, proposals
from taos_core.store import atomic_write_json
from taos_core.util import TaosError


class TestAdaptationApproval(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.paths = make_home()
        self.addCleanup(cleanup, self.tmp)

    def propose(self, atom_id: str = "result-has-method") -> dict:
        return proposals.propose(
            self.paths, kind="atom", title="Keep the method with the result",
            body="A missing method makes the result hard to replay.", evidence=[], agent="codex",
            atom={"id": atom_id, "rule": "The method exists.",
                  "check": {"type": "file_must_exist", "target": "method.md"}},
        )

    def check_ids(self) -> set:
        return {row["id"] for row in atoms.check(self.paths)}

    def audit(self, proposal_id: str) -> list:
        return [row for row in events.read(self.paths) if row.get("proposal_id") == proposal_id]

    def cli(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO / "taos"), "--home", str(self.paths.home), *arguments],
            text=True, capture_output=True,
        )

    def test_cli_review_install_and_retire(self) -> None:
        definition = self.tmp / "atom.json"
        definition.write_text(json.dumps({
            "id": "result-has-method", "rule": "The method exists.",
            "check": {"type": "file_must_exist", "target": "method.md"},
        }), encoding="utf-8")
        queued = self.cli("propose", "--agent", "codex", "--kind", "atom", "--title", "Keep the method",
                          "--body", "Flag a missing method file.", "--atom-json", str(definition))
        self.assertEqual(queued.returncode, 0, queued.stderr)
        proposal_id = proposals.open_proposals(self.paths)[0]["id"]
        self.assertNotIn("result-has-method", self.check_ids())
        accepted = self.cli("proposals", "decide", proposal_id, "--status", "accepted", "--by", "human")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertNotIn("result-has-method", self.check_ids())
        installed = self.cli("atoms", "promote", proposal_id, "--by", "human")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        checked = self.cli("atoms", "check", "--json")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertFalse(next(row for row in json.loads(checked.stdout) if row["id"] == "result-has-method")["ok"])
        (self.paths.home / "method.md").write_text("Method\n", encoding="utf-8")
        checked = self.cli("atoms", "check", "--json")
        self.assertTrue(next(row for row in json.loads(checked.stdout) if row["id"] == "result-has-method")["ok"])
        retired = self.cli("atoms", "retire", "result-has-method", "--by", "human", "--reason", "Superseded.")
        self.assertEqual(retired.returncode, 0, retired.stderr)
        self.assertNotIn("result-has-method", self.check_ids())
        retry = self.cli("atoms", "promote", proposal_id, "--by", "human")
        self.assertEqual(retry.returncode, 1, retry.stderr)
        self.assertIn("retired", retry.stderr)
        retired_again = atoms.retire(self.paths, "result-has-method", reason="A different reason.")
        self.assertEqual(retired_again["retirement_reason"], "Superseded.")
        self.assertEqual([row["type"] for row in self.audit(proposal_id)],
                         ["proposal_create", "proposal_decide", "proposal_decide", "atom_retire"])

    def test_nonhuman_cannot_decide_promote_or_retire(self) -> None:
        prop = self.propose()
        for decision in ("accepted", "rejected"):
            with self.subTest(decision=decision), self.assertRaisesRegex(TaosError, "human must"):
                proposals.decide(self.paths, proposal_id=prop["id"], status=decision, by="codex")
        with self.assertRaisesRegex(TaosError, "human must"):
            atoms.promote(self.paths, prop["id"], by="claude")
        denied = self.cli("atoms", "promote", prop["id"], "--by", "codex")
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(proposals.get(self.paths, prop["id"])["status"], "proposed")
        self.assertNotIn("result-has-method", self.check_ids())
        # The historical direct promotion of a pending proposal still works.
        atoms.promote(self.paths, prop["id"])
        with self.assertRaisesRegex(TaosError, "human must"):
            atoms.retire(self.paths, "result-has-method", reason="Test", by="system")
        self.assertIn("result-has-method", self.check_ids())

    def test_decline_is_final_and_has_no_effect(self) -> None:
        prop = self.propose()
        before = self.paths.atoms_file.read_bytes()
        declined = self.cli("proposals", "decide", prop["id"], "--status", "rejected", "--note", "No.")
        self.assertEqual(declined.returncode, 0, declined.stderr)
        self.assertEqual(proposals.get(self.paths, prop["id"])["decided_by"], "human")
        with self.assertRaisesRegex(TaosError, "rejected"):
            proposals.decide(self.paths, proposal_id=prop["id"], status="accepted")
        with self.assertRaisesRegex(TaosError, "rejected"):
            atoms.promote(self.paths, prop["id"])
        proposals.decide(self.paths, proposal_id=prop["id"], status="rejected")
        self.assertEqual(self.paths.atoms_file.read_bytes(), before)
        self.assertEqual([row.get("status") for row in self.audit(prop["id"])], [None, "rejected"])

    def test_unapproved_legacy_and_retired_records_cannot_activate(self) -> None:
        for status in ("accepted", "retired"):
            prop = self.propose()
            atomic_write_json(self.paths.proposals_dir / (prop["id"] + ".json"),
                              dict(prop, status=status, decided_by="codex"))
            with self.subTest(status=status), self.assertRaisesRegex(TaosError, status):
                atoms.promote(self.paths, prop["id"])
        self.assertNotIn("result-has-method", self.check_ids())

    def test_duplicate_concurrent_promotions_and_atom_id_reuse(self) -> None:
        prop = self.propose()
        cmd = ("atoms", "promote", prop["id"], "--by", "human")
        with ThreadPoolExecutor(max_workers=4) as threads:
            results = list(threads.map(lambda _: self.cli(*cmd), range(4)))
        self.assertTrue(all(result.returncode == 0 for result in results), [result.stderr for result in results])
        self.assertEqual(sum(row["id"] == "result-has-method" for row in atoms.load(self.paths)["atoms"]), 1)
        self.assertEqual([row.get("status") for row in self.audit(prop["id"])], [None, "accepted", "promoted"])
        reused = self.propose()
        with self.assertRaisesRegex(TaosError, "already exists"):
            atoms.promote(self.paths, reused["id"])
        self.assertEqual(proposals.get(self.paths, reused["id"])["status"], "proposed")
        atoms.retire(self.paths, "result-has-method", reason="Superseded.")
        with self.assertRaisesRegex(TaosError, "cannot be reused"):
            atoms.promote(self.paths, reused["id"])

    def test_proposal_id_collision_keeps_the_original(self) -> None:
        prop = self.propose()
        with mock.patch.object(proposals, "short_id", return_value=prop["id"]), self.assertRaisesRegex(TaosError, "in use"):
            self.propose("different-atom")
        self.assertEqual(proposals.get(self.paths, prop["id"]), prop)

    def test_retry_repairs_interrupted_promotion_audit(self) -> None:
        prop = self.propose()
        emit = events.emit

        def interrupt_promoted(*args, **fields):
            if fields.get("status") == "promoted":
                raise OSError("interrupted after atom save")
            return emit(*args, **fields)

        with mock.patch.object(events, "emit", side_effect=interrupt_promoted):
            with self.assertRaisesRegex(OSError, "after atom save"):
                atoms.promote(self.paths, prop["id"])
        self.assertEqual(proposals.get(self.paths, prop["id"])["status"], "accepted")
        installed = atoms.promote(self.paths, prop["id"])
        self.assertEqual(atoms.promote(self.paths, prop["id"]), installed)
        self.assertEqual([row.get("status") for row in self.audit(prop["id"])], [None, "accepted", "promoted"])

    def test_interruption_before_activation_keeps_the_check_inactive(self) -> None:
        prop = self.propose()
        with mock.patch.object(events, "emit", side_effect=OSError("interrupted before activation")):
            with self.assertRaisesRegex(OSError, "before activation"):
                atoms.promote(self.paths, prop["id"])
        self.assertEqual(proposals.get(self.paths, prop["id"])["status"], "accepted")
        self.assertNotIn("result-has-method", self.check_ids())
        atoms.promote(self.paths, prop["id"])
        self.assertIn("result-has-method", self.check_ids())
        self.assertEqual([row.get("status") for row in self.audit(prop["id"])], [None, "accepted", "promoted"])

    def test_command_atoms_keep_readers_and_refuse_writers(self) -> None:
        construct_example(self.tmp, self.paths)
        reader = {"id": "task-is-present", "rule": "The first task exists.",
                  "check": {"type": "taos_command_exit_zero", "argv": ["taos", "task", "show", "CMP-1", "--json"]}}
        prop = proposals.propose(self.paths, kind="atom", title="Check first task", body="Keep the task findable.",
                                 evidence=[], agent="codex", atom=reader)
        atoms.promote(self.paths, prop["id"])
        waiting = self.propose()
        writer = {"id": "obsolete-command-atom", "rule": "An older write command atom.",
                  "check": {"type": "taos_command_exit_zero",
                            "argv": ["taos", "atoms", "promote", waiting["id"], "--by", "human"]}}
        with self.assertRaisesRegex(TaosError, "can only run these readers"):
            proposals.propose(self.paths, kind="atom", title="Try a writer", body="A command atom.",
                              evidence=[], agent="codex", atom=writer)
        store = atoms.load(self.paths)
        store["atoms"].append(writer)
        atomic_write_json(self.paths.atoms_file, store)
        checked = {row["id"]: row for row in atoms.check(self.paths)}
        self.assertTrue(checked["policy-layer-resolves"]["ok"])
        self.assertTrue(checked["task-is-present"]["ok"])
        self.assertFalse(checked["obsolete-command-atom"]["ok"])
        self.assertIn("can only run these readers", checked["obsolete-command-atom"]["detail"])
        self.assertEqual(proposals.get(self.paths, waiting["id"])["status"], "proposed")
        self.assertNotIn("result-has-method", checked)
