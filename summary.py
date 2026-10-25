"""Plain-language summaries for the cards and the one-sentence answers on the address view. Pure functions: no Streamlit,
no network. Everything stated here comes from numbers already computed by analysis.py / sections.py."""
from __future__ import annotations

from sources.ct import property_type
import analysis
from wording import plural, walk_phrase

# AI verdict (models.py) -> what the renter sees
COULDNT_CHECK = "couldn't check right now"
COULDNT_CHECK_PLACES = ("We couldn't check what's around this address right now: the OpenStreetMap servers did not answer in time. "
                        "That is different from finding nothing. Try again in a few minutes.")
COULDNT_CHECK_STREET = "We couldn't check street-level reports right now. That is different from finding none. Try again in a few minutes."
SINGULAR = {"Bars": "bar", "Pubs": "pub", "Nightclubs": "nightclub", "Fire stations": "fire station", "Hospitals": "hospital", "Rail lines": "rail line"}
VERDICT_UI = {"hidden gem": ("Great fit", "great", "check"), "fine": ("Good", "good", "minus"), "think twice": ("Think twice", "warn", "alert")}


def verdict_from_score(score: float | None) -> str | None:
    """A quick read from the 0-100 score, used only while no AI verdict exists."""
    if score is None:
        return None
    return "hidden gem" if score >= 70 else "fine" if score >= 45 else "think twice"


def quiet_phrase(quiet_score: float | None) -> str:
    if quiet_score is None:
        return "Night: still checking"
    return "Night: calm" if quiet_score >= 70 else "Night: lively" if quiet_score >= 40 else "Night: busy"


def _minutes(x: float) -> str:
    return f"{x:g}"


def transit_fact(rows: list[dict]) -> tuple[str, float | None]:
    by = {r["category"]: r for r in rows}
    cands = [(by[c]["walk_min"], lab) for c, lab in (("bus_stop", "Bus"), ("train_station", "Train")) if c in by and by[c]["walk_min"] is not None]
    if not cands:
        return "Transit: none within 800 m", None
    m, lab = min(cands)
    row = next(r for r in rows if r["walk_min"] == m and r["category"] in ("bus_stop", "train_station"))
    return f"{lab} {walk_phrase(m, row.get('walk_m'))}", m


LEVEL = {"think twice": 0, "fine": 1, "hidden gem": 2}
_WEAK = {"Gym": "gym", "Transit": "transit", "Groceries": "groceries"}


def main_reason(verdict: str | None, scores: dict | None, walk_rows: list[dict] | None) -> str:
    """The one thing that most explains the verdict, from the same numbers the score uses (not from the AI's wording)."""
    if not scores:
        return ""
    if verdict == "hidden gem":
        return "close to what you need"
    cats = {c: scores.get(c) for c in ("Quiet", "Gym", "Transit", "Groceries") if scores.get(c) is not None}
    worst, sc = min(cats.items(), key=lambda kv: kv[1]) if cats else (None, 100)
    if worst is None or sc >= 60:
        return "a few things to check"
    if worst == "Quiet":
        return "noisy at night" if sc < 40 else "lively at night"
    rows = {r["category"]: r for r in (walk_rows or [])}
    if worst == "Gym":
        return "no gym nearby" if not rows.get("gym") or rows["gym"]["walk_min"] is None else "gym farther than you like"
    if worst == "Transit":
        return "far from transit"
    return "far from groceries"


DISAGREE_NOTE = ("Why a verdict and a score can differ: the score rates walking convenience against your priorities; "
                 "the AI verdict also weighs noise, street reports and owner records.")


def disagreement_note(ai_verdict: str | None, score: float | None, reason: str) -> str:
    """One line shown only when the AI verdict and the 0-100 score point different ways."""
    quick = verdict_from_score(score)
    if ai_verdict is None or quick is None or LEVEL[ai_verdict] == LEVEL[quick]:
        return ""
    return DISAGREE_NOTE


def card_summary(scores: dict | None, walk_rows: list[dict] | None, portfolio_total: int | None, in_ct: bool,
                 landlord_known: bool, ai_verdict: str | None = None, block_failed: bool = False, prop: dict | None = None) -> dict:
    """What one result card shows: verdict, score and four plain-language facts."""
    verdict, source = ai_verdict, "AI team"
    if verdict is None:
        verdict, source = verdict_from_score((scores or {}).get("Overall")), "quick read from your priorities"
    label, tone, icon = VERDICT_UI.get(verdict, ("Checking…", "neutral", "info")) if verdict else ("Checking…", "neutral", "info")
    facts = []
    if block_failed and (walk_rows is None or scores is None):      # the lookup failed: say so, never "none within 800 m"
        facts += [("basket", f"Grocery: {COULDNT_CHECK}"), ("moon", f"Night: {COULDNT_CHECK}"), ("bus", f"Transit: {COULDNT_CHECK}")]
    elif walk_rows is None or scores is None:
        facts += [("basket", "Grocery: mapping the block…"), ("moon", "Night: mapping the block…"), ("bus", "Transit: mapping the block…")]
    else:
        g = next((r for r in walk_rows if r["category"] == "grocery"), None)
        facts.append(("basket", f"Grocery {walk_phrase(g['walk_min'], g.get('walk_m'))}" if g and g["walk_min"] is not None else "Grocery: none within 800 m"))
        facts.append(("moon", quiet_phrase(scores.get("Quiet"))))
        facts.append(("bus", transit_fact(walk_rows)[0]))
    kind = (prop or {}).get("kind")
    if not in_ct:
        facts.append(("key", "Owner records: not available in this state yet"))
    elif landlord_known and kind == "condo_no_master":
        facts.append(("key", "Condo building: no single owner in the data"))
    elif landlord_known and kind == "private_owner":
        facts.append(("key", "Private owner: name not shown"))
    elif landlord_known and kind == "private_home":
        facts.append(("key", "Private home: may not be a rental"))
    elif landlord_known and kind == "not_housing":
        facts.append(("key", f"Not housing: {property_type.not_housing_label(prop['use'])}"))
    elif landlord_known and kind == "condo_association":
        facts.append(("key", "Condo association record"))
    elif not landlord_known:
        facts.append(("key", "Owner: checking public records…"))
    elif portfolio_total is None:
        facts.append(("key", "Owner: no parcel record found"))
    elif portfolio_total == 0:
        facts.append(("key", "Owner holds no other parcels"))
    else:
        facts.append(("key", f"Owner holds {portfolio_total} other parcel{'s' if portfolio_total != 1 else ''}"))
    if block_failed and not verdict:
        label, tone, icon = "Couldn't check the block", "neutral", "info"
    reason = main_reason(verdict, scores, walk_rows) if verdict else ""
    if kind == "not_housing" and landlord_known:       # no rental verdict for a building the parcel record does not list as housing
        label, tone, icon, verdict, reason = "Not housing", "neutral", "info", None, property_type.not_housing_label(prop["use"])
    score = (scores or {}).get("Overall")
    return {"verdict": verdict, "label": label, "tone": tone, "icon": icon, "source": source if verdict else "",
            "reason": reason, "badge": f"{label} · {reason}" if reason else label,
            "note": disagreement_note(ai_verdict, score, reason) if ai_verdict else "",
            "score": round(score) if score is not None else None, "facts": facts}


def on_foot(minutes: float, metres: float | None, away: bool = False) -> str:
    """'next door', 'under 1 minute on foot' or '2.2 minutes on foot' (with away=True: '... away')."""
    if metres is not None and metres < 50:
        return "next door"
    if minutes < 1:
        return "under 1 minute " + ("away" if away else "on foot")
    return f"{_minutes(minutes)} {'minute' if minutes == 1 else 'minutes'} " + ("away" if away else "on foot")


def chain_headline(t: dict | None) -> str:
    """'Owner -> linked entity -> N related companies -> M buildings' as one line (the same words as the map caption)."""
    if not t:
        return ""
    ents = t.get("entities") or []
    if not ents:
        return "Owner → no company principal to follow"
    names = " and ".join(e["name"] for e in ents)
    return f"Owner → {names} → {_plural(t['companies_total'], 'related company').replace('companys', 'companies')} → {_plural(t['parcels_total'], 'building')}"


def chain_sentence(t: dict | None) -> str:
    if not t:
        return ""
    ents = t.get("entities") or []
    if not ents:
        return "Its registry entry lists no company as a principal, so there is no further link to follow."
    e = ents[0]
    n = t["companies_total"]
    s = ("The registry lists the company as its own principal" if e.get("is_owner_itself")
         else f"Its registry entry lists {e['name']} as a principal")
    if n == 0:
        return s + "; no other registered company lists the same principal."
    return (s + f"; {n} other registered {'company lists' if n == 1 else 'companies list'} the same principal name, "
            f"linked to {_plural(t['parcels_total'], 'building')} in the parcel data.")


def _place(name: str) -> str:
    """'DELAWARE' -> 'Delaware', but keep 'CT' as it is."""
    return name if len(name) <= 3 else name.title()


def _plural(n: int, word: str) -> str:
    return plural(n, word)


def answers(address: str, scores: dict | None, walk_rows: list[dict] | None, noise_rows: list[dict] | None, street: dict | None,
            landlord: dict | None, ai_questions: list[str] | None, in_ct: bool, trail: dict | None = None,
            block_failed: bool = False) -> dict[str, str]:
    """One sentence per question on the address view."""
    out = {}
    if walk_rows is None:
        out["walk"] = COULDNT_CHECK_PLACES if block_failed else "Still mapping the block…"
    else:
        by = {r["category"]: r for r in walk_rows}
        bits = []
        g = by.get("grocery")
        bits.append(f"The nearest grocery is {g['nearest']}, {on_foot(g['walk_min'], g.get('walk_m'))}" if g and g["walk_min"] is not None
                    else "There is no grocery within 800 m")
        gy = by.get("gym")
        bits.append(f"a gym is {on_foot(gy['walk_min'], gy.get('walk_m'), away=True)}" if gy and gy["walk_min"] is not None else "no gym within 800 m")
        t, _ = transit_fact(walk_rows)
        bits.append(t[0].lower() + t[1:])
        out["walk"] = "; ".join(bits) + "."
    if noise_rows is None:
        out["noise"] = COULDNT_CHECK_PLACES if block_failed else "Still mapping the block…"
    else:
        shown = [(r["count"], r["label"]) for r in noise_rows if r["count"]]
        shown.sort(reverse=True)
        words = ", ".join(plural(c, SINGULAR.get(lab, lab.lower().rstrip("s")), lab.lower()) for c, lab in shown[:3]) or "no bars, clubs, fire stations or rail lines"
        feel = quiet_phrase((scores or {}).get("Quiet")).replace("Night: ", "") + " at night"
        out["noise"] = f"Expect it to be {feel}: {words} within 800 m."
    if street is not None and street.get("error"):         # a failed lookup is neither "still checking" nor "none"
        out["street"] = COULDNT_CHECK_STREET if in_ct else "Street-level reports are only connected for Connecticut so far."
    elif street is None:
        out["street"] = ("Street-level reports are only connected for Connecticut so far." if not in_ct else "Still checking street-level reports…")
    else:
        top = street["rows"][0]["request_type"] if street.get("rows") else None
        out["street"] = (f"{_plural(street['total'], 'street-level report')} in the last 12 months within 200 m"
                         + (f", mostly “{top}”" if top else "") + ". These describe the street, not the building."
                         + (f" {street['coverage_note']}" if street.get("coverage_note") else ""))
    if not in_ct:
        out["owner"] = "Landlord data is not available in this state yet."
    elif landlord is None:
        out["owner"] = "Still checking public records…"
    elif landlord.get("errors", {}).get("parcel"):
        out["owner"] = "We could not find a parcel record for this address."
    else:
        p, r, pf = landlord.get("parcel") or {}, landlord.get("registry"), landlord.get("portfolio")
        prop = landlord.get("property") or {}
        if prop.get("kind") in property_type.HIDDEN_KINDS:
            out["ask"] = (ai_questions[0] if ai_questions else "Run the AI team to get three questions to ask and a draft email.")
            out["owner"] = prop["message"]
            return out
        s = (prop["message"] + " ") if prop.get("kind") in ("condo_association", "not_housing") else ""
        s += f"The parcel record lists {p.get('owner')} as the owner"
        if r:
            s += f" ({r['entity_type']}, {r['status'].lower()}, formed in {_place(r['formed_in'])})"
        s += "."
        if pf:
            s += (f" The same owner name or mailing address appears on {_plural(pf['total'], 'other parcel')}." if pf["total"]
                  else " We found no other parcels under the same owner name or mailing address.")
        out["owner"] = s + ((" " + chain_sentence(trail)) if trail else "")
    out["ask"] = (ai_questions[0] if ai_questions else "Run the AI team to get three questions to ask and a draft email.")
    return out


def map_text_alternative(places_data: dict | None, walk_rows: list[dict] | None, failed: bool = False) -> list[str]:
    """A short list that says what the map shows, for people who cannot see it."""
    if not places_data:
        return ["We couldn't check the places around this address right now, so none are drawn."] if failed else ["The map is still loading."]
    items = []
    for cat, label in (("grocery", "Grocery"), ("gym", "Gym"), ("park", "Park"), ("bus_stop", "Bus stop"), ("train_station", "Train or subway")):
        near = next((p for p in places_data["results"] if p["category"] == cat), None)
        if near:
            items.append(f"{label}: {near['name'] or label.lower()}, {near['distance_m']} m away")
    counts = places_data.get("counts", {})
    noisy = ", ".join(plural(counts[c], c.replace("_", " ")) for c in ("nightclub", "bar", "pub", "fire_station", "hospital", "rail_line") if counts.get(c))
    items.append("Noise sources within 800 m: " + (noisy or "none"))
    return items
