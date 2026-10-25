"""The TOML reader used by the design tests must work without tomllib (Python 3.10)."""
from pathlib import Path

import pytest

from tests import _toml_compat as tc

CONFIG = (Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml").read_text()


def test_the_mini_parser_reads_the_real_config():
    cfg = tc.parse_minimal(CONFIG)
    assert cfg["theme"]["light"]["backgroundColor"] == "#F5F5F7" and cfg["theme"]["dark"]["secondaryBackgroundColor"] == "#1C1C1E"
    assert cfg["theme"]["baseFontSize"] == 16 and cfg["server"]["headless"] is True and cfg["browser"]["gatherUsageStats"] is False


def test_the_mini_parser_agrees_with_the_real_toml_library_when_one_exists():
    if tc._toml is None:
        pytest.skip("no TOML library on this Python: the mini parser is the only reader (that is the 3.10 case)")
    assert tc.parse_minimal(CONFIG) == tc._toml.loads(CONFIG)


def test_the_mini_parser_handles_comments_quotes_and_numbers():
    text = '# top\n[a.b]\nx = "hi # not a comment"  # trailing\ny = 3\nz = 1.5\nflag = false\n\n[c]\nk = \'single\'\n'
    assert tc.parse_minimal(text) == {"a": {"b": {"x": "hi # not a comment", "y": 3, "z": 1.5, "flag": False}}, "c": {"k": "single"}}


def test_loads_falls_back_to_the_mini_parser_when_no_library_is_installed(monkeypatch):
    monkeypatch.setattr(tc, "_toml", None)
    assert tc.loads(CONFIG)["theme"]["light"]["textColor"] == "#1D1D1F"


def test_requirements_add_tomli_only_for_python_before_3_11():
    req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
    assert 'tomli>=2.0; python_version < "3.11"' in req


def test_no_python_3_11_only_syntax_or_modules_in_the_project():
    import ast
    root = Path(__file__).resolve().parent.parent
    bad = []
    for f in list(root.glob("*.py")) + list(root.glob("sources/**/*.py")) + list(root.glob("tests/*.py")) + list(root.glob("scripts/*.py")):
        src = f.read_text()
        try:
            ast.parse(src, feature_version=(3, 10))
        except SyntaxError as exc:
            bad.append((f.name, str(exc)))
        if f.name != "test_toml_compat.py" and "import tomllib" in src and f.name != "_toml_compat.py":
            bad.append((f.name, "imports tomllib directly"))
    assert not bad, bad


def test_import_falls_back_cleanly_when_neither_tomllib_nor_tomli_can_be_imported(monkeypatch):
    """Simulates Python 3.10 without tomli: the module still imports and still reads the config."""
    import importlib
    import sys
    monkeypatch.setitem(sys.modules, "tomllib", None)       # None in sys.modules makes `import tomllib` raise ImportError
    monkeypatch.setitem(sys.modules, "tomli", None)
    mod = importlib.reload(tc)
    try:
        assert mod.BACKEND == "built-in mini parser" and mod._toml is None
        assert mod.loads(CONFIG)["theme"]["dark"]["backgroundColor"] == "#000000"
    finally:
        monkeypatch.undo()
        importlib.reload(tc)
