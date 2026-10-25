"""Building name -> street address, for input that has no street number ("Ansonia Apartments").

One Nominatim call per name (US only, same 1 request/second limit and User-Agent as the address lookup), cached with the result, a
"not found" included, so the same name never costs a second call. The match is only ever a suggestion: the app shows it and continues
only after the person says yes. A match without a house number is treated as not found: we never guess a number.
"""
from __future__ import annotations

import re

from ..common import SourceResult, get_json, run_source, slug
from .geocode import DATASET as GEOCODE_DATASET

NOT_FOUND = "Couldn't find that building by name. Please enter the street address."
DATASET = {**GEOCODE_DATASET, "name": "OpenStreetMap Nominatim search API (building name)", "id": "nominatim/search?name"}


def looks_like_name(text: str) -> bool:
    """True when the first part of the input (before the first comma) has no number, so it cannot be a street address."""
    first = (text or "").split(",")[0]
    return bool(first.strip()) and not re.search(r"\d", first)


def _live(name: str) -> dict:
    rows = get_json(DATASET["url"], {"q": name, "format": "jsonv2", "addressdetails": 1, "limit": 1, "countrycodes": "us"}, timeout=20)
    if not rows:
        return {"query": name, "found": False}
    r = rows[0]
    a = r.get("address", {})
    iso = a.get("ISO3166-2-lvl4", "")
    house, road = (a.get("house_number") or "").split(";")[0].strip() or None, a.get("road")      # OSM may list "1111;1073": use the first
    city = a.get("city") or a.get("town") or a.get("village") or a.get("hamlet")
    state = iso.split("-")[-1] if iso.startswith("US-") else a.get("state")
    out = {"query": name, "found": bool(house and road and city), "name": r.get("name") or (r.get("display_name") or "").split(",")[0],
           "house_number": house, "road": road, "city": city, "state_code": state, "lat": float(r["lat"]), "lon": float(r["lon"])}
    if out["found"]:
        out["address"] = f"{house} {road}, {city}, {state}"
    return out


def find_building(name: str, *, save: bool = False) -> SourceResult:
    key = slug(name)
    return run_source("core", "name_search", key, lambda: _live(name), DATASET,
                      count=lambda d: 1 if d.get("found") else 0, fields=lambda d: sorted(d), save=save)


def check(name: str) -> dict:
    """{'ok': True, 'name', 'address'} to ask the person "Is this right?", or {'ok': False, 'message'}."""
    res = find_building(name)
    d = res.data if res.ok else None
    if not d or not d.get("found"):
        return {"ok": False, "typed": name, "message": NOT_FOUND}
    return {"ok": True, "typed": name, "name": d["name"], "address": d["address"]}
