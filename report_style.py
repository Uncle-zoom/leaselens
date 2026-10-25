"""Shared look and small drawing helpers for report.html and slides.html (same colours and type as the app: see styles.TOKENS)."""
from __future__ import annotations

import html

import styles

L = styles.TOKENS["light"]
FONT = "Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
e = html.escape


from tokenomics import money  # noqa: E402,F401  (one formatter for every dollar amount)


def thousands(x: float) -> str:
    return f"{x:,.0f}"


BASE_CSS = f"""
:root {{ --bg:{L['bg']}; --card:{L['card']}; --text:{L['text']}; --text2:{L['text2']}; --accent:{L['accent']}; --link:{L['accent_text']};
        --green:{L['green']}; --orange:{L['orange']}; --red:{L['red']}; --hair:rgba(0,0,0,.10); }}
* {{ box-sizing:border-box; }}
body {{ font-family:{FONT}; color:var(--text); background:var(--bg); margin:0; line-height:1.5; }}
a {{ color:var(--link); }}
.note {{ color:#767676; font-size:.82em; }}
.num {{ font-variant-numeric:tabular-nums; }}
"""

REPORT_CSS = BASE_CSS + f"""
.page {{ max-width:8.5in; margin:0 auto; padding:.55in .6in; background:#fff; font-size:10pt; }}
h1 {{ font-size:34pt; letter-spacing:-.03em; margin:.1em 0 .1em; line-height:1.05; }}
h2 {{ font-size:17pt; letter-spacing:-.02em; margin:1.3em 0 .35em; padding-top:.6em; border-top:2px solid var(--accent); break-after:avoid; }}
h3 {{ font-size:12pt; margin:1.1em 0 .25em; break-after:avoid; }}
h4 {{ font-size:10.5pt; margin:.9em 0 .15em; break-after:avoid; }}
p, li {{ margin:.35em 0; }} ul {{ padding-left:1.2em; margin:.3em 0; }}
.sub {{ font-size:14pt; color:var(--text2); margin:.1em 0 .6em; }}
.byline {{ color:var(--text2); }}
.pitch {{ font-size:12.5pt; line-height:1.4; margin:.7em 0; }}
.stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:.5em; margin:.8em 0; }}
.stat {{ background:var(--bg); border-radius:12px; padding:.6em .7em; }}
.stat b {{ display:block; font-size:17pt; letter-spacing:-.02em; }} .stat span {{ color:var(--text2); font-size:8.5pt; }}
table {{ width:100%; border-collapse:collapse; font-size:8.8pt; margin:.5em 0; break-inside:avoid; }}
th, td {{ text-align:left; padding:.35em .5em; border-bottom:1px solid var(--hair); vertical-align:top; }}
th {{ background:var(--bg); font-weight:600; }}
td.n, th.n {{ text-align:right; }}
figure {{ margin:.6em 0; break-inside:avoid; }}
figure img {{ max-width:100%; max-height:3.3in; border:1px solid var(--hair); border-radius:10px; display:block; }}
figure.wide img {{ max-height:3.9in; }} figure.tall img {{ max-height:4.3in; }}
figcaption {{ color:var(--text2); font-size:8.5pt; margin-top:.25em; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:.8em; align-items:start; }}
.callout {{ background:var(--bg); border-radius:12px; padding:.6em .8em; margin:.6em 0; break-inside:avoid; }}
.ok {{ color:var(--green); font-weight:600; }} .bad {{ color:var(--red); font-weight:600; }}
code {{ font-family:ui-monospace,Menlo,monospace; font-size:.9em; background:var(--bg); padding:0 .25em; border-radius:4px; }}
pre {{ background:var(--bg); padding:.5em .7em; border-radius:8px; white-space:pre-wrap; font-size:8.3pt; margin:.4em 0; break-inside:avoid; }}
svg text {{ font-family:{FONT}; }}
.src {{ color:var(--text2); font-size:8pt; }}
.verbatim {{ border-left:3px solid var(--accent); padding-left:.8em; margin:.5em 0; }}
@page {{ size:Letter; margin:0; }}
@media print {{ body {{ background:#fff; }} .page {{ padding:.5in .6in; max-width:none; }} a {{ color:inherit; text-decoration:none; }}
  * {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }} }}
"""


def bars(items: list[tuple[str, float, str]], unit: str, width: int = 520, fmt=lambda v: f"{v:.1f}") -> str:
    """Horizontal bars. items: (label, value, colour). Labels and values are real numbers passed in by the caller."""
    top = max(v for _, v, _ in items) or 1
    row, h = 26, 26 * len(items) + 8
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" aria-label="Bar chart">']
    for i, (label, v, color) in enumerate(items):
        y = 4 + i * row
        w = max(2, (width - 230) * v / top)
        out.append(f'<text x="0" y="{y + 15}" font-size="11" fill="{L["text"]}">{e(label)}</text>'
                   f'<rect x="170" y="{y + 2}" width="{w:.0f}" height="16" rx="4" fill="{color}"/>'
                   f'<text x="{170 + w + 6:.0f}" y="{y + 15}" font-size="11" fill="{L["text"]}" class="num">{e(fmt(v))} {e(unit)}</text>')
    out.append("</svg>")
    return "".join(out)


def diagram(tools: list[str], model: str, sources: list[str], width: int = 900) -> str:
    """The data flow: address -> router -> sources -> fact sheet -> agents (+ chat tools) -> code checks -> page. Labels come from the code."""
    def box(x, y, w, h, title, lines, fill="#fff", stroke="#c7c7cc", bold=True):
        t = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
        t += f'<text x="{x + 10}" y="{y + 19}" font-size="12.5" font-weight="{600 if bold else 400}" fill="{L["text"]}">{e(title)}</text>'
        for i, ln in enumerate(lines):
            t += f'<text x="{x + 10}" y="{y + 36 + i * 14}" font-size="10" fill="{L["text2"]}">{e(ln)}</text>'
        return t

    def arrow(x1, y1, x2, y2):
        return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{L["accent"]}" stroke-width="1.8" fill="none" marker-end="url(#ah)"/>'

    s = [f'<svg viewBox="0 0 {width} 436" width="100%" role="img" aria-label="Agents, tools and data flow">',
         f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{L["accent"]}"/></marker></defs>']
    s.append(box(8, 150, 100, 70, "Address", ["typed by the", "renter (up to 3)"]))
    s.append(box(130, 150, 110, 70, "Router", ["US: block report", "CT: + landlord data", "NYC: parked"], stroke=L["accent"]))
    s.append(box(262, 20, 190, 190, "Public data (free, no keys)", [x for x in sources], fill="#f5f9ff"))
    s.append(box(262, 230, 190, 70, "Saved samples", ["Demo mode and any", "failed call fall back here"], fill="#fafafa"))
    s.append(box(474, 120, 130, 120, "Fact sheet", ["numbers, names,", "walking minutes,", "owner records;", "public text cleaned", "of instructions"], stroke=L["accent"]))
    s.append(box(626, 14, 160, 62, "Block analyst", ["verdict + 3 reasons"], fill="#f2faf4"))
    s.append(box(626, 84, 160, 62, "Landlord analyst", ["plain English + 3 questions"], fill="#f2faf4"))
    s.append(box(626, 154, 160, 62, "Negotiator", ["email draft (never sent)"], fill="#f2faf4"))
    s.append(box(626, 224, 160, 62, "Coordinator", ["ranks 2+ addresses"], fill="#f2faf4"))
    s.append(box(626, 294, 160, 78, "Chat agent", [f"tools: {tools[0]}", f"{tools[1]}", "answers only from the data"], fill="#f2faf4"))
    s.append(box(806, 60, 88, 335, "Code checks", ["fact check", "", "wording rule", "", "request, token,", "dollar caps", "", "usage log"], fill="#fff7ec", stroke=L["orange"]))
    s.append(box(474, 330, 130, 70, "Page", ["cards, address view,", "compare, copy email"], fill="#fff"))
    s.append(f'<text x="8" y="424" font-size="10.5" fill="{L["text2"]}">All five agents: {e(model)} through Portkey (PydanticAI).</text>')
    for a in (arrow(108, 185, 130, 185), arrow(240, 175, 262, 140), arrow(452, 150, 474, 170), arrow(452, 265, 474, 215), arrow(604, 170, 626, 45),
              arrow(604, 175, 626, 115), arrow(604, 185, 626, 185), arrow(604, 195, 626, 255), arrow(604, 210, 626, 330), arrow(786, 185, 806, 185),
              arrow(806, 385, 604, 385)):
        s.append(a)
    s.append("</svg>")
    return "".join(s)
