"""Geocode the concert halls in classical_concert_halls_BW_Bayern_Hessen.csv
using OpenStreetMap's Nominatim API. Outputs data/venues.json with lat/lng
plus a stable id and all CSV columns.

Nominatim is free but rate-limited to 1 request/sec — we add a delay between
calls and use a descriptive User-Agent so it doesn't 403 us. Cached results
are written incrementally so reruns don't re-geocode.
"""
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
CSV = ROOT / "classical_concert_halls_BW_Bayern_Hessen.csv"
OUT = ROOT / "data" / "venues.json"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "shintachibana-classical-concerts/0.1 (+https://github.com/shintachibana/music)"


def make_id(city: str, venue: str) -> str:
    """Stable slug like `stuttgart_liederhalle-beethoven-saal`."""
    base = f"{city}_{venue}".lower()
    base = re.sub(r"[äöü]", lambda m: {"ä": "ae", "ö": "oe", "ü": "ue"}[m.group()], base)
    base = re.sub(r"[ß]", "ss", base)
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base


def geocode(query: str):
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": "1",
        "countrycodes": "de",
    })
    req = urllib.request.Request(f"{NOMINATIM}?{params}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if OUT.exists():
        for v in json.loads(OUT.read_text(encoding="utf-8")):
            existing[v["id"]] = v

    venues = []
    with open(CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = make_id(row["City"], row["Venue"])
            if vid in existing and "lat" in existing[vid]:
                venues.append(existing[vid])
                print(f"  cached: {vid}")
                continue

            # Try venue + city first, then fall back to city alone
            for query in (f"{row['Venue']} {row['City']}, Germany", f"{row['City']}, Germany"):
                try:
                    print(f"  geocoding: {query!r}")
                    coords = geocode(query)
                    time.sleep(1.1)
                    if coords:
                        break
                except Exception as e:
                    print(f"    error: {e}")
                    coords = None
                    time.sleep(2)
            entry = {
                "id": vid,
                "name": row["Venue"],
                "bundesland": row["Bundesland"],
                "city": row["City"],
                "venue_type": row["Venue_Type"],
                "capacity": int(row["Capacity"]) if row["Capacity"].isdigit() else None,
                "resident_orchestra": row["Resident_Orchestra"],
                "website": row["Website"],
            }
            if coords:
                entry["lat"], entry["lng"] = coords
            venues.append(entry)
            # Save incrementally so we don't lose progress
            OUT.write_text(json.dumps(venues, ensure_ascii=False, indent=2), encoding="utf-8")

    OUT.write_text(json.dumps(venues, ensure_ascii=False, indent=2), encoding="utf-8")
    geocoded = sum(1 for v in venues if "lat" in v)
    print(f"\nDone — {geocoded}/{len(venues)} venues geocoded → {OUT}")


if __name__ == "__main__":
    main()
