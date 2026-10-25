"""One source of truth for cost: tokenomics.cost_summary(). tokenomics.md, report.html and slides.html must print identical strings."""
import re

import build_report
import build_slides
import report_data as rd
import tokenomics


def _stand_in_rows():
    """Rows written by the offline stand-in model (tiny token counts); a running app may add real rows at any time."""
    return [r for r in tokenomics.load_rows() if r.get("input_tokens", 0) < 2000 and r.get("agent")]


def test_cost_strings_identical_in_markdown_report_and_slides():
    d = rd.load()
    cs = tokenomics.cost_summary()
    assert d["costs"]["text"] == cs["text"]
    md = tokenomics.build_report(cs["rows"], None)
    report = build_report.build(d)
    slides = "".join(build_slides.build(d))
    t = cs["text"]
    for key in ("one", "three", "month", "total", "scale_1", "scale_100", "scale_10000"):
        assert t[key] in md, key
        assert t[key] in report, key
    for key in ("one", "three", "month", "total"):
        assert key == "one" or t[key] in slides, key           # slides show the 3-address, per-month and total figures
    assert str(cs["calls_averaged"]) in md and str(cs["calls_logged"]) in md
    assert f"{cs['calls_averaged']} agent calls averaged; {cs['calls_logged']} calls logged in total" in report
    assert not _stand_in_rows()                                 # building them never writes stand-in runs to the real usage log


def test_no_hard_coded_dollar_amounts_in_builders():
    for f in ("build_report.py", "build_slides.py"):
        src = (rd.ROOT / f).read_text()
        assert not re.findall(r"\$\d+\.\d+", src), f
