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
    # variants so both feed the same ranking row.
    "Beethoven: Sinfonie Nr. 3":                       "Beethoven: Sinfonie Nr. 3 Es-Dur, Eroica",
    "Beethoven: Sinfonie Nr. 3 Es-Dur":                "Beethoven: Sinfonie Nr. 3 Es-Dur, Eroica",
    "Beethoven: Sinfonie Nr. 6":                       "Beethoven: Sinfonie Nr. 6 F-Dur, Pastorale",
    "Beethoven: Sinfonie Nr. 6 F-Dur":                 "Beethoven: Sinfonie Nr. 6 F-Dur, Pastorale",
    "Beethoven: Sinfonie Nr. 9":                       "Beethoven: Sinfonie Nr. 9 d-Moll, Choral",
    "Beethoven: Sinfonie Nr. 9 d-Moll":                "Beethoven: Sinfonie Nr. 9 d-Moll, Choral",
    "Schubert: Sinfonie Nr. 8":                        "Schubert: Sinfonie Nr. 8 h-Moll, Unvollendete",
    "Schubert: Sinfonie Nr. 8 h-Moll":                 "Schubert: Sinfonie Nr. 8 h-Moll, Unvollendete",
    "Tschaikowsky: Sinfonie Nr. 6":                    "Tschaikowsky: Sinfonie Nr. 6 h-Moll, Pathétique",
    "Tschaikowsky: Sinfonie Nr. 6 h-Moll":             "Tschaikowsky: Sinfonie Nr. 6 h-Moll, Pathétique",
    # Mussorgsky's Pictures has appeared on BPO Japan tours only in
    # Ravel's orchestration — credit the arranger in the display name.
    "Mussorgsky: Bilder einer Ausstellung":            "Mussorgsky: Bilder einer Ausstellung (Bearbeitung von Maurice Ravel)",
    "Mussorgsky/Ravel: Bilder einer Ausstellung":      "Mussorgsky: Bilder einer Ausstellung (Bearbeitung von Maurice Ravel)",
}


def normalize_work(w: str) -> str:
    """Drop opus/catalogue numbers and trailing parentheticals so that
    e.g. 'Beethoven: Sinfonie Nr. 5 c-Moll op. 67' and 'Beethoven: Sinfonie
    Nr. 5 c-Moll' both collapse to the same key."""
    w = strip_tags(w).strip()
    # Strip catalogue numbers
    w = re.sub(r"\s+op\.\s*\d+[a-z]?", "", w)
    w = re.sub(r"\s+KV\s*\d+", "", w)
    w = re.sub(r"\s+BWV\s*\d+", "", w)
    w = re.sub(r"\s+Sz\.\s*\d+", "", w)
    w = re.sub(r"\s+D\.\s*\d+", "", w)
    w = re.sub(r"\s+M\.\s*\d+", "", w)
    w = re.sub(r"\s+WWV\s*\d+", "", w)
    w = re.sub(r"\s+WAB\s*\d+", "", w)
    w = re.sub(r"\s+Hob\.\s*I:?\d+", "", w)
    # Strip trailing parentheticals (nickname / format / conductor / ed.)
    prev = None
    while prev != w:
        prev = w
        w = re.sub(r"\s*\([^)]*\)\s*$", "", w).strip()
    return CANONICAL.get(w, w)


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

    # Preserve any existing <a> wrappers on the ranking so the Wikipedia
    # link layer survives regeneration.
    work_link: dict[str, str] = {}
    for anchor, work in re.findall(
        r"<tr><td>\d+</td><td>(<a [^>]*>)([^<]+)</a></td>",
        ranking,
    ):
        work_link[work] = anchor

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
