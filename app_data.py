"""Glue used by the app and by generate_agent_samples.py: run the data layer for an address and build its FactSheet."""
from __future__ import annotations

import analysis
from facts import FactSheet, build_fact_sheet
from jobs import result_or_error, start_job
from sources import router

DEMO_ADDRESSES = ["360 State Street, New Haven, CT", "100 York Street, New Haven, CT",
                  "365 Orchard Street, New Haven, CT"]


def sheet_from_job(job, prefs: analysis.Prefs) -> FactSheet | None:
    """FactSheet from a finished Job (None while any part is still loading)."""
    if not all(f.done() for f in (job.geo, job.block, job.street, job.landlord)):
        return None
    geo = result_or_error(job.geo)[0]
    g = geo.data if geo is not None and geo.ok else None
    plan = router.route(g) if g else None
    return build_fact_sheet(job.address, g, result_or_error(job.block)[0], result_or_error(job.street)[0],
                            result_or_error(job.landlord)[0], prefs, bool(plan) and "ct" in plan.markets,
                            plan.coming_soon if plan else (), trail=_trail(job))


def _trail(job) -> dict | None:
    ch = result_or_error(job.chain)[0] if job.chain.done() else None
    return ch["trail"].data if ch and ch["trail"].ok else None


def collect_fact_sheet(address: str, prefs: analysis.Prefs, timeout: float = 120) -> FactSheet:
    job = start_job(address)
    for f in (job.geo, job.block, job.street, job.landlord):
        f.result(timeout=timeout)
    return sheet_from_job(job, prefs)
