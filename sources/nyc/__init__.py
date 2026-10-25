"""New York City market: 311, HPD violations, owner/agent records and the landlord trail from NYC + NYS open data."""
from __future__ import annotations

from ..common import SourceResult
from . import complaints, geo, owner, portfolio, registry, violations


def run(geo_core: dict, address: str, *, save: bool = False) -> dict[str, SourceResult]:
    out: dict[str, SourceResult] = {}
    out["geo"] = geo.lookup(address, save=save)
    if not out["geo"].ok:
        return out
    g = out["geo"].data
    out["complaints"] = complaints.fetch_311(g["lat"], g["lon"], save=save)
    out["violations"] = violations.fetch_violations(g["bbl"], save=save)
    out["owner"] = owner.find_owner(g["bbl"], save=save)
    if out["owner"].ok:
        o = out["owner"].data
        corp = next((x["name"] for x in o["owners"] if x.get("name")), None) or o.get("pluto_owner_name")
        if corp:
            out["registry"] = registry.find_entity(corp, save=save)
        out["portfolio"] = portfolio.find_portfolio(o, save=save)
    return out


class _Market:
    name = "nyc"
    label = "New York City"
    enabled = False   # coming soon: code kept, router sends NYC addresses to the nationwide report only
    adapters = ("geo", "complaints", "violations", "owner", "registry", "portfolio")

    @staticmethod
    def matches(geo: dict) -> bool:
        nyc_counties = {"New York County", "Kings County", "Bronx County", "Queens County", "Richmond County"}
        return geo.get("state_code") == "NY" and geo.get("county") in nyc_counties

    run = staticmethod(run)


MARKET = _Market()
