"""Generate the BPO Program Trend by Era page.

A two-column layout:
  • Left timeline: every year from 1955-2025 listed in a sticky
    sidebar, banded by chief conductor with Japan-tour markers.
  • Right column: hand-written decade-by-decade analysis of the
    programming tendencies on tour.

Usage:
    python3 era_trend.py     # → Berliner Philharmoniker/Program_Trend_by_Era.html
"""
import re
import sys


# (start_year, end_year, name, wiki_slug, css_class)
CHIEFS = [
    (1955, 1989, "Herbert von Karajan", "Herbert_von_Karajan", "karajan"),
    (1990, 2001, "Claudio Abbado",      "Claudio_Abbado",      "abbado"),
    (2002, 2018, "Simon Rattle",        "Simon_Rattle",        "rattle"),
    (2019, 2026, "Kirill Petrenko",     "Kirill_Petrenko",     "petrenko"),
]
# Per-chief accent colour for the timeline band — bright but still
# readable with white text on the tour pill.
CHIEF_COLOUR = {
    "karajan":  "#F59E0B",   # amber-500 — Karajan era
    "abbado":   "#3B82F6",   # blue-500 — Abbado era
    "rattle":   "#14B8A6",   # teal-500 — Rattle era
    "petrenko": "#E11D48",   # rose-600 — Petrenko era
}


# Decade-by-decade analysis paragraphs. Each entry: list of paragraphs.
DECADE_ANALYSIS = {
    "1950s": [
        "Karajan elected chief in April 1955 begins shaping the post-war BPO. "
        "The first Japan tour follows in November 1957 — sixteen concerts "
        "across nine cities, almost all conducted by Karajan with Wilhelm "
        "Schüchter covering one date.",
        "Programmes are essentially the canonical German curriculum: "
        "Beethoven 3 and 5 anchor most evenings, Brahms 1 and 2 alternate, "
        "Wagner's <em>Meistersinger</em> Vorspiel and <em>Tannhäuser</em> "
        "Ouvertüre open. Modernism is represented only by Hindemith's "
        "<em>Mathis der Maler</em> Sinfonie — a piece Hindemith himself "
        "would conduct in Japan the following year with the WPO.",
    ],
    "1960s": [
        "Two Japan tours, both with Karajan and entirely his programme. "
        "1966 is a monumental Beethoven cycle in Tokyo Bunka Kaikan: "
        "all nine symphonies plus three overtures across five evenings "
        "(April 12 – 16), followed by a national tour reprising "
        "<em>Aus der Neuen Welt</em>, Brahms 2 and Mozart 25 in twelve "
        "more cities up to early May. The cycle establishes a touring "
        "template — the BPO arrives, presents an integral cycle in Tokyo, "
        "and re-dresses excerpts for the regional venues.",
    ],
    "1970s": [
        "1970 Osaka brings the second complete Beethoven cycle, this time "
        "as part of the EXPO '70 cultural programme. Three more tours follow "
        "(1973, 1977, 1979), all Karajan, all canon-heavy. Brahms cycles "
        "join Beethoven cycles as a touring genre; Schubert <em>Unvollendete</em> "
        "becomes a fixed encore-symphony.",
        "Bruckner is largely absent from the touring repertoire — Karajan "
        "kept it for the home seasons and the major European cycles — but "
        "R. Strauss tone poems and Wagner overtures fill the supplement slot.",
    ],
    "1980s": [
        "Karajan's final decade with the orchestra: 1981, 1984, 1986 and "
        "1988 Japan tours. The Beethoven / Brahms axis stays central, but "
        "deeper Romantic and turn-of-century works enter the rotation — "
        "Tchaikovsky 6 (1988), Mussorgsky <em>Pictures</em> in Ravel's "
        "orchestration, R. Strauss <em>Heldenleben</em> and Don Juan.",
        "Health deteriorates from the mid-decade; April 1989 resignation; "
        "Karajan dies July 1989. The last touring relationship before the "
        "handover is unmistakeably canon-anchored.",
    ],
    "1990s": [
        "Abbado is elected October 1989 and takes office in 1990. "
        "Programming pivots immediately. Mahler enters the touring core: "
        "Mahler 9 in 1994, Mahler 2 <em>Auferstehung</em> with the Swedish "
        "Radio Chorus across multiple Tokyo + Osaka dates in 1996, paired "
        "with Beethoven 9.",
        "1989's staged tour had already presented Rossini's <em>Il viaggio "
        "a Reims</em> at Tokyo Bunka Kaikan (Karajan-Abbado handover year), "
        "and Berg's <em>Wozzeck</em> at NHK Hall — the Second Viennese "
        "School returns to the touring stage. By 1998 the BPO is touring "
        "with Stravinsky <em>L'oiseau de feu</em> and a far more elastic "
        "programme palette than under Karajan.",
    ],
    "2000s": [
        "2000 closes the Abbado era with a staged <em>Tristan und Isolde</em> "
        "(three nights at Tokyo Bunka Kaikan) plus a Beethoven cycle. "
        "Rattle takes over in September 2002.",
        "2004 brings Rattle's first BPO Japan tour with Mahler 5 and a "
        "Dvořák / Wagner / Brahms 2 framework. 2005 keeps the canon but "
        "with a more curatorial register; 2008 returns with Brahms 1 & 2 in "
        "the new Hyogo Performing Arts Centre. The decade marks the BPO's "
        "first appearances in mid-size regional halls outside the Tokyo / "
        "Osaka axis.",
    ],
    "2010s": [
        "Rattle's peak years on the BPO touring stage. Four tours (2011, "
        "2013, 2016, 2017) and the contemporary fringe widens dramatically: "
        "Boulez <em>Notations</em>, Magnus Lindberg <em>Aura</em>, Unsuk "
        "Chin's <em>Šu</em>, Adès. Hosokawa Toshio's <em>Circulating "
        "Ocean</em> (2017) is the orchestra's first direct engagement with "
        "a Japanese composer on tour.",
        "Bruckner cycles continue and the Brahms / Beethoven core stays "
        "intact, but the post-1950 European modernist line is now a "
        "regular feature, not a one-off.",
    ],
    "2020s": [
        "Petrenko takes over August 2019 and tours Japan in November of "
        "the same year — Bruckner 8 in Nagoya, Osaka, Fukuoka and Suntory; "
        "R. Strauss <em>Don Quixote</em> (with Quandt) and Beethoven "
        "<em>Eroica</em> on the other half. COVID erases 2020-2022 tours.",
        "2023 returns the orchestra with a denser Austro-German / "
        "central-European-modern axis: Berg <em>Drei Orchesterstücke</em>, "
        "Reger orchestral works (almost unique to Petrenko in our data), "
        "more Strauss. 2025 follows the same line. The Petrenko era so far "
        "trades Rattle's contemporary breadth for darker, denser Austro-"
        "German Romantic-modern repertoire.",
    ],
}


def get_tour_counts(concerts_html: str) -> dict:
    """Return {year: concert_count} — one entry per row of the BPO
    concerts table, summed by year."""
    counts: dict[int, int] = {}
    for y in re.findall(r"<tr><td>(\d{4})</td>", concerts_html):
        year = int(y)
        counts[year] = counts.get(year, 0) + 1
    return counts


def get_chief_for_year(year: int):
    for start, end, name, slug, css_class in CHIEFS:
        if start <= year <= end:
            return name, slug, css_class
    return None


def build_timeline_row(year: int, tour_counts: dict) -> str:
    chief = get_chief_for_year(year)
    n_concerts = tour_counts.get(year, 0)
    is_tour = n_concerts > 0
    decade_marker = (year % 10 == 0)
    row_classes = ["yr"]
    if chief: row_classes.append(f"era-{chief[2]}")
    if is_tour: row_classes.append("tour")
    if decade_marker: row_classes.append("decade")

    # Chief name only shown on transition years (first year of tenure)
    chief_label = ""
    if chief:
        name, slug, css_class = chief
        # Find this chief's start year
        start = next(s for s, e, n, _, _ in CHIEFS if n == name)
        if year == start:
            chief_label = (
                f'<span class="chief-start">'
                f'<a href="https://en.wikipedia.org/wiki/{slug}" target="_blank" rel="noopener">'
                f'{name}</a> chief'
                f'</span>'
            )
        elif year == next(e for s, e, n, _, _ in CHIEFS if n == name) and year != 2026:
            chief_label = f'<span class="chief-end">→ {name} ends</span>'

    # Tour pill — colour matches the chief conductor era; label uses
    # the chief's family name (last token of his full name) + the
    # concert count for that year.  e.g. "Karajan (16)". The pill
    # itself is a link to Concerts_in_Japan.html?year=NNNN so the
    # user can open the filtered concert list in a new tab.
    tour_label = ""
    if is_tour:
        pill_colour = CHIEF_COLOUR.get(chief[2], "#D97706") if chief else "#D97706"
        family = chief[0].split()[-1] if chief else "tour"
        tour_label = (
            f'<a class="tour-pill" '
            f'href="Concerts_in_Japan.html?year={year}" '
            f'target="_blank" rel="noopener" '
            f'title="Open {n_concerts} {year} concerts in a new tab" '
            f'style="background:{pill_colour};">'
            f'{family}&nbsp;({n_concerts})'
            f'</a>'
        )

    return (
        f'<div class="{" ".join(row_classes)}" id="y{year}">'
        f'<span class="year-num">{year}</span>'
        f'{chief_label}'
        f'{tour_label}'
        f'</div>'
    )


def build_timeline_html(tour_counts: dict, start: int = 1955, end: int = 2026) -> str:
    rows = []
    last_decade = None
    for year in range(start, end + 1):
        decade = (year // 10) * 10
        if decade != last_decade:
            rows.append(f'<div class="decade-marker" id="t{decade}s">'
                        f'<span>{decade}s</span></div>')
            last_decade = decade
        rows.append(build_timeline_row(year, tour_counts))
    return "\n".join(rows)


def build_analysis_html() -> str:
    blocks = []
    for decade in sorted(DECADE_ANALYSIS.keys()):
        paras = "\n".join(f"<p>{p}</p>" for p in DECADE_ANALYSIS[decade])
        blocks.append(
            f'<section class="decade-block" id="d{decade}">'
            f'<h2>{decade}</h2>\n{paras}\n</section>'
        )
    return "\n\n".join(blocks)


def build_page(concerts_html: str) -> str:
    tour_counts = get_tour_counts(concerts_html)
    timeline_html = build_timeline_html(tour_counts)
    analysis_html = build_analysis_html()
    n_tours = sum(1 for y in tour_counts if 1955 <= y <= 2026)

    # Chief colour CSS rules
    chief_css = "\n".join(
        f".yr.era-{cls} {{ border-left-color: {col}; }}\n"
        f".yr.era-{cls} .year-num {{ color: {col}; }}"
        for cls, col in CHIEF_COLOUR.items()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Berliner Philharmoniker — Program Trend by Era</title>
<style>
* {{ box-sizing: border-box; }}
body {{
  font-family: Arial, sans-serif;
  font-size: 14px;
  margin: 0;
  padding: 24px 20px 60px;
  color: #222;
  background-color: #FFF8EC;
  background-image: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cg font-family='Georgia,serif'%3E%3Ctext x='15' y='48' font-size='38' transform='rotate(-12 30 38)' fill='%23D97706' fill-opacity='0.13'%3E♫%3C/text%3E%3Ctext x='120' y='30' font-size='26' fill='%230F766E' fill-opacity='0.13'%3E♪%3C/text%3E%3Ctext x='175' y='95' font-size='32' transform='rotate(15 188 80)' fill='%23D97706' fill-opacity='0.13'%3E♬%3C/text%3E%3Ctext x='45' y='125' font-size='30' fill='%239F1239' fill-opacity='0.11'%3E♩%3C/text%3E%3C/g%3E%3C/svg%3E");
  background-repeat: repeat;
}}
.container {{ max-width: 1180px; margin: 0 auto; }}
.page-header {{
  position: sticky;
  top: 0;
  z-index: 10;
  background: #FFF8EC;
  padding: 12px 0 16px;
  margin: 0 0 20px;
  box-shadow: 0 2px 0 #FFF8EC;
}}
h1 {{
  font-size: 22px;
  margin: 0 0 6px;
  text-align: center;
  color: #000;
}}
.subhead {{
  text-align: center;
  font-size: 13px;
  color: #555;
  margin: 0 0 10px;
}}
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
  background: #D97706;
  box-shadow: 0 1px 3px rgba(180,83,9,0.25);
}}
.toolbar a:hover {{ background: #B45309; }}

.era-page {{
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 28px;
  align-items: start;
}}

.timeline {{
  position: sticky;
  top: 130px;
  max-height: 80vh;
  overflow-y: auto;
  background: rgba(255,255,255,0.78);
  border: 1px solid rgba(180,83,9,0.20);
  border-radius: 8px;
  padding: 10px 12px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}}
.timeline-hint {{
  position: sticky;
  top: 0;
  margin: -10px -12px 6px;
  padding: 6px 12px;
  background: rgba(217,119,6,0.10);
  border-bottom: 1px solid rgba(180,83,9,0.18);
  font-size: 11px;
  font-style: italic;
  color: #6B4118;
  text-align: center;
  z-index: 3;
}}
.timeline-hint::before {{
  content: "💡";
  font-style: normal;
  margin-right: 4px;
}}
.decade-marker {{
  position: sticky;
  top: -10px;
  background: #F5F5F4;            /* very light warm stone */
  color: #57534E;                 /* mid stone-grey text — soft, neutral */
  font-weight: 800;
  letter-spacing: 1px;
  padding: 4px 10px;
  margin: 10px -12px 4px;
  font-size: 12px;
  border-bottom: 1px solid #D6D3D1;
  z-index: 2;
}}
.decade-marker:first-child {{ margin-top: 0; }}
.decade-marker span {{ display: block; }}
.yr {{
  display: grid;
  grid-template-columns: 44px 1fr auto;
  align-items: center;
  gap: 6px;
  padding: 3px 6px 3px 0;
  border-left: 3px solid transparent;
  font-size: 12.5px;
  line-height: 1.3;
}}
.yr.tour {{
  background: rgba(217,119,6,0.10);
  font-weight: 600;
}}
{chief_css}
.year-num {{
  font-variant-numeric: tabular-nums;
  text-align: right;
  padding-right: 8px;
  font-weight: 600;
  color: #555;
}}
.tour-pill {{
  display: inline-block;
  background: #D97706;
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 10px;
  letter-spacing: 0.4px;
  white-space: nowrap;
  text-decoration: none;          /* <a> styling */
  cursor: pointer;
  transition: filter 0.12s ease, transform 0.12s ease;
}}
.tour-pill:hover {{
  filter: brightness(0.92) drop-shadow(0 2px 4px rgba(0,0,0,0.25));
  transform: translateY(-1px);
}}
.chief-start, .chief-end {{
  font-size: 11.5px;
  color: #1c1917;
  font-style: italic;
}}
.chief-start a {{ color: inherit; text-decoration: none; border-bottom: 1px dotted rgba(180,83,9,0.4); }}
.chief-start a:hover {{ color: #B45309; }}
.chief-end {{ color: #888; }}

.analyses {{
  background: rgba(255,255,255,0.78);
  border: 1px solid rgba(180,83,9,0.20);
  border-radius: 8px;
  padding: 18px 22px 22px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}}
.decade-block {{
  margin-bottom: 26px;
  padding-bottom: 16px;
  border-bottom: 1px dashed rgba(180,83,9,0.20);
}}
.decade-block:last-child {{ border-bottom: none; margin-bottom: 0; }}
.decade-block h2 {{
  margin: 0 0 10px;
  padding: 0 0 6px;
  border-bottom: 2px solid #D97706;
  color: #B45309;
  font-size: 19px;
  letter-spacing: 1px;
}}
.decade-block p {{
  margin: 0 0 8px;
  line-height: 1.55;
  font-size: 13.5px;
  color: #222;
}}

.footnote {{
  max-width: 800px;
  margin: 32px auto 0;
  text-align: center;
  font-size: 12px;
  color: #777;
  line-height: 1.6;
}}

@media (max-width: 800px) {{
  .era-page {{
    grid-template-columns: 1fr;
  }}
  .timeline {{
    position: static;
    max-height: 60vh;
  }}
}}
</style>
</head>
<body>
<div class="container">
<div class="page-header">
<h1>Berliner Philharmoniker — Program Trend by Era</h1>
<p class="subhead">Chief-conductor chronology and Japan-tour markers · {n_tours} tours documented 1957 – 2025.</p>
<p class="toolbar">
  <a href="Concerts_in_Japan.html">Concerts in Japan</a>
  <a href="Program_Ranking.html">Program Ranking</a>
  <a href="Composer_Chart.html">Performances by Composer</a>
  <a href="Performances_by_Conductor.html">Performances by Conductor</a>
  <a href="Performances_by_Prefecture.html">Performances by Prefecture</a>
  <a href="index.html">Home</a>
</p>
</div>

<div class="era-page">
  <aside class="timeline" aria-label="BPO chief-conductor + tour timeline">
    <div class="timeline-hint">Click any tour to show its concerts</div>
{timeline_html}
  </aside>
  <main class="analyses">
{analysis_html}
  </main>
</div>

<p class="footnote">
The chief-conductor (<em>Chefdirigent</em>) tenures shown reflect the
elected periods. The Japan-tour markers are drawn live from the
<a href="Concerts_in_Japan.html">Concerts in Japan</a> table.
</p>
</div>
</body>
</html>
"""


def main():
    in_path  = "Berliner Philharmoniker/Concerts_in_Japan.html"
    out_path = "Berliner Philharmoniker/Program_Trend_by_Era.html"
    with open(in_path, encoding="utf-8") as f:
        html = f.read()
    page = build_page(html)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {out_path}")
    counts = get_tour_counts(html)
    print(f"  {len(counts)} tour years, {sum(counts.values())} concerts on timeline")


if __name__ == "__main__":
    main()
