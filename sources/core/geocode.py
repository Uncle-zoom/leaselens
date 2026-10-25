"""Address -> lat/lon with OpenStreetMap Nominatim (max 1 request per second)."""
from __future__ import annotations

from ..common import SourceResult, get_json, run_source, slug

DATASET = {
    "name": "OpenStreetMap Nominatim search API",
    "id": "nominatim/search",
    "url": "https://nominatim.openstreetmap.org/search",
    "terms": "https://operations.osmfoundation.org/policies/nominatim/ (max 1 req/s, User-Agent required)",
}


def address_key(address: str) -> str:
    return slug(address)


def _live(address: str) -> dict:
    rows = get_json(DATASET["url"], {"q": address, "format": "jsonv2", "addressdetails": 1,
                                     "limit": 1, "countrycodes": "us"}, timeout=20)
    if not rows:
        raise ValueError("Nominatim returned no match")
    r = rows[0]
    a = r.get("address", {})
    iso = a.get("ISO3166-2-lvl4", "")
    return {
        "query": address,
        "lat": float(r["lat"]), "lon": float(r["lon"]),
        "display_name": r.get("display_name"),
        "house_number": a.get("house_number"), "road": a.get("road"),
        "city": a.get("city") or a.get("town") or a.get("village") or a.get("hamlet"),
        "county": a.get("county"), "state": a.get("state"),
        "state_code": iso.split("-")[-1] if iso.startswith("US-") else None,
        "postcode": a.get("postcode"),
        "osm_type": r.get("osm_type"), "osm_id": r.get("osm_id"),
        "place_class": r.get("category"), "place_type": r.get("type"),
        "importance": r.get("importance"),
        "address": a,
    }


def geocode(address: str, *, save: bool = False) -> SourceResult:
    return run_source(
        "core", "geocode", address_key(address), lambda: _live(address), DATASET,
        count=lambda d: 1 if d else 0,
        fields=lambda d: [k for k in d if k != "address"],
        save=save)
