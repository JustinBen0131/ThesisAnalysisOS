// Native disclosures keep every decision and source readable without JavaScript.
document.querySelectorAll(".review-workshop").forEach((workshop) => {
  const cases = Array.from(workshop.querySelectorAll(".review-case"));
  const depth = workshop.querySelector(".review-depth");
  const proofs = Array.from(workshop.querySelectorAll(".review-proof"));
  depth.hidden = false;
  depth.addEventListener("click", () => {
    const show = depth.getAttribute("aria-pressed") !== "true";
    depth.setAttribute("aria-pressed", String(show));
    proofs.forEach(proof => { proof.open = show; });
  });
  const openCase = (item) => {
    item.open = true;
    const heading = item.querySelector("summary");
    heading.focus();
    heading.scrollIntoView({block: "start"});
  };

  workshop.querySelector(".review-start").addEventListener("click", (event) => {
    event.preventDefault();
    openCase(cases[0]);
  });

  cases.forEach((item, index) => {
    const choices = Array.from(item.querySelectorAll(".review-choice"));
    const next = document.createElement("button");
    next.type = "button";
    next.className = "review-next";
    next.textContent = index + 1 === cases.length ? "Get the review prompt" : "Next decision";
    next.hidden = true;
    item.querySelector(".review-body").append(next);
    choices.forEach((choice) => {
      choice.addEventListener("toggle", () => {
        if (!choice.open) return;
        choices.forEach((other) => { if (other !== choice) other.open = false; });
        next.hidden = false;
      });
    });
    next.addEventListener("click", () => {
      item.open = false;
      if (index + 1 < cases.length) {
        openCase(cases[index + 1]);
      } else {
        const heading = workshop.querySelector(".review-takeaway h2");
        heading.tabIndex = -1;
        heading.focus();
        heading.scrollIntoView({block: "start"});
      }
    });
  });
});
