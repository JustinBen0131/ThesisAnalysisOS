# A small measurement

Six pendulum swings, a fit for g, and a check. `taos demo` copies this folder
to a temporary place and uses it to show what TAOS records about a result. It
has no dependencies.

    python3 analysis/fit.py      prints g and its uncertainty
    python3 analysis/check.py    the check: exits 0 when the fit is sane

| File | What it is |
|---|---|
| `data/swings.csv` | what was measured |
| `analysis/fit.py`, `analysis/check.py` | what is computed from it, and the check |
| `figures/style.txt` | how the plot looks; the check does not read it |

In the demo the check is declared to read `analysis/` and `data/`, so an edit
to the plot style leaves a passed check alone and an edit to the data does
not.
