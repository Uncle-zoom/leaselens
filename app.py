"""LeaseLens: know the block and the landlord before you sign.   Run:  streamlit run app.py

Flow: landing (search) -> scanning (step indicator) -> result cards -> address view (questions with one-sentence answers)
and a head-to-head compare view. Data logic and agent behaviour live in jobs.py, analysis.py, sections.py, team.py and are unchanged.
"""
from __future__ import annotations

from sources.ct import property_type
import html
import itertools
import os
import time
from concurrent.futures import FIRST_COMPLETED, wait

import pandas as pd
import streamlit as st

import ai_runtime
import analysis
import maps
import sections
import styles
import summary
import team
import ui_helpers
import ui_html
import wording
from app_data import DEMO_ADDRESSES, sheet_from_job
from guardrails import Budget
from jobs import Job, result_or_error, start_job
from sources import router
from sources.common import load_env
from sources.core import building

LOAD_DEADLINE_S = 45
EXAMPLES = [("360 State Street", DEMO_ADDRESSES[0]), ("100 York Street", DEMO_ADDRESSES[1]), ("365 Orchard Street", DEMO_ADDRESSES[2])]
QUIET_CHOICES = {"Not much": "low", "Somewhat": "medium", "A lot": "high"}
SAVED_NOTE = "saved results from a live run (default priorities)"
AGENT_LABEL = {"block": "Block analyst", "landlord": "Landlord analyst", "email": "Email draft"}

st.set_page_config(page_title="LeaseLens", page_icon="🔎", layout="wide", initial_sidebar_state="collapsed")
load_env()
st.markdown(styles.css(), unsafe_allow_html=True)
ui_helpers.embed_html("<script>window.parent.document.documentElement.lang = 'en';</script>", 1)   # screen readers: page language

# ------------------------------------------------------------------ state
S = st.session_state
S.setdefault("demo", True)
S.setdefault("view", "landing")
S.setdefault("detail", 0)
S.setdefault("n_fields", 1)
S.setdefault("want_ai", False)
S.setdefault("session_budget", Budget("this session", **team.SESSION_CAPS))
S.setdefault("last_run", None)
S.setdefault("chats", {})
S.setdefault("ai_handles", {})
S.setdefault("neg_emails", {})
S.setdefault("name_checks", {})        # building names waiting for "Is this right?" (slot -> building.check result)
S.setdefault("addresses", [])          # what was searched; widget values are lost when the landing page is not on screen
S.setdefault("prefs_vals", {"max_grocery": 10, "max_gym": 15, "max_transit": 8, "quiet_label": "Somewhat"})
demo: bool = S.demo
os.environ["LEASELENS_OFFLINE"] = "1" if demo else "0"
session_budget: Budget = S.session_budget


def go(view: str, detail: int = 0) -> None:
    S.view, S.detail = view, detail


def fill_example(address: str) -> None:
    S.addr0 = address


def accept_name(k: int) -> None:
    """"Yes": use the street address found for a building name. Once every name is confirmed, run the search."""
    chk = S.name_checks.pop(k)
    S[f"addr{k}"] = chk["address"]
    if not S.name_checks:
        S.addresses = addresses_now()
        S.view = "results"


def reject_name(k: int) -> None:
    """"Try the street address": clear the name so the person can type the address."""
    S.name_checks.pop(k, None)
    S[f"addr{k}"] = ""


def request_ai() -> None:
    """Ask for the AI verdict. The page the user is on stays the page they are on (results or address view)."""
    S.want_ai = True


with st.sidebar:
    st.toggle("Demo mode (offline sample data)", key="demo",
              help="Runs fully offline with the three sample New Haven addresses. Turn off to look up any US address live.")
    meter_ph = st.empty()
    heartbeat_ph = st.empty()


def beat() -> None:
    """Call inside every loop that waits for background work. Streamlit only notices a click (for example on the Demo mode switch) when the
    running script sends something to the page; a silent wait loop made the first click wait until the loop ended, so people clicked twice."""
    heartbeat_ph.markdown("")


def render_meter() -> None:
    last = S.last_run
    with meter_ph.container():
        st.caption("AI cost meter")
        if demo:
            st.caption("Demo mode shows saved AI results: no model calls, $0.")
        st.caption(f"This run: {last['tokens']:,} tokens, ${last['usd']:.4f}" if last else "This run: nothing yet")
        st.caption(f"This session: {session_budget.tokens:,} tokens, ${session_budget.usd:.4f} (cap ${session_budget.max_usd:.2f})")


# ------------------------------------------------------------------ priorities ("Personalize")
def personalize() -> analysis.Prefs:
    pv = S.prefs_vals
    with st.expander("Personalize: what matters to you"):
        g = st.slider("I want a grocery within this many minutes' walk", 3, 30, pv["max_grocery"], key="w_grocery")
        gy = st.slider("I want a gym within this many minutes' walk", 3, 30, pv["max_gym"], key="w_gym")
        t = st.slider("I want transit within this many minutes' walk", 3, 30, pv["max_transit"], key="w_transit")
        q = st.select_slider("Quiet at night matters", options=list(QUIET_CHOICES), value=pv["quiet_label"], key="w_quiet")
    S.prefs_vals = {"max_grocery": g, "max_gym": gy, "max_transit": t, "quiet_label": q}     # kept for the other views
    return analysis.Prefs(g, gy, t, QUIET_CHOICES[q])


# ------------------------------------------------------------------ jobs
@st.cache_resource
def job_store() -> dict:
    return {}


def get_job(address: str) -> Job:
    store = job_store()
    key = (demo, " ".join(address.lower().split()))
    if key not in store:
        store[key] = start_job(address)
    return store[key]


def _norm(a: str) -> str:
    return " ".join(a.lower().replace(",", " ").split())


def part(job: Job, name: str):
    return result_or_error(job.futures()[name])


def geo_data(job: Job):
    if not job.geo.done():
        return None, None
    res, err = result_or_error(job.geo)
    if err:
        return None, err
    return (res.data, None) if res.ok else (None, res.live_error or res.error)


def short_title(address: str) -> str:
    return address.split(",")[0].strip()


# ------------------------------------------------------------------ AI results (saved in demo mode, live otherwise)
def ai_data(address: str, snap, handle_run_key):
    if demo:
        return ai_runtime.saved_address(address), SAVED_NOTE
    data = (snap or {}).get("addresses", {}).get(address)
    if data is not None:
        extra = {key: S.neg_emails[(handle_run_key, address, tone)] for tone, key in (("friendly", "email_negotiate"), ("firm", "email_negotiate_firm"))
                 if (handle_run_key, address, tone) in S.neg_emails}
        data = {**data, **extra}
    return data, "live AI run"


def show_removed(rem: list[dict]) -> None:
    if rem:
        with st.expander(f"Removed by code checks ({len(rem)})"):
            st.caption("Removed because a sentence contained a number or name that is not in the data we found, or wording we do not allow "
                       "(labels, claims of control, and in emails threats or legal claims).")
            for r in rem:
                wording = [u for u in r["unsupported"] if u.startswith("banned wording")]
                why = ", ".join(wording) if wording else "not in the data: " + ", ".join(r["unsupported"])
                st.write(f"- “{r['text']}”  ({why})")


# ====================================================================== LANDING
def view_landing() -> None:
    for k in range(3):
        if f"addr{k}" not in S:
            S[f"addr{k}"] = S.addresses[k] if k < len(S.addresses) else ""
    S.n_fields = max(S.n_fields, min(3, max(1, len(S.addresses))))
    st.markdown(ui_html.hero_html(), unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 3, 1])
    with mid:
        with st.form("search", border=False):
            st.text_input("Apartment address", key="addr0", placeholder="For example: 360 State Street, New Haven, CT")
            for k, label in ((1, "Second address"), (2, "Third address")):
                if S.n_fields > k:
                    st.text_input(label, key=f"addr{k}", placeholder="Another apartment to compare")
            c1, c2 = st.columns(2)
            add = c1.form_submit_button("Add another address", disabled=S.n_fields >= 3, use_container_width=True)
            check = c2.form_submit_button("Check addresses", type="primary", use_container_width=True)
        for k, chk in sorted(S.name_checks.items()):
            if chk["ok"]:
                st.info(f"We found: **{chk['name']}**, {chk['address']}. Is this right?")
                b1, b2 = st.columns(2)
                b1.button("Yes", key=f"name_yes_{k}", type="primary", on_click=accept_name, args=(k,), use_container_width=True)
                b2.button("Try the street address", key=f"name_no_{k}", on_click=reject_name, args=(k,), use_container_width=True)
            else:
                st.warning(f"“{chk['typed']}”: {chk['message']}")
        st.markdown('<p class="ll-muted" style="text-align:center;margin:.2rem 0">Or try an example</p>', unsafe_allow_html=True)
        chips = st.columns(3)
        for k, (label, address) in enumerate(EXAMPLES):
            chips[k].button(label, key=f"chip_{k}", on_click=fill_example, args=(address,), use_container_width=True)
        personalize()
        if demo:
            st.caption("Demo mode is on: it works offline with the three example addresses above. Turn it off in the sidebar to look up any US address.")
        st.button("How LeaseLens checks its own work", key="to_hood", type="tertiary", on_click=go, args=("hood",))
        if add:
            S.n_fields = min(3, S.n_fields + 1)
            st.rerun()
        if check:
            if not any(S.get(f"addr{k}", "").strip() for k in range(3)):
                st.error("Type an address first, or tap one of the examples.")
            else:
                S.name_checks = {k: building.check(a) for k in range(3) if (a := S.get(f"addr{k}", "").strip())
                                 and not demo and building.looks_like_name(a)}      # a name has no street number; Demo mode has no live lookup
                if S.name_checks:
                    st.rerun()                   # show "We found ... Is this right?"; the search starts only after Yes
                S.addresses = addresses_now()
                S.view = "results"
                st.rerun()


# ====================================================================== shared data for results / detail / compare
def addresses_now() -> list[str]:
    """Addresses typed on the landing page, else the ones last searched."""
    typed = [S.get(f"addr{k}", "").strip() for k in range(3)]
    typed = [a for a in typed if a]
    return typed if (S.view == "landing" and typed) else list(S.addresses)


def prepare():
    """Returns (addresses, jobs) after the demo-mode check, or stops the page with a clear message."""
    addrs = addresses_now()
    if demo:
        known = {_norm(d) for d in DEMO_ADDRESSES}
        for a in [a for a in addrs if _norm(a) not in known]:
            st.warning(f"“{a}”: Demo mode only has the 3 sample addresses; switch it off to look this up live.")
        addrs = [a for a in addrs if _norm(a) in known]
    if not addrs:
        st.button("← Back to search", on_click=go, args=("landing",))
        st.stop()
    return addrs, [get_job(a) for a in addrs]


def wait_for(jobs: list[Job], placeholder, include_pgeo: bool = False, deadline_s: float = LOAD_DEADLINE_S) -> None:
    """Block (with a visible step indicator) until the jobs have finished or the deadline passes."""
    def parts():
        return [f for j in jobs for k, f in j.futures().items() if include_pgeo or k not in ("pgeo", "chain")]
    end = time.time() + deadline_s
    while time.time() < end:
        pend = [f for f in parts() if not f.done()]
        placeholder.markdown(ui_html.steps_html(step_state(jobs)), unsafe_allow_html=True)
        if not pend:
            break
        wait(pend, timeout=0.4, return_when=FIRST_COMPLETED)


def step_state(jobs: list[Job]) -> list[bool]:
    geo = all(j.geo.done() for j in jobs)
    block = geo and all(j.block.done() for j in jobs)
    records = geo and all(j.street.done() and j.landlord.done() for j in jobs)
    return [geo, block, records, geo and block and records]


class VM:
    """Everything the page needs to show one address (computed from finished futures; None where not ready yet)."""

    def __init__(self, job: Job, prefs: analysis.Prefs):
        self.job, self.address = job, job.address
        self.geo, self.geo_err = geo_data(job)
        self.plan = router.route(self.geo) if self.geo else None
        self.in_ct = bool(self.plan) and "ct" in self.plan.markets
        blk = part(job, "block")[0] if job.block.done() else None
        self.places = blk["places"] if blk else None
        self.walking = blk.get("walking") if blk else None
        self.scores = self.walk_rows = self.noise_rows = None
        # the block lookup finished but gave no usable places (all map servers failed or timed out): never to be shown as "none within 800 m"
        self.places_failed = bool(self.geo) and job.block.done() and (self.places is None or not self.places.ok)
        if self.places is not None and self.places.ok:
            wk = self.walking.data if self.walking is not None and self.walking.ok else None
            self.scores = analysis.score_address(self.places.data, wk, prefs)
            self.walk_rows = analysis.walk_table(self.places.data, wk, prefs)
            self.noise_rows = analysis.noise_table(self.places.data)
        street_res = part(job, "street")[0] if job.street.done() else None
        self.street = sections.street_section(street_res, self.in_ct) if job.street.done() else None
        ld = part(job, "landlord")[0] if job.landlord.done() else None
        self.landlord = (sections.landlord_section(ld["parcels"], ld["registry"], ld["portfolio"], self.in_ct,
                                                   self.plan.coming_soon if self.plan else ())
                         if job.landlord.done() and ld is not None else None)
        pf = (ld or {}).get("portfolio") if ld else None
        self.portfolio_total = pf.data["total_matches"] if pf is not None and pf.ok else None
        self.prop = (self.landlord or {}).get("property") if self.landlord else None
        self.landlord_known = job.landlord.done() and job.geo.done()
        pg = part(job, "pgeo")[0] if job.pgeo.done() else None
        self.pgeo = pg
        ch = part(job, "chain")[0] if job.chain.done() else None
        self.chain = ch                                       # {"trail": SourceResult, "located": ...} or None
        self.trail = ch["trail"].data if ch and ch["trail"].ok else None
        self.chain_pins = (ch or {}).get("located") if ch else None


def card_for(i: int, vm: VM, snap, handle_run_key, ai_note: str = "") -> tuple[str, str]:
    """(card html, the 'verdict and score differ' note for this address or '')."""
    title = short_title(vm.address)
    if vm.geo_err or (vm.job.geo.done() and vm.geo is None):
        return (f'<article class="ll-card" aria-label="{html.escape(title)}"><h3 class="ll-addr">{html.escape(title)}</h3>'
                f'<p>{ui_html.icon("alert")} We could not find this address. Check the spelling and try again.</p></article>'), ""
    if vm.geo is None:
        return ui_html.card_html(title, None), ""
    data, _ = ai_data(vm.address, snap, handle_run_key)
    verdict = (((data or {}).get("block") or {}).get("output") or {}).get("verdict")
    s = summary.card_summary(vm.scores, vm.walk_rows, vm.portfolio_total, vm.in_ct, vm.landlord_known, verdict, block_failed=vm.places_failed, prop=vm.prop)
    return ui_html.card_html(title, s, ai_note), s["note"]


# ====================================================================== RESULTS (scanning + cards)
def view_results() -> None:
    addrs, jobs = prepare()
    st.button("← New search", on_click=go, args=("landing",))
    st.markdown('<h1 style="margin:.4rem 0 .8rem;font-size:2.2rem">Your results</h1>', unsafe_allow_html=True)
    prefs = personalize()
    steps_ph = st.empty()
    ai_ok, ai_why = team.ai_configured()
    run_key = (tuple(addrs), prefs.max_grocery, prefs.max_gym, prefs.max_transit, prefs.quiet)

    note_ph = st.empty()
    notes: dict[int, str] = {}
    cols = st.columns(len(addrs))
    card_phs = []
    for i, col in enumerate(cols):
        with col:
            card_phs.append(st.empty())
            st.button("See details", key=f"detail_{i}", on_click=go, args=("detail", i), use_container_width=True)
    action_ph = st.container()
    handle = None if demo else S.ai_handles.get(run_key)

    def snap_now():
        return handle.snapshot_json() if handle is not None else None

    # --- the AI buttons (live mode only; demo mode shows saved results)
    with action_ph:
        row = st.columns([1, 1])
        if len(addrs) > 1:
            row[0].button("Compare side by side", type="primary", on_click=go, args=("compare",), use_container_width=True)
        if demo:
            st.caption(f"AI verdicts shown are {SAVED_NOTE}.")
        elif not ai_ok:
            st.caption(f"Live AI is not set up ({ai_why}). Turn on Demo mode in the sidebar to see saved AI results.")
        else:
            asked = S.pop("want_ai", False)
            if (row[1].button("Get the AI verdict", use_container_width=True, disabled=handle is not None and not handle.done) or asked) \
                    and (handle is None or handle.done):
                sheets = [sheet_from_job(j, prefs) for j in jobs]
                if all(sh is not None for sh in sheets):
                    handle = ai_runtime.start_live(sheets, session_budget)
                    S.ai_handles[run_key] = handle
                else:
                    st.info("Still collecting the facts. Press the button again in a moment.")
    for e in (snap_now() or {}).get("errors", []):
        st.warning(e)

    def draw(i: int) -> None:
        vm = VM(jobs[i], prefs)
        note = ""
        if handle is not None and not handle.done:
            note = ui_html_status("The AI team is writing its verdict…")
        card_html, notes[i] = card_for(i, vm, snap_now(), run_key, note)
        card_phs[i].markdown(card_html, unsafe_allow_html=True)
        if any(notes.values()):          # said once, above the cards, instead of on every card
            note_ph.markdown(f'<p class="ll-note" role="note">{html.escape(summary.DISAGREE_NOTE)}</p>', unsafe_allow_html=True)

    # take the list of unfinished lookups BEFORE the first draw: one that finishes in between would otherwise never be redrawn
    pending = {f: (i, n) for i, j in enumerate(jobs) for n, f in j.futures().items() if not f.done() and n not in ("pgeo", "chain")}
    for i in range(len(jobs)):
        draw(i)
    steps_ph.markdown(ui_html.steps_html(step_state(jobs)), unsafe_allow_html=True)
    end = time.time() + LOAD_DEADLINE_S
    while pending and time.time() < end:
        beat()
        done_, _ = wait(list(pending), timeout=0.4, return_when=FIRST_COMPLETED)
        for f in done_:
            i, _n = pending.pop(f)
            draw(i)
        if done_:
            steps_ph.markdown(ui_html.steps_html(step_state(jobs)), unsafe_allow_html=True)
    for i in range(len(jobs)):      # one last look at everything: no card is left showing "checking…" for a lookup that has finished
        draw(i)
    if handle is not None and not handle.done:
        seen, t_end = -1, time.time() + 150
        while not handle.done and time.time() < t_end:
            beat()
            n = handle.run.finished_count()
            if n != seen:
                seen = n
                for i in range(len(jobs)):
                    draw(i)
            time.sleep(0.3)
        S.last_run = handle.snapshot_json()["run"]
        for i in range(len(jobs)):
            draw(i)
    steps_ph.markdown('<div class="ll-sr" role="status" aria-live="polite">All done. Results are ready.</div>', unsafe_allow_html=True)
    if pending:
        st.info("A few sources are taking longer than usual. Open an address or press a button to pick up late results.")
    st.button("How LeaseLens checks its own work", key="to_hood2", type="tertiary", on_click=go, args=("hood",))


def ui_html_status(text: str) -> str:
    return f'<p class="ll-load" role="status"><span class="ll-spin"></span><span>{html.escape(text)}</span></p>'


# ====================================================================== ADDRESS VIEW
def question(title: str, answer: str) -> None:
    st.markdown(f'<h2 style="font-size:1.5rem;margin:1.6rem 0 .1rem">{html.escape(title)}</h2><p class="ll-answer">{html.escape(answer)}</p>',
                unsafe_allow_html=True)


def view_detail() -> None:
    addrs, jobs = prepare()
    i = min(S.detail, len(addrs) - 1)
    prefs = personalize_quiet()
    st.button("← All results", on_click=go, args=("results",))
    steps_ph = st.empty()
    wait_for(jobs, steps_ph, include_pgeo=True, deadline_s=LOAD_DEADLINE_S)
    steps_ph.empty()
    vm = VM(jobs[i], prefs)
    ai_ok, ai_why = team.ai_configured()
    run_key = (tuple(addrs), prefs.max_grocery, prefs.max_gym, prefs.max_transit, prefs.quiet)
    handle = None if demo else S.ai_handles.get(run_key)
    if S.pop("want_ai", False) and ai_ok and not demo and (handle is None or handle.done):
        sheets = [sheet_from_job(j, prefs) for j in jobs]          # the page waited for every lookup above, so the facts are ready
        if all(sh is not None for sh in sheets):
            handle = ai_runtime.start_live(sheets, session_budget)
            S.ai_handles[run_key] = handle
    snap = handle.snapshot_json() if handle is not None else None
    data, note = ai_data(vm.address, snap, run_key)
    block_out = ((data or {}).get("block") or {}).get("output")
    landlord_out = ((data or {}).get("landlord") or {}).get("output")

    if vm.geo is None:
        st.markdown(f'<h1>{html.escape(short_title(vm.address))}</h1>', unsafe_allow_html=True)
        st.error("We could not find this address. Check the spelling and try again.")
        return
    s = summary.card_summary(vm.scores, vm.walk_rows, vm.portfolio_total, vm.in_ct, vm.landlord_known, (block_out or {}).get("verdict"),
                             block_failed=vm.places_failed, prop=vm.prop)
    place = ", ".join(x for x in (vm.geo.get("city"), f"{vm.geo.get('state_code') or ''} {vm.geo.get('postcode') or ''}".strip()) if x)
    st.markdown(f'<h1 style="margin:.3rem 0 .2rem">{html.escape(short_title(vm.address))}</h1><p class="ll-muted" style="margin:0 0 .8rem">{html.escape(place)}</p>'
                f'<div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap">{ui_html.pill(s["badge"], s["tone"], s["icon"])}'
                + (f'<span class="ll-tabular" role="img" aria-label="Overall score {s["score"]} out of 100"><strong style="font-size:1.6rem">{s["score"]}</strong> '
                   f'<span class="ll-muted">out of 100</span></span>' if s["score"] is not None else "") + "</div>", unsafe_allow_html=True)
    if block_out:
        st.markdown(f'<p class="ll-answer">{html.escape(block_out["summary"])}</p>', unsafe_allow_html=True)

    # ---- 1. within a short walk
    question("What's within a short walk?", summary.answers(vm.address, vm.scores, vm.walk_rows, vm.noise_rows, vm.street,
                                                           vm.landlord, None, vm.in_ct, block_failed=vm.places_failed)["walk"])
    pins = (vm.pgeo or {}).get("located") if vm.pgeo else None
    mcol, tcol = st.columns([3, 2])
    with mcol:
        cpins = (vm.chain_pins or {}).get("located") if vm.chain_pins else None
        ui_helpers.show_map(maps.build_block_map(vm.geo["lat"], vm.geo["lon"], vm.places, vm.walking.data if vm.walking is not None and vm.walking.ok else None,
                                                 pins, (vm.portfolio_total if vm.portfolio_total is not None else None),
                                                 cpins, vm.trail["parcels_total"] if vm.trail else None), 420)
    with tcol:
        st.markdown('<h3 style="font-size:1.05rem">Map summary (text version)</h3>', unsafe_allow_html=True)
        items = summary.map_text_alternative(vm.places.data if vm.places is not None and vm.places.ok else None, vm.walk_rows, vm.places_failed)
        st.markdown("<ul>" + "".join(f"<li>{html.escape(t)}</li>" for t in items) + "</ul>", unsafe_allow_html=True)
        st.caption("Rings on the map show about 5 and 10 minutes on foot. Source: OpenStreetMap.")
    st.markdown(maps.legend_html(bool(pins), chain=bool(cpins)), unsafe_allow_html=True)
    if s["note"]:
        st.markdown(f'<p class="ll-muted">{html.escape(s["note"])}</p>', unsafe_allow_html=True)
    with st.expander("See walking times"):
        if vm.places_failed:
            st.warning(summary.COULDNT_CHECK_PLACES)
        elif vm.walk_rows is None:
            st.markdown(ui_html_status("Still mapping the block…"), unsafe_allow_html=True)
        else:
            rows = [[r["label"], r["nearest"] or "none within 800 m", "-" if r["walk_min"] is None else wording.walk_phrase(r["walk_min"], r.get("walk_m")).replace(" walk", ""),
                     "" if r["limit"] is None else f"{r['limit']} min", "" if r["meets"] is None else ("Yes" if r["meets"] else "No")]
                    for r in vm.walk_rows]
            st.markdown(ui_html.table_html(["Place", "Nearest", "Walk", "Your limit", "Within your limit?"], rows,
                                           "Walking minutes to the nearest place of each kind", {2, 3}), unsafe_allow_html=True)
            sec = sections.block_section(vm.places, vm.walking, prefs)
            st.caption(f"Source: [{sec['cite'][0]}]({sec['cite'][1]}) · {sec.get('origin', '')}. Minutes are routed on footpaths when available, "
                       "otherwise straight-line distance × 1.3 at 5 km/h.")

    # ---- 2. noise
    question("Will it be noisy?", summary.answers(vm.address, vm.scores, vm.walk_rows, vm.noise_rows, vm.street, vm.landlord, None, vm.in_ct,
                                                  block_failed=vm.places_failed)["noise"])
    with st.expander("See noise sources"):
        if vm.places_failed:
            st.warning(summary.COULDNT_CHECK_PLACES)
        elif vm.noise_rows is None:
            st.markdown(ui_html_status("Still mapping the block…"), unsafe_allow_html=True)
        else:
            st.markdown(ui_html.table_html(["Type", "Within 800 m", "Nearest", "Distance"],
                                           [[r["label"], r["count"], r["nearest"] or "-", "-" if r["nearest_m"] is None else f"{r['nearest_m']} m"]
                                            for r in vm.noise_rows], "Noise sources near the building", {1, 3}), unsafe_allow_html=True)
            st.caption("Rail lines count the nearest track segment only. Source: OpenStreetMap.")

    # ---- 3. neighbors report
    street_sec = vm.street
    street_answer = summary.answers(vm.address, vm.scores, vm.walk_rows, vm.noise_rows, street_sec if street_sec and not street_sec["error"] else None,
                                    vm.landlord, None, vm.in_ct)["street"]
    if street_sec and street_sec["error"] and vm.in_ct:           # a failed lookup is not "still checking" and not "none"
        street_answer = summary.COULDNT_CHECK_STREET
    question("What do neighbors report?", street_answer)
    st.markdown('<div class="ll-note"><strong>Street-level reports, not housing complaints.</strong> They describe the public street: snow, signals, parking, dumping, potholes.</div>',
                unsafe_allow_html=True)
    with st.expander("See what was reported"):
        if street_sec is None:
            st.markdown(ui_html_status("Fetching street-level reports…"), unsafe_allow_html=True)
        elif street_sec["error"]:
            st.write(street_sec["error"])
        else:
            st.markdown(ui_html.table_html(["Type of report", "Reports", "Still open"],
                                           [[r["request_type"], r["count"], r["open"]] for r in street_sec["rows"][:12]],
                                           f"Within {street_sec['radius_m']} m since {street_sec['since']}", {1, 2}), unsafe_allow_html=True)
            st.caption(f"Source: [{street_sec['cite'][0]}]({street_sec['cite'][1]}) · {street_sec['origin']}")

    # ---- 4. owner
    ll = vm.landlord
    question("Who owns this building?", summary.answers(vm.address, vm.scores, vm.walk_rows, vm.noise_rows, None, ll, None, vm.in_ct, vm.trail)["owner"])
    with st.expander("See the owner, registry record and other parcels"):
        render_owner_details(vm, ll)

    # ---- 5. ask
    question("What should I ask?", summary.answers(vm.address, None, None, None, None, None, (landlord_out or {}).get("questions"), vm.in_ct)["ask"])
    if handle is not None and not handle.done:
        await_ai(handle, addrs)
    else:
        render_ai_details(i, vm, data, note, block_out, landlord_out, ai_ok, ai_why, run_key)


def await_ai(handle, addrs: list[str]) -> None:
    """The AI team is running: show each agent's progress right here on the address view, then reload this same page with the results."""
    ph = st.empty()
    t_end = time.time() + 150
    while not handle.done and time.time() < t_end:
        beat()
        prog = handle.progress()
        rows = [f"**{short_title(a)}**: " + " · ".join(f"{'✅' if prog.get((a, k)) else '⏳'} {AGENT_LABEL[k]}" for k in AGENT_LABEL) for a in addrs]
        with ph.container():
            st.markdown(ui_html_status("The AI team is working: the verdict, the landlord notes and the email drafts appear here in a moment."), unsafe_allow_html=True)
            st.markdown("\n\n".join(rows))
        time.sleep(0.3)
    if handle.done:
        S.last_run = handle.snapshot_json()["run"]
        st.rerun()                                       # same view, same address: now with the AI results
    st.info("The AI team is taking longer than usual. Reload this page in a moment to see its results.")


def personalize_quiet() -> analysis.Prefs:
    """Detail and compare views reuse the priorities chosen on the landing page (no widgets, so no key clashes)."""
    pv = S.prefs_vals
    return analysis.Prefs(pv["max_grocery"], pv["max_gym"], pv["max_transit"], QUIET_CHOICES[pv["quiet_label"]])


def render_owner_details(vm: VM, ll) -> None:
    if ll is None:
        st.markdown(ui_html_status("Searching Connecticut parcel and business records…"), unsafe_allow_html=True)
        return
    if not ll["available"]:
        st.info(ll["note"])
        return
    if ll["errors"].get("parcel"):
        st.warning(ll["errors"]["parcel"])
        return
    p = ll["parcel"]
    prop = ll.get("property") or {}
    if prop.get("message"):
        st.info(prop["message"])
    if prop.get("kind") in property_type.HIDDEN_KINDS:
        st.caption(f"Source: [{ll['cites']['parcel'][0]}]({ll['cites']['parcel'][1]}) · {p['origin']}")
        return
    st.markdown("**Owner on the parcel record**")
    bits = [b for b in (p["use"], f"built {p['year_built']}" if p["year_built"] else None) if b]
    st.write(f"{p['owner']}" + (f" and {p['co_owner']}" if p["co_owner"] else "") + f" owns {p['location']}"
             + (f" ({', '.join(bits)})" if bits else "") + (f". Tax bills go to: {p['mailing']}." if p["mailing"] else "."))
    st.caption(f"Source: [{ll['cites']['parcel'][0]}]({ll['cites']['parcel'][1]}) · {p['origin']}")
    st.markdown("**Business registry record**")
    if ll["errors"].get("registry"):
        st.write(ll["errors"]["registry"])
    else:
        r = ll["registry"]
        st.write(f"{r['name']}: {r['entity_type']}, status {r['status']}, formed in {r['formed_in']}, registered {r['registered']}. "
                 f"Business address: {r['business_address']}. Registered agent: {', '.join(r['agents']) or 'none listed'}. "
                 f"Principals: {', '.join(r['principals']) or 'none listed'}.")
        st.caption(f"Matched to the parcel owner by {r['matched_how']} (confidence: {r['confidence']}). "
                   f"Source: [{ll['cites']['registry'][0]}]({ll['cites']['registry'][1]}) · {r['origin']}")
    map_shown = False
    st.markdown("**Other parcels linked to this owner**")
    pf = ll["portfolio"]
    if ll["errors"].get("portfolio"):
        st.write(ll["errors"]["portfolio"])
    elif pf["total"] == 0:
        st.write("No other Connecticut parcels were found under the same owner name or mailing address.")
    else:
        by = ", ".join(f"{n} by {k}" for k, n in pf["by_type"].items())
        st.write(f"{wording.plural(pf['total'], 'other parcel')} ({by}). Each shows how it was matched and how confident the match is.")
        pg = vm.pgeo
        if pg and pg["located"]:       # the map first: it answers "where are they?" at a glance; the table below gives the detail
            map_shown = show_owner_map(vm, pg["located"], pf["total"], with_chain=True)
            st.caption(f"Showing {len(pg['located'])} of {pf['total']} other parcels on the map"
                       + (f"; {pg['failed']} could not be located" if pg["failed"] else "") + ".")
        rows = [[r["Address"], r["Owner on record"], r["How matched"], r["Confidence"]] for r in pf["rows"][:10]]
        st.markdown(ui_html.table_html(["Address", "Owner on record", "How matched", "Confidence"], rows,
                                       f"First {len(rows)} of {pf['total']} (exact-name matches are listed first)"), unsafe_allow_html=True)
        st.caption("A mailing-address match means tax bills go to the same address. It is weaker evidence than an identical owner name, "
                   "and is marked lower confidence when many different owners share the address.")
        st.caption(f"Source: [{ll['cites']['portfolio'][0]}]({ll['cites']['portfolio'][1]}) · {pf['origin']}")
    render_trail(vm, map_shown)


def show_owner_map(vm: VM, owner_pins: list[dict], owner_total: int | None, with_chain: bool) -> bool:
    """One map for the owner's other parcels and (as a second, clustered layer) the buildings of the companies linked through a principal."""
    cpins = ((vm.chain_pins or {}).get("located") or []) if with_chain else []
    ctotal = vm.trail["parcels_total"] if vm.trail else None
    ui_helpers.show_map(maps.build_parcel_map(vm.geo["lat"], vm.geo["lon"], owner_pins, owner_total, cpins or None, ctotal), 380)
    st.markdown(maps.legend_html(True, owner_only=bool(owner_pins), chain=bool(cpins)), unsafe_allow_html=True)
    return True


def render_trail(vm: VM, map_shown: bool) -> None:
    """Owner -> linked entity -> N related companies -> M buildings, one extra level, each link with how it was matched and a confidence."""
    st.markdown("**Ownership trail: companies linked through a shared principal**")
    if not vm.job.chain.done():
        st.markdown(ui_html_status("Following the registry principals one level…"), unsafe_allow_html=True)
        return
    if vm.chain is None:
        st.write("Not followed: the state registry has no entry for the owner name, so there is no principal to look up.")
        return
    tr = vm.chain["trail"]
    if not tr.ok:
        st.write(f"The trail could not be followed ({(tr.live_error or tr.error or 'unknown error')[:140]}).")
        return
    t = tr.data
    st.markdown(f'<p class="ll-answer" style="font-size:1.1rem">{html.escape(summary.chain_headline(t))}</p>', unsafe_allow_html=True)
    st.markdown(ui_html.chain_html(t), unsafe_allow_html=True)
    cp = ((vm.chain_pins or {}).get("located") or []) if vm.chain_pins else []
    if cp and not map_shown:
        show_owner_map(vm, [], None, with_chain=True)
        st.caption(f"Showing {len(cp)} of {t['parcels_total']} buildings on the map.")
    elif cp:
        st.caption(f"The map above has a second layer, “Related companies' buildings”: showing {len(cp)} of {t['parcels_total']}.")
    comps = [dict(c, entity=e["name"]) for e in t["entities"] for c in e["companies"]]
    if comps:
        st.markdown(ui_html.table_html(
            ["Company", "Type", "Status", "Registered in", "How matched", "Confidence"],
            [[c["name"], c["business_type"] or "-", c["status"] or "-", ", ".join(x for x in (c["city"], c["state"]) if x) or "-", c["matched_how"], c["confidence"]]
             for c in comps[:10]],
            f"Related companies: first {min(10, len(comps))} of {t['companies_total']}"), unsafe_allow_html=True)
    if t["parcels"]:
        st.markdown(ui_html.table_html(
            ["Address", "Company", "How matched", "Confidence"],
            [[p["location"], p["company"], p["match_type"], p["confidence"]] for p in t["parcels"][:10]],
            f"Buildings: first {min(10, len(t['parcels']))} of {t['parcels_total']}"), unsafe_allow_html=True)
    notes = []
    if t["individual_principals_not_followed"]:
        notes.append(f"{t['individual_principals_not_followed']} principal(s) are people and were not followed: a name alone is weak evidence.")
    if t["registered_agents_not_followed"]:
        notes.append("Registered agent(s) " + ", ".join(t["registered_agents_not_followed"]) + " were not followed: an agent is shared by many unrelated companies.")
    notes.append(f"Limits: {t['caps']['companies']} companies and {t['caps']['parcels']} parcels shown at most; one level only.")
    st.caption(" ".join(notes))
    st.caption(f"Source: [{tr.dataset['name']}]({tr.dataset['url']}) · {sections.origin_label(tr)}")


def render_ai_details(i: int, vm: VM, data, note, block_out, landlord_out, ai_ok, ai_why, run_key) -> None:
    sheet = sheet_from_job(vm.job, personalize_quiet())
    if not data:
        st.info("No AI analysis for this address yet." + (" Saved results exist only for the three example addresses." if demo else ""))
        if not demo:
            if ai_ok:
                st.button("Get the AI verdict", key="ask_ai", type="primary", on_click=request_ai)
            else:
                st.caption(f"Live AI is not set up ({ai_why}).")
    else:
        st.caption(f"Source: {note}. Facts and counts only. A draft only: LeaseLens never sends anything.")
        if block_out:
            with st.expander("Why this verdict", expanded=True):
                for r in block_out["reasons"]:
                    st.markdown(f"- {r}")
        if landlord_out:
            with st.expander("What the landlord records show", expanded=False):
                st.write(landlord_out["plain_english"])
                for o in landlord_out["observations"]:
                    st.markdown(f"- {o}")
            st.markdown("**Three questions to ask the landlord**")
            st.markdown("\n".join(f"{n}. {q}" for n, q in enumerate(landlord_out["questions"], 1)))
        em_ask = (data.get("email_ask_questions") or {}).get("output")
        em_neg = {"friendly": (data.get("email_negotiate") or {}).get("output"), "firm": (data.get("email_negotiate_firm") or {}).get("output")}
        if em_ask or any(em_neg.values()):
            with st.expander("Draft email to the leasing agent", expanded=True):
                kind = st.radio("Purpose", ["Ask questions", "Negotiate"], horizontal=True, key=f"emailkind_{i}")
                tone = "friendly"
                if kind == "Negotiate":
                    tone = st.radio("Tone", ["Friendly", "Firm"], horizontal=True, key=f"emailtone_{i}",
                                    help="Firm cites every relevant fact and asks for specific concessions (rent, repairs, lease terms). "
                                         "Both stay factual and polite: no threats and no legal claims.").lower()
                em = em_ask if kind == "Ask questions" else em_neg[tone]
                if em is None and kind == "Negotiate":
                    if demo:
                        st.info(f"A {tone} negotiation draft is not saved for this address in Demo mode.")
                    elif ai_ok:
                        if st.button(f"Draft the {tone} negotiation email", key=f"neg_{i}_{tone}"):
                            with st.spinner(f"Drafting the {tone} negotiation email…"):
                                res, err = ai_runtime.negotiate(sheet, session_budget, tone)
                            if err:
                                st.warning(err)
                            else:
                                S.neg_emails[(run_key, vm.address, tone)] = res
                                em = res["output"]
                if em is not None:
                    default_text = f"Subject: {em['subject']}\n\n{em['body']}"
                    st.text_area("Edit before you send it yourself", default_text, height=300, key=f"email_{i}_{kind}_{tone}")
                    ui_helpers.embed_html(ui_helpers.copy_button_html(S.get(f"email_{i}_{kind}_{tone}", default_text)), 56)
        show_removed(ai_runtime.all_removals(data))

    with st.expander("Ask about this apartment"):
        chats = S.chats.setdefault(vm.address, {"turns": [], "history": None})
        for t_ in chats["turns"]:
            with st.chat_message("user"):
                st.write(t_["question"])
            with st.chat_message("assistant"):
                st.write(t_["answer"] or t_["error"])
                show_removed(t_.get("removed", []))
        if demo:
            saved = (ai_runtime.saved_address(vm.address) or {}).get("chat_examples", [])
            st.caption("Chat needs the live model. In Demo mode, pick a question that was asked in a live run:")
            if saved:
                q = st.selectbox("Saved question", [x["question"] for x in saved], key=f"saveq_{i}")
                ex = next(x for x in saved if x["question"] == q)
                st.markdown(f"**Answer:** {ex['output']['answer'] if 'output' in ex else ex.get('error', '')}")
        elif not ai_ok:
            st.info(f"Chat is unavailable ({ai_why}).")
        else:
            with st.form(f"chat_{i}", clear_on_submit=True):
                question_text = st.text_input("Your question about this address", placeholder="Is the nearest grocery within my limit?")
                sent = st.form_submit_button("Ask")
            if sent and question_text.strip():
                with st.spinner("Looking it up in the data…"):
                    ans, chats["history"] = ai_runtime.ask(sheet, question_text.strip(), chats["history"], session_budget)
                chats["turns"].append({"question": question_text.strip(), **ans})
                if ans.get("tokens"):
                    S.last_run = {"tokens": ans["tokens"], "usd": ans["usd"], "requests": 1}
                with st.chat_message("user"):
                    st.write(question_text.strip())
                with st.chat_message("assistant"):
                    st.write(ans["answer"] or ans["error"])
                    show_removed(ans.get("removed", []))


# ====================================================================== COMPARE
def view_compare() -> None:
    addrs, jobs = prepare()
    prefs = personalize_quiet()
    st.button("← All results", on_click=go, args=("results",))
    st.markdown('<h1 style="margin:.3rem 0 .6rem">Side by side</h1>', unsafe_allow_html=True)
    steps_ph = st.empty()
    wait_for(jobs, steps_ph)
    steps_ph.empty()
    vms = [VM(j, prefs) for j in jobs]
    labels = [short_title(a) for a in addrs]
    scores = {lab: v.scores for lab, v in zip(labels, vms)}
    win = analysis.winners(scores)
    rows = []
    for cat in ["Overall"] + analysis.CATEGORIES:
        vals = [(f"{round(v.scores[cat])}" if v.scores else "-") for v in vms]
        w = win.get(cat, "—")
        idx = labels.index(w) if w in labels else ("tie" if str(w).startswith("tie") else None)
        rows.append({"name": cat if cat != "Quiet" else "Quiet at night", "values": vals, "winner": idx})
    streets = [(v.street["total"] if v.street and not v.street["error"] else "-") for v in vms]
    rows.append({"name": "Street-level reports (12 months)", "values": streets, "winner": None})
    rows.append({"name": "Other parcels linked to the owner", "values": [v.portfolio_total if v.portfolio_total is not None else "-" for v in vms], "winner": None})
    best = win.get("Overall", "—")
    st.markdown(f'<p class="ll-answer">{html.escape("Best overall for your priorities: " + best + "." if best in labels else "These addresses are tied overall." if str(best).startswith("tie") else "Add a second address to compare.")}</p>',
                unsafe_allow_html=True)
    st.markdown(ui_html.compare_html(labels, rows), unsafe_allow_html=True)
    st.caption("Scores are 0 to 100, higher is better. 100 means a place is right next door; 50 is exactly your walking limit; no place within 800 m scores 0. "
               "Quiet falls as bars, clubs, fire stations, hospitals and rail lines get closer. No AI is used in these scores.")
    rec, note = (ai_runtime.saved_recommendation(addrs), SAVED_NOTE) if demo else (None, "")
    if not demo:
        handle = S.ai_handles.get((tuple(addrs), prefs.max_grocery, prefs.max_gym, prefs.max_transit, prefs.quiet))
        rec = (handle.snapshot_json()["recommendation"] if handle is not None else None)
        note = "live AI run"
    with st.expander("AI recommendation and trade-offs", expanded=rec is not None):
        if not rec:
            st.write("No AI recommendation yet." + ("" if demo else " Press “Get the AI verdict” on the results page."))
        else:
            o = rec["output"]
            st.caption(f"Source: {note}. Drafts and advice only; nothing is sent.")
            for r in sorted(o["ranking"], key=lambda r: r["rank"]):
                st.markdown(f"**{r['rank']}. {short_title(r['address'])}**: {r['headline']}")
                st.markdown("\n".join(f"- {x}" for x in r["strengths"]) + "\n" + "\n".join(f"- Trade-off: {x}" for x in r["trade_offs"]))
            st.markdown(f"**Overall.** {o['overall']}")
            st.markdown(f"**Trade-offs.** {o['key_tradeoffs']}")
            show_removed(rec.get("removed", []))


# ====================================================================== UNDER THE HOOD
def view_hood() -> None:
    from hood_view import render_under_the_hood
    st.button("← Back", on_click=go, args=("results" if addresses_now() else "landing",))
    render_under_the_hood()


{"landing": view_landing, "results": view_results, "detail": view_detail, "compare": view_compare, "hood": view_hood}.get(S.view, view_landing)()
render_meter()
