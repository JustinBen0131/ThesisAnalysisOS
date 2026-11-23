(function () {
  "use strict";

  for (const game of document.querySelectorAll("[data-first-game]")) {
    const reading = game.querySelector("[data-game-reading]");
    const content = game.querySelector("[data-game-content]");
    const stage = game.querySelector("[data-game-stage]");
    const live = game.querySelector("[data-game-live]");
    const views = new Map(Array.from(game.querySelectorAll("[data-game-view]"),
      (template) => [template.dataset.gameView, template]));

    function show(view, moveFocus = true) {
      stage.replaceChildren(views.get(view).content.cloneNode(true));
      live.textContent = "";
      if (moveFocus) stage.querySelector("h2").focus();
    }

    function name(input) {
      return input.closest("label").querySelector(".first-game__plan-title").textContent;
    }

    stage.addEventListener("click", (event) => {
      const reveal = event.target.closest("[data-reveal-choice]");
      if (!reveal) return;
      const choices = reveal.closest("[data-choice]");
      const inputs = Array.from(choices.querySelectorAll("input"));
      const missed = inputs.filter((input) => input.dataset.verdict === "stale" && !input.checked);
      const extra = inputs.filter((input) => input.dataset.verdict === "holds" && input.checked);
      const unknown = inputs.find((input) => input.dataset.verdict === "unknown" && input.checked);
      const comments = [];
      if (missed.length) comments.push("Also check " + missed.map(name).join(" and ").toLowerCase() + ".");
      if (extra.length) comments.push("Leave " + extra.map(name).join(" and ").toLowerCase() + " as is.");
      if (unknown) comments.push("Check the growth figure separately. Its source is unknown.");
      const feedback = comments.length ? comments.join(" ") : choices.dataset.correct;
      show(choices.dataset.reveal, false);
      stage.querySelector("[data-game-feedback]").textContent = feedback;
      stage.querySelector("h2").focus();
    });

    function updateScale(action) {
      const field = stage.querySelector("[data-field]");
      const label = stage.querySelector("[data-scale-label]");
      const grow = stage.querySelector('[data-action="grow"]');
      const correct = stage.querySelector('[data-action="correct"]');
      const results = field.children.length;
      if (action === "grow") {
        field.dataset.phase = "grown";
        label.textContent = results + " results";
        live.textContent = results + " results are on record.";
        correct.hidden = false;
        correct.focus();
        grow.hidden = true;
        return;
      }
      field.dataset.phase = "corrected";
      const stale = field.querySelectorAll(".first-game__dot--affected").length;
      label.textContent = stale + " stale · " + (results - stale) + " hold";
      live.textContent = "";
      stage.querySelector("[data-scale-lesson]").hidden = false;
      stage.querySelector("[data-game-end]").hidden = false;
      label.tabIndex = -1;
      label.focus();
      correct.hidden = true;
    }

    stage.addEventListener("click", (event) => {
      const action = event.target.closest("button[data-action]")?.dataset.action;
      if (views.has(action)) show(action);
      if (action === "grow" || action === "correct") updateScale(action);
    });

    function prepare() {
      if (game.open && content.hidden) {
        show("flight", false);
        reading.hidden = true;
        content.hidden = false;
      }
    }
    game.addEventListener("toggle", prepare);
    prepare();
  }
}());
