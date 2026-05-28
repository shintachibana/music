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
}


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
body {{
  font-family: Arial, sans-serif;
  font-size: 13px;
  margin: 0;
  padding: 60px 20px;
  color: #222;
  background-color: #FFF8EC;
  background-image: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cg font-family='Georgia,serif'%3E%3Ctext x='15' y='48' font-size='38' transform='rotate(-12 30 38)' fill='%23D97706' fill-opacity='0.16'%3E♫%3C/text%3E%3Ctext x='120' y='30' font-size='26' fill='%230F766E' fill-opacity='0.15'%3E♪%3C/text%3E%3Ctext x='175' y='95' font-size='32' transform='rotate(15 188 80)' fill='%23D97706' fill-opacity='0.16'%3E♬%3C/text%3E%3Ctext x='45' y='125' font-size='30' fill='%239F1239' fill-opacity='0.14'%3E♩%3C/text%3E%3Ctext x='135' y='165' font-size='28' transform='rotate(-8 148 155)' fill='%230F766E' fill-opacity='0.15'%3E♫%3C/text%3E%3Ctext x='80' y='195' font-size='34' fill='%23D97706' fill-opacity='0.16'%3E♬%3C/text%3E%3Ctext x='195' y='185' font-size='22' fill='%239F1239' fill-opacity='0.14'%3E♪%3C/text%3E%3C/g%3E%3C/svg%3E");
  background-repeat: repeat;
}}
h1 {{
  font-size: 20px;
  margin: 0;
  padding: 0 0 18px;
  text-align: center;
  position: sticky;
  top: 0;
  z-index: 5;
  background-color: #FFF8EC;
}}
.subhead {{
  text-align: center;
  font-size: 13px;
  color: #555;
  margin: -8px 0 14px;
}}
.toolbar {{
  position: sticky;
  top: 52px;
  z-index: 4;
  background-color: #FFF8EC;
  margin: 0;
  padding: 4px 0 18px;
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
thead th {{
  position: sticky;
  top: 0;
  background: #D97706;
  color: #fff;
  font-weight: bold;
  padding: 8px 10px;
  border: 1px solid #B45309;
  text-align: left;
  white-space: nowrap;
  z-index: 2;
  cursor: pointer;
  user-select: none;
}}
thead th .arrow {{ font-size: 11px; margin-left: 4px; opacity: 0.55; }}
thead th.sort-active .arrow {{ opacity: 1; }}
thead tr.filter-row th {{
  position: sticky;
  top: 36px;
  background: #FDF1E3;
  border: 1px solid #B45309;
  padding: 4px 6px;
  cursor: default;
  z-index: 2;
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
td.cell-soloist    {{ font-weight: 600; white-space: nowrap; }}
td.cell-instrument {{ white-space: nowrap; color: #555; }}
td.cell-work       {{ min-width: 320px; }}
td.cell-conductor  {{ white-space: nowrap; }}
td.cell-count      {{ text-align: right; font-weight: 700; color: #B45309; font-variant-numeric: tabular-nums; }}
/* Continuation rows visually merge with the row above for the
   soloist + instrument cells: top border is removed and the cell
   text is hidden but the cell still occupies its grid slot. */
tr.cont td.cell-soloist .cell-text,
tr.cont td.cell-instrument .cell-text {{ visibility: hidden; }}
tr.cont td.cell-soloist,
tr.cont td.cell-instrument {{ border-top: 1px solid transparent; }}
td a {{ color: #78350F; text-decoration: none; border-bottom: 1px dotted #B45309; }}
td a:hover {{ color: #3F1D08; border-bottom-style: solid; }}
.footnote {{ max-width: 880px; margin: 22px auto 0; text-align: center; font-size: 12px; color: #777; line-height: 1.55; }}
</style>
</head>
<body>
<h1>Berliner Philharmoniker — Guest Soloists in Japan</h1>
<p class="subhead">{rows_count} distinct soloist · work · conductor pairings across {n_soloists} guest soloists. Players who are themselves members of the Berliner Philharmoniker (Bendix-Balgley, Pahud, Mayer, Dohr, Kashimoto, etc.) are excluded.</p>
<p class="toolbar">
  <a href="Performances_in_Japan.html">Performances in Japan</a>
  <a href="Program_Ranking.html">Program Ranking</a>
  <a href="Performances_by_Conductor.html">Performances by Conductor</a>
  <a href="Composer_Chart.html">Performances by Composer</a>
  <a href="index.html">Home</a>
</p>
<div class="wrap">
<table id="soloists">
<thead>
<tr>
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
  <th><input type="search" class="col-filter" data-col="4" placeholder="≥ count"></th>
</tr>
</thead>
<tbody>
{body}
</tbody>
</table>
</div>
<p class="footnote">Each row is one (soloist · instrument · work · conductor) combination, with the count of concerts in which that combination appeared. Click any column header to sort. Type in a filter box to narrow the list — the Performances filter accepts plain text ("3") or "≥ 3" / "3+" to mean "at least 3".</p>
<script>
(function() {{
  const table = document.getElementById('soloists');
  const tbody = table.tBodies[0];
  const ths   = table.tHead.rows[0].cells;
  const fInputs = table.tHead.querySelectorAll('input.col-filter');
  const KEYS = ['soloist','instrument','work','conductor','count'];
  // Cache each row's lowercased cell text + numeric count for filtering / sorting.
  const rows  = Array.from(tbody.rows).map(tr => ({{
    el:  tr,
    soloist:    tr.cells[0].textContent.trim().toLowerCase(),
    instrument: tr.cells[1].textContent.trim().toLowerCase(),
    work:       tr.cells[2].textContent.trim().toLowerCase(),
    conductor:  tr.cells[3].textContent.trim().toLowerCase(),
    count:      parseInt(tr.cells[4].textContent.trim(), 10) || 0,
    soloistKey: tr.dataset.soloistKey,
  }}));
  let activeKey = 'soloist';
  let activeDir = 'asc';

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
    recomputeContinuation();
  }}

  function recomputeContinuation() {{
    let prev = null;
    let stripe = 0;
    for (const r of rows) {{
      if (r.el.style.display === 'none') continue;
      if (r.soloistKey === prev) {{
        r.el.classList.add('cont');
      }} else {{
        r.el.classList.remove('cont');
        if (prev !== null) stripe++;  // alternate banding per soloist group
        prev = r.soloistKey;
      }}
      // Banding follows the soloist group, not the raw row index, so
      // merged groups read as a single visual block.
      r.el.classList.toggle('group-odd',  stripe % 2 === 0);
      r.el.classList.toggle('group-even', stripe % 2 === 1);
    }}
  }}

  function applySort() {{
    rows.sort((a, b) => {{
      let av = a[activeKey], bv = b[activeKey];
      if (av === bv) {{
        // Secondary sort: keep each soloist's rows together when
        // the user sorts by something other than soloist, so the
        // merged-cell layout still makes sense.
        if (activeKey !== 'soloist') {{
          if (a.soloist !== b.soloist) return a.soloist < b.soloist ? -1 : 1;
          if (a.count !== b.count) return b.count - a.count;
        }}
        return 0;
      }}
      return (av < bv ? -1 : 1) * (activeDir === 'asc' ? 1 : -1);
    }});
    const frag = document.createDocumentFragment();
    for (const r of rows) frag.appendChild(r.el);
    tbody.appendChild(frag);
    recomputeContinuation();
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

  recomputeContinuation();
}})();
</script>
</body>
</html>
"""


def render(counts: dict) -> str:
    # Default sort: keep each soloist's rows adjacent so the merged
    # name+instrument cell makes sense. Within a soloist, list the
    # most-performed pairings first.
    items = sorted(
        counts.items(),
        key=lambda kv: (
            kv[0][1].lower(),   # soloist plain name
            kv[0][2].lower(),   # instrument
            -kv[1],             # performances desc
            kv[0][3].lower(),   # work
            kv[0][4].lower(),   # conductor
        ),
    )
    body_rows = []
    distinct_soloists = set()
    for (name_html, plain_name, instrument, work, conductor), n in items:
        distinct_soloists.add(plain_name)
        key = html_lib.escape(plain_name.lower() + "|" + instrument.lower(), quote=True)
        body_rows.append(
            f'<tr data-soloist-key="{key}">'
            f'<td class="cell-soloist"><span class="cell-text">{name_html}</span></td>'
            f'<td class="cell-instrument"><span class="cell-text">{html_lib.escape(instrument)}</span></td>'
            f'<td class="cell-work"><span class="cell-text">{work}</span></td>'
            f'<td class="cell-conductor"><span class="cell-text">{conductor_link(conductor)}</span></td>'
            f'<td class="cell-count"><span class="cell-text">{n}</span></td>'
            f'</tr>'
        )
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
