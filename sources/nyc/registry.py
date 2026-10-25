"""NY State Department of State corporation records (data.ny.gov) for an owner company."""
from __future__ import annotations

from ..common import SourceResult, run_source, slug, socrata, socrata_str
from ..matching import normalize_name
from .common import NYS_DOMAIN

DATASET_ID = "n9v6-gdp6"
DATASET = {
    "name": "Active Corporations: Beginning 1800 (NY Department of State, data.ny.gov)",
    "id": DATASET_ID,
    "url": f"https://{NYS_DOMAIN}/resource/{DATASET_ID}.json",
    "terms": "https://data.ny.gov (open data, Socrata, no key)",
}
KEEP = ["dos_id", "current_entity_name", "entity_type", "jurisdiction", "initial_dos_filing_date", "county",
        "dos_process_name", "dos_process_address_1", "dos_process_address_2", "dos_process_city", "dos_process_state",
        "dos_process_zip", "registered_agent_name", "registered_agent_address_1", "registered_agent_city",
        "registered_agent_state", "registered_agent_zip", "chairman_name", "location_name", "location_address_1",
        "location_city", "location_state", "location_zip"]


def _live(owner_name: str) -> dict:
    upper = owner_name.upper().strip()
    rows = socrata(NYS_DOMAIN, DATASET_ID, {"$where": f"upper(current_entity_name)='{socrata_str(upper)}'", "$limit": 5})
    how, confidence = "exact name", "high"
    if not rows:
        words = normalize_name(owner_name).split()
        prefix = " ".join(words[:2])
        cands = socrata(NYS_DOMAIN, DATASET_ID, {"$where": f"upper(current_entity_name) like '{socrata_str(prefix)}%'",
                                                 "$limit": 200})
        rows = [r for r in cands if normalize_name(r["current_entity_name"]) == normalize_name(owner_name)]
        how, confidence = "normalized name", "medium"
    if not rows:
        raise ValueError(f"no NY Department of State record named {owner_name!r}")
    rec = {k: rows[0][k] for k in KEEP if rows[0].get(k) not in (None, "")}
    return {"query": owner_name, "matched_how": how, "confidence": confidence,
            "entity": rec, "other_records_with_same_name": len(rows) - 1, "results": [rec]}


def find_entity(owner_name: str, *, save: bool = False) -> SourceResult:
    return run_source("nyc", "registry", slug(owner_name), lambda: _live(owner_name), DATASET,
                      count=lambda d: len(d["results"]), fields=lambda d: sorted(d["entity"]), save=save)
