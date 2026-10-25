# LeaseLens tokenomics

All numbers come from `output/usage_log.json` (real `gpt-6-luna` calls through Portkey, prices from `data/prices.json`: $0.10 / 1M fresh input, $0.01 / 1M cached input, $0.50 / 1M output). 127 agent calls averaged; 137 calls logged in total, costing $0.0791. Data sources (OpenStreetMap, SeeClickFix, data.ct.gov) are free and cost $0.

## Measured per call (average)

| Agent | Calls logged | Input tokens | of which cached | Output tokens | Cost per call |
|---|---|---|---|---|---|
| block_analyst | 28 | 3,028 | 695 | 449 | $0.0005 |
| chat | 20 | 4,830 | 3,852 | 189 | $0.0002 |
| coordinator | 6 | 6,072 | 0 | 1,436 | $0.0013 |
| landlord_analyst | 27 | 3,094 | 812 | 466 | $0.0005 |
| negotiator | 46 | 3,197 | 980 | 996 | $0.0007 |

Overall cache hit rate across these calls: **36%** of input tokens were served from cache.

## Cost per run

| Run | Model calls | Input tokens | Output tokens | Cost |
|---|---|---|---|---|
| One address, all agents (block + landlord + email draft) | 3 | 9,319 | 1,911 | $0.0017 |
| Comparison of 3 addresses (3 × those + the coordinator) | 10 | 34,027 | 7,168 | $0.0063 |
| One chat question | 1 | 4,830 | 189 | $0.0002 |

## Cost per user per month

**Assumption.** A renter checks 5 addresses in a month (a typical search: a handful of listings shortlisted, not every listing browsed; this is my assumption, not measured). The app compares up to 3 at a time, so that is 2 comparisons. Each address gets the three specialists, 3 chat questions and 1 extra negotiation email. Costs use the measured per-call averages above; the coordinator is charged at its 3-address cost even for the 2-address group (slightly conservative).

Model calls per user per month: **37** · tokens: **167,415** · cost: **$0.0181** per user per month.

## Cost at scale

| Users | Model cost per month | Notes |
|---|---|---|
| 1 | $0.0181 |  |
| 100 | $1.81 | fits a class project or a pilot |
| 10,000 | $180.81 | see the caveat below |

**Caveat at 10,000 users.** The model bill stays small, but the free public data services would not: Nominatim allows 1 request per second and the Overpass servers ask for fair use, so at that scale LeaseLens would need its own geocoder and map-data server or a paid provider. The cost above is the model only; hosting, Portkey fees and those data services are not included.

## Measured: caching on vs. caching broken

Same workload each time: the 3 demo addresses (3 specialists each + the coordinator = 10 calls), same facts, same prompts. In the broken run a random string is put at the very start of every request, so no prefix can be reused.

| Run | Input tokens | Cached tokens | Cache hit rate | Output tokens | Cost | Seconds (sum of calls) |
|---|---|---|---|---|---|---|
| Cached, run 1 | 34,996 | 12,870 | 37% | 6,786 | $0.0057 | 14 |
| Cached, run 2 | 34,996 | 12,870 | 37% | 6,786 | $0.0057 | 3 |
| Caching broken | 35,202 | 0 | 0% | 7,545 | $0.0073 | 80 |

Run 1 was not cold: the provider's cache already held these instructions from earlier calls that day, so runs 1 and 2 billed alike. The hit rate is only about a third because the specialists of one run start at the same moment (nothing is cached yet for the first wave) and the facts differ per address; repeated and sequential use hits more (chat turns average a far higher rate). The seconds column is the sum of per-call latency and also reflects provider load at that moment, so treat it as indicative only.

**Difference:** caching cut the cost of this workload by **21%** ($0.0073 → $0.0057). Output tokens (which are never cached) are the part that remains.

**Quality difference:**
- two cached runs (the run-to-run noise floor): block verdicts identical for 3 of 3 addresses; ranking identical (360 State Street > 100 York Street > 365 Orchard Street vs 360 State Street > 100 York Street > 365 Orchard Street); items removed by the fact check 0 vs 0.
- cached vs cache-broken: block verdicts identical for 3 of 3 addresses; ranking identical (360 State Street > 100 York Street > 365 Orchard Street vs 360 State Street > 100 York Street > 365 Orchard Street); items removed by the fact check 0 vs 2.
- Caching only changes what is billed and how fast the prompt is processed, not the model's inputs, so any difference above is ordinary run-to-run variation of the model (compare it with the two cached runs).
