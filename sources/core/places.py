"""Everything within an 800 m radius of a point, via the OpenStreetMap Overpass API.

Amenities: groceries/supermarkets, gyms, parks, bus stops, train/subway stations, pharmacies.
Noise sources: bars, pubs, nightclubs, fire stations, hospitals, rail lines.
The radius is straight-line (Overpass `around`); walking.py turns distances into walking minutes.
"""
from __future__ import annotations

import re
import json
import queue
import threading
import time

from ..common import CACHE_DIR, SourceResult, bbox, coord_key, haversine_m, http, run_source

DATASET = {
    "name": "OpenStreetMap via Overpass API (interpreter)",
    "id": "overpass/interpreter",
    "url": "https://overpass-api.de/api/interpreter",
    "terms": "https://wiki.openstreetmap.org/wiki/Overpass_API (fair use; ODbL data)",
}
SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",     # mirror (also tried at the same time as the main server)
    "https://overpass.openstreetmap.fr/api/interpreter",  # mirror (also tried at the same time as the main server)
]
RACE_TIMEOUT = 20      # overall limit for one lookup
RADIUS_M = 800
KEEP_PER_CATEGORY = 40

AMENITIES = ("grocery", "gym", "park", "bus_stop", "train_station", "pharmacy")
NOISE = ("bar", "pub", "nightclub", "fire_station", "hospital", "rail_line")


def build_query(lat: float, lon: float, radius: int = RADIUS_M) -> str:
    """One small query: bus stops are plain nodes (no area search), and rail geometry is clipped to the search box
    so a long track does not drag its whole length into the answer."""
    a = f"(around:{radius},{lat},{lon})"
    south, north, west, east = bbox(lat, lon, radius)
    return f"""[out:json][timeout:20];
(
  nwr{a}["shop"~"^(supermarket|grocery|greengrocer|convenience)$"];
  nwr{a}["leisure"~"^(fitness_centre|park)$"];
  nwr{a}["amenity"~"^(gym|pharmacy|bar|pub|nightclub|fire_station|hospital)$"];
  node{a}["highway"="bus_stop"];
  nwr{a}["amenity"="bus_station"];
  nwr{a}["railway"~"^(station|halt|subway_entrance)$"];
  nwr{a}["public_transport"="station"];
);
out center tags qt;
way{a}["railway"~"^(rail|light_rail)$"]["tunnel"!="yes"];
out tags geom({south:.5f},{west:.5f},{north:.5f},{east:.5f}) qt;"""


NEWS = re.compile(r"\bnews(agent|agents|stand|paper|papers)?\b", re.I)
COACH = re.compile(r"megabus|greyhound|flixbus|peter pan|coach|bus (station|terminal|stop)", re.I)


def _is_coach_stop(tags: dict) -> bool:
    """A long-distance bus or coach stop (Megabus, Greyhound) is mapped like a station but is a bus, not a train or subway."""
    rail = (tags.get("railway") in ("station", "halt", "subway_entrance") or "yes" in (tags.get("train"), tags.get("subway"), tags.get("light_rail"))
            or tags.get("station") in ("subway", "light_rail", "train"))
    return not rail and (tags.get("amenity") == "bus_station" or tags.get("bus") == "yes" or bool(COACH.search(tags.get("name") or "")))


def classify(tags: dict) -> tuple[str, str, str] | None:
    """(group, category, kind) for an OSM element, or None if we don't use it."""
    shop, leisure, amenity = tags.get("shop"), tags.get("leisure"), tags.get("amenity")
    if shop in ("newsagent", "kiosk") or (shop == "convenience" and NEWS.search(tags.get("name") or "")):
        return None                                      # a newsagent sells papers and snacks: not a place to buy groceries
    if amenity == "bus_station" or (tags.get("public_transport") == "station" and _is_coach_stop(tags)):
        return "amenity", "bus_stop", "coach_stop"
    if shop in ("supermarket", "grocery", "greengrocer", "convenience"):
        return "amenity", "grocery", shop
    if leisure == "fitness_centre" or amenity == "gym":
        return "amenity", "gym", leisure or amenity
    if leisure == "park":
        return "amenity", "park", "park"
    if tags.get("highway") == "bus_stop":
        return "amenity", "bus_stop", "bus_stop"
    if tags.get("railway") in ("station", "halt", "subway_entrance") or tags.get("public_transport") == "station":
        kind = "subway_entrance" if tags.get("railway") == "subway_entrance" else (
            "subway_station" if tags.get("station") == "subway" else "station")
        return "amenity", "train_station", kind
    if amenity == "pharmacy":
        return "amenity", "pharmacy", "pharmacy"
    if amenity in ("bar", "pub", "nightclub", "fire_station", "hospital"):
        return "noise", amenity, amenity
    if tags.get("railway") in ("rail", "light_rail"):
        return "noise", "rail_line", tags["railway"]
    return None


def parse(elements: list[dict], lat: float, lon: float, radius: int = RADIUS_M) -> dict:
    places = []
    for el in elements:
        tags = el.get("tags", {})
        cls = classify(tags)
        if not cls:
            continue
        group, category, kind = cls
        if "geometry" in el:  # rail way: nearest vertex
            pts = [(g["lat"], g["lon"]) for g in el["geometry"] if g]     # clipped geometry has null points outside the box
            if not pts:
                continue
            plat, plon = min(pts, key=lambda p: haversine_m(lat, lon, *p))
        elif "lat" in el:
            plat, plon = el["lat"], el["lon"]
        elif "center" in el:
            plat, plon = el["center"]["lat"], el["center"]["lon"]
        else:
            continue
        dist = haversine_m(lat, lon, plat, plon)
        if dist > radius:
            continue
        places.append({
            "group": group, "category": category, "kind": kind,
            "name": tags.get("name") or tags.get("operator") or tags.get("brand"),
            "lat": round(plat, 6), "lon": round(plon, 6), "distance_m": round(dist),
            "osm": f"{el['type']}/{el['id']}",
        })
    places.sort(key=lambda p: p["distance_m"])
    # a rail line is one map object per track segment: report only the nearest segment
    first_rail = next((p for p in places if p["category"] == "rail_line"), None)
    places = [p for p in places if p["category"] != "rail_line"] + ([first_rail] if first_rail else [])
    places.sort(key=lambda p: p["distance_m"])
    # the same station/park is often mapped as several OSM objects: keep the nearest of each name
    kept, seen = [], set()
    for p in places:
        if p["name"] and p["category"] in ("train_station", "park", "hospital", "fire_station"):
            k = (p["category"], p["kind"], p["name"].lower())
            if k in seen:
                continue
            seen.add(k)
        kept.append(p)
    counts = {c: sum(1 for p in kept if p["category"] == c) for c in AMENITIES + NOISE}
    shown, per = [], {}
    for p in kept:
        per[p["category"]] = per.get(p["category"], 0) + 1
        if per[p["category"]] <= KEEP_PER_CATEGORY:
            shown.append(p)
    return {"center": {"lat": lat, "lon": lon}, "radius_m": radius, "counts": counts, "results": shown}


LATENCY_FILE = CACHE_DIR / "overpass_latency.json"
FIRST_TIMEOUT = 8      # the fastest known server must answer within 8 s...
HEDGE_AFTER = 3.0      # ...and if it has not answered after 3 s the other servers are asked too
OTHER_TIMEOUT = 15


def _latencies() -> dict[str, float]:
    try:
        return json.loads(LATENCY_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _remember(server: str, seconds: float) -> None:
    """Keep a running average of each server's speed so the next lookup asks the fastest one first."""
    lat = _latencies()
    lat[server] = round(0.6 * lat.get(server, seconds) + 0.4 * seconds, 2)
    try:
        LATENCY_FILE.parent.mkdir(parents=True, exist_ok=True)
        LATENCY_FILE.write_text(json.dumps(lat))
    except OSError:
        pass


def order_servers(latency: dict[str, float] | None = None) -> list[str]:
    lat = _latencies() if latency is None else latency
    return sorted(SERVERS, key=lambda s: lat.get(s, 6.0))      # unknown servers count as "medium"


def _live(lat: float, lon: float, radius: int) -> dict:
    """Ask the fastest known Overpass server first (8 s limit); after 3 s without an answer ask the others as well and
    take whichever answers first. On 2026-10-20 the main server took 40-70 s while a mirror answered in 2-4 s."""
    query = build_query(lat, lon, radius)

    def ask(server: str, timeout: float) -> dict:
        t0 = time.perf_counter()
        try:
            resp = http("POST", server, data={"data": query}, timeout=timeout, attempts=1)
            data = parse(resp.json()["elements"], lat, lon, radius)
        except Exception:
            _remember(server, 20.0)
            raise
        _remember(server, time.perf_counter() - t0)
        data["server"] = server
        return data

    ranked = order_servers()
    answers: "queue.Queue[tuple[str, dict | Exception]]" = queue.Queue()

    def worker(server: str, timeout: float) -> None:
        try:
            answers.put((server, ask(server, timeout)))
        except Exception as exc:
            answers.put((server, exc))

    def launch(server: str, timeout: float) -> None:
        # daemon threads: a slow server we no longer need must never keep this lookup (or the program) waiting
        threading.Thread(target=worker, args=(server, timeout), daemon=True).start()

    launch(ranked[0], FIRST_TIMEOUT)
    outstanding, errors, hedged = 1, [], False
    deadline = time.monotonic() + RACE_TIMEOUT
    while outstanding and time.monotonic() < deadline:
        try:
            server, result = answers.get(timeout=max(0.05, (HEDGE_AFTER if not hedged else deadline - time.monotonic())))
        except queue.Empty:
            result = None
        if result is not None:
            outstanding -= 1
            if not isinstance(result, Exception):
                return result
            errors.append(f"{server}: {type(result).__name__}")
        if not hedged and (result is None or outstanding == 0):
            hedged = True
            for other in ranked[1:]:
                launch(other, OTHER_TIMEOUT)
                outstanding += 1
    raise RuntimeError("all Overpass servers failed (" + "; ".join(errors or ["timed out"]) + ")")


def find_places(lat: float, lon: float, radius: int = RADIUS_M, *, save: bool = False) -> SourceResult:
    return run_source(
        "core", "places", coord_key(lat, lon), lambda: _live(lat, lon, radius), DATASET,
        count=lambda d: len(d["results"]),
        fields=lambda d: sorted({k for p in d["results"] for k in p}),
        save=save)
