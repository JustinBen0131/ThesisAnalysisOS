/* A correction and its recorded dependencies, drawn from the graph produced by the site build. */
(function mountArchitecture(createRecord) {
  "use strict";
  var cover = document.getElementById("architecture-cover"), demo = document.getElementById("mind-demo");
  var start = document.getElementById("mind-start"), fallback = document.getElementById("mind-static");
  var fileStart = document.getElementById("mind-change-start");
  if (!cover || !demo || !start || !fallback) { return; }
  var controls = null, demoOpen = false, explorerEntry = null;
  var heading = document.getElementById("mind-title"), header = document.querySelector(".top");
  var guideTitle = document.getElementById("guide-title"), copy = document.getElementById("guide-copy");
  var guideRole = document.getElementById("guide-role"), next = document.getElementById("guide-next");
  var back = document.getElementById("guide-back"), explore = document.getElementById("guide-explore");
  var time = document.getElementById("guide-time"), gravity = document.getElementById("guide-gravity");
  var data = document.getElementById("swing-reading").dataset;
  var handoff = document.getElementById("guide-handoff"), interaction = document.getElementById("guide-check");
  var contrast = document.getElementById("guide-compare");
  var guideStep = 0;
  var scenes = [
    [guideTitle.textContent, guideRole.textContent, copy.textContent],
    ["Which result should Codex recheck?", "You → Codex",
      "The earlier " + Number(data.oldG).toFixed(2) + " m/s² pass used the original timings. Choose which result to follow."],
    ["What did Codex find?", "Codex → You",
      "The gravity fit falls below the required " + data.low + "–" + data.high + " m/s². Codex’s handoff covers the pendulum study alone."],
    ["What does the next agent inherit?", "You · Reviewer",
      "The next agent inherits the failed pendulum check. You decide whether to approve a revised estimate."]
  ];
  function showGuide(step, focus) {
    if (!Number.isInteger(step) || step < 0 || step >= scenes.length) { step = 0; }
    guideStep = step;
    cover.dataset.guideStep = String(step);
    guideTitle.textContent = scenes[step][0]; guideRole.textContent = scenes[step][1]; copy.textContent = scenes[step][2];
    time.querySelector("span").textContent = (step ? data.newPeriod : data.oldPeriod) + " s";
    time.href = step ? time.dataset.corrected : time.dataset.original;
    gravity.href = step ? gravity.dataset.corrected : gravity.dataset.original;
    document.getElementById("guide-fit").textContent = Number(step >= 2 ? data.newG : data.oldG).toFixed(2) + " m/s²";
    document.getElementById("guide-verdict").textContent = ["✓ Passed", "↻ Recheck", "× Failed", "× Failed"][step];
    document.getElementById("guide-retain").textContent = step ? "✓ Unchanged" : "Recorded";
    start.hidden = step !== 0; interaction.hidden = step === 0; back.hidden = step === 0;
    next.hidden = step !== 1 && step !== 2;
    contrast.hidden = step !== 1;
    cover.removeAttribute("data-guide-contrast");
    next.textContent = step === 1 ? "Recheck gravity →" : "Review the handoff →";
    handoff.hidden = step !== 3;
    try { history.replaceState(Object.assign({}, history.state, {livingRecordGuide: step}), ""); } catch (_) {}
    if (focus) {
      (step === 0 ? start : step === 3 ? handoff.querySelector("a") : next).focus({preventScroll: true});
    }
  }
  // The reader changes scenes. No renderer, clock or network request drives the guide.
  guideTitle.setAttribute("aria-live", "polite");
  copy.setAttribute("aria-live", "polite");
  copy.setAttribute("aria-atomic", "true");
  start.hidden = false; fallback.hidden = true; explore.hidden = false;
  if (fileStart) { fileStart.hidden = false; }
  start.addEventListener("click", function () { showGuide(1, true); });
  next.addEventListener("click", function () { showGuide(guideStep + 1, true); });
  contrast.addEventListener("click", function () {
    if (guideStep !== 1) { return; }
    cover.setAttribute("data-guide-contrast", "");
    copy.textContent = contrast.dataset.explanation;
  });
  back.addEventListener("click", function () { showGuide(guideStep - 1, true); });

  function returnToArchitecture(focusStart) {
    demoOpen = false;
    if (controls) { controls.stop(); }
    demo.hidden = true; cover.hidden = false;
    if (focusStart !== false) { (explorerEntry || explore).focus(); }
  }
  function revealHeading() {
    var top = heading.getBoundingClientRect().top, covered = header ? Math.max(0, header.getBoundingClientRect().bottom) : 0;
    if (top < covered || top >= window.innerHeight) { heading.scrollIntoView({block: "start", behavior: "instant"}); }
  }
  function openExample(savedStep, comparing, selection) {
    demoOpen = true; cover.hidden = true; demo.hidden = false;
    if (!controls) { controls = createRecord(function () { return demoOpen; }, returnToArchitecture); }
    if (!controls) {
      demoOpen = false; demo.hidden = true; cover.hidden = false;
      explore.hidden = true; if (fileStart) { fileStart.hidden = true; }
      return;
    }
    controls.play(savedStep, comparing, selection);
  }
  explore.addEventListener("click", function () {
    explorerEntry = explore;
    openExample(0);
    if (!demoOpen) { fallback.click(); return; }
    document.getElementById("record-explorer").open = true;
    document.getElementById("record-picker").focus();
  });
  if (fileStart) { fileStart.addEventListener("click", function () {
    explorerEntry = fileStart;
    openExample(0);
    if (!demoOpen) { fallback.click(); return; }
    document.getElementById("mind-file-action").click();
    heading.focus({preventScroll: true});
    revealHeading();
  }); }
  demo.addEventListener("click", function (event) {
    if (event.target.closest("[data-mind=next],[data-mind=previous]")) { revealHeading(); }
  });
  function requestedRecord() {
    if (location.hash === "#review") { return "review"; }
    if (!location.hash.startsWith("#record=")) { return ""; }
    try { return decodeURIComponent(location.hash.slice(8)); } catch (_) { return ""; }
  }
  function restoreEntry() {
    var state = history.state || {}, savedStep = state.livingRecordStep, key = requestedRecord();
    if (key) {
      var saved = state.livingRecordSelection;
      openExample(undefined, false, saved && saved.key === key ? saved :
        {key: key, changed: [], expanded: true, focus: "heading", direct: true});
    }
    else if (Number.isInteger(savedStep) && savedStep >= 0) { openExample(savedStep, state.livingRecordComparing === true); }
    else {
      if (demoOpen) { returnToArchitecture(false); }
      showGuide(state.livingRecordGuide, false);
    }
  }
  window.addEventListener("popstate", restoreEntry);
  window.addEventListener("hashchange", function () {
    var key = requestedRecord(), saved = history.state && history.state.livingRecordSelection;
    if (key && (!saved || saved.key !== key)) { restoreEntry(); }
  });
  window.addEventListener("pageshow", function (event) {
    if (event.persisted && controls && history.state && history.state.livingRecordSelection) {
      controls.restoreFocus(history.state.livingRecordSelection);
    }
  });
  restoreEntry();

}(function createRecord(isOpen, returnToArchitecture) {
  "use strict";
  var canvas = document.getElementById("mind"), source = document.getElementById("record-graph");
  if (!canvas || !source || !canvas.getContext) { return; }
  var G;
  try { G = JSON.parse(source.textContent); } catch (_) { return; }
  if (!G || !Array.isArray(G.nodes) || !Array.isArray(G.edges) || !G.nodes.length) { return; }
  var N = G.nodes, E = G.edges;
  var figure = document.querySelector(".mind") || canvas.parentNode;
  var sayEl = document.getElementById("mind-copy") || document.getElementById("mind-say"), tallyEl = document.getElementById("mind-tally");
  var tip = document.getElementById("mind-tip");
  var query = function (text) { return !!(window.matchMedia && window.matchMedia(text).matches); };
  var still = query("(prefers-reduced-motion: reduce)"), coarse = query("(pointer: coarse)");
  var ctx = canvas.getContext("2d");
  if (!ctx) { return; }
  var C = { holds: "#6fd3a0", stale: "#f2a23a", fails: "#ef8f80", file: "#bfe6f2", ink: "#eef3ee", gold: "#e3bd6a" };
  var LINE = "127,231,196", MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
  var HUB = [0.5, 0.46, 0], T = 0.2, W = 0, H = 0, dpr = 1, unit = 1, clock = 0, seed = 11, box = [0, 0, 1, 1], cosY = 1, sinY = 0;

  function rnd() { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; }
  function esc(text) { return String(text).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }
  var recordNames = {
    "examples/measurement/data/swings.csv": "Pendulum readings",
    "examples/measurement/analysis/fit.py": "Gravity calculation",
    "examples/measurement/analysis/check.py": "Gravity acceptance check",
    "examples/measurement/figures/style.txt": "Pendulum figure settings",
    "site/plot_pendulum.py": "Pendulum plotting script",
    "site/measurement_exhibit.py": "Pendulum evidence page builder",
    "site/assets/pendulum-sensitivity.png": "Pendulum sensitivity plot",
    "examples/model_evaluation/a.csv": "Instrument A readings",
    "examples/model_evaluation/b.csv": "Instrument B readings",
    "examples/model_evaluation/policy.json": "Instrument flagging threshold",
    "examples/model_evaluation/predictions.json": "Predicted instrument results",
    "bootstrap/answers.example.json": "Example project settings",
    "bootstrap/answers.schema.json": "Project settings format",
    "evals/model_evaluation.schema.json": "Instrument report format",
    ".codex/hooks.json": "Codex checks before commands",
    "evals/results/measurement_audit.json": "Pendulum audit",
    "evals/results/handoff_audit.json": "Handoff experiment",
    "evals/results/reuse_frontier.json": "Check reuse experiment",
    "evals/results/at_revision.json": "Earlier release comparison",
    "evals/results/mutations.json": "Seeded fault experiment",
    "evals/results/model_evaluation.json": "Instrument comparison"
  };
  function plain(node) {
    var path = String(node.l), base = path.split("/").pop();
    if (recordNames[path]) { return recordNames[path]; }
    if (node.k === "p") { return "Evidence page"; }
    if (node.k === "r") { return node.t || base; }
    if (node.k === "c") { return node.t || path; }
    var stem = base.replace(/\.[a-z0-9]+$/i, "").replace(/^test_/, "").replace(/[_-]+/g, " ").trim();
    var title = stem.charAt(0).toUpperCase() + stem.slice(1).toLowerCase();
    if (/(^|\/)tests?\//.test(path) || /^test_/.test(base)) { return title + " tests"; }
    if (/\.py$/i.test(base)) { return title + " script"; }
    if (/\.csv$/i.test(base)) { return title + " data"; }
    if (/\.md$/i.test(base)) { return title + " document"; }
    return title;
  }
  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }

  /* The outline of a brain seen from the side, facing right. */
  var CORTEX = [[0.928, 0.422], [0.912, 0.315], [0.861, 0.229], [0.760, 0.164], [0.626, 0.138], [0.475, 0.127], [0.332, 0.159],
    [0.223, 0.250], [0.130, 0.331], [0.080, 0.439], [0.076, 0.519], [0.114, 0.616], [0.206, 0.675], [0.374, 0.745], [0.500, 0.788],
    [0.592, 0.796], [0.676, 0.777], [0.727, 0.734], [0.744, 0.681], [0.815, 0.643], [0.886, 0.568], [0.920, 0.498]];

  function dense(p, steps, closed) {      /* the smooth curve through these points, as short straight pieces */
    var n = p.length, last = closed ? n : n - 1, out = [], i, k, a, b, c, d, t, u;
    for (i = 0; i < last; i++) {
      b = p[i]; c = p[(i + 1) % n]; a = closed || i > 0 ? p[(i - 1 + n) % n] : b; d = closed || i < n - 2 ? p[(i + 2) % n] : c;
      for (k = 0; k < steps; k++) {
        t = k / steps; u = 1 - t;
        out.push([u * u * u * b[0] + 3 * u * u * t * (b[0] + (c[0] - a[0]) / 6) + 3 * u * t * t * (c[0] - (d[0] - b[0]) / 6) + t * t * t * c[0],
          u * u * u * b[1] + 3 * u * u * t * (b[1] + (c[1] - a[1]) / 6) + 3 * u * t * t * (c[1] - (d[1] - b[1]) / 6) + t * t * t * c[1]]);
      }
    }
    if (!closed) { out.push(p[n - 1]); }
    return out;
  }
  var SMOOTH = dense(CORTEX, 12, true);
  var RIM = (function () {                /* the same outline with the folds of the cortex along its edge */
    var n = SMOOTH.length, out = [], total = 0, s = 0, lambda, i, a, b, q, nx, ny, len;
    function gap(j) { var m = SMOOTH[(j - 1 + n) % n]; return Math.sqrt(Math.pow(SMOOTH[j][0] - m[0], 2) + Math.pow(SMOOTH[j][1] - m[1], 2)); }
    for (i = 0; i < n; i++) { total += gap(i); }
    lambda = total / Math.round(total / 0.058);
    for (i = 0; i < n; i++) {
      a = SMOOTH[(i - 1 + n) % n]; b = SMOOTH[(i + 1) % n]; q = SMOOTH[i];
      nx = b[1] - a[1]; ny = a[0] - b[0]; len = Math.sqrt(nx * nx + ny * ny) || 1; nx /= len; ny /= len;
      if (nx * (q[0] - HUB[0]) + ny * (q[1] - HUB[1]) < 0) { nx = -nx; ny = -ny; }
      if (i) { s += gap(i); }
      len = 0.0085 * Math.abs(Math.sin(Math.PI * s / lambda));
      out.push([q[0] + nx * len, q[1] + ny * len]);
    }
    return out;
  }());
  function radius(a) {                    /* how far the outline is from the centre in one direction */
    var dx = Math.cos(a), dy = Math.sin(a), best = 0, n = SMOOTH.length, i, p, q, ex, ey, den, t, s;
    for (i = 0; i < n; i++) {
      p = SMOOTH[i]; q = SMOOTH[(i + 1) % n]; ex = q[0] - p[0]; ey = q[1] - p[1]; den = dx * ey - dy * ex;
      if (Math.abs(den) < 1e-9) { continue; }
      t = ((p[0] - HUB[0]) * ey - (p[1] - HUB[1]) * ex) / den; s = ((p[0] - HUB[0]) * dy - (p[1] - HUB[1]) * dx) / den;
      if (t > best && s >= 0 && s <= 1) { best = t; }
    }
    return best;
  }

  /* Where each record sits. Files line the back in three layers, the ones the most
     stands on nearest the centre. Claims line the front. The three measurements sit around the centre, and the page is the face. */
  N.forEach(function (node, i) { node.i = i; node.state = "holds"; node.on = []; node.under = []; });
  E.forEach(function (edge, i) { N[edge[0]].on.push(i); N[edge[1]].under.push(i); });
  function reach(file) {          /* every record that stands on this file, directly or through a measurement */
    var seen = {}, queue = [file];
    while (queue.length) { N[queue.pop()].under.forEach(function (i) { var r = E[i][0]; if (!seen[r]) { seen[r] = true; queue.push(r); } }); }
    return Object.keys(seen).map(Number);
  }
  function kind(k, g) { return N.filter(function (node) { return node.k === k && (g === undefined || g.indexOf(node.g) >= 0); }); }
  function arc(list, from, to, scale, z) {
    list.forEach(function (node, k) {
      var a = from + (to - from) * (list.length === 1 ? 0.5 : k / (list.length - 1)), r = radius(a) * scale;
      node.at = [HUB[0] + Math.cos(a) * r, HUB[1] + Math.sin(a) * r, z];
    });
  }
  var records = N.filter(function (node) { return node.k !== "f"; }), claimed = kind("c").length;
  var files = N.filter(function (node) { return node.k === "f" && node.under.length; });
  var code = kind("f").sort(function (a, b) { return reach(b.i).length - reach(a.i).length; });
  var inner = Math.round(code.length * 0.2), middle = Math.round(code.length * 0.33);
  arc(code.slice(0, inner), 2.20, 4.42, 0.52, 0.5); arc(code.slice(inner, inner + middle), 2.12, 4.50, 0.69, -0.5); arc(code.slice(inner + middle), 2.06, 4.57, 0.86, 0);
  arc(kind("c", [0, 1]), -1.40, 1.01, 0.86, 0); arc(kind("c", [2, 3]), -1.30, 0.92, 0.69, 0.5); arc(kind("c", [4]), -1.05, 0.72, 0.52, -0.5);
  // Recorded experiments surround the assistants. Assistants are illustrative actors, outside the dependency graph.
  var runSlots = [[0.32, 0.28], [0.71, 0.28], [0.64, 0.20], [0.68, 0.61], [0.335, 0.61], [0.76, 0.43]];
  kind("r").forEach(function (node, k, all) {
    var a = k * 2 * Math.PI / all.length;
    var slot = runSlots[k] || [0.5 + 0.24 * Math.cos(a), 0.42 + 0.22 * Math.sin(a)];
    node.at = [slot[0], slot[1], 0];
  });
  kind("p").forEach(function (node) { node.at = [0.91, 0.46, 0]; });
  var experiments = kind("r");
  var gravity = experiments.find(function (n) { return n.l === "evals/results/measurement_audit.json"; });
  var instruments = experiments.find(function (n) { return n.l === "evals/results/model_evaluation.json"; });
  var swing = files.find(function (node) { return node.l === "examples/measurement/data/swings.csv"; });
  if (swing) { swing.at = [0.222, 0.40, 0]; }
  N.forEach(function (node) { if (!node.at) { node.at = [0.5, 0.9, 0]; } node.s = [0, 0, 0]; });

  /* Every link is a spoke. A measurement is joined straight to what it stands on and to what stands on it. Anything
     else goes through the centre, where the one comparison is made. Spokes bow away from the middle like a fountain. */
  function spoke(p, q) {
    var dx = q[0] - p[0], dy = q[1] - p[1], len = Math.sqrt(dx * dx + dy * dy) || 1, nx = -dy / len, ny = dx / len, my = (p[1] + q[1]) / 2;
    if (ny < 0) { nx = -nx; ny = -ny; }
    len *= my >= HUB[1] ? 0.08 : -0.08;
    return [p, [(p[0] + q[0]) / 2 + nx * len, my + ny * len, (p[2] + q[2]) / 2], q];
  }
  var SEG = E.map(function (edge) {
    var rec = N[edge[0]], base = N[edge[1]];
    return rec.k === "r" || base.k === "r" ? [spoke(rec.at, base.at)] : [spoke(rec.at, HUB), spoke(HUB, base.at)];
  }), EP = SEG.map(function (segs) { return segs.map(function () { return [0, 0, 0, 0, 0, 0]; }); });

  function project(u, v, z) {
    var dx = u - 0.5, dz = z * T, x = dx * cosY + dz * sinY, depth = dz * cosY - dx * sinY, k = 1 + depth * 0.2;
    return [box[0] + (0.5 + x * k) * box[2], box[1] + (0.572 + (v - 0.53) * k) * box[3], depth];
  }
  function flat(u, v) { return [box[0] + u * box[2], box[1] + v * box[3]]; }
  function place() {              /* where everything is on the screen for this turn of the head */
    var i, k, s, a, c, b;
    for (i = 0; i < N.length; i++) { N[i].s = project(N[i].at[0], N[i].at[1], N[i].at[2]); }
    for (i = 0; i < SEG.length; i++) {
      for (k = 0; k < SEG[i].length; k++) {
        s = SEG[i][k]; a = project(s[0][0], s[0][1], s[0][2]); c = project(s[1][0], s[1][1], s[1][2]); b = project(s[2][0], s[2][1], s[2][2]);
        EP[i][k] = [a[0], a[1], c[0], c[1], b[0], b[1]];
      }
    }
  }
  function along(i, t) {          /* t = 0 at the record, 1 at what it stands on */
    var n = EP[i].length, f = Math.min(n - 1, Math.floor(t * n)), s = EP[i][f], w = t * n - f, u = 1 - w;
    return [u * u * s[0] + 2 * u * w * s[2] + w * w * s[4], u * u * s[1] + 2 * u * w * s[3] + w * w * s[5]];
  }
  function link(i) { EP[i].forEach(function (s, k) { if (!k) { ctx.moveTo(s[0], s[1]); } ctx.quadraticCurveTo(s[2], s[3], s[4], s[5]); }); }
  function outline(points, z, scale, cx, cy, open) {
    var i, q;
    ctx.beginPath();
    for (i = 0; i < points.length; i++) {
      q = project(cx + (points[i][0] - cx) * scale, cy + (points[i][1] - cy) * scale, z);
      if (i) { ctx.lineTo(q[0], q[1]); } else { ctx.moveTo(q[0], q[1]); }
    }
    if (!open) { ctx.closePath(); }
  }
  function size(node) { return (node.k === "r" ? 6.2 : node.k === "p" ? 5.6 : node.k === "c" ? 3 : 2) * unit; }

  var story = null, pulses = [], rings = [], hover = -1, touched = false, shown = true, raf = 0, asked = false;

  var reading = document.getElementById("swing-reading");
  var display = reading && reading.dataset;
  var actors = [
    {name: "Claude", u: 0.37, v: 0.337}, {name: "Codex", u: 0.627, v: 0.337},
    {name: "ChatGPT", u: 0.36, v: 0.49}, {name: "Claude Code", u: 0.66, v: 0.49},
    {name: "Gemini", u: 0.5, v: 0.635}
  ];
  // Leave time to read each caption and look at the corresponding nodes.
  // The last result stays on screen until the reader moves on.
  var chapterStarts = [0, 4650, 11300, 16300, 21700];
  var traceDuration = 1650;
  var stage = canvas.parentNode;
  var labels = document.getElementById("story-labels");
  var swingLabel = labels.querySelector(".swing-label");
  var gravityLabel = labels.querySelector(".gravity-label");
  var instrumentLabel = labels.querySelector(".instrument-label");
  var positionLabels = true, instrumentPin = [0, 0];
  var person = stage.querySelector(".mind-person");
  var userPoint = [0, 0];
  var storyHeadline = document.getElementById("mind-title");
  var replay = figure.querySelector("[data-case=swing]");
  var previous = figure.querySelector("[data-mind=previous]");

  var comparison = document.getElementById("timing-comparison");
  var compareAgain = document.getElementById("compare-swing-times");
  var comparing = false;
  var pauseButton = figure.querySelector("[data-mind-pause]");
  var paused = false;

  // Keep the controls beside the caption on a phone, including in the tab order.
  var compact = window.matchMedia && window.matchMedia("(max-width: 34em)");
  var controlsRow = figure.querySelector(".story-controls");
  function placeControls() {
    var anchor = figure.querySelector(compact.matches ? ".mind-story" : ".mind-read");
    if (controlsRow.previousElementSibling === anchor) { return; }
    var focused = document.activeElement;
    anchor.after(controlsRow);
    if (controlsRow.contains(focused)) { focused.focus({preventScroll: true}); }
  }
  if (compact) {
    placeControls();
    if (compact.addEventListener) { compact.addEventListener("change", placeControls); }
    else { compact.addListener(placeControls); }
  }

  function setPause(value) {
    paused = value;
    if (pauseButton) {
      pauseButton.textContent = paused ? "Continue" : "Pause";
      pauseButton.setAttribute("aria-pressed", String(paused));
      pauseButton.hidden = still || !story || story.step === chapterStarts.length - 1;
    }
    if (!paused) { last = 0; }
  }

  function storyCopy(step) {
    var headings = ["You have two results to review.", "Claude corrects one swing time.",
      "The old gravity estimate needs a new check.", "You hand the review to Codex.",
      "Codex sets the old gravity estimate aside."];
    storyHeadline.textContent = comparing ? "Which fit does this swing time support?" : headings[step];
    if (comparison) {
      var key = step === 0 ? "original" : "corrected";
      comparison.hidden = step !== 1 && !comparing;
      comparison.querySelector('input[value="' + key + '"]').checked = true;
      comparison.querySelectorAll("[data-fit]").forEach(function (fit) {
        fit.hidden = !comparing || fit.dataset.fit !== key;
      });
      gravityLabel.href = comparison.querySelector('[data-fit="' + key + '"] a').getAttribute("data-case");
    }
    if (comparing || (comparison && step === 1)) {
      sayEl.textContent = "";
    } else if (step === 0) {
      sayEl.textContent = "One study estimated gravity from swing times. Another tested two instruments on known faults.";
    } else if (step === 1) {
      say('<span class="timing-comparison"><span><small>Earlier swing time</small><strong>' + esc(display.oldPeriod) +
        ' s</strong></span><span class="timing-arrow" aria-hidden="true">→</span><span><small>Corrected time</small><strong>' +
        esc(display.newPeriod) + ' s</strong></span></span>');
    } else if (step === 2) {
      sayEl.textContent = "At this length, a longer swing gives a lower estimate. Orange marks the old " +
        Number(display.oldG).toFixed(2) + " m/s².";
    } else if (step === 3) {
      sayEl.textContent = "The corrected estimate is " + Number(display.newG).toFixed(2) +
        " m/s². This study requires at least " + display.low + " m/s².";
    } else {
      sayEl.textContent = "The old estimate used the original time. The instrument comparison used separate readings, so Codex can keep it.";
    }
    swingLabel.textContent = step ? "Changed time" : "Swing time";
    var gravityStatus = ["From swing times", "↻ Recheck", "↻ Recheck", "× New check failed", "⊘ Set aside"][step];
    if (comparing) { gravityStatus = step === 0 ? "✓ Check passed" : "× New check failed"; }
    gravityLabel.querySelector("small").textContent = gravityStatus;
    instrumentLabel.querySelector("small").textContent = step ? "✓ Keep using" : "Separate readings";
    labels.toggleAttribute("data-corrected", step >= 1);
  }

  function beginStory() {
    dismissSelection(false);
    if (disclosure) { disclosure.open = false; }
    if (!swing || !gravity || !instruments || !display) { return; }
    var edge = gravity.on.find(function (i) { return E[i][1] === swing.i; });
    if (edge === undefined) { return; }
    story = {start: clock, step: -1, timingEdge: edge, traceStart: null};
    labels.hidden = false;
    positionLabels = true;
    hover = -1; inspectRecord(-1);
    setPause(false);
    updateStory(0);
  }

  function updateStory(step, automatic) {
    if (!story || step === story.step) { return; }
    if (inlineSelected) { dismissSelection(false); }
    if (step >= 1 && !swing.changed) { change(swing.i, true); }
    story.step = step;
    rememberStep(step);
    story.traceStart = !still && !paused && (step === 1 || step === 4) ? clock : null;
    if (replay) { replay.textContent = step < chapterStarts.length - 1 ? "Next step" : "Replay"; }
    if (previous) { previous.hidden = false; previous.disabled = step === 0; }
    if (pauseButton) { pauseButton.hidden = still || step === chapterStarts.length - 1; }
    storyCopy(step);
    var caption = storyHeadline.parentNode;
    if (automatic && !still && caption.animate) {
      caption.animate([{opacity: 0.78}, {opacity: 1}], {duration: 200, easing: "ease-out"});
    }
    if (reading) { reading.hidden = step < 4; }
    if (tallyEl) { tallyEl.hidden = true; }
  }

  // Keep the opted-in chapter on this browser history entry, including when
  // the browser discards the document while the reader inspects evidence.
  function rememberStep(step) {
    var state = history.state || {};
    var keepComparison = comparing && (step === 0 || step === 1);
    if (state.livingRecordStep === step && !!state.livingRecordComparing === keepComparison) { return; }
    var next = Object.assign({}, state);
    if (step === undefined) { delete next.livingRecordStep; }
    else { next.livingRecordStep = step; }
    if (keepComparison) { next.livingRecordComparing = true; }
    else { delete next.livingRecordComparing; }
    try { history.replaceState(next, ""); } catch (_) { /* History can be unavailable in an embedded preview. */ }
  }

  function seekStep(step) {
    var goingBack = step < story.step, keepPaused = paused || goingBack;
    if (goingBack) { resetRecord(); beginStory(); }
    story.start = clock - chapterStarts[step];
    setPause(keepPaused);
    updateStory(step);
  }

  // Reuse the two recorded chapters so the diagram, link and fitted value
  // always refer to the same input. Explicit comparison pauses the clock.
  function compareTime(input) {
    if (!story) { return; }
    comparing = true;
    setPause(true);
    var step = input.value === "original" ? 0 : 1;
    if (step !== story.step) { seekStep(step); }
    else { storyCopy(step); rememberStep(step); }
    wake();
  }
  if (comparison) {
    comparison.addEventListener("focusin", function () { setPause(true); });
    comparison.addEventListener("click", function (event) {
      if (event.target.matches('input[name="swing-time"]')) { compareTime(event.target); }
    });
    if (compareAgain) {
      compareAgain.addEventListener("click", function () {
        var input = comparison.querySelector('input[value="corrected"]');
        compareTime(input);
        input.focus();
      });
    }
  }

  function leaveStory() {
    comparing = false;
    if (comparison) { comparison.hidden = true; }
    rememberStep(undefined);
    labels.hidden = true;
    if (tallyEl) { tallyEl.hidden = false; }
    story = null;
    if (replay) { replay.textContent = "Replay"; }
    if (previous) { previous.hidden = true; }
    setPause(false);
    if (reading) { reading.hidden = true; }
    if (storyHeadline) { storyHeadline.textContent = "Explore the evidence behind a result."; }
  }

  function ring(i, colour) { if (!still) { rings.push({ i: i, start: clock, colour: colour }); } }
  function pulse(i, outward, delay, time, colour, done) {
    if (still) { if (done) { done(); } return; }
    pulses.push({ i: i, out: outward, start: clock + delay, time: time * EP[i].length, colour: colour, done: done });
  }
  function staleCount(extra) {
    var set = {}; (extra || []).forEach(function (i) { set[i] = true; });
    records.forEach(function (node) { if (node.state === "stale") { set[node.i] = true; } });
    return Object.keys(set).length;
  }
  function say(html) { if (sayEl) { sayEl.innerHTML = html; } }
  function tally() {
    var stale = staleCount();
    if (tallyEl) { tallyEl.innerHTML = "<span class=\"holds\">" + (records.length - stale) + " still apply</span><span class=\"stale\">" + stale + " to recheck</span>"; }
    var action = document.getElementById("mind-file-action");
    var input = action && files.find(function (node) { return node.l === action.getAttribute("data-file"); });
    if (input) { action.textContent = input.changed ? "Reset simulated edits" : "Edit the experiment script"; }
  }
  // Standing is computed on input. A frame or pulse can only change what is drawn.
  function change(file, guided) {
    var node = N[file], hit;
    if (node.changed) { say("This file has already changed in this example."); return; }
    if (!guided) { leaveStory(); }
    hit = reach(file);
    node.changed = true;
    if (!guided) { ring(file, C.ink); wave(node.at, [1, 0.72, 0.3]); }
    hit.forEach(function (i) {
      var affected = N[i];
      affected.state = "stale";
      affected.on.forEach(function (edge) {
        var input = N[E[edge][1]];
        if (!guided && (input.i === file || hit.indexOf(input.i) !== -1)) {
          pulse(edge, false, input.i === file ? 0 : 190, 420, C.stale);
        }
      });
    });
    tally();
    if (guided) { return; }

    say(hit.length ? esc(plain(node)) + " changed. " + plural(hit.length, "saved result") +
        (hit.length === 1 ? " needs" : " need") + " another check." : "No result in this example uses that file.");
  }
  function resetRecord() {
    labels.hidden = true;
    if (tallyEl) { tallyEl.hidden = false; }
    if (reading) { reading.hidden = true; }
    story = null;
    setPause(false);
    pulses.length = 0;
    rings.length = 0;
    waves.length = 0;
    hover = -1;
    if (tip) { tip.hidden = true; }
    if (explorer) { explorer.value = ""; }
    N.forEach(function (node) {
      node.changed = false;
      node.state = "holds";
    });
    tally();
    if (replay) { replay.textContent = "Replay the handoff"; }

  }
  function takeOver() {
    if (touched) { return; }
    touched = true;
    if (sayEl) { sayEl.setAttribute("aria-live", "polite"); }

  }

  /* The brain itself. Where the browser can, it is a true three-dimensional shape worked out point by point on the
     graphics card and drawn as a hologram: a shell of glass with a bright edge, the furrows of the cortex as fine
     lines of light, and a plane of light passing down through it. Nothing is shaded like flesh. It is turned by the
     same angle as the records, so every dot keeps its place inside it. The front warms where records are stale, and
     a ring of light crosses the shell when a file changes or the checks run again. Where the graphics card is not
     available, the outline further down is drawn instead. */
  var S = 0.42, waves = [], amber = 0;
  function inBrain(at) { return [(at[0] - 0.5) / S, -(at[1] - 0.53) / 1.28 / S, at[2] * T / S]; }
  function wave(at, tint) {
    if (still || !BRAIN) { return; }
    waves.push({ b: inBrain(at), start: clock, tint: tint }); if (waves.length > 3) { waves.shift(); }
  }
  var FRAG = [
    "#ifdef GL_FRAGMENT_PRECISION_HIGH",
    "precision highp float;",
    "#else",
    "precision mediump float;",
    "#endif",
    "uniform vec2 uRes; uniform vec2 uCS; uniform float uTime; uniform float uStale; uniform vec4 uWave[3]; uniform vec3 uTint[3];",
    "const float S = 0.42; const float ASP = 1.28;",
    "float ell(vec3 p, vec3 r) { float k0 = length(p / r); float k1 = length(p / (r * r)); return k0 * (k0 - 1.0) / max(k1, 0.0001); }",
    "float smin(float a, float b, float k) { float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0); return mix(b, a, h) - k * h * (1.0 - h); }",
    "float seg(vec2 p, vec2 a, vec2 b) { vec2 pa = p - a; vec2 ba = b - a; return length(pa - ba * clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0)); }",
    "float gyr(vec3 q) { return dot(sin(q), cos(q.yzx)); }",
    "float field(vec3 p) {",                         /* where this is zero on the shell, a furrow runs */
    "  vec3 q = p * 17.0;",
    "  q += 1.9 * sin(q.yzx * 0.31 + vec3(0.3, 1.7, 4.1));",
    "  q += 0.8 * sin(q.zxy * 0.77 + vec3(2.1, 0.4, 3.3));",
    "  return gyr(q) + 0.5 * gyr(q * 0.61 + vec3(1.3, 4.2, 0.7));",
    "}",
    "float smooth3(vec3 b) {",                       /* the frontal, parietal and occipital mass, and the temporal lobe under it */
    "  vec3 p = vec3(b.x, b.y, abs(b.z));",
    "  float c = ell(p - vec3(0.50, 0.20, 0.30), vec3(0.52, 0.46, 0.36));",
    "  c = smin(c, ell(p - vec3(-0.06, 0.25, 0.33), vec3(0.70, 0.50, 0.39)), 0.10);",
    "  c = smin(c, ell(p - vec3(-0.62, 0.10, 0.25), vec3(0.40, 0.38, 0.31)), 0.10);",
    "  vec3 t = p - vec3(0.03, -0.26, 0.40);",
    "  t.xy = vec2(0.9856 * t.x - 0.1692 * t.y, 0.1692 * t.x + 0.9856 * t.y);",
    "  return smin(c, ell(t, vec3(0.54, 0.22, 0.27)), 0.09);",
    "}",
    "float map(vec3 b) {",                           /* the same shell, dented a little along each furrow so the edge is a brain's */
    "  float c = smooth3(b);",
    "  if (c < 0.06) { c += 0.022 * (1.0 - smoothstep(0.0, 0.5, abs(field(b)))); }",
    "  return c;",
    "}",
    "void main() {",
    "  vec2 uv = gl_FragCoord.xy / uRes;",
    "  vec2 p = vec2(uv.x - 0.5, (1.0 - uv.y - 0.572) / ASP);",
    "  vec3 col = vec3(0.0);",
    "  if (abs(p.x) < 0.49 && p.y > -0.37 && p.y < 0.26) {",
    "    float d = 0.47; float near = 9.0; float hit = 0.0; vec3 b = vec3(0.0); float m = 9.0;",
    "    for (int i = 0; i < 72; i++) {",
    "      vec2 xy = p / (1.0 + 0.2 * d);",
    "      b = vec3((xy.x * uCS.x - d * uCS.y) / S, -xy.y / S, (xy.x * uCS.y + d * uCS.x) / S);",
    "      m = map(b); near = min(near, m);",
    "      if (m < 0.001) { hit = 1.0; break; }",
    "      d -= m * S * 0.7;",
    "      if (d < -0.47) { break; }",
    "    }",
    "    vec3 mint = vec3(0.50, 0.91, 0.77); vec3 white = vec3(0.92, 1.0, 0.97);",
    "    vec3 tone = mix(mint, vec3(0.97, 0.68, 0.28), uStale * smoothstep(-0.25, 0.65, b.x) * 0.85);",
    "    float px = 1.0 / (S * uRes.x);",
    "    if (hit > 0.5) {",
    "      vec2 k = vec2(1.0, -1.0); float e = 0.003;",
    "      vec3 n = normalize(k.xyy * smooth3(b + k.xyy * e) + k.yyx * smooth3(b + k.yyx * e) + k.yxy * smooth3(b + k.yxy * e) + k.xxx * smooth3(b + k.xxx * e));",
    "      float facing = clamp(dot(n, vec3(-uCS.y, 0.0, uCS.x)), 0.0, 1.0);",
    "      float away = 1.0 - facing; float rim = away * away * away;",
    "      float pass = (b.y - (1.0 - 1.9 * fract(uTime / 9.0))) / 0.16;",             /* a soft band of light passing down */
    "      float sheen = exp(-pass * pass);",
    "      col = tone * (0.022 + 0.07 * away) * (1.0 + 0.7 * sheen)",                 /* the glass, and a soft light passing down it */
    "          + mix(tone, white, rim) * rim * 1.0;",                                 /* the edge */
    "      for (int j = 0; j < 3; j++) {",
    "        if (uWave[j].w >= 0.0) {",
    "          float r = length(b - uWave[j].xyz) - uWave[j].w * 1.15;",
    "          col += uTint[j] * exp(-r * r / 0.006) * max(0.0, 1.0 - uWave[j].w / 1.6) * (0.05 + 0.25 * away);",
    "        }",
    "      }",
    "    } else {",
    "      float edge = 1.0 - smoothstep(0.0, 2.0 * px, near);",
    "      col = mix(tone, white, 0.8) * edge * 0.95 + tone * exp(-near * 30.0) * 0.06;",
    "    }",
    "  }",
    "  col = min(col, vec3(1.0));",
    "  gl_FragColor = vec4(col, max(col.r, max(col.g, col.b)));",
    "}"
  ].join("\n");
  var BRAIN = null, rendererReady = false;
  function createBrain() {
    var c = document.createElement("canvas"), gl = null, prog, at, loc = {}, lost = false, quality = 1, fullW = 0, fullH = 0;
    var pace = 16, count = 0, prev = 0, W4 = new Float32Array(12), T3 = new Float32Array(9);
    try {
      gl = c.getContext("webgl", { alpha: true, antialias: false, depth: false, stencil: false, premultipliedAlpha: true }) || c.getContext("experimental-webgl");
    } catch (e) { gl = null; }
    if (!gl) { return null; }
    function shader(type, text) {
      var s = gl.createShader(type); gl.shaderSource(s, text); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { throw new Error(gl.getShaderInfoLog(s) || "shader"); }
      return s;
    }
    try {
      prog = gl.createProgram();
      gl.attachShader(prog, shader(gl.VERTEX_SHADER, "attribute vec2 a; void main() { gl_Position = vec4(a, 0.0, 1.0); }"));
      gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FRAG)); gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { throw new Error(gl.getProgramInfoLog(prog) || "link"); }
    } catch (e) {
      if (window.console && window.console.warn) { window.console.warn("The brain is drawn as an outline: " + e.message); }
      return null;
    }
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer()); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    at = gl.getAttribLocation(prog, "a"); gl.enableVertexAttribArray(at); gl.vertexAttribPointer(at, 2, gl.FLOAT, false, 0, 0);
    ["uRes", "uCS", "uTime", "uStale", "uWave", "uTint"].forEach(function (name) { loc[name] = gl.getUniformLocation(prog, name); });
    c.addEventListener("webglcontextlost", function (event) { event.preventDefault(); lost = true; });
    function resize() {
      var w = Math.max(2, Math.round(fullW * quality)), h = Math.max(2, Math.round(fullH * quality));
      if (c.width !== w || c.height !== h) { c.width = w; c.height = h; gl.viewport(0, 0, w, h); }
    }
    return {
      canvas: c,
      ok: function () { return !lost && fullW > 1; },
      size: function (w, h) { fullW = w; fullH = h; resize(); },
      draw: function () {
        var now = window.performance && window.performance.now ? window.performance.now() : 0, i, w, age;
        if (prev && now - prev < 250) {         /* a slow machine gets a coarser picture, not a slower page */
          pace += (now - prev - pace) * 0.08; count += 1;
          if (count > 50 && pace > 27 && quality > 0.5) { quality = Math.max(0.5, quality * 0.75); count = 0; pace = 16; resize(); }
        }
        prev = now;
        amber += (Math.min(1, staleCount() / 12) - amber) * (still || story ? 1 : 0.05);
        for (i = 0; i < 3; i++) {
          w = waves[i]; age = w ? (clock - w.start) / 1000 : -1;
          if (w && age < 1.7) { W4[i * 4] = w.b[0]; W4[i * 4 + 1] = w.b[1]; W4[i * 4 + 2] = w.b[2]; W4[i * 4 + 3] = age; T3[i * 3] = w.tint[0]; T3[i * 3 + 1] = w.tint[1]; T3[i * 3 + 2] = w.tint[2]; }
          else { W4[i * 4 + 3] = -1; }
        }
        gl.uniform2f(loc.uRes, c.width, c.height); gl.uniform2f(loc.uCS, cosY, sinY);
        gl.uniform1f(loc.uTime, story || still ? 0 : clock / 1000); gl.uniform1f(loc.uStale, amber);
        gl.uniform4fv(loc.uWave, W4); gl.uniform3fv(loc.uTint, T3);
        gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
    };
  }

  function label(text, x, y, align, colour) {
    ctx.textAlign = align; ctx.lineWidth = 3.2; ctx.strokeStyle = "rgba(6,15,11,0.92)"; ctx.strokeText(text, x, y);
    ctx.fillStyle = colour; ctx.fillText(text, x, y);
  }
  function stroke(alpha, width) { ctx.strokeStyle = "rgba(" + LINE + "," + alpha + ")"; ctx.lineWidth = width; ctx.stroke(); }
  var shellPicture = document.createElement("canvas"), shellKey = "";
  var shellContext = shellPicture.getContext("2d");
  function hologram() {           /* the head itself: a pool of light under it, its outline, and a band of light passing down */
    var base = flat(0.5, 0.945), rx = 0.25 * box[2], n = RIM.length, beam, glow, q, sweep, band, edge, head, i, k;
    ctx.save(); ctx.translate(base[0], base[1]); ctx.scale(1, 0.11);
    glow = ctx.createRadialGradient(0, 0, 0, 0, 0, rx);
    glow.addColorStop(0, "rgba(" + LINE + ",0.17)"); glow.addColorStop(1, "rgba(" + LINE + ",0)");
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(0, 0, rx, 0, 6.2832); ctx.fill(); ctx.restore();
    ctx.beginPath(); ctx.ellipse(base[0], base[1], rx * 0.7, rx * 0.055, 0, 0, 6.2832); stroke(0.2, 1);
    if (BRAIN && BRAIN.ok()) {
      var key = [canvas.width, canvas.height, staleCount()].join("/");
      if (shellContext && (story || still)) {
        if (key !== shellKey) {
          BRAIN.draw();
          shellPicture.width = BRAIN.canvas.width; shellPicture.height = BRAIN.canvas.height;
          shellContext.drawImage(BRAIN.canvas, 0, 0); shellKey = key;
        }
        ctx.drawImage(shellPicture, box[0], box[1], box[2], box[3]);
      } else {
        shellKey = ""; BRAIN.draw(); ctx.drawImage(BRAIN.canvas, box[0], box[1], box[2], box[3]);
      }
      return;
    }

    q = project(HUB[0], HUB[1], 0);
    glow = ctx.createRadialGradient(q[0], q[1], 0, q[0], q[1], box[2] * 0.5);
    glow.addColorStop(0, "rgba(" + LINE + ",0.13)"); glow.addColorStop(0.7, "rgba(" + LINE + ",0.045)"); glow.addColorStop(1, "rgba(" + LINE + ",0.02)");
    ctx.save(); outline(RIM, 0, 1, HUB[0], HUB[1]); ctx.clip();
    ctx.fillStyle = glow; ctx.fillRect(0, 0, W, H);
    if (!still && !story) {
      sweep = (clock % 7200) / 7200; band = flat(0, -0.05 + sweep * 1.1)[1]; edge = box[3] * 0.07;
      beam = ctx.createLinearGradient(0, band - edge, 0, band + edge);
      beam.addColorStop(0, "rgba(170,255,228,0)"); beam.addColorStop(0.5, "rgba(170,255,228,0.075)"); beam.addColorStop(1, "rgba(170,255,228,0)");
      ctx.fillStyle = beam; ctx.fillRect(0, band - edge, W, edge * 2);
    }
    ctx.restore();

    ctx.globalCompositeOperation = "lighter"; ctx.lineJoin = "round";
    [[0.45, 0.1]].forEach(function (slice) {
      outline(SMOOTH, slice[0], Math.sqrt(1 - Math.pow(0.88 * slice[0], 2)), HUB[0], HUB[1]); stroke(slice[1], 1);
    });
    ctx.save(); ctx.shadowColor = "rgba(" + LINE + ",0.75)"; ctx.shadowBlur = 16 * unit; outline(RIM, 0, 1, HUB[0], HUB[1]); stroke(0.7, 1.4); ctx.restore();
    if (!still && !story) {       /* a light travels the outline, the way a hologram is drawn */
      head = Math.floor((clock % 9000) / 9000 * n);
      for (k = 0; k < 4; k++) {
        ctx.beginPath();
        for (i = 0; i <= 14; i++) {
          q = RIM[(head - k * 14 - i + n * 8) % n]; q = project(q[0], q[1], 0);
          if (i) { ctx.lineTo(q[0], q[1]); } else { ctx.moveTo(q[0], q[1]); }
        }
        ctx.strokeStyle = "rgba(225,255,244," + (0.85 - k * 0.2).toFixed(2) + ")"; ctx.lineWidth = 2.2 - k * 0.35; ctx.stroke();
      }
    }
    ctx.globalCompositeOperation = "source-over";
  }
  function drawSwing() {
    if (!swing || !display) { return; }
    var period = Number(swing.changed ? display.newPeriod : display.oldPeriod);
    var angle = still || (story && story.step !== 1) ? 0.18 : 0.39 * Math.sin(clock * 2 * Math.PI / (1000 * period));
    var pivot = swing.s, length = Math.max(15, 23 * unit);
    var x = pivot[0] + Math.sin(angle) * length, y = pivot[1] + Math.cos(angle) * length;
    var colour = swing.changed ? C.stale : "#b6d6c8";
    ctx.strokeStyle = colour; ctx.fillStyle = colour; ctx.lineWidth = 1.45;
    ctx.beginPath(); ctx.moveTo(pivot[0], pivot[1]); ctx.lineTo(x, y); ctx.stroke();
    ctx.beginPath(); ctx.arc(x, y, Math.max(2.4, 3.4 * unit), 0, Math.PI * 2); ctx.fill();
    if (!story) {
      ctx.font = "550 " + Math.max(9, 11.5 * unit) + "px " + MONO;
      label((swing.changed ? display.newPeriod : display.oldPeriod) + " s", pivot[0], pivot[1] + length + 14 * unit, "center", colour);
    }
  }

  function drawActors() {
    var human = userPoint, active = story ? (story.step < 2 ? 0 : story.step >= 3 ? 1 : -1) : !touched && swing && !swing.changed ? 0 : -1;
    var radius = Math.max(2.6, 3.5 * unit);
    if (!story) {
      var center = project(0.51, 0.406, 0);
      var halo = ctx.createRadialGradient(center[0], center[1], 0, center[0], center[1], 0.155 * box[2]);
      halo.addColorStop(0, "rgba(7,23,18,0.92)"); halo.addColorStop(0.65, "rgba(7,23,18,0.82)"); halo.addColorStop(1, "rgba(7,23,18,0)");
      ctx.fillStyle = halo; ctx.fillRect(center[0] - box[2] * 0.17, center[1] - box[2] * 0.17, box[2] * 0.34, box[2] * 0.34);
    }
    actors.forEach(function (actor, i) {
      var xy = project(actor.u, actor.v, 0);
      var on = i === active;
      ctx.strokeStyle = on ? C.gold : "rgba(180,217,201,0.56)";
      ctx.fillStyle = on ? C.gold : "#152e24"; ctx.lineWidth = on ? 1.65 : 1;
      ctx.beginPath(); ctx.moveTo(xy[0], xy[1] - radius); ctx.lineTo(xy[0] + radius, xy[1]);
      ctx.lineTo(xy[0], xy[1] + radius); ctx.lineTo(xy[0] - radius, xy[1]); ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.font = (on ? "650 " : "500 ") + Math.max(9, 13 * unit) + "px ui-sans-serif, system-ui, sans-serif";
      var nameY = xy[1] + Math.max(12, 15 * unit);
      if (on) {
        var nameWidth = ctx.measureText(actor.name).width + 10;
        var height = Math.max(13, 17 * unit);
        ctx.fillStyle = C.gold;
        ctx.fillRect(xy[0] - nameWidth / 2, nameY - height / 2, nameWidth, height);
        ctx.fillStyle = "#182018"; ctx.textAlign = "center";
        ctx.fillText(actor.name, xy[0], nameY);
      } else if (!story || i < 2) {
        label(actor.name, xy[0], nameY, "center", story ? "#8da498" : "#b5c9be");
      }
    });
    if (!story || still || (story.step !== 0 && story.step !== 3)) { return; }
    var elapsed = clock - story.start - chapterStarts[story.step];
    if (story.step === 0) { elapsed -= 920; }
    if (elapsed < 0) { return; }
    var t = Math.min(1, elapsed / 1900);
    var claude = project(actors[0].u, actors[0].v, 0), codex = project(actors[1].u, actors[1].v, 0);
    var from = human, to = claude;
    if (story.step === 3) {
      // The flagged estimate reaches the reader, who hands the review to Codex.
      if (elapsed < 800) { from = gravity.s; to = human; t = elapsed / 800; }
      else { to = codex; t = Math.min(1, (elapsed - 800) / 1450); }
    }
    var control = [(from[0]+to[0])/2, (from[1]+to[1])/2 - 24*unit];
    ctx.strokeStyle = "rgba(228,192,115,0.35)"; ctx.lineWidth = 1;
    ctx.setLineDash([3*unit, 5*unit]); ctx.beginPath(); ctx.moveTo(from[0],from[1]);
    ctx.quadraticCurveTo(control[0],control[1],to[0],to[1]); ctx.stroke(); ctx.setLineDash([]);
    var k = t*t*(3-2*t), back = 1-k;
    var x = back*back*from[0]+2*back*k*control[0]+k*k*to[0], y = back*back*from[1]+2*back*k*control[1]+k*k*to[1];
    ctx.fillStyle = C.gold; ctx.beginPath(); ctx.arc(x,y,3*unit,0,Math.PI*2);ctx.fill();
  }

  // EP stores the same quadratic that draws the dependency, from result to input.
  // Trace it in reverse so the light starts at the corrected reading.
  function drawTimingPath() {
    if (!story || !story.step) { return; }
    var edge = story.timingEdge, curve = EP[edge][0];
    var progress = story.traceStart === null ? 1 : Math.min(1, (clock - story.traceStart) / traceDuration);
    var lit = story.step === 1 ? progress : 1;
    var end = along(edge, 1 - lit);
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(curve[4], curve[5]);
    ctx.quadraticCurveTo(curve[4] + lit * (curve[2] - curve[4]), curve[5] + lit * (curve[3] - curve[5]), end[0], end[1]);
    ctx.strokeStyle = "#f2ad56"; ctx.lineWidth = Math.max(2, 3.2 * unit);
    ctx.shadowColor = "#e58832"; ctx.shadowBlur = 5 * unit; ctx.stroke();
    if (progress < 1) {
      var head = along(edge, 1 - progress);
      ctx.beginPath(); ctx.arc(head[0], head[1], Math.max(3, 4.3 * unit), 0, 2 * Math.PI);
      ctx.fillStyle = "#fff2cd"; ctx.shadowBlur = 9 * unit; ctx.fill();
    }
    ctx.restore();
  }

  function locateStoryLabels() {
    if (!positionLabels || !story) { return; }
    // The guided camera is fixed. Reposition the labels only on entry or resize.
    var gap = Math.max(9, 14 * unit);
    function pin(element, at, dx, dy) {
      element.style.left = (at[0] + dx) + "px";
      element.style.top = (at[1] + dy) + "px";
    }
    pin(swingLabel, swing.s, -box[2] * 0.008, -gap * 1.8);
    pin(gravityLabel, gravity.s, -gap, gap * 0.55);
    instrumentPin = [instruments.s[0] - box[2] * 0.048, instruments.s[1] - box[3] * 0.080];
    pin(instrumentLabel, instrumentPin, 0, -2);
    positionLabels = false;
  }

  function draw() {
    var breath = still || story ? 1 : 0.86 + 0.14 * Math.sin(clock / 1900), yaw = still || story ? -0.05 : -0.05 + 0.11 * Math.sin(clock / 3200);
    var i, k, node, at, r, p, t, colour, glow, halo, age, rec, base, back, eased, near, word;
    cosY = Math.cos(yaw); sinY = Math.sin(yaw); place();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H); ctx.globalAlpha = 1;
    hologram();
    if (rendererReady && W > 0 && H > 0) { figure.classList.add("painted"); }
    locateStoryLabels();

    ctx.globalCompositeOperation = "lighter";
    ctx.beginPath(); for (i = 0; i < E.length; i++) { link(i); } stroke(story ? 0.013 : 0.026, 0.9);
    for (i = 0; i < E.length; i++) {
      rec = N[E[i][0]]; base = N[E[i][1]]; near = hover === E[i][0] || hover === E[i][1] || rec === selected || base === selected;
      if (near || (rec.state === "stale" && (base.changed || base.state === "stale"))) {
        ctx.beginPath(); link(i); ctx.strokeStyle = near ? "rgba(238,243,238,0.6)" : story ? "rgba(242,162,58,0.14)" : "rgba(242,162,58,0.38)"; ctx.lineWidth = 1; ctx.stroke();
      }
    }
    drawTimingPath();
    for (i = pulses.length - 1; i >= 0; i--) {
      p = pulses[i]; t = (clock - p.start) / p.time;
      if (t < 0) { continue; }
      if (t >= 1) { pulses.splice(i, 1); if (p.done) { p.done(); } continue; }
      ctx.globalAlpha = 0.3 * (1 - Math.abs(2 * t - 1)); ctx.beginPath(); link(p.i); ctx.strokeStyle = p.colour; ctx.lineWidth = 1; ctx.stroke();
      for (k = 0; k < 7; k++) {
        back = Math.max(0, t - k * 0.03); eased = back * back * (3 - 2 * back);
        at = along(p.i, p.out ? eased : 1 - eased);
        if (!k) { ctx.globalAlpha = 0.22; ctx.fillStyle = p.colour; ctx.beginPath(); ctx.arc(at[0], at[1], 7 * unit, 0, 6.2832); ctx.fill(); }
        ctx.globalAlpha = (1 - k / 7) * 0.9; ctx.fillStyle = k ? p.colour : "#ffffff";
        ctx.beginPath(); ctx.arc(at[0], at[1], (k ? 1.6 : 2.4) * unit, 0, 6.2832); ctx.fill();
      }
    }
    for (i = 0; i < N.length; i++) {
      node = N[i]; at = node.s; r = size(node);
      if (node.k === "f" && !node.changed) { continue; }
      colour = node.k === "f" ? C.ink : C[node.state];
      glow = r * (node.k === "c" ? 3.6 : 4.4) * (node.changed || node.state === "stale" ? 1.22 : breath);
      halo = ctx.createRadialGradient(at[0], at[1], 0, at[0], at[1], glow);
      halo.addColorStop(0, colour); halo.addColorStop(0.2, colour); halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalAlpha = node.k === "f" ? 0.9 : node.state === "stale" ? 0.5 : 0.42; ctx.fillStyle = halo;
      ctx.beginPath(); ctx.arc(at[0], at[1], glow, 0, 6.2832); ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
    for (i = 0; i < N.length; i++) {
      node = N[i]; at = node.s; r = size(node);
      ctx.fillStyle = node.k === "f" ? (node.changed ? "#ffffff" : C.file) : C[node.state];
      ctx.globalAlpha = (story && node !== gravity && node !== instruments && node !== swing ? 0.34 : 1) * (0.86 + 0.14 * Math.max(-1, Math.min(1, at[2] / T)));
      ctx.beginPath(); ctx.arc(at[0], at[1], i === hover || node === selected ? r + 1.6 : r, 0, 6.2832); ctx.fill();
      if (node === selected) {
        ctx.globalAlpha = 1; ctx.strokeStyle = C.gold; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(at[0], at[1], r + 6 * unit, 0, 6.2832); ctx.stroke();
      }
      if (node.k === "r" || node.k === "p") {
        ctx.globalAlpha = 0.75; ctx.strokeStyle = C[node.state]; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(at[0], at[1], r + 4.5 * unit, 0, 6.2832); ctx.stroke();
      }
    }
    for (i = rings.length - 1; i >= 0; i--) {
      age = (clock - rings[i].start) / 900;
      if (age >= 1) { rings.splice(i, 1); continue; }
      at = N[rings[i].i].s;
      ctx.globalAlpha = (1 - age) * 0.8; ctx.strokeStyle = rings[i].colour; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.arc(at[0], at[1], size(N[rings[i].i]) + (3 + age * 22) * unit, 0, 6.2832); ctx.stroke();
    }
    ctx.globalAlpha = 1; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
    drawActors();
    drawSwing();
    if (story) {
      ctx.beginPath(); ctx.moveTo(instrumentPin[0], instrumentPin[1]);
      ctx.lineTo(instruments.s[0], instruments.s[1] - size(instruments) - 2);
      ctx.strokeStyle = "rgba(157,230,185,0.72)"; ctx.lineWidth = 1; ctx.stroke();
    } else {
      drawRecordNames();
    }
    ctx.textBaseline = "alphabetic";
    ctx.textAlign = "left";
  }

  function drawRecordNames() {
    ctx.font = "600 " + Math.max(9, 12 * unit) + "px ui-sans-serif, system-ui, sans-serif";
    N.forEach(function (rec) {
      var at = rec.s, title = null, x = at[0], y = at[1] - 15 * unit, align = "center";
      if (rec.k === "p") { title = "Evidence page"; x += 6 * unit; align = "right"; }
      else if (rec === swing) { title = "Swing period"; y -= 3 * unit; }
      else if (rec.l === "evals/results/measurement_audit.json") { title = "Gravity audit"; y += 36 * unit; }
      if (title) { label(title, x, y, align, rec.state === "stale" || rec.changed ? C.stale : C.ink); }
    });
  }

  var last = 0;
  function frame(now) {
    raf = 0;
    if (!isOpen() || !shown || document.hidden) { return; }
    // The moving signal benefits from more frames than a settled diagram.
    var age = story ? clock - story.start - chapterStarts[story.step] : Infinity;
    var movingSignal = story && (story.step === 1 || (story.step === 0 && age < 2850) ||
      (story.step === 3 && age < 2300) || (story.traceStart !== null && clock - story.traceStart < traceDuration));
    var frameInterval = 1000 / (movingSignal ? 60 : 30);
    if (last && now - last < frameInterval - 1) {
      raf = window.requestAnimationFrame(frame); return;
    }
    if (!paused) { clock += now - (last || now); }
    last = now;
    if (story) {
      var elapsed = clock - story.start;
      var next = chapterStarts.length - 1;
      while (next > 0 && elapsed < chapterStarts[next]) { next -= 1; }
      updateStory(next, true);
    }
    draw();
    var tracing = story && story.traceStart !== null && clock - story.traceStart < traceDuration;
    if (!paused && (!story || story.step < chapterStarts.length - 1 || tracing)) { raf = window.requestAnimationFrame(frame); }
  }
  function wake() { if (!isOpen()) { return; } last = 0; if (still) { draw(); } else if (!raf) { raf = window.requestAnimationFrame(frame); } }

  function fit() {
    var rect = canvas.getBoundingClientRect(), w = rect.width, h = rect.height, aspect = 1.28;
    if (!w || !h || (W === w && H === h && dpr === Math.min(2, window.devicePixelRatio || 1))) { return; }
    dpr = Math.min(2, window.devicePixelRatio || 1); W = w; H = h;
    // The people and their work share one coordinate system inside the shell.
    // The shell texture has transparent margins above and below its outline.
    var topInset = 0.105, visibleHeight = 0.865;
    w = Math.min(W, h * aspect / visibleHeight); h = w / aspect;
    box = [(W - w) / 2, (H - h * visibleHeight) / 2 - h * topInset, w, h];
    unit = Math.max(0.62, Math.min(2, w / 640));
    positionLabels = true;
    userPoint = project(HUB[0], HUB[1], 0);
    stage.style.setProperty("--shell-width", (box[2] * 0.88) + "px");
    stage.style.setProperty("--shell-top", (box[1] + box[3] * 0.155) + "px");
    stage.style.setProperty("--person-left", (userPoint[0] - (person ? person.offsetWidth : 44) / 2) + "px");
    stage.style.setProperty("--person-top", userPoint[1] + "px");
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    if (BRAIN) { BRAIN.size(box[2] * dpr, box[3] * dpr); }
    wake();
  }
  function nearest(event) {
    var rect = canvas.getBoundingClientRect(), x = event.clientX - rect.left, y = event.clientY - rect.top, best = -1, d = coarse ? 676 : 225;
    N.forEach(function (node, i) { var q = (node.s[0] - x) * (node.s[0] - x) + (node.s[1] - y) * (node.s[1] - y); if (q < d) { d = q; best = i; } });
    return best;
  }
  function describe(node) {
    if (node.k === "f") {
      var affected = reach(node.i).length;
      if (!affected) { return "No result in this example uses this file."; }
      return plural(affected, "result") + (affected === 1 ? " uses" : " use") + " this file.";
    }
    var applies = node.state !== "stale";
    if (node.k === "p") {
      return applies ? "The studies cited on this page still match their saved inputs."
                     : "A study quoted on this page needs checking again.";
    }
    if (!applies) {
      var changed = files.find(function (file) { return file.changed && reach(file.i).indexOf(node.i) >= 0; });
      return (changed ? plain(changed) + " changed." : "An input changed.") +
        (node.k === "r" ? " Rerun this check before using its result." : " Check the evidence again before citing this claim.");
    }
    return node.finding || "The files behind this claim match the version that was checked.";
  }
  function inspectRecord(i) {
    if (!tip) { return; }
    tip.hidden = i < 0 || !!selected;
    if (!tip.hidden) {
      var node = N[i];
      tip.innerHTML = "<b>" + esc(plain(node)) + "</b><span>" + esc(describe(node)) + "</span>";
    }
  }
  canvas.addEventListener("pointermove", function (event) {
    var i = nearest(event);
    if (i === hover) { return; }
    hover = i; canvas.style.cursor = i < 0 ? "default" : "pointer";
    inspectRecord(i);
    if (still || paused || (story && story.step === 4)) { draw(); }
  });
  canvas.addEventListener("pointerleave", function () {
    hover = -1; inspectRecord(-1);
    if (still || paused || (story && story.step === 4)) { draw(); }
  });
  canvas.addEventListener("click", function (event) {
    var i = nearest(event);
    if (i < 0) { return; }
    selectRecord(N[i], true);
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-mind]"), function (button) {
    button.addEventListener("click", function () {
      takeOver();
      comparing = false;
      if (button.getAttribute("data-mind") === "again") { returnToArchitecture(); return; }
      else if (button.getAttribute("data-mind") === "previous") {
        if (story && story.step > 0) { seekStep(story.step - 1); }
      }
      else if (button.hasAttribute("data-case")) {
        if (story && story.step < chapterStarts.length - 1) { seekStep(story.step + 1); }
        else { resetRecord(); beginStory(); }
      }
      else {
        var file = files.find(function (node) { return node.l === button.getAttribute("data-file"); });
        if (file && button.getAttribute("data-mind") === "illustrate") {
          dismissSelection(false);
          if (file.changed) {
            resetRecord(); leaveStory();
            say("The original files are back. Each recorded result can be used again.");
          } else {
            change(file.i, false);
          }
          storyHeadline.textContent = "What changes after one file edit?";
        } else if (file) { selectRecord(file, false); simulateSelectedEdit(); }
      }
      wake();
    });
  });

  if (pauseButton) {
    pauseButton.addEventListener("click", function () {
      if (inlineSelected) { dismissSelection(false); }
      if (comparing) { comparing = false; storyCopy(story.step); rememberStep(story.step); }
      setPause(!paused);
      if (!paused) { wake(); }
    });
  }
  var explorer = document.getElementById("record-picker");
  var disclosure = document.getElementById("record-explorer");
  var card = document.getElementById("policy-example");
  var cardTitle = document.getElementById("policy-example-title");
  var cardKind = document.getElementById("policy-example-kind");
  var cardCopy = document.getElementById("policy-example-copy");
  var cardLinks = document.getElementById("policy-example-links");
  var editButton = document.getElementById("policy-example-edit");
  var dismissButton = document.getElementById("policy-example-dismiss");
  var cardStatus = document.getElementById("policy-example-status");
  var readerNotice = document.getElementById("policy-reader-notice");
  var inline = document.getElementById("policy-inline");
  var inlineTitle = document.getElementById("policy-inline-title"), inlineCopy = document.getElementById("policy-inline-copy");
  var inlineSource = document.getElementById("policy-inline-source"), inlineMore = document.getElementById("policy-inline-more");
  var inlineDismiss = document.getElementById("policy-inline-dismiss");
  var readout = figure.querySelector(".mind-read"), narrative = figure.querySelector(".mind-story");
  var selected = null, inlineSelected = false, recordByKey = new Map();
  var evidenceKinds = {tested: "Example from a test", measured: "Recorded observation",
    documented: "From the project documentation", forecast: "Saved prediction"};

  // Public bookmarks remain the same when titles, counts, and node order change.
  var claimIds = [
    ["A recorded result", "verdict"], ["A passed check", "changed-input"],
    ["The answer names", "changed-file"], ["No route moves", "closure-waiver"],
    ["A result is shared", "shared-result"], ["A change to a file", "unassigned-input"],
    ["A declared domain", "ignored-input"], ["A check marked isolated", "isolated-files"],
    ["An acceptance records", "review"], ["Only a person accepts", "review"], ["A work product", "output-inputs"],
    ["A new or lapsed", "changed-instruction"], ["The instruction that", "earlier-instruction"],
    ["A replacement governs", "temporary-instruction"], ["What governs a task", "startup-instructions"],
    ["A reminder shown", "judged-repeat"], ["A setup is credited", "observed-setup"],
    ["A lapsed lease", "expired-assignment"], ["A refused start", "blocked-start"],
    ["A label is read", "missing-label"], ["A decision-bank run", "saved-answers"],
    ["A change is not confirmed", "fixed-prediction"], ["A number quoted", "measured-source"],
    ["An isolated check sees", "fixed-environment"], ["Each isolated result", "recorded-isolation"],
    ["The setup answers", "declared-folders"], ["No row of this file", "claim-register"],
    ["The demo runs", "demo"], ["Earlier releases had", "release-comparison"],
    ["The tests notice", "removed-safeguards"], ["Reuse by basis", "reuse-counts"],
    ["Age limits trade", "age-limits"], ["In the open", "omitted-input"],
    ["Isolated, a check", "omitted-isolated-input"], ["Asking costs", "file-count-cost"],
    ["Cost of consulting", "file-count-cost"], ["Isolating a check costs", "isolation-cost"],
    ["Added cost of isolating", "isolation-cost"], ["The first-minute reads run locally", "local-session-reads"],
    ["Reading one demo session", "session-reading"], ["The suite passes", "test-matrix"],
    ["Cases collected by the self-test suite", "test-matrix"]
  ];
  var readmeIds = [
    [/^\d+ tests$/, "readme-tests"], [/fail at/, "readme-releases"], [/removals are caught/, "readme-faults"],
    [/executions and/, "readme-reuse"], [/wrong reuses in/, "readme-omitted-input"], [/runs passed/, "readme-isolation"]
  ];
  function recordKey(node) {
    if (node.k !== "c") { return {f: "file:", r: "run:", p: "page:"}[node.k] + node.l; }
    var repeat = "README.md repeats: ";
    var item = node.l.startsWith(repeat) ? readmeIds.find(function (entry) { return entry[0].test(node.l.slice(repeat.length)); }) :
      claimIds.find(function (entry) { return node.l.startsWith(entry[0]); });
    return item ? item[1] : "claim:" + node.l;
  }
  N.forEach(function (node) { recordByKey.set(recordKey(node), node); });

  function rememberSelection(focus) {
    var old = history.state || {}, next = Object.assign({}, old);
    var url = new URL(location.href);
    if (selected) {
      var key = recordKey(selected);
      if (!old.livingRecordSelection) { next.livingRecordOrigin = /^#(?:record=|review$)/.test(url.hash) ? "" : url.hash; }
      url.hash = "record=" + encodeURIComponent(key).replace(/%2F/gi, "/").replace(/%3A/gi, ":");
      next.livingRecordSelection = {key: key, sha256: selected.sha256 || "",
        changed: files.filter(function (file) { return file.changed; }).map(recordKey),
        focus: focus || "", expanded: disclosure.open, inline: inlineSelected,
        placement: inlineSelected && inline.parentElement === narrative ? "above" : "below",
        step: inlineSelected && story ? story.step : null, comparing: inlineSelected && comparing};
    } else if (old.livingRecordSelection || /^#(?:record=|review$)/.test(url.hash)) {
      url.hash = old.livingRecordOrigin || "";
      delete next.livingRecordSelection; delete next.livingRecordOrigin;
    } else { return; }
    try { history.replaceState(next, "", url); } catch (_) { /* Embedded previews may disable history. */ }
  }
  function restoreFocus(saved) {
    if (!selected || recordKey(selected) !== saved.key) { return; }
    if (saved.inline) {
      if (saved.focus === inlineSource.getAttribute("href")) { inlineSource.focus({preventScroll: true}); }
      return;
    }
    if (!saved.expanded) { return; }
    var link = Array.from(cardLinks.querySelectorAll("a")).find(function (item) {
      return item.getAttribute("href") === saved.focus;
    });
    (link || (saved.focus === "picker" ? explorer : cardTitle)).focus({preventScroll: true});
  }
  function dismissSelection(focusPicker) {
    if (!card) { return; }
    selected = null; card.hidden = true; clearInline(); explorer.value = ""; hover = -1;
    readerNotice.textContent = "";
    rememberSelection();
    if (focusPicker) { explorer.focus({preventScroll: true}); wake(); }
  }
  function clearInline() {
    inlineSelected = false;
    if (!inline) { return; }
    inline.hidden = true;
    narrative.classList.remove("policy-inline-host");
    narrative.style.removeProperty("--selection-caption-height");
    if (inline.parentElement !== readout) { readout.prepend(inline); }
  }

  // Most evidence already starts with a complete example. These short accounts
  // keep the outcome when the original paragraph first sets up the situation.
  var shortExamples = {
    "verdict": "A task whose check has never run receives an unknown result and a reason explaining why.",
    "review": "After the timing table changed, the check passed again and the reviewer still had to approve the edited version.",
    "changed-input": "Changing the project’s version number immediately invalidated the earlier passing check.",
    "shared-result": "Two tasks asked for the same check on identical files and the execution counter recorded one run.",
    "ignored-input": "Changing a reading invalidated its check even though Git ignored the data file.",
    "temporary-instruction": "When the one-reviewer exception expired on March 8, releases once again required two reviewers.",
    "judged-repeat": "Three replies already included units, so three reminders produced zero repeated mistakes.",
    "observed-setup": "The session counted once, but no setup received credit because nobody recorded which one ran.",
    "blocked-start": "An agent tried to start a blocked repair and acquired no assignment.",
    "missing-label": "A row with no outcome label contributed zero to the harmless-outcome count.",
    "saved-answers": "A reviewer could recover the original answers behind scores of one and four.",
    "fixed-prediction": "Entering a time saving without a source was refused even when it fell inside the predicted range.",
    "fixed-environment": "A check that needed the caller’s tuning setting passed normally and failed in isolation.",
    "removed-safeguards": "The tests caught a deliberate change that let an approval carry over to an edited version."
  };
  var shortByText = new Map();
  Object.keys(shortExamples).forEach(function (key) {
    var node = recordByKey.get(key);
    if (node && node.evidence) { shortByText.set(node.evidence.text, shortExamples[key]); }
  });
  function showInline(node, placement) {
    var evidence = node.evidence, text = evidence ? evidence.text : describe(node);
    clearInline();
    inlineSelected = true;
    inlineTitle.textContent = plain(node);
    inlineCopy.textContent = shortByText.get(text) || (text.match(/^.*?[.!?](?=\s+[A-Z“]|$)/) || [text])[0];
    var link = evidence && (evidence.links.find(function (item) {
      return evidence.kind === "measured" && item.path.startsWith("evals/results/");
    }) || evidence.links[0]);
    inlineSource.hidden = !link;
    if (link) { inlineSource.href = link.href; inlineSource.textContent = link.label; }
    else { inlineSource.removeAttribute("href"); }
    inline.hidden = false;
    // Read the actual wrapped height before choosing an existing caption area.
    // Neither position overlays the canvas or moves its upper edge.
    var upper = narrative.getBoundingClientRect(), head = document.querySelector(".top");
    var above = placement === "above" || (!placement && inline.getBoundingClientRect().bottom > window.innerHeight - 6 &&
      upper.bottom > (head ? head.getBoundingClientRect().bottom : 0) + inline.offsetHeight);
    if (above) {
      narrative.style.setProperty("--selection-caption-height", upper.height + "px");
      narrative.classList.add("policy-inline-host"); narrative.appendChild(inline);
    }
    rememberSelection("inline");
  }

  function selectRecord(node, fromCanvas, placement) {
    if (!card || !node) { return; }
    takeOver();
    if (!fromCanvas) { leaveStory(); }
    setPause(true);
    selected = node; hover = node.i; explorer.value = recordKey(node);
    inspectRecord(-1);
    if (fromCanvas) {
      card.hidden = true; showInline(node, placement); wake();
      return;
    }
    clearInline();
    var evidence = node.evidence;
    var description = describe(node);
    say(esc(node.k === "f" ? description : node.state === "stale" ? description : "Select another point to explore its record."));
    cardTitle.textContent = plain(node);
    cardKind.textContent = evidence ? evidenceKinds[evidence.kind] : node.k === "f" ? "Source file" : "Record status";
    cardCopy.textContent = evidence ? evidence.text : description;
    cardLinks.replaceChildren();
    if (evidence) {
      evidence.links.forEach(function (sourceLink) {
        var link = document.createElement("a");
        link.href = sourceLink.href; link.textContent = sourceLink.label;
        cardLinks.appendChild(link);
      });
    }
    editButton.hidden = node.k !== "f" || node.changed;
    cardStatus.textContent = node.k === "f" && node.changed ? editConsequence(node) : "";
    disclosure.open = true; card.hidden = false;
    rememberSelection("picker");
    ring(node.i, node.state === "stale" ? C.stale : C.holds); wake();
    readerNotice.textContent = cardKind.textContent + ". " + cardTitle.textContent + ". " + cardCopy.textContent;
  }
  function editConsequence(node) {
    var affected = reach(node.i).length;
    return affected ? "Simulated edit. " + plural(affected, "saved result") +
      (affected === 1 ? " needs" : " need") + " another check." : "Simulated edit. No saved result uses this file.";
  }
  function simulateSelectedEdit() {
    if (!selected || selected.k !== "f" || selected.changed) { return; }
    change(selected.i);
    cardStatus.textContent = editConsequence(selected);
    editButton.hidden = true; dismissButton.focus({preventScroll: true});
    rememberSelection("heading"); wake();
  }
  if (explorer && card) {
    [{ k: "r", title: "Measurements" }, { k: "c", title: "Claims" },
     { k: "p", title: "Page" }, { k: "f", title: "Source files" }].forEach(function (group) {
      var choices = document.createElement("optgroup");
      choices.label = group.title;
      kind(group.k).forEach(function (node) {
        var option = document.createElement("option");
        option.value = recordKey(node);
        option.textContent = plain(node);
        choices.appendChild(option);
      });
      explorer.appendChild(choices);
    });
    explorer.addEventListener("change", function () {
      if (explorer.value) { selectRecord(recordByKey.get(explorer.value), false); }
      else { dismissSelection(false); }
    });
    dismissButton.addEventListener("click", function () { dismissSelection(true); });
    inlineDismiss.addEventListener("click", function () {
      dismissSelection(false);
      canvas.tabIndex = -1; canvas.focus({preventScroll: true}); wake();
    });
    inlineMore.addEventListener("click", function () {
      selectRecord(selected, false);
      cardTitle.focus({preventScroll: true});
      card.scrollIntoView({block: "nearest", behavior: "instant"});
    });
    inlineSource.addEventListener("focus", function () { rememberSelection(inlineSource.getAttribute("href")); });
    inlineSource.addEventListener("click", function () { rememberSelection(inlineSource.getAttribute("href")); });
    editButton.addEventListener("click", simulateSelectedEdit);
    function recordSourceFocus(event) {
      var link = event.target.closest("a");
      if (link) { rememberSelection(link.getAttribute("href")); }
    }
    cardLinks.addEventListener("focusin", recordSourceFocus);
    cardLinks.addEventListener("click", recordSourceFocus);
    disclosure.addEventListener("toggle", function () {
      if (disclosure.open && story) {
        takeOver(); leaveStory(); setPause(true);
        say("Choose a point in the diagram or a record from the list.");
        wake();
      }
      if (selected && history.state && history.state.livingRecordSelection &&
          history.state.livingRecordSelection.expanded !== disclosure.open) {
        rememberSelection(history.state.livingRecordSelection.focus);
      }
    });
  }

  /* The page's own question to the repository, shown as it is answered in the last line of the page. */
  var standing = document.getElementById("standing"), page = N.filter(function (node) { return node.k === "p"; })[0];
  if (standing && page && window.MutationObserver) {
    new MutationObserver(function () {
      if (!isOpen() || story || asked || /not asked yet/.test(standing.textContent) || !/\b(holds|stale|unknown)\b/.test(standing.textContent)) { return; }
      asked = true;
      page.on.forEach(function (edge, k) {
        pulse(edge, true, k * 40, 600, C.gold, function () { pulse(edge, false, 0, 600, C.gold, k ? null : function () { ring(page.i, C.gold); }); });
      });
    }).observe(standing, { childList: true, subtree: true, characterData: true });
  }

  if (window.ResizeObserver) { new ResizeObserver(fit).observe(canvas); } else { window.addEventListener("resize", fit); }
  if (window.IntersectionObserver) {
    new IntersectionObserver(function (seen) { shown = seen[seen.length - 1].isIntersecting; if (shown) { wake(); } }).observe(canvas);
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { wake(); } });
  window.addEventListener("pagehide", function () { if (story) { setPause(true); } });
  figure.classList.add("live");
  function play(savedStep, savedComparison, savedSelection) {
    comparing = !!(comparison && savedComparison && (savedStep === 0 || savedStep === 1));
    if (savedStep !== undefined && savedStep >= chapterStarts.length) { returnToArchitecture(false); return; }
    resetRecord();
    var node = savedSelection && recordByKey.get(savedSelection.key);
    if (node && (!savedSelection.sha256 || savedSelection.sha256 === node.sha256)) {
      if (savedSelection.inline && Number.isInteger(savedSelection.step) &&
          savedSelection.step >= 0 && savedSelection.step < chapterStarts.length) {
        beginStory(); comparing = !!savedSelection.comparing; seekStep(savedSelection.step);
      }
      (savedSelection.changed || []).forEach(function (key) {
        var file = recordByKey.get(key);
        if (file && file.k === "f" && !file.changed) { change(file.i, true); }
      });
      selectRecord(node, !!savedSelection.inline, savedSelection.placement);
      disclosure.open = !!savedSelection.expanded;
      rememberSelection(savedSelection.focus);
      window.requestAnimationFrame(function () {
        restoreFocus(savedSelection);
        if (savedSelection.direct) { card.scrollIntoView({block: "center", behavior: "instant"}); }
      });
    } else if (savedSelection) { returnToArchitecture(false); return; }
    else { beginStory(); }
    if (story && Number.isInteger(savedStep) && savedStep >= 0 && savedStep < chapterStarts.length) {
      setPause(true);
      seekStep(savedStep);
    }
    fit();
    wake();
    if (!rendererReady) {
      window.requestAnimationFrame(function () {
        if (!isOpen() || rendererReady) { return; }
        BRAIN = createBrain();
        if (BRAIN) { BRAIN.size(box[2] * dpr, box[3] * dpr); }
        rendererReady = true; wake();
      });
    }
  }
  function stop() {
    dismissSelection(false);
    if (disclosure) { disclosure.open = false; }
    comparing = false;
    rememberStep(undefined);
    window.cancelAnimationFrame(raf); raf = 0; last = 0; clock = 0;
    resetRecord();
  }
  return {play: play, stop: stop, restoreFocus: restoreFocus};
}));
