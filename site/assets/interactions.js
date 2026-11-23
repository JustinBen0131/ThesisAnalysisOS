/* A new random key for each page load. No browser storage or full URLs are sent. */
(function () {
  "use strict";
  if (location.origin !== "https://whatstillholds.com" || navigator.globalPrivacyControl ||
      navigator.doNotTrack === "1" || !window.crypto || !crypto.randomUUID) return;

  if (document.currentScript?.hasAttribute("data-release")) return;

  const homePath = path => path === "/" || path === "/index.html";
  const evidencePath = path => path === "/evidence" || path.startsWith("/evidence/");
  const home = homePath(location.pathname);
  if (!home && !evidencePath(location.pathname)) return;
  const ref = document.referrer ? new URL(document.referrer) : null;
  const fromHome = ref && ref.origin === location.origin && homePath(ref.pathname);
  const fixture = params => params.get("report_check") === "1";
  const test = fixture(new URLSearchParams(location.search)) || (!home && fromHome && fixture(ref.searchParams));
  const key = crypto.randomUUID();
  const endpoint = "https://whatstillholds-interactions.just0131.workers.dev/v1";
  const HOME = 1, OFFER = 2, START = 4, RESULT = 8, LINK = 16, RESULT_LINK = 32;
  const EVIDENCE = 64, FROM_HOME = 128, WALKTHROUGH = 256;
  let flags = 0;

  function mark(bits) {
    if ((flags & bits) === bits) return;
    flags |= bits;
    fetch(endpoint, {method: "POST", body: key + "|" + flags + "|" + Number(Boolean(test)),
      mode: "cors", credentials: "omit", referrerPolicy: "no-referrer", keepalive: true}).catch(() => {});
  }
  function begin() {
    if (document.hidden || document.prerendering) return;
    mark(home ? HOME : EVIDENCE | (fromHome ? FROM_HOME : 0));
  }
  begin();
  document.addEventListener("visibilitychange", begin);
  document.addEventListener("prerenderingchange", begin);
  if (!home) return;

  // These roles are shared by releases even when the copy or layout changes.
  const role = (name, originalId) => document.querySelector('[data-reader="' + name + '"]') || document.getElementById(originalId);
  const start = role("play", "mind-start");
  const demo = role("example", "mind-demo");
  const outcome = role("conclusion", "swing-reading");
  const headline = role("headline", "mind-title");

  function onScreen(element, eligible, bits) {
    if (!element || !window.IntersectionObserver) return;
    let inView = false, timer = 0;
    function check() {
      clearTimeout(timer);
      if (!document.hidden && inView && eligible()) {
        timer = setTimeout(() => { if (!document.hidden && inView && eligible()) mark(bits); }, 1000);
      }
    }
    const io = new IntersectionObserver(entries => {
      inView = entries[entries.length - 1].intersectionRatio >= 0.5;
      check();
    }, {threshold: [0, 0.5]});
    io.observe(element);
    document.addEventListener("visibilitychange", check);
    if (demo) {
      const changes = new MutationObserver(check);
      changes.observe(demo, {attributes: true, attributeFilter: ["hidden"]});
      if (outcome) changes.observe(outcome, {attributes: true, attributeFilter: ["hidden"]});
    }
  }
  if (start && demo) onScreen(start, () => !start.hidden && demo.hidden, HOME | OFFER);
  if (demo && outcome) onScreen(headline, () => Boolean(flags & START) && !demo.hidden && !outcome.hidden, HOME | OFFER | START | RESULT);

  function action(event) {
    if (!event.isTrusted || event.defaultPrevented || document.hidden || event.button > 1) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (event.type === "click" && start && start.contains(target) && demo && !demo.hidden) mark(HOME | OFFER | START);
    if (event.type === "click" && target.closest(".stepnav button, .walk button")) mark(HOME | WALKTHROUGH);
    const link = target.closest("a[href]");
    if (!link) return;
    const dest = new URL(link.href);
    if (dest.origin !== location.origin || !evidencePath(dest.pathname)) return;
    const atResult = Boolean(flags & START) && outcome && !outcome.hidden && demo && !demo.hidden && outcome.contains(link);
    mark(HOME | LINK | (atResult ? RESULT | RESULT_LINK : 0));
  }
  document.addEventListener("click", action);
  document.addEventListener("auxclick", action);
}());

/* This contract is selected by the release stamp on the public V2 script tag. */
(function () {
  "use strict";
  const loader = document.currentScript;
  const release = loader?.dataset.release;
  if (!/^[0-9a-f]{12}$/.test(release || "") || location.origin !== "https://whatstillholds.com" ||
      navigator.globalPrivacyControl || navigator.doNotTrack === "1" || window.doNotTrack === "1") return;

  const own = location.origin;
  const params = new URLSearchParams(location.search);
  const ref = document.referrer ? new URL(document.referrer) : null;
  const localRef = ref?.origin === own;
  const tag = params.get("report_check");
  const inherited = localRef && ref.searchParams.get("report_check") === "1";
  let test = tag === "1" || (tag !== "0" && inherited);
  // Only an explicitly labeled QA tab stores a boolean. Ordinary readers get no storage or session ID.
  try {
    if (tag === "0") sessionStorage.removeItem("wsh-report-check");
    else if (test) sessionStorage.setItem("wsh-report-check", "1");
    else test = sessionStorage.getItem("wsh-report-check") === "1";
  } catch (_) {}
  if (test) {
    // Retain the test marker across named tabs, middle-clicks and browsers with storage disabled.
    function carryTag(event) {
      const link = event.target.closest?.("a[href]");
      if (!link) return;
      const target = new URL(link.href);
      if (target.origin !== own || link.hasAttribute("download")) return;
      const sameTabFragment = link.getAttribute("href").startsWith("#") && !link.target &&
        event.type === "click" && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
      if (sameTabFragment) return;
      if (!(target.pathname.endsWith("/") || /\.html$/.test(target.pathname)) || target.searchParams.has("report_check")) return;
      target.searchParams.set("report_check", "1");
      link.href = target.href;
    }
    for (const name of ["click", "auxclick", "contextmenu"]) document.addEventListener(name, carryTag, true);
  } else if (loader.dataset.cfBeacon) {
    const beacon = document.createElement("script");
    beacon.src = "https://static.cloudflareinsights.com/beacon.min.js";
    beacon.dataset.cfBeacon = loader.dataset.cfBeacon;
    beacon.defer = true;
    document.head.append(beacon);
  }

  function surface(path) {
    const name = path.replace(/\/index\.html$/, "/").replace(/\/$/, "");
    if (!name) return "home";
    if (name === "/record.html") return "record";
    if (name === "/hpc" || name === "/decision") return name.slice(1);
    if (name === "/workflows/transit") return "transit";
    if (name.startsWith("/workflows/")) return "workflow";
    if (/^\/(evidence|studies)(\/|$)/.test(name)) return "evidence";
    if (name === "/exchange") return "exchange";
    return null;
  }

  function entryChannel() {
    if (localRef) return "internal";
    const tagged = (params.get("utm_source") || "").toLowerCase();
    if (["github", "youtube", "linkedin"].includes(tagged)) return tagged;
    if (!ref) return "direct_unknown";
    const host = ref.hostname.toLowerCase();
    const under = domain => host === domain || host.endsWith("." + domain);
    if (under("github.com")) return "github";
    if (under("youtube.com") || under("youtu.be")) return "youtube";
    if (under("linkedin.com") || under("lnkd.in")) return "linkedin";
    if (under("google.com") || under("bing.com") || under("duckduckgo.com")) return "search";
    return "other_referral";
  }

  const page = surface(location.pathname);
  if (!page || !window.crypto?.randomUUID) return;
  const key = crypto.randomUUID();
  const entry = entryChannel();
  const layout = matchMedia("(max-width:820px)").matches ? "compact" : "wide";
  const endpoint = "https://whatstillholds-interactions.just0131.workers.dev/v1";
  const OPEN=1, OFFER=2, START=4, CHECKPOINT=8, FINISH=16, PROOF=32, ZIP=64, FEEDBACK=128;
  const FILM_PLAY=256, FILM_END=512, SETUP=1024, PACKET=2048, BUILD=4096, CHECK=8192;
  const CASE=16384, SHEET=32768, REFERENCE=65536, CONTINUE=131072, FILM_OFFER=262144;
  let flags = 0;
  function mark(bits) {
    if (document.hidden || document.prerendering || (flags & bits) === bits) return;
    flags |= OPEN | bits;
    const body = ["2", key, release, page, entry, layout, Number(test), flags].join("|");
    const options = {method:"POST", body, credentials:"omit", mode:"cors", referrerPolicy:"no-referrer", keepalive:true};
    // Each update contains the full state. Retried or reordered requests merge into the same page row.
    const sent = flags;
    const retry = () => { if (flags === sent) fetch(endpoint, options).catch(() => {}); };
    fetch(endpoint, options).then(response => { if (response.status >= 500) retry(); }, retry);
  }
  function opened() { mark(OPEN); }
  opened();
  document.addEventListener("visibilitychange", opened);
  document.addEventListener("prerenderingchange", opened);

  function exposure(selector, bit) {
    const element = document.querySelector(selector);
    if (!element || !window.IntersectionObserver) return;
    let visible = false, timer;
    const observe = new IntersectionObserver(entries => {
      visible = entries[entries.length - 1].intersectionRatio >= .5;
      arm();
    }, {threshold:[0, .5]});
    function arm() {
      clearTimeout(timer);
      if (visible && !document.hidden && !document.prerendering) timer = setTimeout(() => {
        if (visible && !document.hidden && element.isConnected && element.getClientRects().length) {
          mark(bit);
          observe.disconnect();
          document.removeEventListener("visibilitychange", arm);
        }
      }, 1000);
    }
    observe.observe(element);
    document.addEventListener("visibilitychange", arm);
  }
  const sheet = page === "hpc" && document.querySelector("[data-run-sheet] [data-result]");
  if (sheet) new MutationObserver(() => {
    if (!sheet.hidden && sheet.getClientRects().length &&
        sheet.closest("[data-run-sheet]").querySelector('[name="reuse"]')?.value === "new") mark(SHEET);
  }).observe(sheet, {attributes:true, attributeFilter:["hidden"]});
  const decision = page === "home" || page === "decision";
  if (decision) exposure("#switch #build", OFFER);
  if (page === "record") exposure("#mind-start", OFFER);
  if (page === "hpc") exposure('[data-stage="plan"] [data-go="returned"]', OFFER);
  const video = document.querySelector("video#preview-film");
  if (page === "home" && video) {
    exposure(".film-play", FILM_OFFER);
    video.addEventListener("playing", () => { if (!video.paused) mark(FILM_OFFER | FILM_PLAY); });
    video.addEventListener("ended", () => { if (video.ended) mark(FILM_OFFER | FILM_PLAY | FILM_END); });
  }

  const shown = selector => {
    const el = document.querySelector(selector);
    return Boolean(el && !el.closest("[hidden]") && el.getClientRects().length);
  };
  // The story advances on timers as well as clicks and can replace its controls on Back.
  const story = decision && document.querySelector(".visitor-story");
  function readStory() {
    if (!story || !(flags & START) || document.hidden) return;
    if (shown("#stakes") || shown("#track .wrong")) mark(CHECKPOINT);
    if ((flags & CHECKPOINT) && story.dataset.ref === "1" && shown("#meter")) mark(REFERENCE);
    if ((flags & REFERENCE) && shown("#after")) mark(FINISH);
  }
  if (story) {
    const changes = new MutationObserver(() => {
      readStory();
      if (flags & FINISH) changes.disconnect();
    });
    changes.observe(story, {subtree:true, childList:true, attributes:true,
      attributeFilter:["hidden", "class", "data-ref"]});
    document.addEventListener("visibilitychange", readStory);
  }
  function controls(target) {
    if (decision && target.closest("#try")) {
      const btn = target.closest("button");
      if (btn && !(flags & START) && ["build", "check"].includes(btn.id) && shown("#recap"))
        mark(OFFER | START | (btn.id === "build" ? BUILD : CHECK));
      readStory();
    }
    if (page === "decision" && target.closest(".rd-case.is-done .rd-choices button")) mark(CASE);
    if (page === "record" && target.closest("#mind-start, #guide-next")) {
      const step = document.querySelector("#architecture-cover")?.dataset.guideStep;
      if (step === "1") mark(OFFER | START);
      if (step === "2" && flags & START) mark(CHECKPOINT);
      if (step === "3" && flags & CHECKPOINT) mark(FINISH);
    }
    if (page === "hpc") {
      const step = target.closest("[data-hpc-board] [data-go]")?.dataset.go;
      if (step === "returned" && shown('[data-stage="returned"]')) mark(OFFER | START);
      if (step === "checked" && flags & START && shown('[data-stage="checked"]')) mark(CHECKPOINT);
      if (step === "resolved" && flags & CHECKPOINT && shown('[data-stage="resolved"]')) mark(FINISH);
    }
  }
  function action(event) {
    if (!event.isTrusted || event.defaultPrevented || document.hidden || event.button > 1 ||
        (event.type === "auxclick" && event.button !== 1)) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (event.type === "click") controls(target);
    const link = target.closest("a[href]");
    if (!link) return;
    const dest = new URL(link.href);
    if (dest.origin === "https://github.com" && dest.pathname === "/JustinBen0131/ThesisAnalysisOS/issues/new" &&
        page === "exchange") mark(FEEDBACK);
    if (dest.origin !== own) return;
    if (decision && flags & FINISH && link.closest("#after, #second .onward")) mark(CONTINUE);
    if (/^\/(evidence|studies|records)(\/|$)/.test(dest.pathname) &&
        (dest.pathname !== location.pathname || dest.hash && dest.hash !== location.hash)) mark(PROOF);
    if (/^\/source\/thesisanalysisos-[a-f0-9]{7,40}\.zip$/.test(dest.pathname)) mark(ZIP);
    if (surface(dest.pathname) === "home" && ["#start", "#run"].includes(dest.hash)) mark(SETUP);
    if (page === "transit" && dest.pathname === "/workflows/transit/handoff.txt") mark(PACKET);
  }
  document.addEventListener("click", action);
  document.addEventListener("auxclick", action);
}());
