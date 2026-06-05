// Concerts app — shared between index.html (map view) and table.html.

const BL_TAG = {
  "Baden-Württemberg": "BW",
  "Bayern": "BY",
  "Hessen": "HE",
};

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

let VENUES = [];
let CONCERTS = [];

async function loadData() {
  const [v, c] = await Promise.all([
    fetch("../data/venues.json").then((r) => r.json()),
    fetch("../data/concerts.json").then((r) => r.json()),
  ]);
  VENUES = v;
  CONCERTS = (c.concerts || []).map(normalizeConcert);
}

function normalizeConcert(c) {
  // Date can come as YYYY-MM-DD. Derive year/month/day for filtering.
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(c.date || "");
  if (m) {
    c.year = +m[1];
    c.month = +m[2];
    c.day = +m[3];
  }
  // Ensure arrays exist
  c.performers = c.performers || [];
  c.program = c.program || [];
  return c;
}

function venueById(id) {
  return VENUES.find((v) => v.id === id);
}

function matchesFilters(c, f) {
  if (f.venue_id && c.venue_id !== f.venue_id) return false;
  if (f.month && c.month !== +f.month) return false;
  if (f.date && c.date !== f.date) return false;
  if (f.bundesland) {
    const v = venueById(c.venue_id);
    const bl = (v && v.bundesland) || c.bundesland || "";
    if (bl !== f.bundesland) return false;
  }
  if (f.city) {
    const v = venueById(c.venue_id);
    const city = (v && v.city) || c.city || "";
    if (city !== f.city) return false;
  }
  if (f.performer) {
    const t = f.performer.toLowerCase();
    if (!c.performers.some((p) => p.toLowerCase().includes(t))) return false;
  }
  if (f.composer) {
    const t = f.composer.toLowerCase();
    if (!c.program.some((p) => (p.composer || "").toLowerCase().includes(t))) return false;
  }
  if (f.work) {
    const t = f.work.toLowerCase();
    if (!c.program.some((p) => (p.work || "").toLowerCase().includes(t))) return false;
  }
  if (f.search) {
    const t = f.search.toLowerCase();
    const v = venueById(c.venue_id);
    const haystack = [
      c.title || "",
      c.ensemble || "",
      c.performers.join(" "),
      c.program.map((p) => `${p.composer || ""} ${p.work || ""}`).join(" "),
      v ? v.name + " " + v.city : c.venue || "",
      v ? v.city : c.city || "",
    ].join(" ").toLowerCase();
    if (!haystack.includes(t)) return false;
  }
  return true;
}

function uniqueCities() {
  const cities = new Set();
  for (const v of VENUES) if (v.city) cities.add(v.city);
  for (const c of CONCERTS) if (c.city) cities.add(c.city);
  return [...cities].sort();
}

function fillCommonControls(idPrefix = "") {
  const monthSel = document.getElementById("f-month");
  if (monthSel) {
    for (let i = 1; i <= 12; i++) {
      const opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = `${i.toString().padStart(2, "0")} – ${MONTH_NAMES[i - 1]}`;
      monthSel.appendChild(opt);
    }
  }
  const citySel = document.getElementById("f-city");
  if (citySel) {
    for (const city of uniqueCities()) {
      const opt = document.createElement("option");
      opt.value = city;
      opt.textContent = city;
      citySel.appendChild(opt);
    }
  }
}

function getFilters() {
  const f = {};
  for (const k of ["month", "date", "bundesland", "city", "performer", "composer", "work", "search"]) {
    const el = document.getElementById("f-" + k);
    if (el) f[k] = el.value.trim();
  }
  // venue_id comes from the URL only (set when the user clicks a map marker)
  const params = new URLSearchParams(window.location.search);
  const venueId = params.get("venue_id");
  if (venueId) f.venue_id = venueId;
  return f;
}

function anyFilterSet(f) {
  return Object.values(f).some((v) => v && v !== "");
}

// ===== Map view =====

let mapInstance = null;
let markerLayer = null;
let addressLayer = null;

function setupMap() {
  mapInstance = L.map("map").setView([49.2, 9.5], 7);  // centered on BW/Bayern/Hessen
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 18,
  }).addTo(mapInstance);
  markerLayer = L.layerGroup().addTo(mapInstance);
  addressLayer = L.layerGroup().addTo(mapInstance);
  wireAddressInput();
}

// --- Address geocoding + concentric radius circles ---

const RADII_KM = [50, 100, 150, 200];
const CIRCLE_COLORS = ["#5d3fd3", "#5d3fd3", "#5d3fd3", "#5d3fd3"];
let _addressDebounce = null;
let _lastAddressQuery = "";

function wireAddressInput() {
  const input = document.getElementById("f-address");
  if (!input) return;
  input.addEventListener("input", () => {
    clearTimeout(_addressDebounce);
    _addressDebounce = setTimeout(() => onAddressChanged(input.value.trim()), 500);
  });
  // Also clear on the "Clear all" button — already wired by clearAllAddressToo below
}

async function onAddressChanged(q) {
  const statusEl = document.getElementById("address-status");
  addressLayer.clearLayers();
  if (!q) {
    statusEl.textContent = "";
    _lastAddressQuery = "";
    return;
  }
  if (q === _lastAddressQuery) return;
  _lastAddressQuery = q;
  statusEl.textContent = "Looking up…";
  try {
    const params = new URLSearchParams({
      q, format: "json", limit: "1", countrycodes: "de,at,ch",
    });
    const resp = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, {
      headers: { "Accept-Language": "de,en" },
    });
    const hits = await resp.json();
    if (!hits.length) {
      statusEl.textContent = "Address not found";
      return;
    }
    const { lat, lon, display_name } = hits[0];
    statusEl.textContent = `📍 ${display_name.split(",").slice(0, 3).join(", ")}`;
    drawAddressOverlay(parseFloat(lat), parseFloat(lon));
  } catch (e) {
    statusEl.textContent = "Geocoding failed";
    console.error(e);
  }
}

function drawAddressOverlay(lat, lng) {
  // Pin at the address itself
  const pin = L.marker([lat, lng], {
    icon: L.divIcon({
      className: "",
      html: `<div style="background:#222;color:white;border-radius:50%;width:14px;height:14px;border:2px solid white;box-shadow:0 0 4px rgba(0,0,0,0.6)"></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    }),
  });
  addressLayer.addLayer(pin);

  RADII_KM.forEach((km, i) => {
    const opacity = 0.7 - i * 0.12;
    const fill = i === 0 ? 0.08 : 0.03;
    const circle = L.circle([lat, lng], {
      radius: km * 1000,
      color: CIRCLE_COLORS[i],
      weight: 1.5,
      opacity,
      fillColor: CIRCLE_COLORS[i],
      fillOpacity: fill,
      interactive: false,
    });
    addressLayer.addLayer(circle);
    // Label the radius at the north edge of each circle
    const labelLat = lat + km / 111;  // ~111 km per degree of latitude
    const label = L.marker([labelLat, lng], {
      icon: L.divIcon({
        className: "",
        html: `<div style="background:white;color:#5d3fd3;font-size:0.7rem;font-weight:700;padding:1px 6px;border:1px solid #5d3fd3;border-radius:3px;white-space:nowrap;transform:translateX(-50%)">${km} km</div>`,
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      }),
      interactive: false,
    });
    addressLayer.addLayer(label);
  });
  // Fit the largest circle in view
  mapInstance.fitBounds(L.latLng(lat, lng).toBounds(RADII_KM[RADII_KM.length - 1] * 2 * 1000));
}

function renderMap() {
  if (!mapInstance) setupMap();
  markerLayer.clearLayers();
  const f = getFilters();
  const hint = document.getElementById("hint");
  const stats = document.getElementById("stats");
  if (!anyFilterSet(f)) {
    hint.style.display = "block";
    stats.textContent = "No filter set — map is empty";
    return;
  }
  hint.style.display = "none";

  // Group matching concerts by venue
  const byVenue = new Map();
  for (const c of CONCERTS) {
    if (!matchesFilters(c, f)) continue;
    if (!byVenue.has(c.venue_id)) byVenue.set(c.venue_id, []);
    byVenue.get(c.venue_id).push(c);
  }

  let totalConcerts = 0;
  for (const [vid, concerts] of byVenue) {
    const v = venueById(vid);
    if (!v || v.lat == null) continue;
    totalConcerts += concerts.length;
    const icon = L.divIcon({
      className: "",
      html: `<div class="venue-marker">${concerts.length}</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    const m = L.marker([v.lat, v.lng], { icon, title: `${v.name} — ${concerts.length} concert${concerts.length === 1 ? "" : "s"} (click to view in table)` });
    m.on("click", () => {
      const params = new URLSearchParams({ venue_id: v.id });
      // Carry the active map filters into the table view too
      for (const [k, val] of Object.entries(f)) {
        if (val) params.set(k, val);
      }
      window.open(`table.html?${params.toString()}`, "_blank");
    });
    m.addTo(markerLayer);
  }
  const venueCount = byVenue.size;
  stats.textContent = venueCount === 0
    ? "No matching concerts for these filters"
    : `${totalConcerts} concert${totalConcerts === 1 ? "" : "s"} at ${venueCount} venue${venueCount === 1 ? "" : "s"}`;
}

function renderPopup(v, concerts) {
  const tag = BL_TAG[v.bundesland] || "";
  const venueHtml = v.website
    ? `<a href="${escape(v.website)}" target="_blank" rel="noopener">${escape(v.name)}</a>`
    : escape(v.name);
  const top = `
    <div class="popup-venue">${venueHtml}</div>
    <div class="popup-city">
      <span class="bl-tag ${tag}">${tag}</span>
      ${escape(v.city)}
    </div>`;
  if (concerts.length === 0) {
    return top + `<div class="popup-empty">No concerts loaded for this venue.</div>`;
  }
  const MAX_IN_POPUP = 5;
  const sorted = concerts.slice().sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  const overflow = sorted.length > MAX_IN_POPUP ? sorted.length - MAX_IN_POPUP : 0;
  const items = sorted
    .slice(0, MAX_IN_POPUP)
    .map((c) => `
      <div class="popup-concert">
        <span class="date">${escape(c.date || "?")}</span>
        ${c.time ? `<span style="color:var(--muted)"> · ${escape(c.time)}</span>` : ""}
        <span class="title"> ${escape(c.title || "")}</span>
        ${c.performers.length ? `<div>${escape(c.performers.join(", "))}</div>` : ""}
        ${c.program.length ? `<div class="program">${c.program.map((p) => escape(`${p.composer || ""}: ${p.work || ""}`)).join(" · ")}</div>` : ""}
        ${c.url ? `<a href="${escape(c.url)}" target="_blank" rel="noopener">Details ↗</a>` : ""}
      </div>`)
    .join("");
  const overflowHtml = overflow
    ? `<div class="popup-overflow">+ ${overflow} more concert${overflow === 1 ? "" : "s"} — see the <a href="table.html">table view</a></div>`
    : "";
  return top + `<div class="popup-concerts">${items}${overflowHtml}</div>`;
}

// ===== Table view =====

function renderTable() {
  const tbody = document.querySelector("#concerts-table tbody");
  const f = getFilters();
  const rows = CONCERTS.filter((c) => matchesFilters(c, f));
  rows.sort(sortBy(currentSort));
  const venueMap = Object.fromEntries(VENUES.map((v) => [v.id, v]));
  tbody.innerHTML = rows
    .map((c) => {
      const v = venueMap[c.venue_id] || {};
      const bundesland = v.bundesland || c.bundesland || "";
      const tag = BL_TAG[bundesland] || "";
      const city = v.city || c.city || "";
      const venueName = v.name || c.venue || "";
      const venueSite = v.website || "";
      const venueCell = venueSite
        ? `<a href="${escape(venueSite)}" target="_blank" rel="noopener">${escape(venueName)}</a>`
        : escape(venueName);
      const prog = c.program.map((p) => `${p.composer || ""}: ${p.work || ""}`).join("\n");
      return `<tr>
        <td>${escape(c.date || "")}${c.time ? "<br><small style='color:var(--muted)'>" + escape(c.time) + "</small>" : ""}</td>
        <td>${tag ? `<span class="bl-tag ${tag}">${tag}</span> ` : ""}${escape(bundesland)}</td>
        <td>${escape(city)}</td>
        <td>${venueCell}</td>
        <td>${escape(c.performers.join("; "))}</td>
        <td class="program">${escape(prog)}</td>
        <td>${c.url ? `<a href="${escape(c.url)}" target="_blank" rel="noopener">↗</a>` : ""}</td>
      </tr>`;
    })
    .join("");
  document.getElementById("hint").style.display = rows.length ? "none" : "block";
  document.getElementById("stats").textContent =
    `${rows.length} concert${rows.length === 1 ? "" : "s"} (of ${CONCERTS.length} total)`;
}

let currentSort = { key: "date", asc: true };
function sortBy({ key, asc }) {
  return (a, b) => {
    const va = (a[key] || "").toString().toLowerCase();
    const vb = (b[key] || "").toString().toLowerCase();
    return asc ? va.localeCompare(vb) : vb.localeCompare(va);
  };
}

// ===== Utils =====

function escape(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function wireFilters(onChange) {
  for (const id of ["f-month", "f-date", "f-bundesland", "f-city", "f-performer", "f-composer", "f-work", "f-search"]) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", onChange);
  }
  const clear = document.getElementById("clear-filters");
  if (clear) {
    clear.addEventListener("click", () => {
      for (const id of ["f-month", "f-date", "f-bundesland", "f-city", "f-performer", "f-composer", "f-work", "f-search", "f-address"]) {
        const el = document.getElementById(id);
        if (el) el.value = "";
      }
      // Also clear any address overlay drawn on the map
      if (typeof addressLayer !== "undefined" && addressLayer) {
        addressLayer.clearLayers();
        _lastAddressQuery = "";
        const s = document.getElementById("address-status");
        if (s) s.textContent = "";
      }
      onChange();
    });
  }
}

// ===== Venue banner (table page only) =====

function renderVenueBanner() {
  const banner = document.getElementById("venue-banner");
  if (!banner) return;
  const params = new URLSearchParams(window.location.search);
  const venueId = params.get("venue_id");
  if (!venueId) {
    banner.style.display = "none";
    return;
  }
  const v = venueById(venueId);
  if (!v) {
    banner.style.display = "none";
    return;
  }
  const baseUrl = window.location.pathname; // strip query
  banner.innerHTML =
    `<span>Filtered to <strong>${escape(v.name)}</strong> · ${escape(v.city)}</span>` +
    ` <a href="${baseUrl}" class="clear-link">show all concerts</a>`;
  banner.style.display = "flex";
}

// ===== Sticky-top measurement =====

function updateStickyTopHeight() {
  const el = document.querySelector(".sticky-top");
  if (!el) return;
  const h = el.getBoundingClientRect().height;
  document.documentElement.style.setProperty("--sticky-top-height", `${Math.ceil(h)}px`);
}

function watchStickyTop() {
  updateStickyTopHeight();
  if ("ResizeObserver" in window) {
    const ro = new ResizeObserver(() => updateStickyTopHeight());
    const el = document.querySelector(".sticky-top");
    if (el) ro.observe(el);
  }
  window.addEventListener("resize", updateStickyTopHeight);
}

// ===== Bootstrap =====

(async () => {
  await loadData();
  fillCommonControls();
  watchStickyTop();
  if (document.getElementById("map")) {
    setupMap();
    // Default to the current month so the map isn't empty on first load
    const monthSel = document.getElementById("f-month");
    if (monthSel && !monthSel.value) {
      monthSel.value = String(new Date().getMonth() + 1);
    }
    wireFilters(renderMap);
    renderMap();
  }
  if (document.getElementById("concerts-table")) {
    // Pre-fill visible filters from the URL (so a marker click can carry context)
    const params = new URLSearchParams(window.location.search);
    for (const k of ["month", "date", "bundesland", "city", "performer", "composer", "work", "search"]) {
      const v = params.get(k);
      const el = document.getElementById("f-" + k);
      if (v && el) el.value = v;
    }
    renderVenueBanner();
    document.querySelectorAll("th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        currentSort = { key, asc: currentSort.key === key ? !currentSort.asc : true };
        renderTable();
      });
    });
    wireFilters(renderTable);
    renderTable();
  }
})();
