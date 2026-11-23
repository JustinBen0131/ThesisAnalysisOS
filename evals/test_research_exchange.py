"""The research exchange: one address per entry, and citation, thread and prediction kept apart."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
import exchange  # noqa: E402
from research_notes import FORMAT as NOTE  # noqa: E402


def record(value):
    return json.dumps({"cases": [{"id": "case-1", "value": value}]}).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def world(**studies):
    """A catalog and the supplied records for {name: raw bytes}."""
    return ({"dataset": [{"identifier": name, "distribution": {"sha256": sha(raw)}} for name, raw in studies.items()]},
            {sha(raw): raw for raw in studies.values()})


def entry(study, raw, observed, replies_to=None, stance=None, text="p", **extra):
    note = {"format": NOTE, "kind": "follow-up", "proposal": text, "scope": "s", "prediction": "could be wrong", "control": "c",
            "evidence": {"study": study, "sha256": sha(raw), "row_id": "case-1", "pointer": "/cases/0/value", "observed": observed}}
    return dict({"format": exchange.FORMAT, "stance": stance or ("proposes" if replies_to is None else "disputes"),
                 "replies_to": replies_to, "note": note}, **extra)


class TestVisitorCheckFiles(unittest.TestCase):
    def test_root_and_chained_replies_list_the_files_the_visitor_needs(self):
        root = {"id": "a", "replies_to": None, "record": "records/first.json"}
        reply = {"id": "b", "replies_to": "a", "record": "records/second.json"}
        followup = {"id": "c", "replies_to": "b", "record": "records/first.json"}
        rows = [root, reply, followup]
        self.assertEqual(exchange.entry_check_files(root, rows), (["records/first.json"], []))
        self.assertEqual(exchange.entry_check_files(followup, rows),
                         (["records/first.json", "records/second.json"], ["b", "a"]))


class ExchangeTest(unittest.TestCase):
    def setUp(self):
        self.a, self.b = record(3), record(7)
        self.root = entry("a.json", self.a, 3)
        self.reply = entry("b.json", self.b, 7, exchange.entry_id(self.root))

    def answers(self, entries, catalog, records, key="standing"):
        result = exchange.thread_standing(entries, catalog, records)
        return [result[exchange.entry_id(e)][key] for e in entries]

    def test_cross_study_reply_holds_when_both_records_are_supplied(self):
        catalog, records = world(**{"a.json": self.a, "b.json": self.b})
        self.assertEqual(self.answers([self.root, self.reply], catalog, records), ["holds", "holds"])

    def test_fresh_evidence_stays_readable_under_a_changed_parent(self):
        catalog, records = world(**{"a.json": record(4), "b.json": self.b})
        result = exchange.thread_standing([self.root, self.reply], catalog, records)
        reply = result[exchange.entry_id(self.reply)]
        self.assertEqual(result[exchange.entry_id(self.root)]["citation"], "stale")
        self.assertEqual((reply["citation"], reply["thread"], reply["standing"]), ("holds", "stale", "stale"))

    def test_a_change_below_never_reaches_the_entry_above(self):
        catalog, records = world(**{"a.json": self.a, "b.json": record(8)})
        self.assertEqual(self.answers([self.root, self.reply], catalog, records), ["holds", "stale"])

    def test_missing_parent_and_missing_record_are_unknown_never_holds(self):
        catalog, records = world(**{"a.json": self.a, "b.json": self.b})
        self.assertEqual(self.answers([self.reply], catalog, records, "thread"), ["unknown"])
        self.assertEqual(self.answers([self.reply], catalog, records), ["unknown"])
        del records[sha(self.a)]
        self.assertEqual(self.answers([self.root, self.reply], catalog, records, "citation"), ["unknown", "holds"])
        self.assertEqual(self.answers([self.root, self.reply], catalog, records), ["unknown", "unknown"])

    def test_misquote_fails_and_its_reply_goes_stale(self):
        wrong = entry("a.json", self.a, 9)
        reply = entry("b.json", self.b, 7, exchange.entry_id(wrong))
        catalog, records = world(**{"a.json": self.a, "b.json": self.b})
        self.assertEqual(self.answers([wrong, reply], catalog, records), ["fails", "stale"])

    def test_unlisted_study_is_unknown(self):
        catalog, records = world(**{"b.json": self.b})
        self.assertEqual(self.answers([self.root], catalog, records, "citation"), ["unknown"])

    def test_one_address_per_entry(self):
        before = exchange.entry_id(self.root)
        self.root["note"]["proposal"] = "p."
        self.assertNotEqual(before, exchange.entry_id(self.root))
        with self.assertRaises(ValueError):
            exchange.loads_entry(b'{"a": 1, "a": 2}')
        for text in (b'{"a": 0.5}', b'{"a": 1e3}', b'{"a": NaN}'):
            with self.assertRaises(ValueError):
                exchange.loads_entry(text)
        self.root["note"]["evidence"]["observed"] = 0.5
        with self.assertRaises(ValueError):
            exchange.check_shape(self.root)

    def test_shape_rules(self):
        self.reply["stance"] = "proposes"
        with self.assertRaises(ValueError):
            exchange.check_shape(self.reply)
        test = entry("b.json", self.b, 7, exchange.entry_id(self.root), stance="tests")
        with self.assertRaises(ValueError):
            exchange.check_shape(test)
        exchange.check_shape(dict(test, outcome="contradicts"))
        with self.assertRaises(ValueError):
            exchange.check_shape(dict(self.root, outcome="as_predicted"))
        with self.assertRaises(ValueError):
            exchange.check_shape(entry("a.json", self.a, 3, text="line\nbreak"))

    def test_closure_agrees_with_injected_labels(self):
        tally = exchange.closure(seed=7, exchanges=300)
        self.assertEqual(tally["entries_disagreeing"], 0)
        self.assertGreater(min(tally["expected_standing"].values()), 0)
        self.assertGreater(min(tally["injected"].values()), 0)
        self.assertEqual(tally, exchange.closure(seed=7, exchanges=300))

    def test_an_earlier_parent_stays_addressable_after_its_text_is_revised(self):
        first = entry("a.json", self.a, 3, text="first wording")
        later = entry("a.json", self.a, 3, text="second wording")
        reply = entry("b.json", self.b, 7, exchange.entry_id(first))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for kept in (first, reply):
                (folder / (exchange.entry_id(kept) + ".json")).write_bytes(exchange.canonical(kept))
            for path in folder.iterdir():
                self.assertEqual(path.stem, hashlib.sha256(path.read_bytes()).hexdigest())
            merged = exchange.with_history([later], exchange.load_history(folder))
            self.assertEqual([revision for _, revision in merged], ["current", "earlier", "earlier"])
            entries = [e for e, _ in merged]
            catalog, records = world(**{"a.json": self.a, "b.json": self.b})
            self.assertEqual(self.answers(entries, catalog, records), ["holds", "holds", "holds"])
            catalog, records = world(**{"a.json": record(4), "b.json": self.b})
            result = exchange.thread_standing(entries, catalog, records)
            old_reply = result[exchange.entry_id(reply)]
            self.assertEqual(result[exchange.entry_id(first)]["citation"], "stale")
            self.assertEqual((old_reply["citation"], old_reply["thread"]), ("holds", "stale"))
            self.assertEqual(exchange.with_history([first], exchange.load_history(folder))[1:], [(reply, "earlier")])
            (folder / (exchange.entry_id(first) + ".json")).write_bytes(exchange.canonical(first) + b"\n")
            with self.assertRaises(ValueError):
                exchange.load_history(folder)

    def test_an_accepted_file_is_a_project_entry_with_a_reviewed_source_and_no_typed_name(self):
        good = {"source": "https://github.com/JustinBen0131/ThesisAnalysisOS/issues/12", "accepted": "2026-11-22"}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / (exchange.entry_id(self.root) + ".json")
            path.write_text(json.dumps({"entry": self.root, "provenance": good}))
            self.assertEqual(exchange.load_accepted(folder), [(self.root, dict(good, words="project"))])
            for bad in (dict(good, source="https://example.org/issues/1"), dict(good, accepted="today"),
                        dict(good, accepted="2026-02-31"),
                        dict(good, origin="A lab"), dict(good, name="Someone")):
                path.write_text(json.dumps({"entry": self.root, "provenance": bad}))
                with self.assertRaises(ValueError):
                    exchange.load_accepted(folder)
            path.unlink()
            (folder / ("0" * 64 + ".json")).write_text(json.dumps({"entry": self.root, "provenance": good}))
            with self.assertRaises(ValueError):
                exchange.load_accepted(folder)

    def test_hidden_characters_and_oversized_entries_are_refused(self):
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            exchange.loads_entry(b" " * (exchange.MAX_INPUT_BYTES + 1))
        for hidden in ("\u202e", "\u200b", "\u2066", "\ufeff", "\u0007", "\u0085", "\u2028"):
            with self.assertRaises(ValueError):
                exchange.check_shape(entry("a.json", self.a, 3, text="plain" + hidden + "text"))
        with self.assertRaises(ValueError):
            exchange.check_shape(entry("a.json", self.a, [1] * 9000))
        exchange.check_shape(entry("a.json", self.a, 3, text="m/s\u00b2 and caf\u00e9 are ordinary text"))
        with self.assertRaisesRegex(ValueError, "NFC"):
            exchange.check_shape(entry("a.json", self.a, 3, text="cafe\u0301"))

if __name__ == "__main__":
    unittest.main()
