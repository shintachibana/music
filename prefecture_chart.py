"""Generate a Japan-map Performances-by-Prefecture page from a
Concerts_in_Japan.html source.

Usage:
    python3 prefecture_chart.py bpo
    python3 prefecture_chart.py wpo

Visualisation: faint prefecture choropleth + proportional bubble at
each prefecture's centroid. Hover any prefecture for a tooltip
listing the contributing cities (with their sub-totals) and every
work performed in the prefecture.

The southern islands (Okinawa) are drawn in a small inset in the
upper-right corner; the main map of Honshū/Hokkaidō/Shikoku/Kyūshū
is fitted to the full canvas so it appears ~120% larger than the
"all 47 prefectures together" projection would yield.
"""
import json
import re
import sys


# city → (latitude, longitude, prefecture_nam)
# prefecture_nam is the short romaji prefecture key. The GeoJSON uses
# longer forms ("Tokyo To", "Osaka Fu", "Hokkai Do", "Hyogo Ken" …)
# which are normalised in JS via normPref().
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
    "Hyogo":       (34.7373, 135.3409, "Hyogo"),
    "Yahata":      (33.8588, 130.7146, "Fukuoka"),
    "Kobe":        (34.6901, 135.1955, "Hyogo"),
    "Matsuyama":   (33.8392, 132.7659, "Ehime"),
    "Himeji":      (34.8167, 134.6867, "Hyogo"),
    # WPO + general repertoire
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
    "Sakai":       (34.5733, 135.4830, "Osaka"),
    "Kawaguchi":   (35.8079, 139.7244, "Saitama"),
    "Kyoto":       (35.0116, 135.7681, "Kyoto"),
    "Aomori":      (40.8246, 140.7406, "Aomori"),
    "Akita":       (39.7186, 140.1024, "Akita"),
    "Chiba":       (35.6074, 140.1065, "Chiba"),
    "Fukui":       (36.0652, 136.2216, "Fukui"),
    "Kitakyushu":  (33.8839, 130.8757, "Fukuoka"),
    "Maebashi":    (36.3895, 139.0634, "Gunma"),
    "Morioka":     (39.7036, 141.1527, "Iwate"),
}


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
    """Walk every row → per-prefecture {total, cities:{c:n}, works:{w:n}}."""
    m = re.search(r"<tbody>(.*?)</tbody>", concerts_html, re.DOTALL)
    if not m:
        return {}
    tbody = m.group(1)

    prefectures: dict[str, dict] = {}
    unknown_cities = set()
    for row in re.findall(r"<tr>.*?</tr>", tbody, re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 5:
            continue
        venue_t = strip_tags(tds[2]).strip()
        city = re.split(r"\(", venue_t, 1)[0].strip()
        if not city:
            continue
        geo = CITY_GEO.get(city)
        if not geo:
            unknown_cities.add(city)
            continue
        _, _, pref = geo

        works = parse_program(tds[4])
        works = [w for w in works if not is_placeholder(w)]

        slot = prefectures.setdefault(pref, {"total": 0, "cities": {}, "works": {}})
        slot["cities"][city] = slot["cities"].get(city, 0) + len(works)
        for w in works:
            slot["works"][w] = slot["works"].get(w, 0) + 1
            slot["total"] += 1

    if unknown_cities:
        print(f"  (no coords mapped for: {sorted(unknown_cities)})", file=sys.stderr)
    return prefectures


def build_page(orchestra: str, prefectures: dict) -> str:
    if orchestra == "bpo":
        title       = "Berliner Philharmoniker — Performances by Prefecture"
        bgcol       = "#FFF8EC"
        accent      = "#D97706"
        accent_d    = "#B45309"
        accent_rgba = "rgba(180,83,9,0.25)"
        notes_color = "%23D97706"
        bubble_fill = "#D97706"
        choro_a     = "#FEF6E2"
        choro_b     = "#B45309"
        extra_nav   = ('<a href="Program_Trend_by_Era.html">Program Trend by Era</a>\n  '
                       '<a href="Audience_Analysis.html">Audience Statistics</a>\n  ')
        concerts_href = "Performances_in_Japan.html"
    else:
        title       = "Wiener Philharmoniker — Performances by Prefecture"
        bgcol       = "#FBF1F4"
        accent      = "#9F1239"
        accent_d    = "#831234"
        accent_rgba = "rgba(159,18,57,0.25)"
        notes_color = "%239F1239"
        bubble_fill = "#9F1239"
        choro_a     = "#FAEBEF"
        choro_b     = "#831234"
        extra_nav   = '<a href="Program_Trend_by_Era.html">Program Trend by Era</a>\n  '
        concerts_href = "Performances_in_Japan.html"

    rows = []
    for pref, info in sorted(prefectures.items(), key=lambda x: -x[1]["total"]):
        rows.append({
            "name":   pref,
            "total":  info["total"],
            "cities": sorted(info["cities"].items(), key=lambda x: (-x[1], x[0])),
            "works":  sorted(info["works"].items(), key=lambda x: (-x[1], x[0])),
        })

    data_json   = json.dumps(rows, ensure_ascii=False)
    total_perf  = sum(p["total"] for p in prefectures.values())
    total_pref  = len(prefectures)

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
  max-width: 900px;
  aspect-ratio: 1 / 1;
  margin: 0 auto;
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
  transition: fill 0.2s ease, stroke 0.15s ease, stroke-width 0.15s ease;
}}
.prefecture.has-data {{
  cursor: default;
}}
.prefecture.has-data:hover {{
  stroke: #1c1917;
  stroke-width: 1.4;
}}
.pref-label {{
  pointer-events: none;
  text-anchor: middle;
  font-family: Arial, sans-serif;
  font-weight: 700;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.85);
  stroke-width: 3px;
  stroke-linejoin: round;
}}
/* Counter on each prefecture bubble — share typography with the
   adjacent .pref-label so the two reads as one matched pair instead
   of a heavier numeric atop a regular-weight name. */
.pref-count {{
  pointer-events: none;
  text-anchor: middle;
  font-family: Arial, sans-serif;
  font-weight: 700;
  paint-order: stroke;
  stroke-width: 3.5px;
  stroke-linejoin: round;
}}

.inset-frame {{
  fill: none;
  stroke: rgba(0,0,0,0.30);
  stroke-width: 1;
  stroke-dasharray: 4 3;
}}
.inset-label {{
  font-family: Arial, sans-serif;
  font-size: 10px;
  font-weight: 700;
  fill: #555;
  text-anchor: start;
}}

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

#tooltip {{
  position: fixed;
  z-index: 100;
  background: #fff;
  border-radius: 6px;
  box-shadow: 0 6px 22px rgba(0,0,0,0.32);
  padding: 12px 14px 10px;
  width: 460px;
  max-height: 96vh;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.25;
  color: #222;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.12s ease;
}}
#tooltip.wide   {{ width: 720px; }}
#tooltip.wider  {{ width: 920px; }}
#tooltip.widest {{ width: min(1180px, 96vw); font-size: 11.5px; }}
#tooltip.wide   ul {{ column-count: 2; column-gap: 14px; }}
#tooltip.wider  ul {{ column-count: 3; column-gap: 14px; }}
#tooltip.widest ul {{ column-count: 4; column-gap: 14px; }}
#tooltip ul li {{ break-inside: avoid; margin: 0; }}
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
#tooltip h3 .pref-total {{
  color: {accent};
  font-size: 18px;
}}
#tooltip .cities {{
  font-size: 11.5px;
  color: #666;
  margin: 0 0 8px;
  padding: 0 0 6px;
  border-bottom: 1px dashed rgba(0,0,0,0.10);
}}
#tooltip .cities b {{ color: #333; }}
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
#tooltip .work-title.staged-opera {{
  color: {accent_d};
  font-weight: 600;
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
<p class="subhead">{total_pref} prefectures · {total_perf} performances on the orchestra's documented Japan tours. Each prefecture is filled by its total; the bubble at the centroid is sized by the same total. Hover any prefecture for the work list &amp; contributing cities.</p>
<p class="toolbar">
  <a href="{concerts_href}">Performances in Japan</a>
  <a href="Program_Ranking.html">Program Ranking</a>
  <a href="Composer_Chart.html">Performances by Composer</a>
  <a href="Performances_by_Conductor.html">Performances by Conductor</a>
  {extra_nav}<a href="index.html">Home</a>
</p>
</div>

<div id="chart-wrap">
  <div id="chart"></div>
  <div class="legend">
    <span class="legend-item"><span>Prefecture total:</span><span class="legend-swatch"></span><span>low → high</span></span>
    <span class="legend-item">
      <span>Counter shown inside each prefecture (uniform font, colour encodes magnitude).</span>
    </span>
  </div>
</div>

<div id="tooltip" role="tooltip"></div>

<p class="footnote">
Map data © <a href="https://github.com/dataofjapan/land" target="_blank" rel="noopener">dataofjapan/land</a> (Japan prefecture boundaries).
Hover any prefecture's bubble for the full list of works performed there and the contributing cities.
</p>

<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const prefData = {data_json};
const prefTotals = Object.fromEntries(prefData.map(p => [p.name, p.total]));
const prefByName = Object.fromEntries(prefData.map(p => [p.name, p]));

const tooltipEl = document.getElementById('tooltip');

function showTooltip(p, evt) {{
  const works = p.works || [];
  let prevCount = null, prevRank = 0;
  const items = works.map(([w, n], i) => {{
    let rank;
    if (n === prevCount) {{ rank = prevRank; }}
    else                  {{ rank = i + 1; prevCount = n; prevRank = rank; }}
    const isStaged = w.includes('(staged opera)') || w.includes('(concert performance)');
    const titleCls = isStaged ? 'work-title staged-opera' : 'work-title';
    return `<li><span class="work-rank">${{rank}}.</span><span class="${{titleCls}}">${{w}}</span><span class="work-count">${{n}}</span></li>`;
  }}).join('');
  const cities = (p.cities || []).map(([c, n]) => `<b>${{c}}</b>&nbsp;${{n}}`).join(' · ');
  const citiesLine = cities ? `<p class="cities">${{cities}}</p>` : '';
  // Switch to a multi-column layout when the work list is long so
  // every entry stays visible without scrolling.
  tooltipEl.classList.remove('wide', 'wider', 'widest');
  if (works.length > 100)      tooltipEl.classList.add('widest');
  else if (works.length > 70)  tooltipEl.classList.add('wider');
  else if (works.length > 30)  tooltipEl.classList.add('wide');
  tooltipEl.innerHTML = `
    <h3>${{p.name}}<span class="pref-total">${{p.total}}</span></h3>
    ${{citiesLine}}
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

function normPref(nam) {{
  if (nam === "Hokkai Do") return "Hokkaido";
  return nam.replace(/ (Ken|Fu|To)$/, '');
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

  // Drop:
  //  • Okinawa prefecture (no concerts, far south)
  //  • Polygons that hang below Kyūshū (Amami, Tokara, Yakushima,
  //    Tanegashima, Ogasawara, etc.) — maxLat < 31°N
  //  • The Kuril chain off northern Hokkaido (Etorofu/Iturup,
  //    Kunashiri/Kunashir, Shikotan, Habomai) — minLng > 146°E
  //    AND minLat > 42.5°N. These appear inside Hokkaidō's
  //    MultiPolygon in the dataofjapan/land file.
  const SOUTH_CUTOFF = 31.0;
  const KURIL_LNG    = 146.0;
  const KURIL_LAT    = 42.5;
  function shouldKeepPoly(poly) {{
    const lngs = poly[0].map(p => p[0]);
    const lats = poly[0].map(p => p[1]);
    const minLng = Math.min(...lngs);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    if (maxLat < SOUTH_CUTOFF) return false;
    if (minLng > KURIL_LNG && minLat > KURIL_LAT) return false;
    return true;
  }}
  function filterPolys(feature) {{
    if (feature.geometry.type === 'MultiPolygon') {{
      const kept = feature.geometry.coordinates.filter(shouldKeepPoly);
      return {{ ...feature, geometry: {{ type: 'MultiPolygon', coordinates: kept }} }};
    }}
    if (feature.geometry.type === 'Polygon') {{
      return shouldKeepPoly(feature.geometry.coordinates) ? feature : null;
    }}
    return feature;
  }}
  const isOkinawa = f => normPref(f.properties.nam) === 'Okinawa';
  const mainFeatures = geoData.features
    .filter(f => !isOkinawa(f))
    .map(filterPolys)
    .filter(f => f && (f.geometry.coordinates && f.geometry.coordinates.length > 0));
  const mainCollection = {{ type: 'FeatureCollection', features: mainFeatures }};

  // Fit the trimmed mainland into the full canvas so Japan fills the
  // square frame — no rightward shift, no margin to either side.
  const mainProjection = d3.geoMercator().fitSize([W * 0.98, H * 0.98], mainCollection);
  const mainPath = d3.geoPath(mainProjection);

  const allTotals = Object.values(prefTotals);
  const maxPref = Math.max(1, ...allTotals);
  // Sqrt-distributed colour scale so low-count prefectures (Ehime 3,
  // Niigata 5…) still have visibly distinct tints, rather than getting
  // swallowed by the lightest end next to Tokyo's 240.
  const colorScale = d3.scalePow()
    .exponent(0.55)
    .domain([0, maxPref])
    .range(["{choro_a}", "{choro_b}"])
    .interpolate(d3.interpolateRgb);

  // -------- MAIN MAP --------
  const gMain = document.createElementNS(svgNS, 'g');

  // Prefecture polygons — themselves are the hover targets.
  const gP = document.createElementNS(svgNS, 'g');
  mainFeatures.forEach(f => {{
    const nam = normPref(f.properties.nam || '');
    const count = prefTotals[nam] || 0;
    const p = document.createElementNS(svgNS, 'path');
    p.setAttribute('class', count > 0 ? 'prefecture has-data' : 'prefecture');
    p.setAttribute('d', mainPath(f));
    p.setAttribute('fill', colorScale(count));
    if (count > 0) {{
      const entry = prefByName[nam];
      p.addEventListener('mouseenter', (evt) => showTooltip(entry, evt));
      p.addEventListener('mousemove',  moveTooltip);
      p.addEventListener('mouseleave', hideTooltip);
    }}
    gP.appendChild(p);
  }});
  gMain.appendChild(gP);

  // Uniform font size for every prefecture — the colour does the
  // magnitude encoding now, the number is just the readable value.
  const COUNT_FS = 14;
  const NAME_FS  = 10;
  function tileIsDark(count) {{
    return count >= maxPref * 0.30;
  }}
  // Centroid offsets in projected pixels for prefectures whose default
  // centroid would collide with a neighbour. Format: [dx, dy].
  const LABEL_OFFSETS = {{
    "Tokyo":    [ 14, -10 ],  // nudge NE so it doesn't sit on Kanagawa
    "Kanagawa": [-12,  10 ],  // pull SW to the Yokohama side
    "Saitama":  [  0, -10 ],  // sits above Tokyo on the map
    "Chiba":    [ 14,   2 ],
  }};

  const gT = document.createElementNS(svgNS, 'g');
  mainFeatures.forEach(f => {{
    const nam = normPref(f.properties.nam || '');
    const entry = prefByName[nam];
    if (!entry) return;
    const xy = mainPath.centroid(f);
    if (!xy || !isFinite(xy[0])) return;
    const [cx, cy] = xy;
    const [dx, dy] = LABEL_OFFSETS[entry.name] || [0, 0];
    const x = cx + dx;
    const y = cy + dy;
    const dark = tileIsDark(entry.total);

    const count = document.createElementNS(svgNS, 'text');
    count.setAttribute('class', 'pref-count');
    count.setAttribute('x', x);
    count.setAttribute('y', y);
    count.setAttribute('font-size', COUNT_FS);
    // Set font-family on the SVG element directly. Some browsers don't
    // reliably apply CSS classes to SVG <text>, causing the larger
    // Tokyo/Osaka counters to fall back to the system serif while the
    // smaller prefectures show in Arial. Inline attribute is safer.
    count.setAttribute('font-family', 'Arial, sans-serif');
    count.setAttribute('font-weight', '700');
    count.setAttribute('fill', dark ? '#fff' : '{accent_d}');
    count.setAttribute('stroke', dark ? 'rgba(0,0,0,0.55)' : 'rgba(255,255,255,0.92)');
    count.textContent = entry.total;
    gT.appendChild(count);

    const lbl = document.createElementNS(svgNS, 'text');
    lbl.setAttribute('class', 'pref-label');
    lbl.setAttribute('x', x);
    lbl.setAttribute('y', y + COUNT_FS * 0.85);
    lbl.setAttribute('font-size', NAME_FS);
    lbl.setAttribute('font-family', 'Arial, sans-serif');
    lbl.setAttribute('font-weight', '700');
    lbl.setAttribute('fill', dark ? '#fff' : '#1c1917');
    lbl.setAttribute('stroke', dark ? 'rgba(0,0,0,0.55)' : 'rgba(255,255,255,0.92)');
    lbl.textContent = entry.name;
    gT.appendChild(lbl);
  }});
  gMain.appendChild(gT);
  svg.appendChild(gMain);

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
        in_path  = "Berliner_Philharmoniker_in_Japan/Performances_in_Japan.html"
        out_path = "Berliner_Philharmoniker_in_Japan/Performances_by_Prefecture.html"
    elif orchestra == "wpo":
        in_path  = "Wiener_Philharmoniker_in_Japan/Performances_in_Japan.html"
        out_path = "Wiener_Philharmoniker_in_Japan/Performances_by_Prefecture.html"
    else:
        print(f"Unknown orchestra '{orchestra}'. Use 'bpo' or 'wpo'.", file=sys.stderr)
        sys.exit(1)

    with open(in_path, encoding="utf-8") as f:
        html = f.read()
    prefectures = aggregate(html)
    page = build_page(orchestra, prefectures)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)

    n_total = sum(p["total"] for p in prefectures.values())
    print(f"Wrote {out_path}")
    print(f"  {len(prefectures)} prefectures, {n_total} total performances")


if __name__ == "__main__":
    main()
