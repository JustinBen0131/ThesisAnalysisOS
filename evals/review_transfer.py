"""Replay portable review identity checks on public synthetic instrument rows."""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples/model_evaluation"
RECORD = REPO / "evals/results/followups/review-transfer.json"
CASE = "offsetting-score-corrections"
TASK = "RR-1"
QUESTIONS = {
    "sensitivity": "Did instrument A detect at least ¾ of the known faults?",
    "false-alarms": "How many false alarms did instrument A produce at score ≥60?",
}
SUBSETS = {"a-policy": ("a.csv", "policy.json"), "all-policy": ("a.csv", "b.csv", "policy.json")}
VERSIONS = ("current", "changed")
TRANSPORTS = ("terminal-compact", "editor-reformatted", "web-plain-crlf")
MATCH = "The reply matches this task, question and selected sources. The operator evaluates its conclusion."
PROMPT_MARKER = "Cite the source rows or method you actually used.\n"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain_reply(path, reply, transport):
    if transport == "terminal-compact":
        text = json.dumps(reply, ensure_ascii=False, separators=(",", ":")) + "\n"
    elif transport == "editor-reformatted":
        text = json.dumps(reply, ensure_ascii=False, sort_keys=True, indent=4) + "\n"
    else:
        assert transport == "web-plain-crlf"
        text = ("\n" + json.dumps(reply, ensure_ascii=False, indent=2) + "\n").replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    assert json.loads(path.read_bytes()) == reply
    return path


def review_fields(question):
    response = {"uncertainty": "Fictional rows do not estimate performance in service.",
                "next_check": "Recount from the supplied scores and fault labels."}
    if question == "sensitivity":
        return dict(response, finding="contradicted", conclusion="A detected 2 of 4, below ¾.",
                    evidence=["a.csv, A01 to A04", "policy.json, minimum sensitivity"])
    return dict(response, finding="supported", conclusion="A produced 1 false alarm at score ≥60.",
                evidence=["a.csv, A05 to A08", "policy.json, flag threshold"])


def replay(tmp):
    from model_evaluation import independently_count, perturb, read_json, read_samples
    from taos_core import demo, lifecycle, reviews
    from taos_core.paths import Paths
    from taos_core.util import TaosError

    workspace = tmp / "analysis"
    workspace.mkdir()
    attachments = tmp / "supplied"
    attachments.mkdir()
    source_names = SUBSETS["all-policy"]
    for name in source_names:
        shutil.copyfile(EXAMPLE / name, attachments / name)
    design = next(case for case in read_json(EXAMPLE / "predictions.json")["cases"] if case["id"] == CASE)
    assert len(design["edits"]) == 2 and {edit["file"] for edit in design["edits"]} == {"a.csv", "b.csv"}
    perturb(attachments, design["edits"])
    corrected_hashes = {name: digest(attachments / name) for name in source_names}
    policy = read_json(attachments / "policy.json")
    cutoff = policy["flag_if_score_at_least"]
    minimum = Fraction(**policy["minimum_sensitivity"])
    counts = independently_count(read_samples(attachments / "a.csv"), cutoff)
    assert counts == {"tp": 2, "fn": 2, "fp": 1, "tn": 3}
    known_faults = counts["tp"] + counts["fn"]
    assert Fraction(counts["tp"], known_faults) < minimum
    report = "Instrument A detects {} of {} known faults.\n".format(counts["tp"], known_faults)
    (workspace / "report.txt").write_text(report, encoding="utf-8")
    gate_code = "from pathlib import Path; assert Path('report.txt').read_text(encoding='utf-8') == " + repr(report)
    gate = {"name": "report", "command": shlex.join([sys.executable, "-B", "-c", gate_code])}
    home = demo.scratch_home(tmp, workspace=workspace, project="Instrument review replies", prefix="RR", gates=[gate],
                             tasks=[{"title": "Record independent instrument recount",
                                     "done_when": "Sensitivity and false alarms are independently counted"}])
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    def cli(paths, *args):
        command = [sys.executable, "-B", str(home.launcher), "--home", str(paths.home), *map(str, args)]
        result = subprocess.run(command, cwd=tmp, env=environment, capture_output=True, encoding="utf-8", timeout=20)
        return result.returncode, result.stdout or result.stderr

    def success(paths, *args):
        code, output = cli(paths, *args)
        assert code == 0, (args, code, output)
        return output

    success(home, "gate", "run", "--task", TASK, "--agent", "codex")
    success(home, "task", "transition", TASK, "--to", "done", "--agent", "codex", "--reason",
            "Independent row count complete", "--evidence", "report.txt")
    success(home, "task", "accept", TASK, "--by", "human", "--note", "Fixture operator accepts the row count")
    changed = Paths(tmp / "os-changed")
    shutil.copytree(home.home, changed.home)
    success(changed, "task", "evidence", TASK, "--agent", "codex", "--ref", "later verification note",
            "--note", "Checked for duplicate sample IDs")
    records = dict(zip(VERSIONS, (home, changed)))

    def transfer(question, sources):
        args = ["capsule", TASK, "--transfer", question]
        for source in sources:
            args.extend(("--source", source))
        return args

    def issue(paths, question, sources):
        draft = success(paths, *transfer(question, sources))
        assert draft.rstrip("\n") == reviews.transfer_prompt(lifecycle.capsule(paths, TASK), question, sources)
        assert str(tmp) not in draft
        for path in sources:
            assert f"{path.name}  {digest(path)}" in draft
        return json.JSONDecoder().raw_decode(draft.split(PROMPT_MARKER, 1)[1])[0]

    checks = Counter()

    def check(paths, question, sources, reply, expected, group):
        code, output = cli(paths, *transfer(question, sources), "--check-review", reply)
        try:
            result = reviews.check_review(lifecycle.capsule(paths, TASK), question, sources, reply)
            core_match = True
        except TaosError as error:
            result = str(error)
            core_match = False
        cli_match = code == 0
        checks[(group, "cli", cli_match)] += 1
        checks[(group, "core", core_match)] += 1
        assert cli_match == core_match == expected, (reply.name, question, code, output, result)
        assert result in output and (not expected or result == MATCH)
        return {"cli_exit": code, "core_match": core_match, "diagnostic": result}

    def files(subset):
        return [attachments / name for name in SUBSETS[subset]]

    keys = list(product(VERSIONS, QUESTIONS, SUBSETS))
    # Predict a match only when the designed version, question and source labels
    # agree. No packet or request hashes are used to construct this oracle.
    expected = [[claim == target for target in keys] for claim in keys]
    replies = []
    issued = []
    for index, (version, question, subset) in enumerate(keys):
        template = issue(records[version], QUESTIONS[question], files(subset))
        issued.append(template)
        response = dict(template, **review_fields(question))
        replies.append(plain_reply(tmp / f"reply-{index}.json", response, TRANSPORTS[index % len(TRANSPORTS)]))
    distinct_requests = len({row["request_id"] for row in issued})
    distinct_packets = len({row["packet_id"] for row in issued})
    assert distinct_requests == len(keys) and distinct_packets == len(VERSIONS)

    matrix = [
        [check(records[version], QUESTIONS[question], files(subset), reply, expected[row][col], "matrix")
         for col, (version, question, subset) in enumerate(keys)]
        for row, reply in enumerate(replies)
    ]
    diagnostics = Counter(cell["diagnostic"] for row in matrix for cell in row)
    question = QUESTIONS["sensitivity"]
    original = replies[keys.index(("current", "sensitivity", "all-policy"))]
    base_reply = json.loads(original.read_bytes())
    shared = files("all-policy")
    controls = {}

    def control(name, sources, reply, match):
        controls[name] = {"expected_match": match, **check(home, question, sources, reply, match, "control")}

    for mode in TRANSPORTS:
        formatted = plain_reply(tmp / f"{mode}.json", base_reply, mode)
        control(mode, shared, formatted, True)
    control("reordered-sources", list(reversed(shared)), original, True)
    control("omitted-sources", (), original, False)
    source = attachments / "a.csv"
    original_bytes = source.read_bytes()
    shutil.copyfile(EXAMPLE / "a.csv", source)
    assert source.read_bytes() != original_bytes
    changed_source = issue(home, question, shared)
    assert changed_source["packet_id"] == base_reply["packet_id"]
    assert changed_source["request_id"] != base_reply["request_id"]
    control("changed-selected-bytes", shared, original, False)
    source.write_bytes(original_bytes)
    control("exact-source-rewind", shared, original, True)
    caption = attachments / "caption.txt"
    caption.write_text("Illustration one\n", encoding="utf-8")
    assert issue(home, question, shared)["request_id"] == base_reply["request_id"]
    caption.write_text("Illustration two\n", encoding="utf-8")
    control("unshared-file-edit", shared, original, True)
    assert {path.name: digest(path) for path in shared} == corrected_hashes

    no_source = issue(home, question, ())
    uncertain = dict(no_source, finding="uncertain", conclusion="I cannot independently confirm the sensitivity.",
                     evidence=[], uncertainty="No scores or reference labels were supplied.",
                     next_check="Get the labeled rows for A.")
    control("uncertain-without-evidence", (), plain_reply(tmp / "uncertain.json", uncertain, TRANSPORTS[2]), True)
    unsupported = dict(uncertain, finding="supported", conclusion="A meets ¾.")
    control("supported-without-evidence", (), plain_reply(tmp / "unsupported.json", unsupported, TRANSPORTS[0]), False)
    fenced = tmp / "markdown-fenced.json"
    fenced.write_bytes(b"```json\n" + original.read_bytes() + b"```\n")
    control("markdown-fenced-json", shared, fenced, False)

    def acceptance():
        capsule = json.loads(success(home, "capsule", TASK, "--json"))
        record = capsule["task"]["acceptance"]
        standing = next(part["state"] for part in capsule["standing"]["parts"] if part["kind"] == "acceptance")
        return {"record": record, "standing": standing,
                "receipt_bytes": (home.state / "acceptance" / record["receipt"]).read_bytes(),
                "task_bytes": home.tasks_file.read_bytes(), "event_bytes": home.events_file.read_bytes()}

    before = acceptance()
    claimed_detections = 3
    wrong = dict(base_reply, finding="supported", conclusion="A detected 3 of 4 and met the ¾ limit.",
                 next_check="Independently recount the cited rows.")
    control("right-identity-wrong-science", shared, plain_reply(tmp / "wrong-science.json", wrong, TRANSPORTS[1]), True)
    after = acceptance()
    recount = independently_count(read_samples(attachments / "a.csv"), cutoff)
    assert recount == counts and recount["tp"] != claimed_detections
    assert before == after and before["record"]["by"] == "human" and before["standing"] == "holds"

    def match_rows(rows):
        return ["".join("1" if match else "0" for match in row) for row in rows]

    return {
        "question_predeclared": "Can a plain-text reply travel from a terminal to a text editor or a web-style message and still match the exact question and selected sources?",
        "scope": "Real local CLI and core. Local simulation of plain-text formats. Public fictional readings. No model or network calls.",
        "fixture_case": {"id": CASE, "edits": design["edits"], "corrected_source_sha256": corrected_hashes},
        "questions": QUESTIONS, "source_subsets": {name: list(group) for name, group in SUBSETS.items()},
        "matrix_order": [{"record": key[0], "question": key[1], "sources": key[2],
                          "format": TRANSPORTS[index % len(TRANSPORTS)]} for index, key in enumerate(keys)],
        "distinct_requests": distinct_requests, "distinct_task_packets": distinct_packets,
        "matrix_expected_match_bits": match_rows(expected),
        "matrix_cli_exit_rows": [[cell["cli_exit"] for cell in row] for row in matrix],
        "matrix_core_match_bits": match_rows([[cell["core_match"] for cell in row] for row in matrix]),
        "matrix_diagnostics": dict(diagnostics), "controls": controls,
        "wrong_conclusion": {"claimed_detected": claimed_detections, "independently_counted": recount,
                             "known_faults": known_faults, "minimum_sensitivity": str(minimum),
                             "recount_disagreed": True},
        "fixture_human_acceptance": {"standing_before": before["standing"], "standing_after": after["standing"],
                                     "acceptance_record_unchanged": before["record"] == after["record"],
                                     "receipt_bytes_unchanged": before["receipt_bytes"] == after["receipt_bytes"],
                                     "task_bytes_unchanged": before["task_bytes"] == after["task_bytes"],
                                     "event_bytes_unchanged": before["event_bytes"] == after["event_bytes"]},
        "counts": {actor: {group: {"success": checks[(group, actor, True)], "fail": checks[(group, actor, False)]}
                           for group in ("matrix", "control")} for actor in ("cli", "core")},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="rerun and compare against the recorded result")
    mode.add_argument("--output", type=Path, help="write the new result to this path")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(REPO))
    source_files = [Path(__file__).resolve(), REPO / "evals/model_evaluation.py", REPO / "taos",
                    REPO / "taos_core/lifecycle.py", REPO / "taos_core/reviews.py"]
    source_files.extend(EXAMPLE / name for name in (*SUBSETS["all-policy"], "predictions.json"))
    with TemporaryDirectory(prefix="taos-review-transfer-") as temp:
        record = {"schema": "taos-review-transfer-experiment/1", **replay(Path(temp)),
                  "sources": {p.relative_to(REPO).as_posix(): digest(p) for p in source_files}}
    if args.verify:
        if record != json.loads(RECORD.read_text(encoding="utf-8")):
            raise SystemExit("Replay differs from the saved review transfer experiment.")
        print("Verified all matrix pairs, controls and source fingerprints.")
    else:
        output = json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)


if __name__ == "__main__":
    main()
