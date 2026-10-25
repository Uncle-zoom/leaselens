"""Ownership trail, one extra level: owner company -> a company listed as its principal -> other registered companies that list the same
principal -> those companies' parcels.

    Owner (parcel record) -> linked entity (registry principal) -> N related companies -> M buildings

Every link says HOW it was matched and how confident the match is. Wording rule (CLAUDE.md): links are "linked to", never claims of
control. Individuals listed as principals are NOT followed: a person's name alone (46 businesses share the name of one New Haven
principal) is weak evidence, and registered agents are shared by thousands of companies, so they are listed but not followed either.
"""
from __future__ import annotations

from ..common import SourceResult, run_source, slug, socrata, socrata_str
from ..matching import looks_like_entity, normalize_name
from .parcels import DATASET_ID as PARCELS_ID
from .registry import AGENTS, MASTER, PRINCIPALS

DOMAIN = "data.ct.gov"
DATASET = {
    "name": "Connecticut Business Registry (Business Master n7gp-d28j, Principals ka36-64k6) + 2026 Connecticut Parcel and CAMA Data (ibe8-9i3q)",
    "id": f"{MASTER} / {PRINCIPALS} / {PARCELS_ID}",
    "url": f"https://{DOMAIN}/resource/{PRINCIPALS}.json",
    "terms": "https://data.ct.gov (open data, Socrata, no key)",
}
COMPANY_CAP = 30         # related companies shown per linked entity
PARCEL_CAP = 200         # parcels shown in all
ENTITY_CAP = 3           # company principals followed
ID_FETCH_CAP = 400       # business ids read per principal (the total is reported as "at least" beyond this)
CONF_RANK = {"high": 2, "medium": 1, "low": 0}


def weakest(*levels: str) -> str:
    return min(levels, key=lambda c: CONF_RANK[c])


def _name_variants(name: str) -> list[str]:
    """How the same company can be spelled in the parcel file: with or without commas and periods."""
    up = name.upper().strip()
    return list(dict.fromkeys([up, up.replace(",", ""), up.replace(",", "").replace(".", ""), up.replace(".", "")]))


def _in_list(values: list[str]) -> str:
    return ",".join(f"'{socrata_str(v)}'" for v in values)


def _principal_matches(entity: str) -> tuple[dict[str, str], bool]:
    """business_id -> how the principal name matched, for every registry entry that lists a principal with this name."""
    ids: dict[str, str] = {}
    rows = socrata(DOMAIN, PRINCIPALS, {"$where": f"upper(name__c)='{socrata_str(entity.upper())}'", "$select": "business_id,name__c",
                                         "$limit": ID_FETCH_CAP})
    for r in rows:
        ids[r["business_id"]] = "same principal name (exact)"
    truncated = len(rows) >= ID_FETCH_CAP
    words = normalize_name(entity).split()
    prefix = " ".join(words[:2]) if len(words) > 1 else (words[0] if words else "")
    if prefix and not truncated:
        cands = socrata(DOMAIN, PRINCIPALS, {"$where": f"upper(name__c) like '{socrata_str(prefix)}%'", "$select": "business_id,name__c",
                                              "$limit": ID_FETCH_CAP})
        for r in cands:
            if r["business_id"] not in ids and normalize_name(r["name__c"]) == normalize_name(entity):
                ids[r["business_id"]] = "same principal name (normalized)"
    return ids, truncated


def _companies(ids: dict[str, str], exclude_id: str | None) -> list[dict]:
    ids = {k: v for k, v in ids.items() if k != exclude_id}
    out: list[dict] = []
    keys = list(ids)
    for i in range(0, len(keys), 100):
        chunk = keys[i:i + 100]
        rows = socrata(DOMAIN, MASTER, {"$where": "id in(" + _in_list(chunk) + ")", "$select": "id,name,business_type,status,billingcity,billingstate",
                                        "$limit": 100})
        for r in rows:
            how = ids[r["id"]]
            out.append({"id": r["id"], "name": r["name"], "business_type": r.get("business_type"), "status": r.get("status"),
                        "city": r.get("billingcity"), "state": r.get("billingstate"), "matched_how": how,
                        "confidence": "high" if how.endswith("(exact)") else "medium"})
    out.sort(key=lambda c: (c["status"] != "Active", c["name"].upper()))      # active companies first
    return out


def _live(owner_name: str, registry_data: dict) -> dict:
    biz = registry_data.get("business") or {}
    owner_id = biz.get("id")
    principals = registry_data.get("principals") or []
    entities_in = [p for p in principals if p.get("name__c") and looks_like_entity(p["name__c"])]
    people = [p["name__c"] for p in principals if p.get("name__c") and not looks_like_entity(p["name__c"])]
    agents = [a["name__c"] for a in registry_data.get("registered_agents") or [] if a.get("name__c")]
    trail = {"owner": owner_name, "owner_registry_name": biz.get("name"), "individual_principals_not_followed": len(people),
             "registered_agents_not_followed": agents, "entities": [], "entities_not_followed": max(0, len(entities_in) - ENTITY_CAP)}
    shown_names: list[str] = []
    company_of: dict[str, dict] = {}
    for p in entities_in[:ENTITY_CAP]:
        ids, truncated = _principal_matches(p["name__c"])
        comps = _companies(ids, owner_id)
        shown = comps[:COMPANY_CAP]
        own_names = {normalize_name(owner_name), normalize_name(biz.get("name") or "")}
        trail["entities"].append({
            "name": p["name__c"], "is_owner_itself": normalize_name(p["name__c"]) in own_names, "designation": p.get("designation"),
            "matched_how": "listed as a principal on the owner's registry entry", "confidence": "high",
            "related_total": len(comps), "related_total_is_minimum": truncated or len(ids) >= ID_FETCH_CAP,
            "related_shown": len(shown), "companies": shown})
        for c in shown:
            company_of.setdefault(c["name"].upper(), {**c, "entity": p["name__c"]})
        shown_names += [c["name"] for c in shown]
    parcels: list[dict] = []
    total = 0
    if shown_names:
        variants = list(dict.fromkeys(v for n in shown_names for v in _name_variants(n)))
        where = "upper(owner) in(" + _in_list(variants) + ")"
        cnt = socrata(DOMAIN, PARCELS_ID, {"$select": "count(*) as n", "$where": where})
        total = int(cnt[0]["n"]) if cnt else 0
        rows = socrata(DOMAIN, PARCELS_ID, {"$where": where, "$order": "owner,location", "$limit": PARCEL_CAP,
                                             "$select": "location,address_number,street_name,property_city,owner,state_use_description,link"})
        by_norm = {normalize_name(k): v for k, v in company_of.items()}
        for r in rows:
            up = (r.get("owner") or "").upper()
            comp = company_of.get(up) or by_norm.get(normalize_name(up))
            if comp is None:
                continue
            exact = up in company_of
            parcel_how = "exact name" if exact else "normalized name"
            parcel_conf = "high" if exact else "medium"
            parcels.append({
                "location": " ".join((r.get("location") or "").split()), "property_city": r.get("property_city"), "owner": r.get("owner"),
                "use": r.get("state_use_description"), "link": r.get("link"), "company": comp["name"], "entity": comp["entity"],
                "match_type": f"{comp['matched_how']}; parcel owner {parcel_how}",
                "confidence": weakest("high", comp["confidence"], parcel_conf),
                "reason": f"{comp['name']} lists {comp['entity']} as a principal, and {comp['entity']} is a principal of {owner_name}"})
    trail["parcels"] = parcels
    trail["parcels_total"] = total
    trail["parcels_shown"] = len(parcels)
    trail["caps"] = {"companies": COMPANY_CAP, "parcels": PARCEL_CAP, "entities": ENTITY_CAP}
    trail["companies_total"] = sum(e["related_total"] for e in trail["entities"])
    trail["companies_shown"] = sum(e["related_shown"] for e in trail["entities"])
    trail["results"] = parcels
    return trail


def find_trail(owner_name: str, registry_data: dict, *, save: bool = False) -> SourceResult:
    return run_source(
        "ct", "trail", slug(owner_name), lambda: _live(owner_name, registry_data), DATASET,
        count=lambda d: d["parcels_total"],
        fields=lambda d: sorted({k for p in d["parcels"] for k in p}) or ["entities", "companies_total", "parcels_total"],
        save=save)
