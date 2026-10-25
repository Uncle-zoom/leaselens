"""Ownership trail (one extra level), its caps and wording, and the Friendly / Firm email tones. All offline."""
import re
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import analysis
import guardrails
import summary
import team
import ui_html
import usage_log
from app_data import DEMO_ADDRESSES, collect_fact_sheet
from guardrails import Budget
from models import EmailDraft
from sources.ct import registry, trail
from tests.conftest import make_app, page_html

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ a tiny fake of the three data.ct.gov tables
class FakeCT:
    def __init__(self, principals, master, parcels):
        self.principals, self.master, self.parcels = principals, master, parcels
        self.calls = []

    def __call__(self, domain, dataset, params, timeout=40):
        self.calls.append((dataset, dict(params)))
        where = params.get("$where", "")
        if dataset == trail.PRINCIPALS:
            m = re.search(r"upper\(name__c\)='(.*)'", where)
            if m:
                return [r for r in self.principals if r["name__c"].upper() == m.group(1).replace("''", "'")][: params.get("$limit", 99999)]
            m = re.search(r"upper\(name__c\) like '(.*)%'", where)
            return [r for r in self.principals if r["name__c"].upper().startswith(m.group(1))][: params.get("$limit", 99999)]
        if dataset == trail.MASTER:
            ids = re.findall(r"'([^']+)'", where)
            return [self.master[i] for i in ids if i in self.master]
        if dataset == trail.PARCELS_ID:
            names = {n.replace("''", "'") for n in re.findall(r"'((?:[^']|'')*)'", where)}
            rows = sorted((r for r in self.parcels if r["owner"].upper() in names), key=lambda r: (r["owner"], r["location"]))
            if "count(*)" in params.get("$select", ""):
                return [{"n": str(len(rows))}]
            return rows[: params.get("$limit", 99999)]
        raise AssertionError(dataset)


def world(n_companies=3, parcels_per_company=1, extra_principals=()):
    principals = [{"business_id": "OWNER", "name__c": "Alpha Holdings, L.P."}] + [dict(r) for r in extra_principals]
    master, parcels = {"OWNER": {"id": "OWNER", "name": "Owner Tower LLC", "business_type": "LLC", "status": "Active"}}, []
    for k in range(n_companies):
        bid = f"B{k:03d}"
        principals.append({"business_id": bid, "name__c": "Alpha Holdings, L.P." if k % 2 == 0 else "ALPHA HOLDINGS LP"})
        master[bid] = {"id": bid, "name": f"{k} Elm Street LLC", "business_type": "LLC", "status": "Active" if k % 5 else "Dissolved", "billingcity": "New Haven", "billingstate": "CT"}
        parcels += [{"location": f"{k}  ELM ST  {u}", "property_city": "New Haven", "owner": f"{k} ELM STREET LLC", "state_use_description": "APT", "link": f"L{k}-{u}"}
                    for u in range(parcels_per_company)]
    return FakeCT(principals, master, parcels)


REG = {"business": {"id": "OWNER", "name": "Owner Tower LLC"}, "principals": [{"name__c": "Alpha Holdings, L.P.", "designation": "Member"},
                                                                              {"name__c": "JANE Q PUBLIC"}],
       "registered_agents": [{"name__c": "C T CORPORATION SYSTEM"}]}


@pytest.fixture
def fake(monkeypatch):
    def install(w):
        monkeypatch.setenv("LEASELENS_OFFLINE", "0")        # run the real code path; the network is replaced by the fake tables
        monkeypatch.setenv("LEASELENS_NO_CACHE", "1")
        monkeypatch.setattr(trail, "socrata", w)
        return w
    return install


# ------------------------------------------------------------------ chain matching
def test_chain_follows_a_company_principal_one_level_and_skips_people_and_agents(fake):
    fake(world(4, 2))
    t = trail.find_trail("OWNER TOWER LLC", REG).data
    assert [e["name"] for e in t["entities"]] == ["Alpha Holdings, L.P."]                  # the person is not followed
    assert t["individual_principals_not_followed"] == 1 and t["registered_agents_not_followed"] == ["C T CORPORATION SYSTEM"]
    e = t["entities"][0]
    assert e["related_total"] == 4 and e["matched_how"] == "listed as a principal on the owner's registry entry" and e["confidence"] == "high"
    assert t["companies_total"] == 4 and t["parcels_total"] == 8 and t["parcels_shown"] == 8
    assert all(c["id"] != "OWNER" for c in e["companies"])                                # never lists the owner itself as "related"


def test_every_link_records_how_it_was_matched_and_a_confidence_level(fake):
    fake(world(4, 1))
    t = trail.find_trail("OWNER TOWER LLC", REG).data
    kinds = {(c["matched_how"], c["confidence"]) for c in t["entities"][0]["companies"]}
    assert kinds == {("same principal name (exact)", "high"), ("same principal name (normalized)", "medium")}     # "Alpha Holdings, L.P." vs "ALPHA HOLDINGS LP"
    for p in t["parcels"]:
        assert p["match_type"] and p["confidence"] in {"high", "medium", "low"} and p["company"] in p["reason"] and "principal" in p["reason"]
    by_company = {p["company"]: p for p in t["parcels"]}
    exact, norm = by_company["0 Elm Street LLC"], by_company["1 Elm Street LLC"]
    assert exact["confidence"] == "high" and norm["confidence"] == "medium"                  # the chain is only as strong as its weakest link
    assert trail.weakest("high", "medium", "high") == "medium" and trail.weakest("high", "high") == "high"


def test_active_companies_are_listed_before_dissolved_ones(fake):
    fake(world(6, 0))
    comps = trail.find_trail("OWNER TOWER LLC", REG).data["entities"][0]["companies"]
    statuses = [c["status"] for c in comps]
    assert statuses == sorted(statuses, key=lambda s: s != "Active")


def test_no_company_principal_means_the_trail_stops_with_a_clear_reason(fake):
    fake(world(3))
    reg = {**REG, "principals": [{"name__c": "JANE Q PUBLIC"}, {"name__c": "JOHN DOE"}]}
    t = trail.find_trail("OWNER TOWER LLC", reg).data
    assert t["entities"] == [] and t["parcels_total"] == 0 and t["individual_principals_not_followed"] == 2
    assert summary.chain_headline(t) == "Owner → no company principal to follow" and "no company as a principal" in summary.chain_sentence(t)
    assert "stops here" in ui_html.chain_html(t)


# ------------------------------------------------------------------ caps
def test_companies_are_capped_at_thirty_with_the_real_total_reported(fake):
    fake(world(45, 1))
    t = trail.find_trail("OWNER TOWER LLC", REG).data
    e = t["entities"][0]
    assert e["related_total"] == 45 and e["related_shown"] == trail.COMPANY_CAP == 30 and len(e["companies"]) == 30
    assert t["companies_total"] == 45 and t["companies_shown"] == 30
    assert t["parcels_total"] == 30                                      # only the shown companies' parcels are searched
    h = ui_html.chain_html(t)
    assert "showing 30 of 45" in h and "45 related companies" in h


def test_parcels_are_capped_at_two_hundred_with_the_true_count(fake):
    fake(world(30, 12))                                                  # 360 parcels
    t = trail.find_trail("OWNER TOWER LLC", REG).data
    assert t["parcels_total"] == 360 and t["parcels_shown"] == trail.PARCEL_CAP == 200 and len(t["parcels"]) == 200
    assert "showing 200 of 360" in ui_html.chain_html(t) and t["caps"] == {"companies": 30, "parcels": 200, "entities": 3}


def test_only_three_company_principals_are_followed(fake):
    extra = [{"business_id": "OWNER", "name__c": f"Beta {k} Group LLC"} for k in range(5)]
    fake(world(2, 0, extra))
    reg = {**REG, "principals": [{"name__c": "Alpha Holdings, L.P."}] + [{"name__c": f"Beta {k} Group LLC"} for k in range(5)]}
    t = trail.find_trail("OWNER TOWER LLC", reg).data
    assert len(t["entities"]) == 3 and t["entities_not_followed"] == 3


def test_it_makes_a_bounded_number_of_requests(fake):
    w = fake(world(45, 12))
    trail.find_trail("OWNER TOWER LLC", REG)
    assert len(w.calls) <= 10                                            # principals (2) + master (<=1 chunk of 100) + parcels (2), not one per company


# ------------------------------------------------------------------ saved live examples (Demo mode and the tests run from these)
def saved(owner):
    reg = registry.find_business(owner)
    assert reg.ok and reg.origin == "sample", owner
    res = trail.find_trail(owner, reg.data)
    assert res.ok and res.origin == "sample", owner
    return res.data


def test_saved_live_example_of_a_company_principal():
    t = saved("ANSONIA STATE STREET LLC")
    assert [e["name"] for e in t["entities"]] == ["Ansonia Apartments, L.P."] and t["companies_total"] == 4
    assert summary.chain_headline(t) == "Owner → Ansonia Apartments, L.P. → 4 related companies → 0 buildings"
    assert "no other registered company" not in summary.chain_sentence(t) and "4 other registered companies list the same principal name" in summary.chain_sentence(t)


def test_saved_live_example_where_the_cap_applies():
    t = saved("311 BLAKE DEVELOPMENT LLC")
    assert t["companies_total"] == 239 and t["companies_shown"] == 30 and t["parcels_total"] == 9
    assert "showing 30 of 239" in ui_html.chain_html(t)
    assert all(p["confidence"] in {"high", "medium"} and p["match_type"] for p in t["parcels"])


def test_saved_live_example_with_buildings():
    t = saved("BC CHAPEL STREET LLC")
    assert t["entities"][0]["name"] == "Beacon Communities Corp." and t["companies_total"] == 24 and t["parcels_total"] == 2
    assert t["parcels"] and all(p["match_type"].startswith("same principal name") for p in t["parcels"])


def test_saved_people_principals_are_not_followed():
    for owner, people in (("UNIVERSITY TOWERS OWNERS CORP", 6), ("ADAR INVESTMENTS LLC", 1)):
        t = saved(owner)
        assert t["entities"] == [] and t["individual_principals_not_followed"] == people


# ------------------------------------------------------------------ the page and the map
def test_address_view_shows_the_trail_with_how_each_link_was_matched():
    at = make_app("detail", detail=0)
    at.run()
    assert not at.exception and not at.error
    html = page_html(at)
    assert "Ownership trail: companies linked through a shared principal" in html
    assert "Owner → Ansonia Apartments, L.P. → 4 related companies → 0 buildings" in html
    for needle in ("Linked entity", "listed as a principal on the owner&#x27;s registry entry, high confidence", "same principal name (normalized)"):
        assert needle in html, needle
    assert any("Limits: 30 companies and 200 parcels shown at most; one level only." in c.value for c in at.caption)
    assert 'aria-label="Ownership trail"' in html and html.count('class="n"') == 4


def test_address_view_explains_when_the_owner_has_only_people_listed():
    at = make_app("detail", detail=2)
    at.run()
    assert not at.exception
    html = page_html(at)
    assert "Owner → no company principal to follow" in html
    assert any("principal(s) are people and were not followed: a name alone is weak evidence" in c.value for c in at.caption)


def test_map_gets_a_separate_toggleable_clustered_layer_for_the_linked_companies_buildings():
    import maps
    own = [{"lat": 41.31, "lon": -72.92, "address": "1 A ST", "owner": "X", "match_type": "exact name", "confidence": "high"}]
    rel = [{"lat": 41.35, "lon": -72.80, "address": "2 B ST", "owner": "Y LLC", "company": "Y LLC", "match_type": "same principal name (exact)", "confidence": "medium"}]
    html = maps.build_block_map(41.3, -72.9, None, None, own, 88, rel, 9).get_root().render()
    assert html.count("markerClusterGroup(") == 2 and "Related companies&#x27; buildings (1 of 9)".replace("&#x27;", "\\u0027") in html
    assert "L.control.layers" in html and "via Y LLC" in html and "medium confidence" in html
    legend = maps.legend_html(True, chain=True)
    assert "companies linked through a shared principal" in legend and "lg rel" in legend
    pm = maps.build_parcel_map(41.3, -72.9, own, 88, rel, 9).get_root().render()
    assert pm.count("markerClusterGroup(") == 2 and "fitBounds(" in pm


# ------------------------------------------------------------------ Friendly / Firm
@pytest.fixture
def sheet():
    return collect_fact_sheet(DEMO_ADDRESSES[2], analysis.Prefs())


@pytest.fixture(autouse=True)
def _no_real_log(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_log, "LOG", tmp_path / "usage_log.json")


def email_model(body, seen=None, subject="Terms for [unit number]"):
    def fn(messages, info: AgentInfo):
        if seen is not None:
            seen.append(str(messages))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"purpose": "negotiate", "subject": subject, "body": body, "facts_cited": []})])
    return lambda: FunctionModel(fn)


def test_the_tone_reaches_the_model_and_is_kept_on_the_draft(sheet):
    seen = []
    for tone in ("friendly", "firm"):
        c = team.Team(email_model("Hello, thanks. [Your name]", seen)).negotiator(sheet, Budget(**team.RUN_CAPS), "negotiate", tone)
        assert c.output.tone == tone and c.output.purpose == "negotiate"
    assert 'Tone: "friendly"' in seen[0] and 'Tone: "firm"' in seen[1] and "Tone: &quot;" not in seen[1]


def test_prompt_describes_both_tones_and_the_firm_rules():
    p = (ROOT / "prompts" / "negotiator.md").read_text()
    assert 'Tone "friendly"' in p and 'Tone "firm"' in p
    firm = p.split('Tone "firm"')[1]
    for needle in ("EVERY fact", "rent", "repairs", "lease terms", "Never threaten", "no deadlines or ultimatums"):
        assert needle in firm, needle


def test_both_tones_go_through_the_fact_check(sheet):
    body = "Hello,\nThere are 4711 bars near the building.\nThe parcel record lists ADAR INVESTMENTS LLC.\nWe also heard that Zenith Holdings LLC is involved.\n[Your name]"
    for tone in ("friendly", "firm"):
        c = team.Team(email_model(body)).negotiator(sheet, Budget(**team.RUN_CAPS), "negotiate", tone)
        assert "4711" not in c.output.body and "Zenith" not in c.output.body and "ADAR INVESTMENTS LLC" in c.output.body
        reasons = " ".join(" ".join(r.unsupported) for r in c.removed)
        assert "4711" in reasons and "Zenith" in reasons


BAD = ["This landlord controls the whole block.", "They are a slumlord.", "It was secretly acquired.", "A shadow landlord network.",
       "I will file a lawsuit.", "We will take legal action.", "Ask your attorney about this.", "This is illegal.", "Please respond or else.",
       "That is a violation of the code.", "Stop this scam."]


@pytest.mark.parametrize("tone", ["friendly", "firm"])
def test_banned_words_never_appear_in_an_email_draft(sheet, tone):
    body = "Hello,\n" + "\n".join(BAD) + "\nThe parcel record lists ADAR INVESTMENTS LLC.\nPlease reply in writing.\n[Your name]"
    c = team.Team(email_model(body, subject="A slumlord controls this")).negotiator(sheet, Budget(**team.RUN_CAPS), "negotiate", tone)
    text = f"{c.output.subject}\n{c.output.body}"
    assert guardrails.banned_in(text, guardrails.BANNED_EVERYWHERE + guardrails.BANNED_IN_EMAILS) == []
    assert "ADAR INVESTMENTS LLC" in c.output.body and "Please reply in writing." in c.output.body        # everything else is kept
    why = {u for r in c.removed for u in r.unsupported}
    assert {"banned wording: controls", "banned wording: slumlord", "banned wording: secretly", "banned wording: lawsuit"} <= why


def test_banned_words_are_removed_from_every_agent_not_only_emails(sheet):
    from models import BlockVerdict
    out = BlockVerdict(verdict="fine", summary="A shadow landlord runs this.", reasons=["The grocery J & J is near.", "He secretly owns it.", "Quiet is 58.0."])
    clean, removed = guardrails.wording_filter(out, guardrails.BANNED_EVERYWHERE)
    assert guardrails.banned_in(" ".join([clean.summary, *clean.reasons])) == [] and len(removed) == 2
    assert clean.reasons == ["The grocery J & J is near.", "Quiet is 58.0."]


def test_wording_filter_keeps_numbered_lists_intact():
    e = EmailDraft(purpose="negotiate", tone="firm", subject="s", body="Please address these points:\n1. Rent: whether it can be reduced.\n2. Repairs: a written list.\n3. Lease terms: the length.", facts_cited=[])
    clean, removed = guardrails.wording_filter(e, guardrails.BANNED_EVERYWHERE + guardrails.BANNED_IN_EMAILS)
    assert removed == [] and clean.body == e.body


def test_no_banned_wording_anywhere_in_prompts_docs_outputs_or_app_text():
    """CLAUDE.md: never write 'controls', 'secretly', 'shadow landlord' or 'slumlord' in app output, prompts or docs."""
    import ast
    words = guardrails.BANNED_EVERYWHERE[:6]            # the four CLAUDE.md words in their forms
    hits = []
    files = list((ROOT / "prompts").glob("*.md")) + [ROOT / "README.md"] + list((ROOT / "output").glob("*.md")) + list((ROOT / "data" / "samples" / "agents").glob("*.json"))
    for f in files:
        for rx in words:
            if rx.search(f.read_text()):
                hits.append((f.name, rx.pattern))
    for f in list(ROOT.glob("*.py")) + list((ROOT / "sources").rglob("*.py")):
        if f.name == "guardrails.py":
            continue
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for rx in words:
                    if rx.search(node.value):
                        hits.append((f.name, rx.pattern, node.value[:40]))
    assert not hits, hits


def test_saved_drafts_of_both_tones_exist_for_every_demo_address_and_follow_the_rules():
    import agent_store
    for a in DEMO_ADDRESSES:
        d = agent_store.load("address", a)
        friendly, firm = d["email_negotiate"]["output"], d["email_negotiate_firm"]["output"]
        assert firm["tone"] == "firm" and firm["purpose"] == "negotiate" and friendly.get("tone", "friendly") == "friendly"
        body = firm["body"].lower()
        for needle in ("rent", "repairs", "lease"):
            assert needle in body, (a, needle)
        assert re.search(r"^1\. ", firm["body"], re.M) and re.search(r"^2\. ", firm["body"], re.M) and re.search(r"^3\. ", firm["body"], re.M)   # numbered concessions
        assert guardrails.banned_in(firm["body"] + friendly["body"], guardrails.BANNED_EVERYWHERE + guardrails.BANNED_IN_EMAILS) == []
        assert len(firm["body"].split()) > len(friendly["body"].split())                                      # firm cites every fact: it is longer


def test_the_email_draft_has_a_friendly_firm_switch_in_demo_mode():
    at = make_app("detail", detail=0)
    at.run()
    assert not at.exception
    purpose = next(r for r in at.radio if r.label == "Purpose")
    assert purpose.options == ["Ask questions", "Negotiate"] and not [r for r in at.radio if r.label == "Tone"]     # tone only matters for negotiation
    purpose.set_value("Negotiate")
    at.run()
    tone = next(r for r in at.radio if r.label == "Tone")
    assert tone.options == ["Friendly", "Firm"] and tone.value == "Friendly"
    friendly_text = next(t for t in at.text_area if t.label == "Edit before you send it yourself").value
    tone.set_value("Firm")
    at.run()
    firm_text = next(t for t in at.text_area if t.label == "Edit before you send it yourself").value
    assert not at.exception and firm_text != friendly_text and "rent" in firm_text.lower() and "Please reply in writing" in firm_text
    assert len(firm_text.split()) > len(friendly_text.split())
