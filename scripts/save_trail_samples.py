"""Run the ownership-trail source LIVE once and save the results to data/samples/ct/ so Demo mode and the tests work offline.

    python scripts/save_trail_samples.py

Covers the three demo owners and two extra real owners used by the tests: BC CHAPEL STREET LLC (a company principal linked to 24 other
registered companies) and 311 BLAKE DEVELOPMENT LLC (a principal linked to 239 companies, so the 30-company cap shows).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LEASELENS_OFFLINE"] = "0"
os.environ["LEASELENS_NO_CACHE"] = "1"

import jobs  # noqa: E402
from sources.common import load_env  # noqa: E402
from sources.ct import registry, trail  # noqa: E402

load_env()
OWNERS = ["ANSONIA STATE STREET LLC", "UNIVERSITY TOWERS OWNERS CORP", "ADAR INVESTMENTS LLC", "BC CHAPEL STREET LLC", "311 BLAKE DEVELOPMENT LLC"]
for owner in OWNERS:
    reg = registry.find_business(owner, save=True)
    if not reg.ok or reg.origin != "live":
        print(f"{owner}: registry lookup {'failed' if not reg.ok else 'not live'}: {reg.live_error or reg.error}")
        continue
    tr = trail.find_trail(owner, reg.data, save=True)
    d = tr.data if tr.ok else {}
    line = f"{owner}: {tr.origin} {tr.seconds:.1f}s"
    if tr.ok:
        line += (f" | entities {[e['name'] for e in d['entities']]} | companies {d['companies_shown']} of {d['companies_total']} "
                 f"| parcels {d['parcels_shown']} of {d['parcels_total']} | people not followed {d['individual_principals_not_followed']}")
        if d["parcels"]:
            located = jobs.locate_parcels(d["parcels"], d["parcels_total"], save=True)
            line += f" | located {len(located['located'])}/{located['shown']}"
    else:
        line += f" | FAILED {tr.live_error}"
    print(line, flush=True)
