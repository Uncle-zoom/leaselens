"""The three Under-the-hood demos and the tab itself (offline, stand-in model, no key)."""
from pathlib import Path

import under_the_hood as uth


def test_injection_demo_is_flagged_and_the_verdict_is_unchanged():
    d = uth.injection_demo()
    assert d["flagged"] and "10/10" not in d["filtered_report"] and "ignore" not in d["filtered_report"].lower()
    assert "Overflowing trash can" in d["filtered_report"]                       # the harmless part survives as data
    assert d["with_filter"]["prompt_contains_instruction"] is False
    assert d["with_filter"]["verdict"] == d["baseline_verdict"]
    assert d["without_filter"]["prompt_contains_instruction"] is True            # the stand-in model DID see it without the filter
    assert d["without_filter"]["verdict"] == "hidden gem" != d["baseline_verdict"]


def test_fact_check_demo_removes_exactly_the_planted_sentences():
    d = uth.fact_check_demo()
    assert uth.PLANTED_NUMBER_SENTENCE in d["before"]["summary"]
    assert "47" not in d["after"]["summary"] and not any("Zenith" in r for r in d["after"]["reasons"])
    unsupported = {u for r in d["removed"] for u in r["unsupported"]}
    assert "47" in unsupported and ({"Zenith", "Holdings"} & unsupported)
    assert d["after"]["reasons"][0] == d["before"]["reasons"][0]                 # true sentences are untouched


def test_cost_cap_demo_stops_the_run_with_a_friendly_message():
    d = uth.cost_cap_demo(max_requests=2)
    assert [s["result"] for s in d["steps"]] == ["analysed", "analysed", "stopped before calling the model"]
    assert d["requests_used"] == 2 and "request limit reached" in d["message"] and "Nothing more was sent" in d["message"]


def test_demos_do_not_write_to_the_real_usage_log():
    from usage_log import LOG
    before = LOG.read_text() if LOG.exists() else ""
    uth.injection_demo(); uth.cost_cap_demo()
    assert (LOG.read_text() if LOG.exists() else "") == before


def test_under_the_hood_view_renders():
    from tests.conftest import make_app, page_html
    at = make_app("hood")
    at.run()
    assert not at.exception and not at.error
    text = page_html(at)
    assert "Prompt injection" in text and "Fact check" in text and "Cost cap" in text
    assert any("request limit reached" in w.value for w in at.warning)
