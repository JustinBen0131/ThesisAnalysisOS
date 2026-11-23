/* The visitor chooses when to advance. The same exercise also opens directly at /decision/. */
(() => {
  "use strict";
  const story = document.querySelector(".visitor-story");
  if (!story) return;
  const byId = id => document.getElementById(id);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const root = document.documentElement;
  const scrollStory = byId("see");
  const scenes = [5, 3, 4, 4, 5, 5];
  let scene = 0;
  let beatNumber = 1;
  let section = scrollStory ? "top" : "try";

  function setMood() {
    const mood = section === "see" ? beatNumber : section === "try" ? scenes[scene] : 5;
    if (root.dataset.mood !== String(mood)) root.dataset.mood = String(mood);
  }

  if (scrollStory) {
    const beats = Array.from(scrollStory.querySelectorAll(".beat"));
    const tiles = [];
    const pile = byId("pile");
    const panels = ["top", "see", "watch", "try", "run"];
    const links = Array.from(document.querySelectorAll(".rail a[href^='#']"));
    const words = [
      ["finished ✓", "", "", "nothing yet", "Scroll. One of these is about to change."],
      ["finished ✓", "", "", "nothing yet", "Keep scrolling. Does anyone notice?"],
      ["finished ✓", "every agent reads: finished", "up", "one agent, then another, then ten", "Keep scrolling. Someone finds out."],
      ["in doubt", "found late, by a person", "bad", "all of it, in doubt", "One more. What should have happened."],
      ["stale", "changed: a setting", "", "nothing more is built on it unnoticed", ""]
    ];
    for (let i = 0; i < 10; i++) {
      const tile = document.createElement("i");
      tile.style.transitionDelay = reduced.matches ? "0s" : (i * 70) + "ms";
      pile.append(tile);
      tiles.push(tile);
    }
    let last = -1;
    let frame = 0;
    function update() {
      frame = 0;
      const middle = window.innerHeight * 0.5;
      const onScreen = panels.map(byId).find(panel => {
        const r = panel.getBoundingClientRect();
        return r.top <= middle && r.bottom > middle;
      });
      section = onScreen ? onScreen.id : "";
      const line = matchMedia("(max-width:820px)").matches ? window.innerHeight * .72 : middle;
      let current = 0;
      beats.forEach((beat, index) => { if (beat.getBoundingClientRect().top <= line) current = index; });
      beatNumber = current + 1;
      if (current !== last) {
        last = current;
        const [word, reason, status, count, hint] = words[current];
        byId("obj").dataset.b = String(beatNumber);
        byId("word").textContent = word;
        byId("why").textContent = reason || "\u00a0";
        byId("pilelabel").textContent = count;
        byId("hint").textContent = hint ? hint + " ↓" : "";
        byId("setting").textContent = current ? "a setting · changed" : "a setting";
        byId("setting").classList.toggle("chg", current > 0);
        tiles.forEach(tile => { tile.className = status; });
        beats.forEach((beat, index) => beat.classList.toggle("on", current === index));
      }
      links.forEach(link => {
        if (link.hash === "#" + section) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      });
      const length = root.scrollHeight - window.innerHeight;
      byId("prog").style.transform = "scaleX(" + (length > 0 ? Math.min(1, window.scrollY / length) : 0) + ")";
      setMood();
    }
    function queue() { if (!frame) frame = requestAnimationFrame(update); }
    scrollStory.dataset.live = "true";
    window.addEventListener("scroll", queue, {passive: true});
    window.addEventListener("resize", queue);
    window.addEventListener("pageshow", queue);
    update();
  }

  const startingView = byId("try").cloneNode(true);
  let changeTimer;
  let instant = false;
  let choice = null;
  function mountDecision(target = 0) {
    const stage = byId("stage");
    const track = byId("track");
    const buildButton = byId("build");
    const checkButton = byId("check");
    const nextButton = byId("next");
    let builtOnIt = false;
    let stop = 0;
    let busy = false;
    const backButton = byId("back");
    const forwardButton = byId("fwd");
    scene = 0;
    story.dataset.mode = "then";
    story.dataset.sw = "none";
    story.dataset.ref = "0";
    story.dataset.decisionStop = "0";
    setMood();
    stage.dataset.live = "true";
    for (let day = 0; day < 19; day++) {
      const tile = document.createElement("i");
      tile.className = "built";
      track.append(tile);
    }
    if (!reduced.matches && "IntersectionObserver" in window) {
      const reveal = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) {
          stage.classList.add("play");
          reveal.disconnect();
        }
      }, {threshold: 0.12});
      reveal.observe(stage);
      stage.addEventListener("focusin", () => stage.classList.add("play"), {once: true});
    } else stage.classList.add("play");

    function at(value) { scene = value; setMood(); }
    function caption(text) {
      const line = byId("caption");
      line.hidden = false;
      line.textContent = text;
    }
    function heading(first, second) {
      const heading = byId("tryh");
      heading.replaceChildren(first, document.createElement("br"), second);
    }
    function advance(label, action) {
      nextButton.hidden = false;
      nextButton.textContent = label;
      nextButton.onclick = () => {
        nextButton.hidden = true;
        action();
        if (nextButton.hidden && document.activeElement === document.body && scene !== 5) {
          (scene === 4 ? checkButton : byId("caption")).focus({preventScroll:true});
        }
      };
    }
    // One timer at a time. With reduced motion the same information arrives at once.
    function later(ms, action) {
      if (instant) { action(); return; }
      changeTimer = window.setTimeout(action, reduced.matches ? 0 : ms);
    }
    // Back and Forward. A stop is a place where the story waits for the visitor.
    function steps() {
      backButton.disabled = stop === 0 && !busy;
      forwardButton.disabled = stop === 4 || (stop === 0 && !busy && choice === null);
    }
    function leave() { busy = true; steps(); }
    function settle(value) {
      stop = value;
      busy = false;
      story.dataset.decisionStop = String(value);
      steps();
    }
    function jump(value, from) {
      clearTimeout(changeTimer);
      byId("try").replaceWith(startingView.cloneNode(true));
      mountDecision(value);
      const again = byId(from);
      (again.disabled ? byId(from === "back" ? "fwd" : "back") : again).focus({preventScroll:true});
    }
    function setMain(button, id, text) {
      const main = byId(id);
      if (main) main.textContent = text; else button.firstChild.textContent = text;
    }
    // The visitor makes one choice; day 20 then arrives by itself.
    function pick(build) {
      builtOnIt = choice = build;
      leave();
      at(1);
      byId("scene").hidden = byId("scene2").hidden = byId("switch").hidden = true;
      const recap = byId("recap");
      recap.hidden = false;
      if (build) {
        const yours = document.createElement("i");
        yours.className = "built mine";
        track.style.gridTemplateColumns = "repeat(20,minmax(0,1fr))";
        track.append(yours);
        recap.textContent = "You build on it. Your result is the twentieth piece.";
        byId("tracklabel").textContent = "20 pieces · every one says finished ✓";
      } else {
        recap.textContent = "You stop to check. Nothing in the record tells you where to look first.";
      }
      recap.focus({preventScroll:true});
      later(1500, dayTwenty);
    }
    function dayTwenty() {
      at(2);
      Array.from(track.children).forEach((tile, index) => {
        tile.style.transitionDelay = reduced.matches ? "0s" : (index * 45) + "ms";
        tile.classList.remove("built");
        tile.classList.add("wrong");
      });
      byId("tag").textContent = "Day 20";
      byId("tracklabel").textContent = "Day 20 · the work that used this setting needs checking";
      heading("Everything said finished.", "One thing had changed.");
      byId("note").hidden = false;
      caption("On the real project the team built on it for 19 days. Then a colleague noticed that later results had shifted, and traced it back to one setting." +
        (builtOnIt ? " Your result stands on it too." : ""));
      advance("What had changed?", showInstrument);
      settle(1);
    }
    // Back to day 1. The reference arrives by itself, under the reading it contradicts.
    function showInstrument() {
      leave();
      at(3);
      byId("tag").textContent = "Back to day 1";
      stage.querySelector(".days").hidden = true;
      byId("recap").hidden = true;
      byId("meter").hidden = false;
      story.dataset.sw = "on";
      heading("The number was perfect.", "That was the problem.");
      caption("A team was testing a computer simulation of its detector. They sent in a known signal of 1,000 units, but the simulation read 970.\nAn AI agent switched off one correction. Now the simulation read exactly 1,000. That looked like an improvement.");
      later(950, () => {
        story.dataset.sw = "off";
        byId("simval").textContent = "1,000";
        later(2600, showReference);
      });
    }
    function showReference() {
      story.dataset.ref = "1";
      const text = "But the team had already measured the real detector using the same signal. It read 970 too.\nThe simulation was supposed to reproduce the real detector, not an ideal one. By making the simulation read a perfect 1,000, the agent had actually made it less faithful to the experiment.\nThat earlier measurement was already recorded. But nothing connected it to the changed setting, so the apparent improvement went unchallenged.";
      const more = byId("caption2");
      if (more) { more.hidden = false; more.textContent = text; } else caption(text);
      advance("Same day, with this system in place", reopen);
      settle(2);
    }
    // Day 1 again. The tick turns stale by itself, then the first question returns.
    function reopen() {
      leave();
      at(4);
      story.dataset.mode = "today";
      story.dataset.ref = "0";
      byId("meter").hidden = byId("stakes").hidden = true;
      const more = byId("caption2");
      if (more) more.hidden = true;
      byId("caption").hidden = true;
      byId("tag").textContent = "With this system in place";
      heading("Same project, same change.", "This time it says so.");
      if (builtOnIt) track.lastElementChild.remove();
      track.style.gridTemplateColumns = "";
      const tiles = Array.from(track.children);
      tiles.forEach(tile => { tile.style.transitionDelay = ""; tile.className = ""; });
      tiles[0].className = "built";
      stage.querySelector(".days").hidden = false;
      byId("tracklabel").textContent = "Day 1 · the first check says finished ✓";
      const recap = byId("recap");
      recap.hidden = false;
      recap.textContent = "Day 1 again. The agent switches the same setting.";
      recap.focus({preventScroll:true});
      buildButton.disabled = true;
      setMain(buildButton, "buildmain", "Build on it as checked");
      byId("buildsub").textContent = "Not this time. That check used the old setting.";
      byId("checkmain").textContent = "See where to check";
      byId("checksub").textContent = "The record names what changed.";
      later(1200, () => {
        tiles[0].className = "stale";
        byId("tracklabel").textContent = "Day 1 · the setting changed · the earlier check reads stale, before anything is built on it";
        caption("The earlier check was recorded with the setting it used. Open the project after the change and it reads stale. Nobody had to notice. The question in front of you is the same.");
        byId("switch").hidden = false;
        checkButton.classList.add("beckon");
        settle(3);
      });
    }
    // The payoff takes the place of the two buttons: what the next agent is handed, then the way onward.
    function checkAgain() {
      at(5);
      checkButton.classList.remove("beckon");
      byId("switch").hidden = byId("caption").hidden = true;
      const recap = byId("recap");
      recap.textContent = "You open the project. This is what you are handed.";
      const second = byId("second");
      second.hidden = false;
      second.classList.add("unfold");
      byId("after").hidden = false;
      recap.focus({preventScroll:true});
      second.scrollIntoView({behavior:reduced.matches ? "instant" : "smooth",block:"nearest"});
      settle(4);
    }
    buildButton.onclick = () => pick(true);
    checkButton.onclick = () => scene === 4 ? checkAgain() : pick(false);
    backButton.onclick = () => jump(busy ? stop : stop - 1, "back");
    forwardButton.onclick = () => {
      if (busy) { jump(stop + 1, "fwd"); return; }
      if (stop === 0) (choice ? buildButton : checkButton).click();
      else if (stop === 3) checkButton.click();
      else nextButton.click();
      if (!forwardButton.disabled) forwardButton.focus({preventScroll:true});
    };
    byId("replay").onclick = () => {
      clearTimeout(changeTimer);
      choice = null;
      byId("try").replaceWith(startingView.cloneNode(true));
      mountDecision();
      byId("stage").classList.add("play");
      byId("tryh").focus({preventScroll:true});
      byId("try").scrollIntoView({block:"start",behavior:reduced.matches ? "instant" : "smooth"});
    };
    // Arriving by Back or Forward: the same steps, with no waiting.
    if (target || choice !== null) stage.classList.add("play");
    if (target) {
      instant = true;
      pick(choice);
      if (target > 1) { nextButton.hidden = true; showInstrument(); }
      if (target > 2) { nextButton.hidden = true; reopen(); }
      if (target > 3) checkAgain();
      instant = false;
    }
    steps();
  }
  mountDecision();
})();
