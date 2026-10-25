"""Each card section, built from the saved New Haven samples (offline)."""
import re

import analysis
import sections
from sources.common import SourceResult
from sources.core import places, walking
from sources.ct import complaints, parcels, portfolio, registry
from tests.conftest import addr

P = analysis.Prefs()


def block(geo):
    pl = places.find_places(geo["lat"], geo["lon"])
    wk = walking.walking_times((geo["lat"], geo["lon"]), [])
    return pl, wk


PIN = [{"lat": 41.31, "lon": -72.92, "address": "1 A ST", "owner": "X LLC", "match_type": "exact name", "confidence": "high"},
       {"lat": 41.32, "lon": -72.93, "address": "2 B ST", "owner": "X LLC", "match_type": "exact name", "confidence": "high"}]


def test_block_map_has_blue_building_pin_two_walking_rings_and_shaped_icon_markers(geo_for):
    import maps
    g = geo_for("360 State")
    pl, wk = block(g)
    html = sections.build_block_map(g["lat"], g["lon"], pl).get_root().render()
    assert "The building" in html and '"blue"' in html                                   # the building is a blue pin
    assert html.count("L.circle(") == 2 and "5 min walk" in html and "10 min walk" in html     # thin walking rings, labelled
    for shape in ("mk am", "mk sq", "mk tri", "mk dia"):                                    # shapes, not just colour
        assert f'class=\\"{shape}\\"' in html or f'class="{shape}"' in html, shape
    assert "svg aria-hidden" in html and "viewBox" in html                                              # recognisable icons, not letter codes
    for code in (">Pu<", ">Ba<", ">Nc<", ">Rx<", ">Y<", ">G<"):
        assert code not in html, code
    assert abs(maps.ring_radius_m(5) - 320) < 2 and abs(maps.ring_radius_m(10) - 641) < 2
    assert "Legend" not in html                                                             # the legend is under the map, not on it


def test_nearby_markers_merge_into_numbered_clusters(geo_for):
    g = geo_for("360 State")
    pl, _ = block(g)
    html = sections.build_block_map(g["lat"], g["lon"], pl).get_root().render()
    assert html.count("markerClusterGroup(") == 2 and "getChildCount()" in html           # one cluster for amenities, one for noise
    assert "maxClusterRadius" in html


def test_building_marker_is_added_last_and_lifted_above_all_others(geo_for):
    g = geo_for("360 State")
    pl, _ = block(g)
    html = sections.build_block_map(g["lat"], g["lon"], pl).get_root().render()
    assert '"zIndexOffset": 2000' in html
    assert html.rfind("The building") > html.rfind("L.circle(") and html.rfind("The building") > html.rfind("markerClusterGroup(")


def test_tooltips_name_the_place_and_say_the_walk_in_plain_words(geo_for):
    g = geo_for("360 State")
    pl, _ = block(g)
    html = sections.build_block_map(g["lat"], g["lon"], pl).get_root().render()
    assert re.search(r"Elm City Market · Grocery · (next door|under 1 min walk|\d+(\.\d)? min walk)", html)


def test_legend_is_html_under_the_map_with_the_same_shapes():
    import maps
    h = maps.legend_html(owner=True)
    assert 'aria-label="Map legend"' in h and h.count("<li>") == 7
    for cls in ("lg am", "lg sq", "lg tri", "lg dia", "lg ow", "lg ring", "lg pin"):
        assert cls in h
    assert "Owner&#x27;s other buildings" in h and maps.legend_html().count("<li>") == 6


def test_block_map_draws_only_the_nearest_few_markers_so_it_stays_calm(geo_for):
    g = geo_for("360 State")
    pl, _ = block(g)
    html = sections.build_block_map(g["lat"], g["lon"], pl).get_root().render()
    assert html.count("L.marker(") <= 45 and pl.data["counts"]["bus_stop"] > 10


def test_block_map_uses_a_toggleable_clustered_layer_for_the_owners_other_buildings(geo_for):
    g = geo_for("360 State")
    pl, _ = block(g)
    html = sections.build_block_map(g["lat"], g["lon"], pl, owner_pins=PIN, owner_total=88).get_root().render()
    assert "markerClusterGroup" in html and "Owner\\u0027s other buildings (2 of 88)" in html and "L.control.layers" in html
    assert sections.build_block_map(g["lat"], g["lon"], pl).get_root().render().count("L.control.layers") == 0


def test_map_renders_markers_without_any_network(geo_for):
    g = geo_for("360 State")
    pl, _ = block(g)
    html = sections.build_block_map(g["lat"], g["lon"], pl).get_root().render()       # tiles are remote; everything else is inline
    assert html.count("L.marker(") > 5 and "viewBox" in html


def test_map_shows_immediately_without_places(geo_for):
    g = geo_for("360 State")
    html = sections.build_block_map(g["lat"], g["lon"], None).get_root().render()
    assert "The building" in html and html.count("L.marker(") == 3 and "markerClusterGroup" not in html   # the building and two ring labels


def test_dark_basemap_is_selected_by_the_visitors_system_setting(geo_for):
    g = geo_for("360 State")
    html = sections.build_block_map(g["lat"], g["lon"], None).get_root().render()
    assert "prefers-color-scheme: dark" in html and "World_Light_Gray_Base" in html and "World_Dark_Gray_Base" in html


def test_block_section_rows_and_limits(geo_for):
    g = geo_for("360 State")
    pl, wk = block(g)
    sec = sections.block_section(pl, wk if wk.ok else None, P)
    assert sec["error"] is None and [r["category"] for r in sec["rows"]] == [c for c, _ in analysis.AMENITY_ROWS]
    grocery = sec["rows"][0]
    assert grocery["nearest"] and grocery["meets"] is (grocery["walk_min"] <= P.max_grocery)
    assert "OpenStreetMap" in sec["cite"][0] and sec["origin"] == "saved sample (offline)"


def test_block_section_error_is_a_message_not_an_exception():
    failed = SourceResult("places", "core", "k", False, "none", error="no sample", live_error="Timeout")
    assert "could not be loaded" in sections.block_section(failed, None, P)["error"]
    assert "not available" in sections.block_section(None, None, P)["error"]


def test_noise_section_counts_and_nearest(geo_for):
    g = geo_for("360 State")
    pl, _ = block(g)
    sec = sections.noise_section(pl)
    rows = {r["category"]: r for r in sec["rows"]}
    assert set(rows) == {"nightclub", "bar", "pub", "fire_station", "hospital", "rail_line"}
    assert rows["bar"]["count"] == pl.data["counts"]["bar"] > 0 and rows["bar"]["nearest_m"] <= 800
    assert sec["load"] > 0


def test_street_section_is_labelled_street_level(geo_for):
    g = geo_for("360 State")
    sec = sections.street_section(complaints.fetch_complaints(g["lat"], g["lon"]), in_ct=True)
    assert sec["error"] is None and sec["label"] == "Street-level reports, not housing complaints"
    assert sec["total"] == sum(r["count"] for r in sec["rows"]) > 0 and "SeeClickFix" in sec["cite"][0]


def test_street_section_outside_ct_says_so():
    sec = sections.street_section(None, in_ct=False)
    assert "only connected for Connecticut" in sec["error"]


def landlord(address):
    pr = parcels.find_parcel(address, "New Haven")
    primary = pr.data["primary"]
    return sections.landlord_section(pr, registry.find_business(primary["owner"]), portfolio.find_portfolio(primary), True)


def test_landlord_section_full_chain_with_match_and_confidence():
    sec = landlord(addr("365 Orchard"))
    assert sec["available"] and sec["parcel"]["owner"] == "ADAR INVESTMENTS LLC"
    assert sec["registry"]["entity_type"] and sec["registry"]["status"] and sec["registry"]["matched_how"] == "normalized name"
    pf = sec["portfolio"]
    assert pf["total"] > 0 and {"Address", "How matched", "Confidence", "Why"} <= set(pf["rows"][0])
    assert {r["How matched"] for r in pf["rows"]} <= {"exact name", "normalized name", "same mailing address"}
    assert all(sec["cites"][k][1].startswith("https://data.ct.gov") for k in ("parcel", "registry", "portfolio"))


def test_landlord_section_registry_agent_and_principals():
    sec = landlord(addr("360 State"))
    assert sec["registry"]["agents"] == ["C T CORPORATION SYSTEM"] and sec["registry"]["principals"]
    assert sec["portfolio"]["total"] == 0


def test_landlord_section_partial_failures_do_not_raise():
    pr = parcels.find_parcel(addr("360 State"), "New Haven")
    missing = SourceResult("registry", "ct", "k", False, "none", error="no sample")
    sec = sections.landlord_section(pr, missing, None, True)
    assert sec["parcel"] and "No Business Registry record" in sec["errors"]["registry"] and "portfolio" in sec["errors"]
    bad = SourceResult("parcels", "ct", "k", False, "none", live_error="HTTPError: 503")
    assert "could not be loaded" in sections.landlord_section(bad, None, None, True)["errors"]["parcel"]


def test_landlord_section_outside_ct():
    sec = sections.landlord_section(None, None, None, False, ("New York City",))
    assert not sec["available"] and "not available in this state yet" in sec["note"] and "coming soon" in sec["note"]


def test_the_map_opens_fitted_to_the_ten_minute_ring(geo_for):
    import maps
    g = geo_for("360 State")
    b = maps.ring_bounds(g["lat"], g["lon"])
    assert abs((b[1][0] - b[0][0]) * 111_320 / 2 - maps.ring_radius_m(10)) < 3                  # half the box height is the ring radius
    html = sections.build_block_map(g["lat"], g["lon"], None).get_root().render()
    assert "fitBounds(" in html and f"{b[0][0]}" in html and f"{b[1][1]}" in html          # opens fitted to the ring
    assert "fitted < 2" in html                                                                    # re-fits if the iframe was first measured at the wrong size
    assert maps.ring_bounds(g["lat"], g["lon"], 5)[1][0] < b[1][0]


def test_owner_map_refits_to_all_the_parcels_and_has_its_own_short_legend(geo_for):
    import maps
    g = geo_for("360 State")
    pins = [{"lat": 41.35, "lon": -72.95, "address": "1 A", "owner": "X", "match_type": "exact name", "confidence": "high"}]
    html = sections.build_parcel_map(g["lat"], g["lon"], pins).get_root().render()
    assert "fitBounds(" in html and "fitted < 2" in html and "41.35" in html and "lw = 0" in html     # watches its own box, not Leaflet's cache
    legend = maps.legend_html(True, owner_only=True)
    assert legend.count("<li>") == 2 and "The building" in legend and "several close together" in legend and "Walking rings" not in legend
