"""What LeaseLens costs to run, computed from the REAL usage log (output/usage_log.json).

    python tokenomics.py                 # rebuild output/tokenomics.md from the log (no model calls)
    python tokenomics.py --run-nocache   # first run the measured cache experiment (live, about 3 cents), then rebuild

All maths is in plain functions so tests can check it on made-up rows.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import usage_log

ROOT = Path(__file__).resolve().parent
OUT_MD = ROOT / "output" / "tokenomics.md"
RUNS_JSON = ROOT / "output" / "tokenomics_runs.json"
SPECIALISTS = ("block_analyst", "landlord_analyst", "negotiator")

# Assumptions for the monthly figure (stated in the report)
ADDRESSES_PER_MONTH = 5
GROUP_SIZE = 3            # the app compares up to three addresses at once
CHAT_TURNS_PER_ADDRESS = 3
NEGOTIATION_EMAILS_PER_ADDRESS = 1


def load_rows(path: Path | None = None) -> list[dict]:
    path = path or usage_log.LOG
    return json.loads(path.read_text()) if path.exists() else []


def agent_rows(rows: list[dict], cache: str = "on") -> list[dict]:
    """Rows written by the agent team. cache='on' = normal runs, 'off' = the cache-broken experiment, 'all' = both."""
    out = [r for r in rows if r.get("agent") and r.get("input_tokens") is not None]
    if cache == "on":
        return [r for r in out if r.get("cache") != "off"]
    if cache == "off":
        return [r for r in out if r.get("cache") == "off"]
    return out


def hit_rate(rows: list[dict]) -> float:
    inp = sum(r["input_tokens"] for r in rows)
    return sum(r["cached_tokens"] for r in rows) / inp if inp else 0.0


def usage_table(rows: list[dict]) -> list[dict]:
    """Per agent: calls, input / cached / output tokens, cost and cache hit rate (cached / input tokens)."""
    table = []
    for agent in sorted({r["agent"] for r in rows}):
        rs = [r for r in rows if r["agent"] == agent]
        table.append({"agent": agent, "calls": len(rs), "input_tokens": sum(r["input_tokens"] for r in rs),
                      "cached_tokens": sum(r["cached_tokens"] for r in rs),
                      "output_tokens": sum(r["output_tokens"] for r in rs),
                      "cost_usd": round(sum(r["cost_usd"] for r in rs), 6),
                      "cache_hit_rate": round(hit_rate(rs), 3)})
    if rows:
        table.append({"agent": "ALL", "calls": len(rows), "input_tokens": sum(r["input_tokens"] for r in rows),
                      "cached_tokens": sum(r["cached_tokens"] for r in rows),
                      "output_tokens": sum(r["output_tokens"] for r in rows),
                      "cost_usd": round(sum(r["cost_usd"] for r in rows), 6), "cache_hit_rate": round(hit_rate(rows), 3)})
    return table


def per_call_averages(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for agent in {r["agent"] for r in rows}:
        rs = [r for r in rows if r["agent"] == agent]
        out[agent] = {"n": len(rs), "input_tokens": statistics.mean(r["input_tokens"] for r in rs),
                      "cached_tokens": statistics.mean(r["cached_tokens"] for r in rs),
                      "output_tokens": statistics.mean(r["output_tokens"] for r in rs),
                      "cost_usd": statistics.mean(r["cost_usd"] for r in rs)}
    return out


def _sum(avgs: dict, counts: dict[str, float]) -> dict:
    """Tokens and dollars for `counts` calls of each agent, from per-call averages."""
    tot = {"calls": 0.0, "input_tokens": 0.0, "output_tokens": 0.0, "cost_usd": 0.0}
    for agent, n in counts.items():
        a = avgs[agent]
        tot["calls"] += n
        tot["input_tokens"] += n * a["input_tokens"]
        tot["output_tokens"] += n * a["output_tokens"]
        tot["cost_usd"] += n * a["cost_usd"]
    return tot


def single_address_run(avgs: dict) -> dict:
    """One address, all agents: block analyst + landlord analyst + negotiator (the coordinator needs 2+ addresses)."""
    return _sum(avgs, {a: 1 for a in SPECIALISTS})


def comparison_run(avgs: dict, addresses: int = 3) -> dict:
    """A comparison: every specialist for every address, plus one coordinator call."""
    return _sum(avgs, {**{a: addresses for a in SPECIALISTS}, "coordinator": 1})


def monthly_per_user(avgs: dict, addresses: int = ADDRESSES_PER_MONTH, group: int = GROUP_SIZE,
                     chat_turns: int = CHAT_TURNS_PER_ADDRESS, emails: int = NEGOTIATION_EMAILS_PER_ADDRESS) -> dict:
    """A renter checks `addresses` places a month, compared in groups of up to `group` (so ceil(addresses/group)
    coordinator runs). Each address gets the three specialists, `chat_turns` chat questions and `emails` extra
    negotiation emails."""
    groups = -(-addresses // group)
    counts = {"block_analyst": addresses, "landlord_analyst": addresses, "negotiator": addresses * (1 + emails),
              "coordinator": groups}
    if "chat" in avgs:
        counts["chat"] = addresses * chat_turns
    out = _sum(avgs, counts)
    out["coordinator_runs"] = groups
    return out


def at_scale(per_user_usd: float, users: int) -> float:
    return per_user_usd * users


def experiment_summary(rows: list[dict], exp_id: str | None = None) -> dict | None:
    """Group the cache experiment's rows by variant: cached warm-up, cached (steady), busted."""
    ex = [r for r in rows if r.get("experiment")]
    if not ex:
        return None
    exp_id = exp_id or ex[-1]["experiment"]
    ex = [r for r in ex if r["experiment"] == exp_id]
    out = {"experiment": exp_id}
    for v in sorted({r["variant"] for r in ex}):
        rs = [r for r in ex if r["variant"] == v]
        out[v] = {"calls": len(rs), "input_tokens": sum(r["input_tokens"] for r in rs),
                  "cached_tokens": sum(r["cached_tokens"] for r in rs), "output_tokens": sum(r["output_tokens"] for r in rs),
                  "cost_usd": sum(r["cost_usd"] for r in rs), "hit_rate": hit_rate(rs),
                  "seconds": sum(r["seconds"] for r in rs)}
    return out


# ------------------------------------------------------------------ the live experiment
def run_cache_experiment() -> dict:
    """The 3 demo addresses, same workload three times: cached warm-up, cached (steady state), and caching broken
    with a random prefix on every request. Facts come from the saved samples; only the model calls are live."""
    import time
    import agent_store
    import analysis
    from app_data import DEMO_ADDRESSES
    from facts import FactSheet
    from guardrails import Budget
    from sources.common import load_env
    load_env()
    import team
    ok, why = team.ai_configured()
    if not ok:
        raise SystemExit(f"cannot run the experiment: {why}")
    sheets = [FactSheet(a, agent_store.load("facts", a)["data"]) for a in DEMO_ADDRESSES]
    exp_id = time.strftime("nocache-%Y%m%d-%H%M%S")
    results = {}
    for variant, buster in (("cached_warmup", False), ("cached", False), ("busted", True)):
        t = team.Team(cache_buster=buster, tags={"experiment": exp_id, "variant": variant})
        res = t.coordinate(sheets, Budget("this run", max_requests=80, max_tokens=400_000, max_usd=0.5))
        results[variant] = {
            "errors": res["errors"],
            "addresses": {a: {"verdict": per["block"].output.verdict, "reasons": per["block"].output.reasons,
                              "questions": per["landlord"].output.questions,
                              "removed": sum(len(per[k].removed) for k in per)}
                          for a, per in res["addresses"].items() if "block" in per and "landlord" in per},
            "ranking": [(r.rank, r.address) for r in res["recommendation"].output.ranking] if res["recommendation"] else None,
            "recommendation_removed": len(res["recommendation"].removed) if res["recommendation"] else None}
        print(variant, "done", flush=True)
    RUNS_JSON.write_text(json.dumps({"experiment": exp_id, "runs": results}, indent=2, default=str) + "\n")
    return results


def quality_comparison(runs: dict) -> list[str]:
    """Plain-language differences between the cached and the busted run, with the cached-vs-cached difference as the noise floor."""
    def verdicts(v):
        return {a: d["verdict"] for a, d in runs[v]["addresses"].items()}
    def ranking(v):
        return [a for _, a in sorted(runs[v]["ranking"] or [])]
    def removed(v):
        return sum(d["removed"] for d in runs[v]["addresses"].values()) + (runs[v]["recommendation_removed"] or 0)
    notes = []
    for a, b, label in (("cached_warmup", "cached", "two cached runs (the run-to-run noise floor)"), ("cached", "busted", "cached vs cache-broken")):
        if a not in runs or b not in runs:
            continue
        same_v = sum(verdicts(a).get(k) == v for k, v in verdicts(b).items())
        notes.append(f"{label}: block verdicts identical for {same_v} of {len(verdicts(b))} addresses; "
                     f"ranking {'identical' if ranking(a) == ranking(b) else 'different'} ({' > '.join(x.split(',')[0] for x in ranking(a))} vs "
                     f"{' > '.join(x.split(',')[0] for x in ranking(b))}); items removed by the fact check {removed(a)} vs {removed(b)}.")
    return notes


# ------------------------------------------------------------------ report
def money(x: float) -> str:
    """The one way a dollar amount is written in tokenomics.md, report.html and slides.html."""
    return f"${x:,.4f}" if x < 1 else f"${x:,.2f}"


def cost_summary(rows: list[dict] | None = None) -> dict:
    """The single source of every cost figure: reads output/usage_log.json once and returns the numbers plus their final text.
    Averages use the normal-caching agent calls; the total spent counts every logged call (including the cache experiment)."""
    rows = load_rows() if rows is None else rows
    normal, every = agent_rows(rows, "on"), agent_rows(rows, "all")
    avgs = per_call_averages(normal)
    one, three, month = single_address_run(avgs), comparison_run(avgs, 3), monthly_per_user(avgs)
    scale = {n: at_scale(month["cost_usd"], n) for n in (1, 100, 10_000)}
    total = sum(r["cost_usd"] for r in every)
    return {"rows": rows, "normal": normal, "every": every, "avgs": avgs, "one": one, "three": three, "month": month, "scale": scale,
            "total_usd": total, "calls_averaged": len(normal), "calls_logged": len(every),
            "text": {"one": money(one["cost_usd"]), "three": money(three["cost_usd"]), "month": money(month["cost_usd"]),
                     "total": money(total), **{f"scale_{n}": money(v) for n, v in scale.items()}}}


def build_report(rows: list[dict], runs: dict | None) -> str:
    need = set(SPECIALISTS) | {"coordinator"}
    if not need <= set(per_call_averages(agent_rows(rows, "on"))):
        return "# LeaseLens tokenomics\n\nNot enough usage data yet: run `python generate_agent_samples.py` first.\n"
    cs = cost_summary(rows)
    normal, avgs = cs["normal"], cs["avgs"]
    one, three, month = cs["one"], cs["three"], cs["month"]
    L = ["# LeaseLens tokenomics", "",
         "All numbers come from `output/usage_log.json` (real `gpt-6-luna` calls through Portkey, prices from `data/prices.json`: "
         "$0.10 / 1M fresh input, $0.01 / 1M cached input, $0.50 / 1M output). "
         f"{cs['calls_averaged']} agent calls averaged; {cs['calls_logged']} calls logged in total, costing {cs['text']['total']}. Data sources (OpenStreetMap, SeeClickFix, data.ct.gov) are free and cost $0.", "",
         "## Measured per call (average)", "",
         "| Agent | Calls logged | Input tokens | of which cached | Output tokens | Cost per call |", "|---|---|---|---|---|---|"]
    for a in sorted(avgs):
        v = avgs[a]
        L.append(f"| {a} | {v['n']} | {v['input_tokens']:,.0f} | {v['cached_tokens']:,.0f} | {v['output_tokens']:,.0f} | {money(v['cost_usd'])} |")
    L += ["", f"Overall cache hit rate across these calls: **{hit_rate(normal):.0%}** of input tokens were served from cache.", "",
          "## Cost per run", "", "| Run | Model calls | Input tokens | Output tokens | Cost |", "|---|---|---|---|---|",
          f"| One address, all agents (block + landlord + email draft) | {one['calls']:.0f} | {one['input_tokens']:,.0f} | {one['output_tokens']:,.0f} | {money(one['cost_usd'])} |",
          f"| Comparison of 3 addresses (3 × those + the coordinator) | {three['calls']:.0f} | {three['input_tokens']:,.0f} | {three['output_tokens']:,.0f} | {money(three['cost_usd'])} |"]
    if "chat" in avgs:
        L.append(f"| One chat question | 1 | {avgs['chat']['input_tokens']:,.0f} | {avgs['chat']['output_tokens']:,.0f} | {money(avgs['chat']['cost_usd'])} |")
    L += ["", "## Cost per user per month", "",
          f"**Assumption.** A renter checks {ADDRESSES_PER_MONTH} addresses in a month (a typical search: a handful of listings shortlisted, "
          "not every listing browsed; this is my assumption, not measured). The app compares up to "
          f"{GROUP_SIZE} at a time, so that is {month['coordinator_runs']} comparisons. Each address gets the three specialists, "
          f"{CHAT_TURNS_PER_ADDRESS} chat questions and {NEGOTIATION_EMAILS_PER_ADDRESS} extra negotiation email. "
          "Costs use the measured per-call averages above; the coordinator is charged at its 3-address cost even for the 2-address group (slightly conservative).", "",
          f"Model calls per user per month: **{month['calls']:.0f}** · tokens: **{month['input_tokens'] + month['output_tokens']:,.0f}** · "
          f"cost: **{money(month['cost_usd'])}** per user per month.", "",
          "## Cost at scale", "", "| Users | Model cost per month | Notes |", "|---|---|---|"]
    for users, note in ((1, ""), (100, "fits a class project or a pilot"), (10_000, "see the caveat below")):
        L.append(f"| {users:,} | {cs['text'][f'scale_{users}']} | {note} |")
    L += ["", "**Caveat at 10,000 users.** The model bill stays small, but the free public data services would not: Nominatim allows 1 request per "
          "second and the Overpass servers ask for fair use, so at that scale LeaseLens would need its own geocoder and map-data server or a paid provider. "
          "The cost above is the model only; hosting, Portkey fees and those data services are not included.", ""]
    s = experiment_summary(rows)
    if s and "cached" in s and "busted" in s:
        c, b = s["cached"], s["busted"]
        saving = 1 - c["cost_usd"] / b["cost_usd"] if b["cost_usd"] else 0
        L += ["## Measured: caching on vs. caching broken", "",
              "Same workload each time: the 3 demo addresses (3 specialists each + the coordinator = 10 calls), same facts, same prompts. "
              "In the broken run a random string is put at the very start of every request, so no prefix can be reused.", "",
              "| Run | Input tokens | Cached tokens | Cache hit rate | Output tokens | Cost | Seconds (sum of calls) |", "|---|---|---|---|---|---|---|"]
        for name, key in (("Cached, run 1", "cached_warmup"), ("Cached, run 2", "cached"),
                          ("Caching broken", "busted")):
            if key in s:
                v = s[key]
                L.append(f"| {name} | {v['input_tokens']:,} | {v['cached_tokens']:,} | {v['hit_rate']:.0%} | {v['output_tokens']:,} | {money(v['cost_usd'])} | {v['seconds']:.0f} |")
        L += ["", "Run 1 was not cold: the provider's cache already held these instructions from earlier calls that day, so runs 1 and 2 "
              "billed alike. The hit rate is only about a third because the specialists of one run start at the same moment (nothing is cached yet "
              "for the first wave) and the facts differ per address; repeated and sequential use hits more (chat turns average a far higher rate). "
              "The seconds column is the sum of per-call latency and also reflects provider load at that moment, so treat it as indicative only.",
              "", f"**Difference:** caching cut the cost of this workload by **{saving:.0%}** "
              f"({money(b['cost_usd'])} → {money(c['cost_usd'])}). Output tokens (which are never cached) are the part that remains.", ""]
        if runs:
            L += ["**Quality difference:**"] + [f"- {n}" for n in quality_comparison(runs["runs"])] + [
                "- Caching only changes what is billed and how fast the prompt is processed, not the model's inputs, so any difference above "
                "is ordinary run-to-run variation of the model (compare it with the two cached runs).", ""]
    else:
        L += ["## Measured: caching on vs. caching broken", "", "Not run yet: `python tokenomics.py --run-nocache`.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-nocache", action="store_true")
    args = ap.parse_args()
    if args.run_nocache:
        run_cache_experiment()
    runs = json.loads(RUNS_JSON.read_text()) if RUNS_JSON.exists() else None
    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_MD.write_text(build_report(load_rows(), runs))
    print("wrote", OUT_MD.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
