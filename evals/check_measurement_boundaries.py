"""Exercise the shipped pendulum check at its acceptance boundaries.

Run `python3 evals/check_measurement_boundaries.py` for a summary or add
`--json` for inputs, computed fits, actual check output, and SHA-256 fingerprints.
Injected fits test the check's comparisons. The separate six-swing fixtures
test the shipped estimator and check together. These are software controls.
"""

import argparse
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/measurement"
FIT = EXAMPLE / "analysis/fit.py"
CHECK = EXAMPLE / "analysis/check.py"
SWINGS = EXAMPLE / "data/swings.csv"
TAU_SQUARED = Decimal("39.478417604357434475337963999504604541254797628963")
FIT_TOLERANCE = 5e-12
INJECT = """
import json, runpy, sys, types

data = json.loads(sys.argv[2])
shim = types.ModuleType("fit")
shim.swings = lambda: [(1.0, 2.0)] * data["swings"]
shim.fit = lambda rows: (data["g_m_s2"], data["standard_error_m_s2"])
sys.modules["fit"] = shim
runpy.run_path(sys.argv[1], run_name="__main__")
"""
PRINT_FIT = """
import json
from fit import fit, swings

rows = swings()
gravity, error = fit(rows)
print(json.dumps({"swings": len(rows), "g_m_s2": gravity, "standard_error_m_s2": error}))
"""


def run(args, cwd):
    result = subprocess.run([sys.executable, "-B", *args], cwd=cwd, capture_output=True,
                            text=True, check=False, timeout=15)
    return {"exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def checker_matches(result, expected_exit, expected_message):
    return (result["exit"] == expected_exit and not result["stderr"]
            and expected_message in result["stdout"])


def injected_cases():
    """Run the actual checker with one controlled boundary at a time."""
    lower, upper, se_limit, nearby = 9.6, 10.0, 0.2, math.nextafter
    accepted = " +/- "
    outside = "is outside 9.6 to 10.0"
    high_error = "is above 0.2"
    # ID, number of swings, fitted gravity, standard error, expected exit and output.
    cases = (
        ("g-below-lower", 6, nearby(lower, -math.inf), 0.1, 1, outside),
        ("g-at-lower", 6, lower, 0.1, 1, outside),
        ("g-above-lower", 6, nearby(lower, math.inf), 0.1, 0, accepted),
        ("g-below-upper", 6, nearby(upper, -math.inf), 0.1, 0, accepted),
        ("g-at-upper", 6, upper, 0.1, 1, outside),
        ("g-above-upper", 6, nearby(upper, math.inf), 0.1, 1, outside),
        ("se-below-limit", 6, 9.8, nearby(se_limit, -math.inf), 0, accepted),
        ("se-at-limit", 6, 9.8, se_limit, 0, accepted),
        ("se-above-limit", 6, 9.8, nearby(se_limit, math.inf), 1, high_error),
        ("four-swings", 4, 9.8, 0.1, 1, "fewer than 5 swings"),
        ("five-swings", 5, 9.8, 0.1, 0, accepted),
    )
    rows = []
    for identifier, swings, gravity, error, expected_exit, message in cases:
        injected = {"swings": swings, "g_m_s2": gravity, "standard_error_m_s2": error,
                    "g_float_hex": gravity.hex(), "standard_error_float_hex": error.hex()}
        check = run(["-c", INJECT, str(CHECK), json.dumps(injected)], ROOT)
        rows.append({"id": identifier, "injected_fit": injected, "expected_exit": expected_exit,
                     "expected_stdout_contains": message, "checker": check,
                     "matches": checker_matches(check, expected_exit, message)})
    return rows


def scale_periods(baseline, target):
    """Calculate the scale using exact rational data sums and the scaling identity."""
    rows = [(Fraction(length), Fraction(period)) for length, period in baseline]
    xx = sum(length ** 2 for length, _ in rows)
    xy = sum(length * period ** 2 for length, period in rows)
    inverse_slope = xx / xy
    with localcontext() as context:
        context.prec = 48
        original = TAU_SQUARED * Decimal(inverse_slope.numerator) / Decimal(inverse_slope.denominator)
        factor = (original / target).sqrt()
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["length_m", "period_s"])
        writer.writerows((length, str(Decimal(period) * factor)) for length, period in baseline)
    return str(factor), stream.getvalue()


def fitted_cases():
    """Give the shipped fitter and checker two scaled versions of the six-swing CSV."""
    with SWINGS.open(newline="", encoding="utf-8") as source:
        baseline = [(r["length_m"], r["period_s"]) for r in csv.DictReader(source)]
    if len(baseline) != 6:
        raise ValueError("This comparison requires the six-swing fixture")
    planned = (
        ("below-lower-fit", Decimal("9.599"), 1, "is outside 9.6 to 10.0"),
        ("above-lower-fit", Decimal("9.601"), 0, " +/- "),
    )
    rows = []
    with tempfile.TemporaryDirectory(prefix="pendulum-boundaries-") as directory:
        root = Path(directory)
        analysis = root / "analysis"
        analysis.mkdir()
        (root / "data").mkdir()
        for source in (FIT, CHECK):
            shutil.copyfile(source, analysis / source.name)
        for identifier, target, expected_exit, message in planned:
            factor, scaled_csv = scale_periods(baseline, target)
            scaled_bytes = scaled_csv.encode("utf-8")
            (root / "data/swings.csv").write_bytes(scaled_bytes)
            fit_run = run(["-c", PRINT_FIT], analysis)
            check = run([str(analysis / CHECK.name)], root)
            measured = json.loads(fit_run["stdout"]) if fit_run["exit"] == 0 and not fit_run["stderr"] else None
            correct_fit = (measured is not None and measured["swings"] == 6
                           and abs(measured["g_m_s2"] - float(target)) <= FIT_TOLERANCE)
            rows.append({
                "id": identifier, "target_g_m_s2": str(target), "period_scale": factor,
                "scaled_csv": scaled_csv, "csv_sha256": sha256(scaled_bytes).hexdigest(),
                "measured_fit": measured, "fit_process": fit_run,
                "rounded_g_m_s2": f"{measured['g_m_s2']:.2f}" if measured else None,
                "expected_exit": expected_exit, "checker": check,
                "matches": correct_fit and checker_matches(check, expected_exit, message),
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="print full observations and source hashes")
    args = parser.parse_args()
    exact = injected_cases()
    fitted = fitted_cases()
    same_display = all(r["rounded_g_m_s2"] == "9.60" and "g = 9.60" in r["checker"]["stdout"] for r in fitted)
    opposite_exits = [r["checker"]["exit"] for r in fitted] == [1, 0]
    verdict = all(r["matches"] for r in exact + fitted) and same_display and opposite_exits
    files = (Path(__file__).resolve(), FIT, CHECK, SWINGS)
    result = {
        "schema": "pendulum-check-boundaries/1",
        "source_sha256": {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in files},
        "injected_checker_controls": exact,
        "six_swing_fit_controls": fitted,
        "absolute_fit_target_tolerance_m_s2": FIT_TOLERANCE,
        "both_check_outputs_display_9_60": same_display,
        "fitted_exits_fail_then_pass": opposite_exits,
        "passed": verdict,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{sum(r['matches'] for r in exact)}/{len(exact)} injected checker controls matched.")
        for row in fitted:
            measured = row["measured_fit"]
            value = f"{measured['g_m_s2']:.12f} m/s²" if measured else "fit unavailable"
            print(f"{row['id']}: {value}, checker exit {row['checker']['exit']}")
        print("Both print g = 9.60 with opposite exits." if same_display and opposite_exits
              else "The fitted pair did not meet the display and exit comparison. See --json.")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
