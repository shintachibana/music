"""Scrape upcoming concerts from each ensemble's website (Ensembles.csv).

For each ensemble:
  1. Fetch its homepage.
  2. Ask Claude to extract upcoming concerts in the June–August window.
  3. Follow up to 2 calendar / spielplan pages if homepage doesn't list them.

For each concert returned by the model we also try to identify the venue
string. After all ensembles are scraped, a separate pass matches venue
strings to the 29 known venues (data/venues.json) by simple substring
fuzzy match and assigns venue_id where possible. Concerts at unknown
venues are kept in the data but skipped from the map (table view shows
them with the raw venue string).

Env: ANTHROPIC_API_KEY must be set.
"""
from __future__ import annotations
import csv
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("Install: pip install anthropic", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).parent.parent
ENSEMBLES_CSV = ROOT / "Ensembles.csv"
VENUES_JSON = ROOT / "data" / "venues.json"
CONCERTS_JSON = ROOT / "data" / "concerts.json"

MODEL = "claude-sonnet-4-6"
MAX_HTML_CHARS = 40_000
MAX_FOLLOWUPS_PER_ENS = 2
INTER_CALL_SLEEP = 2.0
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TODAY = date.today()
SEASON_START = date(TODAY.year, 6, 1)
SEASON_END = date(TODAY.year, 8, 31)

SYSTEM = f"""You are a classical-music concert-listing extractor for a touring ensemble.

You will be given the HTML of an ENSEMBLE'S website (homepage or calendar).
Extract upcoming CLASSICAL MUSIC concerts performed by this ensemble between
{SEASON_START.isoformat()} and {SEASON_END.isoformat()}.

Include: symphonic, chamber, choral, opera-in-concert, recital, baroque, etc.
EXCLUDE: musicals, pop/rock/jazz, ballet, education events.

For each concert, extract:
  - date         (YYYY-MM-DD, required)
  - time         (HH:MM 24-hour, optional)
  - title        (event title, optional)
  - venue        (string, e.g. "Liederhalle Stuttgart", "Konzerthaus Freiburg") — REQUIRED if at a fixed venue
  - city         (string, e.g. "Stuttgart")
  - performers   (orchestras, choirs, soloists, conductor — be specific)
  - program      (array of {{composer, work}} pairs)
  - url          (event detail page URL if visible)

If the page is a homepage that doesn't list concerts directly, RETURN AN EMPTY
"concerts" array AND suggest up to 3 follow-up URLs likely to contain concert
listings (kalender, spielplan, konzerte, veranstaltungen, programm, season).

Output ONLY this JSON, no commentary, no markdown:
{{
  "concerts": [
    {{"date": "...", "time": "...", "title": "...", "venue": "...", "city": "...",
      "performers": [...], "program": [{{"composer": "...", "work": "..."}}], "url": "..."}}
  ],
  "followup_urls": ["https://...", "..."]
}}

Omit missing fields. Return [] for concerts and [] for followup_urls if nothing useful."""


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "de,en;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def trim_html(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS] + "\n<!-- truncated -->\n"
    return html


def call_api(client: Anthropic, html: str, ensemble: dict, source_url: str) -> dict:
    user = (
        f"Ensemble: {ensemble['Ensemble']} ({ensemble['City']}, {ensemble['Bundesland']})\n"
        f"Source URL: {source_url}\n"
        f"Today: {TODAY.isoformat()}, Window: {SEASON_START} to {SEASON_END}\n\n"
        f"HTML:\n{html}"
    )
    for attempt in range(5):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=4096,
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                timeout=120.0,
            )
            break
        except Exception as e:
            msg = str(e)
            if ("rate_limit" in msg.lower() or "429" in msg) and attempt < 4:
                wait = 30 if attempt == 0 else 60
                print(f"  rate-limit, sleeping {wait}s…")
                time.sleep(wait)
                continue
            if attempt < 4 and ("connection" in msg.lower() or "timeout" in msg.lower()):
                time.sleep(5)
                continue
            raise
    text = resp.content[0].text.strip() if resp.content else ""
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
        if text.startswith("json"):
            text = text[4:].lstrip()
    if not text.startswith("{"):
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            text = text[s : e + 1]
    if not text:
        return {}
    return json.loads(text)


def normalize_concert(c: dict, ensemble_name: str, source_url: str) -> dict | None:
    if not c.get("date") or not re.match(r"^\d{4}-\d{2}-\d{2}$", c["date"]):
        return None
    # Filter to summer window
    if not (SEASON_START.isoformat() <= c["date"] <= SEASON_END.isoformat()):
        return None
    out = {"date": c["date"], "source_url": source_url}
    for k in ("time", "title", "url", "venue", "city"):
        if c.get(k):
            out[k] = c[k]
    # Always include the scraping ensemble as a performer
    performers = c.get("performers") or []
    if ensemble_name not in performers:
        performers = [ensemble_name] + performers
    out["performers"] = [p for p in performers if p]
    if c.get("program"):
        out["program"] = [
            {"composer": p.get("composer", ""), "work": p.get("work", "")}
            for p in c["program"]
            if p.get("composer") or p.get("work")
        ]
    return out


def match_venue(venue_str: str, city_str: str, venues: list[dict]) -> str | None:
    if not venue_str:
        return None
    vs = venue_str.lower()
    cs = (city_str or "").lower()
    best = None
    best_len = 0
    for v in venues:
        vname = v["name"].lower()
        # Take the shorter form (strip parenthetical)
        vshort = re.sub(r"\s*\(.*\)", "", vname).strip()
        keywords = [vshort] + [w for w in vshort.split() if len(w) >= 5]
        for kw in keywords:
            if kw and kw in vs and len(kw) > best_len:
                if cs and v["city"].lower() not in cs and cs not in v["city"].lower():
                    continue
                best = v["id"]
                best_len = len(kw)
    return best


def load_progress() -> tuple[dict, list[dict]]:
    if not CONCERTS_JSON.exists():
        return {}, []
    prev = json.loads(CONCERTS_JSON.read_text(encoding="utf-8"))
    state = prev.get("_ensemble_state", {})
    return state, list(prev.get("concerts", []))


def save_progress(state: dict, concerts: list[dict], original_keys: dict) -> None:
    original_keys["_ensemble_state"] = state
    original_keys["concerts"] = concerts
    CONCERTS_JSON.write_text(json.dumps(original_keys, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        sys.exit(2)

    ensembles = list(csv.DictReader(open(ENSEMBLES_CSV, encoding="utf-8-sig")))
    venues = json.loads(VENUES_JSON.read_text(encoding="utf-8"))
    full = json.loads(CONCERTS_JSON.read_text(encoding="utf-8"))
    state = full.get("_ensemble_state", {})
    concerts = full.get("concerts", [])
    client = Anthropic()

    for i, ens in enumerate(ensembles, 1):
        ens_key = f"{ens['City']}-{ens['Ensemble']}".lower().replace(" ", "-")
        if state.get(ens_key, {}).get("status") == "done":
            print(f"[{i:>2}/{len(ensembles)}] {ens['Ensemble']} — cached")
            continue
        if not ens.get("Website"):
            state[ens_key] = {"status": "skipped"}
            continue
        print(f"[{i:>2}/{len(ensembles)}] {ens['Ensemble']} ({ens['City']})")
        urls_to_try = [ens["Website"]]
        seen = set()
        ens_concerts = []
        ens_state = {"status": "in_progress", "tried": []}
        followups = 0
        try:
            while urls_to_try and followups < MAX_FOLLOWUPS_PER_ENS + 1:
                url = urls_to_try.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                ens_state["tried"].append(url)
                try:
                    print(f"    fetch {url[:100]}")
                    html = fetch_html(url)
                except Exception as e:
                    print(f"    ! fetch failed: {e}")
                    continue
                try:
                    result = call_api(client, trim_html(html), ens, url)
                except Exception as e:
                    print(f"    ! API failed: {e}")
                    continue
                got = result.get("concerts", []) or []
                for c in got:
                    n = normalize_concert(c, ens["Ensemble"], url)
                    if n:
                        n["venue_id"] = match_venue(n.get("venue", ""), n.get("city", ""), venues)
                        n["ensemble"] = ens["Ensemble"]
                        ens_concerts.append(n)
                print(f"    found {len(got)} concerts (cumulative {len(ens_concerts)})")
                if followups < MAX_FOLLOWUPS_PER_ENS:
                    for u in (result.get("followup_urls") or [])[:3]:
                        if u.startswith("http") and u not in seen:
                            urls_to_try.append(u)
                followups += 1
                time.sleep(INTER_CALL_SLEEP)
            ens_state["status"] = "done"
            ens_state["concert_count"] = len(ens_concerts)
        except KeyboardInterrupt:
            ens_state["status"] = "interrupted"
            raise
        except Exception as e:
            ens_state["status"] = "error"
            ens_state["error"] = str(e)
        # Replace any previously-scraped concerts for this ensemble
        concerts = [c for c in concerts if c.get("ensemble") != ens["Ensemble"]]
        concerts.extend(ens_concerts)
        state[ens_key] = ens_state
        full["_ensemble_state"] = state
        full["concerts"] = concerts
        CONCERTS_JSON.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")

    matched = sum(1 for c in concerts if c.get("ensemble") and c.get("venue_id"))
    unmatched = sum(1 for c in concerts if c.get("ensemble") and not c.get("venue_id"))
    print(f"\nDone. Ensemble concerts: matched to known venue {matched}, unmatched {unmatched}")


if __name__ == "__main__":
    main()
