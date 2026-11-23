/* Both decisions are local. Input changes invalidate the last generated handoff. */
(() => {
  const root = document.querySelector("[data-planner]");
  if (!root) return;
  const plan = root.querySelector("[data-run-sheet]");
  const batch = root.querySelector("[data-batch-review]");
  const value = (form, name) => form.elements.namedItem(name).value.trim();
  let previousPilotNote = "";

  const reuseModes = {
    unknown: ["Where will you look?", "An earlier run sheet, a results folder or a teammate’s handoff."],
    match: ["Which result matches, and what confirms it?", "Record a reference and the matching inputs, code, settings and output check."],
    new: ["What did you check, and why is a new run needed?", "Name the search you made or the change that affected the earlier result."]
  };

  function fields(group, visible) {
    group.hidden = !visible;
    group.disabled = !visible;
  }

  function syncPlan() {
    const reuse = value(plan, "reuse");
    const [label, hint] = reuseModes[reuse];
    plan.querySelector("[data-basis-label]").textContent = label;
    plan.querySelector("#pilot-basis-hint").textContent = hint;
    plan.elements.basis.required = reuse !== "unknown";
    fields(plan.querySelector("[data-new-fields]"), reuse === "new");
    plan.querySelector("[data-setting-note]").textContent =
      plan.elements.setting.selectedOptions[0].dataset.guidance || "Choose the setting to see which limits to agree on.";
  }

  function syncBatch() {
    const passed = value(batch, "outcome") === "passed";
    batch.elements.evidence.required = value(batch, "outcome") !== "unchecked";
    batch.querySelector("[data-estimate-choice]").hidden = !passed;
    batch.elements.estimate.disabled = !passed;
    fields(batch.querySelector("[data-measurements]"), passed && batch.elements.estimate.checked);
  }

  const resultLabels = new Set([
    "Setting", "Reason for a new run", "Representative input", "Recipe", "Expected output",
    "Pass condition", "Resource limit and approver", "Reference and evidence", "Current record",
    "Failure evidence", "Observed check", "Earlier pilot observation", "Schedule", "Memory per job", "New output"
  ]);

  function render(form, title, lines, metrics = []) {
    const box = form.querySelector("[data-result]");
    const reading = box.querySelector("[data-reading]");
    const heading = box.querySelector("h4");
    heading.textContent = title;
    reading.replaceChildren();
    if (metrics.length) {
      const strip = document.createElement("dl");
      strip.className = "pilot-metrics";
      for (const [label, value] of metrics) {
        const cell = document.createElement("div");
        const dt = document.createElement("dt"), dd = document.createElement("dd");
        dt.textContent = label; dd.textContent = value;
        cell.append(dt, dd); strip.append(cell);
      }
      reading.append(strip);
    }
    const facts = document.createElement("dl");
    facts.className = "pilot-facts";
    reading.append(facts);
    for (const line of lines.filter(Boolean)) {
      const separator = line.indexOf(" — ");
      const label = line.slice(0, separator);
      if (separator > 0 && resultLabels.has(label)) {
        const row = document.createElement("div");
        const dt = document.createElement("dt"), dd = document.createElement("dd");
        dt.textContent = label; dd.textContent = line.slice(separator + 3);
        row.append(dt, dd); facts.append(row);
      } else {
        const note = document.createElement("p");
        note.textContent = line; reading.append(note);
      }
    }
    if (!facts.children.length) facts.remove();
    const metricLines = metrics.map(([label, val]) => label + " — " + val);
    box.querySelector("code").textContent = [title, "", ...metricLines, ...lines].join("\n");
    box.querySelector("[data-copy-status]").textContent = "";
    box.querySelector("details").open = false;
    box.hidden = false;
    heading.focus();
  }

  function validate(form) {
    for (const input of form.querySelectorAll('input[type="text"]')) {
      input.setCustomValidity(input.required && !input.matches(":disabled") && !input.value.trim()
        ? "Enter a short description." : "");
    }
    for (const name of ["minutes", "peak", "allowance"]) {
      const input = form.elements.namedItem(name);
      if (input && !input.matches(":disabled") && input.value !== "") {
        input.setCustomValidity(input.valueAsNumber > 0 ? "" : "Enter a value greater than zero.");
      }
    }
    return Array.from(form.elements).every(input =>
      input.matches(":disabled") || !input.willValidate || input.reportValidity());
  }

  function buildPlan(e) {
    e.preventDefault();
    if (!validate(plan)) return;
    const reuse = value(plan,"reuse"), basis = value(plan,"basis");
    if (reuse === "unknown") {
      render(plan, "Check for reusable work first", [
        "Look in " + (basis || "the project’s previous results and handoffs") + ".",
        "Compare the inputs, code, settings and the last output check.",
        "Record the matching result or explain which change calls for a pilot."
      ]);
      return;
    }
    if (reuse === "match") {
      render(plan, "Reuse the checked result", [
        "Reference and evidence — " + basis,
        "Link this result to the current task. Reopen the decision if an input, setting or check changes."
      ]);
      return;
    }
    render(plan, "One-job pilot for review", [
      "Setting — " + plan.elements.setting.selectedOptions[0].textContent, "Reason for a new run — " + basis,
      "Representative input — " + value(plan,"sample"), "Recipe — " + value(plan,"recipe"),
      "Expected output — " + value(plan,"output"), "Pass condition — " + value(plan,"check"),
      "Resource limit and approver — " + value(plan,"authority"), "",
      "Run one input once the owner approves. Save the job or command reference, elapsed time, peak memory, output size and observed check.",
      "Hold on missing or failing output. Bring the measured result back before increasing the scope."
    ]);
  }

  const format = new Intl.NumberFormat("en-US", {maximumSignificantDigits: 5});
  function comparisonValues(measured, limit) {
    let digits = 5, print = format;
    while (measured !== limit && print.format(measured) === print.format(limit) && digits < 17) {
      print = new Intl.NumberFormat("en-US", {maximumSignificantDigits: ++digits});
    }
    return [print.format(measured), print.format(limit)];
  }
  function reviewBatch(e) {
    e.preventDefault();
    if (!validate(batch)) return;
    const verdict = value(batch,"outcome"), evidence = value(batch,"evidence");
    const context = [];
    if (verdict !== "unchecked" && value(plan, "reuse") === "new") {
      for (const [name, label] of [["sample", "Representative input"], ["recipe", "Recipe"], ["check", "Pass condition"]]) {
        const detail = value(plan, name);
        if (detail) context.push(label + " — " + detail);
      }
    }
    if (verdict === "unchecked") {
      const label = evidence === previousPilotNote ? "Earlier pilot observation" : "Current record";
      render(batch, "Check the output before scaling", [
        "Open the expected output and apply the agreed pass condition.",
        ...(evidence ? [label + " — " + evidence] : []),
        "Save the observed value and its reference. A completion report alone cannot establish that the output passed."
      ]);
      return;
    }
    if (verdict === "failed") {
      render(batch, "Hold the larger run", ["Failure evidence — " + evidence, ...context,
        "Trace the discrepancy to the input, command, log or returned file. Preserve other checked outputs.",
        "Propose a retry only for affected work after you identify and address the cause."]);
      return;
    }
    if (!batch.elements.estimate.checked) {
      render(batch, "Record the passing pilot", ["Observed check — " + evidence, ...context,
        "Keep the input, output and check together. Use the measured resource needs and the owner’s limits to review any larger batch."]);
      return;
    }

    const number = name => batch.elements.namedItem(name).valueAsNumber;
    const jobs=number("jobs"), cap=number("parallel"), minutes=number("minutes"), peak=number("peak");
    const allowance=number("allowance"), space=number("space"), output=number("output_mib");
    if (!Number.isSafeInteger(jobs) || !Number.isSafeInteger(cap)) {
      const input=batch.elements.namedItem(Number.isSafeInteger(jobs) ? "parallel" : "jobs");
      input.setCustomValidity("Use a whole number within the supported range.");
      input.reportValidity(); return;
    }
    const parallel=Math.min(jobs,cap), waves=Math.ceil(jobs/parallel);
    const elapsed=waves*minutes, storage=jobs*(output/1024), total=jobs*minutes;
    if (![elapsed, storage, total].every(Number.isFinite)) {
      render(batch, "Review the measurement units", ["The estimate exceeds the numeric range. Check the units and reduce the proposed batch."]);
      return;
    }
    const issues=[], tight=[];
    if (peak>allowance) issues.push("One job’s measured peak exceeds its memory limit.");
    else if (peak===allowance) tight.push("The measured job uses the entire per-job memory allowance.");
    if (storage>space) issues.push("The projected output exceeds the space available.");
    else if (storage===space && storage>0) tight.push("The projected output fills the available space.");
    const heading=issues.length ? "Revise the batch before approval" : tight.length ? "Review the available headroom" : "Batch estimate for owner review";
    const [usedMemory, allowedMemory] = comparisonValues(peak, allowance);
    const [newSpace, freeSpace] = comparisonValues(storage, space);
    render(batch, heading, [
      "Observed check — " + evidence, ...context,
      "Schedule — " + jobs + " jobs, up to " + parallel + " at once, in " + waves + (waves===1 ? " group." : " groups."),
      "Memory per job — " + usedMemory + " GiB measured / " + allowedMemory + " GiB limit.",
      "New output — " + newSpace + " GiB estimated / " + freeSpace + " GiB available.",
      "", ...issues, ...tight,
      "Allow for variation, queue waits, temporary files and applicable charges. The resource owner decides whether to proceed."
    ], [
      ["Estimated elapsed time", format.format(elapsed) + " min"],
      ["Total worker time", format.format(total) + " min"],
      ["Groups of jobs", String(waves)]
    ]);
  }

  function wire(form, sync, submit, example, choice, note) {
    const fill = form.querySelector("[data-example]");
    const box = form.querySelector("[data-result]");
    const notes = new Map();
    const remember = () => notes.set(choice.value, note.value);
    note.addEventListener("input", remember);
    note.addEventListener("change", remember);
    choice.addEventListener("change", () => { note.value = notes.get(choice.value) || ""; });
    box.querySelector("[data-copy]").addEventListener("click", async () => {
      const code = box.querySelector("code"), status = box.querySelector("[data-copy-status]");
      try {
        await navigator.clipboard.writeText(code.textContent);
        status.textContent = "Copied";
      } catch {
        box.querySelector("details").open = true;
        const selection = window.getSelection();
        selection.selectAllChildren(code);
        status.textContent = "Text selected. Use your usual copy shortcut.";
      }
    });
    function invalidate() {
      form.querySelector("[data-result]").hidden=true;
      for (const input of form.querySelectorAll("input")) input.setCustomValidity("");
      fill.hidden=true;
      sync();
    }
    form.addEventListener("input", invalidate);
    form.addEventListener("change", invalidate);
    const buildButton = form.querySelector("[data-build]");
    buildButton.addEventListener("click", submit);
    form.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.isComposing && event.target.matches('input[type="text"], input[type="number"]')) {
        event.preventDefault();
        buildButton.click();
      }
    });
    fill.addEventListener("click", () => {
      for (const [name, data] of Object.entries(example)) {
        const input=form.elements.namedItem(name);
        if (input.type==="checkbox") input.checked=data;
        else input.value=data;
      }
      remember();
      invalidate();
    });
    sync();
    return {notes, invalidate};
  }

  wire(plan, syncPlan, buildPlan, {
    reuse:"new", basis:"The sensor calibration changed since the checked summary.", setting:"shared",
    sample:"One typical day of readings, including its usual missing entries.",
    recipe:"Daily summary workflow v2, calibration file v3.", output:"One daily summary table.",
    check:"The accepted and rejected row counts add up to the original input row count.",
    authority:"Project lead reviews one job with 2 GiB of memory and a 20-minute limit."
  }, plan.elements.reuse, plan.elements.basis);
  const batchDraft = wire(batch,syncBatch,reviewBatch,{
    outcome:"passed",evidence:"Example file had 240 readings. The summary accounts for all 240.",
    estimate:true,minutes:8,peak:1.5,output_mib:128,jobs:12,parallel:3,allowance:2,space:4
  }, batch.elements.outcome, batch.elements.evidence);

  const evidenceHint = batch.querySelector("#pilot-evidence-hint");
  const defaultHint = evidenceHint.textContent;
  batch.elements.evidence.addEventListener("input", () => {
    evidenceHint.textContent = defaultHint;
    if (batch.elements.outcome.value === "unchecked") previousPilotNote = "";
  });
  batch.elements.outcome.addEventListener("change", () => {
    batch.elements.estimate.checked = false;
    syncBatch();
  });
  function planChanged(event) {
    if (event.target === plan.elements.authority) {
      if (batch.elements.estimate.checked) {
        batch.elements.estimate.checked = false;
        batchDraft.invalidate();
        evidenceHint.textContent = "The approval limits changed. Confirm the limits before estimating another batch.";
      }
      return;
    }
    const outcome = batch.elements.outcome;
    if (outcome.value === "unchecked" && !batchDraft.notes.has("passed") && !batchDraft.notes.has("failed")) return;
    const previous = batch.elements.evidence.value;
    previousPilotNote = previous.trim();
    outcome.value = "unchecked";
    batchDraft.notes.clear();
    if (previous) batchDraft.notes.set("unchecked", previous);
    batch.elements.estimate.checked = false;
    batchDraft.invalidate();
    evidenceHint.textContent = previousPilotNote
      ? "This note belongs to the earlier pilot. Record a fresh check for the revised run."
      : "The pilot plan changed. Check the revised run before using its result.";
  }
  plan.addEventListener("input", planChanged);
  plan.addEventListener("change", planChanged);
  plan.querySelector("[data-example]").addEventListener("click", planChanged);
  root.hidden=false;
})();
