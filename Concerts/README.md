# Classical Concerts — BW · Bayern · Hessen

Static web app that lists classical-music concerts at 29 major concert halls across Baden-Württemberg, Bayern, and Hessen, with a filterable map view and a sortable data table.

## Pages

- `app/index.html` — **Map view.** Pin-per-venue on an OpenStreetMap tile layer. The map starts empty; pick a filter (month, date, city, performer, composer, work) to populate it.
- `app/table.html` — **Table view.** All concerts in one sortable table with free-text search.

## Data files

- `classical_concert_halls_BW_Bayern_Hessen.csv` — source list of 29 venues (provided).
- `data/venues.json` — venues with geocoded lat/lng (via OpenStreetMap Nominatim).
- `data/concerts.json` — scraped concert listings.

## Run locally

```bash
python3 -m http.server 8800 --directory /path/to/Concerts
```

Then open <http://localhost:8800/app/index.html>.

## Rebuild pipeline

```bash
# 1. Geocode venues (no API key, uses OpenStreetMap Nominatim — 1 req/sec)
python3 build/geocode.py

# 2. Scrape concerts (needs ANTHROPIC_API_KEY — uses Claude Sonnet 4.6
#    to extract structured concert data from each venue's HTML).
export ANTHROPIC_API_KEY="sk-ant-..."
python3 build/scrape.py
```

## Known limitations

- Many German concert hall sites are JavaScript-heavy. Static HTML scraping captures concerts from ~7 of the 29 venues. A future v2 with a headless browser (Playwright) would unlock the other ~22.
- "Programs" (composer + work) are inconsistent across venues — some only list the headline event title.
- Some venue URLs in the CSV no longer resolve (`mphil.de`, `staatstheater.karlsruhe.de`, etc.).

## Tech stack

- Static HTML/CSS/JS
- [Leaflet 1.9](https://leafletjs.com/) + OpenStreetMap tiles (no API key needed)
- Python 3 build scripts
- Anthropic Claude API for scrape extraction
