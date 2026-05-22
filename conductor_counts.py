"""Compute per-conductor performance counts for every work in Program_Ranking.

Reads Concerts_in_Japan.html, sums conductor appearances per ranked work,
and (when run with --write) injects a new <td> into each ranking row.
"""
import re
import subprocess
import sys

REPO = "Berliner Philharmoniker"
CONCERTS = f"{REPO}/Concerts_in_Japan.html"
RANKING = f"{REPO}/Program_Ranking.html"
BASELINE_REF = "HEAD~1"  # commit whose Performances column is the source of truth


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def expand_program(program_html: str):
    """Split a Program cell by <br>, strip tags, propagate composer prefix."""
    parts = re.split(r"<br\s*/?>", program_html)
    current_composer = None
    out = []
    for raw in parts:
        w = strip_tags(raw).strip()
        if not w:
            continue
        # New composer if the leading token before ':' is capitalised words
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

    # Pull the ranking work names (col 2 of each ranking row)
    ranking_rows = re.findall(
        r"<tr><td>(\d+)</td><td>([^<]+)</td><td>(\d+)</td>", ranking
    )
    ranking_works = [r[1] for r in ranking_rows]
    # Longest-prefix match priority
    sorted_works = sorted(set(ranking_works), key=len, reverse=True)

    counts = {w: {} for w in sorted_works}

    tbody = re.search(r"<tbody>(.*?)</tbody>", concerts, re.DOTALL).group(1)
    rows = re.findall(r"<tr>.*?</tr>", tbody, re.DOTALL)

    boundary_chars = set(" ,();.")

    for row in rows:
        tds = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 6:
            continue
        conductor = strip_tags(tds[4]).strip()
        program = tds[5]
        works = expand_program(program)
        for ew in works:
            for cand in sorted_works:
                if ew.startswith(cand):
                    nxt = len(cand)
                    if nxt == len(ew) or ew[nxt] in boundary_chars:
                        counts[cand][conductor] = counts[cand].get(conductor, 0) + 1
                        break

    # --check: print counts vs ranking totals to verify
    if "--check" in sys.argv:
        for rank, work, total in ranking_rows:
            actual_total = sum(counts[work].values())
            mark = "OK" if actual_total == int(total) else f"MISMATCH (expected {total})"
            print(f"#{rank} {work}: total={actual_total} {mark}")
            for c, n in sorted(counts[work].items(), key=lambda x: -x[1]):
                print(f"   {c}: {n}")
        return

    if "--write" not in sys.argv:
        print("Pass --check to verify or --write to update Program_Ranking.html")
        return

    # Rewrite ranking page with new column
    new_ranking = ranking

    # 1. Update <thead> header — add new column at the end
    new_ranking = new_ranking.replace(
        '<thead><tr><th>#</th><th>Composer &amp; Work</th><th>Performances</th></tr></thead>',
        '<thead><tr><th>#</th><th>Composer &amp; Work</th><th>Performances</th><th>Performances by Conductor</th></tr></thead>',
    )

    # 2. Append a 4th <td> to each data row with the per-conductor breakdown
    # Load authoritative totals from the baseline ref (so we never overwrite them)
    proc = subprocess.run(
        ["git", "show", f"{BASELINE_REF}:{RANKING}"],
        capture_output=True, text=True, check=True,
    )
    baseline_totals = {}
    for m in re.finditer(
        r"<tr><td>\d+</td><td>([^<]+)</td><td>(\d+)</td></tr>", proc.stdout
    ):
        baseline_totals[m.group(1)] = int(m.group(2))

    def replace_row(m):
        rank, work = m.group(1), m.group(2)
        breakdown = dict(counts.get(work, {}))
        total = baseline_totals.get(work, sum(breakdown.values()))
        identified = sum(breakdown.values())
        if total > identified:
            breakdown["Unknown"] = total - identified
        lines = [
            f"{c}: {n}"
            for c, n in sorted(
                breakdown.items(),
                key=lambda x: (x[0] == "Unknown", -x[1], x[0]),
            )
        ]
        cell = "<br>".join(lines) if lines else "—"
        return (
            f"<tr><td>{rank}</td><td>{work}</td><td>{total}</td>"
            f"<td>{cell}</td></tr>"
        )

    # Matches the 3-column legacy form OR the 4-column form already written.
    new_ranking = re.sub(
        r"<tr><td>(\d+)</td><td>([^<]+)</td><td>\d+</td>(?:<td>[^<]*(?:<br>[^<]*)*</td>)?</tr>",
        replace_row,
        new_ranking,
    )

    with open(RANKING, "w", encoding="utf-8") as f:
        f.write(new_ranking)
    print("Wrote", RANKING)


if __name__ == "__main__":
    main()
