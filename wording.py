"""Plain wording for walking times, used by the cards, the answers and the map tooltips."""
from __future__ import annotations

NEXT_DOOR_M = 50


def walk_phrase(minutes: float | None, metres: float | None = None, long: bool = True) -> str:
    """'next door' under 50 m, 'under 1 min walk' under a minute, otherwise '2.2 min walk' (or 'min on foot' with long=False)."""
    if minutes is None:
        return "none within 800 m"
    if metres is not None and metres < NEXT_DOOR_M:
        return "next door"
    if minutes < 1:
        return "under 1 min walk"
    return f"{minutes:g} min walk"


def plural(n: int, singular: str, plural_form: str | None = None) -> str:
    """'1 pub', '3 pubs', '1 fire station', '12 companies' (pass plural_form for irregular words)."""
    return f"{n} {singular if n == 1 else (plural_form or singular + 's')}"
