"""NYC 311 requests within 200 m in the last 12 months, grouped by complaint type."""
from __future__ import annotations

from ..common import SourceResult, coord_key, run_source, socrata
from .common import NYC_DOMAIN, months_ago

DATASET_ID = "erm2-nwe9"
DATASET = {
    "name": "311 Service Requests from 2020 to Present (NYC Open Data)",
    "id": DATASET_ID,
    "url": f"https://{NYC_DOMAIN}/resource/{DATASET_ID}.json",
    "terms": "https://www.nyc.gov/html/data/terms.html (open data, no key)",
}
RADIUS_M = 200
MONTHS = 12
CLOSED = {"Closed", "Closed - Resolved"}


def _live(lat: float, lon: float, radius: int, months: int) -> dict:
    since = months_ago(months)
    where = f"within_circle(location, {lat}, {lon}, {radius}) AND created_date >= '{since}'"
    by_type = socrata(NYC_DOMAIN, DATASET_ID, {
        "$select": "complaint_type, status, count(*) as n", "$where": where,
        "$group": "complaint_type, status", "$limit": 5000})
    by_desc = socrata(NYC_DOMAIN, DATASET_ID, {
        "$select": "complaint_type, descriptor, count(*) as n", "$where": where,
        "$group": "complaint_type, descriptor", "$order": "n DESC", "$limit": 1000})
    groups: dict[str, dict] = {}
    for r in by_type:
        g = groups.setdefault(r["complaint_type"], {"complaint_type": r["complaint_type"], "count": 0, "open": 0})
        n = int(r["n"])
        g["count"] += n
        g["open"] += 0 if r.get("status") in CLOSED else n
    for r in by_desc:
        g = groups.get(r["complaint_type"])
        if g is not None and len(g.setdefault("top_descriptors", [])) < 3:
            g["top_descriptors"].append({"descriptor": r.get("descriptor"), "count": int(r["n"])})
    results = sorted(groups.values(), key=lambda g: -g["count"])
    total = sum(g["count"] for g in results)
    noise = sum(g["count"] for g in results if g["complaint_type"].lower().startswith("noise"))
    return {"center": {"lat": lat, "lon": lon}, "radius_m": radius, "months": months, "since": since[:10],
            "total_requests": total, "noise_requests": noise, "results": results}


def fetch_311(lat: float, lon: float, radius: int = RADIUS_M, months: int = MONTHS, *,
              save: bool = False) -> SourceResult:
    return run_source(
        "nyc", "complaints", coord_key(lat, lon), lambda: _live(lat, lon, radius, months), DATASET,
        count=lambda d: d["total_requests"],
        fields=lambda d: ["complaint_type", "count", "open", "top_descriptors"],
        save=save)
