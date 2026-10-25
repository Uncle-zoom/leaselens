"""Capture the four review screenshots of the running app in Demo mode (landing, results cards, address view with map, compare).

    python scripts/capture_screens.py http://localhost:8501 output/screenshots/design_before_after after [dark]

Needs Playwright (dev only, not in requirements.txt) and Google Chrome: pip install playwright. No browser download is needed.
"""
import sys

from playwright.sync_api import sync_playwright

URL, OUT, PREFIX = sys.argv[1], sys.argv[2], sys.argv[3]
DARK = len(sys.argv) > 4 and sys.argv[4] == "dark"
EX = ["360 State Street, New Haven, CT", "100 York Street, New Haven, CT", "365 Orchard Street, New Haven, CT"]


def settle(pg, ms=1500):
    pg.wait_for_timeout(ms)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 1280, "height": 1000}, color_scheme="dark" if DARK else "light")
    pg = ctx.new_page()
    pg.goto(URL)
    pg.get_by_role("button", name="Check addresses").wait_for(timeout=30000)
    settle(pg)
    pg.screenshot(path=f"{OUT}/{PREFIX}_1_landing.png")
    pg.get_by_role("button", name="360 State Street").first.click(); settle(pg)
    for label, addr in (("Second address", EX[1]), ("Third address", EX[2])):
        pg.get_by_role("button", name="Add another address").click(); settle(pg)
        pg.get_by_label(label).fill(addr); pg.get_by_label(label).press("Tab"); settle(pg, 600)
    pg.get_by_role("button", name="Check addresses").click()
    pg.get_by_role("button", name="See details").first.wait_for(timeout=60000)
    pg.wait_for_timeout(9000)
    pg.screenshot(path=f"{OUT}/{PREFIX}_2_results_cards.png")
    pg.get_by_role("button", name="See details").first.click()
    pg.get_by_text("What's within a short walk?").wait_for(timeout=60000)
    pg.wait_for_timeout(7000)
    pg.get_by_text("What's within a short walk?").scroll_into_view_if_needed()
    pg.mouse.wheel(0, 260); pg.wait_for_timeout(1500)
    pg.screenshot(path=f"{OUT}/{PREFIX}_3_address_view_map.png")
    pg.get_by_role("button", name="All results").click()
    pg.get_by_role("button", name="Compare side by side").click()
    pg.get_by_text("Side by side").wait_for(timeout=60000)
    pg.wait_for_timeout(2500)
    pg.screenshot(path=f"{OUT}/{PREFIX}_4_compare.png")
    b.close()
print("captured", PREFIX)
