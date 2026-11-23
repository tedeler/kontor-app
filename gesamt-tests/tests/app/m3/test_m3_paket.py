"""M3: Konfiguration für die Umbuchungserkennung (python-api.md 9.1)."""

from __future__ import annotations

import pytest

from tests.hilfen import kontor


def Config():  # noqa: N802
    return kontor.KontorConfig()


@pytest.mark.kern
def test_vorgaben_und_werte(tmp_path):
    c = Config()(datenbank=tmp_path / "k.sqlite3")
    assert (c.umbuchung_automatisch, c.umbuchung_fenster_tage) == (False, 3)
    c = Config()(datenbank=tmp_path / "k.sqlite3", umbuchung_automatisch=True, umbuchung_fenster_tage=0)
    assert (c.umbuchung_automatisch, c.umbuchung_fenster_tage) == (True, 0)
    assert Config()(datenbank=tmp_path / "k.sqlite3", umbuchung_fenster_tage=366).umbuchung_fenster_tage == 366
    assert list(tmp_path.iterdir()) == []


@pytest.mark.kern
@pytest.mark.parametrize("felder", [
    {"umbuchung_automatisch": 1}, {"umbuchung_automatisch": "ja"}, {"umbuchung_automatisch": None},
    {"umbuchung_fenster_tage": -1}, {"umbuchung_fenster_tage": 367}, {"umbuchung_fenster_tage": True},
    {"umbuchung_fenster_tage": "3"}, {"umbuchung_fenster_tage": 2.0},
], ids=lambda f: ",".join(f"{k}={v!r}" for k, v in f.items()))
def test_ungueltig(tmp_path, felder):
    with pytest.raises(kontor.fehler().KonfigurationsFehler):
        Config()(datenbank=tmp_path / "k.sqlite3", **felder)


def test_from_env(tmp_path):
    basis = {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3")}
    c = Config().from_env(basis)
    assert (c.umbuchung_automatisch, c.umbuchung_fenster_tage) == (False, 3)
    c = Config().from_env({**basis, "KONTOR_UMBUCHUNG_AUTOMATISCH": "Ja", "KONTOR_UMBUCHUNG_FENSTER_TAGE": "5"})
    assert (c.umbuchung_automatisch, c.umbuchung_fenster_tage) == (True, 5)
    c = Config().from_env({**basis, "KONTOR_UMBUCHUNG_AUTOMATISCH": "", "KONTOR_UMBUCHUNG_FENSTER_TAGE": ""})
    assert (c.umbuchung_automatisch, c.umbuchung_fenster_tage) == (False, 3)


@pytest.mark.parametrize("var,wert", [("KONTOR_UMBUCHUNG_AUTOMATISCH", "vielleicht"),
                                      ("KONTOR_UMBUCHUNG_FENSTER_TAGE", "drei"),
                                      ("KONTOR_UMBUCHUNG_FENSTER_TAGE", "-1"),
                                      ("KONTOR_UMBUCHUNG_FENSTER_TAGE", "400")])
def test_from_env_ungueltig(tmp_path, var, wert):
    with pytest.raises(kontor.fehler().KonfigurationsFehler):
        Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), var: wert})
