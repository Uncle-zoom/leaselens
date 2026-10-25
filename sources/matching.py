"""Name and address normalisation used for ownership matching.

Every portfolio link records HOW it was matched and a confidence level (CLAUDE.md).
"""
from __future__ import annotations

import re

_SUFFIX = {
    "LIMITED LIABILITY COMPANY": "LLC", "L L C": "LLC", "LLC": "LLC",
    "INCORPORATED": "INC", "INC": "INC", "CORPORATION": "CORP", "CORP": "CORP",
    "COMPANY": "CO", "CO": "CO", "LIMITED PARTNERSHIP": "LP", "L P": "LP", "LP": "LP",
    "LIMITED": "LTD", "LTD": "LTD", "LLP": "LLP",
}
_STREET = {
    "STREET": "ST", "ST": "ST", "AVENUE": "AVE", "AV": "AVE", "AVE": "AVE", "ROAD": "RD", "RD": "RD",
    "BOULEVARD": "BLVD", "BLVD": "BLVD", "DRIVE": "DR", "DR": "DR", "PLACE": "PL", "PL": "PL",
    "LANE": "LN", "LN": "LN", "COURT": "CT", "CT": "CT", "SQUARE": "SQ", "SQ": "SQ",
    "PARKWAY": "PKWY", "PKWY": "PKWY", "TERRACE": "TER", "TER": "TER", "HIGHWAY": "HWY", "HWY": "HWY",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
}
ORDINAL = re.compile(r"\b(\d+)(ST|ND|RD|TH)\b")


def _words(text: str) -> list[str]:
    text = (text or "").upper().replace("&", " AND ")
    text = re.sub(r"[.,;:'\"()*#/\\-]+", " ", text)
    return text.split()


def normalize_name(name: str) -> str:
    """'Ansonia State Street, L.L.C.' and 'ANSONIA STATE STREET LLC' -> same string."""
    words = _words(name)
    joined = " ".join(words)
    for long_form, short in (("LIMITED LIABILITY COMPANY", "LLC"), ("L L C", "LLC"), ("L P", "LP")):
        joined = joined.replace(long_form, short)
    return " ".join(_SUFFIX.get(w, w) for w in joined.split())


def strip_entity_suffix(norm_name: str) -> str:
    words = norm_name.split()
    while words and words[-1] in {"LLC", "INC", "CORP", "CO", "LP", "LTD", "LLP"}:
        words.pop()
    return " ".join(words)


def looks_like_entity(name: str) -> bool:
    return any(w in {"LLC", "INC", "CORP", "CO", "LP", "LTD", "LLP", "TRUST", "ASSOCIATES", "PARTNERS",
                     "OWNERS", "HOLDINGS", "REALTY", "PROPERTIES", "MANAGEMENT", "UNIVERSITY", "CITY"}
               for w in normalize_name(name).split())


def normalize_address(addr: str) -> str:
    words = [_STREET.get(w, w) for w in _words(addr)]
    return ORDINAL.sub(r"\1", " ".join(words))


def is_po_box(addr: str) -> bool:
    return bool(re.match(r"\s*(P\.?\s*O\.?\s*BOX|POST OFFICE BOX)\b", (addr or "").upper()))


def split_street_address(address: str) -> tuple[str, str]:
    """'360 State Street, New Haven, CT' -> ('360', 'STATE'). The street suffix is dropped
    because CT parcel records store street_name without it ('STATE', 'YORK')."""
    first = address.split(",")[0].strip()
    m = re.match(r"^(\d+[A-Za-z]?)\s+(.*)$", first)
    if not m:
        return "", ""
    number, street = m.group(1), m.group(2)
    words = [w for w in _words(street)]
    suffixes = set(_STREET) - {"NORTH", "SOUTH", "EAST", "WEST", "N", "S", "E", "W"}
    while words and words[-1] in suffixes:
        words.pop()
    words = [_STREET[w] if w in suffixes else w for w in words]       # 'MAIN STREET EXT' -> 'MAIN ST EXT', as the parcel file writes it
    return number, " ".join(words)
