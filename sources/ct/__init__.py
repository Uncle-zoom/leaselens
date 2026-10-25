"""Connecticut market: local complaints + the landlord trail from CT public records."""
from __future__ import annotations

from ..common import SourceResult
from . import complaints, parcels, portfolio, property_type, registry


def run(geo: dict, address: str, *, save: bool = False) -> dict[str, SourceResult]:
    out: dict[str, SourceResult] = {}
    out["complaints"] = complaints.fetch_complaints(geo["lat"], geo["lon"], save=save)
    out["parcels"] = parcels.find_parcel(address, geo.get("city") or "", save=save)
    if out["parcels"].ok:
        primary = out["parcels"].data["primary"]
        if (out["parcels"].data.get("property") or {}).get("kind") not in property_type.HIDDEN_KINDS:      # unit owners and private people are not traced
            out["registry"] = registry.find_business(primary["owner"], save=save)
            out["portfolio"] = portfolio.find_portfolio(primary, save=save)
    return out


class _Market:
    name = "ct"
    label = "Connecticut"
    adapters = ("complaints", "parcels", "registry", "portfolio")

    @staticmethod
    def matches(geo: dict) -> bool:
        return geo.get("state_code") == "CT"

    run = staticmethod(run)


MARKET = _Market()
