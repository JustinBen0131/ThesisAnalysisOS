#!/usr/bin/env python3
"""Run today's counterexample tests against an earlier revision of this repository.

    python3 evals/at_revision.py 071a348

`tests/test_counterexamples.py` uses only entry points that already existed
at that revision, so the same file runs against both. The revision is
exported to a temporary folder and the test file is copied into it. Nothing
in this checkout is touched. It needs the revision in the local history, so
a shallow clone has to fetch it first.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parents[1]
PREVIOUS_RELEASE = "071a348"


def main(argv: Optional[List[str]] = None) -> int:
    revision = ((argv if argv is not None else sys.argv[1:]) or [PREVIOUS_RELEASE])[0]
    tmp = Path(tempfile.mkdtemp(prefix="taos-revision-"))
    try:
        archive = tmp / "revision.tar"
        export = subprocess.run(["git", "-C", str(REPO), "archive", "--output", str(archive), revision],
                                capture_output=True, text=True)
        if export.returncode != 0:
            print("cannot export {0}: {1}".format(revision, export.stderr.strip() or "is it in this clone's history?"))
            return 2
        tree = tmp / "tree"
        tree.mkdir()
        with tarfile.open(str(archive)) as handle:
            try:
                handle.extractall(str(tree), filter="data")
            except TypeError:          # Python before the filter argument existed
                handle.extractall(str(tree))
        shutil.copy2(str(REPO / "tests" / "test_counterexamples.py"), str(tree / "tests" / "test_counterexamples.py"))
        done = subprocess.run([sys.executable, "-m", "unittest", "test_counterexamples"], cwd=str(tree / "tests"),
                              capture_output=True, text=True)
        ran = re.search(r"Ran (\d+) test", done.stderr)
        failures = re.search(r"failures=(\d+)", done.stderr)
        errors = re.search(r"errors=(\d+)", done.stderr)
        for line in done.stderr.splitlines():
            if line.startswith(("FAIL:", "ERROR:")):
                print("  " + line.split(" (")[0])
        print("")
        print("at {0}: ran {1}, failed {2}, errors {3}".format(
            revision, ran.group(1) if ran else "?", failures.group(1) if failures else 0, errors.group(1) if errors else 0))
        return 0
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
