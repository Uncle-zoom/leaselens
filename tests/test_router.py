import textwrap

import sources
from sources import router
from tests.conftest import addr


def test_markets_are_discovered_core_first():
    assert [m.name for m in router.discover_markets()][:3] == ["core", "ct", "nyc"]   # nyc present but disabled


def test_ct_goes_to_core_and_ct():
    plan = router.route({"state_code": "CT", "county": "South Central Connecticut Planning Region"})
    assert plan.markets == ["core", "ct"]
    assert plan.adapters["ct"] == ("complaints", "parcels", "registry", "portfolio")


def test_nyc_is_coming_soon_and_gets_core_only():
    for county in ("New York County", "Kings County", "Bronx County", "Queens County", "Richmond County"):
        plan = router.route({"state_code": "NY", "county": county})
        assert plan.markets == ["core"], county
        assert plan.coming_soon == ("New York City",)


def test_everywhere_else_gets_core_only():
    assert router.route({"state_code": "MA", "county": "Suffolk County"}).markets == ["core"]
    assert router.route({"state_code": "NY", "county": "Albany County"}).coming_soon == ()
    assert router.route({}).markets == ["core"]


def test_routing_of_real_geocoded_samples(geo_for):
    for prefix in ("360 State", "100 York", "365 Orchard"):
        assert router.route(geo_for(prefix)).markets == ["core", "ct"], prefix


def test_adding_a_city_is_one_folder(tmp_path, monkeypatch):
    """A new sources/<city>/__init__.py that defines MARKET is picked up with no change to the router."""
    folder = tmp_path / "zz_testville"
    folder.mkdir()
    (folder / "__init__.py").write_text(textwrap.dedent('''
        class _M:
            name, label, adapters = "zz_testville", "Testville", ("only_source",)
            matches = staticmethod(lambda geo: geo.get("city") == "Testville")
            run = staticmethod(lambda geo, address=None, save=False: {})
        MARKET = _M()
    '''))
    monkeypatch.setattr(sources, "__path__", list(sources.__path__) + [str(tmp_path)])
    monkeypatch.setattr(router, "_sources_path", sources.__path__)
    assert router.route({"city": "Testville", "state_code": "ZZ"}).markets == ["core", "zz_testville"]
    assert router.route({"city": "Elsewhere", "state_code": "ZZ"}).markets == ["core"]
