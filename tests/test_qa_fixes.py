"""Fixes from the live QA test: one-click Demo switch, AI on the address view, failed lookups never shown as "none", plurals."""
import ast
import re
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import summary
import team
import wording
from sources.common import SourceResult
from sources.core import places as core_places
from tests.conftest import DEMO3, make_app, page_html

APP = Path(__file__).resolve().parent.parent / "app.py"


# ------------------------------------------------------------------ 1. the Demo switch takes effect on the first click
def test_demo_switch_turns_off_with_one_change_and_keeps_the_addresses():
    at = make_app("results", addresses=[DEMO3[0], DEMO3[2]])
    at.run()
    assert at.session_state["demo"] is True
    at.sidebar.toggle[0].set_value(False)           # ONE change
    at.run()
    assert not at.exception
    assert at.session_state["demo"] is False and at.session_state["addresses"] == [DEMO3[0], DEMO3[2]]
    assert at.session_state["view"] == "results" and page_html(at).count('class="ll-card"') == 2
    assert "Demo mode only has the 3 sample addresses" not in " ".join(w.value for w in at.warning)


def test_demo_switch_turns_back_on_with_one_change_and_keeps_the_addresses():
    at = make_app("results", addresses=[DEMO3[1]], demo=False)
    at.run()
    at.sidebar.toggle[0].set_value(True)
    at.run()
    assert at.session_state["demo"] is True and at.session_state["addresses"] == [DEMO3[1]] and page_html(at).count('class="ll-card"') == 1


def test_switching_on_the_landing_page_keeps_the_searched_addresses():
    """(In a real browser an unsent form field also survives the switch: checked by hand with Playwright. AppTest cannot model that.)"""
    at = make_app("landing", addresses=[DEMO3[0], DEMO3[1]])
    at.run()
    assert [t.value for t in at.text_input] == [DEMO3[0], DEMO3[1]]
    at.sidebar.toggle[0].set_value(False)
    at.run()
    assert at.session_state["demo"] is False and [t.value for t in at.text_input] == [DEMO3[0], DEMO3[1]]


def test_every_waiting_loop_in_the_app_lets_a_click_through():
    """Streamlit only notices a click when the script sends something to the page. A silent wait loop (the cause of the two-click bug)
    must call beat() or update a placeholder on every pass."""
    tree = ast.parse(APP.read_text())
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.While)]
    assert len(loops) >= 4
    for loop in loops:
        calls = {c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", "") for c in ast.walk(loop) if isinstance(c, ast.Call)}
        assert "beat" in calls or "markdown" in calls, f"while loop at line {loop.lineno} never talks to the page"


# ------------------------------------------------------------------ 2. "Get the AI verdict" on the address view stays on the address view
def _live_detail(monkeypatch, detail=1):
    monkeypatch.setenv("PORTKEY_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MODEL", "gpt-6-luna")
    monkeypatch.setattr("sources.common.load_dotenv", lambda *a, **k: False)
    block = {"verdict": "fine", "summary": "A mixed block.", "reasons": ["The nearest grocery is near.", "Quiet is 4.6.", "There are 100 street-level reports."]}
    landlord = {"plain_english": "The parcel record lists the owner.", "observations": [], "questions": ["Who manages it?", "Who fixes repairs?", "Who is the landlord?"]}
    email = {"purpose": "ask_questions", "tone": "friendly", "subject": "Questions", "body": "Hello, thanks. [Your name]", "facts_cited": []}
    rank = {"ranking": [{"address": a, "rank": i + 1, "headline": "ok", "strengths": [], "trade_offs": []} for i, a in enumerate(DEMO3)], "overall": "ok", "key_tradeoffs": "ok"}

    def fn(messages, info: AgentInfo):
        props = set(info.output_tools[0].parameters_json_schema.get("properties", {}))
        out = block if "verdict" in props else landlord if "plain_english" in props else email if "subject" in props else rank
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])
    monkeypatch.setattr(team, "make_model", lambda: FunctionModel(fn))
    return make_app("detail", detail=detail, demo=False)


def test_ai_verdict_from_the_address_view_stays_on_that_address(monkeypatch):
    at = _live_detail(monkeypatch, detail=1)
    at.run()
    assert not at.exception
    next(b for b in at.button if b.label == "Get the AI verdict").click()
    at.run()
    assert not at.exception and not at.error
    assert at.session_state["view"] == "detail" and at.session_state["detail"] == 1           # did not jump to the results list
    html = page_html(at)
    assert "100 York Street" in html and "Three questions to ask the landlord" in html and "ll-pill" in html
    assert any(t.label == "Edit before you send it yourself" for t in at.text_area)              # the email draft is there too
    handle = next(iter(at.session_state["ai_handles"].values()))
    assert handle.done


def test_request_ai_no_longer_changes_the_page():
    src = APP.read_text()
    body = src.split("def request_ai()")[1].split("\ndef ")[0]
    assert "S.view" not in body and "want_ai" in body


# ------------------------------------------------------------------ 3. a failed lookup is never "none within 800 m"
FAILED = SourceResult("places", "core", "k", False, "none", error="live call failed and no saved sample", live_error="RuntimeError: all Overpass servers failed")
EMPTY = SourceResult("places", "core", "k", True, "live", {"center": {"lat": 41.3, "lon": -72.9}, "radius_m": 800, "counts": {}, "results": []}, 0, [])


def test_failed_places_lookup_says_couldnt_check_on_the_card(monkeypatch):
    monkeypatch.setenv("LEASELENS_NO_CACHE", "1")
    monkeypatch.setattr(core_places, "find_places", lambda *a, **k: FAILED)
    at = make_app("results", addresses=[DEMO3[0]], demo=False)
    at.run()
    assert not at.exception
    html = page_html(at).replace("&#x27;", "'")
    assert "Grocery: couldn't check right now" in html and "Night: couldn't check right now" in html and "Transit: couldn't check right now" in html
    assert "none within 800 m" not in html and "out of 100" not in html


def test_failed_places_lookup_says_couldnt_check_on_the_address_view(monkeypatch):
    monkeypatch.setenv("LEASELENS_NO_CACHE", "1")
    monkeypatch.setattr(core_places, "find_places", lambda *a, **k: FAILED)
    at = make_app("detail", detail=0, demo=False)
    at.run()
    assert not at.exception
    html = page_html(at)
    assert "none within 800 m" not in html and "Still mapping" not in html
    assert summary.COULDNT_CHECK_PLACES in html.replace("&#x27;", "'") or "couldn't check what's around this address right now" in html.replace("&#x27;", "'")
    assert any(summary.COULDNT_CHECK_PLACES == w.value for w in at.warning)
    assert "We couldn't check the places around this address right now" in html.replace("&#x27;", "'")


def test_a_successful_lookup_with_nothing_found_still_says_none(monkeypatch):
    monkeypatch.setenv("LEASELENS_NO_CACHE", "1")          # the walking step is cached by coordinates on disk: do not let an old answer in
    monkeypatch.setattr(core_places, "find_places", lambda *a, **k: EMPTY)
    at = make_app("results", addresses=[DEMO3[0]], demo=False)
    at.run()
    html = page_html(at).replace("&#x27;", "'")
    assert "Grocery: none within 800 m" in html and "couldn't check" not in html


def test_failed_lookup_in_the_agents_facts_is_marked_not_available():
    import analysis
    import facts
    s = facts.build_fact_sheet("x", None, {"places": FAILED, "walking": None}, None, None, analysis.Prefs(), False)
    assert s.data["walking"].startswith("not available") and "none within 800 m" not in s.text


def test_failed_street_lookup_is_not_shown_as_still_checking_or_none(monkeypatch):
    from sources.ct import complaints
    bad = SourceResult("complaints", "ct", "k", False, "none", error="no saved sample", live_error="Timeout")
    monkeypatch.setattr(complaints, "fetch_complaints", lambda *a, **k: bad)
    at = make_app("detail", detail=0, demo=False)
    at.run()
    assert not at.exception
    assert summary.COULDNT_CHECK_STREET in page_html(at).replace("&#x27;", "'")


# ------------------------------------------------------------------ 4. plurals
@pytest.mark.parametrize("n,expected", [(0, "0 pubs"), (1, "1 pub"), (2, "2 pubs")])
def test_plural_helper(n, expected):
    assert wording.plural(n, "pub") == expected


def test_plural_helper_irregular_and_phrases():
    assert wording.plural(1, "fire station") == "1 fire station" and wording.plural(3, "fire station") == "3 fire stations"
    assert wording.plural(1, "company", "companies") == "1 company" and wording.plural(2, "company", "companies") == "2 companies"


def test_noise_answer_uses_singular_for_one():
    rows = [{"label": "Pubs", "count": 1}, {"label": "Fire stations", "count": 1}, {"label": "Bars", "count": 12}, {"label": "Nightclubs", "count": 0}]
    a = summary.answers("x", {"Quiet": 20}, None, rows, None, None, None, True)["noise"]
    assert a == "Expect it to be busy at night: 12 bars, 1 pub, 1 fire station within 800 m."
    rows2 = [{"label": "Hospitals", "count": 1}, {"label": "Rail lines", "count": 2}]
    assert summary.answers("x", {"Quiet": 20}, None, rows2, None, None, None, True)["noise"].endswith("2 rail lines, 1 hospital within 800 m.")


def test_map_summary_and_minutes_use_singular_for_one():
    data = {"results": [], "counts": {"pub": 1, "fire_station": 1, "rail_line": 1, "bar": 2}}
    last = summary.map_text_alternative(data, [])[-1]
    assert "2 bars" in last and "1 pub" in last and "1 fire station" in last and "1 rail line" in last and "1 pubs" not in last
    assert summary.on_foot(1, 120) == "1 minute on foot" and summary.on_foot(1, 120, away=True) == "1 minute away" and summary.on_foot(2.5, 200) == "2.5 minutes on foot"


def test_pages_never_say_1_followed_by_a_plural_noun():
    for view, d in (("detail", 0), ("detail", 1), ("detail", 2), ("results", 0), ("compare", 0)):
        at = make_app(view, detail=d)
        at.run()
        text = page_html(at) + " ".join(c.value for c in at.caption) + " ".join(m.value for m in at.markdown)
        bad = re.findall(r"(?<![\d.,])1 (?:pubs|bars|nightclubs|fire stations|hospitals|rail lines|parcels|companies|buildings|reports|principals)\b", text)
        assert not bad, (view, d, bad)


# ------------------------------------------------------------------ 900 Chapel St: card and map summary must name the same grocery
def test_implausibly_long_routes_fall_back_to_the_straight_line_estimate(monkeypatch):
    from sources.core import walking
    origin = (41.3062053, -72.926438)
    dests = [{"name": "Marketa", "category": "grocery", "kind": "convenience", "lat": 41.306306, "lon": -72.927365},
             {"name": "Rite Aid", "category": "pharmacy", "kind": "pharmacy", "lat": 41.3070, "lon": -72.9250}]
    resp = {"code": "Ok", "durations": [[0, 940, 130]], "distances": [[0, 1176, 200]]}      # Marketa: 78 m away "walks" 1,176 m
    monkeypatch.setattr(walking, "get_json", lambda *a, **k: resp)
    res = walking._osrm("u", origin, dests)
    marketa, rite = res
    assert marketa["walk_m"] < 150 and marketa["walk_min"] < 2 and "implausibly" in marketa["estimated"]
    assert rite["walk_m"] == 200 and "estimated" not in rite


def test_map_summary_and_card_name_the_same_nearest_grocery():
    places = {"results": [{"category": "grocery", "name": "Marketa", "distance_m": 78}, {"category": "grocery", "name": "Gateway Food Store", "distance_m": 116}],
              "counts": {}}
    rows = [{"category": "grocery", "label": "Grocery", "nearest": "Gateway Food Store", "walk_min": 13.3, "walk_m": 996}]
    line = summary.map_text_alternative(places, rows)[0]
    assert line == "Grocery: Gateway Food Store, 13.3 minutes on foot"
    assert summary.map_text_alternative(places, [])[0] == "Grocery: Marketa, 78 m away"            # no walking data: the straight-line fallback
