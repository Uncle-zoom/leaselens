"""Every number in report.html and slides.html comes from here, and every value here is read or computed from the repo's real files:
output/*.json and *.md, output/usage_log.json, data/samples/, data/prices.json, styles.py, prompts/ and the code itself.
Nothing is typed in by hand. The two builders (build_report.py, build_slides.py) only format what this module returns."""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import styles
import tokenomics
from sources.common import SAMPLES_DIR

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
CONTENT = ROOT / "content"
SHOTS = OUT / "screenshots" / "report"
DEMO = ["360 State Street, New Haven, CT", "100 York Street, New Haven, CT", "365 Orchard Street, New Haven, CT"]
NAME = 'Adedeji "Deji" Adebayo'


def read_json(p: Path):
    return json.loads(p.read_text())


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def sample(tier: str, source: str, key: str) -> dict:
    return read_json(SAMPLES_DIR / tier / f"{source}__{slug(key)}.json")["data"]


def content_file(name: str) -> str:
    """A text file the author wrote. Returned exactly as it is on disk (the builders insert it without changing a character)."""
    return (CONTENT / name).read_text()


def image_uri(name: str, folder: Path | None = None) -> str:
    return "data:image/png;base64," + base64.b64encode(((folder or SHOTS) / name).read_bytes()).decode()


# ------------------------------------------------------------------ speed
def speed() -> dict:
    text = (OUT / "speed.md").read_text()
    g = lambda pat: re.search(pat, text).group(1)  # noqa: E731
    row = lambda label: re.search(rf"\| {re.escape(label)} \| about (\d+) s \| ([\d.]+) s \| ([+-][\d.]+) s \|", text)  # noqa: E731
    lk, ai, tot = row("Lookups (median of runs)"), row("AI team (first, cold run)"), re.search(r"\| \*\*Total\*\* \| about (\d+) s \| \*\*([\d.]+) s\*\* \| ([+-][\d.]+) s \|", text)
    steps = {m.group(1): float(m.group(2)) for m in re.finditer(r"\| ([A-Za-z +()]+?) \| [\d.]+ \| [\d.]+ \| \*\*([\d.]+)\*\* \|", text)}
    return {"address": g(r"Address: \*\*(.+?)\*\*"), "lookups_before": float(lk.group(1)), "lookups_now": float(lk.group(2)),
            "ai_before": float(ai.group(1)), "ai_now": float(ai.group(2)), "total_before": float(tot.group(1)), "total_now": float(tot.group(2)),
            "steps": steps, "runs": int(g(r"(\d+) run\(s\)")), "date": g(r"on (\d{4}-\d{2}-\d{2})")}


# ------------------------------------------------------------------ tokens and cost
def costs() -> dict:
    cs = tokenomics.cost_summary()
    rows = cs["rows"]
    runs = read_json(OUT / "tokenomics_runs.json")
    prices = read_json(ROOT / "data" / "prices.json")["gpt-6-luna"]
    every = cs["every"]
    return {
        "calls_logged": cs["calls_logged"], "calls_averaged": cs["calls_averaged"], "total_usd": cs["total_usd"], "text": cs["text"],
        "total_tokens": sum(r["input_tokens"] + r["output_tokens"] for r in every), "hit_rate": tokenomics.hit_rate(cs["normal"]),
        "avgs": cs["avgs"], "one": cs["one"], "three": cs["three"], "month": cs["month"], "scale": cs["scale"], "assumptions": {
            "addresses": tokenomics.ADDRESSES_PER_MONTH, "group": tokenomics.GROUP_SIZE, "chat": tokenomics.CHAT_TURNS_PER_ADDRESS,
            "emails": tokenomics.NEGOTIATION_EMAILS_PER_ADDRESS},
        "cache": tokenomics.experiment_summary(rows), "quality_notes": tokenomics.quality_comparison(runs["runs"]), "quality": quality(runs["runs"]), "prices": prices,
        "usage_table": tokenomics.usage_table(every)}


def quality(runs: dict) -> dict:
    def verdicts(v):
        return {a: d["verdict"] for a, d in runs[v]["addresses"].items()}

    def ranking(v):
        return [a for _, a in sorted(runs[v]["ranking"] or [])]

    def removed(v):
        return sum(d["removed"] for d in runs[v]["addresses"].values()) + (runs[v]["recommendation_removed"] or 0)
    return {"same_verdicts": sum(verdicts("cached")[a] == v for a, v in verdicts("busted").items()), "n": len(verdicts("busted")),
            "same_ranking": ranking("cached") == ranking("busted"), "removed_cached": removed("cached"), "removed_busted": removed("busted"),
            "same_verdicts_cached_vs_cached": sum(verdicts("cached_warmup")[a] == v for a, v in verdicts("cached").items())}


# ------------------------------------------------------------------ the data layer
def data_check() -> dict:
    d = read_json(OUT / "data_check_results.json")
    src = [s for a in d["addresses"] for s in a["sources"] if s["market"] in ("core", "ct")]      # the NYC adapter is parked: not counted
    live = [s for s in src if s["status"].startswith("PASS")]
    by = {}
    for s in src:
        by.setdefault((s["market"], s["source"]), []).append(s)
    return {"addresses": len({a["address"] for a in d["addresses"]}), "checks": len(src), "passed": len(live), "failed": len(src) - len(live), "sources": len(by),
            "datasets": sorted({s["dataset"]["name"] for s in src if s.get("dataset")}), "mode": d["mode"],
            "addresses_run": sorted({a["address"] for a in d["addresses"]})}


# ------------------------------------------------------------------ measured facts from the saved real data
def ownership_facts() -> dict:
    pf = sample("ct", "portfolio", "365 Orchard St New Haven")
    tr_blake = sample("ct", "trail", "311 BLAKE DEVELOPMENT LLC")
    tr_ansonia = sample("ct", "trail", "ANSONIA STATE STREET LLC")
    tr_bc = sample("ct", "trail", "BC CHAPEL STREET LLC")
    return {"portfolio_total": pf["total_matches"], "portfolio_by_type": pf["counts_by_match_type"], "owner": pf["owner"],
            "names_at_mailing": pf["distinct_owner_names_at_mailing_address"], "mailing": pf["mailing"],
            "blake": {"owner": tr_blake["owner"], "entity": tr_blake["entities"][0]["name"], "companies_total": tr_blake["companies_total"],
                      "companies_shown": tr_blake["companies_shown"], "parcels_total": tr_blake["parcels_total"]},
            "ansonia": {"entity": tr_ansonia["entities"][0]["name"], "companies_total": tr_ansonia["companies_total"], "parcels_total": tr_ansonia["parcels_total"]},
            "bc": {"entity": tr_bc["entities"][0]["name"], "companies_total": tr_bc["companies_total"], "parcels_total": tr_bc["parcels_total"]}}


def trace(address: str = DEMO[0]) -> dict:
    """One real run, step by step, from the saved samples of that address."""
    import agent_store
    from sources import router
    key = address
    geo = sample("core", "geocode", key)
    plan = router.route(geo)
    places = sample("core", "places", f"{geo['lat']:.4f}_{geo['lon']:.4f}")
    street = sample("ct", "complaints", f"{geo['lat']:.4f}_{geo['lon']:.4f}")
    parcel = sample("ct", "parcels", key)["primary"]
    reg = sample("ct", "registry", parcel["owner"])
    pf = sample("ct", "portfolio", f"{' '.join(parcel['location'].split())} {parcel['property_city']}")
    tr = sample("ct", "trail", parcel["owner"])
    facts = agent_store.load("facts", address)
    saved = agent_store.load("address", address)
    removed = sum(len(saved[k]["removed"]) for k in ("block", "landlord", "email_ask_questions", "email_negotiate", "email_negotiate_firm") if saved.get(k))
    return {"address": address, "geo": geo, "markets": plan.markets, "places_counts": {k: v for k, v in places["counts"].items() if v},
            "places_total": sum(places["counts"].values()), "street_total": street["total_issues"], "street_top": street["results"][0]["request_type"],
            "parcel": parcel, "registry": reg["business"], "principals": [p["name__c"] for p in reg["principals"]], "agents": [a["name__c"] for a in reg["registered_agents"]],
            "portfolio_total": pf["total_matches"], "trail": tr, "facts_chars": len(json.dumps(facts["data"], indent=1, ensure_ascii=False)),
            "scores": facts["data"]["scores"], "flagged": saved["flagged_untrusted_strings"], "removed_total": removed,
            "calls": {k: {"tokens": saved[k]["tokens"], "usd": saved[k]["usd"], "removed": len(saved[k]["removed"])}
                      for k in ("block", "landlord", "email_ask_questions", "email_negotiate", "email_negotiate_firm") if saved.get(k)},
            "block": saved["block"]["output"], "landlord": saved["landlord"]["output"], "email_firm": saved["email_negotiate_firm"]["output"],
            "chat": saved["chat_examples"]}


# ------------------------------------------------------------------ agents (read from the code and the prompts)
def agents() -> dict:
    prompts = {p.stem: p.read_text() for p in (ROOT / "prompts").glob("*.md")}
    team_src = (ROOT / "team.py").read_text()
    tools = re.findall(r"@agent\.tool\s+def (\w+)", team_src)
    roles = {}
    for name, text in prompts.items():
        if name == "shared":
            continue
        title = re.search(r"# Role: (.+)", text).group(1)
        first = next(line.strip() for line in text.splitlines()[2:] if line.strip() and not line.startswith("#"))
        roles[name] = {"title": title, "first": first}
    outputs = re.findall(r"output_type=(\w+)|self\._call\(\"(\w+)\", (\w+)", team_src)
    models = dict((m[1], m[2]) for m in outputs if m[1])
    return {"roles": roles, "tools": tools, "models": models, "shared_chars": len(prompts["shared"]), "model_name": re.search(r'REQUIRED_MODEL = "(.+?)"', team_src).group(1)}


# ------------------------------------------------------------------ safety evidence (the repo's own code is run here, offline)
def safety() -> dict:
    import tempfile

    import under_the_hood as uth
    import usage_log
    scratch = Path(tempfile.mkdtemp()) / "usage_log.json"          # the stand-in demos below must not add rows to the real usage log
    real_append = usage_log.append
    usage_log.append = lambda entry, log=None: real_append(entry, log or scratch)
    try:
        return _safety(uth)
    finally:
        usage_log.append = real_append


def _safety(uth) -> dict:
    from guardrails import BANNED_EVERYWHERE, BANNED_IN_EMAILS, banned_in, wording_filter
    from models import EmailDraft
    live = read_json(OUT / "safety_live.json")
    planted = EmailDraft(purpose="negotiate", tone="firm", subject="Terms", facts_cited=[],
                         body="Hello,\nThe parcel record lists ANSONIA STATE STREET LLC.\nWe will report this to the city.\nI will take legal action.\nPlease reply in writing.")
    clean, removed = wording_filter(planted, BANNED_EVERYWHERE + BANNED_IN_EMAILS)
    reg_files = list((SAMPLES_DIR / "ct").glob("registry__*.json"))
    raw = "".join(p.read_text() for p in reg_files).lower()
    stored = " ".join(x for x in re.findall(r'"([a-z_]+)":', raw))
    agent_texts, email_texts = "", ""
    for p in (SAMPLES_DIR / "agents").glob("address__*.json"):
        d = read_json(p)
        agent_texts += json.dumps({k: v for k, v in d.items() if k != "facts"})
        email_texts += " ".join(f"{d[k]['output']['subject']} {d[k]['output']['body']}" for k in d if k.startswith("email_") and d[k])
    return {"injection": uth.injection_demo(), "fact_check": uth.fact_check_demo(), "cost_cap": uth.cost_cap_demo(), "live": live,
            "wording": {"before": planted.body, "after": clean.body, "removed": [r.to_dict() for r in removed]},
            "privacy": {"registry_samples": len(reg_files), "residence_fields": stored.count("residence"), "email_fields": len(re.findall(r'"(email|business_email_address)"', raw)),
                        "banned_words_in_saved_ai_output": len(banned_in(agent_texts, BANNED_EVERYWHERE)),
                        "threat_or_legal_words_in_saved_emails": len(banned_in(email_texts, BANNED_IN_EMAILS))},
            "contrast": contrast()}


def contrast() -> dict:
    def lum(h):
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
        r, g, b = (f(int(h.lstrip("#")[i:i + 2], 16) / 255) for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    out = []
    for theme, t in styles.TOKENS.items():
        for label, fg, bg, need in styles.CONTRAST_PAIRS:
            a, b = lum(t[fg]), lum(t[bg])
            out.append({"theme": theme, "pair": label, "fg": t[fg], "bg": t[bg], "ratio": (max(a, b) + 0.05) / (min(a, b) + 0.05), "need": need})
    return {"pairs": out, "n": len(out), "failing": [p for p in out if p["ratio"] < p["need"]], "lowest": min(out, key=lambda p: p["ratio"] / p["need"])}


def tests_collected() -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True)
    m = re.search(r"(\d+) tests? collected", r.stdout) or re.search(r"(\d+) tests collected", r.stdout + r.stderr)
    return int(m.group(1)) if m else int(r.stdout.strip().splitlines()[-1].split()[0])


def repo_check() -> dict:
    r = subprocess.run([sys.executable, "scripts/check_repo.py"], cwd=ROOT, capture_output=True, text=True)
    first = re.search(r"files that would be in the repo: (\d+) \(([\d.]+) MB\)", r.stdout)
    return {"files": int(first.group(1)), "mb": float(first.group(2)), "ok": "no problems found" in r.stdout}


def limits() -> dict:
    import analysis
    pf = sample("ct", "portfolio", "365 Orchard St New Haven")
    kinds: dict[tuple, int] = {}
    for m in pf["results"]:
        kinds[(m["match_type"], m["confidence"])] = kinds.get((m["match_type"], m["confidence"]), 0) + 1
    raw = read_json(OUT / "data_check_results.json")
    nyc = [x for a in raw["addresses"] for x in a["sources"] if x["market"] == "nyc"]
    places = [x["seconds"] for a in raw["addresses"] for x in a["sources"] if x["source"] == "places"]
    return {"match_kinds": kinds, "noise_types": [lab for _, lab, _ in analysis.NOISE_ROWS], "nyc_modules": len(list((ROOT / "sources" / "nyc").glob("*.py"))) - 2,
            "nyc_checked": len(nyc), "nyc_passed": sum(x["status"].startswith("PASS") for x in nyc), "places_seconds": (min(places), max(places)),
            "markets": [m for m in ("core", "ct", "nyc")]}


def load() -> dict:
    return {"name": NAME, "speed": speed(), "costs": costs(), "data_check": data_check(), "own": ownership_facts(), "trace": trace(), "agents": agents(),
            "safety": safety(), "tests": tests_collected(), "repo": repo_check(), "limits": limits()}
