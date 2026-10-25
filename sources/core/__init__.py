"""Nationwide market: geocoding, OpenStreetMap places, walking times. Always runs."""
from __future__ import annotations

from ..common import SourceResult
from . import geocode, places, walking


def run(geo: dict, address: str | None = None, *, save: bool = False) -> dict[str, SourceResult]:
    """Block report for a geocoded address: places within 800 m + walking minutes to the nearest ones."""
    lat, lon = geo["lat"], geo["lon"]
    out: dict[str, SourceResult] = {}
    out["places"] = places.find_places(lat, lon, save=save)
    if out["places"].ok:
        nearest, seen = [], {}
        for p in out["places"].data["results"]:
            if p["group"] == "amenity" and seen.get(p["category"], 0) < 2:
                seen[p["category"]] = seen.get(p["category"], 0) + 1
                nearest.append(p)
        out["walking"] = walking.walking_times((lat, lon), nearest, save=save)
    return out


class _Market:
    name = "core"
    label = "Nationwide (OpenStreetMap)"
    adapters = ("geocode", "places", "walking")

    @staticmethod
    def matches(geo: dict) -> bool:
        return True

    run = staticmethod(run)


MARKET = _Market()
