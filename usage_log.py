"""output/usage_log.json: one row per model call (input, cached and output tokens, cost). Prices: data/prices.json."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "output" / "usage_log.json"
PRICES = ROOT / "data" / "prices.json"
_lock = threading.Lock()


def cost_usd(model: str, input_tokens: int, cached: int, output_tokens: int) -> float:
    """input_tokens includes the cached part; output_tokens includes reasoning tokens."""
    p = json.loads(PRICES.read_text())[model]
    fresh = max(input_tokens - cached, 0)
    return (fresh * p["input_per_1m"] + cached * p["cached_input_per_1m"] + output_tokens * p["output_per_1m"]) / 1_000_000


def append(entry: dict, log: Path | None = None) -> None:
    log = log or LOG
    with _lock:
        log.parent.mkdir(parents=True, exist_ok=True)
        rows = json.loads(log.read_text()) if log.exists() else []
        rows.append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry})
        log.write_text(json.dumps(rows, indent=2) + "\n")
