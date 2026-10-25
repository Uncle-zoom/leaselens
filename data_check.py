"""Prove the data first: run every relevant source on 7 addresses, save samples, write output/data_check.md.

    python data_check.py              # live run; saves real results to data/samples/ and writes the report
    python data_check.py --no-save    # live run without touching data/samples/
    LEASELENS_OFFLINE=1 python data_check.py   # replays the saved samples (no network)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sources import router
from sources.common import ROOT, SAMPLES_DIR, is_offline, load_env

OUTPUT = ROOT / "output"

# (group, address, why this address)
ADDRESSES = [
    ("New Haven", "360 State Street, New Haven, CT", "assigned: downtown condo/apartment tower, owner mails from New York"),
    ("New Haven", "100 York Street, New Haven, CT", "assigned: University Towers, 12+ unit apartment building near Yale"),
    ("New Haven", "365 Orchard Street, New Haven, CT",
     "my pick: a 12+ unit apartment building in a residential neighborhood west of downtown, owned by a local LLC "
     "(Adar Investments) that owns many other New Haven parcels, so it exercises the registry and portfolio chain"),
]

MARKET_TITLES = {"core": "Nationwide (OpenStreetMap)", "ct": "Connecticut"}
SOURCE_ORDER = {
    "core": ["geocode", "places", "walking"],
    "ct": ["complaints", "parcels", "registry", "portfolio"],
}


# ------------------------------------------------------------------ running
def run_all(save: bool) -> list[dict]:
    rows = []
    for group, address, why in ADDRESSES:
        print(f"\n=== {address}", flush=True)
        t0 = time.perf_counter()
        out = router.analyze(address, save=save)
        geo = out["geo"]
        plan = out["plan"]
        entry = {"group": group, "address": address, "why": why, "plan": plan.to_dict() if plan else None,
                 "geo": ({k: geo.data[k] for k in ("lat", "lon", "city", "county", "state_code")} if geo.ok else None),
                 "sources": []}

        def add(market: str, name: str, res) -> None:
            if res is None:
                entry["sources"].append({"market": market, "source": name, "status": "SKIPPED", "seconds": 0.0,
                                         "count": 0, "fields": [], "origin": "none", "note": "upstream source returned nothing"})
                return
            if res.live:
                status = "PASS" if res.count > 0 else "PASS-EMPTY"
            else:
                status = "FAIL"
            entry["sources"].append({
                "market": market, "source": name, "status": status, "seconds": round(res.seconds, 2),
                "count": res.count, "fields": res.fields, "origin": res.origin, "dataset": res.dataset,
                "error": res.error, "live_error": res.live_error, "data": res.data})
            print(f"  {market}/{name:<10} {status:<10} {res.seconds:6.1f}s  n={res.count:<5} origin={res.origin}"
                  + (f"  live_error={res.live_error}" if res.live_error else ""), flush=True)

        add("core", "geocode", geo)
        if plan:
            for market in plan.markets:
                for name in SOURCE_ORDER[market]:
                    if market == "core" and name == "geocode":
                        continue
                    add(market, name, out["results"][market].get(name))
        entry["total_seconds"] = round(time.perf_counter() - t0, 1)
        rows.append(entry)
    return rows


# ------------------------------------------------------------------ LLM check
def check_llm() -> dict:
    """One tiny call to gpt-6-luna through Portkey. .env: this folder first, then the folder above."""
    load_env()
    model = os.getenv("MODEL", "gpt-6-luna").strip()
    res = {"model": model, "ok": False, "seconds": None, "error": None, "usage": None}
    if model != "gpt-6-luna":
        res["error"] = f"refusing to run: MODEL is {model!r}, LeaseLens only uses gpt-6-luna"
        return res
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        res["error"] = "PORTKEY_API_KEY not found in .env (this folder or the folder above)"
        return res
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/"),
                    default_headers={"x-portkey-provider": "openai"}, timeout=30, max_retries=0)
    t0 = time.perf_counter()
    try:
        r = client.responses.create(model=model, input="Reply with the single word: ready", max_output_tokens=16)
        res["seconds"] = round(time.perf_counter() - t0, 2)
        u = r.usage
        cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
        prices = json.loads((ROOT / "data" / "prices.json").read_text())[model]
        cost = ((u.input_tokens - cached) * prices["input_per_1m"] + cached * prices["cached_input_per_1m"]
                + u.output_tokens * prices["output_per_1m"]) / 1_000_000
        res.update(ok=True, reply=(r.output_text or "").strip()[:40],
                   usage={"input_tokens": u.input_tokens, "cached_tokens": cached, "output_tokens": u.output_tokens,
                          "cost_usd": round(cost, 8)})
        log = OUTPUT / "usage_log.json"
        entries = json.loads(log.read_text()) if log.exists() else []
        entries.append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "purpose": "data_check ping",
                        "model": model, **res["usage"]})
        log.write_text(json.dumps(entries, indent=2) + "\n")
    except Exception as exc:
        res["seconds"] = round(time.perf_counter() - t0, 2)
        res["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return res


# ------------------------------------------------------------------ report
def short(v, n=90) -> str:
    s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def sample_text(market: str, source: str, d: dict) -> str:
    """A compact human-readable excerpt of what a source returned."""
    try:
        if source == "geocode":
            return f"lat {d['lat']:.5f}, lon {d['lon']:.5f}; {d['city']}, {d['county']}, {d['state_code']} {d['postcode']}"
        if source == "places":
            c = {k: v for k, v in d["counts"].items() if v}
            near = "; ".join(f"{p['name'] or p['kind']} ({p['category']}, {p['distance_m']} m)" for p in d["results"][:3])
            return f"counts {c}. Nearest: {near}"
        if source == "walking":
            r = d["results"][:2]
            return f"method={d['method']}; " + "; ".join(f"{x['name'] or x['category']}: {x['walk_min']} min ({x['walk_m']} m)" for x in r)
        if market == "ct" and source == "complaints":
            return f"{d['total_issues']} issues since {d['since']}: " + ", ".join(f"{g['request_type']} {g['count']}" for g in d["results"][:4])
        if source == "parcels":
            p = d["primary"]
            return (f"{p['location']} | owner {p['owner']} | mail {p.get('mailing_address')}, {p.get('mailing_city')} "
                    f"{p.get('mailing_state')} | use {p.get('state_use_description')}")
        if market == "ct" and source == "registry":
            b = d["business"]
            ag = ", ".join(a["name__c"] for a in d["registered_agents"]) or "none listed"
            pr = ", ".join(p["name__c"] for p in d["principals"][:3]) or "none listed"
            return (f"{b['name']} ({b.get('business_type')}, {b.get('status')}, formed {b.get('formation_place')}); "
                    f"agent {ag}; principals {pr}; matched by {d['matched_how']}")
        if source == "portfolio":
            m = d["results"][:2]
            return (f"{d['total_matches']} other parcels/buildings {d['counts_by_match_type']}; e.g. "
                    + "; ".join(f"{x.get('location') or x.get('address')} [{x['match_type']}/{x['confidence']}]" for x in m))
        if source == "geo":
            return f"BBL {d['bbl']}, BIN {d['bin']}, {d['label']}, confidence {d['confidence']}"
        if market == "nyc" and source == "complaints":
            return f"{d['total_requests']} requests since {d['since']} ({d['noise_requests']} noise): " + ", ".join(
                f"{g['complaint_type']} {g['count']}" for g in d["results"][:4])
        if source == "violations":
            cls = ", ".join(f"class {c['class']}: {c['open']} open/{c['closed']} closed" for c in d["violations_by_class"])
            return f"{d['violations_total']} HPD violations ({cls}); {d['hpd_complaints_last_12_months']} HPD complaints in 12 months"
        if source == "owner":
            o = d["owners"][0]["name"] if d["owners"] else "none registered"
            ag = d["managing_agents"][0]["name"] if d["managing_agents"] else "none"
            return f"PLUTO owner {d['pluto_owner_name']}; HPD owner {o}; agent {ag}; {len(d['results'])} registered contacts"
        if market == "nyc" and source == "registry":
            e = d["entity"]
            return (f"{e['current_entity_name']} ({e.get('entity_type')}, {e.get('jurisdiction')}), DOS id {e['dos_id']}; "
                    f"agent {e.get('registered_agent_name', 'none listed')}")
    except Exception as exc:  # a sample line must never break the report
        return f"(sample unavailable: {exc})"
    return short(d)


def fields_text(fields: list[str], n=10) -> str:
    return ", ".join(fields[:n]) + (f" (+{len(fields) - n} more)" if len(fields) > n else "")


def dataset_text(ds: dict) -> str:
    return f"{ds.get('name')} — id `{ds.get('id')}` — {ds.get('url')}"


RECOMMENDATIONS = {
    "core": [
        "Overpass is the slow part: 47-72 s per address on 2026-10-20 (main server ~40 s even for a tiny query; a mirror answered in 2-4 s on a later test). "
        "Fallback: query the mirrors first, cache per block in data/samples/, show the map first and fill places in as they arrive.",
        "The OSRM demo server's `foot` profile returns car speeds (~7 m/s), so it is rejected by a speed check. Walking times come from the public "
        "routing.openstreetmap.de foot instance (`osrm_fossgis_foot`); if that is down, straight-line x 1.3 at 5 km/h is used and the method is recorded.",
        "OSM coverage is uneven (many bus stops have no name; convenience stores are tagged `convenience`, not grocery). The 800 m radius is straight-line; walking minutes are the real test.",
    ],
    "ct": [
        "**New Haven complaints are street-level, not housing.** SeeClickFix issues are mostly snow, signals, parking, dumping and potholes reported on the street. "
        "They describe the block, not the building; do not present them as housing-code complaints.",
        "Parcels are searchable by address (street number + street name + town) but NOT by coordinates: the dataset has no lat/lon. "
        "Fallback for a failed address match: statewide parcel GIS layer (spatial query) or the town assessor's CAMA site (`cama_site_link`).",
        "Portfolio matching by owner name is strong (exact LLC name). Mailing-address matches are weak when the address is a PO box or a shared office, and are marked low confidence. "
        "360 State Street returned 0 other parcels: the LLC owns only that building and its principal is another entity (\"Ansonia Apartments, L.P.\"). "
        "Following principals to their other LLCs is the next step, not built yet.",
        "Registry names differ from parcel names (\"ADAR INVESTMENTS LLC\" vs \"ADAR INVESTMENTS, LLC\"); handled by a normalized-name match, flagged medium confidence. "
        "Individual owners (people) have no registry record. Principals' home addresses and e-mails are in the raw data and are deliberately not kept.",
    ],
}


def write_report(rows: list[dict], llm: dict, mode: str) -> Path:
    L = [f"# LeaseLens data check", "",
         f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')} ({mode}). Three New Haven addresses, every relevant source called live; "
         "real results saved to `data/samples/` for offline use.", "",
         "**Status key:** PASS = live call succeeded and returned records; PASS-EMPTY = live call worked but found nothing; "
         "FAIL = the live call failed (the app would use the saved sample); SKIPPED = an upstream source returned nothing.", "",
         "## Addresses", "", "| # | Group | Address | Why |", "|---|---|---|---|"]
    for i, e in enumerate(rows, 1):
        L.append(f"| {i} | {e['group']} | {e['address']} | {e['why']} |")
    L += ["", "## Router", "", "| Address | Geocoded as | Markets chosen |", "|---|---|---|"]
    for e in rows:
        g = e["geo"] or {}
        L.append(f"| {e['address']} | {g.get('city')}, {g.get('county')}, {g.get('state_code')} | "
                 f"{', '.join(e['plan']['markets']) if e['plan'] else 'geocode failed'} |")
    L += ["", "**New York City: coming soon.** The `sources/nyc/` code is written but switched off (not tested, not called); "
          "NYC addresses currently get the nationwide block report only. Boston/other-state fallback was not re-tested in this round."]
    for market in ("core", "ct"):
        L += ["", f"## {MARKET_TITLES[market]}", "",
              "| Source | Dataset (name, id, URL) | Pass | Seconds (median / max) | Records (min–max) | Fields returned | Sample of what came back |",
              "|---|---|---|---|---|---|---|"]
        for name in SOURCE_ORDER[market]:
            runs = [(e, s) for e in rows for s in e["sources"] if s["market"] == market and s["source"] == name]
            if not runs:
                continue
            ok = [s for _, s in runs if s["status"].startswith("PASS")]
            secs = [s["seconds"] for _, s in runs if s["status"] != "SKIPPED"]
            counts = [s["count"] for _, s in runs if s["status"].startswith("PASS")]
            first = next(((e, s) for e, s in runs if s["status"] == "PASS" and s.get("data")), None)
            ds = next((s["dataset"] for _, s in runs if s.get("dataset")), {})
            sample = f"*{first[0]['address']}*: " + sample_text(market, name, first[1]["data"]) if first else "—"
            L.append(f"| **{name}** | {dataset_text(ds)} | {len(ok)}/{len(runs)} | "
                     f"{statistics.median(secs):.1f} / {max(secs):.1f} | "
                     f"{(str(min(counts)) + '–' + str(max(counts))) if counts else '—'} | "
                     f"{fields_text(next((s['fields'] for _, s in runs if s['fields']), []))} | {sample.replace('|', '/')} |")
        L += ["", f"### {MARKET_TITLES[market]}: result per address", "",
              "| Address | " + " | ".join(SOURCE_ORDER[market]) + " |", "|---|" + "---|" * len(SOURCE_ORDER[market])]
        for e in rows:
            cells = []
            for name in SOURCE_ORDER[market]:
                s = next((s for s in e["sources"] if s["market"] == market and s["source"] == name), None)
                cells.append("n/a (not routed)" if s is None else f"{s['status']} {s['seconds']:.1f}s n={s['count']}")
            if any(c != "n/a (not routed)" for c in cells):
                L.append(f"| {e['address']} | " + " | ".join(cells) + " |")
        notes = RECOMMENDATIONS.get(market)
        if notes:
            L += ["", f"### {MARKET_TITLES[market]}: weak spots and the fallback I recommend", ""] + [f"- {n}" for n in notes]
    L += ["", "## Model check (gpt-6-luna via Portkey)", ""]
    if llm["ok"]:
        L.append(f"PASS: model `{llm['model']}` replied `{llm.get('reply')}` in {llm['seconds']} s; usage {llm['usage']}. "
                 "The key is read from `.env` (this folder first, then the folder above) and is never printed.")
    else:
        L.append(f"FAIL: {llm['error']}")
    path = OUTPUT / "data_check.md"
    OUTPUT.mkdir(exist_ok=True)
    path.write_text("\n".join(L) + "\n")
    return path


def report_only() -> int:
    """Rebuild the report from the last live run's numbers plus the saved samples. Makes no network calls."""
    os.environ["LEASELENS_OFFLINE"] = "1"
    saved = json.loads((OUTPUT / "data_check_results.json").read_text())
    by_addr = {e["address"]: e for e in saved["addresses"]}
    rows = []
    for group, address, why in ADDRESSES:
        e = by_addr[address]
        data = router.analyze(address)
        for s in e["sources"]:
            res = data["geo"] if s["source"] == "geocode" else data["results"].get(s["market"], {}).get(s["source"])
            s["data"] = res.data if res is not None and res.ok else None
        e["sources"] = [s for s in e["sources"] if s["market"] in ("core", "ct")]
        rows.append({**e, "group": group, "why": why})
    path = write_report(rows, saved["llm"], "live run of 2026-10-20, replayed from saved samples")
    print("wrote", path.relative_to(ROOT))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true", help="do not write data/samples/")
    ap.add_argument("--report-only", action="store_true",
                    help="rebuild output/data_check.md from output/data_check_results.json + data/samples/ (no network)")
    ap.add_argument("--no-llm", action="store_true", help="skip the gpt-6-luna call")
    args = ap.parse_args()
    os.environ["LEASELENS_NO_CACHE"] = "1"   # the check must hit the real services
    load_env()
    if args.report_only:
        return report_only()
    mode = "OFFLINE replay of data/samples" if is_offline() else "live"
    rows = run_all(save=not args.no_save and not is_offline())
    llm = {"ok": False, "error": "skipped", "model": "gpt-6-luna"} if (args.no_llm or is_offline()) else check_llm()
    OUTPUT.mkdir(exist_ok=True)
    slim = [{**e, "sources": [{k: v for k, v in s.items() if k != "data"} for s in e["sources"]]} for e in rows]
    (OUTPUT / "data_check_results.json").write_text(json.dumps({"mode": mode, "llm": llm, "addresses": slim}, indent=2, default=str) + "\n")
    report = write_report(rows, llm, mode)

    print("\n================ SUMMARY ================")
    for market in ("core", "ct"):
        for name in SOURCE_ORDER[market]:
            runs = [s for e in rows for s in e["sources"] if s["market"] == market and s["source"] == name]
            if runs:
                ok = sum(s["status"].startswith("PASS") for s in runs)
                med = statistics.median([s["seconds"] for s in runs if s["status"] != "SKIPPED"] or [0])
                print(f"{market:<5}{name:<11}{ok}/{len(runs)} pass   median {med:5.1f}s")
    fails = [(e["address"], s["market"], s["source"], s.get("live_error") or s.get("error")) for e in rows
             for s in e["sources"] if s["status"] == "FAIL"]
    print(f"live failures: {len(fails)}")
    for f in fails:
        print("  ", f)
    print(f"LLM {llm['model']}: {'PASS' if llm['ok'] else 'FAIL/' + str(llm['error'])}"
          + (f" ({llm['seconds']}s, {llm['usage']})" if llm["ok"] else ""))
    print(f"report: {report.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
