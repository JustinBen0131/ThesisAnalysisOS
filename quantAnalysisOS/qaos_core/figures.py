"""Figures for the research notes, drawn from the book and nothing else.

A figure shows a recorded result. If the record is not there, the figure is
not drawn; nothing here computes a new number about a market.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from . import charts, store
from .data import Dataset
from .study import Book, Study, StudyError


def _years(dates: np.ndarray) -> np.ndarray:
    dates = np.asarray(dates, dtype="datetime64[D]")
    year = dates.astype("datetime64[Y]")
    start = year.astype("datetime64[D]")
    length = (year + np.timedelta64(1, "Y")).astype("datetime64[D]") - start
    return year.astype(int) + 1970 + (dates - start).astype(float) / length.astype(float)


def _percent(value: float) -> str:
    return "{0:g}%".format(round(100.0 * value, 1))


def sensitivity(record: Dict[str, Any]) -> str:
    wanted = [s for s in (0.25, 0.5, 1.0) if any(row["true_sharpe"] == s for row in record["rows"])]
    series = []
    for sharpe in wanted:
        rows = sorted((row for row in record["rows"] if row["true_sharpe"] == sharpe), key=lambda row: row["years"])
        series.append({"name": "Sharpe {0:g}".format(sharpe), "x": [0.0] + [row["years"] for row in rows],
                       "y": [0.0] + [row["median_z"] for row in rows]})
    return charts.line_chart(
        series, "How long a true edge takes to show",
        "Median significance reached in {0:,} toy markets per point, by years of data".format(record["settings"]["toys"]),
        x_label="years of data", y_label="Z, in sigma", palette="ordinal", markers=True,
        h_lines=[(2.0, "2σ"), (3.0, "3σ")], y_range=(0.0, 7.0),
        description="Median significance of a true Sharpe ratio of 0.25, 0.5 and 1.0 after 1 to 40 years of toy data.")


def look_elsewhere(record: Dict[str, Any]) -> str:
    rows = [row for row in record["rows"] if row.get("family", "unrelated rules") == "unrelated rules"]
    positions = list(range(len(rows)))
    labels = {i: str(row["grid"]) for i, row in enumerate(rows)}
    names = (("naive", "judged alone"), ("deflated", "deflated Sharpe"), ("mixed_event", "mixed-event"))
    series = [{"name": label, "x": positions, "y": [row["false_positive"][key]["rate"] for row in rows]} for key, label in names]
    return charts.line_chart(
        series, "What a search finds in pure noise",
        "Share of {0:,} empty toy markets where the best of N unrelated rules passed as significant".format(record["settings"]["toys"]),
        x_label="unrelated rules tried", y_label="false alarms", markers=True, x_ticks=positions,
        x_format=lambda v: labels.get(int(round(v)), ""), y_format=_percent,
        h_lines=[(record["settings"]["nominal_alpha"], "nominal {0:.0%}".format(record["settings"]["nominal_alpha"]))],
        y_range=(0.0, 1.0),
        description="False alarm rate against number of rules tried, for three ways of judging the best rule.")


def power(record: Dict[str, Any]) -> str:
    rows = record["rows"]
    positions = list(range(len(rows)))
    labels = {i: "{0:g}".format(row["r2"]) for i, row in enumerate(rows)}
    names = (("sharpe", "sharpe test"), ("alpha", "alpha test"), ("timing", "timing test"))
    series = [{"name": label, "x": positions, "y": [row["confirmed"][key]["rate"] for row in rows]} for key, label in names]
    return charts.line_chart(
        series, "How often the procedure confirms a signal of known size",
        "Scan, freeze, unblind on {0:,} toy markets per point; the first point has no signal in it".format(record["settings"]["toys"]),
        x_label="injected signal: share of daily variance that is predictable (r2)", y_label="confirmed", markers=True,
        x_ticks=positions, x_format=lambda v: labels.get(int(round(v)), ""), y_format=_percent, y_range=(0.0, 1.0),
        description="Confirmation rate of three registered tests against injected signal strength.")


def study_growth(study: Study, curves: Dict[str, Any]) -> str:
    x = _years(curves["dates"])
    chosen = study.frozen["chosen"]
    lines = [(float(_years(np.asarray([curves["holdout_start"]]))[0]), "holdout opens")] if curves["holdout_start"] is not None else []
    series = [{"name": "the frozen rule", "x": x, "y": curves["strategy"]},
              {"name": "buy and hold", "x": x, "y": curves["benchmark"]},
              {"name": "Treasury bills", "x": x, "y": curves["cash"]}]
    return charts.line_chart(
        series, "{0}: growth of $1".format(study.id),
        "{0}, after costs, log scale{1}".format(chosen["strategy"], "" if curves["unblinded"] else "; development window only"),
        y_label="value of $1", log_y=True, v_lines=lines, x_format=lambda v: "{0:.0f}".format(v),
        y_format=lambda v: "${0:,.0f}".format(v) if v >= 1 else "${0:g}".format(v),
        description="Growth of one dollar in the frozen rule, in buy-and-hold and in Treasury bills.")


def study_drawdown(study: Study, curves: Dict[str, Any]) -> str:
    x = _years(curves["dates"])
    lines = [(float(_years(np.asarray([curves["holdout_start"]]))[0]), "holdout opens")] if curves["holdout_start"] is not None else []
    series = [{"name": "the frozen rule", "x": x, "y": curves["strategy_drawdown"]},
              {"name": "buy and hold", "x": x, "y": curves["benchmark_drawdown"]}]
    low = float(min(curves["strategy_drawdown"].min(), curves["benchmark_drawdown"].min()))
    return charts.line_chart(
        series, "{0}: loss from the previous high".format(study.id),
        "Drawdown after costs{0}".format("" if curves["unblinded"] else "; development window only"),
        y_label="drawdown", v_lines=lines, x_format=lambda v: "{0:.0f}".format(v), y_format=_percent,
        y_range=(np.floor(low * 10.0) / 10.0, 0.0), height=320,
        description="Drawdown of the frozen rule and of buy-and-hold.")


def build(book: Book, out_dir: Path, loader: Callable[[str], Optional[Dataset]]) -> List[Path]:
    """Draw every figure the book can support. Returns the files written."""
    out_dir = Path(out_dir)
    written: List[Path] = []

    def write(name: str, svg: str) -> None:
        store.write_text_atomic(out_dir / name, svg)
        written.append(out_dir / name)

    makers = {"sensitivity": sensitivity, "look_elsewhere": look_elsewhere, "power": power}
    for name, maker in makers.items():
        record = store.read_json(book.toys / (name + ".json"))
        if record is not None:
            write("toy-{0}.svg".format(name.replace("_", "-")), maker(record))
    for study_id in book.study_ids():
        study = Study(book, study_id)
        if study.frozen is None:
            continue
        dataset = loader(study.prereg["dataset"]["name"])
        if dataset is None:
            continue
        try:
            curves = study.curves(dataset)
        except StudyError:
            continue
        write("{0}-growth.svg".format(study_id.lower()), study_growth(study, curves))
        write("{0}-drawdown.svg".format(study_id.lower()), study_drawdown(study, curves))
    return written
