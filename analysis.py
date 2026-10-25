"""Pure functions: walking tables, noise tables and the transparent scores. No Streamlit, no network."""
from __future__ import annotations

from dataclasses import dataclass

from sources.core.walking import estimate

AMENITY_ROWS = [("grocery", "Grocery"), ("gym", "Gym"), ("park", "Park"),
                ("bus_stop", "Bus stop"), ("train_station", "Train / subway")]
NOISE_ROWS = [("nightclub", "Nightclubs", 3.0), ("bar", "Bars", 1.5), ("pub", "Pubs", 1.0),
              ("fire_station", "Fire stations", 2.0), ("hospital", "Hospitals", 1.5), ("rail_line", "Rail lines", 3.0)]
QUIET_WEIGHT = {"low": 0.5, "medium": 1.0, "high": 2.0}
QUIET_SCALE = 8.0       # noise load at which the quiet score has fallen to 37 (100 * e^-1)
RADIUS_M = 800
CATEGORIES = ["Groceries", "Gym", "Transit", "Quiet"]


@dataclass(frozen=True)
class Prefs:
    max_grocery: int = 10   # walking minutes
    max_gym: int = 15
    max_transit: int = 8
    quiet: str = "medium"   # how much night-time quiet matters: low / medium / high

    def limit(self, category: str) -> int | None:
        return {"grocery": self.max_grocery, "gym": self.max_gym,
                "bus_stop": self.max_transit, "train_station": self.max_transit}.get(category)


def _label(p: dict | None) -> str:
    if not p:
        return ""
    return p.get("name") or p.get("kind", "").replace("_", " ") or p.get("category", "")


def walk_table(places_data: dict, walking_data: dict | None, prefs: Prefs) -> list[dict]:
    """Walking minutes to the nearest place of each amenity type, and whether it meets the limit.

    Uses routed minutes when walking.py has them; otherwise straight-line x 1.3 at 5 km/h.
    """
    places = places_data.get("results", [])
    routed = (walking_data or {}).get("results", [])
    method = (walking_data or {}).get("method", "straight_line_x1.3_at_5kmh")
    rows = []
    for cat, label in AMENITY_ROWS:
        cands = [r for r in routed if r.get("category") == cat]
        used = method
        if not cands:
            near = [p for p in places if p["category"] == cat][:1]
            cands = estimate((places_data["center"]["lat"], places_data["center"]["lon"]), near)
            used = "straight_line_x1.3_at_5kmh"
        best = min(cands, key=lambda r: r["walk_min"]) if cands else None
        limit = prefs.limit(cat)
        rows.append({
            "category": cat, "label": label,
            "nearest": _label(best) if best else None,
            "walk_min": best["walk_min"] if best else None,
            "walk_m": best["walk_m"] if best else None,
            "method": used if best else None,
            "limit": limit,
            "meets": None if limit is None or best is None else best["walk_min"] <= limit,
            "count_800m": places_data.get("counts", {}).get(cat, 0),
        })
    return rows


def noise_table(places_data: dict) -> list[dict]:
    rows = []
    for cat, label, _w in NOISE_ROWS:
        items = [p for p in places_data.get("results", []) if p["category"] == cat]
        # counts[cat] is the real total; results is capped per category
        rows.append({"category": cat, "label": label, "count": places_data.get("counts", {}).get(cat, len(items)),
                     "nearest": _label(items[0]) if items else None,
                     "nearest_m": items[0]["distance_m"] if items else None})
    return rows


def noise_load(places_data: dict) -> float:
    """Sum over noise sources of weight x (1 - distance/800 m). Rail counts once (nearest segment)."""
    weights = {c: w for c, _l, w in NOISE_ROWS}
    return round(sum(weights[p["category"]] * max(0.0, 1 - p["distance_m"] / RADIUS_M)
                     for p in places_data.get("results", []) if p["category"] in weights), 2)


def score_walk(walk_min: float | None, limit: float) -> float:
    """100 at 0 minutes, 50 exactly at your limit, 0 at twice your limit; nothing within 800 m = 0."""
    if walk_min is None:
        return 0.0
    return round(max(0.0, 100 * (1 - walk_min / (2 * limit))), 1)


def score_quiet(load: float) -> float:
    import math
    return round(100 * math.exp(-load / QUIET_SCALE), 1)


def score_address(places_data: dict | None, walking_data: dict | None, prefs: Prefs) -> dict | None:
    """Scores 0-100 for Groceries, Gym, Transit, Quiet and a weighted Overall. None if no place data."""
    if not places_data:
        return None
    walks = {r["category"]: r for r in walk_table(places_data, walking_data, prefs)}

    def mins(*cats):
        vals = [walks[c]["walk_min"] for c in cats if walks[c]["walk_min"] is not None]
        return min(vals) if vals else None

    s = {"Groceries": score_walk(mins("grocery"), prefs.max_grocery),
         "Gym": score_walk(mins("gym"), prefs.max_gym),
         "Transit": score_walk(mins("bus_stop", "train_station"), prefs.max_transit),
         "Quiet": score_quiet(noise_load(places_data))}
    w = {"Groceries": 1.0, "Gym": 1.0, "Transit": 1.0, "Quiet": QUIET_WEIGHT[prefs.quiet]}
    s["Overall"] = round(sum(s[c] * w[c] for c in CATEGORIES) / sum(w.values()), 1)
    return s


def winners(scores: dict[str, dict | None]) -> dict[str, str]:
    """Which address wins each category (highest score). Ties are reported as 'tie: A, B'."""
    out = {}
    live = {a: s for a, s in scores.items() if s}
    for cat in CATEGORIES + ["Overall"]:
        if len(live) < 2:
            out[cat] = "—"
            continue
        best = max(s[cat] for s in live.values())
        top = [a for a, s in live.items() if s[cat] == best]
        out[cat] = top[0] if len(top) == 1 else "tie: " + ", ".join(top)
    return out
