"""Bug fixes and the two approved additions found in live tests on Connecticut addresses outside New Haven (offline, saved samples)."""
import json

import pytest

import analysis
import facts
import sections
import summary
import ui_html
from sources.core import building, places
from sources.ct import parcels, portfolio, property_type, trail
from sources.matching import split_street_address
from tests.conftest import make_app

import analysis

FRANKLIN = "10 Franklin Avenue, Hartford, CT"            # condo building, 8 unit records, no master record
EVERGREEN = "77 Evergreen Avenue, Hartford, CT"          # condo association record exists
MAIN777 = "777 Main Street, Hartford, CT"                # a record for "Unit CNDASC" and a linked company next door
HORSLEY = "2 Horsley Avenue, New Haven, CT"              # single family, owner lives there
MIDDLETOWN = "200 Main Street Ext, Middletown, CT"       # stored as address_number "200.0"; commercial


def pr(address, city):
    return parcels.find_parcel(address, city)


# ------------------------------------------------------------------ fix 1: "200" and "200.0"
def test_street_number_matches_with_and_without_dot_zero(monkeypatch):
    seen = {}

    def fake(domain, ds, params):
        seen.update(params)
        return [{"address_number": "200.0", "street_name": "MAIN ST EXT", "location": "200 MAIN ST EXT", "owner": "X LLC"}]
    monkeypatch.setattr(parcels, "socrata", fake)
    parcels._live("200 Main Street Ext, Middletown, CT", "Middletown")
    assert "address_number in('200','200.0')" in seen["$where"] and "MAIN ST EXT" in seen["$where"]
    assert portfolio.same_number("200", "200.0") and portfolio.same_number("200.0", "200") and not portfolio.same_number("200", "2000")
    assert split_street_address("200 Main Street Ext, Middletown") == ("200", "MAIN ST EXT")


def test_middletown_200_main_st_ext_finds_the_owner():
    res = pr(MIDDLETOWN, "Middletown")
    assert res.ok and res.data["primary"]["owner"] == "MCGRATH DENTAL PROPERTIES LLC" and res.data["primary"]["address_number"] == "200.0"


# ------------------------------------------------------------------ fix 2: never raw codes or None
def test_condo_association_record_is_not_shown_as_a_raw_code():
    assert property_type.location_label("98 GARDEN ST, Unit CNDASC") == "98 GARDEN ST (condo association record)"
    assert property_type.use_label(None) is None and property_type.use_label("Commercial  MDL-94") == "commercial"
    ll = sections.landlord_section(pr(MAIN777, "Hartford"), None, None, True)
    assert ll["parcel"]["location"] == "777 MAIN ST (condo association record)"
    assert "None" not in json.dumps({k: v for k, v in ll["parcel"].items() if k in ("location", "use")})


def test_owner_details_never_print_none_or_raw_codes():
    ll = sections.landlord_section(pr(MAIN777, "Hartford"), None, None, True)
    text = summary.answers(MAIN777, None, None, None, None, ll, None, True)["owner"]
    assert "None" not in text and "CNDASC" not in text


# ------------------------------------------------------------------ fix 3: the company is its own principal
def test_company_listed_as_its_own_principal_is_said_so_and_related_companies_still_shown():
    t = trail.find_trail("777 MAIN STREET LLC", {}).data
    e = t["entities"][0]
    assert e["name"] == "777 MAIN STREET LLC" and e["is_owner_itself"] is True
    assert e["related_total"] >= 1 and any(c["name"] == "777 RESIDENTIAL LLC" for c in e["companies"])
    assert summary.chain_sentence(t).startswith("The registry lists the company as its own principal")
    assert "the registry lists the company as its own principal" in ui_html.chain_html(t)


def test_a_different_principal_is_not_called_the_owner_itself():
    t = trail.find_trail("ANSONIA STATE STREET LLC", {}).data
    assert not any(e.get("is_owner_itself") for e in t["entities"])
    assert "its own principal" not in summary.chain_sentence(t)


# ------------------------------------------------------------------ fix 4: OSM categories
@pytest.mark.parametrize("tags", [
    {"public_transport": "station", "bus": "yes", "name": "Megabus stop"},
    {"public_transport": "station", "name": "Greyhound"},
    {"amenity": "bus_station", "name": "Union Station Bus Terminal"}])
def test_coach_stops_are_bus_not_train(tags):
    assert places.classify(tags)[1] == "bus_stop"


def test_rail_stations_stay_train_and_newsagents_are_not_groceries():
    assert places.classify({"railway": "station", "public_transport": "station", "name": "Union Station"})[1] == "train_station"
    assert places.classify({"public_transport": "station", "train": "yes"})[1] == "train_station"
    assert places.classify({"shop": "newsagent"}) is None
    assert places.classify({"shop": "convenience", "name": "Yale Newsstand"}) is None
    assert places.classify({"shop": "convenience", "name": "Corner Market"})[1] == "grocery"


# ------------------------------------------------------------------ fix 5: card label
def test_night_label_is_never_quiet_lively():
    assert summary.quiet_phrase(85) == "Night: calm" and summary.quiet_phrase(50) == "Night: lively"
    assert "Quiet:" not in summary.quiet_phrase(10) and "Quiet:" not in summary.quiet_phrase(None)


# ------------------------------------------------------------------ fix 6: 0 street reports
def test_zero_street_reports_adds_the_coverage_note():
    from sources.common import SourceResult
    data = {"total_issues": 0, "results": [], "since": "2025-10-21", "radius_m": 200, "months": 12, "recent": []}
    res = SourceResult("complaints", "ct", "k", True, "sample", data, 0, [], 0.0, {})
    st = sections.street_section(res, True)
    assert st["coverage_note"] == "SeeClickFix use varies by city; 0 may mean little coverage."
    assert "SeeClickFix use varies by city; 0 may mean little coverage." in summary.answers("x", None, None, None, st, None, None, True)["street"]
    data2 = {**data, "total_issues": 4, "results": [{"request_type": "Pothole", "count": 4, "open": 1}]}
    st2 = sections.street_section(SourceResult("complaints", "ct", "k", True, "sample", data2, 4, [], 0.0, {}), True)
    assert st2["coverage_note"] is None


# ------------------------------------------------------------------ fix 7: a linked company on the same street reaches the AI facts and the prompt
def test_linked_company_on_the_same_street_is_in_the_facts_and_the_prompt():
    t = trail.find_trail("777 MAIN STREET LLC", {}).data
    near = facts._trail_on_this_street(MAIN777, t, [])
    assert near and near[0]["owner_company"] == "777 RESIDENTIAL LLC" and near[0]["address"] == "777-799 MAIN ST"
    assert near[0]["how_matched"].startswith("same principal name") and near[0]["confidence"] in ("high", "medium")
    assert facts._trail_on_this_street("1 Elm Street, Hartford, CT", t, []) == []
    prompt = open("prompts/landlord_analyst.md").read()
    assert "related_company_parcels_on_this_street" in prompt and '"linked to"' in prompt


# ------------------------------------------------------------------ Addition A: property type and privacy
def sheet(address, city):
    p = pr(address, city)
    return p, facts.build_fact_sheet(address, None, None, None, {"parcels": p, "registry": None, "portfolio": None}, analysis.Prefs(), True)


def test_condo_building_without_master_record_names_no_unit_owner():
    p, s = sheet(FRANKLIN, "Hartford")
    prop = p.data["property"]
    assert prop["kind"] == "condo_no_master" and prop["unit_records"] == 8
    assert prop["message"] == ("Condo building: 8 unit records with different owners. No single building owner in the parcel data; "
                               "ask who owns the unit you would rent.")
    assert all(r["owner"] == "a private owner" for r in p.data["results"]) and "mailing_address" not in p.data["primary"]
    ll = sections.landlord_section(p, None, None, True)
    assert ll["registry"] is None and ll["portfolio"] is None and "Not searched" in ll["errors"]["registry"]
    assert summary.answers(FRANKLIN, None, None, None, None, ll, None, True)["owner"] == prop["message"]
    assert summary.card_summary(None, None, None, True, True, prop=prop)["facts"][-1][1] == "Condo building: no single owner in the data"
    assert "property_note" in s.text and "Condo building" in s.text


def test_ct_run_does_not_trace_unit_owners_or_private_homes(monkeypatch):
    from sources import ct
    called = []
    monkeypatch.setattr(ct.registry, "find_business", lambda *a, **k: called.append("registry"))
    monkeypatch.setattr(ct.portfolio, "find_portfolio", lambda *a, **k: called.append("portfolio"))
    monkeypatch.setattr(ct.complaints, "fetch_complaints", lambda *a, **k: None)
    for address, city in ((FRANKLIN, "Hartford"), (HORSLEY, "New Haven")):
        ct.run({"lat": 41.0, "lon": -72.0, "city": city}, address)
    assert called == []


def test_condo_association_record_is_called_the_condo_association():
    p = pr(MAIN777, "Hartford")
    assert p.data["property"]["kind"] == "condo_association"
    assert "condo association" in p.data["property"]["message"]
    p2 = pr(EVERGREEN, "Hartford")
    assert p2.data["property"]["kind"] == "condo_association" and p2.data["primary"]["owner"] == "WESTGREEN CONDOMINIUM ASSOC INC"
    assert {r["owner"] for r in p2.data["results"]} == {"WESTGREEN CONDOMINIUM ASSOC INC", "a private owner"}        # unit owners are people
    ll = sections.landlord_section(p2, None, None, True)
    assert summary.answers(EVERGREEN, None, None, None, None, ll, None, True)["owner"].startswith("This record belongs to the condo association")


def test_privately_owned_home_hides_the_name_and_says_it_may_not_be_a_rental():
    p, s = sheet(HORSLEY, "New Haven")
    prop = p.data["property"]
    assert prop["kind"] == "private_home" and prop["message"] == "Looks like a privately owned home where the owner lives. It may not be a rental."
    assert p.data["primary"]["owner"] == "a private owner" and "DEGAETANO" not in json.dumps(p.data) and "DEGAETANO" not in s.text
    ll = sections.landlord_section(p, None, None, True)
    assert ll["parcel"]["owner"] == "a private owner"
    assert summary.answers(HORSLEY, None, None, None, None, ll, None, True)["owner"] == prop["message"]


def test_non_residential_use_says_not_housing():
    p = pr(MIDDLETOWN, "Middletown")
    assert p.data["property"]["kind"] == "not_housing"
    assert p.data["property"]["message"] == "The parcel record lists this as commercial, not housing."
    assert p.data["primary"]["owner"] == "MCGRATH DENTAL PROPERTIES LLC"                    # a company is still named
    assert property_type.classify({"state_use_description": "Vacant Land"}, [])["message"].endswith("vacant land, not housing.")
    assert property_type.classify({"state_use_description": "Exempt Comm"}, [])["kind"] == "not_housing"


def test_apartments_and_company_owners_are_unchanged():
    for key in ("360 State Street, New Haven, CT", "100 York Street, New Haven, CT", "365 Orchard Street, New Haven, CT"):
        p = pr(key, "New Haven")
        assert p.data.get("property", {"kind": "standard"})["kind"] == "standard" and p.data["primary"]["owner"] != "a private owner"
    a = {"state_use_description": "Single Family", "owner": "SMITH JOHN", "location": "5 ELM ST", "mailing_address": "9 OTHER RD"}
    assert property_type.classify(a, [a])["kind"] == "private_owner"                         # a person who owns a house or condo elsewhere: never named
    b = {"state_use_description": "Single Family", "owner": "ELM HOMES LLC", "location": "5 ELM ST", "mailing_address": "5 ELM ST"}
    assert property_type.classify(b, [b])["kind"] == "standard"                              # a company is never "a private owner"
    c = {"state_use_description": "Two Family", "owner": "SMITH JOHN", "location": "5 ELM ST", "mailing_address": "5 ELM ST"}
    assert property_type.classify(c, [c])["kind"] == "standard"                              # multi-family keeps the normal flow
    d = {**a, "owner": "SMITH FAMILY TRUST", "mailing_address": "5 Elm St"}
    assert property_type.classify(d, [d])["kind"] == "standard"


# ------------------------------------------------------------------ Addition B: search by building name
def test_a_name_is_input_without_a_street_number():
    assert building.looks_like_name("Yale University Art Gallery") and building.looks_like_name("Ansonia Apartments, New Haven")
    assert not building.looks_like_name("360 State Street, New Haven, CT") and not building.looks_like_name("")


def test_building_name_found_shows_the_street_address_to_confirm():
    c = building.check("Yale University Art Gallery")
    assert c == {"ok": True, "typed": "Yale University Art Gallery", "name": "Yale University Art Gallery", "address": "1111 Chapel Street, New Haven, CT"}


@pytest.mark.parametrize("name", ["Zzyzx Qwertyplex Towers", "Elm City Market", "Central Park"])   # no match / no house number / no house number
def test_building_name_not_found_or_without_house_number_is_never_guessed(name):
    c = building.check(name)
    assert c == {"ok": False, "typed": name, "message": "Couldn't find that building by name. Please enter the street address."}


def test_name_lookup_is_one_cached_call_per_name(monkeypatch):
    calls = []
    monkeypatch.setattr(building, "get_json", lambda *a, **k: calls.append(a) or [])
    monkeypatch.setenv("LEASELENS_OFFLINE", "0")
    monkeypatch.setattr("sources.common.CACHE_DIR", __import__("pathlib").Path(__import__("tempfile").mkdtemp()))
    building.find_building("Nowhere Heights")
    building.find_building("Nowhere Heights")
    assert len(calls) == 1 and calls[0][1]["limit"] == 1 and calls[0][1]["countrycodes"] == "us"


def test_page_asks_is_this_right_and_continues_only_after_yes(monkeypatch):
    monkeypatch.setattr(building, "check", lambda name: {"ok": True, "typed": name, "name": "Yale University Art Gallery",
                                                         "address": "1111 Chapel Street, New Haven, CT"})
    at = make_app("landing", addresses=[], demo=False)
    at.run()
    at.text_input[0].set_value("Yale University Art Gallery")
    next(b for b in at.button if b.label == "Check addresses").click()
    at.run()
    assert at.session_state["view"] == "landing"
    assert any("We found: **Yale University Art Gallery**, 1111 Chapel Street, New Haven, CT. Is this right?" in i.value for i in at.info)
    assert {"Yes", "Try the street address"} <= {b.label for b in at.button}
    next(b for b in at.button if b.label == "Try the street address").click()
    at.run()
    assert at.session_state["view"] == "landing" and at.text_input[0].value == "" and not at.session_state["name_checks"]
    at.text_input[0].set_value("Yale University Art Gallery")
    next(b for b in at.button if b.label == "Check addresses").click()
    at.run()
    next(b for b in at.button if b.label == "Yes").click()
    at.run()
    assert at.session_state["view"] == "results" and at.session_state["addresses"] == ["1111 Chapel Street, New Haven, CT"]


def test_page_blocks_when_the_name_is_not_found(monkeypatch):
    monkeypatch.setattr(building, "check", lambda name: {"ok": False, "typed": name, "message": building.NOT_FOUND})
    at = make_app("landing", addresses=[], demo=False)
    at.run()
    at.text_input[0].set_value("Zzyzx Qwertyplex Towers")
    next(b for b in at.button if b.label == "Check addresses").click()
    at.run()
    assert at.session_state["view"] == "landing" and any(building.NOT_FOUND in w.value for w in at.warning)


# ------------------------------------------------------------------ follow-up: unit written only on the tax-bill address, cache version
STRAWBERRY = "1 Strawberry Hill Ave, Stamford, CT"       # "Res. Condo"; the location has no unit text


def test_unit_is_read_from_the_mailing_address_and_markers_are_stripped():
    assert property_type.strip_unit("1 STRAWBERRY HILL AVE # 3B") == ("1 STRAWBERRY HILL AVE", "3B")
    assert property_type.strip_unit("1 STRAWBERRY HILL AVE #3D") == ("1 STRAWBERRY HILL AVE", "3D")
    assert property_type.strip_unit("5 ELM ST APT 4") == ("5 ELM ST", "4") and property_type.strip_unit("5 ELM ST STE 200") == ("5 ELM ST", "200")
    assert property_type.strip_unit("5 ELM ST UNIT 4B") == ("5 ELM ST", "4B") and property_type.strip_unit("5 ELM ST") == ("5 ELM ST", "")
    rec = {"location": "1 STRAWBERRY HILL AVENUE", "street_name": "STRAWBERRY HILL AVENUE", "mailing_address": "1 STRAWBERRY HILL AVE # 3B"}
    assert property_type.unit_of(rec) == "3B"
    assert property_type.unit_of({**rec, "mailing_address": "44 HUCKLEBERRY HOLLOW"}) == ""            # a different street is not a unit


def test_condo_with_unit_only_on_the_mailing_address_is_a_condo_building():
    rec = lambda owner, unit: {"location": "1 STRAWBERRY HILL AVENUE", "street_name": "STRAWBERRY HILL AVENUE", "owner": owner,
                               "mailing_address": f"1 STRAWBERRY HILL AVE #{unit}", "state_use_description": "Res. Condo"}
    rows = [rec("BORECKI YVETTE", "3B"), rec("NACHT SALLY", "3E")]
    assert property_type.classify(rows[0], rows)["kind"] == "condo_no_master"


def test_one_condo_record_with_a_person_owner_is_never_named():
    one = {"location": "1 STRAWBERRY HILL AVENUE", "street_name": "STRAWBERRY HILL AVENUE", "owner": "BORECKI YVETTE MEDICI",
           "mailing_address": "1 STRAWBERRY HILL AVE # 3B", "state_use_description": "Res. Condo"}
    assert property_type.classify(one, [one])["kind"] == "private_home"                      # the unit marker is ignored when comparing addresses
    away = {**one, "mailing_address": "9 OTHER RD"}
    assert property_type.classify(away, [away])["kind"] == "private_owner"
    data = property_type.apply_privacy({"primary": away, "results": [away]}, property_type.classify(away, [away]))
    assert data["primary"]["owner"] == "a private owner" and "mailing_address" not in data["primary"]


def test_stamford_real_record_names_no_person_anywhere():
    p = pr(STRAWBERRY, "Stamford")
    assert p.data["property"]["kind"] == "condo_no_master"
    ll = sections.landlord_section(p, None, None, True)
    s = facts.build_fact_sheet(STRAWBERRY, None, None, None, {"parcels": p, "registry": None, "portfolio": None}, analysis.Prefs(), True)
    text = " ".join([json.dumps(p.data), json.dumps(ll), s.text, summary.answers(STRAWBERRY, None, None, None, None, ll, None, True)["owner"]])
    for name in ("BORECKI", "GINSBERG", "RAUCHER", "SHERBER", "NACHT", "YVETTE"):
        assert name not in text
    assert ll["parcel"]["location"] == "1 STRAWBERRY HILL AVENUE"
    assert "Unit" not in sections.landlord_section(pr(FRANKLIN, "Hartford"), None, None, True)["parcel"]["location"]


def test_hartford_777_main_still_shows_the_company_and_middletown_gets_no_rental_verdict():
    ll = sections.landlord_section(pr(MAIN777, "Hartford"), None, None, True)
    assert ll["parcel"]["owner"] == "777 MAIN STREET LLC"
    prop = pr(MIDDLETOWN, "Middletown").data["property"]
    card = summary.card_summary({"Overall": 80, "Quiet": 80}, [], 0, True, True, prop=prop)
    assert card["label"] == "Not housing" and card["verdict"] is None and card["facts"][-1][1] == "Not housing: commercial"


def test_a_saved_record_without_property_is_classified_and_hidden_when_loaded(monkeypatch):
    from sources.common import SourceResult
    old = {"query": "x", "number": "1", "street": "S", "city": "Stamford",
           "primary": {"location": "1 S ST", "owner": "DOE JANE", "mailing_address": "1 S ST", "state_use_description": "Single Family"},
           "results": [{"location": "1 S ST", "owner": "DOE JANE", "mailing_address": "1 S ST", "state_use_description": "Single Family"}]}
    monkeypatch.setattr(parcels, "_find_parcel", lambda *a, **k: SourceResult("parcels", "ct", "k", True, "sample", old, 1, [], 0.0, {}))
    res = parcels.find_parcel("1 S St, Stamford, CT", "Stamford")
    assert res.data["property"]["kind"] == "private_home" and res.data["primary"]["owner"] == "a private owner"


def test_old_cache_entries_without_the_current_version_are_ignored(tmp_path, monkeypatch):
    import sources.common as c
    monkeypatch.setattr(c, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("LEASELENS_NO_CACHE", raising=False)
    c._cache_file("ct", "parcels", "k").parent.mkdir(parents=True, exist_ok=True)
    c._cache_file("ct", "parcels", "k").write_text(json.dumps({"data": {"primary": {"owner": "DOE JANE"}}}))          # written before 'property' existed
    assert c._cache_get("ct", "parcels", "k") is None and c._cache_get("ct", "parcels", "k", stale_ok=True) is None
    c._cache_put("ct", "parcels", "k", {"data": {"x": 1}})
    assert c._cache_get("ct", "parcels", "k")["data"] == {"x": 1} and c.CACHE_VERSION >= 2
