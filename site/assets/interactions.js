/* A new random key for each page load. No browser storage or full URLs are sent. */
(function () {
  "use strict";
  if (location.origin !== "https://whatstillholds.com" || navigator.globalPrivacyControl ||
      navigator.doNotTrack === "1" || !window.crypto || !crypto.randomUUID) return;

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
