import gzip
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

from qaos_core import sources
from qaos_core.data import Dataset, align, carry_forward, quality, rf_from_yield, to_dates


def small(periods=40, assets=2, seed=0):
    rng = np.random.default_rng(seed)
    dates = np.busday_offset(np.datetime64("2020-01-01"), np.arange(periods), roll="forward")
    prices = 100.0 * np.cumprod(1.0 + rng.standard_normal((periods, assets)) * 0.01, axis=0)
    return Dataset("small", dates, ["AAA", "BBB"][:assets], prices, 252.0, np.full(periods, 0.0001))


class DatasetIdentity(unittest.TestCase):
    def test_fingerprint_moves_with_any_number_it_reads(self):
        base = small()
        self.assertEqual(base.fingerprint(), small().fingerprint())
        for change in ("price", "rf", "date", "symbol", "frequency"):
            other = small()
            if change == "price":
                other.prices[17, 1] *= 1.0000001
            elif change == "rf":
                other.rf[3] = 0.0002
            elif change == "date":
                other.dates[-1] = other.dates[-1] + np.timedelta64(1, "D")
            elif change == "symbol":
                other.symbols[0] = "AAB"
            else:
                other.periods_per_year = 12.0
            self.assertNotEqual(base.fingerprint(), other.fingerprint(), change)

    def test_nan_before_listing_is_part_of_the_identity_but_stable(self):
        a, b = small(), small()
        a.prices[:5, 1] = np.nan
        b.prices[:5, 1] = float("nan")
        self.assertEqual(a.fingerprint(), b.fingerprint())

    def test_csv_round_trip_is_exact(self):
        ds = small()
        ds.prices[:3, 1] = np.nan
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "small.csv"
            ds.to_csv(path)
            back = Dataset.from_csv(path)
            self.assertEqual(back.fingerprint(), ds.fingerprint())
            self.assertEqual(back.symbols, ds.symbols)
            self.assertEqual(json.loads(path.with_suffix(".json").read_text())["fingerprint"], ds.fingerprint())

    def test_window_head_select(self):
        ds = small()
        cut = ds.window(str(ds.dates[10]), str(ds.dates[19]))
        self.assertEqual(cut.dates.shape[0], 10)
        self.assertEqual(ds.head(7).prices.shape, (7, 2))
        self.assertEqual(ds.select(["BBB"]).symbols, ["BBB"])
        np.testing.assert_array_equal(ds.select(["BBB"]).prices[:, 0], ds.prices[:, 1])
        self.assertEqual(ds.window(end=str(ds.dates[-1])).fingerprint(), ds.fingerprint())
        longer = small(60)
        self.assertEqual(longer.head(40).fingerprint(), ds.fingerprint(), "a longer history with the same past is the same past")

    def test_returns_convention(self):
        ds = small()
        r = ds.returns
        np.testing.assert_array_equal(r[0], 0.0)
        np.testing.assert_allclose(r[5], ds.prices[5] / ds.prices[4] - 1.0)

    def test_shape_mismatch_is_refused(self):
        with self.assertRaises(ValueError):
            Dataset("x", to_dates(["2020-01-01"]), ["A", "B"], np.ones((1, 1)))


class Assembly(unittest.TestCase):
    def test_align_inner_and_union(self):
        d1 = to_dates(["2020-01-01", "2020-01-02", "2020-01-03"])
        d2 = to_dates(["2020-01-02", "2020-01-03", "2020-01-06"])
        dates, names, table = align({"A": (d1, np.array([1.0, 2.0, 3.0])), "B": (d2, np.array([20.0, 30.0, 60.0]))})
        self.assertEqual([str(d) for d in dates], ["2020-01-02", "2020-01-03"])
        np.testing.assert_array_equal(table, [[2.0, 20.0], [3.0, 30.0]])
        dates, names, table = align({"A": (d1, np.array([1.0, 2.0, 3.0])), "B": (d2, np.array([20.0, 30.0, 60.0]))}, how="union")
        self.assertEqual(dates.shape[0], 4)
        self.assertTrue(np.isnan(table[0, 1]) and np.isnan(table[3, 0]))
        _, _, filled = align({"A": (d1, np.array([1.0, 2.0, 3.0])), "B": (d2, np.array([20.0, 30.0, 60.0]))}, how="union", fill_limit=1)
        self.assertEqual(filled[3, 0], 3.0)

    def test_rf_uses_the_rate_known_at_the_start_of_the_period(self):
        dates = to_dates(["2020-01-02", "2020-01-03", "2020-01-06"])
        rf = rf_from_yield(dates, np.array([3.65, 7.30, 99.0]))
        self.assertEqual(rf[0], 0.0)
        self.assertAlmostEqual(rf[1], 1.0365 ** (1 / 365) - 1, places=12)
        self.assertAlmostEqual(rf[2], 1.0730 ** (3 / 365) - 1, places=12)   # a weekend is three days of interest

    def test_carry_forward_never_reads_the_future(self):
        out = carry_forward(to_dates(["2020-01-01", "2020-01-05", "2020-01-10"]),
                            to_dates(["2020-01-03", "2020-01-08"]), np.array([1.0, 2.0]))
        self.assertTrue(np.isnan(out[0]))
        np.testing.assert_array_equal(out[1:], [1.0, 2.0])


class Quality(unittest.TestCase):
    def test_clean_data_holds(self):
        out = quality(small(300))
        self.assertEqual(out["verdict"], "holds")
        self.assertEqual(out["golden_periods"], 300)

    def test_structural_problems_fail(self):
        ds = small(100)
        ds.prices[50, 0] = np.nan
        self.assertEqual(quality(ds)["verdict"], "fails")
        ds = small(100)
        ds.prices[50, 0] = -1.0
        self.assertEqual(quality(ds)["verdict"], "fails")
        ds = small(100)
        ds.dates[40] = ds.dates[39]
        self.assertEqual(quality(ds)["verdict"], "fails")

    def test_a_jump_is_flagged_not_removed(self):
        ds = small(400)
        ds.prices[200:, 0] *= 1.6
        out = quality(ds)
        self.assertEqual(out["verdict"], "holds")
        self.assertEqual(out["per_symbol"]["AAA"]["jumps"], 1)
        self.assertFalse(out["golden"][200])
        self.assertEqual(out["golden_periods"], 399)

    def test_stale_prices_are_counted(self):
        ds = small(100)
        ds.prices[30:40, 1] = ds.prices[29, 1]
        self.assertGreaterEqual(quality(ds)["per_symbol"]["BBB"]["stale_periods"], 10)

    def test_a_late_start_is_not_a_gap(self):
        ds = small(100)
        ds.prices[:20, 1] = np.nan
        out = quality(ds)
        self.assertEqual(out["verdict"], "holds")
        self.assertEqual(out["golden_periods"], 80)


class Parsing(unittest.TestCase):
    def test_date_formats(self):
        dates, names, values = sources.read_table("Date,A\n1/4/1999,1.5\n192607,2.5\n2001-02-03,3.5\n")
        self.assertEqual(sorted(str(d) for d in dates), ["1926-07-31", "1999-01-04", "2001-02-03"])
        self.assertEqual(names, ["A"])

    def test_blank_cells_are_nan_and_rows_are_sorted(self):
        dates, _, values = sources.read_table("Date,A,B\n2020-01-03,3,\n2020-01-02,2,x\n")
        self.assertEqual(str(dates[0]), "2020-01-02")
        self.assertTrue(np.isnan(values[0, 1]) and np.isnan(values[1, 1]))

    def test_stooq_fred_yahoo(self):
        dates, close = sources.parse_stooq(b"Date,Open,High,Low,Close,Volume\n2024-01-02,1,2,0.5,1.5,100\n2024-01-03,1,2,0.5,1.6,100\n")
        np.testing.assert_array_equal(close, [1.5, 1.6])
        with self.assertRaises(sources.SourceError):
            sources.parse_stooq(b"No data")
        dates, values = sources.parse_fred(b"observation_date,DTB3\n2024-01-02,5.22\n2024-01-03,.\n")
        self.assertEqual(values[0], 5.22)
        self.assertTrue(np.isnan(values[1]))
        payload = {"chart": {"result": [{"meta": {"gmtoffset": -18000}, "timestamp": [1704205800, 1704292200, 1704300000],
                                         "indicators": {"adjclose": [{"adjclose": [100.0, None, 101.5]}]}}]}}
        dates, values = sources.parse_yahoo(json.dumps(payload).encode())
        self.assertEqual([str(d) for d in dates], ["2024-01-02", "2024-01-03"])
        self.assertEqual(values[-1], 101.5)
        with self.assertRaises(sources.SourceError):
            sources.parse_yahoo(b'{"chart": {"result": null}}')

    def test_french_index_is_the_product_of_the_returns(self):
        text = "Date,Mkt-RF,SMB,HML,RF\n192607,2.96,-2.30,-2.87,0.22\n192608,2.64,-1.40,4.19,0.25\n"
        ds = sources.french_dataset(text)
        self.assertEqual(ds.symbols, ["MKT", "SMB", "HML"])
        self.assertEqual([str(d) for d in ds.dates], ["1926-06-30", "1926-07-31", "1926-08-31"])
        self.assertEqual(ds.periods_per_year, 12.0)
        np.testing.assert_allclose(ds.returns[1:, 0], [0.0296 + 0.0022, 0.0264 + 0.0025], atol=1e-14)
        np.testing.assert_allclose(ds.rf, [0.0, 0.0022, 0.0025], atol=1e-15)
        np.testing.assert_allclose(ds.returns[1:, 1] - ds.rf[1:], [-0.0230, -0.0140], atol=1e-14)

    def test_a_pinned_wheel_member_is_read_without_the_network(self):
        with tempfile.TemporaryDirectory() as folder:
            body = gzip.compress(b"Date,Mkt-RF,SMB,HML,RF\n192607,1,1,1,0.1\n192608,1,1,1,0.1\n192609,1,1,1,0.1\n")
            wheel = Path(folder) / "arch-9.0.0-cp313-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("arch/data/frenchdata/frenchdata.csv.gz", body)
            raw, record = sources.pypi_member("arch", "9.0.0", "arch/data/frenchdata/frenchdata.csv.gz", Path(folder))
            self.assertEqual(raw, body)
            self.assertEqual(record["version"], "9.0.0")
            self.assertEqual(len(record["sha256"]), 64)
            with self.assertRaises(sources.SourceError, msg="not the file the dataset was defined on"):
                sources.pull("french", wheel_dir=Path(folder))
            with self.assertRaises(sources.SourceError):
                sources.pypi_member("arch", "9.0.0", "arch/data/nothing.csv", Path(folder))
        with self.assertRaises(sources.SourceError):
            sources.pull("not-a-dataset")
        with self.assertRaises(sources.SourceError):
            sources.vendor_series("bloomberg", "SPY")

    def test_every_pinned_dataset_names_its_hash(self):
        for name, (package, version, member, digest, description) in sources.PYPI_MEMBERS.items():
            self.assertEqual(len(digest), 64, name)
            self.assertTrue(version and member and description, name)


if __name__ == "__main__":
    unittest.main()
