"""Time a live (non-demo, uncached) lookup and AI run end to end, step by step.

    python time_live.py ["101 Dwight Street, New Haven, CT"] [--runs 2] [--md output/speed.md] [--no-ai]

Costs about 0.2 cents per run for the AI team. Facts come from the live services; nothing is cached.
"""
import argparse
import os
import statistics
import time
from datetime import datetime
from pathlib import Path

os.environ["LEASELENS_OFFLINE"] = "0"
os.environ["LEASELENS_NO_CACHE"] = "1"     # a first-time visitor: nothing cached

from jobs import result_or_error, start_job  # noqa: E402
from sources.common import load_env  # noqa: E402

load_env()
LABELS = {"geo": "Address found (map can draw)", "street": "Street reports (SeeClickFix)", "landlord": "Parcel + registry + other parcels",
          "block": "Places + walking (OpenStreetMap)", "pgeo": "Other parcels placed on the map", "chain": "Ownership trail (linked entity, related companies, buildings)"}
# Reported from a live test on Thursday (101 Dwight St): lookups about 20 s, AI team about 20 s, about 40 s in all.
BASELINE = {"lookups_s": 20.0, "ai_s": 20.0}


def measure(address: str, with_ai: bool = True) -> dict:
    t0 = time.perf_counter()
    job = start_job(address)
    done: dict[str, float] = {}
    while len(done) < len(job.futures()) and time.perf_counter() - t0 < 120:
        for name, f in job.futures().items():
            if name not in done and f.done():
                done[name] = time.perf_counter() - t0
        time.sleep(0.05)
    out = {"address": address, "steps": done, "lookups_s": max(v for k, v in done.items() if k not in ("pgeo", "chain")), "all_s": max(done.values())}
    ll = result_or_error(job.landlord)[0]
    if ll and ll["portfolio"] is not None and ll["portfolio"].ok:
        out["other_parcels"] = ll["portfolio"].data["total_matches"]
    if with_ai:
        import ai_runtime
        import analysis
        import team
        from app_data import sheet_from_job
        from guardrails import Budget
        sheet = sheet_from_job(job, analysis.Prefs())
        t1 = time.perf_counter()
        handle = ai_runtime.start_live([sheet], Budget("this session", **team.SESSION_CAPS))
        first: dict[str, float] = {}
        while time.perf_counter() - t1 < 120:
            for (_a, kind), f in handle.run.futures.items():
                if f.done() and kind not in first:
                    first[kind] = time.perf_counter() - t1
            if handle.done:
                break
            time.sleep(0.02)
        snap = handle.snapshot_json()
        out["ai"] = {"total_s": time.perf_counter() - t1, "first": first, "calls": snap["run"]["requests"], "tokens": snap["run"]["tokens"],
                     "usd": snap["run"]["usd"], "coordinator_skipped": snap["recommendation"] is None, "errors": snap["errors"]}
    return out


def report(runs: list[dict]) -> str:
    med = lambda xs: statistics.median(xs)  # noqa: E731
    L = [f"# LeaseLens speed report", "", f"Address: **{runs[0]['address']}**. Live, uncached run(s) on {datetime.now():%Y-%m-%d %H:%M}, "
         f"{len(runs)} run(s). Times are seconds from the moment the address is submitted.", "",
         "## Lookups (page content appears as each step finishes)", "", "| Step | " + " | ".join(f"Run {i + 1}" for i in range(len(runs))) + " | Median |",
         "|---|" + "---|" * (len(runs) + 1)]
    for key in ("geo", "street", "landlord", "block", "pgeo", "chain"):
        vals = [r["steps"].get(key) for r in runs]
        if all(v is not None for v in vals):
            L.append(f"| {LABELS[key]} | " + " | ".join(f"{v:.1f}" for v in vals) + f" | **{med(vals):.1f}** |")
    L.append("| **All page sections ready** | " + " | ".join(f"{r['lookups_s']:.1f}" for r in runs) + f" | **{med([r['lookups_s'] for r in runs]):.1f}** |")
    ai = [r["ai"] for r in runs if "ai" in r]
    if ai:
        L += ["", "## AI team (block analyst, landlord analyst, email draft in parallel; one address, so no coordinator)", "",
              "| Measure | " + " | ".join(f"Run {i + 1}" for i in range(len(ai))) + " | Median |", "|---|" + "---|" * (len(ai) + 1),
              "| All three agents done (s) | " + " | ".join(f"{a['total_s']:.1f}" for a in ai) + f" | **{med([a['total_s'] for a in ai]):.1f}** |",
              "| First agent result (s) | " + " | ".join(f"{min(a['first'].values()):.1f}" for a in ai) + f" | {med([min(a['first'].values()) for a in ai]):.1f} |",
              "| Model calls / tokens / cost | " + " | ".join(f"{a['calls']} / {a['tokens']:,} / ${a['usd']:.4f}" for a in ai) + " | |"]
    lk, ai_med = med([r["lookups_s"] for r in runs]), (ai[0]["total_s"] if ai else None)    # AI: the first (cold) run
    L += ["", "## Against the Thursday baseline", "", "| | Thursday | Now | Change |", "|---|---|---|---|",
          f"| Lookups (median of runs) | about {BASELINE['lookups_s']:.0f} s | {lk:.1f} s | {lk - BASELINE['lookups_s']:+.1f} s |"]
    if ai_med is not None:
        L += [f"| AI team (first, cold run) | about {BASELINE['ai_s']:.0f} s | {ai_med:.1f} s | {ai_med - BASELINE['ai_s']:+.1f} s |",
              f"| **Total** | about {BASELINE['lookups_s'] + BASELINE['ai_s']:.0f} s | **{lk + ai_med:.1f} s** | {lk + ai_med - BASELINE['lookups_s'] - BASELINE['ai_s']:+.1f} s |"]
    L += ["", "## What to know when reading these numbers", "",
          "- The slowest lookup is almost always the places search: it uses OpenStreetMap's free public Overpass servers, whose speed changes hour to hour "
          "(measured here from about 2 s to over 18 s for the same query). The app asks the fastest known server first and the others after 3 s, "
          "and shows every other section while it waits.",
          "- Run 1 and run 2 are independent (nothing cached), so their spread is the real run-to-run variation.",
          "- If a later run's AI time is far below the first, the provider answered an identical request from its own cache (the second run sent the same prompts). Use the first run as the realistic cold figure for the AI team; the lookups are uncached in every run.",
          "- AI timing is the model provider's latency at that moment; the specialists run in parallel, so the time is about that of the slowest one.", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("address", nargs="?", default="101 Dwight Street, New Haven, CT")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--md", default=None)
    ap.add_argument("--no-ai", action="store_true")
    a = ap.parse_args()
    runs = []
    for i in range(a.runs):
        r = measure(a.address, with_ai=not a.no_ai)
        runs.append(r)
        print(f"run {i + 1}: lookups {r['lookups_s']:.1f}s" + (f", AI {r['ai']['total_s']:.1f}s" if "ai" in r else "")
              + "  steps: " + ", ".join(f"{k} {v:.1f}" for k, v in sorted(r["steps"].items(), key=lambda kv: kv[1])), flush=True)
    text = report(runs)
    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(text)
        print("wrote", a.md)


if __name__ == "__main__":
    main()
