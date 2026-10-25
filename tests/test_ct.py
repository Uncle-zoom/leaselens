from sources.ct import complaints, parcels, portfolio, registry
from tests.conftest import addr

STATE = addr("360 State")
ORCHARD = addr("365 Orchard")


def test_ct_complaints_from_sample(geo_for):
    g = geo_for("360 State")
    res = complaints.fetch_complaints(g["lat"], g["lon"])
    assert res.ok and res.origin == "sample"
    assert res.count == res.data["total_issues"] == sum(x["count"] for x in res.data["results"])
    assert res.data["radius_m"] == 200 and res.data["months"] == 12
    assert res.data["results"] == sorted(res.data["results"], key=lambda x: -x["count"])   # grouped, biggest first


def test_ct_parcels_from_sample():
    res = parcels.find_parcel(STATE, "New Haven")
    assert res.ok and res.origin == "sample"
    p = res.data["primary"]
    assert p["owner"] == "ANSONIA STATE STREET LLC" and p["mailing_city"] == "NEW YORK"
    assert {"owner", "mailing_address", "mailing_city", "mailing_state"} <= set(res.fields)


def test_ct_registry_from_sample():
    res = registry.find_business("ANSONIA STATE STREET LLC")
    assert res.ok and res.origin == "sample"
    assert res.data["business"]["name"] == "Ansonia State Street LLC" and res.data["matched_how"] == "exact name"
    assert res.data["registered_agents"] and res.data["principals"]
    flat = str(res.data)
    assert "residence" not in flat and "@" not in flat      # personal residence addresses / e-mails are not kept


def test_ct_registry_normalized_match_from_sample():
    res = registry.find_business("ADAR INVESTMENTS LLC")      # registry spells it "ADAR INVESTMENTS, LLC"
    assert res.ok and res.data["matched_how"] == "normalized name" and res.data["confidence"] == "medium"


def test_ct_portfolio_records_how_each_match_was_made():
    subject = parcels.find_parcel(ORCHARD, "New Haven").data["primary"]
    res = portfolio.find_portfolio(subject)
    assert res.ok and res.origin == "sample" and res.count > 0
    allowed = {"exact name", "normalized name", "same mailing address"}
    for m in res.data["results"]:
        assert m["match_type"] in allowed and m["confidence"] in {"high", "medium", "low"} and m["reason"]
        assert not (m["address_number"] == subject["address_number"] and m["street_name"] == subject["street_name"])
    assert any(m["match_type"] == "exact name" and m["confidence"] == "high" for m in res.data["results"])
