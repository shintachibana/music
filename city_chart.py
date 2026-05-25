"""Generate a Japan-map Performances-by-City page from a
Concerts_in_Japan.html source.

Usage:
    python3 city_chart.py bpo   # → "Berliner Philharmoniker/Performances_by_City.html"
    python3 city_chart.py wpo   # → "Wiener Philharmoniker/Performances_by_City.html"

Visualisation: bubble overlay + faint prefecture choropleth.
Prefecture polygons are tinted by total performances anywhere in the
prefecture; each city is drawn as a circle whose area is proportional
to its own count, with a hover tooltip listing the works performed
there. The Japan GeoJSON is fetched at page load from a CDN.
"""
import json
import re
import sys


# city → (latitude, longitude, prefecture_nam)
# prefecture_nam matches the "nam" property in dataofjapan's Japan
# GeoJSON (romaji, capitalised, no macron, no "-prefecture" suffix).
CITY_GEO = {
    "Tokyo":       (35.6762, 139.6503, "Tokyo"),
    "Osaka":       (34.6937, 135.5023, "Osaka"),
    "Nagoya":      (35.1815, 136.9066, "Aichi"),
    "Kawasaki":    (35.5308, 139.7029, "Kanagawa"),
    "Kawaguchiko": (35.4960, 138.7637, "Yamanashi"),
    "Yokohama":    (35.4437, 139.6380, "Kanagawa"),
    "Fukuoka":     (33.5904, 130.4017, "Fukuoka"),
    "Okayama":     (34.6551, 133.9195, "Okayama"),
    "Hiroshima":   (34.3853, 132.4553, "Hiroshima"),
    "Sendai":      (38.2682, 140.8694, "Miyagi"),
    "Takarazuka":  (34.8059, 135.3597, "Hyogo"),
    "Sapporo":     (43.0686, 141.3506, "Hokkaido"),
    "Kanazawa":    (36.5616, 136.6566, "Ishikawa"),
    "Takamatsu":   (34.3429, 134.0466, "Kagawa"),
    "Hyogo":       (34.7373, 135.3409, "Hyogo"),     # Hyogo Performing Arts Center, Nishinomiya
    "Yahata":      (33.8588, 130.7146, "Fukuoka"),   # Kitakyushu
    "Kobe":        (34.6901, 135.1955, "Hyogo"),
    "Matsuyama":   (33.8392, 132.7659, "Ehime"),
    "Himeji":      (34.8167, 134.6867, "Hyogo"),
    # WPO-specific cities (reuse the same script for WPO)
    "Otsu":        (35.0044, 135.8686, "Shiga"),
    "Niigata":     (37.9026, 139.0235, "Niigata"),
    "Nagano":      (36.6485, 138.1949, "Nagano"),
    "Matsudo":     (35.7878, 139.9032, "Chiba"),
    "Tsu":         (34.7185, 136.5057, "Mie"),
    "Toyota":      (35.0834, 137.1564, "Aichi"),
    "Toyama":      (36.6953, 137.2113, "Toyama"),
    "Shizuoka":    (34.9756, 138.3829, "Shizuoka"),
    "Kurashiki":   (34.5851, 133.7720, "Okayama"),
    "Kumamoto":    (32.8031, 130.7079, "Kumamoto"),
    "Kagoshima":   (31.5969, 130.5571, "Kagoshima"),
    "Kurume":      (33.3122, 130.5083, "Fukuoka"),
    "Nishinomiya": (34.7373, 135.3409, "Hyogo"),
    "Miyazaki":    (31.9077, 131.4202, "Miyazaki"),
    "Koriyama":    (37.4002, 140.3597, "Fukushima"),
    "Saitama":     (35.8617, 139.6455, "Saitama"),
    "Hamamatsu":   (34.7108, 137.7261, "Shizuoka"),
    "Yamagata":    (38.2404, 140.3633, "Yamagata"),
    "Kanagawa":    (35.4437, 139.6380, "Kanagawa"),
    "Sakai":       (34.5733, 135.4830, "Osaka"),
    "Kawaguchi":   (35.8079, 139.7244, "Saitama"),
    "Kyoto":       (35.0116, 135.7681, "Kyoto"),
    "Aomori":      (40.8246, 140.7406, "Aomori"),
    "Akita":       (39.7186, 140.1024, "Akita"),
}


# Tags allowed inside work names — preserve <em>...</em> so titles like
# Oberon, Eroica, Pastorale stay italicised in the tooltip.
def strip_tags_keep_em(s: str) -> str:
    s = re.sub(r"</?a\b[^>]*>", "", s)
    s = re.sub(r"<(?!/?em\b)[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


PLACEHOLDER_TOKENS = (
    "to be researched", "not documented",
    "various programs", "program details", "program not",
    "three concerts", "three programs",
    "brahms symphonies and", "german/austrian core",
    "dance selections",
)

def is_placeholder(w: str) -> bool:
    low = w.lower()
    return any(tok in low for tok in PLACEHOLDER_TOKENS)


def parse_program(prog_html: str) -> list[str]:
    lines = re.split(r"<br\s*/?>", prog_html)
    out = []
    current_composer = None
    for raw in lines:
        text = strip_tags_keep_em(raw)
        if not text:
            continue
        plain = re.sub(r"</?em\b[^>]*>", "", text)
        m = re.match(r"^([^\W\d_][^:\d\n]{0,40}?):\s+(.+)$", plain)
        if m and m.group(1)[0].isupper() and len(m.group(1)) < 45:
            current_composer = m.group(1).strip()
            out.append(text)
        else:
            if current_composer:
                out.append(f"{current_composer}: {text}")
            else:
                out.append(text)
    return out


def aggregate(concerts_html: str):
    """Walk every row → per-city {total, works:{w:n}}."""
    m = re.search(r"<tbody>(.*?)</tbody>", concerts_html, re.DOTALL)
    if not m:
        return {}
    tbody = m.group(1)

    cities: dict[str, dict] = {}
    for row in re.findall(r"<tr>.*?</tr>", tbody, re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 5:
            continue
        venue_t = strip_tags(tds[2]).strip()
        city = re.split(r"\(", venue_t, 1)[0].strip()
        if not city:
            continue

        works = parse_program(tds[4])
        works = [w for w in works if not is_placeholder(w)]

        slot = cities.setdefault(city, {"total": 0, "works": {}, "venues": set()})
        slot["venues"].add(venue_t)
        for w in works:
            slot["works"][w] = slot["works"].get(w, 0) + 1
            slot["total"] += 1

    return cities


def build_page(orchestra: str, cities: dict) -> str:
    if orchestra == "bpo":
        title       = "Berliner Philharmoniker — Performances by City"
        bgcol       = "#FFF8EC"
        accent      = "#D97706"
        accent_d    = "#B45309"
        accent_rgba = "rgba(180,83,9,0.25)"
        notes_color = "%23D97706"
        bubble_fill = "#D97706"
        choro_a     = "#FEF6E2"  # lightest
        choro_b     = "#B45309"  # darkest
    else:
        title       = "Wiener Philharmoniker — Performances by City"
        bgcol       = "#FBF1F4"
        accent      = "#9F1239"
        accent_d    = "#831234"
        accent_rgba = "rgba(159,18,57,0.25)"
        notes_color = "%239F1239"
        bubble_fill = "#9F1239"
        choro_a     = "#FAEBEF"
        choro_b     = "#831234"

    # Build the data array.
    city_data = []
    pref_totals: dict[str, int] = {}
    for city, info in sorted(cities.items(), key=lambda x: -x[1]["total"]):
        geo = CITY_GEO.get(city)
        if not geo:
            print(f"  (no coords mapped for: {city})", file=sys.stderr)
            continue
        lat, lng, pref = geo
        works_sorted = sorted(info["works"].items(), key=lambda x: (-x[1], x[0]))
        city_data.append({
            "name":   city,
            "lat":    lat,
            "lng":    lng,
            "pref":   pref,
            "total":  info["total"],
            "venues": sorted(info["venues"]),
            "works":  works_sorted,
        })
        pref_totals[pref] = pref_totals.get(pref, 0) + info["total"]

    cities_json = json.dumps(city_data, ensure_ascii=False)
    pref_json   = json.dumps(pref_totals, ensure_ascii=False)
    total_perf  = sum(info["total"] for info in cities.values())
    total_cities = len(city_data)

    music_svg = (
        "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' "
        "width='220' height='220'%3E%3Cg font-family='Georgia,serif'%3E"
        f"%3Ctext x='15' y='48' font-size='38' transform='rotate(-12 30 38)' fill='{notes_color}' fill-opacity='0.16'%3E♫%3C/text%3E"
        "%3Ctext x='120' y='30' font-size='26' fill='%230F766E' fill-opacity='0.15'%3E♪%3C/text%3E"
        f"%3Ctext x='175' y='95' font-size='32' transform='rotate(15 188 80)' fill='{notes_color}' fill-opacity='0.16'%3E♬%3C/text%3E"
        "%3Ctext x='45' y='125' font-size='30' fill='%239F1239' fill-opacity='0.14'%3E♩%3C/text%3E"
        "%3Ctext x='135' y='165' font-size='28' transform='rotate(-8 148 155)' fill='%230F766E' fill-opacity='0.15'%3E♫%3C/text%3E"
        f"%3Ctext x='80' y='195' font-size='34' fill='{notes_color}' fill-opacity='0.16'%3E♬%3C/text%3E"
        "%3Ctext x='195' y='185' font-size='22' fill='%239F1239' fill-opacity='0.14'%3E♪%3C/text%3E"
        "%3C/g%3E%3C/svg%3E"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; }}
body {{
  font-family: Arial, sans-serif;
  font-size: 13px;
  margin: 0;
  padding: 24px 20px;
  color: #222;
  background-color: {bgcol};
  background-image: url("{music_svg}");
  background-repeat: repeat;
}}
.page-header {{
  position: sticky;
  top: 0;
  z-index: 5;
  background-color: {bgcol};
  margin: 0 -20px 20px;
  padding: 12px 20px 14px;
  box-shadow: 0 2px 0 {bgcol};
}}
h1 {{
  font-size: 20px;
  margin: 0;
  padding: 0 0 6px;
  text-align: center;
  color: #000;
}}
.subhead {{
  text-align: center;
  font-size: 13px;
  color: #555;
  margin: 0;
  padding: 0 0 10px;
}}
.toolbar {{
  text-align: center;
  margin: 0;
  padding: 0;
}}
.toolbar a {{
  display: inline-block;
  padding: 6px 14px;
  font-size: 13px;
  text-decoration: none;
  border-radius: 4px;
  margin: 0 4px;
  color: #fff;
  background: {accent};
  box-shadow: 0 1px 3px {accent_rgba};
}}
.toolbar a:hover {{ background: {accent_d}; }}

#chart-wrap {{
  max-width: 1140px;
  margin: 0 auto;
}}
#chart {{
  width: 100%;
  aspect-ratio: 4 / 5;
  border: 2px solid {accent};
  border-radius: 8px;
  background: rgba(255,255,255,0.55);
  box-shadow: 0 2px 14px rgba(0,0,0,0.10);
  position: relative;
}}
#chart svg {{
  width: 100%;
  height: 100%;
  display: block;
}}
.prefecture {{
  stroke: rgba(120,120,120,0.55);
  stroke-width: 0.5;
  transition: fill 0.2s ease;
}}
.bubble {{
  fill: {bubble_fill};
  fill-opacity: 0.78;
  stroke: #fff;
  stroke-width: 1.5;
  cursor: default;
  transition: stroke-width 0.15s ease, filter 0.15s ease;
}}
.bubble:hover {{
  stroke-width: 2.5;
  filter: drop-shadow(0 3px 8px rgba(0,0,0,0.4));
}}
.city-label {{
  pointer-events: none;
  text-anchor: middle;
  fill: #1c1917;
  font-family: Arial, sans-serif;
  font-size: 10px;
  font-weight: 600;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.92);
  stroke-width: 3px;
  stroke-linejoin: round;
}}
.city-count {{
  pointer-events: none;
  text-anchor: middle;
  fill: #fff;
  font-family: Arial, sans-serif;
  font-weight: 800;
  text-shadow: 0 1px 2px rgba(0,0,0,0.85);
}}

/* Legend */
.legend {{
  display: flex;
  justify-content: center;
  gap: 22px;
  margin-top: 10px;
  font-size: 12px;
  color: #555;
}}
.legend-item {{ display: flex; align-items: center; gap: 6px; }}
.legend-swatch {{
  width: 90px;
  height: 12px;
  border-radius: 3px;
  background: linear-gradient(to right, {choro_a}, {choro_b});
  border: 1px solid rgba(0,0,0,0.18);
}}
.legend-bubbles {{ display: flex; align-items: flex-end; gap: 4px; }}
.legend-bubble {{
  display: inline-block;
  border-radius: 50%;
  background: {bubble_fill};
  border: 1.5px solid #fff;
  box-shadow: 0 0 0 1px rgba(0,0,0,0.25);
}}

/* Tooltip */
#tooltip {{
  position: fixed;
  z-index: 100;
  background: #fff;
  border-radius: 6px;
  box-shadow: 0 6px 22px rgba(0,0,0,0.32);
  padding: 12px 14px 10px;
  width: 440px;
  max-height: 70vh;
  overflow-y: auto;
  font-size: 12.5px;
  line-height: 1.45;
  color: #222;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.12s ease;
}}
#tooltip.visible {{ opacity: 1; }}
#tooltip h3 {{
  margin: 0 0 6px;
  padding: 0 0 6px;
  border-bottom: 2px solid {accent};
  font-size: 14px;
  font-weight: 700;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}}
#tooltip h3 .city-total {{
  color: {accent};
  font-size: 18px;
}}
#tooltip .venues {{
  font-size: 11.5px;
  color: #666;
  margin: 0 0 6px;
}}
#tooltip ul {{
  margin: 0;
  padding: 0;
  list-style: none;
}}
#tooltip li {{
  margin: 1px 0;
  display: flex;
  align-items: baseline;
  gap: 6px;
}}
#tooltip .work-rank {{
  flex: 0 0 auto;
  min-width: 1.8em;
  text-align: right;
  color: #888;
  font-variant-numeric: tabular-nums;
}}
#tooltip .work-title {{
  flex: 1 1 auto;
  min-width: 0;
}}
#tooltip .work-count {{
  flex: 0 0 auto;
  font-weight: 700;
  color: {accent_d};
  font-variant-numeric: tabular-nums;
}}

.footnote {{
  max-width: 800px;
  margin: 26px auto 0;
  text-align: center;
  font-size: 12px;
  color: #777;
  line-height: 1.6;
}}
</style>
</head>
<body>
<div class="page-header">
<h1>{title}</h1>
<p class="subhead">{total_cities} cities · {total_perf} performances on the orchestra's documented Japan tours. Prefecture fill encodes that prefecture's total; each bubble's area is proportional to that city's count. Hover a bubble for the full work list.</p>
<p class="toolbar">
  <a href="Concerts_in_Japan.html">Concerts in Japan →</a>
  <a href="Program_Ranking.html">Program Ranking →</a>
  <a href="Composer_Chart.html">Performances by Composer →</a>
  <a href="Performances_by_Conductor.html">Performances by Conductor →</a>
  <a href="index.html">Home</a>
</p>
</div>

<div id="chart-wrap">
  <div id="chart"></div>
  <div class="legend">
    <span class="legend-item"><span>Prefecture total:</span><span class="legend-swatch"></span><span>low → high</span></span>
    <span class="legend-item">
      <span>City count:</span>
      <span class="legend-bubbles">
        <span class="legend-bubble" style="width:6px;height:6px;"></span>
        <span class="legend-bubble" style="width:11px;height:11px;"></span>
        <span class="legend-bubble" style="width:17px;height:17px;"></span>
        <span class="legend-bubble" style="width:24px;height:24px;"></span>
      </span>
    </span>
  </div>
</div>

<div id="tooltip" role="tooltip"></div>

<p class="footnote">
Map data © <a href="https://github.com/dataofjapan/land" target="_blank" rel="noopener">dataofjapan/land</a> (Japan prefecture boundaries).
Hover any city's bubble for the full list of works performed in that city by the orchestra.
</p>

<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const cities = {cities_json};
const prefTotals = {pref_json};

const tooltipEl = document.getElementById('tooltip');

function showTooltip(c, evt) {{
  const works = c.works || [];
  let prevCount = null, prevRank = 0;
  const items = works.map(([w, n], i) => {{
    let rank;
    if (n === prevCount) {{ rank = prevRank; }}
    else                  {{ rank = i + 1; prevCount = n; prevRank = rank; }}
    return `<li><span class="work-rank">${{rank}}.</span><span class="work-title">${{w}}</span><span class="work-count">${{n}}</span></li>`;
  }}).join('');
  const venues = (c.venues || []).map(v => v.replace(/^[^(]*\\(?/, '').replace(/\\)$/, '')).filter(Boolean);
  const venuesLine = venues.length ? `<p class="venues">${{venues.join(' · ')}}</p>` : '';
  tooltipEl.innerHTML = `
    <h3>${{c.name}}<span class="city-total">${{c.total}}</span></h3>
    ${{venuesLine}}
    <ul>${{items || '<li><em>(no works recorded)</em></li>'}}</ul>`;
  moveTooltip(evt);
  tooltipEl.classList.add('visible');
}}
function hideTooltip() {{ tooltipEl.classList.remove('visible'); }}
function moveTooltip(evt) {{
  const pad = 14;
  const ttW = tooltipEl.offsetWidth, ttH = tooltipEl.offsetHeight;
  const vW = window.innerWidth, vH = window.innerHeight;
  let x = evt.clientX + pad;
  let y = evt.clientY + pad;
  if (x + ttW > vW - 8) x = evt.clientX - ttW - pad;
  if (y + ttH > vH - 8) y = evt.clientY - ttH - pad;
  if (x < 8) x = 8;
  if (y < 8) y = 8;
  tooltipEl.style.left = x + 'px';
  tooltipEl.style.top  = y + 'px';
}}

const GEOJSON_URL = "https://cdn.jsdelivr.net/gh/dataofjapan/land@master/japan.geojson";

let geoData = null;
function loadGeo() {{
  return fetch(GEOJSON_URL).then(r => r.json()).then(j => {{ geoData = j; return j; }});
}}

function render() {{
  if (!geoData) return;
  const wrap = document.getElementById('chart');
  wrap.innerHTML = '';
  const W = wrap.clientWidth;
  const H = wrap.clientHeight;

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${{W}} ${{H}}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');

  // Fit Japan's mainland into the box
  const projection = d3.geoMercator().fitSize([W, H * 0.98], geoData);
  const path = d3.geoPath(projection);

  const maxPref = Math.max(1, ...Object.values(prefTotals));
  const colorScale = d3.scaleSequential()
    .domain([0, maxPref])
    .interpolator(d3.interpolateRgb("{choro_a}", "{choro_b}"));

  // Prefectures
  const gP = document.createElementNS(svgNS, 'g');
  gP.setAttribute('class', 'prefectures');
  function normPref(nam) {{
    // dataofjapan/land uses "Tokyo To", "Osaka Fu", "Kyoto Fu",
    // "Hokkai Do", "Hyogo Ken", etc. Strip the administrative suffix
    // so the choropleth lookup keys match our bare-name prefecture map.
    if (nam === "Hokkai Do") return "Hokkaido";
    return nam.replace(/ (Ken|Fu|To)$/, '');
  }}

  geoData.features.forEach(f => {{
    const namRaw = f.properties.nam || f.properties.NAME_1 || f.properties.name || '';
    const nam = normPref(namRaw);
    const count = prefTotals[nam] || 0;
    const p = document.createElementNS(svgNS, 'path');
    p.setAttribute('class', 'prefecture');
    p.setAttribute('d', path(f));
    p.setAttribute('fill', colorScale(count));
    gP.appendChild(p);
  }});
  svg.appendChild(gP);

  // Bubbles
  const maxCity = Math.max(1, ...cities.map(c => c.total));
  // Radius scale: sqrt area → linear count, clamp min and max for legibility
  const rMin = 4, rMax = 36;
  function radius(n) {{
    return rMin + (rMax - rMin) * Math.sqrt(n / maxCity);
  }}
  const gB = document.createElementNS(svgNS, 'g');
  gB.setAttribute('class', 'bubbles');

  // Sort largest first for label drawing (smaller cities labelled on top so
  // tiny cities aren't hidden by big bubbles).
  const sortedCities = cities.slice().sort((a, b) => b.total - a.total);
  sortedCities.forEach(c => {{
    const xy = projection([c.lng, c.lat]);
    if (!xy) return;
    const [x, y] = xy;
    const r = radius(c.total);

    const circ = document.createElementNS(svgNS, 'circle');
    circ.setAttribute('class', 'bubble');
    circ.setAttribute('cx', x);
    circ.setAttribute('cy', y);
    circ.setAttribute('r', r);
    circ.addEventListener('mouseenter', (evt) => showTooltip(c, evt));
    circ.addEventListener('mousemove',  moveTooltip);
    circ.addEventListener('mouseleave', hideTooltip);
    gB.appendChild(circ);

    // Count on top of bubble (only if big enough)
    if (r >= 13) {{
      const t = document.createElementNS(svgNS, 'text');
      t.setAttribute('class', 'city-count');
      t.setAttribute('x', x);
      t.setAttribute('y', y + r * 0.4);
      t.setAttribute('font-size', Math.max(10, Math.min(22, r * 0.95)));
      t.textContent = c.total;
      gB.appendChild(t);
    }}

    // City name below bubble
    const lbl = document.createElementNS(svgNS, 'text');
    lbl.setAttribute('class', 'city-label');
    lbl.setAttribute('x', x);
    lbl.setAttribute('y', y + r + 11);
    lbl.textContent = c.name;
    gB.appendChild(lbl);
  }});
  svg.appendChild(gB);

  wrap.appendChild(svg);
}}

loadGeo().then(render);
window.addEventListener('resize', () => {{
  clearTimeout(window._chartResizeTimer);
  window._chartResizeTimer = setTimeout(render, 100);
}});
</script>
</body>
</html>
"""


def main():
    orchestra = sys.argv[1].lower() if len(sys.argv) > 1 else "bpo"
    if orchestra == "bpo":
        in_path  = "Berliner Philharmoniker/Concerts_in_Japan.html"
        out_path = "Berliner Philharmoniker/Performances_by_City.html"
    elif orchestra == "wpo":
        in_path  = "Wiener Philharmoniker/Concerts_in_Japan.html"
        out_path = "Wiener Philharmoniker/Performances_by_City.html"
    else:
        print(f"Unknown orchestra '{orchestra}'. Use 'bpo' or 'wpo'.", file=sys.stderr)
        sys.exit(1)

    with open(in_path, encoding="utf-8") as f:
        html = f.read()
    cities = aggregate(html)

    page = build_page(orchestra, cities)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Wrote {out_path}")
    n_total = sum(info["total"] for info in cities.values())
    print(f"  {len(cities)} cities, {n_total} total performances")


if __name__ == "__main__":
    main()
