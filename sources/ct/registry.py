"""CT Business Registry (data.ct.gov): business record, registered agent and principals for an owner name."""
from __future__ import annotations

from ..common import SourceResult, run_source, slug, socrata, socrata_str
from ..matching import normalize_name

DOMAIN = "data.ct.gov"
MASTER, PRINCIPALS, AGENTS = "n7gp-d28j", "ka36-64k6", "qh2m-n44y"
DATASET = {
    "name": "Connecticut Business Registry - Business Master (+ Principals ka36-64k6, Agents qh2m-n44y)",
    "id": f"{MASTER} / {PRINCIPALS} / {AGENTS}",
    "url": f"https://{DOMAIN}/resource/{MASTER}.json",
    "terms": "https://data.ct.gov (open data, Socrata, no key)",
}
# Individuals' residence addresses and contact e-mails are in the raw data. We do not keep them:
# an owner's registered *business* address is what a renter needs.
MASTER_KEEP = ["id", "name", "business_type", "status", "sub_status", "accountnumber", "date_registration",
               "citizenship", "formation_place", "billingstreet", "billing_unit", "billingcity", "billingstate",
               "billingpostalcode", "mailing_address", "naics_code", "annual_report_due_date"]
PRINCIPAL_KEEP = ["name__c", "designation", "type", "business_street_address_1", "business_street_address_2",
                  "business_city", "business_state", "business_zip_code"]
AGENT_KEEP = ["name__c", "type", "business_street_address_1", "business_street_address_2", "business_city",
              "business_state", "business_zip_code"]


def _clean(row: dict, keep: list[str]) -> dict:
    return {k: row[k] for k in keep if row.get(k) not in (None, "")}


def _live(owner_name: str) -> dict:
    upper = owner_name.upper().strip()
    rows = socrata(DOMAIN, MASTER, {"$where": f"upper(name)='{socrata_str(upper)}'", "$limit": 5})
    how, confidence = "exact name", "high"
    if not rows:  # normalised match: "ACME, L.L.C." vs "ACME LLC"
        words = normalize_name(owner_name).split()
        prefix = " ".join(words[:2])
        cands = socrata(DOMAIN, MASTER, {"$where": f"upper(name) like '{socrata_str(prefix)}%'", "$limit": 200})
        rows = [r for r in cands if normalize_name(r["name"]) == normalize_name(owner_name)]
        how, confidence = "normalized name", "medium"
    if not rows:
        raise ValueError(f"no Business Registry record named {owner_name!r}")
    rows.sort(key=lambda r: r.get("status") != "Active")  # active first
    biz = rows[0]
    principals = socrata(DOMAIN, PRINCIPALS, {"business_id": biz["id"], "$limit": 50})
    agents = socrata(DOMAIN, AGENTS, {"business_key": biz["id"], "$limit": 10})
    return {"query": owner_name, "matched_how": how, "confidence": confidence,
            "business": _clean(biz, MASTER_KEEP),
            "other_records_with_same_name": len(rows) - 1,
            "registered_agents": [_clean(a, AGENT_KEEP) for a in agents],
            "principals": [_clean(p, PRINCIPAL_KEEP) for p in principals],
            "results": [_clean(biz, MASTER_KEEP)]}


def find_business(owner_name: str, *, save: bool = False) -> SourceResult:
    return run_source(
        "ct", "registry", slug(owner_name), lambda: _live(owner_name), DATASET,
        count=lambda d: len(d["results"]) + len(d["principals"]) + len(d["registered_agents"]),
        fields=lambda d: sorted(set(d["business"]) | {"registered_agents", "principals"}),
        save=save)
