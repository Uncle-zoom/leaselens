"""Every test runs offline: LEASELENS_OFFLINE=1 and the network is blocked, so a stray call fails loudly."""
import socket

import pytest

from data_check import ADDRESSES


@pytest.fixture(autouse=True)
def fresh_job_store():
    """The page keeps its background jobs in st.cache_resource, which lives as long as the process: start every test with none."""
    import streamlit as st
    st.cache_resource.clear()
    yield


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("LEASELENS_OFFLINE", "1")
    calls = []

    def blocked(*args, **kwargs):
        calls.append(args)
        raise AssertionError(f"network call attempted in an offline test: {args[:2]}")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    return calls


def addr(prefix: str) -> str:
    return next(a for _, a, _ in ADDRESSES if a.startswith(prefix))


@pytest.fixture
def geo_for():
    """Geocode an address from the saved samples (no network)."""
    from sources.core import geocode

    def _geo(prefix: str) -> dict:
        res = geocode.geocode(addr(prefix))
        assert res.ok and res.origin == "sample", res.error
        return res.data
    return _geo


APP_PATH = str(__import__("pathlib").Path(__file__).parent.parent / "app.py")
DEMO3 = ["360 State Street, New Haven, CT", "100 York Street, New Haven, CT", "365 Orchard Street, New Haven, CT"]


def make_app(view="landing", addresses=None, detail=0, demo=True, timeout=120):
    """The Streamlit page, opened on a given view with given state (offline samples in demo mode)."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP_PATH, default_timeout=timeout)
    at.session_state["demo"] = demo
    at.session_state["view"] = view
    at.session_state["detail"] = detail
    at.session_state["addresses"] = list(DEMO3 if addresses is None else addresses)
    return at


def page_html(at) -> str:
    """All markdown on the page, as one string."""
    return " ".join(m.value for m in at.markdown)


@pytest.fixture(autouse=True)
def keep_real_usage_log_clean(monkeypatch, tmp_path):
    """Stand-in model runs in tests must never add rows to output/usage_log.json (it holds only real model calls)."""
    import usage_log
    real_append = usage_log.append
    monkeypatch.setattr(usage_log, "append", lambda entry, log=None: real_append(entry, log or tmp_path / "usage_log.json"))
