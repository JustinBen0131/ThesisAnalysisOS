"""Do subgroup checks still apply after instrument scores or a shared threshold change?"""
import argparse
import csv
import hashlib
import json
import shlex
import shutil
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/model_evaluation"
RECORD = ROOT / "evals/results/model_evaluation.json"
GROUPS = {"A": ("a",), "B": ("b",), "pooled": ("a", "b")}
CELLS = ("tp", "fn", "fp", "tn")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def read_samples(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def perturb(work, edits):
    for edit in edits:
        path = work / edit["file"]
        if path.suffix == ".csv":
            rows = read_samples(path)
            selected = [row for row in rows if row["id"] == edit["id"]]
            require(len(selected) == 1, "expected exactly one matching reading")
            selected[0]["score"] = str(edit["score"])
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        elif path.name == "policy.json":
            policy = read_json(path)
            policy["flag_if_score_at_least"] = edit["threshold"]
            path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
        elif path.name == "caption.txt":
            path.write_text(edit["value"] + "\n", encoding="utf-8")
        else:
            raise ValueError("unknown perturbation")


def independently_count(rows, threshold):
    # ID sets reconstruct the confusion table independently of the gate's per-row branch.
    ids = {row["id"] for row in rows}
    require(len(ids) == len(rows), "duplicate sample ID")
    fault = {row["id"] for row in rows if int(row["reference_fault"]) == 1}
    flagged = {row["id"] for row in rows if int(row["score"]) >= threshold}
    return dict(zip(CELLS, map(len, (fault & flagged, fault - flagged, flagged - fault, ids - (fault | flagged)))))


def direction(after, before):
    def sensitivity(counts):
        return Fraction(counts["tp"], counts["tp"] + counts["fn"])
    delta = sensitivity(after) - sensitivity(before)
    return "up" if delta > 0 else "down" if delta < 0 else "same"


def output_counts(record, earlier=None):
    # The shared gate cache keeps the exit code and input digests, but drops stdout.
    # When a result was reused, read its counts from the original gate output.
    return {item["name"]: earlier[item["name"]] if item["name"] in record["reused"] else json.loads(item["tail"])
            for item in record["results"]}


def case_run(tmp, trial, design, demo, gates):
    work = tmp / "evaluation"
    work.mkdir()
    for name in ("a.csv", "b.csv", "policy.json", "model.py"):
        shutil.copyfile(EXAMPLE / name, work / name)
    (work / "caption.txt").write_text("QC overview\n", encoding="utf-8")
    domains = {"a": ["a.csv"], "b": ["b.csv"], "policy": ["policy.json"],
               "calculation": ["model.py"], "display": ["caption.txt"]}
    checks = []
    for name, groups in GROUPS.items():
        command = " ".join(shlex.quote(s) for s in (sys.executable, "-B", "model.py", name, *groups))
        checks.append({"name": name, "command": command, "depends_on": ["policy", "calculation", *groups]})
    paths = demo.scratch_home(tmp, workspace=work, project="Instrument QC", prefix="QC",
                              gates=[{"name": g["name"], "command": g["command"]} for g in checks],
                              tasks=[{"title": "Review the two instruments and the pooled result"}])
    demo.configure(paths, basis={"domains": domains}, gates=checks)
    log = tmp / "executions.log"
    before = gates.run(paths, task_id="QC-1", agent="codex", timeout=15)
    initial = output_counts(before)
    require(before["ok"] and log.read_text().splitlines() == list(GROUPS), "initial run did not execute all checks")
    require(initial == {k: dict(zip(CELLS, v)) for k, v in design["baseline_counts"].items()}, "baseline counts differ")
    initial_hashes = {p.name: digest(p) for p in sorted(work.iterdir()) if p.name in ("a.csv", "b.csv", "policy.json", "caption.txt")}
    perturb(work, trial["edits"])
    earlier = {v["gate"]: v["state"] for v in gates.standing(paths, "QC-1")}
    cutoff = read_json(work / "policy.json")["flag_if_score_at_least"]
    samples = {group: read_samples(work / (group + ".csv")) for group in ("a", "b")}
    expected_counts = {}
    for name, groups in GROUPS.items():
        counts = independently_count([row for group in groups for row in samples[group]], cutoff)
        require([counts[k] for k in CELLS] == trial["counts"][name], "independent count disagrees with design")
        expected_counts[name] = counts
    boundary = len(log.read_text().splitlines())
    result = gates.run(paths, task_id="QC-1", agent="codex", timeout=15)
    ran = log.read_text().splitlines()[boundary:]
    observed = output_counts(result, initial)
    failed = [row["name"] for row in result["results"] if row["exit"] != 0]
    final = {v["gate"]: v["state"] for v in gates.standing(paths, "QC-1")}
    expected_old = {name: "stale" if name in trial["old_stale"] else "holds" for name in GROUPS}
    expected_final = {name: "fails" if name in trial["fail"] else "holds" for name in GROUPS}
    signs = [direction(observed[name], initial[name]) for name in GROUPS]
    require(observed == expected_counts and signs == trial["sensitivity_direction"], "gate metric mismatch")
    require(earlier == expected_old and final == expected_final and failed == trial["fail"], "receipt or check mismatch")
    require(ran == trial["execute"] and result["reused"] == [n for n in GROUPS if n not in ran], "execution log mismatch")
    return {"id": trial["id"], "edits": trial["edits"], "threshold": cutoff, "samples": samples,
            "before_sha256": initial_hashes, "after_sha256": {n: digest(work / n) for n in initial_hashes},
            "old_receipts": earlier, "executed": ran, "reused": result["reused"], "result_after_consultation": final,
            "counts": observed, "independent_counts": expected_counts, "sensitivity_direction": dict(zip(GROUPS, signs))}


def collect(engine):
    sys.path.insert(0, str(engine))
    from taos_core import demo, gates
    design = read_json(EXAMPLE / "predictions.json")
    cases = []
    for trial in design["cases"]:
        with tempfile.TemporaryDirectory(prefix="taos-instrument-qc-") as tmp:
            cases.append(case_run(Path(tmp), trial, design, demo, gates))
    # Seal the engine modules actually loaded in this fresh process and the constructor's inputs.
    engine_inputs = {Path(module.__file__).resolve() for name, module in sys.modules.items()
                     if name.startswith("taos_core") and getattr(module, "__file__", None)}
    engine_inputs.update(engine / name for name in ("bootstrap/answers.example.json", "bootstrap/answers.schema.json", ".codex/hooks.json"))
    engine_inputs.update((engine / "taos_core/templates").glob("*.tmpl"))
    sources = {str(path.relative_to(engine)): digest(path) for path in sorted(engine_inputs)}
    for path in [Path(__file__).resolve()] + sorted(EXAMPLE.iterdir()):
        if path.is_file():
            sources[str(path.relative_to(ROOT))] = digest(path)
    return {"schema": "instrument-qc-model-evaluation-v1", "sources": sources, "cell_order": list(CELLS),
            "design_sha256": digest(EXAMPLE / "predictions.json"), "baseline_counts": design["baseline_counts"], "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="repeat the cases and compare every field with the committed record")
    mode.add_argument("--write", action="store_true", help="save the full measurement record")
    parser.add_argument("--engine-root", type=Path, default=ROOT, help="TAOS checkout (defaults to this repository)")
    args = parser.parse_args()
    result = collect(args.engine_root.resolve())
    if args.verify:
        require(result == read_json(RECORD), "record differs from this run")
    if args.write:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for case in result["cases"]:
        hits = ", ".join(f"{n} {c['tp']}/{c['tp'] + c['fn']}" for n, c in case["counts"].items())
        print(f"{case['id']}: detected {hits}; reran {', '.join(case['executed']) or 'none'}")
    if args.verify:
        print("Verified all case observations and source fingerprints.")


if __name__ == "__main__":
    main()
