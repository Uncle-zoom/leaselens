# LeaseLens data check

Run: 2026-10-20 22:24 (live run of 2026-10-20, replayed from saved samples). Three New Haven addresses, every relevant source called live; real results saved to `data/samples/` for offline use.

**Status key:** PASS = live call succeeded and returned records; PASS-EMPTY = live call worked but found nothing; FAIL = the live call failed (the app would use the saved sample); SKIPPED = an upstream source returned nothing.

## Addresses

| # | Group | Address | Why |
|---|---|---|---|
| 1 | New Haven | 360 State Street, New Haven, CT | assigned: downtown condo/apartment tower, owner mails from New York |
| 2 | New Haven | 100 York Street, New Haven, CT | assigned: University Towers, 12+ unit apartment building near Yale |
| 3 | New Haven | 365 Orchard Street, New Haven, CT | my pick: a 12+ unit apartment building in a residential neighborhood west of downtown, owned by a local LLC (Adar Investments) that owns many other New Haven parcels, so it exercises the registry and portfolio chain |

## Router

| Address | Geocoded as | Markets chosen |
|---|---|---|
| 360 State Street, New Haven, CT | New Haven, South Central Connecticut Planning Region, CT | core, ct |
| 100 York Street, New Haven, CT | New Haven, New Haven, CT | core, ct |
| 365 Orchard Street, New Haven, CT | New Haven, New Haven, CT | core, ct |

**New York City: coming soon.** The `sources/nyc/` code is written but switched off (not tested, not called); NYC addresses currently get the nationwide block report only. Boston/other-state fallback was not re-tested in this round.

## Nationwide (OpenStreetMap)

| Source | Dataset (name, id, URL) | Pass | Seconds (median / max) | Records (min–max) | Fields returned | Sample of what came back |
|---|---|---|---|---|---|---|
| **geocode** | OpenStreetMap Nominatim search API — id `nominatim/search` — https://nominatim.openstreetmap.org/search | 3/3 | 0.5 / 0.7 | 1–1 | query, lat, lon, display_name, house_number, road, city, county, state, state_code (+6 more) | *360 State Street, New Haven, CT*: lat 41.30544, lon -72.92321; New Haven, South Central Connecticut Planning Region, CT 06510 |
| **places** | OpenStreetMap via Overpass API (interpreter) — id `overpass/interpreter` — https://overpass-api.de/api/interpreter | 3/3 | 47.9 / 72.4 | 46–125 | category, distance_m, group, kind, lat, lon, name, osm | *360 State Street, New Haven, CT*: counts {'grocery': 13, 'gym': 2, 'park': 29, 'bus_stop': 36, 'train_station': 2, 'pharmacy': 2, 'bar': 12, 'pub': 7, 'nightclub': 3, 'fire_station': 1, 'rail_line': 1}. Nearest: Elm City Market (grocery, 27 m); bus_stop (bus_stop, 55 m); bus_stop (bus_stop, 66 m) |
| **walking** | OSRM foot routing (public servers), else straight-line estimate — id `osrm/table/foot` — https://router.project-osrm.org/table/v1/foot/ | 3/3 | 0.9 / 0.9 | 8–12 | method, category, kind, lat, lon, name, straight_m, walk_m, walk_min | *360 State Street, New Haven, CT*: method=osrm_fossgis_foot; Elm City Market: 0.1 min (8 m); bus_stop: 1.4 min (107 m) |

### Nationwide (OpenStreetMap): result per address

| Address | geocode | places | walking |
|---|---|---|---|
| 360 State Street, New Haven, CT | PASS 0.2s n=1 | PASS 47.9s n=108 | PASS 0.9s n=12 |
| 100 York Street, New Haven, CT | PASS 0.7s n=1 | PASS 72.4s n=125 | PASS 0.9s n=9 |
| 365 Orchard Street, New Haven, CT | PASS 0.5s n=1 | PASS 47.4s n=46 | PASS 0.9s n=8 |

### Nationwide (OpenStreetMap): weak spots and the fallback I recommend

- Overpass is the slow part: 47-72 s per address on 2026-10-20 (main server ~40 s even for a tiny query; a mirror answered in 2-4 s on a later test). Fallback: query the mirrors first, cache per block in data/samples/, show the map first and fill places in as they arrive.
- The OSRM demo server's `foot` profile returns car speeds (~7 m/s), so it is rejected by a speed check. Walking times come from the public routing.openstreetmap.de foot instance (`osrm_fossgis_foot`); if that is down, straight-line x 1.3 at 5 km/h is used and the method is recorded.
- OSM coverage is uneven (many bus stops have no name; convenience stores are tagged `convenience`, not grocery). The 800 m radius is straight-line; walking minutes are the real test.

## Connecticut

| Source | Dataset (name, id, URL) | Pass | Seconds (median / max) | Records (min–max) | Fields returned | Sample of what came back |
|---|---|---|---|---|---|---|
| **complaints** | SeeClickFix public API v2 - issues (New Haven, CT and other participating places) — id `seeclickfix/api/v2/issues` — https://seeclickfix.com/api/v2/issues | 3/3 | 2.6 / 3.4 | 54–100 | request_type, count, open, address, created_at, distance_m, request_type, status, summary, url | *360 State Street, New Haven, CT*: 87 issues since 2025-10-21: Public Space - Snow Related 10, Traffic Signal / Pedestrian Signal 8, PUBLIC SPACE ENFORCEMENT 7, Illegal Dumping 5 |
| **parcels** | 2026 Connecticut Parcel and CAMA Data (Office of Policy and Management) — id `ibe8-9i3q` — https://data.ct.gov/resource/ibe8-9i3q.json | 3/3 | 0.3 / 0.6 | 1–5 | address_number, appraised_total, assessed_total, cama_site_link, link, location, mailing_address, mailing_address_2, mailing_city, mailing_state (+9 more) | *360 State Street, New Haven, CT*: 360  STATE ST / owner ANSONIA STATE STREET LLC / mail 192 LEXINGTON AVE, NEW YORK NY / use CONDO MAIN |
| **registry** | Connecticut Business Registry - Business Master (+ Principals ka36-64k6, Agents qh2m-n44y) — id `n7gp-d28j / ka36-64k6 / qh2m-n44y` — https://data.ct.gov/resource/n7gp-d28j.json | 3/3 | 1.3 / 1.4 | 2–8 | accountnumber, annual_report_due_date, billing_unit, billingcity, billingpostalcode, billingstate, billingstreet, business_type, citizenship, date_registration (+8 more) | *360 State Street, New Haven, CT*: Ansonia State Street LLC (LLC, Active, formed DELAWARE); agent C T CORPORATION SYSTEM; principals Ansonia Apartments, L.P.; matched by exact name |
| **portfolio** | 2026 Connecticut Parcel and CAMA Data (Office of Policy and Management) — id `ibe8-9i3q` — https://data.ct.gov/resource/ibe8-9i3q.json | 3/3 | 0.9 / 1.4 | 0–88 | address_number, confidence, link, location, mailing_address, mailing_city, mailing_state, match_type, owner, property_city (+3 more) | *100 York Street, New Haven, CT*: 2 other parcels/buildings {'exact name': 2}; e.g. 379  GEORGE ST [exact name/high]; 390  GEORGE ST [exact name/high] |

### Connecticut: result per address

| Address | complaints | parcels | registry | portfolio |
|---|---|---|---|---|
| 360 State Street, New Haven, CT | PASS 3.4s n=87 | PASS 0.3s n=5 | PASS 0.9s n=3 | PASS-EMPTY 1.4s n=0 |
| 100 York Street, New Haven, CT | PASS 2.6s n=100 | PASS 0.6s n=1 | PASS 1.4s n=8 | PASS 0.7s n=2 |
| 365 Orchard Street, New Haven, CT | PASS 1.6s n=54 | PASS 0.3s n=1 | PASS 1.3s n=2 | PASS 0.9s n=88 |

### Connecticut: weak spots and the fallback I recommend

- **New Haven complaints are street-level, not housing.** SeeClickFix issues are mostly snow, signals, parking, dumping and potholes reported on the street. They describe the block, not the building; do not present them as housing-code complaints.
- Parcels are searchable by address (street number + street name + town) but NOT by coordinates: the dataset has no lat/lon. Fallback for a failed address match: statewide parcel GIS layer (spatial query) or the town assessor's CAMA site (`cama_site_link`).
- Portfolio matching by owner name is strong (exact LLC name). Mailing-address matches are weak when the address is a PO box or a shared office, and are marked low confidence. 360 State Street returned 0 other parcels: the LLC owns only that building and its principal is another entity ("Ansonia Apartments, L.P."). Following principals to their other LLCs is the next step, not built yet.
- Registry names differ from parcel names ("ADAR INVESTMENTS LLC" vs "ADAR INVESTMENTS, LLC"); handled by a normalized-name match, flagged medium confidence. Individual owners (people) have no registry record. Principals' home addresses and e-mails are in the raw data and are deliberately not kept.

## Model check (gpt-6-luna via Portkey)

PASS: model `gpt-6-luna` replied `ready` in 4.6 s; usage {'input_tokens': 13, 'cached_tokens': 0, 'output_tokens': 5, 'cost_usd': 3.8e-06}. The key is read from `.env` (this folder first, then the folder above) and is never printed.
