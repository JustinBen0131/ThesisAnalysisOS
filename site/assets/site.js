/* Two small things. Without this file the page still says everything: every step is shown, one under the other. */
(function () {
  "use strict";
  var archivedRecord = document.querySelector("[data-record-archive]");
  if (archivedRecord) {
    function followRecordBookmark() {
      if (location.hash === "#review" || location.hash.startsWith("#record=")) {
        location.replace(archivedRecord.href + location.hash);
      }
    }
    followRecordBookmark();
    window.addEventListener("hashchange", followRecordBookmark);
  }
  document.querySelectorAll(".command-block").forEach(function (block) {
    var button = block.querySelector(".copy-commands");
    var code = block.querySelector("code");
    var status = block.querySelector(".copy-status"), timeout;
    if (!button || !code || !status) { return; }
    button.hidden = false;
    button.addEventListener("click", async function () {
      window.clearTimeout(timeout);
      var copied = false;
      try {
        await navigator.clipboard.writeText(code.textContent);
        copied = true;
      } catch (_) {
        var selection = window.getSelection();
        selection.selectAllChildren(code);
        try { copied = document.execCommand("copy"); } catch (_) {}
        if (copied) { selection.removeAllRanges(); }
      }
      button.classList.toggle("copied", copied);
      status.textContent = copied ? "Copied" : "Selected — press Ctrl+C or ⌘C";
      timeout = window.setTimeout(function () {
        button.classList.remove("copied");
        status.textContent = "";
      }, copied ? 1700 : 5000);
    });
  });
}());

(function () {
  "use strict";

  // 1. The run, one moment at a time.
  var stepper = document.querySelector(".stepper");
  var steps = stepper ? Array.prototype.slice.call(stepper.querySelectorAll(".step")) : [];
  if (steps.length) {
    var current = 0, timer = 0, play = document.querySelector("[data-play]");
    var nav = document.createElement("ol");
    nav.className = "stepnav";
    nav.setAttribute("aria-label", "Moments of the run");
    var buttons = steps.map(function (step, index) {
      step.tabIndex = -1;
      step.setAttribute("aria-label", step.querySelector(".tell h3").textContent);
      var item = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      var numeral = document.createElement("span");
      numeral.textContent = String(index + 1);
      button.append(numeral, step.getAttribute("data-short"));
      button.setAttribute("aria-controls", step.id);
      button.addEventListener("click", function () { choose(index); });
      item.appendChild(button);
      nav.appendChild(item);
      var walk = document.createElement("p");
      walk.className = "walk";
      walk.innerHTML = '<button type="button" class="prev">Previous</button><button type="button" class="next">Next</button>';
      walk.querySelector(".prev").disabled = index === 0;
      walk.querySelector(".next").disabled = index === steps.length - 1;
      walk.querySelector(".prev").addEventListener("click", function () { choose(index - 1, true); });
      walk.querySelector(".next").addEventListener("click", function () { choose(index + 1, true); });
      step.querySelector(".tell").appendChild(walk);
      return button;
    });
    stepper.insertBefore(nav, steps[0]);
    stepper.className += " live";
    function show(index, record) {
      current = Math.max(0, Math.min(steps.length - 1, index));
      steps.forEach(function (step, at) { step.hidden = at !== current; });
      buttons.forEach(function (button, at) {
        if (at === current) { button.setAttribute("aria-current", "step"); } else { button.removeAttribute("aria-current"); }
      });
      var hash = "#" + steps[current].id;
      if (record && history.replaceState && location.hash !== hash) {
        try { history.replaceState(history.state, "", hash); } catch (_) { /* Keep the panel usable when history updates are restricted. */ }
      }
    }
    function playbackLabel() {
      if (!play) { return; }
      var label = "▶ Play the steps";
      if (timer) { label = "❚❚ Pause"; }
      else if (current === steps.length - 1) { label = "↻ Replay the steps"; }
      else if (current > 0) { label = "▶ Continue"; }
      play.textContent = label;
      play.setAttribute("aria-pressed", String(Boolean(timer)));
    }
    function pause() {
      window.clearTimeout(timer);
      timer = 0;
      playbackLabel();
    }
    function choose(index, fromPanel) {
      show(index, true);
      pause();
      if (fromPanel) {
        // The tapped button has just disappeared with its panel.
        var step = steps[current];
        step.focus({preventScroll: true});
        step.scrollIntoView({block: "start", behavior: "instant"});
      }
    }
    function playStep() {
      if (current === steps.length - 1) { pause(); return; }
      var scene = steps[current];
      var reading = Array.from(scene.querySelectorAll(".step-story, dt, dd"), function (item) {
        return item.textContent;
      }).join(" ");
      var milliseconds = Math.min(15500, Math.max(6500, 1200 + 300 * reading.trim().split(/\s+/).length));
      timer = window.setTimeout(function () { show(current + 1, true); playStep(); }, milliseconds);
      playbackLabel();
    }
    function followFragment(onLoad) {
      var index = steps.findIndex(function (step) { return "#" + step.id === location.hash; });
      if (index >= 0) {
        var target = steps[index];
        for (var drawer = target.closest("details"); drawer; drawer = drawer.parentElement.closest("details")) {
          drawer.open = true;
        }
      }
      if (index >= 0 || onLoad) { show(index >= 0 ? index : 0, false); }
      pause();
      if (!onLoad && index >= 0) {
        steps[current].focus({preventScroll: true});
        steps[current].scrollIntoView({block: "start", behavior: "instant"});
      }
    }
    steps.forEach(function (step) {
      step.querySelectorAll("details").forEach(function (detail) {
        detail.addEventListener("toggle", function () { if (detail.open) { pause(); } });
      });
    });
    nav.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") { return; }
      choose(current + (event.key === "ArrowRight" ? 1 : -1));
      buttons[current].focus();
      event.preventDefault();
    });
    followFragment(true);
    window.addEventListener("hashchange", function () { followFragment(false); });
    window.addEventListener("pagehide", pause);
    document.addEventListener("visibilitychange", function () { if (document.hidden) { pause(); } });
    if (play) {
      play.hidden = false;
      play.addEventListener("click", function () {
        if (timer) { pause(); return; }
        if (current === steps.length - 1) { show(0, true); }
        playStep();
      });
      Array.prototype.forEach.call(document.querySelectorAll("[data-watch]"), function (link) {
        link.addEventListener("click", function () {
          if (!timer) { window.setTimeout(function () { if (!timer) { show(0, true); playStep(); } }, 700); }
        });
      });
    }
  }

  // 2. The page asks the repository whether the files it was built from are still the same.
  var line = document.getElementById("standing");
  if (!line || !window.fetch) { return; }
  var note = line.querySelector(".nojs");
  if (note) { note.parentNode.removeChild(note); }
  var answer = function (state, reason, paths) {
    var chip = line.querySelector(".chip");
    chip.className = "chip " + state;
    chip.lastChild.nodeValue = state;
    var said = document.createElement("span");
    said.textContent = " " + reason + " ";
    chip.parentNode.insertBefore(said, chip.nextSibling);
    if (paths && paths.length) {
      var details = document.createElement("details");
      var label = document.createElement("summary");
      label.textContent = "Inspect the differing files";
      var list = document.createElement("ul");
      paths.forEach(function (path) {
        var item = document.createElement("li");
        item.textContent = path;
        list.appendChild(item);
      });
      details.appendChild(label);
      details.appendChild(list);
      line.insertAdjacentElement("afterend", details);
    }
  };
  fetch(line.getAttribute("data-src")).then(function (reply) { return reply.json(); }).then(function (built) {
    var ask = "https://api.github.com/repos/" + built.repository + "/git/trees/" + built.branch + "?recursive=1";
    return fetch(ask, { headers: { Accept: "application/vnd.github+json" } }).then(function (reply) {
      if (!reply.ok) { throw new Error("it answered " + reply.status); }
      return reply.json();
    }).then(function (tree) {
      if (tree.truncated) { throw new Error("its file list was cut short"); }
      var now = {};
      tree.tree.forEach(function (entry) { now[entry.path] = entry.sha; });
      var moved = built.stands_on.filter(function (file) { return now[file.path] !== file.blob; })
        .map(function (file) { return file.path; });
      if (moved.length) {
        answer("stale", moved.length + " source files differ between this build and GitHub’s public main branch.", moved);
      } else {
        answer("holds", "All " + built.stands_on.length + " source files match public main.");
      }
    });
  }).catch(function (problem) {
    answer("unknown", "GitHub comparison unavailable (" + problem.message + ").");
  });
}());
