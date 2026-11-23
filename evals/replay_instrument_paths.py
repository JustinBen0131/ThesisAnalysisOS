"""Compare two correction orders, then rewind each edit in reverse order.

Each route starts a fresh native TAOS home with the shipped A, B and pooled
checks. At every observation, gates.standing and gates.run supply the native
decisions. Reused stdout is read from the original execution receipt. A raw
CSV tally by ID and a fresh execution of all three check commands provide
separate controls. Both execution counts come from model.py's process log.
The second control runs after each native consultation, outside TAOS, and
cannot seed its receipt store.

Run python3 evals/replay_instrument_paths.py --verify from the checkout.
"""
import argparse
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from model_evaluation import EXAMPLE, GROUPS, ROOT, independently_count, read_json, read_samples, require

sys.path.insert(0, str(ROOT))
from taos_core import demo, gates


RECORD = ROOT / "evals/results/followups/instrument-paths.json"
FILES = ("a.csv", "b.csv", "model.py", "policy.json", "predictions.json")
OLD_SCORES = {"A": ("A03", 70, 50), "B": ("B04", 50, 70)}
EXPECTED_TP = {"baseline": (3, 3), "A": (2, 3), "B": (3, 4), "AB": (2, 4)}
TASK = "QC-1"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def instrument_checks(tmp, work):
    domains = {"a": ["a.csv"], "b": ["b.csv"], "policy": ["policy.json"],
               "calculation": ["model.py"], "display": ["caption.txt"]}
    commands = {name: [sys.executable, "-B", "model.py", name, *groups] for name, groups in GROUPS.items()}
    checks = [{"name": name, "command": shlex.join(commands[name]),
               "depends_on": ["policy", "calculation", *groups]} for name, groups in GROUPS.items()]
    paths = demo.scratch_home(tmp, workspace=work, project="Instrument QC", prefix="QC",
                              gates=[{"name": c["name"], "command": c["command"]} for c in checks],
                              tasks=[{"title": "Review the two instruments and the pooled result"}])
    demo.configure(paths, basis={"domains": domains}, gates=checks)
    return paths, commands


def corrected_inputs(original):
    design = json.loads(original["predictions.json"])
    edits, = [case["edits"] for case in design["cases"] if case["id"] == "offsetting-score-corrections"]
    require(edits == [{"file": group.lower() + ".csv", "id": row, "score": new}
                      for group, (row, old, new) in OLD_SCORES.items()], "fixture edits differ")
    corrected = {}
    for group, (row, old, new) in OLD_SCORES.items():
        raw = original[group.lower() + ".csv"]
        old_line = f"{row},1,{old}\n".encode()
        require(raw.splitlines(keepends=True).count(old_line) == 1, f"expected one original row for {row}")
        corrected[group] = raw.replace(old_line, f"{row},1,{new}\n".encode())
    return corrected


def raw_readings(work, state):
    samples = {group: read_samples(work / (group + ".csv")) for group in ("a", "b")}
    counts = {name: independently_count([row for group in groups for row in samples[group]], 60)
              for name, groups in GROUPS.items()}
    a, b = EXPECTED_TP[state]
    for name, detected, total in (("A", a, 4), ("B", b, 4), ("pooled", a + b, 8)):
        c = counts[name]
        require((c["tp"], c["tp"] + c["fn"]) == (detected, total), f"{state}/{name}: fixed prediction differs")
    return counts


def log_rows(log):
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def observe(paths, work, commands, seen, state):
    raw = raw_readings(work, state)
    # Independent history uses the literal relevant input bytes for each check.
    keys = {name: (name, *(work.joinpath(group + ".csv").read_bytes() for group in groups),
                   (work / "model.py").read_bytes(), (work / "policy.json").read_bytes())
            for name, groups in GROUPS.items()}
    before = {row["gate"]: row["state"] for row in gates.standing(paths, TASK)}
    predicted_before = {name: seen.get(key, "stale" if seen else "unknown") for name, key in keys.items()}
    require(before == predicted_before, f"{state}: receipt standing differs from byte history: {before}")
    log = work.parent / "executions.log"
    start = len(log_rows(log))
    record = gates.run(paths, task_id=TASK, agent="codex", timeout=15)
    executed = log_rows(log)[start:]
    keep = [name for name in GROUPS if before[name] == "holds"]
    require(record["reused"] == keep and executed == [n for n in GROUPS if n not in keep],
            f"{state}: native execution log or reuse differs from standing")

    native, exits = {}, {}
    for row in record["results"]:
        name = row["name"]
        source = row
        if name in keep:
            original_run = read_json(paths.home / row["receipt"])
            source, = [item for item in original_run["results"] if item["name"] == name]
            require(name not in original_run["reused"] and row["basis"] == source["basis"] and
                    row["exit"] == source["exit"], f"{state}/{name}: reuse did not cite its execution")
        native[name] = json.loads(source["tail"])
        exits[name] = row["exit"]
    after = {row["gate"]: row["state"] for row in gates.standing(paths, TASK)}
    for name, key in keys.items():
        c = raw[name]
        expected_exit = int(4 * c["tp"] < 3 * (c["tp"] + c["fn"]))
        require(exits[name] == expected_exit and after[name] == ("fails" if expected_exit else "holds"),
                f"{state}/{name}: native verdict differs from raw sensitivity")
        seen[key] = after[name]

    all_start = len(log_rows(log))
    rerun_all = {}
    for name, command in commands.items():
        process = subprocess.run(command, cwd=work, text=True, capture_output=True, timeout=15)
        require(process.returncode == exits[name] and not process.stderr, f"{state}/{name}: forced check differs")
        rerun_all[name] = json.loads(process.stdout)
    all_executed = log_rows(log)[all_start:]
    require(all_executed == list(GROUPS), f"{state}: incomplete rerun-all process log")
    require(native == raw == rerun_all, f"{state}: native counts, CSV tally and rerun-all counts disagree")
    sensitivity = {n: f"{c['tp']}/{c['tp'] + c['fn']}" for n, c in native.items()}
    return ({"state": state, "before": before, "after": after, "executed": executed, "reused": record["reused"],
             "rerun_all_count": len(all_executed), "native_sensitivity": sensitivity}, raw)


def run_route(tmp, order, original, corrected, states):
    work = tmp / "evaluation"
    work.mkdir()
    for name, data in original.items():
        (work / name).write_bytes(data)
    (work / "caption.txt").write_text("QC overview\n", encoding="utf-8")
    paths, commands = instrument_checks(tmp, work)
    steps, seen, applied = [], {}, set()
    for action, group in [("start", None), *(("apply", g) for g in order),
                          *(("rewind", g) for g in reversed(order))]:
        if group:
            file = group.lower() + ".csv"
            if action == "apply":
                (work / file).write_bytes(corrected[group])
                applied.add(group)
            else:
                (work / file).write_bytes(original[file])
                applied.remove(group)
        state = "".join(sorted(applied)) or "baseline"
        for name, data in original.items():
            instrument = name[0].upper() if name.endswith(".csv") else None
            expected = corrected[instrument] if instrument in applied else data
            require((work / name).read_bytes() == expected, f"{order}/{state}: wrong fixture bytes for {name}")
        step, raw = observe(paths, work, commands, seen, state)
        step["action"] = f"{action} {group}" if group else action
        steps.append(step)
        require(states.setdefault(state, raw) == raw, f"{state}: path-dependent raw tally")
    restored = all((work / name).read_bytes() == data for name, data in original.items())
    require(restored and steps[0]["native_sensitivity"] == steps[-1]["native_sensitivity"], "rewind failed")
    return {"order": list(order), "steps": steps, "restored_fixture_bytes": restored,
            "native_executions": sum(len(step["executed"]) for step in steps),
            "rerun_all_executions": sum(step["rerun_all_count"] for step in steps)}


def replay():
    original = {name: (EXAMPLE / name).read_bytes() for name in FILES}
    policy = json.loads(original["policy.json"])
    require(policy == {"flag_if_score_at_least": 60, "minimum_sensitivity": {"numerator": 3, "denominator": 4}},
            "fixture policy differs from the independent predictions")
    corrected = corrected_inputs(original)
    states, routes = {}, []
    for order in ("AB", "BA"):
        with tempfile.TemporaryDirectory(prefix="taos-instrument-path-") as tmp:
            routes.append(run_route(Path(tmp), order, original, corrected, states))
    hashes = {name: sha256(data) for name, data in original.items()}
    # Digest the sorted UTF-8 filename/digest manifest so file boundaries are explicit.
    fixture_digest = sha256("".join(f"{name}\t{hashes[name]}\n" for name in sorted(hashes)).encode())
    return {"schema": "instrument-correction-paths/1", "fixture": "examples/model_evaluation",
            "fixture_sha256": fixture_digest,
            "source_sha256": hashes, "policy": policy, "checks": list(GROUPS),
            "edits": {g: {"id": row, "from": old, "to": new} for g, (row, old, new) in OLD_SCORES.items()},
            "independent_csv_counts": states, "routes": routes,
            "native_executions": sum(route["native_executions"] for route in routes),
            "rerun_all_executions": sum(route["rerun_all_executions"] for route in routes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="compare all observations to the checked-in result")
    mode.add_argument("--write", action="store_true", help="write the verified observations as JSON")
    args = parser.parse_args()
    result = replay()
    if args.verify:
        require(result == read_json(RECORD), "replay differs from the checked-in result")
    if args.write:
        RECORD.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for route in result["routes"]:
        print(f"{' then '.join(route['order'])} and rewind: {route['native_executions']} native executions, "
              f"{route['rerun_all_executions']} rerun-all executions, original fixture restored.")
    print("All 10 observations agree with independent CSV counts and fresh checks.")


if __name__ == "__main__":
    main()
