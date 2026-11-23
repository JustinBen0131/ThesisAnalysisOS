/* Enhance the complete static example with one decision at a time. */
(() => {
  const board = document.querySelector("[data-hpc-board]");
  if (!board) return;

  const frames = Array.from(board.querySelectorAll("[data-stage]"));
  const byStage = new Map(frames.map(frame => [frame.dataset.stage, frame]));
  const inspection = board.querySelector("[data-feedback-line]");
  const probes = Array.from(board.querySelectorAll("[data-inspect]"));
  const invitation = inspection?.textContent;
  for (const probe of probes) probe.hidden = false;
  if (inspection) inspection.hidden = false;

  const reviewButton = board.querySelector('[data-stage="returned"] [data-go="checked"]');
  const defaultReviewLabel = reviewButton?.textContent;
  function show(frame, moveFocus) {
    if (frame.dataset.stage === "plan" && inspection) {
      inspection.textContent = invitation;
      for (const probe of probes) {
        probe.setAttribute("aria-pressed", "false");
        delete probe.closest("th").dataset.finding;
      }
      if (reviewButton) reviewButton.textContent = defaultReviewLabel;
      for (const log of board.querySelectorAll("details[open]")) log.open = false;
    }
    for (const item of frames) item.hidden = item !== frame;
    if (moveFocus) {
      try { history.replaceState({...history.state, hpcPilotStage: frame.dataset.stage}, ""); }
      catch (_) { /* The exhibit also runs in previews with restricted history. */ }
      frame.querySelector("h3").focus({preventScroll: true});
      board.scrollIntoView({block: "start", behavior: "instant"});
    }
  }

  board.addEventListener("click", event => {
    const selected = event.target.closest("button[data-inspect]");
    if (selected && inspection) {
      for (const probe of probes) probe.setAttribute("aria-pressed", String(probe === selected));
      selected.closest("th").dataset.finding = selected.dataset.match === "true" ? "match" : "discrepancy";
      if (selected.dataset.match === "false" && reviewButton) reviewButton.textContent = "Open C’s transfer report";
      inspection.textContent = selected.dataset.feedback;
      return;
    }
    const button = event.target.closest("button[data-go]");
    if (!button || !board.contains(button)) return;
    const next = byStage.get(button.dataset.go);
    if (next) show(next, true);
  });

  for (const actions of board.querySelectorAll(".hpc-actions")) actions.hidden = false;
  board.dataset.enhanced = "";
  show(byStage.get(history.state?.hpcPilotStage) || byStage.get("plan"), false);
})();
