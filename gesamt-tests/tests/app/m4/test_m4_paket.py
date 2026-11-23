"""M4: Konfiguration, Modul kontor.importer.gnucash, Mock-Szenario beitragsaenderung (python-api.md 10, plugins.md 8)."""

from __future__ import annotations

import datetime as dt
import inspect
import json

import pytest

from tests.hilfen import kontor
from tests.hilfen.m4 import VORLAGEN_MOCK, lade, mock_datei, umsatz
from tests.hilfen.api import neue_api


def Config():  # noqa: N802
    return kontor.KontorConfig()


@pytest.mark.kern
def test_lernmodell_automatisch_vorgabe_und_typ(tmp_path):
    c = Config()(datenbank=tmp_path / "k.sqlite3")
    assert c.lernmodell_automatisch is False
    assert Config()(datenbank=tmp_path / "k.sqlite3", lernmodell_automatisch=True).lernmodell_automatisch is True
    for falsch in (1, "ja", None, 0):
        with pytest.raises(kontor.fehler().KonfigurationsFehler):
            Config()(datenbank=tmp_path / "k.sqlite3", lernmodell_automatisch=falsch)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("wert,soll", [("1", True), ("JA", True), ("on", True), ("0", False), ("", False),
                                       ("nein", False)])
def test_lernmodell_from_env(tmp_path, wert, soll):
    c = Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_LERNMODELL_AUTOMATISCH": wert})
    assert c.lernmodell_automatisch is soll
    assert Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3")}).lernmodell_automatisch is False


def test_lernmodell_from_env_ungueltig(tmp_path):
    with pytest.raises(kontor.fehler().KonfigurationsFehler):
        Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_LERNMODELL_AUTOMATISCH": "oft"})


@pytest.mark.kern
def test_szenario_beitragsaenderung_erlaubt(tmp_path):
    c = Config()(datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_szenario="beitragsaenderung")
    assert c.mock_szenario == "beitragsaenderung"
    c = Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_MOCK_MODUS": "1",
                           "KONTOR_MOCK_SZENARIO": "beitragsaenderung"})
    assert c.mock_szenario == "beitragsaenderung"
    api = neue_api(tmp_path, mock_modus=True, mock_szenario="beitragsaenderung")
    assert api.get("/api/status", erwartet=200).daten["mock_szenario"] == "beitragsaenderung"


def test_modul_gnucash():
    m = kontor.modul("kontor.importer.gnucash")
    e = kontor.modul("kontor.importer.ergebnis")
    assert m.ImportErgebnis is e.ImportErgebnis and m.ImportMeldung is e.ImportMeldung
    sig = inspect.signature(m.importiere_gnucash)
    assert list(sig.parameters)[:2] == ["config", "quelle"]
    assert sig.parameters["dateiname"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["dateiname"].default is None


def _plugin(daten, szenario, heute="2024-12-31"):
    return kontor.modul("kontor.plugins.mock_bank").MockBankPlugin(daten, szenario, dt.date.fromisoformat(heute))


@pytest.mark.kern
def test_mock_beitragsaenderung_liefert_anderen_betrag():
    """plugins.md 8: nur Umsätze mit betrag_beitragsaenderung ändern sich, alle Felder sonst gleich."""
    d = lade(VORLAGEN_MOCK)
    iban = d["bank"]["konten"][0]["iban"]
    von, bis = dt.date(2024, 1, 1), dt.date(2024, 12, 31)
    normal = _plugin(VORLAGEN_MOCK, "normal").umsaetze(iban, von, bis)
    neu = _plugin(VORLAGEN_MOCK, "beitragsaenderung").umsaetze(iban, von, bis)
    roh = {u["umsatz_id"]: u for u in d["bank"]["umsaetze"]}
    assert [u.umsatz_id for u in normal] == [u.umsatz_id for u in neu] == sorted(
        roh, key=lambda i: (roh[i]["buchungstag"], i))
    geaendert = 0
    for a, b in zip(normal, neu):
        r = roh[a.umsatz_id]
        assert a.betrag == r["betrag"]
        assert b.betrag == r.get("betrag_beitragsaenderung", r["betrag"])
        geaendert += a.betrag != b.betrag
        assert (a.buchungstag, a.verwendungszweck, a.gegenpartei_name) == (b.buchungstag, b.verwendungszweck,
                                                                           b.gegenpartei_name)
    assert geaendert == sum("betrag_beitragsaenderung" in u for u in d["bank"]["umsaetze"]) > 0
    for sz in ("bankfehler", "tan_erforderlich"):
        with pytest.raises(kontor.fehler().BankFehler):
            _plugin(VORLAGEN_MOCK, sz).umsaetze(iban, von, bis)


def test_mock_beitragsaenderung_schluessel_ungueltig(tmp_path):
    i = lade(VORLAGEN_MOCK)["bank"]["konten"][0]["iban"]
    p = mock_datei(tmp_path / "d.json", [(i, "Giro", "girokonto")],
                   [umsatz("X-1", i, "2024-01-02", -100, "A", betrag_beitragsaenderung="viel")])
    with pytest.raises(kontor.fehler().KonfigurationsFehler):
        _plugin(p, "beitragsaenderung")
    ok = mock_datei(tmp_path / "e.json", [(i, "Giro", "girokonto")],
                    [umsatz("X-1", i, "2024-01-02", -100, "A", betrag_beitragsaenderung=-101)])
    assert [u.betrag for u in _plugin(ok, "normal").umsaetze(i, dt.date(2024, 1, 1), dt.date(2024, 1, 31))] == [-100]
    json.loads(ok.read_text(encoding="utf-8"))


def test_eingebauter_datensatz_mit_beitragsaenderung():
    p = kontor.modul("kontor.plugins.mock_bank").MockBankPlugin(None, "beitragsaenderung", dt.date(2024, 6, 30))
    konten = p.konten()
    assert konten
    p.umsaetze(konten[0].iban, dt.date(2024, 1, 1), dt.date(2024, 6, 30))


def test_beitragsaenderung_auch_fuer_mail_mock_und_unbekannt_bleibt_unbekannt(tmp_path, netz_gesperrt):
    """plugins.md 8: der Mail-Mock nimmt das Szenario an und verhält sich wie normal; E-095: andere
    unbekannte Namen bleiben ungültig."""
    from tests.hilfen.pfade import MOCK
    daten = MOCK / "mock_daten.json"
    roh = json.loads(daten.read_text(encoding="utf-8"))
    mm = kontor.modul("kontor.plugins.mock_mail").MockMailPlugin
    a = mm(daten, "normal", dt.date(2024, 12, 31))
    b = mm(daten, "beitragsaenderung", dt.date(2024, 12, 31))
    assert sorted(b.postfaecher()) == sorted(a.postfaecher()) == sorted(roh["mail"]["postfaecher"])
    seit = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    for pf in roh["mail"]["postfaecher"]:
        assert [n.nachricht_id for n in b.nachrichten(pf, seit)] == [n.nachricht_id for n in a.nachrichten(pf, seit)]
    for cls in (mm, kontor.modul("kontor.plugins.mock_bank").MockBankPlugin):
        with pytest.raises(kontor.fehler().KonfigurationsFehler):
            cls(daten, "gibtsnicht_m1")
    with pytest.raises(kontor.fehler().KonfigurationsFehler) as info:
        Config()(datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_szenario="gibtsnicht_m1")
    assert info.value.code == "konfiguration_ungueltig"
