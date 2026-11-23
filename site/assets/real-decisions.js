/* Five real decisions. Each choice answers in one line; the record of what happened opens after the first choice.
   Without this script every reply and every record is already on the page. */
(function () {
  var root = document.querySelector('[data-rd]');
  if (!root) return;
  var cases = root.querySelectorAll('.rd-case'), count = root.querySelector('#rd-count'), tried = 0;
  function tally() {
    count.textContent = tried === 0 ? 'Pick a move on any of them. Nothing is scored.'
      : tried < cases.length ? tried + ' of ' + cases.length + ' tried'
      : 'All five tried. Each one is in the record this page was built from.';
  }
  Array.prototype.forEach.call(cases, function (card) {
    var buttons = card.querySelectorAll('.rd-choices button'), say = card.querySelector('.rd-say');
    var replies = card.querySelectorAll('.rd-replies li span');
    Array.prototype.forEach.call(buttons, function (b, n) {
      b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', function () {
        Array.prototype.forEach.call(buttons, function (o) { o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); });
        say.textContent = replies[n].textContent;
        if (!card.classList.contains('is-done')) { card.classList.add('is-done'); tried++; tally(); }
      });
    });
  });
  root.dataset.live = '1'; tally();
})();
