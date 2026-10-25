"""Pick data adapters from a geocoded address.

CT -> core + ct;  NYC -> core only (nyc is switched off: `enabled = False`, coming soon);  anywhere else in the US -> core only.

Adding a city means adding ONE folder under sources/ whose __init__.py defines `MARKET` with
  name, label, adapters (names of its sources), matches(geo) -> bool, and run(geo, address, save=False).
Nothing in this file changes: markets are discovered by scanning the sources/ package.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass

from . import __path__ as _sources_path
from .common import SourceResult
from .core import geocode


def discover_markets() -> list:
    """Every sources/<folder>/ that exposes MARKET. `core` first (always on), the rest alphabetical."""
    found = []
    for mod in pkgutil.iter_modules(_sources_path):
        if not mod.ispkg:
            continue
        pkg = importlib.import_module(f"{__package__}.{mod.name}")
        market = getattr(pkg, "MARKET", None)
        if market is not None:
            found.append(market)
    return sorted(found, key=lambda m: (m.name != "core", m.name))


@dataclass
class RoutePlan:
    markets: list[str]                # e.g. ["core", "ct"]
    adapters: dict[str, tuple[str, ...]]
    label: str
    coming_soon: tuple[str, ...] = ()   # markets that match the address but are switched off

    def to_dict(self) -> dict:
        return {"markets": self.markets, "adapters": {k: list(v) for k, v in self.adapters.items()}, "label": self.label,
                "coming_soon": list(self.coming_soon)}


def route(geo: dict) -> RoutePlan:
    matched = [m for m in discover_markets() if m.matches(geo)]
    chosen = [m for m in matched if getattr(m, "enabled", True)]
    soon = tuple(m.label for m in matched if not getattr(m, "enabled", True))
    return RoutePlan([m.name for m in chosen], {m.name: tuple(m.adapters) for m in chosen},
                     " + ".join(m.label for m in chosen), soon)


def analyze(address: str, *, save: bool = False) -> dict:
    """Geocode, route, and run every relevant adapter. Returns {"geo", "plan", "results": {market: {source: SourceResult}}}."""
    geo_res = geocode.geocode(address, save=save)
    if not geo_res.ok:
        return {"geo": geo_res, "plan": None, "results": {}}
    plan = route(geo_res.data)
    markets = {m.name: m for m in discover_markets()}
    results: dict[str, dict[str, SourceResult]] = {}
    for name in plan.markets:
        results[name] = markets[name].run(geo_res.data, address, save=save)
    return {"geo": geo_res, "plan": plan, "results": results}
