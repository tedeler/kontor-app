"""M5: Konfiguration, Fehlerklasse, Modul kontor.kredite (python-api.md 12)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import kontor
from tests.hilfen.m5 import kreditfaelle


def Config():  # noqa: N802
    return kontor.KontorConfig()


@pytest.mark.kern
def test_wiederkehrend_automatisch_vorgabe_und_typ(tmp_path):
    c = Config()(datenbank=tmp_path / "k.sqlite3")
    assert c.wiederkehrend_automatisch is False
    assert Config()(datenbank=tmp_path / "k.sqlite3", wiederkehrend_automatisch=True).wiederkehrend_automatisch is True
    for falsch in (1, "ja", None, 0):
        with pytest.raises(kontor.fehler().KonfigurationsFehler):
            Config()(datenbank=tmp_path / "k.sqlite3", wiederkehrend_automatisch=falsch)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("wert,soll", [("1", True), ("Ja", True), ("on", True), ("0", False), ("", False),
                                       ("NEIN", False)])
def test_wiederkehrend_from_env(tmp_path, wert, soll):
    umgebung = {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_WIEDERKEHREND_AUTOMATISCH": wert}
    assert Config().from_env(umgebung).wiederkehrend_automatisch is soll
    assert Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3")}).wiederkehrend_automatisch is False


def test_wiederkehrend_from_env_ungueltig(tmp_path):
    with pytest.raises(kontor.fehler().KonfigurationsFehler):
        Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_WIEDERKEHREND_AUTOMATISCH": "x"})


@pytest.mark.kern
def test_fehlerklasse_kredit_rate_zu_klein():
    f = kontor.fehler()
    assert issubclass(f.KreditRateZuKlein, f.KontorFehler)
    assert f.KreditRateZuKlein.code == "kredit_rate_zu_klein"


@pytest.mark.kern
def test_tilgungsplan_python_fehlerfaelle():
    tp = kontor.modul("kontor.kredite").tilgungsplan
    gut = {"restschuld": 100_000, "stand_datum": "2024-01-01", "sollzins": 30_000, "rate": 10_000,
           "erste_faelligkeit": "2024-02-01"}
    assert tp(gut)["anzahl_raten"] == 11
    zu_klein = next(f for f in kreditfaelle() if f["name"] == "rate_zu_klein")["parameter"]
    with pytest.raises(kontor.fehler().KreditRateZuKlein):
        tp(zu_klein)
    for falsch in ({**gut, "restschuld": 0}, {**gut, "rate": 10_000.0}, {**gut, "sollzins": 1_000_001},
                   {**gut, "erste_faelligkeit": "2024-01-01"}, {**gut, "zinsmethode": "act/366"},
                   {**gut, "sondertilgungen": [{"datum": "2023-12-31", "betrag": 5}]},
                   {**gut, "rate": True}, {k: v for k, v in gut.items() if k != "rate"}):
        with pytest.raises(ValueError):
            tp(falsch)


def test_tilgungsplan_python_mit_date_objekten():
    """python-api.md 12.3: Daten als datetime.date oder Text, Rückgabe immer mit Text."""
    tp = kontor.modul("kontor.kredite").tilgungsplan
    a = tp({"restschuld": 100_000, "stand_datum": dt.date(2024, 1, 1), "sollzins": 30_000, "rate": 10_000,
            "erste_faelligkeit": dt.date(2024, 2, 1),
            "sondertilgungen": [{"datum": dt.date(2024, 5, 3), "betrag": 2000}]})
    b = tp({"restschuld": 100_000, "stand_datum": "2024-01-01", "sollzins": 30_000, "rate": 10_000,
            "erste_faelligkeit": "2024-02-01", "sondertilgungen": [{"datum": "2024-05-03", "betrag": 2000}],
            "zinsmethode": "30/360"})
    assert a == b and a["zeilen"][0]["faelligkeit"] == "2024-02-01"
