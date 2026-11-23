"""Question-led study briefs with JSON Pointers into the exact public observations."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path


def _indexed(record, array, key="id"):
    index = {}
    for position, row in enumerate(record[array]):
        identity = row[key]
        if identity in index:
            raise ValueError(f"Ambiguous {key} {identity!r} in /{array}")
        index[identity] = (row, f"/{array}/{position}")
    return index


def _observation(label, value, *pointers):
    return {"label": label, "value": value, "pointers": list(pointers)}


def _revisions(record):
    rows = []
    summaries = []
    for label, source, path in [
        (revision, record["revisions"][revision], f"/revisions/{revision}")
        for revision in ("071a348", "89f36ce")
    ] + [("Reference checkout", record["here"], "/here")]:
        missed, total = source["did_not_pass"], source["ran"]
        if missed != len(source["names"]) or not 0 <= missed <= total:
            raise ValueError(f"Inconsistent regression counts in {path}")
        rows.append(_observation(label, f"{missed} of {total} failed or raised an error",
                                 path + "/did_not_pass", path + "/ran", path + "/names"))
        context = f"at {label}" if path != "/here" else "on the reference checkout"
        summaries.append(f"{missed} of {total} {context}")
    return "Tests failed or raised errors in " + ", ".join(summaries) + ".", rows


def _mutations(record):
    caught, total, missed, names = (record[key] for key in ("caught", "faults", "missed", "names"))
    if (caught + len(missed) != total or len(set(names)) != total or len(names) != total
            or len(set(missed)) != len(missed) or not set(missed).issubset(names)):
        raise ValueError("Inconsistent seeded fault names and counts")
    reference = "leases: a lapsed lease can be revived"
    at = names.index(reference)
    rows = [
        _observation("Detected faults", f"{caught} of {total} seeded faults", "/caught", "/faults"),
        _observation("Missed faults", ", ".join(missed) if missed else "None", "/missed"),
        _observation("Expired assignment can be revived", "Missed" if reference in missed else "Detected",
                     f"/names/{at}", "/missed"),
    ]
    return f"The tests detected {caught} of {total} specified faults and missed {len(missed)}.", rows


def _reuse(record):
    indexed = _indexed(record, "rows", "policy")
    policies = [
        ("rerun everything", "Rerun every check"),
        ("TAOS, 12 domain(s) declared", "Each folder tracked separately"),
        ("oracle (knows what every check reads)", "Reference using the folders actually read"),
        ("TAOS, each check hides one folder it reads", "Each check omits one folder"),
    ]
    rows = []
    for policy, label in policies:
        row, path = indexed[policy]
        rows.append(_observation(label, f"{row['executions']} executions, {row['wrong']} outdated reuses",
                                 path + "/policy", path + "/executions", path + "/wrong"))
    all_checks = indexed[policies[0][0]][0]
    tracked = indexed[policies[1][0]][0]
    omitted = indexed[policies[-1][0]][0]
    finding = (f"Across {record['relied_on']} requests after edits, listing the inputs reduced executions "
               f"from {all_checks['executions']} to {tracked['executions']} with {tracked['wrong']} outdated reuses. "
               f"With a folder omitted, {omitted['executions']} checks ran and earlier results were reused "
               f"{omitted['wrong']} times after their inputs changed.")
    rows.insert(0, _observation("Requests after edits", str(record["relied_on"]), "/relied_on"))
    return finding, rows


def _period(case, path, length):
    matches = [(i, period) for i, (measured_length, period) in enumerate(case["rows"])
               if Decimal(measured_length) == length]
    if len(matches) != 1:
        raise ValueError(f"Expected one {length} m pendulum reading at {path}")
    position, period = matches[0]
    return period, f"{path}/rows/{position}"


def _measurement(record):
    indexed = _indexed(record, "cases")
    before, before_path = indexed["baseline"]
    after, after_path = indexed["row-6-1.05"]
    old_period, old_row = _period(before, before_path, Decimal("1.20"))
    new_period, new_row = _period(after, after_path, Decimal("1.20"))
    rows = [_observation("Period of the 1.20 m pendulum", f"{old_period} to {new_period} s", old_row, new_row)]
    for identity, label in [("baseline", "Original fit"), ("row-6-1.05", "After the timing correction"),
                            ("omission-1.02", "All periods increased by 2%, data folder omitted"),
                            ("style", "Only the figure style changed")]:
        row, path = indexed[identity]
        verdict = "passed" if row["fresh_exit"] == 0 else "failed"
        rows.append(_observation(label, f"{row['g']:.4f} ± {row['se']:.4f} m/s² (statistical SE). "
                                 f"Earlier pass {row['retained']}, fresh check {verdict}.",
                                 path + "/id", path + "/g", path + "/se", path + "/retained", path + "/fresh_exit"))
    finding = (f"Changing one period from {old_period} to {new_period} s shifted the estimated gravity "
               f"from {before['g']:.2f} to {after['g']:.2f} m/s². The old pass was marked {after['retained']} and "
               f"the fresh check {'passed' if after['fresh_exit'] == 0 else 'failed'}.")
    return finding, rows


def _model(record):
    indexed = _indexed(record, "cases")
    edit, path = indexed["offsetting-score-corrections"]
    order = record["cell_order"]
    if len(order) != 4 or set(order) != {"tp", "fn", "fp", "tn"}:
        raise ValueError("Missing or ambiguous classification cells")
    rows, changes = [], {}
    for group, label in (("A", "Instrument A"), ("B", "Instrument B"), ("pooled", "Combined readings")):
        old = record["baseline_counts"][group]
        if len(old) != len(order):
            raise ValueError(f"Incomplete baseline confusion table for {group}")
        new = edit["counts"][group]
        tp, fn = order.index("tp"), order.index("fn")
        old_total, new_total = old[tp] + old[fn], new["tp"] + new["fn"]
        delta = 100 * (new["tp"] / new_total - old[tp] / old_total)
        changes[group] = delta
        prefix = f"/baseline_counts/{group}/"
        selected = f"{path}/counts/{group}/"
        change = f"{delta:+g}" if delta else "0"
        rows.append(_observation(label, f"{old[tp]}/{old_total} to {new['tp']}/{new_total} known faults detected "
                                 f"({change} percentage points). Check status: {edit['result_after_consultation'][group]}.",
                                 path + "/id", "/cell_order", prefix + str(tp), prefix + str(fn), selected + "tp", selected + "fn",
                                 f"{path}/result_after_consultation/{group}"))
    control, control_path = indexed["figure-caption"]
    rows.append(_observation("Only the caption changed",
                             f"{len(control['executed'])} checks executed, {len(control['reused'])} reused",
                             control_path + "/id", control_path + "/executed", control_path + "/reused"))
    finding = (f"After offsetting score corrections, sensitivity changed by {changes['A']:+g} percentage "
               f"points for instrument A, {changes['B']:+g} for B and {changes['pooled']:g} for the combined readings.")
    return finding, rows


def _handoff(record):
    indexed = _indexed(record, "observations")
    events = [
        ("baseline", "Original run"), ("style-only", "Only the plot style changed"),
        ("measurement-fails", "Timing correction"), ("new-task-sees-failure", "Another task starts"),
        ("restore-exact-bytes", "Original data restored"), ("same-values-new-bytes", "Same values, new spelling"),
        ("share-respelled-pass", "Another task reads the rewritten data"),
    ]
    counts = record["counts"]
    rows = [_observation("Requests in this history",
                         f"{counts['gate_requests']} requests, {counts['executions']} executions, {counts['reused']} reuses",
                         "/counts/gate_requests", "/counts/executions", "/counts/reused")]
    for identity, label in events:
        row, path = indexed[identity]
        verdict = "passed" if row["exit"] == 0 else "failed"
        action = {"reuse": "reused", "execute": "executed"}[row["execution"]]
        rows.append(_observation(label, f"{row['task']} {action} the check ({verdict}). "
                                 f"Status {row['before']} → {row['after']}. The cited run was {row['execution_origin']}.",
                                 path + "/id", path + "/task", path + "/execution", path + "/exit", path + "/before",
                                 path + "/after", path + "/execution_origin"))
    restored = indexed["restore-exact-bytes"][0]
    correction = indexed["measurement-fails"][0]
    fresh = "passed" if correction["exit"] == 0 else "failed"
    recovery_action = {"reuse": "reused", "execute": "executed"}[restored["execution"]]
    finding = (f"After the correction the old result was {correction['before']}, and the fresh check {fresh}. "
               f"After restoring the original data, the task {recovery_action} the result from the {restored['execution_origin']} run.")
    return finding, rows


def _session(record):
    surfaces = record["surfaces"]
    rows = []
    for key, label in (("compact_status", "Project status"), ("task_capsule", "One task brief"),
                       ("agents_md", "Project instructions")):
        row = surfaces[key]
        prefix = "/surfaces/" + key
        value = f"{row['lines']} lines, {row['bytes']:,} UTF-8 bytes. {row['delivery']}"
        rows.append(_observation(label, value, prefix + "/lines", prefix + "/bytes", prefix + "/delivery"))
    return (f"The brief for one task was {surfaces['task_capsule']['lines']} lines. "
            "The status and project instructions are available separately.", rows)


def study_briefs(records_dir: Path, dataset_by_stem: dict) -> dict:
    """All paths are site-root relative; each observation's pointers resolve within its raw JSON file."""
    specs = {
        "at_revision": (_revisions, "source/raw/docs/METHOD.md", "evidence/#revision-comparison"),
        "mutations": (_mutations, "source/raw/docs/METHOD.md", "evidence/#seeded-faults"),
        "reuse_frontier": (_reuse, "source/raw/evals/reuse_frontier.py", "evidence/#reuse-full"),
        "measurement_audit": (_measurement, "records/measurement-method.md", "evidence/pendulum/"),
        "model_evaluation": (_model, "records/model-evaluation/docs/MODEL_EVALUATION.md", "evidence/model-evaluation/"),
        "session_footprint": (_session, "source/raw/evals/session_footprint.py", "evidence/#session-reading"),
        "handoff_audit": (_handoff, "records/handoff-method.md", "evidence/#handoff-audit"),
    }
    briefs = {}
    for stem, (read, method_path, detail_path) in specs.items():
        dataset = dataset_by_stem[stem]
        raw = (records_dir / (stem + ".json")).read_bytes()
        if dataset["identifier"] != f"evals/results/{stem}.json":
            raise ValueError(f"The dataset identifier does not name {stem}.json")
        if "distribution" in dataset and dataset["distribution"]["sha256"] != hashlib.sha256(raw).hexdigest():
            raise ValueError(f"Catalog digest differs from the recorded bytes for {stem}")
        finding, observations = read(json.loads(raw))
        scope = dataset["description"]
        if stem == "at_revision":
            scope += " Reproduction requires Git and a checkout containing both historical commits. The source ZIP lacks that history."
        if stem == "mutations":
            scope += " The runner requires the unmodified test modules to pass first. One seeded fault tests macOS isolation."
        command = f"python3 evals/{stem}.py"
        if stem in {"measurement_audit", "model_evaluation", "handoff_audit", "session_footprint"}:
            command += " --verify"
        briefs[stem] = dict(question=dataset["name"], finding=finding, method=dataset["measurementTechnique"], scope=scope,
                            observations=observations, test_command=command, method_path=method_path, detail_path=detail_path)
    return briefs
