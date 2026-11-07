/* Owner phone page. The Ed25519 key is generated here with WebCrypto, is non-extractable and
   stays in this browser's IndexedDB. The server only ever gets the public key (hex) and
   signatures. What you approve is read from the exact bytes being signed. */
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var DB = 'ask-first-owner', STORE = 'keys', KEY = 'owner';
  var msg = $('#pair-msg');

  function idb(mode, fn) {
    return new Promise(function (resolve, reject) {
      var open = indexedDB.open(DB, 1);
      open.onupgradeneeded = function () { open.result.createObjectStore(STORE); };
      open.onerror = function () { reject(open.error); };
      open.onsuccess = function () {
        var tx = open.result.transaction(STORE, mode), req = fn(tx.objectStore(STORE));
        tx.oncomplete = function () { resolve(req.result); };
        tx.onerror = function () { reject(tx.error); };
      };
    });
  }
  function hex(buf) { return Array.prototype.map.call(new Uint8Array(buf), function (b) { return ('0' + b.toString(16)).slice(-2); }).join(''); }
  function post(url, body) {
    return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      .then(function (r) { return r.json().then(function (j) { j.status = r.status; return j; }); });
  }
  function supported() { return window.crypto && crypto.subtle && window.indexedDB; }

  async function getKey() { return idb('readonly', function (s) { return s.get(KEY); }); }
  async function makeKey() {
    var pair = await crypto.subtle.generateKey({name: 'Ed25519'}, false, ['sign', 'verify']);
    var pub = hex(await crypto.subtle.exportKey('raw', pair.publicKey));
    await idb('readwrite', function (s) { return s.put({priv: pair.privateKey, pub: pub}, KEY); });
    return {priv: pair.privateKey, pub: pub};
  }

  var form = $('#pair-form');
  if (form) form.addEventListener('submit', async function (e) {
    e.preventDefault();
    msg.textContent = ''; msg.className = 'result';
    try {
      if (!supported()) throw new Error('This browser has no Ed25519 WebCrypto. Use a recent browser.');
      var k = await getKey() || await makeKey();
      var r = await post('/owner/pair', {code: $('#code').value, public_key: k.pub});
      if (!r.ok) throw new Error('Pairing refused: ' + r.reason + '. ' + (r.detail || ''));
      msg.textContent = 'Paired. This phone can now approve mandates.'; msg.className = 'result ok';
      location.reload();
    } catch (err) { msg.textContent = String(err.message || err); msg.className = 'result bad'; }
  });

  document.querySelectorAll('.mandate').forEach(function (li) {
    var out = $('.result', li);
    function busy(b) { li.classList.toggle('busy', b); li.querySelectorAll('button').forEach(function (x) { x.disabled = b; }); }
    $('.approve', li).addEventListener('click', async function () {
      busy(true); out.textContent = 'Signing on this phone…'; out.className = 'result';
      try {
        if (!supported()) throw new Error('No Ed25519 WebCrypto in this browser.');
        var k = await getKey();
        if (!k) throw new Error('Pair this phone first (enter the code above).');
        var canon = li.getAttribute('data-canonical');
        var signed = JSON.parse(canon);                 /* what is signed == what is shown */
        var on = function (f) { return li.querySelector('[data-signed="' + f + '"]') || document.createElement('i'); };
        if (signed.recipient !== on('recipient').textContent || signed.action !== on('action').textContent ||
            Number(signed.cap).toFixed(2) !== on('cap').getAttribute('data-value'))
          throw new Error('Screen and signed bytes disagree; not signing.');
        var sig = hex(await crypto.subtle.sign({name: 'Ed25519'}, k.priv, new TextEncoder().encode(canon)));
        var r = await post('/owner/approve', {mandate_id: li.getAttribute('data-id'), signature: sig});
        if (!r.ok) throw new Error('Rejected: ' + r.reason + '. ' + (r.detail || ''));
        out.textContent = 'Approved and executed.'; out.className = 'result ok'; setTimeout(function () { location.reload(); }, 500);
      } catch (err) { out.textContent = String(err.message || err); out.className = 'result bad'; busy(false); }
    });
    $('.decline', li).addEventListener('click', async function () {
      busy(true);
      var r = await post('/owner/decline', {mandate_id: li.getAttribute('data-id')});
      out.textContent = r.ok ? 'Declined. A decline is final.' : 'Could not decline.'; out.className = 'result ' + (r.ok ? 'ok' : 'bad');
      setTimeout(function () { location.reload(); }, 500);
    });
  });

  /* "Expires in 58 min": the same words as the server (gate.minutes_left), kept current. */
  function left(exp) {
    var s = exp - Math.floor(Date.now() / 1000);
    if (s <= 0) return 'expired';
    if (s < 60) return 'under a minute';
    var m = Math.ceil(s / 60);
    return m <= 90 ? m + ' min' : Math.floor(m / 60) + ' h ' + (m % 60) + ' min';
  }
  function tick() {
    document.querySelectorAll('.expires[data-exp]').forEach(function (e) {
      var l = left(Number(e.getAttribute('data-exp')));
      e.textContent = l === 'expired' ? 'Expired' : 'Expires in ' + l;
      if (l === 'expired') {
        var li = e.closest('.mandate');
        if (li) li.querySelectorAll('.decide button').forEach(function (b) { b.disabled = true; });
      }
    });
  }

  /* The phone buzzes: poll /owner/api/pending (two counters); a new request vibrates the phone (where the browser
     allows it) and puts "(1)" in the tab title. Nothing here can approve: that still needs a tap. */
  var list = $('#pending-list'), bar = $('#new-request');
  var BASE_TITLE = document.title, BADGE = 'ask-first-badge';
  var asked = Number(list ? list.getAttribute('data-asked') : 0) || 0, unseen = 0;
  function badge(n) {                         /* carried over the reload that shows the new card */
    unseen = n;
    document.title = n > 0 ? '(' + n + ') ' + BASE_TITLE : BASE_TITLE;
    try { if (n > 0) sessionStorage.setItem(BADGE, String(n)); else sessionStorage.removeItem(BADGE); } catch (e) { /* private mode */ }
  }
  try { var carried = Number(sessionStorage.getItem(BADGE) || 0); if (carried > 0) badge(carried); } catch (e) { /* private mode */ }
  ['pointerdown', 'keydown'].forEach(function (ev) { document.addEventListener(ev, function () { badge(0); }); });
  function busyNow() {
    return !!document.querySelector('.mandate.busy, .mandate details[open]') ||
      (document.activeElement && /INPUT|TEXTAREA/.test(document.activeElement.tagName));
  }
  if (bar) bar.addEventListener('click', function () { location.reload(); });

  function poll() {
    if (!list) return;
    /* the poll answers two numbers only (waiting now, asked ever): no ids, amounts or bytes */
    fetch(list.getAttribute('data-poll'), {headers: {'Accept': 'application/json'}, cache: 'no-store'})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || typeof j.asked !== 'number' || typeof j.waiting !== 'number') return;
        var fresh = j.asked - asked;
        if (fresh <= 0) return;
        asked = j.asked;
        if (j.waiting <= 0) return;           /* asked and already gone (declined, expired) */
        if (navigator.vibrate) { try { navigator.vibrate([180, 90, 180]); } catch (e) { /* not allowed yet */ } }
        badge(unseen + fresh);
        if (busyNow()) {                      /* never pull the page from under a tap */
          bar.textContent = unseen === 1 ? 'A new request arrived · show it' : unseen + ' new requests · show them';
          bar.hidden = false;
        } else {
          location.reload();                  /* the server renders the card from the signed fields */
        }
      })
      .catch(function () { /* offline for a moment: try again on the next tick */ });
  }
  tick();
  setInterval(tick, 15000);
  setInterval(poll, Number((list && list.getAttribute('data-poll-ms')) || 3000));
})();
