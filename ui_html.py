"""HTML snippets for cards, steps and tables. Every string that comes from data is escaped here."""
from __future__ import annotations

import html

import icons


def icon(name: str) -> str:
    return icons.svg(name, size="")


def pill(label: str, tone: str, icon_name: str) -> str:
    return f'<span class="ll-pill ll-tone-{tone}">{icon(icon_name)}<span>{html.escape(label)}</span></span>'


def card_html(title: str, s: dict | None, ai_note: str = "") -> str:
    """One result card. `s` is summary.card_summary(...) or None while nothing is known yet."""
    if s is None:
        body = '<p class="ll-load"><span class="ll-spin"></span><span>Checking this address…</span></p>'
    else:
        score = s["score"]
        facts = "".join(f"<li>{icon(i)}<span>{html.escape(t)}</span></li>" for i, t in s["facts"])
        meter = ("" if score is None else
                 f'<div class="ll-score" role="img" aria-label="Overall score {score} out of 100"><strong class="ll-num">{score}</strong>'
                 f'<span>out of 100</span></div><div class="ll-meter" aria-hidden="true"><i style="width:{score}%"></i></div>')
        src = f'<p class="ll-muted" style="margin:.1rem 0 .6rem;font-size:.9rem">Verdict from the {html.escape(s["source"])}.</p>' if s["source"] else ""
        body = f'{pill(s["badge"], s["tone"], s["icon"])}{src}{meter}<ul class="ll-facts">{facts}</ul>'
    return f'<article class="ll-card" aria-label="{html.escape(title)}"><h3 class="ll-addr">{html.escape(title)}</h3>{body}{ai_note}</article>'


STEPS = ["Finding the address", "Mapping the block", "Checking public records", "Done"]


def steps_html(done: list[bool]) -> str:
    """Step indicator. `done[k]` is True when step k has finished. Includes a polite live region for screen readers."""
    cur = next((k for k, d in enumerate(done) if not d), len(STEPS))
    items = []
    for k, name in enumerate(STEPS):
        if done[k]:
            items.append(f'<li class="done"><span class="dot">{icon("check")}</span><span>{html.escape(name)}<span class="ll-sr"> (finished)</span></span></li>')
        elif k == cur:
            items.append(f'<li class="now" aria-current="step"><span class="dot"></span><span>{html.escape(name)}…</span></li>')
        else:
            items.append(f'<li><span class="dot"></span><span>{html.escape(name)}</span></li>')
    msg = "All done. Results are ready." if cur >= len(STEPS) else f"Step {cur + 1} of {len(STEPS)}: {STEPS[cur]}."
    return f'<ol class="ll-steps" aria-label="Progress">{"".join(items)}</ol><div class="ll-sr" role="status" aria-live="polite">{html.escape(msg)}</div>'


def table_html(headers: list[str], rows: list[list], caption: str = "", num_cols: set[int] = frozenset()) -> str:
    th = "".join(f'<th scope="col">{html.escape(h)}</th>' for h in headers)
    trs = ""
    for r in rows:
        tds = "".join(f'<td class="{"num" if k in num_cols else ""}">{html.escape(str(c))}</td>' for k, c in enumerate(r))
        trs += f"<tr>{tds}</tr>"
    cap = f"<caption>{html.escape(caption)}</caption>" if caption else ""
    return f'<div class="ll-tablewrap"><table class="ll-table">{cap}<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def compare_html(labels: list[str], rows: list[dict]) -> str:
    """Head-to-head table. rows: {"name", "values": [..], "winner": index | None | "tie", "scored": bool}. The winner of a scored row
    is marked with a check icon AND the word Best."""
    th = '<th scope="col">What</th>' + "".join(f'<th scope="col">{html.escape(l)}</th>' for l in labels)
    trs = ""
    for r in rows:
        tds = ""
        for k, v in enumerate(r["values"]):
            win = r.get("winner") == k
            mark = f'<span class="ll-win">{icon("check-circle")}Best</span> ' if win else ""
            tds += f'<td class="num"><div class="ll-cell">{mark}<span class="ll-tabular">{html.escape(str(v))}</span></div></td>'
        trs += f'<tr><th scope="row">{html.escape(r["name"])}</th>{tds}</tr>'
    return (f'<div class="ll-tablewrap"><table class="ll-table"><caption>Head to head. “Best” marks the highest score in a row; '
            f'rows without it are shown for information.</caption><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')


def hero_html() -> str:
    return ('<a class="ll-skip" href="#main-content">Skip to the main content</a><div class="ll-brand">Lease<b>Lens</b></div>'
            '<section class="ll-hero" id="main-content" aria-labelledby="hero-h"><h1 id="hero-h">Know the block and the landlord before you sign.</h1>'
            '<p>Paste an address. We check what is around it and who owns it.</p></section>')


def chain_html(t: dict) -> str:
    """The ownership trail as four numbered steps, each with how it was matched and a confidence level."""
    ents = t.get("entities") or []

    def step(n, label, value, how=""):
        return (f'<li><span class="n" aria-hidden="true">{n}</span><span class="lab">{html.escape(label)}</span>'
                f'<span class="val">{value}</span>' + (f'<span class="how">{how}</span>' if how else "") + "</li>")

    def counts(items, key_a, key_b="confidence"):
        c: dict[tuple, int] = {}
        for it in items:
            k = (it[key_a], it[key_b])
            c[k] = c.get(k, 0) + 1
        return "; ".join(f"{n} by {a}, {b} confidence" for (a, b), n in sorted(c.items(), key=lambda kv: -kv[1]))

    steps = [step(1, "Owner on the parcel record", html.escape(t["owner"]))]
    if not ents:
        steps.append(step(2, "Linked entity (a company listed as a principal in the state registry)", "None",
                          "No company is listed as a principal, so the trail stops here."))
    else:
        steps.append(step(2, "Linked entity (a company listed as a principal in the state registry)", html.escape(" and ".join(e["name"] for e in ents)),
                          "; ".join((f"{html.escape(e['name'])}: the registry lists the company as its own principal, {e['confidence']} confidence"
                                     if e.get("is_owner_itself") else
                                     f"{html.escape(e['name'])}: {html.escape(e['matched_how'])}, {e['confidence']} confidence") for e in ents)))
        comps = [c for e in ents for c in e["companies"]]
        total, shown = t["companies_total"], t["companies_shown"]
        minimum = "at least " if any(e["related_total_is_minimum"] for e in ents) else ""
        steps.append(step(3, "Other registered companies that list the same principal", f"{minimum}{total} related {'company' if total == 1 else 'companies'}"
                          + (f' <span class="lab">(showing {shown} of {minimum}{total})</span>' if shown < total else ""),
                          html.escape(counts(comps, "matched_how")) if comps else "No other registered company lists this principal."))
        parcels = t["parcels"]
        steps.append(step(4, "Buildings (parcels) owned by those companies", f"{t['parcels_total']} {'building' if t['parcels_total'] == 1 else 'buildings'}"
                          + (f' <span class="lab">(showing {t["parcels_shown"]} of {t["parcels_total"]})</span>' if t["parcels_shown"] < t["parcels_total"] else ""),
                          html.escape(counts(parcels, "match_type")) if parcels else "None of those companies appears as an owner in the Connecticut parcel data."))
    return f'<ol class="ll-chain" aria-label="Ownership trail">{"".join(steps)}</ol>'
