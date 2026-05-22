"""Build the Wiener Philharmoniker Program Ranking from Concerts_in_Japan data.

Computes per-conductor performance counts for each work that appears 2+
times across all documented Japan tours, sorts by descending total, and
writes the table body into Program_Ranking.html.
"""
import re
import sys

REPO = "Wiener Philharmoniker"
CONCERTS = f"{REPO}/Concerts_in_Japan.html"
RANKING = f"{REPO}/Program_Ranking.html"

PLACEHOLDER_TOKENS = (
    "to be researched",
    "not documented",
)


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def is_placeholder(w: str) -> bool:
    if not w or len(w) < 3:
        return True
    low = w.lower()
    if any(tok in low for tok in PLACEHOLDER_TOKENS):
        return True
    if low.startswith("various programs"):
        return True
    if low.startswith("program details") or low.startswith("program not"):
        return True
    if low.startswith("three concerts") or low.startswith("three programs"):
        return True
    if low.startswith("brahms symphonies and"):
        return True
    if low.startswith("german/austrian core"):
        return True
    return False


CANONICAL = {
    "Beethoven: Sinfonie Nr. 1": "Beethoven: Sinfonie Nr. 1 C-Dur",
    "Beethoven: Sinfonie Nr. 2": "Beethoven: Sinfonie Nr. 2 D-Dur",
    "Beethoven: Sinfonie Nr. 3": "Beethoven: Sinfonie Nr. 3 Es-Dur",
    "Beethoven: Sinfonie Nr. 4": "Beethoven: Sinfonie Nr. 4 B-Dur",
    "Beethoven: Sinfonie Nr. 5": "Beethoven: Sinfonie Nr. 5 c-Moll",
    "Beethoven: Sinfonie Nr. 6": "Beethoven: Sinfonie Nr. 6 F-Dur",
    "Beethoven: Sinfonie Nr. 7": "Beethoven: Sinfonie Nr. 7 A-Dur",
    "Beethoven: Sinfonie Nr. 8": "Beethoven: Sinfonie Nr. 8 F-Dur",
    "Beethoven: Sinfonie Nr. 9": "Beethoven: Sinfonie Nr. 9 d-Moll",
    "Brahms: Sinfonie Nr. 1": "Brahms: Sinfonie Nr. 1 c-Moll",
    "Brahms: Sinfonie Nr. 2": "Brahms: Sinfonie Nr. 2 D-Dur",
    "Brahms: Sinfonie Nr. 3": "Brahms: Sinfonie Nr. 3 F-Dur",
    "Brahms: Sinfonie Nr. 4": "Brahms: Sinfonie Nr. 4 e-Moll",
    "R. Strauss: Till Eulenspiegel": "R. Strauss: Till Eulenspiegels lustige Streiche",
    "R. Strauss: Till Eulenspiegels lustige Streiche": "R. Strauss: Till Eulenspiegels lustige Streiche",
}


def normalize_work(w: str) -> str:
    w = strip_tags(w).strip()
    # Strip catalog numbers
    w = re.sub(r"\s+op\.\s*\d+[a-z]?", "", w)
    w = re.sub(r"\s+KV\s*\d+", "", w)
    w = re.sub(r"\s+BWV\s*\d+", "", w)
    w = re.sub(r"\s+Sz\.\s*\d+", "", w)
    w = re.sub(r"\s+D\.\s*\d+", "", w)
    w = re.sub(r"\s+M\.\s*\d+", "", w)
    w = re.sub(r"\s+WWV\s*\d+", "", w)
    w = re.sub(r"\s+WAB\s*\d+", "", w)
    # Strip trailing parentheticals repeatedly (nickname, format, conductor)
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

    tbody_match = re.search(r"<tbody>(.*?)</tbody>", concerts, re.DOTALL)
    if not tbody_match:
        print("Could not find <tbody> in concerts file", file=sys.stderr)
        return 1
    tbody = tbody_match.group(1)
    rows = re.findall(r"<tr>.*?</tr>", tbody, re.DOTALL)

    work_counts = {}

    for row in rows:
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 6:
            continue
        conductor = strip_tags(tds[4]).strip()
        program = tds[5]
        for w in expand_program(program):
            normalized = normalize_work(w)
            if is_placeholder(normalized):
                continue
            work_counts.setdefault(normalized, {})
            work_counts[normalized][conductor] = (
                work_counts[normalized].get(conductor, 0) + 1
            )

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

    new_rows = []
    for i, (work, total, conductors) in enumerate(ranked, 1):
        lines = [
            f"{c}: {n}"
            for c, n in sorted(conductors.items(), key=lambda x: (-x[1], x[0]))
        ]
        cell = "<br>".join(lines)
        new_rows.append(
            f"<tr><td>{i}</td><td>{work}</td><td>{total}</td><td>{cell}</td></tr>"
        )

    new_tbody = "<tbody>\n" + "\n".join(new_rows) + "\n</tbody>"
    ranking = re.sub(r"<tbody>.*?</tbody>", new_tbody, ranking, flags=re.DOTALL)

    with open(RANKING, "w", encoding="utf-8") as f:
        f.write(ranking)
    print(f"Wrote {RANKING} with {len(ranked)} ranked works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
