"""Generate a circle-packed Performances-by-Conductor page from a
Concerts_in_Japan.html source.

Usage:
    python3 conductor_chart.py bpo   # → "Berliner Philharmoniker/Performances_by_Conductor.html"
    python3 conductor_chart.py wpo   # → "Wiener Philharmoniker/Performances_by_Conductor.html"

Visualisation: D3 hierarchical pack — each conductor is a circle whose
area is proportional to total performance count on the orchestra's
documented Japan tours. Portraits fill each circle; hovering surfaces
the full work-list (Composer: Work) with counts.

This is deliberately a different visual paradigm from the squarified
treemap used by composer_chart.py.
"""
import json
import re
import sys
from urllib.parse import quote

# Conductor → Wikimedia Commons portrait filename. Used by the FilePath
# helper to construct an image URL. TIFs are auto-converted to JPEG.
CONDUCTOR_IMAGE = {
    # BPO
    "Herbert von Karajan":  "Herbert_Von_Karajan,_Fundo_Correio_da_Manhã_-_2_(cropped).tif",
    "Simon Rattle":         "Simon_Rattle_(cropped).jpg",
    "Claudio Abbado":       "Claudio_Abbado_Senato.jpg",
    "Kirill Petrenko":      "Berliner_Philharmoniker_at_Brandenburg_Gate_asv2019-08-24_img22.jpg",
    "Gustavo Dudamel":      "Gustavo_Dudamel.jpeg",
    "Zubin Mehta":          "Zubin_Mehta,_1985_-_collezione_Tino_Barindelli.tif",
    "Seiji Ozawa":          "Seiji_Ozawa_1963.jpg",
    "Mariss Jansons":       "2015_Jansons_Mariss-0242_(18794705869)_(2)_(cropped).jpg",
    "Wilhelm Schüchter":    "Wilhelm_Schüchter_(1).jpg",
    # WPO – populated as needed for reuse
    "Valery Gergiev":       "Valery_Gergiev_2024.jpg",
    "Riccardo Muti":        "Riccardo_Muti_-_Pacotto_Magliani_(cropped).jpg",
    "Christian Thielemann": "Christian_Thielemann_2013.jpg",
    "Andris Nelsons":       "Andris_Nelsons_2017.jpg",
    "Georges Prêtre":       "Georges_Pretre_2009.jpg",
    "Franz Welser-Möst":    "Franz_Welser-Möst_2014.jpg",
    "Lorin Maazel":         "Lorin_Maazel_1959.jpg",
    "Nikolaus Harnoncourt": "Nikolaus_Harnoncourt_in_2007.jpg",
    "Christoph von Dohnányi": "Christoph_von_Dohnanyi_(cropped).jpg",
    "James Levine":         "James_Levine.jpg",
    "Karl Böhm":            "Karl_Böhm_1973.jpg",
    "Giuseppe Sinopoli":    "Giuseppe_Sinopoli.jpg",
    "Bernard Haitink":      "Bernard_Haitink_2008.jpg",
    "Paul Hindemith":       "Paul_Hindemith_1923.jpg",
    "Christoph Eschenbach": "Christoph_Eschenbach_2007.jpg",
    "Carlos Kleiber":       "Carlos_Kleiber_1965.jpg",
    "Georg Solti":          "Georg_Solti_1967.jpg",
    "André Previn":         "André_Previn_(1976).jpg",
    "Leopold Hager":        "Leopold_Hager.jpg",
    "Tugan Sokhiev":        "Tugan_Sokhiev_2019.jpg",
    "Willi Boskovsky":      "Willi_Boskovsky_1955.jpg",
    "Andrés Orozco-Estrada": "Andres_Orozco-Estrada.jpg",
}


def wiki_image(filename: str, width: int = 480) -> str:
    return (
        f"https://en.wikipedia.org/wiki/Special:FilePath/"
        f"{quote(filename, safe='(),_-.')}?width={width}"
    )


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def strip_tags_keep_em(s: str) -> str:
    """Strip all tags except <em>...</em>, which we keep so work names that
    italicise the work title (e.g. <em>Oberon</em>, Ouvertüre) stay
    italicised in the tooltip work list."""
    # Drop anchor opens/closes
    s = re.sub(r"</?a\b[^>]*>", "", s)
    # Drop everything else except <em>...</em>
    s = re.sub(r"<(?!/?em\b)[^>]+>", "", s)
    # Collapse runs of whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_program(prog_html: str) -> list[str]:
    """Split a Program cell into individual works (Composer: Work format).

    Inline <em>...</em> tags are preserved so titles like "Oberon,
    Ouvertüre" render italicised in the tooltip — matching the
    Composer Chart's behaviour."""
    lines = re.split(r"<br\s*/?>", prog_html)
    out = []
    current_composer = None
    for raw in lines:
        text = strip_tags_keep_em(raw)
        if not text:
            continue
        # The composer prefix is plain text (never wrapped in <em>), so
        # match the leading "Composer: …" portion on the plain-text form.
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


# Lines that are placeholder / aggregated rather than real works.
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


def aggregate(concerts_html: str) -> tuple[dict, dict]:
    """Walk every concert row → {conductor: {total: N, works: {work: count}}}.
    Joint-conductor cells (e.g. "Mehta / Ozawa") credit each conductor with
    the works in that concert.
    Returns (totals, details) where:
       totals[cond]  = int
       details[cond] = {work: count}
    """
    m = re.search(r"<tbody>(.*?)</tbody>", concerts_html, re.DOTALL)
    if not m:
        return {}, {}
    tbody = m.group(1)

    totals: dict[str, int] = {}
    details: dict[str, dict[str, int]] = {}

    for row in re.findall(r"<tr>.*?</tr>", tbody, re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 5:
            continue
        cond_text = strip_tags(tds[3]).strip()
        program   = tds[4]
        if not cond_text:
            continue

        # Joint conductors → "X / Y" → split
        conductors = [c.strip() for c in cond_text.split("/") if c.strip()]

        works = parse_program(program)
        works = [w for w in works if not is_placeholder(w)]

        for cond in conductors:
            d = details.setdefault(cond, {})
            for w in works:
                d[w] = d.get(w, 0) + 1
                totals[cond] = totals.get(cond, 0) + 1
    return totals, details


def build_page(orchestra: str, totals: dict, details: dict) -> str:
    if orchestra == "bpo":
        title    = "Berliner Philharmoniker — Performances by Conductor"
        title_pre = "Berliner Philharmoniker"
        bgcol    = "#FFF8EC"
        accent   = "#D97706"
        accent_d = "#B45309"
        accent_rgba = "rgba(180,83,9,0.25)"
        notes_color = "%23D97706"
    else:
        title    = "Wiener Philharmoniker — Performances by Conductor"
        title_pre = "Wiener Philharmoniker"
        bgcol    = "#FBF1F4"
        accent   = "#9F1239"
        accent_d = "#831234"
        accent_rgba = "rgba(159,18,57,0.25)"
        notes_color = "%239F1239"

    # Build data array.
    children = []
    for cond, total in sorted(totals.items(), key=lambda x: -x[1]):
        works_dict = details.get(cond, {})
        works_sorted = sorted(works_dict.items(), key=lambda x: (-x[1], x[0]))
        img_file = CONDUCTOR_IMAGE.get(cond)
        img = wiki_image(img_file) if img_file else ""
        children.append({
            "name": cond,
            "value": total,
            "img": img,
            "works": works_sorted,
        })

    data_json = json.dumps({"name": "root", "children": children}, ensure_ascii=False)

    total_perf = sum(totals.values())
    total_cond = len(totals)

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
  max-width: 720px;
  aspect-ratio: 1 / 1;
  margin: 0 auto;
  border: 2px solid {accent};
  border-radius: 8px;
  background: rgba(255,255,255,0.4);
  box-shadow: 0 2px 14px rgba(0,0,0,0.10);
}}
#chart svg {{
  width: 100%;
  height: 100%;
  display: block;
}}
.bubble {{
  cursor: default;
  transition: filter 0.15s ease;
}}
.bubble:hover {{
  filter: drop-shadow(0 4px 14px rgba(0,0,0,0.35));
}}
.bubble image {{ pointer-events: none; }}
.bubble .ring {{
  fill: none;
  stroke: rgba(255,255,255,0.9);
  stroke-width: 2;
}}
.bubble .ring-outer {{
  fill: none;
  stroke: {accent_d};
  stroke-width: 1.5;
  stroke-opacity: 0.55;
}}
.bubble .label-bg {{
  fill: rgba(0,0,0,0.65);
  pointer-events: none;
}}
.bubble text {{
  pointer-events: none;
  text-anchor: middle;
  fill: #fff;
  text-shadow: 0 1px 2px rgba(0,0,0,0.85);
  font-family: Arial, sans-serif;
  font-weight: 600;
}}
.bubble text.name {{
  font-weight: 700;
}}
.bubble text.count {{
  font-weight: 800;
  letter-spacing: -0.5px;
}}
.bubble.hide-label text, .bubble.hide-label .label-bg {{ display: none; }}

/* Hover tooltip */
#tooltip {{
  position: fixed;
  z-index: 100;
  background: #fff;
  border-radius: 6px;
  box-shadow: 0 6px 22px rgba(0,0,0,0.32);
  padding: 12px 14px 10px;
  width: 440px;
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
  margin: 0 0 8px;
  padding: 0 0 6px;
  border-bottom: 2px solid {accent};
  font-size: 14px;
  font-weight: 700;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}}
#tooltip h3 .conductor-total {{
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
<div class="page-header">
<h1>{title}</h1>
<p class="subhead">Each bubble's area is proportional to that conductor's total performances on the orchestra's documented Japan tours. {total_cond} conductors, {total_perf} performances total — laid out by a hierarchical circle-pack.</p>
<p class="toolbar">
  <a href="Concerts_in_Japan.html">Concerts in Japan →</a>
  <a href="Program_Ranking.html">Program Ranking →</a>
  <a href="Composer_Chart.html">Performances by Composer →</a>
  <a href="Performances_by_Prefecture.html">Performances by Prefecture →</a>
  <a href="index.html">Home</a>
</p>
</div>

<div id="chart-wrap">
  <div id="chart"></div>
</div>

<div id="tooltip" role="tooltip"></div>

<p class="footnote">
Portraits via <a href="https://commons.wikimedia.org/" target="_blank" rel="noopener">Wikimedia Commons</a>.
Hover over any conductor's bubble for the full list of works they conducted with the orchestra on Japan tours.
</p>

<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const data = {data_json};

const tooltipEl = document.getElementById('tooltip');

function showTooltip(d, evt) {{
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
  // Switch to a multi-column layout when the work list is long
  // so every entry stays visible without scrolling.
  tooltipEl.classList.remove('wide', 'wider', 'widest');
  if (works.length > 100)      tooltipEl.classList.add('widest');
  else if (works.length > 70)  tooltipEl.classList.add('wider');
  else if (works.length > 30)  tooltipEl.classList.add('wide');
  tooltipEl.innerHTML = `
    <h3>${{d.data.name}}<span class="conductor-total">${{d.data.value}}</span></h3>
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

function safeId(name) {{ return 'cl-' + name.replace(/[^A-Za-z0-9]/g, '_'); }}

function render() {{
  const wrap = document.getElementById('chart');
  wrap.innerHTML = '';
  const W = wrap.clientWidth;
  const H = wrap.clientHeight;

  const root = d3.hierarchy(data)
    .sum(d => d.value)
    .sort((a, b) => b.value - a.value);

  d3.pack()
    .size([W, H])
    .padding(4)(root);

  // Compute the actual bounding box of the packed leaves so the SVG
  // viewBox wraps them tightly — no big internal margins inside the
  // bordered frame.
  const leaves = root.leaves();
  const pad = 6;
  let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity;
  leaves.forEach(d => {{
    xMin = Math.min(xMin, d.x - d.r);
    yMin = Math.min(yMin, d.y - d.r);
    xMax = Math.max(xMax, d.x + d.r);
    yMax = Math.max(yMax, d.y + d.r);
  }});
  const vbX = xMin - pad;
  const vbY = yMin - pad;
  const vbW = (xMax - xMin) + pad * 2;
  const vbH = (yMax - yMin) + pad * 2;

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', `${{vbX}} ${{vbY}} ${{vbW}} ${{vbH}}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');

  // <defs> with one clipPath per conductor circle.
  const defs = document.createElementNS(svgNS, 'defs');
  svg.appendChild(defs);

  root.leaves().forEach(d => {{
    const cid = safeId(d.data.name);

    // Clip path for the portrait
    const clip = document.createElementNS(svgNS, 'clipPath');
    clip.setAttribute('id', cid);
    const clipCircle = document.createElementNS(svgNS, 'circle');
    clipCircle.setAttribute('cx', d.x);
    clipCircle.setAttribute('cy', d.y);
    clipCircle.setAttribute('r', d.r);
    clip.appendChild(clipCircle);
    defs.appendChild(clip);

    const g = document.createElementNS(svgNS, 'g');
    g.classList.add('bubble');

    // Portrait — if no image, draw a coloured fill for fallback.
    if (d.data.img) {{
      const img = document.createElementNS(svgNS, 'image');
      img.setAttributeNS('http://www.w3.org/1999/xlink', 'href', d.data.img);
      img.setAttribute('href', d.data.img);
      img.setAttribute('x', d.x - d.r);
      img.setAttribute('y', d.y - d.r);
      img.setAttribute('width', d.r * 2);
      img.setAttribute('height', d.r * 2);
      img.setAttribute('preserveAspectRatio', 'xMidYMin slice');
      img.setAttribute('clip-path', `url(#${{cid}})`);
      g.appendChild(img);
    }} else {{
      const fill = document.createElementNS(svgNS, 'circle');
      fill.setAttribute('cx', d.x);
      fill.setAttribute('cy', d.y);
      fill.setAttribute('r', d.r);
      fill.setAttribute('fill', '{accent}');
      fill.setAttribute('fill-opacity', '0.4');
      g.appendChild(fill);
    }}

    // White ring on top of portrait
    const ring = document.createElementNS(svgNS, 'circle');
    ring.setAttribute('class', 'ring');
    ring.setAttribute('cx', d.x);
    ring.setAttribute('cy', d.y);
    ring.setAttribute('r', d.r - 1);
    g.appendChild(ring);

    // Accent-coloured outer ring
    const outer = document.createElementNS(svgNS, 'circle');
    outer.setAttribute('class', 'ring-outer');
    outer.setAttribute('cx', d.x);
    outer.setAttribute('cy', d.y);
    outer.setAttribute('r', d.r);
    g.appendChild(outer);

    // Label: bottom band over the portrait
    const r = d.r;
    const nameSize  = Math.max(8,  Math.min(20, r * 0.18));
    const countSize = Math.max(12, Math.min(46, r * 0.40));
    const bandH = nameSize + countSize + 12;
    const bandY = d.y + r - bandH;
    if (r > 22) {{
      // Use a clipped rect for the label gradient. We'll just use a filled rect inside the clip.
      const lbg = document.createElementNS(svgNS, 'rect');
      lbg.setAttribute('class', 'label-bg');
      lbg.setAttribute('x', d.x - r);
      lbg.setAttribute('y', bandY);
      lbg.setAttribute('width', r * 2);
      lbg.setAttribute('height', bandH);
      lbg.setAttribute('clip-path', `url(#${{cid}})`);
      g.appendChild(lbg);

      const tname = document.createElementNS(svgNS, 'text');
      tname.setAttribute('class', 'name');
      tname.setAttribute('x', d.x);
      tname.setAttribute('y', bandY + nameSize + 2);
      tname.setAttribute('font-size', nameSize);
      // Trim long names by ellipsis if needed (approximated by char count)
      let nameStr = d.data.name;
      const approxCharW = nameSize * 0.55;
      const maxChars = Math.floor((r * 1.6) / approxCharW);
      if (nameStr.length > maxChars && maxChars > 4) {{
        nameStr = nameStr.slice(0, maxChars - 1).trim() + '…';
      }}
      tname.textContent = nameStr;
      g.appendChild(tname);

      const tcount = document.createElementNS(svgNS, 'text');
      tcount.setAttribute('class', 'count');
      tcount.setAttribute('x', d.x);
      tcount.setAttribute('y', d.y + r - 5);
      tcount.setAttribute('font-size', countSize);
      tcount.textContent = d.data.value;
      g.appendChild(tcount);
    }} else {{
      g.classList.add('hide-label');
    }}

    // A transparent circle on top is the hover target — guarantees the
    // entire bubble area accepts pointer events, even where the clipped
    // portrait is.
    const hit = document.createElementNS(svgNS, 'circle');
    hit.setAttribute('cx', d.x);
    hit.setAttribute('cy', d.y);
    hit.setAttribute('r', d.r);
    hit.setAttribute('fill', 'transparent');
    hit.addEventListener('mouseenter', (evt) => showTooltip(d, evt));
    hit.addEventListener('mousemove',  moveTooltip);
    hit.addEventListener('mouseleave', hideTooltip);
    g.appendChild(hit);

    svg.appendChild(g);
  }});

  wrap.appendChild(svg);
}}

render();
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
        out_path = "Berliner Philharmoniker/Performances_by_Conductor.html"
    elif orchestra == "wpo":
        in_path  = "Wiener Philharmoniker/Concerts_in_Japan.html"
        out_path = "Wiener Philharmoniker/Performances_by_Conductor.html"
    else:
        print(f"Unknown orchestra '{orchestra}'. Use 'bpo' or 'wpo'.", file=sys.stderr)
        sys.exit(1)

    with open(in_path, encoding="utf-8") as f:
        html = f.read()
    totals, details = aggregate(html)

    page = build_page(orchestra, totals, details)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Wrote {out_path}")
    print(f"  {len(totals)} conductors, {sum(totals.values())} total performances")
    missing = [c for c in totals if c not in CONDUCTOR_IMAGE]
    if missing:
        print(f"  (no portrait mapped for: {missing})")


if __name__ == "__main__":
    main()
