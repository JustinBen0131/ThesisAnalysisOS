"""Render the pendulum audit from its recorded results and verified inputs."""

import hashlib
import json
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any, Dict, Optional


def load_audit(repo: Path) -> Dict[str, Any]:
    """Refuse to publish measurements whose recorded source bytes have changed."""
    root = repo.resolve()
    path = root / "evals/results/measurement_audit.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    sources = record.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("The measurement audit has no source fingerprints.")
    for name, expected in sources.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Invalid source path in measurement audit: {name!r}")
        source = (root / relative).resolve()
        source.relative_to(root)
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Measurement audit source missing or changed: {name}")
    # Matplotlib writes this PNG text chunk beside the plotted pixels.
    figure = root / "site/assets/pendulum-sensitivity.png"
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii")
    if b"tEXtSourceSHA256\0" + fingerprint not in figure.read_bytes():
        raise ValueError("The sensitivity figure needs regenerating from the recorded audit.")
    return record


def _boundary_example(boundaries: Optional[Dict[str, Any]]) -> str:
    if boundaries is None:
        return "The boundary controls compare rounded displays with the check on the unrounded fits."
    if boundaries.get("passed") is not True:
        raise ValueError("The pendulum boundary controls did not pass.")
    rows = {row["id"]: row for row in boundaries["six_swing_fit_controls"]}
    below, above = rows["below-lower-fit"], rows["above-lower-fit"]
    low, high = (float(row["measured_fit"]["g_m_s2"]) for row in (below, above))
    displayed = below["rounded_g_m_s2"]
    if (displayed != above["rounded_g_m_s2"] or displayed != f"{low:.2f}" or displayed != f"{high:.2f}"
            or (below["checker"]["exit"], above["checker"]["exit"]) != (1, 0)):
        raise ValueError("The pendulum boundary pair requires matching displays and opposite check outcomes.")
    return (f"Two fits both display as {escape(displayed)} m/s². Using the unrounded values, the check rejected "
            f"the fit near {low:.3f} m/s² and accepted the fit near {high:.3f} m/s².")


def audit_section(record: Dict[str, Any], boundaries: Optional[Dict[str, Any]] = None) -> str:
    """Show retained standing next to an independent calculation and a fresh run."""
    cases = record["cases"]
    by_id = {case["id"]: case for case in cases}
    if len(by_id) != len(cases):
        raise ValueError("Duplicate case ID in the measurement audit.")
    declarations = {"declared", "unclassified-input", "omitted-input"}
    states = ("holds", "stale", "unknown")
    for case in cases:
        if case["cohort"] not in declarations or case["retained"] not in states:
            raise ValueError(f"Unexpected measurement audit case: {case['id']}")

    declared = [case for case in cases if case["cohort"] == "declared"]
    changed = [case for case in declared if case["estimate_changed"]]
    unchanged = [case for case in declared if not case["estimate_changed"]]
    omitted = [case for case in cases if case["cohort"] == "omitted-input"]
    unclassified = [case for case in cases if case["cohort"] == "unclassified-input"]
    unclassified_unknown = sum(case["retained"] == "unknown" for case in unclassified)
    stale_changed = sum(case["retained"] == "stale" for case in changed)
    stale_unchanged = sum(case["retained"] == "stale" for case in unchanged)
    valid_reuses = [case for case in unchanged if case["retained"] == "holds" and case["fresh_exit"] == 0]
    held_omissions = sum(case["retained"] == "holds" and case["fresh_exit"] != 0 for case in omitted)
    agree = sum(case["oracle_agrees"] for case in cases)

    def case_link(identifier, label):
        case = by_id[identifier]
        return f'<a href="pendulum/#case-{escape(case["id"], quote=True)}">{escape(label)}</a>'

    reuse_names = {"baseline": "unchanged baseline", "style": "edit to the figure style"}
    reuse_examples = ", ".join(case_link(case["id"], reuse_names.get(case["id"], _edit_label(case["id"])))
                              for case in valid_reuses)
    examples = (
        ("baseline", "Original six swings"),
        ("scale-1.001", "All periods increased by 0.1%"),
        ("scale-1.02", "All periods increased by 2%"),
        ("unclassified-1.02", "Same 2% increase, no input group lists the data"),
        ("omission-1.02", "Same 2% increase, the fit omits the data group"),
    )
    rows = []
    for identifier, label in examples:
        case = by_id[identifier]
        state = escape(case["retained"])
        gate = "pass" if case["fresh_exit"] == 0 else "fail"
        result = f'{float(case["g"]):.4f} ± {float(case["se"]):.4f}'
        rows.append(
            f'<tr><th scope="row">{case_link(identifier, label)}</th><td>{escape(result)}</td>'
            f'<td><span class="chip {state}">{state}</span></td><td>{gate}</td></tr>'
        )

    return f"""
<section id="measurement-audit" class="measurement-audit" aria-labelledby="audit-heading"><div class="wrap prose">
<h2 id="audit-heading">When could the earlier pendulum check be reused?</h2>
<p>A gravity estimate from {len(record['baseline_rows'])} pendulum readings passed the study’s check.
In each of {len(cases)} selected cases, we asked whether the earlier pass still applied, then ran the fit and check again.
With all inputs listed, the software kept the earlier pass in {len(valid_reuses)} cases where the fitted result
stayed the same ({reuse_examples}).</p>
<ul class="answers" id="pendulum-reuse-decisions" aria-label="Earlier pass compared with the fresh fit">
<li><strong>{stale_changed} of {len(changed)}<br>flagged</strong><span><b>All inputs listed, fitted result changed.</b>
The estimate or its standard error moved. Even the {case_link("scale-1.001", "0.1% increase in all periods")}
flagged the old pass, although the fresh fit still passed.</span></li>
<li><strong>{stale_unchanged} of {len(unchanged)}<br>flagged</strong><span><b>All inputs listed, fitted result unchanged.</b>
{case_link("decimal-spelling", "Adding a trailing zero")}, {case_link("row-order", "reordering the readings")}
and {case_link("fit-comment", "editing a code comment")} each flagged the old pass. The count of {len(unchanged)} includes the unchanged baseline.</span></li>
<li><strong>{held_omissions} of {len(omitted)}<br>wrongly kept</strong><span><b>The fit’s input list omitted the data folder.</b>
The software kept the old pass after the periods {case_link("omission-0.98", "fell by 2%")} or
{case_link("omission-1.02", "rose by 2%")}. Both fresh fits failed the check.</span></li>
<li><strong>{unclassified_unknown} of {len(unclassified)}<br>unknown</strong><span><b>No input group listed the data.</b>
For the same {case_link("unclassified-0.98", "decrease")} and {case_link("unclassified-1.02", "increase")},
the software reported that it could not establish whether the old pass still applied.</span></li>
</ul>
<details><summary>Compare five fitted values and their check results</summary>
<figure class="experiment">
<figcaption id="audit-examples">The gravity estimates are in m/s² with one statistical standard error.
An old pass marked <em>stale</em> needs a new check. Select a case for its original readings and check output.</figcaption>
<div class="scroll" role="region" aria-labelledby="audit-examples" tabindex="0">
<table class="claims" aria-labelledby="audit-examples"><thead><tr>
<th scope="col">Change</th><th scope="col">Fit ± standard error</th>
<th scope="col">Old pass</th><th scope="col">Fresh check</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></figure></details>
<h3 id="pendulum-fit-limits">What does the uncertainty cover?</h3>
<p>The fit assumes small pendulum swings. It gives each reading equal weight and fits a straight line through
the origin to squared period versus length. The slope gives the gravity estimate. Its statistical standard error
comes from scatter around the line, propagated to gravity to first order. Length, timing and swing-amplitude
calibration uncertainties are outside that error.</p>
<p>A second implementation evaluated the same estimator with 48-digit decimal arithmetic. In {agree} of {len(cases)}
cases it reproduced the estimate and standard error within {record['absolute_tolerance']:g} m/s² and agreed with
the fresh check’s verdict. This tests the numerical implementation. The accuracy of the physical model remains
an open question for this teaching dataset. The case counts describe the selected perturbations.</p>
<p id="pendulum-check-limits">{_boundary_example(boundaries)}
<a href="../records/pendulum-boundaries.json">Inspect the boundary cases</a> ·
<a href="../records/check_measurement_boundaries.py">Read the boundary check</a>.</p>
<p><a href="pendulum/">Browse all {len(cases)} cases</a> ·
<a href="../records/measurement_audit.json">Download the raw cases (JSON)</a> ·
<a href="../records/measurement-method.md">Measurement method</a> ·
<a href="../records/measurement_audit.py">Audit script</a> · <a href="../records/review_measurement_audit.py">Independent verifier</a></p>
<p><a href="../source/">Download this build’s source</a>, extract the ZIP and run <code>python3 evals/measurement_audit.py --verify</code>.</p>
</div></section>"""


def _edit_label(identifier: str) -> str:
    controls = {
        "baseline": "Original six swings",
        "style": "Add a comment to the figure style",
        "decimal-spelling": "Add a trailing zero to the first length",
        "row-order": "Reverse the order of the observations",
        "fit-comment": "Add a comment to the fit code",
    }
    if identifier in controls:
        return controls[identifier]
    group, factor = identifier.rsplit("-", 1)
    percent = (Decimal(factor) - 1) * 100
    subject = "All periods"
    if group.startswith("row-"):
        subject = f"Swing {int(group[4:])} period"
    sign = "+" if percent >= 0 else "−"
    return f"{subject} {sign}{abs(percent).normalize():f}%"


def _case_table(group, baseline_g, caption):
    rows = []
    for case in group:
        label = escape(_edit_label(case["id"]))
        state = escape(case["retained"])
        fresh = "pass" if case["fresh_exit"] == 0 else "fail"
        values = "\n".join(f"{escape(str(length))}, {escape(str(period))}" for length, period in case["rows"])
        delta = float(case["g"]) - baseline_g
        delta_text = "0.000000" if delta == 0 else f"{delta:+.6f}".replace("-", "−")
        rows.append(f"""
<tr id="case-{escape(case['id'], quote=True)}"><th scope="row" aria-label="{label}">
<details class="case-observations"><summary>{label}</summary>
<p>Length (m), period (s)</p><pre id="readings-{escape(case['id'], quote=True)}">{values}</pre>
<p>Change in gravity from baseline <strong>{delta_text} m/s²</strong></p>
<p>Fresh check output</p><pre>{escape(case['fresh_output'])}</pre>
</details></th><td><span class="chip {state}">{state}</span></td>
<td>{float(case['g']):.4f} ± {float(case['se']):.4f}</td><td>{fresh}</td></tr>""")
    return f"""
<div class="scroll" role="region" aria-label="{escape(caption, quote=True)}" tabindex="0">
<table class="claims case-table" aria-label="{escape(caption, quote=True)}"><thead><tr>
<th scope="col">Edit</th><th scope="col">Earlier pass</th><th scope="col">Updated fit ± SE (m/s²)</th>
<th scope="col">Fresh check</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""


def audit_cases_page(record: Dict[str, Any]) -> str:
    """Return the case browser body for the site's shared page shell."""
    cases = record["cases"]
    baseline_g = float(next(case["g"] for case in cases if case["id"] == "baseline"))
    sections = (
        ("declared", "Inputs declared", "The fit lists both the analysis code and swing data among its inputs."),
        ("unclassified-input", "Data outside every input group",
         "The fit reads the swing data, but the workspace assigns those data to no input group."),
        ("omitted-input", "Data group omitted by the fit",
         "The workspace assigns the swing data to a group called measurements. The fit reads the data and omits that group from its declaration."),
    )
    jumps = []
    body = []
    for cohort, title, explanation in sections:
        group = [case for case in cases if case["cohort"] == cohort]
        jumps.append(f'<a href="#{cohort}">{title} ({len(group)})</a>')
        single_swings, other_edits = [], []
        for case in group:
            if case["id"].startswith("row-") and case["id"][4:5].isdigit():
                single_swings.append(case)
            else:
                other_edits.append(case)
        content = _case_table(other_edits, baseline_g, title)
        if single_swings:
            single_table = _case_table(single_swings, baseline_g, "Changes to the period of one swing")
            content += f'<details class="case-sweeps"><summary>Inspect {len(single_swings)} single-swing edits</summary>{single_table}</details>'
        body.append(f"""
<section class="case-index" id="{cohort}" aria-labelledby="heading-{cohort}"><div class="wrap prose">
<h2 id="heading-{cohort}">{title}</h2><p>{explanation}</p>{content}</div></section>""")
    return f"""
<section class="hero slim case-index"><div class="wrap">
<p><a href="../#measurement-audit">Back to the measurement audit</a></p>
<h1>The pendulum cases</h1>
<p class="lead">Start with the <a href="#case-scale-1.001">0.1% period increase</a>. The old pass becomes stale
because its inputs changed. The updated estimate still passes. Compare the <a href="#case-scale-1.02">2% increase</a>
to see an edit that also makes the new fit fail.</p>
<p>All {len(cases)} cases start from the same six swings. Each row pairs the status of the earlier pass with
the new estimate of gravity, one standard error (SE), and the fresh check. The check requires at least five observations,
gravity strictly between 9.6 and 10.0 m/s², and a standard error of at most 0.2 m/s².</p>
<p>Expand a row to see the lengths, periods and exact check output.
<a href="../#pendulum-fit-limits">Fit assumptions and uncertainty</a> ·
<a href="../../records/measurement-method.md">Recorded protocol</a> ·
<a href="../../records/measurement_audit.json">Raw observations (JSON)</a> ·
<a href="../../records/review_measurement_audit.py">Independent verifier</a>.</p>
<nav class="case-jumps" aria-label="Input declarations">{' '.join(jumps)}</nav>
</div></section>
<section class="case-figure"><div class="wrap prose">
<figure><a href="../../assets/pendulum-sensitivity.png"><img src="../../assets/pendulum-sensitivity.png"
width="1152" height="909" loading="lazy" alt="The fit changes little when the shortest swing is edited. Changing the longest swing’s period by five percent shifts fitted gravity by about 0.39 metres per second squared in either direction."></a>
<figcaption>Each point is a new fit after editing one period. The dotted lines show where the gravity criterion changes verdict. <a href="#declared">Inspect the corresponding fits below</a>.</figcaption></figure>
</div></section>{''.join(body)}"""
