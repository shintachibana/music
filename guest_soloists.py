"""Generate the BPO "Guest Soloists" page.

Walks every row of Berliner_Philharmoniker_in_Japan/Performances_in_Japan.html,
parses the Soloists column, pairs each soloist with the work in that
concert that matches their instrument, and groups by
(soloist, instrument, work, conductor) to produce a row count.

Players who are themselves members of the Berliner Philharmoniker are
excluded so the table is strictly about guests.

Usage:
    python3 guest_soloists.py
"""
import html as html_lib
import re
from pathlib import Path
from urllib.parse import quote

# Reuse helpers from conductor_chart.py (lives in the same directory).
from conductor_chart import (
    CONDUCTOR_URL,
    strip_tags,
    strip_tags_keep_em,
    parse_program,
    is_placeholder,
)


# Names the user identified as Berliner Philharmoniker members rather
# than guest soloists. Matching is by name only (instrument may vary,
# e.g. "Noah Bendix-Balgley (violin I)" vs. "(violin)").
BPO_MEMBERS = {
    "Noah Bendix-Balgley",
    "Thomas Timm",
    "Amihai Grosz",
    "Ludwig Quandt",
    "Janne Saksala",
    "Emmanuel Pahud",
    "Albrecht Mayer",
    "Wenzel Fuchs",
    "Daniele Damiano",
    "Stefan Dohr",
    "Guillaume Jehl",
    "Daishin Kashimoto",
    # Former BPO principals also excluded as orchestra members:
    "Ottomar Borwitzky",   # principal cello
    "Thomas Brandis",      # concertmaster (1962–1983)
    "Wolfram Christ",      # principal viola (1979–1999)
    "Rainer Kussmaul",     # concertmaster (1992–2000)
}


# For instruments the icon is an emoji of the instrument family. For
# vocal types each voice gets its OWN distinctly-coloured letter
# badge (S / Ms / A / C / T / Br / B …) so the table no longer shows
# the same microphone for every singer.
INSTRUMENT_ICON = {
    "piano":          "🎹",
    "harpsichord":    "🎹",
    "organ":          "🎹",
    "violin":         "🎻",
    "violin i":       "🎻",
    "violin ii":      "🎻",
    "viola":          "🎻",
    "cello":          "🎻",
    "violoncello":    "🎻",
    "double bass":    "🎻",
    "harp":           "🎼",
    "guitar":         "🎸",
    "flute":          "🎶",
    "oboe":           "🎶",
    "clarinet":       "🎶",
    "bassoon":        "🎶",
    "english horn":   "🎶",
    "horn":           "🎺",
    "trumpet":        "🎺",
    "trombone":       "🎺",
    "percussion":     "🥁",
}

# Voice-type badges. Each entry is (label, background-colour). Colours
# move along the spectrum red → indigo to mirror the high → low vocal
# range; narrator/speaker get a neutral grey.
VOICE_BADGE = {
    "soprano":        ("S",   "#DC2626"),  # red — highest female
    "boy soprano":    ("S",   "#EC4899"),  # pink — treble
    "mezzo-soprano":  ("Ms",  "#EA580C"),  # orange
    "mezzo":          ("Ms",  "#EA580C"),
    "alto":           ("A",   "#CA8A04"),  # amber
    "contralto":      ("C",   "#65A30D"),  # lime — lowest female
    "tenor":          ("T",   "#0891B2"),  # cyan
    "baritone":       ("Br",  "#2563EB"),  # blue
    "bass-baritone":  ("BBr", "#4F46E5"),  # indigo
    "bass":           ("B",   "#312E81"),  # deep indigo — lowest male
    "narrator":       ("N",   "#6B7280"),  # neutral grey
    "speaker":        ("Sp",  "#6B7280"),
}


def instrument_icon_html(instr: str) -> str:
    """Return the HTML for the small icon rendered before the
    instrument name. Voices get a coloured letter badge so each
    voice type is distinguishable; everything else gets an emoji."""
    key = instr.lower().strip()
    if key in VOICE_BADGE:
        label, color = VOICE_BADGE[key]
        return (
            f'<span class="voice-badge" style="background:{color}"'
            f' aria-hidden="true">{label}</span>'
        )
    emoji = INSTRUMENT_ICON.get(key, "🎵")
    return f'<span class="instr-icon" aria-hidden="true">{emoji}</span>'


# Instrument → list of case-insensitive substrings that mark a work
# as featuring this instrument. Vocal types map to the magic string
# "VOCAL" which is handled by VOCAL_WORK_REGEX.
INSTR_TO_WORK_KEYWORDS = {
    "piano":          ["klavier", "tripelkonzert"],
    "violin":         ["violin", "sinfonia concertante", "doppelkonzert", "tripelkonzert"],
    "violin i":       ["violin", "sinfonia concertante", "doppelkonzert"],
    "violin ii":      ["violin", "sinfonia concertante", "doppelkonzert"],
    "cello":          ["cello", "violoncello", "doppelkonzert", "tripelkonzert"],
    "violoncello":    ["violoncello", "cello", "doppelkonzert", "tripelkonzert"],
    "viola":          ["viola", "bratsche", "sinfonia concertante"],
    "double bass":    ["kontrabass"],
    "flute":          ["flöte", "flute"],
    "oboe":           ["oboe"],
    "english horn":   ["englischhorn", "englisch horn"],
    "clarinet":       ["klarinette", "clarinet"],
    "bassoon":        ["fagott"],
    "horn":           ["horn", "waldhorn"],
    "trumpet":        ["trompete", "trumpet"],
    "trombone":       ["posaune", "trombone"],
    "harp":           ["harfe", "harp"],
    "organ":          ["orgel"],
    "percussion":     ["percussion", "schlagzeug"],
    "guitar":         ["gitarre", "guitar"],
    "harpsichord":    ["cembalo", "harpsichord"],
    "soprano":        ["VOCAL"],
    "boy soprano":    ["VOCAL"],
    "alto":           ["VOCAL"],
    "mezzo":          ["VOCAL"],
    "mezzo-soprano":  ["VOCAL"],
    "contralto":      ["VOCAL"],
    "tenor":          ["VOCAL"],
    "baritone":       ["VOCAL"],
    "bass":           ["VOCAL"],
    "bass-baritone":  ["VOCAL"],
    "narrator":       ["VOCAL"],
    "speaker":        ["VOCAL"],
}

# Words / patterns identifying a work that requires vocal soloists.
VOCAL_WORK_REGEX = re.compile(
    r"\b(lied|requiem|te deum|stabat|missa|kantate|cantata|"
    r"vorspiel und liebestod|choral|"
    r"\(staged opera\)|\(concert performance\)|"
    r"sinfonie nr\. 9 d-moll op\. 125|"
    r"mahler:[^|]*sinfonie nr\. 2|"
    r"mahler:[^|]*sinfonie nr\. 3|"
    r"mahler:[^|]*sinfonie nr\. 4|"
    r"mahler:[^|]*sinfonie nr\. 8|"
    r"wesendonck|rückert|"
    r"matthäus|johannes-passion|"
    r"orph[éeé]e|orfeo|schöpfung|messias)",
    re.IGNORECASE,
)


def parse_soloists(td_html: str):
    """Yield (display_html, plain_name, instrument) for each soloist
    entry in the cell.

    display_html keeps any <a href="…"> anchor so the rendered table
    cell still links out. plain_name is the bare name used for
    de-duplication and BPO-member exclusion.
    """
    if not td_html or "not documented" in td_html.lower():
        return
    # Drop chorus / orchestra annotations after a semicolon (e.g.
    # "; combined chorus — …"). Keep only the soloist list.
    s = td_html.split(";")[0]
    # Soloist entries are split by commas but ONLY commas that sit
    # AFTER a closing ")" — names themselves may contain commas in
    # rare cases. Walk the string and split when we see "), " outside
    # any anchor tag.
    entries = []
    buf = []
    depth_paren = 0
    in_tag = False
    last_close = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
        if not in_tag:
            if ch == "(":
                depth_paren += 1
                last_close = False
            elif ch == ")":
                depth_paren -= 1
                last_close = True
                buf.append(ch)
                i += 1
                continue
            elif ch == "," and depth_paren == 0 and last_close:
                entries.append("".join(buf).strip())
                buf = []
                i += 1
                last_close = False
                continue
            else:
                if not ch.isspace():
                    last_close = False
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        entries.append(tail)

    for entry in entries:
        # Capture optional anchor + name + (instrument)
        m = re.match(
            r'^(\s*<a\s+href="[^"]+"[^>]*>[^<]+</a>|\s*[^()<]+?)'
            r'\s*\(([^()]+)\)\s*$',
            entry,
        )
        if not m:
            continue
        name_html = m.group(1).strip()
        instrument = m.group(2).strip()
        # Plain name with anchor stripped, used for filtering / sort
        plain_name = re.sub(r"<[^>]+>", "", name_html).strip()
        if not plain_name:
            continue
        yield name_html, plain_name, instrument


def is_vocal_work(work_text: str) -> bool:
    return bool(VOCAL_WORK_REGEX.search(work_text))


def works_for_instrument(works, instrument: str):
    """Return the subset of `works` that match this instrument. If no
    keyword maps to the instrument or no work matches, return the
    full list so the soloist still appears against the concert's
    repertoire rather than disappearing."""
    instr_low = re.sub(r"^[0-9]+\.\s*", "", instrument.lower()).strip()
    keywords = INSTR_TO_WORK_KEYWORDS.get(instr_low)
    if not keywords:
        return works
    if keywords == ["VOCAL"]:
        matched = [w for w in works if is_vocal_work(w)]
    else:
        matched = [w for w in works if any(k in w.lower() for k in keywords)]
    return matched or works


def conductor_link(name: str) -> str:
    slug = CONDUCTOR_URL.get(name)
    if not slug:
        return html_lib.escape(name)
    return (
        f'<a href="https://en.wikipedia.org/wiki/{slug}" '
        f'target="_blank" rel="noopener">{html_lib.escape(name)}</a>'
    )


def aggregate(perf_html: str):
    """Walk the source table and accumulate
    counts[(name_html, plain_name, instrument, work, conductor)] = n
    Soloist URLs are preserved through `name_html`.
    """
    m = re.search(r"<tbody>(.*?)</tbody>", perf_html, re.DOTALL)
    if not m:
        return {}
    counts = {}
    for row in re.findall(r"<tr>.*?</tr>", m.group(1), re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 7:
            continue
        conductors_raw = strip_tags(tds[3]).strip()
        if not conductors_raw:
            continue
        conductors = [c.strip() for c in conductors_raw.split("/") if c.strip()]
        works = parse_program(tds[4])
        works = [w for w in works if not is_placeholder(w)]
        if not works:
            continue
        for name_html, plain_name, instrument in parse_soloists(tds[6]):
            if plain_name in BPO_MEMBERS:
                continue
            matched_works = works_for_instrument(works, instrument)
            for w in matched_works:
                for cond in conductors:
                    key = (name_html, plain_name, instrument, w, cond)
                    counts[key] = counts.get(key, 0) + 1
    return counts


# --------------------------------------------------------------------------
#                                 RENDER
# --------------------------------------------------------------------------

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Berliner Philharmoniker — Guest Soloists in Japan</title>
<style>
* {{ box-sizing: border-box; }}
:root {{
  /* Sensible defaults — JS refines these to the live measurements
     for the page-header and the table's column-header row. */
  --header-h: 132px;
  --col-header-h: 38px;
}}
body {{
  font-family: Arial, sans-serif;
  font-size: 13px;
  margin: 0;
  padding: 0 20px 24px;
  color: #222;
  background-color: #FFF8EC;
  background-image: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cg font-family='Georgia,serif'%3E%3Ctext x='15' y='48' font-size='38' transform='rotate(-12 30 38)' fill='%23D97706' fill-opacity='0.16'%3E♫%3C/text%3E%3Ctext x='120' y='30' font-size='26' fill='%230F766E' fill-opacity='0.15'%3E♪%3C/text%3E%3Ctext x='175' y='95' font-size='32' transform='rotate(15 188 80)' fill='%23D97706' fill-opacity='0.16'%3E♬%3C/text%3E%3Ctext x='45' y='125' font-size='30' fill='%239F1239' fill-opacity='0.14'%3E♩%3C/text%3E%3Ctext x='135' y='165' font-size='28' transform='rotate(-8 148 155)' fill='%230F766E' fill-opacity='0.15'%3E♫%3C/text%3E%3Ctext x='80' y='195' font-size='34' fill='%23D97706' fill-opacity='0.16'%3E♬%3C/text%3E%3Ctext x='195' y='185' font-size='22' fill='%239F1239' fill-opacity='0.14'%3E♪%3C/text%3E%3C/g%3E%3C/svg%3E");
  background-repeat: repeat;
}}
.page-header {{
  position: sticky;
  top: 0;
  z-index: 5;
  background-color: #FFF8EC;
  margin: 0 -20px 0;
  padding: 14px 20px 12px;
  box-shadow: 0 2px 0 #FFF8EC;
}}
h1 {{
  font-size: 20px;
  margin: 0 0 4px;
  padding: 0;
  text-align: center;
}}
.subhead {{
  text-align: center;
  font-size: 13px;
  color: #555;
  margin: 0 auto 10px;
  max-width: 1080px;
  line-height: 1.5;
}}
.toolbar {{
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}}
.toolbar a {{
  display: inline-block;
  padding: 6px 14px;
  font-size: 13px;
  text-decoration: none;
  border-radius: 4px;
  color: #fff;
  background: #D97706;
  box-shadow: 0 1px 3px rgba(180,83,9,0.25);
}}
.toolbar a:hover {{ background: #B45309; }}

.wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; min-width: 980px; }}
thead tr.header-row th {{
  position: sticky;
  top: var(--header-h, 0px);
  background: #D97706;
  color: #fff;
  font-weight: bold;
  padding: 8px 10px;
  border: 1px solid #B45309;
  text-align: left;
  white-space: nowrap;
  z-index: 3;
  cursor: pointer;
  user-select: none;
}}
thead tr.header-row th .arrow {{ font-size: 11px; margin-left: 4px; opacity: 0.55; }}
thead tr.header-row th.sort-active .arrow {{ opacity: 1; }}
thead tr.filter-row th {{
  position: sticky;
  top: calc(var(--header-h, 0px) + var(--col-header-h, 36px));
  background: #FDF1E3;
  border: 1px solid #B45309;
  padding: 4px 6px;
  cursor: default;
  z-index: 2;
}}
.instr-icon {{
  display: inline-block;
  margin-right: 6px;
  font-size: 15px;
  vertical-align: -1px;
  line-height: 1;
}}
.voice-badge {{
  display: inline-block;
  min-width: 22px;
  height: 18px;
  margin-right: 6px;
  padding: 0 5px;
  border-radius: 9px;
  text-align: center;
  font-weight: 700;
  font-size: 10.5px;
  line-height: 18px;
  color: #fff;
  letter-spacing: 0.5px;
  vertical-align: 1px;
}}
thead tr.filter-row input {{
  width: 100%;
  font: inherit;
  font-size: 12px;
  padding: 3px 6px;
  border: 1px solid #c9a87a;
  border-radius: 3px;
  background: #fff;
  color: #222;
}}
thead tr.filter-row input:focus {{ outline: 2px solid #D97706; outline-offset: 0; }}
tbody tr.group-odd   {{ background: #fff; }}
tbody tr.group-even  {{ background: #FDF1E3; }}
tbody tr:hover {{ background: #FFF4D9; }}
td {{ padding: 6px 10px; border: 1px solid #ccc; vertical-align: middle; line-height: 1.4; }}
td.cell-soloist    {{ font-weight: 600; white-space: nowrap; vertical-align: top; padding-top: 8px; }}
td.cell-instrument {{ white-space: nowrap; color: #555; vertical-align: top; padding-top: 8px; }}
td.cell-work       {{ min-width: 320px; }}
td.cell-conductor  {{ white-space: nowrap; }}
td.cell-count      {{ text-align: right; font-weight: 700; color: #B45309; font-variant-numeric: tabular-nums; }}
td.cell-count a    {{ color: inherit; border-bottom: 1px dotted #D97706; }}
td.cell-count a:hover {{ color: #7c2d12; border-bottom-style: solid; }}
td a {{ color: #78350F; text-decoration: none; border-bottom: 1px dotted #B45309; }}
td a:hover {{ color: #3F1D08; border-bottom-style: solid; }}
.footnote {{ max-width: 880px; margin: 22px auto 0; text-align: center; font-size: 12px; color: #777; line-height: 1.55; }}
</style>
</head>
<body>
<div class="page-header">
<h1>Berliner Philharmoniker — Guest Soloists in Japan</h1>
<p class="subhead">{rows_count} distinct soloist · work · conductor pairings across {n_soloists} guest soloists. Players who are themselves members of the Berliner Philharmoniker (Bendix-Balgley, Pahud, Mayer, Dohr, Kashimoto, etc.) are excluded. Click any number in the Performances column to drill into the matching rows in the master Performances list.</p>
<p class="toolbar">
  <a href="Performances_in_Japan.html">Performances in Japan</a>
  <a href="Program_Ranking.html">Program Ranking</a>
  <a href="Performances_by_Conductor.html">Performances by Conductor</a>
  <a href="Composer_Chart.html">Performances by Composer</a>
  <a href="index.html">Home</a>
</p>
</div>
<div class="wrap">
<table id="soloists">
<thead>
<tr class="header-row">
  <th data-key="soloist"    data-type="text" class="sort-active" data-sort-dir="asc">Soloist<span class="arrow">▾</span></th>
  <th data-key="instrument" data-type="text">Instrument<span class="arrow">▾</span></th>
  <th data-key="work"       data-type="text">Work<span class="arrow">▾</span></th>
  <th data-key="conductor"  data-type="text">Conductor<span class="arrow">▾</span></th>
  <th data-key="count"      data-type="num" style="text-align:right">Performances<span class="arrow">▾</span></th>
</tr>
<tr class="filter-row">
  <th><input type="search" class="col-filter" data-col="0" placeholder="filter soloist…"></th>
  <th><input type="search" class="col-filter" data-col="1" placeholder="filter instrument…"></th>
  <th><input type="search" class="col-filter" data-col="2" placeholder="filter work…"></th>
  <th><input type="search" class="col-filter" data-col="3" placeholder="filter conductor…"></th>
  <th>&nbsp;</th>
</tr>
</thead>
<tbody>
{body}
</tbody>
</table>
</div>
<p class="footnote">Each row is one (soloist · instrument · work · conductor) combination, with the count of concerts in which that combination appeared. Click any column header to sort, type in a filter box to narrow the list, or click a number in the Performances column to open the matching rows of the master Performances in Japan list.</p>
<script>
(function() {{
  // Measure the sticky page-header + table header-row heights and
  // expose them as CSS variables so each sticky band can be offset
  // by the right amount. Re-measure on resize.
  function measureStickyOffsets() {{
    const ph = document.querySelector('.page-header');
    const hr = document.querySelector('thead tr.header-row');
    if (ph) document.documentElement.style.setProperty('--header-h', ph.offsetHeight + 'px');
    if (hr) document.documentElement.style.setProperty('--col-header-h', hr.offsetHeight + 'px');
  }}
  measureStickyOffsets();
  // Also re-measure after the page is fully laid out (fonts loaded,
  // images sized, etc.) so the defaults declared in :root get
  // replaced with the actual rendered heights.
  if (document.readyState !== 'complete') {{
    window.addEventListener('load', measureStickyOffsets);
  }}
  window.addEventListener('resize', measureStickyOffsets);
  // One more pass on the next animation frame to catch any late
  // reflow (e.g. subhead wrap once the system font kicks in).
  requestAnimationFrame(measureStickyOffsets);

  const table = document.getElementById('soloists');
  const tbody = table.tBodies[0];
  const ths   = table.tHead.querySelector('tr.header-row').cells;
  const fInputs = table.tHead.querySelectorAll('input.col-filter');
  const KEYS = ['soloist','instrument','work','conductor','count'];

  // Build the in-memory row list. The first row of each (soloist,
  // instrument) group is rendered with 5 cells; continuation rows
  // are rendered with only 3 (work, conductor, count). We need to
  // know the soloist & instrument HTML for every row so that we can
  // rebuild rowspans after any sort or filter reorders the table.
  const soloistHTMLByKey    = {{}};
  const instrumentHTMLByKey = {{}};
  for (const tr of tbody.rows) {{
    if (!tr.dataset.cont) {{
      soloistHTMLByKey[tr.dataset.soloistKey]    = tr.cells[0].innerHTML;
      instrumentHTMLByKey[tr.dataset.soloistKey] = tr.cells[1].innerHTML;
    }}
  }}

  const rows = Array.from(tbody.rows).map(tr => {{
    const isCont = !!tr.dataset.cont;
    const offset = isCont ? 0 : 2;
    const key    = tr.dataset.soloistKey;
    return {{
      el:  tr,
      soloistKey: key,
      isCont,
      soloist:    soloistHTMLByKey[key].replace(/<[^>]+>/g, '').trim().toLowerCase(),
      instrument: instrumentHTMLByKey[key].replace(/<[^>]+>/g, '').trim().toLowerCase(),
      work:       tr.cells[offset    ].textContent.trim().toLowerCase(),
      conductor:  tr.cells[offset + 1].textContent.trim().toLowerCase(),
      count:      parseInt(tr.cells[offset + 2].textContent.trim(), 10) || 0,
    }};
  }});

  let activeKey = 'soloist';
  let activeDir = 'asc';

  function flattenRows() {{
    // Restore every row to the 5-cell flat form. Any rowspans get
    // wiped; missing soloist/instrument cells get re-inserted so the
    // row has its own copy of those cells again.
    for (const r of rows) {{
      const tr = r.el;
      if (tr.cells.length < 5) {{
        const wCell = tr.cells[0];
        const tdInstr = document.createElement('td');
        tdInstr.className = 'cell-instrument';
        tdInstr.innerHTML = instrumentHTMLByKey[r.soloistKey];
        tr.insertBefore(tdInstr, wCell);
        const tdSol = document.createElement('td');
        tdSol.className = 'cell-soloist';
        tdSol.innerHTML = soloistHTMLByKey[r.soloistKey];
        tr.insertBefore(tdSol, tdInstr);
      }}
      tr.cells[0].removeAttribute('rowspan');
      tr.cells[1].removeAttribute('rowspan');
    }}
  }}

  function rebuildGroups() {{
    // Step 1: every row owns its own 5 cells with no rowspans.
    flattenRows();
    // Step 2: walk visible rows in DOM order, merge consecutive rows
    //         that share the same (soloist, instrument) key by setting
    //         a rowspan on the first row's cell-soloist / cell-instrument
    //         and removing those cells from the continuation rows.
    const visible = rows.filter(r => r.el.style.display !== 'none');
    let i = 0;
    while (i < visible.length) {{
      let j = i;
      while (j < visible.length && visible[j].soloistKey === visible[i].soloistKey) j++;
      const groupSize = j - i;
      if (groupSize > 1) {{
        visible[i].el.cells[0].rowSpan = groupSize;
        visible[i].el.cells[1].rowSpan = groupSize;
        for (let k = i + 1; k < j; k++) {{
          // Remove cell-soloist (index 0) and cell-instrument (then 0 again).
          visible[k].el.deleteCell(0);
          visible[k].el.deleteCell(0);
        }}
      }}
      i = j;
    }}
    // Step 3: alternate group-level banding so each merged block reads
    //         as a single visual unit.
    let prev = null, stripe = 0;
    for (const r of visible) {{
      if (r.soloistKey !== prev) {{
        if (prev !== null) stripe++;
        prev = r.soloistKey;
      }}
      r.el.classList.toggle('group-odd',  stripe % 2 === 0);
      r.el.classList.toggle('group-even', stripe % 2 === 1);
    }}
  }}

  function applyFilters() {{
    const filters = [];
    fInputs.forEach(inp => filters.push(inp.value.trim().toLowerCase()));
    // Numeric filter: accept "5", "5+", ">= 5", ">5"
    let minCount = null;
    const cf = filters[4];
    if (cf) {{
      const m = cf.match(/(?:>=?|≥)?\s*(\d+)\s*\+?/);
      if (m) minCount = parseInt(m[1], 10);
    }}
    for (const r of rows) {{
      let visible = true;
      for (let i = 0; i < 4; i++) {{
        if (filters[i] && !r[KEYS[i]].includes(filters[i])) {{ visible = false; break; }}
      }}
      if (visible && minCount !== null && r.count < minCount) visible = false;
      r.el.style.display = visible ? '' : 'none';
    }}
    rebuildGroups();
  }}

  function applySort() {{
    rows.sort((a, b) => {{
      let av = a[activeKey], bv = b[activeKey];
      if (av === bv) {{
        // Keep each soloist's rows together when the user sorts by
        // something other than soloist, so the merge still reads.
        if (activeKey !== 'soloist') {{
          if (a.soloist !== b.soloist) return a.soloist < b.soloist ? -1 : 1;
        }}
        return 0;
      }}
      return (av < bv ? -1 : 1) * (activeDir === 'asc' ? 1 : -1);
    }});
    flattenRows();   // ensure every row owns its full cell set before reordering
    const frag = document.createDocumentFragment();
    for (const r of rows) frag.appendChild(r.el);
    tbody.appendChild(frag);
    rebuildGroups();
  }}

  for (let i = 0; i < ths.length; i++) {{
    ths[i].addEventListener('click', () => {{
      const key = ths[i].dataset.key;
      if (key === activeKey) {{
        activeDir = (activeDir === 'asc') ? 'desc' : 'asc';
      }} else {{
        activeKey = key;
        activeDir = (ths[i].dataset.type === 'num') ? 'desc' : 'asc';
      }}
      for (const th of ths) th.classList.remove('sort-active');
      ths[i].classList.add('sort-active');
      applySort();
    }});
  }}
  fInputs.forEach(inp => inp.addEventListener('input', applyFilters));

  // Initial render already has rowspans baked in by the generator,
  // so we only need to set the group-banding classes once.
  let prev = null, stripe = 0;
  for (const r of rows) {{
    if (r.soloistKey !== prev) {{
      if (prev !== null) stripe++;
      prev = r.soloistKey;
    }}
    r.el.classList.toggle('group-odd',  stripe % 2 === 0);
    r.el.classList.toggle('group-even', stripe % 2 === 1);
  }}
}})();
</script>
</body>
</html>
"""


def render(counts: dict) -> str:
    # Strict alphabetical default sort. The Soloist + Instrument cells
    # are then merged via rowspan for every adjacent group sharing the
    # same (soloist, instrument).
    items = sorted(
        counts.items(),
        key=lambda kv: (
            kv[0][1].lower(),   # soloist plain name
            kv[0][2].lower(),   # instrument
            kv[0][3].lower(),   # work
            kv[0][4].lower(),   # conductor
        ),
    )

    # Pre-compute group sizes so the first row in each group can carry
    # the rowspan on the merged cells.
    body_rows = []
    distinct_soloists = set()
    n = len(items)
    i = 0
    while i < n:
        (name_html_i, plain_name_i, instrument_i, *_), _ = items[i]
        j = i
        while (j < n
               and items[j][0][1] == plain_name_i
               and items[j][0][2] == instrument_i):
            j += 1
        group_size = j - i
        key = html_lib.escape(plain_name_i.lower() + "|" + instrument_i.lower(), quote=True)
        for k in range(i, j):
            (name_html, plain_name, instrument, work, conductor), count = items[k]
            distinct_soloists.add(plain_name)
            if k == i:
                rowspan = f' rowspan="{group_size}"' if group_size > 1 else ""
                icon_html = instrument_icon_html(instrument)
                row = (
                    f'<tr data-soloist-key="{key}">'
                    f'<td class="cell-soloist"{rowspan}>{name_html}</td>'
                    f'<td class="cell-instrument"{rowspan}>'
                    f'{icon_html}{html_lib.escape(instrument)}</td>'
                )
            else:
                row = f'<tr data-soloist-key="{key}" data-cont="1">'
            # Click-through to the matching rows in the master
            # Performances list: ?soloist=…&conductor=…&work=… are
            # substring-matched against the source table.
            work_plain = re.sub(r"<[^>]+>", "", work).strip()
            drill_url = (
                f"Performances_in_Japan.html?"
                f"soloist={quote(plain_name)}"
                f"&conductor={quote(conductor)}"
                f"&work={quote(work_plain)}"
            )
            row += (
                f'<td class="cell-work">{work}</td>'
                f'<td class="cell-conductor">{conductor_link(conductor)}</td>'
                f'<td class="cell-count">'
                f'<a href="{drill_url}" title="Show these performances in the master list">{count}</a>'
                f'</td>'
                f'</tr>'
            )
            body_rows.append(row)
        i = j

    return PAGE_TEMPLATE.format(
        rows_count=len(items),
        n_soloists=len(distinct_soloists),
        body="\n".join(body_rows),
    )


def main():
    src = Path("Berliner_Philharmoniker_in_Japan/Performances_in_Japan.html")
    out = Path("Berliner_Philharmoniker_in_Japan/Guest_Soloists.html")
    counts = aggregate(src.read_text(encoding="utf-8"))
    out.write_text(render(counts), encoding="utf-8")
    print(f"Wrote {out}")
    soloists = {key[1] for key in counts}
    print(f"  {len(counts)} rows, {len(soloists)} distinct soloists, "
          f"{sum(counts.values())} performance attributions")


if __name__ == "__main__":
    main()
