"""Review the seven-request pendulum handoff using saved observations and original source files."""
import argparse
import csv
import hashlib
import io
import json
import runpy
from collections import Counter
from copy import deepcopy
from decimal import localcontext
from pathlib import Path

# The intervention schedule, from the published protocol. Status and origin are derived below.
HISTORY = (
    ("baseline", "PEN-1", "none"),
    ("style-only", "PEN-2", "style"),
    ("measurement-fails", "PEN-2", "material"),
    ("new-task-sees-failure", "PEN-3", "none"),
    ("restore-exact-bytes", "PEN-2", "restore"),
    ("same-values-new-bytes", "PEN-2", "respell"),
    ("share-respelled-pass", "PEN-3", "none"),
)
ACTOR = {"PEN-1": "codex", "PEN-2": "claude", "PEN-3": "codex"}
EXAMPLE = "examples/measurement/"
DATA = "data/swings.csv"
STYLE = "figures/style.txt"
ANALYSIS = ("analysis/check.py", "analysis/fit.py", DATA)


def require(observed, expected, label):
    if observed != expected or type(observed) is not type(expected):
        raise ValueError(f"{label}: expected {expected!r}, found {observed!r}")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def original_sources(repo, record):
    sources = record["sources"]
    required = {EXAMPLE + path for path in (*ANALYSIS, STYLE)}
    required.update(("evals/handoff_audit.py", "taos_core/basis.py", "taos_core/gates.py", "taos_core/demo.py"))
    if not required.issubset(sources):
        raise ValueError("incomplete source manifest")
    for name, expected in sources.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"invalid relative source: {name}")
        path = (repo / relative).resolve()
        path.relative_to(repo)
        require(digest(path.read_bytes()), expected, name)


def csv_version(original, spelling):
    # Preserve every other byte, including line endings. The intervention targets the last swing only.
    lines = original.splitlines(keepends=True)
    require(lines[-1].rstrip(b"\r\n"), b"1.20,2.19", "original sixth reading")
    lines[-1] = lines[-1].replace(b"2.19", spelling, 1)
    return b"".join(lines)


def analysis_basis(example, data):
    files = {name: digest(data if name == DATA else (example / name).read_bytes()) for name in ANALYSIS}
    signature = "\n".join(name + "\0" + files[name] for name in sorted(files))
    return {"analysis": digest(signature.encode("utf-8")), "(undeclared)": digest(b"")}


def numerical_output(raw, arithmetic):
    header, *rows = csv.reader(io.StringIO(raw.decode("utf-8")))
    require(header, arithmetic["HEADER"], "measurement columns")
    rows = arithmetic["as_rational"](rows)
    with localcontext() as context:
        context.prec = 48
        g, se = arithmetic["estimate"](rows)
        code, stdout = arithmetic["expected_gate"](rows, g, se)
    return rows, code, stdout


def view(cache, key, task_has_record):
    if key in cache:
        origin, exit_code, _ = cache[key]
        return ("holds", origin) if exit_code == 0 else ("fails", None)
    return ("stale", None) if task_has_record else ("unknown", None)


def check_views(recorded, active, cache, key, previously_requested, label):
    require(set(recorded), set(active), label + " task set")
    for task in active:
        state, origin = view(cache, key, task in previously_requested)
        require(recorded[task]["state"], state, label + " " + task + " status")
        require(recorded[task]["pass_origin"], origin, label + " " + task + " pass origin")


def verify(repo, record):
    repo = Path(repo).resolve()
    require(record["schema"], "pendulum-handoff-audit/1", "schema")
    original_sources(repo, record)
    # Only the independent rational-sum estimator and text/exit oracle are used.
    arithmetic = runpy.run_path(str(repo / "evals/review_measurement_audit.py"))
    example = repo / EXAMPLE
    original = (example / DATA).read_bytes()
    original_rows, _, _ = numerical_output(original, arithmetic)
    data = original
    style = (example / STYLE).read_bytes()
    cache, active, previously_requested = {}, [], set()
    tally = Counter()
    require(len(record["observations"]), len(HISTORY), "request count")
    for index, (row, (step, task, edit)) in enumerate(zip(record["observations"], HISTORY), 1):
        for field, value in (("sequence", index), ("id", step), ("task", task), ("edit", edit),
                             ("actor_label", ACTOR[task]), ("task_started", task not in active)):
            require(row[field], value, step + " " + field)
        if task not in active:
            active.append(task)
        if edit == "style":
            style += b"\n# change presentation only\n"
        elif edit == "material":
            data = csv_version(original, b"2.2995")
        elif edit == "restore":
            data = original
        elif edit == "respell":
            data = csv_version(original, b"2.190")
        require(row["csv_text"].encode("utf-8"), data, step + " current CSV")
        require(row["data_sha256"], digest(data), step + " data fingerprint")
        require(row["style_sha256"], digest(style), step + " style fingerprint")
        basis = analysis_basis(example, data)
        require(row["basis_sha256"], basis, step + " receipt basis")
        numeric, code, output = numerical_output(data, arithmetic)
        require(row["csv_exact_original"], data == original, step + " byte equality")
        require(row["csv_same_numbers"], numeric == original_rows, step + " numerical equality")
        key = basis["analysis"]
        check_views(row["views_before"], active, cache, key, previously_requested, step + " before")
        before, _ = view(cache, key, task in previously_requested)
        if before == "holds":
            action = "reuse"
            origin, earlier_code, earlier_output = cache[key]
            require((code, output), (earlier_code, earlier_output), step + " reused outcome")
        else:
            action, origin = "execute", step
            cache[key] = (step, code, output)
        previously_requested.add(task)
        after, _ = view(cache, key, True)
        expected = {"before": before, "execution": action, "exit": code, "after": after, "execution_origin": origin}
        for field, value in expected.items():
            require(row[field], value, step + " " + field)
        require(row["prediction"], expected, step + " prediction")
        require(row["reused_gates"], ["fit"] if action == "reuse" else [], step + " reuse flags")
        require(row["output_from_origin"], output, step + " rounded check output")
        check_views(row["views_after"], active, cache, key, previously_requested, step + " after")
        tally["gate_requests"] += 1
        tally["reused" if action == "reuse" else "executions"] += 1
        tally["exit_1"] += int(code == 1)
    require(dict(tally), record["counts"], "summary counts")
    require(record["expectation_mismatches"], [], "expectation mismatches")
    return f"{tally['gate_requests']} requests, {tally['executions']} executions, {tally['reused']} reuses, {tally['exit_1']} failed check results; fit outputs, input hashes and receipt origins agree."


def rejection_checks(repo, record):
    def wrong_origin(data):
        row = data["observations"][-1]
        row["execution_origin"] = row["prediction"]["execution_origin"] = "baseline"
        for moment in ("views_before", "views_after"):
            for item in row[moment].values():
                item["pass_origin"] = "baseline"

    def wrong_reading(data):
        row = data["observations"][2]
        row["csv_text"] = row["csv_text"].replace("2.2995", "2.2895")
        row["data_sha256"] = digest(row["csv_text"].encode("utf-8"))

    def wrong_output(data):
        data["observations"][2]["output_from_origin"] = "g = 9.45 is outside 9.6 to 10.0"

    tests = (("different passing receipt", wrong_origin), ("changed reading with recomputed hash", wrong_reading),
             ("incorrect rounded fit with same exit", wrong_output))
    accepted = []
    for label, change in tests:
        altered = deepcopy(record)
        change(altered)
        try:
            verify(repo, altered)
        except ValueError:
            accepted.append(label)
        else:
            raise ValueError("unexpectedly accepted: " + label)
    return accepted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--record", type=Path, help="saved JSON; defaults to the handoff record in --repo")
    parser.add_argument("--self-test", action="store_true", help="also test three deliberately altered observations")
    options = parser.parse_args()
    record = json.loads((options.record or options.repo / "evals/results/handoff_audit.json").read_text(encoding="utf-8"))
    print(verify(options.repo, record))
    if options.self_test:
        for label in rejection_checks(options.repo, record):
            print("Rejected " + label)


if __name__ == "__main__":
    main()
