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
      c.performers.join(" "),
      c.program.map((p) => `${p.composer || ""} ${p.work || ""}`).join(" "),
      v ? v.name + " " + v.city : "",
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
  return f;
}

function anyFilterSet(f) {
  return Object.values(f).some((v) => v && v !== "");
}

// ===== Map view =====

let mapInstance = null;
let markerLayer = null;

function setupMap() {
  mapInstance = L.map("map").setView([49.2, 9.5], 7);  // centered on BW/Bayern/Hessen
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 18,
  }).addTo(mapInstance);
  markerLayer = L.layerGroup().addTo(mapInstance);
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
    const m = L.marker([v.lat, v.lng], { icon });
    m.bindPopup(renderPopup(v, concerts));
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
  const items = concerts
    .sort((a, b) => (a.date || "").localeCompare(b.date || ""))
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
  return top + `<div class="popup-concerts">${items}</div>`;
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
      for (const id of ["f-month", "f-date", "f-bundesland", "f-city", "f-performer", "f-composer", "f-work", "f-search"]) {
        const el = document.getElementById(id);
        if (el) el.value = "";
      }
      onChange();
    });
  }
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
    wireFilters(renderMap);
    renderMap();
  }
  if (document.getElementById("concerts-table")) {
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
