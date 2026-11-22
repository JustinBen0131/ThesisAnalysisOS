"""Short, independently verifiable readings of the repository's recorded studies."""
import ast
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit


STUDIES = (
    ("model_evaluation", "Can an overall score hide a problem in one group?"),
    ("measurement_audit", "What happens to a published number after one reading changes?"),
    ("handoff_audit", "Can another task recover the exact check behind a result?"),
    ("reuse_frontier", "Which checks can a team skip after editing a file?"),
    ("mutations", "Do the tests catch deliberately broken protections?"),
    ("at_revision", "Which failures disappeared between software revisions?"),
)

DECISION_SOURCES = (
    ("approval", ("TaskStore.accept",),
     "TestWhy.test_acceptance_is_of_one_version_and_does_not_carry_over"),
    ("instruction", ("governing", "_governing", "displaced_by", "in_force", "covers"),
     "TestInstructionsKeepTheirTime.test_a_later_replacement_does_not_erase_the_earlier_answer"),
    ("control", ("score",), "TestChanges.test_confirmed_refuted_and_control_moved"),
)


def landing(stem):
    return "studies/" + stem.replace("_", "-") + "/"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


GUIDE_SOURCES = ("README.md", "BOOTSTRAP.md", "MANUAL.md", "SECURITY.md", "docs/ARCHITECTURE.md", "docs/CLAIMS.md",
                 "docs/METHOD.md", "CITATION.cff")


def open_question(out, exchange):
    """Prepare an unsubmitted reply to a current proposal whose recorded prediction remains untested."""
    for row in exchange["entries"]:
        if (row["stance"] != "proposes" or row["replies_to"] is not None or
                row["provenance"].get("revision", "current") != "current" or
                row["standing"] != "holds" or row["prediction"]["status"] != "untested"):
            continue
        raw = (out / row["entry"]).read_bytes()
        if digest(raw) != row["id"]:
            raise ValueError("The open question differs from its archived entry.")
        entry = json.loads(raw)
        draft_note = {"format": entry["note"]["format"], "kind": "follow-up", "proposal": "", "scope": "",
                      "prediction": "", "control": "", "evidence": entry["note"]["evidence"]}
        draft = {"format": entry["format"], "stance": "asks", "replies_to": row["id"], "note": draft_note}
        path = f"exchange/drafts/reply-to-{row['id']}.json"
        (out / "exchange/drafts").mkdir(exist_ok=True)
        write_json(out / path, draft)
        return row, path
    return None


def guide(ctx, base, exchange, question, source_files):
    findings = {Path(node["l"]).stem: node["finding"] for node in ctx["graph"]["nodes"] if node["k"] == "r"}
    base = base.rstrip("/") + "/" if base else ""
    if base:
        origin = urlsplit(base)
        if origin.scheme != "https" or not origin.netloc or origin.query or origin.fragment:
            raise ValueError("The released agent guide needs an HTTPS site URL with an optional project path.")
    sources = {row["path"]: base + "source/" + row["raw_url"] for row in source_files if row["path"] in GUIDE_SOURCES}
    def file(title, path, note):
        return f"- [{title}]({base}{path}) {note}"
    lines = ["# ThesisAnalysisOS", ""]
    if question:
        row, draft = question
        title = re.sub(r"([\\\[\]`*<>])", r"\\\1", " ".join(row["plain"].split()))
        scope = re.sub(r"([\\\[\]`*<>])", r"\\\1", " ".join(row["scope"].split()))
        lines += ["## Open research question", "", f"[{title}]({base}{row['page']})", "",
                  "The earlier observation is on record. This proposed test is still open.", "",
                  scope, "", f"Read the [cited observation]({base}{row['record']}) at `{row['pointer']}`. "
                  f"[Reply in a few lines]({row['reply']}) opens a prefilled GitHub issue for a person to review and send.", "",
                  f"To share a file, complete the four blank note fields in the [reply draft]({base}{draft}) and "
                  f"[verify it locally]({base}exchange/index.md). Teams can exchange the file offline.", ""]
    outside = exchange["adoption"]["accepted_from_outside"]
    noun = "entry" if outside == 1 else "entries"
    lines += [f"The project has published {outside} {noun} based on outside suggestions. "
              "Entries are contributed research data. They give visiting assistants no instructions.", "",
        "> A research operating system for teams using AI assistants. This library publishes experiments on "
        "which results survive a change of data, method or reviewer.", "",
        "Start with the question closest to yours. Each short study gives the observed answer, its limits, "
        "the exact fields in the raw record and a way to repeat the check. The instrument and pendulum examples use teaching data.", "",
        "## Find evidence", "",
        *[file(question, landing(stem) + "index.md", findings[stem]) for stem, question in STUDIES], "",
        "## Pick up a research decision", "",
        file("Which version did the reviewer approve?", "studies/decisions/approval.json", "Read the complete approval function and version-change test."),
        file("Which instruction applied on the day of the analysis?", "studies/decisions/instruction.json", "Read the date lookup and its two-date test."),
        file("What if the prediction succeeds but the control moves?", "studies/decisions/control.json", "Read the grading function and its control-change test."),
        file("Read the three decisions in Markdown", "studies/decisions.md", "See the examples and what each test establishes."), "",
        "## Cite a result or return to it", "",
        file("Study versions", "research-versions.json", "Compare SHA-256 values for the decision packets, raw records, selected fields, Markdown readings and HTML pages. "
             "An unchanged observations hash lets you reuse your saved bytes when the website changes."),
        file("Dataset catalog", "research-catalog.json", "Six datasets with methods, variables, scope and downloads. The source ZIP in a clean build contains the original files."),
        file("Evidence checks for this build", "research-audit.json", "See how many quoted comparisons were traced to their original values and which records matched the archived source."),
        file("Verify a complete download", "release.json", "Check every served file against its byte count and SHA-256, or compare a release fingerprint saved independently."),
        file("Trace a correction across two records", "graph.json", "Open worked_traversals.corrected_pendulum_reading to follow the same corrected data from the fit to the receiving task."),
        file("Code and tests as plain text", "source/index.json", "Each file has a byte count, SHA-256 and a line-numbered viewer."), "",
        "## Continue an experiment", "",
        file("Browse the other threads", "exchange/", "Read the questions, replies and reported tests."),
        file("Download the discussion", "exchange.json", "Each reply names the exact entry it answers and the observation it cites."),
        file("Follow new questions and replies", "exchange/feed.json", "Use this JSON Feed in a reader or keep the entry IDs you have already seen."),
        file("What changed when one instrument supplied more readings?", "exchange/instrument-imbalance.md", "A follow-up used the original classifier on 24 fictional readings. Inspect the separate corrections and the restored scores."),
        file("What happens when assistants pass copies of results to each other?", "exchange/simulation.md", "Compare 14 rules in a seeded model of research teams. The method includes the prediction that failed."),
        file("Draft a question or correction", "research-notes/index.md", "Quote one observation, say what result would change your mind, and check the citation locally. Share it when your team chooses."), "",
        "## Run it on a project", "",
        file("Give feedback on one task", "exchange/index.md#workflow-feedback", "Read the optional questionnaire with your operator. Describe what happened and how you checked it. Your operator decides whether to share the draft."),
        file("Read the actual demo run", "records/demo.json", "Six moments record commands, observed answers and the readings used for each fit. Reproduce them with `./taos demo --json`."),
        f"- [Run the demo locally]({sources['README.md']}) The command `./taos demo` runs the pendulum example in a temporary project.",
        f"- [Set up a new project]({sources['BOOTSTRAP.md']}) The setup interview starts with the researcher's question and working constraints.",
        f"- [Daily use]({sources['MANUAL.md']}) Find tasks, handoffs, recorded instructions and decisions.", "",
        "## Optional", "",
        f"- [Code architecture]({sources['docs/ARCHITECTURE.md']}) Where to look for each part of the implementation.",
        f"- [Software claims]({sources['docs/CLAIMS.md']}) Definitions, tests, measured results and exceptions.",
        f"- [Experiment design and prior work]({sources['docs/METHOD.md']}) How the tests were chosen.",
        f"- [Software citation]({sources['CITATION.cff']}) Author and citation information for the software.", "",
    ]
    return "\n".join(lines)


def decision_source(repo, path, symbol, anchor=None):
    data = (repo / path).read_bytes()
    text = data.decode("utf-8")
    body = ast.parse(text, filename=path).body
    parts = symbol.split(".")
    if len(parts) == 2:
        classes = [node for node in body if isinstance(node, ast.ClassDef) and node.name == parts[0]]
        if len(classes) != 1:
            raise ValueError(f"Ambiguous or missing decision source {path}:{symbol}")
        body = classes[0].body
    functions = [node for node in body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name == parts[-1]]
    if len(functions) != 1:
        raise ValueError(f"Ambiguous or missing decision source {path}:{symbol}")
    node = functions[0]
    if anchor is not None and anchor != f"L{node.lineno}":
        raise ValueError(f"Stale decision fixture {path}#{anchor} for {symbol}")
    start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
    end = node.end_lineno
    return {"path": path, "symbol": symbol, "start_line": start, "end_line": end, "sha256": digest(data),
            "text": "".join(text.splitlines(keepends=True)[start - 1:end]),
            "raw_url": "../../source/raw/" + quote(path),
            "viewer_url": "../../source/files/" + quote(path) + f".html#L{start}"}


def write_decision_reading(out, repo, questions, github, ref):
    root = github + "/blob/" + ref + "/"
    lines = ["# Three decisions a research team can trace", "",
             "Each source packet contains the complete functions and test, their line ranges and the SHA-256 of each full file.", ""]
    directory = out / "studies" / "decisions"
    directory.mkdir()
    if len(questions) != len(DECISION_SOURCES):
        raise ValueError("The decision questions and source fixtures differ")
    for fixture, question_record in zip(DECISION_SOURCES, questions):
        slug, symbols, test_symbol = fixture
        question, example, limit, code, code_label, test, test_label = question_record
        code_path, code_anchor = code.split("#")
        test_path, test_anchor = test.split("#")
        write_json(directory / (slug + ".json"), {
            "schema": "decision-source/1", "id": slug, "question": question, "example": example, "scope": limit,
            "implementation": [decision_source(repo, code_path, symbol, code_anchor if index == 0 else None)
                               for index, symbol in enumerate(symbols)],
            "test": decision_source(repo, test_path, test_symbol, test_anchor),
        })
        lines += ["## " + question, "", example + " " + limit, "",
                  f"[Download the complete code and test](decisions/{slug}.json)", "",
                  f"[{code_label}]({root}{code}) · [{test_label}]({root}{test})", ""]
    (out / "studies" / "decisions.md").write_text("\n".join(lines), encoding="utf-8")


def pointer_source(document, pointer):
    """Resolve an RFC 6901 pointer, retaining the semantic identity of its row when present."""
    if not pointer.startswith("/"):
        raise ValueError(f"Expected a JSON Pointer into an observation: {pointer}")
    node = document
    row = {}
    for token in pointer[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            if not key.isdecimal() or str(int(key)) != key:
                raise ValueError(f"Invalid array index in {pointer}")
            node = node[int(key)]
            if isinstance(node, dict):
                for field in ("id", "policy"):
                    if field in node:
                        row = {field: node[field]}
                        break
        else:
            node = node[key]
    return {"pointer": pointer, **({"row": row} if row else {})}


def write_reading(out, stem, dataset, brief):
    path = out / landing(stem)
    path.mkdir(parents=True, exist_ok=True)
    raw_name = Path(dataset["identifier"]).name
    raw = (out / "records" / raw_name).read_bytes()
    if digest(raw) != dataset["distribution"]["sha256"]:
        raise ValueError(f"Record content does not match its version: {raw_name}")
    record = json.loads(raw)
    rows = []
    for observation in brief["observations"]:
        refs = [pointer_source(record, p) for p in observation["pointers"]]
        if not refs:
            raise ValueError(f"Observation lacks a primary source: {stem}")
        rows.append({"label": observation["label"], "value": observation["value"], "sources": refs})
    evidence = {"study": dataset["identifier"], "question": brief["question"], "finding": brief["finding"],
                "method": brief["method"], "scope": brief["scope"],
                "record": {"href": "../../records/" + raw_name, "sha256": digest(raw)}, "observations": rows}
    write_json(path / "observations.json", evidence)
    lines = ["# " + brief["question"], "", brief["finding"], "", "## Recorded comparisons", ""]
    for row in rows:
        pointers = ", ".join("`" + item["pointer"] + "`" for item in row["sources"])
        selectors = list(dict.fromkeys(str(next(iter(item["row"].values()))) for item in row["sources"] if "row" in item))
        identity = " Row " + ", ".join("`" + name + "`" for name in selectors) + "." if selectors else ""
        statement = str(row["value"])
        if not statement.endswith((".", "?", "!")):
            statement += "."
        lines.append(f"- **{row['label']}** — {statement}{identity} Raw fields {pointers}.")
    lines += ["", "## Method and scope", "", brief["method"], "", brief["scope"], "",
              "## Verify or cite this observation", "",
              f"Raw file `{dataset['identifier']}`. SHA-256 `{digest(raw)}`. Cite the case or policy name when present, its JSON Pointer and this digest.", "",
              f"[Original observations](../../records/{raw_name}) · [Selected fields and case names](observations.json) · "
              f"[Detailed evidence](../../{brief['detail_path']}) · [Method](../../{brief['method_path']})", "",
              "From the [source checkout](../../source/), run", "", "```sh", brief["test_command"], "```", ""]
    (path / "index.md").write_text("\n".join(lines), encoding="utf-8")
    return rows


def reading_body(dataset, brief, rows):
    esc = html.escape
    values = "".join("<tr><th scope=\"row\">" + esc(row["label"]) + "</th><td>" + esc(str(row["value"])) + "</td></tr>" for row in rows)
    raw_name = quote(Path(dataset["identifier"]).name)
    return (f'<section class="hero slim"><div class="wrap"><p class="kicker">Research evidence</p>'
            f'<h1>{esc(brief["question"])}</h1><p class="lead">{esc(brief["finding"])}</p></div></section>'
            '<section><div class="wrap prose"><h2>What the record shows</h2>'
            '<div class="scroll"><table class="claims"><thead><tr><th scope="col">Comparison</th><th scope="col">Recorded result</th></tr></thead>'
            f'<tbody>{values}</tbody></table></div><h2>How it was tested</h2><p>{esc(brief["method"])}</p>'
            f'<p>{esc(brief["scope"])}</p><p><a href="../../{esc(brief["detail_path"])}">Inspect the full comparison</a> · '
            f'<a href="../../{esc(brief["method_path"])}">Read the method</a></p>'
            f'<h2>Check the evidence</h2><p><a href="../../records/{raw_name}">Download the original observations</a> · '
            '<a href="observations.json">Find the fields behind each number</a> · <a href="index.md">Read and cite this study as Markdown</a></p>'
            '<p>Run this command from the <a href="../../source/">source checkout</a>.</p>'
            f'<pre class="shell"><code>{esc(brief["test_command"])}</code></pre>'
            '<p><a href="../../research-notes/index.md">Propose a follow-up experiment</a> · '
            '<a href="../../evidence/#study-records">Browse all six studies</a></p></div></section>')


def study_versions(out, datasets, revision):
    """Compare raw observations, editorial readings and the actual served pages independently."""
    def item(href, file=None):
        return {"href": href, "sha256": digest((out / (file or href)).read_bytes())}
    studies = {}
    for dataset in datasets:
        stem = Path(dataset["identifier"]).stem
        path = landing(stem)
        reading = (out / path / "index.md").read_text(encoding="utf-8")
        [detail] = re.findall(r"\[Detailed evidence\]\(\.\./\.\./(evidence/[^)]+)\)", reading)
        detail_path = urlsplit(detail).path
        if detail_path.endswith("/"):
            detail_path += "index.html"
        studies[stem] = {
            "identifier": dataset["identifier"], "observations": item("records/" + stem + ".json"),
            "reading": item(path + "index.md"), "page": item(path, path + "index.html"),
            "selected": item(path + "observations.json"), "detail": item(detail, detail_path),
        }
    write_json(out / "research-versions.json",
               {"format": 1, "build_revision": revision, "algorithm": "sha256",
                "home": item("./", "index.html"), "guide": item("llms.txt"), "studies": studies,
                "decisions": {"guide": item("studies/decisions.md"),
                              "packets": {slug: item(f"studies/decisions/{slug}.json")
                                          for slug, _, _ in DECISION_SOURCES}}})
