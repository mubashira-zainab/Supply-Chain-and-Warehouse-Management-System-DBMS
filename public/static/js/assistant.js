/* SC&WMS — AI assistant chat UI. The browser never sees any API key: it only talks to /api/assistant. */
(function () {
  var log = document.getElementById('chat-log');
  var form = document.getElementById('chat-form');
  var input = document.getElementById('chat-input');
  var send = document.getElementById('chat-send');
  var token = document.querySelector('meta[name="csrf-token"]').content;
  var history = [];

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function scroll() { log.scrollTop = log.scrollHeight; }

  function addUser(text) {
    var m = el('div', 'msg msg-user'); m.appendChild(el('div', 'bubble', text)); log.appendChild(m); scroll();
  }

  function addBot(res) {
    var m = el('div', 'msg msg-bot');
    var b = el('div', 'bubble' + (res.ok ? '' : ' bubble-error'));
    b.appendChild(el('p', null, res.ok ? res.reply : res.error));

    if (res.ok && res.columns && res.columns.length) {
      var wrap = el('div', 'table-wrapper chat-table');
      var t = el('table'); var thead = el('thead'); var hr = el('tr');
      res.columns.forEach(function (c) { hr.appendChild(el('th', null, c.replace(/_/g, ' '))); });
      thead.appendChild(hr); t.appendChild(thead);
      var tb = el('tbody');
      if (!res.rows.length) { var er = el('tr', 'empty-row'); var ec = el('td', null, 'No rows returned.'); ec.colSpan = res.columns.length; er.appendChild(ec); tb.appendChild(er); }
      res.rows.forEach(function (r) {
        var tr = el('tr');
        r.forEach(function (v) { tr.appendChild(el('td', null, v == null ? '—' : v)); });
        tb.appendChild(tr);
      });
      t.appendChild(tb); wrap.appendChild(t); b.appendChild(wrap);
      if (res.truncated) b.appendChild(el('p', 'text-muted small', 'Showing the first ' + res.rows.length + ' rows.'));
    }
    if (res.sql) {
      var d = el('details', 'sql-details'); d.appendChild(el('summary', null, 'View generated SQL'));
      d.appendChild(el('pre', null, res.sql)); b.appendChild(d);
    }
    if (res.provider) b.appendChild(el('div', 'bubble-meta', 'Answered by ' + res.provider + ' · ' + res.model));
    m.appendChild(b); log.appendChild(m); scroll();
  }

  function ask(q) {
    q = (q || '').trim(); if (!q) return;
    addUser(q); input.value = ''; send.disabled = true;
    var typing = el('div', 'msg msg-bot'); typing.appendChild(el('div', 'bubble typing', 'Thinking…')); log.appendChild(typing); scroll();
    fetch('/api/assistant', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
      body: JSON.stringify({ question: q, history: history })
    }).then(function (r) { return r.json(); }).then(function (res) {
      typing.remove(); addBot(res);
      if (res.ok && res.sql) { history.push({ q: q, sql: res.sql }); history = history.slice(-3); }
    }).catch(function () {
      typing.remove(); addBot({ ok: false, error: 'Network error — please try again.' });
    }).then(function () { send.disabled = false; input.focus(); });
  }

  form.addEventListener('submit', function (e) { e.preventDefault(); ask(input.value); });
  document.querySelectorAll('.chip').forEach(function (c) { c.addEventListener('click', function () { ask(c.dataset.q); }); });
})();
