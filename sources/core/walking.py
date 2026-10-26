"""Walking minutes from a point to places.

1. Public OSRM demo server, foot profile. Its `foot` profile is actually the car profile
   (verified: ~7 m/s), so every answer is checked for a walking-like speed and rejected if not.
2. A second public OSRM instance that really serves a foot profile (routing.openstreetmap.de).
3. Fallback: straight-line distance x 1.3 at 5 km/h.
`method` records which one produced the numbers.
"""
from __future__ import annotations

from ..common import SourceResult, coord_key, get_json, haversine_m, run_source

DATASET = {
    "name": "OSRM foot routing (public servers), else straight-line estimate",
    "id": "osrm/table/foot",
    "url": "https://router.project-osrm.org/table/v1/foot/",
    "terms": "https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server (demo server: no heavy use)",
}
OSRM_SERVERS = [   # the instance that really serves a foot profile first; the demo server (car speeds) is only a last try
    ("osrm_fossgis_foot", "https://routing.openstreetmap.de/routed-foot/table/v1/foot/"),
    ("osrm_demo_foot", "https://router.project-osrm.org/table/v1/foot/"),
]
MAX_DESTINATIONS = 12
DETOUR = 1.3
WALK_KMH = 5.0
# A real pedestrian profile averages ~1.1-1.5 m/s; the car profile gives 5+ m/s.
MIN_MS, MAX_MS = 0.6, 2.5
# A route much longer than the straight line is a snapping artifact (e.g. the start point lands on a disconnected footpath), not a real
# detour: 78 m to a shop that "walks" 1,176 m. Real city detours are rarely over 3x.
MAX_DETOUR, MIN_EXTRA_M = 3.0, 250


def estimate(origin: tuple[float, float], dests: list[dict]) -> list[dict]:
    out = []
    for d in dests:
        straight = haversine_m(origin[0], origin[1], d["lat"], d["lon"])
        walk_m = straight * DETOUR
        out.append({**_ident(d), "straight_m": round(straight), "walk_m": round(walk_m),
                    "walk_min": round(walk_m / (WALK_KMH * 1000 / 60), 1)})
    return out


def _ident(d: dict) -> dict:
    return {k: d.get(k) for k in ("name", "category", "kind", "lat", "lon")}


def _osrm(url: str, origin: tuple[float, float], dests: list[dict]) -> list[dict]:
    coords = ";".join([f"{origin[1]},{origin[0]}"] + [f"{d['lon']},{d['lat']}" for d in dests])
    data = get_json(url + coords, {"sources": 0, "annotations": "duration,distance"}, timeout=6)
    if data.get("code") != "Ok":
        raise ValueError(f"OSRM code {data.get('code')}")
    secs, meters = data["durations"][0][1:], data["distances"][0][1:]
    speeds = [m / s for m, s in zip(meters, secs) if m and s and m > 150]
    if not speeds:
        raise ValueError("no usable routes to judge speed")
    avg = sum(speeds) / len(speeds)
    if not (MIN_MS <= avg <= MAX_MS):
        raise ValueError(f"not a walking profile (average {avg:.1f} m/s)")
    out = []
    for d, s, m in zip(dests, secs, meters):
        if s is None or m is None:
            raise ValueError("OSRM returned no route for a destination")
        straight = haversine_m(origin[0], origin[1], d["lat"], d["lon"])
        if m > MAX_DETOUR * straight and m - straight > MIN_EXTRA_M:
            out.append({**estimate(origin, [d])[0], "estimated": "route was implausibly long for the distance"})
            continue
        out.append({**_ident(d), "straight_m": round(straight), "walk_m": round(m), "walk_min": round(s / 60, 1)})
    return out


def _live(origin: tuple[float, float], dests: list[dict]) -> dict:
    dests = dests[:MAX_DESTINATIONS]
    attempts = []
    for method, url in OSRM_SERVERS:
        try:
            results = _osrm(url, origin, dests)
            return {"method": method, "attempts": attempts, "origin": list(origin), "results": results}
        except Exception as exc:
            attempts.append({"method": method, "accepted": False, "reason": f"{type(exc).__name__}: {exc}"})
    return {"method": "straight_line_x1.3_at_5kmh", "attempts": attempts, "origin": list(origin),
            "results": estimate(origin, dests)}


def walking_times(origin: tuple[float, float], dests: list[dict], *, save: bool = False) -> SourceResult:
    return run_source(
        "core", "walking", coord_key(*origin), lambda: _live(origin, dests), DATASET,
        count=lambda d: len(d["results"]),
        fields=lambda d: ["method"] + sorted({k for r in d["results"] for k in r}),
        save=save)
