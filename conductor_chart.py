"""Generate a circle-packed Performances-by-Conductor page from a
Concerts_in_Japan.html source.

Usage:
    python3 conductor_chart.py bpo   # → "Berliner_Philharmoniker_in_Japan/Performances_by_Conductor.html"
    python3 conductor_chart.py wpo   # → "Wiener_Philharmoniker_in_Japan/Performances_by_Conductor.html"

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
    # WPO – verified Wikimedia Commons portrait filenames
    "Valery Gergiev":        "Valery_Gergiev_David_Shankbone_2010.jpg",
    "Riccardo Muti":         "Riccardo_Muti.jpg",
    "Christian Thielemann":  "Thielemann_2047-Michelides_(1).jpg",
    "Andris Nelsons":        "Andris_Nelsons.JPG",
    "Georges Prêtre":        "Georges_Pretre_1989_Garmisch-19890625-RM-113345.jpg",
    "Franz Welser-Möst":     "Franz_Welser-Most_conducting_the_New_York_Philharmonic_-_49616007592.jpg",
    "Lorin Maazel":          "Lorin_Maazel,_1958_-_collezione_Tino_Barindelli.tif",
    "Nikolaus Harnoncourt":  "Nikolaus_Harnoncourt_(1980).jpg",
    "Christoph von Dohnányi": "Christoph-von-Dohnányi-cropped.png",
    "James Levine":          "James_Levine_2013.jpg",
    "Karl Böhm":             "Karl_Böhm_(1894–1981)_~1950_OeNB_653942.jpg",
    "Giuseppe Sinopoli":     "Giuseppe_Sinopoli.jpg",
    "Bernard Haitink":       "Bernard_Haitink_1984b.jpg",
    "Paul Hindemith":        "Paul_Hindemith_1923.jpg",
    "Christoph Eschenbach":  "Christoph_Eschenbach_(cropped).jpg",
    "Carlos Kleiber":        "Carlos_Kleiber.png",
    "Georg Solti":           "Sir_George_Solti_6_Allan_Allan_Warren.jpg",
    "André Previn":          "André_Previn.jpg",
    "Leopold Hager":         "Leopold_Hager_1982_Bamberg-19821009-RM-172843.jpg",
    "Tugan Sokhiev":         "Tugan_Sokhiev.jpg",
    "Andrés Orozco-Estrada": "Andres_Orozco_Estrada.jpg",
    "Rudolf Buchbinder":     "Rudolf_Buchbinder,_2010_(cropped).jpg",
    # Willi Boskovsky — the only Commons image of him is the 1962
    # Vienna Octet group photo (he was the ensemble's leader); it is
    # the file the Wikipedia article uses too.
    "Willi Boskovsky":       "Vienna_Octet_1962_touring_Southern_Afrtica.jpg",
}


# Conductor → English Wikipedia article slug. Each value is the URL
# path component, so wiki_link() turns it into a full URL.
CONDUCTOR_URL = {
    # BPO
    "Herbert von Karajan":  "Herbert_von_Karajan",
    "Simon Rattle":         "Simon_Rattle",
    "Claudio Abbado":       "Claudio_Abbado",
    "Kirill Petrenko":      "Kirill_Petrenko",
    "Gustavo Dudamel":      "Gustavo_Dudamel",
    "Zubin Mehta":          "Zubin_Mehta",
    "Seiji Ozawa":          "Seiji_Ozawa",
    "Mariss Jansons":       "Mariss_Jansons",
    "Wilhelm Schüchter":    "Wilhelm_Sch%C3%BCchter",
    # WPO (overlapping entries share the same slug)
    "Riccardo Muti":         "Riccardo_Muti",
    "Lorin Maazel":          "Lorin_Maazel",
    "Paul Hindemith":        "Paul_Hindemith",
    "Valery Gergiev":        "Valery_Gergiev",
    "Christian Thielemann":  "Christian_Thielemann",
    "Andris Nelsons":        "Andris_Nelsons",
    "Georges Prêtre":        "Georges_Pr%C3%AAtre",
    "Franz Welser-Möst":     "Franz_Welser-M%C3%B6st",
    "Nikolaus Harnoncourt":  "Nikolaus_Harnoncourt",
    "Christoph von Dohnányi": "Christoph_von_Dohn%C3%A1nyi",
    "James Levine":          "James_Levine",
    "Karl Böhm":             "Karl_B%C3%B6hm",
    "Giuseppe Sinopoli":     "Giuseppe_Sinopoli",
    "Bernard Haitink":       "Bernard_Haitink",
    "Christoph Eschenbach":  "Christoph_Eschenbach",
    "Carlos Kleiber":        "Carlos_Kleiber",
    "Georg Solti":           "Georg_Solti",
    "André Previn":          "Andr%C3%A9_Previn",
    "Leopold Hager":         "Leopold_Hager",
    "Tugan Sokhiev":         "Tugan_Sokhiev",
    "Willi Boskovsky":       "Willi_Boskovsky",
    "Andrés Orozco-Estrada": "Andr%C3%A9s_Orozco-Estrada",
    "Rudolf Buchbinder":     "Rudolf_Buchbinder",
}


def wiki_link(name: str) -> str:
    """Return the full en.wikipedia URL for the conductor, or empty."""
    slug = CONDUCTOR_URL.get(name)
    return f"https://en.wikipedia.org/wiki/{slug}" if slug else ""


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


def aggregate(concerts_html: str) -> tuple[dict, dict, dict]:
    """Walk every concert row → conductor totals, per-work counts, and
    per-conductor concert counts. Joint-conductor cells (e.g. "Mehta /
    Ozawa") credit each conductor with the works in that concert.

    Returns (totals, details, concerts) where:
       totals[cond]   = total performance count (works played)
       details[cond]  = {work: count}
       concerts[cond] = number of concerts (rows) led
    """
    m = re.search(r"<tbody>(.*?)</tbody>", concerts_html, re.DOTALL)
    if not m:
        return {}, {}, {}
    tbody = m.group(1)

    totals: dict[str, int] = {}
    details: dict[str, dict[str, int]] = {}
    concerts: dict[str, int] = {}

    for row in re.findall(r"<tr>.*?</tr>", tbody, re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 5:
            continue
        cond_text = strip_tags(tds[3]).strip()
        program   = tds[4]
        if not cond_text:
            continue

        # Joint conductors → "X / Y" → split
        conductors_list = [c.strip() for c in cond_text.split("/") if c.strip()]

        works = parse_program(program)
        works = [w for w in works if not is_placeholder(w)]

        for cond in conductors_list:
            concerts[cond] = concerts.get(cond, 0) + 1
            d = details.setdefault(cond, {})
            for w in works:
                d[w] = d.get(w, 0) + 1
                totals[cond] = totals.get(cond, 0) + 1
    return totals, details, concerts


def composers_for(details: dict, cond: str) -> list[tuple[str, int]]:
    """Roll up a conductor's works to per-composer totals."""
    by_composer: dict[str, int] = {}
    for w, n in details.get(cond, {}).items():
        if ":" in w:
            comp = w.split(":", 1)[0].strip()
        else:
            comp = "Other"
        # Strip parenthetical qualifier like "Bach (arr. Webern)" → "Bach"
        comp = re.sub(r"\s*\([^)]*\)\s*", "", comp).split("/")[0].strip()
        by_composer[comp] = by_composer.get(comp, 0) + n
    return sorted(by_composer.items(), key=lambda x: (-x[1], x[0]))


def linked_name(name: str) -> str:
    """Return the conductor name wrapped in an <a> to en.wikipedia,
    or the bare name if no URL is mapped."""
    url = wiki_link(name)
    if not url:
        return name
    return f'<a href="{url}" target="_blank" rel="noopener">{name}</a>'


def bpo_analysis_html(details: dict) -> str:
    """Hand-written analysis paragraphs for the four BPO Chefdirigenten.

    The top-composers ticker under each heading is rebuilt from `details`
    each render so the numbers always match the current data."""
    def ticker(cond: str, n: int = 5) -> str:
        tops = composers_for(details, cond)[:n]
        return " · ".join(f"<b>{c}</b>&nbsp;{v}" for c, v in tops)

    return f"""<section class="analysis">
<h2>Programme tendencies — BPO Chefdirigenten</h2>
<p class="lede">Patterns across each chief conductor's recorded Japan-tour repertoire.</p>

<h3>{linked_name("Herbert von Karajan")}<span class="years"> · 1957 – 1988</span></h3>
<p class="top-composers">{ticker("Herbert von Karajan")}</p>
<p>The Austro-German core dominates: Beethoven and Brahms together account for nearly half of his Japan total. Around them he assembled a tightly curated supplementary repertoire — R. Strauss tone poems, a steady Mozart presence, and Wagner overtures. Slavic and French additions (Dvořák, Tschaikowsky, Debussy, Ravel) round the picture out, while modernism is conspicuously absent (a single Schönberg, a single Webern, no Bartók). The Karajan-era programmes are canon-anchored: blockbuster symphonies and showpieces designed for the touring stage.</p>

<h3>{linked_name("Claudio Abbado")}<span class="years"> · 1989 – 2002</span></h3>
<p class="top-composers">{ticker("Claudio Abbado")}</p>
<p>Beethoven and Brahms still anchor the picture, but the centre of gravity shifts. Mahler arrives as a major pillar (vs. Karajan's single appearance), Schumann re-enters meaningfully, and the Second Viennese School reaches the stage — three nights of Berg's <em>Wozzeck</em> as a staged opera. Bruckner and a more curatorial, retrospective approach to Brahms speak to a recital-style programming intelligence. The pivot away from the strict Karajan canon is most clearly marked by the prominence of late-Romantic and early-modernist composers Karajan rarely toured.</p>

<h3>{linked_name("Simon Rattle")}<span class="years"> · 2002 – 2018</span></h3>
<p class="top-composers">{ticker("Simon Rattle")}</p>
<p>The most eclectic of the four. Beethoven and Brahms remain the bedrock, but Rattle introduces Strawinsky, Haydn, and Mahler at scale, plus a wide contemporary fringe: Boulez (<em>Notations</em>), Magnus Lindberg (<em>Aura</em>), Unsuk Chin (<em>Šu</em>), Adès, and Hosokawa Toshio (<em>Circulating Ocean</em>). Rachmaninow, Prokofjew, and Ravel earn footing too. Rattle clearly used the BPO touring platform to extend the canon outward — into post-1950 European modernism and Pacific-rim composers — while keeping the German tradition as the ground.</p>

<h3>{linked_name("Kirill Petrenko")}<span class="years"> · 2019 – present</span></h3>
<p class="top-composers">{ticker("Kirill Petrenko")}</p>
<p>A small sample so far, but already a distinctive profile. Brahms tops the list, but Berg's <em>Drei Orchesterstücke</em>, Reger, and R. Strauss are level with Brahms 2 in performance count; Mozart, Bartók, and Janáček round it out. The lineup signals a return to the dense early-modern Austro-German tradition — Reger barely appears in any other chief's repertoire — with the Second Viennese School in active rotation, continuing Abbado's line of interest but with darker, denser sub-repertoire.</p>
</section>

"""


# Hand-written notes per WPO conductor with >10 concerts (12 names as
# of the current dataset). Kept terse — the top-composer ticker
# beneath each heading is rebuilt from the live data on every render.
WPO_CONDUCTOR_NOTES = {
    "Riccardo Muti": (
        "Long-standing WPO touring partner. Schubert is the spine — four "
        "different symphonies appear, with the <em>Große</em> C-major as "
        "the tour signature (8 performances). Rossini overtures, "
        "particularly <em>Semiramide</em> (9), and Strawinsky's "
        "<em>Le baiser de la fée</em> Divertimento (6) recur as house "
        "pieces. Italian lyricism met Schubertian breadth."
    ),
    "Lorin Maazel": (
        "Pure canon-virtuoso. Beethoven 5 + 6, Mozart 25, R. Strauss "
        "<em>Don Juan</em>, and Tschaikowsky 5 each appear seven times — "
        "a tight rotation of canon symphonies framed by a tone-poem "
        "closer. Strauss-family encores recur after the symphonic main, "
        "Maazel's signature New-Year-style finish on tour."
    ),
    "Paul Hindemith": (
        "The orchestra's 1956 maiden Japan tour, led almost entirely by "
        "Hindemith as both composer-conductor and ambassador. A panorama "
        "of German tradition: Bach Suite 2, Mozart's <em>Fagottkonzert</em> "
        "and 3rd Horn Concerto, Wagner's <em>Siegfried-Idyll</em>, Brahms "
        "<em>Haydn-Variationen</em>, Beethoven 4 — pedagogical curation "
        "with a single Hindemith piece (the Sinfonietta) per evening."
    ),
    "Valery Gergiev": (
        "Two tours (2004, 2020). Tschaikowsky 6 <em>Pathétique</em> (9 "
        "performances) is the spine. A J. Strauss medley — "
        "<em>Krönungslieder</em>, <em>Niko-Polka</em>, "
        "<em>Kaiser-Walzer</em>, <em>Persischer Marsch</em>, "
        "<em>Wiener Blut</em> (5 each in 2004) — paired with Prokofjew "
        "Piano Concerto 2 (Matsuev) for a Russian / Vienna pairing "
        "characteristic of his approach."
    ),
    "Zubin Mehta": (
        "Tone-poem virtuoso. Debussy <em>La mer</em> (6) and R. Strauss "
        "<em>Ein Heldenleben</em> (5) are his calling cards. Brahms "
        "concertos with Buchbinder and Bronfman, Bruckner 7 and 8, and "
        "Webern's <em>Sechs Stücke</em> op. 6 sit comfortably next to "
        "the late-Romantic core."
    ),
    "Claudio Abbado": (
        "Beethoven <em>Eroica</em> (8) is the anchor, with Mozart 40 (5) "
        "and a Rossini <em>Il viaggio a Reims</em> staged-opera run (5) "
        "carrying the Italian operatic side. Webern's <em>Fünf Stücke</em> "
        "op. 10 (4) is the modernist marker — a hint of the same Berg / "
        "Webern thread Abbado pursued at the BPO."
    ),
    "Seiji Ozawa": (
        "Brahms-centred. A near-complete Brahms cycle (1 and 4 with 5 "
        "and 4 performances, plus 2 and 3 multiple times), then Bartók "
        "<em>Wonderful Mandarin</em> Suite (4), Dvořák <em>New World</em> "
        "(4) and Haydn 60 <em>Il distratto</em> (4) round it out. A "
        "global-citizen mix with the Romantic German core kept warm."
    ),
    "Christian Thielemann": (
        "Late-Romantic German weight. Brahms 4 and Schumann "
        "<em>Rheinische</em> (4 each) lead, with Bruckner 5 (Nowak) and "
        "8 (Haas) sitting deep in the catalogue. Beethoven "
        "<em>Pastorale</em> (3) and Strauss orchestral songs with "
        "Hampson complete the picture — a direct continuator of the "
        "Karajan / Böhm line at WPO."
    ),
    "Georg Solti": (
        "Tight Beethoven-Strauss-Schubert core: Beethoven 7 (10) and "
        "R. Strauss <em>Till Eulenspiegels lustige Streiche</em> (10) "
        "repeated obsessively, plus Schubert <em>Unvollendete</em> (8). "
        "Solti's WPO tours were canon-anchored power-stage evenings — "
        "very few outliers."
    ),
    "Karl Böhm": (
        "Mozart and Schubert specialist. Beethoven 5, 6, and 7 (3 each), "
        "Schubert <em>Unvollendete</em> and <em>Große</em> (2 each), "
        "Mozart 29 and <em>Jupiter</em>. Strauss-family encores after "
        "the symphonic main. Pure Viennese house repertoire."
    ),
    "Andris Nelsons": (
        "Newer-generation eclectic. Dvořák <em>New World</em> (4), "
        "Beethoven Piano Concerto 3 (3), Haydn 103 <em>Paukenwirbel</em> "
        "(3), Mozart 33 (3), Mussorgsky <em>Khovanshchina</em> Prelude "
        "(3), R. Strauss <em>Ein Heldenleben</em> (3), Shostakovich 9 "
        "(3). Short repertoire span but eclectic, including Henri "
        "Tomasi's Trombone Concerto — almost unique to him in our data."
    ),
    "Christoph Eschenbach": (
        "Liszt Piano Concerto 1 (4 performances) — a piano-conductor's "
        "signature, rarely toured by anyone else — plus Bruckner 4 "
        "<em>Romantische</em> (3) and Mozart <em>Jupiter</em> (3). "
        "A distinctive Liszt / Brucknerian fingerprint."
    ),
}


def wpo_analysis_html(totals: dict, details: dict, concerts: dict) -> str:
    """Analysis paragraphs for every WPO conductor who gave more than
    ten concerts. Conductors are ordered by total performance count."""

    def ticker(cond: str, n: int = 5) -> str:
        tops = composers_for(details, cond)[:n]
        return " · ".join(f"<b>{c}</b>&nbsp;{v}" for c, v in tops)

    eligible = [
        (cond, totals[cond], concerts[cond])
        for cond in totals
        if concerts.get(cond, 0) > 10 and cond in WPO_CONDUCTOR_NOTES
    ]
    eligible.sort(key=lambda x: -x[1])

    blocks = []
    for cond, total, n_concerts in eligible:
        note = WPO_CONDUCTOR_NOTES[cond]
        blocks.append(
            f'<h3>{linked_name(cond)}'
            f'<span class="years"> · {n_concerts} concerts, {total} performances</span>'
            f'</h3>\n'
            f'<p class="top-composers">{ticker(cond)}</p>\n'
            f'<p>{note}</p>'
        )

    body = "\n\n".join(blocks)
    return f"""<section class="analysis">
<h2>Programme tendencies — conductors with more than ten concerts</h2>
<p class="lede">Repertoire patterns across each conductor's documented Japan tours with the orchestra. WPO is self-governing — there is no <em>Chefdirigent</em> tradition — so the dozen below are simply the long-form guest collaborators.</p>

{body}
</section>

"""


def build_page(orchestra: str, totals: dict, details: dict, concerts: dict) -> str:
    if orchestra == "bpo":
        title    = "Berliner Philharmoniker — Performances by Conductor"
        title_pre = "Berliner Philharmoniker"
        bgcol    = "#FFF8EC"
        accent   = "#D97706"
        accent_d = "#B45309"
        accent_rgba = "rgba(180,83,9,0.25)"
        notes_color = "%23D97706"
        chart_grad_mid   = "rgba(254,215,170,0.55)"   # peach
        chart_grad_outer = "rgba(217,119,6,0.32)"     # amber edge
        analysis_section = bpo_analysis_html(details)
        extra_nav = ('<a href="Program_Trend_by_Era.html">Program Trend by Era</a>\n  '
                     '<a href="Audience_Analysis.html">Audience Statistics</a>\n  ')
        concerts_href = "Concerts_in_Japan.html"
    else:
        title    = "Wiener Philharmoniker — Performances by Conductor"
        title_pre = "Wiener Philharmoniker"
        bgcol    = "#FBF1F4"
        accent   = "#9F1239"
        accent_d = "#831234"
        accent_rgba = "rgba(159,18,57,0.25)"
        notes_color = "%239F1239"
        chart_grad_mid   = "rgba(251,207,232,0.55)"   # pale rose
        chart_grad_outer = "rgba(159,18,57,0.30)"     # burgundy edge
        analysis_section = wpo_analysis_html(totals, details, concerts)
        extra_nav = '<a href="Program_Trend_by_Era.html">Program Trend by Era</a>\n  '
        concerts_href = "Performances_in_Japan.html"

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
            "url": wiki_link(cond),
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
  /* Soft radial vignette in the accent palette — clear white-cream
     in the centre where the largest bubble sits, deepening toward
     the corners. Makes the portraits pop against the frame and
     ties the chart to the page's accent colour. */
  background:
    radial-gradient(circle at center,
      rgba(255,255,255,0.85) 0%,
      {chart_grad_mid}        45%,
      {chart_grad_outer}      100%);
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
/* SVG anchor wrapping a bubble — click opens the conductor's Wikipedia */
#chart a {{ cursor: pointer; outline: none; }}
#chart a:focus .bubble .ring-outer,
#chart a:hover .bubble .ring-outer {{
  stroke: {accent_d};
  stroke-width: 2.5;
  stroke-opacity: 1;
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
.analysis {{
  max-width: 900px;
  margin: 36px auto 0;
  padding: 18px 22px 22px;
  background: rgba(255,255,255,0.7);
  border-left: 4px solid {accent};
  border-radius: 4px;
  font-size: 13.5px;
  line-height: 1.55;
  color: #222;
}}
.analysis h2 {{
  margin: 0 0 6px;
  padding: 0 0 6px;
  font-size: 17px;
  font-weight: 700;
  color: {accent_d};
  border-bottom: 1px solid {accent_rgba};
}}
.analysis .lede {{
  margin: 4px 0 14px;
  color: #555;
  font-style: italic;
}}
.analysis h3 {{
  margin: 16px 0 4px;
  padding: 0;
  font-size: 14.5px;
  font-weight: 700;
  color: #1c1917;
}}
.analysis h3 a {{
  color: inherit;
  text-decoration: none;
  border-bottom: 1px dotted {accent_rgba};
}}
.analysis h3 a:hover {{ color: {accent_d}; border-bottom-color: {accent_d}; }}
.analysis h3 .years {{
  font-weight: 500;
  color: #888;
  font-size: 12.5px;
  margin-left: 6px;
}}
.analysis p {{
  margin: 0 0 4px;
}}
.analysis .top-composers {{
  font-size: 12px;
  color: #777;
  margin: 2px 0 4px;
  font-variant-numeric: tabular-nums;
}}
.analysis .top-composers b {{
  color: {accent_d};
}}
</style>
</head>
<body>
<div class="page-header">
<h1>{title}</h1>
<p class="subhead">Each bubble's area is proportional to that conductor's total performances on the orchestra's documented Japan tours. {total_cond} conductors, {total_perf} performances total — laid out by a hierarchical circle-pack.</p>
<p class="toolbar">
  <a href="{concerts_href}">Concerts in Japan</a>
  <a href="Program_Ranking.html">Program Ranking</a>
  <a href="Composer_Chart.html">Performances by Composer</a>
  <a href="Performances_by_Prefecture.html">Performances by Prefecture</a>
  {extra_nav}<a href="index.html">Home</a>
</p>
</div>

<div id="chart-wrap">
  <div id="chart"></div>
</div>

<div id="tooltip" role="tooltip"></div>

{analysis_section}
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

    // Per-conductor shift of the default-rendered image. Negative
    // values shift the image UP through the bubble, which moves the
    // visible source content DOWN (i.e. we scroll past the head to
    // reveal more of the face). Useful for photos where the subject's
    // face sits low in the source crop (mid-body or head-and-shoulders
    // shots with extra headroom) and ends up hidden behind the
    // bottom label band.
    const SHIFT_Y = {{
      "Andris Nelsons":  -0.30,   // 1:1.5 full-body press shot
      "Bernard Haitink": -0.40,   // 1:1.29 press shot with extra headroom
    }};

    // Always paint a faint accent fill behind the portrait — fills any
    // transparent margin left by a shifted/cropped image and gives
    // unmapped conductors a coloured circle to stand in for the photo.
    const fill = document.createElementNS(svgNS, 'circle');
    fill.setAttribute('cx', d.x);
    fill.setAttribute('cy', d.y);
    fill.setAttribute('r', d.r);
    fill.setAttribute('fill', '{accent}');
    fill.setAttribute('fill-opacity', d.data.img ? '0.15' : '0.40');
    g.appendChild(fill);

    if (d.data.img) {{
      const img = document.createElementNS(svgNS, 'image');
      img.setAttributeNS('http://www.w3.org/1999/xlink', 'href', d.data.img);
      img.setAttribute('href', d.data.img);
      const shiftY = SHIFT_Y[d.data.name] || 0;
      img.setAttribute('x', d.x - d.r);
      img.setAttribute('y', d.y - d.r + shiftY * d.r);
      img.setAttribute('width', d.r * 2);
      img.setAttribute('height', d.r * 2);
      img.setAttribute('preserveAspectRatio', 'xMidYMin slice');
      img.setAttribute('clip-path', `url(#${{cid}})`);
      g.appendChild(img);
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

    // Label: bottom band over the portrait. Family-name only so the
    // text fits inside crowded mid-size bubbles ("Maazel" instead of
    // "Lorin Maazel", "Welser-Möst" instead of "Franz Welser-Möst").
    const familyName = (full) => full.split(/\s+/).pop();
    const r = d.r;
    const nameSize  = Math.max(7,  Math.min(15, r * 0.15));
    const countSize = Math.max(11, Math.min(38, r * 0.34));
    const bandH = nameSize + countSize + 12;
    const bandY = d.y + r - bandH;
    if (r > 18) {{
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
      // Trim further by ellipsis if even the family name doesn't fit.
      let nameStr = familyName(d.data.name);
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

    // Wrap the bubble in <a> if we have a Wikipedia URL — clicking the
    // bubble opens the conductor's en.wikipedia article in a new tab.
    if (d.data.url) {{
      const link = document.createElementNS(svgNS, 'a');
      link.setAttribute('href', d.data.url);
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener');
      link.setAttribute('aria-label', `${{d.data.name}} — Wikipedia`);
      link.appendChild(g);
      svg.appendChild(link);
    }} else {{
      svg.appendChild(g);
    }}
  }});

  wrap.appendChild(svg);
}}

render();
window.addEventListener('resize', () => {{
  clearTimeout(window._chartResizeTimer);
  window._chartResizeTimer = setTimeout(render, 100);
}});

// Touch / tap-outside dismiss. On iPad and other touch devices, mouseenter
// fires on the first tap but mouseleave never does — so the tooltip stays
// pinned to the last conductor until another bubble is tapped. Listen at
// the document level for any pointerdown / touchend whose target isn't
// inside a bubble and hide the tooltip explicitly. The existing pointer
// handlers on desktop are unaffected.
function dismissIfOutsideBubble(evt) {{
  const t = evt.target;
  if (t && t.closest && t.closest('.bubble')) return;
  hideTooltip();
}}
document.addEventListener('pointerdown', dismissIfOutsideBubble, true);
document.addEventListener('touchend',    dismissIfOutsideBubble, true);
</script>
</body>
</html>
"""


def main():
    orchestra = sys.argv[1].lower() if len(sys.argv) > 1 else "bpo"
    if orchestra == "bpo":
        in_path  = "Berliner_Philharmoniker_in_Japan/Concerts_in_Japan.html"
        out_path = "Berliner_Philharmoniker_in_Japan/Performances_by_Conductor.html"
    elif orchestra == "wpo":
        in_path  = "Wiener_Philharmoniker_in_Japan/Performances_in_Japan.html"
        out_path = "Wiener_Philharmoniker_in_Japan/Performances_by_Conductor.html"
    else:
        print(f"Unknown orchestra '{orchestra}'. Use 'bpo' or 'wpo'.", file=sys.stderr)
        sys.exit(1)

    with open(in_path, encoding="utf-8") as f:
        html = f.read()
    totals, details, concerts = aggregate(html)

    page = build_page(orchestra, totals, details, concerts)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Wrote {out_path}")
    print(f"  {len(totals)} conductors, {sum(totals.values())} total performances")
    missing = [c for c in totals if c not in CONDUCTOR_IMAGE]
    if missing:
        print(f"  (no portrait mapped for: {missing})")


if __name__ == "__main__":
    main()
