/* The CLI computes the decision once. This reader displays the report without sending it anywhere. */
(() => {
  const root = document.querySelector("[data-compute-intake]");
  if (!root) return;
  const get = key => root.querySelector("[" + key + "]");
  const question = root.querySelector('[name="question"]');
  const platform = root.querySelector('[name="platform"]');
  const briefBox = get("data-brief-result");
  const body = get("data-brief-body");
  const briefStatus = get("data-brief-status");
  const status = get("data-report-status");
  const result = get("data-imported");
  const fileInput = get("data-review-file");
  const labels = {keep: "Reuse", wait: "Already in flight", inspect: "Inspect evidence",
    retry: "Review a targeted retry", pilot: "Plan unstarted work"};
  const metrics = {jobs:"Jobs", concurrent:"Concurrent jobs", waves:"Waves", elapsed_seconds:"Elapsed seconds before queue waits",
    worker_seconds:"Worker-seconds", space_mib:"Peak storage (MiB)", files:"Peak file slots", shared_memory_mib:"Peak shared memory (MiB)", cost_minor:"Estimated cost in minor units"};
  function text(tag, value) {
    const el = document.createElement(tag);
    el.textContent = String(value);
    return el;
  }
  get("data-question-panel").hidden = false;
  get("data-import-label").hidden = false;
  let openedReport = null;
  function describeReport() {
    if (!openedReport) return;
    const query = question.value.trim();
    const differs = (query && openedReport.question !== query) ||
      (platform.value && openedReport.setting !== platform.value);
    status.textContent = differs ? "Opened a review for a different question or environment than your current brief." : "Opened the local review.";
  }
  function invalidate() {
    briefBox.hidden = true;
    body.textContent = "";
    briefStatus.textContent = "";
    describeReport();
  }
  question.addEventListener("input", invalidate);
  platform.addEventListener("change", invalidate);
  const prepare = get("data-make-brief");
  question.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.isComposing) {
      event.preventDefault();
      prepare.click();
    }
  });
  prepare.addEventListener("click", () => {
    if (!question.value.trim() || !platform.value) {
      briefStatus.textContent = "Enter your research question and choose an environment.";
      (!question.value.trim() ? question : platform).focus();
      return;
    }
    const choice = platform.selectedOptions[0];
    const fields = {question: question.value.trim(), setting: choice.textContent, guidance: choice.dataset.guidance};
    body.textContent = get("data-brief-template").content.textContent.replace(/\{(question|setting|guidance)\}/g,
      (_, key) => fields[key]);
    briefBox.hidden = false;
    briefBox.querySelector("h3").focus();
  });
  get("data-copy-brief").addEventListener("click", async () => {
    try {
      const original = body.textContent;
      await navigator.clipboard.writeText(original);
      if (briefBox.hidden || body.textContent !== original) return;
      briefStatus.textContent = "Brief copied.";
    } catch {
      if (briefBox.hidden) return;
      briefBox.querySelector("details").open = true;
      window.getSelection().selectAllChildren(body);
      briefStatus.textContent = "Instructions selected. Use your usual copy shortcut.";
    }
  });
  get("data-save-brief").addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([body.textContent + "\n"], {type:"text/plain;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = "hpc-inspection-brief.txt";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  const isText = value => typeof value === "string";
  const isObject = value => value && typeof value === "object" && !Array.isArray(value);
  function validate(report) {
    if (!isObject(report) || report.format !== root.dataset.format || !isText(report.question) ||
        !isText(report.next) || !isText(report.scope) || !Array.isArray(report.outputs) ||
        !report.outputs.length || report.outputs.length > 10000 ||
        !Array.isArray(report.unexpected) || !report.unexpected.every(isText)) return false;
    for (const field of ["packet_sha256", "reviewer_sha256"]) {
      if (report[field] !== undefined && !(typeof report[field] === "string" && /^[0-9a-f]{64}$/.test(report[field]))) return false;
    }
    const ids = new Set();
    for (const row of report.outputs) {
      if (!isObject(row) || !isText(row.id) || !row.id.trim() || ids.has(row.id) ||
          !Object.prototype.hasOwnProperty.call(labels, row.action) || !isText(row.reason) || !isText(row.reference)) return false;
      ids.add(row.id);
    }
    const usage = report.accounting;
    if (usage !== undefined) {
      if (!isObject(usage) || !isText(usage.reason)) return false;
      if (usage.worker_seconds === null) {
        if (usage.attempts !== null || usage.outputs !== null || usage.sha256 !== null) return false;
      } else if (![usage.worker_seconds, usage.attempts, usage.outputs].every(Number.isSafeInteger) ||
                 usage.worker_seconds < 0 || usage.attempts < 1 || usage.outputs < 1 ||
                 usage.outputs > report.outputs.length || usage.outputs > usage.attempts ||
                 typeof usage.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(usage.sha256)) return false;
    }
    const batch = report.batch;
    return batch === null || (isObject(batch) && ["hold","owner_review"].includes(batch.state) &&
      Array.isArray(batch.issues) && batch.issues.every(isText) &&
      (batch.warnings === undefined || (Array.isArray(batch.warnings) && batch.warnings.every(isText))) && Array.isArray(batch.ids) && batch.ids.every(isText) &&
      isText(batch.owner) && isObject(batch.estimates));
  }
  function readReport(report) {
    const part = document.createDocumentFragment();
    part.append(text("h4", report.question), text("p", report.next));
    const usage = report.accounting;
    const kept = report.outputs.filter(row => row.action === "keep").length;
    part.append(text("p", kept + " of " + report.outputs.length + " listed outputs were reusable at review."));
    if (!usage || usage.worker_seconds === null) {
      part.append(text("p", "Worker time unknown. " + (usage ? usage.reason : "This review has no accounting record.")));
    } else {
      part.append(text("p", usage.worker_seconds.toLocaleString() + " recorded worker-seconds across " +
        usage.attempts + " attempt(s) covering " + usage.outputs + " of " + report.outputs.length + " listed outputs."));
    }
    const list = document.createElement("ul");
    list.className = "compute-rows";
    for (const row of report.outputs) {
      const li = document.createElement("li");
      li.append(text("strong", row.id + " · " + labels[row.action]), text("p", row.reason));
      if (row.reference) li.append(text("small", row.reference));
      list.append(li);
    }
    part.append(list);
    const identity = document.createElement("details");
    identity.append(text("summary", "Evidence behind this review"));
    if (report.packet_sha256 && report.reviewer_sha256) {
      identity.append(text("p", "Evidence packet SHA-256: " + report.packet_sha256),
                      text("p", "Reviewer SHA-256: " + report.reviewer_sha256));
    } else {
      identity.append(text("p", "This older review has no evidence fingerprint. Run the current reviewer to identify its source."));
    }
    if (usage && usage.sha256) identity.append(text("p", "Accounting receipt SHA-256: " + usage.sha256));
    for (const row of report.outputs) {
      if (!isObject(row.basis)) continue;
      const facts = ["input", "recipe", "settings", "check"]
        .filter(key => isText(row.basis[key])).map(key => {
          const checked = isObject(row.recorded_basis) ? row.recorded_basis[key] : undefined;
          if (isText(checked) && checked !== row.basis[key]) {
            return key + " when checked = " + checked + ", requested now = " + row.basis[key];
          }
          return key + " = " + row.basis[key];
        });
      if (facts.length) identity.append(text("p", row.id + " · " + facts.join(" · ")));
    }
    part.append(identity);
    if (report.unexpected.length) part.append(text("p", "Unlisted returns: " + report.unexpected.join(", ")));
    const batch = report.batch;
    if (batch) {
      part.append(text("h4", batch.state === "hold" ? "Hold this batch" : "Take this batch to the resource owner"));
      part.append(text("p", "Proposed IDs: " + batch.ids.join(", ") + (batch.owner ? " · " + batch.owner : "")));
      for (const msg of [...batch.issues, ...(batch.warnings || [])]) part.append(text("p", msg));
      if (Object.keys(batch.estimates).length) part.append(text("h5", "Estimated batch use"));
      const estimates = document.createElement("dl");
      estimates.className = "pilot-facts";
      for (const [key, label] of Object.entries(metrics)) {
        if (!Object.prototype.hasOwnProperty.call(batch.estimates, key)) continue;
        const row = document.createElement("div");
        const unit = key === "cost_minor" ? " " + batch.estimates.currency : "";
        row.append(text("dt", label), text("dd", String(batch.estimates[key]) + unit));
        estimates.append(row);
      }
      part.append(estimates);
    }
    part.append(text("p", report.scope));
    return part;
  }
  let request = 0;
  fileInput.addEventListener("change", async () => {
    const turn = ++request;
    openedReport = null;
    result.replaceChildren();
    status.textContent = "";
    const file = fileInput.files[0];
    if (!file) return;
    try {
      if (file.size > 16 * 1024 * 1024) throw new Error();
      const report = JSON.parse(await file.text());
      if (turn !== request) return;
      if (!validate(report)) throw new Error();
      result.append(readReport(report));
      openedReport = report;
      describeReport();
    } catch {
      if (turn !== request) return;
      status.textContent = "Choose a JSON report produced by taos hpc review --json, up to 16 MiB.";
    }
  });
})();
