"""Measure retained receipts against fresh pendulum fits on a fixed perturbation grid."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from taos_core import demo, gates

EXAMPLE = ROOT / "examples/measurement"
ARTIFACT = ROOT / "evals/results/measurement_audit.json"
TOL = 1e-10
PI = Decimal("3.1415926535897932384626433832795028841971693993751")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    names = ["evals/measurement_audit.py", "docs/MEASUREMENT_AUDIT.md", "bootstrap/answers.example.json"]
    paths = [ROOT / name for name in names]
    paths.extend(sorted((ROOT / "taos_core").glob("*.py")))
    paths.extend(sorted(p for p in EXAMPLE.rglob("*") if p.is_file() and "__pycache__" not in p.parts))
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["length_m", "period_s"]:
            raise ValueError("expected columns length_m,period_s")
        rows = [(row["length_m"], row["period_s"]) for row in reader]
    if len(rows) < 5 or any(not Decimal(s).is_finite() or Decimal(s) <= 0 for row in rows for s in row):
        raise ValueError("at least five finite positive lengths and periods are required")
    return rows


def independent_fit(rows):
    with localcontext() as ctx:
        ctx.prec = 48
        points = [(Decimal(l), Decimal(t) ** 2) for l, t in rows]
        weights = sum(l ** 2 for l, _ in points)
        slope = sum((t2 / l) * (l ** 2 / weights) for l, t2 in points)
        scatter = sum((t2 - l * slope) ** 2 for l, t2 in points)
        slope_se = (scatter / ((len(rows) - 1) * weights)).sqrt()
        g = 4 * PI ** 2 / slope
        return float(g), float(g * slope_se / slope)


def design(n):
    cases = [(name, "declared", None, None) for name in ("baseline", "style", "decimal-spelling", "row-order", "fit-comment")]
    cases.extend(("scale-" + k, "declared", "all", k) for k in ("0.98", "1.001", "1.02"))
    for i in range(n):
        cases.extend(("row-{}-{}".format(i + 1, k), "declared", i, k) for k in ("0.95", "0.99", "1.01", "1.05"))
    cases.extend(("unclassified-" + k, "unclassified-input", "all", k) for k in ("0.98", "1.02"))
    cases.extend(("omission-" + k, "omitted-input", "all", k) for k in ("0.98", "1.02"))
    return cases


def change(work, case, rows):
    name, _, selected, k = case
    data = work / "data/swings.csv"
    if name == "style" or name == "fit-comment":
        rel = "figures/style.txt" if name == "style" else "analysis/fit.py"
        path = work / rel
        path.write_bytes(path.read_bytes() + b"\n# audit control\n")
    elif name == "decimal-spelling" or name == "row-order" or k is not None:
        if name == "decimal-spelling":
            first = format(Decimal(rows[0][0]), "f")
            rows = [(first + ("0" if "." in first else ".0"), rows[0][1])] + rows[1:]
        elif name == "row-order":
            rows = list(reversed(rows))
        else:
            rows = [(l, str(Decimal(t) * Decimal(k)) if selected == "all" or i == selected else t)
                    for i, (l, t) in enumerate(rows)]
        with data.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["length_m", "period_s"])
            writer.writerows(rows)


def differs(left, right):
    return any(abs(a - b) > TOL for a, b in zip(left, right))


def measure(input_path, case):
    name, cohort, selected, factor = case
    with tempfile.TemporaryDirectory(prefix="taos-audit-") as temp:
        tmp = Path(temp)
        paths = demo.build(tmp)
        work = tmp / "pendulum"
        data = work / "data/swings.csv"
        shutil.copyfile(input_path, data)
        if cohort != "declared":
            config = json.loads(paths.config_file.read_text())
            config["basis"]["domains"]["analysis"] = ["analysis/*"]
            if cohort == "omitted-input":
                config["basis"]["domains"]["measurements"] = ["data/*"]
            demo.configure(paths, basis=config["basis"])
        initial = gates.run(paths, task_id="PEN-1", agent="codex")
        if not initial["ok"] or gates.standing(paths, "PEN-1")[0]["state"] != "holds":
            raise ValueError("the initial input must produce a passing and retained fit receipt")
        rows = read_rows(data)
        base = independent_fit(rows)
        before_sha = digest(data)
        change(work, case, rows)
        retained = gates.standing(paths, "PEN-1")[0]["state"]
        after = read_rows(data)
        expected = independent_fit(after)
        precision = subprocess.run([sys.executable, "-B", "-c",
            "import json; from fit import fit, swings; print(json.dumps(fit(swings())))"],
            cwd=work / "analysis", check=True, text=True, capture_output=True)
        observed = json.loads(precision.stdout)
        fresh = gates.run(paths, task_id="PEN-1", agent="codex", force=True)["results"][0]
        expect_pass = len(after) >= 5 and 9.6 < expected[0] < 10.0 and expected[1] <= .2
        scale_ok = None
        if selected == "all":
            prediction = [value / float(factor) ** 2 for value in base]
            scale_ok = not differs(observed, prediction)
        return dict(id=name, cohort=cohort, retained=retained, fresh_exit=fresh["exit"], fresh_output=fresh["tail"],
                    g=round(observed[0], 12), se=round(observed[1], 12), expected_g=round(expected[0], 12),
                    expected_se=round(expected[1], 12), estimate_changed=differs(expected, base),
                    expected_pass=expect_pass, oracle_agrees=(not differs(observed, expected)
                    and expect_pass == (fresh["exit"] == 0)), scale_prediction_agrees=scale_ok,
                    data_sha256_before=before_sha, data_sha256_after=digest(data), rows=after)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--verify", action="store_true", help="repeat the audit and compare with the checked-in record")
    modes.add_argument("--write", action="store_true", help="replace the record for the shipped fixture")
    p.add_argument("--case", help="report just one named case")
    p.add_argument("--input", type=Path, default=EXAMPLE / "data/swings.csv", help="another pendulum CSV")
    args = p.parse_args()
    if (args.write or args.verify) and (args.case or args.input.resolve() != (EXAMPLE / "data/swings.csv").resolve()):
        p.error("--write and --verify require all cases on the shipped fixture")
    base_rows = read_rows(args.input)
    cases = [c for c in design(len(base_rows)) if args.case is None or c[0] == args.case]
    if not cases:
        p.error("unknown case: " + str(args.case))
    measured = [measure(args.input, c) for c in cases]
    record = dict(schema="pendulum-measurement-audit/1", units="m/s^2", absolute_tolerance=TOL,
                  baseline_rows=base_rows, input_sha256=digest(args.input), sources=sources(), cases=measured)
    result = json.dumps(record, indent=2, sort_keys=True) + "\n"
    intact = all(r["oracle_agrees"] and r["scale_prediction_agrees"] is not False for r in measured)
    if args.verify:
        if not ARTIFACT.is_file() or json.loads(result) != json.loads(ARTIFACT.read_text()):
            sys.exit("Audit differs from evals/results/measurement_audit.json")
        print("{} cases reproduced; source fingerprints, gate exits, standing and fitted values match.".format(len(cases)))
    elif args.write:
        if not intact:
            sys.exit("Audit disagreement; reference record left in place")
        ARTIFACT.write_text(result, encoding="utf-8")
        print("{} measured cases written to {}".format(len(cases), ARTIFACT.relative_to(ROOT)))
    else:
        print(result, end="")
    return 0 if intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
