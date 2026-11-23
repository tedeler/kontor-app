"""Fiktive Test-IBANs: prüfziffergültig und offensichtlich synthetisch."""

from hypothesis import given, strategies as st

from generator.iban import FIKTIVE_BLZ, ist_gueltig, normalisiere, fiktive_iban, ungueltige_iban


@given(st.integers(min_value=0, max_value=9_999_999_999))
def test_test_iban_gueltig_und_fiktiv(nr):
    iban = fiktive_iban(nr)
    assert ist_gueltig(iban)
    assert iban.startswith("DE") and len(iban) == 22
    assert iban[4:12] == FIKTIVE_BLZ == "00000000"


@given(st.integers(min_value=0, max_value=9_999_999_999))
def test_ungueltige_iban_ungueltig(nr):
    assert not ist_gueltig(ungueltige_iban(nr))


def test_bekannte_beispiel_iban():
    # Beispiel-IBAN aus der Literatur (nur zur Prüfung des Algorithmus, nicht als Testdatum verwendet)
    assert ist_gueltig("DE89 3704 0044 0532 0130 00")
    assert not ist_gueltig("DE88 3704 0044 0532 0130 00")


def test_normalisieren():
    assert normalisiere(" de72 0000 0000 0000 0010 01 ") == "DE72000000000000001001"
