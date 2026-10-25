"""Builders for each section of an address card. Pure data in, plain dicts out (so they are testable offline).

Every section carries its own `error` message and the `source` it cites, so one failure never breaks the page.
"""
from __future__ import annotations

import html

import folium

import analysis
from sources.common import SourceResult
from sources.ct import property_type

CITE = {
    "osm": ("OpenStreetMap via Overpass API", "https://overpass-api.de/api/interpreter"),
    "walking": ("OSRM foot routing (routing.openstreetmap.de), else straight-line x 1.3 at 5 km/h",
                "https://routing.openstreetmap.de/routed-foot/"),
    "seeclickfix": ("SeeClickFix public API v2 (issues)", "https://seeclickfix.com/api/v2/issues"),
    "parcels": ("2026 Connecticut Parcel and CAMA Data, CT Office of Policy and Management (data.ct.gov ibe8-9i3q)",
                "https://data.ct.gov/resource/ibe8-9i3q.json"),
    "registry": ("Connecticut Business Registry: Business Master n7gp-d28j, Principals ka36-64k6, Agents qh2m-n44y",
                 "https://data.ct.gov/resource/n7gp-d28j.json"),
}


def origin_label(res: SourceResult | None) -> str:
    if res is None:
        return ""
    return {"live": "live data", "cache": "cached live data", "sample": "saved sample (offline)"}.get(res.origin, "")


def _err(res: SourceResult | None, what: str) -> str | None:
    if res is None:
        return f"{what} is not available for this address."
    if not res.ok:
        why = res.live_error or res.error or "unknown error"
        return f"{what} could not be loaded ({why[:160]})."
    return None


# ------------------------------------------------------------------ block (walking) and noise
def block_section(places: SourceResult | None, walking: SourceResult | None, prefs: analysis.Prefs) -> dict:
    err = _err(places, "Nearby places")
    if err:
        return {"error": err, "rows": [], "cite": CITE["osm"]}
    rows = analysis.walk_table(places.data, walking.data if walking and walking.ok else None, prefs)
    return {"error": None, "rows": rows, "origin": origin_label(places), "cite": CITE["osm"], "walk_cite": CITE["walking"],
            "radius_m": places.data["radius_m"]}


def noise_section(places: SourceResult | None) -> dict:
    err = _err(places, "Noise sources")
    if err:
        return {"error": err, "rows": [], "cite": CITE["osm"]}
    return {"error": None, "rows": analysis.noise_table(places.data), "load": analysis.noise_load(places.data),
            "origin": origin_label(places), "cite": CITE["osm"]}


# ------------------------------------------------------------------ street conditions
NO_REPORTS_NOTE = "SeeClickFix use varies by city; 0 may mean little coverage."


def street_section(complaints: SourceResult | None, in_ct: bool) -> dict:
    cite = CITE["seeclickfix"]
    if not in_ct:
        return {"error": "Street-level reports are only connected for Connecticut so far.", "rows": [], "cite": cite}
    err = _err(complaints, "Street-level reports")
    if err:
        return {"error": err, "rows": [], "cite": cite}
    d = complaints.data
    return {"error": None, "rows": d["results"], "total": d["total_issues"], "since": d["since"],
            "radius_m": d["radius_m"], "origin": origin_label(complaints), "cite": cite,
            "label": "Street-level reports, not housing complaints",
            "coverage_note": NO_REPORTS_NOTE if not d["total_issues"] else None}


# ------------------------------------------------------------------ landlord
def landlord_section(parcels: SourceResult | None, registry: SourceResult | None,
                     portfolio: SourceResult | None, in_ct: bool, coming_soon: tuple = ()) -> dict:
    if not in_ct:
        note = ("Landlord data is not available in this state yet."
                + (f" {', '.join(coming_soon)} is coming soon." if coming_soon else ""))
        return {"available": False, "note": note}
    out = {"available": True, "parcel": None, "registry": None, "portfolio": None,
           "errors": {}, "cites": {"parcel": CITE["parcels"], "registry": CITE["registry"], "portfolio": CITE["parcels"]}}
    if (e := _err(parcels, "The parcel record")):
        out["errors"]["parcel"] = e
        return out
    p = parcels.data["primary"]
    prop = parcels.data.get("property") or {"kind": "standard", "message": None}
    out["property"] = prop
    out["parcel"] = {
        "owner": p.get("owner"), "co_owner": p.get("co_owner"), "location": property_type.location_label(p.get("location"), p.get("unit"), building_only=prop["kind"] == "condo_no_master"),
        "mailing": ", ".join(x for x in (p.get("mailing_address"), p.get("mailing_address_2"), p.get("mailing_city"),
                                         p.get("mailing_state"), p.get("mailing_zip")) if x),
        "use": property_type.use_label(p.get("state_use_description")), "year_built": (p.get("ayb") or "").split(".")[0] or None,
        "last_sale": p.get("sale_date", "").split(" ")[0] or None, "origin": origin_label(parcels),
        "records_at_address": parcels.count}
    if registry is None or not registry.ok:
        out["errors"]["registry"] = ("No Business Registry record was found for this owner name. The owner may be a person, "
                                     "a trust, or a company registered elsewhere." if registry is not None else
                                     "The Business Registry was not searched.")
    else:
        b = registry.data["business"]
        out["registry"] = {
            "name": b.get("name"), "entity_type": b.get("business_type"), "status": b.get("status"),
            "formed_in": b.get("formation_place"), "registered": (b.get("date_registration") or "").split("T")[0],
            "business_address": ", ".join(x for x in (b.get("billingstreet"), b.get("billing_unit"), b.get("billingcity"),
                                                      b.get("billingstate"), b.get("billingpostalcode")) if x),
            "agents": [a["name__c"] for a in registry.data["registered_agents"]],
            "principals": [p_["name__c"] for p_ in registry.data["principals"]],
            "matched_how": registry.data["matched_how"], "confidence": registry.data["confidence"],
            "origin": origin_label(registry)}
    if portfolio is None or not portfolio.ok:
        out["errors"]["portfolio"] = _err(portfolio, "The other-parcels search") or "The other-parcels search did not run."
    else:
        d = portfolio.data
        out["portfolio"] = {
            "total": d["total_matches"], "by_type": d["counts_by_match_type"], "shown": len(d["results"]),
            "distinct_owner_names_at_mailing_address": d["distinct_owner_names_at_mailing_address"],
            "rows": [{"Address": " ".join(m.get("location", "").split()), "Owner on record": m.get("owner"),
                      "How matched": m["match_type"], "Confidence": m["confidence"], "Why": m["reason"]}
                     for m in d["results"]],
            "origin": origin_label(portfolio)}
    if prop["kind"] in property_type.HIDDEN_KINDS:
        out["registry"] = out["portfolio"] = None
        out["errors"]["registry"] = out["errors"]["portfolio"] = "Not searched: unit owners and private owners are not looked up."
    return out


# ------------------------------------------------------------------ map


from maps import build_block_map, build_map, build_parcel_map, js_safe  # noqa: E402,F401  (map drawing lives in maps.py)
