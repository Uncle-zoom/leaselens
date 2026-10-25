"""One address's fetched facts, as the data block every agent reads (and the fact check compares against).

Everything written by residents or registries (SeeClickFix titles, owner and registry names) is passed
through guardrails.sanitize here, so it reaches the model as inert data and never reaches a system prompt.
"""
from __future__ import annotations

from sources.ct import property_type
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field

import analysis
from sources.matching import split_street_address
import sections
from guardrails import FactIndex, sanitize


FILTER_ENABLED = True   # the untrusted-text filter. Switched off ONLY by safety_live.py, to show what the real model does without it.


@contextmanager
def filter_disabled():
    """For the live safety test only: build fact sheets with the untrusted-text filter off."""
    global FILTER_ENABLED
    FILTER_ENABLED = False
    try:
        yield
    finally:
        FILTER_ENABLED = True


@dataclass
class FactSheet:
    address: str
    data: dict
    text: str = ""
    flagged: list[str] = field(default_factory=list)   # untrusted strings that were cleaned (for the audit note)
    index: FactIndex | None = None

    def __post_init__(self):
        self.text = json.dumps(self.data, indent=1, ensure_ascii=False)
        self.index = FactIndex.build(self.text)

    def block(self) -> str:
        return f"<data>\n{self.text}\n</data>"


def _clean(value, flagged: list[str], limit: int = 120):
    if value in (None, ""):
        return value
    if not FILTER_ENABLED:
        return str(value)
    text, was = sanitize(str(value), limit)
    if was:
        flagged.append(str(value)[:200])
    return text


def _trail_on_this_street(address: str, trail: dict | None, flagged: list[str]) -> list[dict]:
    """Parcels of companies linked through a principal that sit on the same street, within 60 numbers of this address (e.g. 777-799 Main St)."""
    if not trail:
        return []
    num, street = split_street_address(address)
    if not num.isdigit():
        return []
    out = []
    for p in trail.get("parcels") or []:
        n2, s2 = split_street_address(re.sub(r"^(\d+)-\d+", r"\1", p.get("location") or ""))       # '777-799 MAIN ST' starts at 777
        if s2 == street and n2.isdigit() and abs(int(n2) - int(num)) <= 60:
            out.append({"address": _clean(p["location"], flagged), "owner_company": _clean(p["company"], flagged),
                        "linked_through": _clean(p["entity"], flagged), "how_matched": p["match_type"], "confidence": p["confidence"]})
    return out[:10]


def build_fact_sheet(address: str, geo: dict | None, block: dict | None, street, landlord: dict | None,
                     prefs: analysis.Prefs, in_ct: bool, coming_soon: tuple = (), trail: dict | None = None) -> FactSheet:
    flagged: list[str] = []
    d: dict = {"address": address}
    if geo:
        d["area"] = ", ".join(x for x in (geo.get("city"), geo.get("state")) if x)
    d["my_priorities"] = {"longest_walk_to_grocery_minutes": prefs.max_grocery,
                          "longest_walk_to_gym_minutes": prefs.max_gym,
                          "longest_walk_to_transit_minutes": prefs.max_transit,
                          "night_time_quiet_matters": prefs.quiet}
    d["search_windows"] = {"places_and_noise_radius_m": analysis.RADIUS_M, "street_reports_radius_m": 200,
                           "street_reports_period": "last 12 months", "street_reports_period_months": 12}
    places, walking = (block or {}).get("places"), (block or {}).get("walking")
    if places is not None and places.ok:
        wk = walking.data if walking is not None and walking.ok else None
        d["scores"] = analysis.score_address(places.data, wk, prefs)
        sec = sections.block_section(places, walking, prefs)
        d["walking"] = [{"place_type": r["label"], "nearest": r["nearest"] or "none within 800 m",
                         "walk_minutes": r["walk_min"], "my_limit_minutes": r["limit"],
                         "meets_limit": r["meets"]} for r in sec["rows"]]
        nz = sections.noise_section(places)
        d["noise_within_800m"] = [{"type": r["label"], "count": r["count"], "nearest": r["nearest"],
                                  "nearest_distance_m": r["nearest_m"]} for r in nz["rows"]]
    else:
        d["walking"] = d["noise_within_800m"] = "not available (nearby places could not be loaded)"

    st = sections.street_section(street, in_ct)
    if st["error"]:
        d["street_reports"] = {"available": False, "reason": st["error"]}
    else:
        recent = [_clean(r["summary"] or r["request_type"], flagged, 100) for r in (street.data.get("recent") or [])]
        d["street_reports"] = {
            "what_this_is": "street-level reports by residents about the public street, not housing complaints",
            "radius_m": st["radius_m"], "since": st["since"], "total": st["total"],
            "by_type": [{"type": _clean(r["request_type"], flagged), "reports": r["count"], "still_open": r["open"]}
                        for r in st["rows"][:8]],
            "recent_report_titles": recent}
        if st.get("coverage_note"):
            d["street_reports"]["coverage_note"] = st["coverage_note"]

    ll = sections.landlord_section((landlord or {}).get("parcels"), (landlord or {}).get("registry"),
                                   (landlord or {}).get("portfolio"), in_ct, coming_soon)
    if not ll["available"]:
        d["landlord"] = {"available": False, "reason": ll["note"]}
    else:
        out: dict = {"available": True}
        if ll["errors"].get("parcel"):
            out["parcel_record"] = ll["errors"]["parcel"]
        else:
            p = ll["parcel"]
            out["parcel_record"] = {"owner": _clean(p["owner"], flagged), "co_owner": _clean(p["co_owner"], flagged),
                                    "property": p["location"], "property_use": p["use"], "year_built": p["year_built"],
                                    "tax_bill_mailing_address": _clean(p["mailing"], flagged)}
            if (ll.get("property") or {}).get("message"):
                out["parcel_record"]["property_note"] = ll["property"]["message"]
        if ll["registry"]:
            r = ll["registry"]
            out["business_registry"] = {
                "name": _clean(r["name"], flagged), "entity_type": r["entity_type"], "status": r["status"],
                "formed_in": r["formed_in"], "registered": r["registered"],
                "business_address": _clean(r["business_address"], flagged),
                "registered_agents": [_clean(a, flagged) for a in r["agents"]],
                "principals": [_clean(a, flagged) for a in r["principals"]],
                "matched_to_parcel_owner_by": r["matched_how"], "match_confidence": r["confidence"]}
        else:
            out["business_registry"] = ll["errors"].get("registry", "not searched")
        if ll["portfolio"]:
            pf = ll["portfolio"]
            out["other_parcels_linked_to_owner"] = {
                "total": pf["total"], "count_by_match_type": pf["by_type"],
                "different_owner_names_at_same_mailing_address": pf["distinct_owner_names_at_mailing_address"],
                "examples": [{"address": _clean(r["Address"], flagged), "owner_on_record": _clean(r["Owner on record"], flagged),
                              "how_matched": r["How matched"], "confidence": r["Confidence"]} for r in pf["rows"][:10]]}
        else:
            out["other_parcels_linked_to_owner"] = ll["errors"].get("portfolio", "not searched")
        near = _trail_on_this_street(address, trail, flagged) if (ll.get("property") or {}).get("kind") not in property_type.HIDDEN_KINDS else []
        if near:
            out["ownership_trail"] = {"linked_entity": [_clean(e["name"], flagged) for e in trail["entities"]],
                                      "related_companies_total": trail["companies_total"],
                                      "related_company_parcels_on_this_street": near}
        d["landlord"] = out
    return FactSheet(address, d, flagged=flagged)


def section(sheet: FactSheet, name: str) -> dict | list | str:
    """Read-only access used by the chat agent's tools."""
    aliases = {"priorities": "my_priorities", "noise": "noise_within_800m"}
    key = aliases.get(name, name)
    return sheet.data.get(key, f"no section called {name!r}")
