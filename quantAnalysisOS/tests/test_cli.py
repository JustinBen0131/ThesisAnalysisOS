import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from qaos_core import cli, demo, toys
from qaos_core.data import Dataset


def toy_dataset(name="toy", seed=15, r2=0.04, years=12):
    periods = years * 252
    raw = toys.latent_drift(1, periods, mu_ann=0.0, vol_ann=0.16, r2=r2, rng=toys.generator(seed))
    prices = toys.as_market(raw)[1][0]
    dates = np.busday_offset(np.datetime64("2008-01-01"), np.arange(periods + 1), roll="forward")
    return Dataset(name, dates, ["TOY"], prices, 252.0, np.full(periods + 1, 0.00005))


class Cli(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.saved = {key: os.environ.get(key) for key in ("QAOS_BOOK", "QAOS_DATA")}
        os.environ["QAOS_BOOK"] = str(self.root / "book")
        os.environ["QAOS_DATA"] = str(self.root / "data")

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.folder.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_an_empty_book(self):
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("none registered", out)
        self.assertIn("none open", out)
        code, out, _ = self.run_cli("data", "list")
        self.assertIn("no datasets recorded", out)
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)

    def test_need(self):
        code, out, _ = self.run_cli("need", "--sharpe", "0.5")
        self.assertEqual(code, 0)
        self.assertIn("3 sigma takes 36.0 years", out)

    def test_gates(self):
        code, out, _ = self.run_cli("gate", "causality", "--strategy", "tsmom")
        self.assertEqual(code, 0)
        self.assertIn("holds", out)
        code, out, _ = self.run_cli("gate", "causality", "--strategy", "pairs_zscore")
        self.assertEqual(code, 0)

    def test_refusals_exit_2_and_say_why(self):
        code, _, err = self.run_cli("study", "show", "QA-9")
        self.assertEqual(code, 2)
        self.assertIn("refused", err)
        code, _, err = self.run_cli("data", "qa", "nothing")
        self.assertEqual(code, 2)
        self.assertIn("not on this machine", err)
        code, _, err = self.run_cli("toys", "astrology", "--quick")
        self.assertEqual(code, 2)
        code, _, err = self.run_cli("toys", "sensitivity", "--quick", "--write")
        self.assertEqual(code, 2)
        self.assertIn("not for the record", err)
        code, _, err = self.run_cli("paper", "step", "ghost")
        self.assertEqual(code, 2)

    def test_a_study_from_registration_to_verdict_then_paper(self):
        toy_dataset().to_csv(self.root / "data" / "toy.csv")
        spec = {"id": "QA-1", "title": "Trend on a toy", "hypothesis": "Trend earns a positive Sharpe.",
                "dataset": "toy", "holdout_start": "2014-01-01", "strategy": "trend_sma",
                "grid": [{"window": w} for w in (50, 100, 200)], "decision": {"test": "sharpe", "z_min": 2.0},
                "prior_exposure": "none: a toy"}
        path = self.root / "spec.json"
        path.write_text(json.dumps(spec))

        code, out, _ = self.run_cli("data", "qa", "toy")
        self.assertEqual(code, 0)
        self.assertIn("toy: holds", out)
        code, out, _ = self.run_cli("study", "register", str(path))
        self.assertEqual(code, 0, out)
        self.assertIn("registered QA-1", out)
        code, _, err = self.run_cli("study", "unblind", "QA-1", "--by", "me")
        self.assertEqual(code, 2)
        self.assertIn("not frozen", err)
        code, out, _ = self.run_cli("study", "scan", "QA-1")
        self.assertIn("The holdout was not read", out)
        code, out, _ = self.run_cli("study", "freeze", "QA-1")
        self.assertEqual(code, 0)
        self.assertIn("mixed-event", out)
        code, _, err = self.run_cli("study", "unblind", "QA-1")
        self.assertEqual(code, 2)
        self.assertIn("signed", err)
        code, out, _ = self.run_cli("study", "unblind", "QA-1", "--by", "me")
        self.assertEqual(code, 0)
        self.assertIn("verdict", out)
        code, _, err = self.run_cli("study", "unblind", "QA-1", "--by", "me")
        self.assertEqual(code, 2)
        self.assertIn("opens once", err)
        code, out, _ = self.run_cli("study", "systematics", "QA-1", "--window", "holdout")
        self.assertEqual(code, 0)
        code, out, _ = self.run_cli("study", "show", "QA-1")
        for word in ("hypothesis", "known before", "development trials", "frozen", "unblinded", "systematics"):
            self.assertIn(word, out)
        code, out, _ = self.run_cli("study", "why", "QA-1", "--check")
        self.assertEqual(code, 0)
        self.assertIn("holds", out)
        code, out, _ = self.run_cli("study", "list")
        self.assertIn("unblinded", out)

        code, out, _ = self.run_cli("paper", "open", "main", "--cash", "10000")
        self.assertEqual(code, 0)
        self.assertIn("fake money", out)
        code, _, err = self.run_cli("paper", "step", "main")
        self.assertEqual(code, 2)
        self.assertIn("mandate", err)
        code, out, _ = self.run_cli("paper", "mandate", "main", "--data", "toy", "--strategy", "trend_sma",
                                    "--params", '{"window": 100}', "--rebalance", "month_start", "--stage", "promoted", "--study", "QA-1")
        self.assertEqual(code, 0, out)
        self.assertIn("causality holds", out)
        code, out, _ = self.run_cli("paper", "step", "main")
        self.assertEqual(code, 0)
        self.assertIn("1 step(s)", out)
        code, out, _ = self.run_cli("paper", "step", "main")
        self.assertIn("nothing new", out)
        code, out, _ = self.run_cli("status")
        self.assertIn("QA-1", out)
        self.assertIn("[paper money]", out)
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing fails", out)

        # now the vendor revises one number
        revised = toy_dataset()
        revised.prices[400, 0] *= 1.0005
        revised.to_csv(self.root / "data" / "toy.csv")
        code, out, _ = self.run_cli("study", "why", "QA-1", "--check")
        self.assertEqual(code, 1)
        self.assertIn("stale", out)

    def test_doctor_fails_on_an_edited_ledger(self):
        self.run_cli("paper", "open", "main")
        ledger = self.root / "book" / "paper" / "main" / "ledger.jsonl"
        entry = json.loads(ledger.read_text())
        entry["cash"] = 1e9
        ledger.write_text(json.dumps(entry) + "\n")
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("fails", out)

    def test_toys_quick_renders_and_full_run_is_recorded(self):
        code, out, _ = self.run_cli("toys", "power", "--quick")
        self.assertEqual(code, 0)
        self.assertIn("timing test", out)
        code, out, _ = self.run_cli("toys", "look_elsewhere", "--quick")
        self.assertIn("mixed-event", out)
        code, out, _ = self.run_cli("toys", "pulls", "--quick")
        self.assertIn("pull width", out)

    def test_demo_tells_the_whole_story(self):
        out = io.StringIO()
        self.assertEqual(demo.run(out), 0)
        text = out.getvalue()
        for phrase in ("A search always finds something", "Count the search", "Open the box once", "not confirmed",
                       "confirmed at", "The box opens once", "stale", "Fake money first", "content does not match its hash"):
            self.assertIn(phrase, text)
        lines = text.splitlines()
        nav = [line for line in lines if line.strip().startswith("NAV")][0].split("$")[1].split()[0]
        engine_says = [line for line in lines if "says $" in line][0].split("$")[1].rstrip(".")
        self.assertEqual(nav, engine_says, "the broker and the engine agree to the cent")


if __name__ == "__main__":
    unittest.main()
