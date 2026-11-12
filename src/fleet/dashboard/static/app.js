"use strict";
const SEVERITY = { 1: "warning", 2: "high", 3: "critical" };
const COLOR = { 1: "#e8b500", 2: "#f07800", 3: "#d92d20" };
const ROUTE_COLOR = ["#2e6bd6", "#7a4cc2", "#12805c", "#b5487a", "#8a6d00"];

const map = L.map("map", { preferCanvas: false }).setView([43.92, -78.86], 13);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: "© OpenStreetMap contributors",
}).addTo(map);

const state = { vehicles: {}, alerts: {}, markers: {}, dots: {}, showResolved: false };
const $ = (sel) => document.querySelector(sel);
const fmt = (v, digits = 0) => (v === null || v === undefined ? "–" : Number(v).toFixed(digits));

function drawRoutes(routes) {
  const bounds = [];
  routes.forEach((r, i) => {
    L.polyline(r.polyline, { color: ROUTE_COLOR[i % ROUTE_COLOR.length], weight: 4, opacity: 0.6, className: "route" })
      .bindTooltip(`${r.id}: ${r.name}`).addTo(map);
    bounds.push(...r.polyline);
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [20, 20] });
}

function openHazard(vid) {
  return Object.values(state.alerts).some((a) => a.vehicle_id === vid && a.kind === "hazard" && a.resolved_ms === null);
}

function updateVan(v) {
  state.vehicles[v.id] = v;
  if (v.lat === null || v.lat === undefined) return renderFleet();
  let m = state.markers[v.id];
  if (!m) {
    m = L.circleMarker([v.lat, v.lon], { radius: 9, weight: 3, fillOpacity: 0.95, className: "van" })
      .bindTooltip(v.name).addTo(map);
    state.markers[v.id] = m;
  }
  m.setLatLng([v.lat, v.lon]);
  styleVan(v.id);
  renderFleet();
}

function styleVan(vid) {
  const m = state.markers[vid], v = state.vehicles[vid];
  if (!m) return;
  const hazard = openHazard(vid);
  m.setStyle({
    color: !v.online ? "#98a2b3" : hazard ? "#d92d20" : "#1d2330",
    fillColor: !v.online ? "#d0d5dd" : "#ffffff",
  });
  const el = m.getElement();
  if (el) el.classList.toggle("van-pulse", hazard && v.online);
}

function renderFleet() {
  const rows = Object.values(state.vehicles).sort((a, b) => a.id.localeCompare(b.id)).map((v) => `
    <tr class="${v.online ? "" : "offline"}" data-vehicle="${v.id}">
      <td>${v.name}${v.online ? "" : " (offline)"}</td><td>${v.route_id}</td>
      <td>${fmt(v.speed_kmh)} km/h</td><td>${fmt(v.soc_pct, 1)}%</td>
      <td>${v.trip ?? "–"}</td><td>${fmt(v.odometer_km, 2)} km</td>
    </tr>`);
  $("#fleet tbody").innerHTML = rows.join("");
}

function updateAlert(a) {
  state.alerts[a.id] = a;
  if (a.kind === "hazard" && !state.dots[a.id]) {
    state.dots[a.id] = L.circleMarker([a.lat, a.lon], {
      radius: 5, weight: 1, color: COLOR[a.severity], fillColor: COLOR[a.severity], fillOpacity: 0.9,
      className: `hazard-dot sev-dot-${a.severity}`,
    }).bindTooltip(`${a.hazard_type} (${SEVERITY[a.severity]})`).addTo(map);
  }
  styleVan(a.vehicle_id);
  renderAlerts();
}

function renderAlerts() {
  const name = (vid) => state.vehicles[vid]?.name ?? vid;
  const items = Object.values(state.alerts)
    .filter((a) => state.showResolved || a.resolved_ms === null)
    .sort((a, b) => b.opened_ms - a.opened_ms)
    .map((a) => {
      const label = a.kind === "offline" ? "offline" : `${a.hazard_type.replace("_", " ")} · ${SEVERITY[a.severity]}`;
      const latency = a.kind === "hazard" ? `${a.t1_ms - a.t0_ms} ms` : "";
      const time = new Date(a.opened_ms).toLocaleTimeString();
      const ack = a.acked_ms ? "acked" : `<button data-ack="${a.id}">Ack</button>`;
      return `<li class="${a.resolved_ms ? "resolved" : ""}" data-alert="${a.id}">
        <span class="sev ${a.kind === "offline" ? "sev-offline" : `sev-${a.severity}`}"></span>
        <span>${name(a.vehicle_id)} · ${label}</span>
        <span class="meta">${time} ${latency}${a.resolved_ms ? " · resolved" : ""}</span>${ack}</li>`;
    });
  $("#alerts").innerHTML = items.join("") || "<li>No alerts</li>";
}

function renderLatency(l) {
  $("#latency").innerHTML = `
    <span>median <b>${fmt(l.median_ms)}</b> ms</span>
    <span>p95 <b>${fmt(l.p95_ms)}</b> ms</span>
    <span>max <b>${fmt(l.max_ms)}</b> ms</span>
    <span class="${l.count ? (l.pass ? "pass" : "fail") : ""}">${l.count ? (l.pass ? "PASS" : "FAIL") : "no data"} (n=${l.count})</span>`;
}

function renderRouteTable(rows) {
  $("#route-table tbody").innerHTML = rows.map((r) => `
    <tr class="${r.highest ? "highest" : ""}" data-route="${r.route_id}">
      <td>${r.route_id}: ${r.route_name}</td><td>${r.vehicle}</td><td>${r.trips}</td>
      <td>${fmt(r.km, 1)}</td><td>${fmt(r.kwh, 2)}</td><td>${fmt(r.kwh_per_100km, 1)}</td>
      <td>${r.hazards ?? "–"}</td><td>${fmt(r.hazards_per_100km, 1)}</td>
    </tr>`).join("");
}

async function applySnapshot(s) {
  if (s.routes) drawRoutes(s.routes);
  Object.values(s.vehicles).forEach(updateVan);
  s.alerts.forEach(updateAlert);
  renderLatency(s.latency);
  renderRouteTable(s.route_table);
  // Resolved alerts still get a map dot; the toggle only filters the queue.
  const all = await (await fetch("/api/snapshot?include_resolved=true")).json();
  all.alerts.forEach(updateAlert);
}

function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => { $("#conn").textContent = "live"; $("#conn").classList.add("live"); };
  ws.onclose = () => {
    $("#conn").textContent = "reconnecting…"; $("#conn").classList.remove("live");
    setTimeout(connect, 1000);
  };
  ws.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "snapshot") applySnapshot(ev);
    else if (ev.type === "vehicle") updateVan(ev.vehicle);
    else if (ev.type === "alert") updateAlert(ev.alert);
    else if (ev.type === "latency") renderLatency(ev.latency);
    else if (ev.type === "route_table") renderRouteTable(ev.rows);
  };
}

$("#alerts").addEventListener("click", async (e) => {
  const id = e.target.dataset.ack;
  if (id) await fetch(`/api/alerts/${id}/ack`, { method: "POST" });
});

$("#show-resolved").addEventListener("change", (e) => {
  state.showResolved = e.target.checked;
  renderAlerts();
});

connect();
