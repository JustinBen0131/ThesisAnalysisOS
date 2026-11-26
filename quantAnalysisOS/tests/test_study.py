import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from qaos_core import store, strategies, toys
from qaos_core.data import Dataset
from qaos_core.study import Book, Study, StudyError, code_fingerprint, default_warmup, rebalance_mask

GRID = [{"window": w} for w in (20, 50, 100, 200)]


def toy_market(seed=14, r2=0.04, years=8):
    periods = years * 252
    raw = toys.latent_drift(1, periods, mu_ann=0.0, vol_ann=0.16, r2=r2, rng=toys.generator(seed))
    prices = toys.as_market(raw)[1][0]
    dates = np.busday_offset(np.datetime64("2010-01-01"), np.arange(periods + 1), roll="forward")
    return Dataset("toy", dates, ["TOY"], prices, 252.0, np.full(periods + 1, 0.00005))


def spec(dataset, **overrides):
    base = {"id": "QA-1", "title": "Trend on a toy", "hypothesis": "Trend earns a positive Sharpe.",
            "holdout_start": str(dataset.dates[dataset.dates.shape[0] // 2]), "strategy": "trend_sma", "grid": GRID,
            "decision": {"test": "sharpe", "z_min": 2.0}}
    base.update(overrides)
    return base


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.book = Book(Path(self.folder.name) / "book")
        self.data = toy_market()

    def tearDown(self):
        self.folder.cleanup()

    def register(self, **overrides):
        return Study.register(self.book, spec(self.data, **overrides), self.data)


class Registration(Base):
    def test_a_registration_is_sealed_and_logged(self):
        study = self.register()
        self.assertEqual(study.state(), "registered")
        self.assertTrue(store.seal_holds(study.prereg))
        self.assertEqual(study.trials.read()[0]["seal"], study.prereg["seal"])
        self.assertEqual(study.prereg["development"]["periods"] + study.prereg["holdout"]["periods"], self.data.dates.shape[0])
        self.assertEqual(study.prereg["engine"]["lag"], 1)
        self.assertEqual(study.prereg["engine"]["warmup"], 203)
        self.assertEqual(self.book.study_ids(), ["QA-1"])

    def test_what_is_refused(self):
        cases = {
            "a bad id": {"id": "study one"},
            "no hypothesis": {"hypothesis": " "},
            "no grid": {"grid": []},
            "the same configuration twice": {"grid": [{"window": 20}, {"window": 20}]},
            "an unknown strategy": {"strategy": "alchemy"},
            "an unknown test": {"decision": {"test": "vibes"}},
            "a holdout with no development before it": {"holdout_start": str(self.data.dates[50])},
            "a holdout after the data ends": {"holdout_start": "2099-01-01"},
            "an unknown rebalance rule": {"engine": {"rebalance": "whenever"}},
        }
        for label, override in cases.items():
            with self.assertRaises(StudyError, msg=label):
                self.register(**override)
        self.register()
        with self.assertRaises(StudyError, msg="registering the same id again"):
            self.register()

    def test_a_timing_test_that_cannot_reach_its_bar_is_refused(self):
        with self.assertRaises(StudyError) as caught:
            self.register(decision={"test": "timing", "z_min": 3.5})
        self.assertIn("rotations", str(caught.exception))
        self.register(decision={"test": "timing", "z_min": 2.0})

    def test_a_reused_holdout_is_on_the_record(self):
        first = self.register()
        self.assertEqual(first.prereg["holdout"]["already_opened_by"], [])
        second = self.register(id="QA-2")
        self.assertEqual(second.prereg["holdout"]["already_opened_by"], [], "nobody has opened it yet")
        first.scan(self.data)
        first.freeze(self.data, n_shifts=30)
        first.unblind(self.data, by="t", n_boot=200, n_shifts=30)
        with self.assertRaises(StudyError) as caught:
            self.register(id="QA-3")
        self.assertIn("QA-1", str(caught.exception))
        third = self.register(id="QA-3", prior_exposure="QA-1 opened this holdout and found the trend rule not confirmed.")
        self.assertEqual(third.prereg["holdout"]["already_opened_by"], ["QA-1"])

    def test_mixed_strategy_grids(self):
        study = self.register(grid=[{"strategy": "trend_sma", "params": {"window": 50}}, {"strategy": "hold", "params": {}}])
        self.assertEqual([g["strategy"] for g in study.grid()], ["trend_sma", "hold"])

    def test_warmup_and_masks(self):
        self.assertEqual(default_warmup([{"params": {"lookback": 252, "vol_window": 63}}], lag=1), 255)
        dates = self.data.dates
        self.assertIsNone(rebalance_mask("every", dates))
        self.assertEqual(rebalance_mask({"every": 5}, dates).sum(), int(np.ceil(dates.shape[0] / 5)))
        self.assertTrue(rebalance_mask("month_start", dates).sum() > 90)


class Blinding(Base):
    def test_a_strategy_never_sees_the_holdout_during_development(self):
        seen = []

        def spy(prices, **_):
            seen.append(prices.shape[-2])
            return np.zeros(prices.shape)

        strategies.REGISTRY["spy"] = spy
        try:
            study = self.register(strategy="spy", grid=[{"a": 1}, {"a": 2}])
            study.scan(self.data)
            self.assertEqual(set(seen), {study.prereg["development"]["periods"]})
        finally:
            del strategies.REGISTRY["spy"]

    def test_scan_logs_every_configuration_and_only_development_dates(self):
        study = self.register()
        rows = study.scan(self.data)
        self.assertEqual(len(rows), 4)
        self.assertEqual(study.state(), "developing")
        last_dev = study.prereg["development"]["last"]
        for row in rows:
            self.assertLessEqual(row["window"][1], last_dev)
            self.assertEqual(row["data"], study.prereg["development"]["fingerprint"])
        self.assertEqual(len([e for e in study.trials.read() if e["kind"] == "trial"]), 4)

    def test_the_order_of_operations_is_enforced(self):
        study = self.register()
        with self.assertRaises(StudyError, msg="freeze before scan"):
            study.freeze(self.data, n_shifts=30)
        with self.assertRaises(StudyError, msg="unblind before freeze"):
            study.unblind(self.data, by="t")
        study.scan(self.data)
        with self.assertRaises(StudyError, msg="unblind before freeze, after scan"):
            study.unblind(self.data, by="t")
        study.freeze(self.data, n_shifts=30)
        with self.assertRaises(StudyError, msg="scan after freeze"):
            study.scan(self.data)
        with self.assertRaises(StudyError, msg="freeze twice"):
            study.freeze(self.data, n_shifts=30)
        with self.assertRaises(StudyError, msg="unsigned unblinding"):
            study.unblind(self.data, by=" ")
        study.unblind(self.data, by="tester", n_boot=200, n_shifts=30)
        with self.assertRaises(StudyError, msg="the box opens once"):
            study.unblind(self.data, by="tester", n_boot=200, n_shifts=30)
        with self.assertRaises(StudyError, msg="amend after the search is over"):
            study.amend([{"window": 30}], "one more")
        self.assertEqual(study.state(), "unblinded")

    def test_amendments_are_allowed_logged_and_counted(self):
        study = self.register()
        study.scan(self.data)
        with self.assertRaises(StudyError):
            study.amend([{"window": 30}], "")
        study.amend([{"window": 30}, {"window": 20}], "wanted a faster rule")   # 20 is already there
        self.assertEqual(len(study.grid()), 5)
        with self.assertRaises(StudyError, msg="the new configuration has not been evaluated"):
            study.freeze(self.data, n_shifts=30)
        study.scan(self.data)
        frozen = study.freeze(self.data, n_shifts=30)
        self.assertEqual(frozen["trials"]["n"], 5)

    def test_holdout_systematics_wait_for_the_unblinding(self):
        study = self.register()
        study.scan(self.data)
        with self.assertRaises(StudyError):
            study.systematics(self.data)
        study.freeze(self.data, n_shifts=30)
        dev = study.systematics(self.data)
        self.assertLess(dev["variations"]["costs x4"], dev["variations"]["costs x0"])
        self.assertGreaterEqual(dev["total"], 0.0)
        with self.assertRaises(StudyError):
            study.systematics(self.data, window="holdout")
        study.unblind(self.data, by="t", n_boot=200, n_shifts=30)
        self.assertEqual(study.systematics(self.data, window="holdout")["window"], "holdout")


class Verdicts(Base):
    def run_study(self, data, **overrides):
        study = Study.register(self.book, spec(data, **overrides), data)
        study.scan(data)
        frozen = study.freeze(data, n_shifts=60)
        return study, frozen, study.unblind(data, by="tester", n_boot=300, n_shifts=60)

    def test_a_real_signal_is_confirmed(self):
        data = toy_market(seed=15, r2=0.04, years=20)
        study, frozen, result = self.run_study(data)
        self.assertEqual(result["verdict"], "confirmed", result["reasons"])
        self.assertGreaterEqual(result["decision"]["z"], 2.0)
        self.assertEqual(result["trials_counted"], 4)
        self.assertEqual(result["frozen"], frozen["seal"])
        self.assertGreater(result["z_by_test"]["timing"], 1.5)

    def test_noise_is_not(self):
        data = toy_market(seed=13, r2=0.0, years=20)
        study, frozen, result = self.run_study(data, id="QA-2")
        self.assertEqual(result["verdict"], "not_confirmed")
        self.assertTrue(result["reasons"])
        self.assertGreater(frozen["mixed_event"]["p_global"], 0.05)

    def test_a_declared_choice_is_recorded_as_one(self):
        study = self.register()
        study.scan(self.data)
        frozen = study.freeze(self.data, choice=2, n_shifts=30)
        self.assertEqual(frozen["chosen"]["params"], {"window": 100})
        self.assertIn("declared", frozen["selection"])

    def test_the_freeze_says_what_the_holdout_can_show(self):
        study = self.register()
        study.scan(self.data)
        outlook = study.freeze(self.data, n_shifts=30)["holdout_outlook"]
        self.assertAlmostEqual(outlook["years"], study.prereg["holdout"]["periods"] / 252.0, places=9)
        self.assertLessEqual(outlook["expected_z_after_haircut"], max(outlook["expected_z_if_development_is_truth"], 0.0))


class Standing(Base):
    def finished(self):
        study = self.register()
        study.scan(self.data)
        study.freeze(self.data, n_shifts=30)
        study.unblind(self.data, by="t", n_boot=200, n_shifts=30)
        return study

    def test_holds_then_stale_when_one_price_is_revised(self):
        study = self.finished()
        self.assertEqual(study.standing(self.data), ("holds", []))
        revised = Dataset("toy", self.data.dates, ["TOY"], self.data.prices.copy(), 252.0, self.data.rf)
        revised.prices[100, 0] *= 1.0001
        word, reasons = study.standing(revised)
        self.assertEqual(word, "stale")
        self.assertIn("registered", reasons[0])
        with self.assertRaises(StudyError):
            Study(self.book, "QA-1").systematics(revised)

    def test_more_history_with_the_same_past_still_holds(self):
        study = self.finished()
        extra = 30
        dates = np.concatenate([self.data.dates, np.busday_offset(self.data.dates[-1], np.arange(1, extra + 1))])
        prices = np.vstack([self.data.prices, self.data.prices[-1] * np.cumprod(np.full((extra, 1), 1.001), axis=0)])
        longer = Dataset("toy", dates, ["TOY"], prices, 252.0, np.concatenate([self.data.rf, np.full(extra, 0.00005)]))
        self.assertEqual(study.standing(longer)[0], "holds")

    def test_unknown_without_the_data(self):
        word, reasons = self.finished().standing(None)
        self.assertEqual(word, "unknown")
        self.assertTrue(reasons)

    def test_fails_when_a_sealed_record_is_edited(self):
        for name in ("prereg", "frozen", "result"):
            with self.subTest(record=name):
                self.tearDown()
                self.setUp()
                study = self.finished()
                path = study.dir / (name + ".json")
                record = json.loads(path.read_text())
                if name == "prereg":
                    record["decision"]["z_min"] = 0.5
                elif name == "frozen":
                    record["trials"]["n"] = 1
                else:
                    record["verdict"] = "confirmed"
                path.write_text(json.dumps(record))
                self.assertEqual(Study(self.book, "QA-1").standing(self.data)[0], "fails")

    def test_fails_when_a_record_is_resealed_behind_the_logs_back(self):
        study = self.finished()
        path = study.dir / "result.json"
        record = json.loads(path.read_text())
        record["verdict"] = "confirmed"
        path.write_text(json.dumps(store.seal(record)))       # a valid seal, but not the one that was logged
        word, reasons = Study(self.book, "QA-1").standing(self.data)
        self.assertEqual(word, "fails")
        self.assertIn("trial log", reasons[0])

    def test_fails_when_the_trial_log_is_edited(self):
        study = self.finished()
        lines = study.trials.path.read_text().splitlines()
        entry = json.loads(lines[2])
        entry["sharpe"] = 9.9
        lines[2] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        study.trials.path.write_text("\n".join(lines) + "\n")
        self.assertEqual(Study(self.book, "QA-1").standing(self.data)[0], "fails")

    def test_stale_when_the_code_that_computed_it_changes(self):
        study = self.finished()
        import qaos_core.study as module

        original = module.code_fingerprint
        module.code_fingerprint = lambda: "0" * 64
        try:
            word, reasons = study.standing(self.data)
            self.assertEqual(word, "stale")
            self.assertIn("changed", reasons[0])
        finally:
            module.code_fingerprint = original
        self.assertEqual(len(code_fingerprint()), 64)

    def test_a_missing_study_is_named(self):
        with self.assertRaises(StudyError):
            Study(self.book, "QA-99")


if __name__ == "__main__":
    unittest.main()
