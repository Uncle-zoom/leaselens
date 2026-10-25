"""Other NYC buildings registered with HPD to the same owner or managing agent.

Each match records how it was matched and a confidence level:
  exact name            owner company/person name identical on both HPD registrations   high
  normalized name       same after ignoring punctuation / LLC spelling                  medium
  same registration contact   same managing agent (company, or person + business address)   medium
  same mailing address  owner registered at the same business address, different name   medium/low
A managing agent is hired by owners, so a shared agent shows a shared manager, not necessarily a shared owner.
"""
from __future__ import annotations

from ..common import SourceResult, run_source, socrata, socrata_str
from ..matching import (is_po_box, looks_like_entity, normalize_address, normalize_name)
from .common import NYC_DOMAIN, make_bbl
from .owner import CONTACT_ID, OWNER_TYPES, REG_ID, display_name

DATASET = {
    "name": "HPD Registration Contacts (feu5-w2e2) + Multiple Dwelling Registrations (tesw-yqqr), NYC Open Data",
    "id": f"{CONTACT_ID} / {REG_ID}",
    "url": f"https://{NYC_DOMAIN}/resource/{CONTACT_ID}.json",
    "terms": "https://www.nyc.gov/html/data/terms.html (open data, no key)",
}
FETCH = 2000
CAP = 200
OWNER_TYPE_SQL = "('CorporateOwner','IndividualOwner','JointOwner')"
RANK = {"exact name": 0, "normalized name": 1, "same registration contact": 2, "same mailing address": 3}


def _addr(c: dict) -> str:
    """Loose address key: house number + ZIP + first street word. HPD business addresses are free text
    ('SHEA CENTER DR. STE 200' vs 'SHEA CENTER DRIVE'), so exact string equality would miss real links."""
    street = normalize_address(c.get("businessstreetname", "")).split()
    return f"{(c.get('businesshousenumber') or '').upper()}|{(c.get('businesszip') or '')[:5]}|{street[0] if street else ''}"


def _live(owner: dict) -> dict:
    subject_reg = (owner.get("registration") or {}).get("registrationid")
    subject_bbl = owner["bbl"]
    owners = owner.get("owners") or []
    agents = owner.get("managing_agents") or []
    if not owners and not agents and not owner.get("pluto_owner_name"):
        raise ValueError("no owner or agent on record to match")
    found: dict[str, dict] = {}  # registrationid -> match info (strongest wins)

    def add(contacts: list[dict], how: str, confidence: str, reason: str) -> None:
        for c in contacts:
            rid = c["registrationid"]
            if rid == subject_reg:
                continue
            cur = found.get(rid)
            if cur is None or RANK[how] < RANK[cur["match_type"]]:
                found[rid] = {"registrationid": rid, "match_type": how, "confidence": confidence,
                              "reason": reason, "matched_contact": display_name(c), "contact_type": c.get("type")}

    sel = "registrationid,type,corporationname,firstname,lastname,businesshousenumber,businessstreetname,businesszip"
    owner_names = {o["name"] for o in owners if o.get("name")}
    if not owner_names and owner.get("pluto_owner_name"):
        owner_names = {owner["pluto_owner_name"]}
    for name in owner_names:
        entity = looks_like_entity(name)
        rows = socrata(NYC_DOMAIN, CONTACT_ID, {
            "$select": sel, "$limit": FETCH,
            "$where": f"upper(corporationname)='{socrata_str(name.upper())}' AND type in{OWNER_TYPE_SQL}"})
        add(rows, "exact name", "high" if entity else "medium",
            "owner name on the HPD registration is identical" + ("" if entity else " (personal names can be shared)"))
        words = normalize_name(name).split()
        if words and entity:
            prefix = " ".join(words[:2]) if len(words) > 1 else words[0]
            cands = socrata(NYC_DOMAIN, CONTACT_ID, {
                "$select": sel, "$limit": FETCH,
                "$where": f"upper(corporationname) like '{socrata_str(prefix)}%' AND type in{OWNER_TYPE_SQL}"})
            norm = [r for r in cands if r.get("corporationname") and r["corporationname"].upper() != name.upper()
                    and normalize_name(r["corporationname"]) == normalize_name(name)]
            add(norm, "normalized name", "medium", "same name after ignoring punctuation and LLC spelling")

    people_done: set[tuple] = set()
    for ct in agents + (owner.get("head_officers") or []):
        corp = ct.get("corporationname")
        if corp and ct.get("type") == "Agent":
            rows = socrata(NYC_DOMAIN, CONTACT_ID, {
                "$select": sel, "$limit": FETCH,
                "$where": f"upper(corporationname)='{socrata_str(corp.upper())}' AND type='Agent'"})
            add(rows, "same registration contact", "medium", "same managing-agent company on the HPD registration")
        first, last = (ct.get("firstname") or "").upper(), (ct.get("lastname") or "").upper()
        if first and last and (first, last, _addr(ct)) not in people_done:
            people_done.add((first, last, _addr(ct)))
            rows = socrata(NYC_DOMAIN, CONTACT_ID, {
                "$select": sel, "$limit": FETCH,
                "$where": (f"upper(lastname)='{socrata_str(last)}' AND upper(firstname)='{socrata_str(first)}' "
                           "AND type in('Agent','HeadOfficer','Officer')")})
            add([r for r in rows if _addr(r) == _addr(ct)], "same registration contact", "medium",
                "same person and business address listed as agent or officer on both HPD registrations")

    mailing_owners: set[str] = set()
    for o in owners:
        if not o.get("businesshousenumber") or not o.get("businessstreetname"):
            continue
        rows = socrata(NYC_DOMAIN, CONTACT_ID, {
            "$select": sel, "$limit": FETCH,
            "$where": (f"upper(businesshousenumber)='{socrata_str(o['businesshousenumber'].upper())}' AND "
                       f"upper(businessstreetname)='{socrata_str(o['businessstreetname'].upper())}' AND "
                       f"businesszip='{socrata_str(o.get('businesszip', ''))}' AND type in{OWNER_TYPE_SQL}")})
        mailing_owners |= {normalize_name(display_name(r)) for r in rows}
        shared = len(mailing_owners) > 5 or is_po_box(f"{o['businesshousenumber']} {o['businessstreetname']}")
        add([r for r in rows if normalize_name(display_name(r)) != normalize_name(o["name"])],
            "same mailing address", "low" if shared else "medium",
            "different owner name registered at the same business address"
            + (" (address shared by many owners: possibly an agent's or manager's office)" if shared else ""))

    # registrationid -> building
    rids = list(found)
    buildings = []
    for i in range(0, len(rids), 150):
        chunk = rids[i:i + 150]
        regs = socrata(NYC_DOMAIN, REG_ID, {
            "$where": "registrationid in(" + ",".join(f"'{socrata_str(r)}'" for r in chunk) + ")",
            "$select": "registrationid,boroid,housenumber,streetname,zip,block,lot,bin", "$limit": 500})
        for r in regs:
            bbl = make_bbl(r["boroid"], r["block"], r["lot"])
            if bbl == subject_bbl:
                continue
            buildings.append({"bbl": bbl, "address": f"{r.get('housenumber', '')} {r.get('streetname', '')}".strip(),
                              "zip": r.get("zip"), **{k: v for k, v in found[r["registrationid"]].items()
                                                      if k != "registrationid"}})
    uniq: dict[str, dict] = {}
    for b in buildings:
        if b["bbl"] not in uniq or RANK[b["match_type"]] < RANK[uniq[b["bbl"]]["match_type"]]:
            uniq[b["bbl"]] = b
    matches = sorted(uniq.values(), key=lambda m: (RANK[m["match_type"]], m["address"]))
    counts: dict[str, int] = {}
    for m in matches:
        counts[m["match_type"]] = counts.get(m["match_type"], 0) + 1
    return {"bbl": subject_bbl, "owner_names": sorted(owner_names),
            "managing_agents": [a.get("name") for a in agents],
            "head_officers": [h.get("name") for h in owner.get("head_officers") or []], "total_matches": len(matches),
            "counts_by_match_type": counts,
            "results": matches[:CAP]}


def find_portfolio(owner: dict, *, save: bool = False) -> SourceResult:
    return run_source(
        "nyc", "portfolio", owner["bbl"], lambda: _live(owner), DATASET,
        count=lambda d: d["total_matches"],
        fields=lambda d: sorted({k for m in d["results"] for k in m}),
        save=save)
