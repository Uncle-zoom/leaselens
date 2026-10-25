"""Other Connecticut parcels linked to the same owner, each with HOW it was matched and a confidence level."""
from __future__ import annotations

from ..common import SourceResult, run_source, slug, socrata, socrata_str
from ..matching import (is_po_box, looks_like_entity, normalize_address, normalize_name, strip_entity_suffix)
from .parcels import DATASET_ID, DOMAIN

DATASET = {
    "name": "2026 Connecticut Parcel and CAMA Data (Office of Policy and Management)",
    "id": DATASET_ID,
    "url": f"https://{DOMAIN}/resource/{DATASET_ID}.json",
    "terms": "https://data.ct.gov (open data, Socrata, no key)",
}
KEEP = ["location", "address_number", "street_name", "property_city", "owner", "mailing_address", "mailing_city",
        "mailing_state", "state_use_description", "number_of_units", "link"]
CAP = 200          # parcels shown
FETCH = 1000       # rows fetched per query


def same_number(a: str | None, b: str | None) -> bool:
    """17 towns store the street number as '200.0': '200' and '200.0' are the same number."""
    def norm(x):
        x = (x or "").strip()
        return x[:-2] if x.endswith(".0") else x
    return norm(a) == norm(b)


def _same_building(row: dict, subject: dict) -> bool:
    return (same_number(row.get("address_number"), subject.get("address_number"))
            and (row.get("street_name") or "").upper() == (subject.get("street_name") or "").upper()
            and (row.get("property_city") or "").upper() == (subject.get("property_city") or "").upper())


def _live(subject: dict) -> dict:
    owner = (subject.get("owner") or "").strip()
    if not owner:
        raise ValueError("subject parcel has no owner name")
    entity = looks_like_entity(owner)
    sel = ",".join(KEEP)
    seen: dict[str, dict] = {}
    names_at_mailing: set[str] = set()

    def add(rows: list[dict], how: str, confidence: str, reason: str) -> None:
        for r in rows:
            if _same_building(r, subject) or r.get("link") in seen or r.get("link") == subject.get("link"):
                continue
            seen[r["link"]] = {**{k: r.get(k) for k in KEEP if r.get(k)}, "match_type": how,
                               "confidence": confidence, "reason": reason}

    exact = socrata(DOMAIN, DATASET_ID, {"$where": f"upper(owner)='{socrata_str(owner.upper())}'",
                                         "$select": sel, "$limit": FETCH})
    add(exact, "exact name", "high" if entity else "medium",
        "owner name is identical on both parcels" + ("" if entity else " (a personal name: different people can share it)"))

    words = normalize_name(owner).split()
    if words:
        prefix = " ".join(words[:2]) if len(words) > 1 else words[0]
        cands = socrata(DOMAIN, DATASET_ID, {"$where": f"upper(owner) like '{socrata_str(prefix)}%'",
                                             "$select": sel, "$limit": FETCH})
        base = strip_entity_suffix(normalize_name(owner))
        norm = [r for r in cands if r.get("owner") and r["owner"].upper() != owner.upper()
                and strip_entity_suffix(normalize_name(r["owner"])) == base
                and normalize_name(r["owner"]) == normalize_name(owner)]
        add(norm, "normalized name", "medium" if entity else "low",
            "owner names are the same after ignoring punctuation and LLC/L.L.C.-style spelling")

    mail, mcity, mstate = subject.get("mailing_address"), subject.get("mailing_city"), subject.get("mailing_state")
    same_as_property = mail and normalize_address(mail) == normalize_address(subject.get("location", ""))
    if mail and mcity and not same_as_property:
        rows = socrata(DOMAIN, DATASET_ID, {
            "$where": (f"upper(mailing_address)='{socrata_str(mail.upper())}' AND upper(mailing_city)="
                       f"'{socrata_str(mcity.upper())}'" + (f" AND upper(mailing_state)='{socrata_str(mstate.upper())}'" if mstate else "")),
            "$select": sel, "$limit": FETCH})
        names_at_mailing = {normalize_name(r["owner"]) for r in rows if r.get("owner")}
        shared = len(names_at_mailing) > 5 or is_po_box(mail)
        add(rows, "same mailing address", "low" if shared else "medium",
            ("this mailing address is a PO box or is used by many different owners (possibly an agent or "
             "manager's office), so it is weak evidence of common ownership") if shared else
            "tax bills for both parcels go to the same mailing address, under a different owner name")

    matches = sorted(seen.values(), key=lambda m: ({"exact name": 0, "normalized name": 1}.get(m["match_type"], 2),
                                                   m.get("location", "")))
    counts: dict[str, int] = {}
    for m in matches:
        counts[m["match_type"]] = counts.get(m["match_type"], 0) + 1
    return {"owner": owner, "mailing": {"address": mail, "city": mcity, "state": mstate},
            "distinct_owner_names_at_mailing_address": len(names_at_mailing),
            "total_matches": len(matches), "counts_by_match_type": counts,
            "results": matches[:CAP]}


def find_portfolio(subject_parcel: dict, *, save: bool = False) -> SourceResult:
    return run_source(
        "ct", "portfolio", slug(subject_parcel.get("location", "") + " " + subject_parcel.get("property_city", "")),
        lambda: _live(subject_parcel), DATASET,
        count=lambda d: d["total_matches"],
        fields=lambda d: sorted({k for m in d["results"] for k in m}),
        save=save)
