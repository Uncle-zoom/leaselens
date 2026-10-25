# LeaseLens

Know the block and the landlord before you sign.

LeaseLens checks an apartment address before you sign a lease: what is really within walking
distance (groceries, gyms, transit), nearby noise sources, street-level reports, and who owns the
building, traced through Connecticut public records (owner on the parcel record -> the state business
registry -> the owner's other parcels). An AI team (PydanticAI, `gpt-6-luna` through Portkey) turns the
facts into a verdict, plain-English landlord notes, questions to ask and a draft email. It never sends anything.

Coverage: anywhere in the US gets the block report (OpenStreetMap); Connecticut also gets street reports and the
landlord trail. New York City code exists in `sources/nyc/` but is switched off ("coming soon").

## Setup (fresh clone)

Needs **Python 3.10 to 3.14** (tested on 3.14; the requirements also resolve for 3.10).

```bash
git clone https://github.com/<your-username>/leaselens.git     # use the URL of this repository
cd leaselens
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

If the folder is synced by Dropbox, OneDrive or iCloud, pause syncing (or exclude `.venv`) while you create the
virtual environment and install: live sync can corrupt it.

### API key (only needed for live AI)

Create a `.env` file **in this folder or in the folder above it** (this folder is read first):

```
PORTKEY_API_KEY=your-portkey-key
MODEL=gpt-6-luna
LEASELENS_CONTACT_EMAIL=you@example.com   # optional: sent in the User-Agent of public-data requests
```

`MODEL` must be `gpt-6-luna`; LeaseLens refuses to run the AI with anything else. The key is never printed or logged.
No key is needed for Demo mode, the tests, or the data layer.

## Run

```bash
streamlit run app.py
```

Open the address Streamlit prints (usually http://localhost:8501).

- **Search by building name:** type a name with no street number (live mode only); LeaseLens asks Nominatim once, shows "We found: ... Is this right?" and continues only on Yes. No match or no house number: it asks for the street address and never guesses.
- **Private homes and condos:** a single-family home or condo unit whose owner looks like a person and receives the tax bill at the property is shown as "a private owner" (it may not be a rental); a condo building with only unit records names no unit owner and is not traced.
- **Demo mode** (sidebar toggle, on by default) runs fully offline from `data/samples/` with the three New Haven demo
  addresses, including saved AI results. No network and no key needed.
- Turn Demo mode off to look up any US address live (Connecticut addresses also get landlord data). Press
  "Get the AI verdict" on the results page to use the model; a cost meter in the sidebar shows tokens and dollars.
- The page flow is: search -> result cards (verdict, score, four plain facts) -> address view (five questions, each with a one-sentence answer and details one tap away) -> side-by-side compare. "Under the hood" (link at the bottom of the search and results pages) shows the guardrails (prompt-injection filter, fact check, cost cap) and the usage table.
- **Ownership trail (Connecticut):** under "Who owns this building?" the app follows the owner company's registry principals one extra level: owner → a company listed as a principal → other registered companies that list the same principal → those companies' parcels. Every link shows how it was matched (exact or normalized name) and a confidence level; at most 30 companies and 200 parcels are shown, with "showing X of Y". People listed as principals and registered agents are not followed (a name alone, or an agent shared by thousands of companies, is weak evidence). Links are described as "linked to", never as control.
- **Email tone:** the draft email has Ask questions / Negotiate, and for Negotiate a Friendly / Firm switch. Firm cites every relevant fact and asks for specific concessions (rent, repairs, lease terms); both stay factual and polite, with no threats or legal claims, and both go through the fact check and the wording rule.
- Design: light by default, dark follows your system setting; all colours and CSS are in `styles.py` (contrast of every pair is tested). Before/after screenshots: `output/screenshots/design_before_after/`.

## Tests

```bash
python -m pytest -q                                   # everything, offline (about 1 to 5 minutes)
LEASELENS_OFFLINE=1 python -m pytest -q -m smoke      # the offline smoke checks
```

All tests run offline from `data/samples/` (the network is blocked during tests) and use a stand-in model, so they
cost nothing and need no key.

## Other commands

```bash
python data_check.py              # live check of every data source; saves data/samples/ and writes output/data_check.md
python data_check.py --report-only   # rebuild that report from saved results, no network
python generate_agent_samples.py  # run the AI team live on the 3 demo addresses and save data/samples/agents/ (costs about 1 cent)
python time_live.py "101 Dwight Street, New Haven, CT" --runs 2 --md output/speed.md   # time live, uncached runs step by step (about 0.4 cents)
python tokenomics.py              # rebuild output/tokenomics.md from output/usage_log.json
python tokenomics.py --run-nocache   # also re-run the measured caching on/off experiment (live, about 3 cents)
python scripts/save_trail_samples.py   # run the ownership-trail source live once and save data/samples/ct/trail__*.json (about 15 s, free)
python generate_agent_samples.py --firm-only   # add a live Firm negotiation draft to each saved demo address (about 0.3 cents)
python safety_live.py             # live prompt-injection test of the real model with the filter on and off (about 0.3 cents)

pip install -r requirements-dev.txt   # only for the next two: Playwright, which drives your installed Google Chrome
python make_screenshots.py        # starts the app in Demo mode and saves report screenshots to output/screenshots/report/
python build_report.py --pdf      # builds output/report.html (+ report.pdf) from the repo's real files; text in content/*.md is inserted unchanged
python build_slides.py            # builds output/slides.html (reveal.js from vendor/, works offline)
python scripts/check_repo.py      # checks the folder is ready to be a public repo (ignored files, no keys, no private paths)
```

## What's in this repo

| Path | What it is |
|---|---|
| `app.py`, `styles.py`, `maps.py` | The Streamlit app (search, result cards, address view, compare); the colour tokens and CSS; the maps |
| `summary.py`, `ui_html.py`, `ui_helpers.py`, `icons.py`, `wording.py` | Plain-language card text and answers; HTML for cards, steps and tables; small page helpers; icons; walking-time wording |
| `sources/` | The data layer, one module per source: `core/` (geocode, OpenStreetMap places, walking times), `ct/` (SeeClickFix, parcels, business registry, portfolio, ownership trail), `nyc/` (written, switched off), `router.py` picks adapters from the address |
| `analysis.py`, `sections.py` | Transparent scoring and the pure builders behind each card section |
| `jobs.py`, `app_data.py` | Background fetching so the page never blocks; glue that builds an address's fact sheet |
| `facts.py`, `guardrails.py` | The fact sheet every agent reads; untrusted-text filter, fact check and spending caps |
| `team.py`, `models.py`, `prompts/` | The agents (block analyst, landlord analyst, negotiator, coordinator, chat), their structured outputs and prompts |
| `ai_runtime.py`, `agent_store.py`, `under_the_hood.py`, `hood_view.py` | Live-or-saved AI results for the page; saved results store; the guardrail demos and their page |
| `usage_log.py`, `tokenomics.py` | Token and cost logging (`output/usage_log.json`); the cost analysis |
| `data/samples/` | Saved real results (data sources and agent outputs) so everything runs offline; `data/prices.json` |
| `output/` | `data_check.md` (source check), `tokenomics.md`, `speed.md`, `usage_log.json`, `safety_live.json`, `screenshots/` |
| `scripts/`, `make_screenshots.py`, `time_live.py` | Report and release helpers: screenshots, speed test, repo-readiness check |
| `tests/` | Offline pytest suite |
| `CLAUDE.md` | The project rules (data, privacy, testing) |

Data sources: OpenStreetMap (Overpass, Nominatim), OSRM foot routing, SeeClickFix public API, data.ct.gov (parcels and
business registry). All free, no keys, each with a User-Agent and rate limiting. Facts and counts only: owner names,
agents and mailing addresses are shown exactly as recorded, each cited to its dataset, and every ownership link shows how
it was matched and how confident that match is.

## Notes for publishing

`.env` (your key), `.venv/`, `.cache/` and `__pycache__/` are in `.gitignore`; `data/samples/` and `output/` are committed on purpose so the
app and tests run offline from a fresh clone. No e-mail address or personal path is stored in the code: set `LEASELENS_CONTACT_EMAIL`
in your own `.env`. Run `python scripts/check_repo.py` before pushing.
