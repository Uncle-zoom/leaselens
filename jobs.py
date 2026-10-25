"""Background fetching so the page never waits on a slow service.

Each address becomes a Job whose parts (geocode, block report, street reports, landlord trail) finish
independently. The page draws the map as soon as the geocode is back and fills in the rest as it arrives.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from sources import router
from sources.common import SourceResult, is_offline
from sources.core import census_batch, geocode
from sources.core import run as core_run
from sources.ct import complaints, parcels, portfolio, registry, trail

_POOL = ThreadPoolExecutor(max_workers=24, thread_name_prefix="leaselens")


@dataclass
class Job:
    address: str
    geo: Future          # -> SourceResult
    block: Future        # -> {"places": SourceResult, "walking": SourceResult | None} | None
    street: Future       # -> SourceResult | None   (None = not a Connecticut address)
    landlord: Future     # -> {"parcels", "registry", "portfolio"} | None
    pgeo: Future         # -> locate_parcels(...) result | None   (the owner's other parcels, geocoded)
    chain: Future        # -> {"trail": SourceResult, "located": locate_parcels(...) | None} | None   (owner -> linked entity -> companies -> buildings)

    def futures(self) -> dict[str, Future]:
        return {"geo": self.geo, "block": self.block, "street": self.street, "landlord": self.landlord,
                "pgeo": self.pgeo, "chain": self.chain}


def _after_geo(geo_f: Future, fn):
    def run():
        g = geo_f.result()
        return fn(g.data) if g.ok else None
    return _POOL.submit(run)


def _landlord(address: str):
    def go(g: dict):
        if not _in_ct(g):
            return None
        out = {"parcels": parcels.find_parcel(address, g.get("city") or ""), "registry": None, "portfolio": None}
        if out["parcels"].ok:
            primary = out["parcels"].data["primary"]
            reg_f = _POOL.submit(registry.find_business, primary["owner"])      # independent of each other: run together
            out["portfolio"] = portfolio.find_portfolio(primary)
            out["registry"] = reg_f.result()
        return out
    return go


def _in_ct(g: dict) -> bool:
    return "ct" in router.route(g).markets


MAX_PARCEL_PINS = 25


def locate_parcels(rows: list[dict], total: int, *, limit: int = MAX_PARCEL_PINS, save: bool = False) -> dict:
    """Put up to `limit` of the owner's other parcels on the map.

    Fast path: one Census batch request for all of them. Anything it cannot match (and everything in offline mode,
    which replays saved samples) goes through the existing Nominatim geocoder, cached, at 1 request per second.
    """
    chosen, seen = [], set()
    for r in rows:
        street = " ".join(r.get("location", "").split())
        if street and street not in seen:
            seen.add(street)
            chosen.append((street, r))
        if len(chosen) >= limit:
            break
    batch: dict[str, tuple[float, float]] = {}
    if chosen and not is_offline():
        try:
            res = census_batch.geocode_batch([(st, r.get("property_city") or "", "CT") for st, r in chosen])
            if res.ok:
                batch = {chosen[int(k)][0]: tuple(v) for k, v in res.data["matched"].items()}
        except Exception:
            batch = {}      # fall through to Nominatim for every parcel
    located, failed = [], 0
    for street, r in chosen:
        if street in batch:
            lat, lon = batch[street]
        else:
            g = geocode.geocode(f"{street}, {r.get('property_city') or ''}, CT", save=save)
            if not g.ok:
                failed += 1
                continue
            lat, lon = g.data["lat"], g.data["lon"]
        located.append({"address": street, "owner": r.get("owner"), "match_type": r.get("match_type"),
                        "confidence": r.get("confidence"), "lat": lat, "lon": lon})
    return {"located": located, "failed": failed, "shown": len(chosen), "total": total,
            "from_census_batch": len(batch)}


def _pgeo(landlord_f: Future) -> Future:
    def run():
        ll = landlord_f.result()
        pf = ll.get("portfolio") if ll else None
        if not pf or not pf.ok or not pf.data["results"]:
            return None
        return locate_parcels(pf.data["results"], pf.data["total_matches"])
    return _POOL.submit(run)


def _chain(landlord_f: Future) -> Future:
    """One extra level of the ownership trail, after the landlord lookup (it needs the registry record)."""
    def run():
        ll = landlord_f.result()
        reg = ll.get("registry") if ll else None
        if not ll or reg is None or not reg.ok or not ll["parcels"].ok:
            return None
        owner = ll["parcels"].data["primary"]["owner"]
        tr = trail.find_trail(owner, reg.data)
        located = locate_parcels(tr.data["parcels"], tr.data["parcels_total"]) if tr.ok and tr.data["parcels"] else None
        return {"trail": tr, "located": located}
    return _POOL.submit(run)


def start_job(address: str) -> Job:
    geo_f = _POOL.submit(geocode.geocode, address)
    landlord_f = _after_geo(geo_f, _landlord(address))
    return Job(
        address, geo_f,
        block=_after_geo(geo_f, lambda g: core_run(g, address)),
        street=_after_geo(geo_f, lambda g: complaints.fetch_complaints(g["lat"], g["lon"]) if _in_ct(g) else None),
        landlord=landlord_f, pgeo=_pgeo(landlord_f), chain=_chain(landlord_f))


def result_or_error(fut: Future) -> tuple[object | None, str | None]:
    """(value, None) or (None, message). A crashed worker becomes a message, never an exception on the page."""
    try:
        return fut.result(), None
    except Exception as exc:  # the page must never crash
        return None, f"{type(exc).__name__}: {exc}"
