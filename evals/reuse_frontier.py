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
script exits 1 if one of them fails. P7 came later, with the isolation it
tests: it was committed to docs/METHOD.md before that code was written.

Supplemental timings compare a warm in-process consultation to one direct,
uncached check command on eight files. Ratios are computed within each pair
on the same machine. Their sign intervals assume independent rounds with a
common median; shared cache and machine load can correlate repeated rounds.

    python3 evals/reuse_frontier.py            the full run, about two minutes
    python3 evals/reuse_frontier.py --verify   check the saved measurements without starting a clock
    python3 evals/reuse_frontier.py --write    also record the numbers with the bytes they were measured on
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
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

if str(REPO / "evals") not in sys.path:
    sys.path.insert(0, str(REPO / "evals"))

import measured  # noqa: E402
from taos_core import demo, gates  # noqa: E402

RECORD = REPO / "evals" / "results" / "reuse_frontier.json"
STANDS_ON = ["taos_core/*.py", "evals/reuse_frontier.py"]

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
    "P7": "isolated, a check that reads a folder it did not declare never passes, and correct declarations cost nothing extra",
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

    def __init__(self, tmp: Path, k: int, tasks: int = 1, files: int = 4, hide: bool = False, isolate: bool = False):
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
                       gates=[dict(gate, depends_on=declared(check, k, hide), isolated=isolate)
                              for check, gate in enumerate(plain)])
        self.tasks = ["RU-{0}".format(index + 1) for index in range(tasks)]
        self.executed_at = [-1] * CHECKS     # the edit after which each check last really ran
        self.touched_at = [-1] * CHECKS      # the last edit to a file each check really reads

    def command(self, check: int) -> str:
        files = " ".join("d{0:02d}/*".format(folder) for folder in reads(check))
        # like a real check, it fails when a file it reads is not there
        return "cat {0} > /dev/null && cat {0} | cksum >> '{1}'".format(files, self.logs / "c{0}.log".format(check))

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


# The control always reads eight six-byte files, even when the measured tree grows.
# Each round visits every size. Each group of six rounds balances all possible orders.
FILES_PER_FOLDER = (4, 40, 400)
UPKEEP_ROUNDS = 12
ISOLATION_ROUNDS = 36
TIMING_SCHEMA = "paired-reference-v1"


def digest(data: Any) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def median_interval(values: Sequence[float]) -> Dict[str, float]:
    """Central order statistics for a two-sided sign interval on the median.

    With n independent draws from a continuous distribution and rank k (one-based),
    the probability outside [X(k), X(n+1-k)] is 2 * P(Bin(n, 1/2) < k).
    Use the narrowest ranks with at least 95% coverage. Ties are conservative.
    """
    ordered = sorted(values)
    n = len(ordered)
    if n < 6 or any(not math.isfinite(value) for value in ordered):
        raise ValueError("a finite 95% median interval requires at least six finite observations")
    tail, rank = 1, 1
    while 40 * (tail + math.comb(n, rank)) <= 2 ** n:
        tail += math.comb(n, rank)
        rank += 1
    return {"median": statistics.median(ordered), "low": ordered[rank - 1], "high": ordered[-rank],
            "rank": rank, "coverage": 1 - 2 * tail / (2 ** n)}


def workload(run: Dict[str, Any]) -> Dict[str, Any]:
    seed, edits = run["seed"], run["edits"]
    if type(seed) is not int or type(edits) is not int or edits < 1:
        raise ValueError("expected a seeded, nonempty edit trace")
    if (run["checks"], run["folders"], run["relied_on"]) != (CHECKS, FOLDERS, CHECKS * edits):
        raise ValueError("workload dimensions differ from the edit trace")
    return {"seed": seed, "edits": edits, "checks": CHECKS, "folders": FOLDERS,
            "edit_trace_sha256": digest(trace(edits, seed)),
            "initial_file_contents": "start\n", "upkeep_domains": 6,
            "files_per_folder": list(FILES_PER_FOLDER), "upkeep_rounds": UPKEEP_ROUNDS,
            "isolation_rounds": ISOLATION_ROUNDS, "isolation_domains": FOLDERS,
            "reference": "uncached command for check 0 on two folders with four files each",
            "consultation": "one in-process gates.run for six checks; initial verification excluded"}


def balanced_orders(arms, rounds, rng):
    """Randomize complete sets of permutations so each arm occupies each position equally often."""
    permutations = list(itertools.permutations(arms))
    if rounds % len(permutations):
        raise ValueError("a balanced design requires complete sets of orders")
    result = []
    for _ in range(rounds // len(permutations)):
        rng.shuffle(permutations)
        result.extend(permutations)
    return result


def timing_schedule(seed: int):
    rng = random.Random(seed)
    sizes = balanced_orders(FILES_PER_FOLDER, UPKEEP_ROUNDS, rng)
    orders = {size: balanced_orders(("ask", "reference"), UPKEEP_ROUNDS, rng) for size in FILES_PER_FOLDER}
    for block, order in enumerate(sizes):
        for size in order:
            yield {"study": "upkeep", "block": block, "files": FOLDERS * size, "order": list(orders[size][block])}
    triples = balanced_orders(("open", "isolated", "reference"), ISOLATION_ROUNDS, rng)
    for block, (order, edit) in enumerate(zip(triples, trace(ISOLATION_ROUNDS, seed))):
        yield {"study": "isolation", "block": block, "edit": list(edit), "order": list(order)}


def uncached_reference(world: World) -> float:
    """Run the actual check command directly. Its independent execution log must grow by one."""
    command = world.command(0)
    before = world.executions(0)
    start = time.perf_counter()
    code, _ = gates._execute(command, world.work, timeout=1800)
    elapsed = time.perf_counter() - start
    if code or world.executions(0) != before + 1:
        raise ValueError("uncached reference did not complete exactly one check")
    return elapsed


def observe_timing(seed: int) -> List[Dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="taos-reuse-") as tmp:
        def world(name, domains, **kwargs):
            home = Path(tmp) / name
            home.mkdir()
            return World(home, domains, **kwargs)

        control = world("control", FOLDERS)
        trees = {FOLDERS * size: world("tree-" + str(size), 6, files=size) for size in FILES_PER_FOLDER}
        arms = {name: world(name, FOLDERS, isolate=(name == "isolated")) for name in ("open", "isolated")}
        for workspace in [*trees.values(), *arms.values()]:
            workspace.consult(-1)
        uncached_reference(control)
        observations = []
        for planned in timing_schedule(seed):
            upkeep = planned["study"] == "upkeep"
            if not upkeep:
                for workspace in arms.values():
                    workspace.edit(planned["block"], *planned["edit"])
            seconds = {}
            for arm in planned["order"]:
                if arm == "reference":
                    seconds[arm] = uncached_reference(control)
                else:
                    target = trees[planned["files"]] if upkeep else arms[arm]
                    ran, seconds[arm] = target.consult(planned["block"])
                    if ran != (0 if upkeep else 1):
                        raise ValueError("timing arm executed an unexpected number of checks")
            observations.append(dict(planned, seconds=seconds))
        return observations


def summarize_timing(run: Dict[str, Any], observations: list, conditions: dict) -> Dict[str, Any]:
    """Validate the recorded experiment design before deriving every quoted number."""
    schedule = list(timing_schedule(run["seed"]))
    if not isinstance(observations, list) or len(observations) != len(schedule):
        raise ValueError("timing record is missing observations")
    trees = {FOLDERS * size: [] for size in FILES_PER_FOLDER}
    reference, deltas, overhead = [], [], []
    for planned, row in zip(schedule, observations):
        if not isinstance(row, dict) or {k: v for k, v in row.items() if k != "seconds"} != planned:
            raise ValueError("timing observation differs from its scheduled block or order")
        seconds = row.get("seconds")
        if not isinstance(seconds, dict) or set(seconds) != set(planned["order"]):
            raise ValueError("timing observation lacks the scheduled arms")
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in seconds.values()):
            raise ValueError("each elapsed time must be positive and finite")
        reference.append(seconds["reference"])
        if planned["study"] == "upkeep":
            trees[planned["files"]].append(seconds)
        else:
            delta = seconds["isolated"] - seconds["open"]
            deltas.append(delta)
            overhead.append(delta / seconds["reference"])

    finest = max((row for row in run["rows"] if "domain(s) declared" in row["policy"]),
                 key=lambda row: int(row["policy"].split()[1]))
    spared = CHECKS - finest["executions"] / run["edits"]
    sizes = []
    for files, pairs in trees.items():
        elapsed = statistics.median(p["ask"] for p in pairs)
        sizes.append({"files": files, "input_bytes": files * len(b"start\n"), "seconds": elapsed,
                      "break_even_check_seconds": elapsed / spared if spared > 0 else None,
                      "reference_ratio": median_interval([p["ask"] / p["reference"] for p in pairs])})
    # Each list is in block order, so this compares tree sizes within the same round.
    small, large = trees[min(trees)], trees[max(trees)]
    growth = median_interval([b["ask"] / a["ask"] for a, b in zip(small, large)])
    delta = median_interval(deltas)
    return {"upkeep": sizes, "checks_spared_per_consultation": spared,
            "seconds_per_execution": statistics.median(reference), "large_to_small_time_ratio": growth,
            "isolating_one_execution": {"pairs": len(deltas), "median_seconds": delta["median"],
                                        "low_seconds": delta["low"], "high_seconds": delta["high"],
                                        "network_and_workspace_closed": conditions["network_and_workspace_closed"],
                                        "added_reference_ratio": median_interval(overhead)}}


def timing_record(run: Dict[str, Any]) -> Dict[str, Any]:
    design = workload(run)
    observations = observe_timing(run["seed"])
    conditions = {"system": platform.system(), "release": platform.release(), "architecture": platform.machine(),
                  "python": platform.python_version(), "clock": "time.perf_counter", "cache": "warmed",
                  "concurrent_machine_load": "uncontrolled", "network_and_workspace_closed": gates.closes()}
    dataset = {"schema": TIMING_SCHEMA, "workload": design, "conditions": conditions, "observations": observations}
    return dict(dataset, dataset_sha256=digest(dataset), **summarize_timing(run, observations, conditions))


def verify_timing(run: Dict[str, Any]) -> None:
    """Check dataset identity, matched ordering and derived values. No local clocks are sampled."""
    timing = run.get("timing")
    if not isinstance(timing, dict) or timing.get("schema") != TIMING_SCHEMA:
        raise ValueError("saved record has no raw timings in the paired-reference format")
    if timing.get("workload") != workload(run):
        raise ValueError("timing workload differs from the recorded edit trace")
    conditions = timing.get("conditions")
    required = ("system", "release", "architecture", "python", "clock", "cache", "concurrent_machine_load")
    if (not isinstance(conditions, dict) or not all(isinstance(conditions.get(k), str) and conditions[k] for k in required)
            or type(conditions.get("network_and_workspace_closed")) is not bool):
        raise ValueError("timing record is missing measurement conditions")
    dataset = {k: timing.get(k) for k in ("schema", "workload", "conditions", "observations")}
    if timing.get("dataset_sha256") != digest(dataset):
        raise ValueError("timing dataset fingerprint differs from its raw observations or conditions")
    for key, value in summarize_timing(run, timing["observations"], conditions).items():
        if timing.get(key) != value:
            raise ValueError("summary differs from raw timings: " + key)


def expected(edit_trace: Sequence[Tuple[int, int]], k: int) -> int:
    """From the edits alone: how many checks declare the domain each edit fell in."""
    return sum(sum(1 for check in range(CHECKS) if group(folder, k) in declared(check, k)) for folder, _ in edit_trace)


def measure(edit_trace: Sequence[Tuple[int, int]], k: int, tasks: int = 1, hide: bool = False,
            isolate: bool = False) -> Dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="taos-reuse-"))
    try:
        world = World(tmp, k, tasks=tasks, hide=hide, isolate=isolate)
        world.consult(-1)                                   # the first verification of everything is not counted
        executions, wrong = 0, 0
        for step, (folder, index) in enumerate(edit_trace):
            world.edit(step, folder, index)
            ran, _ = world.consult(step)
            executions += ran
            wrong += world.stale_relied_on()
        return {"executions": executions, "wrong": wrong}
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def refusals(edit_trace: Sequence[Tuple[int, int]], k: int) -> Dict[str, int]:
    """Every check hides one folder it reads, and every check is isolated. Does one ever pass, or get reused?"""
    tmp = Path(tempfile.mkdtemp(prefix="taos-reuse-"))
    try:
        world = World(tmp, k, hide=True, isolate=True)
        runs = passed = reused = 0
        for step in range(-1, len(edit_trace)):
            if step >= 0:
                world.edit(step, *edit_trace[step])
            record = gates.run(world.paths, task_id=world.tasks[0], agent="codex")
            runs += len(record["results"]) - len(record["reused"])
            passed += sum(1 for result in record["results"] if result["exit"] == 0)
            reused += len(record["reused"])
        return {"runs": runs, "passed": passed, "reused": reused}
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


def experiment(edits: int = 60, seed: int = 7, ks: Sequence[int] = GRANULARITIES, timing: bool = True) -> Dict[str, Any]:
    edit_trace = trace(edits, seed)
    oracle = expected(edit_trace, FOLDERS)
    rows: List[Dict[str, Any]] = [{"policy": "rerun everything", "executions": CHECKS * edits, "wrong": 0}]
    for every in WINDOWS:
        rows.append(dict(window(edit_trace, every), policy="rerun when older than {0} consultations".format(every)))
    by_k = {}
    for k in ks:
        found = measure(edit_trace, k)
        by_k[k] = dict(found, expected=expected(edit_trace, k))
        rows.append({"policy": "TAOS, {0} domain(s) declared".format(k), "executions": found["executions"], "wrong": found["wrong"],
                     "expected": by_k[k]["expected"]})
    rows.append({"policy": "oracle (knows what every check reads)", "executions": oracle, "wrong": 0})
    finest = max(ks)
    shared = measure(edit_trace, finest, tasks=3)
    hidden = measure(edit_trace, finest, hide=True)
    rows.append({"policy": "TAOS, three tasks asking", "executions": shared["executions"], "wrong": shared["wrong"]})
    rows.append({"policy": "TAOS, each check hides one folder it reads", "executions": hidden["executions"], "wrong": hidden["wrong"]})
    alone = measure(edit_trace, finest, isolate=True)
    refused = refusals(edit_trace, finest)
    rows.append({"policy": "TAOS, checks isolated, declared correctly", "executions": alone["executions"], "wrong": alone["wrong"]})
    rows.append({"policy": "TAOS, checks isolated, each hides one folder", "executions": refused["runs"], "wrong": refused["reused"],
                 "passed": refused["passed"]})
    ordered = [by_k[k]["executions"] for k in sorted(ks)]
    held = {
        "P1": all(by_k[k]["wrong"] == 0 for k in ks) and shared["wrong"] == 0,
        "P2": all(by_k[k]["executions"] == by_k[k]["expected"] for k in ks),
        "P3": shared["executions"] == by_k[finest]["executions"],
        "P4": all(later <= earlier for earlier, later in zip(ordered, ordered[1:])) and by_k[finest]["executions"] == oracle,
        "P5": hidden["wrong"] > 0,
        "P6": all(not (row["executions"] <= oracle and row["wrong"] == 0) for row in rows[1:1 + len(WINDOWS)]),
        "P7": (refused["passed"] == 0 and refused["reused"] == 0
               and alone["executions"] == by_k[finest]["executions"] and alone["wrong"] == 0),
    }
    result: Dict[str, Any] = {"edits": edits, "seed": seed, "checks": CHECKS, "folders": FOLDERS, "relied_on": CHECKS * edits,
                              "rows": rows, "predictions": {key: {"text": PREDICTIONS[key], "held": held[key]} for key in PREDICTIONS},
                              "environment": {"python": platform.python_version(), "platform": platform.platform()}}
    if timing:
        result["timing"] = timing_record(result)
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
        from claims import timing_claims
        out.extend(["", "  Supplemental timings for this workload on the recorded machine."])
        out.extend("  " + label + ": " + value for label, value in timing_claims(result).items())
        if timing.get("schema") == TIMING_SCHEMA:
            growth = timing["large_to_small_time_ratio"]
            out.append("  Largest/smallest tree consultation time within each round: "
                       "{median:.2g}× (95% median interval {low:.2g} to {high:.2g}).".format(**growth))
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--edits", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-timing", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="verify the saved timing data, summaries and source fingerprints without measuring again")
    mode.add_argument("--write", action="store_true", help="record the numbers with the bytes they were measured on")
    args = parser.parse_args(argv)
    if args.verify:
        try:
            run = json.loads(RECORD.read_text(encoding="utf-8"))
            verify_timing(run)
            if run.get("measured_on", {}).get("patterns") != sorted(STANDS_ON):
                raise ValueError("saved source declaration differs from this experiment")
            verdict = measured.standing(run)
            if verdict["state"] != "holds":
                raise ValueError(verdict["reason"])
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print("Could not verify recorded timings: " + str(exc), file=sys.stderr)
            return 1
        print("Verified source fingerprints, timing dataset, paired orders and derived summaries.")
        return 0
    if args.edits < 1:
        parser.error("--edits must be positive")
    result = experiment(edits=args.edits, seed=args.seed, timing=not args.no_timing)
    print(report(result))
    if args.write:
        result["measured_on"] = measured.stamp(STANDS_ON)
        RECORD.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("recorded in {0}".format(RECORD))
    return 0 if all(item["held"] for item in result["predictions"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
