"""New Haven 311-style issues from the public SeeClickFix API (v2): within 200 m, last 12 months."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..common import SourceResult, bbox, coord_key, get_json, haversine_m, run_source

DATASET = {
    "name": "SeeClickFix public API v2 - issues (New Haven, CT and other participating places)",
    "id": "seeclickfix/api/v2/issues",
    "url": "https://seeclickfix.com/api/v2/issues",
    "terms": "https://dev.seeclickfix.com/ (public read API, no key)",
}
RADIUS_M = 200
MONTHS = 12
MAX_PAGES = 6


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _live(lat: float, lon: float, radius: int, months: int) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=round(months * 30.4))
    min_lat, max_lat, min_lon, max_lon = bbox(lat, lon, radius)
    params = {"min_lat": min_lat, "max_lat": max_lat, "min_lng": min_lon, "max_lng": max_lon,
              "after": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"), "per_page": 100, "page": 1,
              "status": "open,acknowledged,closed,archived", "sort": "created_at", "sort_direction": "DESC"}
    issues, pages = [], 0
    while pages < MAX_PAGES:
        data = get_json(DATASET["url"], params, timeout=10)
        issues += data.get("issues", [])
        pages += 1
        if not data.get("metadata", {}).get("pagination", {}).get("next_page"):
            break
        params["page"] += 1
    rows = []
    for i in issues:
        d = haversine_m(lat, lon, i["lat"], i["lng"])
        if d > radius or _parse_ts(i["created_at"]) < cutoff:
            continue
        rows.append({"request_type": (i.get("request_type") or {}).get("title") or "Unspecified",
                     "status": i.get("status"), "created_at": i["created_at"], "distance_m": round(d),
                     "address": i.get("address"), "summary": (i.get("summary") or "")[:120],
                     "url": i.get("html_url")})
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r["request_type"], {"request_type": r["request_type"], "count": 0, "open": 0})
        g["count"] += 1
        g["open"] += r["status"] in ("Open", "Acknowledged")
    results = sorted(groups.values(), key=lambda g: -g["count"])
    return {"center": {"lat": lat, "lon": lon}, "radius_m": radius, "months": months,
            "since": cutoff.date().isoformat(), "total_issues": len(rows), "pages_fetched": pages,
            "results": results, "recent": rows[:5]}


def fetch_complaints(lat: float, lon: float, radius: int = RADIUS_M, months: int = MONTHS, *,
                     save: bool = False) -> SourceResult:
    return run_source(
        "ct", "complaints", coord_key(lat, lon), lambda: _live(lat, lon, radius, months), DATASET,
        count=lambda d: d["total_issues"],
        fields=lambda d: ["request_type", "count", "open"] + sorted({k for r in d["recent"] for k in r}),
        save=save)
