"""Run the agent team LIVE once on the 3 demo addresses and save the results to data/samples/agents/.

    python generate_agent_samples.py [--only "360 State"]

Facts come from the saved data samples (so they are stable); only the model calls are live.
Also geocodes (live, once) the other parcels of each demo address so the landlord map works offline.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import agent_store
import analysis
from app_data import DEMO_ADDRESSES, collect_fact_sheet
from guardrails import Budget
from sources.common import load_env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--skip-geocode", action="store_true")
    ap.add_argument("--firm-only", action="store_true", help="only add the live Firm negotiation draft to each saved address (about 0.1 cent)")
    args = ap.parse_args()
    load_env()
    import team
    ok, why = team.ai_configured()
    if not ok:
        raise SystemExit(f"cannot run live agents: {why}")
    addresses = [a for a in DEMO_ADDRESSES if not args.only or args.only.lower() in a.lower()]
    prefs = analysis.Prefs()

    if args.firm_only:
        from facts import FactSheet
        t = team.Team(session=Budget("this run", max_requests=20, max_tokens=100_000, max_usd=0.05))
        for a in DEMO_ADDRESSES:
            sheet = FactSheet(a, agent_store.load("facts", a)["data"])
            saved = agent_store.load("address", a)
            firm = t.negotiator(sheet, Budget("this email", **team.CHAT_CAPS), "negotiate", "firm")
            saved["email_negotiate_firm"] = firm.to_dict()
            agent_store.save("address", a, saved)
            print(a, "| firm draft:", len(firm.output.body.split()), "words | removed:", len(firm.removed), "| tokens", firm.tokens, "| $", round(firm.usd, 5), flush=True)
        return 0

    # 1) geocode each demo address's other parcels once, live, and save them as samples
    import jobs
    from sources.ct import parcels, portfolio
    if not args.skip_geocode:
        os.environ["LEASELENS_NO_CACHE"] = "1"
        for a in DEMO_ADDRESSES:
            os.environ["LEASELENS_OFFLINE"] = "1"
            primary = parcels.find_parcel(a, "New Haven").data["primary"]
            pf = portfolio.find_portfolio(primary)
            os.environ["LEASELENS_OFFLINE"] = "0"
            if pf.ok and pf.data["results"]:
                res = jobs.locate_parcels(pf.data["results"], pf.data["total_matches"], save=True)
                print(f"geocoded {len(res['located'])}/{res['shown']} other parcels for {a}", flush=True)
        del os.environ["LEASELENS_NO_CACHE"]
    os.environ["LEASELENS_OFFLINE"] = "1"      # data from samples; the model calls below are still live

    session = Budget("this generation run", max_requests=400, max_tokens=2_000_000, max_usd=1.0)
    t = team.Team(session=session)
    sheets = [collect_fact_sheet(a, prefs) for a in addresses]
    t0 = time.time()
    run_budget = Budget("this run", max_requests=80, max_tokens=400_000, max_usd=0.5)
    result = t.coordinate(sheets, run_budget)
    for s in sheets:
        per = result["addresses"][s.address]
        neg = t.negotiator(s, run_budget, "negotiate")
        chat = []
        history = None
        for q in ["How far is the nearest grocery store, and does it meet my limit?",
                  "Who owns this building and what else do they own?",
                  "What is the monthly rent and are pets allowed?"]:
            try:
                ans, history = t.chat(s, q, history, Budget("this question", **team.CHAT_CAPS))
                chat.append({"question": q, **ans.to_dict()})
            except Exception as exc:
                chat.append({"question": q, "error": f"{type(exc).__name__}: {exc}"})
        agent_store.save("facts", s.address, {"address": s.address, "data": s.data})
        agent_store.save("address", s.address, {
            "address": s.address, "priorities": prefs.__dict__, "flagged_untrusted_strings": s.flagged,
            "block": per["block"].to_dict() if "block" in per else None,
            "landlord": per["landlord"].to_dict() if "landlord" in per else None,
            "email_ask_questions": per["email"].to_dict() if "email" in per else None,
            "email_negotiate": neg.to_dict(), "chat_examples": chat})
    if result["recommendation"]:
        agent_store.save("recommendation", agent_store.recommendation_key([s.address for s in sheets]), {
            "addresses": [s.address for s in sheets], "priorities": prefs.__dict__,
            **result["recommendation"].to_dict()})
    print(json.dumps({"errors": result["errors"], "requests": run_budget.requests, "tokens": run_budget.tokens,
                      "usd": round(run_budget.usd, 5), "seconds": round(time.time() - t0, 1)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
