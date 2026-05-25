"""Generate Audience Analysis page for BPO or WPO.

Aggregates audience (= venue capacity) across composers, works, and
conductors from Concerts_in_Japan.html, using capacities defined in
Concert_Halls.html. Renders three horizontal-bar charts on one page.

Usage:
    python3 audience_analysis.py bpo
    python3 audience_analysis.py wpo
"""
import re
import sys
from collections import defaultdict
from urllib.parse import quote as urlquote


HALL_SUFFIX_RE = re.compile(
    r',\s*(?:main|large|grand|concert|symphony|forest|kokusai|kobelco)\s+hall.*$',
    re.IGNORECASE,
)


def load_capacities(halls_html: str):
    """Return list of (name_lower, capacity_int, city_lower) tuples for
    each row in Concert_Halls.html that has a numeric capacity."""
    entries = []
    pattern = re.compile(
        r'<tr><td class="hall">(.*?)</td><td>([^<]*)</td><td>[^<]*</td>'
        r'<td class="cap">([^<]+)</td></tr>',
        re.DOTALL,
    )
    for m in pattern.finditer(halls_html):
        name_html, city, cap = m.group(1), m.group(2), m.group(3)
        name_html = re.sub(r'<div class="note">.*?</div>', '', name_html, flags=re.DOTALL)
        name = re.sub(r'<[^>]+>', '', name_html).strip()
        cap = cap.strip().replace(',', '')
        if not cap.isdigit():
            continue
        entries.append((name.lower(), int(cap), city.strip().lower()))
    return entries


def parse_concerts(concerts_html: str):
    """Yield one dict per <tr> in the concerts <tbody>."""
    m = re.search(r"<tbody>(.*?)</tbody>", concerts_html, re.DOTALL)
    if not m:
        return
    tbody = m.group(1)
    for row_m in re.finditer(r'<tr([^>]*)>(.*?)</tr>', tbody, re.DOTALL):
        attrs, row_html = row_m.groups()
        is_future = 'class="future"' in attrs
        tds = re.findall(r"<td>(.*?)</td>", row_html, re.DOTALL)
        if len(tds) < 5:
            continue
        try:
            year = int(re.sub(r"<[^>]+>", "", tds[0]).strip())
        except ValueError:
            continue
        city_hall_txt = re.sub(r"<[^>]+>", " ", tds[2])
        city_hall_txt = re.sub(r"\s+", " ", city_hall_txt).strip()
        m_h = re.search(r"\(([^)]+)\)\s*$", city_hall_txt)
        if m_h:
            hall = m_h.group(1).strip()
            city = city_hall_txt[: m_h.start()].strip()
        else:
            hall = ""
            city = city_hall_txt
        cond_txt = re.sub(r"<[^>]+>", "", tds[3]).strip()
        conductors = [c.strip() for c in cond_txt.split("/") if c.strip()]
        prog_html = tds[4]
        works = []
        for line in re.split(r"<br\s*/?>", prog_html):
            txt = re.sub(r"<[^>]+>", "", line).strip()
            if txt:
                works.append(txt)
        yield {
            "year": year, "city": city, "hall": hall,
            "conductors": conductors, "works": works,
            "future": is_future,
        }


def lookup_capacity(hall: str, city: str, entries) -> int:
    """Score-based capacity lookup. Prefers exact name match, then a
    same-city substring match, then any substring match, then default."""
    if hall:
        key = hall.lower().strip()
        city_lc = city.lower().strip()
        candidates = []
        for name, cap, ecity in entries:
            # "Old X" must never match "X" (and vice versa) — historic
            # predecessors have their own row when known.
            if key.startswith("old ") and key[4:].strip() == name:
                continue
            if name.startswith("old ") and name[4:].strip() == key:
                continue
            base = HALL_SUFFIX_RE.sub('', name).strip()
            score = 0
            if name == key or base == key:
                score = 100
            elif key in name or name in key:
                score = 60
            elif key in base or base in key:
                score = 55
            if score == 0:
                continue
            if ecity == city_lc:
                score += 30
            candidates.append((score, cap))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    if city.lower().strip() in ("tokyo", "osaka"):
        return 1600
    return 1200


def round_down_100(n: int) -> int:
    return (n // 100) * 100


def aggregate(concerts, entries):
    composer_a: dict = defaultdict(int)
    work_a: dict = defaultdict(int)
    conductor_a: dict = defaultdict(int)
    n_concerts = 0
    total = 0
    for c in concerts:
        if c["future"]:
            continue
        n_concerts += 1
        cap = lookup_capacity(c["hall"], c["city"], entries)
        total += cap
        composers_in = set()
        for w in c["works"]:
            if ":" in w:
                composers_in.add(w.split(":", 1)[0].strip())
        for comp in composers_in:
            composer_a[comp] += cap
        for w in set(c["works"]):
            work_a[w] += cap
        for cond in c["conductors"]:
            conductor_a[cond] += cap
    sort_desc = lambda d: sorted(
        [(k, round_down_100(v)) for k, v in d.items()],
        key=lambda x: (-x[1], x[0]),
    )
    return {
        "composer": sort_desc(composer_a),
        "work": sort_desc(work_a),
        "conductor": sort_desc(conductor_a),
        "n_concerts": n_concerts,
        "total": round_down_100(total),
    }


def escape_html(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))


def fmt_int(n: int) -> str:
    return f"{n:,}"


def build_bar_section(title, anchor, items, max_v, visible_top,
                      link_param, accent):
    if not items:
        return f'<section class="chart-section" id="section-{anchor}"><h2>{title}</h2><p>No data.</p></section>'
    rows = []
    for i, (label, v) in enumerate(items):
        rank = i + 1
        hidden = " hidden" if rank > visible_top else ""
        width = (v / max_v * 100) if max_v else 0
        href = f'../{"Berliner Philharmoniker" if accent == "#D97706" else "Wiener Philharmoniker"}/Concerts_in_Japan.html'
        # Use a relative link (we are inside the orchestra dir)
        href = f'Concerts_in_Japan.html?{link_param}={urlquote(label)}'
        rows.append(
            f'<div class="bar-row{hidden}">'
            f'<span class="rank">{rank}</span>'
            f'<a class="bar-name" href="{href}" target="_blank" rel="noopener" '
            f'title="Open concerts contributing to this {anchor} total in a new tab">'
            f'{escape_html(label)}</a>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{width:.2f}%;"></span></span>'
            f'<span class="bar-value">{fmt_int(v)}</span>'
            f'</div>'
        )
    rows_html = "\n".join(rows)
    show_all = (
        f'<button class="show-all-toggle" data-section="{anchor}">'
        f'Show all {len(items)}</button>'
        if len(items) > visible_top else ''
    )
    return (
        f'<section class="chart-section" id="section-{anchor}">'
        f'<h2 id="{anchor}">{title}</h2>'
        f'<div class="bar-list">{rows_html}</div>'
        f'{show_all}'
        f'</section>'
    )


def build_page(concerts_html, halls_html, orchestra="bpo"):
    entries = load_capacities(halls_html)
    concerts = list(parse_concerts(concerts_html))
    data = aggregate(concerts, entries)

    if orchestra == "bpo":
        title = "Berliner Philharmoniker — Audience Analysis"
        bgcol = "#FFF8EC"
        accent = "#D97706"
        accent_d = "#B45309"
        accent_soft = "rgba(180,83,9,0.20)"
        accent_tint = "rgba(217,119,6,0.10)"
        toolbar_links = (
            '  <a href="Concerts_in_Japan.html">Concerts in Japan</a>\n'
            '  <a href="Program_Ranking.html">Program Ranking</a>\n'
            '  <a href="Composer_Chart.html">Performances by Composer</a>\n'
            '  <a href="Performances_by_Conductor.html">Performances by Conductor</a>\n'
            '  <a href="Performances_by_Prefecture.html">Performances by Prefecture</a>\n'
            '  <a href="Program_Trend_by_Era.html">Program Trend by Era</a>\n'
            '  <a href="../Concert_Halls.html">Concert Halls</a>\n'
            '  <a href="index.html">Home</a>'
        )
    else:
        title = "Wiener Philharmoniker — Audience Analysis"
        bgcol = "#FBF1F4"
        accent = "#9F1239"
        accent_d = "#831234"
        accent_soft = "rgba(159,18,57,0.20)"
        accent_tint = "rgba(159,18,57,0.08)"
        toolbar_links = (
            '  <a href="Concerts_in_Japan.html">Concerts in Japan</a>\n'
            '  <a href="Program_Ranking.html">Program Ranking</a>\n'
            '  <a href="Composer_Chart.html">Performances by Composer</a>\n'
            '  <a href="Performances_by_Conductor.html">Performances by Conductor</a>\n'
            '  <a href="Performances_by_Prefecture.html">Performances by Prefecture</a>\n'
            '  <a href="Program_Trend_by_Era.html">Program Trend by Era</a>\n'
            '  <a href="../Concert_Halls.html">Concert Halls</a>\n'
            '  <a href="index.html">Home</a>'
        )

    comp_max = data["composer"][0][1] if data["composer"] else 1
    work_max = data["work"][0][1] if data["work"] else 1
    cond_max = data["conductor"][0][1] if data["conductor"] else 1

    comp_section = build_bar_section(
        "Audience by Composer", "composer", data["composer"], comp_max,
        visible_top=20, link_param="composer", accent=accent,
    )
    work_section = build_bar_section(
        "Audience by Work", "work", data["work"], work_max,
        visible_top=25, link_param="work", accent=accent,
    )
    cond_section = build_bar_section(
        "Audience by Conductor", "conductor", data["conductor"], cond_max,
        visible_top=100, link_param="conductor", accent=accent,
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
  font-size: 14px;
  margin: 0;
  padding: 24px 20px 60px;
  color: #222;
  background: {bgcol};
}}
.container {{ max-width: 1180px; margin: 0 auto; }}
.page-header {{ margin-bottom: 20px; }}
h1 {{ font-size: 22px; margin: 0 0 6px; text-align: center; color: #000; }}
.subhead {{ text-align: center; font-size: 13px; color: #555; margin: 0 0 12px; }}
.toolbar {{
  text-align: center;
  margin: 0;
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
  background: {accent};
  box-shadow: 0 1px 3px {accent_soft};
}}
.toolbar a:hover {{ background: {accent_d}; }}

.chart-section {{
  margin: 28px 0;
  background: rgba(255,255,255,0.85);
  border: 1px solid {accent_soft};
  border-radius: 8px;
  padding: 18px 22px 22px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}}
.chart-section h2 {{
  margin: 0 0 14px;
  padding: 0 0 6px;
  border-bottom: 2px solid {accent};
  color: {accent_d};
  font-size: 18px;
  letter-spacing: 0.5px;
}}

.bar-row {{
  display: grid;
  grid-template-columns: 36px minmax(180px, 260px) 1fr 90px;
  gap: 12px;
  align-items: center;
  padding: 4px 0;
  font-size: 13px;
}}
.bar-row.hidden {{ display: none; }}
.rank {{
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: #888;
  font-size: 11.5px;
}}
.bar-name {{
  color: #1c1917;
  text-decoration: none;
  border-bottom: 1px dotted {accent_soft};
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}}
.bar-name:hover {{ color: {accent_d}; border-bottom-color: {accent}; }}
.bar-track {{
  background: {accent_tint};
  border-radius: 3px;
  height: 14px;
  display: block;
  overflow: hidden;
}}
.bar-fill {{
  background: {accent};
  height: 100%;
  border-radius: 3px;
  display: block;
}}
.bar-value {{
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: {accent_d};
}}

#section-work .bar-row {{
  grid-template-columns: 36px minmax(280px, 460px) 1fr 90px;
}}
#section-conductor .bar-row {{
  grid-template-columns: 36px minmax(180px, 240px) 1fr 90px;
}}

.show-all-toggle {{
  margin-top: 12px;
  background: transparent;
  color: {accent_d};
  border: 1px solid {accent_soft};
  border-radius: 4px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
}}
.show-all-toggle:hover {{ background: {accent_tint}; }}

.footnote {{
  max-width: 820px;
  margin: 32px auto 0;
  text-align: center;
  font-size: 12px;
  color: #777;
  line-height: 1.65;
}}
.footnote a {{ color: {accent_d}; }}

@media (max-width: 720px) {{
  .bar-row,
  #section-work .bar-row,
  #section-conductor .bar-row {{
    grid-template-columns: 28px 1fr 80px;
    row-gap: 2px;
  }}
  .bar-track {{ grid-column: 1 / -1; }}
}}
</style>
</head>
<body>
<div class="container">
<div class="page-header">
<h1>{title}</h1>
<p class="subhead">Cumulative audience across {fmt_int(data["n_concerts"])} concerts (sum of hall capacities). Click any bar to open the contributing concerts.</p>
<p class="toolbar">
{toolbar_links}
</p>
</div>

{comp_section}
{work_section}
{cond_section}

<p class="footnote">
Each concert's audience equals the venue's seating capacity (sold-out assumption). When the venue isn't in
the <a href="../Concert_Halls.html">Concert Halls</a> reference, the default is 1,600 seats for Tokyo and
Osaka and 1,200 seats elsewhere. Totals are rounded down to the nearest 100. The 2026 planned tour is excluded.
</p>

</div>
<script>
document.querySelectorAll('.show-all-toggle').forEach(function (btn) {{
  btn.addEventListener('click', function () {{
    var section = btn.dataset.section;
    document.querySelectorAll('#section-' + section + ' .bar-row.hidden').forEach(function (r) {{
      r.classList.remove('hidden');
    }});
    btn.style.display = 'none';
  }});
}});
</script>
</body>
</html>
"""


def main():
    orchestra = sys.argv[1].lower() if len(sys.argv) > 1 else "bpo"
    if orchestra == "bpo":
        in_path = "Berliner Philharmoniker/Concerts_in_Japan.html"
        out_path = "Berliner Philharmoniker/Audience_Analysis.html"
    elif orchestra == "wpo":
        in_path = "Wiener Philharmoniker/Concerts_in_Japan.html"
        out_path = "Wiener Philharmoniker/Audience_Analysis.html"
    else:
        print(f"Unknown orchestra '{orchestra}'", file=sys.stderr)
        sys.exit(1)
    with open("Concert_Halls.html", encoding="utf-8") as f:
        halls_html = f.read()
    with open(in_path, encoding="utf-8") as f:
        concerts_html = f.read()
    page = build_page(concerts_html, halls_html, orchestra)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    data = aggregate(list(parse_concerts(concerts_html)), load_capacities(halls_html))
    print(f"Wrote {out_path}")
    print(f"  {data['n_concerts']} concerts, total audience {fmt_int(data['total'])}")
    print(f"  composers={len(data['composer'])}, works={len(data['work'])}, conductors={len(data['conductor'])}")


if __name__ == "__main__":
    main()
