import summary


def test_verdict_labels_follow_the_brief():
    assert summary.VERDICT_UI["hidden gem"][0] == "Great fit" and summary.VERDICT_UI["fine"][0] == "Good" and summary.VERDICT_UI["think twice"][0] == "Think twice"


def test_quick_read_verdict_from_score():
    assert [summary.verdict_from_score(x) for x in (90, 70, 69.9, 45, 10, None)] == ["hidden gem", "hidden gem", "fine", "fine", "think twice", None]


def test_quiet_phrases_in_plain_words():
    assert summary.quiet_phrase(85) == "Night: calm" and summary.quiet_phrase(50) == "Night: lively"
    assert summary.quiet_phrase(8) == "Night: busy"


ROWS = [{"category": "grocery", "walk_min": 2.2, "nearest": "J & J"}, {"category": "bus_stop", "walk_min": 6.0, "nearest": "x"},
        {"category": "train_station", "walk_min": 9.5, "nearest": "y"}]


def test_card_has_four_plain_language_facts():
    s = summary.card_summary({"Overall": 71.6, "Quiet": 8}, ROWS, 88, True, True, "think twice")
    assert [t for _, t in s["facts"]] == ["Grocery 2.2 min walk", "Night: busy", "Bus 6 min walk", "Owner holds 88 other parcels"]
    assert s["label"] == "Think twice" and s["score"] == 72 and s["source"] == "AI team"
    assert s["badge"] == "Think twice · noisy at night"


def test_card_facts_for_missing_or_unavailable_data():
    s = summary.card_summary(None, None, None, True, False, None)
    assert s["label"] == "Checking…" and all("…" in t for _, t in s["facts"])
    nonct = summary.card_summary({"Overall": 50, "Quiet": 50}, ROWS, None, False, True, None)
    assert nonct["facts"][-1][1] == "Owner records: not available in this state yet" and nonct["source"].startswith("quick read")
    assert summary.card_summary({"Overall": 50, "Quiet": 50}, ROWS, 0, True, True, None)["facts"][-1][1] == "Owner holds no other parcels"
    assert summary.card_summary({"Overall": 50, "Quiet": 50}, ROWS, 1, True, True, None)["facts"][-1][1] == "Owner holds 1 other parcel"


def test_transit_fact_picks_the_nearest_of_bus_or_train():
    assert summary.transit_fact(ROWS) == ("Bus 6 min walk", 6.0)
    assert summary.transit_fact([{"category": "bus_stop", "walk_min": None}])[0] == "Transit: none within 800 m"


def test_each_answer_is_one_plain_sentence_group_not_a_table():
    walk = [{"category": "grocery", "walk_min": 2.2, "nearest": "J & J"}, {"category": "gym", "walk_min": None, "nearest": None}] + ROWS[1:]
    noise = [{"count": 12, "label": "Bars"}, {"count": 0, "label": "Pubs"}, {"count": 3, "label": "Nightclubs"}]
    a = summary.answers("x", {"Quiet": 8}, walk, noise, {"total": 87, "rows": [{"request_type": "Snow"}]}, None, ["Who manages it?"], True)
    assert "J & J" in a["walk"] and "no gym within 800 m" in a["walk"] and a["walk"].endswith(".")
    assert a["noise"] == "Expect it to be busy at night: 12 bars, 3 nightclubs within 800 m."
    assert "87 street-level reports" in a["street"] and "not the building" in a["street"] and a["ask"] == "Who manages it?"
    assert summary.answers("x", None, None, None, None, None, None, False)["owner"] == "Landlord data is not available in this state yet."


# ------------------------------------------------------------------ wording for short walks
import pytest

from wording import walk_phrase


@pytest.mark.parametrize("minutes,metres,expected", [(0.1, 8, "next door"), (0.6, 49, "next door"), (0.6, 50, "under 1 min walk"),
                                                      (0.9, None, "under 1 min walk"), (1.0, 83, "1 min walk"), (2.2, 180, "2.2 min walk"),
                                                      (None, None, "none within 800 m")])
def test_walk_phrase(minutes, metres, expected):
    assert walk_phrase(minutes, metres) == expected


def test_cards_say_next_door_or_under_one_minute_instead_of_zero_point_something():
    rows = [{"category": "grocery", "walk_min": 0.1, "walk_m": 8, "nearest": "Elm City Market"},
            {"category": "bus_stop", "walk_min": 0.7, "walk_m": 107, "nearest": "x"}]
    s = summary.card_summary({"Overall": 72, "Quiet": 8}, rows, 0, True, True, "think twice")
    assert [t for _, t in s["facts"]][0] == "Grocery next door" and [t for _, t in s["facts"]][2] == "Bus under 1 min walk"
    a = summary.answers("x", {"Quiet": 8}, rows + [{"category": "gym", "walk_min": 0.5, "walk_m": 100, "nearest": "G"}], [], None, None, None, True)
    assert "Elm City Market, next door" in a["walk"] and "a gym is under 1 minute away" in a["walk"] and "0.1" not in a["walk"]


# ------------------------------------------------------------------ the verdict badge shows its main reason
SC = {"Overall": 72, "Quiet": 8, "Gym": 83, "Transit": 96, "Groceries": 100}


def test_main_reason_names_the_weakest_area_in_plain_words():
    assert summary.main_reason("think twice", SC, []) == "noisy at night"
    assert summary.main_reason("think twice", {**SC, "Quiet": 55, "Gym": 0}, [{"category": "gym", "walk_min": None}]) == "no gym nearby"
    assert summary.main_reason("fine", {**SC, "Quiet": 55, "Gym": 0}, [{"category": "gym", "walk_min": 20}]) == "gym farther than you like"
    assert summary.main_reason("think twice", {**SC, "Quiet": 50}, []) == "lively at night"
    assert summary.main_reason("think twice", {k: 90 for k in SC}, []) == "a few things to check"
    assert summary.main_reason("hidden gem", SC, []) == "close to what you need"


def test_a_line_explains_when_the_verdict_and_the_score_disagree():
    note = summary.disagreement_note("think twice", 72, "noisy at night")
    assert note == summary.DISAGREE_NOTE and note.startswith("Why a verdict and a score can differ") and len(note) < 220
    assert summary.disagreement_note("hidden gem", 40, "") == note                                          # either direction
    assert summary.disagreement_note("hidden gem", 80, "") == "" and summary.disagreement_note("fine", 60, "") == ""     # they agree: no line
    assert summary.disagreement_note(None, 72, "noisy at night") == ""


def test_every_demo_card_shows_the_reason_and_no_card_is_left_checking():
    from tests.conftest import make_app, page_html
    import re
    at = make_app("results")
    at.run()
    h = page_html(at)
    assert "checking" not in h.lower()
    pills = re.findall(r"ll-pill[^>]*>.*?<span>(.*?)</span></span>", h)
    assert pills == ["Think twice · noisy at night", "Think twice · noisy at night", "Think twice · no gym nearby"]
    assert h.count("Why a verdict and a score can differ") == 1                # said once above the cards, not on each of the three
    assert 'role="note"' in h and h.index("Why a verdict and a score") < h.index('class="ll-card"')
