from sources.matching import (is_po_box, looks_like_entity, normalize_address, normalize_name,
                              split_street_address, strip_entity_suffix)


def test_normalize_name_ignores_punctuation_and_llc_spelling():
    assert normalize_name("ADAR INVESTMENTS, LLC") == normalize_name("Adar Investments L.L.C.") == "ADAR INVESTMENTS LLC"
    assert strip_entity_suffix(normalize_name("Ansonia State Street, Limited Liability Company")) == "ANSONIA STATE STREET"


def test_normalize_name_keeps_different_companies_apart():
    assert normalize_name("115 DIAMOND NAVCAPMAN LLC") != normalize_name("115 EDGEWOOD NAVCAPMAN LLC")


def test_normalize_address_and_po_box():
    assert normalize_address("1745 SHEA CENTER DRIVE") == normalize_address("1745 Shea Center Dr.")
    assert is_po_box("PO BOX 2970") and is_po_box("P.O. Box 9344") and not is_po_box("19 HOWE ST")


def test_split_street_address_drops_suffix():
    assert split_street_address("360 State Street, New Haven, CT") == ("360", "STATE")
    assert split_street_address("100 York Street, New Haven, CT") == ("100", "YORK")
    assert split_street_address("not an address") == ("", "")


def test_looks_like_entity():
    assert looks_like_entity("ADAR INVESTMENTS LLC") and not looks_like_entity("ROACH CASONDRA")


def test_hamden_centre_spellings_normalize_the_same():
    base = normalize_name("HAMDEN CENTRE APARTMENTS, LLC")
    for v in ("Hamden Centre Apartments LLC", "HAMDEN CENTRE APARTMENTS, L.L.C.", "Hamden  Centre Apartments, L.L.C", "hamden centre apartments llc."):
        assert normalize_name(v) == base
