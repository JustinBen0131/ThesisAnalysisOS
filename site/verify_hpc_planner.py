"""Exercise the generated HPC worksheet in an installed Chromium browser.

Run python3 site/verify_hpc_planner.py, or pass --browser /path/to/chromium.
The check uses a temporary browser profile and the local site's actual controls.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from html import escape, unescape
from pathlib import Path

SITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SITE.parent))
from hpc_planner import render_planner
from hpc_review import sample_review


def resource_cases():
    """Calculate the expected decisions in exact fractional units, independently of the UI."""
    cases = []
    shapes = [(1, 7, .5, 0), (3, 3, 1.75, 32), (7, 2, 7.5, 64),
              (13, 3, 4.25, 128), (29, 6, 3.5, .25)]
    for jobs, parallel, minutes, output in shapes:
        required = jobs * Fraction(output) / 1024
        capacities = [required / 2, required, required + 1] if required else [0, 1]
        workers = min(jobs, parallel)
        groups = len(range(0, jobs, workers))
        for memory in (1, 2, 4):
            for space in capacities:
                if memory < 2 or space < required:
                    title = "Revise the batch before approval"
                elif memory == 2 or (required and space == required):
                    title = "Review the available headroom"
                else:
                    title = "Batch estimate for owner review"
                fields = dict(jobs=jobs, parallel=parallel, minutes=minutes, output_mib=output,
                              peak=2, allowance=memory, space=float(space))
                cases.append(dict(fields=fields, title=title, groups=groups, elapsed=groups * minutes,
                                  worker=jobs * minutes))
    return cases


DRIVE = r"""
const plan = document.querySelector("[data-run-sheet]");
const batch = document.querySelector("[data-batch-review]");
const readings = [];
function check(caseName, passed) { readings.push({case: caseName, passed: Boolean(passed)}); }
function set(box, name, value) {
  const field = box.elements.namedItem(name);
  if (field.type === "checkbox") field.checked = value;
  else field.value = String(value);
  for (const type of ["input", "change"]) field.dispatchEvent(new Event(type, {bubbles:true}));
}
function build(box) {
  box.querySelector("[data-build]").click();
  const result = box.querySelector("[data-result]");
  return result.hidden ? "" : result.querySelector("code").textContent;
}
try {
  document.querySelector(".compute-manual").open = true;
  document.querySelector(".pilot-after").open = true;
  set(plan, "basis", "Search tomorrow in the imaging folder.");
  set(plan, "reuse", "match");
  check("A search location cannot authorize reuse", build(plan) === "");
  set(plan, "basis", "R-17. Image IDs and output check match.");
  check("A documented match can be reused", build(plan).startsWith("Reuse the checked result"));
  set(plan, "reuse", "unknown");
  check("Search and match keep separate notes", plan.elements.basis.value.startsWith("Search tomorrow"));
  set(plan, "reuse", "new");
  for (const [key,value] of Object.entries({basis:"New calibration", setting:"shared", sample:"Image stack A",
      recipe:"count-v1", output:"Image count", check:"37 named images", authority:"Facility lead"})) set(plan,key,value);
  check("One bounded pilot is possible", build(plan).startsWith("One-job pilot for review"));
  set(batch, "outcome", "failed"); set(batch, "evidence", "No image IDs arrived.");
  check("A failed return holds the batch", build(batch).startsWith("Hold the larger run"));
  set(batch, "outcome", "passed");
  check("A failure note cannot establish a pass", build(batch) === "");
  set(batch, "evidence", "37 IDs checked with count-v1.");
  check("The handoff identifies the checked recipe", build(batch).includes("Recipe — count-v1"));
  set(plan, "recipe", "count-v2");
  check("Editing the recipe retires the handoff", batch.querySelector("[data-result]").hidden);
  check("The old observation remains identifiable", build(batch).includes("Earlier pilot observation — 37 IDs checked with count-v1."));
  set(batch, "outcome", "passed"); set(batch, "evidence", "37 IDs checked with count-v2."); set(batch, "estimate", true);
  const cases = JSON.parse(document.getElementById("cases").textContent);
  for (const item of cases) {
    for (const [key,number] of Object.entries(item.fields)) set(batch,key,number);
    const actual = build(batch);
    check("Resource case " + JSON.stringify(item.fields), actual.startsWith(item.title) &&
      actual.includes("Estimated elapsed time — " + item.elapsed + " min") &&
      actual.includes("Total worker time — " + item.worker + " min") &&
      actual.includes("Groups of jobs — " + item.groups));
  }
  for (const [key,number] of Object.entries({jobs:1, parallel:1, minutes:5, peak:1, allowance:2, output_mib:1024.001, space:1})) {
    set(batch,key,number);
  }
  const closeLimit = build(batch);
  check("A small storage overrun is visible in the two displayed numbers", closeLimit.startsWith("Revise the batch") &&
    !closeLimit.includes("New output — 1 GiB estimated / 1 GiB available."));
  set(plan, "authority", "Updated allocation");
  check("Changed limits preserve the observed pass and reopen the estimate", batch.elements.outcome.value === "passed" &&
    batch.elements.evidence.value.includes("count-v2") && !batch.elements.estimate.checked && batch.querySelector("[data-result]").hidden);
} catch (error) {
  check("Browser error: " + error.message, false);
}
async function readReview(record) {
  const field = document.querySelector("[data-review-file]");
  const transfer = new DataTransfer();
  transfer.items.add(new File([JSON.stringify(record)], "campaign-review.json", {type: "application/json"}));
  field.files = transfer.files;
  const status = document.querySelector("[data-report-status]");
  const value = document.querySelector("[data-imported]");
  const done = new Promise(resolve => {
    const observer = new MutationObserver(() => {
      if (status.textContent) { observer.disconnect(); resolve(); }
    });
    observer.observe(status, {childList: true, subtree: true});
  });
  field.dispatchEvent(new Event("change", {bubbles: true}));
  await done;
  return value;
}
async function checkAccounting() {
  try {
    const current = JSON.parse(document.getElementById("review-fixture").textContent);
    const imported = await readReview(current);
    const workerEstimate = Array.from(imported.querySelectorAll("dt")).find(label => label.textContent === "Worker-seconds");
    check("Retained worker time and projected batch time have separate labels",
      imported.textContent.includes("220 recorded worker-seconds") &&
      imported.textContent.includes("Estimated batch use") && workerEstimate?.nextElementSibling?.textContent === "90");
    check("The displayed decision accounts for all three listed outputs",
      imported.textContent.includes("2 of 3 listed outputs were reusable"));
    const old = {...current}; delete old.accounting;
    check("An older review shows unknown worker time", (await readReview(old)).textContent.includes("Worker time unknown"));
    const invalid = {...current, accounting: {...current.accounting, attempts: -1}};
    check("Invalid accounting clears the previous report", !(await readReview(invalid)).textContent);
    check("A valid review can be opened after an invalid report",
      (await readReview(current)).textContent.includes(current.accounting.sha256));
  } catch (error) {
    check("Imported review error: " + error.message, false);
  }
  const output = document.createElement("pre");
  output.id = "worksheet-verdict";
  output.textContent = JSON.stringify(readings);
  document.body.replaceChildren(output);
}
checkAccounting();
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", help="Path to an installed Chromium or Chrome executable")
    args = parser.parse_args()
    browser = (args.browser or shutil.which("chromium") or shutil.which("chromium-browser")
               or shutil.which("google-chrome") or shutil.which("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    if not browser:
        parser.exit(2, "Pass --browser with the path to an installed Chromium browser.\n")
    with tempfile.TemporaryDirectory(prefix="hpc-worksheet-") as directory:
        root = Path(directory)
        page = root / "worksheet.html"
        script = escape((SITE / "assets/hpc-planner.js").as_uri(), quote=True)
        review_script = escape((SITE / "assets/hpc-review.js").as_uri(), quote=True)
        cases = resource_cases()
        page.write_text(f'<!doctype html><meta charset="utf-8">{render_planner()}'
                        f'<script id="cases" type="application/json">{json.dumps(cases)}</script>'
                        f'<script id="review-fixture" type="application/json">{json.dumps(sample_review())}</script>'
                        f'<script src="{script}"></script><script src="{review_script}"></script><script>{DRIVE}</script>', encoding="utf-8")
        result = subprocess.run([browser, "--headless", "--disable-background-networking", "--no-first-run",
                                 "--user-data-dir=" + str(root / "profile"), "--virtual-time-budget=5000", "--dump-dom", page.as_uri()],
                                capture_output=True, text=True, timeout=45)
        match = re.search(r'<pre id="worksheet-verdict">(.*?)</pre>', result.stdout, re.S)
        if result.returncode or not match:
            parser.exit(1, "The browser did not return a worksheet result. Check the executable and headless support.\n")
        checks = json.loads(unescape(match.group(1)))
    failures = [entry["case"] for entry in checks if not entry["passed"]]
    if sum(entry["case"].startswith("Resource case ") for entry in checks) != len(cases):
        failures.append("The browser did not exercise every prepared resource combination.")
    print(json.dumps({"browser_checks": len(checks), "resource_combinations": len(cases), "failures": failures}, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
