"""HPD housing code violations and tenant complaints for one building (by BBL)."""
from __future__ import annotations

from ..common import SourceResult, run_source, socrata, socrata_str
from .common import NYC_DOMAIN, months_ago

VIOLATIONS_ID, COMPLAINTS_ID = "wvxf-dwi5", "ygpa-z7cr"
DATASET = {
    "name": "Housing Maintenance Code Violations (wvxf-dwi5) + Housing Maintenance Code Complaints and Problems (ygpa-z7cr), NYC HPD",
    "id": f"{VIOLATIONS_ID} / {COMPLAINTS_ID}",
    "url": f"https://{NYC_DOMAIN}/resource/{VIOLATIONS_ID}.json",
    "terms": "https://www.nyc.gov/html/data/terms.html (open data, no key)",
}
CLASS_MEANING = {"A": "non-hazardous", "B": "hazardous", "C": "immediately hazardous", "I": "informational"}
MONTHS = 12


def _live(bbl: str, months: int) -> dict:
    b = socrata_str(bbl)
    since = months_ago(months)
    by_class = socrata(NYC_DOMAIN, VIOLATIONS_ID, {
        "$select": "class, violationstatus, count(*) as n", "$where": f"bbl='{b}'",
        "$group": "class, violationstatus", "$limit": 200})
    recent = socrata(NYC_DOMAIN, VIOLATIONS_ID, {
        "$select": "class, count(*) as n", "$where": f"bbl='{b}' AND inspectiondate >= '{since}'",
        "$group": "class", "$limit": 20})
    worst_open = socrata(NYC_DOMAIN, VIOLATIONS_ID, {
        "$select": "class, apartment, story, inspectiondate, novdescription, currentstatus, rentimpairing",
        "$where": f"bbl='{b}' AND violationstatus='Open' AND class='C'",
        "$order": "inspectiondate DESC", "$limit": 5})
    comp = socrata(NYC_DOMAIN, COMPLAINTS_ID, {
        "$select": "major_category, complaint_status, count(distinct complaint_id) as n",
        "$where": f"bbl='{b}' AND received_date >= '{since}'",
        "$group": "major_category, complaint_status", "$limit": 500})

    table: dict[str, dict] = {}
    for r in by_class:
        cls = r.get("class") or "?"
        t = table.setdefault(cls, {"class": cls, "meaning": CLASS_MEANING.get(cls, ""), "open": 0, "closed": 0})
        t["open" if r.get("violationstatus") == "Open" else "closed"] += int(r["n"])
    classes = [table[k] for k in sorted(table)]
    recent_by_class = {r["class"]: int(r["n"]) for r in recent}
    for t in classes:
        t["issued_last_12_months"] = recent_by_class.get(t["class"], 0)

    cats: dict[str, dict] = {}
    for r in comp:
        c = cats.setdefault(r["major_category"], {"major_category": r["major_category"], "complaints": 0, "open": 0})
        n = int(r["n"])
        c["complaints"] += n
        c["open"] += n if r.get("complaint_status") == "OPEN" else 0
    complaints = sorted(cats.values(), key=lambda c: -c["complaints"])
    total_v = sum(t["open"] + t["closed"] for t in classes)
    return {"bbl": bbl, "months": months, "since": since[:10],
            "violations_total": total_v, "violations_open": sum(t["open"] for t in classes),
            "violations_by_class": classes, "open_class_c_examples": worst_open,
            "hpd_complaints_last_12_months": sum(c["complaints"] for c in complaints),
            "hpd_complaints_by_category": complaints,
            "results": classes}


def fetch_violations(bbl: str, months: int = MONTHS, *, save: bool = False) -> SourceResult:
    return run_source(
        "nyc", "violations", bbl, lambda: _live(bbl, months), DATASET,
        count=lambda d: d["violations_total"] + d["hpd_complaints_last_12_months"],
        fields=lambda d: ["class", "meaning", "open", "closed", "issued_last_12_months",
                          "major_category", "complaints", "novdescription", "inspectiondate"],
        save=save)
