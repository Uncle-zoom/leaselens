"""Owner name and mailing address for a Connecticut address, from the state parcel + CAMA dataset."""
from __future__ import annotations

from ..common import SourceResult, run_source, slug, socrata, socrata_str
from ..matching import split_street_address
from . import property_type

DOMAIN, DATASET_ID = "data.ct.gov", "ibe8-9i3q"
DATASET = {
    "name": "2026 Connecticut Parcel and CAMA Data (Office of Policy and Management)",
    "id": DATASET_ID,
    "url": f"https://{DOMAIN}/resource/{DATASET_ID}.json",
    "terms": "https://data.ct.gov (open data, Socrata, no key)",
}
KEEP = ["pid", "location", "address_number", "street_name", "unit", "property_city", "owner", "co_owner",
        "mailing_address", "mailing_address_2", "mailing_city", "mailing_state", "mailing_zip",
        "state_use_description", "number_of_units", "assessed_total", "appraised_total", "ayb",
        "valuation_year", "sale_date", "sale_price", "link", "cama_site_link"]


def _live(address: str, city: str) -> dict:
    number, street = split_street_address(address)
    if not number or not street:
        raise ValueError(f"could not read a street number and name from {address!r}")
    where = (f"upper(property_city)='{socrata_str(city.upper())}' AND address_number in('{socrata_str(number)}','{socrata_str(number)}.0') "
             f"AND upper(street_name) like '{socrata_str(street)}%'")
    rows = socrata(DOMAIN, DATASET_ID, {"$where": where, "$select": ",".join(KEEP), "$limit": 50, "$order": "location"})
    if not rows:
        raise ValueError(f"no parcel record for {number} {street}, {city}")
    parcels = [{k: r.get(k) for k in KEEP if r.get(k) not in (None, "")} for r in rows]
    # a condo building has a "main" record plus one per unit: prefer the record without a unit number
    primary = (next((p for p in parcels if property_type.unit_of(p) == "CNDASC"), None)
               or next((p for p in parcels if not property_type.unit_of(p)), parcels[0]))
    data = {"query": address, "number": number, "street": street, "city": city, "primary": primary, "results": parcels}
    data["property"] = property_type.classify(primary, parcels)
    return property_type.apply_privacy(data, data["property"])


def find_parcel(address: str, city: str, *, save: bool = False) -> SourceResult:
    res = _find_parcel(address, city, save=save)
    d = res.data
    if res.ok and d and "property" not in d:           # an older saved sample: classify and hide names exactly as a live result would
        d["property"] = property_type.classify(d["primary"], d["results"])
        property_type.apply_privacy(d, d["property"])
    return res


def _find_parcel(address: str, city: str, *, save: bool = False) -> SourceResult:
    return run_source(
        "ct", "parcels", slug(address), lambda: _live(address, city), DATASET,
        count=lambda d: len(d["results"]),
        fields=lambda d: sorted(d["primary"]),
        save=save)
