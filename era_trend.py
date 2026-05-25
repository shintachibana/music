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
from urllib.parse import quote as urlquote


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
DECADE_ANALYSIS_BPO = {
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


# WPO has no Chefdirigent tradition — the orchestra is self-governing —
# so each tour is shaped by whichever guest conductor it engaged. The
# decade analysis reflects who toured rather than who was "in charge".
DECADE_ANALYSIS_WPO = {
    "1950s": [
        "The maiden Japan tour, 1956, led entirely by Paul Hindemith — "
        "composer-conductor, friend of the orchestra, and ambassador. "
        "A pedagogical survey of German tradition: Bach Suite 2, "
        "Mozart's Bassoon and 3rd Horn Concertos, Wagner's "
        "<em>Siegfried-Idyll</em>, Brahms <em>Haydn-Variationen</em>, "
        "Beethoven 4, with a Hindemith Sinfonietta on each evening.",
        "1959 returns with Karajan as the principal conductor (eight "
        "concerts) and Willi Boskovsky leading three all-Johann-Strauss "
        "dance evenings — the New Year's-Concert formula transplanted "
        "to Tokyo and Osaka venues.",
    ],
    "1960s": [
        "Only one tour this decade: 1969, Georg Solti with twelve "
        "concerts plus a single Boskovsky New-Year's-style evening. "
        "Beethoven 7 + R. Strauss + Schubert <em>Unvollendete</em> "
        "forms a clearly Solti-shaped power-canon programme. The WPO's "
        "Japan appearances are still rarer than the BPO's in this era."
    ],
    "1970s": [
        "Three tours mark a generational handover. 1973 brings Abbado "
        "for his first Japan run — Beethoven cycles and Mozart 40. "
        "1975 introduces Riccardo Muti alongside the elder Karl Böhm; "
        "1977 pairs Christoph von Dohnányi with Böhm again. Böhm's "
        "Mozart/Schubert/Beethoven gravitas and Muti's emergent Italian "
        "lyricism start their decades-long WPO Japan partnership."
    ],
    "1980s": [
        "Lorin Maazel becomes the dominant Japan-tour figure — 1980, "
        "1983 and 1986, all his work. Beethoven 5 + 6 + Mozart 25 + R. "
        "Strauss <em>Don Juan</em> + Tschaikowsky 5 form a tight "
        "canon-virtuoso rotation. Abbado returns 1987 and 1989; the "
        "1989 tour includes the Berg <em>Wozzeck</em> staged opera and "
        "the Schumann <em>Requiem für Mignon</em> — first markers of "
        "modernist outreach."
    ],
    "1990s": [
        "Annual tours begin. The guest-conductor roster widens "
        "dramatically: Sinopoli (1992), Ozawa (1993), Solti + Kleiber "
        "(1994, with Kleiber's <em>Rosenkavalier</em> staged opera "
        "run), Levine (1995), Mehta + Ozawa (1996), Haitink (1997), "
        "Muti (1999). Mahler enters the touring core through Sinopoli "
        "and Haitink; the late-Romantic / early-modernist palette "
        "broadens steadily across the decade."
    ],
    "2000s": [
        "Annual tours continue with deeper repertoire variety. "
        "Thielemann debuts (2003, Brahms 1 / Bruckner 7); Gergiev's "
        "first Japan tour (2004) brings the Tschaikowsky 6 "
        "<em>Pathétique</em> spine and a J. Strauss medley. Muti's "
        "Schubert-focused tours (2005, 2008) and Harnoncourt's "
        "Mozart-Beethoven late-style (2006) frame the decade. "
        "Pfitzner's <em>Violinkonzert</em> with Küchl (Gergiev 2004) "
        "is an unusual entry."
    ],
    "2010s": [
        "Conductor rotation widens further: Nelsons, Prêtre and "
        "Welser-Möst share 2010 (Mahler 9 originally planned with "
        "Ozawa, reshuffled when he withdrew); Thielemann (2013), "
        "Dudamel (2014), Mehta + Ozawa together (2016 — Suntory Hall "
        "30th Anniversary). Hosokawa Toshio's <em>Nostalghia</em> "
        "(through Mehta and Levine) and Takemitsu's "
        "<em>Visions</em> bring Japanese composers into the touring "
        "fold."
    ],
    "2020s": [
        "COVID-era interruptions. Gergiev's second Japan tour (Nov "
        "2020) goes ahead with reduced capacity. Muti returns 2021 "
        "(Schubert and Mendelssohn cycles); Sokhiev 2023 introduces "
        "Brahms 1 / Dvořák 8 alongside Saint-Saëns PC 2; Nelsons "
        "2024; Thielemann 2025. The post-pandemic mix reads as "
        "Romantic / late-Romantic German core with selective Russian "
        "and Mahler-tradition guests."
    ],
}


def get_tour_counts(concerts_html: str) -> dict:
    """Return {year: concert_count} — one entry per row of the
    concerts table, summed by year. Matches plain <tr> and
    <tr class="future"> rows alike."""
    counts: dict[int, int] = {}
    for y in re.findall(r"<tr[^>]*><td>(\d{4})</td>", concerts_html):
        year = int(y)
        counts[year] = counts.get(year, 0) + 1
    return counts


def get_tour_conductors_by_year(concerts_html: str):
    """Return (conductors, planned_years).

    conductors: {year: [(conductor_full_name, count), ...] sorted desc}.
    planned_years: set of years where every row is marked
        <tr class="future"> — used to render the era timeline pill
        with a 'planned' style.
    Joint-conductor cells split on '/' and credit each side with the
    concert appearance separately."""
    result: dict[int, dict[str, int]] = {}
    future_per_year: dict[int, int] = {}
    total_per_year: dict[int, int] = {}
    m = re.search(r"<tbody>(.*?)</tbody>", concerts_html, re.DOTALL)
    if not m:
        return {}, set()
    tbody = m.group(1)
    for row in re.findall(r"<tr[^>]*>.*?</tr>", tbody, re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 5:
            continue
        ystr = re.sub(r"<[^>]+>", "", tds[0]).strip()
        try:
            year = int(ystr)
        except ValueError:
            continue
        is_future = 'class="future"' in row
        total_per_year[year] = total_per_year.get(year, 0) + 1
        if is_future:
            future_per_year[year] = future_per_year.get(year, 0) + 1
        cond_cell = re.sub(r"<[^>]+>", "", tds[3]).strip()
        d = result.setdefault(year, {})
        for c in cond_cell.split("/"):
            c = c.strip()
            if c:
                d[c] = d.get(c, 0) + 1
    planned_years = {
        y for y in total_per_year
        if future_per_year.get(y, 0) == total_per_year[y]
    }
    conductors = {y: sorted(d.items(), key=lambda kv: -kv[1]) for y, d in result.items()}
    return conductors, planned_years


def get_chief_for_year(year: int):
    for start, end, name, slug, css_class in CHIEFS:
        if start <= year <= end:
            return name, slug, css_class
    return None


def build_timeline_row(year: int, tour_conductors: dict, planned_years: set,
                        show_chief: bool, default_pill: str) -> str:
    """One row of the timeline. tour_conductors[year] is the live
    [(name, n_concerts), ...] list of who led that year's tour. The
    pill label uses the conductor's family name; one pill per
    conductor in the list (so a year with Mehta(5) + Ozawa(3) gets
    two pills). Years in planned_years are rendered in a muted
    'future' style."""
    chief = get_chief_for_year(year) if show_chief else None
    conds = tour_conductors.get(year, [])
    is_tour = len(conds) > 0
    is_planned = year in planned_years
    decade_marker = (year % 10 == 0)
    row_classes = ["yr"]
    if chief: row_classes.append(f"era-{chief[2]}")
    if is_tour: row_classes.append("tour")
    if is_planned: row_classes.append("future")
    if decade_marker: row_classes.append("decade")

    # Chief name only shown on transition years (first year of tenure)
    chief_label = ""
    if chief:
        name, slug, css_class = chief
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

    # One pill per actual tour conductor that year. Pill colour follows
    # the chief era (when show_chief is on) so the visual era stays
    # readable even when a guest conductor leads the tour (e.g. Ozawa
    # 1986 in the Karajan era). When show_chief is off (WPO mode), use
    # the orchestra's default pill colour for every tour conductor.
    # Planned (future) tours render with a muted neutral pill regardless
    # of era, so they stand out as forthcoming rather than realised.
    if is_planned:
        pill_colour = "#94A3B8"
        pill_extra_class = " planned"
    else:
        pill_colour = CHIEF_COLOUR.get(chief[2], default_pill) if chief else default_pill
        pill_extra_class = ""
    pills = []
    for cond_full, n in conds:
        family = cond_full.split()[-1]
        title_suffix = " — planned" if is_planned else ""
        pills.append(
            f'<a class="tour-pill{pill_extra_class}" '
            f'href="Concerts_in_Japan.html?year={year}&conductor={urlquote(cond_full)}" '
            f'target="_blank" rel="noopener" '
            f'title="Open {n} {year} concert(s) led by {cond_full}{title_suffix} in a new tab" '
            f'style="background:{pill_colour};">'
            f'{family}&nbsp;({n})'
            f'</a>'
        )
    # Wrap the pills in a flex container so they each shrink to text
    # length and lay out side-by-side (or wrap to a second line if the
    # row's contents exceed its width — e.g. 2010 with three guest
    # conductors fits in one line; the year with seven would wrap).
    tour_label = f'<span class="tour-pills">{"".join(pills)}</span>' if pills else ''

    return (
        f'<div class="{" ".join(row_classes)}" id="y{year}">'
        f'<span class="year-num">{year}</span>'
        f'{chief_label}'
        f'{tour_label}'
        f'</div>'
    )


def build_timeline_html(tour_conductors: dict, planned_years: set,
                         show_chief: bool, default_pill: str,
                         start: int = 1955, end: int = 2026) -> str:
    rows = []
    last_decade = None
    for year in range(start, end + 1):
        decade = (year // 10) * 10
        if decade != last_decade:
            rows.append(f'<div class="decade-marker" id="t{decade}s">'
                        f'<span>{decade}s</span></div>')
            last_decade = decade
        rows.append(build_timeline_row(year, tour_conductors, planned_years,
                                        show_chief, default_pill))
    return "\n".join(rows)


def build_analysis_html(decade_analysis: dict) -> str:
    blocks = []
    for decade in sorted(decade_analysis.keys()):
        paras = "\n".join(f"<p>{p}</p>" for p in decade_analysis[decade])
        blocks.append(
            f'<section class="decade-block" id="d{decade}">'
            f'<h2>{decade}</h2>\n{paras}\n</section>'
        )
    return "\n\n".join(blocks)


def build_page(concerts_html: str, orchestra: str = "bpo") -> str:
    tour_conductors, planned_years = get_tour_conductors_by_year(concerts_html)
    tour_counts = get_tour_counts(concerts_html)
    realised_tour_years = [y for y in tour_conductors if 1955 <= y <= 2026 and y not in planned_years]
    n_tours = len(realised_tour_years)
    n_planned = sum(1 for y in tour_conductors if 1955 <= y <= 2026 and y in planned_years)
    end_realised = max(realised_tour_years, default=2025)

    # Orchestra-specific palette + content
    if orchestra == "bpo":
        title = "Berliner Philharmoniker — Program Trend by Era"
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
            '  <a href="Audience_Analysis.html">Audience Analysis</a>\n'
            '  <a href="index.html">Home</a>'
        )
        show_chief = True
        default_pill = "#D97706"
        decade_analysis = DECADE_ANALYSIS_BPO
        start_year = 1955
        planned_phrase_bpo = f" plus {n_planned} scheduled for {min(planned_years)}" if planned_years else ""
        subhead_extra = f"Chief-conductor chronology and Japan-tour markers · {n_tours} tours documented 1957 – {end_realised}{planned_phrase_bpo}."
        footer_note = (
            "The chief-conductor (<em>Chefdirigent</em>) tenures shown reflect the "
            "elected periods. The Japan-tour markers are drawn live from the "
            "<a href=\"Concerts_in_Japan.html\">Concerts in Japan</a> table."
        )
    else:
        title = "Wiener Philharmoniker — Program Trend by Era"
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
            '  <a href="index.html">Home</a>'
        )
        show_chief = False
        # Softer rose for the pills — the deep burgundy used as the page
        # accent was too saturated as a flood-fill on every tour pill.
        # Stepped from pink-600 (#DB2777) down to pink-500 for a gentler
        # tone that still keeps white text legible.
        default_pill = "#EC4899"
        decade_analysis = DECADE_ANALYSIS_WPO
        start_year = 1955  # WPO first toured Japan in 1956 — same canvas
        planned_phrase_wpo = f" plus {n_planned} scheduled for {min(planned_years)}" if planned_years else ""
        subhead_extra = f"Tour-conductor chronology · {n_tours} Japan tours documented 1956 – {end_realised}{planned_phrase_wpo}. The Vienna Philharmonic is self-governing; programmes shift with the guest conductor of each tour."
        footer_note = (
            "The Vienna Philharmonic has no <em>Chefdirigent</em> tradition — "
            "each tour is led by an invited guest. Conductor names are pulled "
            "live from the <a href=\"Concerts_in_Japan.html\">Concerts in Japan</a> "
            "table; click any tour pill to filter that page by the year."
        )

    timeline_html = build_timeline_html(tour_conductors, planned_years,
                                          show_chief, default_pill, start=start_year)
    analysis_html = build_analysis_html(decade_analysis)

    # Chief colour CSS rules
    chief_css = "\n".join(
        f".yr.era-{cls} {{ border-left-color: {col}; }}\n"
        f".yr.era-{cls} .year-num {{ color: {col}; }}"
        for cls, col in CHIEF_COLOUR.items()
    )

    # Notes-pattern background SVG colour key
    if orchestra == "bpo":
        notes_pattern = "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cg font-family='Georgia,serif'%3E%3Ctext x='15' y='48' font-size='38' transform='rotate(-12 30 38)' fill='%23D97706' fill-opacity='0.13'%3E♫%3C/text%3E%3Ctext x='120' y='30' font-size='26' fill='%230F766E' fill-opacity='0.13'%3E♪%3C/text%3E%3Ctext x='175' y='95' font-size='32' transform='rotate(15 188 80)' fill='%23D97706' fill-opacity='0.13'%3E♬%3C/text%3E%3Ctext x='45' y='125' font-size='30' fill='%239F1239' fill-opacity='0.11'%3E♩%3C/text%3E%3C/g%3E%3C/svg%3E"
        hint_text_color = "#6B4118"
    else:
        notes_pattern = "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cg font-family='Georgia,serif'%3E%3Ctext x='15' y='48' font-size='38' transform='rotate(-12 30 38)' fill='%239F1239' fill-opacity='0.13'%3E♫%3C/text%3E%3Ctext x='120' y='30' font-size='26' fill='%230F766E' fill-opacity='0.13'%3E♪%3C/text%3E%3Ctext x='175' y='95' font-size='32' transform='rotate(15 188 80)' fill='%239F1239' fill-opacity='0.13'%3E♬%3C/text%3E%3Ctext x='45' y='125' font-size='30' fill='%23B8860B' fill-opacity='0.11'%3E♩%3C/text%3E%3C/g%3E%3C/svg%3E"
        hint_text_color = "#5B0E27"

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
  background-color: {bgcol};
  background-image: url("{notes_pattern}");
  background-repeat: repeat;
}}
.container {{ max-width: 1180px; margin: 0 auto; }}
.page-header {{
  position: sticky;
  top: 0;
  z-index: 10;
  background: {bgcol};
  padding: 12px 0 16px;
  margin: 0 0 20px;
  box-shadow: 0 2px 0 {bgcol};
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
  background: {accent};
  box-shadow: 0 1px 3px {accent_soft};
}}
.toolbar a:hover {{ background: {accent_d}; }}

.era-page {{
  display: grid;
  grid-template-columns: 400px 1fr;
  gap: 28px;
  align-items: start;
}}

.timeline {{
  position: sticky;
  top: 130px;
  max-height: 80vh;
  overflow-y: auto;
  background: rgba(255,255,255,0.78);
  border: 1px solid {accent_soft};
  border-radius: 8px;
  padding: 10px 12px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}}
.timeline-hint {{
  position: sticky;
  top: 0;
  margin: -10px -12px 6px;
  padding: 6px 12px;
  background: {accent_tint};
  border-bottom: 1px solid {accent_soft};
  font-size: 11px;
  font-style: italic;
  color: {hint_text_color};
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
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  padding: 3px 6px 3px 0;
  border-left: 3px solid transparent;
  font-size: 12.5px;
  line-height: 1.3;
}}
.yr.tour {{
  background: {accent_tint};
  font-weight: 600;
}}
.yr.future {{
  border-left: 3px dashed #94A3B8 !important;
  background: rgba(148, 163, 184, 0.12) !important;
}}
.yr.future .year-num {{
  color: #64748B;
  font-style: italic;
}}
{chief_css}
.year-num {{
  width: 44px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  text-align: right;
  padding-right: 8px;
  font-weight: 600;
  color: #555;
}}
.tour-pills {{
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex: 0 1 auto;
  min-width: 0;
}}
.tour-pill {{
  display: inline-block;
  background: {accent};
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
.tour-pill.planned {{
  font-style: italic;
  box-shadow: inset 0 0 0 1px #64748B;
}}
.tour-pill.planned::after {{
  content: " ◷";
  font-style: normal;
  font-size: 9px;
  margin-left: 2px;
  opacity: 0.85;
}}
.chief-start, .chief-end {{
  font-size: 11.5px;
  color: #1c1917;
  font-style: italic;
}}
.chief-start a {{ color: inherit; text-decoration: none; border-bottom: 1px dotted {accent_soft}; }}
.chief-start a:hover {{ color: {accent_d}; }}
.chief-end {{ color: #888; }}

.analyses {{
  background: rgba(255,255,255,0.78);
  border: 1px solid {accent_soft};
  border-radius: 8px;
  padding: 18px 22px 22px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}}
.decade-block {{
  margin-bottom: 26px;
  padding-bottom: 16px;
  border-bottom: 1px dashed {accent_soft};
}}
.decade-block:last-child {{ border-bottom: none; margin-bottom: 0; }}
.decade-block h2 {{
  margin: 0 0 10px;
  padding: 0 0 6px;
  border-bottom: 2px solid {accent};
  color: {accent_d};
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

@media (max-width: 900px) {{
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
<h1>{title}</h1>
<p class="subhead">{subhead_extra}</p>
<p class="toolbar">
{toolbar_links}
</p>
</div>

<div class="era-page">
  <aside class="timeline" aria-label="{title} timeline">
    <div class="timeline-hint">Click any tour to show its concerts</div>
{timeline_html}
  </aside>
  <main class="analyses">
{analysis_html}
  </main>
</div>

<p class="footnote">
{footer_note}
</p>
</div>
</body>
</html>
"""


def main():
    orchestra = sys.argv[1].lower() if len(sys.argv) > 1 else "bpo"
    if orchestra == "bpo":
        in_path  = "Berliner Philharmoniker/Concerts_in_Japan.html"
        out_path = "Berliner Philharmoniker/Program_Trend_by_Era.html"
    elif orchestra == "wpo":
        in_path  = "Wiener Philharmoniker/Concerts_in_Japan.html"
        out_path = "Wiener Philharmoniker/Program_Trend_by_Era.html"
    else:
        print(f"Unknown orchestra '{orchestra}'. Use 'bpo' or 'wpo'.", file=sys.stderr)
        sys.exit(1)
    with open(in_path, encoding="utf-8") as f:
        html = f.read()
    page = build_page(html, orchestra)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {out_path}")
    counts = get_tour_counts(html)
    print(f"  {len(counts)} tour years, {sum(counts.values())} concerts on timeline")


if __name__ == "__main__":
    main()
