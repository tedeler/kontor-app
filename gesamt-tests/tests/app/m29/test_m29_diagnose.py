"""M29: Diagnoseprotokoll des Bankabrufs ohne persönliche Daten (bankzugang.md 4.6, 5; E-265).

Geprüft werden die Verbote (kein Wert der Attrappe, der nach 5 nie enthalten sein darf) und wenige positive Merkmale,
die die Definition wörtlich nennt; Wortlaut und Aufbau der Zeilen sind frei.
"""

from __future__ import annotations

import logging

import pytest

from tests.hilfen.api import Api
from tests.hilfen.fints_attrappe import FintsAttrappe
from tests.hilfen.m6 import BIS, VON, echt_api, fints_daten, fints_felder, giro, pin_setzen, sync, tan_antwort
from tests.hilfen.m29 import (
    ZUGANG, ZUSATZ_VERFAHREN, code, diagnose, diagnose_schalten, konten_abrufen, konten_mit_tan, konten_waehlen,
    neustart, pruefe_ohne_persoenliches, verbotene_werte, verfahren,
)

pytestmark = pytest.mark.kern
ZEITRAUM = {"von": VON.isoformat(), "bis": BIS.isoformat()}


@pytest.fixture(scope="module")
def bank():
    return fints_daten()


def _api(tmp_path, a, daten, **extra) -> Api:
    api = echt_api(tmp_path, **fints_felder(a, daten, **extra))
    pin_setzen(api, daten["pin"])
    return api


def _zeilen(api: Api) -> list[str]:
    d = diagnose(api)
    assert all(isinstance(z, str) for z in d["zeilen"]) and len(d["zeilen"]) <= 600
    return d["zeilen"]


def _enthaelt(zeilen: list[str], text: str) -> bool:
    return any(text in z for z in zeilen)


def test_ausgeliefert_aus_einschalten_leert_ausschalten_laesst_stehen(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        assert diagnose(api) == {"aktiv": False, "zeilen": []}, "ausgeliefert ausgeschaltet"
        konten_abrufen(api)
        verfahren(api)
        assert diagnose(api) == {"aktiv": False, "zeilen": []}, "ausgeschaltet entstehen keine Zeilen"
        assert diagnose_schalten(api, True) == {"aktiv": True, "zeilen": []}
        konten_abrufen(api)
        zeilen = _zeilen(api)
        assert zeilen, "eingeschaltet schreibt das Plugin je Aufruf Zeilen"
        aus = diagnose_schalten(api, False)
        assert aus == {"aktiv": False, "zeilen": zeilen}, "Ausschalten lässt die Zeilen stehen"
        konten_abrufen(api)
        assert diagnose(api) == aus
        assert diagnose_schalten(api, True) == {"aktiv": True, "zeilen": []}, "Einschalten leert das Protokoll"
        for koerper in ({}, {"aktiv": "ja"}, {"aktiv": 1}, {"aktiv": True, "zeilen": []}):
            assert code(api.put(ZUGANG + "/diagnose", json=koerper, erwartet=422)) == "validierung"
        assert diagnose(api)["aktiv"] is True


def test_zeilen_ueberstehen_keinen_neustart(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        diagnose_schalten(api, True)
        konten_abrufen(api)
        assert _zeilen(api)
        neu = neustart(api)
        assert diagnose(neu) == {"aktiv": True, "zeilen": []}
        pin_setzen(neu, daten["pin"])
        konten_abrufen(neu)
        assert _zeilen(neu), "nach dem Neustart wird weiter protokolliert"


def test_inhalt_und_keine_persoenlichen_daten(tmp_path, bank, caplog, capfd, netz_nur_loopback):
    """Kontenabruf mit TAN zur Anmeldung, TAN-Verfahren und ein Lauf mit TAN zum Umsatzabruf."""
    daten, erw = bank
    caplog.set_level(logging.INFO)
    with FintsAttrappe(daten, tan_pflicht="einmal", seitengroesse=30) as a:
        a.tan_anmeldung = "einmal"
        a.verfahren_zusatz = [ZUSATZ_VERFAHREN]
        a.erlaubte_verfahren = [daten["tan_verfahren"]["funktion"], ZUSATZ_VERFAHREN["funktion"]]
        api = _api(tmp_path, a, daten)
        diagnose_schalten(api, True)
        verfahren(api)
        erg = konten_abrufen(api)
        vorgang = erg["tan_erforderlich"]["vorgang"]
        konten_abrufen(api, 422, vorgang=vorgang, tan="918273")
        konten_abrufen(api, vorgang=vorgang, tan=daten["tan"])
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "wartet_auf_tan", lauf
        lauf = tan_antwort(api, lauf["tan_anforderung_id"], daten["tan"]).daten
        assert lauf["status"] == "erfolgreich", lauf
        zeilen = _zeilen(api)
    # ---- positive Merkmale (bankzugang.md 5)
    assert len(zeilen) >= 10
    for segment in ("HKIDN", "HKSPA", "HKCAZ", "HKTAN"):
        assert _enthaelt(zeilen, segment), f"Segmentart {segment} fehlt (je Nachricht die Segmentarten mit Version)"
    assert _enthaelt(zeilen, "camt.052.001.08"), "Angebot der Bank bzw. gewähltes camt-Format"
    assert _enthaelt(zeilen, "Konto 1") and _enthaelt(zeilen, "Konto 2"), "je Konto nur eine laufende Nummer"
    assert _enthaelt(zeilen, daten["tan_verfahren"]["funktion"]) and _enthaelt(zeilen, ZUSATZ_VERFAHREN["funktion"])
    assert _enthaelt(zeilen, daten["tan_verfahren"]["name"]), "TAN-Verfahren mit Nummer und Name"
    assert _enthaelt(zeilen, "3920") and _enthaelt(zeilen, "0030"), "Rückmeldungen der Bank mit Code"
    assert _enthaelt(zeilen, "200"), "HTTP-Status"
    # ---- nie enthalten
    verboten = verbotene_werte(daten, a, extra=("918273", vorgang))
    assert a.referenzen and a.system_ids
    pruefe_ohne_persoenliches(zeilen, verboten)
    # ---- zusätzlich im Log des Dienstes (Stufe INFO); PIN und TAN stehen in keinem Logeintrag
    raus, err = capfd.readouterr()
    info = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("HKCAZ" in m for m in info) or "HKCAZ" in err, "Diagnosezeilen fehlen im Log (Stufe INFO)"
    for geheim in (daten["pin"], daten["tan"], "918273"):
        assert geheim not in caplog.text and geheim not in raus and geheim not in err


def test_fehler_mit_klasse_und_code(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = echt_api(tmp_path, **fints_felder(a, daten))
        diagnose_schalten(api, True)
        pin_setzen(api, "SYNTH-FALSCHE-PIN-DIAG")
        assert code(konten_abrufen(api, 409)) == "bank_pin_falsch"
        zeilen = _zeilen(api)
        assert _enthaelt(zeilen, "bank_pin_falsch"), "bei Fehlern Fehlerklasse und Code"
        assert _enthaelt(zeilen, "9931"), "Rückmeldung der Bank mit Code"
        pruefe_ohne_persoenliches(zeilen, verbotene_werte(daten, a, extra=("SYNTH-FALSCHE-PIN-DIAG",)))
        a.http_status = 503
        pin_setzen(api, daten["pin"])
        assert code(konten_abrufen(api, 409)) == "bank_verbindung"
        zeilen = _zeilen(api)
        assert _enthaelt(zeilen, "bank_verbindung") and _enthaelt(zeilen, "503")
        pruefe_ohne_persoenliches(zeilen, verbotene_werte(daten, a))


@pytest.mark.parametrize("zusatz,verboten", [
    ("Rueckfrage KONTOR-TEST-01 DE95000000000000006601 Vorgang 4711998877",
     ("KONTOR-TEST-01", "DE95000000000000006601", "4711998877")),
    ("Rueckfrage Konto 0000006601 Telefon 0301234567 Nr 12345", ("0000006601", "0301234567", "12345")),
])
def test_freitexte_der_bank_werden_bereinigt(tmp_path, bank, zusatz, verboten, netz_nur_loopback):
    daten, _ = bank
    assert daten["benutzer"] == "KONTOR-TEST-01"
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.rueckmeldung_zusatz = zusatz
        api = _api(tmp_path, a, daten)
        diagnose_schalten(api, True)
        konten_abrufen(api)
        konten_waehlen(api, [giro(bank[1])])
        assert sync(api, **ZEITRAUM)["status"] == "erfolgreich"
        zeilen = _zeilen(api)
    assert _enthaelt(zeilen, "Rueckfrage"), "Rückmeldungen der Bank mit bereinigtem Text"
    texte = [z for z in zeilen if "Rueckfrage" in z]
    for wert in verboten:
        assert not any(wert in z for z in texte), f"{wert!r} nicht ersetzt (Kennungen, IBANs, Ziffernfolgen ab fünf)"
    pruefe_ohne_persoenliches(zeilen, verbotene_werte(daten, a))


@pytest.mark.parametrize("feld,wert,form", [("datum_kaputt", "03.06.2024", "99.99.9999"),
                                            ("betrag_kaputt", "12,5b", "99,9a"),
                                            ("datum_kaputt", "Juni 2024", "aaaa 9999")])
def test_unlesbare_umsatzdaten_nur_als_form(tmp_path, bank, feld, wert, form, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        setattr(a, feld, wert)
        api = _api(tmp_path, a, daten)
        diagnose_schalten(api, True)
        konten_abrufen(api)
        konten_waehlen(api, [giro(erw)])
        lauf = sync(api, **ZEITRAUM)
        konto = next(k for k in lauf["konten"] if k["iban"] == giro(erw))
        assert (konto["status"], konto["fehler"]["code"]) == ("fehlgeschlagen", "bank_fehler"), lauf
        assert api.alle_buchungen() == [], "der ganze Abruf scheitert, nichts wird gebucht"
        zeilen = _zeilen(api)
    assert _enthaelt(zeilen, form), f"Form des Werts ({form}) fehlt: Ziffern als 9, Buchstaben als a"
    assert not _enthaelt(zeilen, wert), "nie der Wert selbst"
    assert _enthaelt(zeilen, "bank_fehler")
    pruefe_ohne_persoenliches(zeilen, verbotene_werte(daten, a))


def test_hoechstens_600_zeilen_aelteste_zuerst(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        diagnose_schalten(api, True)
        konten_abrufen(api)
        assert len(_zeilen(api)) >= 1
        voll = None
        # W-015 (E-289): die Zeilenzahl je Abruf ist nicht festgelegt (der erste Abruf darf mehr schreiben);
        # wiederholen, bis 600 erreicht sind – höchstens 300 Abrufe, jeder fügt vor der Grenze Zeilen hinzu.
        for _ in range(300):
            vorher = _zeilen(api)
            konten_abrufen(api)
            jetzt = _zeilen(api)
            if len(jetzt) == 600:
                voll = jetzt
                break
            assert len(jetzt) > len(vorher), "jeder Abruf schreibt Zeilen ins Diagnoseprotokoll"
            assert jetzt[:len(vorher)] == vorher, "älteste zuerst: neue Zeilen kommen ans Ende"
        assert voll is not None, "das Protokoll erreicht 600 Zeilen nicht"
        konten_abrufen(api)
        nach = _zeilen(api)
        assert len(nach) == 600, "höchstens 600 Zeilen"
        assert any(nach[:600 - x] == voll[x:] for x in range(1, 600)), "die ältesten Zeilen fallen heraus"


def test_kontenabruf_mit_tan_ohne_wortlaut_der_anforderung(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        api = _api(tmp_path, a, daten)
        diagnose_schalten(api, True)
        assert konten_mit_tan(api, daten["tan"])
        zeilen = _zeilen(api)
    assert zeilen and _enthaelt(zeilen, "0030")
    assert not _enthaelt(zeilen, daten["challenge"]) and not _enthaelt(zeilen, daten["challenge"][:25])
    pruefe_ohne_persoenliches(zeilen, verbotene_werte(daten, a, ))
    assert a.referenzen
