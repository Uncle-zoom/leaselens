"""What kind of property a Connecticut parcel record describes, and what we may say about its owner.

Rules come from the real state_use_description values in the state file (a count by value showed 100+ spellings of the same few classes:
"Single Fam MDL-01", "SINGLE FAMILY", "One Family", "Res Condo Unit", "Commercial Improv", "Vacant Land", ...), so they match words, not exact values.

    standard            apartments, multi-family, company owners, unknown use: shown as before
    condo_no_master     a condo building whose records are all units: no single building owner exists in the data; unit owners are not named
    condo_association   the association's own record (unit CNDASC): called the condo association
    private_home        a single-family home or condo unit, owner looks like a person and the tax bill goes to the property: owner not named
    not_housing         commercial, industrial, exempt, vacant land: "not housing"
"""
from __future__ import annotations

import re

from ..matching import _STREET, looks_like_entity, normalize_address, normalize_name

_SUFFIXES = set(_STREET)
HIDDEN_KINDS = ("condo_no_master", "private_home", "private_owner")      # names hidden, not traced
PRIVATE_OWNER = "a private owner"
CAP_ROWS = 50            # the parcel query returns at most this many records for one street number
NOT_HOUSING = re.compile(r"\b(commerc\w*|comm|industrial|exempt|municipal|mun|vacant|vac|land|lnd|forest|open space|use assessment|"
                         r"farm\w*|utility|utilities|office|retail|warehouse|federal)\b", re.I)
CONDO = re.compile(r"condo", re.I)
SINGLE = re.compile(r"(single fam|sfr|one fam|1-?\s?fam|res dwelling|^residential|^resident\w*\s*(mdl|$)|^residentia|half duplex|manufactured|mobile home)", re.I)
EXTRA_ENTITY = {"ASSOC", "ASSN", "ASSOCIATION", "PARTNERSHIP", "CHURCH", "TOWN", "AUTHORITY", "BANK", "FUND", "CONDOMINIUM", "CONDO", "GROUP",
                "ESTATE", "FOUNDATION", "HOUSING", "TRUSTEES", "DEVELOPMENT", "ENTERPRISES", "INVESTMENTS", "CLUB", "SOCIETY", "STATE", "COUNTY"}


UNIT_MARK = re.compile(r"[\s,]*(?:#|\bapt\.?|\bunit|\bste\.?|\bsuite)\s*#?\s*([A-Za-z0-9-]+)\s*$", re.I)


def strip_unit(addr: str | None) -> tuple[str, str]:
    """'1 STRAWBERRY HILL AVE # 3B' -> ('1 STRAWBERRY HILL AVE', '3B'); an address without a unit marker comes back unchanged."""
    a = " ".join((addr or "").split())
    m = UNIT_MARK.search(a)
    return (a[:m.start()].strip(), m.group(1).upper()) if m else (a, "")


def unit_of(rec: dict) -> str:
    """The unit of a condo record, or '' for a building-level record. Towns write it three ways: the `unit` field, ', Unit 0A1' at the end of
    the location, or a bare suffix after the street ('484  WHITNEY AV  1B', '484 WHITNEY AV #A6')."""
    u = (rec.get("unit") or "").strip()
    if u:
        return u.upper()
    loc = rec.get("location") or ""
    m = re.search(r",?\s*unit\s+(\S+)\s*$", loc, re.I)
    if m:
        return m.group(1).upper()
    base, mail_unit = strip_unit(rec.get("mailing_address"))
    if mail_unit and normalize_address(base) == normalize_address(" ".join(loc.split())):      # the unit appears only on the tax-bill address
        return mail_unit
    tokens = loc.replace(",", " ").split()
    street = (rec.get("street_name") or "").split()
    rest = tokens[1 + len(street):] if len(tokens) > 1 + len(street) else []
    if rest and rest[0].upper() in _SUFFIXES:                  # the street's own suffix ('AV', 'ST') is not a unit
        rest = rest[1:]
    return " ".join(rest).upper()


USE_WORDS = (("commercial", r"commerc|\bcomm\b|office|retail|warehouse"), ("industrial", r"industrial"), ("exempt", r"exempt|federal"),
             ("municipal", r"municipal|\bmun\b"), ("utility", r"utilit"), ("vacant land", r"vacant|\bvac\b|land|\blnd\b|forest|open space|farm|use assessment"))


def not_housing_label(use: str) -> str:
    """'commercial improv' -> 'commercial': the plain word for the class, not the town's abbreviation."""
    return next((word for word, rx in USE_WORDS if re.search(rx, use, re.I)), use or "a non-housing use")


def clean_use(use: str | None) -> str:
    """'Commercial  MDL-94' -> 'commercial': the town's appraisal-model code is not for readers."""
    u = re.sub(r"\bMDL[-\s]?\d+\b|\bM-?\d{2}\b", "", use or "", flags=re.I)
    return " ".join(u.split()).lower()


def owner_is_person(owner: str | None) -> bool:
    if not owner or looks_like_entity(owner):
        return False
    return not (set(normalize_name(owner).split()) & EXTRA_ENTITY)


def classify(primary: dict, results: list[dict]) -> dict:
    use = clean_use(primary.get("state_use_description"))
    unit = unit_of(primary)
    out = {"kind": "standard", "use": use, "message": None, "unit_records": 0}
    if unit == "CNDASC" or (CONDO.search(use) and re.search(r"\b(assoc|assn)\w*", primary.get("owner") or "", re.I)):
        return {**out, "kind": "condo_association",
                "message": "This record belongs to the condo association (the shared building), not to a single unit."}
    if NOT_HOUSING.search(use) and not CONDO.search(use):
        return {**out, "kind": "not_housing", "message": f"The parcel record lists this as {not_housing_label(use)}, not housing."}
    if CONDO.search(use) and NOT_HOUSING.search(use):                           # "Commercial Condo"
        return {**out, "kind": "not_housing", "message": f"The parcel record lists this as {not_housing_label(use)}, not housing."}
    units = [r for r in results if unit_of(r)]
    master = any(re.search(r"\b(main|master|assoc\w*|common)\b", r.get("state_use_description") or "", re.I) for r in results)
    if CONDO.search(use) and units and len(units) == len(results) and len(results) > 1 and not master:
        n = len(results)
        count = f"{CAP_ROWS} or more" if n >= CAP_ROWS else str(n)
        return {**out, "kind": "condo_no_master", "unit_records": n,
                "message": (f"Condo building: {count} unit records with different owners. No single building owner in the parcel data; "
                            "ask who owns the unit you would rent.")}
    home = bool(SINGLE.search(use)) or bool(CONDO.search(use))
    if home and owner_is_person(primary.get("owner")):
        # a person who owns a single-family home or a condo unit: never named, whether they live there or not
        mail_base = strip_unit(primary.get("mailing_address"))[0]
        loc = " ".join((primary.get("location") or "").split())
        if mail_base and normalize_address(mail_base) == normalize_address(strip_unit(loc)[0]):
            return {**out, "kind": "private_home",
                    "message": "Looks like a privately owned home where the owner lives. It may not be a rental."}
        return {**out, "kind": "private_owner",
                "message": "The parcel record lists a private individual as the owner, so the name is not shown. Ask who the landlord is."}
    return out


def apply_privacy(data: dict, prop: dict) -> dict:
    """Hide names of people before the record goes anywhere (app, report, AI facts, saved samples)."""
    hide = ("owner", "co_owner", "mailing_address", "mailing_address_2", "mailing_city", "mailing_state", "mailing_zip")
    if prop["kind"] == "condo_association":                      # the association's own record stays; the unit owners next to it are people
        records = [r for r in data["results"] if r is not data["primary"]]
    elif prop["kind"] in HIDDEN_KINDS:
        records = [data["primary"], *data["results"]]
    else:
        return data
    for rec in records:
        for k in hide:
            rec.pop(k, None)
        rec["owner"] = PRIVATE_OWNER
    return data


def location_label(location: str | None, unit: str | None = None, building_only: bool = False) -> str:
    """The address as the record has it, but never a raw code: 'UNIT CNDASC' is the condo association's own record."""
    loc = " ".join((location or "").split())
    if building_only:                                          # a condo building has no single unit to name
        loc = strip_unit(re.sub(r",?\s*unit\s+\S+$", "", loc, flags=re.I))[0]
    if re.search(r"\bunit\s+cndasc\b", loc, re.I) or (unit or "").upper() == "CNDASC":
        base = re.sub(r",?\s*\bunit\s+cndasc\b", "", loc, flags=re.I).strip()
        return f"{base} (condo association record)".strip()
    return loc


def use_label(use: str | None) -> str | None:
    """The use as recorded, without appraisal-model codes; None when the record gives none."""
    u = clean_use(use)
    return u or None
