"""NYC address -> BBL (borough-block-lot), BIN and lat/lon with NYC Planning Labs' GeoSearch."""
from __future__ import annotations

from ..common import SourceResult, get_json, run_source, slug

DATASET = {
    "name": "NYC Planning Labs GeoSearch v2 (Pelias, NYC PAD addresses)",
    "id": "geosearch.planninglabs.nyc/v2/search",
    "url": "https://geosearch.planninglabs.nyc/v2/search",
    "terms": "https://geosearch.planninglabs.nyc/docs/ (free, no key)",
}


def _live(address: str) -> dict:
    data = get_json(DATASET["url"], {"text": address, "size": 1}, timeout=20)
    feats = data.get("features") or []
    if not feats:
        raise ValueError("GeoSearch returned no match")
    f = feats[0]
    p = f["properties"]
    pad = (p.get("addendum") or {}).get("pad") or {}
    if not pad.get("bbl"):
        raise ValueError("GeoSearch matched a place but returned no BBL")
    lon, lat = f["geometry"]["coordinates"]
    return {"query": address, "label": p.get("label"), "bbl": pad["bbl"], "bin": pad.get("bin"),
            "lat": lat, "lon": lon, "borough": p.get("borough"), "housenumber": p.get("housenumber"),
            "street": p.get("street"), "zip": p.get("postalcode"), "confidence": p.get("confidence"),
            "match_type": p.get("match_type"), "accuracy": p.get("accuracy")}


def lookup(address: str, *, save: bool = False) -> SourceResult:
    return run_source("nyc", "geo", slug(address), lambda: _live(address), DATASET,
                      count=lambda d: 1 if d else 0, fields=lambda d: sorted(d), save=save)
