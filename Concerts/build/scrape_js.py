"""Playwright-based scraper for the JS-heavy venues and ensembles that the
static-HTML pass (build/scrape.py, build/scrape_ensembles.py) couldn't read.

Strategy per target:
  1. Launch a headless Chromium tab (Playwright Python).
  2. Navigate to the homepage. Wait for network-idle.
  3. Grab the *rendered* DOM (inner HTML after JS has run).
  4. Pass it to Claude — same prompts as the static-HTML scripts —
     to extract concert listings (or follow-up URLs).
  5. For follow-ups, load each in a new tab and repeat.
  6. Save data/concerts.json incrementally so the script is resumable.

Targets are picked from the prior runs' state in data/concerts.json:
  - venues whose _state[id].concert_count is 0
  - ensembles whose _ensemble_state[key].concert_count is 0

Existing concert listings from the previous scrapes are kept untouched;
this script only adds new ones for the targets it processes.

Env: ANTHROPIC_API_KEY must be set.
"""
from __future__ import annotations
import csv
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("Install: pip install anthropic", file=sys.stderr)
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("Install: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).parent.parent
VENUES_JSON = ROOT / "data" / "venues.json"
ENSEMBLES_CSV = ROOT / "Ensembles.csv"
CONCERTS_JSON = ROOT / "data" / "concerts.json"

MODEL = "claude-sonnet-4-6"
MAX_HTML_CHARS = 60_000
MAX_FOLLOWUPS = 2
INTER_CALL_SLEEP = 2.0
PAGE_LOAD_TIMEOUT_MS = 30_000
NETWORK_IDLE_TIMEOUT_MS = 12_000

TODAY = date.today()
SEASON_START = date(TODAY.year, 6, 1)
SEASON_END = date(TODAY.year, 8, 31)


VENUE_SYSTEM = f"""You are a classical-music concert-listing extractor.

You will be given the rendered HTML of a German concert venue website (homepage or events page).
Extract upcoming CLASSICAL MUSIC concerts that take place at this venue between
TODAY ({TODAY.isoformat()}) and {SEASON_END.isoformat()}.

Include: symphonic, chamber, choral, opera in concert, recital, baroque, etc.
EXCLUDE: musicals, pop/rock/jazz, ballet, education events, exhibitions.

For each concert, extract:
  - date         (YYYY-MM-DD, required)
  - time         (HH:MM 24-hour, optional)
  - title        (event title, optional)
  - performers   (orchestras, choirs, soloists, conductor — be specific, separate items)
  - program      (array of {{composer, work}} pairs)
  - url          (event detail page URL if visible)

If the page is a homepage that doesn't list concerts directly, return an empty
"concerts" array AND suggest up to 3 follow-up URLs likely to contain concert
listings (programm / spielplan / konzerte / kalender / veranstaltungen / saison).

Output ONLY this JSON, no commentary, no markdown:
{{
  "concerts": [...],
  "followup_urls": ["https://...", "..."]
}}

Omit missing fields. Return [] for either if nothing useful is found."""


ENSEMBLE_SYSTEM = f"""You are a classical-music concert-listing extractor for a touring ensemble.

You will be given the rendered HTML of an ENSEMBLE'S website.
Extract upcoming CLASSICAL MUSIC concerts performed by this ensemble between
{SEASON_START.isoformat()} and {SEASON_END.isoformat()}.

Include classical only. Exclude musicals/pop/jazz/rock/ballet/education.

For each concert, extract:
  - date         (YYYY-MM-DD, required)
  - time         (HH:MM 24-hour, optional)
  - title        (event title, optional)
  - venue        (string, e.g. "Liederhalle Stuttgart") — REQUIRED if at a fixed venue
  - city         (string)
  - performers   (orchestras, choirs, soloists, conductor — be specific)
  - program      (array of {{composer, work}} pairs)
  - url          (event detail page URL if visible)

If the page is a homepage that doesn't list concerts directly, return an empty
"concerts" array AND suggest up to 3 follow-up URLs likely to contain concert
listings (kalender / spielplan / konzerte / veranstaltungen / programm / saison).

Output ONLY this JSON, no commentary, no markdown:
{{
  "concerts": [...],
  "followup_urls": ["https://...", "..."]
}}

Omit missing fields. Return [] for either if nothing useful is found."""


def render_page(page, url: str) -> str:
    """Open url in the given Playwright page, wait for JS, return inner HTML."""
    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
    # Best-effort: wait for network to settle so SPA content has time to render.
    try:
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
    except PWTimeout:
        pass
    # Give late-loading JS a moment
    page.wait_for_timeout(1500)
    return page.content()


def trim_html(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    # Collapse runs of whitespace to save tokens
    html = re.sub(r"[ \t]+", " ", html)
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS] + "\n<!-- truncated -->\n"
    return html


def call_api(client: Anthropic, system: str, user: str) -> dict:
    for attempt in range(5):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=4096,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                timeout=120.0,
            )
            break
        except Exception as e:
            msg = str(e)
            if ("rate_limit" in msg.lower() or "429" in msg) and attempt < 4:
                wait = 30 if attempt == 0 else 60
                print(f"   rate-limit, sleeping {wait}s…")
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


def normalize_venue_concert(c: dict, venue_id: str, source_url: str) -> dict | None:
    if not c.get("date") or not re.match(r"^\d{4}-\d{2}-\d{2}$", c["date"]):
        return None
    out = {"venue_id": venue_id, "date": c["date"], "source_url": source_url}
    for k in ("time", "title", "url"):
        if c.get(k):
            out[k] = c[k]
    if c.get("performers"):
        out["performers"] = [p for p in c["performers"] if p]
    if c.get("program"):
        out["program"] = [
            {"composer": p.get("composer", ""), "work": p.get("work", "")}
            for p in c["program"]
            if p.get("composer") or p.get("work")
        ]
    return out


def normalize_ensemble_concert(c: dict, ensemble_name: str, source_url: str, match_venue_fn) -> dict | None:
    if not c.get("date") or not re.match(r"^\d{4}-\d{2}-\d{2}$", c["date"]):
        return None
    if not (SEASON_START.isoformat() <= c["date"] <= SEASON_END.isoformat()):
        return None
    out = {"date": c["date"], "source_url": source_url, "ensemble": ensemble_name}
    for k in ("time", "title", "url", "venue", "city"):
        if c.get(k):
            out[k] = c[k]
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
    out["venue_id"] = match_venue_fn(out.get("venue", ""), out.get("city", ""))
    return out


def match_venue_factory(venues: list[dict]):
    def m(venue_str: str, city_str: str):
        if not venue_str:
            return None
        vs, cs = venue_str.lower(), (city_str or "").lower()
        best, best_len = None, 0
        for v in venues:
            vshort = re.sub(r"\s*\(.*\)", "", v["name"].lower()).strip()
            keywords = [vshort] + [w for w in vshort.split() if len(w) >= 5]
            for kw in keywords:
                if kw and kw in vs and len(kw) > best_len:
                    if cs and v["city"].lower() not in cs and cs not in v["city"].lower():
                        continue
                    best, best_len = v["id"], len(kw)
        return best
    return m


def is_non_pro(c: dict, academic_venue_ids: set) -> bool:
    """Same logic as scrape_ensembles + later filter pass."""
    PAT = re.compile(
        r"\b("
        r"hochschule\s+f(ü|ue)r\s+musik|"
        r"klasse\s+(prof|ulrich|j[üu]rgen|bernd|haruko|herr|frau|dr\.)|"
        r"nachwuchs[a-zäöüß]*|"
        r"junge[rnsm]?\s+(sinfonie|philharmon|streich|musiker|musikerinnen)|"
        r"jugendorchester|"
        r"orchesterakademie|"
        r"sch(ü|ue)lerkonzert|"
        r"studienkonzert|"
        r"musik\s+publik|"
        r"exotische\s+h(ö|oe)lzer|"
        r"theaterakademie"
        r")",
        re.IGNORECASE,
    )
    if c.get("venue_id") in academic_venue_ids:
        return True
    blob = " ".join([
        c.get("ensemble", ""),
        c.get("title", ""),
        c.get("venue", ""),
        " ".join(c.get("performers") or []),
    ])
    return bool(PAT.search(blob))


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        sys.exit(2)

    venues = json.loads(VENUES_JSON.read_text(encoding="utf-8"))
    ensembles = list(csv.DictReader(open(ENSEMBLES_CSV, encoding="utf-8-sig")))
    full = json.loads(CONCERTS_JSON.read_text(encoding="utf-8"))
    v_state = full.get("_state", {})
    e_state = full.get("_ensemble_state", {})
    js_state = full.get("_js_state", {})
    concerts = full.get("concerts", [])

    # Pick targets: venues + ensembles with 0 concerts so far, and not yet attempted by this script
    venue_targets = []
    for v in venues:
        st = v_state.get(v["id"], {})
        if st.get("concert_count", 0) > 0:
            continue
        if js_state.get(v["id"], {}).get("status") == "done":
            continue
        if not v.get("website"):
            continue
        venue_targets.append(v)

    ensemble_targets = []
    for ens in ensembles:
        key = f"{ens['City']}-{ens['Ensemble']}".lower().replace(" ", "-")
        st = e_state.get(key, {})
        if st.get("concert_count", 0) > 0:
            continue
        if js_state.get(key, {}).get("status") == "done":
            continue
        if not ens.get("Website"):
            continue
        ensemble_targets.append((key, ens))

    print(f"Targets — venues: {len(venue_targets)}, ensembles: {len(ensemble_targets)}")

    client = Anthropic()
    match_v = match_venue_factory(venues)
    academic_venue_ids = {"wuerzburg-hochschule-fuer-musik-wuerzburg-konzertsaal"}

    def save():
        full["_state"] = v_state
        full["_ensemble_state"] = e_state
        full["_js_state"] = js_state
        full["concerts"] = concerts
        CONCERTS_JSON.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")

    def process_target(page, label: str, key: str, start_url: str, system: str, normalize, ens_name=None):
        nonlocal concerts
        print(f"\n[{label}] {key}")
        urls_to_try = [start_url]
        seen = set()
        found = []
        state = {"status": "in_progress", "tried": []}
        followups = 0
        while urls_to_try and followups <= MAX_FOLLOWUPS:
            url = urls_to_try.pop(0)
            if url in seen:
                continue
            seen.add(url)
            state["tried"].append(url)
            try:
                print(f"    render {url[:95]}")
                html = render_page(page, url)
            except Exception as e:
                print(f"    ! render failed: {type(e).__name__}: {str(e)[:80]}")
                continue
            user_msg = f"Source URL: {url}\nToday: {TODAY.isoformat()}\n\nHTML:\n{trim_html(html)}"
            try:
                result = call_api(client, system, user_msg)
            except Exception as e:
                print(f"    ! API failed: {type(e).__name__}: {str(e)[:80]}")
                continue
            time.sleep(INTER_CALL_SLEEP)
            got = result.get("concerts", []) or []
            for c in got:
                n = normalize(c, url) if ens_name is None else normalize(c, ens_name, url)
                if n and not is_non_pro(n, academic_venue_ids):
                    found.append(n)
            print(f"    got {len(got)} concert candidates (kept {len(found)} cumulative)")
            if followups < MAX_FOLLOWUPS:
                for u in (result.get("followup_urls") or [])[:3]:
                    if u and u.startswith("http") and u not in seen:
                        urls_to_try.append(u)
            followups += 1
        state["status"] = "done"
        state["concert_count"] = len(found)
        # Replace previously-stored concerts for this target (if any)
        if ens_name:
            concerts = [c for c in concerts if c.get("ensemble") != ens_name]
        else:
            # venue scope: keep concerts at other venues, drop any prior at this venue
            concerts = [c for c in concerts if c.get("venue_id") != key or c.get("ensemble")]
        concerts.extend(found)
        return state

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="de-DE",
        )
        page = ctx.new_page()

        for i, v in enumerate(venue_targets, 1):
            label = f"V {i:>2}/{len(venue_targets)}"
            state = process_target(
                page, label, v["id"], v["website"], VENUE_SYSTEM,
                normalize=lambda c, url, vid=v["id"]: normalize_venue_concert(c, vid, url),
            )
            js_state[v["id"]] = state
            save()

        for i, (key, ens) in enumerate(ensemble_targets, 1):
            label = f"E {i:>2}/{len(ensemble_targets)}"
            ens_name = ens["Ensemble"]
            state = process_target(
                page, label, key, ens["Website"], ENSEMBLE_SYSTEM,
                normalize=lambda c, name, url: normalize_ensemble_concert(c, name, url, match_v),
                ens_name=ens_name,
            )
            js_state[key] = state
            save()

        ctx.close()
        browser.close()

    print(f"\nDone. Total concerts now: {len(concerts)}")


if __name__ == "__main__":
    main()
