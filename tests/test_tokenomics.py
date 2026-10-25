import json

import pytest

import tokenomics as tk


def row(agent, inp, cached, out, cost, **extra):
    return {"agent": agent, "input_tokens": inp, "cached_tokens": cached, "output_tokens": out, "cost_usd": cost, "seconds": 1.0, **extra}


ROWS = [row("block_analyst", 3000, 1000, 600, 0.0006), row("block_analyst", 3200, 3000, 400, 0.0004),
        row("landlord_analyst", 4000, 0, 800, 0.0008), row("negotiator", 3500, 500, 500, 0.0005),
        row("coordinator", 9000, 3000, 1000, 0.0012), row("chat", 2000, 0, 200, 0.0003),
        row("block_analyst", 3000, 0, 600, 0.0009, cache="off")]          # cache-broken rows are excluded from "normal"


def test_agent_rows_filters_cache_runs_and_non_agent_rows():
    rows = ROWS + [{"purpose": "data_check ping", "input_tokens": 13, "cached_tokens": 0, "output_tokens": 5, "cost_usd": 0}]
    assert len(tk.agent_rows(rows, "on")) == 6 and len(tk.agent_rows(rows, "off")) == 1 and len(tk.agent_rows(rows, "all")) == 7


def test_hit_rate_and_usage_table():
    rows = tk.agent_rows(ROWS, "on")
    assert tk.hit_rate(rows) == pytest.approx((1000 + 3000 + 500 + 3000) / (3000 + 3200 + 4000 + 3500 + 9000 + 2000))
    table = {t["agent"]: t for t in tk.usage_table(rows)}
    assert table["block_analyst"]["calls"] == 2 and table["block_analyst"]["input_tokens"] == 6200
    assert table["block_analyst"]["cache_hit_rate"] == pytest.approx(4000 / 6200, abs=1e-3)
    assert table["ALL"]["calls"] == 6 and table["ALL"]["cost_usd"] == pytest.approx(0.0006 + 0.0004 + 0.0008 + 0.0005 + 0.0012 + 0.0003)


def test_per_call_averages():
    a = tk.per_call_averages(tk.agent_rows(ROWS, "on"))
    assert a["block_analyst"]["n"] == 2 and a["block_analyst"]["cost_usd"] == pytest.approx(0.0005)
    assert a["block_analyst"]["input_tokens"] == pytest.approx(3100)


def test_single_address_and_comparison_runs():
    a = tk.per_call_averages(tk.agent_rows(ROWS, "on"))
    one = tk.single_address_run(a)
    assert one["calls"] == 3 and one["cost_usd"] == pytest.approx(0.0005 + 0.0008 + 0.0005)
    three = tk.comparison_run(a, 3)
    assert three["calls"] == 10 and three["cost_usd"] == pytest.approx(3 * one["cost_usd"] + 0.0012)


def test_monthly_cost_uses_stated_assumptions():
    a = tk.per_call_averages(tk.agent_rows(ROWS, "on"))
    m = tk.monthly_per_user(a, addresses=5, group=3, chat_turns=3, emails=1)
    assert m["coordinator_runs"] == 2                                    # 5 addresses in groups of 3 -> 2 comparisons
    expect = 5 * 0.0005 + 5 * 0.0008 + 10 * 0.0005 + 2 * 0.0012 + 15 * 0.0003
    assert m["cost_usd"] == pytest.approx(expect) and m["calls"] == 5 + 5 + 10 + 2 + 15


def test_scaling_is_linear():
    assert tk.at_scale(0.02, 100) == pytest.approx(2.0) and tk.at_scale(0.02, 10_000) == pytest.approx(200.0)


def test_experiment_summary_and_quality_comparison():
    rows = [row("block_analyst", 1000, 0, 100, 0.001, experiment="e1", variant="busted", cache="off"),
            row("block_analyst", 1000, 800, 100, 0.0004, experiment="e1", variant="cached"),
            row("block_analyst", 1000, 0, 100, 0.001, experiment="e1", variant="cached_warmup")]
    s = tk.experiment_summary(rows)
    assert s["cached"]["hit_rate"] == 0.8 and s["busted"]["hit_rate"] == 0 and s["busted"]["cost_usd"] > s["cached"]["cost_usd"]
    base = {"errors": [], "recommendation_removed": 0, "ranking": [[1, "A, x"], [2, "B, x"]],
            "addresses": {"A": {"verdict": "fine", "removed": 0}, "B": {"verdict": "fine", "removed": 0}}}
    other = json.loads(json.dumps(base)); other["addresses"]["B"]["verdict"] = "think twice"
    notes = tk.quality_comparison({"cached_warmup": base, "cached": base, "busted": other})
    assert "2 of 2" in notes[0] and "1 of 2" in notes[1]


def test_report_contains_every_required_section():
    rows = tk.agent_rows(ROWS, "on") + [row("block_analyst", 1000, 800, 100, 0.0004, experiment="e1", variant="cached"),
                                        row("block_analyst", 1000, 0, 100, 0.001, experiment="e1", variant="busted", cache="off")]
    md = tk.build_report(rows, None)
    for needle in ("Measured per call", "Cost per run", "Cost per user per month", "Assumption", "10,000", "caching on vs. caching broken"):
        assert needle in md
    assert tk.build_report([], None).startswith("# LeaseLens tokenomics") and "Not enough usage data" in tk.build_report([], None)
