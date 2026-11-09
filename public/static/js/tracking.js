/* SC&WMS — shipment map tracking (Leaflet + OpenStreetMap, no API key needed) */
(function () {
  var COLORS = { 'In Transit': '#2563eb', 'Delivered': '#16a34a', 'Returned': '#d97706' };
  var PAKISTAN = [30.4, 69.3];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pin(cls, emoji) {
    return L.divIcon({ className: 'map-pin ' + cls, html: emoji, iconSize: [30, 30], iconAnchor: [15, 15] });
  }
  var ICON = { wh: pin('pin-wh', '🏭'), truck: pin('pin-truck', '🚚'), home: pin('pin-home', '📍'), done: pin('pin-done', '✅') };

  function baseMap(el) {
    var map = L.map(el, { scrollWheelZoom: false }).setView(PAKISTAN, 5);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    map.on('click', function () { map.scrollWheelZoom.enable(); });   // click the map to enable wheel-zoom
    return map;
  }

  /* ── overview map: all shipments (dashboard + shipments page) ── */
  function initOverview(el, data) {
    var map = baseMap(el), pts = [];
    (data.warehouses || []).forEach(function (w) {
      if (!w.p) return;
      L.marker(w.p, { icon: ICON.wh }).addTo(map).bindTooltip(esc(w.name));
      pts.push(w.p);
    });
    (data.shipments || []).forEach(function (s) {
      var c = COLORS[s.status] || '#64748b';
      if (s.origin && s.dest) {
        L.polyline([s.origin, s.dest], { color: c, weight: 2, opacity: .55, dashArray: '6 8' }).addTo(map);
      }
      if (s.dest) { L.marker(s.dest, { icon: s.status === 'Delivered' ? ICON.done : ICON.home }).addTo(map)
        .bindTooltip(esc(s.customer)); pts.push(s.dest); }
      if (s.status === 'In Transit' && s.current) {
        L.marker(s.current, { icon: ICON.truck }).addTo(map).bindPopup(
          '<b>' + esc(s.tracking) + '</b><br>' + esc(s.product) + ' × ' + esc(s.qty) +
          '<br>To: ' + esc(s.customer) + '<br>Last scan: ' + esc(s.last) +
          '<br><a href="' + esc(s.url) + '">Open live tracking →</a>');
        pts.push(s.current);
      }
    });
    if (pts.length) map.fitBounds(pts, { padding: [40, 40], maxZoom: 7 });
    setTimeout(function () { map.invalidateSize(); }, 200);
    return map;
  }

  /* ── single shipment: route, checkpoints, live position ── */
  function initTrack(el, t0, apiUrl) {
    var map = baseMap(el), layer = L.layerGroup().addTo(map), first = true;

    function draw(t) {
      layer.clearLayers();
      var pts = [];
      if (t.origin && t.dest) {
        L.polyline([t.origin, t.dest], { color: '#94a3b8', weight: 2, dashArray: '6 8' }).addTo(layer);
      }
      if (t.origin) { L.marker(t.origin, { icon: ICON.wh }).addTo(layer).bindTooltip(esc(t.origin_name || 'Origin')); pts.push(t.origin); }
      if (t.dest)   { L.marker(t.dest,   { icon: t.status === 'Delivered' ? ICON.done : ICON.home }).addTo(layer)
                        .bindTooltip(esc(t.customer + ' — ' + (t.address || ''))); pts.push(t.dest); }
      var path = (t.events || []).filter(function (e) { return e.p; });
      if (path.length > 1) {
        L.polyline(path.map(function (e) { return e.p; }), { color: '#2563eb', weight: 4, opacity: .9 }).addTo(layer);
      }
      path.forEach(function (e) {
        L.circleMarker(e.p, { radius: 5, color: '#1d4ed8', weight: 2, fillColor: '#fff', fillOpacity: 1 })
          .addTo(layer).bindPopup('<b>' + esc(e.type) + '</b><br>' + esc(e.location) + '<br>' + esc(e.time));
        pts.push(e.p);
      });
      if (t.status === 'In Transit' && t.current) {
        L.marker(t.current, { icon: ICON.truck, zIndexOffset: 1000 }).addTo(layer)
          .bindPopup('<b>' + esc(t.tracking_no) + '</b><br>Currently near the last scan');
      }
      if (first && pts.length) { map.fitBounds(pts, { padding: [50, 50], maxZoom: 8 }); first = false; }
    }

    function render(t) {
      draw(t);
      var set = function (id, html) { var n = document.getElementById(id); if (n) n.innerHTML = html; };
      var cls = { 'In Transit': 'badge-transit', 'Delivered': 'badge-delivered', 'Returned': 'badge-returned' }[t.status] || 'badge-secondary';
      set('t-status', '<span class="badge ' + cls + '">' + esc(t.status) + '</span>');
      set('t-progress-label', t.progress + '%');
      var bar = document.getElementById('t-progress-bar'); if (bar) bar.style.width = t.progress + '%';
      set('t-distance', t.distance_km != null ? esc(t.distance_km) + ' km' : '—');
      set('t-remaining', t.status === 'In Transit' ? esc(t.remaining_km) + ' km' : '—');
      set('t-eta', t.status === 'Delivered' ? 'Delivered' : (t.eta ? esc(t.eta) : '—'));
      var html = '';
      (t.events || []).slice().reverse().forEach(function (e, i) {
        html += '<li class="tl-item' + (i === 0 ? ' tl-latest' : '') + '"><span class="tl-dot"></span>' +
                '<div class="tl-type">' + esc(e.type) + '</div><div class="tl-loc">' + esc(e.location) + '</div>' +
                (e.note ? '<div class="tl-note">' + esc(e.note) + '</div>' : '') +
                '<div class="tl-time">' + esc(e.time) + '</div></li>';
      });
      set('t-timeline', html || '<li class="td-muted">No events yet.</li>');
    }

    render(t0);
    if (t0.status === 'In Transit' && apiUrl) {          // live refresh every 15 s
      var timer = setInterval(function () {
        fetch(apiUrl, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (j) {
          if (j.ok) { render(j.t); if (j.t.status !== 'In Transit') clearInterval(timer); }
        }).catch(function () {});
      }, 15000);
    }
    setTimeout(function () { map.invalidateSize(); }, 200);
    return map;
  }

  window.SCWMS = { initOverview: initOverview, initTrack: initTrack };
})();
