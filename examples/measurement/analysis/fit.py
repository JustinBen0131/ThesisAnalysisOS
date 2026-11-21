"""g from pendulum swings: T^2 = (4 pi^2 / g) L, fitted through the origin."""

import csv
import math
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "swings.csv"


def swings():
    with DATA.open(newline="") as handle:
        return [(float(row["length_m"]), float(row["period_s"])) for row in csv.DictReader(handle)]


def fit(rows):
    """Least squares for the slope of T^2 against L. Returns g and its standard error."""
    sxx = sum(length * length for length, _ in rows)
    sxy = sum(length * period * period for length, period in rows)
    slope = sxy / sxx
    scatter = sum((period * period - slope * length) ** 2 for length, period in rows) / (len(rows) - 1)
    g = 4 * math.pi ** 2 / slope
    return g, g * math.sqrt(scatter / sxx) / slope


if __name__ == "__main__":
    g, error = fit(swings())
    print("g = {0:.2f} +/- {1:.2f} m/s^2 from {2} swings".format(g, error, len(swings())))
