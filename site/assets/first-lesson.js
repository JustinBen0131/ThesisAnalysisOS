(() => {
  const bench = document.querySelector("#first-lesson .lesson-bench");
  if (!bench) return;
  const steps = new Map(Array.from(bench.querySelectorAll("[data-step]"), row => [row.dataset.step, row]));
  const buttons = bench.querySelector(".lesson-actions");
  const log = bench.querySelector(".lesson-log");

  function show(key) {
    const row = steps.get(key);
    bench.dataset.phase = key;
    if (key === "baseline") bench.dataset.restyled = "false";
    if (key === "style-only") bench.dataset.restyled = "true";
    bench.querySelector('[data-display="value"]').textContent = row.dataset.value;
    bench.querySelector('[data-display="state"]').textContent = row.dataset.state;
    bench.querySelector('[data-display="reason"]').textContent = row.querySelector("p").textContent;
    const item = document.createElement("li");
    item.textContent = row.querySelector("code").textContent;
    log.append(item);
    for (const button of buttons.querySelectorAll("button")) {
      const pick = button.dataset.pick;
      button.hidden = !(
        (pick === "style-only" && key === "baseline") ||
        (pick === "timing-edited" && ["baseline", "style-only"].includes(key)) ||
        (pick === "rerun" && key === "timing-edited") ||
        (pick === "reset" && key !== "baseline")
      );
    }
  }
  buttons.addEventListener("click", event => {
    const button = event.target.closest("button[data-pick]");
    if (!button || button.hidden) return;
    if (button.dataset.pick === "reset") {
      log.replaceChildren();
      show("baseline");
    } else {
      show(button.dataset.pick);
    }
    buttons.querySelector("button:not([hidden])").focus();
  });
  show("baseline");
  log.hidden = false;
  buttons.hidden = false;
})();
