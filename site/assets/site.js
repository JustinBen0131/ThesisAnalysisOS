/* Two small things. Without this file the page still says everything: every step is shown, one under the other. */
(function () {
  "use strict";

  // 1. The run, one moment at a time.
  var stepper = document.querySelector(".stepper");
  var steps = stepper ? Array.prototype.slice.call(stepper.querySelectorAll(".step")) : [];
  if (steps.length) {
    var nav = document.createElement("ol");
    nav.className = "stepnav";
    nav.setAttribute("aria-label", "Moments of the run");
    var buttons = steps.map(function (step, index) {
      var item = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.innerHTML = "<span>" + (index + 1) + "</span>" + step.getAttribute("data-short");
      button.addEventListener("click", function () { show(index, true); });
      item.appendChild(button);
      nav.appendChild(item);
      var walk = document.createElement("p");
      walk.className = "walk";
      walk.innerHTML = '<button type="button" class="prev">Previous</button><button type="button" class="next">Next</button>';
      walk.querySelector(".prev").disabled = index === 0;
      walk.querySelector(".next").disabled = index === steps.length - 1;
      walk.querySelector(".prev").addEventListener("click", function () { show(index - 1, true); });
      walk.querySelector(".next").addEventListener("click", function () { show(index + 1, true); });
      step.querySelector(".tell").appendChild(walk);
      return button;
    });
    stepper.insertBefore(nav, steps[0]);
    stepper.className += " live";
    var current = 0;
    var show = function (index, record) {
      current = Math.max(0, Math.min(steps.length - 1, index));
      steps.forEach(function (step, at) { step.hidden = at !== current; });
      buttons.forEach(function (button, at) {
        if (at === current) { button.setAttribute("aria-current", "step"); } else { button.removeAttribute("aria-current"); }
      });
      if (record && window.history && history.replaceState) { history.replaceState(null, "", "#run-" + (current + 1)); }
    };
    nav.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") { return; }
      show(current + (event.key === "ArrowRight" ? 1 : -1), true);
      buttons[current].focus();
      event.preventDefault();
    });
    var asked = /^#run-(\d+)$/.exec(window.location.hash || "");
    show(asked ? Number(asked[1]) - 1 : 0, false);
  }

  // 2. The page asks the repository whether the files it was built from are still the same.
  var line = document.getElementById("standing");
  if (!line || !window.fetch) { return; }
  var note = line.querySelector(".nojs");
  if (note) { note.parentNode.removeChild(note); }
  var answer = function (state, reason) {
    var chip = line.querySelector(".chip");
    chip.className = "chip " + state;
    chip.lastChild.nodeValue = state;
    var said = document.createElement("span");
    said.textContent = " " + reason + " ";
    chip.parentNode.insertBefore(said, chip.nextSibling);
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
        answer("stale", "Asked just now: the repository has changed " + moved.join(", ") + " since this page was built. It");
      } else {
        answer("holds", "Asked just now: the " + built.stands_on.length + " files it stands on are the same in the repository. It");
      }
    });
  }).catch(function (problem) {
    answer("unknown", "The repository could not be asked (" + problem.message + "), so this is not rounded to anything. It");
  });
}());
