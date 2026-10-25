"""Design system and accessibility (WCAG 2.2 AA) checks, all offline."""
import re
from pathlib import Path

import pytest

import styles
import summary
import ui_html
from tests import _toml_compat
from tests.conftest import make_app, page_html

ROOT = Path(__file__).resolve().parent.parent


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def luminance(h):
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(v / 255) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# ------------------------------------------------------------------ colour contrast
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("label,fg,bg,minimum", styles.CONTRAST_PAIRS, ids=[p[0] for p in styles.CONTRAST_PAIRS])
def test_every_colour_pair_meets_wcag_aa(theme, label, fg, bg, minimum):
    t = styles.TOKENS[theme]
    ratio = contrast(t[fg], t[bg])
    assert ratio >= minimum, f"{theme}: {label}: {t[fg]} on {t[bg]} is {ratio:.2f}:1, needs {minimum}:1"


def test_contrast_function_matches_known_values():
    assert round(contrast("#000000", "#FFFFFF"), 1) == 21.0
    assert round(contrast("#767676", "#FFFFFF"), 2) == 4.54          # the classic AA boundary grey
    assert contrast("#248A3D", "#FFFFFF") < 4.5                      # why the brief's green was darkened


def test_the_brief_palette_is_used_where_it_passes():
    L = styles.TOKENS["light"]
    assert (L["bg"], L["card"], L["text"], L["text2"], L["accent"], L["orange"], L["red"]) == \
        ("#F5F5F7", "#FFFFFF", "#1D1D1F", "#6E6E73", "#0071E3", "#B25000", "#D70015")
    D = styles.TOKENS["dark"]
    assert (D["bg"], D["card"]) == ("#000000", "#1C1C1E")


def test_streamlit_theme_config_matches_the_tokens():
    cfg = _toml_compat.loads((ROOT / ".streamlit" / "config.toml").read_text())
    for theme in ("light", "dark"):
        c, t = cfg["theme"][theme], styles.TOKENS[theme]
        assert (c["backgroundColor"].lower(), c["secondaryBackgroundColor"].lower(), c["textColor"].lower()) == \
            (t["bg"].lower(), t["card"].lower(), t["text"].lower())
    assert cfg["theme"]["light"]["primaryColor"].lower() == styles.TOKENS["light"]["accent"].lower()


# ------------------------------------------------------------------ the CSS
CSS = styles.css()


def test_visible_focus_ring_for_keyboard_users():
    assert ":focus-visible" in CSS and re.search(r"outline:\s*3px solid var\(--focus\)", CSS)


def test_motion_is_subtle_and_switched_off_for_reduced_motion():
    durations = [float(x) for x in re.findall(r"ll(?:fade)\s+(\.\d+)s", CSS)]
    assert durations and all(0.15 <= d <= 0.2 for d in durations)            # 150-200 ms fade/slide
    assert "prefers-reduced-motion: reduce" in CSS and re.search(r"animation:\s*none !important", CSS)


def test_dark_mode_follows_the_system_setting():
    assert "prefers-color-scheme: dark" in CSS and styles.TOKENS["dark"]["card"] in CSS


def test_type_is_inter_with_system_fallbacks_and_readable_body_text():
    assert "family=Inter" in CSS and "-apple-system" in CSS and "SF Pro" in CSS and "Segoe UI" in CSS
    assert re.search(r"font-size:\s*1\.0625rem", CSS) and re.search(r"line-height:\s*1\.5", CSS)       # 17px body, 1.5 line height
    assert "tabular-nums" in CSS and "letter-spacing:-0.02em" in CSS


def test_layout_survives_narrow_screens_and_zoom():
    assert "max-width: 640px" in CSS and re.search(r"flex-wrap:\s*wrap", CSS)
    assert "overflow-x:auto" in CSS                                              # wide tables scroll instead of being cut off
    assert not re.search(r"(?<!max-)(?<!min-)width:\s*\d{4,}px", CSS)                              # no fixed desktop-only widths


def test_cards_use_the_specified_radius_border_and_soft_shadow():
    assert "--radius:16px" in CSS and "var(--hairline)" in CSS and "rgba(0,0,0,0.06)" in CSS and "box-shadow" in CSS


def test_skip_link_and_screen_reader_helpers_exist():
    assert ".ll-skip:focus" in CSS and ".ll-sr" in CSS


# ------------------------------------------------------------------ HTML snippets
def test_step_indicator_announces_progress_politely():
    h = ui_html.steps_html([True, False, False, False])
    assert 'role="status"' in h and 'aria-live="polite"' in h and 'aria-current="step"' in h
    assert "Step 2 of 4: Mapping the block." in h and "(finished)" in h
    assert "All done. Results are ready." in ui_html.steps_html([True, True, True, True])
    assert [s for s in ui_html.STEPS] == ["Finding the address", "Mapping the block", "Checking public records", "Done"]


def test_icons_are_decorative_and_every_status_carries_words():
    assert 'aria-hidden="true"' in ui_html.icon("check") and 'focusable="false"' in ui_html.icon("check")
    for key, (label, tone, icon) in summary.VERDICT_UI.items():
        pill = ui_html.pill(label, tone, icon)
        assert label in pill and "<svg" in pill                              # text + icon (+ colour)
    assert {v[0] for v in summary.VERDICT_UI.values()} == {"Great fit", "Good", "Think twice"}


def test_tables_have_captions_and_header_scopes():
    h = ui_html.table_html(["A", "B"], [[1, 2]], "Caption here", {1})
    assert "<caption>Caption here</caption>" in h and h.count('scope="col"') == 2
    c = ui_html.compare_html(["X", "Y"], [{"name": "Overall", "values": [1, 2], "winner": 1}])
    assert 'scope="row"' in c and "Best" in c and "<svg" in c and "<caption>" in c


def test_data_is_escaped_in_every_snippet():
    evil = '<img src=x onerror=alert(1)>'
    s = summary.card_summary({"Overall": 50, "Quiet": 50}, [], 1, True, True, None)
    assert "<img" not in ui_html.card_html(evil, s) and "<img" not in ui_html.table_html([evil], [[evil]], evil)


def test_card_has_an_accessible_name_and_a_labelled_score():
    s = summary.card_summary({"Overall": 71.6, "Quiet": 80}, [], 0, True, True, "fine")
    h = ui_html.card_html("360 State Street", s)
    assert '<article class="ll-card" aria-label="360 State Street">' in h and 'aria-label="Overall score 72 out of 100"' in h
    assert s["label"] == "Good" and s["tone"] == "good"


# ------------------------------------------------------------------ the page
@pytest.mark.parametrize("view", ["landing", "results", "detail", "compare", "hood"])
def test_every_view_has_exactly_one_h1_and_no_unlabelled_controls(view):
    at = make_app(view, addresses=[] if view == "landing" else None)
    at.run()
    assert not at.exception and not at.error
    h1 = len(re.findall(r"<h1[ >]", page_html(at))) + len(at.title)
    assert h1 == 1, view
    assert all(t.label for t in at.text_input) and all(b.label for b in at.button) and all(s.label for s in at.slider)
    assert all(t.label for t in at.text_area) and all(t.label for t in at.toggle)


def test_the_map_has_a_text_alternative_next_to_it():
    at = make_app("detail", detail=0)
    at.run()
    html = page_html(at)
    assert "Map summary (text version)" in html and "Noise sources within 800 m" in html
    assert any("map_" in f.proto.srcdoc or "leaflet" in f.proto.srcdoc.lower() for f in at.get("iframe"))


def test_page_language_is_set_for_screen_readers():
    at = make_app("landing", addresses=[])
    at.run()
    assert any("documentElement.lang = 'en'" in f.proto.srcdoc for f in at.get("iframe"))


def test_headings_on_the_address_view_are_questions():
    at = make_app("detail", detail=1)
    at.run()
    qs = re.findall(r"<h2[^>]*>(.*?)</h2>", page_html(at))
    assert [q.replace("&#x27;", "'") for q in qs] == ["What's within a short walk?", "Will it be noisy?", "What do neighbors report?",
                                                         "Who owns this building?", "What should I ask?"]
