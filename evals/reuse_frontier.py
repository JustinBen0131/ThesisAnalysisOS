#!/usr/bin/env python3
"""Does keeping a record of a verified result pay for itself? Measured on the real mechanism.

A recorded result is a structure. It costs upkeep (each time it is consulted,
what it stood on is fingerprinted again) and it saves transport (the check is
not run again). This script measures both on TAOS itself, not on a model of
it: real files are edited, `taos gate run` decides what to rerun, and each
check appends a line to a log outside the workspace every time it really
executes. Whether a reuse was wrong is judged from that log and from which
file the generator edited, never from TAOS's own bookkeeping.

The predictions are written down in PREDICTIONS before anything runs. The
script exits 1 if one of them fails.

    python3 evals/reuse_frontier.py                 the full run, about a minute
    python3 evals/reuse_frontier.py --json out.json  also write the numbers
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from taos_core import demo, gates  # noqa: E402

FOLDERS, CHECKS, READS = 12, 6, 2       # check i reads folders 2i and 2i+1: what a check reads is local
GRANULARITIES = (1, 2, 3, 4, 6, 12)     # how many domains the same 12 folders are declared as
WINDOWS = (2, 4, 8)                     # "rerun when older than W consultations", the usual substitute

PREDICTIONS = {
    "P1": "with what each check reads declared correctly, no stale result is ever reused, at any granularity",
    "P2": "the number of executions equals the count derived from the edit trace exactly: nothing extra, nothing missed",
    "P3": "three tasks asking the same questions execute no more checks than one task does",
    "P4": "finer declarations never cost more executions, and stop helping once they match what the checks read",
    "P5": "a check that reads a folder it did not declare does reuse a stale result: the declaration is the limit",
    "P6": "no age window reaches both the oracle's execution count and zero stale reuse",
}


def reads(check: int) -> List[int]:
    return [READS * check + offset for offset in range(READS)]


def group(folder: int, k: int) -> str:
    return "g{0:02d}".format(folder // (FOLDERS // k))


def declared(check: int, k: int, hide: bool = False) -> List[str]:
    folders = reads(check)[:-1] if hide else reads(check)
    return sorted({group(folder, k) for folder in folders})


class World(object):
    """One workspace, one constructed home, and the logs that count real executions."""

    def __init__(self, tmp: Path, k: int, tasks: int = 1, files: int = 4, hide: bool = False):
        self.tmp, self.k, self.hide, self.files = tmp, k, hide, files
        self.work, self.logs = tmp / "work", tmp / "logs"
        self.logs.mkdir()
        for folder in range(FOLDERS):
            (self.work / "d{0:02d}".format(folder)).mkdir(parents=True)
            for index in range(files):
                (self.work / "d{0:02d}".format(folder) / "f{0}.txt".format(index)).write_text("start\n", encoding="utf-8")
        plain = [{"name": "c{0}".format(check), "command": self.command(check)} for check in range(CHECKS)]
        self.paths = demo.scratch_home(tmp, workspace=self.work, project="Reuse", prefix="RU", gates=plain,
                                       tasks=[{"title": "Task {0}".format(index + 1)} for index in range(tasks)])
        size = FOLDERS // k
        domains = {"g{0:02d}".format(index): ["d{0:02d}/*".format(folder) for folder in range(index * size, (index + 1) * size)]
                   for index in range(k)}
        demo.configure(self.paths, basis={"domains": domains},
                       gates=[dict(gate, depends_on=declared(check, k, hide)) for check, gate in enumerate(plain)])
        self.tasks = ["RU-{0}".format(index + 1) for index in range(tasks)]
        self.executed_at = [-1] * CHECKS     # the edit after which each check last really ran
        self.touched_at = [-1] * CHECKS      # the last edit to a file each check really reads

    def command(self, check: int) -> str:
        files = " ".join("d{0:02d}/*".format(folder) for folder in reads(check))
        return "cat {0} | cksum >> '{1}'".format(files, self.logs / "c{0}.log".format(check))

    def executions(self, check: int) -> int:
        log = self.logs / "c{0}.log".format(check)
        return len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0

    def consult(self, step: int) -> Tuple[int, float]:
        """Every task asks whether every check holds on the files as they are. Returns (executions, seconds)."""
        before = [self.executions(check) for check in range(CHECKS)]
        started = time.perf_counter()
        for task in self.tasks:
            record = gates.run(self.paths, task_id=task, agent="codex")
            if not record["ok"]:
                raise SystemExit("a check failed, which this workload never expects")
        seconds = time.perf_counter() - started
        ran = 0
        for check in range(CHECKS):
            if self.executions(check) != before[check]:
                self.executed_at[check] = step
                ran += self.executions(check) - before[check]
        return ran, seconds

    def edit(self, step: int, folder: int, index: int) -> None:
        (self.work / "d{0:02d}".format(folder) / "f{0}.txt".format(index)).write_text("edit {0}\n".format(step), encoding="utf-8")
        for check in range(CHECKS):
            if folder in reads(check):
                self.touched_at[check] = step

    def stale_relied_on(self) -> int:
        """How many checks are being relied on although a file they read changed after they last really ran."""
        return sum(1 for check in range(CHECKS) if self.executed_at[check] < self.touched_at[check])


def trace(edits: int, seed: int, files: int = 4) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    return [(rng.randrange(FOLDERS), rng.randrange(files)) for _ in range(edits)]


def expected(edit_trace: Sequence[Tuple[int, int]], k: int) -> int:
    """From the edits alone: how many checks declare the domain each edit fell in."""
    return sum(sum(1 for check in range(CHECKS) if group(folder, k) in declared(check, k)) for folder, _ in edit_trace)


def measure(edit_trace: Sequence[Tuple[int, int]], k: int, tasks: int = 1, hide: bool = False) -> Dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="taos-reuse-"))
    try:
        world = World(tmp, k, tasks=tasks, hide=hide)
        world.consult(-1)                                   # the first verification of everything is not counted
        executions, wrong, samples = 0, 0, []
        for step, (folder, index) in enumerate(edit_trace):
            world.edit(step, folder, index)
            ran, seconds = world.consult(step)
            executions += ran
            wrong += world.stale_relied_on()
            samples.append((ran, seconds))
        return {"executions": executions, "wrong": wrong, "samples": samples}
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def window(edit_trace: Sequence[Tuple[int, int]], every: int) -> Dict[str, int]:
    """The age rule on the same edits, computed directly: rerun everything each `every` consultations."""
    ran_at, touched_at, executions, wrong = [-1] * CHECKS, [-1] * CHECKS, 0, 0
    for step, (folder, _) in enumerate(edit_trace):
        for check in range(CHECKS):
            if folder in reads(check):
                touched_at[check] = step
        if step % every == 0:
            ran_at = [step] * CHECKS
            executions += CHECKS
        wrong += sum(1 for check in range(CHECKS) if ran_at[check] < touched_at[check])
    return {"executions": executions, "wrong": wrong}


def upkeep(files: int, repeats: int = 5) -> Dict[str, float]:
    """Seconds to ask "does everything still hold?" when nothing changed, for a workspace of a given size."""
    tmp = Path(tempfile.mkdtemp(prefix="taos-reuse-"))
    try:
        world = World(tmp, 6, files=files)
        world.consult(-1)
        asked = [world.consult(0)[1] for _ in range(repeats)]
        return {"files": FOLDERS * files, "seconds": statistics.median(asked)}
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def line_fit(samples: Sequence[Tuple[int, float]]) -> Tuple[float, float]:
    """Least squares for seconds = base + per_check * executions."""
    xs, ys = [float(ran) for ran, _ in samples], [seconds for _, seconds in samples]
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread if spread else 0.0
    return mean_y - slope * mean_x, slope


def experiment(edits: int = 60, seed: int = 7, ks: Sequence[int] = GRANULARITIES, timing: bool = True) -> Dict[str, Any]:
    edit_trace = trace(edits, seed)
    oracle = expected(edit_trace, FOLDERS)
    rows: List[Dict[str, Any]] = [{"policy": "rerun everything", "executions": CHECKS * edits, "wrong": 0}]
    for every in WINDOWS:
        rows.append(dict(window(edit_trace, every), policy="rerun when older than {0} consultations".format(every)))
    by_k, pooled = {}, []
    for k in ks:
        found = measure(edit_trace, k)
        by_k[k] = dict(found, expected=expected(edit_trace, k))
        pooled += found["samples"]
        rows.append({"policy": "TAOS, {0} domain(s) declared".format(k), "executions": found["executions"], "wrong": found["wrong"],
                     "expected": by_k[k]["expected"]})
    rows.append({"policy": "oracle (knows what every check reads)", "executions": oracle, "wrong": 0})
    finest = max(ks)
    shared = measure(edit_trace, finest, tasks=3)
    hidden = measure(edit_trace, finest, hide=True)
    rows.append({"policy": "TAOS, three tasks asking", "executions": shared["executions"], "wrong": shared["wrong"]})
    rows.append({"policy": "TAOS, each check hides one folder it reads", "executions": hidden["executions"], "wrong": hidden["wrong"]})
    ordered = [by_k[k]["executions"] for k in sorted(ks)]
    held = {
        "P1": all(by_k[k]["wrong"] == 0 for k in ks) and shared["wrong"] == 0,
        "P2": all(by_k[k]["executions"] == by_k[k]["expected"] for k in ks),
        "P3": shared["executions"] == by_k[finest]["executions"],
        "P4": all(later <= earlier for earlier, later in zip(ordered, ordered[1:])) and by_k[finest]["executions"] == oracle,
        "P5": hidden["wrong"] > 0,
        "P6": all(not (row["executions"] <= oracle and row["wrong"] == 0) for row in rows[1:1 + len(WINDOWS)]),
    }
    result: Dict[str, Any] = {"edits": edits, "seed": seed, "checks": CHECKS, "folders": FOLDERS, "relied_on": CHECKS * edits,
                              "rows": rows, "predictions": {key: {"text": PREDICTIONS[key], "held": held[key]} for key in PREDICTIONS},
                              "environment": {"python": platform.python_version(), "platform": platform.platform()}}
    if timing:
        base, per_check = line_fit(pooled)
        sizes = [upkeep(files) for files in (4, 40, 400)]
        spared = CHECKS - by_k[finest]["executions"] / float(edits)      # checks not rerun per consultation
        for size in sizes:
            size["break_even_check_seconds"] = size["seconds"] / spared
        result["timing"] = {"seconds_when_something_reran": base, "seconds_per_execution": per_check, "upkeep": sizes,
                            "checks_spared_per_consultation": spared}
    return result


def report(result: Dict[str, Any]) -> str:
    out = ["{0} edits, {1} checks, {2} results relied on. A wrong reuse is a result relied on after a file it reads changed.".format(
        result["edits"], result["checks"], result["relied_on"]), "",
        "  {0:<44} {1:>10} {2:>12}".format("policy", "executions", "wrong reuses")]
    for row in result["rows"]:
        out.append("  {0:<44} {1:>10} {2:>12}".format(row["policy"], row["executions"], row["wrong"]))
    out.append("")
    for key, item in result["predictions"].items():
        out.append("  {0} {1}  {2}".format(key, "held  " if item["held"] else "FAILED", item["text"]))
    timing = result.get("timing")
    if timing:
        out += ["", "  On this machine one execution of these small checks costs {0:.1f} ms, and asking costs:".format(
            1000 * timing["seconds_per_execution"])]
        for size in timing["upkeep"]:
            out.append("    {0:>5} files: {1:6.1f} ms to ask when nothing changed; reuse pays for any check slower than {2:.1f} ms".format(
                size["files"], 1000 * size["seconds"], 1000 * size["break_even_check_seconds"]))
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--edits", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-timing", action="store_true")
    parser.add_argument("--json", help="also write the numbers to this file")
    args = parser.parse_args(argv)
    result = experiment(edits=args.edits, seed=args.seed, timing=not args.no_timing)
    print(report(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if all(item["held"] for item in result["predictions"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
