"""Build the Berliner Philharmoniker Program Ranking from Concerts_in_Japan.

Scans every concert row, normalises each work in the Program cell, sums
performances per work + per conductor, and writes a new <tbody> sorted
by descending total. Tied totals share a rank. Wikipedia <a> wrappers
already present on the ranking page are preserved across regenerations.

Run with --write to update Program_Ranking.html, --check to just print.
"""
import re
import sys

REPO = "Berliner Philharmoniker"
CONCERTS = f"{REPO}/Concerts_in_Japan.html"
RANKING = f"{REPO}/Program_Ranking.html"

PLACEHOLDER_TOKENS = (
    "to be researched",
    "not documented",
    "various programs",
    "program details",
    "program not",
    "works by",  # grab-bag listings, not a single work
)


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def is_placeholder(w: str) -> bool:
    if not w or len(w) < 3:
        return True
    low = w.lower()
    return any(tok in low for tok in PLACEHOLDER_TOKENS)


# Canonical name lookup — different surface forms that should count as the
# same work. Add entries here if regeneration starts splitting a work in
# two because the Concerts page uses two slightly different titles for it.
CANONICAL: dict[str, str] = {
    # Beethoven symphonies — sometimes appear with or without op. number
    "Beethoven: Sinfonie Nr. 1": "Beethoven: Sinfonie Nr. 1 C-Dur",
    "Beethoven: Sinfonie Nr. 2": "Beethoven: Sinfonie Nr. 2 D-Dur",
    "Beethoven: Sinfonie Nr. 4": "Beethoven: Sinfonie Nr. 4 B-Dur",
    "Beethoven: Sinfonie Nr. 5": "Beethoven: Sinfonie Nr. 5 c-Moll",
    "Beethoven: Sinfonie Nr. 7": "Beethoven: Sinfonie Nr. 7 A-Dur",
    "Beethoven: Sinfonie Nr. 8": "Beethoven: Sinfonie Nr. 8 F-Dur",
    "Brahms: Sinfonie Nr. 1": "Brahms: Sinfonie Nr. 1 c-Moll",
    "Brahms: Sinfonie Nr. 2": "Brahms: Sinfonie Nr. 2 D-Dur",
    "Brahms: Sinfonie Nr. 3": "Brahms: Sinfonie Nr. 3 F-Dur",
    "Brahms: Sinfonie Nr. 4": "Brahms: Sinfonie Nr. 4 e-Moll",
    "Brahms: Klavierkonzert Nr. 1": "Brahms: Klavierkonzert Nr. 1 d-Moll",
    "Brahms: Klavierkonzert Nr. 2": "Brahms: Klavierkonzert Nr. 2 B-Dur",
    # Works with widely-used nicknames — collapse name-only and name+nickname
    # variants so both feed the same ranking row. Nicknames are wrapped in
    # <em> for italic display; Schubert 8 also gets its D. 759 catalogue number.
    "Beethoven: Sinfonie Nr. 3": "Beethoven: Sinfonie Nr. 3 Es-Dur, <em>Eroica</em>",
    "Beethoven: Sinfonie Nr. 3 Es-Dur": "Beethoven: Sinfonie Nr. 3 Es-Dur, <em>Eroica</em>",
    "Beethoven: Sinfonie Nr. 3 Es-Dur, Eroica": "Beethoven: Sinfonie Nr. 3 Es-Dur, <em>Eroica</em>",
    "Beethoven: Sinfonie Nr. 6": "Beethoven: Sinfonie Nr. 6 F-Dur, <em>Pastorale</em>",
    "Beethoven: Sinfonie Nr. 6 F-Dur": "Beethoven: Sinfonie Nr. 6 F-Dur, <em>Pastorale</em>",
    "Beethoven: Sinfonie Nr. 6 F-Dur, Pastorale": "Beethoven: Sinfonie Nr. 6 F-Dur, <em>Pastorale</em>",
    "Beethoven: Sinfonie Nr. 9": "Beethoven: Sinfonie Nr. 9 d-Moll, <em>Choral</em>",
    "Beethoven: Sinfonie Nr. 9 d-Moll": "Beethoven: Sinfonie Nr. 9 d-Moll, <em>Choral</em>",
    "Beethoven: Sinfonie Nr. 9 d-Moll, Choral": "Beethoven: Sinfonie Nr. 9 d-Moll, <em>Choral</em>",
    "Schubert: Sinfonie Nr. 8": "Schubert: Sinfonie Nr. 8 h-Moll, <em>Unvollendete</em>",
    "Schubert: Sinfonie Nr. 8 h-Moll": "Schubert: Sinfonie Nr. 8 h-Moll, <em>Unvollendete</em>",
    "Schubert: Sinfonie Nr. 8 h-Moll, Unvollendete": "Schubert: Sinfonie Nr. 8 h-Moll, <em>Unvollendete</em>",
    "Tschaikowsky: Sinfonie Nr. 6": "Tschaikowsky: Sinfonie Nr. 6 h-Moll, <em>Pathétique</em>",
    "Tschaikowsky: Sinfonie Nr. 6 h-Moll": "Tschaikowsky: Sinfonie Nr. 6 h-Moll, <em>Pathétique</em>",
    "Tschaikowsky: Sinfonie Nr. 6 h-Moll, Pathétique": "Tschaikowsky: Sinfonie Nr. 6 h-Moll, <em>Pathétique</em>",
    # Mozart symphonies with universally-used nicknames
    "Mozart: Sinfonie Nr. 35": "Mozart: Sinfonie Nr. 35 D-Dur, <em>Haffner</em>",
    "Mozart: Sinfonie Nr. 35 D-Dur": "Mozart: Sinfonie Nr. 35 D-Dur, <em>Haffner</em>",
    "Mozart: Sinfonie Nr. 35 D-Dur, Haffner": "Mozart: Sinfonie Nr. 35 D-Dur, <em>Haffner</em>",
    "Mozart: Sinfonie Nr. 38": "Mozart: Sinfonie Nr. 38 D-Dur, <em>Prager</em>",
    "Mozart: Sinfonie Nr. 38 D-Dur": "Mozart: Sinfonie Nr. 38 D-Dur, <em>Prager</em>",
    "Mozart: Sinfonie Nr. 38 D-Dur, Prager": "Mozart: Sinfonie Nr. 38 D-Dur, <em>Prager</em>",
    "Mozart: Sinfonie Nr. 41": "Mozart: Sinfonie Nr. 41 C-Dur, <em>Jupiter</em>",
    "Mozart: Sinfonie Nr. 41 C-Dur": "Mozart: Sinfonie Nr. 41 C-Dur, <em>Jupiter</em>",
    "Mozart: Sinfonie Nr. 41 C-Dur, Jupiter": "Mozart: Sinfonie Nr. 41 C-Dur, <em>Jupiter</em>",
    # Brahms titled works
    "Brahms: Variationen über ein Thema von Haydn": "Brahms: <em>Variationen über ein Thema von Haydn</em>",
    "Brahms: Haydn-Variationen": "Brahms: <em>Variationen über ein Thema von Haydn</em>",
    "Brahms: Tragische Ouvertüre": "Brahms: <em>Tragische Ouvertüre</em>",
    "Brahms: Akademische Festouvertüre": "Brahms: <em>Akademische Festouvertüre</em>",
    # Beethoven incidental music + overtures
    "Beethoven: Coriolan-Ouvertüre": "Beethoven: <em>Coriolan</em>-Ouvertüre",
    "Beethoven: Egmont": "Beethoven: <em>Egmont</em>",
    "Beethoven: Egmont-Ouvertüre": "Beethoven: <em>Egmont</em>-Ouvertüre",
    "Beethoven: Fidelio": "Beethoven: <em>Fidelio</em>",
    "Beethoven: Leonore-Ouvertüre Nr. 3": "Beethoven: <em>Leonore</em>-Ouvertüre Nr. 3",
    # R. Strauss tone poems
    "R. Strauss: Ein Heldenleben": "R. Strauss: <em>Ein Heldenleben</em>",
    "R. Strauss: Don Juan": "R. Strauss: <em>Don Juan</em>",
    "R. Strauss: Don Quixote": "R. Strauss: <em>Don Quixote</em>",
    "R. Strauss: Also sprach Zarathustra": "R. Strauss: <em>Also sprach Zarathustra</em>",
    "R. Strauss: Till Eulenspiegels lustige Streiche": "R. Strauss: <em>Till Eulenspiegels lustige Streiche</em>",
    # Debussy
    "Debussy: La mer": "Debussy: <em>La mer</em>",
    "Debussy: Prélude à l'après-midi d'un faune": "Debussy: <em>Prélude à l'après-midi d'un faune</em>",
    "Debussy: Nocturnes": "Debussy: <em>Nocturnes</em>",
    # Stravinsky ballets / orchestral works
    "Strawinsky: L'oiseau de feu, Suite": "Strawinsky: <em>L'oiseau de feu</em>, Suite",
    "Strawinsky: Le sacre du printemps": "Strawinsky: <em>Le sacre du printemps</em>",
    "Strawinsky: Petruschka": "Strawinsky: <em>Petruschka</em>",
    # Dvořák
    "Dvořák: Sinfonie Nr. 9 e-Moll, Aus der Neuen Welt": "Dvořák: Sinfonie Nr. 9 e-Moll, <em>Aus der Neuen Welt</em>",
    "Dvořák: Symphonische Dichtung Die Waldtaube": "Dvořák: Symphonische Dichtung <em>Die Waldtaube</em>",
    # Wagner operas
    "Wagner: Die Meistersinger von Nürnberg, Vorspiel zum 1. Akt": "Wagner: <em>Die Meistersinger von Nürnberg</em>, Vorspiel zum 1. Akt",
    "Wagner: Tristan und Isolde": "Wagner: <em>Tristan und Isolde</em>",
    "Wagner: Tristan und Isolde, Vorspiel und Liebestod": "Wagner: <em>Tristan und Isolde</em>, Vorspiel und Liebestod",
    "Wagner: Tannhäuser-Ouvertüre": "Wagner: <em>Tannhäuser</em>-Ouvertüre",
    "Wagner: Siegfried-Idyll": "Wagner: <em>Siegfried-Idyll</em>",
    # Mahler song cycles
    "Mahler: Rückert-Lieder": "Mahler: <em>Rückert-Lieder</em>",
    # Schumann
    "Schumann: Manfred-Ouvertüre": "Schumann: <em>Manfred</em>-Ouvertüre",
    # Ravel
    "Ravel: Daphnis et Chloé, Suite Nr. 2": "Ravel: <em>Daphnis et Chloé</em>, Suite Nr. 2",
    "Ravel: La valse": "Ravel: <em>La valse</em>",
    "Ravel: Boléro": "Ravel: <em>Boléro</em>",
    "Ravel: Rhapsodie espagnole": "Ravel: <em>Rhapsodie espagnole</em>",
    # Bartók
    "Bartók: Suite aus Der wunderbare Mandarin": "Bartók: Suite aus <em>Der wunderbare Mandarin</em>",
    # Bernstein
    "Bernstein: West Side Story, Symphonische Tänze": "Bernstein: <em>West Side Story</em>, Symphonische Tänze",
    # Hindemith
    "Hindemith: Sinfonie Mathis der Maler": "Hindemith: Sinfonie <em>Mathis der Maler</em>",
    # Janáček
    "Janáček: Lašské tance": "Janáček: <em>Lašské tance</em>",
    # Smetana
    "Smetana: Die Moldau": "Smetana: <em>Die Moldau</em>",
    # Mussorgsky (standalone, not the Bilder pictures already handled)
    "Mussorgsky: Eine Nacht auf dem kahlen Berge": "Mussorgsky: <em>Eine Nacht auf dem kahlen Berge</em>",
    # Respighi
    "Respighi: Pini di Roma": "Respighi: <em>Pini di Roma</em>",
    # Magnus Lindberg
    "Magnus Lindberg: Aura": "Magnus Lindberg: <em>Aura</em>",
    # Unsuk Chin
    "Unsuk Chin: Chorós Chordón": "Unsuk Chin: <em>Chorós Chordón</em>",
    # Boulez
    "Boulez: Notations I–IV, VII": "Boulez: <em>Notations I–IV, VII</em>",
    # Reger
    "Reger: Mozart-Variationen": "Reger: <em>Mozart-Variationen</em>",
    # Berg
    "Berg: Drei Orchesterstücke": "Berg: <em>Drei Orchesterstücke</em>",
    "Berg: Drei Stücke für Orchester": "Berg: <em>Drei Stücke für Orchester</em>",
    # Weber
    "Weber: Oberon, Ouvertüre": "Weber: <em>Oberon</em>, Ouvertüre",
    # Verdi
    "Verdi: Requiem": "Verdi: <em>Requiem</em>",
    # Mussorgsky's Pictures has appeared on BPO Japan tours only in
    # Ravel's orchestration — credit the arranger in the display name.
    "Mussorgsky: Bilder einer Ausstellung": "Mussorgsky: <em>Bilder einer Ausstellung</em> (Bearbeitung von Maurice Ravel)",
    "Mussorgsky/Ravel: Bilder einer Ausstellung": "Mussorgsky: <em>Bilder einer Ausstellung</em> (Bearbeitung von Maurice Ravel)",
}


CAT_RE = re.compile(
    r"\b(op\.\s*\d+[a-z]?|KV\s*\d+[a-z]?|BWV\s*\d+|D\.\s*\d+|"
    r"Hob\.\s*[IV]+:\d+|WAB\s*\d+|Sz\.\s*\d+|TrV\s*\d+|HWV\s*\d+)\b"
)

KNOWN_COMPOSERS = (
    "Bach (arr. Webern)", "Bach", "Bartók", "Beethoven", "Berg", "Berlioz",
    "Bernstein", "Boulez", "Brahms", "Britten", "Bruckner", "Chopin",
    "Debussy", "Dukas", "Dvořák", "Falla", "Fortner", "Glinka", "Grieg",
    "Haydn", "Hindemith", "Honegger", "Janáček", "Liszt", "Magnus Lindberg",
    "Mahler", "Mendelssohn", "Mozart", "Mussorgsky/Ravel",
    "Mussorgsky (arr. Schostakowitsch)", "Mussorgsky", "Nielsen", "Prokofjew",
    "R. Strauss", "Rachmaninow", "Ravel", "Reger", "Respighi", "Reznicek",
    "Rimsky-Korsakow", "Rossini", "Saint-Saëns", "Schönberg",
    "Schostakowitsch", "Schubert", "Schumann", "Sibelius", "Smetana",
    "Strawinsky", "Takemitsu", "Tschaikowsky", "Unsuk Chin", "Verdi",
    "Wagner", "Weber", "Webern", "Wolf", "J. Strauss II", "J. Strauss",
    "Josef Strauss", "Adès", "Hayashi",
)

# Populated by main() from the concerts file. Used by normalize_work to
# append a catalogue suffix (op./D./KV/BWV/…) when the canonical display
# string lacks one but a known catalogue number exists in the data.
CAT_MAP: dict[tuple[str, str], str] = {}


def build_cat_map(concerts: str) -> dict[tuple[str, str], str]:
    """Walk the concerts page and build {(composer, work_base): catalogue}.

    work_base is the plain (no-markup, no-catalogue, no-nickname) form,
    so it matches what normalize_work + CANONICAL produce after stripping.
    The most common catalogue for each work wins (Counter.most_common).
    """
    from collections import Counter
    tbody_m = re.search(r"<tbody>(.*?)</tbody>", concerts, re.DOTALL)
    if not tbody_m:
        return {}
    samples: dict[tuple[str, str], Counter] = {}
    for row in re.findall(r"<tr>.*?</tr>", tbody_m.group(1), re.DOTALL):
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 6:
            continue
        composer = None
        for line in re.split(r"<br\s*/?>", tds[5]):
            plain = strip_tags(line).strip()
            if not plain:
                continue
            prefix = next((c for c in KNOWN_COMPOSERS if plain.startswith(c + ": ")), None)
            if prefix:
                composer = prefix
                work = plain[len(prefix) + 2:]
            else:
                work = plain
            if not composer:
                continue
            cat = CAT_RE.search(work)
            if not cat:
                continue
            base = work[:cat.start()].rstrip()
            base = re.sub(r",\s*[A-Za-zÉ][^,]*$", "", base).strip()
            base = re.sub(r"\s*\([^)]*\)\s*$", "", base).strip()
            samples.setdefault((composer, base), Counter())[cat.group(1)] += 1
    return {k: v.most_common(1)[0][0] for k, v in samples.items()}


def append_catalogue(display: str) -> str:
    """If `display` lacks a catalogue suffix but CAT_MAP has one for the
    underlying (composer, work_base), insert it. The catalogue goes
    BEFORE any comma-style nickname so the order reads e.g.
    "Sinfonie Nr. 3 Es-Dur op. 55, <em>Eroica</em>"."""
    plain = strip_tags(display)
    if CAT_RE.search(plain):
        return display
    composer = next((c for c in KNOWN_COMPOSERS if plain.startswith(c + ": ")), None)
    if not composer:
        return display
    base = plain[len(composer) + 2:]
    base = re.sub(r",\s*[A-Za-zÉ][^,]*$", "", base).strip()
    base = re.sub(r"\s*\([^)]*\)\s*$", "", base).strip()
    cat = CAT_MAP.get((composer, base))
    if not cat:
        return display
    # Insert before a trailing comma-style nickname (with or without <em>);
    # otherwise just append at the end.
    nick_m = re.search(r",\s*<em>[^<]+</em>\s*$", display)
    if nick_m:
        return display[:nick_m.start()] + " " + cat + display[nick_m.start():]
    nick_m = re.search(r",\s*[A-ZÉ][^,]*$", display)
    if nick_m:
        return display[:nick_m.start()] + " " + cat + display[nick_m.start():]
    return display + " " + cat


def normalize_work(w: str) -> str:
    """Drop opus/catalogue numbers and trailing parentheticals so that
    e.g. 'Beethoven: Sinfonie Nr. 5 c-Moll op. 67' and 'Beethoven: Sinfonie
    Nr. 5 c-Moll' both collapse to the same key. After canonicalising,
    re-append a catalogue suffix (op./D./KV/…) from CAT_MAP so the
    displayed ranking row shows a consistent catalogue number."""
    w = strip_tags(w).strip()
    # Strip catalogue numbers
    w = re.sub(r"\s+op\.\s*\d+[a-z]?", "", w)
    w = re.sub(r"\s+KV\s*\d+[a-z]?", "", w)
    w = re.sub(r"\s+BWV\s*\d+", "", w)
    w = re.sub(r"\s+Sz\.\s*\d+", "", w)
    w = re.sub(r"\s+D\.\s*\d+", "", w)
    w = re.sub(r"\s+M\.\s*\d+", "", w)
    w = re.sub(r"\s+WWV\s*\d+", "", w)
    w = re.sub(r"\s+WAB\s*\d+", "", w)
    w = re.sub(r"\s+Hob\.\s*I:?\d+", "", w)
    w = re.sub(r"\s+HWV\s*\d+", "", w)
    w = re.sub(r"\s+TrV\s*\d+", "", w)
    # Strip trailing parentheticals (nickname / format / conductor / ed.)
    prev = None
    while prev != w:
        prev = w
        w = re.sub(r"\s*\([^)]*\)\s*$", "", w).strip()
    canonical = CANONICAL.get(w, w)
    return append_catalogue(canonical)


def expand_program(program_html: str):
    """Split a Program cell by <br>, strip tags, propagate composer prefix."""
    parts = re.split(r"<br\s*/?>", program_html)
    current_composer = None
    out = []
    for raw in parts:
        w = strip_tags(raw).strip()
        if not w:
            continue
        m = re.match(r"^([^\W\d_][^:\d\n]*?):\s+(.+)$", w, re.UNICODE)
        if m and m.group(1)[0].isupper() and len(m.group(1)) < 40:
            current_composer = m.group(1).strip()
            out.append(w)
        else:
            if current_composer:
                out.append(f"{current_composer}: {w}")
            else:
                out.append(w)
    return out


def main():
    with open(CONCERTS, encoding="utf-8") as f:
        concerts = f.read()
    with open(RANKING, encoding="utf-8") as f:
        ranking = f.read()

    # Populate the module-level CAT_MAP so normalize_work can append
    # consistent op./D./KV/… numbers to each work's display string.
    global CAT_MAP
    CAT_MAP = build_cat_map(concerts)

    # Preserve any existing <a> wrappers on the ranking so the Wikipedia
    # link layer survives regeneration. The lazy .+? handles work names
    # that include their own HTML markup (e.g. <em>Unvollendete</em>).
    # We also store an alias under the catalogue-appended form so the
    # anchor follows the work when the displayed name picks up a new
    # op./D./KV/… suffix between regenerations.
    work_link: dict[str, str] = {}
    for anchor, work in re.findall(
        r"<tr><td>\d+</td><td>(<a [^>]*>)(.+?)</a></td>",
        ranking,
    ):
        work_link[work] = anchor
        # Alias 1: same work with the catalogue appended (covers the case
        # where the existing row has no catalogue but the new canonical
        # will).
        appended = append_catalogue(work)
        if appended != work:
            work_link[appended] = anchor
        # Alias 2: same work with catalogue moved from after the
        # comma-nickname to before it ("WORK, <em>Nick</em> op. N" →
        # "WORK op. N, <em>Nick</em>"). Covers the historical "nickname
        # before catalogue" style this script no longer emits.
        m = re.search(
            r",\s*(<em>[^<]+</em>)\s+(\b(?:op\.|KV|BWV|D\.|Hob\.|WAB|Sz\.|TrV|HWV)\s*\d+(?:[a-z]|:?\d+)*\b)",
            work,
        )
        if m:
            reordered = work[:m.start()] + " " + m.group(2) + ", " + m.group(1) + work[m.end():]
            work_link[reordered] = anchor

    tbody_match = re.search(r"<tbody>(.*?)</tbody>", concerts, re.DOTALL)
    if not tbody_match:
        print("Could not find <tbody> in concerts file", file=sys.stderr)
        return 1
    tbody = tbody_match.group(1)
    rows = re.findall(r"<tr>.*?</tr>", tbody, re.DOTALL)

    # work → {conductor: count}
    work_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 6:
            continue
        conductor = strip_tags(tds[4]).strip()
        program = tds[5]
        for w in expand_program(program):
            if is_placeholder(w):
                continue
            normalized = normalize_work(w)
            if is_placeholder(normalized):
                continue
            # Skip "Composer: Sinfonien" without a specific number — generic
            # placeholder for an undocumented multi-symphony program.
            if re.match(r"^[^:]+:\s+Sinfonien\s*$", normalized):
                continue
            work_counts.setdefault(normalized, {})
            work_counts[normalized][conductor] = (
                work_counts[normalized].get(conductor, 0) + 1
            )

    # Keep works that have appeared at least twice (matching the existing
    # threshold used by the WPO equivalent).
    ranked = [
        (work, sum(conductors.values()), conductors)
        for work, conductors in work_counts.items()
        if sum(conductors.values()) >= 2
    ]
    ranked.sort(key=lambda x: (-x[1], x[0]))

    if "--check" in sys.argv:
        for i, (work, total, conductors) in enumerate(ranked, 1):
            print(f"#{i} {work}: total={total}")
            for c, n in sorted(conductors.items(), key=lambda x: (-x[1], x[0])):
                print(f"   {c}: {n}")
        return 0

    if "--write" not in sys.argv:
        print("Pass --check to print the ranking or --write to update the page.")
        return 0

    # Ensure the <thead> includes the "Performances by Conductor" column.
    new_ranking = ranking.replace(
        '<thead><tr><th>#</th><th>Composer &amp; Work</th><th>Performances</th></tr></thead>',
        '<thead><tr><th>#</th><th>Composer &amp; Work</th><th>Performances</th><th>Performances by Conductor</th></tr></thead>',
    )

    new_rows = []
    prev_total = None
    current_rank = 0
    for position, (work, total, conductors) in enumerate(ranked, start=1):
        if total != prev_total:
            current_rank = position
            prev_total = total
        lines = [
            f"{c}: {n}"
            for c, n in sorted(conductors.items(), key=lambda x: (-x[1], x[0]))
        ]
        cell = "<br>".join(lines) if lines else "—"
        anchor = work_link.get(work, "")
        work_html = f"{anchor}{work}</a>" if anchor else work
        new_rows.append(
            f"<tr><td>{current_rank}</td><td>{work_html}</td>"
            f"<td>{total}</td><td>{cell}</td></tr>"
        )

    new_tbody = "<tbody>\n" + "\n".join(new_rows) + "\n</tbody>"
    new_ranking = re.sub(r"<tbody>.*?</tbody>", new_tbody, new_ranking, flags=re.DOTALL)

    with open(RANKING, "w", encoding="utf-8") as f:
        f.write(new_ranking)
    print(f"Wrote {RANKING} with {len(ranked)} ranked works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
