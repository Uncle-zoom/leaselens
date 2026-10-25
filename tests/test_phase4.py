"""Phase 4: legends, badge, copy button, loading text, live safety result, Census batch geocoding."""
import json
from pathlib import Path

import jobs
import sections
import ui_helpers
import under_the_hood as uth
from sources.common import SourceResult
from sources.core import census_batch
from tests.conftest import addr


# ------------------------------------------------------------------ legends
def test_every_map_has_a_legend_and_an_owner_layer_in_it(geo_for):
    import maps
    g = geo_for("360 State")
    assert "Walking rings" in maps.legend_html() and "The building" in maps.legend_html()
    parcels = sections.build_parcel_map(g["lat"], g["lon"], [{"lat": 41.3, "lon": -72.9, "address": "1 A ST", "owner": "X LLC",
                                                             "match_type": "exact name", "confidence": "high"}]).get_root().render()
    assert "markerClusterGroup" in parcels and parcels.count("L.marker(") == 2 and "viewBox" in parcels      # clustered building icons


# ------------------------------------------------------------------ badge, loading, how it works
def test_verdict_badge_is_distinct_for_each_verdict():
    html = {v: ui_helpers.verdict_badge(v, "Because.") for v in ("hidden gem", "fine", "think twice")}
    assert "Hidden gem" in html["hidden gem"] and "Fine" in html["fine"] and "Think twice" in html["think twice"]
    assert len({h.split("background:")[1][:7] for h in html.values()}) == 3     # three different colours


def test_badge_escapes_model_text():
    assert "<script>" not in ui_helpers.verdict_badge("fine", "<script>alert(1)</script>")


def test_loading_html_has_spinner_and_message():
    h = ui_helpers.loading_html("Fetching street-level reports…")
    assert "ll-spin" in h and "Fetching street-level reports" in h


def test_how_it_works_has_three_one_line_steps():
    h = ui_helpers.how_it_works_html()
    assert h.count('class="ll-step"') == 3 and all(f">{n}<" in h for n in "123")


# ------------------------------------------------------------------ copy button
def test_copy_button_carries_the_email_text_safely():
    text = 'Subject: Hi\n\nHello "agent", </script><b>x</b> & more'
    h = ui_helpers.copy_button_html(text)
    assert "Copy email" in h and "navigator.clipboard.writeText" in h and "execCommand" in h and "ff4fa3" not in h.lower()   # blue, not the old pink
    assert "</script><b>" not in h.split("const text =")[1].split(";")[0]        # cannot close the script tag early
    payload = h.split("const text = ")[1].split(";\n")[0].replace("<\\/", "</")
    assert json.loads(payload) == text


def test_demo_address_view_has_a_badge_score_and_copy_email():
    from tests.conftest import make_app, page_html
    at = make_app("detail", detail=1)
    at.run()
    assert not at.exception and not at.error
    md = page_html(at)
    assert "ll-pill" in md and "out of 100" in md
    assert any("Copy email" in f.proto.srcdoc for f in at.get("iframe"))


# ------------------------------------------------------------------ live safety result
def test_live_safety_file_is_complete_and_honest():
    d = uth.live_safety()
    assert d and d["model"] == "gpt-6-luna" and d["address"].startswith("360 State")
    for key in ("filter_on", "filter_off"):
        v = d[key]
        assert {"block_verdict", "flagged_by_filter", "tokens", "cost_usd", "instruction_followed",
                "what_the_model_was_shown_for_the_planted_report"} <= set(v)
        assert v["tokens"] > 0 and v["cost_usd"] > 0
    assert d["filter_on"]["flagged_by_filter"] and not d["filter_off"]["flagged_by_filter"]
    assert "10/10" not in d["filter_on"]["what_the_model_was_shown_for_the_planted_report"]
    assert "10/10" in d["filter_off"]["what_the_model_was_shown_for_the_planted_report"]      # the model really saw it
    assert d["total_cost_usd"] == round(d["filter_on"]["cost_usd"] + d["filter_off"]["cost_usd"], 6)


def test_live_safety_missing_file_returns_none(tmp_path):
    assert uth.live_safety(tmp_path / "nope.json") is None


def test_under_the_hood_shows_the_live_run():
    from tests.conftest import make_app, page_html
    at = make_app("hood")
    at.run()
    assert not at.exception
    assert "Live run with the real model" in page_html(at)
    assert any("Honest reading" in i.value for i in at.info)


# ------------------------------------------------------------------ Census batch geocoder
def test_census_csv_and_parse_roundtrip():
    csv_text = census_batch.build_csv([("101 DWIGHT ST", "New Haven", "CT"), ("9 NOWHERE LN", "New Haven", "CT")])
    assert csv_text.splitlines()[0] == '0,101 DWIGHT ST,New Haven,CT,'
    reply = ('"0","101 DWIGHT ST, New Haven, CT, ","Match","Exact","101 DWIGHT ST, NEW HAVEN, CT, 06511","-72.93,41.30","1","L"\n'
             '"1","9 NOWHERE LN, New Haven, CT, ","No_Match"\n')
    assert census_batch.parse_response(reply, 2) == {0: (41.30, -72.93)}


def fake_rows(n):
    return [{"location": f"{i}  MAIN ST", "property_city": "New Haven", "owner": "X LLC", "match_type": "exact name",
             "confidence": "high"} for i in range(1, n + 1)]


def test_locate_parcels_uses_one_batch_request_and_falls_back_for_misses(monkeypatch):
    monkeypatch.setattr(jobs, "is_offline", lambda: False)
    asked = []

    def fake_batch(addresses):
        asked.append(len(addresses))
        return SourceResult("census_batch", "core", "k", True, "live", {"matched": {"0": [41.3, -72.9], "1": [41.31, -72.91]},
                                                                      "total": len(addresses)}, 2, [])

    nominatim = []

    def fake_geocode(q, save=False):
        nominatim.append(q)
        return SourceResult("geocode", "core", q, True, "live", {"lat": 41.4, "lon": -72.8}, 1, [])
    monkeypatch.setattr(jobs.census_batch, "geocode_batch", fake_batch)
    monkeypatch.setattr(jobs.geocode, "geocode", fake_geocode)
    out = jobs.locate_parcels(fake_rows(4), total=88, limit=25)
    assert asked == [4] and len(out["located"]) == 4 and out["shown"] == 4 and out["total"] == 88
    assert out["from_census_batch"] == 2 and len(nominatim) == 2          # the two Census misses went to Nominatim


def test_locate_parcels_caps_at_25_and_survives_a_batch_failure(monkeypatch):
    monkeypatch.setattr(jobs, "is_offline", lambda: False)
    monkeypatch.setattr(jobs.census_batch, "geocode_batch", lambda a: (_ for _ in ()).throw(RuntimeError("down")))
    calls = []
    monkeypatch.setattr(jobs.geocode, "geocode", lambda q, save=False: calls.append(q) or SourceResult(
        "geocode", "core", q, True, "live", {"lat": 41.4, "lon": -72.8}, 1, []))
    out = jobs.locate_parcels(fake_rows(40), total=40, limit=25)
    assert len(out["located"]) == 25 and len(calls) == 25 and out["from_census_batch"] == 0


def test_locate_parcels_offline_never_calls_the_census_service(monkeypatch):
    monkeypatch.setattr(jobs.census_batch, "geocode_batch", lambda a: (_ for _ in ()).throw(AssertionError("no network offline")))
    from sources.ct import parcels, portfolio
    pr = parcels.find_parcel(addr("365 Orchard"), "New Haven").data["primary"]
    pf = portfolio.find_portfolio(pr)
    out = jobs.locate_parcels(pf.data["results"], pf.data["total_matches"])
    assert len(out["located"]) == 25 and out["total"] == 88


# ------------------------------------------------------------------ public-repo hygiene
def test_user_agent_has_a_contact_only_when_one_is_configured(monkeypatch):
    from sources import common
    monkeypatch.delenv("LEASELENS_CONTACT_EMAIL", raising=False)
    assert "@" not in common.user_agent() and common.user_agent().startswith("LeaseLens/0.1")
    monkeypatch.setenv("LEASELENS_CONTACT_EMAIL", "me@example.org")
    assert "contact: me@example.org" in common.user_agent()


def test_no_personal_email_or_private_path_is_shipped_in_the_code():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    bad = []
    for f in list(root.glob("*.py")) + list(root.glob("sources/**/*.py")) + list(root.glob("tests/*.py")) + list(root.glob("scripts/*.py")) + [root / "README.md"]:
        text = f.read_text()
        if f.name in ("check_repo.py", "test_phase4.py"):      # these two name the patterns they search for
            continue
        if re.search(r"[\w.]+@gmail\.com", text) or "/Us" + "ers/" in text:
            bad.append(f.name)
    assert not bad, bad
