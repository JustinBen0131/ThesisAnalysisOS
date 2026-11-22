#!/usr/bin/env python3
"""Does this repository still stand behind what it says about itself?

`docs/CLAIMS.md` lists every claim with the code that implements it and the
test or the recorded run that checks it. This script reads that file back
against the repository as it is, and answers each row in the words TAOS uses
for any result:

  holds    the code and the test it names exist, or the number is the one a
           recorded run produced on exactly these bytes
  stale    the number was measured on code that has changed since
  fails    the row names something that is not there, or quotes a number the
           recorded run does not contain
  unknown  there is no recorded run to compare with

    python3 evals/claims.py             every row; exits 1 only when one fails
    python3 evals/claims.py --strict    exits 1 unless every row holds (CI runs this)
    python3 evals/claims.py --json

Finding that a named test exists is not running it. `./taos selftest` runs it.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
for entry in (str(REPO), str(REPO / "evals")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import measured  # noqa: E402
from taos_core import basis  # noqa: E402

CLAIMS = REPO / "docs" / "CLAIMS.md"
README = REPO / "README.md"
RESULTS = REPO / "evals" / "results"
RUNS = ("at_revision", "mutations", "reuse_frontier")
TICKED = re.compile(r"`([^`]+)`")


def recorded(name: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads((RESULTS / (name + ".json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def sources(folder: str) -> Dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted((REPO / folder).glob("*.py"))}


def defined(name: str, text: str) -> bool:
    return re.search(r"^\s*(def|class) {0}\b|^{0}\s*[:=]".format(re.escape(name)), text, re.M) is not None


def missing(token: str, code: Dict[str, str], tests: Dict[str, str]) -> Optional[str]:
    """None when the thing a row names is in the repository; otherwise what is not there."""
    words = token.split()
    if token.startswith(".taos/") or not words:      # written at run time, not part of the repository
        return None
    if words[0] in ("python3", "./taos", "taos"):
        return next(("{0} is not a file".format(word) for word in words if word.endswith(".py") and not (REPO / word).is_file()), None)
    if "::" in token:
        name, _, inner = token.partition("::")
        text = tests.get(Path(name).name) if name.startswith("tests/") else None
        return None if text is not None and defined(inner, text) else "{0} is not in {1}".format(inner, name)
    if "/" in token or token.endswith((".py", ".md", ".json")):
        return None if (REPO / token).exists() else "{0} is not a file".format(token)
    if token.startswith(("test_", "Test")):
        return None if any(defined(token, text) for text in tests.values()) else "no test is named {0}".format(token)
    owner, _, name = token.rpartition(".")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.]*", token):
        return None                                   # prose in ticks, not a name
    if not owner:
        return None if any(defined(name, text) for text in code.values()) else "nothing in taos_core defines {0}".format(name)
    homes = [code[owner + ".py"]] if owner + ".py" in code else [text for text in code.values() if defined(owner, text)]
    return None if any(defined(name, text) for text in homes) else "{0} is not defined".format(token)


def frontier(run: Dict[str, Any]) -> List[Any]:
    """The rows of the reuse experiment the documents quote: finest declaration, age limits, hidden input, the two isolated arms."""
    rows = {row["policy"]: row for row in run["rows"]}
    finest = max((row for row in run["rows"] if "domain(s) declared" in row["policy"]), key=lambda row: int(row["policy"].split()[1]))
    aged = [row for row in run["rows"] if row["policy"].startswith("rerun when older")]
    return [finest, aged, rows["TAOS, each check hides one folder it reads"], rows["TAOS, checks isolated, declared correctly"],
            rows["TAOS, checks isolated, each hides one folder"]]


def quoted(name: str, run: Dict[str, Any]) -> List[str]:
    """What a document may quote from a recorded run, rendered from the run and from nothing else."""
    if name == "at_revision":
        here = run["here"]
        parts = ["{0} of {1} fail at `{2}`".format(there["did_not_pass"], there["ran"], revision)
                 for revision, there in sorted(run["revisions"].items())]
        return ["; ".join(parts + ["{0} of {1} pass here".format(here["ran"] - here["did_not_pass"], here["ran"])])]
    if name == "mutations":
        return ["{0} of {1} seeded faults caught".format(run["caught"], run["faults"])]
    finest, aged, hidden, alone, refused = frontier(run)
    said = [
        "{0} executions, {1} wrong, in {2} results relied on".format(finest["executions"], finest["wrong"], run["relied_on"]),
        "{0} executions with {1} wrong".format(", ".join(str(row["executions"]) for row in aged),
                                               ", ".join(str(row["wrong"]) for row in aged)),
        "{0} wrong in {1} when every check hid one folder".format(hidden["wrong"], run["relied_on"]),
        "{0} of {1} runs passed when every check hid one folder and ran isolated; {2} executions, {3} wrong with everything declared".format(
            refused["passed"], refused["executions"], alone["executions"], alone["wrong"]),
    ]
    timing = run.get("timing")
    if timing:
        said.append("{0} ms for {1} files".format(", ".join("{0:.1f}".format(1000 * size["seconds"]) for size in timing["upkeep"]),
                                                  ", ".join("{0:,}".format(size["files"]) for size in timing["upkeep"])))
    return said


def quotable(name: str, run: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """`quoted`, or None when there is no run, or one written by an older version of its script."""
    try:
        return quoted(name, run) if run is not None else None
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def front_page(runs: Dict[str, Any], tests: int) -> List[str]:
    """The numbers README.md repeats. Each has to be there in these words, or the front page has drifted from the runs."""
    said = ["{0} tests".format(tests)]
    at, faults, reuse = [runs.get(name) if quotable(name, runs.get(name)) is not None else None for name in RUNS]
    if at:
        said.append(quoted("at_revision", at)[0].replace("; ", ", "))
    if faults:
        said.append("{0} of {1} removals are caught".format(faults["caught"], faults["faults"]))
    if reuse:
        finest, _, hidden, _, refused = frontier(reuse)
        said += ["{0} executions and {1} wrong reuses".format(finest["executions"], finest["wrong"]),
                 "{0} wrong reuses in {1}".format(hidden["wrong"], reuse["relied_on"]),
                 "{0} of {1} runs passed".format(refused["passed"], refused["executions"])]
    return said


def check() -> List[Dict[str, Any]]:
    """One verdict per row of docs/CLAIMS.md that says tested or measured, then one per number README.md repeats."""
    code, tests = sources("taos_core"), sources("tests")
    runs = {name: recorded(name) for name in RUNS}
    size = unittest.TestLoader().discover(str(REPO / "tests")).countTestCases()
    out: List[Dict[str, Any]] = []
    run_name = RUNS[0]
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not line.startswith("|") or len(cells) != 4 or not cells[0].strip("-: ") or cells[3] == "Status":
            continue
        claim, what, how, status = cells
        if re.fullmatch(r"\d+ tests", what):          # the size of the suite is counted, not recorded
            verdict = (basis.verdict(basis.HOLDS, "counted") if what == "{0} tests".format(size)
                       else basis.verdict(basis.FAILS, "the suite holds {0} tests".format(size)))
        elif status.startswith("measured"):
            run_name = next((name for name in RUNS if "evals/{0}.py".format(name) in how), run_name)
            run = runs.get(run_name)
            said = quotable(run_name, run)
            if said is None:
                verdict = basis.verdict(basis.UNKNOWN, "evals/results/{0}.json holds no run of this script as it is; "
                                        "run it with --write".format(run_name))
            elif what not in said:
                verdict = basis.verdict(basis.FAILS, "the recorded run says: {0}".format(" | ".join(said)))
            else:
                verdict = measured.standing(run)
        elif status.startswith("tested"):
            gone = [problem for token in TICKED.findall(what + " " + how) for problem in [missing(token, code, tests)] if problem]
            verdict = (basis.verdict(basis.FAILS, "; ".join(gone)) if gone
                       else basis.verdict(basis.HOLDS, "the code and the test it names exist"))
        else:
            continue
        out.append(dict(verdict, claim=claim, where="docs/CLAIMS.md"))
    page = README.read_text(encoding="utf-8") if README.is_file() else None
    for phrase in front_page(runs, size) if page is not None else []:
        verdict = (basis.verdict(basis.HOLDS, "the recorded run says the same") if phrase in page
                   else basis.verdict(basis.FAILS, "README.md does not say it, and the recorded run does"))
        out.append(dict(verdict, claim="README.md repeats: {0}".format(phrase), where="README.md"))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    words = list(argv if argv is not None else sys.argv[1:])
    rows = check()
    if "--json" in words:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for row in rows:
            claim = row["claim"] if len(row["claim"]) <= 96 else row["claim"][:93] + "..."
            print("  {0:<8} {1}".format(row["state"], claim))
            if row["state"] != basis.HOLDS:
                print("  {0:<8} {1}".format("", row["reason"]))
        tally = ["{0} {1}".format(sum(1 for row in rows if row["state"] == state), state)
                 for state in basis.STATES if any(row["state"] == state for row in rows)]
        print("")
        print("{0} rows: {1}.".format(len(rows), ", ".join(tally)))
    strict = "--strict" in words
    return 1 if any(row["state"] == basis.FAILS or (strict and row["state"] != basis.HOLDS) for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
