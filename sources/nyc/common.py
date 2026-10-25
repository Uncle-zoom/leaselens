"""Small helpers shared by the NYC adapters."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

NYC_DOMAIN = "data.cityofnewyork.us"
NYS_DOMAIN = "data.ny.gov"
BORO_CODE = {"1": "MN", "2": "BX", "3": "BK", "4": "QN", "5": "SI"}
BORO_NAME = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island"}


def split_bbl(bbl: str) -> tuple[str, int, int]:
    """'1009660001' -> ('1', 966, 1)  (borough digit, tax block, tax lot)."""
    bbl = str(bbl).split(".")[0]
    if len(bbl) != 10 or not bbl.isdigit():
        raise ValueError(f"not a 10-digit BBL: {bbl!r}")
    return bbl[0], int(bbl[1:6]), int(bbl[6:])


def make_bbl(boroid: str, block: str | int, lot: str | int) -> str:
    return f"{int(boroid)}{int(block):05d}{int(lot):04d}"


def months_ago(months: int) -> str:
    """SoQL floating timestamp for `months` months ago, e.g. '2025-10-20T00:00:00'."""
    d = datetime.now(timezone.utc) - timedelta(days=round(months * 30.4))
    return d.strftime("%Y-%m-%dT00:00:00")
