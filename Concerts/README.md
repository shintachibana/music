# Classical Concerts — BW · Bayern · Hessen

Static web app that visualizes upcoming professional classical-music concerts across **Baden-Württemberg, Bayern, and Hessen**. Concerts come from two pipelines: scraping the websites of 29 major concert halls and 35 ensembles, then enriching each listing from its individual event page.

**Live data:** 104 concerts, 85 with detailed programs, 268 works listed.

## Pages

- `app/index.html` — **Map view.** Pin-per-venue on an OpenStreetMap tile layer. Map starts empty until you pick a filter (month, date, city, performer, composer, work). When multiple concerts share one venue, the marker shows the count and a popup lists up to 10 of them (with a link to the table view for the rest). Venue name in the popup links to the official website.
- `app/table.html` — **Table view.** All concerts in one sortable, filterable table. Free-text search across composer / work / performer / venue / city. Title bar, filter row, and table header stay pinned while scrolling. Venue name links out to the official website.

## Reference docs

- `Concert Hall.md` — markdown table of the 29 source venues plus 39 additional venues discovered through ensemble scraping (grouped by Bundesland).
- `Ensembles.md` — markdown table of all 35 ensembles whose seasons we scraped, grouped by Bundesland.

## Data files

| File | Content | Notes |
|---|---|---|
| `classical_concert_halls_BW_Bayern_Hessen.csv` | 29 source venues | provided |
| `Ensembles.csv` | 35 ensembles | provided |
| `data/venues.json` | venues with geocoded lat/lng | via Nominatim |
| `data/concerts.json` | the 104 concert listings | shipped artifact |

## Run locally

```bash
python3 -m http.server 8800 --directory /path/to/Concerts
```

Then open <http://localhost:8800/app/index.html>.

## Rebuild pipeline

```bash
# 1. Geocode venues (no API key — uses OpenStreetMap Nominatim, 1 req/sec)
python3 build/geocode.py

# 2. Scrape concerts from each venue's homepage (needs ANTHROPIC_API_KEY).
#    Resumable, rate-limit aware. ~$3–8 cost for a full pass.
export ANTHROPIC_API_KEY="sk-ant-..."
python3 build/scrape.py

# 3. Scrape each ensemble's website for June–August concerts (needs key).
#    Tries to match each concert's venue string to one of the 29 known
#    venues; unmatched entries still appear in the table.
python3 build/scrape_ensembles.py

# 4. Enrich each concert from its individual event-detail page (needs key).
#    Skips concerts that already have program data, so subsequent runs
#    only process the holes.
python3 build/enrich.py
```

All build scripts write progress to `data/concerts.json` incrementally, so killing and restarting picks up where it left off.

## Results so far

| Source | Concerts found | Programs filled |
|---|---|---|
| Venue scrape (29 halls) | 35 | high (most have detail-page URLs) |
| Ensemble scrape (35 ensembles) | 87 | partial; many enriched in pass 2 |
| Auto-filtered (non-pro / out-of-region) | −18 | — |
| **Net committed** | **104** | **85 with programs, 268 works** |

Top contributors after dedup:

- Münchener Kammerorchester
- Württembergisches Kammerorchester Heilbronn
- Nürnberger Symphoniker
- Opern- und Museumsorchester Frankfurt
- Hofer Symphoniker
- SWR Symphonieorchester
- Festspielhaus Baden-Baden
- Alte Oper Frankfurt

## Non-pro filter

`build/scrape_ensembles.py` keeps youth and academic concerts out by name. The filter drops anything with these substrings in title / venue / performer / ensemble:

- `Hochschule für Musik`, `Theaterakademie`, `Orchesterakademie`
- `Klasse Prof.`, `Musik publik`, `Exotische Hölzer`
- `Nachwuchs*`, `Junge[rsn] Sinfonie/Philharmonie/Streich…`
- `Jugendorchester`, `Schülerkonzert`, `Studienkonzert`
- All events at `Würzburg Hochschule für Musik Konzertsaal` (entirely academic venue)

## Known limitations

- **Static HTML only.** Many German concert hall and orchestra sites are JavaScript-heavy. Roughly half the 29 venues and a third of the 35 ensembles yield nothing from raw HTML. A Playwright-based scraper is the obvious next step.
- **English translations of programs** aren't done — composer + work are stored as the original German.
- **Some URLs no longer resolve** (`mphil.de` via that path, `staatstheater.karlsruhe.de`, several Wiesbaden / Karlsruhe entries) so those venues contribute nothing.
- **Map only shows mapped venues** — concerts at unmapped venues (e.g. small Bavarian towns the ensembles tour to) appear in the table but not on the map.

## Tech stack

- Static HTML/CSS/JS, no build step
- [Leaflet 1.9](https://leafletjs.com/) + OpenStreetMap tiles (no API key)
- Python 3 build scripts using only the stdlib + `anthropic`
- Anthropic Claude API (Sonnet 4.6) for HTML → structured-concert extraction
- OpenStreetMap Nominatim for geocoding (no API key)
