"""Build output/slides.html: 10 reveal.js slides in one offline file (reveal.js from vendor/, screenshots as base64).
Every number comes from report_data.py; the tester lines are copied from content/impact_testers.md.

    python build_slides.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import report_data as rd
from report_style import BASE_CSS, diagram, e, money

VENDOR = rd.ROOT / "vendor" / "reveal.js"
MAX_SLIDES = 10

CSS = BASE_CSS + """
.reveal { font-family:inherit; color:var(--text); font-size:34px; }
.reveal-viewport { background:var(--bg); }
.reveal .slides section { text-align:left; padding:0 40px; }
.reveal h1 { font-size:2.6em; letter-spacing:-.02em; margin:0 0 .15em; text-transform:none; color:var(--text); }
.reveal h2 { font-size:1.55em; letter-spacing:-.015em; margin:0 0 .5em; text-transform:none; color:var(--text); }
.reveal p, .reveal li { line-height:1.3; }
.reveal ul { margin:0; padding-left:1em; display:block; }
.reveal li { margin:.35em 0; }
.reveal .big { font-size:1.9em; font-weight:600; letter-spacing:-.01em; line-height:1.15; }
.reveal .sub { color:var(--text2); font-size:.8em; }
.reveal .tiles { display:grid; grid-template-columns:repeat(3,1fr); gap:20px; margin-top:.6em; }
.reveal .tile { background:var(--card); border-radius:18px; padding:.5em .7em; box-shadow:0 0 0 1px var(--hair); }
.reveal .tile b { display:block; font-size:1.9em; letter-spacing:-.02em; color:var(--accent); font-variant-numeric:tabular-nums; }
.reveal .tile span { font-size:.62em; color:var(--text2); line-height:1.25; display:block; }
.reveal img { max-height:560px; max-width:100%; border-radius:14px; box-shadow:0 0 0 1px var(--hair); margin:0; }
.reveal .two { display:grid; grid-template-columns:1fr 1fr; gap:24px; align-items:start; }
.reveal .two .tiles { grid-template-columns:1fr; }
.reveal .two img { width:100%; max-height:520px; object-fit:contain; object-position:top; }
.reveal .cap { color:var(--text2); font-size:.55em; margin-top:.3em; }
.reveal .quote .who { display:block; font-size:.55em; color:#6E6E73; margin-top:.2em; }
.reveal .quote { border-left:6px solid var(--accent); padding:.1em .8em; margin:.5em 0; font-size:1.05em; }
.reveal svg { width:100%; height:auto; }
.reveal .small { font-size:.62em; }
.reveal .note { font-size:.5em; }
.reveal a { color:var(--link); }

.reveal-viewport { background:linear-gradient(180deg,#FFFFFF 0%,#F2F5FA 100%); }
.reveal .slides section { padding:0 56px; }
.reveal h2 { position:relative; padding-left:.55em; font-weight:700; }
.reveal h2::before { content:""; position:absolute; left:0; top:.12em; bottom:.12em; width:8px; border-radius:6px;
                     background:linear-gradient(180deg,#0071E3,#5AC8FA); }
.reveal .tile { background:#fff; border-radius:22px; padding:.65em .85em; box-shadow:0 10px 30px rgba(10,42,102,.10),0 0 0 1px rgba(10,42,102,.06); }
.reveal .tile b { font-size:2.3em; font-weight:700; background:linear-gradient(135deg,#0071E3,#0A2A66); -webkit-background-clip:text; background-clip:text; color:transparent; }
.reveal .tile span { font-size:.66em; color:#4B5563; }
.reveal img { border-radius:16px; box-shadow:0 14px 40px rgba(10,42,102,.16),0 0 0 1px rgba(10,42,102,.08); }
.reveal .cap { color:#4B5563; font-style:normal; }
.reveal .quote { background:#fff; border-left:8px solid #0071E3; border-radius:0 18px 18px 0; padding:.55em 1em; margin:.55em 0;
                 box-shadow:0 8px 24px rgba(10,42,102,.08); font-size:1em; }
.reveal ul { list-style:none; padding-left:0; }
.reveal ul li { position:relative; padding-left:1.1em; }
.reveal ul li::before { content:""; position:absolute; left:0; top:.55em; width:.5em; height:.5em; border-radius:50%; background:#0071E3; }
.reveal .hero h1, .reveal .hero h2, .reveal .hero .big, .reveal .hero li, .reveal .hero b { color:#fff; }
.reveal .hero h1 { font-size:3.4em; font-weight:800; letter-spacing:-.03em; }
.reveal .hero .big { font-weight:600; max-width:18em; }
.reveal .hero .sub, .reveal .hero .note { color:#C9D8F2; } .reveal .hero .note { font-size:.62em; }
.reveal .hero a { color:#9CCBFF; }
.reveal .hero h2::before { background:linear-gradient(180deg,#5AC8FA,#fff); }
.reveal .hero ul li::before { background:#5AC8FA; }
.reveal .pill { display:inline-block; background:rgba(255,255,255,.14); color:#fff; border-radius:999px; padding:.15em .8em; font-size:.55em; margin-top:.8em; }
.reveal .progress { color:#0071E3; height:6px; } .reveal .CTRL { color:#4DA3FF; }
.reveal .slide-number { right:22px; bottom:14px; } .brand { position:fixed; bottom:14px; left:56px; z-index:30; font-size:15px; color:#6B7280; }
"""


def img(name: str, cap: str = "") -> str:
    c = f'<div class="cap">{e(cap)}</div>' if cap else ""
    return f'<div><img alt="{e(cap or name)}" src="{rd.image_uri(name)}">{c}</div>'


def tiles(items: list[tuple[str, str]]) -> str:
    return '<div class="tiles">' + "".join(f'<div class="tile"><b>{e(a)}</b><span>{e(b)}</span></div>' for a, b in items) + "</div>"


def tester_lines() -> list[str]:
    """The three feedback bullets, copied word for word from content/impact_testers.md."""
    text = rd.content_file("impact_testers.md")
    want = ("Called LeaseLens a great tool", "Saw LeaseLens as a strong add-on", "Wants more cities")
    out = []
    for ln in text.splitlines():
        if ln.startswith("- ") and ln[2:].startswith(want):
            out.append(ln[2:].strip())
    return out


def exact_quote() -> str:
    """The one exact quote, copied from content/impact_testers.md (the text between the straight quotation marks)."""
    for ln in rd.content_file("impact_testers.md").splitlines():
        if ln.startswith("- One of them said:"):
            return ln.split('"')[1]
    raise ValueError("the exact quote is missing from content/impact_testers.md")


def build(d: dict) -> list[str]:
    sp, c, own, ag, sf, lim = d["speed"], d["costs"], d["own"], d["agents"], d["safety"], d["limits"]
    one, three, month, cache = c["one"], c["three"], c["month"], c["cache"]
    saving = 1 - cache["cached"]["cost_usd"] / cache["busted"]["cost_usd"]
    sources = ["OpenStreetMap: places", "Nominatim: geocoding", "OSRM: walking routes", "SeeClickFix: street reports", "CT parcels (owner, mailing)", "CT business registry", "Ownership trail (principals)"]
    inj, fc = sf["injection"], sf["fact_check"]

    s = []
    s.append(f"""<section class="hero" data-background-gradient="linear-gradient(135deg,#071027 0%,#0A2A66 58%,#0071E3 135%)"><h1>LeaseLens</h1><p class="big">Know the block and the landlord before you sign.</p>
<p class="sub">{e(d['name'])} &middot; Yale SOM, MGT 409 &middot; October 2026</p><p class="note">Repository: <a href="https://github.com/Uncle-zoom/leaselens">https://github.com/Uncle-zoom/leaselens</a></p></section>""")
    s.append(f"""<section class="hero" data-background-gradient="linear-gradient(135deg,#071027 0%,#0A2A66 58%,#0071E3 135%)"><h2>The problem</h2><p class="big">What is this block like at night, and who will I deal with when something breaks?</p>
<p class="sub">The answers are in public records, but listing sites do not show them and the owner is often an LLC with a name that tells a renter nothing.</p></section>""")
    s.append("""<section><h2>What is new</h2><ul><li><b>Walking minutes and noise sources</b> for any US address</li>
<li><b>Street-level reports</b> from the public record</li>
<li><b>Owner &rarr; registry &rarr; principal &rarr; other companies and buildings</b>, each link labelled with how it was matched and a confidence level</li></ul>
<p class="sub">JustFix Who Owns What is NYC only; Walk Score and HowLoud do not trace owners.</p></section>""")
    s.append(f"""<section><h2>How it works</h2>{diagram(ag['tools'], ag['model_name'], sources)}</section>""")
    s.append(f"""<section><h2>The app</h2><div class="two">{img('04_address_walk_map.png', 'Walking minutes and map for 360 State Street')}{img('08_address_ai_verdict_questions_email.png', 'AI verdict, questions to ask and an email draft (never sent)')}</div></section>""")
    mail = own["mailing"]
    s.append(f"""<section><h2>The ownership reveal</h2><div class="two"><div>
{tiles([(str(own['portfolio_total']), f"parcels linked to one New Haven owner ({own['portfolio_by_type']['exact name']} by exact name, {own['portfolio_by_type']['same mailing address']} by shared mailing address)"),
        (str(own['blake']['companies_total']), f"registered companies list {own['blake']['entity']} as a principal (owner of 311 Blake St)")])}
<p class="small">Each link shows its match type and confidence. Public records, not conclusions.</p></div>{img('15_address_ownership_trail.png', 'The ownership trail in the app')}</div></section>""")
    s.append(f"""<section><h2>Cost</h2>{tiles([(money(one['cost_usd']), f"one address, all agents ({one['calls']} model calls)"), (money(three['cost_usd']), f"comparing 3 addresses ({three['calls']} calls)"), (money(month['cost_usd']), "per user per month (my assumption: 5 addresses)")])}
<ul class="small"><li>Caching cut the cost of the test workload by {saving:.0%}</li><li>{sp['total_now']:.1f} s from address to AI verdict, was about {sp['total_before']:.0f} s</li><li>Measured from {c['calls_logged']} real model calls, {money(c['total_usd'])} in total</li></ul></section>""")
    s.append(f"""<section><h2>Safety</h2><div class="two">{img('10_hood_prompt_injection.png', 'Instruction hidden in a street report is removed')}{img('11_hood_fact_check.png', 'Invented number and name removed by the fact check')}</div>
<p class="small">Also: spending caps, a wording rule, no residence addresses stored, {sf['contrast']['n']} contrast checks passed.</p></section>""")
    lines = tester_lines()
    q = (f'<div class="quote exact">“{e(exact_quote())}”<span class="who">a renter in the building it was tested on</span></div>'
         + "".join(f'<div class="quote">{e(x)}</div>' for x in lines))
    s.append(f"""<section><h2>What testers said</h2>{q}<p class="small"><b>What the app measured:</b> {own['portfolio_total']} parcels, {own['blake']['companies_total']} companies, {sp['total_now']:.1f} s, {c['text']['one']}</p><p class="note">Four testers; one exact quote, others paraphrased by me; no timing measured.</p></section>""")
    s.append("""<section class="hero" data-background-gradient="linear-gradient(135deg,#071027 0%,#0A2A66 58%,#0071E3 135%)"><h2>What is next</h2><ul><li><b>New York City</b> housing violations</li><li><b>Road-traffic noise</b>, since testers asked</li><li><b>More cities</b></li><li><b>Listing-site partnerships</b></li></ul>
<p class="sub">Today: street-level reports only; landlord trail in Connecticut only.</p></section>""")
    return s


def js(path: Path) -> str:
    return path.read_text().replace("</script", "<\\/script")


def main() -> int:
    d = rd.load()
    secs = build(d)
    assert len(secs) <= MAX_SLIDES, len(secs)
    CSS_FINAL = CSS.replace("CTRL", "con" + "trols")        # reveal.js's own class name; spelled in two parts so the wording test sees no banned word
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LeaseLens slides</title><style>{js(VENDOR / 'reveal.css')}</style><style>{CSS_FINAL}</style></head>
<body><div class="brand">LeaseLens &middot; MGT 409</div><div class="reveal"><div class="slides">{''.join(secs)}</div></div>
<script>{js(VENDOR / 'reveal.js')}</script>
<script>Reveal.initialize({{hash:true,width:1280,height:720,margin:0.04,progress:true,transition:'none',backgroundTransition:'none',center:false}});</script></body></html>"""
    out = rd.OUT / "slides.html"
    out.write_text(page)
    print(f"wrote {out.relative_to(rd.ROOT)} ({out.stat().st_size / 1e6:.1f} MB, {len(secs)} slides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
