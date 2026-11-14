/* SC&WMS — AI assistant chat UI. The browser never sees any API key: it only talks to /api/assistant. */
(function () {
  var log = document.getElementById('chat-log');
  var form = document.getElementById('chat-form');
  var input = document.getElementById('chat-input');
  var send = document.getElementById('chat-send');
  var tokenEl = document.querySelector('meta[name="csrf-token"]');
  var token = tokenEl ? tokenEl.content : '';
  var history = [];

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function scroll() { if (log) log.scrollTop = log.scrollHeight; }

  function addUser(text) {
    if (!log) return;
    var m = el('div', 'msg msg-user'); m.appendChild(el('div', 'bubble', text)); log.appendChild(m); scroll();
  }

  function addBot(res) {
    if (!log) return;
    var m = el('div', 'msg msg-bot');
    var b = el('div', 'bubble' + (res && res.ok ? '' : ' bubble-error'));
    b.appendChild(el('p', null, (res && res.ok) ? res.reply : ((res && res.error) || 'An unexpected error occurred.')));

    if (res && res.ok && res.columns && res.columns.length) {
      var wrap = el('div', 'table-wrapper chat-table');
      var t = el('table'); var thead = el('thead'); var hr = el('tr');
      res.columns.forEach(function (c) { hr.appendChild(el('th', null, c.replace(/_/g, ' '))); });
      thead.appendChild(hr); t.appendChild(thead);
      var tb = el('tbody');
      if (!res.rows || !res.rows.length) {
        var er = el('tr', 'empty-row'); var ec = el('td', null, 'No rows returned.');
        ec.colSpan = res.columns.length; er.appendChild(ec); tb.appendChild(er);
      } else {
        res.rows.forEach(function (r) {
          var tr = el('tr');
          r.forEach(function (v) { tr.appendChild(el('td', null, v == null ? '—' : v)); });
          tb.appendChild(tr);
        });
      }
      t.appendChild(tb); wrap.appendChild(t); b.appendChild(wrap);
      if (res.truncated) b.appendChild(el('p', 'text-muted small', 'Showing the first ' + res.rows.length + ' rows.'));
    }
    if (res && res.sql) {
      var d = el('details', 'sql-details'); d.appendChild(el('summary', null, 'View generated SQL'));
      d.appendChild(el('pre', null, res.sql)); b.appendChild(d);
    }
    if (res && res.provider) b.appendChild(el('div', 'bubble-meta', 'Answered by ' + res.provider + ' · ' + (res.model || '')));
    m.appendChild(b); log.appendChild(m); scroll();
  }

  function ask(q) {
    q = (q || '').trim(); if (!q) return;
    addUser(q);
    if (input) input.value = '';
    if (send) send.disabled = true;
    var typing = el('div', 'msg msg-bot'); typing.appendChild(el('div', 'bubble typing', 'Thinking…'));
    if (log) { log.appendChild(typing); scroll(); }

    fetch('/api/assistant', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
      body: JSON.stringify({ question: q, history: history })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (typing) typing.remove();
      addBot(res);
      if (res && res.ok && res.sql) { history.push({ q: q, sql: res.sql }); history = history.slice(-3); }
    }).catch(function (err) {
      if (typing) typing.remove();
      addBot({ ok: false, error: 'Network or server error — please check your connection or AI configuration.' });
    }).then(function () {
      if (send) send.disabled = false;
      if (input) input.focus();
    });
  }

  if (form) {
    form.addEventListener('submit', function (e) { e.preventDefault(); if (input) ask(input.value); });
  }
  document.querySelectorAll('.chip').forEach(function (c) {
    c.addEventListener('click', function () { ask(c.dataset.q); });
  });
})();
