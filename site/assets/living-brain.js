/* The living brain, v4. Same choice sequence as brain-v3; the memory is now drawn.
   Without this script the section still reads top to bottom: every sentence is in the HTML. */
(function () {
  var root = document.querySelector('[data-lb]');
  if (!root) return;
  var $ = function (id) { return root.querySelector('#' + id); };
  var NS = 'http://www.w3.org/2000/svg';
  var still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var SWITCH = [118, 196], DAYS = 19;
  var STEPS = ['The choice', 'Nineteen days', 'Why it failed', 'With the links kept', 'What changed'];
  var NOTE_CLOSED = $('lb-note').textContent;
  var NOTE_OPEN = 'Earlier test · a little under 100';
  var firstReading = $('lb-readout').textContent;
  var firstQuestion = $('lb-caption').textContent;
  var scene = 0, looked = false, keyboardStep = false, timers = [], nodes = [], threads = [];

  // Nineteen days of work, placed inside the outline in reading order.
  var pts = [], i;
  for (i = 0; i < 7; i++) pts.push([222 + i * 46, 140 - 8 * Math.sin(Math.PI * i / 6)]);
  for (i = 0; i < 6; i++) pts.push([240 + i * 50, 200 + (i % 2 ? 4 : -4)]);
  for (i = 0; i < 6; i++) pts.push([215 + i * 46, 256 + 8 * Math.sin(Math.PI * i / 5)]);
  pts.forEach(function (p) {
    var t = document.createElementNS(NS, 'path');
    t.setAttribute('class', 'lb-thread');
    t.setAttribute('d', 'M' + SWITCH[0] + ' ' + SWITCH[1] + ' C ' + (SWITCH[0] + 70) + ' ' + SWITCH[1] + ', ' +
      (p[0] - 70) + ' ' + p[1].toFixed(1) + ', ' + (p[0] - 12) + ' ' + p[1].toFixed(1));
    $('lb-threads').appendChild(t); threads.push(t);
    var r = document.createElementNS(NS, 'rect');
    r.setAttribute('class', 'lb-node'); r.setAttribute('x', p[0] - 11); r.setAttribute('y', (p[1] - 8).toFixed(1));
    r.setAttribute('width', 22); r.setAttribute('height', 16); r.setAttribute('rx', 4);
    $('lb-nodes').appendChild(r); nodes.push(r);
  });

  function later(fn, ms) { if (still || !ms) { fn(); return; } timers.push(setTimeout(fn, ms)); }
  function stopMotion() { timers.forEach(clearTimeout); timers = []; }
  function each(list, cls, base, gap) {
    list.forEach(function (el, n) { later(function () { el.setAttribute('class', base + (cls ? ' ' + cls : '')); }, gap ? n * gap : 0); });
  }
  function paint(cls, gap) { each(nodes, cls, 'lb-node', gap); }
  function link(cls, gap) { each(threads, cls, 'lb-thread', gap); }
  function say(text) { $('lb-caption').textContent = text; }
  function label(text) { $('lb-tracklabel').textContent = text; }
  function read(html) { $('lb-readout').innerHTML = html; }
  function sw(v) {
    root.dataset.sw = v;
    $('lb-on').classList.toggle('is-sel', v === 'on'); $('lb-off').classList.toggle('is-sel', v === 'off');
    $('lb-on').setAttribute('aria-pressed', v === 'on'); $('lb-off').setAttribute('aria-pressed', v === 'off');
  }
  function lock(v) { $('lb-on').disabled = v; $('lb-off').disabled = v; }
  function set(n) { scene = n; root.dataset.scene = n; }
  function step(n) {
    var items = root.querySelectorAll('.lb-steps i');
    for (var k = 0; k < items.length; k++) { items[k].className = k < n ? 'is-done' : (k === n ? 'is-now' : ''); }
    $('lb-stepname').textContent = STEPS[n];
  }
  function next(text, fn) {
    var b = $('lb-next'); b.textContent = text; b.hidden = false;
    if (keyboardStep && (document.activeElement === document.body || root.contains(document.activeElement))) {
      b.focus({ preventScroll: true });
    }
    b.onclick = function (event) { keyboardStep = event.detail === 0; b.hidden = true; fn(); };
  }
  function note(open) {
    root.dataset.ref = open ? '1' : '0';
    $('lb-note').textContent = open ? NOTE_OPEN : NOTE_CLOSED;
    $('lb-note').setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function fill() {
    var d = 0;
    (function one() {
      nodes[d].setAttribute('class', 'lb-node is-built'); d++;
      label('Day ' + d + ' · work built on that choice');
      if (d < DAYS) { later(one, 170); } else { later(fall, 800); }
    })();
  }
  function fall() {
    set(2); paint('is-wrong'); label('Day 20');
    say('On day 20, someone reviewing the results noticed they had shifted. The changed setting had gone unmarked.');
    next('What did the earlier test show?', why);
  }
  function why() {
    set(3); step(2); note(true); $('lb-next').hidden = true;
    read('The reference sample read <b>a little under 100</b> with the usual correction.');
    say('The reference sample also read low. The simulation with the usual correction agreed with that earlier test. Its result had been in the project notes for a month.');
    next('Try the same change with a saved check', again);
  }
  function again() {
    set(4); step(3); root.dataset.mode = 'today'; root.dataset.ask = '1';
    $('lb-tag').textContent = 'Replay with the operating system';
    $('lb-fieldcap').textContent = 'The same days · links kept';
    sw('on'); lock(false); paint('is-holds', 30); link('is-on', 30);
    label('Same 19 days · one mark per day');
    read('The simulation reads <b>a little under 100</b>. The saved check still applies.');
    say('Now the setting is in a tracked file. Switch the correction off and see what the next agent can tell.');
    if (keyboardStep) $('lb-off').focus({ preventScroll: true });
  }
  function flag() {
    var first = scene === 4;
    stopMotion();
    set(5); root.dataset.ask = '0'; sw('off'); paint('is-stale', 45); link('is-on is-stale', 45);
    label('Check again · the correction file changed');
    read('The simulation reads <b>almost exactly 100</b>.');
    say('The next agent can see that the correction changed after the last check. It knows to check the result before using it.');
    $('lb-verdict').textContent = 'Check again · correction changed';
    $('lb-verdict').classList.add('is-stale');
    $('lb-second').hidden = false;
    if (first) next('What changed after', after);
  }
  function restore() {
    stopMotion();
    sw('on'); paint('is-holds'); link('is-on');
    label('Original setting restored · the saved check applies again');
    read('The simulation reads <b>a little under 100</b>.');
    $('lb-verdict').textContent = 'Earlier check applies · original files restored';
    $('lb-verdict').classList.remove('is-stale');
    say('The files match the ones used for the saved check. The next agent can use that check again.');
  }
  function after() {
    step(4); $('lb-after').hidden = false;
    $('lb-after').scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'nearest' });
    if (keyboardStep) $('lb-after').querySelector('h3').focus({ preventScroll: true });
  }
  function reset(event) {
    stopMotion(); looked = false; keyboardStep = false;
    set(0); step(0); root.dataset.mode = 'then'; root.dataset.ask = '0'; sw('none'); lock(false); note(false);
    paint(''); link('');
    $('lb-tag').textContent = 'As it happened';
    $('lb-fieldcap').textContent = 'The project’s memory · one mark a day, no links';
    label('19 days of work will stand on this choice');
    read(firstReading);
    say(firstQuestion);
    $('lb-next').hidden = true; $('lb-second').hidden = true; $('lb-after').hidden = true;
    root.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' });
    if (event && event.detail === 0) $('lb-on').focus({ preventScroll: true });
  }
  function pick(v) {
    if (scene === 0) {
      set(1); step(1); sw('off'); lock(true); read('The simulation reads <b>almost exactly 100</b>.');
      if (v === 'off') {
        say('You switched it off. The agent made the same choice and kept the setting that gave back almost exactly 100.');
      } else if (looked) {
        say('You read the earlier test and kept the usual correction. The agent switched it off and kept the reading closer to 100.');
      } else {
        say('You kept the usual correction. The agent switched it off because the reading looked closer to 100.');
      }
      next('See what happened over 19 days', fill);
    } else if (scene >= 4) {
      if (v === 'off' && root.dataset.sw !== 'off') flag();
      else if (v === 'on' && scene === 5 && root.dataset.sw !== 'on') restore();
    }
  }
  $('lb-on').onclick = function (event) { keyboardStep = event.detail === 0; pick('on'); };
  $('lb-off').onclick = function (event) { keyboardStep = event.detail === 0; pick('off'); };
  $('lb-note').onclick = function (event) {
    keyboardStep = event.detail === 0;
    if (scene === 2) { why(); return; }
    var open = root.dataset.ref !== '1';
    note(open);
    if (scene === 0) {
      looked = looked || open;
      say(open ? 'A month ago, a reference sample read a little under 100 with the usual correction. Which setting would you keep?' : firstQuestion);
    }
  };
  $('lb-again').onclick = reset;
  // The page is written to read without this script; once it runs, the later parts wait for their turn.
  $('lb-next').hidden = true; $('lb-second').hidden = true; $('lb-after').hidden = true;
  root.dataset.live = '1'; step(0);
})();
