"""M2: neue Fehlerklassen, TanAntwort, Signaturen, Konfiguration, kontor.sync (python-api.md 8, plugins.md 7)."""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from tests.hilfen import kontor

UNTER_BANKFEHLER = [("BankPinFehlt", "bank_pin_fehlt"), ("BankPinFalsch", "bank_pin_falsch"),
                    ("TanUngueltig", "tan_ungueltig"), ("TanAbgelaufen", "tan_abgelaufen")]


def Config():  # noqa: N802
    return kontor.KontorConfig()


@pytest.mark.kern
@pytest.mark.parametrize("name,code", UNTER_BANKFEHLER)
def test_neue_fehlerklassen(name, code):
    f = kontor.fehler()
    cls = getattr(f, name)
    assert issubclass(cls, f.BankFehler) and issubclass(cls, f.PluginFehler) and cls.code == code
    e = cls("Deutsche Meldung")
    assert str(e) == "Deutsche Meldung" == e.meldung and isinstance(e.details, dict)


def test_tan_antwort_datenklasse():
    bank = kontor.modul("kontor.plugins.bank")
    cls = bank.TanAntwort
    assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen
    assert [f.name for f in dataclasses.fields(cls)] == ["anforderung_id", "tan"]
    a = cls("MOCK-TAN-2024-06-30", "GEHEIM-TAN-777")
    assert a == cls("MOCK-TAN-2024-06-30", "GEHEIM-TAN-777")
    assert "GEHEIM-TAN-777" not in repr(a) and "MOCK-TAN-2024-06-30" in repr(a)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.tan = "x"


def _kw_only(funktion, name):
    p = inspect.signature(funktion).parameters[name]
    return p.kind == inspect.Parameter.KEYWORD_ONLY and p.default is None


def test_signaturen():
    bank = kontor.modul("kontor.plugins.bank")
    assert _kw_only(bank.BankPlugin.umsaetze, "tan")
    assert list(inspect.signature(bank.BankPlugin.umsaetze).parameters)[:4] == ["self", "iban", "von", "bis"]
    assert _kw_only(kontor.plugins().erzeuge_bank_plugin, "pin_quelle")
    mock = kontor.modul("kontor.plugins.mock_bank").MockBankPlugin
    assert _kw_only(mock.__init__, "pin_quelle")
    assert _kw_only(mock.umsaetze, "tan")
    assert bank.BankPlugin.__abstractmethods__ == frozenset({"konten", "umsaetze"})


def test_sync_modul():
    sync = kontor.modul("kontor.sync")
    assert callable(sync.planer_takt)
    assert list(inspect.signature(sync.planer_takt).parameters) == ["app"]


@pytest.mark.kern
def test_konfiguration_vorgaben(tmp_path):
    c = Config()(datenbank=tmp_path / "k.sqlite3")
    assert (c.sync_intervall_minuten, c.sync_wiederholung_minuten, c.sync_erstabruf_tage,
            c.sync_ueberlappung_tage, c.planer_starten) == (0, 30, 90, 14, True)
    c = Config()(datenbank=tmp_path / "k.sqlite3", sync_intervall_minuten=360, sync_wiederholung_minuten=1,
                 sync_erstabruf_tage=0, sync_ueberlappung_tage=0, planer_starten=False)
    assert (c.sync_intervall_minuten, c.sync_wiederholung_minuten, c.sync_erstabruf_tage,
            c.sync_ueberlappung_tage, c.planer_starten) == (360, 1, 0, 0, False)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.kern
@pytest.mark.parametrize("felder", [
    {"sync_intervall_minuten": -1}, {"sync_intervall_minuten": "60"}, {"sync_intervall_minuten": True},
    {"sync_intervall_minuten": 1.5}, {"sync_wiederholung_minuten": 0}, {"sync_wiederholung_minuten": -5},
    {"sync_erstabruf_tage": -1}, {"sync_ueberlappung_tage": -1}, {"sync_ueberlappung_tage": None},
    {"planer_starten": "ja"}, {"planer_starten": 1},
], ids=lambda f: ",".join(f"{k}={v!r}" for k, v in f.items()))
def test_konfiguration_ungueltig(tmp_path, felder):
    with pytest.raises(kontor.fehler().KonfigurationsFehler):
        Config()(datenbank=tmp_path / "k.sqlite3", **felder)


def test_from_env_m2(tmp_path):
    env = {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_SYNC_INTERVALL_MINUTEN": "360",
           "KONTOR_SYNC_WIEDERHOLUNG_MINUTEN": "15", "KONTOR_SYNC_ERSTABRUF_TAGE": "30",
           "KONTOR_SYNC_UEBERLAPPUNG_TAGE": "0", "KONTOR_PLANER_STARTEN": "nein"}
    c = Config().from_env(env)
    assert (c.sync_intervall_minuten, c.sync_wiederholung_minuten, c.sync_erstabruf_tage,
            c.sync_ueberlappung_tage, c.planer_starten) == (360, 15, 30, 0, False)
    c = Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_SYNC_INTERVALL_MINUTEN": "",
                           "KONTOR_PLANER_STARTEN": ""})
    assert (c.sync_intervall_minuten, c.planer_starten) == (0, True)
    assert Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"),
                              "KONTOR_PLANER_STARTEN": "ON"}).planer_starten is True


@pytest.mark.parametrize("var,wert", [
    ("KONTOR_SYNC_INTERVALL_MINUTEN", "sechzig"), ("KONTOR_SYNC_INTERVALL_MINUTEN", "-1"),
    ("KONTOR_SYNC_WIEDERHOLUNG_MINUTEN", "0"), ("KONTOR_SYNC_ERSTABRUF_TAGE", "1.5"),
    ("KONTOR_SYNC_UEBERLAPPUNG_TAGE", "x"), ("KONTOR_PLANER_STARTEN", "vielleicht"),
])
def test_from_env_m2_ungueltig(tmp_path, var, wert):
    with pytest.raises(kontor.fehler().KonfigurationsFehler):
        Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), var: wert})
