#!/usr/bin/env python3
"""Run today's counterexample tests against earlier revisions of this repository.

    python3 evals/at_revision.py              the two earlier releases, and this checkout
    python3 evals/at_revision.py 071a348      one revision, and this checkout
    python3 evals/at_revision.py --write      also record the counts with the bytes they were measured on

`tests/test_counterexamples.py` uses only entry points that already existed
at those revisions, so the same file runs against each. A revision is
exported to a temporary folder and the test file is copied into it. Nothing
in this checkout is touched. It needs the revisions in the local history, so
a shallow clone has to fetch them first.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "evals") not in sys.path:
    sys.path.insert(0, str(REPO / "evals"))

import measured  # noqa: E402

RELEASES = ("071a348", "89f36ce")     # the release the cases were written against, and the one after it
RECORD = REPO / "evals" / "results" / "at_revision.json"
STANDS_ON = ["taos", "taos_core/*.py", "taos_core/templates/*", "bootstrap/*.json", "tests/test_counterexamples.py",
             "tests/helpers.py", "evals/at_revision.py", "evals/revision_suite.py", "evals/measured.py"]


def counts(tree: Path) -> Dict[str, Any]:
    """Run the same identified cases in the target interpreter, with its own product imports."""
    runner = Path(__file__).with_name("revision_suite.py")
    done = subprocess.run([sys.executable, "-I", str(runner), str(tree)], capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError("Incomplete counterexample suite. " + done.stderr[-600:])
    return json.loads(done.stdout.splitlines()[-1])


def source_identity():
    stamp = measured.stamp(STANDS_ON)
    head = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    changes = subprocess.check_output(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=all",
                                       "--", *STANDS_ON], text=True)
    return stamp, {"base_commit": head, "source_commit": None if changes.strip() else head,
                   "source_sha256": stamp["files"]["sha256"]}


def at(revision: str) -> Optional[Dict[str, Any]]:
    tmp = Path(tempfile.mkdtemp(prefix="taos-revision-"))
    try:
        archive = tmp / "revision.tar"
        commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", revision + "^{commit}"],
                                capture_output=True, text=True)
        if commit.returncode:
            print(f"The revision {revision} is missing from this checkout. Fetch the study revisions to replay them.")
            return None
        sha = commit.stdout.strip()
        export = subprocess.run(["git", "-C", str(REPO), "archive", "--output", str(archive), sha],
                                capture_output=True, text=True)
        if export.returncode != 0:
            print("cannot export {0}: {1}".format(revision, export.stderr.strip() or "is it in this clone's history?"))
            return None
        tree = tmp / "tree"
        tree.mkdir()
        with tarfile.open(str(archive)) as handle:
            try:
                handle.extractall(str(tree), filter="data")
            except TypeError:          # Python before the filter argument existed
                handle.extractall(str(tree))
        shutil.copy2(str(REPO / "tests" / "test_counterexamples.py"), str(tree / "tests" / "test_counterexamples.py"))
        return dict(counts(tree), source_commit=sha)
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    words = list(argv if argv is not None else sys.argv[1:])
    revisions = [word for word in words if word != "--write"] or list(RELEASES)
    writing = "--write" in words and revisions == list(RELEASES)
    initial = source_identity() if writing else None
    found: Dict[str, Any] = {"revisions": {}, "here": counts(REPO)}
    for revision in revisions:
        there = at(revision)
        if there is None:
            return 2
        if there["case_roster_sha256"] != found["here"]["case_roster_sha256"]:
            print(f"Different test inventories at {revision} and the current checkout. No record written.")
            return 2
        found["revisions"][revision] = there
        for name in there["names"]:
            print("  " + name)
        print("at {0}: ran {1}, did not pass {2}".format(revision, there["ran"], there["did_not_pass"]))
        print("")
    print("here: ran {0}, did not pass {1}".format(found["here"]["ran"], found["here"]["did_not_pass"]))
    if writing:
        if source_identity() != initial:
            print("The source changed while the study was running. No record written.")
            return 2
        found["measured_on"], identity = initial
        found["here"].update(identity)
        from taos_core.store import atomic_write_json
        atomic_write_json(RECORD, found, mode=0o644)
        print("recorded in {0}".format(RECORD.relative_to(REPO)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
