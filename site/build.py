#!/usr/bin/env python3
"""Build the public page from the repository's own records.

Nothing on the page is typed in twice. The run it steps through is the output
of `./taos demo`, captured when the page is built. Every number is read from
`evals/results/`, and every claim from `docs/CLAIMS.md` with the standing
`evals/claims.py` gives it. The build stops if a recorded run no longer
stands, if the structured demo record disagrees with the walkthrough, or if a link
inside the page leads nowhere.

Each page is written twice from one source: as HTML for a person and as
Markdown for an agent, with `llms.txt`, `claims.json` and `standing.json`
beside them. `standing.json` lists the files the page was built from, by
hash, so the page can ask the repository whether it still holds. `graph.json`
is the record itself as a graph: every claim, every recorded run and the page,
tied to the files each stands on. The record explorer draws those connections.

    python3 site/build.py                         writes ./_site, links to main
    python3 site/build.py --out DIR --ref REVISION --url https://example.org/
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlsplit

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "evals"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))  # support loaders that import the builder by filename

import claims as read_back  # noqa: E402  (evals/claims.py)
import measured  # noqa: E402
import demo_walkthrough  # noqa: E402
from copy_controls import copy_block  # noqa: E402
from hpc_exhibit import DESCRIPTION as HPC_DESCRIPTION, PAGE_TITLE as HPC_TITLE, hpc_markdown, render_hpc, run_trace  # noqa: E402
import hpc_review  # noqa: E402
from hpc_planner import worksheet as pilot_worksheet  # noqa: E402
from first_game import game_markdown, render_game  # noqa: E402
from first_lesson import lesson_markdown, render_lesson  # noqa: E402
from review_practice import practice_markdown, render_practice  # noqa: E402
from taos_core.demo import write as write_terminal_demo  # noqa: E402
from reuse_play import recorded_comparison, reuse_play, timing_observations  # noqa: E402
from visitor_claims import visitor_claim_title  # noqa: E402
from policy_evidence import attach_policy_evidence  # noqa: E402
from research_catalog import research_catalog  # noqa: E402
import agent_guide  # noqa: E402
from study_briefs import study_briefs  # noqa: E402
from transit_exhibit import render_transit_exhibit, render_transit_markdown, transit_transfer  # noqa: E402
from transit_workflow import load_adaptation_record, load_record as load_transit_record  # noqa: E402
from research_notes import write_research_notes  # noqa: E402
from exchange import exchange_html, write_exchange  # noqa: E402
from exchange_result import write_followup  # noqa: E402
from research_feed import write_feed  # noqa: E402
import reading_navigation  # noqa: E402
from source_snapshot import retain_published_archives, write_source_snapshot  # noqa: E402
from release_integrity import protect_pages, verify_homepage_film, write_manifest  # noqa: E402
from verify_research_guide import verify as verify_research_guide  # noqa: E402
from film_player import PUBLIC_MEDIA_DIR, film_files, opening_link, render_player  # noqa: E402
from handoff_exhibit import HANDOFF_METHOD, HANDOFF_RECORD, HANDOFF_RUNNER  # noqa: E402
from handoff_exhibit import handoff_markdown, handoff_section, load_handoff  # noqa: E402
from setting_change_exhibit import SETTING_DOWNLOAD, SETTING_FIXTURE_FILES, SETTING_RECORD, SETTING_SOURCES  # noqa: E402
from setting_change_exhibit import load_setting_change, next_agent_fields  # noqa: E402
from measurement_exhibit import audit_cases_page, audit_section, load_audit  # noqa: E402

from model_evaluation_exhibit import (  # noqa: E402
    MODEL_DOWNLOADS, load_instrument_paths, load_model_evaluation, model_evaluation_html, model_evaluation_markdown, reviewer_materials,
)

NAME = "JustinBen0131/ThesisAnalysisOS"
GITHUB = "https://github.com/" + NAME
STANDS_ON = ["evals/results/at_revision.json", "evals/results/mutations.json", "evals/results/reuse_frontier.json",
             "evals/results/session_footprint.json", "examples/transit/workflow.json",
             "examples/transit/adaptation/workflow.json", "docs/CLAIMS.md",
             "taos_core/demo.py", "taos_core/basis.py", "taos_core/gates.py"]
AUDIT_RECORD = "evals/results/measurement_audit.json"
AUDIT_METHOD = "docs/MEASUREMENT_AUDIT.md"
BOUNDARY_CHECK = "evals/check_measurement_boundaries.py"
AUDIT_DOWNLOADS = {AUDIT_RECORD: "measurement_audit.json", AUDIT_METHOD: "measurement-method.md",
                   BOUNDARY_CHECK: "check_measurement_boundaries.py",
                   "evals/measurement_audit.py": "measurement_audit.py",
                   "evals/review_measurement_audit.py": "review_measurement_audit.py"}
HANDOFF_DOWNLOADS = {HANDOFF_RECORD: "handoff_audit.json", HANDOFF_RUNNER: "handoff_audit.py",
                     "evals/review_handoff_audit.py": "review_handoff_audit.py"}
TRACE_CLAIM = "Reuse by basis relied on no stale result and executed what an oracle would"
SOFTWARE_CITATION = "source/files/CITATION.cff.html"
DESCRIPTION = ("A research operating system for people working with multiple AI agents. The agents share task "
               "ownership, saved checks and the decisions a person still needs to make.")
RUN_NAMES = {"at_revision": "known failures", "mutations": "seeded faults", "reuse_frontier": "reuse experiment",
             "session_footprint": "session reading"}


USES = [
    ("Checks", "A saved pass identifies the inputs the check tested.", "taos_core/gates.py"),
    ("Closing work", "Before a task can close, TAOS verifies its required checks or records an explicit waiver.", "taos_core/lifecycle.py"),
    ("Instructions", "The dated quotation identifies which instruction applied to which tasks.", "taos_core/rules.py"),
    ("Lessons", "The record distinguishes a delivered reminder from a documented repeat of the mistake.", "taos_core/lessons.py"),
    ("Acceptance", "The approval identifies the person who reviewed the work and the version they accepted.", "taos_core/standing.py"),
    ("Handoffs", "The next session receives the previous findings and can check whether they still apply.", "taos_core/handoff.py"),
    ("Changes to the system", "A proposed change includes a prediction that a separate reviewer can compare with the outcome.", "taos_core/changes.py"),
    ("This page", "The build reads the saved measurements. The browser can compare its source files with the current versions.", "site/build.py"),
]

RESEARCH_QUESTIONS = [
    ("approval", "Which version did the reviewer approve?",
     "A reviewer accepts an analysis. In the version-change test, a file is edited and its check passes again. "
     "The earlier approval stays with the version the reviewer saw.",
     "The edited task has a passing check and needs its own human approval. The test records the reviewer accepting the new version.",
     "taos_core/tasks.py", "Approval code", "tests/test_standing.py", "Version-change test"),
    ("instruction", "Which instruction applied when the analysis ran?",
     "A calibration reference changes from A to B. The date test retrieves A for a January run and B for a February run.",
     "This reconstructs the instructions recorded for that task and date. The analysis log can show which reference was used.",
     "taos_core/rules.py", "Instruction lookup", "tests/test_counterexamples.py", "Two-date test"),
    ("control", "Did a proposed change meet its prediction?",
     "Record a predicted range and a control before changing a procedure. In the grading test, a result in range "
     "with a shifted control receives the verdict CONTROL_MOVED.",
     "A grader can name the source of a measurement. Reproducing its value requires the original observations.",
     "taos_core/changes.py", "Scoring rules", "tests/test_science.py", "Control-change test"),
]

ANSWERS = [
    ("holds", "The saved result still applies to the recorded inputs or instructions."),
    ("fails", "Running the check on the current inputs produced a failure."),
    ("stale", "A recorded input or instruction changed. The earlier result needs a fresh check or review."),
    ("unknown", "The available evidence is insufficient to establish whether the earlier result applies."),
]

LINEAGE = [
    ("Truth maintenance", "A system links a conclusion to its assumptions and revises it when an assumption changes.",
     "Doyle 1979; de Kleer 1986"),
    ("Build systems", "A build tool tracks inputs to each output and reruns affected steps after an edit.",
     "Mokhov, Mitchell and Peyton Jones 2018"),
    ("Temporal databases", "A database can preserve both when a rule applied and when someone entered it.", "Snodgrass and Ahn 1985"),
    ("Provenance", "A provenance record links an output to its inputs and the work that produced it.", "W3C PROV-DM 2013"),
    ("Hermetic builds", "An isolated build limits a step to its declared inputs.", "Bazel sandboxing; the Nix build sandbox"),
]

LIMITS = [
    "These tests measure software behavior. The effect on research quality was outside their scope.",
    "The reuse experiment used one synthetic workload on one laptop. The time saved depends on how much each skipped check costs.",
    "A check with access to the workspace can read inputs its author forgot to list. Restricting it to the listed inputs exposes omissions and takes time on each run.",
    "On macOS, isolation also blocks the network and the rest of the workspace. On other platforms the run record reports those restrictions as open.",
]

esc = html.escape


def inline(text: str) -> str:
    """The little Markdown a table cell uses: code, bold, links."""
    out = esc(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)


def chip(state: str, label: Optional[str] = None) -> str:
    return '<span class="chip {0}"><i aria-hidden="true"></i>{1}</span>'.format(esc(state), esc(label or state))


# ---------------------------------------------------------------- what the page is built from

def git(*words: str) -> str:
    done = subprocess.run(["git"] + list(words), cwd=str(REPO), capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def blob(path: Path) -> str:
    """The hash git gives this file's bytes, so the page can be compared with the repository without git."""
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def recorded_runs() -> Dict[str, Any]:
    runs = {}
    for name in read_back.RUNS:
        run = read_back.recorded(name)
        verdict = measured.standing(run) if run is not None else {"state": "unknown", "reason": "no recorded run"}
        if verdict["state"] != "holds":
            raise SystemExit("evals/results/{0}.json is {1}: {2}. Run evals/{0}.py --write, then build again.".format(
                name, verdict["state"], verdict["reason"]))
        runs[name] = run
    return runs




WORD = re.compile(r"^(\s+)(holds|stale|fails|unknown|ok|held|FAIL)(\s+)")
SHADE = {"ok": "holds", "held": "holds", "FAIL": "fails"}


def terminal(lines: List[str]) -> str:
    out = []
    for line in lines:
        if line.startswith("$ "):
            out.append('<span class="cmd"><b aria-hidden="true">$</b> {0}</span>'.format(esc(line[2:])))
        elif line.startswith("    "):
            found = WORD.match(line)
            if found:
                word = found.group(2)
                out.append('<span class="out"><em class="{0}">{1}</em>{2}{3}</span>'.format(
                    SHADE.get(word, word), esc(word), found.group(3), esc(line[found.end():])))
            else:
                out.append('<span class="out">{0}</span>'.format(esc(line.strip())))
        elif line.strip():
            out.append('<span class="say">{0}</span>'.format(esc(line)))
    return "".join(out)


def claims_file() -> List[Dict[str, Any]]:
    """docs/CLAIMS.md as sections of table rows and bullets, in order."""
    sections: List[Dict[str, Any]] = []
    for line in (REPO / "docs" / "CLAIMS.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            sections.append({"title": line[3:].strip(), "head": None, "rows": [], "bullets": []})
        elif not sections:
            continue
        elif line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) != 4 or not cells[0].strip("-: "):
                continue
            if sections[-1]["head"] is None:
                sections[-1]["head"] = cells
            else:
                sections[-1]["rows"].append(cells)
        elif line.startswith("- "):
            sections[-1]["bullets"].append(line[2:].strip())
        elif line.startswith("  ") and line.strip() and sections[-1]["bullets"]:
            sections[-1]["bullets"][-1] += " " + line.strip()
    return [section for section in sections if section["rows"] or section["bullets"]]


def home_of(token: str, code: Dict[str, str], tests: Dict[str, str]) -> Optional[str]:
    """The repository file a name in backticks lives in, or None when it names no file."""
    words = token.split()
    if not words or token.startswith(".taos/"):
        return None
    if words[0] in ("python3", "./taos", "taos"):
        return next((word for word in words if word.endswith(".py") and (REPO / word).is_file()), None)
    if "::" in token:
        token = token.partition("::")[0]
    if "/" in token or token.endswith((".py", ".md", ".json")):
        return token if (REPO / token).is_file() else None
    if token.startswith(("test_", "Test")):
        return next(("tests/" + name for name, text in tests.items() if read_back.defined(token, text)), None)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.]*", token):
        return None
    owner, _, name = token.rpartition(".")
    if not owner:
        return next(("taos_core/" + file for file, text in code.items() if read_back.defined(name, text)), None)
    if owner + ".py" in code:
        return "taos_core/" + owner + ".py"
    return next(("taos_core/" + file for file, text in code.items() if read_back.defined(owner, text)), None)


def record_graph(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """The repository's own record as a graph, for the picture on the front page and for `graph.json`.

    A node is a file, a recorded run, a claim or the page. An edge runs from a record to something it stands on.
    The claims are the rows `evals/claims.py` answers, in its order: a measured row stands on its recorded run and
    the run on the files it was measured on, a tested row on the files that hold the code and the test it names.
    """
    code, tests = read_back.sources("taos_core"), read_back.sources("tests")
    suite = sorted("tests/" + name for name in tests)
    measured_on = {name: sorted(ctx["runs"][name]["measured_on"]["files"]["files"]) for name in read_back.RUNS}
    rows: List[Tuple[str, int, List[str], Optional[str]]] = []
    section, run_name = -1, read_back.RUNS[0]
    for line in read_back.CLAIMS.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section += 1
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not line.startswith("|") or len(cells) != 4 or not cells[0].strip("-: ") or cells[3] == "Status":
            continue
        claim, what, how, status = cells
        if re.fullmatch(r"\d+ tests", what):
            rows.append((claim, section, suite, None))
        elif status.startswith("measured"):
            run_name = next((name for name in read_back.RUNS if "evals/{0}.py".format(name) in how), run_name)
            rows.append((claim, section, [], run_name))
        elif status.startswith("tested"):
            named = {found for token in read_back.TICKED.findall(what + " " + how) for found in [home_of(token, code, tests)] if found}
            rows.append((claim, section, sorted(named), None))
    front = [row["claim"] for row in ctx["rows"] if row["where"] == "README.md"]
    repeats: List[Tuple[List[str], Optional[str]]] = [(suite, None), ([], "at_revision"), ([], "mutations")] + [([], "reuse_frontier")] * 3
    if [row["claim"] for row in ctx["rows"] if row["where"] != "README.md"] != [row[0] for row in rows] or len(front) != len(repeats):
        raise SystemExit("the picture of the record no longer mirrors evals/claims.py; update record_graph in site/build.py")
    rows += [(claim, section + 1, ["README.md"] + on_files, on_run) for claim, (on_files, on_run) in zip(front, repeats)]
    alone = [row[0] for row in rows if not row[2] and not row[3]]
    if alone:
        raise SystemExit("a claim in the picture stands on nothing, so it could never go stale: {0}".format(alone[0]))
    files = sorted({path for path in STANDS_ON if not path.startswith("evals/results/")}
                   | {path for row in rows for path in row[2]} | {path for names in measured_on.values() for path in names})
    nodes: List[Dict[str, Any]] = [
        {"k": "f", "l": path, "g": path.split("/")[0] if path.split("/")[0] in ("taos_core", "tests") else "other"} for path in files]
    at = {path: index for index, path in enumerate(files)}
    run_at = {}
    for name in read_back.RUNS:
        run_at[name] = len(nodes)
        nodes.append({"k": "r", "l": "evals/results/{0}.json".format(name), "t": RUN_NAMES[name]})
    edges = [[run_at[name], at[path]] for name in read_back.RUNS for path in measured_on[name]]
    groups = {number: rank for rank, number in enumerate(sorted({row[1] for row in rows}))}
    for claim, number, on_files, on_run in rows:
        edges += [[len(nodes), at[path]] for path in on_files] + ([[len(nodes), run_at[on_run]]] if on_run else [])
        nodes.append({"k": "c", "l": re.sub(r"[`*]", "", claim), "g": min(groups[number], 4)})
    edges += [[len(nodes), run_at[Path(path).stem] if path.startswith("evals/results/") else at[path]] for path in STANDS_ON]
    nodes.append({"k": "p", "l": "this page"})
    # Append the audit to preserve existing graph addresses.
    page_at = len(nodes) - 1
    by_path = {node["l"]: index for index, node in enumerate(nodes) if node["k"] in ("f", "r")}
    # Append each experiment in order to keep earlier graph addresses stable.
    exhibits = [
        ("audit", AUDIT_RECORD, "measurement audit",
         {AUDIT_METHOD, "evals/review_measurement_audit.py", "site/measurement_exhibit.py",
          "site/plot_pendulum.py", "site/assets/pendulum-sensitivity.png", "site/build.py",
          "site/visitor_claims.py", "site/film_player.py", "site/assets/mind.js", "site/assets/style.css", "site/assets/site.js", "site/assets/record-opening.webp", "site/assets/architecture-shell.webp"}),
        ("handoff", HANDOFF_RECORD, "handoff audit", {HANDOFF_METHOD, "site/handoff_exhibit.py", "evals/review_handoff_audit.py"}),
        ("model_evaluation", "evals/results/model_evaluation.json", "instrument comparison",
         {"docs/MODEL_EVALUATION.md", "evals/review_model_evaluation.py", "evals/model_evaluation.schema.json",
          "site/model_evaluation_exhibit.py", "site/source_snapshot.py"}),
    ]
    for key, record, title, page_sources in exhibits:
        sources = ctx[key]["sources"]
        for path in sorted(set(sources) | page_sources):
            if path not in by_path:
                by_path[path] = len(nodes)
                group = path.split("/")[0]
                nodes.append({"k": "f", "l": path, "g": group if group in ("taos_core", "tests") else "other"})
        run_index = len(nodes)
        nodes.append({"k": "r", "l": record, "t": title})
        edges.extend([run_index, by_path[path]] for path in sorted(sources))
        edges.append([page_at, run_index])
        edges.extend([page_at, by_path[path]] for path in sorted(page_sources))
    # Keep the numeric addresses of existing nodes stable when adding page-only sources.
    for path in ("site/research_catalog.py", BOUNDARY_CHECK, "site/agent_guide.py", "site/study_briefs.py",
                 "site/research_notes.py", "site/exchange.py", "site/verify_research_guide.py",
                 "site/research_feed.py", "site/exchange_result.py", "site/policy_evidence.py", "evals/replay_instrument_imbalance.py",
                 "evals/results/followups/instrument-imbalance.json",
                 "site/reuse_play.py", "site/assets/reuse.js", "site/assets/reuse.css", "site/demo_walkthrough.py",
                 "docs/opener.py", "docs/opener.svg", "site/copy_controls.py", "site/first_game.py",
                 "site/assets/first-game.js", "site/assets/first-game.css", "site/first_lesson.py",
                 "site/assets/first-lesson.js", "site/assets/first-lesson.css", "site/assets/theme.css", "site/assets/theme.js",
                 "site/review_practice.py", "site/assets/review-practice.css", "site/assets/review-practice.js",
                 "site/home_reading.html", "site/visitor_header.html", "site/next_agent.html", "site/assets/visitor.css",
                 "site/decision.html", "site/decision.md", "site/assets/living-brain.js",
                 "site/assets/living-brain.css", "site/assets/real-decisions.js", "site/assets/real-decisions.css",
                 "site/assets/journey.css", "site/assets/report-story.js", *SETTING_SOURCES):
        edges.append([page_at, len(nodes)])
        nodes.append({"k": "f", "l": path, "g": "other"})
    correction = next(row for row in ctx["model_evaluation"]["cases"] if row["id"] == "offsetting-score-corrections")["counts"]
    group, pool = correction["A"], correction["pooled"]
    original_hits = dict(zip(ctx["model_evaluation"]["cell_order"], ctx["model_evaluation"]["baseline_counts"]["A"]))["tp"]
    trials = {row["id"]: row for row in ctx["audit"]["cases"]}
    handoff = ctx["handoff"]["counts"]
    findings = {
        "model_evaluation": f'Instrument A caught {group["tp"]} of {group["tp"] + group["fn"]} faults, down from {original_hits}. '
                            f'Together, the instruments still caught {pool["tp"]} of {pool["tp"] + pool["fn"]}.',
        "measurement_audit": f'Correcting one timing moved the gravity estimate from {trials["baseline"]["g"]:.2f} '
                             f'to {trials["row-6-1.05"]["g"]:.2f} m/s².',
        "handoff_audit": f'Three tasks requested the same fit {handoff["gate_requests"]} times. '
                         f'They could reuse an earlier pass {handoff["reused"]} times.',
        "reuse_frontier": f'Listing the files each check used cut repeat runs from {ctx["everything"]["executions"]} '
                          f'to {ctx["finest"]["executions"]} in this experiment.',
        "mutations": f'The tests caught {ctx["caught"]} of {ctx["faults"]} deliberately introduced errors.',
        "at_revision": f'{ctx["cases_pass"]} of {ctx["cases"]} checks passed on this version.',
        "session_footprint": f'The task brief in this demo contained {ctx["runs"]["session_footprint"]["surfaces"]["task_capsule"]["bytes"]:,} UTF-8 bytes.',
    }
    for node in nodes:
        if node["k"] == "r":
            node["finding"] = findings[Path(node["l"]).stem]
            node["href"] = "records/" + Path(node["l"]).name
            node["sha256"] = hashlib.sha256((REPO / node["l"]).read_bytes()).hexdigest()
        elif node["k"] == "c":
            node["t"] = visitor_claim_title(node["l"])
            if node["l"].startswith("A check marked isolated"):
                node["finding"] = "The check can change its copies. The original files stay untouched."
    return attach_policy_evidence({"nodes": nodes, "edges": edges}, REPO)


def pendulum_traversal(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Connect two recorded experiments through the exact bytes of their shared edit."""
    graph = ctx["graph"]
    positions = {node["l"]: i for i, node in enumerate(graph["nodes"]) if node["k"] in ("f", "r")}
    csv = "examples/measurement/data/swings.csv"
    measurement, handoff = ctx["audit"], ctx["handoff"]

    def locate(record: Dict[str, Any], collection: str, case_id: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
        matches = [(i, row) for i, row in enumerate(record[collection]) if row["id"] == case_id]
        if len(matches) != 1:
            raise SystemExit(f"Expected one {case_id!r} in {collection}, found {len(matches)}")
        i, row = matches[0]
        return row, {"id": case_id, "pointer": f"/{collection}/{i}"}

    before, before_ref = locate(measurement, "cases", "baseline")
    after, after_ref = locate(measurement, "cases", "row-6-1.05")
    sender, sender_ref = locate(handoff, "observations", "measurement-fails")
    receiver, receiver_ref = locate(handoff, "observations", "new-task-sees-failure")
    if not (measurement["sources"][csv] == handoff["sources"][csv] == before["data_sha256_after"] == after["data_sha256_before"]
            and after["data_sha256_before"] != after["data_sha256_after"] == sender["data_sha256"] == receiver["data_sha256"]
            and after["fresh_output"] == sender["output_from_origin"] == receiver["output_from_origin"]
            and before["fresh_exit"] == 0 and after["fresh_exit"] == sender["exit"] == receiver["exit"] == 1
            and (sender["actor_label"], receiver["actor_label"], receiver["before"], receiver["execution"]) ==
                ("claude", "codex", "fails", "execute")
            and all([positions[path], positions[csv]] in graph["edges"] for path in (AUDIT_RECORD, HANDOFF_RECORD))):
        raise SystemExit("The measurement and handoff records no longer document the same pendulum correction.")
    instrument_path = "evals/results/model_evaluation.json"
    instrument_node = positions[instrument_path]
    instrument = ctx["model_evaluation"]
    recorded_inputs = instrument["sources"]
    graph_inputs = {graph["nodes"][dependency]["l"] for run, dependency in graph["edges"] if run == instrument_node}
    sensor_files = ["examples/model_evaluation/a.csv", "examples/model_evaluation/b.csv"]
    if (graph_inputs != set(recorded_inputs) or csv in recorded_inputs or not instrument["cases"]
            or not set(sensor_files).issubset(recorded_inputs)
            or any(case["before_sha256"].get(Path(path).name) != recorded_inputs[path]
                   for path in sensor_files for case in instrument["cases"])):
        raise SystemExit("The instrument comparison's recorded inputs no longer support the pendulum contrast.")
    return {
        "question": "Which recorded checks used the corrected swing timing, and what did the next task see?",
        "scope": "One edit in two saved experiments. The handoff used scripted actor labels.",
        "changed_input": {"path": csv, "node": positions[csv]},
        "runs": {
            "measurement": {"path": AUDIT_RECORD, "node": positions[AUDIT_RECORD],
                            "rows": {"before": before_ref, "after": after_ref}},
            "handoff": {"path": HANDOFF_RECORD, "node": positions[HANDOFF_RECORD],
                        "rows": {"sender": sender_ref, "receiver": receiver_ref}},
        },
        "contrast": {"path": instrument_path, "node": instrument_node, "sources_pointer": "/sources",
                     "instrument_data": sensor_files,
                     "scope": "The swing CSV edit touched none of this run's recorded inputs. "
                              "The pendulum handoff executed only the pendulum fit."},
    }


def gather(ref: str) -> Dict[str, Any]:
    runs = recorded_runs()
    rows = read_back.check()
    not_holding = [row for row in rows if row["state"] != "holds"]
    if not_holding:
        raise SystemExit("a claim does not hold, so the page would say something the code does not: {0} ({1})".format(
            not_holding[0]["claim"], not_holding[0]["reason"]))
    reuse = runs["reuse_frontier"]
    finest, aged, hidden, alone, refused = read_back.frontier(reuse)
    by_policy = {row["policy"]: row for row in reuse["rows"]}
    at = runs["at_revision"]
    first_release = sorted(at["revisions"].items(), key=lambda item: -item[1]["did_not_pass"])[0]
    demo_record, capsule = demo_walkthrough.capture_review_session(REPO)
    ctx = {
        "ref": ref, "revision": git("rev-parse", "HEAD") or "unknown",
        "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        "runs": runs, "rows": rows, "demo_record": demo_record, "successor_capsule": capsule, "sections": claims_file(),
        "reuse": reuse, "finest": finest, "aged": aged, "hidden": hidden, "alone": alone, "refused": refused,
        "everything": by_policy["rerun everything"],
        "oracle": next(row for row in reuse["rows"] if row["policy"].startswith("oracle")),
        "cases": at["here"]["ran"], "cases_pass": at["here"]["ran"] - at["here"]["did_not_pass"],
        "first_release": first_release[0], "first_release_failed": first_release[1]["did_not_pass"],
        "faults": runs["mutations"]["faults"], "caught": runs["mutations"]["caught"],
        "audit": load_audit(REPO),
        "handoff": load_handoff(REPO),
        "setting_change": load_setting_change(REPO),
        "model_evaluation": load_model_evaluation(REPO),
        "instrument_paths": load_instrument_paths(REPO),
        "decisions": agent_guide.decision_readings(REPO, RESEARCH_QUESTIONS),
    }
    ctx["chapters"] = demo_walkthrough.chapters(ctx["demo_record"], ctx["audit"])
    graph = ctx["graph"] = record_graph(ctx)
    # Compare the same transitive inputs in the live footer that the graph draws.
    inputs: Dict[int, List[int]] = {}
    for record, dependency in graph["edges"]:
        inputs.setdefault(record, []).append(dependency)
    page = next(i for i, node in enumerate(graph["nodes"]) if node["k"] == "p")
    seen = set()
    queue = list(inputs[page])
    while queue:
        index = queue.pop()
        if index not in seen:
            seen.add(index)
            queue.extend(inputs.get(index, []))
    paths = sorted(graph["nodes"][i]["l"] for i in seen if graph["nodes"][i]["k"] in ("r", "f"))
    ctx["stands_on"] = [{"path": path, "blob": blob(REPO / path)} for path in paths]
    return ctx


# ---------------------------------------------------------------- the page for a person

PAGE_DESCRIPTIONS = {
    "decision/": "Choose whether to build on a saved result, then trace the instrument setting that changed.",
    "record.html": "Explore which files and checks support a project result and follow a rule back to its source.",
    "hpc/": HPC_DESCRIPTION,
    "evidence/": "Compare recorded experiments on stale results, independent checks and handoffs. Each study includes its data and method.",
    "evidence/pendulum/": "Inspect the readings, fitted values and check output for each of 36 pendulum cases.",
    "evidence/model-evaluation/": "Trace how two score corrections moved detection between instruments while leaving the combined score unchanged.",
    "exchange/": "Follow research questions and replies to their data. Check each cited observation against a downloadable record.",
    "workflows/transit/": "Follow two shifts as a transit operator corrects a bus report and passes the counting rule to the next shift.",
    "workflows/review/": "Practise reviewing a pendulum result and prepare the evidence a second reader needs to check it.",
    "workflows/everyday/": "A flight time changes. Decide which travel plans to check and which ones you can still use.",
    "404.html": "Find the research homepage, its evidence and the guide for AI agents.",
}


SHELL = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<meta name="description" content="$description">
<meta property="og:title" content="$title">
<meta property="og:description" content="$description">
<meta property="og:type" content="website">
$card<meta name="theme-color" content="#f5f2ea">
$canonical<link rel="stylesheet" href="${root}assets/style.css">
$reuse_styles
<link rel="stylesheet" href="${root}assets/theme.css">
$visitor_styles
<script src="${root}assets/theme.js"></script>
<link rel="license" href="${root}license.txt">
<link rel="icon" href="${root}assets/favicon.svg" type="image/svg+xml">
$markdown_head
<link rel="describedby" type="application/json" href="${root}research-catalog.json" title="Research datasets and evidence">
<link rel="describedby" type="text/plain" href="${root}llms.txt" title="Research guide for AI agents">
<link rel="alternate" type="application/feed+json" href="${root}exchange/feed.json" title="Research questions and replies">
${study_links}
<script type="application/ld+json">$linked</script>
</head>
<body class="$page_class">
<a class="skip" href="#main">Skip to the content</a>
$header
<main id="main">
$body
</main>
<footer class="foot"><div class="wrap">
<p><a href="${root}source/">Source for this build · <code>$short</code></a> · $built UTC</p>
$footer_appearance
<p id="standing" data-src="${root}standing.json"><span class="lead-in">Comparison with public main</span> $neutral
<span class="nojs">Enable JavaScript to compare the source files.</span></p>
<p class="small links"><a href="$github">Repository</a>$agent_footer$markdown_footer &middot;
<a rel="license" href="${root}license.txt">Apache License 2.0</a></p>
$measurement_note
</div></footer>
<script src="${root}assets/site.js" defer></script>
${scripts}${analytics}</body>
</html>
""")


def shell(ctx: Dict[str, Any], root: str, title: str, body: str, url: str, path: str, scripts: str = "",
          *, dataset: Optional[dict] = None) -> str:
    linked = {"@context": "https://schema.org", "@type": "SoftwareSourceCode", "name": "ThesisAnalysisOS",
              "description": DESCRIPTION, "codeRepository": GITHUB, "programmingLanguage": "Python",
              "license": GITHUB + "/blob/main/LICENSE",
              "subjectOf": {"@type": "DataCatalog", "@id": root + "research-catalog.json"},
              "citation": root + SOFTWARE_CITATION}
    study_links = ""
    if dataset:
        linked = {"@context": ["https://schema.org", {"@base": root}], **dataset}
        record = Path(dataset["identifier"]).name
        study_links = (f'<link rel="item" type="application/json" href="{root}records/{esc(record)}">\n'
                       '<link rel="describedby" type="application/json" href="observations.json" title="Recorded comparisons">')
    card = '<meta name="twitter:card" content="summary">\n' if not url else (
        '<meta property="og:image" content="{0}assets/social.png">\n<meta property="og:image:width" content="1200">\n'
        '<meta property="og:image:height" content="630">\n<meta name="twitter:card" content="summary_large_image">\n').format(esc(url))
    styles = {"": ("journey", "reuse", "first-lesson"), "decision/": ("journey", "real-decisions"),
              "record.html": ("journey",),
              "workflows/transit/": ("transit",),
              "workflows/review/": ("review-practice",), "workflows/everyday/": ("first-game",),
              "hpc/": ("hpc", "hpc-planner", "hpc-review")}.get(path, ())
    enhancements = [asset for asset in styles if asset not in ("transit", "reuse", "journey")]
    markdown_name = "record.md" if path == "record.html" else "index.md"
    count_visits = ctx.get("public_analytics") and path != "404.html"

    if path in ("", "decision/"):
        exercise = Template((HERE / "next_agent.html").read_text(encoding="utf-8"))
        cases = "#decisions" if path else "decision/#decisions"
        body = body.replace("<!--next-agent-->", exercise.substitute(
            root=root, cases=cases, title_tag="h1" if path else "h2",
            **next_agent_fields(ctx["setting_change"], root, lambda name: source(ctx, name))))

    if path == "hpc/":
        body = '<nav class="story-return" aria-label="Return to the homepage"><a href="../">← Back to the homepage</a></nav>' + body
    page_class = "home" if path in ("", "record.html") else "document"
    if path and path != "404.html":
        body += (f'<nav class="reading-onward" aria-label="Continue exploring">'
                 f'<a href="{root}">Home</a><a href="{root}#run">Try it on your own project</a></nav>')
    if path:
        title = title.removesuffix(" · ThesisAnalysisOS").removesuffix(": ThesisAnalysisOS") + " · ThesisAnalysisOS"
    return SHELL.substitute(
        page_class=page_class + " visitor-page", card=card, title=esc(title), header=reading_navigation.header(root, path),
        visitor_styles=f'<link rel="stylesheet" href="{root}assets/visitor.css">',
        footer_appearance=reading_navigation.APPEARANCE,
        measurement_note=('<details class="visit-counts"><summary>How visits are counted</summary>'
                          '<p>We count actions such as starting an example or opening its evidence. Each page view '
                          'gets a fresh random ID. The report records the type of page, how you arrived, a broad '
                          'screen-size category, and which actions you took. Your research questions and the contents '
                          'of files you open stay in your browser. Global Privacy Control or Do Not Track turns these '
                          'counts off.</p></details>' if count_visits else ""),
        description=esc(dataset["abstract"] if dataset else PAGE_DESCRIPTIONS.get(path, DESCRIPTION)),
        root=root, github=GITHUB, body=body,
        study_links=study_links,
        markdown_head=(f'<link rel="alternate" type="text/markdown" href="{markdown_name}" title="This page as Markdown">'
                       if path != "404.html" else ""),
        markdown_footer=(f' &middot; <a href="{markdown_name}">This page as Markdown</a>' if path != "404.html" else ""),
        reuse_styles="\n".join(
            [f'<link rel="stylesheet" href="{esc(root)}assets/{asset}.css">' for asset in styles] +
            [f'<script defer src="{esc(root)}assets/{asset}.js"></script>' for asset in enhancements]),
        analytics=(f'<script defer src="{esc(root)}assets/interactions.js" data-release="{esc(ctx["revision"][:12])}" '
                   """data-cf-beacon='{"token":"4d73a9ec7d20404a82e7a8e2f480a27f"}'></script>\n"""
                   if count_visits else ""),
        canonical='<link rel="canonical" href="{0}">\n'.format(esc(url + path)) if url else "",
        linked=json.dumps(linked).replace("</", "<\\/"), revision=esc(ctx["revision"]), short=esc(ctx["revision"][:7]),
        built=esc(ctx["built"]), neutral=chip("unknown", "not asked yet"), scripts=scripts,
        agent_footer=f' &middot; <a class="agent-entrance" href="{esc(root)}llms.txt">Guide for AI agents</a>')


def source(ctx: Dict[str, Any], path: str, label: Optional[str] = None) -> str:
    return '<a class="src" href="{0}/blob/{1}/{2}"><code>{3}</code></a>'.format(GITHUB, esc(ctx["ref"]), esc(path), esc(label or path))


def reuse_explanation(ctx: Dict[str, Any]) -> Dict[str, str]:
    run = ctx["reuse"]
    return {
        "title": "Which checks need to run after one file changes?",
        "setup": ("In a synthetic workspace, {checks} checks each read two folders. After the starting runs, "
                  "we edited one file at a time and requested each check result after every edit. "
                  "That made {relied_on} requests across {edits} edits.").format(**run),
        "saving": "{0} repeat runs avoided".format(ctx["everything"]["executions"] - ctx["finest"]["executions"]),
        "comparison": ("Running every check after every edit would take {0} runs. When each check listed both folders "
                       "it read, TAOS ran {1} checks and used {2} stale results.").format(
                           ctx["everything"]["executions"], ctx["finest"]["executions"], ctx["finest"]["wrong"]),
        "omission": ("When each check listed only one of the two folders it read, TAOS ran {0} checks. "
                     "In {1} of {2} uses, a check's input had changed since its last run. An old result "
                     "used again after another edit counted again.").format(
                         ctx["hidden"]["executions"], ctx["hidden"]["wrong"], run["relied_on"]),
    }


def bars(ctx: Dict[str, Any]) -> str:
    aged = [("Rerun after {0} requests".format(row["policy"].split()[4]), row) for row in ctx["aged"]]
    shown = ([("Rerun everything, every time", ctx["everything"])] + aged
             + [("Reuse if all listed inputs match", ctx["finest"]), ("An oracle that knows what each check reads", ctx["oracle"]),
                ("Reuse with one input missing from each list", ctx["hidden"])])
    most_run = max(row["executions"] for _, row in shown)
    most_wrong = max(row["wrong"] for _, row in shown) or 1
    lines = []
    for label, row in shown:
        mark = ' class="ours"' if row is ctx["finest"] else ""
        lines.append(
            '<tr{0}><th scope="row">{1}</th>'
            '<td><span class="metric-label" aria-hidden="true">Checks executed</span><span class="bar run" style="width:{2:.1f}%"></span><span class="n">{3}</span></td>'
            '<td><span class="metric-label" aria-hidden="true">Stale results relied on</span>{4}<span class="n{6}">{5}</span></td></tr>'.format(
                mark, esc(label), 100.0 * row["executions"] / most_run, row["executions"],
                '<span class="bar wrong" style="width:{0:.1f}%"></span>'.format(100.0 * row["wrong"] / most_wrong) if row["wrong"] else "",
                row["wrong"], " zero" if row["wrong"] == 0 else ""))
    return ('<table class="bars"><thead><tr><th scope="col">Policy</th><th scope="col">Checks executed</th>'
            '<th scope="col">Stale results relied on</th></tr></thead><tbody>{0}</tbody></table>').format("".join(lines))


def home(ctx: Dict[str, Any]) -> str:
    chapters = ctx["chapters"]
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    messages = [body.strip() for body in re.findall(r"^```[^\n]*\n(.*?)^```[ \t]*$", readme, re.M | re.S)
                if body.lstrip().startswith("Read BOOTSTRAP.md")]
    if len(messages) != 1:
        raise ValueError("The setup example needs one first message from the README.")
    steps = []
    for position, scene in enumerate(chapters, 1):
        facts = "".join(f'<div><dt>{esc(label)}</dt> <dd>{esc(value)}</dd></div>' for label, value in scene.facts)
        extra = demo_walkthrough.comparison_html(scene.comparisons) if scene.comparisons else ""
        steps.append(
            f'<article class="step demo-scene" id="{scene.anchor}" data-short="{esc(scene.short)}">'
            f'<div class="tell"><p class="count">Step {position} of {len(chapters)}</p><h3>{esc(scene.title)}</h3>'
            f'<p class="step-story">{esc(scene.story)}</p></div>'
            f'<dl class="demo-facts" aria-label="Observed in this run">{facts}</dl>{extra}'
            '<details class="demo-proof"><summary>Show the commands and results</summary>'
            f'<div class="term" role="group" aria-label="Recorded commands and output"><pre>{terminal(scene.lines)}</pre></div>'
            f'<p class="small source-link">{source(ctx, scene.code, "Read the implementation")}</p></details></article>')
    reuse = ctx["reuse"]
    service = ctx["service_report"]
    source_readings = "".join(
        f'<li><h3>{esc(question)}</h3><p>{esc(example)}</p><p><a href="{esc(code)}">{esc(code_label)}</a> · '
        f'<a href="{esc(test)}">{esc(test_label)}</a></p></li>'
        for (question, example, _limit, code, code_label, test, test_label), _packet in ctx["decisions"])
    return Template((HERE / "home_reading.html").read_text(encoding="utf-8")).substitute(
        on_time=service["on_time"], logged=service["recorded"], scheduled=service["scheduled"], canceled=service["canceled"],
        github=GITHUB, ref=esc(ctx["ref"]), film=ctx["film"], film_link=ctx["film_link"],
        source_readings=source_readings, bootstrap_block=copy_block("setup-prompt", messages[0], "Copy setup message"),
        first_lesson=render_lesson(ctx["demo_record"], ctx["audit"]), steps="".join(steps),
        welcome_command=copy_block("welcome-command", "./taos welcome", "Copy setup command"),
        own_command=copy_block("own-project-command", './taos use ../my-project --check "python3 -m unittest discover -s tests"', "Copy project setup example"),
        checks=reuse["checks"], relied=reuse["relied_on"], trace_executions=ctx["finest"]["executions"],
        trace_wrong=ctx["finest"]["wrong"], hidden_wrong=ctx["hidden"]["wrong"], bars=bars(ctx),
        reuse_play=reuse_play(reuse, ctx["finest"], ctx["hidden"], ctx["everything"]),
        reuse_recorded=esc(recorded_comparison(reuse, ctx["finest"], ctx["hidden"], ctx["everything"])))


def record_explorer(ctx: Dict[str, Any]) -> str:
    before, after = demo_walkthrough.fit_verdicts(ctx["chapters"])
    trial = next(row for row in ctx["audit"]["cases"] if row["id"] == "row-6-1.05")
    baseline = next(row for row in ctx["audit"]["cases"] if row["id"] == "baseline")
    original_rows, corrected_rows = baseline["rows"], trial["rows"]
    if [row[0] for row in original_rows] != [row[0] for row in corrected_rows]:
        raise ValueError("The illustrated timing correction requires the same pendulum lengths in order.")
    changes = [(a, b) for a, b in zip(original_rows, corrected_rows) if a[1] != b[1]]
    if len(changes) != 1:
        raise ValueError("The illustrated gravity fit requires one corrected period.")
    original, corrected = changes[0]
    if not (float(original[1]) < float(corrected[1]) and trial["g"] < baseline["g"]):
        raise ValueError("The walkthrough requires a longer swing time and a lower gravity estimate.")
    received = next(row for row in ctx["handoff"]["observations"] if row["id"] == "new-task-sees-failure")
    if not (baseline["fresh_exit"] == 0 and trial["retained"] == "stale" and trial["fresh_exit"] != 0
            and received["before"] == "fails" and received["actor_label"] == "codex"):
        raise SystemExit("The saved checks no longer support the pendulum handoff shown in the record explorer.")
    changed_input = "examples/measurement/data/swings.csv"
    if changed_input not in ctx["audit"]["sources"] or changed_input in ctx["model_evaluation"]["sources"]:
        raise SystemExit("The recorded inputs no longer support the two decisions in the handoff diagram.")
    graph = ctx["graph"]
    instrument_control = next(case for case in ctx["model_evaluation"]["cases"] if case["id"] == "figure-caption")
    counts = instrument_control["counts"]["pooled"]
    limits = re.fullmatch(r"g = [\d.]+ is outside ([\d.]+) to ([\d.]+)", trial["fresh_output"])
    if not limits:
        raise ValueError("Expected the corrected gravity check to report its accepted interval.")
    fault_marks = []
    for y, group in enumerate(("a", "b")):
        known_faults = [row for row in instrument_control["samples"][group] if int(row["reference_fault"])]
        for x, row in enumerate(known_faults):
            caught = float(row["score"]) >= instrument_control["threshold"]
            fill = "currentColor" if caught else "none"
            fault_marks.append(f'<circle cx="{7 + 9*x}" cy="{8 + y*11}" r="3" fill="{fill}"/>')
    if instrument_control["old_receipts"]["pooled"] != "holds":
        raise ValueError("The illustrated fault count requires a passing baseline instrument check.")
    drawn = json.dumps(graph, separators=(",", ":"))
    claim_lines = (REPO / "docs/CLAIMS.md").read_text(encoding="utf-8").splitlines()
    trace_line = next(i for i, line in enumerate(claim_lines, 1) if line.startswith("| " + TRACE_CLAIM + " |"))
    return Template("""
<h1 class="record-page-title">Explore the project record</h1>
<section id="record" class="mind-page"><div class="wrap">
<figure class="mind">
<figcaption class="mind-head">Research operating system walkthrough</figcaption>
<div id="architecture-cover" class="evidence-guide" data-guide-step="0">
<div class="guide-heading">
<p class="guide-credit">Guided example · Simulated research records</p>
<h2 id="guide-title" data-reader="headline" tabindex="-1">One reading changes. Which result needs a new check?</h2>
</div>
<div class="guide-map" role="group" aria-label="Two independent paths from recorded input to result">
<img class="guide-shell" src="assets/architecture-shell.webp" width="800" height="497" loading="lazy" alt="">
<div class="guide-paths"><span class="guide-map-name">Two study records</span>
<div class="guide-path guide-gravity">
<a class="guide-input" id="guide-time" href="$original_readings" data-original="$original_readings" data-corrected="$corrected_readings">
<svg class="guide-glyph guide-pendulum" viewBox="0 0 44 31" fill="none" stroke="currentColor" stroke-width="1.35" aria-hidden="true">
<path d="M10 3h22M20 4l-8 19m8-19 8 19" /><path d="M10 23q8 7 20 0" stroke-dasharray="2 2"/><circle cx="12" cy="23" r="3.2" fill="currentColor"/><circle cx="28" cy="23" r="2.8"/></svg><b>Swing time</b>
<span>$old_period s</span></a><span class="guide-edge" aria-hidden="true"></span>
<a class="guide-result" id="guide-gravity" href="$original_case" data-original="$original_case" data-corrected="$corrected_case"><b>Gravity estimate</b>
<span id="guide-fit">$old_fit m/s²</span><em id="guide-verdict">✓ Passed</em></a>
</div>
<div class="guide-path guide-instrument">
<a class="guide-input" href="workflows/review/reviewer-sources.md">
<svg class="guide-glyph" viewBox="0 0 44 29" stroke="currentColor" stroke-width="1.35" role="img" aria-label="One row per instrument. Filled circles mark detected faults.">$fault_marks</svg>
<b>Instrument study</b><span>Scores + fault labels</span></a><span class="guide-edge" aria-hidden="true"></span>
<a class="guide-result" href="evidence/model-evaluation/"><b>Faults caught</b><span>$detected of $known</span><em id="guide-retain">Recorded</em></a>
</div></div></div>
<div class="guide-desk">
<div class="guide-speaker"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="12" cy="7" r="3.5"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></svg><span id="guide-role">You · Reviewer</span></div>
<p class="guide-narration" id="guide-copy">The gravity estimate uses all $timing_count swing times. For the $swing_length m pendulum, replace $old_period s with $new_period s.</p>
<div class="guide-actions">
<button id="mind-start" type="button" class="guide-primary" data-reader="play" aria-controls="guide-check" hidden>Use the corrected time <span aria-hidden="true">→</span></button>
<div id="guide-check" data-reader="example" hidden>
<button id="guide-next" type="button" class="guide-primary" hidden></button>
<button id="guide-compare" type="button" class="guide-back" aria-controls="guide-copy" hidden
data-explanation="All $instrument_rows instrument readings and their fault labels stayed the same, so the count still holds at $detected of $known known faults.">What about the fault count?</button>
<div id="guide-handoff" data-reader="conclusion" hidden><a class="guide-primary" href="evidence/#handoff-request-$received_step">Open Codex’s handoff <span aria-hidden="true">↗</span></a></div>
</div>
<button class="guide-back" id="guide-back" type="button" hidden>Back</button>
<a id="mind-static" href="./#run">Read the recorded example <span aria-hidden="true">→</span></a>
</div></div>
<div class="guide-more"><button type="button" id="guide-explore" aria-controls="mind-demo" hidden>Explore all records</button>
<button type="button" id="mind-change-start" aria-controls="mind-demo" hidden>Try a file change</button></div>
</div>
<div id="mind-demo" hidden>
<div class="mind-story">
<h2 class="mind-title" id="mind-title" tabindex="-1" aria-live="polite">You have two results to review.</h2>
<div id="mind-say" class="mind-say">
<p id="mind-copy" aria-live="polite">One study estimated gravity from swing times. Another tested two instruments on known faults.</p>
<fieldset id="timing-comparison" class="timing-comparison" hidden>
<legend>Swing time of the <span class="measured-length">$swing_length&nbsp;m</span> pendulum</legend>
<div class="timing-options">
<label><input type="radio" name="swing-time" value="original"><span>Earlier <strong>$old_period s</strong></span></label>
<label><input type="radio" name="swing-time" value="corrected" checked><span>Corrected <strong>$new_period s</strong></span></label>
</div>
<div class="timing-result" role="status" aria-atomic="true">
<p data-fit="original" hidden><strong>$old_fit m/s²</strong> · Check passed. <a href="$original_readings" data-case="$original_case">Original six readings</a></p>
<p data-fit="corrected" hidden><strong>$new_fit m/s²</strong> · Fresh check failed. <a href="$corrected_readings" data-case="$corrected_case">Corrected six readings</a></p>
</div></fieldset></div></div>
<div class="mind-stage"><span class="mind-person" aria-hidden="true">
<svg width="21" height="23" viewBox="0 0 24 26" fill="none" stroke="currentColor" stroke-width="1.8">
<circle cx="12" cy="7" r="4"/><path d="M3 23v-2a9 9 0 0 1 18 0v2"/></svg><b>You</b></span>
<img class="mind-poster" src="assets/architecture-shell.webp" width="800" height="497" alt=""><canvas id="mind" role="img" aria-label="Map of linked measurements, files and claims. Choose a record from the list to inspect its evidence."></canvas>
<div id="story-labels" class="story-labels" role="group" aria-label="Follow the reading and the two results" hidden>
<span class="swing-label">Swing time</span>
<a class="gravity-label" href="$original_case"><b>Gravity estimate</b><small></small></a>
<a class="instrument-label" href="evidence/model-evaluation/"><b>Instrument comparison</b><small></small></a>
</div>
</div>
<div class="still"><div class="term"><pre>$specimen</pre></div>
<p class="small">Real output. The same check on the same task, before and after one input was measured again.</p></div>
<div class="mind-read"><div class="policy-inline" id="policy-inline" role="region" aria-labelledby="policy-inline-title" hidden>
<strong id="policy-inline-title"></strong>
<span id="policy-inline-copy"></span>
<span class="policy-inline-actions"><a id="policy-inline-source" hidden></a>
<button type="button" id="policy-inline-more">Full example</button>
<button type="button" id="policy-inline-dismiss" aria-label="Dismiss selected point">Dismiss</button></span></div>
<p id="mind-tip" class="mind-tip" hidden></p>
<div class="mind-file-action"><button type="button" id="mind-file-action" data-mind="illustrate" data-file="evals/reuse_frontier.py">Edit the experiment script</button>
<p id="mind-tally" class="mind-tally" aria-live="polite"></p></div></div>
<p class="mind-ctl story-controls"><button type="button" data-mind="previous" disabled>Previous step</button>
<button type="button" data-mind-pause aria-pressed="false" hidden>Pause</button>
<button type="button" data-mind="next" data-case="swing">Next step</button>
<button type="button" data-mind="again">Back to guided example</button>
</p>
<div id="swing-reading" class="swing-reading" hidden data-length="$swing_length" data-old-period="$old_period"
data-new-period="$new_period" data-old-g="$old_g" data-new-g="$new_g" data-low="$check_low" data-high="$check_high" data-faults="$caught">
<p><a href="evidence/#handoff-request-$received_step">See the check Codex received</a> ·
<a href="$corrected_case">Inspect the six readings</a></p>
<button type="button" class="compare-readings" id="compare-swing-times">Compare the swing times</button></div>
<details class="mind-note mind-trace"><summary>See the sources for the reuse experiment</summary>
<ol><li>The <a href="$github/blob/$revision/evals/reuse_frontier.py">experiment script</a> was an input to the
<a href="records/reuse_frontier.json">recorded reuse experiment</a>.</li>
<li>The experiment supports the claim “<a href="$github/blob/$revision/docs/CLAIMS.md#L$trace_line">$trace_claim</a>.”
The policy executed $trace_executions checks with $trace_wrong wrong reuses across $relied results relied on.</li>
<li>An edit to the script puts that claim in doubt. The <a href="records/mutations.json">seeded-fault experiment</a>
used different inputs and still supports its $caught-of-$faults result.</li></ol></details>
<details class="mind-note policy-explorer" id="record-explorer"><summary>Explore the record <span class="policy-picker-hint">Select a circle to see its evidence.</span></summary>
<div class="record-picker"><label class="policy-reader-notice" for="record-picker">Choose a result or source</label>
<select id="record-picker" aria-controls="policy-example"><option value="">Choose a record</option></select></div>
<section class="policy-example" id="policy-example" aria-labelledby="policy-example-title" hidden>
<p class="policy-example-kind" id="policy-example-kind"></p>
<h3 id="policy-example-title" tabindex="-1"></h3>
<p class="policy-example-copy" id="policy-example-copy"></p>
<div class="policy-example-links" id="policy-example-links"></div>
<div class="policy-example-actions"><button id="policy-example-edit" type="button" hidden>Simulate a file edit</button>
<button id="policy-example-dismiss" type="button">Dismiss</button></div>
<p class="policy-example-status" id="policy-example-status" aria-live="polite"></p>
</section>
<span class="policy-reader-notice" id="policy-reader-notice" aria-live="polite"></span>
<div class="record-key" role="group" aria-label="Map legend">
<span><i class="assistant-mark" aria-hidden="true"></i>AI agent</span>
<span><i class="evidence-mark" aria-hidden="true"></i>Evidence</span>
<a href="graph.json">Graph data <span class="policy-reader-notice">(JSON)</span></a></div></details>
</div></figure></div>
<script type="application/json" id="record-graph">$graph</script>
</section>
""").substitute(
        github=GITHUB, revision=esc(ctx["revision"]), trace_line=trace_line, trace_claim=esc(TRACE_CLAIM),
        received_step=received["sequence"], swing_length=esc(original[0]), old_period=esc(original[1]), new_period=esc(corrected[1]),
        old_g="{:.4f}".format(baseline["g"]), new_g="{:.4f}".format(trial["g"]),
        old_fit=f"{baseline['g']:.2f}", new_fit=f"{trial['g']:.2f}",
        timing_count=len(original_rows), instrument_rows=sum(map(len, instrument_control["samples"].values())),
        detected=counts["tp"], known=counts["tp"] + counts["fn"], fault_marks="".join(fault_marks),
        check_low=esc(limits[1]), check_high=esc(limits[2]),
        original_case="evidence/pendulum/#case-" + esc(baseline["id"]),
        corrected_case="evidence/pendulum/#case-" + esc(trial["id"]),
        original_readings="evidence/pendulum/#readings-" + esc(baseline["id"]),
        corrected_readings="evidence/pendulum/#readings-" + esc(trial["id"]),
        trace_executions=ctx["finest"]["executions"], trace_wrong=ctx["finest"]["wrong"], specimen=terminal([before, after]),
        graph=drawn.replace("</", "<\\/"), caught=ctx["caught"], faults=ctx["faults"], relied=ctx["reuse"]["relied_on"])


def evidence(ctx: Dict[str, Any]) -> str:
    standing = {row["claim"]: row for row in ctx["rows"] if row["where"] == "docs/CLAIMS.md"}
    parts = []
    for section in ctx["sections"]:
        parts.append("<h2>{0}</h2>".format(esc(section["title"])))
        if section["rows"]:
            head = "".join('<th scope="col">{0}</th>'.format(esc(cell)) for cell in section["head"][:3]) + '<th scope="col">Standing</th>'
            body = []
            for claim, what, how, status in section["rows"]:
                found = standing.get(claim)
                state = chip(found["state"]) if found else '<span class="chip reported"><i aria-hidden="true"></i>{0}</span>'.format(esc(status))
                anchor = {"`python3 evals/at_revision.py`": "revision-comparison",
                          "`python3 evals/mutations.py`": "seeded-faults"}.get(how)
                row_id = f' id="{anchor}"' if anchor else ""
                body.append(('<tr{0}><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}'
                             '<span class="kind">{5}</span></td></tr>').format(
                    row_id, inline(claim), inline(what), inline(how), state, esc(status) if found else ""))
            parts.append(('<div class="scroll" role="region" tabindex="0" aria-label="{2}">'
                          '<table class="claims"><thead><tr>{0}</tr></thead><tbody>{1}</tbody></table></div>').format(
                head, "".join(body), esc(section["title"])))
        if section["bullets"]:
            parts.append("<ul class=\"limits\">{0}</ul>".format("".join("<li>{0}</li>".format(inline(text)) for text in section["bullets"])))
    reuse = ctx["reuse"]
    rows = "".join("<tr><td>{0}</td><td class=\"num\">{1}</td><td class=\"num\">{2}</td></tr>".format(
        esc(row["policy"]), row["executions"], row["wrong"]) for row in reuse["rows"])
    predictions = "".join("<li>{0} <strong>{1}.</strong> {2}</li>".format(
        chip("holds" if item["held"] else "fails", "held" if item["held"] else "failed"), esc(key), esc(item["text"]))
        for key, item in sorted(reuse["predictions"].items()))
    holding = sum(1 for row in ctx["rows"] if row["state"] == "holds")
    model = ctx["model_evaluation"]
    corrected = next(row for row in model["cases"] if row["id"] == "offsetting-score-corrections")
    model_rows = []
    reading_rows = []
    for key, label in (("compact_status", "Project status"), ("task_capsule", "One task brief"), ("agents_md", "Project instructions")):
        row = ctx["runs"]["session_footprint"]["surfaces"][key]
        reading_rows.append(f'<tr><th scope="row">{label}</th><td>{row["lines"]}</td><td>{row["bytes"]:,}</td><td>{esc(row["delivery"])}</td></tr>')
    for key, name in (("A", "Instrument A"), ("B", "Instrument B"), ("pooled", "Both combined")):
        old = dict(zip(model["cell_order"], model["baseline_counts"][key]))
        new = corrected["counts"][key]
        status = "Passed" if corrected["result_after_consultation"][key] == "holds" else "Failed"
        model_rows.append(f'<tr><th scope="row">{name}</th><td>{old["tp"]} / {old["tp"] + old["fn"]}</td>'
                          f'<td>{new["tp"]} / {new["tp"] + new["fn"]} <span class="result-{status.lower()}">{status}</span></td></tr>')
    return Template("""
<section class="hero slim"><div class="wrap">
<p class="kicker">Evidence</p>
<h1>What the evidence shows</h1>
<p class="lead">A researcher corrects two readings. The pooled score stays the same.
One instrument now fails its check. Follow the sample IDs, then see what the next researcher can reuse.</p>
<p><a href="#model-evaluation">Compare the two instruments</a> · <a href="#measurement-audit">Inspect the pendulum fit</a> ·
<a href="#handoff-audit">Follow a handoff across three tasks</a> ·
<a href="#reuse-full">Compare the cost of rerunning checks</a> · <a href="#checked-claims">Review the software claims</a></p>
</div></section>
<section id="model-evaluation"><div class="wrap prose">
<p class="kicker">Model evaluation</p><h2>Can the classifier pass overall while one instrument fails its check?</h2>
<p>Each instrument had eight fictional readings with assigned scores, including four known faults.
The program flags a reading when its score reaches the cutoff. A passing check must flag at least three of
the four faults. The experiment corrected one score on each instrument and repeated all three checks.</p>
<div class="scroll" role="region" aria-labelledby="faults-caption" tabindex="0"><table class="model-result"><caption id="faults-caption">Known faults detected</caption><thead><tr>
<th scope="col">Readings</th><th scope="col">Before correction</th><th scope="col">After correction</th></tr></thead>
<tbody>$model_rows</tbody></table></div>
<p>The two corrections canceled when the readings were combined. TAOS required a fresh pooled check
because the files used to calculate it had changed.</p>
<p><a class="more" href="model-evaluation/">Inspect the corrected readings and all four experiments &rarr;</a></p>
</div></section>
$audit
$handoff
<section id="session-reading"><div class="wrap prose">
<h2>What does the next AI agent read?</h2>
<p>A new session can start with a short project status. Opening one task brings up a separate brief with its next action.
Here is how much text the pendulum demo supplied for each kind of reading.</p>
<div class="scroll"><table class="claims"><thead><tr><th scope="col">Reading</th><th scope="col">Lines</th><th scope="col">UTF-8 bytes</th><th scope="col">When it appears</th></tr></thead>
<tbody>$reading_rows</tbody></table></div>
<p class="small">The recorder replaces machine paths and dates with fixed labels before counting. Each row measures a separate text.
<a href="../studies/session-footprint/">See the actual readings and method</a> · <a href="../records/session_footprint.json">Download the record</a></p>
</div></section>
<section id="study-records"><div class="wrap prose"><h2>Studies you can check</h2>
<p>Choose a question for its recorded comparisons, method, limits and source data.</p>
<ul>$study_list</ul>
<p><a href="../research-audit.json">See which source values this build verified</a> ·
<a href="../exchange/">Follow a question in the research exchange</a></p></div></section>
<section id="checked-claims"><div class="wrap prose">
<h2>How the software claims were checked</h2>
<p>At build time, $holding of $claims entries passed the repository's readback. For a tested claim,
the readback confirms that the named code and test exist. The test suite runs separately. For a measured claim,
it checks the quoted number against the saved run and compares the input fingerprints with the files now present.
The count also includes numbers repeated in the README.</p>
<p><a href="$github/blob/$ref/docs/CLAIMS.md">Claim definitions and limits</a> ·
<!--evidence-source-download--> ·
<a href="../claims.json">Readback results (JSON)</a> · Run locally with <code>python3 evals/claims.py --strict</code>.</p>
$parts</div></section>
<section><div class="wrap prose">
<h2 id="reuse-full">The reuse experiment in full</h2>
<p>Each of $checks checksum checks reads a pair of folders in a synthetic workspace with $folders folders.
The experiment changes one file at a time. After each of $edits edits, it asks for all $checks results, giving $relied uses.
“Wrong reuse” counts each use of an earlier result after a file the check reads changed. One outdated result can count
more than once. Execution counts start after the six initial checks. The isolated failure row also includes those first six attempts.
Random seed $seed, Python $python on $platform.</p>
<div class="scroll"><table class="claims"><thead><tr><th scope="col">Policy, as recorded</th><th scope="col">Executions</th>
<th scope="col">Wrong reuses</th></tr></thead><tbody>$rows</tbody></table></div>
$timing_observations
<h3 class="sub">Predictions, written before the runs</h3>
<ul class="predictions">$predictions</ul>
<p><a class="more" href="../records/reuse_frontier.json">Download the recorded comparisons (JSON)</a> &middot;
<a class="more" href="$github/blob/$ref/evals/reuse_frontier.py">Read the experiment script</a></p>
</div></section>
""").substitute(github=GITHUB, ref=esc(ctx["ref"]), holding=holding, claims=len(ctx["rows"]), parts="".join(parts), audit=audit_section(ctx["audit"], ctx["boundary_controls"]),
                study_list="".join(f'<li><a href="../{agent_guide.landing(stem)}">{esc(question)}</a></li>' for stem, question in agent_guide.STUDIES),
                handoff=handoff_section(ctx["handoff"]), model_rows="".join(model_rows), reading_rows="".join(reading_rows),
                edits=reuse["edits"], checks=reuse["checks"], folders=reuse["folders"], seed=reuse["seed"],
                relied=reuse["relied_on"], python=esc(reuse["environment"]["python"]),
                platform=esc(reuse["environment"]["platform"]), rows=rows, predictions=predictions,
                timing_observations=timing_observations(reuse))


# ---------------------------------------------------------------- the same page for an agent

def home_markdown(ctx: Dict[str, Any], url: str) -> str:
    explanation = reuse_explanation(ctx)
    kinds = [node["k"] for node in ctx["graph"]["nodes"]]
    out = ["# ThesisAnalysisOS: what still holds?", "",
           "> " + DESCRIPTION, "",
           "A different agent picks up a report after its data changes. In the [optional bus film](./#field-film), "
           "see why canceled trips change Monday’s answer. The [saved handoff](workflows/transit/handoff.txt) names "
           "the Tuesday records that still need a person’s attention.", "",
           "In [a real research decision](decision/index.md), turning off a correction made a simulation look more accurate. "
           "Open the earlier measurement and choose what you would carry forward.", "",
           "When a new chat starts, the next agent can read your instructions, see who owns the work and find the "
           "decisions that still need you. In the [two-session transit walkthrough](workflows/transit/index.md), "
           "open the actual brief another agent receives before it prepares the next day’s report.", "",
           "The [pendulum audit](evidence/pendulum/) traces a corrected timing into the gravity estimate. "
           "The separate [instrument study](evidence/model-evaluation/) uses its own readings.", "",
           "A check can miss a change if its input list is incomplete. The [measurement audit](evidence/#measurement-audit) "
           "includes two cases where an old pass survived a change and the fresh measurement failed.", "",
           "- [Independent measurement audit](evidence/#measurement-audit) · [Protocol](records/measurement-method.md) · "
           "[Raw measurements](records/measurement_audit.json) · [Reproduction script](records/measurement_audit.py)",
           "- [Pendulum handoff](evidence/#handoff-audit) · [Method](records/handoff-method.md) · "
           "[Raw observations](records/handoff_audit.json) · [Reproduction script](records/handoff_audit.py)",
           "- Repository: " + GITHUB,
           "- [Software citation](" + SOFTWARE_CITATION + ") · [License](license.txt)",
           "- Built from revision `{0}` on {1}. Whether that still holds: compare `standing.json` with the repository.".format(
               ctx["revision"], ctx["built"]),
           "- Python standard library only. No network and no model calls.",
           "The [evidence graph](graph.json) links {0} files, {1} recorded runs and {2} claims to this page. "
           "The interactive view simulates an edit in the browser.".format(
               kinds.count("f"), kinds.count("r"), kinds.count("c")), "",
           lesson_markdown(ctx["demo_record"], ctx["audit"]), "", "## Every step in the recorded run", "",
           "The demo fits six pendulum timings, edits the plot style, then corrects one timing. The website runs "
           "`./taos demo --json` at build time. [Download the complete run](records/demo.json).", ""]
    for number, scene in enumerate(ctx["chapters"], 1):
        out += [f"### {number}. {scene.title}", "", scene.story, ""]
        out += [f"- {label} — {value}" for label, value in scene.facts]
        if scene.comparisons:
            out += ["", demo_walkthrough.comparison_markdown(scene.comparisons)]
        out += ["", "```text"] + scene.lines + ["```", "", f"Implementation in `{scene.code}`", ""]
    out += ["## How to read a saved check", "", "No result outlives what it stood on.", "",
            "Each record names who produced it and the inputs or instructions it relied on. TAOS calls those its basis. "
            "Comparing the recorded basis with the current one yields one of four answers.", ""]
    out += ["- **{0}** — {1}".format(state, text) for state, text in ANSWERS]
    out += ["", "1. An old pass can still apply if the inputs match.",
            "2. The original dated instruction identifies what the researcher requested and where it applied.",
            "3. The program records whether its check passed. A separate record identifies which version a person approved.",
            "", "## Where would I use this?", ""]
    for (question, example, limit, code, code_label, test, test_label), _ in ctx["decisions"]:
        out += ["### " + question, "", example + " " + limit, "",
                f"[{code_label}]({code}) · [{test_label}]({test})", ""]
    out += ["For a numerical example, [compare the two groups with their pooled result](evidence/#model-evaluation) "
            "after correcting scores in a synthetic instrument evaluation.", "", "### What each record preserves", ""]
    out += ["- {0}: {1} (`{2}`)".format(name, text, path) for name, text, path in USES]
    out += ["", "## Evidence", "",
            "- {0} of {1} regression tests pass on this revision. {2} fail on the first release tested, `{3}`.".format(
                ctx["cases_pass"], ctx["cases"], ctx["first_release_failed"], ctx["first_release"]),
            "- {0} of {1} deliberately removed protections caused their associated tests to fail.".format(ctx["caught"], ctx["faults"]),
            "- {0} of {1} published claims passed the repository’s checks (`claims.json`).".format(
                sum(1 for row in ctx["rows"] if row["state"] == "holds"), len(ctx["rows"])), "",
            "### " + explanation["title"], "", explanation["setup"], "",
            "**" + explanation["saving"] + ".** " + explanation["comparison"], "", explanation["omission"], "",
            "[Full results and method](evidence/#reuse-full) · [Recorded data](records/reuse_frontier.json)"]
    out += ["", "What this does not show:", ""] + ["- " + text for text in LIMITS]
    out += ["", "## How scientific software tracks a result back to its inputs", ""] + ["- {0}. {1} ({2})".format(a, b, c) for a, b, c in LINEAGE]
    out += ["", "Multiple agents can share a project, take responsibility for different tasks and hand work to the next reviewer. "
            "The record includes dated instructions and the version a person approved. In the reuse experiment, "
            "grouping the inputs into 6 or 12 domains saved the same number of check executions. "
            "[Study design, predictions, and references](" + GITHUB + "/blob/" + ctx["ref"] + "/docs/METHOD.md)."]
    out += ["", "## Data, code, and local setup", "",
            "- Read `AGENTS.md` in the repository first. It says how to examine the system without setting it up.",
            "- `python3 evals/claims.py --json` checks the published claims against the current checkout.",
            "- `./taos demo` runs the pendulum example in a temporary folder. `./taos selftest` runs the tests.",
            "- To use it for a project, create a repository from the template and follow `BOOTSTRAP.md`.", "",
            "The [research catalog](research-catalog.json) lists the experiments by question, with methods, limits and downloadable observations. The [agent index](llms.txt) links the project records and code. The [research exchange](exchange/) links questions and replies to the evidence they cite.", ""]
    return "\n".join(out)


def evidence_markdown(ctx: Dict[str, Any]) -> str:
    out = ["# What the evidence shows", "",
           "If a researcher corrects an input after a check has passed, can the team still use that pass? "
           "The pendulum experiment inspects the old pass first, then repeats the fit and checks its numerical result.", "",
           "[Browse all pendulum cases](pendulum/index.md) · [Protocol and limits](../records/measurement-method.md) · "
           "[Raw observations](../records/measurement_audit.json) · [Reproduction script](../records/measurement_audit.py) · "
           "[Independent verifier](../records/review_measurement_audit.py)", ""]
    out += ["## Can the classifier pass overall while one instrument fails its check?", "",
            "[Compare corrected readings, subgroup counts, and four controlled edits](model-evaluation/index.md).", ""]
    out += handoff_markdown(ctx["handoff"]) + [
           "A separate [reuse experiment](./#reuse-full) asks which checks need to run again after a file changes. "
           "[Download the recorded comparisons](../records/reuse_frontier.json).", "",
           "A fresh agent can open a short status summary and a brief for one task. "
           "[Read the actual session texts and their sizes](../studies/session-footprint/index.md). "
           "[Follow a fictional transit report into a second session](../workflows/transit/index.md).", "",
           "## Software claims", "",
           "At revision `{0}`, `python3 evals/claims.py --json` checked code and test references, measured values, and "
           "the numbers repeated in the README. A tested row confirms the named code and test exist. "
           "A measured row also checks the quoted number and the saved input fingerprints.".format(ctx["revision"]), "",
           "| Standing | Claim | Reason |", "|---|---|---|"]
    out += ["| {0} | {1} | {2} |".format(row["state"], row["claim"].replace("|", "/"), row["reason"].replace("|", "/")) for row in ctx["rows"]]
    out += ["", "Full text with code, tests and what is not claimed: {0}/blob/{1}/docs/CLAIMS.md".format(GITHUB, ctx["ref"]), ""]
    return "\n".join(out)


# ---------------------------------------------------------------- write, then check what was written

class PageLinks(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.targets = []
        self.ids = set()
        self.feed(path.read_text(encoding="utf-8"))
        self.close()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value and name in {"href", "src", "poster"}:
                self.targets.append(value)
            if name == "id":
                self.ids.add(value)


def broken(out: Path, url: str = "", revision: str = "") -> List[str]:
    """Check site links and anchors as a browser resolves them, including nested 404s."""
    base = url or "https://offline.invalid/"
    site = urlsplit(base)
    out = out.resolve()
    pages = {path: PageLinks(path) for path in sorted(out.rglob("*.html"))}
    problems = []
    for page, links in pages.items():
        document = page.relative_to(out).as_posix()
        address = urljoin(base, "missing/nested/page" if document == "404.html" else document)
        for target in links.targets:
            link = urlsplit(urljoin(address, target))
            if revision and link.geturl().split("#", 1)[0] == GITHUB + "/commit/" + revision:
                problems.append(f"{document}: {target} should open the bundled source")
                continue
            if (link.scheme, link.netloc) != (site.scheme, site.netloc):
                continue
            resource = unquote(link.path)
            if not resource.startswith(site.path):
                problems.append(f"{document}: {target} leaves the site directory")
                continue
            path = page if target.startswith("#") else (out / resource[len(site.path):]).resolve()
            if path.is_dir():
                path /= "index.html"
            if not path.is_relative_to(out) or not path.is_file():
                problems.append(f"{document}: {target}")
            elif link.fragment and path in pages and unquote(link.fragment) not in pages[path].ids:
                problems.append(f"{document}: {target} has no matching anchor")
    return problems


def build(out: Path, ref: str, url: str, release: bool = False, preview_film_dir: Optional[Path] = None) -> Dict[str, Any]:
    files = film_files(preview_film_dir, out, release)
    if release and (not re.fullmatch(r"[0-9a-f]{40}", ref) or git("rev-parse", "HEAD") != ref):
        raise SystemExit("Release source must match the full commit tested by CI.")
    ctx = gather(ref)
    ctx["public_analytics"] = (release and url == "https://whatstillholds.com/"
                               and os.environ.get("GITHUB_REPOSITORY") == NAME
                               and os.environ.get("GITHUB_REF") == "refs/heads/main")
    if out.exists():
        shutil.rmtree(str(out))
    (out / "evidence/pendulum").mkdir(parents=True)
    (out / "decision").mkdir()
    (out / "evidence/model-evaluation").mkdir()
    (out / "workflows/transit").mkdir(parents=True)
    (out / "workflows/review").mkdir(parents=True)
    (out / "workflows/everyday").mkdir(parents=True)
    (out / "hpc").mkdir()
    (out / "records").mkdir()
    shutil.copytree(str(HERE / "assets"), str(out / "assets"))
    media_dir = PUBLIC_MEDIA_DIR if preview_film_dir is None else "private-film"
    ctx["film"] = render_player(files, out, media_dir)
    ctx["film_link"] = opening_link(files)
    for path, filename in {**AUDIT_DOWNLOADS, **HANDOFF_DOWNLOADS}.items():
        shutil.copy2(REPO / path, out / "records" / filename)
    for path, destination in MODEL_DOWNLOADS.items():
        target = out / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / path, target)
    shutil.copy2(REPO / "evals/results/model_evaluation.json", out / "records/model_evaluation.json")
    shutil.copy2(REPO / SETTING_RECORD, out / SETTING_DOWNLOAD)
    for name in read_back.RUNS:
        shutil.copy2(str(REPO / "evals" / "results" / (name + ".json")), str(out / "records" / (name + ".json")))
    write = lambda path, text: (out / path).write_text(text, encoding="utf-8")  # noqa: E731
    transit_path = REPO / "examples/transit/workflow.json"
    transit = load_transit_record(transit_path)
    ctx["service_report"] = transit["observations"]["monday"]
    adaptation_path = REPO / "examples/transit/adaptation/workflow.json"
    adaptation = load_adaptation_record(adaptation_path)
    shutil.copy2(transit_path, out / "records/transit-workflow.json")
    shutil.copy2(adaptation_path, out / "records/transit-adaptation.json")
    write("workflows/transit/index.html", shell(ctx, "../../", "The morning bus report · ThesisAnalysisOS",
          render_transit_exhibit(transit, adaptation=adaptation), url, "workflows/transit/"))
    write("workflows/transit/index.md", render_transit_markdown(transit, adaptation=adaptation))
    write("workflows/transit/handoff.txt", transit["observations"]["handoff"])
    write("workflows/transit/transfer.txt", transit_transfer(transit["observations"]["capsule"]) + "\n")
    reviewer_prompt, reviewer_sources = reviewer_materials(ctx["model_evaluation"], REPO)
    write("workflows/review/index.html", shell(ctx, "../../", "Practice reviewing an AI-assisted result · ThesisAnalysisOS",
          render_practice(ctx["demo_record"], ctx["audit"], capsule_text=ctx["successor_capsule"]), url, "workflows/review/"))
    write("workflows/review/index.md", practice_markdown(ctx["demo_record"], ctx["audit"], capsule_text=ctx["successor_capsule"]))
    everyday = ('<section class="plain"><div class="wrap"><p class="kicker">A first example</p>'
                '<h1>Which plans still work after a flight changes?</h1>'
                + render_game("../../#run") + '<p><a href="../review/">Try a research decision</a></p></div></section>')
    write("workflows/everyday/index.html", shell(ctx, "../../", "Try a change · ThesisAnalysisOS", everyday, url, "workflows/everyday/"))
    write("workflows/everyday/index.md", game_markdown("../../#run"))
    write("hpc/index.html", shell(ctx, "../", HPC_TITLE, render_hpc(), url, "hpc/"))
    write("hpc/index.md", hpc_markdown())
    write("hpc/pilot-worksheet.md", pilot_worksheet())
    write("hpc/" + hpc_review.BRIEF_LINK, hpc_review.default_brief() + "\n")
    write("hpc/" + hpc_review.REPORT_LINK, json.dumps(hpc_review.sample_review(), indent=2, ensure_ascii=False) + "\n")
    write("hpc/example-run.json", json.dumps(run_trace(), ensure_ascii=False, indent=2) + "\n")
    write("workflows/review/reviewer-prompt.txt", reviewer_prompt)
    write("workflows/review/reviewer-sources.md", reviewer_sources)
    handoff_method = (REPO / HANDOFF_METHOD).read_text(encoding="utf-8")
    for path, destination in HANDOFF_DOWNLOADS.items():
        handoff_method = handoff_method.replace("../" + path, destination)
    write("records/handoff-method.md", handoff_method)
    # The boundary controls exercise the ordinary checker without altering the recorded 36-case study.
    boundary = subprocess.check_output([sys.executable, str(REPO / BOUNDARY_CHECK), "--json"], cwd=REPO, text=True)
    ctx["boundary_controls"] = json.loads(boundary)
    write("records/pendulum-boundaries.json", boundary)

    write("index.html", shell(ctx, "./", "ThesisAnalysisOS · What still holds?", home(ctx), url, "",
                              '<script src="assets/report-story.js" defer></script>\n'
                              '<script src="assets/reuse.js" defer></script>'))
    decision = (HERE / "decision.html").read_text(encoding="utf-8")
    write("decision/index.html", shell(ctx, "../", "Try a research decision · ThesisAnalysisOS",
                                      decision, url, "decision/", '<script src="../assets/report-story.js" defer></script>'))
    shutil.copy2(HERE / "decision.md", out / "decision/index.md")
    write("record.html", shell(ctx, "./", "Explore the project record · ThesisAnalysisOS", record_explorer(ctx),
                               url, "record.html", '<script src="assets/mind.js" defer></script>'))
    write("record.md", "# Explore the project record\n\n"
          "Follow a file, a saved check or a claim to its evidence in the [interactive record](record.html). "
          "The [downloadable graph](graph.json) lists the same files and connections. "
          "The pendulum example links a [corrected measurement](evidence/pendulum/) to "
          "[the task that received it](evidence/#handoff-audit).\n")
    write("evidence/index.html", shell(ctx, "../", "Evidence: ThesisAnalysisOS", evidence(ctx), url, "evidence/"))
    write("evidence/pendulum/index.html", shell(ctx, "../../", "Pendulum audit observations", audit_cases_page(ctx["audit"]),
                                              url, "evidence/pendulum/"))
    write("evidence/model-evaluation/index.html", shell(ctx, "../../", "Model evaluation by instrument",
          model_evaluation_html(ctx["model_evaluation"], ctx["instrument_paths"]), url, "evidence/model-evaluation/"))
    write("evidence/model-evaluation/index.md", model_evaluation_markdown(ctx["model_evaluation"], ctx["instrument_paths"]))
    md = ["# Pendulum audit observations", "",
          "The fit uses six swing timings and a straight line through zero. Each estimate and its standard error are in m/s². "
          "The standard error describes scatter around this model. The experiment assumes small swings and gives each squared "
          "period equal weight. Calibration of lengths and times and finite swing amplitude are outside that error.", "",
          "A separate decimal calculation checks the arithmetic of the same estimator. A [supplemental acceptance check]"
          "(../../records/pendulum-boundaries.json) records what happens immediately on either side of the cutoffs. "
          "The [fit assumptions and limits](../#pendulum-fit-limits) accompany the recorded cases.", "",
          "| Case | Old receipt | Fit ± SE | Fresh check |", "|---|---|---|---|"]
    for row in ctx["audit"]["cases"]:
        md.append("| {id} | {retained} | {g:.6f} ± {se:.6f} | {fresh} |".format(
            **row, fresh="pass" if row["fresh_exit"] == 0 else "fail"))
    md.extend(["", "[Raw rows and check output](../../records/measurement_audit.json)", ""])
    write("evidence/pendulum/index.md", "\n".join(md))
    base = "/" + "/".join(url.split("/")[3:]) if url else "/"      # a project page is served under the repository's name
    write("404.html", shell(ctx, base, "Not found: ThesisAnalysisOS",
                            '<section class="hero slim"><div class="wrap"><p class="kicker">404</p><h1>unknown</h1>'
                            '<p class="lead">Nothing is recorded at this address. <a href="{0}">Start from the front page</a>.</p>'
                            '</div></section>'.format(base), url, "404.html"))
    write("index.md", home_markdown(ctx, url))
    write("evidence/index.md", evidence_markdown(ctx))
    (out / "studies").mkdir()
    agent_guide.write_decision_reading(out, ctx["decisions"])
    write("claims.json", json.dumps({"repository": NAME, "revision": ctx["revision"], "built": ctx["built"],
                                     "check": "python3 evals/claims.py --json", "rows": ctx["rows"]}, indent=2, sort_keys=True) + "\n")
    write("records/demo.json", json.dumps(ctx["demo_record"], ensure_ascii=False, indent=2) + "\n")
    write("records/pendulum-capsule.txt", ctx["successor_capsule"])
    # Both text views use the same run as the JSON. Mark UTF-8 for hosts that omit a charset.
    for name, full in (("demo.txt", False), ("demo-transcript.txt", True)):
        terminal_view = io.StringIO()
        write_terminal_demo(ctx["demo_record"], terminal_view, full=full, width=None if full else 80, color=False)
        write("records/" + name, "\ufeff" + terminal_view.getvalue())
    write("standing.json", json.dumps({"repository": NAME, "branch": "main", "revision": ctx["revision"], "built": ctx["built"],
                                       "stands_on": ctx["stands_on"]}, indent=2, sort_keys=True) + "\n")
    write("graph.json", json.dumps({
        "repository": NAME, "revision": ctx["revision"], "built": ctx["built"],
        "reading": "A node is a file (f), a recorded run (r), a claim (c) or the page (p). An edge is [record, what it stands on], "
                   "as positions in nodes. The claims are the rows of `python3 evals/claims.py --json`, in its order.",
        "nodes": ctx["graph"]["nodes"], "edges": ctx["graph"]["edges"],
        "worked_traversals": {"corrected_pendulum_reading": pendulum_traversal(ctx)}}, sort_keys=True) + "\n")
    write("robots.txt", "User-agent: *\nAllow: /\n" + ("Sitemap: {0}sitemap.xml\n".format(url) if url else ""))
    if url:
        paths = ["", "decision/", "record.html", "hpc/", "workflows/review/", "workflows/transit/", "workflows/everyday/", "evidence/", "evidence/pendulum/", "evidence/model-evaluation/", "exchange/"]
        paths.extend(agent_guide.landing(stem) for stem, _ in agent_guide.STUDIES)
        write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
              + "".join(f"<url><loc>{esc(url + path)}</loc></url>\n" for path in paths)
              + "</urlset>\n")
    for name in ("LICENSE", "NOTICE"):
        shutil.copyfile(REPO / name, out / (name.lower() + ".txt"))
    write(".nojekyll", "")
    evidence_files = {link["path"] for node in ctx["graph"]["nodes"]
                      for link in node.get("evidence", {}).get("links", [])}
    evidence_files.update(agent_guide.GUIDE_SOURCES)
    evidence_files.update(hpc_review.SOURCES)
    # Keep source URLs cited by previously published research pages available to returning readers.
    evidence_files.update(("site/build.py", "taos_core/standing.py", "taos_core/handoff.py", "taos_core/lifecycle.py"))
    for _, packet in ctx["decisions"]:
        evidence_files.update(entry["path"] for entry in [*packet["implementation"], packet["test"]])
    evidence_files.update(("docs/opener.svg", "site/home_reading.html", "site/visitor_header.html", "site/next_agent.html", "site/assets/visitor.css",
                 "site/decision.html", "site/decision.md",
                           "evals/session_footprint.py", "evals/transit_workflow.py",
                           "tests/test_transit_workflow.py", "docs/TRANSIT_WORKFLOW.md", "docs/LINEAGE.md",
                           "examples/transit/tuesday-schedule.csv", "examples/transit/tuesday-dispatch.csv"))
    evidence_files.update((*SETTING_SOURCES, *SETTING_FIXTURE_FILES))
    snapshot = write_source_snapshot(out, REPO, GITHUB, ctx["ref"], ctx["revision"], evidence_files)
    if release and not snapshot["archive"]:
        raise SystemExit("Release requires the verified source archive for the tested commit.")
    if release:
        retain_published_archives(out, REPO)
    archive = snapshot["archive"]
    if archive:
        setup = (f'<a href="source/{esc(archive)}" data-source-download download>Download this demo</a> (ZIP). '
                 'Open the unzipped folder in a macOS or Linux terminal with Git and Python 3.9 or later installed.')
        welcome_source = (f'<a href="source/{esc(archive)}" data-source-download download>Download this version (ZIP)</a>. '
                          'Open the extracted folder in a terminal and run the command below.')
        welcome = "./taos welcome"
        commands = "./taos demo"
    else:
        setup = "To try the published demo, open a macOS or Linux terminal with Git and Python 3.9 or later installed."
        welcome_source = "Open a macOS or Linux terminal to get the public release and try it."
        welcome = f"git clone {GITHUB}.git\ncd ThesisAnalysisOS\n./taos welcome"
        commands = f"git clone {GITHUB}.git\ncd ThesisAnalysisOS\n./taos demo"
    evidence_page = out / "evidence" / "index.html"
    evidence_source = (f'<a href="../source/{esc(archive)}" data-source-download download>Download the source for this build</a>'
                       if archive else '<a href="../source/">Browse the source for this build</a>')
    evidence_page.write_text(evidence_page.read_text(encoding="utf-8").replace("<!--evidence-source-download-->", evidence_source), encoding="utf-8")
    homepage = out / "index.html"
    homepage.write_text(homepage.read_text(encoding="utf-8")
                        .replace("<!--welcome-source-->", welcome_source)
                        .replace("<!--welcome-command-block-->", copy_block("quick-setup", welcome, "Copy setup command"))
                        .replace("<!--demo-setup-->", setup)
                        .replace("<!--demo-command-block-->", copy_block("demo-commands", commands, "Copy commands")), encoding="utf-8")
    catalog = research_catalog(out / "records", url if release else "",
                               ctx["revision"] if archive else None,
                               source_archive="source/" + archive if archive else None)
    recorded = {node["l"]: node for node in ctx["graph"]["nodes"] if node["k"] == "r"}
    datasets = catalog["dataset"]
    if len(datasets) != len(recorded) or {item["identifier"] for item in datasets} != recorded.keys():
        raise SystemExit("The research catalog and evidence graph list different experiments.")
    public_commit = (release and os.environ.get("GITHUB_ACTIONS") == "true"
                     and os.environ.get("GITHUB_REPOSITORY") == NAME and os.environ.get("GITHUB_REF") == "refs/heads/main"
                     and os.environ.get("GITHUB_SHA") == ctx["revision"])
    for item in datasets:
        run = recorded[item["identifier"]]
        if item["distribution"]["sha256"] != run["sha256"]:
            raise SystemExit(f"The dataset download does not match its graph evidence: {item['identifier']}")
        item["abstract"] = run["finding"]
        if public_commit:
            item["sameAs"] = f'{GITHUB}/blob/{ctx["revision"]}/{item["identifier"]}'
    catalog["citation"] = (url if release else "") + SOFTWARE_CITATION
    groups = {Path(item["identifier"]).stem: item for item in datasets}
    briefs = study_briefs(out / "records", groups)
    if set(groups) != set(briefs) or set(groups) != {stem for stem, _ in agent_guide.STUDIES}:
        raise ValueError("Study records, agent guide and dataset catalog must describe the same experiments.")
    for stem, dataset in groups.items():
        path = agent_guide.landing(stem)
        brief = briefs[stem]
        rows = agent_guide.write_reading(out, stem, dataset, brief)
        dataset["url"] = (url if release else "") + path

        dataset["description"] = brief["method"] + " " + brief["scope"]
        dataset["subjectOf"] = {"@type": "DigitalDocument", "name": "Recorded comparisons, scope and source fields",
                                "url": (url if release else "") + path + "index.md"}
        page = shell(ctx, "../../", brief["question"], agent_guide.reading_body(dataset, brief, rows), url, path, dataset=dataset)
        write(path + "index.html", page)
    write_research_notes(out, catalog)
    followup = write_followup(out, REPO, url if release else "")
    model_name = "exchange_simulation.json"
    model_bytes = (REPO / "evals/results" / model_name).read_bytes()
    model = json.loads(model_bytes)
    if model["kind"] != "model, not a measurement" or not model["uses"] or not model["predictions"]:
        raise ValueError("The exchange simulation needs its modeled requests, predictions and scope.")
    (out / "records" / model_name).write_bytes(model_bytes)
    shutil.copyfile(REPO / "docs/EXCHANGE_SIMULATION.md", out / "exchange/simulation.md")
    sim_base = url if release else ""
    modeled = {"@type": "Dataset", "identifier": "evals/results/" + model_name,
               "name": "What happens when assistants pass copies of results to each other?",
               "description": f"A seeded model compared {len(model['rows'])} policies across {model['uses']:,} simulated requests. All agent actions follow programmed rules.",
               "url": sim_base + "exchange/simulation.md",
               "distribution": {"@type": "DataDownload", "contentUrl": sim_base + "records/" + model_name,
                                "encodingFormat": "application/json", "sha256": hashlib.sha256(model_bytes).hexdigest()}}
    discussion_catalog = {**catalog, "name": "Evidence cited in the research exchange",
                          "dataset": [*datasets, followup, modeled]}
    discussion_catalog["@id"] = (url if release else "") + "exchange-catalog.json"
    write("exchange-catalog.json", json.dumps(discussion_catalog, ensure_ascii=False, indent=2) + "\n")
    exchange_index = write_exchange(out, discussion_catalog, url, public_revision=ctx["revision"] if release else None)
    if not release or url.rstrip("/") == "https://whatstillholds.com":
        shutil.copyfile(HERE / "security.txt", out / ".well-known/security.txt")
    question = agent_guide.open_question(out, exchange_index)
    sources = json.loads((out / "source/index.json").read_bytes())["files"]
    write("llms.txt", agent_guide.guide(ctx, url if release else "", exchange_index, question, sources))
    write_feed(out, exchange_index, url)
    related = ('<section><div class="wrap prose"><h2>Explore the experiments</h2>'
               '<p><a href="instrument-imbalance.md">See the classifier follow-up</a> · '
               '<a href="simulation.md">Compare 14 rules in a simulated research team</a> · '
               '<a href="../records/exchange_simulation.json">Read the simulation data</a></p>'
               '<p><a href="feed.json">Subscribe to questions and replies</a></p></div></section>')
    write("exchange/index.html", shell(ctx, "../", "Research exchange: ThesisAnalysisOS", exchange_html(exchange_index) + related, url, "exchange/"))
    write("research-catalog.json", json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    # Put the same verifiable dataset descriptions in the HTML that introduces these studies.
    # The archive is known only after source_snapshot has rewritten and checked the local links.
    homepage = (out / "index.html").read_text(encoding="utf-8")
    linked_data = json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    write("index.html", homepage.replace("</head>", f'<script type="application/ld+json">{linked_data}</script>\n</head>', 1))
    protect_pages(out, analytics=ctx["public_analytics"])
    if preview_film_dir is None:
        verify_homepage_film(out)
    agent_guide.study_versions(out, datasets, ctx["revision"])
    write("research-audit.json", json.dumps(verify_research_guide(out, writing_report=True), indent=2) + "\n")
    problems = broken(out, url, ctx["revision"])
    if problems:
        raise SystemExit("links that lead nowhere:\n  " + "\n  ".join(problems))
    write_manifest(out, ctx["revision"])
    return ctx


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the public page from the repository's records.")
    parser.add_argument("--out", default=str(REPO / "_site"))
    parser.add_argument("--ref", default="main", help="the revision that links to code point at")
    parser.add_argument("--url", default="", help="where the site will be served, ending in a slash")
    parser.add_argument("--release", action="store_true", help="require the tested commit and its exact source ZIP")
    parser.add_argument("--preview-film-dir", type=Path, help="include a private local film preview from this directory")
    args = parser.parse_args(argv)
    worktree = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--show-toplevel"],
                              text=True, capture_output=True) if shutil.which("git") else None
    if not worktree or worktree.returncode or Path(worktree.stdout.strip()).resolve() != REPO:
        raise SystemExit("Building the source browser requires a Git checkout of ThesisAnalysisOS. "
                         "Clone the repository and run this command from its root.")
    ctx = build(Path(args.out), args.ref, args.url, release=args.release, preview_film_dir=args.preview_film_dir)
    print("built {0} from {1}: {2} moments, {3} claims hold, stands on {4} files, the record drawn as {5} nodes and {6} edges".format(
        args.out, ctx["revision"][:7], len(ctx["chapters"]), len(ctx["rows"]), len(ctx["stands_on"]),
        len(ctx["graph"]["nodes"]), len(ctx["graph"]["edges"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
