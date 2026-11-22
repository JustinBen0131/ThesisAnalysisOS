#!/usr/bin/env python3
"""Do the tests have teeth? Put each known fault back, one at a time, and see whether a test notices.

Each entry below removes one protection from a copy of the code: the date
check on an instruction, the binding of a pass to the files it tested, the
rule that only a person accepts. If the named test module still passes with
the protection gone, that test was not testing it.

    python3 evals/mutations.py            every fault, about two minutes
    python3 evals/mutations.py dates      only the faults whose name contains "dates"
    python3 evals/mutations.py --write    every fault, and record the count with the bytes it was measured on

Nothing in this checkout is changed: every fault is applied to a temporary copy.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "evals") not in sys.path:
    sys.path.insert(0, str(REPO / "evals"))

import measured  # noqa: E402

SKIP = shutil.ignore_patterns(".git", ".taos", "__pycache__", "results")
RECORD = REPO / "evals" / "results" / "mutations.json"
STANDS_ON = ["taos_core/*.py", "tests/*.py", "evals/mutations.py"]

# (name, file, the protection, what replaces it, the test module that must fail)
FAULTS: List[Tuple[str, str, str, str, str]] = [
    ("dates: an instruction governs on every day", "taos_core/rules.py",
     '    return basis.within(rule["said_on"], rule.get("expires"), on)', "    return True", "test_counterexamples"),
    ("scope: a replacement applies outside its own scope", "taos_core/rules.py",
     ' and in_force(other, on) and covers(other["scope"], scope):', " and in_force(other, on):", "test_counterexamples"),
    ("lessons: every time shown counts as a repeat", "taos_core/lessons.py",
     '"exposures": len(cases), "repeats": len(violated),', '"exposures": len(cases), "repeats": len(cases),', "test_counterexamples"),
    ("lessons: a bare id prefix is in scope", "taos_core/lessons.py",
     'any(item.startswith(scope + "-") for item in lineage)', "any(item.startswith(scope) for item in lineage)", "test_counterexamples"),
    ("basis: a pass covers files edited afterwards", "taos_core/basis.py",
     "        if recorded.get(name) == now.get(name):\n            continue", "        if True:\n            continue", "test_counterexamples"),
    ("closure: done can be reached without a holding check", "taos_core/tasks.py",
     '                if short and not str(waive or "").strip():', "                if False:", "test_counterexamples"),
    ("control: a profile is credited without being observed", "taos_core/control.py",
     '            if row.get("observed") is True:', "            if True:", "test_counterexamples"),
    ("leases: a lapsed lease can be revived", "taos_core/claims.py",
     "                if not self._is_fresh(claim, now or utc_now()):", "                if False:", "test_counterexamples"),
    ("replay: any text is read as true", "taos_core/replay.py",
     '    if isinstance(value, str) and value.strip().lower() in ("true", "yes", "1"):', "    if isinstance(value, str) and value.strip():",
     "test_counterexamples"),
    ("changes: a number from nowhere confirms a change", "taos_core/changes.py",
     '    if not counted and not str(source or "").strip():', "    if False:", "test_counterexamples"),
    ("anchors: a prediction can be rewritten", "taos_core/anchors.py",
     '    if sci.find(all_adjustments(paths), adjustment_id, "adjustment").get("prediction"):', "    if False:", "test_counterexamples"),
    ("start: a refused start still takes the claim", "taos_core/lifecycle.py",
     '    if task.get("status") == "blocked" and store.blockers(task["id"]):', "    if False:", "test_counterexamples"),
    ("sharing: a result is shared whatever the files are", "taos_core/gates.py",
     "    return sha256_text(canonical_json([definition, digests]))", "    return sha256_text(canonical_json([definition]))", "test_standing"),
    ("domains: a check on an undeclared domain is trusted", "taos_core/gates.py",
     "        if undeclared:", "        if False:", "test_standing"),
    ("acceptance: it carries over to an edited version", "taos_core/standing.py",
     '    verdict = basis.compare(given.get("basis") or {}, snap, listed=(receipt or {}).get("snapshot"))',
     '    verdict = basis.verdict(basis.HOLDS, "")', "test_standing"),
    ("acceptance: an agent can accept its own work", "taos_core/tasks.py",
     '        if by != "human":', "        if False:", "test_standing"),
    ("domains: an input git ignores is left out of what a check stood on", "taos_core/basis.py",
     '        names = sorted(set(names) | set(on_disk(root, named, settings.get("ignore"))))', "        pass", "test_counterexamples"),
    ("isolation: an isolated check runs where every file can be read", "taos_core/gates.py",
     "            code, tail = _isolated(cwd, before, filed, command, timeout)", "            code, tail = _execute(command, cwd, timeout)",
     "test_counterexamples"),
]


def passes(tree: Path, module: str) -> bool:
    done = subprocess.run([sys.executable, "-m", "unittest", module], cwd=str(tree / "tests"), capture_output=True, text=True)
    return done.returncode == 0


def caught(fault: Tuple[str, str, str, str, str]) -> bool:
    """Apply one fault to a fresh copy and run its test module there. True when the module fails."""
    name, relative, protection, replacement, module = fault
    tmp = Path(tempfile.mkdtemp(prefix="taos-fault-"))
    try:
        tree = tmp / "tree"
        shutil.copytree(str(REPO), str(tree), ignore=SKIP)
        target = tree / relative
        text = target.read_text(encoding="utf-8")
        if text.count(protection) != 1:
            raise SystemExit("the fault {0!r} no longer applies to {1}: update evals/mutations.py".format(name, relative))
        target.write_text(text.replace(protection, replacement), encoding="utf-8")
        return not passes(tree, module)
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    words = list(argv if argv is not None else sys.argv[1:])
    wanted = [word for word in words if word != "--write"]
    faults = [fault for fault in FAULTS if not wanted or any(word in fault[0] for word in wanted)]
    for module in sorted({fault[4] for fault in faults}):
        if not passes(REPO, module):          # the control: with nothing broken, the tests pass
            print("{0} fails before any fault is applied; fix that first".format(module))
            return 1
    missed = []
    for fault in faults:
        hit = caught(fault)
        print("  {0}  {1}".format("caught" if hit else "MISSED", fault[0]))
        if not hit:
            missed.append(fault[0])
    print("")
    print("{0} of {1} seeded faults caught.".format(len(faults) - len(missed), len(faults)))
    if "--write" in words and not wanted:
        found = {"faults": len(faults), "caught": len(faults) - len(missed), "missed": missed,
                 "names": [fault[0] for fault in faults], "measured_on": measured.stamp(STANDS_ON)}
        RECORD.write_text(json.dumps(found, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("recorded in {0}".format(RECORD.relative_to(REPO)))
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
