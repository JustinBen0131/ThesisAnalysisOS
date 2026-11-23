// Run the release client with synthetic browser signals. All requests stay in this process.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const client = fs.readFileSync(path.join(__dirname, "assets/interactions.js"), "utf8");
const turn = () => new Promise(resolve => setImmediate(resolve));

function page(signal, initiallyPrivate, hidden, status) {
  const origin = "https://whatstillholds.com";
  const listeners = {}, requests = [], scripts = [];
  const context = {
    location: new URL(origin + "/evidence/"), URL, URLSearchParams,
    document: {
      hidden, referrer: "", currentScript: {dataset: {release: "123456789abc", cfBeacon: "{}"}, hasAttribute: () => true},
      addEventListener: (type, fn) => { listeners[type] = fn; },
      querySelector: () => null, createElement: () => ({dataset: {}}), head: {append: script => scripts.push(script)}
    },
    navigator: {}, crypto: {randomUUID: () => "synthetic-page"}, matchMedia: () => ({matches:false}),
    sessionStorage: {getItem: () => null}, Element: class {}, fetch: (_url, options) => {
      requests.push(options); return Promise.resolve({status});
    }
  };
  context.window = context;
  function optOut() {
    if (signal === "window") context.doNotTrack = "1";
    else if (signal === "navigator") context.navigator.doNotTrack = "1";
    else context.navigator.globalPrivacyControl = true;
  }
  if (initiallyPrivate) optOut();
  vm.runInNewContext(client, context);
  return {requests, scripts, optOut, visible() {
    context.document.hidden = false;
    listeners.visibilitychange?.();
  }};
}

(async () => {
  for (const signal of ["gpc", "navigator", "window"]) {
    const already = page(signal, true, false, 200);
    assert.equal(already.requests.length, 0);
    assert.equal(already.scripts.length, 0);
    const hidden = page(signal, false, true, 200);
    hidden.optOut();
    hidden.visible();
    assert.equal(hidden.requests.length, 0);
    const retry = page(signal, false, false, 503);
    assert.equal(retry.requests.length, 1);
    retry.optOut();
    await turn();
    assert.equal(retry.requests.length, 1);
  }
  const allowed = page("gpc", false, false, 503);
  await turn();
  assert.equal(allowed.requests.length, 2);
  assert.equal(allowed.requests[0].credentials, "omit");
  console.log("Three privacy signals pass at page load, on visibility change and before retry. Positive control passed.");
})().catch(error => { console.error(error); process.exitCode = 1; });
