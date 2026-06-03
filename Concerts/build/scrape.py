"""Scrape upcoming concerts from each venue's website using the Anthropic API.

Pipeline per venue:
  1. Fetch the venue's homepage HTML (with a realistic browser User-Agent).
  2. Ask Claude to extract upcoming concert events (next 3 months from today)
     as structured JSON. If the homepage doesn't show concerts directly, the
     model also returns a list of URLs to follow (calendar / season / events
     pages).
  3. For each suggested follow-up URL, fetch and extract.
  4. Save each venue's concerts incrementally to data/concerts.json so the
     script is resumable.

Env: ANTHROPIC_API_KEY must be set.

Realism note: many German concert hall websites are JavaScript-heavy. For
those, the raw HTML may not contain the event list. This script does its
best with what static HTML provides, then notes which venues need a
headless browser to scrape properly.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("Install the SDK: pip install anthropic", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).parent.parent
VENUES = ROOT / "data" / "venues.json"
OUT = ROOT / "data" / "concerts.json"

MODEL = "claude-sonnet-4-6"
MAX_FOLLOWUPS_PER_VENUE = 2  # cap iteration depth per venue
MAX_HTML_CHARS = 40_000  # truncate huge HTML pages (~10K tokens)
INTER_CALL_SLEEP = 2.0  # gentle pacing between calls to stay under 30K-tpm limit
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TODAY = date.today()
WINDOW_END = TODAY + timedelta(days=90)


SYSTEM_PROMPT = f"""You are a classical-music concert-listing extractor.

You will be given the HTML of a German concert venue website (homepage or events page).
Your job is to extract upcoming CLASSICAL MUSIC concerts that take place between
TODAY ({TODAY.isoformat()}) and {WINDOW_END.isoformat()} at that venue.

Include only classical concerts: symphonic, chamber music, choral, solo recitals,
opera in concert, Lieder recitals, baroque ensembles, etc.

EXCLUDE: musicals, pop/jazz/rock concerts, ballet, spoken-word events, conferences,
workshops, exhibitions, dance, family/kids non-music events.

For each concert, extract:
  - date         (YYYY-MM-DD, required)
  - time         (HH:MM 24-hour, optional)
  - title        (event title, e.g. "Sinfoniekonzert 5", optional)
  - performers   (array of strings: orchestras, choirs, soloists, conductor — be specific)
  - program      (array of {{composer, work}} pairs)
  - url          (link to the event detail page if visible)

If the page is a homepage that doesn't list concerts directly, RETURN AN EMPTY
"concerts" array AND suggest up to 3 follow-up URLs likely to contain concert
listings (calendar / programm / spielplan / veranstaltungen / season).

Output ONLY this JSON structure — no commentary, no markdown:
{{
  "concerts": [
    {{"date": "...", "time": "...", "title": "...", "performers": [...], "program": [{{"composer": "...", "work": "..."}}], "url": "..."}}
  ],
  "followup_urls": ["https://...", "..."]
}}

If a field is missing, OMIT it (don't include nulls or empty strings)."""


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "de,en;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        # Best-effort encoding detection
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def trim_html(html: str) -> str:
    # Cheap cleanup: remove <script>, <style>, comments, then truncate.
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS] + f"\n<!-- truncated at {MAX_HTML_CHARS} chars -->\n"
    return html


def call_api(client: Anthropic, html: str, venue_name: str, source_url: str) -> dict:
    user = (
        f"Venue: {venue_name}\n"
        f"Source URL: {source_url}\n"
        f"Today's date: {TODAY.isoformat()}\n\n"
        f"HTML:\n{html}"
    )
    for attempt in range(5):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                timeout=120.0,
            )
            break
        except Exception as e:
            # Retry on rate-limit (429) and transient connection errors
            msg = str(e)
            if ("rate_limit" in msg.lower() or "429" in msg) and attempt < 4:
                wait = 30 if attempt == 0 else 60  # rate limit window is per minute
                print(f"    rate-limit hit, sleeping {wait}s before retry…")
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
        # Strip CoT prose
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def normalize_concert(c: dict, venue_id: str, source_url: str) -> dict | None:
    if not c.get("date"):
        return None
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", c["date"]):
        return None
    out = {"venue_id": venue_id, "date": c["date"]}
    for k in ("time", "title", "url"):
        if c.get(k):
            out[k] = c[k]
    if c.get("performers"):
        out["performers"] = [p for p in c["performers"] if p]
    if c.get("program"):
        out["program"] = [p for p in c["program"] if p.get("composer") or p.get("work")]
    out["source_url"] = source_url
    return out


def load_progress() -> tuple[dict, list[dict]]:
    if not OUT.exists():
        return {}, []
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}, []
    state = prev.get("_state", {})
    return state, list(prev.get("concerts", []))


def save_progress(state: dict, concerts: list[dict]) -> None:
    OUT.write_text(
        json.dumps(
            {"_state": state, "scraped_at": TODAY.isoformat(), "concerts": concerts},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        sys.exit(2)

    venues = json.loads(VENUES.read_text(encoding="utf-8"))
    state, concerts = load_progress()
    client = Anthropic()

    for i, v in enumerate(venues, 1):
        if state.get(v["id"], {}).get("status") == "done":
            print(f"[{i:>2}/{len(venues)}] {v['id']} — cached")
            continue
        if not v.get("website"):
            state[v["id"]] = {"status": "skipped", "reason": "no website"}
            continue
        print(f"[{i:>2}/{len(venues)}] {v['id']}")
        urls_to_try = [v["website"]]
        seen_urls = set()
        venue_concerts = []
        followups = 0
        venue_state = {"status": "in_progress", "tried": []}
        try:
            while urls_to_try and followups < MAX_FOLLOWUPS_PER_VENUE + 1:
                url = urls_to_try.pop(0)
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                venue_state["tried"].append(url)
                try:
                    print(f"    fetch {url}")
                    html = fetch_html(url)
                except Exception as e:
                    print(f"    ! fetch failed: {e}")
                    continue
                try:
                    result = call_api(client, trim_html(html), v["name"], url)
                except Exception as e:
                    print(f"    ! API call failed: {e}")
                    continue
                time.sleep(INTER_CALL_SLEEP)
                got = result.get("concerts", []) or []
                for c in got:
                    n = normalize_concert(c, v["id"], url)
                    if n:
                        venue_concerts.append(n)
                print(f"    found {len(got)} concerts (cumulative for venue: {len(venue_concerts)})")
                if followups < MAX_FOLLOWUPS_PER_VENUE:
                    for u in (result.get("followup_urls") or [])[:3]:
                        if u.startswith("http") and u not in seen_urls:
                            urls_to_try.append(u)
                followups += 1
            venue_state["status"] = "done"
            venue_state["concert_count"] = len(venue_concerts)
        except KeyboardInterrupt:
            venue_state["status"] = "interrupted"
            raise
        except Exception as e:
            venue_state["status"] = "error"
            venue_state["error"] = str(e)
        # Replace any existing concerts for this venue with the fresh set
        concerts = [c for c in concerts if c["venue_id"] != v["id"]]
        concerts.extend(venue_concerts)
        state[v["id"]] = venue_state
        save_progress(state, concerts)
        time.sleep(0.5)  # gentle pacing

    print(f"\nDone. {len(concerts)} concerts across {sum(1 for s in state.values() if s.get('status') == 'done')} venues.")


if __name__ == "__main__":
    main()
