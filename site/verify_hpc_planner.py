"""Exercise the generated HPC worksheet in an installed Chromium browser.

Run python3 site/verify_hpc_planner.py, or pass --browser /path/to/chromium.
The check uses a temporary browser profile and the local site's actual controls.
"""

import argparse
import json
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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
  const done = new Promise((resolve, reject) => {
    const observer = new MutationObserver(() => {
      if (status.textContent) { clearTimeout(timer); observer.disconnect(); resolve(); }
    });
    const timer = setTimeout(() => {
      observer.disconnect();
      reject(new Error("The file import did not report a result within 10 seconds."));
    }, 10000);
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
  await fetch("/verdict", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(readings)});
}
checkAccounting();
"""


def installed_browser(requested):
    names = [requested] if requested else [
        "google-chrome", "google-chrome-stable",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "chromium", "chromium-browser"]
    rejected = []
    for name in names:
        executable = shutil.which(name)
        if not executable:
            continue
        try:
            probe = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as error:
            rejected.append(f"{executable}: {error}")
            continue
        output = (probe.stdout + "\n" + probe.stderr).strip()
        version = re.search(r"^(?:Google Chrome(?: for Testing)?|Chromium) [0-9][^\n]*", output, re.M)
        if probe.returncode == 0 and version:
            return executable, version.group()
        rejected.append(f"{executable}: {output[:150] or 'no version reported'}")
    detail = " Tried " + " / ".join(rejected) if rejected else ""
    raise ValueError("Pass --browser with the path to an installed Chromium or Chrome executable." + detail)


class WorksheetHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.server.last_path = self.path
        super().do_GET()

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        if self.path != "/verdict" or self.headers.get_content_type() != "application/json" or not 0 < size <= 131072:
            self.send_error(400)
            return
        report = self.rfile.read(size)
        self.send_response(204)
        self.end_headers()
        self.server.verdict.put(report)


def run_browser(browser, version, root, pages):
    handler = partial(WorksheetHandler, directory=str(pages))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, tempfile.TemporaryFile() as errors:
        server.verdict = queue.Queue()
        server.last_path = "(no page requested)"
        server.timeout = 0.2
        url = f"http://127.0.0.1:{server.server_port}/worksheet.html"
        process = subprocess.Popen([browser, "--headless", "--disable-background-networking", "--no-first-run",
                                    "--user-data-dir=" + str(root / "profile"), url],
                                   stdout=subprocess.DEVNULL, stderr=errors)
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and process.poll() is None:
                server.handle_request()
                try:
                    return json.loads(server.verdict.get_nowait())
                except queue.Empty:
                    continue
            errors.seek(0)
            detail = errors.read().decode(errors="replace").strip().splitlines()
            reason = f"exit {process.returncode}" if process.returncode is not None else "45-second timeout"
            raise RuntimeError(f"{version} ({browser}): {reason}, last request {server.last_path}. "
                               + " ".join(detail[-4:])[-650:])
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", help="Path to an installed Chromium or Chrome executable")
    args = parser.parse_args()
    try:
        browser, version = installed_browser(args.browser)
    except ValueError as error:
        parser.exit(2, str(error) + "\n")
    with tempfile.TemporaryDirectory(prefix="hpc-worksheet-") as directory:
        root = Path(directory)
        pages = root / "site"
        pages.mkdir()
        for asset in ("hpc-planner.js", "hpc-review.js"):
            shutil.copyfile(SITE / "assets" / asset, pages / asset)
        cases = resource_cases()
        (pages / "worksheet.html").write_text(f'<!doctype html><meta charset="utf-8">{render_planner()}'
                        f'<script id="cases" type="application/json">{json.dumps(cases)}</script>'
                        f'<script id="review-fixture" type="application/json">{json.dumps(sample_review())}</script>'
                        f'<script src="hpc-planner.js"></script><script src="hpc-review.js"></script><script>{DRIVE}</script>', encoding="utf-8")
        try:
            checks = run_browser(browser, version, root, pages)
        except (OSError, RuntimeError, ValueError) as error:
            parser.exit(1, f"Worksheet browser check failed: {error}\n")
    failures = [entry["case"] for entry in checks if not entry["passed"]]
    if sum(entry["case"].startswith("Resource case ") for entry in checks) != len(cases):
        failures.append("The browser did not exercise every prepared resource combination.")
    if not any(entry["case"] == "A valid review can be opened after an invalid report" for entry in checks):
        failures.append("The browser did not complete the file-import round trip.")
    print(json.dumps({"browser": version, "browser_checks": len(checks), "resource_combinations": len(cases),
                      "failures": failures}, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
