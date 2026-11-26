import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from qaos_core import store


class CleanAndSeal(unittest.TestCase):
    def test_unknown_is_null_never_a_number(self):
        cleaned = store.clean({"a": float("nan"), "b": np.float64("inf"), "c": np.array([1.0, np.nan]), "d": np.int64(3)})
        self.assertEqual(cleaned, {"a": None, "b": None, "c": [1.0, None], "d": 3})
        self.assertNotIn("NaN", store.canonical({"x": float("nan")}))

    def test_canonical_ignores_key_order(self):
        self.assertEqual(store.sha256_obj({"a": 1, "b": [2, 3]}), store.sha256_obj({"b": [2, 3], "a": 1}))
        self.assertNotEqual(store.sha256_obj({"a": 1}), store.sha256_obj({"a": 2}))

    def test_seal_notices_any_edit(self):
        sealed = store.seal({"sharpe": 0.41, "params": {"window": 200}})
        self.assertTrue(store.seal_holds(sealed))
        edited = json.loads(json.dumps(sealed))
        edited["sharpe"] = 0.91
        self.assertFalse(store.seal_holds(edited))
        self.assertFalse(store.seal_holds({"sharpe": 0.41}))

    def test_atomic_write_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "deep" / "x.json"
            store.write_json_atomic(path, {"v": np.float64(1.5), "n": float("nan")})
            self.assertEqual(store.read_json(path), {"v": 1.5, "n": None})
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["x.json"], "no temp file left behind")
            self.assertEqual(store.read_json(Path(folder) / "missing.json", "default"), "default")


class Chain(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "log.jsonl"
        self.log = store.ChainLog(self.path, clock=lambda: "2026-01-01T00:00:00Z")
        for value in range(5):
            self.log.append({"kind": "trial", "value": value})

    def tearDown(self):
        self.folder.cleanup()

    def _lines(self):
        return self.path.read_text(encoding="utf-8").splitlines()

    def test_links_and_verifies(self):
        entries = self.log.read()
        self.assertEqual([entry["seq"] for entry in entries], [0, 1, 2, 3, 4])
        self.assertEqual(entries[0]["prev"], store.GENESIS)
        for before, after in zip(entries, entries[1:]):
            self.assertEqual(after["prev"], before["hash"])
        self.assertEqual(self.log.verify(), (True, "5 entries"))
        self.assertEqual(self.log.head(), entries[-1]["hash"])

    def test_an_edit_is_noticed(self):
        lines = self._lines()
        entry = json.loads(lines[2])
        entry["value"] = 99
        lines[2] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, detail = self.log.verify()
        self.assertFalse(ok)
        self.assertIn("entry 2", detail)

    def test_a_deleted_or_reordered_line_is_noticed(self):
        lines = self._lines()
        self.path.write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8")
        self.assertFalse(self.log.verify()[0])
        self.path.write_text("\n".join([lines[1], lines[0]] + lines[2:]) + "\n", encoding="utf-8")
        self.assertFalse(self.log.verify()[0])

    def test_reserved_fields_cannot_be_supplied(self):
        entry = self.log.append({"kind": "x", "seq": 400, "prev": "forged", "hash": "forged", "ts": "never"})
        self.assertEqual(entry["seq"], 5)
        self.assertEqual(entry["ts"], "2026-01-01T00:00:00Z")
        self.assertTrue(self.log.verify()[0])

    def test_two_writers_keep_one_chain(self):
        other = store.ChainLog(self.path)
        other.append({"kind": "from the other writer"})
        self.log.append({"kind": "after it"})       # the first writer's cached head is now out of date
        other.append({"kind": "and again"})
        ok, detail = self.log.verify()
        self.assertTrue(ok, detail)
        self.assertEqual(detail, "8 entries")

    def test_nan_cannot_enter_the_record(self):
        entry = self.log.append({"sharpe": float("nan")})
        self.assertIsNone(entry["sharpe"])
        self.assertTrue(all(math.isfinite(v) for e in self.log.read() for v in e.values() if isinstance(v, float)))


if __name__ == "__main__":
    unittest.main()
