"""Maps with an explicit height, hedged Overpass lookups, parallel agents, progressive AI results."""
import json
import threading
import time

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import analysis
import sections
import team
import ui_helpers
import usage_log
from guardrails import Budget
from sources.core import places
from tests.conftest import addr


# ------------------------------------------------------------------ maps render in every tab
def test_maps_are_drawn_in_a_fixed_height_iframe(monkeypatch, geo_for):
    import streamlit as st
    seen = []
    monkeypatch.setattr(st, "iframe", lambda html, height=None, **k: seen.append((html, height)), raising=False)
    g = geo_for("360 State")
    ui_helpers.show_map(sections.build_map(g["lat"], g["lon"], None), 420)
    ui_helpers.show_map(sections.build_parcel_map(g["lat"], g["lon"], []), 400)
    assert [h for _, h in seen] == [420, 400]
    assert all("L.map" in html or "leaflet" in html.lower() for html, _ in seen)


@pytest.mark.parametrize("detail", [0, 1, 2])
def test_every_address_view_gets_a_map_iframe(detail):
    from tests.conftest import make_app
    at = make_app("detail", detail=detail)
    at.run()
    assert not at.exception
    maps_ = [f for f in at.get("iframe") if "leaflet" in f.proto.srcdoc.lower()]
    assert maps_ and "The building" in maps_[0].proto.srcdoc


# ------------------------------------------------------------------ Overpass: smaller query, fastest first, hedging
def test_query_is_small_and_clips_rail_geometry():
    q = places.build_query(41.3054, -72.9232)
    assert 'node(around:800,41.3054,-72.9232)["highway"="bus_stop"]' in q            # bus stops: nodes only
    assert "out center tags qt;" in q and "geom(" in q and "[timeout:20]" in q
    assert len(q) < 1200


def test_parse_ignores_null_points_in_clipped_rail_geometry():
    el = {"type": "way", "id": 9, "tags": {"railway": "rail"},
          "geometry": [None, {"lat": 41.3070, "lon": -72.9232}, None]}
    d = places.parse([el], 41.3054, -72.9232)
    assert d["counts"]["rail_line"] == 1
    assert places.parse([{**el, "geometry": [None, None]}], 41.3054, -72.9232)["counts"]["rail_line"] == 0


def test_fastest_known_server_is_asked_first():
    lat = {places.SERVERS[0]: 30.0, places.SERVERS[1]: 2.0, places.SERVERS[2]: 5.0}
    assert places.order_servers(lat) == [places.SERVERS[1], places.SERVERS[2], places.SERVERS[0]]
    assert places.order_servers({})[0] in places.SERVERS


def _fake_http(delays: dict[str, float], fail: set[str] = frozenset(), log: list | None = None):
    def http(method, url, data=None, timeout=None, attempts=1, **k):
        if log is not None:
            log.append((url, timeout, time.monotonic()))
        time.sleep(delays.get(url, 0.0))
        if url in fail:
            raise TimeoutError("slow")

        class R:
            def json(self):
                return {"elements": [{"type": "node", "id": 1, "lat": 41.3055, "lon": -72.9232, "tags": {"shop": "supermarket", "name": "Mart"}}]}
        return R()
    return http


@pytest.fixture
def fast_hedge(monkeypatch, tmp_path):
    monkeypatch.setattr(places, "HEDGE_AFTER", 0.15)
    monkeypatch.setattr(places, "LATENCY_FILE", tmp_path / "lat.json")
    monkeypatch.setattr(places, "_latencies", lambda: {s: i for i, s in enumerate(places.SERVERS)})   # SERVERS[0] fastest


def test_first_server_answers_alone_when_it_is_fast(monkeypatch, fast_hedge):
    log = []
    monkeypatch.setattr(places, "http", _fake_http({}, log=log))
    out = places._live(41.3054, -72.9232, 800)
    assert out["server"] == places.SERVERS[0] and len(log) == 1 and log[0][1] == places.FIRST_TIMEOUT   # 8 s limit, no hedge


def test_slow_first_server_is_hedged_and_the_fast_mirror_wins(monkeypatch, fast_hedge):
    slow, fast = places.SERVERS[0], places.SERVERS[2]
    log = []
    monkeypatch.setattr(places, "http", _fake_http({slow: 2.0}, log=log))
    t0 = time.monotonic()
    out = places._live(41.3054, -72.9232, 800)
    assert out["server"] != slow and time.monotonic() - t0 < 1.0              # did not wait for the slow server
    assert {u for u, _, _ in log} == set(places.SERVERS)


def test_failed_first_server_falls_back_immediately(monkeypatch, fast_hedge):
    monkeypatch.setattr(places, "http", _fake_http({}, fail={places.SERVERS[0]}))
    out = places._live(41.3054, -72.9232, 800)
    assert out["server"] != places.SERVERS[0]


def test_all_servers_failing_raises_a_clear_error(monkeypatch, fast_hedge):
    monkeypatch.setattr(places, "http", _fake_http({}, fail=set(places.SERVERS)))
    with pytest.raises(RuntimeError, match="all Overpass servers failed"):
        places._live(41.3054, -72.9232, 800)


# ------------------------------------------------------------------ AI team: parallel, progressive, no coordinator for one address
BLOCK = {"verdict": "fine", "summary": "A mixed block.", "reasons": [
    "The nearest grocery, J & J, is a 2.2 minute walk.", "No gym is listed within 800 m.", "There are 54 street-level reports."]}
LANDLORD = {"plain_english": "The parcel record lists ADAR INVESTMENTS LLC.", "observations": [], "questions": ["a?", "b?", "c?"]}
EMAIL = {"purpose": "ask_questions", "subject": "Questions", "body": "Hello, thanks.", "facts_cited": []}


def timed_model(delay: float, calls: list):
    """Every call takes `delay` seconds; the answer depends on which output schema was asked for."""
    def fn(messages, info: AgentInfo):
        calls.append((threading.current_thread().name, time.monotonic()))
        time.sleep(delay)
        props = set(info.output_tools[0].parameters_json_schema.get("properties", {}))
        out = BLOCK if "verdict" in props else LANDLORD if "plain_english" in props else EMAIL if "subject" in props else \
            {"ranking": [], "overall": "x", "key_tradeoffs": "y"}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])
    return lambda: FunctionModel(fn)


@pytest.fixture(autouse=True)
def _no_real_log(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_log, "LOG", tmp_path / "usage_log.json")


@pytest.fixture
def sheet():
    from app_data import collect_fact_sheet
    return collect_fact_sheet(addr("365 Orchard"), analysis.Prefs())


def test_three_agents_run_in_parallel_not_in_sequence(sheet):
    calls = []
    t = team.Team(timed_model(0.4, calls))
    t0 = time.monotonic()
    run = t.start([sheet], Budget(**team.RUN_CAPS))
    run.wait()
    elapsed = time.monotonic() - t0
    assert len(calls) == 3 and elapsed < 0.4 * 2                         # sequential would be >= 1.2 s
    assert max(c[1] for c in calls) - min(c[1] for c in calls) < 0.3      # all three started together


def test_one_address_makes_no_coordinator_call(sheet):
    calls = []
    run = team.Team(timed_model(0.01, calls)).start([sheet], Budget(**team.RUN_CAPS))
    run.wait()
    snap = run.snapshot()
    assert len(calls) == 3 and snap["recommendation"] is None and snap["done"] and set(snap["addresses"][sheet.address]) == {"block", "landlord", "email"}


def test_two_addresses_get_a_coordinator_call_after_the_specialists(sheet):
    from app_data import collect_fact_sheet
    other = collect_fact_sheet(addr("360 State"), analysis.Prefs())
    calls = []
    run = team.Team(timed_model(0.01, calls)).start([sheet, other], Budget(**team.RUN_CAPS))
    run.wait()
    assert len(calls) == 7                                              # 3 specialists x 2 addresses + 1 coordinator
    assert run.snapshot()["recommendation"] is not None and run.finished_count() == 7


def test_results_appear_as_each_agent_finishes(sheet):
    gate = threading.Event()
    state = {"n": 0}

    def fn(messages, info: AgentInfo):
        props = set(info.output_tools[0].parameters_json_schema.get("properties", {}))
        if "subject" in props:                      # the email draft is the slow one
            gate.wait(5)
            out = EMAIL
        else:
            out = BLOCK if "verdict" in props else LANDLORD
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])
    run = team.Team(lambda: FunctionModel(fn)).start([sheet], Budget(**team.RUN_CAPS))
    deadline = time.monotonic() + 3
    while run.finished_count() < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    snap = run.snapshot()                           # block and landlord are in while the email is still being written
    assert not snap["done"] and set(snap["addresses"][sheet.address]) == {"block", "landlord"}
    gate.set()
    run.wait()
    assert run.snapshot()["done"] and "email" in run.snapshot()["addresses"][sheet.address]


def test_budget_error_in_one_agent_does_not_hide_the_others(sheet):
    run = team.Team(timed_model(0.01, [])).start([sheet], Budget("this run", max_requests=1))
    run.wait()
    snap = run.snapshot()
    assert snap["errors"] and "limit reached" in snap["errors"][0] and snap["done"]


def test_request_cap_is_atomic_under_parallel_calls():
    b = Budget("this run", max_requests=5)
    passed, blocked = [], []

    def go():
        try:
            b.reserve()
            passed.append(1)
        except guardrails.BudgetExceeded:
            blocked.append(1)
    import guardrails
    threads = [threading.Thread(target=go) for _ in range(40)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(passed) == 5 and len(blocked) == 35 and b.requests == 5


def test_a_failed_live_call_falls_back_to_an_older_cache_entry(tmp_path, monkeypatch):
    import os
    from sources import common
    monkeypatch.setenv("LEASELENS_OFFLINE", "0")
    monkeypatch.delenv("LEASELENS_NO_CACHE", raising=False)
    monkeypatch.setattr(common, "CACHE_DIR", tmp_path)
    path = common._cache_file("core", "places", "k")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"v": common.CACHE_VERSION, "dataset": {"name": "x"}, "data": {"results": [1, 2]}}))
    old = time.time() - 20 * 24 * 3600                              # older than the 7-day freshness window
    os.utime(path, (old, old))

    def boom():
        raise RuntimeError("all Overpass servers failed")
    res = common.run_source("core", "places", "k", boom, {"name": "x"}, count=lambda d: len(d["results"]), fields=lambda d: [])
    assert res.ok and res.origin == "cache" and res.count == 2 and "all Overpass servers failed" in res.live_error
    os.utime(path, (time.time() - 90 * 24 * 3600,) * 2)               # beyond the stale limit: no fallback
    res = common.run_source("core", "places", "k", boom, {"name": "x"}, count=lambda d: 0, fields=lambda d: [])
    assert not res.ok


def test_maps_remeasure_themselves_when_their_tab_is_opened(geo_for):
    g = geo_for("360 State")
    for m in (sections.build_map(g["lat"], g["lon"], None), sections.build_parcel_map(g["lat"], g["lon"], [])):
        html = m.get_root().render()
        assert "setInterval" in html and f"{m.get_name()}.invalidateSize()" in html and "getContainer()" in html


def test_js_safe_neutralises_characters_that_break_map_scripts():
    assert sections.js_safe("Garden Street Park`") == "Garden Street Park'"
    assert "${" not in sections.js_safe("a ${b}") and "\\" not in sections.js_safe("a\\b")
    assert "<" not in sections.js_safe("<script>alert(1)</script>")


@pytest.mark.parametrize("prefix", ["360 State", "100 York", "365 Orchard"])
def test_every_demo_map_script_is_valid_javascript(prefix, geo_for, tmp_path):
    """Regression: OpenStreetMap has a park named 'Garden Street Park`' (stray backtick). It made the map script invalid, so
    two of the three address tabs showed a blank map."""
    import re
    import shutil
    import subprocess
    from sources.core import places as pl
    g = geo_for(prefix)
    html = sections.build_map(g["lat"], g["lon"], pl.find_places(g["lat"], g["lon"])).get_root().render()
    big = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    assert "Park`" not in big
    assert big.count("`") % 2 == 0                                         # template literals are balanced
    if shutil.which("node"):
        f = tmp_path / "map.js"
        f.write_text(big)
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[:300]


# ------------------------------------------------------------------ the page: live-mode run and progressive results
def _live_app(monkeypatch, addresses=None):
    from app_data import DEMO_ADDRESSES
    from tests.conftest import make_app
    monkeypatch.setenv("PORTKEY_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MODEL", "gpt-6-luna")
    monkeypatch.setattr("sources.common.load_dotenv", lambda *a, **k: False)
    rank = {"ranking": [{"address": a, "rank": i + 1, "headline": "ok", "strengths": [], "trade_offs": []}
                        for i, a in enumerate(DEMO_ADDRESSES)], "overall": "ok", "key_tradeoffs": "ok"}

    def fn(messages, info: AgentInfo):
        props = set(info.output_tools[0].parameters_json_schema.get("properties", {}))
        out = BLOCK if "verdict" in props else LANDLORD if "plain_english" in props else EMAIL if "subject" in props else rank
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])
    monkeypatch.setattr(team, "make_model", lambda: FunctionModel(fn))
    return make_app("results", addresses=addresses, demo=False)


def test_live_run_updates_the_cards_with_the_verdict(monkeypatch):
    at = _live_app(monkeypatch)
    at.run()
    assert not at.exception
    button = next(b for b in at.button if b.label == "Get the AI verdict")
    button.click()
    at.run()
    assert not at.exception and not at.error
    from tests.conftest import page_html
    assert "Verdict from the AI team." in page_html(at)                  # the cards now carry the AI team's verdict
    handle = next(iter(at.session_state["ai_handles"].values()))
    assert handle.done and handle.snapshot_json()["recommendation"] is not None


def test_single_address_live_run_skips_the_coordinator(monkeypatch):
    at = _live_app(monkeypatch, addresses=["360 State Street, New Haven, CT"])
    at.run()
    next(b for b in at.button if b.label == "Get the AI verdict").click()
    at.run()
    assert not at.exception
    handle = next(iter(at.session_state["ai_handles"].values()))
    snap = handle.snapshot_json()
    assert snap["done"] and snap["single_address"] and snap["recommendation"] is None and snap["run"]["requests"] == 3
