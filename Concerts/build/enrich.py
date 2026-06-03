"""Enrich existing concerts in data/concerts.json by fetching each concert's
detail page (the `url` field) and extracting the full program (composer + work
pairs) and any additional performer info.

Runs in place — overwrites data/concerts.json after each batch of updates so
the script is resumable. Only fetches a concert's detail page once; cached
results are stored under `_enriched: true` on each concert.

Env: ANTHROPIC_API_KEY must be set.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("Install the SDK: pip install anthropic", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).parent.parent
CONCERTS = ROOT / "data" / "concerts.json"

MODEL = "claude-sonnet-4-6"
MAX_HTML_CHARS = 40_000
INTER_CALL_SLEEP = 2.0
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SYSTEM = """You are reading the detail page of a single classical-music concert at a German venue.

Extract:
- title       (event title, e.g. "Sinfoniekonzert 5")
- time        (HH:MM 24-hour) if visible
- performers  (orchestras, choirs, soloists, conductor — be specific, separate items)
- program     (array of {composer, work} pairs covering EVERY work performed)

Composer should be the surname or "First Last" form (e.g. "Brahms", "Richard Strauss").
Work should be the concrete title (e.g. "Symphony No. 4 in E minor, Op. 98").

Output ONLY this JSON, no commentary, no markdown:
{
  "title": "...",
  "time": "HH:MM",
  "performers": ["..."],
  "program": [{"composer": "...", "work": "..."}]
}

Omit any field you cannot determine confidently. If nothing useful is on the page, return {}."""


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


def call_api(client: Anthropic, html: str, url: str) -> dict:
    for attempt in range(5):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": f"URL: {url}\n\nHTML:\n{html}"}],
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
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    if not text:
        return {}
    return json.loads(text)


def merge(concert: dict, fresh: dict) -> bool:
    """Update concert in place. Returns True if anything actually changed."""
    changed = False
    # Only fill in missing/empty fields; don't overwrite existing program if we
    # already had one (unless the new one has more entries).
    for k in ("title", "time"):
        if fresh.get(k) and not concert.get(k):
            concert[k] = fresh[k]
            changed = True
    if fresh.get("performers"):
        old = set((concert.get("performers") or []))
        merged = list(concert.get("performers") or [])
        for p in fresh["performers"]:
            if p and p not in old:
                merged.append(p)
                changed = True
        concert["performers"] = merged
    if fresh.get("program"):
        old_program = concert.get("program") or []
        if len(fresh["program"]) > len(old_program):
            concert["program"] = [
                {"composer": p.get("composer", ""), "work": p.get("work", "")}
                for p in fresh["program"]
                if p.get("composer") or p.get("work")
            ]
            changed = True
    return changed


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        sys.exit(2)

    data = json.loads(CONCERTS.read_text(encoding="utf-8"))
    concerts = data["concerts"]
    client = Anthropic()

    todo = [c for c in concerts if c.get("url") and not c.get("_enriched")]
    print(f"Total concerts: {len(concerts)}")
    print(f"To enrich: {len(todo)}")
    if not todo:
        return

    enriched = 0
    updated = 0
    for i, c in enumerate(todo, 1):
        url = c["url"]
        print(f"[{i:>2}/{len(todo)}] {c['date']} — {url[:90]}")
        try:
            html = fetch_html(url)
        except Exception as e:
            print(f"   ! fetch failed: {e}")
            c["_enriched"] = "fetch_error"
            continue
        try:
            result = call_api(client, trim_html(html), url)
        except Exception as e:
            print(f"   ! API failed: {e}")
            c["_enriched"] = "api_error"
            continue
        if merge(c, result):
            updated += 1
            print(f"   updated. now {len(c.get('program', []))} works, {len(c.get('performers', []))} performers")
        else:
            print(f"   no new info")
        c["_enriched"] = True
        enriched += 1
        # Save incrementally
        data["enriched_at"] = time.strftime("%Y-%m-%d")
        CONCERTS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(INTER_CALL_SLEEP)

    print(f"\nDone — enriched {enriched} concerts, {updated} got new info.")


if __name__ == "__main__":
    main()
