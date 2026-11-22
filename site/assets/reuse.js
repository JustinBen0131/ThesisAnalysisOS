/* The reuse experiment as something to play with. The rule is the experiment's own:
   a check runs again when a folder on its list changed; a result is outdated when a folder
   it reads changed after it last ran. No network, no storage. */
(function () {
  "use strict";

  function start(checks) {
    var ranAt = [], touchedAt = [], k;
    for (k = 0; k < checks; k += 1) { ranAt.push(-1); touchedAt.push(-1); }
    return { ranAt: ranAt, touchedAt: touchedAt, step: -1, edits: 0, runs: 0, outdated: 0 };
  }

  function change(state, folder, reads, hide) {
    var check = Math.floor(folder / reads), listed = !hide || folder % reads !== reads - 1, k;
    state.step += 1;
    state.edits += 1;
    state.touchedAt[check] = state.step;
    if (listed) { state.ranAt[check] = state.step; state.runs += 1; }
    for (k = 0; k < state.ranAt.length; k += 1) {
      if (state.ranAt[k] < state.touchedAt[k]) { state.outdated += 1; }
    }
    return { folder: folder, check: check, ran: listed };
  }

  if (typeof module !== "undefined" && module.exports) { module.exports = { start: start, change: change }; }
  if (typeof document === "undefined") { return; }

  Array.prototype.forEach.call(document.querySelectorAll(".reuse-play"), function (root) {
    var trace = JSON.parse(root.getAttribute("data-trace"));
    var checks = Number(root.getAttribute("data-checks")), reads = Number(root.getAttribute("data-reads"));
    var units = Array.prototype.slice.call(root.querySelectorAll(".reuse-unit"));
    var tiles = Array.prototype.slice.call(root.querySelectorAll(".reuse-folder"));
    var wires = Array.prototype.slice.call(root.querySelectorAll(".reuse-wires path[data-folder]"));
    var sparks = Array.prototype.slice.call(root.querySelectorAll(".reuse-wires path.spark"));
    var say = root.querySelector(".reuse-say"), bad = root.querySelector(".reuse-tally .bad");
    var skipped = root.querySelector(".reuse-tally .saved");
    var replayButton = root.querySelector('[data-act="replay"]'), replayLabel = replayButton.textContent;
    var hideBox = root.querySelector('[data-act="hide"]');
    var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var state = start(checks), hide = false, timer = null;

    function unlisted(folder) { return hide && folder % reads === reads - 1; }

    function paint(result) {
      var values = { runs: state.runs, saved: state.edits * checks - state.runs, outdated: state.outdated };
      Object.keys(values).forEach(function (key) {
        root.querySelector('[data-tally="' + key + '"]').textContent = values[key];
      });
      bad.hidden = !hide;
      skipped.hidden = hide;
      bad.classList.toggle("on", state.outdated > 0);
      units.forEach(function (unit, k) {
        var outdated = state.ranAt[k] < state.touchedAt[k], ran = Boolean(result) && result.ran && result.check === k;
        unit.classList.toggle("ran", ran);
        unit.classList.toggle("outdated", outdated);
        unit.querySelector(".reuse-state").textContent = outdated ? "outdated" : ran ? "ran again" : "kept";
      });
      tiles.forEach(function (tile, folder) {
        tile.classList.toggle("changed", Boolean(result) && result.folder === folder);
        tile.classList.toggle("unlisted", unlisted(folder));
      });
      wires.forEach(function (wire) {
        var folder = Number(wire.getAttribute("data-folder"));
        wire.classList.toggle("off", unlisted(folder));
        wire.classList.toggle("lit", Boolean(result) && result.ran && result.folder === folder);
      });
    }

    function pulse(folder) {
      var wire = root.querySelector('.reuse-wires path[data-spark="' + folder + '"]');
      if (calm || !wire) { return; }
      wire.classList.remove("go");
      wire.getBoundingClientRect();
      wire.classList.add("go");
    }

    sparks.forEach(function (wire) {
      wire.addEventListener("animationend", function () { wire.classList.remove("go"); });
    });

    function sentence(result) {
      if (result.ran) {
        var outdated = state.ranAt.filter(function (ran, check) { return ran < state.touchedAt[check]; }).length;
        var summary = outdated === 1 ? " One other result is still outdated."
          : outdated ? " " + outdated + " other results are still outdated." : "";
        return "Folder " + (result.folder + 1) + " changed. Check " + (result.check + 1) + " ran again." + summary;
      }
      return "Folder " + (result.folder + 1) + " changed, but check " + (result.check + 1) +
        " left it off its list. Its old result is still in use.";
    }

    function apply(folder, animate) {
      var result = change(state, folder, reads, hide);
      paint(result);
      if (animate && result.ran) { pulse(folder); }
      return result;
    }

    function stop() {
      var running = timer !== null;
      if (running) { window.clearInterval(timer); timer = null; }
      replayButton.textContent = replayLabel;
      return running;
    }

    function reset(message) {
      stop();
      state = start(checks);
      paint(null);
      say.textContent = message;
    }

    function finished() {
      say.textContent = hide
        ? "All " + trace.length + " recorded changes replayed. Only " + state.runs + " checks ran, and an outdated result was used " + state.outdated + " times."
        : "All " + trace.length + " recorded changes replayed. " + state.runs + " checks ran, " + (state.edits * checks - state.runs) +
          " runs were skipped, and no outdated result was used.";
    }

    function replay() {
      var next = 0;
      if (stop()) { say.textContent = "Replay stopped after " + state.edits + " changes."; return; }
      reset("Replaying " + trace.length + " recorded changes.");
      if (calm) { trace.forEach(function (folder) { change(state, folder, reads, hide); }); paint(null); finished(); return; }
      replayButton.textContent = "Stop replay";
      timer = window.setInterval(function () {
        apply(trace[next], true);
        next += 1;
        if (next >= trace.length) { stop(); finished(); }
      }, 110);
    }

    tiles.forEach(function (tile, folder) {
      tile.disabled = false;
      tile.addEventListener("click", function () {
        var interrupted = stop();
        var result = apply(folder, true);
        say.textContent = (interrupted ? "Replay stopped. " : "") + sentence(result);
      });
    });
    replayButton.addEventListener("click", replay);
    root.querySelector('[data-act="reset"]').addEventListener("click", function () {
      reset("Pick a folder to change a file in it.");
    });
    hideBox.addEventListener("change", function () {
      hide = hideBox.checked;
      tiles.forEach(function (tile, folder) {
        tile.setAttribute("aria-label", "Change a file in folder " + (folder + 1) +
          (unlisted(folder) ? " (left off the list)" : ""));
      });
      reset(hide ? "Dashed folders are off the lists. Try one."
                 : "Both folders are listed again.");
    });
    root.querySelector(".reuse-ctl").hidden = false;
    root.querySelector(".reuse-invite").hidden = false;
    apply(trace[0], false);
  });
}());
