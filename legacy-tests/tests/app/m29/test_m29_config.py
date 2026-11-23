"""M29: Konfiguration ohne AqBanking (bankzugang.md 2, python-api.md 21; E-259, E-265)."""

from __future__ import annotations

import dataclasses
import importlib
import inspect

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api, neue_config

pytestmark = pytest.mark.kern
ENTFALLEN = ("aqbanking_verzeichnis", "aqbanking_programme", "aqbanking_timeout_sekunden", "aqbanking_saldo")


def Config():  # noqa: N802
    return kontor.KontorConfig()


def F():  # noqa: N802
    return kontor.fehler()


def test_bank_plugin_nur_mock_und_fints(tmp_path):
    assert neue_config(tmp_path / "a").bank_plugin == "fints"
    assert neue_config(tmp_path / "b", mock_modus=True).bank_plugin == "mock"
    assert neue_config(tmp_path / "c", bank_plugin="fints").bank_plugin == "fints"


def test_aqbanking_ist_konfigurationsfehler_mit_feld(tmp_path):
    with pytest.raises(F().KonfigurationsFehler) as e:
        Config()(datenbank=tmp_path / "k.sqlite3", bank_plugin="aqbanking")
    assert e.value.code == "konfiguration_ungueltig"
    assert e.value.details.get("feld") == "bank_plugin"


@pytest.mark.parametrize("wert", ["aqbanking", "fints", ""])
def test_from_env_aqbanking_gilt_als_fints(tmp_path, wert):
    c = Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_BANK_PLUGIN": wert})
    assert c.bank_plugin == "fints" and c.mock_modus is False


def test_aqbanking_variablen_werden_nicht_gelesen(tmp_path):
    """Auch früher ungültige Werte stören nicht (bankzugang.md 2)."""
    umgebung = {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_BANK_PLUGIN": "aqbanking",
                "KONTOR_AQBANKING_VERZEICHNIS": str(tmp_path / "aq"), "KONTOR_AQBANKING_PROGRAMME": "/nicht/da",
                "KONTOR_AQBANKING_TIMEOUT_SEKUNDEN": "abc", "KONTOR_AQBANKING_SALDO": "vielleicht"}
    c = Config().from_env(umgebung)
    assert c.bank_plugin == "fints"
    for feld in ENTFALLEN:
        assert not hasattr(c, feld), feld
    assert not (tmp_path / "aq").exists()


@pytest.mark.parametrize("feld,wert", [("aqbanking_verzeichnis", "/tmp/aq"), ("aqbanking_programme", "/usr/bin"),
                                       ("aqbanking_timeout_sekunden", 120), ("aqbanking_saldo", False)])
def test_felder_gibt_es_nicht_mehr(tmp_path, feld, wert):
    cls = Config()
    assert feld not in {f.name for f in dataclasses.fields(cls)}
    assert feld not in inspect.signature(cls).parameters
    with pytest.raises((TypeError, F().KonfigurationsFehler)):
        cls(datenbank=tmp_path / "k.sqlite3", **{feld: wert})


def test_fints_felder_bleiben(tmp_path):
    c = neue_config(tmp_path, fints_url="https://banking.example.invalid/fints", fints_blz="00000000",
                    fints_benutzer="SYNTH-NUTZER", fints_kunden_id="SYNTH-KUNDE", fints_produkt_id="SYNTH-PRODUKT",
                    fints_tan_verfahren="913")
    assert (c.fints_url, c.fints_blz, c.fints_benutzer, c.fints_kunden_id, c.fints_produkt_id,
            c.fints_tan_verfahren) == ("https://banking.example.invalid/fints", "00000000", "SYNTH-NUTZER",
                                       "SYNTH-KUNDE", "SYNTH-PRODUKT", "913")


def test_fehlerklasse_und_modul_entfallen():
    f = F()
    assert not hasattr(f, "BankTanNichtUnterstuetzt")
    codes = {getattr(x, "code", None) for x in vars(f).values() if inspect.isclass(x)}
    assert "bank_tan_nicht_unterstuetzt" not in codes
    with pytest.raises(ImportError):
        importlib.import_module("kontor.plugins.aqbanking")


def test_plugin_auswahl_und_status(tmp_path, netz_gesperrt):
    p = kontor.plugins()
    echt = neue_config(tmp_path / "e")
    b = p.erzeuge_bank_plugin(echt)
    assert (b.name, b.ist_mock) == ("fints", False)
    assert type(b) is kontor.modul("kontor.plugins.fints").FintsBankPlugin
    mock = neue_config(tmp_path / "m", mock_modus=True)
    assert p.erzeuge_bank_plugin(mock).name == "mock"
    assert Api(echt).get("/api/status", erwartet=200).daten["plugins"]["bank"] == {"name": "fints", "mock": False}
    assert Api(mock).get("/api/status", erwartet=200).daten["plugins"]["bank"] == {"name": "mock", "mock": True}
    netz_gesperrt.pruefe()
