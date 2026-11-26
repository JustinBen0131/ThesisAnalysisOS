"""How results are written for a person: plain text, fixed width, no decoration.

A number is printed with its error or not printed. `unknown` is a word, never
a zero.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence

WORDS = ("holds", "stale", "fails", "unknown")


def num(value: Any, digits: int = 2, sign: bool = False) -> str:
    if value is None:
        return "unknown"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(value):
        return "unknown" if value != value else ("inf" if value > 0 else "-inf")
    return ("{0:+.{1}f}" if sign else "{0:.{1}f}").format(value, digits)


def pct(value: Any, digits: int = 1, sign: bool = False) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "unknown"
    return ("{0:+.{1}f}%" if sign else "{0:.{1}f}%").format(100.0 * float(value), digits)


def pm(value: Any, error: Any, digits: int = 2, sign: bool = True) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "unknown"
    if error is None or (isinstance(error, float) and error != error):
        return num(value, digits, sign)
    return "{0} +/- {1}".format(num(value, digits, sign), num(error, digits))


def rate(cell: Dict[str, Any], digits: int = 1) -> str:
    """A counted rate, written as the count it is: '13 of 400 (3.2%)'."""
    if not cell or not cell.get("n"):
        return "unknown"
    return "{0} of {1} ({2})".format(cell["k"], cell["n"], pct(cell["rate"], digits))


def money(value: float, currency: str = "USD") -> str:
    symbol = "$" if currency == "USD" else ""
    text = "{0}{1:,.2f}".format(symbol, abs(float(value)))
    text = text if symbol else "{0} {1}".format(text, currency)
    return "-" + text if value < 0 else text


def sigma(z: Any) -> str:
    if z is None or (isinstance(z, float) and z != z):
        return "unknown"
    z = float(z)
    if math.isinf(z):
        return "beyond the resolution of the test"
    return "{0:.1f} sigma".format(z)


def table(headers: Sequence[str], rows: Iterable[Sequence[Any]], indent: int = 2, right: Optional[Sequence[int]] = None) -> str:
    rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for column, cell in enumerate(row):
            widths[column] = max(widths[column], len(cell))
    right_set = set(range(1, len(headers))) if right is None else set(right)

    def line(cells: Sequence[str]) -> str:
        parts = []
        for column, cell in enumerate(cells):
            parts.append(cell.rjust(widths[column]) if column in right_set else cell.ljust(widths[column]))
        return (" " * indent + "  ".join(parts)).rstrip()

    out = [line([str(h) for h in headers]), line(["-" * w for w in widths])]
    out.extend(line(row) for row in rows)
    return "\n".join(out)


def box(title: str, lines: Sequence[str], width: int = 78) -> str:
    inner = width - 2
    out = ["+" + "-" * inner + "+"]
    for text in [title] + list(lines):
        out.append("| " + text[:inner - 2].ljust(inner - 2) + " |")
    out.append("+" + "-" * inner + "+")
    return "\n".join(out)


# --------------------------------------------------------------- toy studies

def render_toy(out: Dict[str, Any]) -> str:
    name = out["study"]
    lines = ["{0}  (seed {1})".format(name, out["seed"]), "  " + out["headline"], ""]
    settings = out.get("settings", {})
    lines.append("  " + "; ".join("{0}: {1}".format(key, value) for key, value in settings.items()))
    lines.append("")
    rows = out["rows"]
    if name == "sensitivity":
        lines.append(table(["true Sharpe", "years", "expected Z", "median Z", "reaches 2 sigma", "reaches 3 sigma"],
                           [[num(r["true_sharpe"]), r["years"], num(r["expected_z"]), num(r["median_z"]),
                             pct(r["power_2sigma"]["rate"], 1), pct(r["power_3sigma"]["rate"], 1)] for r in rows]))
        lines.append("")
        lines.append("  The rows with a true Sharpe of 0.00 are the false-alarm rate. A normal Z gives 2.3% and 0.1%.")
    elif name == "look_elsewhere":
        lines.append(table(["family", "rules tried", "worth (indep.)", "best Sharpe", "judged alone", "deflated (N)", "deflated (N eff)", "mixed-event"],
                           [[r.get("family", ""), r["grid"], num(r["effective_trials"], 1), num(r["mean_best_sharpe"], 2, True),
                             pct(r["false_positive"]["naive"]["rate"]), pct(r["false_positive"]["deflated"]["rate"]),
                             pct(r["false_positive"]["deflated_eff"]["rate"]), pct(r["false_positive"]["mixed_event"]["rate"])] for r in rows]))
        lines.append("")
        lines.append("  Last four columns: share of markets where the best rule passed as significant. Every one is a false alarm.")
    elif name == "pulls":
        body = []
        for r in rows:
            for label in ("mertens", "newey_west", "bootstrap"):
                e = r["errors"][label]
                body.append([r["market"], label, pm(r["bias"], r["bias_error"], 3), num(r["true_spread"], 3), num(e["mean_quoted"], 3),
                             pm(e["pull_width"], e["pull_width_error"], 2, False), pct(e["coverage_68"]["rate"], 0), pct(e["coverage_95"]["rate"], 0)])
        lines.append(table(["market", "error from", "bias", "true spread", "quoted", "pull width", "in 1 sigma", "in 2 sigma"], body, right=[2, 3, 4, 5, 6, 7]))
        lines.append("")
        lines.append("  An honest error gives pull width 1.00, 68% inside one sigma and 95% inside two.")
    elif name == "overfit":
        lines.append(table(["hidden signal r2", "a perfect forecaster", "rules", "Sharpe where chosen", "Sharpe afterwards", "afterwards > 0", "corr"],
                           [[num(r["r2"], 3), num(r.get("oracle_sharpe"), 2), r["grid"], num(r["development_best"], 2, True),
                             pm(r["holdout_same_config"], r["holdout_error"]), pct(r["holdout_positive"]["rate"], 0),
                             num(r["correlation"], 2, True)] for r in rows]))
    elif name == "power":
        lines.append(table(["injected r2", "a perfect forecaster", "the trend rule", "buy-and-hold", "sharpe test", "alpha test", "timing test"],
                           [[num(r["r2"], 3), num(r.get("oracle_sharpe"), 2), num(r["holdout_sharpe_strategy"], 2, True), num(r["holdout_sharpe_buy_and_hold"], 2, True),
                             rate(r["confirmed"]["sharpe"]), rate(r["confirmed"]["alpha"]), rate(r["confirmed"]["timing"])] for r in rows]))
        lines.append("")
        lines.append("  Last three columns: how often the holdout confirmed. In the first row there is no skill to confirm.")
    return "\n".join(lines)


# ------------------------------------------------------------------- studies

def render_trials(rows: List[Dict[str, Any]], top: int = 12) -> str:
    ranked = sorted(rows, key=lambda row: (row.get("sharpe") is None, -(row.get("sharpe") or -1e9)))
    shown = ranked[:top]
    body = [[r["index"], r["strategy"], _params(r["params"]), pm(r.get("sharpe"), r.get("sharpe_se")),
             pct(r.get("cagr")), pct(r.get("max_drawdown")), num(r.get("turnover_ann"), 1), pct(r.get("avg_exposure"), 0)] for r in shown]
    text = table(["#", "strategy", "parameters", "Sharpe", "CAGR", "max drawdown", "turnover/yr", "exposure"], body, right=[0, 3, 4, 5, 6, 7])
    if len(ranked) > top:
        text += "\n  ... {0} more".format(len(ranked) - top)
    return text


def _params(params: Dict[str, Any]) -> str:
    return ", ".join("{0}={1}".format(key, value) for key, value in sorted((params or {}).items())) or "-"


def render_frozen(frozen: Dict[str, Any]) -> str:
    chosen = frozen["chosen"]
    dev = frozen["development"]
    trials = frozen["trials"]
    deflated = frozen["deflated"]
    mixed = frozen.get("mixed_event")
    outlook = frozen["holdout_outlook"]
    lines = [
        "  chosen       #{0} {1} ({2}); {3}".format(chosen["index"], chosen["strategy"], _params(chosen["params"]), frozen["selection"]),
        "  development  Sharpe {0} over {1} years; CAGR {2}, max drawdown {3}".format(
            pm(dev["sharpe"], dev["sharpe_se"]), num(dev["years"], 1), pct(dev["cagr"]), pct(dev["max_drawdown"])),
        "  the search   {0} configurations tried, worth {1} independent ones".format(trials["n"], num(trials["n_effective"], 1)),
        "               an unskilled search of that size expects a best Sharpe of {0}".format(num(deflated["sr0_ann"], 2, True)),
        "               deflated Sharpe: p = {0} ({1})".format(num(deflated["p"], 3), sigma(deflated["z"])),
    ]
    if mixed:
        lines.append("               mixed-event, whole grid: p {0} {1} ({2}{3}) over {4} rotations".format(
            "<=" if mixed.get("at_floor") else "=", num(mixed["p_global"], 3), "at least " if mixed.get("at_floor") else "",
            sigma(mixed["z_global"]), mixed["n_shifts"]))
    alpha = frozen["benchmark"]["alpha"]
    bench = frozen["benchmark"]["summary"]
    lines += [
        "  benchmark    Sharpe {0}; the strategy's alpha to it is {1}/yr (t = {2}), beta {3}".format(
            pm(bench["sharpe"], bench["sharpe_se"]), pct(alpha["alpha_ann"], 1, True), num(alpha["t_alpha"]), num(alpha["beta"])),
        "  the holdout  {0} years. If the development Sharpe were the truth it would show {1}; after the search haircut, {2}.".format(
            num(outlook["years"], 1), sigma(outlook["expected_z_if_development_is_truth"]), sigma(outlook["expected_z_after_haircut"])),
        "               3 sigma at this Sharpe takes {0} years of data.".format(num(outlook["years_for_3_sigma_at_development_sharpe"], 0)),
    ]
    return "\n".join(lines)


def render_result(result: Dict[str, Any]) -> str:
    hold = result["holdout"]
    boot = result["bootstrap"]
    alpha = result["benchmark"]["alpha"]
    bench = result["benchmark"]["summary"]
    decision = result["decision"]
    lines = [
        "  window       {0} to {1} ({2} years), opened by {3}".format(result["window"][0], result["window"][1], num(hold["years"], 1), result["opened_by"]),
        "  holdout      Sharpe {0} (bootstrap 68%: {1} to {2}); CAGR {3}, max drawdown {4}".format(
            pm(hold["sharpe"], boot["se"]), num(boot["lo68"], 2, True), num(boot["hi68"], 2, True), pct(hold["cagr"]), pct(hold["max_drawdown"])),
        "  benchmark    Sharpe {0}; alpha {1}/yr (t = {2}), beta {3}".format(
            num(bench["sharpe"], 2, True), pct(alpha["alpha_ann"], 1, True), num(alpha["t_alpha"]), num(alpha["beta"])),
        "  tests        sharpe {0}   alpha {1}   timing {2}{3}".format(
            sigma(result["z_by_test"]["sharpe"]), sigma(result["z_by_test"]["alpha"]),
            "at least " if (result.get("timing") or {}).get("at_floor") else "", sigma(result["z_by_test"]["timing"])),
        "  at {0:g}x costs Sharpe {1}".format(result["cost_stress"]["factor"], num(result["cost_stress"]["sharpe"], 2, True)),
        "  against the development estimate: pull {0}".format(num(result["pull_vs_development"], 2, True)),
        "  registered   test '{0}', bar {1} sigma, after {2} configurations tried".format(decision["test"], num(decision["z_min"], 1), result["trials_counted"]),
        "  verdict      {0}{1}".format(result["verdict"].replace("_", " "), "" if not result["reasons"] else ": " + "; ".join(result["reasons"])),
    ]
    return "\n".join(lines)


def render_systematics(syst: Dict[str, Any]) -> str:
    lines = ["  nominal Sharpe {0} on the {1} window".format(num(syst["nominal"], 2, True), syst["window"])]
    lines.append(table(["variation", "Sharpe", "shift"], [[name, num(value, 2, True), num(value - syst["nominal"], 2, True)]
                                                         for name, value in syst["variations"].items()], indent=4))
    neighbours = syst["parameter_neighbours"]
    lines.append("    {0} parameter neighbours span {1} to {2}; first half {3}, second half {4}".format(
        neighbours["n"], num(neighbours["min"], 2, True), num(neighbours["max"], 2, True),
        num(syst["halves"][0], 2, True), num(syst["halves"][1], 2, True)))
    lines.append("    systematic: " + ", ".join("{0} {1}".format(name, num(value)) for name, value in syst["components"].items())
                 + "; in quadrature {0}".format(num(syst["total"])))
    return "\n".join(lines)


def render_paper(status: Dict[str, Any]) -> str:
    currency = status["currency"]
    lines = [
        "  {0}  [{1} money]  ledger {2} ({3})".format(status["account"], status["money"], status["ledger"], status["ledger_detail"]),
        "  NAV {0}   opened with {1}   since open {2}   drawdown {3}".format(
            money(status["nav"], currency), money(status["opened_with"], currency), pct(status["return_since_open"], 2, True), pct(status["drawdown"], 1)),
        "  cash {0}   costs paid {1}   interest earned {2}   marks {3}, fills {4}, last mark {5}".format(
            money(status["cash"], currency), money(status["costs_paid"], currency), money(status["interest_earned"], currency),
            status["marks"], status["fills"], status["last_mark"] or "none"),
    ]
    if status["weights"]:
        lines.append("  holding  " + "  ".join("{0} {1}".format(symbol, pct(weight, 1)) for symbol, weight in sorted(status["weights"].items())))
    else:
        lines.append("  holding  cash only")
    if status["pending_order"]:
        targets = status["pending_order"]["targets"]
        lines.append("  pending  decided {0}: {1}".format(status["pending_order"]["decided"],
                     "  ".join("{0} {1}".format(s, pct(w, 1)) for s, w in sorted(targets.items())) or "all cash"))
    if status["braked"]:
        lines.append("  BRAKED   the drawdown brake is on; the account is going to cash until a human resumes it")
    return "\n".join(lines)
