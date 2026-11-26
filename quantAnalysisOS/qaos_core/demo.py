"""`qaos demo`: the idea, working, in a throwaway folder.

Two toy markets through the real machinery: register, scan, freeze, unblind,
then a paper account stepped through one of them. Seeds are fixed so the run
is the same every time. It illustrates; `qaos toys` measures.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

from . import __version__, engine, paper, report, strategies, toys
from .data import Dataset
from .study import Book, Study, StudyError

YEARS = 20
GRID = [{"window": int(w)} for w in np.unique(np.linspace(10, 400, 40).round())]
MARKETS = {"A": {"seed": 13, "r2": 0.0}, "B": {"seed": 14, "r2": 0.04}}


def market(seed: int, r2: float) -> Dataset:
    periods = int(YEARS * 252)
    raw = toys.latent_drift(1, periods, mu_ann=0.0, vol_ann=0.16, r2=r2, rng=toys.generator(seed))
    prices = toys.as_market(raw)[1][0]
    dates = np.busday_offset(np.datetime64("2001-01-01"), np.arange(periods + 1), roll="forward")
    return Dataset("toy", dates, ["TOY"], prices, 252.0)


def _study(book: Book, study_id: str, dataset: Dataset) -> Tuple[Study, Dict[str, Any]]:
    spec = {
        "id": study_id,
        "title": "Trend rule on a toy market",
        "hypothesis": "Holding the asset only while it is above its moving average earns a positive Sharpe ratio.",
        "holdout_start": str(dataset.dates[dataset.dates.shape[0] // 2]),
        "strategy": "trend_sma", "grid": GRID,
        "decision": {"test": "sharpe", "z_min": 2.0},
    }
    study = Study.register(book, spec, dataset)
    study.scan(dataset)
    return study, study.freeze(dataset, n_shifts=200)


def run(out=None) -> int:
    write = (out or sys.stdout).write

    def say(text: str = "") -> None:
        write(text + "\n")

    say(report.box("QAOS  quantAnalysisOS {0}".format(__version__), [
        "An edge is a claim. It is kept with what it stood on, and tested once.",
        "Ask it later: holds, stale, fails or unknown, and why."]))
    say("Here: two toy markets, twenty years each. One is pure noise. One has a slow")
    say("drift hidden in it. Forty trend rules are tried on the first decade of each.")
    say()
    with tempfile.TemporaryDirectory(prefix="qaos-demo-") as folder:
        book = Book(Path(folder) / "book")
        data = {name: market(**settings) for name, settings in MARKETS.items()}
        studies: Dict[str, Study] = {}
        frozen: Dict[str, Dict[str, Any]] = {}
        for index, name in enumerate(("A", "B")):
            studies[name], frozen[name] = _study(book, "QA-{0}".format(index + 1), data[name])

        say("1  A search always finds something")
        for name in ("A", "B"):
            say("   market {0}   best of {1} rules: Sharpe {2} on the development decade".format(
                name, frozen[name]["trials"]["n"], report.num(frozen[name]["development"]["sharpe"], 2, True)))
        better = max(("A", "B"), key=lambda n: frozen[n]["development"]["sharpe"])
        say("   By the number a backtest prints, {0} is the better trade.".format(better))
        say()

        say("2  Count the search")
        for name in ("A", "B"):
            mixed = frozen[name]["mixed_event"]
            say("   market {0}   rotated against its own returns: p = {1} ({2})".format(
                name, report.num(mixed["p_global"], 3), report.sigma(mixed["z_global"])))
        say("   Every rule's weights are rotated in time against the market, the whole grid")
        say("   at once, and the best of each rotation is kept. That is the background.")
        say()

        say("3  Open the box once")
        results = {name: studies[name].unblind(data[name], by="demo") for name in ("A", "B")}
        for name in ("A", "B"):
            r = results[name]
            say("   market {0}   holdout Sharpe {1}   {2}{3}".format(
                name, report.pm(r["holdout"]["sharpe"], r["bootstrap"]["se"]), r["verdict"].replace("_", " "),
                " at {0}".format(report.sigma(r["decision"]["z"])) if r["verdict"] == "confirmed" else ""))
        try:
            studies["B"].unblind(data["B"], by="demo")
        except StudyError as error:
            say("   refused    a second look: " + str(error).split(". ", 1)[-1])
        say("   A was the noise. B had the drift, at a strength (r2 = {0}) no real market offers.".format(MARKETS["B"]["r2"]))
        say()

        say("4  A result stands on its data")
        word, _ = studies["B"].standing(data["B"])
        say("   {0:<10} QA-2, as recorded".format(word))
        revised = Dataset("toy", data["B"].dates, ["TOY"], data["B"].prices.copy(), 252.0)
        revised.prices[2000, 0] *= 1.001
        word, reasons = studies["B"].standing(revised)
        say("   {0:<10} one price out of {1} is revised by a tenth of a percent".format(word, revised.prices.shape[0]))
        say()

        say("5  Fake money first")
        chosen = frozen["B"]["chosen"]
        start = data["B"].dates.shape[0] - 505
        account = paper.PaperAccount.open(book.paper, "demo", 10000.0, limits={"drawdown_brake": None})
        mandate = {"dataset": "toy", "strategy": chosen["strategy"], "params": chosen["params"],
                   "rebalance": "every", "stage": "promoted", "study": "QA-2"}
        paper.set_mandate(account, mandate)
        steps = paper.advance(account, data["B"], from_date=str(data["B"].dates[start]))
        weights = strategies.build(chosen["strategy"], data["B"].prices, chosen["params"])[start:]
        reference = 10000.0 * engine.run(data["B"].returns[start:], weights, lag=1).nav()[-1]
        status = account.status()
        say("   paper      {0} of fake money, stepped through B's last two years a day at a time".format(report.money(10000.0)))
        say("   NAV        {0} after {1} marks and {2} fills. The backtest engine, asked".format(
            report.money(status["nav"]), status["marks"], status["fills"]))
        say("              separately about the same days, says {0}.".format(report.money(reference)))
        say("              ({0} over those two years. A confirmed edge still has losing stretches.)".format(
            report.pct(status["return_since_open"], 1, True)))
        ok, detail = account.ledger.verify()
        say("   {0:<10} the ledger: {1}, each naming the hash of the one before".format("holds" if ok else "fails", detail))
        lines = account.ledger.path.read_text(encoding="utf-8").splitlines()
        target = next(i for i, line in enumerate(lines) if '"kind":"fill"' in line and json.loads(line)["cost"] > 0)
        entry = json.loads(lines[target])
        entry["cost"] = 0.0
        lines[target] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        account.ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, detail = account.ledger.verify()
        say("   {0:<10} one fill's cost is edited to zero by hand: {1}".format("holds" if ok else "fails", detail))
        say()
    say("Nothing here read a real market, and nothing in this repository can place an order.")
    say("The two markets were picked to make the point. How often each thing happens is")
    say("measured, with errors, by: ./qaos toys all")
    return 0
