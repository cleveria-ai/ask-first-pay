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
    msg.textContent = '';
    try {
      if (!supported()) throw new Error('This browser has no Ed25519 WebCrypto. Use a recent Chrome, Edge, Safari or Firefox.');
      var k = await getKey() || await makeKey();
      var r = await post('/owner/pair', {code: $('#code').value, public_key: k.pub});
      if (!r.ok) throw new Error('Pairing refused: ' + r.reason + '. ' + (r.detail || ''));
      msg.textContent = 'Paired. This phone can now approve mandates.';
      location.reload();
    } catch (err) { msg.textContent = String(err.message || err); }
  });

  document.querySelectorAll('.mandate').forEach(function (li) {
    var out = $('.result', li);
    function busy(b) { li.querySelectorAll('button').forEach(function (x) { x.disabled = b; }); }
    $('.approve', li).addEventListener('click', async function () {
      busy(true); out.textContent = '';
      try {
        if (!supported()) throw new Error('No Ed25519 WebCrypto in this browser.');
        var k = await getKey();
        if (!k) throw new Error('Pair this phone first (enter the code above).');
        var canon = li.getAttribute('data-canonical');
        var signed = JSON.parse(canon);                 /* what is signed == what is shown */
        var shown = li.querySelector('dd').textContent;
        if (signed.recipient !== shown) throw new Error('Screen and signed bytes disagree; not signing.');
        var sig = hex(await crypto.subtle.sign({name: 'Ed25519'}, k.priv, new TextEncoder().encode(canon)));
        var r = await post('/owner/approve', {mandate_id: li.getAttribute('data-id'), signature: sig});
        if (!r.ok) throw new Error('Rejected: ' + r.reason + '. ' + (r.detail || ''));
        out.textContent = 'Approved and executed.'; setTimeout(function () { location.reload(); }, 500);
      } catch (err) { out.textContent = String(err.message || err); busy(false); }
    });
    $('.decline', li).addEventListener('click', async function () {
      busy(true);
      var r = await post('/owner/decline', {mandate_id: li.getAttribute('data-id')});
      out.textContent = r.ok ? 'Declined.' : 'Could not decline.';
      setTimeout(function () { location.reload(); }, 500);
    });
  });
})();
