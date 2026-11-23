"""Controlled observations for the timing design. No benchmark is run in CI."""

import copy
import io
import json
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claims
import reuse_frontier as reuse


def observations(scale=1):
    samples = []
    for row in reuse.timing_schedule(7):
        # Different baseline speeds in the same run make the pairing observable.
        ref = (1 + row["block"] % 3) * scale
        if row["study"] == "upkeep":
            seconds = {"reference": ref, "ask": ref * row["files"] / 48}
        else:
            seconds = {"reference": ref, "open": 4 * ref, "isolated": 3 * ref}
        samples.append(dict(row, seconds=seconds))
    return samples


def fixture(scale=1):
    run = {"seed": 7, "edits": 60, "checks": 6, "folders": 12, "relied_on": 360, "rows": [
        {"policy": "TAOS, 12 domain(s) declared", "executions": 60, "wrong": 0},
        {"policy": "rerun when older than 2 consultations", "executions": 180, "wrong": 30},
        {"policy": "TAOS, each check hides one folder it reads", "executions": 29, "wrong": 150},
        {"policy": "TAOS, checks isolated, declared correctly", "executions": 60, "wrong": 0},
        {"policy": "TAOS, checks isolated, each hides one folder", "executions": 366, "wrong": 0, "passed": 0}]}
    with mock.patch.object(reuse, "observe_timing", return_value=observations(scale)), mock.patch.object(reuse.gates, "closes", return_value=False):
        run["timing"] = reuse.timing_record(run)
    return run


class TestPairedTiming(unittest.TestCase):
    def test_finite_sample_sign_interval(self):
        interval = reuse.median_interval(range(12))
        self.assertEqual((interval["rank"], interval["low"], interval["high"], interval["median"]), (3, 2, 9, 5.5))
        self.assertEqual(interval["coverage"], 1 - 2 * (1 + 12 + 66) / 4096)
        self.assertEqual(reuse.median_interval([7] * 6)["coverage"], 31 / 32)
        with self.assertRaisesRegex(ValueError, "at least six"):
            reuse.median_interval(range(5))

    def test_order_balances_each_size_and_isolation_arm(self):
        plan = list(reuse.timing_schedule(7))
        self.assertEqual(plan, list(reuse.timing_schedule(7)))
        self.assertNotEqual(plan, list(reuse.timing_schedule(8)))
        trees = [p for p in plan if p["study"] == "upkeep"]
        for files in (48, 480, 4800):
            rows = [p for p in trees if p["files"] == files]
            self.assertEqual(Counter(p["order"][0] for p in rows), {"ask": 6, "reference": 6})
            self.assertEqual(sorted(p["block"] for p in rows), list(range(12)))
            self.assertEqual(Counter(i % 3 for i, p in enumerate(trees) if p["files"] == files), {0: 4, 1: 4, 2: 4})
        isolated = [p for p in plan if p["study"] == "isolation"]
        self.assertEqual(len(Counter(tuple(p["order"]) for p in isolated)), 6)
        self.assertEqual(set(Counter(tuple(p["order"]) for p in isolated).values()), {6})
        self.assertEqual([tuple(p["edit"]) for p in isolated], reuse.trace(36, 7))

    def test_observer_executes_arms_in_saved_order(self):
        events = []

        class FixtureWorld:
            def __init__(self, home, domains, **kwargs):
                self.name = home.name

            def consult(self, step):
                if step >= 0:
                    events.append((self.name, step))
                return (int(self.name in ("open", "isolated")), 0.125)

            def edit(self, step, folder, index):
                events.append(("edit " + self.name, step, folder, index))

        def reference(world):
            events.append((world.name,))
            return 0.25

        with mock.patch.object(reuse, "World", FixtureWorld), mock.patch.object(reuse, "uncached_reference", reference):
            samples = reuse.observe_timing(7)
        expected = [("control",)]  # warmup
        for row in reuse.timing_schedule(7):
            if row["study"] == "isolation":
                expected.extend([("edit " + arm, row["block"], *row["edit"]) for arm in ("open", "isolated")])
            for arm in row["order"]:
                if arm == "reference":
                    expected.append(("control",))
                else:
                    name = "tree-" + str(row["files"] // 12) if arm == "ask" else arm
                    expected.append((name, row["block"]))
        self.assertEqual(events, expected)
        self.assertEqual([s["order"] for s in samples], [s["order"] for s in reuse.timing_schedule(7)])

    def test_uncached_reference_really_runs_its_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = object.__new__(reuse.World)
            world.work, world.logs = Path(tmp) / "work", Path(tmp) / "logs"
            world.logs.mkdir()
            for dirname in ("d00", "d01"):
                folder = world.work / dirname
                folder.mkdir(parents=True)
                for index in range(4):
                    (folder / f"f{index}.txt").write_text("start\n")
            with mock.patch.object(reuse.time, "perf_counter", side_effect=[100, 100.25, 101, 101.125]):
                self.assertEqual(reuse.uncached_reference(world), 0.25)
                self.assertEqual(reuse.uncached_reference(world), 0.125)
            self.assertEqual(world.executions(0), 2)
            self.assertTrue(all(line.endswith(" 48") for line in (world.logs / "c0.log").read_text().splitlines()))
            with mock.patch.object(reuse.gates, "_execute", return_value=(0, "")):
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    reuse.uncached_reference(world)

    def test_ratios_use_within_observation_arithmetic(self):
        run = fixture()
        timing = run["timing"]
        self.assertEqual([s["reference_ratio"]["median"] for s in timing["upkeep"]], [1, 10, 100])
        self.assertEqual(timing["large_to_small_time_ratio"]["median"], 100)
        self.assertEqual(timing["isolating_one_execution"]["added_reference_ratio"]["median"], -1)
        self.assertEqual(timing["checks_spared_per_consultation"], 5)
        self.assertEqual(timing["upkeep"][0]["break_even_check_seconds"], 2 / 5)
        self.assertEqual(timing["upkeep"][0]["input_bytes"], 288)
        # Median of individual ratios differs from the ratio of medians.
        data = observations()
        i = 0
        for row in data:
            if row.get("files") == 48:
                row["seconds"] = {"ask": (1, 10, 10)[i % 3], "reference": (1, 1, 10)[i % 3]}
                i += 1
        summary = reuse.summarize_timing(run, data, timing["conditions"])
        self.assertEqual(summary["upkeep"][0]["reference_ratio"]["median"], 1)
        self.assertEqual(summary["upkeep"][0]["seconds"], 10)

    def test_speed_is_descriptive_and_saved_identity_is_verified(self):
        # Use a second synthetic run on a machine ten times slower.
        first, second = fixture(), fixture(10)
        for run in (first, second):
            reuse.verify_timing(run)
        self.assertEqual(claims.timing_claims(first), claims.timing_claims(second))
        self.assertNotEqual(first["timing"]["dataset_sha256"], second["timing"]["dataset_sha256"])
        for key, mutation, reason in [
                ("summary", lambda t: t["upkeep"][0].update(seconds=19), "summary"),
                ("raw", lambda t: t["observations"][0]["seconds"].update(reference=22), "fingerprint"),
                ("workload", lambda t: t["workload"].update(seed=9), "workload"),
                ("conditions", lambda t: t["conditions"].update(system="changed"), "fingerprint")]:
            with self.subTest(key):
                run = copy.deepcopy(first)
                mutation(run["timing"])
                with self.assertRaisesRegex(ValueError, reason):
                    reuse.verify_timing(run)
        run = copy.deepcopy(first)
        run["seed"] += 1
        with self.assertRaisesRegex(ValueError, "workload"):
            reuse.verify_timing(run)

    def test_missing_reordered_and_invalid_samples_fail(self):
        run = fixture()
        for change in ("dropped", "reordered", "zero", "nan", "missing arm"):
            with self.subTest(change):
                data = observations()
                if change == "dropped":
                    data.pop()
                elif change == "reordered":
                    data.reverse()
                elif change == "missing arm":
                    del data[0]["seconds"]["reference"]
                else:
                    data[0]["seconds"]["reference"] = 0 if change == "zero" else float("nan")
                with self.assertRaises(ValueError):
                    reuse.summarize_timing(run, data, run["timing"]["conditions"])

    def test_claims_use_saved_rows_and_historical_units(self):
        old = fixture()
        old["timing"] = {"upkeep": [{"files": 48, "seconds": .02}],
                         "isolating_one_execution": {"median_seconds": .1, "pairs": 40, "low_seconds": .08, "high_seconds": .11}}
        legacy = claims.timing_claims(old)
        self.assertIn("historical", legacy[claims.UPKEEP_LABEL])
        self.assertIn("20.0 ms", legacy[claims.UPKEEP_LABEL])
        self.assertNotIn("×", legacy[claims.ISOLATION_LABEL])
        run = fixture()
        rows = claims.timing_claims(run)
        self.assertEqual(list(rows), [claims.UPKEEP_LABEL, claims.ISOLATION_LABEL])
        self.assertEqual(claims.quoted("reuse_frontier", run)[-2:], list(rows.values()))
        self.assertTrue(all("|" not in text for text in rows.values()))
        self.assertNotIn("ms", " ".join(claims.front_page({"reuse_frontier": old}, 0)))
        run["timing"]["observations"].clear()
        self.assertEqual(claims.front_page({"reuse_frontier": run}, 0), claims.front_page({"reuse_frontier": old}, 0))

    def test_verify_cli_reads_source_and_dataset_without_running_experiment(self):
        run = fixture()
        run["measured_on"] = reuse.measured.stamp(reuse.STANDS_ON)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(reuse, "experiment", side_effect=AssertionError), \
                mock.patch.object(reuse, "RECORD", Path(tmp) / "record.json"), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            reuse.RECORD.write_text(json.dumps(run))
            self.assertEqual(reuse.main(["--verify"]), 0)
            run["measured_on"]["files"]["sha256"] = "0" * 64
            reuse.RECORD.write_text(json.dumps(run))
            self.assertEqual(reuse.main(["--verify"]), 1)
            run["timing"]["upkeep"][1]["seconds"] = 99
            reuse.RECORD.write_text(json.dumps(run))
            self.assertEqual(reuse.main(["--verify"]), 1)
            del run["timing"]["schema"]
            reuse.RECORD.write_text(json.dumps(run))
            self.assertEqual(reuse.main(["--verify"]), 1)


if __name__ == "__main__":
    unittest.main()
