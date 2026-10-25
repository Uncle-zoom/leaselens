# LeaseLens speed report

Address: **101 Dwight Street, New Haven, CT**. Live, uncached run(s) on 2026-10-24 10:00, 2 run(s). Times are seconds from the moment the address is submitted.

## Lookups (page content appears as each step finishes)

| Step | Run 1 | Run 2 | Median |
|---|---|---|---|
| Address found (map can draw) | 0.7 | 0.1 | **0.4** |
| Street reports (SeeClickFix) | 3.9 | 1.7 | **2.8** |
| Parcel + registry + other parcels | 4.6 | 2.4 | **3.5** |
| Places + walking (OpenStreetMap) | 5.3 | 2.9 | **4.1** |
| Other parcels placed on the map | 6.6 | 7.9 | **7.3** |
| **All page sections ready** | 5.3 | 2.9 | **4.1** |

## AI team (block analyst, landlord analyst, email draft in parallel; one address, so no coordinator)

| Measure | Run 1 | Run 2 | Median |
|---|---|---|---|
| All three agents done (s) | 11.6 | 0.4 | **6.0** |
| First agent result (s) | 5.0 | 0.3 | 2.6 |
| Model calls / tokens / cost | 3 / 11,966 / $0.0020 | 3 / 11,966 / $0.0020 | |

## Against the Thursday baseline

| | Thursday | Now | Change |
|---|---|---|---|
| Lookups (median of runs) | about 20 s | 4.1 s | -15.9 s |
| AI team (first, cold run) | about 20 s | 11.6 s | -8.4 s |
| **Total** | about 40 s | **15.7 s** | -24.3 s |

## What to know when reading these numbers

- The slowest lookup is almost always the places search: it uses OpenStreetMap's free public Overpass servers, whose speed changes hour to hour (measured here from about 2 s to over 18 s for the same query). The app asks the fastest known server first and the others after 3 s, and shows every other section while it waits.
- Run 1 and run 2 are independent (nothing cached), so their spread is the real run-to-run variation.
- If a later run's AI time is far below the first, the provider answered an identical request from its own cache (the second run sent the same prompts). Use the first run as the realistic cold figure for the AI team; the lookups are uncached in every run.
- AI timing is the model provider's latency at that moment; the specialists run in parallel, so the time is about that of the slowest one.
