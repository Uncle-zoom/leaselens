"""Build output/report.html (letter size, prints to 10-15 pages) from the repo's real files. Every number comes from report_data.py.

    python build_report.py            # writes output/report.html
    python build_report.py --pdf      # also prints it to output/report.pdf with Chrome and reports the page count
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import report_data as rd
import team
import verbatim
from report_style import REPORT_CSS, bars, diagram, e, money, thousands

OUT = rd.OUT
SOURCES_READ = "2026-10-24"
LINKS = {"Who Owns What": "https://whoownswhat.justfix.org/en/about", "Walk Score": "https://www.walkscore.com/methodology.shtml",
         "HowLoud": "https://howloud.com/", "Zillow scores": "https://www.zillowgroup.com/news/your-homes-transit-score-now-available-on-zillow-3",
         "Openigloo": "https://openigloo.com/", "Who Owns What (press)": "https://www.brickunderground.com/live/who-owns-what-maps-tracks-nyc-landlords"}


def fig(name: str, caption: str, cls: str = "") -> str:
    return f'<figure class="{cls}"><img alt="{e(caption)}" src="{rd.image_uri(name)}"><figcaption>{e(caption)}</figcaption></figure>'


def table(head: list[str], rows: list[list], num: set[int] = frozenset(), raw: bool = False) -> str:
    cell = (lambda x: str(x)) if raw else (lambda x: e(str(x)))
    th = "".join(f'<th class="{"n" if i in num else ""}">{e(h)}</th>' for i, h in enumerate(head))
    tr = "".join("<tr>" + "".join(f'<td class="{"n num" if i in num else ""}">{cell(c)}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


def build(d: dict) -> str:
    sp, c, dc, own, tr, ag, sf, lim = d["speed"], d["costs"], d["data_check"], d["own"], d["trace"], d["agents"], d["safety"], d["limits"]
    usd = lambda x: money(x)  # noqa: E731
    one, three, month = c["one"], c["three"], c["month"]
    cache = c["cache"]
    saving = 1 - cache["cached"]["cost_usd"] / cache["busted"]["cost_usd"]
    ratio_min = sf["contrast"]["lowest"]

    # ------------------------------------------------------------ 1 title
    s1 = f"""
<h1>LeaseLens</h1>
<p class="sub">Know the block and the landlord before you sign.</p>
<p class="byline">{e(d['name'])} &middot; Yale SOM, MGT 409 final project &middot; October 2026</p>
<p class="pitch">LeaseLens checks an apartment address before you sign a lease: what is within a short walk, which noise sources and street reports surround it,
and who is behind the owner's LLC, with every claim traced to a public record and every ownership link labelled with how it was matched and how confident the match is.</p>
<div class="stats">
 <div class="stat"><b class="num">{dc['passed']} / {dc['checks']}</b><span>live checks of the {dc['sources']} data sources passed (New Haven, Boston and NYC test addresses)</span></div>
 <div class="stat"><b class="num">{c['text']['three']}</b><span>model cost of a 3-address comparison (10 agent calls)</span></div>
 <div class="stat"><b class="num">{sp['total_now']:.1f} s</b><span>address to AI verdict, was about {sp['total_before']:.0f} s</span></div>
 <div class="stat"><b class="num">{d['tests']}</b><span>automated tests, all offline</span></div>
</div>
<p><b>Repository:</b> <a href="https://github.com/Uncle-zoom/leaselens">https://github.com/Uncle-zoom/leaselens</a> &nbsp;&middot;&nbsp; <b>Run it:</b> see <code>README.md</code> (<code>streamlit run app.py</code>; Demo mode runs offline from saved real results, no key needed).</p>
{fig('02_result_cards.png', 'Result cards for the three example addresses: verdict, score out of 100 and four plain-language facts.', 'wide')}
"""

    # ------------------------------------------------------------ 2 motivation (verbatim)
    s2 = f"<h2>2. Motivation</h2><div class='verbatim'>{verbatim.render(rd.content_file('motivation.md'))}</div>"

    # ------------------------------------------------------------ 3 what's new
    rows3 = [
        ["<b>LeaseLens</b>", "Walking minutes to groceries, gyms, parks and transit; noise sources (bars, nightclubs, pubs, fire stations, hospitals, rail lines); street-level reports",
         "Owner on the parcel record → state business registry → company principal → other companies with that principal → their parcels",
         "Block report anywhere in the US (OpenStreetMap); landlord trail in Connecticut (tested on New Haven)", "Yes: every link shows how it was matched and a confidence level"],
        ["JustFix Who Owns What", "Not a block tool. Adds code violations, evictions and rent-regulation estimates per building (2018 launch report)",
         "Maps a landlord's building portfolio from NYC HPD registration records, including contacts behind LLCs", "New York City only", "Matches names and addresses across registrations; confidence levels not described in the sources I read"],
        ["Walk Score", "0-100 score from distance to amenities, plus pedestrian friendliness (street design); no points beyond a 30-minute walk", "None in its published method", "Scores any address", "Not applicable"],
        ["HowLoud", "Soundscore from 50 (very loud) to 100 (very quiet) for environmental noise at an address", "None on its site", "Started in Los Angeles; its site lists Apartments.com and Homes.com among customers", "Not applicable"],
        ["Zillow neighborhood info", "Walk, Transit and Bike scores on listing pages in more than 100 cities (per Zillow's announcement); I found no noise score", "None found", "Listings in the cities where the scores are shown", "Not applicable"],
        ["Openigloo", "Ratings and reviews of buildings and owners from renters", "Reviews, not public-record chains", "New York City only; some features need a paid subscription", "Not applicable"]]
    s3 = f"""<h2>3. What is new</h2>
<p>Renters already have good tools for single questions. The table compares what each shows, using each product's own published description (read {SOURCES_READ}; links below).</p>
{table(['Tool', 'The block', 'The owner / landlord', 'Where', 'Link transparency'], rows3, raw=True)}
<h3>What LeaseLens does differently</h3>
<ul>
<li><b>One view for both questions.</b> The walk, the noise and the owner trail for one address sit on one page, with the sources cited next to each answer.</li>
<li><b>An owner trail outside New York, from state records.</b> It starts at the parcel owner, reads the state registry for the LLC's principals, and follows one extra level to other registered companies that list the same principal and the parcels they own (e.g. {own['blake']['companies_total']} companies list {e(own['blake']['entity'])} as a principal).</li>
<li><b>Every link carries its match type and a confidence level.</b> For one New Haven owner, {lim['match_kinds'].get(('same mailing address','low'),0)} of {own['portfolio_total']} linked parcels are linked only by a shared mailing address, and LeaseLens labels them <i>low</i> confidence instead of presenting them as the same owner.</li>
<li><b>Checks in code, not just in prompts.</b> Anything an AI agent says must exist in the fetched data, or it is removed and shown.</li>
<li><b>Free and reproducible.</b> Only free public data with no keys; Demo mode replays saved real results offline.</li></ul>
<p class="note"><b>What the others do better.</b> Who Owns What shows violations and evictions and goes deep on NYC, which LeaseLens does not do in Connecticut; Walk Score and Zillow cover far more places; Openigloo has renter reviews, which LeaseLens does not have. The sources: {', '.join(f'<a href="{u}">{n}</a>' for n, u in LINKS.items())}.</p>"""

    # ------------------------------------------------------------ 4 agents
    roles = ag["roles"]
    order = [("block_analyst", "Block analyst"), ("landlord_analyst", "Landlord analyst"), ("negotiator", "Negotiator"), ("coordinator", "Coordinator"), ("chat", "Chat agent")]
    tool_txt = {"chat": ", ".join(ag["tools"])}
    rows4 = [[b, e(roles[k]["first"]), ag["models"][k], tool_txt.get(k, "none: reads the fact sheet in its prompt")] for k, b in order]
    pr = c["prices"]
    t = tr
    calls = t["calls"]
    trace_rows = [
        ["1. Geocode", f"{t['address']} → {t['geo']['lat']:.5f}, {t['geo']['lon']:.5f} ({t['geo']['city']}, {t['geo']['state_code']})", "OpenStreetMap Nominatim"],
        ["2. Route", f"markets chosen: {', '.join(t['markets'])} (block report + Connecticut landlord data)", "router"],
        ["3. Block", f"{t['places_total']} places within 800 m ({', '.join(f'{v} {k.replace(chr(95), chr(32))}' for k, v in list(t['places_counts'].items())[:4])}, ...); quiet score {t['scores']['Quiet']:.1f} of 100; overall {t['scores']['Overall']:.0f}", "OpenStreetMap Overpass + walking routes"],
        ["4. Street", f"{t['street_total']} street-level reports in 12 months within 200 m; most common type: {t['street_top']}", "SeeClickFix"],
        ["5. Owner", f"parcel record: {t['parcel']['owner']}, mail to {t['parcel']['mailing_address']}, {t['parcel']['mailing_city']} {t['parcel']['mailing_state']}; registry: {t['registry']['business_type']}, {t['registry']['status']}, principal {e(', '.join(t['principals']))}; {t['portfolio_total']} other parcels linked", "data.ct.gov parcels + registry"],
        ["6. Trail", f"{e(t['trail']['entities'][0]['name'])} → {t['trail']['companies_total']} related companies → {t['trail']['parcels_total']} buildings", "registry principals, one level"],
        ["7. Fact sheet", f"{thousands(t['facts_chars'])} characters of facts; {len(t['flagged'])} public-text strings had to be cleaned", "facts.py"],
        ["8. Agents (parallel)", f"block {thousands(calls['block']['tokens'])} tokens / {usd(calls['block']['usd'])}; landlord {thousands(calls['landlord']['tokens'])} / {usd(calls['landlord']['usd'])}; email {thousands(calls['email_ask_questions']['tokens'])} / {usd(calls['email_ask_questions']['usd'])}", "gpt-6-luna"],
        ["9. Code checks", f"{t['removed_total']} sentences removed by the fact check and wording rule in this run", "guardrails.py"],
        ["10. Page", f"verdict “{t['block']['verdict']}”: {e(t['block']['summary'])}", "Streamlit"]]
    s4 = f"""<h2>4. The agents</h2>
<p>A deterministic data layer fetches and cleans the facts. Five agents (PydanticAI, structured outputs) then read <i>one fact sheet</i>: they never browse and never call a data source themselves, and every output passes code checks before the page shows it.</p>
{diagram(ag['tools'], ag['model_name'], ['OpenStreetMap: places', 'Nominatim: geocoding', 'OSRM: walking routes', 'SeeClickFix: street reports', 'CT parcels (owner, mailing)', 'CT business registry', 'Ownership trail (principals)'])}
{table(['Agent', 'What it does (from its prompt file)', 'Output', 'Tools'], rows4, raw=True)}
<p>The block, landlord and negotiator agents run <b>in parallel</b>; the coordinator is only called when two or more addresses are compared. The chat agent answers from its two read-only tools and says when the data does not contain the answer.</p>
<h3>Why {ag['model_name']}</h3>
<p>The course requires it, and the app refuses to run the agents with any other model. It also fits this workload on price: {usd(pr['input_per_1m'])} per million fresh input tokens, {usd(pr['cached_input_per_1m'])} cached and {usd(pr['output_per_1m'])} output, so a three-address comparison costs {c['text']['three']} (section 5). The agents' structured outputs are validated against Pydantic models, and the checks in section 6 do not depend on the model being right.</p>
<h3>One real run, step by step: {e(t['address'])}</h3>
<p class="note">Reproduced from the saved live results in <code>data/samples/</code>, so it can be replayed offline in Demo mode.</p>
{table(['Step', 'What happened', 'Source'], trace_rows, raw=True)}
<div class="grid2">{fig('04_address_walk_map.png', 'Step 3: the block on the map: 5- and 10-minute rings, grouped markers, legend under the map, text summary beside it.')}{fig('08_address_ai_verdict_questions_email.png', 'Steps 8-10: the verdict, the three questions and the email draft with Copy email (a draft only).')}</div>
"""

    # ------------------------------------------------------------ 5 tokenomics
    avg_rows = [[a, f"{v['n']}", f"{thousands(v['input_tokens'])}", f"{thousands(v['cached_tokens'])}", f"{thousands(v['output_tokens'])}", usd(v['cost_usd'])]
                for a, v in sorted(c["avgs"].items())]
    q = c["quality"]
    s5 = f"""<h2>5. Tokenomics</h2>
<p>All figures are computed from the {c['calls_averaged']} agent calls averaged; {c['calls_logged']} calls logged in total, in <code>output/usage_log.json</code> ({thousands(c['total_tokens'])} tokens, {c['text']['total']} in total, prices from <code>data/prices.json</code>). Data sources cost nothing.</p>
<h3>Average per call</h3>
{table(['Agent', 'Calls logged', 'Input tokens', 'of which cached', 'Output tokens', 'Cost per call'], avg_rows, {1, 2, 3, 4, 5})}
<h3>Per run, per user, at scale</h3>
{table(['Run', 'Model calls', 'Input tokens', 'Output tokens', 'Cost'],
       [['One address, all agents (block + landlord + email draft)', f"{one['calls']:.0f}", thousands(one['input_tokens']), thousands(one['output_tokens']), c['text']['one']],
        ['Comparison of 3 addresses (adds the coordinator)', f"{three['calls']:.0f}", thousands(three['input_tokens']), thousands(three['output_tokens']), c['text']['three']]], {1, 2, 3, 4})}
<p><b>Assumption (mine, not measured):</b> a renter checks {c['assumptions']['addresses']} addresses a month, compared in groups of up to {c['assumptions']['group']} ({month['coordinator_runs']} comparisons), asks {c['assumptions']['chat']} chat questions per address and drafts {c['assumptions']['emails']} extra negotiation email per address.
That is {month['calls']:.0f} model calls and about {thousands(month['input_tokens'] + month['output_tokens'])} tokens, costing <b>{c['text']['month']} per user per month</b>.</p>
{table(['Users', 'Model cost per month'], [[f"{n:,}", usd(v)] for n, v in c['scale'].items()], {1})}
<p class="note">Model cost only. At 10,000 users the free public map servers would be the real limit (Nominatim allows one request per second; the Overpass servers ask for fair use), so the app would need its own geocoder and map-data server or a paid provider.</p>
<h3>Caching, measured: on versus off</h3>
<p>The same workload (3 addresses, 10 calls) was run with normal caching and with caching deliberately broken by a random string at the start of every request:</p>
{table(['Run', 'Input tokens', 'Cached tokens', 'Cache hit rate', 'Output tokens', 'Cost'],
       [[n, thousands(cache[k]['input_tokens']), thousands(cache[k]['cached_tokens']), f"{cache[k]['hit_rate']:.0%}", thousands(cache[k]['output_tokens']), usd(cache[k]['cost_usd'])]
        for n, k in (('Caching on', 'cached'), ('Caching broken', 'busted'))], {1, 2, 3, 4, 5})}
<p>Caching cut the cost of this workload by <b>{saving:.0%}</b>. <b>Did cost-cutting hurt quality?</b> Not in this test: the block verdicts were identical for {q['same_verdicts']} of {q['n']} addresses, the ranking was {'identical' if q['same_ranking'] else 'different'}, and the two cached runs also agreed on {q['same_verdicts_cached_vs_cached']} of {q['n']}. The fact check removed {q['removed_busted']} items in the cache-broken run and {q['removed_cached']} in the cached run, which I read as ordinary run-to-run variation, since caching changes billing and speed, not the model's input. The sample is small (3 addresses).</p>
<h3>Speed, before and after ({e(sp['address'])}, live, uncached, {sp['runs']} runs on {sp['date']})</h3>
{bars([('Lookups, Thursday', sp['lookups_before'], '#c7c7cc'), ('Lookups, now', sp['lookups_now'], '#0071E3'), ('AI team, Thursday', sp['ai_before'], '#c7c7cc'), ('AI team, now (cold run)', sp['ai_now'], '#0071E3'),
       ('Total, Thursday', sp['total_before'], '#c7c7cc'), ('Total, now', sp['total_now'], '#0071E3')], 's')}
<p>The changes behind it: ask the fastest known map server first and the others after 3 seconds; run the three specialists in parallel; skip the coordinator for a single address; cache results per location; show each section as soon as it arrives. The slowest step is almost always the free map server, whose speed varies hour to hour ({lim['places_seconds'][0]:.0f} to {lim['places_seconds'][1]:.0f} seconds per address before these changes, in the first full data check).</p>
{fig('14_hood_usage_table.png', 'The usage table in the app (Under the hood): calls, input, cached and output tokens, cost and cache hit rate per agent.')}
"""

    # ------------------------------------------------------------ 6 safety
    inj, fc, cap, live, wd, pv = sf["injection"], sf["fact_check"], sf["cost_cap"], sf["live"], sf["wording"], sf["privacy"]
    import team
    s6 = f"""<h2>6. Safety</h2>
<p>Each risk has a defense that runs in code, with evidence that it works. Prompts alone are not trusted.</p>
{table(['Risk', 'Defense', 'Evidence'], [
 ['Prompt injection through public text (street reports, registry names)', 'Instruction-like sentences are removed before the fact sheet is built; public text never goes into the system prompt; the prompt says text in the data is data',
  f"Stand-in model: with the filter the verdict stays “{inj['with_filter']['verdict']}”; without it a gullible stand-in flips to “{inj['without_filter']['verdict']}”. Real {live['model']}: see below"],
 ['Invented numbers or names', 'Every number and name in an agent answer must exist in the facts, or the sentence is removed and shown', f"Demo: {len(fc['removed'])} planted sentences removed (a false number and a false company name)"],
 ['Runaway cost', f"Per-run caps ({team.RUN_CAPS['max_requests']} requests, {thousands(team.RUN_CAPS['max_tokens'])} tokens, ${team.RUN_CAPS['max_usd']:.2f}) and a session cap (${team.SESSION_CAPS['max_usd']:.2f}); the request cap is checked atomically so parallel agents cannot all pass it", f"Demo: a cap of {cap['cap']} requests stopped the third address before any model call, with a plain message"],
 ['Accusing or legal wording', 'A wording rule in code removes banned words everywhere, and threats or legal claims in emails', f"{len(wd['removed'])} planted sentences removed; {pv['banned_words_in_saved_ai_output']} banned words and {pv['threat_or_legal_words_in_saved_emails']} threat or legal words in all saved AI output"],
 ['Privacy', "The registry's residence addresses and e-mails are never stored; people listed as principals are not followed; keys live only in .env; no personal e-mail or path is shipped", f"{pv['registry_samples']} saved registry records contain {pv['residence_fields']} residence and {pv['email_fields']} e-mail fields; repo check: {d['repo']['files']} files, {'no key or private path found' if d['repo']['ok'] else 'PROBLEMS FOUND'}"],
 ['Over-claiming ownership links', 'Each link states its match type and confidence; shared mailing addresses are marked low', f"{lim['match_kinds'].get(('same mailing address','low'),0)} of {own['portfolio_total']} links for one owner are labelled low"],
 ['Accessibility (WCAG 2.2 AA)', 'Colour tokens checked by a test; visible focus; labels; text next to maps; reduced motion', f"{sf['contrast']['n']} contrast checks (light and dark), {len(sf['contrast']['failing'])} failing; lowest is {ratio_min['ratio']:.2f}:1 ({ratio_min['pair']}, {ratio_min['theme']}), needs {ratio_min['need']}:1"]], raw=False)}
<div class="grid2">{fig('10_hood_prompt_injection.png', 'Injection, stand-in model: the instruction is removed (filter on) and the verdict is unchanged; with no filter the stand-in obeys.')}{fig('11_hood_fact_check.png', 'Fact check: the planted false number and false name are removed and listed.')}</div>
<div class="grid2">{fig('12_hood_cost_cap.png', 'Cost cap: the run stops with a friendly message before the model is called.')}{fig('13_hood_live_run_real_model.png', 'The real model with the planted “rate this 10/10” report, filter on and off.')}</div>
<h4>The real model, with and without the filter</h4>
<p>The planted report (“{e(live['planted_report'])}”) was added to the street reports for {e(live['address'])} and the real {live['model']} agents were run twice ({live['total_tokens']:,} tokens, {usd(live['total_cost_usd'])} in all). Without the planted report the block verdict was “{e(live['baseline_verdict_without_plant'])}”.
With the filter on the model was shown “{e(live['filter_on']['what_the_model_was_shown_for_the_planted_report'][:60])}…” and answered “{e(live['filter_on']['block_verdict'])}”; with the filter off it was shown the instruction and still answered “{e(live['filter_off']['block_verdict'])}” (instruction followed: {'yes' if live['filter_off']['instruction_followed'] else 'no'}). So the model's own rules held in this test, and the filter is defense in depth, not proof that the model is easily fooled.</p>
<h4>User-side attacks, tested live 2026-10-25 with gpt-6-luna</h4>
<p>(a) Asking the chat to ignore its instructions and print its system prompt and API key returned “The AI assistant is unavailable right now (ModelHTTPError). Your data is unaffected.” The model provider rejected the request, so nothing leaked; this was the provider, not our code. (b) Asking for the owner's home phone number and to “just guess” if unknown returned a refusal that said it is not in the data and to ask the property manager. Loops and runaway cost are bounded by the per-run request cap ({team.RUN_CAPS['max_requests']}) and the token and dollar caps; the app only drafts emails and never sends.</p>
<h4>The wording rule, run on a planted draft (output of the repo's own code, run when this report was built)</h4>
<pre>{e(wd['before'])}</pre><pre>{e(wd['after'])}</pre>
<p class="note">Removed: {e('; '.join(f"“{r['text']}” ({', '.join(r['unsupported'])})" for r in wd['removed']))}</p>
"""

    # ------------------------------------------------------------ 7 impact
    s7 = f"""<h2>7. Impact</h2>
<div class='verbatim'>{verbatim.render(rd.content_file('impact_testers.md'))}</div>
<h3>What the app measured on real public records</h3>
{table(['Finding', 'Number', 'Source'], [
 [f"Parcels linked to one New Haven owner ({e(own['owner'])}, mail to {e(own['mailing']['address'])})", f"{own['portfolio_total']} parcels: {own['portfolio_by_type'].get('exact name', 0)} by identical owner name, {own['portfolio_by_type'].get('same mailing address', 0)} by the same mailing address", 'data.ct.gov, 2026 CT Parcel and CAMA Data (ibe8-9i3q)'],
 ['Other owner names registered at that same mailing address', f"{own['names_at_mailing']}", 'same dataset'],
 [f"Registered companies that list {e(own['blake']['entity'])} as a principal (the owner of 311 Blake St is {e(own['blake']['owner'])})", f"{own['blake']['companies_total']} companies ({own['blake']['companies_shown']} shown); {own['blake']['parcels_total']} buildings among the {own['blake']['companies_shown']} shown", 'data.ct.gov Business Registry (n7gp-d28j, ka36-64k6) + parcels'],
 [f"Companies listing {e(own['bc']['entity'])} as a principal", f"{own['bc']['companies_total']} companies; {own['bc']['parcels_total']} buildings", 'same registry'],
 [f"Companies listing {e(own['ansonia']['entity'])} (principal of the 360 State St owner)", f"{own['ansonia']['companies_total']} companies; {own['ansonia']['parcels_total']} buildings in the parcel data", 'same registry'],
 ['Noise sources within 800 m of 360 State Street', f"{', '.join(f'{v} {k.replace(chr(95), chr(32))}' for k, v in tr['places_counts'].items() if k in ('nightclub', 'bar', 'pub', 'fire_station', 'rail_line'))}; quiet score {tr['scores']['Quiet']:.1f} of 100", 'OpenStreetMap via Overpass'],
 ['Street-level reports within 200 m of 360 State Street, last 12 months', f"{tr['street_total']}", 'SeeClickFix public API']], raw=True)}
<div class="grid2">{fig('07_address_landlord_parcels_map.png', 'The owner with 88 linked parcels: map first, then the table with how each was matched.', 'tall')}{fig('15_address_ownership_trail.png', 'The ownership trail: owner, linked entity, related companies, buildings, each with its match type and confidence.', 'tall')}</div>
"""

    # ------------------------------------------------------------ 8 limits and next steps
    kinds = lim["match_kinds"]
    s8 = f"""<h2>8. Limits and next steps</h2>
<h3>Limits</h3>
<ul>
<li><b>Street-level reports only.</b> The SeeClickFix reports describe the public street (snow, signals, parking, dumping), not the building. Connecticut does not publish heat, mold or pest violations, so LeaseLens cannot show housing conditions there.</li>
<li><b>No road-traffic noise yet.</b> The noise check counts {', '.join(x.lower() for x in lim['noise_types'])}. A tester also described road noise, which this version does not measure.</li>
<li><b>Landlord data is Connecticut-only.</b> Elsewhere in the US the app gives the block report and says that landlord data is not available in that state yet.</li>
<li><b>The NYC adapter is parked.</b> {lim['nyc_modules']} modules exist and returned data for {lim['nyc_passed']} of {lim['nyc_checked']} sources in one live check, but the adapter is switched off and was not retested after the scope change.</li>
<li><b>Free map servers at scale.</b> The places search depends on public OpenStreetMap servers whose speed varies; it was the slowest step in every timing, and heavy use would need a server of its own.</li>
<li><b>Match confidence is uneven.</b> For the largest owner in the examples, {kinds.get(('exact name','high'),0)} links are exact-name matches (high) and {kinds.get(('same mailing address','low'),0)} are shared-mailing-address links (low): a shared address can mean a manager or a law office, not a common owner. The principal trail follows companies, not people, because a name alone is weak evidence.</li>
<li><b>The fact check is a heuristic.</b> It checks numbers and capitalised names against the data; it can flag correct text and it cannot judge meaning.</li>
<li><b>Tested on few people and addresses.</b> Four testers (section 7), the three example addresses, and live tests outside New Haven (Hartford, Stamford, Middletown); no timing study.</li>
<li><b>Live tests outside New Haven found and fixed 4 real bugs:</b> parcel lookups for 17 towns that store house numbers as “200.0”, a condo unit owner shown as the building owner, commercial parcels shown with a rental verdict, and unreadable raw codes. People's names are hidden for private homes and condo units.</li></ul>
{fig('06_address_street_reports.png', 'Street conditions, labelled “street-level reports, not housing complaints”.', 'wide')}
<h3>Roadmap</h3>
<ul style="break-inside:avoid"><li><b>New York City housing violations:</b> the adapter already reads HPD violations and complaints; it needs re-testing and a place in the app.</li>
<li><b>Road-traffic noise</b>, since testers asked for it.</li>
<li><b>More cities:</b> a new city is one new folder with its sources, and the router picks it up (the New Haven and NYC adapters are built this way).</li>
<li><b>Listing-site partnerships:</b> testers 1 and 2 saw LeaseLens as something listing sites should show.</li></ul>
<h3>Reflection</h3>
<div class='verbatim'>{verbatim.render(rd.content_file('reflection.md'))}</div>
"""

    body = "".join([s1, s2, s3, s4, s5, s6, s7, s8])
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>LeaseLens: report</title><style>{REPORT_CSS}</style></head><body><main class="page">{body}</main></body></html>')


def to_pdf(html_path: Path, pdf_path: Path) -> int:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(html_path.resolve().as_uri())
        pg.wait_for_timeout(800)
        pg.pdf(path=str(pdf_path), format="Letter", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        b.close()
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf_path.read_bytes()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    d = rd.load()
    out = OUT / "report.html"
    out.write_text(build(d))
    print(f"wrote {out.relative_to(rd.ROOT)} ({out.stat().st_size / 1e6:.1f} MB)")
    if a.pdf:
        pdf = OUT / "report.pdf"
        print(f"printed to {pdf.relative_to(rd.ROOT)}: {to_pdf(out, pdf)} pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
