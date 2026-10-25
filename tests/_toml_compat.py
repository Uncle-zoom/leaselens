"""Read TOML on every supported Python (3.10 to 3.14).

tomllib is in the standard library from 3.11; on 3.10 use tomli (same API) if it is installed, and otherwise a tiny parser that
understands exactly what .streamlit/config.toml uses: [tables], key = "text" | number | true/false, and # comments.
"""
from __future__ import annotations

import re

try:
    import tomllib as _toml            # Python 3.11+
except ImportError:                    # Python 3.10
    try:
        import tomli as _toml
    except ImportError:
        _toml = None

BACKEND = _toml.__name__ if _toml else "built-in mini parser"


def _value(raw: str):
    raw = raw.strip()
    if raw[:1] in "\"'":
        return raw[1:raw.index(raw[0], 1)]
    raw = re.sub(r"\s+#.*$", "", raw)
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return int(raw)
    except ValueError:
        return float(raw)


def parse_minimal(text: str) -> dict:
    out: dict = {}
    table = out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"\[([A-Za-z0-9_.\-]+)\]", re.sub(r"\s+#.*$", "", line))
        if m:
            table = out
            for part in m.group(1).split("."):
                table = table.setdefault(part, {})
            continue
        key, _, raw = line.partition("=")
        table[key.strip()] = _value(raw)
    return out


def loads(text: str) -> dict:
    return _toml.loads(text) if _toml else parse_minimal(text)
