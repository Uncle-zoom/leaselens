"""Who owns a NYC building: PLUTO tax-lot owner + HPD multiple-dwelling registration contacts."""
from __future__ import annotations

from ..common import SourceResult, run_source, socrata
from .common import BORO_CODE, NYC_DOMAIN, split_bbl

PLUTO_ID, REG_ID, CONTACT_ID = "64uk-42ks", "tesw-yqqr", "feu5-w2e2"
DATASET = {
    "name": "PLUTO (64uk-42ks) + HPD Multiple Dwelling Registrations (tesw-yqqr) + HPD Registration Contacts (feu5-w2e2), NYC Open Data",
    "id": f"{PLUTO_ID} / {REG_ID} / {CONTACT_ID}",
    "url": f"https://{NYC_DOMAIN}/resource/{REG_ID}.json",
    "terms": "https://www.nyc.gov/html/data/terms.html (open data, no key)",
}
PLUTO_KEEP = "address,ownername,ownertype,bldgclass,unitsres,unitstotal,numfloors,yearbuilt,landuse,zipcode,bbl"
OWNER_TYPES = {"CorporateOwner", "IndividualOwner", "JointOwner"}
CONTACT_KEEP = ["type", "contactdescription", "corporationname", "title", "firstname", "middleinitial", "lastname",
                "businesshousenumber", "businessstreetname", "businessapartment", "businesscity", "businessstate",
                "businesszip"]


def display_name(c: dict) -> str:
    person = " ".join(x for x in (c.get("firstname"), c.get("middleinitial"), c.get("lastname")) if x)
    return c.get("corporationname") or person


def _live(bbl: str) -> dict:
    boro, block, lot = split_bbl(bbl)
    pluto_rows = socrata(NYC_DOMAIN, PLUTO_ID, {"$select": PLUTO_KEEP, "$limit": 1,
                                                 "$where": f"borough='{BORO_CODE[boro]}' AND block={block} AND lot={lot}"})
    regs = socrata(NYC_DOMAIN, REG_ID, {"boroid": boro, "block": str(block), "lot": str(lot),
                                         "$order": "lastregistrationdate DESC", "$limit": 5})
    if not pluto_rows and not regs:
        raise ValueError(f"no PLUTO lot or HPD registration for BBL {bbl}")
    pluto = pluto_rows[0] if pluto_rows else {}
    contacts, registration = [], None
    if regs:
        registration = {k: regs[0].get(k) for k in ("registrationid", "housenumber", "streetname", "zip", "bin",
                                                     "lastregistrationdate", "registrationenddate")}
        rows = socrata(NYC_DOMAIN, CONTACT_ID, {"registrationid": regs[0]["registrationid"], "$limit": 100})
        for r in rows:
            c = {k: r[k] for k in CONTACT_KEEP if r.get(k) not in (None, "")}
            c["name"] = display_name(r)
            contacts.append(c)
    owners = [c for c in contacts if c.get("type") in OWNER_TYPES]
    return {"bbl": bbl, "pluto": pluto, "pluto_owner_name": pluto.get("ownername"),
            "registration": registration,
            "owners": owners,
            "managing_agents": [c for c in contacts if c.get("type") == "Agent"],
            "head_officers": [c for c in contacts if c.get("type") == "HeadOfficer"],
            "other_contacts": [c for c in contacts if c.get("type") not in OWNER_TYPES | {"Agent", "HeadOfficer"}],
            "results": contacts}


def find_owner(bbl: str, *, save: bool = False) -> SourceResult:
    return run_source(
        "nyc", "owner", bbl, lambda: _live(bbl), DATASET,
        count=lambda d: len(d["results"]) + (1 if d["pluto"] else 0),
        fields=lambda d: sorted(set(d["pluto"]) | {k for c in d["results"] for k in c}),
        save=save)
