import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from qaos_core import charts, figures, store, toy_studies
from qaos_core.study import Book, Study, StudyError

from tests.test_study import spec, toy_market

SVG = "{http://www.w3.org/2000/svg}"


class Ticks(unittest.TestCase):
    def test_nice_ticks_are_round_and_inside(self):
        self.assertEqual(charts.nice_ticks(0.0, 6.5), [0.0, 2.0, 4.0, 6.0])
        self.assertEqual(charts.nice_ticks(0.0, 1.0), [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
        ticks = charts.nice_ticks(-0.55, 0.0)
        self.assertTrue(all(-0.55 <= t <= 0.0 for t in ticks) and 0.0 in ticks)
        self.assertEqual(charts.nice_ticks(3.0, 3.0), [3.0])

    def test_log_ticks(self):
        self.assertEqual(charts.log_ticks(1.0, 5000.0), [1.0, 10.0, 100.0, 1000.0])
        self.assertEqual(charts.log_ticks(1.0, 30.0), [1.0, 2.0, 5.0, 10.0, 20.0])


class LineChart(unittest.TestCase):
    def chart(self, n=2, **kwargs):
        x = list(range(20))
        series = [{"name": "series <{0}>".format(i), "x": x, "y": [1.0 + 0.1 * i * v for v in x]} for i in range(n)]
        return charts.line_chart(series, "A & B", "sub", **kwargs)

    def test_it_is_well_formed_and_escaped(self):
        root = ET.fromstring(self.chart(3, x_label="x", y_label="y", h_lines=[(2.0, "bar")], v_lines=[(5.0, "then")]))
        self.assertEqual(root.tag, SVG + "svg")
        self.assertEqual(root.find(SVG + "title").text, "A & B")
        self.assertEqual(len(root.findall(SVG + "path")), 3)
        texts = [t.text for t in root.iter(SVG + "text")]
        self.assertIn("series <0>", texts)

    def test_one_series_has_no_legend_and_many_are_refused(self):
        one = ET.fromstring(self.chart(1))
        two = ET.fromstring(self.chart(2))
        count = lambda root, name: sum(1 for t in root.iter(SVG + "text") if t.text == name)
        self.assertEqual(count(one, "series <0>"), 1, "the end label only")
        self.assertEqual(count(two, "series <0>"), 2, "legend and end label")
        with self.assertRaises(ValueError):
            self.chart(4)
        with self.assertRaises(ValueError):
            charts.line_chart([], "t")

    def test_text_never_wears_the_series_colour_and_both_modes_are_defined(self):
        svg = self.chart(2)
        style = svg.split("<style>")[1].split("</style>")[0]
        self.assertIn("prefers-color-scheme: dark", style)
        for colour in charts.PALETTES["categorical"]["light"][:2] + charts.PALETTES["categorical"]["dark"][:2]:
            self.assertIn(colour, style)
        root = ET.fromstring(svg)
        for text in root.iter(SVG + "text"):
            self.assertIn(text.get("class"), ("t", "st", "tk", "lb", "lb2"))

    def test_log_scale_and_end_labels_that_would_collide(self):
        x = list(range(10))
        series = [{"name": "a", "x": x, "y": [1.0 * (1.5 ** v) for v in x]}, {"name": "b", "x": x, "y": [1.01 * (1.5 ** v) for v in x]}]
        root = ET.fromstring(charts.line_chart(series, "t", log_y=True))
        labels = [t for t in root.iter(SVG + "text") if t.get("class") == "lb"]
        ys = sorted(float(t.get("y")) for t in labels)
        self.assertGreaterEqual(ys[1] - ys[0], 14.9)


class FromTheBook(unittest.TestCase):
    def test_toy_figures_are_drawn_from_records_only(self):
        with tempfile.TemporaryDirectory() as folder:
            book = Book(Path(folder) / "book")
            out = Path(folder) / "figures"
            self.assertEqual(figures.build(book, out, lambda name: None), [])
            store.write_json_atomic(book.toys / "sensitivity.json", toy_studies.sensitivity(quick=True))
            store.write_json_atomic(book.toys / "power.json", toy_studies.power(quick=True))
            written = figures.build(book, out, lambda name: None)
            self.assertEqual(sorted(p.name for p in written), ["toy-power.svg", "toy-sensitivity.svg"])
            for path in written:
                ET.fromstring(path.read_text())

    def test_a_study_figure_does_not_show_the_holdout_before_it_is_opened(self):
        with tempfile.TemporaryDirectory() as folder:
            book = Book(Path(folder) / "book")
            data = toy_market()
            study = Study.register(book, spec(data), data)
            with self.assertRaises(StudyError):
                study.curves(data)
            study.scan(data)
            study.freeze(data, n_shifts=30)
            before = study.curves(data)
            last_dev = np.datetime64(study.prereg["development"]["last"], "D")
            self.assertLessEqual(before["dates"][-1], last_dev)
            self.assertIsNone(before["holdout_start"])
            self.assertFalse(before["unblinded"])
            written = figures.build(book, Path(folder) / "figures", lambda name: data)
            self.assertEqual(sorted(p.name for p in written), ["qa-1-drawdown.svg", "qa-1-growth.svg"])
            self.assertIn("development window only", written[0].read_text() + written[1].read_text())
            study.unblind(data, by="t", n_boot=200, n_shifts=30)
            after = study.curves(data)
            self.assertEqual(after["dates"][-1], data.dates[-1])
            self.assertTrue(after["unblinded"])
            self.assertLessEqual(float(after["strategy_drawdown"].min()), 0.0)
            np.testing.assert_allclose(after["strategy"][:before["strategy"].shape[0]], before["strategy"], rtol=1e-12)


if __name__ == "__main__":
    unittest.main()
