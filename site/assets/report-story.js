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
  function mountDecision() {
    const stage = byId("stage");
    const track = byId("track");
    const buildButton = byId("build");
    const checkButton = byId("check");
    const nextButton = byId("next");
    let builtOnIt = false;
    scene = 0;
    story.dataset.mode = "then";
    story.dataset.sw = "none";
    story.dataset.ref = "0";
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
    function pick(build) {
      builtOnIt = build;
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
      caption("On the real project, work was built on the changed setting for 19 days.");
      advance("Go to day 20", dayTwenty);
      recap.focus({preventScroll:true});
    }
    function dayTwenty() {
      at(2);
      Array.from(track.children).forEach(tile => {
        tile.classList.remove("built");
        tile.classList.add("wrong");
      });
      byId("tag").textContent = "Day 20";
      byId("tracklabel").textContent = "Day 20 · the work that used this setting needs checking";
      heading("Everything said finished.", "One thing had changed.");
      byId("stakes").hidden = byId("note").hidden = false;
      caption("A colleague noticed that later results had shifted and traced the change back to one setting." +
        (builtOnIt ? " Your result uses it too." : ""));
      advance("What had changed?", showInstrument);
    }
    function showInstrument() {
      at(3);
      byId("tag").textContent = "Back to day 1";
      stage.querySelector(".days").hidden = true;
      byId("meter").hidden = false;
      story.dataset.sw = "on";
      changeTimer = window.setTimeout(() => {
        story.dataset.sw = "off";
        byId("simval").textContent = "100, almost exactly";
      }, reduced.matches ? 0 : 950);
      heading("The number was perfect.", "That was the problem.");
      caption("An agent tested a computer model of an instrument. Put in 100 and it read a little under 100. Switching off one correction made it read almost exactly 100, so the agent kept that setting.");
      advance("Why was a perfect 100 wrong?", showReference);
    }
    function showReference() {
      story.dataset.ref = "1";
      caption("The team had already tested the instrument. Its reference reading was a little under 100. The rounder number came from changing how the model measured. The earlier test still stood.");
      advance("Open the project again, with this system in place", reopen);
    }
    function reopen() {
      at(4);
      story.dataset.mode = "today";
      story.dataset.ref = "0";
      byId("meter").hidden = byId("stakes").hidden = true;
      byId("tag").textContent = "With this system in place";
      stage.querySelector(".days").hidden = false;
      heading("Same project, same change.", "This time it says so.");
      if (builtOnIt) track.lastElementChild.remove();
      track.style.gridTemplateColumns = "";
      Array.from(track.children).forEach(tile => { tile.className = ""; });
      track.firstElementChild.className = "stale";
      byId("tracklabel").textContent = "Day 1 · the result reads stale · changed: one setting";
      byId("recap").textContent = "Day 1 again. The agent switches the setting.";
      buildButton.disabled = true;
      byId("buildsub").textContent = "The result reads stale.";
      byId("checkmain").textContent = "Check it first";
      byId("checksub").textContent = "One setting changed. Start there.";
      byId("switch").hidden = false;
      checkButton.classList.add("beckon");
      caption("You open the project. The saved result now names the setting that changed. Where would you start?");
      checkButton.focus({preventScroll:true});
    }
    function checkAgain() {
      at(5);
      checkButton.classList.remove("beckon");
      checkButton.classList.add("sel");
      checkButton.disabled = true;
      byId("second").hidden = false;
      caption("Set aside the model result saved before the setting changed. Keep the earlier instrument measurement and use it to check the next result.");
      advance("What changed after", () => {
        const after = byId("after");
        after.hidden = false;
        after.setAttribute("tabindex", "-1");
        after.focus({preventScroll:true});
        after.scrollIntoView({behavior:reduced.matches ? "instant" : "smooth",block:"center"});
      });
      byId("caption").focus({preventScroll:true});
    }
    buildButton.onclick = () => pick(true);
    checkButton.onclick = () => scene === 4 ? checkAgain() : pick(false);
    byId("replay").onclick = () => {
      clearTimeout(changeTimer);
      byId("try").replaceWith(startingView.cloneNode(true));
      mountDecision();
      byId("stage").classList.add("play");
      byId("tryh").focus({preventScroll:true});
      byId("try").scrollIntoView({block:"start",behavior:reduced.matches ? "instant" : "smooth"});
    };
  }
  mountDecision();
})();
