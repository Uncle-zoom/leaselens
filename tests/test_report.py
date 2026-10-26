"""The report and slides: built from real files, self-contained, and the author's three text files inserted unchanged."""
import re

import build_report
import build_slides
import report_data as rd
import verbatim


def _report():
    return build_report.build(rd.load())


def test_content_files_inserted_word_for_word():
    html = _report()
    for name in ("motivation.md", "impact_testers.md", "reflection.md"):
        text = rd.content_file(name)
        assert verbatim.plain(text) in verbatim.visible(html), name


def test_report_is_self_contained():
    html = _report()
    assert not re.findall(r'<(?:img|script|link)[^>]+(?:src|href)="https?://', html)
    assert html.count("data:image/png;base64,") >= 10
    assert "TO FILL" not in html and "github.com/Uncle-zoom/leaselens" in html


def test_no_placeholder_notes_left_and_note_style_is_small_grey():
    html = _report()
    assert "TO ADD" not in html and "TO FILL" not in html and "Not measured: time saved" not in html
    css = re.search(r"\.note\s*\{[^}]*\}", html).group(0)
    assert "background" not in css and "#767676" in css


def test_slides_are_at_most_ten_and_offline():
    secs = build_slides.build(rd.load())
    assert 1 <= len(secs) <= 10
    page = "".join(secs)
    assert not re.findall(r'<(?:img|script|link)[^>]+(?:src|href)="https?://', page)


def test_slide_tester_lines_are_in_the_source_file():
    lines = build_slides.tester_lines()
    assert len(lines) == 3
    src = rd.content_file("impact_testers.md")
    assert all(x in src for x in lines)


def test_numbers_come_from_the_repo_files():
    d = rd.load()
    html = _report()
    assert f"{d['own']['portfolio_total']} parcels" in html
    assert f"{d['own']['blake']['companies_total']} companies" in html
    assert f"{d['speed']['total_now']:.1f} s" in html


QUOTE = "I wish I had a tool like this before I moved in, I will be using this for my second year apartment hunt."


def test_four_testers_and_the_exact_quote_are_everywhere_they_should_be():
    src = rd.content_file("impact_testers.md")
    assert src.count(QUOTE) == 1 and "Four people tried" in src and "Both agreed to be quoted without their names." in src
    assert "Two people" not in src and "Both testers" not in src and "No timing was measured." in src
    assert not re.search(r"\b\d{3,4} Chapel", src)                               # no street number for their building
    assert build_slides.exact_quote() == QUOTE
    page = "".join(build_slides.build(rd.load()))
    assert page.index(QUOTE) < page.index("Called LeaseLens a great tool")        # the exact quote is the first card
    assert "a renter in the building it was tested on" in page and "Four testers; one exact quote, others paraphrased by me; no timing measured." in page
    report = _report()
    assert "Four testers (section 7)" in report and "Two testers" not in report
    assert "TO FILL" not in report and "TO ADD" not in report and "TO FILL" not in page and "TO ADD" not in page
