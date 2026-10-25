"""The page flow: landing -> results cards -> address view -> compare (offline, Demo mode)."""
import re

import pytest

from tests.conftest import DEMO3, make_app, page_html


# ------------------------------------------------------------------ landing
def test_landing_has_one_labelled_search_field_and_a_single_primary_button():
    at = make_app("landing", addresses=[])
    at.run()
    assert not at.exception and not at.error
    html = page_html(at)
    assert "Know the block and the landlord before you sign." in html
    assert [t.label for t in at.text_input] == ["Apartment address"]                  # every input has a real label
    names = [b.label for b in at.button]
    assert "Check addresses" in names and "Add another address" in names
    assert [b.label for b in at.button if b.key and b.key.startswith("chip_")] == ["360 State Street", "100 York Street", "365 Orchard Street"]
    assert not at.sidebar.slider                                                        # priorities live in "Personalize", not the sidebar
    assert [t.label for t in at.sidebar.toggle] == ["Demo mode (offline sample data)"]


def test_example_chip_fills_the_field():
    at = make_app("landing", addresses=[])
    at.run()
    next(b for b in at.button if b.key == "chip_1").click()
    at.run()
    assert at.text_input[0].value == DEMO3[1]


def test_add_another_address_up_to_three_fields():
    at = make_app("landing", addresses=[])
    at.run()
    for expected in (["Apartment address", "Second address"], ["Apartment address", "Second address", "Third address"]):
        next(b for b in at.button if b.label == "Add another address").click()
        at.run()
        assert [t.label for t in at.text_input] == expected
    assert next(b for b in at.button if b.label == "Add another address").disabled


def test_check_addresses_with_nothing_typed_explains_what_to_do():
    at = make_app("landing", addresses=[])
    at.run()
    next(b for b in at.button if b.label == "Check addresses").click()
    at.run()
    assert not at.exception and any("Type an address first" in e.value for e in at.error)


def test_check_addresses_moves_to_results():
    at = make_app("landing", addresses=[])
    at.run()
    at.text_input[0].set_value(DEMO3[0])
    next(b for b in at.button if b.label == "Check addresses").click()
    at.run()
    assert not at.exception and at.session_state["view"] == "results" and at.session_state["addresses"] == [DEMO3[0]]


# ------------------------------------------------------------------ results
def test_results_show_one_card_per_address_with_verdict_score_and_four_facts():
    at = make_app("results")
    at.run()
    assert not at.exception and not at.error
    html = page_html(at)
    assert html.count('class="ll-card"') == 3
    for title in ("360 State Street", "100 York Street", "365 Orchard Street"):
        assert f'aria-label="{title}"' in html
    assert len(re.findall(r"out of 100", html)) >= 3 and html.count("ll-pill") >= 3
    assert "Grocery" in html and "Night:" in html and "Owner holds 88 other parcels" in html
    assert len([b for b in at.button if b.label == "See details"]) == 3
    assert any(b.label == "Compare side by side" for b in at.button)


def test_every_status_has_text_and_an_icon_not_just_colour():
    at = make_app("results")
    at.run()
    html = page_html(at)
    for pill in re.findall(r'<span class="ll-pill[^>]*>(.*?)</span></span>', html):
        assert "<svg" in pill and re.search(r"(Great fit|Good|Think twice|Checking)", pill)


def test_demo_mode_unknown_address_says_demo_only_has_the_samples():
    at = make_app("results", addresses=[DEMO3[0], "101 Dwight St, New Haven, CT"])
    at.run()
    assert not at.exception
    assert any("Demo mode only has the 3 sample addresses; switch it off to look this up live." in w.value and "101 Dwight St" in w.value
               for w in at.warning)
    assert page_html(at).count('class="ll-card"') == 1 and "None" not in page_html(at)


def test_live_mode_unknown_address_shows_a_message_not_a_crash():
    at = make_app("results", addresses=["1 Nowhere Lane, Atlantis, ZZ"], demo=False)
    at.run()
    assert not at.exception
    assert "We could not find this address" in page_html(at)


def test_changing_priorities_changes_the_scores():
    at = make_app("results", addresses=[DEMO3[0]])
    at.run()
    s0 = int(re.search(r"Overall score (\d+) out of 100", page_html(at)).group(1))
    next(s for s in at.slider if s.key == "w_gym").set_value(3)           # a gym must now be within 3 minutes (the nearest is 5)
    at.run()
    assert not at.exception
    assert int(re.search(r"Overall score (\d+) out of 100", page_html(at)).group(1)) < s0


# ------------------------------------------------------------------ address view
def test_address_view_is_a_set_of_questions_with_one_sentence_answers():
    at = make_app("detail", detail=0)
    at.run()
    assert not at.exception and not at.error
    html = page_html(at)
    for q in ("What&#x27;s within a short walk?", "Will it be noisy?", "What do neighbors report?", "Who owns this building?", "What should I ask?"):
        assert q in html
    assert "Street-level reports, not housing complaints." in html
    assert "ANSONIA STATE STREET LLC" in html                              # the owner answer
    assert "Map summary (text version)" in html                            # text alternative next to the map
    labels = [e.label for e in at.expander]
    assert {"See walking times", "See noise sources", "See what was reported", "See the owner, registry record and other parcels",
            "Draft email to the leasing agent", "Ask about this apartment"} <= set(labels)


def test_address_view_shows_the_ai_verdict_questions_and_a_copy_email_button():
    at = make_app("detail", detail=2)
    at.run()
    html = page_html(at)
    assert "Think twice" in html and "Three questions to ask the landlord" in html
    assert any(t.label == "Edit before you send it yourself" and t.value.startswith("Subject:") for t in at.text_area)
    assert any("Copy email" in f.proto.srcdoc for f in at.get("iframe"))
    assert any("Draft only" in c.value or "never sends anything" in c.value for c in at.caption)


# ------------------------------------------------------------------ compare
def test_compare_marks_exactly_one_winner_per_scored_row_with_icon_and_text():
    at = make_app("compare")
    at.run()
    assert not at.exception and not at.error
    html = page_html(at)
    rows = re.findall(r"<tr><th scope=\"row\">(.*?)</th>(.*?)</tr>", html, re.S)
    scored = [r for r in rows if r[0] in ("Overall", "Groceries", "Gym", "Transit", "Quiet at night")]
    assert len(scored) == 5
    for name, cells in scored:
        assert cells.count("Best</span>") == 1 and cells.count("<svg") == 1, name
    for name, cells in rows:
        if name.startswith(("Street-level", "Other parcels")):
            assert "Best" not in cells
    assert "Best overall for your priorities: 360 State Street." in html
