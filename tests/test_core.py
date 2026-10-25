import pytest

from sources.core import geocode, places, walking
from sources.common import coord_key
from tests.conftest import addr

NEW_HAVEN = addr("360 State")


def test_geocode_from_sample():
    res = geocode.geocode(NEW_HAVEN)
    assert res.ok and res.origin == "sample" and res.count == 1
    assert res.data["state_code"] == "CT" and 41.2 < res.data["lat"] < 41.4
    assert {"lat", "lon", "state", "county", "city"} <= set(res.fields)


def test_places_from_sample():
    g = geocode.geocode(NEW_HAVEN).data
    res = places.find_places(g["lat"], g["lon"])
    assert res.ok and res.origin == "sample" and res.count > 0
    cats = {p["category"] for p in res.data["results"]}
    assert "grocery" in cats and "bus_stop" in cats
    assert all(p["distance_m"] <= 800 for p in res.data["results"])
    assert res.data["results"] == sorted(res.data["results"], key=lambda p: p["distance_m"])


def test_places_parse_classifies_and_filters():
    elements = [
        {"type": "node", "id": 1, "lat": 41.3055, "lon": -72.9232, "tags": {"shop": "supermarket", "name": "Mart"}},
        {"type": "node", "id": 2, "lat": 41.3056, "lon": -72.9232, "tags": {"amenity": "bar", "name": "Pub One"}},
        {"type": "node", "id": 3, "lat": 41.50, "lon": -72.9232, "tags": {"amenity": "pharmacy"}},   # too far
        {"type": "node", "id": 4, "lat": 41.3055, "lon": -72.9232, "tags": {"amenity": "bench"}},    # unused tag
        {"type": "way", "id": 5, "tags": {"railway": "rail"},
         "geometry": [{"lat": 41.3070, "lon": -72.9232}, {"lat": 41.3100, "lon": -72.9232}]},
        {"type": "way", "id": 6, "tags": {"railway": "rail"}, "geometry": [{"lat": 41.3080, "lon": -72.9232}]},
    ]
    data = places.parse(elements, 41.3054, -72.9232)
    cats = [p["category"] for p in data["results"]]
    assert cats.count("grocery") == 1 and cats.count("bar") == 1 and "pharmacy" not in cats
    assert cats.count("rail_line") == 1                      # only the nearest rail segment is kept
    assert data["counts"]["rail_line"] == 1


def test_walking_from_sample_records_method():
    g = geocode.geocode(NEW_HAVEN).data
    pl = places.find_places(g["lat"], g["lon"]).data["results"]
    dest = [p for p in pl if p["group"] == "amenity"][:2]
    res = walking.walking_times((g["lat"], g["lon"]), dest)
    assert res.ok and res.origin == "sample"
    assert res.data["method"] in {"osrm_demo_foot", "osrm_fossgis_foot", "straight_line_x1.3_at_5kmh"}
    assert all(r["walk_min"] >= 0 for r in res.data["results"])


def test_walking_straight_line_fallback_math():
    # 1 km due north of the origin: straight 1000 m x 1.3 = 1300 m at 5 km/h = 15.6 min
    origin = (41.0, -72.0)
    dest = {"name": "x", "category": "park", "kind": "park", "lat": 41.0 + 1000 / 111_320, "lon": -72.0}
    out = walking.estimate(origin, [dest])[0]
    assert abs(out["straight_m"] - 1000) <= 2 and abs(out["walk_min"] - 15.6) < 0.2


def test_walking_rejects_car_speed_osrm(monkeypatch):
    """The OSRM demo server's 'foot' profile answers at car speed: it must be rejected."""
    monkeypatch.setattr(walking, "get_json", lambda *a, **k: {
        "code": "Ok", "durations": [[0, 100, 100]], "distances": [[0, 1000, 1200]]})   # 10-12 m/s
    with pytest.raises(ValueError, match="not a walking profile"):
        walking._osrm("http://x/", (41.0, -72.0), [{"lat": 41.01, "lon": -72.0}, {"lat": 41.02, "lon": -72.0}])


def test_walking_accepts_real_walking_speed(monkeypatch):
    monkeypatch.setattr(walking, "get_json", lambda *a, **k: {
        "code": "Ok", "durations": [[0, 800]], "distances": [[0, 1000]]})                # 1.25 m/s
    out = walking._osrm("http://x/", (41.0, -72.0), [{"lat": 41.009, "lon": -72.0, "name": "a"}])
    assert out[0]["walk_min"] == 13.3 and out[0]["walk_m"] == 1000


def test_coord_key_is_stable():
    assert coord_key(41.30544, -72.92321) == "41.3054_-72.9232"
