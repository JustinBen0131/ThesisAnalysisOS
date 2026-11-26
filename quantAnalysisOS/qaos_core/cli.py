"""qaos: the command line. Each verb is a thin wrapper over the module that owns it."""

from __future__ import annotations

import argparse
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__, figures, gates, paper, report, sources, stats, store, toy_studies
from .data import Dataset, quality
from .study import Book, Study, StudyError, code_fingerprint, toy_code_fingerprint

HOME = Path(__file__).resolve().parent.parent


def book() -> Book:
    return Book(Path(os.environ.get("QAOS_BOOK") or HOME / "book"))


def data_dir() -> Path:
    return Path(os.environ.get("QAOS_DATA") or HOME / "data")


class CliError(Exception):
    pass


def load(name: str) -> Dataset:
    path = data_dir() / (name + ".csv")
    if not path.is_file():
        hint = "./qaos data pull {0}".format(name) if name in sources.PYPI_MEMBERS else "./qaos data fetch {0} --symbols ...".format(name)
        raise CliError("dataset '{0}' is not on this machine ({1}). Get it with: {2}".format(name, path, hint))
    return Dataset.from_csv(path, name)


def try_load(name: str) -> Optional[Dataset]:
    try:
        return load(name)
    except CliError:
        return None


def say(text: str = "") -> None:
    sys.stdout.write(text + "\n")


# -------------------------------------------------------------------- status

def cmd_status(args: argparse.Namespace) -> int:
    b = book()
    say("quantAnalysisOS {0}   book: {1}".format(__version__, b.root))
    say()
    ids = b.study_ids()
    say("studies")
    if not ids:
        say("  none registered")
    rows = []
    for study_id in ids:
        study = Study(b, study_id)
        word, reasons = study.standing(try_load(study.prereg["dataset"]["name"]))
        result = study.result
        rows.append([study_id, study.state(), (result or {}).get("verdict", "").replace("_", " "), word,
                     study.prereg["title"][:52]])
    if rows:
        say(report.table(["id", "state", "verdict", "stands", "title"], rows, right=[]))
    say()
    say("paper accounts")
    names = sorted(p.name for p in b.paper.iterdir() if (p / "ledger.jsonl").is_file()) if b.paper.is_dir() else []
    if not names:
        say("  none open")
    for name in names:
        say(report.render_paper(paper.PaperAccount(b.paper, name).status()))
    say()
    say("toy studies on record")
    toys_found = sorted(b.toys.glob("*.json")) if b.toys.is_dir() else []
    if not toys_found:
        say("  none written. Run: ./qaos toys all --write")
    for path in toys_found:
        record = store.read_json(path)
        stale = "" if record.get("code") == toy_code_fingerprint() else "  [stale: code changed since]"
        say("  {0:<15} {1}{2}".format(record["study"], record["headline"], stale))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    b = book()
    bad = 0
    say("doctor")
    for study_id in b.study_ids():
        study = Study(b, study_id)
        word, reasons = study.standing(try_load(study.prereg["dataset"]["name"]))
        say("  {0:<8} study {1} ({2}){3}".format(word, study_id, study.state(), "" if not reasons else ": " + "; ".join(reasons)))
        bad += word == "fails"
    if b.paper.is_dir():
        for path in sorted(b.paper.iterdir()):
            if not (path / "ledger.jsonl").is_file():
                continue
            ok, detail = store.ChainLog(path / "ledger.jsonl").verify()
            say("  {0:<8} paper ledger {1}: {2}".format("holds" if ok else "fails", path.name, detail))
            bad += not ok
            mandate = store.read_json(path / "mandate.json")
            if mandate is not None:
                sealed = store.seal_holds(mandate)
                say("  {0:<8} paper mandate {1}".format("holds" if sealed else "fails", path.name))
                bad += not sealed
    calibration = gates.calibration(toys_n=800)
    say("  {0:<8} engine calibration ({1} standard candles)".format(calibration["verdict"], len(calibration["checks"])))
    for item in calibration["checks"]:
        if item["verdict"] != "holds":
            say("             {0}: {1}".format(item["check"], item["detail"]))
    bad += calibration["verdict"] != "holds"
    say()
    say("nothing fails." if not bad else "{0} thing(s) fail.".format(bad))
    return 1 if bad else 0


# --------------------------------------------------------------------- gates

def cmd_gate(args: argparse.Namespace) -> int:
    if args.which == "calibration":
        out = gates.calibration()
        say("calibration: {0}".format(out["verdict"]))
        for item in out["checks"]:
            say("  {0:<6} {1}: {2}".format(item["verdict"], item["check"], item["detail"]))
        return 0 if out["verdict"] == "holds" else 1
    from . import toys as _toys

    params = json.loads(args.params) if args.params else {}
    if args.data:
        prices = load(args.data).prices
    else:
        prices = _toys.as_market(_toys.garch(1, 1500, mu_ann=0.05, rng=_toys.generator(7)))[1][0]
        if args.strategy == "pairs_zscore":
            prices = _toys.ou_pair(1, 1500, rng=_toys.generator(7))[0]
    out = gates.causality(args.strategy, params, prices)
    say("causality: {0}  {1}({2})  worst difference {3:.1e}".format(out["verdict"], args.strategy, params, out.get("worst_difference", float("nan"))))
    return 0 if out["verdict"] == "holds" else 1


# ---------------------------------------------------------------------- toys

def cmd_toys(args: argparse.Namespace) -> int:
    names = list(toy_studies.STUDIES) if args.name == "all" else [args.name]
    for name in names:
        if name not in toy_studies.STUDIES:
            raise CliError("unknown toy study '{0}'. Known: {1}, all".format(name, ", ".join(toy_studies.STUDIES)))
        if args.show:
            record = store.read_json(book().toys / (name + ".json"))
            if record is None:
                raise CliError("no recorded run of '{0}'. Run: ./qaos toys {0} --write".format(name))
            say(report.render_toy(record))
            word = "holds" if record.get("code") == toy_code_fingerprint() else "stale: the toy code changed since this was recorded"
            say("")
            say("  {0}".format(word))
            say("")
            continue
        kwargs: Dict[str, Any] = {"quick": args.quick}
        if args.seed is not None:
            kwargs["seed"] = args.seed
        out = toy_studies.STUDIES[name](**kwargs)
        out["code"] = toy_code_fingerprint()
        out["quick"] = bool(args.quick)
        say(report.render_toy(out))
        say()
        if args.write:
            if args.quick:
                raise CliError("a quick run is for looking, not for the record; drop --quick to write")
            target = book().toys / (name + ".json")
            store.write_json_atomic(target, out)
            say("  written to {0}".format(target))
            say()
    return 0


def cmd_need(args: argparse.Namespace) -> int:
    say("A true annual Sharpe of {0:g}:".format(args.sharpe))
    say(report.table(["years of data", "expected Z"], [[y, report.num(stats.expected_z(args.sharpe, y))] for y in (1, 2, 3, 5, 10, 20, 30, 50)]))
    say()
    for z in (2.0, 3.0, 5.0):
        say("  {0:g} sigma takes {1:.1f} years".format(z, stats.years_for_z(args.sharpe, z)))
    say()
    say("Years of data are the luminosity here, and they arrive at one year per year.")
    say("The only ways to go faster: more independent bets, or a longer history that you did not tune on.")
    return 0


# ---------------------------------------------------------------------- data

def _save(dataset: Dataset) -> None:
    path = data_dir() / (dataset.name + ".csv")
    dataset.to_csv(path)
    described = dataset.describe()
    say("  {0}: {1} periods, {2} to {3}, {4}".format(dataset.name, described["periods"], described["first"], described["last"],
                                                   ", ".join(dataset.symbols[:8]) + (" ..." if len(dataset.symbols) > 8 else "")))
    say("  fingerprint {0}".format(described["fingerprint"]))
    say("  saved to {0}".format(path))


def cmd_data(args: argparse.Namespace) -> int:
    if args.action == "list":
        directory = data_dir()
        manifests = sorted(directory.glob("*.json")) if directory.is_dir() else []
        if not manifests:
            say("no datasets recorded. Reproducible ones: " + ", ".join(sorted(sources.PYPI_MEMBERS)))
        for manifest in manifests:
            meta = store.read_json(manifest)
            present = manifest.with_suffix(".csv").is_file()
            word = "unknown"
            if present:
                word = "holds" if Dataset.from_csv(manifest.with_suffix(".csv")).fingerprint() == meta.get("fingerprint") else "stale"
            say("  {0:<8} {1:<14} {2} to {3}  {4} periods  {5}".format(word, meta.get("name", manifest.stem), meta.get("first"), meta.get("last"),
                                                                    meta.get("periods"), (meta.get("fingerprint") or "")[:12]))
            if not present:
                say("           the numbers are not on this machine; re-pull to compare")
        return 0
    if args.action == "pull":
        for name in args.names:
            _save(sources.pull(name, Path(args.wheels) if args.wheels else None))
        return 0
    if args.action == "fetch":
        if not args.symbols:
            raise CliError("fetch needs --symbols SPY,IEF,...")
        dataset = sources.vendor_dataset(args.names[0], [s for s in args.symbols.split(",") if s], vendor=args.vendor,
                                         rf_series=None if args.rf == "none" else args.rf, start=args.start)
        _save(dataset)
        return 0
    if args.action == "qa":
        for name in args.names:
            out = quality(load(name))
            say("{0}: {1}   golden periods {2} of {3} ({4})".format(name, out["verdict"], out["golden_periods"],
                                                                 out["dataset"]["periods"], report.pct(out["golden_fraction"])))
            for problem in out["problems"]:
                say("  problem: " + problem)
            rows = [[symbol, info.get("first"), info.get("last"), info.get("valid"), info.get("gaps_inside"), info.get("jumps"),
                     info.get("stale_periods"), report.pct(info.get("max_abs_return"))] for symbol, info in out["per_symbol"].items()]
            say(report.table(["symbol", "first", "last", "valid", "gaps", "jumps", "stale", "largest move"], rows))
        return 0
    raise CliError("unknown data action")


# --------------------------------------------------------------------- study

def cmd_study(args: argparse.Namespace) -> int:
    b = book()
    if args.action == "list":
        for study_id in b.study_ids():
            study = Study(b, study_id)
            say("  {0:<8} {1:<11} {2}".format(study_id, study.state(), study.prereg["title"]))
        return 0
    if args.action == "register":
        spec = json.loads(Path(args.target).read_text(encoding="utf-8"))
        dataset = load(spec["dataset"])
        check = quality(dataset)
        if check["verdict"] != "holds":
            raise CliError("data quality fails for '{0}': {1}".format(spec["dataset"], "; ".join(check["problems"])))
        study = Study.register(b, spec, dataset)
        prereg = study.prereg
        say("registered {0}: {1}".format(study.id, prereg["title"]))
        say("  development {0} to {1} ({2} periods)   holdout from {3} ({4} periods, sealed)".format(
            prereg["development"]["first"], prereg["development"]["last"], prereg["development"]["periods"],
            prereg["holdout"]["start"], prereg["holdout"]["periods"]))
        say("  {0} configurations may be tried; test '{1}' at {2} sigma".format(len(prereg["grid"]), prereg["decision"]["test"], prereg["decision"]["z_min"]))
        say("  seal {0}".format(prereg["seal"]))
        return 0
    study = Study(b, args.target)
    name = study.prereg["dataset"]["name"]
    if args.action == "show":
        prereg = study.prereg
        say("{0}  [{1}]  {2}".format(study.id, study.state(), prereg["title"]))
        say("  hypothesis   " + prereg["hypothesis"])
        if prereg.get("prior_exposure"):
            say("  known before " + prereg["prior_exposure"])
        for note in prereg.get("notes") or []:
            say("  note         " + note)
        say("  data         {0}, {1} to {2}; holdout from {3}".format(name, prereg["dataset"]["first"], prereg["dataset"]["last"], prereg["holdout"]["start"]))
        if prereg["holdout"].get("already_opened_by"):
            say("  not blind    this holdout was already opened by " + ", ".join(prereg["holdout"]["already_opened_by"]))
        say("  registered   {0}; test '{1}' at {2} sigma; {3} configurations".format(
            prereg["registered_at"], prereg["decision"]["test"], prereg["decision"]["z_min"], len(study.grid())))
        rows = study.trial_rows()
        if rows:
            say()
            say("development trials")
            say(report.render_trials(rows))
        if study.frozen:
            say()
            say("frozen")
            say(report.render_frozen(study.frozen))
        if study.result:
            say()
            say("unblinded")
            say(report.render_result(study.result))
        for window in ("development", "holdout"):
            syst = store.read_json(study.dir / "systematics-{0}.json".format(window))
            if syst:
                say()
                say("systematics")
                say(report.render_systematics(syst))
        return 0
    if args.action == "why":
        word, reasons = study.standing(try_load(name))
        say("  {0:<8} {1} ({2})".format(word, study.id, study.state()))
        for reason in reasons:
            say("           " + reason)
        if getattr(args, "check", False):
            return 0 if word == "holds" else 1
        return 0
    dataset = load(name)
    if args.action == "scan":
        rows = study.scan(dataset)
        say("{0}: {1} configurations evaluated on the development window. The holdout was not read.".format(study.id, len(rows)))
        say(report.render_trials(rows))
        return 0
    if args.action == "freeze":
        frozen = study.freeze(dataset, choice=args.choice)
        say("{0} frozen.".format(study.id))
        say(report.render_frozen(frozen))
        return 0
    if args.action == "unblind":
        if not args.by:
            raise CliError("unblinding is signed: --by NAME")
        result = study.unblind(dataset, by=args.by)
        say("{0}: the box is open.".format(study.id))
        say(report.render_result(result))
        return 0
    if args.action == "systematics":
        say(report.render_systematics(study.systematics(dataset, window=args.window)))
        return 0
    raise CliError("unknown study action")


# --------------------------------------------------------------------- paper

def cmd_paper(args: argparse.Namespace) -> int:
    b = book()
    if args.action == "open":
        limits = {"trade_bps": args.trade_bps}
        if args.brake is not None:
            limits["drawdown_brake"] = args.brake if args.brake > 0 else None
        account = paper.PaperAccount.open(b.paper, args.name, args.cash, limits=limits, note=args.note or "")
        say("opened paper account '{0}' with {1} of fake money.".format(args.name, report.money(args.cash)))
        say(report.render_paper(account.status()))
        return 0
    if args.action == "status":
        names = [args.name] if args.name else (sorted(p.name for p in b.paper.iterdir() if (p / "ledger.jsonl").is_file()) if b.paper.is_dir() else [])
        if not names:
            say("no paper accounts. Open one: ./qaos paper open main --cash 10000")
        for name in names:
            say(report.render_paper(paper.PaperAccount(b.paper, name).status()))
        return 0
    account = paper.PaperAccount(b.paper, args.name)
    if args.action == "mandate":
        mandate = paper.set_mandate(account, {
            "dataset": args.data, "symbols": [s for s in (args.symbols or "").split(",") if s],
            "strategy": args.strategy, "params": json.loads(args.params) if args.params else {},
            "rebalance": args.rebalance, "stage": args.stage, "study": args.study or "", "note": args.note or "",
        })
        check = gates.causality(mandate["strategy"], mandate["params"], load(args.data).select(mandate["symbols"] or load(args.data).symbols).prices)
        say("mandate set for '{0}': {1} {2} on {3}, {4}; causality {5}".format(
            args.name, mandate["strategy"], mandate["params"], mandate["dataset"], mandate["stage"], check["verdict"]))
        if check["verdict"] == "fails":
            raise CliError("the strategy looks ahead; this mandate must not be stepped")
        return 0
    if args.action == "step":
        mandate = store.read_json(account.dir / "mandate.json")
        if mandate is None:
            raise CliError("set a mandate first: ./qaos paper mandate {0} --data ... --strategy ...".format(args.name))
        steps = paper.advance(account, load(mandate["dataset"]), mandate, from_date=args.replay_from)
        if not steps:
            say("nothing new: the data ends at the last mark ({0}).".format(account.last_date))
        else:
            say("{0} step(s), {1} to {2}; {3} filled.".format(len(steps), steps[0]["date"], steps[-1]["date"], sum(1 for s in steps if s["filled"])))
        say(report.render_paper(account.status()))
        return 0
    if args.action == "resume":
        if not args.by:
            raise CliError("releasing the brake is signed: --by NAME")
        account.resume(args.by, args.note or "")
        say(report.render_paper(account.status()))
        return 0
    raise CliError("unknown paper action")


# ---------------------------------------------------------------------- misc

def cmd_figures(args: argparse.Namespace) -> int:
    target = Path(args.out) if args.out else HOME / "research" / "figures"
    written = figures.build(book(), target, try_load)
    if not written:
        say("nothing to draw: the book has no toy studies or frozen studies on record.")
    for path in written:
        say("  " + str(path))
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    suite = unittest.defaultTestLoader.discover(str(HOME / "tests"), top_level_dir=str(HOME))
    outcome = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if outcome.wasSuccessful() else 1


def cmd_demo(args: argparse.Namespace) -> int:
    from . import demo

    return demo.run()


def cmd_version(args: argparse.Namespace) -> int:
    say("quantAnalysisOS {0}".format(__version__))
    return 0


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="qaos", description="quantAnalysisOS: market research run like a physics analysis. Fake money until a human says otherwise.")
    sub = top.add_subparsers(dest="command")

    sub.add_parser("demo", help="the idea in a minute, in a throwaway folder").set_defaults(func=cmd_demo)
    sub.add_parser("status", help="what the book holds").set_defaults(func=cmd_status)
    sub.add_parser("doctor", help="verify every ledger, seal and the engine's calibration").set_defaults(func=cmd_doctor)
    sub.add_parser("selftest", help="run the tests of quantAnalysisOS itself").set_defaults(func=cmd_selftest)
    sub.add_parser("version", help="print the version").set_defaults(func=cmd_version)
    fig = sub.add_parser("figures", help="draw the figures for research/ from what the book holds")
    fig.add_argument("--out", default="")
    fig.set_defaults(func=cmd_figures)

    gate = sub.add_parser("gate", help="run a gate: calibration or causality")
    gate.add_argument("which", choices=["calibration", "causality"])
    gate.add_argument("--strategy", default="trend_sma")
    gate.add_argument("--params", default="")
    gate.add_argument("--data", default="")
    gate.set_defaults(func=cmd_gate)

    toys = sub.add_parser("toys", help="run a toy study: " + ", ".join(toy_studies.STUDIES) + ", or all")
    toys.add_argument("name")
    toys.add_argument("--seed", type=int, default=None)
    toys.add_argument("--quick", action="store_true", help="small and fast, for looking")
    toys.add_argument("--write", action="store_true", help="record the result in the book")
    toys.add_argument("--show", action="store_true", help="print the recorded result without running anything")
    toys.set_defaults(func=cmd_toys)

    need = sub.add_parser("need", help="how much data a Sharpe ratio needs before it can be seen")
    need.add_argument("--sharpe", type=float, required=True)
    need.set_defaults(func=cmd_need)

    data = sub.add_parser("data", help="datasets: list, pull (reproducible), fetch (vendor), qa")
    data.add_argument("action", choices=["list", "pull", "fetch", "qa"])
    data.add_argument("names", nargs="*")
    data.add_argument("--symbols", default="")
    data.add_argument("--vendor", default="yahoo", choices=sorted(sources.VENDORS))
    data.add_argument("--rf", default="DTB3", help="FRED series for the risk-free rate, or 'none'")
    data.add_argument("--start", default=None)
    data.add_argument("--wheels", default="", help="a folder of already downloaded wheels")
    data.set_defaults(func=cmd_data)

    study = sub.add_parser("study", help="studies: register, scan, freeze, unblind, systematics, show, why, list")
    study.add_argument("action", choices=["list", "register", "scan", "freeze", "unblind", "systematics", "show", "why"])
    study.add_argument("target", nargs="?", default="")
    study.add_argument("--choice", type=int, default=None, help="freeze this grid index instead of the best")
    study.add_argument("--by", default="", help="who opens the box")
    study.add_argument("--window", default="development", choices=["development", "holdout"])
    study.add_argument("--check", action="store_true", help="exit 1 unless the study holds")
    study.set_defaults(func=cmd_study)

    pap = sub.add_parser("paper", help="paper accounts: open, mandate, step, status, resume")
    pap.add_argument("action", choices=["open", "mandate", "step", "status", "resume"])
    pap.add_argument("name", nargs="?", default="")
    pap.add_argument("--cash", type=float, default=10000.0)
    pap.add_argument("--trade-bps", type=float, default=paper.DEFAULT_LIMITS["trade_bps"], help="cost per unit traded, in basis points")
    pap.add_argument("--brake", type=float, default=None, help="drawdown brake as a fraction (0.20); 0 turns it off")
    pap.add_argument("--data", default="")
    pap.add_argument("--symbols", default="")
    pap.add_argument("--strategy", default="")
    pap.add_argument("--params", default="")
    pap.add_argument("--rebalance", default="month_start")
    pap.add_argument("--stage", default="commissioning", choices=["commissioning", "promoted"])
    pap.add_argument("--study", default="")
    pap.add_argument("--note", default="")
    pap.add_argument("--by", default="")
    pap.add_argument("--replay-from", default=None, help="start a new account in the past (labelled a replay)")
    pap.set_defaults(func=cmd_paper)
    return top


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not getattr(args, "func", None):
        parser().print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except (CliError, StudyError, paper.PaperError, sources.SourceError) as error:
        sys.stderr.write("refused: {0}\n".format(error))
        return 2
    except BrokenPipeError:  # pragma: no cover
        return 0
