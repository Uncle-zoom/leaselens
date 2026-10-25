"""Simple line icons (24x24 viewBox, Feather-style paths) shared by the page and the map. Always decorative: text carries the meaning."""
from __future__ import annotations

PATHS = {
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "check-circle": '<circle cx="12" cy="12" r="10"/><path d="m8 12 3 3 5-6"/>',
    "minus": '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "basket": '<path d="m5 11 4-7M19 11l-4-7M2 11h20l-2 9H4z"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "bus": '<rect x="4" y="3" width="16" height="14" rx="3"/><path d="M4 11h16M8 21v-4M16 21v-4M8 14h.01M16 14h.01"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M16 7l3 3"/>',
    # map markers
    "cart": '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6"/>',
    "dumbbell": '<path d="M6.5 6.5v11M17.5 6.5v11M3.5 9v6M20.5 9v6M6.5 12h11"/>',
    "tree": '<path d="M12 22v-6M12 2 6 10h3l-4 6h14l-4-6h3z"/>',
    "train": '<rect x="5" y="3" width="14" height="14" rx="3"/><path d="M5 11h14M9 21l2-4M15 21l-2-4M9 14h.01M15 14h.01"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "mug": '<path d="M5 8h11v9a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3zM16 10h2a2 2 0 0 1 0 5h-2M8 3v2M12 3v2"/>',
    "music": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "flame": '<path d="M12 22c4 0 7-3 7-7 0-3-2-5-3-7-1 2-2 3-4 3 0-3-1-5-3-7-1 3-4 5-4 11 0 4 3 7 7 7z"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    "building": '<path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6"/>',
}


def svg(name: str, size: str = "", extra: str = "") -> str:
    dims = f' width="{size}" height="{size}"' if size else ""
    return (f'<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"{dims} fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" {extra}>{PATHS.get(name, PATHS["info"])}</svg>')
