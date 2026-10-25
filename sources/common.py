"""Shared plumbing for every LeaseLens data source.

Every source module goes through here so the rules in CLAUDE.md are enforced in one place:
User-Agent with a contact email, per-host rate limiting, a timeout on every call, and a
fallback to data/samples/ when LEASELENS_OFFLINE=1 or the live call fails.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "data" / "samples"

CACHE_DIR = ROOT / ".cache"       # local, gitignored: per-location results of live calls
CACHE_VERSION = 2          # bump when a source's data shape changes: older cache entries are then ignored (v2: parcels carry 'property')
CACHE_TTL_S = 7 * 24 * 3600
DEFAULT_TIMEOUT = 25  # seconds, per HTTP call
# No personal address is shipped in the code (this repo is public). Set LEASELENS_CONTACT_EMAIL in .env: Nominatim and other free services
# ask for a way to contact whoever runs the app.

# Minimum seconds between two calls to the same host. Nominatim's policy is 1 request/second.
MIN_INTERVAL = {
    "nominatim.openstreetmap.org": 1.1,
    "overpass-api.de": 1.0,
    "router.project-osrm.org": 0.5,
    "routing.openstreetmap.de": 0.5,
}
DEFAULT_INTERVAL = 0.25

_last_call: dict[str, float] = {}
_throttle_lock = threading.Lock()


class OfflineError(RuntimeError):
    """Raised instead of making a network call when LEASELENS_OFFLINE=1."""


def load_env() -> None:
    """Load .env from this folder first, then the folder above (first value wins)."""
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(ROOT.parent / ".env", override=False)


def is_offline() -> bool:
    return os.getenv("LEASELENS_OFFLINE", "").strip().lower() in {"1", "true", "yes"}


def user_agent() -> str:
    email = os.getenv("LEASELENS_CONTACT_EMAIL", "").strip()
    return f"LeaseLens/0.1 (Yale SOM MGT 409 student project" + (f"; contact: {email})" if email else ")")


def _throttle(host: str) -> None:
    gap = MIN_INTERVAL.get(host, DEFAULT_INTERVAL)
    with _throttle_lock:
        wait = _last_call.get(host, 0.0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.monotonic()


def http(method: str, url: str, *, params: dict | None = None, data: dict | None = None, files: dict | None = None,
         timeout: float = DEFAULT_TIMEOUT, attempts: int = 2) -> requests.Response:
    """The only function in the data layer that touches the network."""
    if is_offline():
        raise OfflineError(f"LEASELENS_OFFLINE=1: refusing network call to {url}")
    host = requests.utils.urlparse(url).hostname or ""
    headers = {"User-Agent": user_agent(), "Accept": "application/json"}
    last_exc: Exception | None = None
    for attempt in range(attempts):  # by default one retry on transient errors
        _throttle(host)
        try:
            resp = requests.request(method, url, params=params, data=data, files=files, headers=headers, timeout=timeout)
            if resp.status_code in (429, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(2)
                continue
            resp.raise_for_status()
            return resp
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(1)
                continue
            raise
    raise last_exc  # pragma: no cover


def get_json(url: str, params: dict | None = None, timeout: float = DEFAULT_TIMEOUT) -> Any:
    return http("GET", url, params=params, timeout=timeout).json()


def socrata(domain: str, dataset_id: str, params: dict, timeout: float = 40) -> list[dict]:
    """Query a Socrata (SODA 2.x) dataset. No app token is used (no keys allowed)."""
    return get_json(f"https://{domain}/resource/{dataset_id}.json", params, timeout=timeout)


def socrata_str(value: str) -> str:
    """Escape a value for use inside a single-quoted SoQL string."""
    return value.replace("'", "''")


# ---------------------------------------------------------------- samples
def slug(text: str, limit: int = 110) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit] or "x"


def coord_key(lat: float, lon: float) -> str:
    return f"{lat:.4f}_{lon:.4f}"


def sample_path(tier: str, source: str, key: str) -> Path:
    return SAMPLES_DIR / tier / f"{source}__{slug(key)}.json"


def save_sample(tier: str, source: str, key: str, payload: dict) -> Path:
    path = sample_path(tier, source, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    return path


def load_sample(tier: str, source: str, key: str) -> dict | None:
    path = sample_path(tier, source, key)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _cache_file(tier: str, source: str, key: str) -> Path:
    return CACHE_DIR / tier / f"{source}__{slug(key)}.json"


STALE_TTL_S = 60 * 24 * 3600   # a live call that fails may still fall back to a cache entry this old


def _cache_get(tier: str, source: str, key: str, stale_ok: bool = False) -> dict | None:
    if os.getenv("LEASELENS_NO_CACHE"):
        return None
    path = _cache_file(tier, source, key)
    try:
        if path.exists() and time.time() - path.stat().st_mtime < (STALE_TTL_S if stale_ok else CACHE_TTL_S):
            hit = json.loads(path.read_text())
            return hit if hit.get("v") == CACHE_VERSION else None
    except (OSError, ValueError):
        pass
    return None


def _cache_put(tier: str, source: str, key: str, payload: dict) -> None:
    if os.getenv("LEASELENS_NO_CACHE"):
        return
    try:
        path = _cache_file(tier, source, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**payload, "v": CACHE_VERSION}, default=str))
    except OSError:
        pass  # the cache is an optimisation only


# ---------------------------------------------------------------- result
@dataclass
class SourceResult:
    source: str
    tier: str
    key: str
    ok: bool
    origin: str                      # "live", "cache", "sample" (offline or fallback) or "none"
    data: Any = None
    count: int = 0
    fields: list[str] = field(default_factory=list)
    seconds: float = 0.0
    dataset: dict = field(default_factory=dict)   # exact dataset name / id / url used
    error: str | None = None         # why nothing was returned
    live_error: str | None = None    # why the live call failed (set when we fell back to a sample)

    @property
    def live(self) -> bool:
        return self.ok and self.origin == "live"

    def to_dict(self) -> dict:
        return asdict(self)


def run_source(tier: str, source: str, key: str, live: Callable[[], dict], dataset: dict, *,
               count: Callable[[dict], int], fields: Callable[[dict], list[str]],
               save: bool = False) -> SourceResult:
    """Run `live()`; on offline mode or any failure fall back to data/samples/.

    `live` returns a JSON-serialisable dict. With save=True a successful live result is written
    to data/samples/<tier>/ so the project can run offline later.
    """
    start = time.perf_counter()
    live_error = None
    if not is_offline():
        hit = _cache_get(tier, source, key)
        if hit is not None:
            return SourceResult(source, tier, key, True, "cache", hit["data"], count(hit["data"]), fields(hit["data"]),
                                time.perf_counter() - start, hit.get("dataset") or dataset)
        try:
            data = live()
            _cache_put(tier, source, key, {"dataset": dataset, "data": data})
            res = SourceResult(source, tier, key, True, "live", data, count(data), fields(data),
                               time.perf_counter() - start, dataset)
            if save:
                save_sample(tier, source, key, {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                "source": source, "key": key, "dataset": dataset, "data": data})
            return res
        except Exception as exc:  # any live failure -> fall back to an older cached answer, then to the sample
            live_error = f"{type(exc).__name__}: {exc}"
            old = _cache_get(tier, source, key, stale_ok=True)
            if old is not None:
                return SourceResult(source, tier, key, True, "cache", old["data"], count(old["data"]), fields(old["data"]),
                                    time.perf_counter() - start, old.get("dataset") or dataset, live_error=live_error)
    sample = load_sample(tier, source, key)
    if sample is not None:
        data = sample["data"]
        return SourceResult(source, tier, key, True, "sample", data, count(data), fields(data),
                            time.perf_counter() - start, sample.get("dataset") or dataset, live_error=live_error)
    reason = "offline mode and no saved sample" if live_error is None else "live call failed and no saved sample"
    return SourceResult(source, tier, key, False, "none", None, 0, [], time.perf_counter() - start,
                        dataset, error=f"{reason} for key {key!r}", live_error=live_error)


# ---------------------------------------------------------------- geometry
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * math.cos(math.radians(lat)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon
