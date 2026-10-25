"""Start LeaseLens in Demo mode and save report-ready screenshots to output/screenshots/report/.

    pip install -r requirements-dev.txt        # Playwright; it drives your installed Google Chrome
    python make_screenshots.py [--out output/screenshots/report] [--port 8765] [--only 07_landlord]

Nothing here needs a network except the map tiles (Esri) and, for the landlord map, nothing else: Demo mode runs from data/samples/.
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EX = ["360 State Street, New Haven, CT", "100 York Street, New Haven, CT", "365 Orchard Street, New Haven, CT"]

# file name (without .png) -> what it shows. This list is the contract: tests check it matches what is written.
SHOTS = {
    "01_landing": "Landing page: headline, search field, example chips, Personalize",
    "02_result_cards": "Result cards for the three example addresses",
    "03_compare": "Side-by-side comparison with the winner per row",
    "04_address_walk_map": "Address view: What's within a short walk? (map with rings, clusters, legend, text summary)",
    "05_address_noise": "Address view: Will it be noisy? (noise sources table opened)",
    "06_address_street_reports": "Address view: What do neighbors report? (street-level reports opened)",
    "07_address_landlord_parcels_map": "Address view: Who owns this building? (owner, registry, other parcels table and map)",
    "08_address_ai_verdict_questions_email": "Address view: What should I ask? (AI verdict, questions, email draft with Copy email)",
    "09_chat_answer": "Ask about this apartment: the chat answering a question",
    "10_hood_prompt_injection": "Under the hood: prompt-injection demo",
    "11_hood_fact_check": "Under the hood: fact-check demo",
    "12_hood_cost_cap": "Under the hood: cost-cap demo",
    "13_hood_live_run_real_model": "Under the hood: live run with the real model",
    "14_hood_usage_table": "Under the hood: usage table with cache hit rate",
    "15_address_ownership_trail": "Address view: ownership trail (owner, linked entity, related companies, buildings) with how each link was matched",
    "16_email_firm_tone": "Draft email with the Negotiate purpose and the Firm tone",
}


def free_port(preferred: int = 8765) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 50)):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("no free port found")


def section_clip(start_box: dict, end_box: dict | None, viewport_h: int, max_h: int = 1400, x: int = 60, width: int = 1160) -> dict:
    """The rectangle to capture, in viewport coordinates: from just above the start heading to just above the next heading (or max_h)."""
    y0 = max(start_box["y"] - 14, 0)
    y1 = (end_box["y"] - 8) if end_box is not None and end_box["y"] > start_box["y"] else y0 + max_h
    y1 = min(y1, y0 + max_h, viewport_h)
    return {"x": x, "y": y0, "width": width, "height": max(y1 - y0, 80)}


def start_app(port: int) -> subprocess.Popen:
    env = {**os.environ, "LEASELENS_OFFLINE": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(port), "--server.headless", "true",
                             "--browser.gatherUsageStats", "false"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    for _ in range(120):
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1).read() == b"ok":
                return proc
        except Exception:
            time.sleep(0.5)
    stop_app(proc)
    raise RuntimeError("the app did not start")


def stop_app(proc: subprocess.Popen) -> None:
    """Stop the whole process group, not just the parent (CLAUDE.md / AGENTS.md rule for Dash and Streamlit servers)."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "output" / "screenshots" / "report"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--only", default="", help="only shots whose name contains this text")
    args = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Playwright is not installed: pip install -r requirements-dev.txt (it uses your installed Google Chrome)")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    port = free_port(args.port)
    proc = start_app(port)
    url = f"http://127.0.0.1:{port}"
    saved: list[str] = []
    H = 1500
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            pg = browser.new_context(viewport={"width": 1280, "height": H}, color_scheme="light").new_page()

            def want(name):
                return args.only in name

            def save(name):
                if want(name):
                    pg.screenshot(path=str(out / f"{name}.png"))
                    saved.append(name)

            def heading(text, exact=False):
                return pg.get_by_text(text, exact=exact).first

            def to_top(loc):
                loc.evaluate("el => el.scrollIntoView({block: 'start'})")
                pg.wait_for_timeout(700)

            def shoot_section(name, start_text, end_text=None, wait=1500, max_h=1400):
                if not want(name):
                    return
                start = heading(start_text)
                start.wait_for(timeout=30000)
                to_top(start)
                pg.wait_for_timeout(wait)
                sb = start.bounding_box()
                eb = None
                if end_text:
                    e = heading(end_text)
                    if e.count():
                        eb = e.bounding_box()
                pg.screenshot(path=str(out / f"{name}.png"), clip=section_clip(sb, eb, H, max_h))
                saved.append(name)

            def open_expander(label):
                pg.get_by_text(label, exact=True).first.click()
                pg.wait_for_timeout(900)

            def new_search_to_results():
                pg.goto(url)
                pg.get_by_role("button", name="Check addresses").wait_for(timeout=30000)
                pg.wait_for_timeout(1200)
                save("01_landing")
                pg.get_by_role("button", name="360 State Street").first.click()
                pg.wait_for_timeout(1200)
                for label, addr in (("Second address", EX[1]), ("Third address", EX[2])):
                    pg.get_by_role("button", name="Add another address").click()
                    pg.wait_for_timeout(1200)
                    pg.get_by_label(label).fill(addr)
                    pg.get_by_label(label).press("Tab")
                    pg.wait_for_timeout(500)
                pg.get_by_role("button", name="Check addresses").click()
                pg.get_by_role("button", name="See details").first.wait_for(timeout=60000)
                pg.wait_for_timeout(6000)

            def open_detail(index):
                pg.get_by_role("button", name="See details").nth(index).click()
                pg.get_by_text("What's within a short walk?").wait_for(timeout=60000)
                pg.wait_for_timeout(5000)

            def back_to_results():
                pg.get_by_role("button", name="All results").click()
                pg.get_by_role("button", name="See details").first.wait_for(timeout=60000)
                pg.wait_for_timeout(3000)

            new_search_to_results()
            if want("02_result_cards"):
                pg.mouse.wheel(0, 0)
                pg.screenshot(path=str(out / "02_result_cards.png"), clip={"x": 60, "y": 0, "width": 1160, "height": 1080})
                saved.append("02_result_cards")
            if want("03_compare"):
                pg.get_by_role("button", name="Compare side by side").click()
                pg.get_by_text("Side by side").first.wait_for(timeout=60000)
                pg.wait_for_timeout(2500)
                pg.screenshot(path=str(out / "03_compare.png"), clip={"x": 60, "y": 0, "width": 1160, "height": 1200})
                saved.append("03_compare")
                pg.get_by_role("button", name="All results").click()
                pg.get_by_role("button", name="See details").first.wait_for(timeout=60000)
                pg.wait_for_timeout(2500)

            # ---- address view of 360 State Street
            open_detail(0)
            shoot_section("04_address_walk_map", "What's within a short walk?", "Will it be noisy?", wait=3500)
            if want("05_address_noise"):
                open_expander("See noise sources")
            shoot_section("05_address_noise", "Will it be noisy?", "What do neighbors report?")
            if want("06_address_street_reports"):
                open_expander("See what was reported")
            shoot_section("06_address_street_reports", "What do neighbors report?", "Who owns this building?")
            if want("08_address_ai"):
                shoot_section("08_address_ai_verdict_questions_email", "What should I ask?", "Ask about this apartment", max_h=1450)
            if want("09_chat_answer"):
                open_expander("Ask about this apartment")
                sel = pg.get_by_text("Saved question").first
                sel.scroll_into_view_if_needed()
                box = pg.get_by_role("combobox").last
                box.click()
                box.fill("Who owns")                       # the select filters as you type; Enter picks the match
                pg.wait_for_timeout(600)
                pg.keyboard.press("Enter")
                pg.get_by_text("Answer:").first.wait_for(timeout=10000)
                pg.wait_for_timeout(1200)
                shoot_section("09_chat_answer", "Ask about this apartment", None, max_h=700)

            if want("15_address_ownership_trail"):
                open_expander("See the owner, registry record and other parcels")
                pg.wait_for_timeout(1500)
                shoot_section("15_address_ownership_trail", "Ownership trail: companies linked through a shared principal", "What should I ask?", wait=1500, max_h=1000)
            if want("16_email_firm_tone"):
                to_top(heading("What should I ask?"))
                pg.get_by_text("Negotiate", exact=True).first.click()
                pg.wait_for_timeout(1200)
                pg.get_by_text("Firm", exact=True).first.click()
                pg.wait_for_timeout(1500)
                shoot_section("16_email_firm_tone", "Draft email to the leasing agent", "Ask about this apartment", wait=800, max_h=1100)

            # ---- landlord with the owner's other parcels on the map (the example with 88 linked parcels)
            if want("07_address_landlord"):
                back_to_results()
                open_detail(2)
                open_expander("See the owner, registry record and other parcels")
                pg.wait_for_timeout(2500)
                shoot_section("07_address_landlord_parcels_map", "Who owns this building?", "What should I ask?", wait=3000, max_h=1450)

            # ---- Under the hood
            if args.only == "" or "hood" in args.only:
                back_to_results()
                pg.get_by_role("button", name="How LeaseLens checks its own work").first.click()
                pg.get_by_text("Under the hood").first.wait_for(timeout=60000)
                pg.wait_for_timeout(2500)
                shoot_section("10_hood_prompt_injection", "1 · Prompt injection", "2 · Fact check", max_h=900)
                shoot_section("11_hood_fact_check", "2 · Fact check", "3 · Cost cap", max_h=900)
                shoot_section("12_hood_cost_cap", "3 · Cost cap", "Live run with the real model", max_h=700)
                shoot_section("13_hood_live_run_real_model", "Live run with the real model", "Usage so far", max_h=1100)
                shoot_section("14_hood_usage_table", "Usage so far", None, max_h=700)
            browser.close()
    finally:
        stop_app(proc)
    missing = [n for n in SHOTS if args.only in n and n not in saved]
    print(f"saved {len(saved)} screenshots to {out}" + (f"; MISSING: {missing}" if missing else ""))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
