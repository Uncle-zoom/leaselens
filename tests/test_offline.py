"""LEASELENS_OFFLINE=1 must run everything from data/samples/ and make ZERO network calls."""
import socket

import pytest
import requests

from data_check import ADDRESSES
from sources import router
from sources.common import OfflineError, http


def test_http_refuses_in_offline_mode(monkeypatch):
    sent = []
    monkeypatch.setattr(requests, "request", lambda *a, **k: sent.append(a))
    with pytest.raises(OfflineError):
        http("GET", "https://example.org/")
    assert sent == []


@pytest.mark.smoke
@pytest.mark.parametrize("group,address,_why", ADDRESSES, ids=[a for _, a, _ in ADDRESSES])
def test_full_pipeline_offline_makes_no_network_calls(group, address, _why, monkeypatch, offline):
    requests_made, dns = [], []
    monkeypatch.setattr(requests, "request", lambda *a, **k: requests_made.append(a) or pytest.fail("requests.request called"))
    monkeypatch.setattr(requests.Session, "request", lambda *a, **k: requests_made.append(a) or pytest.fail("Session.request called"))
    out = router.analyze(address)

    assert out["geo"].ok and out["geo"].origin == "sample"
    assert out["plan"].markets == ["core", "ct"]
    for market, results in out["results"].items():
        assert results, market
        for name, res in results.items():
            assert res.ok and res.origin == "sample", f"{market}/{name}: {res.error}"
    assert requests_made == [] and offline == [] and dns == []


def test_unknown_address_offline_fails_cleanly_without_network(offline):
    out = router.analyze("1 Nowhere Lane, Atlantis, ZZ")
    assert not out["geo"].ok and "offline mode and no saved sample" in out["geo"].error
    assert out["plan"] is None and offline == []
