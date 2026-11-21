"""The check: enough swings, and a fit that lands where a pendulum on Earth must."""

import sys

from fit import fit, swings

rows = swings()
g, error = fit(rows)
problems = []
if len(rows) < 5:
    problems.append("fewer than 5 swings")
if not 9.6 < g < 10.0:
    problems.append("g = {0:.2f} is outside 9.6 to 10.0".format(g))
if error > 0.2:
    problems.append("the uncertainty {0:.2f} is above 0.2".format(error))
print("; ".join(problems) or "g = {0:.2f} +/- {1:.2f} m/s^2".format(g, error))
sys.exit(1 if problems else 0)
