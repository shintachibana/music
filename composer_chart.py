"""Generate a proportional-area composer chart from a Program_Ranking page.

Usage:
    python3 composer_chart.py bpo   # → "Berliner Philharmoniker/Composer_Chart.html"
    python3 composer_chart.py wpo   # → "Wiener Philharmoniker/Composer_Chart.html"
"""
import math
import re
import sys
from urllib.parse import quote

# Composer name (as it appears in the ranking page) → Wikimedia Commons filename.
# Resolved by querying Wikipedia's REST API for each composer's article and
# pulling the infobox image. Filenames stored raw (Unicode, parens, etc.) —
# wiki_image() URL-encodes them at use time.
COMPOSER_IMAGE = {
    # BPO data
    "Beethoven":       "Joseph_Karl_Stieler's_Beethoven_mit_dem_Manuskript_der_Missa_solemnis.jpg",
    "Brahms":          "JohannesBrahms_(cropped).jpg",
    "Mozart":          "The_Mozart_Family_-_Wolfgang_Amadeus_Mozart_headshot.jpg",
    "R. Strauss":      "1904_Richard_Strauss_(cropped).jpg",
    "Wagner":          "RichardWagner.jpg",
    "Mahler":          "Photo_of_Gustav_Mahler_by_Moritz_Nähr_01.jpg",
    "Debussy":         "Claude_Debussy_by_Atelier_Nadar.jpg",
    "Tschaikowsky":    "Tchaikovsky_by_Reutlinger_(cropped).jpg",
    "Bruckner":        "Anton_Bruckner.jpg",
    "Berg":            "Alban_Berg_(1885–1935)_~1930_©_Max_Fenichel_(1885–1942).jpg",
    "Ravel":           "Maurice_Ravel_1925.jpg",
    "Schumann":        "Robert_Schumann_1839.jpg",
    "Strawinsky":      "Igor_Stravinsky_LOC_32392u.jpg",
    "Dvořák":          "Dvorak.jpg",
    "Haydn":           "Joseph_Haydn.jpg",
    "Reger":           "Max_Reger_playing_piano.jpg",
    "Prokofjew":       "Sergei_Prokofiev_circa_1918_over_Chair_Bain.jpg",
    # Wikipedia uses his signature as the article's main image — override
    # with the famous Repin portrait for a real face.
    "Mussorgsky":      "Mussorgsky Repin.jpg",
    "Schubert":        "Franz_Schubert_by_Wilhelm_August_Rieder_1875.jpg",
    "Bartók":          "Bartók_Béla_1927.jpg",
    "Bernstein":       "Leonard_Bernstein_by_Jack_Mitchell_(high_quality).jpg",
    "Boulez":          "Pierre_Boulez_(1968).jpg",
    "Janáček":         "Leoš_Janáček_el_1914.png",
    "Magnus Lindberg": "Magnus_Lindberg_3811.jpg",
    "Rachmaninow":     "Sergei_Rachmaninoff_cph.3a40575.jpg",
    "Respighi":        "Ottorino_Respighi,_1927_(cropped).jpg",
    "Unsuk Chin":      "Unsuk Chin.jpg",
    "Verdi":           "Giuseppe_Verdi_by_Ferdinand_Mulnier_BW.jpg",
    # WPO-only composers — filenames pulled from each composer's
    # Wikipedia article via /page/summary, then unquoted to raw form.
    "Bach":            "Johann_Sebastian_Bach.jpg",
    "Mendelssohn":     "Felix_Mendelssohn_Bartholdy_by_Eduard_Magnus_(1833).jpg",
    "J. Strauss II":   "Johann_Strauss_II_by_Fritz_Luckhardt_3-4_crop.jpg",
    "J. Strauss":      "Johann_Strauss_II_by_Fritz_Luckhardt_3-4_crop.jpg",
    "Josef Strauss":   "Strauss_Josef_Luckhardt.png",
    "Rossini":         "Rossini_young-circa-1815.jpg",
    "Liszt":           "Franz_Liszt_by_Herman_Biow-_1843.png",
    "Wolf":            "Hugo_Wolf.jpg",
    "Webern":          "Anton_Webern_in_Stettin,_October_1912.jpg",
    "Hindemith":       "Paul_Hindemith_1923.jpg",
    "Falla":           "ManuelDeFalla.JPG",
    "Sibelius":        "Jean_Sibelius_circa_1898-1900_(3x4_cropped).jpg",
    "Saint-Saëns":     "Saint-Saëns-circa-1880.jpg",
    "Schostakowitsch": "Композитор_Дмитрий_Дмитриевич_Шостакович.jpg",
    "Schönberg":       "阿诺德·勋伯格肖像.jpg",
    "Rimsky-Korsakow": "Walentin_Alexandrowitsch_Serow_004_(cropped_3x4).jpg",
    "Chopin":          "Frederic_Chopin_photo.jpeg",
    "Reznicek":        "Emilreznicekportrait.jpg",
    "Takemitsu":       "TakemitsuToru.jpg",
    # 1957 BPO/Karajan tour additions
    "Weber":           "Caroline_Bardua_-_Bildnis_des_Komponisten_Carl_Maria_von_Weber.jpg",
    "Smetana":         "Smetana_LCCN2014716851_(cropped).jpg",
    # Hikaru Hayashi — no portrait found on Commons; tile falls back to accent colour.
}


def wiki_image(filename: str, width: int = 320) -> str:
    return (
        f"https://en.wikipedia.org/wiki/Special:FilePath/"
        f"{quote(filename, safe='()_-.')}?width={width}"
    )


def placeholder_initials(composer: str, bg_hex: str, accent_dark_hex: str) -> str:
    """Build a data:image/svg+xml URI showing the composer's initials over an
    accent-coloured background — used when no portrait is mapped."""
    # Drop punctuation, split, take first letter of up to two words.
    parts = [p for p in re.split(r"[\s\-]+", composer) if p]
    initials = "".join(p[0] for p in parts[:2]).upper() if parts else composer[:1].upper()
    bg = bg_hex.lstrip("#")
    fg = accent_dark_hex.lstrip("#")
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        f"<defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'>"
        f"<stop offset='0%' stop-color='#{bg}' stop-opacity='0.95'/>"
        f"<stop offset='100%' stop-color='#{fg}' stop-opacity='1'/>"
        f"</linearGradient></defs>"
        f"<rect width='100' height='100' fill='url(#g)'/>"
        f"<text x='50' y='62' text-anchor='middle' font-family='Georgia,serif' "
        f"font-size='42' font-weight='600' fill='#ffffff' "
        f"style='letter-spacing:1px'>{initials}</text>"
        "</svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg, safe="")


def aggregate(ranking_html: str) -> dict:
    """Return {composer: total_performances} parsed from a Program_Ranking page."""
    # Lazy .+? so that work cells containing their own markup (e.g.
    # <em>Unvollendete</em>) still match through to the count column.
    rx = re.compile(
        r'<tr><td>\d+</td><td>(?:<a [^>]+>)?([^<:]+):.+?(?:</a>)?</td><td>(\d+)</td>'
    )
    totals: dict[str, int] = {}
    for m in rx.finditer(ranking_html):
        composer = m.group(1).strip()
        composer = composer.split("/")[0].strip()       # Mussorgsky/Ravel → Mussorgsky
        composer = re.sub(r"\s*\([^)]*\)", "", composer).strip()  # Bach (arr. Webern) → Bach
        totals[composer] = totals.get(composer, 0) + int(m.group(2))
    return totals


def aggregate_with_works(ranking_html: str) -> dict:
    """Return {composer: {"total": int, "works": [(work, count), …]}}.

    Used for the hover tooltip that lists each composer's individual works.
    Work names retain inline <em> markup so the tooltip stays italic-styled
    consistently with the ranking page.
    """
    rx = re.compile(
        r'<tr><td>\d+</td><td>(?:<a [^>]+>)?(.+?)(?:</a>)?</td><td>(\d+)</td>'
    )
    out: dict[str, dict] = {}
    for m in rx.finditer(ranking_html):
        full = m.group(1).strip()
        count = int(m.group(2))
        if ":" not in full:
            continue
        composer_raw, work = full.split(":", 1)
        composer = composer_raw.strip()
        composer = composer.split("/")[0].strip()
        composer = re.sub(r"\s*\([^)]*\)", "", composer).strip()
        work = work.strip()
        slot = out.setdefault(composer, {"total": 0, "works": []})
        slot["works"].append((work, count))
        slot["total"] += count
    # Sort each composer's works by descending count
    for slot in out.values():
        slot["works"].sort(key=lambda x: -x[1])
    return out


def build_page(orchestra: str, totals: dict, composer_details: dict) -> str:
    if orchestra == "bpo":
        title  = "Berliner Philharmoniker — Performances by Composer"
        bgcol  = "#FFF8EC"
        accent = "#D97706"
        accent_d = "#B45309"
        accent_rgba = "rgba(180,83,9,0.25)"
        notes_pattern_color = "%23D97706"
    else:
        title  = "Wiener Philharmoniker — Performances by Composer"
        bgcol  = "#FBF1F4"
        accent = "#9F1239"
        accent_d = "#831234"
        accent_rgba = "rgba(159,18,57,0.25)"
        notes_pattern_color = "%239F1239"

    # JSON-like data emitted into the page; D3 squarify treemap will lay it out.
    import json
    children = []
    for composer, count in sorted(totals.items(), key=lambda x: -x[1]):
        img_filename = COMPOSER_IMAGE.get(composer)
        works = composer_details.get(composer, {}).get("works", [])
        if img_filename:
            img = wiki_image(img_filename, width=480)
        else:
            img = placeholder_initials(composer, accent, accent_d)
        children.append({
            "name": composer,
            "value": count,
            "img": img,
            "works": works,
        })
    data_json = json.dumps({"name": "root", "children": children}, ensure_ascii=False)

    total_perf = sum(totals.values())
    total_composers = len(totals)

    music_svg = (
        "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' "
        "width='220' height='220'%3E%3Cg font-family='Georgia,serif'%3E"
        f"%3Ctext x='15' y='48' font-size='38' transform='rotate(-12 30 38)' fill='{notes_pattern_color}' fill-opacity='0.16'%3E♫%3C/text%3E"
        "%3Ctext x='120' y='30' font-size='26' fill='%230F766E' fill-opacity='0.15'%3E♪%3C/text%3E"
        f"%3Ctext x='175' y='95' font-size='32' transform='rotate(15 188 80)' fill='{notes_pattern_color}' fill-opacity='0.16'%3E♬%3C/text%3E"
        "%3Ctext x='45' y='125' font-size='30' fill='%239F1239' fill-opacity='0.14'%3E♩%3C/text%3E"
        "%3Ctext x='135' y='165' font-size='28' transform='rotate(-8 148 155)' fill='%230F766E' fill-opacity='0.15'%3E♫%3C/text%3E"
        f"%3Ctext x='80' y='195' font-size='34' fill='{notes_pattern_color}' fill-opacity='0.16'%3E♬%3C/text%3E"
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
h1 {{
  font-size: 20px;
  margin: 0;
  padding: 0 0 8px;
  text-align: center;
  color: #000;
}}
.subhead {{
  text-align: center;
  font-size: 13px;
  color: #555;
  margin: 0 0 24px;
}}
.toolbar {{ text-align: center; margin-bottom: 28px; }}
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
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  border: 2px solid {accent};
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255,255,255,0.4);
  box-shadow: 0 2px 14px rgba(0,0,0,0.10);
}}
.tile {{
  position: absolute;
  background-size: cover;
  background-position: center 22%;  /* favour the upper-middle so faces stay centred */
  overflow: hidden;
  cursor: default;
  transition: box-shadow 0.15s ease;
  border: 1px solid {bgcol};
}}
.tile:hover {{
  z-index: 5;
  box-shadow: 0 4px 16px rgba(0,0,0,0.35);
}}
.tile .label {{
  position: absolute;
  left: 0; right: 0; bottom: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.78), rgba(0,0,0,0.0));
  color: #fff;
  padding: 5px 7px 4px;
  line-height: 1.12;
  text-shadow: 0 1px 2px rgba(0,0,0,0.7);
  pointer-events: none;
}}
.tile .name {{
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.tile .count {{
  font-weight: 800;
  letter-spacing: -0.5px;
}}
.tile.hide-label .label {{ display: none; }}

/* Hover tooltip listing each composer's works */
#tooltip {{
  position: fixed;
  z-index: 100;
  background: #fff;
  border-radius: 6px;
  box-shadow: 0 6px 22px rgba(0,0,0,0.32);
  padding: 12px 14px 10px;
  width: 400px;
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
  margin: 0 0 8px;
  padding: 0 0 6px;
  border-bottom: 2px solid {accent};
  font-size: 14px;
  font-weight: 700;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}}
#tooltip h3 .composer-total {{
  color: {accent};
  font-size: 18px;
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
  margin: 32px auto 0;
  text-align: center;
  font-size: 12px;
  color: #777;
  line-height: 1.6;
}}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="subhead">Each cell's area is proportional to that composer's total performances on the orchestra's documented Japan tours. {total_composers} composers, {total_perf} performances total — laid out by a squarified treemap algorithm.</p>
<p class="toolbar">
  <a href="Concerts_in_Japan.html">Concerts in Japan →</a>
  <a href="Program_Ranking.html">Program Ranking →</a>
  <a href="index.html">{title.split(' — ')[0]}</a>
</p>

<div id="chart-wrap">
  <div id="chart"></div>
</div>

<div id="tooltip" role="tooltip"></div>

<p class="footnote">
Portraits via <a href="https://commons.wikimedia.org/" target="_blank" rel="noopener">Wikimedia Commons</a>.
Hover over any tile for the full list of works by that composer.
</p>

<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const data = {data_json};

const tooltipEl = document.getElementById('tooltip');

function showTooltip(d, evt) {{
  // Competition-style tied ranks: works sharing a count share a rank,
  // and the next distinct count skips ahead.
  const works = d.data.works || [];
  let prevCount = null;
  let prevRank = 0;
  const items = works.map(([w, n], i) => {{
    let rank;
    if (n === prevCount) {{
      rank = prevRank;
    }} else {{
      rank = i + 1;
      prevCount = n;
      prevRank = rank;
    }}
    return `<li><span class="work-rank">${{rank}}.</span><span class="work-title">${{w}}</span><span class="work-count">${{n}}</span></li>`;
  }}).join('');
  tooltipEl.innerHTML = `
    <h3>${{d.data.name}}<span class="composer-total">${{d.data.value}}</span></h3>
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

function render() {{
  const container = document.getElementById('chart');
  container.innerHTML = '';
  const W = container.clientWidth;
  const H = container.clientHeight;

  const root = d3.hierarchy(data)
    .sum(d => d.value)
    .sort((a, b) => b.value - a.value);

  d3.treemap()
    .size([W, H])
    .paddingInner(2)
    .tile(d3.treemapSquarify.ratio(1))
    (root);

  root.leaves().forEach(d => {{
    const w = d.x1 - d.x0;
    const h = d.y1 - d.y0;
    const tile = document.createElement('div');
    tile.className = 'tile';
    tile.style.left   = d.x0 + 'px';
    tile.style.top    = d.y0 + 'px';
    tile.style.width  = w + 'px';
    tile.style.height = h + 'px';
    if (d.data.img) tile.style.backgroundImage = `url("${{d.data.img}}")`;

    // Font sizes scale continuously with tile dimensions
    const geomMean = Math.sqrt(w * h);
    let countSize = Math.max(11, Math.min(44, geomMean * 0.13));
    let nameSize  = Math.max(9,  Math.min(20, geomMean * 0.072));
    // For very narrow tiles, cap by width to avoid overflow
    const wCapName  = w * 0.22;
    const wCapCount = w * 0.40;
    if (nameSize  > wCapName)  nameSize  = wCapName;
    if (countSize > wCapCount) countSize = wCapCount;
    // Hide label entirely if there's no room for legible text
    if (geomMean < 38 || w < 40 || h < 32) {{
      tile.classList.add('hide-label');
    }}

    tile.innerHTML = `<div class="label" style="padding:${{Math.max(2, h*0.04)}}px ${{Math.max(3, w*0.04)}}px ${{Math.max(2, h*0.025)}}px;">
      <div class="name"  style="font-size:${{nameSize.toFixed(1)}}px;">${{d.data.name}}</div>
      <div class="count" style="font-size:${{countSize.toFixed(1)}}px;line-height:1;">${{d.data.value}}</div>
    </div>`;

    tile.addEventListener('mouseenter', (evt) => showTooltip(d, evt));
    tile.addEventListener('mousemove',  moveTooltip);
    tile.addEventListener('mouseleave', hideTooltip);

    container.appendChild(tile);
  }});
}}

render();
window.addEventListener('resize', () => {{
  // Debounce so resize isn't laggy
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
        ranking_path = "Berliner Philharmoniker/Program_Ranking.html"
        out_path     = "Berliner Philharmoniker/Composer_Chart.html"
    elif orchestra == "wpo":
        ranking_path = "Wiener Philharmoniker/Program_Ranking.html"
        out_path     = "Wiener Philharmoniker/Composer_Chart.html"
    else:
        print(f"Unknown orchestra '{orchestra}'. Use 'bpo' or 'wpo'.", file=sys.stderr)
        sys.exit(1)

    with open(ranking_path, encoding="utf-8") as f:
        html = f.read()
    totals = aggregate(html)
    composer_details = aggregate_with_works(html)

    page = build_page(orchestra, totals, composer_details)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Wrote {out_path}")
    print(f"  {len(totals)} composers, {sum(totals.values())} total performances")
    missing = [c for c in totals if c not in COMPOSER_IMAGE]
    if missing:
        print(f"  (no portrait mapped for: {missing})")


if __name__ == "__main__":
    main()
