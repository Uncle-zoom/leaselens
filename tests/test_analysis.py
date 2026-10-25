import pytest

import analysis
from analysis import Prefs

P = Prefs()


def fake_places(extra=()):
    base = [
        {"group": "amenity", "category": "grocery", "kind": "supermarket", "name": "Mart", "lat": 41.0 + 100 / 111320, "lon": -72.0, "distance_m": 100, "osm": "n/1"},
        {"group": "amenity", "category": "bus_stop", "kind": "bus_stop", "name": None, "lat": 41.0, "lon": -72.0, "distance_m": 50, "osm": "n/2"},
    ]
    return {"center": {"lat": 41.0, "lon": -72.0}, "radius_m": 800, "counts": {"grocery": 1, "bus_stop": 1},
            "results": base + list(extra)}


def test_score_walk_is_100_at_zero_50_at_limit_0_at_double():
    assert analysis.score_walk(0, 10) == 100 and analysis.score_walk(10, 10) == 50
    assert analysis.score_walk(20, 10) == 0 and analysis.score_walk(35, 10) == 0 and analysis.score_walk(None, 10) == 0


def test_closer_always_scores_higher():
    assert analysis.score_walk(4, 10) > analysis.score_walk(5, 10)


def test_walk_table_meets_limits_and_missing_categories():
    rows = {r["category"]: r for r in analysis.walk_table(fake_places(), None, P)}
    assert rows["grocery"]["meets"] is True and rows["grocery"]["walk_min"] == pytest.approx(1.6, abs=0.2)  # 100 m x1.3 at 5 km/h
    assert rows["gym"]["nearest"] is None and rows["gym"]["meets"] is None       # none within 800 m
    assert rows["park"]["meets"] is None and rows["park"]["limit"] is None       # no limit for parks
    strict = {r["category"]: r for r in analysis.walk_table(fake_places(), None, Prefs(max_grocery=1))}
    assert strict["grocery"]["meets"] is False


def test_routed_walking_minutes_win_over_estimates():
    walking = {"method": "osrm_fossgis_foot", "results": [{"name": "Mart", "category": "grocery", "kind": "supermarket",
                                                           "walk_min": 7.5, "walk_m": 600}]}
    row = next(r for r in analysis.walk_table(fake_places(), walking, P) if r["category"] == "grocery")
    assert row["walk_min"] == 7.5 and row["method"] == "osrm_fossgis_foot"


def test_noise_load_weights_type_and_distance():
    club_near = {"group": "noise", "category": "nightclub", "kind": "nightclub", "name": "C", "lat": 0, "lon": 0, "distance_m": 0, "osm": "n/3"}
    club_far = {**club_near, "distance_m": 800}
    pub_near = {**club_near, "category": "pub", "kind": "pub"}
    assert analysis.noise_load(fake_places([club_near])) == 3.0
    assert analysis.noise_load(fake_places([club_far])) == 0.0
    assert analysis.noise_load(fake_places([pub_near])) < analysis.noise_load(fake_places([club_near]))


def test_quiet_score_falls_as_noise_rises():
    assert analysis.score_quiet(0) == 100 and analysis.score_quiet(4) > analysis.score_quiet(12)


def test_quiet_priority_changes_the_overall_weight():
    noisy = {"group": "noise", "category": "nightclub", "kind": "nightclub", "name": "C", "lat": 0, "lon": 0, "distance_m": 10, "osm": "n/3"}
    pl = fake_places([{**noisy, "osm": f"n/{k}"} for k in range(6)])   # six clubs next door
    low = analysis.score_address(pl, None, Prefs(quiet="low"))["Overall"]
    high = analysis.score_address(pl, None, Prefs(quiet="high"))["Overall"]
    assert high < low                      # a noisy block hurts more when quiet matters more


def test_winners_and_ties():
    s = {"A": {"Groceries": 80, "Gym": 50, "Transit": 70, "Quiet": 90, "Overall": 72.5},
         "B": {"Groceries": 60, "Gym": 50, "Transit": 90, "Quiet": 40, "Overall": 60.0}, "C": None}
    w = analysis.winners(s)
    assert w["Groceries"] == "A" and w["Transit"] == "B" and w["Gym"].startswith("tie") and w["Overall"] == "A"
    assert analysis.winners({"A": s["A"]})["Groceries"] == "—"


def test_real_samples_score_between_0_and_100(geo_for):
    from sources.core import places, walking
    for prefix in ("360 State", "100 York", "365 Orchard"):
        g = geo_for(prefix)
        pl = places.find_places(g["lat"], g["lon"]).data
        sc = analysis.score_address(pl, None, P)
        assert sc and all(0 <= v <= 100 for v in sc.values()), prefix
