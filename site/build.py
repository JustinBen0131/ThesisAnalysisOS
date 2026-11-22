#!/usr/bin/env python3
"""Build the public page from the repository's own records.

Nothing on the page is typed in twice. The run it steps through is the output
of `./taos demo`, captured when the page is built. Every number is read from
`evals/results/`, and every claim from `docs/CLAIMS.md` with the standing
`evals/claims.py` gives it. The build stops if a recorded run no longer
stands, if the demo stops printing a line the page explains, or if a link
inside the page leads nowhere.

Each page is written twice from one source: as HTML for a person and as
Markdown for an agent, with `llms.txt`, `claims.json` and `standing.json`
beside them. `standing.json` lists the files the page was built from, by
hash, so the page can ask the repository whether it still holds.

    python3 site/build.py                         writes ./_site, links to main
    python3 site/build.py --out DIR --ref REVISION --url https://example.org/
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "evals"))
sys.path.insert(0, str(REPO))

import claims as read_back  # noqa: E402  (evals/claims.py)
import measured  # noqa: E402

NAME = "JustinBen0131/ThesisAnalysisOS"
GITHUB = "https://github.com/" + NAME
STANDS_ON = ["evals/results/at_revision.json", "evals/results/mutations.json", "evals/results/reuse_frontier.json",
             "docs/CLAIMS.md", "taos_core/demo.py", "taos_core/basis.py", "taos_core/gates.py"]
DESCRIPTION = ("An operating layer for research done with AI agents. Every result is kept with what it stood on, "
               "so it can be asked later whether it still holds.")

# The seven moments, in the order the demo prints them. `first` and `last` are the lines that bound each one.
STEPS = [
    {"short": "Recorded", "title": "A result is recorded", "answer": "holds", "code": "taos_core/gates.py",
     "first": "$ taos gate run --task PEN-1", "last": "    PEN-1 stands as recorded",
     "text": "An agent runs the check and closes the task. The pass is stored with a fingerprint of the files the check "
             "depends on, and the closure with the instructions in force. Asked now, both hold. Read the last line too. "
             "A check passing is not a person accepting."},
    {"short": "Unrelated edit", "title": "Something else changes", "answer": "holds", "code": "taos_core/basis.py",
     "first": "The plot style is edited", "last": "    PEN-1 stands as recorded",
     "text": "The plot style is edited. The check never read it, so nothing is rerun and nothing is doubted. A rule "
             "that trusts results by age would have had to guess here."},
    {"short": "Input changes", "title": "An input changes", "answer": "stale", "code": "taos_core/basis.py",
     "first": "One swing is measured again", "last": "    PEN-1 does not stand as recorded",
     "text": "One swing is measured again. The old pass is still true about the old data. It no longer answers for the "
             "new data, so the answer is stale, and it names the file that moved."},
    {"short": "Shared", "title": "A second task asks the same question", "answer": "holds", "code": "taos_core/gates.py",
     "section": "2",
     "text": "The check is run again on the new data. Then another agent's task needs the same check on the same files. "
             "A result belongs to the files it tested, not to the task that asked, so it is held and not run twice."},
    {"short": "Instructions", "title": "An instruction keeps its date", "answer": "stale", "code": "taos_core/rules.py",
     "section": "3",
     "text": "A person replaces an instruction. Both are kept, each with the day it was said, so what governed on any "
             "date can still be answered. Work closed under the old words is marked stale against the new ones, and the "
             "new ones are quoted as the person said them."},
    {"short": "Acceptance", "title": "Accepted means this version", "answer": "stale", "code": "taos_core/tasks.py",
     "section": "4", "last": "    stale    acceptance",
     "text": "A person reads the result and accepts it. That acceptance is for these exact files and instructions. A "
             "comment added afterwards does not inherit it."},
    {"short": "Isolation", "title": "A check passes only on what it declared", "answer": "fails", "code": "taos_core/gates.py",
     "section": "5", "last": "    ok    style",
     "text": "A second check says it depends only on the analysis and quietly reads the figure style. Marked isolated, "
             "it runs in an empty folder that holds only what it declared, so the hidden input is not there to be read. "
             "It fails until the declaration is corrected."},
]

USES = [
    ("Checks", "A pass holds for as long as the files it tested are the same.", "taos_core/gates.py"),
    ("Closing work", "One enforcement point. No route to done goes around it.", "taos_core/lifecycle.py"),
    ("Instructions", "Kept by date and scope, in the person's own words.", "taos_core/rules.py"),
    ("Lessons", "A correction shown to an agent is counted apart from a mistake repeated.", "taos_core/lessons.py"),
    ("Acceptance", "By a person, of one exact version.", "taos_core/standing.py"),
    ("Handoffs", "What the next session is told, and whether it is still true.", "taos_core/handoff.py"),
    ("Changes to the system", "Say what a change will do before making it. Score it after.", "taos_core/changes.py"),
    ("This page", "Its numbers are read from the records, and it asks the repository if they moved.", "site/build.py"),
]

ANSWERS = [
    ("holds", "What it stood on is the same."),
    ("fails", "Checked as things are now, and it does not pass."),
    ("stale", "Something it stood on changed, and the change is named."),
    ("unknown", "It cannot be established. It is never rounded to anything else."),
]

LINEAGE = [
    ("Truth maintenance", "A belief is kept with its justification and withdrawn when the justification goes.",
     "Doyle 1979; de Kleer 1986"),
    ("Build systems", "Record what a result was made from and redo only what a change reached.",
     "Mokhov, Mitchell and Peyton Jones 2018"),
    ("Temporal databases", "When something was true is kept apart from when it was recorded.", "Snodgrass and Ahn 1985"),
    ("Provenance", "What a result was derived from is itself data.", "W3C PROV-DM 2013"),
    ("Hermetic builds", "A step can read only the inputs it declared.", "Bazel sandboxing; the Nix build sandbox"),
]

LIMITS = [
    "The evidence is mechanical. Nothing here shows that research comes out better.",
    "One synthetic workload and one laptop. The counts are counts, not a speed-up.",
    "In the open, what a check says it reads is trusted. Isolation closes that, at a cost per run.",
    "Isolation closes the network and the rest of the workspace on macOS only. Elsewhere the record says they were open.",
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


def demo_moments() -> List[List[str]]:
    """Run the demo and cut its output into the seven moments. A line the page explains must still be printed."""
    done = subprocess.run([sys.executable, str(REPO / "taos"), "demo"], cwd=str(REPO), capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit("./taos demo failed, so there is no run to show:\n" + done.stderr[-800:])
    lines = done.stdout.splitlines()

    def find(prefix: str, start: int) -> int:
        for index in range(start, len(lines)):
            if lines[index].startswith(prefix):
                return index
        raise SystemExit("./taos demo no longer prints a line starting {0!r}; update STEPS in site/build.py".format(prefix))

    moments, cursor = [], 0
    for step in STEPS:
        if "section" in step:
            first = find(step["section"] + ". ", cursor) + 1
            nxt = str(int(step["section"]) + 1) + ". "
            last = next((index for index in range(first, len(lines)) if lines[index].startswith(nxt)), len(lines)) - 1
            if "last" in step:
                last = find(step["last"], first)
        else:
            first = find(step["first"], cursor)
            last = find(step["last"], first)
        chosen = lines[first:last + 1]
        while chosen and not chosen[0].strip():
            chosen = chosen[1:]
        while chosen and not chosen[-1].strip():
            chosen = chosen[:-1]
        moments.append(chosen)
        cursor = last + 1
    return moments


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
    return {
        "ref": ref, "revision": git("rev-parse", "HEAD") or "unknown",
        "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        "runs": runs, "rows": rows, "moments": demo_moments(), "sections": claims_file(),
        "reuse": reuse, "finest": finest, "aged": aged, "hidden": hidden, "alone": alone, "refused": refused,
        "everything": by_policy["rerun everything"],
        "oracle": next(row for row in reuse["rows"] if row["policy"].startswith("oracle")),
        "cases": at["here"]["ran"], "cases_pass": at["here"]["ran"] - at["here"]["did_not_pass"],
        "first_release": first_release[0], "first_release_failed": first_release[1]["did_not_pass"],
        "faults": runs["mutations"]["faults"], "caught": runs["mutations"]["caught"],
        "stands_on": [{"path": path, "blob": blob(REPO / path)} for path in STANDS_ON],
    }


# ---------------------------------------------------------------- the page for a person

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
<meta name="twitter:card" content="summary">
$canonical<link rel="stylesheet" href="${root}assets/style.css">
<link rel="icon" href="${root}assets/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="text/markdown" href="index.md" title="This page as Markdown">
<link rel="alternate" type="text/plain" href="${root}llms.txt" title="For language models and agents">
<script type="application/ld+json">$linked</script>
</head>
<body>
<a class="skip" href="#main">Skip to the content</a>
<header class="top"><div class="wrap">
<a class="mark" href="${root}">ThesisAnalysisOS</a>
<nav aria-label="Main">
<a href="${root}#run">A real run</a>
<a href="${root}evidence/">Evidence</a>
<a href="${root}#agents">For agents</a>
<a class="repo" href="$github">GitHub<span aria-hidden="true"> &#8599;</span></a>
</nav>
</div></header>
<main id="main">
$body
</main>
<footer class="foot"><div class="wrap">
<p id="standing" data-src="${root}standing.json"><span class="lead-in">This page</span> $neutral was built from revision
<a href="$github/commit/$revision"><code>$short</code></a> on $built. <span class="nojs">Open it with scripts on and it asks the repository
whether the files it was built from have changed.</span></p>
<p class="small">ThesisAnalysisOS is an independent research prototype by Justin Bennett, generalized from the operating
layer of a physics thesis analysis run with two AI agents. It is not affiliated with any employer or product.
PolyForm Noncommercial 1.0.0, with additional permissions.
<a href="$github">Repository</a> &middot; <a href="${root}llms.txt">llms.txt</a> &middot; <a href="index.md">This page as Markdown</a></p>
</div></footer>
<script src="${root}assets/site.js" defer></script>
</body>
</html>
""")


def shell(ctx: Dict[str, Any], root: str, title: str, body: str, url: str, path: str) -> str:
    linked = {"@context": "https://schema.org", "@type": "SoftwareSourceCode", "name": "ThesisAnalysisOS",
              "description": DESCRIPTION, "codeRepository": GITHUB, "programmingLanguage": "Python",
              "license": GITHUB + "/blob/main/LICENSE", "author": {"@type": "Person", "name": "Justin Bennett"}}
    return SHELL.substitute(
        title=esc(title), description=esc(DESCRIPTION), root=root, github=GITHUB, body=body,
        canonical='<link rel="canonical" href="{0}">\n'.format(esc(url + path)) if url else "",
        linked=json.dumps(linked).replace("</", "<\\/"), revision=esc(ctx["revision"]), short=esc(ctx["revision"][:7]),
        built=esc(ctx["built"]), neutral=chip("unknown", "not asked yet"))


def source(ctx: Dict[str, Any], path: str, label: Optional[str] = None) -> str:
    return '<a class="src" href="{0}/blob/{1}/{2}"><code>{3}</code></a>'.format(GITHUB, esc(ctx["ref"]), esc(path), esc(label or path))


def bars(ctx: Dict[str, Any]) -> str:
    aged = [("Rerun when older than {0} asks".format(row["policy"].split()[4]), row) for row in ctx["aged"]]
    shown = ([("Rerun everything, every time", ctx["everything"])] + aged
             + [("Reuse by basis, inputs declared", ctx["finest"]), ("An oracle that knows what each check reads", ctx["oracle"]),
                ("Reuse by basis, every check hiding one input", ctx["hidden"])])
    most_run = max(row["executions"] for _, row in shown)
    most_wrong = max(row["wrong"] for _, row in shown) or 1
    lines = []
    for label, row in shown:
        mark = ' class="ours"' if row is ctx["finest"] else ""
        lines.append(
            '<tr{0}><th scope="row">{1}</th>'
            '<td><span class="bar run" style="width:{2:.1f}%"></span><span class="n">{3}</span></td>'
            '<td>{4}<span class="n{6}">{5}</span></td></tr>'.format(
                mark, esc(label), 100.0 * row["executions"] / most_run, row["executions"],
                '<span class="bar wrong" style="width:{0:.1f}%"></span>'.format(100.0 * row["wrong"] / most_wrong) if row["wrong"] else "",
                row["wrong"], " zero" if row["wrong"] == 0 else ""))
    return ('<table class="bars"><thead><tr><th scope="col">Policy</th><th scope="col">Checks executed</th>'
            '<th scope="col">Stale results relied on</th></tr></thead><tbody>{0}</tbody></table>').format("".join(lines))


def home(ctx: Dict[str, Any]) -> str:
    moments = ctx["moments"]
    before = next(line for line in moments[0] if "check fit" in line)
    after = next(line for line in moments[2] if "check fit" in line)
    steps = []
    for number, (step, lines) in enumerate(zip(STEPS, moments), 1):
        steps.append(
            '<article class="step" id="run-{0}" data-short="{1}">'
            '<div class="term" role="group" aria-label="Recorded output"><pre>{2}</pre></div>'
            '<div class="tell"><p class="count">{0} of {3}</p><h3>{4}</h3><p>{5}</p>'
            '<p class="answer">{6} {7}</p></div></article>'.format(
                number, esc(step["short"]), terminal(lines), len(STEPS), esc(step["title"]), esc(step["text"]),
                chip("holds" if step["answer"] == "fails" else step["answer"],
                     "fails, then holds" if step["answer"] == "fails" else None),
                source(ctx, step["code"])))
    uses = "".join('<li><h3>{0}</h3><p>{1}</p>{2}</li>'.format(esc(name), esc(text), source(ctx, path)) for name, text, path in USES)
    answers = "".join("<li>{0}<span>{1}</span></li>".format(chip(state), esc(text)) for state, text in ANSWERS)
    lineage = "".join("<li><strong>{0}.</strong> {1} <span class=\"cite\">{2}</span></li>".format(esc(a), esc(b), esc(c))
                      for a, b, c in LINEAGE)
    reuse, refused = ctx["reuse"], ctx["refused"]
    upkeep = reuse["timing"]["upkeep"]
    small, large = upkeep[0], upkeep[-1]
    held = sum(1 for item in reuse["predictions"].values() if item["held"])
    added = reuse["timing"].get("isolating_one_execution")
    cost = ("" if not added else " Isolating one check added {0:.1f} ms, the median of {1} paired runs.".format(
        1000 * added["median_seconds"], added["pairs"]))
    return Template("""
<section class="hero"><div class="wrap">
<div class="pitch">
<p class="kicker">Research software &middot; Justin Bennett</p>
<h1>What still holds?</h1>
<p class="lead">Research keeps moving under its own results. A check that passed last month is a fact about last month.
ThesisAnalysisOS keeps every result an agent records together with what it stood on, so it can be asked later whether it
still stands. It answers <em>holds</em>, <em>fails</em>, <em>stale</em> or <em>unknown</em>, and says why.</p>
<p class="actions"><a class="button" href="#run">Step through a real run</a>
<a class="plain" href="$github">Read the code on GitHub<span aria-hidden="true"> &#8599;</span></a></p>
<p class="small">Python standard library only. No network and no model calls. It runs in a minute.</p>
</div>
<figure class="specimen">
<div class="term"><pre>$specimen</pre></div>
<figcaption>Real output. The same check on the same task, before and after one input was measured again.</figcaption>
</figure>
</div></section>

<section id="run"><div class="wrap">
<p class="kicker">01 / A recorded run</p>
<h2>Seven moments from one small measurement</h2>
<p class="intro">Six pendulum swings, a fit for g, and a check that the fit is sane. Two agents work on it. Everything in
the dark panels is output from <code>./taos demo</code>, captured when this page was built. Nothing was typed in.</p>
<div class="stepper">$steps</div>
</div></section>

<section id="idea"><div class="wrap">
<p class="kicker">02 / The idea</p>
<h2>One comparison, used for everything</h2>
<div class="two">
<div><p>A record is a statement, who made it, and what it stood on. Asking is one comparison between that basis and the
present. There are four answers.</p>
<ul class="answers">$answers</ul></div>
<div><p>Three rules follow, and none of them depends on which model is doing the work.</p>
<ol class="rules">
<li><strong>Validity is the basis, not the age.</strong> A pass from last month holds if nothing it tested has changed. A pass from a minute ago does not if something has.</li>
<li><strong>The original words outrank any summary of them.</strong> An instruction is kept as the person said it, with its date.</li>
<li><strong>An observation has a kind and a source.</strong> Shown is not repeated. Recommended is not executed. A check passing is not a person accepting.</li>
</ol></div>
</div>
<h3 class="sub">Where the same comparison is used</h3>
<ul class="uses">$uses</ul>
</div></section>

<section id="evidence"><div class="wrap">
<p class="kicker">03 / Evidence</p>
<h2>Measured, with the limits beside the numbers</h2>
<ul class="stats">
<li><b>$cases_pass of $cases</b><span>known failure cases pass here. $first_failed of them fail at the first release, <code>$first_release</code>.</span></li>
<li><b>$caught of $faults</b><span>protections, removed one at a time, are noticed by the tests.</span></li>
<li><b>$holding of $claims</b><span>claims hold when read back against the code. A build of this page stops if one does not.</span></li>
</ul>
<figure class="experiment">
<figcaption><strong>When is a recorded result safe to reuse?</strong> $edits edits to a small tree, and after each one all
$checks checks are relied on: $relied results in all. A policy can spend executions, or rely on a stale result.</figcaption>
$bars
<p class="note">Reusing by basis executed what an oracle would and relied on nothing stale. An age limit buys fewer
executions with stale results. The last row is the limit of the design in the open: a check that reads what it did not
declare is reused wrongly. Run isolated, the same checks ran $refused_runs times and never passed, so nothing was
reused.$cost $held of $predictions predictions were written down before the runs, and all of them held.</p>
</figure>
<div class="two">
<div><h3 class="sub">What this does not show</h3><ul class="limits">$limits</ul></div>
<div><h3 class="sub">What asking costs</h3>
<p>Keeping a record is not free. Its basis is fingerprinted each time it is asked. On a $small_files-file tree that took
$small_ms ms, so reuse paid for any check slower than $small_even ms. On a $large_files-file tree it took $large_ms ms,
and reuse paid only for checks slower than $large_even ms.</p>
<p><a class="more" href="evidence/">Every claim, with the code and the test behind it</a></p></div>
</div>
</div></section>

<section id="lineage"><div class="wrap">
<p class="kicker">04 / Where it comes from</p>
<h2>Old ideas, applied to what research rests on</h2>
<div class="two">
<div><p>Nothing here is a new primitive.</p><ul class="lineage">$lineage</ul>
<p>What is added is what a research project rests on and a build system does not model: an instruction with its date, and
a person's acceptance of one exact version.</p></div>
<div><p>The cost question came from physics. A transport network is priced with a two-term ledger: carrying flow costs
less as structure is added, and the structure costs upkeep. A recorded result has the same two terms. Upkeep is
fingerprinting what it stood on. Transport is running the check again. The ledger says structure stops paying once it
matches what is really read, and the measurement agrees: declaring 6 domains or 12 saved the same work. Nothing here
claims that agent work obeys a physical scaling law.</p>
<p>The system was not designed at a desk. It is what survived a year of a physics thesis analysis run with two AI agents,
generalized so that it carries no physics.
<a href="$github/blob/$ref/docs/METHOD.md">The method, the predictions and the prior work</a>.</p></div>
</div>
</div></section>

<section id="agents"><div class="wrap">
<p class="kicker">05 / For agents</p>
<h2>This page is also a file you can read</h2>
<div class="two">
<div><p>Everything above exists as plain text, built from the same source in the same run. An agent does not have to parse
this page, and should not take its word either. It is built to be checked.</p>
<p>In the repository, <code>AGENTS.md</code> says how to examine the system without setting it up, and one command reads
every claim back against the code.</p>
<pre class="shell">python3 evals/claims.py --json</pre></div>
<ul class="files">
<li><a href="llms.txt"><code>/llms.txt</code></a><span>What this is, and where to go next.</span></li>
<li><a href="index.md"><code>/index.md</code></a><span>This page as Markdown, with the run as text.</span></li>
<li><a href="claims.json"><code>/claims.json</code></a><span>Every claim, its standing, and how to check it.</span></li>
<li><a href="standing.json"><code>/standing.json</code></a><span>The files this page was built from, by hash.</span></li>
<li><a href="records/reuse_frontier.json"><code>/records/</code></a><span>The measurements, as recorded.</span></li>
</ul>
</div>
</div></section>

<section id="start"><div class="wrap">
<p class="kicker">06 / Start</p>
<h2>See it in a minute</h2>
<div class="two">
<div><pre class="shell">git clone $github.git
cd ThesisAnalysisOS
./taos demo</pre>
<p class="small">It builds a throwaway copy of the measurement and runs real commands against it. Nothing of yours is touched.</p></div>
<div><p>To run your own project on it, choose <strong>Use this template</strong> on GitHub and follow the manual. Setup is
an interview: an agent asks a short set of questions and builds the system from your answers.</p>
<p class="actions"><a class="button" href="$github">Open the repository<span aria-hidden="true"> &#8599;</span></a>
<a class="plain" href="$github/blob/$ref/MANUAL.md">Read the manual</a></p></div>
</div>
</div></section>
""").substitute(
        github=GITHUB, ref=esc(ctx["ref"]), specimen=terminal([before, after]), steps="".join(steps), answers=answers, uses=uses,
        cases=ctx["cases"], cases_pass=ctx["cases_pass"], first_failed=ctx["first_release_failed"],
        first_release=esc(ctx["first_release"]), caught=ctx["caught"], faults=ctx["faults"],
        holding=sum(1 for row in ctx["rows"] if row["state"] == "holds"), claims=len(ctx["rows"]),
        edits=reuse["edits"], checks=reuse["checks"], relied=reuse["relied_on"], bars=bars(ctx),
        refused_runs=refused["executions"], cost=esc(cost), held=held, predictions=len(reuse["predictions"]),
        limits="".join("<li>{0}</li>".format(esc(text)) for text in LIMITS), lineage=lineage,
        small_files="{0:,}".format(small["files"]), small_ms="{0:.0f}".format(1000 * small["seconds"]),
        small_even="{0:.0f}".format(1000 * small["break_even_check_seconds"]),
        large_files="{0:,}".format(large["files"]), large_ms="{0:.0f}".format(1000 * large["seconds"]),
        large_even="{0:.0f}".format(1000 * large["break_even_check_seconds"]))


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
                body.append("<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}<span class=\"kind\">{4}</span></td></tr>".format(
                    inline(claim), inline(what), inline(how), state, esc(status) if found else ""))
            parts.append('<div class="scroll"><table class="claims"><thead><tr>{0}</tr></thead><tbody>{1}</tbody></table></div>'.format(
                head, "".join(body)))
        if section["bullets"]:
            parts.append("<ul class=\"limits\">{0}</ul>".format("".join("<li>{0}</li>".format(inline(text)) for text in section["bullets"])))
    reuse = ctx["reuse"]
    rows = "".join("<tr><td>{0}</td><td class=\"num\">{1}</td><td class=\"num\">{2}</td></tr>".format(
        esc(row["policy"]), row["executions"], row["wrong"]) for row in reuse["rows"])
    predictions = "".join("<li>{0} <strong>{1}.</strong> {2}</li>".format(
        chip("holds" if item["held"] else "fails", "held" if item["held"] else "failed"), esc(key), esc(item["text"]))
        for key, item in sorted(reuse["predictions"].items()))
    holding = sum(1 for row in ctx["rows"] if row["state"] == "holds")
    return Template("""
<section class="hero slim"><div class="wrap">
<p class="kicker">Evidence</p>
<h1>Every claim, read back</h1>
<p class="lead">This is <a href="$github/blob/$ref/docs/CLAIMS.md"><code>docs/CLAIMS.md</code></a>, with one addition. When
the page was built, each row was checked against the code: a tested row names code and a test that exist, and a measured
row quotes a number its recorded run contains and that run still stands. $holding of $claims hold. Had one not, the build
would have stopped.</p>
<p class="small">Check it yourself in the repository with <code>python3 evals/claims.py</code>.</p>
</div></section>
<section><div class="wrap prose">$parts</div></section>
<section><div class="wrap prose">
<h2>The reuse experiment in full</h2>
<p>$edits edits, $checks checks over $folders folders, seed $seed. After each edit every check is relied on, $relied
results in all. A wrong reuse is a result relied on after a file it reads changed. Python $python on $platform.</p>
<div class="scroll"><table class="claims"><thead><tr><th scope="col">Policy, as recorded</th><th scope="col">Executions</th>
<th scope="col">Wrong reuses</th></tr></thead><tbody>$rows</tbody></table></div>
<h3 class="sub">Predictions, written before the runs</h3>
<ul class="predictions">$predictions</ul>
<p><a class="more" href="../records/reuse_frontier.json">The record itself</a> &middot;
<a class="more" href="$github/blob/$ref/evals/reuse_frontier.py">The script that wrote it</a></p>
</div></section>
""").substitute(github=GITHUB, ref=esc(ctx["ref"]), holding=holding, claims=len(ctx["rows"]), parts="".join(parts),
                edits=reuse["edits"], checks=reuse["checks"], folders=reuse["folders"], seed=reuse["seed"],
                relied=reuse["relied_on"], python=esc(reuse["environment"]["python"]),
                platform=esc(reuse["environment"]["platform"]), rows=rows, predictions=predictions)


# ---------------------------------------------------------------- the same page for an agent

def home_markdown(ctx: Dict[str, Any], url: str) -> str:
    reuse = ctx["reuse"]
    out = ["# ThesisAnalysisOS: what still holds?", "",
           "> " + DESCRIPTION, "",
           "Research keeps moving under its own results. A check that passed last month is a fact about last month. "
           "ThesisAnalysisOS keeps every result an agent records together with what it stood on, so it can be asked later "
           "whether it still stands. It answers `holds`, `fails`, `stale` or `unknown`, and says why.", "",
           "- Repository: " + GITHUB,
           "- Built from revision `{0}` on {1}. Whether that still holds: compare `standing.json` with the repository.".format(
               ctx["revision"], ctx["built"]),
           "- Python standard library only. No network and no model calls.", "",
           "## A recorded run", "",
           "Output of `./taos demo`, captured when this page was built. Six pendulum swings, a fit for g, a check.", ""]
    for number, (step, lines) in enumerate(zip(STEPS, ctx["moments"]), 1):
        out += ["### {0}. {1}".format(number, step["title"]), "", step["text"], "", "```text"] + lines + ["```", "",
                "Code: `{0}`".format(step["code"]), ""]
    out += ["## The idea", "",
            "A record is a statement, who made it, and what it stood on. Asking is one comparison between that basis and the present.", ""]
    out += ["- `{0}`: {1}".format(state, text) for state, text in ANSWERS]
    out += ["", "1. Validity is the basis, not the age.", "2. The original words outrank any summary of them.",
            "3. An observation has a kind and a source. Shown is not repeated. Recommended is not executed. A check passing is not a person accepting.",
            "", "Where the same comparison is used:", ""]
    out += ["- {0}: {1} (`{2}`)".format(name, text, path) for name, text, path in USES]
    out += ["", "## Evidence", "",
            "- {0} of {1} known failure cases pass here; {2} fail at the first release `{3}`.".format(
                ctx["cases_pass"], ctx["cases"], ctx["first_release_failed"], ctx["first_release"]),
            "- {0} of {1} protections, removed one at a time, are noticed by the tests.".format(ctx["caught"], ctx["faults"]),
            "- {0} of {1} claims hold when read back against the code (`claims.json`).".format(
                sum(1 for row in ctx["rows"] if row["state"] == "holds"), len(ctx["rows"])), "",
            "Reuse experiment, {0} results relied on after {1} edits:".format(reuse["relied_on"], reuse["edits"]), "",
            "| Policy | Executions | Wrong reuses |", "|---|---|---|"]
    out += ["| {0} | {1} | {2} |".format(row["policy"], row["executions"], row["wrong"]) for row in reuse["rows"]]
    out += ["", "What this does not show:", ""] + ["- " + text for text in LIMITS]
    out += ["", "## Where it comes from", ""] + ["- {0}. {1} ({2})".format(a, b, c) for a, b, c in LINEAGE]
    out += ["", "## If you are an agent", "",
            "- Read `AGENTS.md` in the repository first. It says how to examine the system without setting it up.",
            "- `python3 evals/claims.py --json` reads every claim back against the code. Do not take this page's word.",
            "- `./taos demo` runs the measurement above in a throwaway folder. `./taos selftest` runs the tests.",
            "- To use it for a project, create a repository from the template and follow `BOOTSTRAP.md`.", "",
            "Files beside this one: `llms.txt`, `claims.json`, `standing.json`, `records/`, `evidence/index.md`.", ""]
    return "\n".join(out)


def evidence_markdown(ctx: Dict[str, Any]) -> str:
    out = ["# Evidence: every claim, read back", "",
           "Standing of each row of `docs/CLAIMS.md` at revision `{0}`, from `python3 evals/claims.py --json`.".format(ctx["revision"]), "",
           "| Standing | Claim | Reason |", "|---|---|---|"]
    out += ["| {0} | {1} | {2} |".format(row["state"], row["claim"].replace("|", "/"), row["reason"].replace("|", "/")) for row in ctx["rows"]]
    out += ["", "Full text with code, tests and what is not claimed: {0}/blob/{1}/docs/CLAIMS.md".format(GITHUB, ctx["ref"]), ""]
    return "\n".join(out)


def llms(ctx: Dict[str, Any], url: str) -> str:
    at = lambda path: (url + path) if url else path  # noqa: E731
    return "\n".join([
        "# ThesisAnalysisOS", "",
        "> " + DESCRIPTION + " It answers holds, fails, stale or unknown, and says why. Python standard library only; "
        "it never calls a network or a model.", "",
        "This site is built from the repository's own records, and each page has a Markdown twin. Do not take the site's "
        "word: `claims.json` gives every claim with its standing, and `python3 evals/claims.py --json` in the repository "
        "reads them back against the code.", "",
        "## Start here", "",
        "- [This page as Markdown]({0}): the idea, a recorded run, the evidence and its limits".format(at("index.md")),
        "- [AGENTS.md]({0}/blob/main/AGENTS.md): how to examine the repository without setting it up, or set it up for a person".format(GITHUB),
        "- [README]({0}/blob/main/README.md): what it is, in one screen".format(GITHUB), "",
        "## Check it", "",
        "- [claims.json]({0}): every claim, its standing at build time, and the command that checks it".format(at("claims.json")),
        "- [standing.json]({0}): the files this site was built from, by git blob hash".format(at("standing.json")),
        "- [Evidence as Markdown]({0}): standing of each claim".format(at("evidence/index.md")),
        "- [docs/CLAIMS.md]({0}/blob/main/docs/CLAIMS.md): each claim with its code, its test, and what is not claimed".format(GITHUB),
        "- [Recorded measurements]({0}): the reuse experiment as written by the script".format(at("records/reuse_frontier.json")), "",
        "## Understand it", "",
        "- [docs/METHOD.md]({0}/blob/main/docs/METHOD.md): the failures that led to the design, prior work, predictions".format(GITHUB),
        "- [docs/ARCHITECTURE.md]({0}/blob/main/docs/ARCHITECTURE.md): a map for reading the code cold".format(GITHUB),
        "- [taos_core/basis.py]({0}/blob/main/taos_core/basis.py): the one comparison everything else uses".format(GITHUB), "",
        "## Use it", "",
        "- [MANUAL.md]({0}/blob/main/MANUAL.md): daily use".format(GITHUB),
        "- [BOOTSTRAP.md]({0}/blob/main/BOOTSTRAP.md): the setup interview an agent runs for a person".format(GITHUB), "",
        "## Optional", "",
        "- [docs/SPEC.md]({0}/blob/main/docs/SPEC.md): exact behavior".format(GITHUB),
        "- [docs/LINEAGE.md]({0}/blob/main/docs/LINEAGE.md): what was tried and did not survive".format(GITHUB), ""])


# ---------------------------------------------------------------- write, then check what was written

LINK = re.compile(r'(?:href|src)="([^"]+)"')


def broken(out: Path) -> List[str]:
    """Links inside the built pages that lead to no file."""
    problems = []
    for page in sorted(out.rglob("*.html")):
        for target in LINK.findall(page.read_text(encoding="utf-8")):
            if re.match(r"^(https?:|mailto:|#|data:)", target):
                continue
            path = (page.parent / target.split("#")[0]).resolve() if target.split("#")[0] else page
            if path.is_dir():
                path = path / "index.html"
            if not path.is_file():
                problems.append("{0}: {1}".format(page.relative_to(out), target))
    return problems


def build(out: Path, ref: str, url: str) -> Dict[str, Any]:
    ctx = gather(ref)
    if out.exists():
        shutil.rmtree(str(out))
    (out / "evidence").mkdir(parents=True)
    (out / "records").mkdir()
    shutil.copytree(str(HERE / "assets"), str(out / "assets"))
    for name in read_back.RUNS:
        shutil.copy2(str(REPO / "evals" / "results" / (name + ".json")), str(out / "records" / (name + ".json")))
    write = lambda path, text: (out / path).write_text(text, encoding="utf-8")  # noqa: E731
    write("index.html", shell(ctx, "./", "ThesisAnalysisOS: what still holds?", home(ctx), url, ""))
    write("evidence/index.html", shell(ctx, "../", "Evidence: ThesisAnalysisOS", evidence(ctx), url, "evidence/"))
    base = "/" + "/".join(url.split("/")[3:]) if url else "/"      # a project page is served under the repository's name
    write("404.html", shell(ctx, base, "Not found: ThesisAnalysisOS",
                            '<section class="hero slim"><div class="wrap"><p class="kicker">404</p><h1>unknown</h1>'
                            '<p class="lead">Nothing is recorded at this address. <a href="{0}">Start from the front page</a>.</p>'
                            '</div></section>'.format(base), url, "404.html"))
    write("index.md", home_markdown(ctx, url))
    write("evidence/index.md", evidence_markdown(ctx))
    write("llms.txt", llms(ctx, url))
    write("claims.json", json.dumps({"repository": NAME, "revision": ctx["revision"], "built": ctx["built"],
                                     "check": "python3 evals/claims.py --json", "rows": ctx["rows"]}, indent=2, sort_keys=True) + "\n")
    write("standing.json", json.dumps({"repository": NAME, "branch": "main", "revision": ctx["revision"], "built": ctx["built"],
                                       "stands_on": ctx["stands_on"]}, indent=2, sort_keys=True) + "\n")
    write("robots.txt", "User-agent: *\nAllow: /\n" + ("Sitemap: {0}sitemap.xml\n".format(url) if url else ""))
    if url:
        write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
              + "".join("<url><loc>{0}{1}</loc><lastmod>{2}</lastmod></url>\n".format(url, path, ctx["built"]) for path in ("", "evidence/"))
              + "</urlset>\n")
    write(".nojekyll", "")
    problems = [problem for problem in broken(out) if not problem.startswith("404.html")]
    if problems:
        raise SystemExit("links that lead nowhere:\n  " + "\n  ".join(problems))
    return ctx


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the public page from the repository's records.")
    parser.add_argument("--out", default=str(REPO / "_site"))
    parser.add_argument("--ref", default="main", help="the revision that links to code point at")
    parser.add_argument("--url", default="", help="where the site will be served, ending in a slash")
    args = parser.parse_args(argv)
    ctx = build(Path(args.out), args.ref, args.url)
    print("built {0} from {1}: {2} moments, {3} claims hold, stands on {4} files".format(
        args.out, ctx["revision"][:7], len(ctx["moments"]), len(ctx["rows"]), len(ctx["stands_on"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
