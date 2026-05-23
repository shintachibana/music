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
# Resolves through https://en.wikipedia.org/wiki/Special:FilePath/<file>?width=N
# which redirects to the real upload.wikimedia.org URL — stable across renames.
COMPOSER_IMAGE = {
    "Beethoven":       "Beethoven.jpg",
    "Brahms":          "JohannesBrahms.jpg",
    "Mozart":          "Wolfgang-amadeus-mozart_1.jpg",
    "R. Strauss":      "Richard_Strauss_in_1894.jpg",
    "Wagner":          "RichardWagner.jpg",
    "Mahler":          "Gustav_Mahler_1909.jpg",
    "Debussy":         "Achille-Claude_Debussy.jpg",
    "Tschaikowsky":    "Porträt_des_Komponisten_Pjotr_I._Tschaikowski_(1840-1893).jpg",
    "Bruckner":        "Anton_Bruckner_1885_grayscale.jpg",
    "Berg":            "Alban_Berg_(1885-1935),_by_Schmutzer_1934.png",
    "Ravel":           "Maurice_Ravel_1925.jpg",
    "Schumann":        "Robert_Schumann_1839.jpg",
    "Strawinsky":      "Igor_Stravinsky_LOC_32392u.jpg",
    "Dvořák":          "Antonin_Dvorak.jpg",
    "Haydn":           "Joseph_Haydn.jpg",
    "Reger":           "Max_Reger.jpg",
    "Prokofjew":       "Sergei_Prokofiev_01.jpg",
    "Mussorgsky":      "Modest_Mussorgsky,_1870.jpg",
    "Schubert":        "Franz_Schubert_by_Wilhelm_August_Rieder_1875.jpg",
    "Bartók":          "Bela_Bartok_1927.jpg",
    "Bernstein":       "Leonard_Bernstein_by_Jack_Mitchell.jpg",
    "Boulez":          "Pierre_Boulez_(2004).jpg",
    "Janáček":         "Leoš_Janáček_(1854-1928).jpg",
    "Magnus Lindberg": "Magnus_Lindberg.jpg",
    "Rachmaninow":     "Sergei_Rachmaninoff_LOC_31550.jpg",
    "Respighi":        "Ottorino_Respighi.jpg",
    "Unsuk Chin":      "Unsuk_Chin_2012.jpg",
    "Verdi":           "Giuseppe_Verdi.jpg",
    "Bach":            "Johann_Sebastian_Bach.jpg",
    "Mendelssohn":     "Felix_Mendelssohn_Bartholdy.jpg",
    "Hikaru Hayashi":  "Hikaru_Hayashi.jpg",
    "J. Strauss II":   "Johann_Strauss_II_by_Fritz_Luckhardt.jpg",
    "Josef Strauss":   "Josef_Strauss.jpg",
    "Rossini":         "Étienne_Carjat,_Portrait_of_Gioachino_Rossini_-_Google_Art_Project.jpg",
    "Liszt":           "Franz_Liszt_by_Pierre_Petit.jpg",
    "Wolf":            "Hugo_Wolf_3.jpg",
    "Webern":          "Anton_Webern.jpg",
    "Hindemith":       "Paul_Hindemith_1923.jpg",
    "Falla":           "Manuel_de_Falla.jpg",
    "Sibelius":        "Jean_Sibelius,_1939.jpg",
    "Saint-Saëns":     "Saint-Saëns,_Camille_-_Petit_1900.jpg",
    "Schostakowitsch": "Dmitri_Shostakovich_credit_Deutsche_Fotothek_adjusted.jpg",
    "Schönberg":       "Arnold_Schönberg_1948.jpg",
    "Rimsky-Korsakow": "Valentin_Serov_-_Portrait_of_the_Composer_Nikolai_Rimsky-Korsakov_-_Google_Art_Project.jpg",
    "Chopin":          "Frederic_Chopin_photo.jpeg",
    "Reznicek":        "Emil_Nikolaus_von_Reznicek_-_Eichberg.jpg",
    "Takemitsu":       "Toru_Takemitsu_1961.jpg",
}


def wiki_image(filename: str, width: int = 320) -> str:
    return (
        f"https://en.wikipedia.org/wiki/Special:FilePath/"
        f"{quote(filename, safe='()_-.')}?width={width}"
    )


def aggregate(ranking_html: str) -> dict:
    """Return {composer: total_performances} parsed from a Program_Ranking page."""
    rx = re.compile(
        r'<tr><td>\d+</td><td>(?:<a [^>]+>)?([^<:]+):[^<]+?(?:</a>)?</td><td>(\d+)</td>'
    )
    totals: dict[str, int] = {}
    for m in rx.finditer(ranking_html):
        composer = m.group(1).strip()
        composer = composer.split("/")[0].strip()       # Mussorgsky/Ravel → Mussorgsky
        composer = re.sub(r"\s*\([^)]*\)", "", composer).strip()  # Bach (arr. Webern) → Bach
        totals[composer] = totals.get(composer, 0) + int(m.group(2))
    return totals


def build_page(orchestra: str, totals: dict) -> str:
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

    sorted_pairs = sorted(totals.items(), key=lambda x: -x[1])
    max_count = sorted_pairs[0][1]
    # side(n) = sqrt(n / max) * 240 → largest composer is a 240-px square,
    # area scales linearly with performances.
    def side_px(n: int) -> int:
        return max(56, round(math.sqrt(n / max_count) * 240))

    tiles = []
    for composer, count in sorted_pairs:
        side  = side_px(count)
        img_filename = COMPOSER_IMAGE.get(composer)
        if img_filename:
            bg_url = wiki_image(img_filename, width=max(320, side * 2))
            bg_css = f'background-image: url("{bg_url}");'
        else:
            bg_css = f'background: {accent};'
        # Show label only on squares big enough to fit text
        show_label = side >= 70
        label_html = (
            f'<div class="label"><div class="name">{composer}</div>'
            f'<div class="count">{count}</div></div>'
        ) if show_label else (
            f'<div class="label hidden"><div class="name">{composer}</div>'
            f'<div class="count">{count}</div></div>'
        )
        title_attr = f'{composer} — {count} performances'
        tiles.append(
            f'<div class="tile" style="width:{side}px;height:{side}px;{bg_css}" '
            f'title="{title_attr}">{label_html}</div>'
        )

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
  padding: 60px 20px;
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

.chart {{
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 6px;
  max-width: 1200px;
  margin: 0 auto;
}}
.tile {{
  position: relative;
  background-size: cover;
  background-position: center top;
  border-radius: 4px;
  overflow: hidden;
  cursor: default;
  box-shadow: 0 1px 4px rgba(0,0,0,0.18);
}}
.tile:hover {{ box-shadow: 0 3px 12px rgba(0,0,0,0.32); }}
.tile .label {{
  position: absolute;
  left: 0; right: 0; bottom: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.75), rgba(0,0,0,0.05));
  color: #fff;
  padding: 4px 6px;
  font-size: 11px;
  line-height: 1.2;
  text-shadow: 0 1px 2px rgba(0,0,0,0.6);
}}
.tile .label.hidden {{ display: none; }}
.tile .name {{ font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.tile .count {{ font-size: 14px; font-weight: 700; }}

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
<p class="subhead">Each square's area is proportional to that composer's total performances on the orchestra's documented Japan tours. {total_composers} composers, {total_perf} performances total.</p>
<p class="toolbar">
  <a href="Concerts_in_Japan.html">Concerts in Japan →</a>
  <a href="Program_Ranking.html">Program Ranking →</a>
  <a href="index.html">{title.split(' — ')[0]}</a>
</p>

<div class="chart">
{chr(10).join(tiles)}
</div>

<p class="footnote">
Portraits via <a href="https://commons.wikimedia.org/" target="_blank" rel="noopener">Wikimedia Commons</a>.
Hover over a square for the composer's exact count.
</p>
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

    page = build_page(orchestra, totals)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Wrote {out_path}")
    print(f"  {len(totals)} composers, {sum(totals.values())} total performances")
    missing = [c for c in totals if c not in COMPOSER_IMAGE]
    if missing:
        print(f"  (no portrait mapped for: {missing})")


if __name__ == "__main__":
    main()
