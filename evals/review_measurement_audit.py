"""Verify the pendulum audit independently using its source CSV and raw JSON.

Run from the repository root. This checks the selected edits, fitted quantities
and expected receipt and gate outcomes. It does not rerun TAOS or generalize
the observations beyond the published pendulum fixture.
"""

import csv
import hashlib
import io
import itertools
import json
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import NamedTuple, Optional


TAU_SQUARED = Decimal("39.478417604357434475337963999504604541254797628963")
TOLERANCE = Decimal("1e-10")
HEADER = ["length_m", "period_s"]


class Case(NamedTuple):
    rows: list
    cohort: str
    standing: str
    period_scale: Optional[Fraction] = None


def require(condition, message):
    if not condition:
        raise ValueError(message)


def as_decimal(value):
    return Decimal(value.numerator) / Decimal(value.denominator)


def estimate(rows):
    """Use exact rational sums for the slope and residual sum of squares."""
    xx = sum(length ** 2 for length, _ in rows)
    xy = sum(length * period ** 2 for length, period in rows)
    yy = sum(period ** 4 for _, period in rows)
    slope = xy / xx
    residual = yy - xy ** 2 / xx
    slope_variance = residual / ((len(rows) - 1) * xx)
    gravity = TAU_SQUARED / as_decimal(slope)
    uncertainty = gravity * as_decimal(slope_variance).sqrt() / as_decimal(slope)
    return gravity, uncertainty


def scenarios(baseline):
    cases = {
        "baseline": Case(baseline, "declared", "holds"),
        "style": Case(baseline, "declared", "holds"),
        "decimal-spelling": Case(baseline, "declared", "stale"),
        "row-order": Case(baseline[::-1], "declared", "stale"),
        "fit-comment": Case(baseline, "declared", "stale"),
    }
    uniform_groups = (
        ("scale", "declared", "stale", ("0.98", "1.001", "1.02")),
        ("omission", "omitted-input", "holds", ("0.98", "1.02")),
        ("unclassified", "unclassified-input", "unknown", ("0.98", "1.02")),
    )
    for label, cohort, standing, factors in uniform_groups:
        for factor in factors:
            scale = Fraction(factor)
            rows = [(length, period * scale) for length, period in baseline]
            cases[f"{label}-{factor}"] = Case(rows, cohort, standing, scale)
    for i, factor in itertools.product(range(len(baseline)), ("0.95", "0.99", "1.01", "1.05")):
        rows = baseline.copy()
        length, period = baseline[i]
        rows[i] = length, period * Fraction(factor)
        cases[f"row-{i + 1}-{factor}"] = Case(rows, "declared", "stale")
    return cases


def expected_gate(rows, gravity, uncertainty):
    problems = []
    if len(rows) < 5:
        problems.append("fewer than 5 swings")
    if not Decimal("9.6") < gravity < Decimal("10.0"):
        problems.append(f"g = {gravity:.2f} is outside 9.6 to 10.0")
    if uncertainty > Decimal("0.2"):
        problems.append(f"the uncertainty {uncertainty:.2f} is above 0.2")
    return int(bool(problems)), "; ".join(problems) or f"g = {gravity:.2f} +/- {uncertainty:.2f} m/s^2"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def as_rational(rows):
    return [(Fraction(length), Fraction(period)) for length, period in rows]


def verify(record, source_bytes):
    header, *fixture = csv.reader(io.StringIO(source_bytes.decode("utf-8")))
    require(header == HEADER, "Unexpected CSV header")
    require(record["baseline_rows"] == fixture, "Recorded baseline rows differ from CSV")
    source_digest = sha256(source_bytes)
    require(record["input_sha256"] == source_digest, "Recorded baseline SHA-256 differs")
    baseline = as_rational(fixture)
    baseline_estimate = estimate(baseline)
    cases = scenarios(baseline)
    rows = record["cases"]
    require(len(rows) == len(cases) and {row["id"] for row in rows} == set(cases),
            "Case IDs differ from the published design")
    counts = Counter()
    for row in rows:
        name = row["id"]
        case = cases[name]
        recorded_rows = row["rows"]
        require(row["cohort"] == case.cohort, f"{name}: unexpected cohort")
        require(row["retained"] == case.standing, f"{name}: unexpected retained standing")
        require(as_rational(recorded_rows) == case.rows, f"{name}: raw rows differ from expected edit")
        if name == "decimal-spelling":
            require(recorded_rows[0][0] != fixture[0][0], f"{name}: decimal spelling did not change")
            require(recorded_rows[0][1:] == fixture[0][1:] and recorded_rows[1:] == fixture[1:],
                    f"{name}: another field changed")
        require(row["data_sha256_before"] == source_digest, f"{name}: wrong input SHA-256")
        data_rewritten = case.period_scale is not None or name.startswith("row-") or name == "decimal-spelling"
        after = csv_bytes(recorded_rows) if data_rewritten else source_bytes
        require(row["data_sha256_after"] == sha256(after), f"{name}: wrong edited SHA-256")

        gravity, uncertainty = estimate(case.rows)
        quantities = (("g", gravity), ("se", uncertainty), ("expected_g", gravity), ("expected_se", uncertainty))
        for field, reference in quantities:
            require(abs(Decimal(str(row[field])) - reference) <= TOLERANCE,
                    f"{name}: {field} differs from independent calculation")
        if case.period_scale is not None:
            for actual, original in zip((gravity, uncertainty), baseline_estimate):
                predicted = original / as_decimal(case.period_scale ** 2)
                require(abs(actual - predicted) < Decimal("1e-44"), f"{name}: analytic period scaling failed")
        scale_flag = True if case.period_scale is not None else None
        require(row["scale_prediction_agrees"] is scale_flag, f"{name}: incorrect scaling comparison flag")
        require(row["oracle_agrees"] is True, f"{name}: the audit reports an oracle disagreement")
        changed = (gravity, uncertainty) != baseline_estimate
        require(row["estimate_changed"] is changed, f"{name}: incorrect estimate-change flag")
        expected_exit, expected_output = expected_gate(case.rows, gravity, uncertainty)
        require(row["expected_pass"] is (expected_exit == 0), f"{name}: incorrect gate prediction")
        require(row["fresh_exit"] == expected_exit, f"{name}: incorrect fresh gate exit")
        require(row["fresh_output"] == expected_output, f"{name}: unexpected fresh gate output")
        counts[case.cohort, case.standing, expected_exit] += 1
    return counts


def main():
    source = Path("examples/measurement/data/swings.csv").read_bytes()
    record = json.loads(Path("evals/results/measurement_audit.json").read_text(encoding="utf-8"))
    with localcontext() as context:
        context.prec = 52
        counts = verify(record, source)
    print(f"{sum(counts.values())} cases independently verified from raw JSON and swing data.")
    for (cohort, standing, gate_exit), count in sorted(counts.items()):
        print(f"  {cohort}: {count} retained {standing}, fresh exit {gate_exit}")


if __name__ == "__main__":
    main()
