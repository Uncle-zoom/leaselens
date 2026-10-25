"""Many street addresses -> lat/lon in ONE request, with the US Census Bureau's free batch geocoder.

Why: Nominatim allows 1 request per second, so placing 25 of an owner's parcels on the map took ~30 s. The Census
geocoder (no key) takes up to 10,000 addresses in one call. Addresses it cannot match fall back to Nominatim.
"""
from __future__ import annotations

import csv
import io

from ..common import SourceResult, http, run_source, slug

DATASET = {
    "name": "US Census Bureau Geocoder, batch addresses (Public_AR_Current)",
    "id": "census/geocoder/locations/addressbatch",
    "url": "https://geocoding.geo.census.gov/geocoder/locations/addressbatch",
    "terms": "https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html (free, no key)",
}


def build_csv(addresses: list[tuple[str, str, str]]) -> str:
    """addresses: (street, city, state). Row ids are the list positions."""
    buf = io.StringIO()
    w = csv.writer(buf)
    for i, (street, city, state) in enumerate(addresses):
        w.writerow([i, street, city, state, ""])
    return buf.getvalue()


def parse_response(text: str, n: int) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) >= 6 and row[2] == "Match" and row[5]:
            lon, lat = (float(x) for x in row[5].split(","))
            out[int(row[0])] = (lat, lon)
    return {k: v for k, v in out.items() if 0 <= k < n}


def _live(addresses: list[tuple[str, str, str]]) -> dict:
    resp = http("POST", DATASET["url"], data={"benchmark": "Public_AR_Current"},
                files={"addressFile": ("addresses.csv", build_csv(addresses), "text/csv")}, timeout=30, attempts=1)
    found = parse_response(resp.text, len(addresses))
    return {"matched": {str(k): list(v) for k, v in found.items()}, "total": len(addresses)}


def geocode_batch(addresses: list[tuple[str, str, str]]) -> SourceResult:
    key = "|".join(slug(" ".join(a)) for a in addresses)[:200]
    return run_source("core", "census_batch", key, lambda: _live(addresses), DATASET,
                      count=lambda d: len(d["matched"]), fields=lambda d: ["matched", "total"])
