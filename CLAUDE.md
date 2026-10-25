# LeaseLens: rules for every session

LeaseLens helps renters check an apartment before signing: what is within walking
distance, nearby noise sources, local complaints, and who owns the building (owner LLC
-> Connecticut business registry -> the owner's other parcels). Streamlit app, PydanticAI
agents, MGT 409 final project, due Mon Oct 26 2026 6 PM.
Scope for now: nationwide block report + Connecticut (New Haven) only. NYC code exists but is parked:
do not call or test it; the router sends NYC addresses to the nationwide report.

## Hard rules
- Model: gpt-6-luna only, through Portkey (PORTKEY_API_KEY). Refuse to run with any other MODEL.
- Load .env from this folder first, then the folder above. Never print, log or commit a key.
- Only free public data with no API keys. Send a User-Agent with a contact email, respect
  rate limits (Nominatim 1 req/s), never scrape a site whose terms forbid it.
- Every external call has a timeout and a fallback to the saved samples in data/samples/.
  Offline mode: LEASELENS_OFFLINE=1 must run the whole app from data/samples/ with no network
  (graders may run it when a public API is down).
- Show what public records say, exactly as recorded and cited to the source (owner names,
  registered agents, mailing addresses included). Report facts and counts, not name-calling:
  no labels like "slumlord" in app output. Every ownership link shows how it was matched
  and a confidence level.
- The app drafts emails; it never sends anything.
- Every number or place the agents mention must exist in the fetched data (code check, not prompt).
- Log every model call's input, cached and output tokens and cost to output/usage_log.json.
- Per-run caps on model requests, tokens and dollars.

## Testing: required after EVERY change
1. Add or update tests in tests/ for what you changed (pytest; use data/samples/ so tests run offline).
2. Run `python -m pytest -q` and show the full summary line.
3. Run the offline smoke check (`LEASELENS_OFFLINE=1 python -m pytest -q -m smoke` once it exists).
4. Only if you changed a live data source module, run that one source live once. Otherwise do not
   make live calls (they are slow and expensive).
5. Keep answers short (under 15 lines): what changed, test result line, what is NOT verified yet.
Never say "done" with failing or skipped tests unless you explain why.

## Wording and scope freeze
- Ownership links are "linked to" with a match type and confidence. Never write "controls",
  "secretly", "shadow landlord" or "slumlord" in app output, prompts or docs.
- After the deeper ownership trail and the Friendly/Firm email tone are done, the app is FROZEN:
  only bug fixes, speed fixes and submission prep. No new features unless the user says so.
