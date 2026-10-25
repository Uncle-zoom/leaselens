"""Saved agent results (data/samples/agents/) so demo mode works with no network and no key."""
from __future__ import annotations

import json
from pathlib import Path

from sources.common import SAMPLES_DIR, slug

AGENTS_DIR = SAMPLES_DIR / "agents"


def _path(kind: str, key: str) -> Path:
    return AGENTS_DIR / f"{kind}__{slug(key)}.json"


def save(kind: str, key: str, payload: dict) -> Path:
    p = _path(kind, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return p


def load(kind: str, key: str) -> dict | None:
    p = _path(kind, key)
    return json.loads(p.read_text()) if p.exists() else None


def recommendation_key(addresses: list[str]) -> str:
    return " | ".join(sorted(a.strip().lower() for a in addresses))
