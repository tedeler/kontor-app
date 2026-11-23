"""M29: Übergang alter Bank-Kennungen (bankzugang.md 3, synchronisation.md 21.2; E-264).

Der Zustand „vor der Umstellung“ entsteht über die Naht ``kontor.sync.kennungen_als_alt_markieren`` zwischen zwei
App-Instanzen auf derselben Datenbank. Die Fälle laufen mit dem Mock-Plugin (zwei Mock-Datendateien mit denselben
Umsätzen und anderen ``umsatz_id``) und einmal mit dem FinTS-Plugin (Attrappe erst ``mt940``, dann ``camt``).
"""

from __future__ import annotations

from collections import Counter

import pytest

from tests.hilfen import m6_orakel as orakel
from tests.hilfen import m9
from tests.hilfen.api import Api
from tests.hilfen.fints_attrappe import FintsAttrappe
from tests.hilfen.m2 import mock_config, sync
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id, rueckgaengig
from tests.hilfen.m6 import BIS, VON, echt_api, fints_daten, fints_felder, pin_setzen
from tests.hilfen.m29 import MOCK_IBAN, als_alt_markieren, bankbuchungen, kennung, mock_datei, mock_umsatz

pytestmark = pytest.mark.kern
ZWEITE_IBAN = "DE98000000000000008002"
ZEITRAUM = {"von": "2024-01-01", "bis": "2024-06-30"}
U = mock_umsatz


def _api(tmp_path, datei) -> Api:
    """App im Mock-Modus auf der Datenbank unter ``tmp_path/db`` mit der angegebenen Mock-Datendatei."""
    return Api(mock_config(tmp_path / "db", daten=datei, heute="2024-06-30"))


def _lauf(api: Api, iban: str = MOCK_IBAN) -> dict:
    lauf = sync(api, **ZEITRAUM)
    assert lauf["status"] == "erfolgreich", lauf
    return next(k for k in lauf["konten"] if k["iban"] == iban)


def _zaehlung(k: dict) -> tuple[int, int, int, int]:
    assert k["umsaetze_gesamt"] == (k["vormerkungen_ignoriert"] + k["buchungen_vorhanden"]
                                    + k["buchungen_zusammengefuehrt"] + k["buchungen_neu"]), k
    return k["umsaetze_gesamt"], k["buchungen_vorhanden"], k["buchungen_zusammengefuehrt"], k["buchungen_neu"]


def _vorher(tmp_path, alt: list[dict], *, markieren: bool = True, ibans=(MOCK_IBAN,)) -> None:
    """Erster Lauf mit den alten Kennungen, danach gelten sie als „alt“."""
    api = _api(tmp_path, mock_datei(tmp_path / "alt.json", alt, ibans))
    k = _lauf(api)
    erwartet = len([u for u in alt if u["iban"] == MOCK_IBAN])
    assert _zaehlung(k) == (erwartet, 0, 0, erwartet)
    if markieren:
        als_alt_markieren(api.config)


def _nachher(tmp_path, neu: list[dict], name: str = "neu.json", ibans=(MOCK_IBAN,)) -> Api:
    return _api(tmp_path, mock_datei(tmp_path / name, neu, ibans))


def _kennungen(api: Api, iban: str = MOCK_IBAN) -> list[list[str]]:
    return sorted(b["kennungen"] for b in bankbuchungen(api, iban))


ALT = [U("A1", "2024-03-01", -1000, "Laden Alpha", "Einkauf"), U("A2", "2024-03-02", -2000, "Laden Beta", "Einkauf"),
       U("A3", "2024-03-05", 5000, "Arbeitgeber Beispiel GmbH", "Lohn")]
NEU = [U("N1", "2024-03-01", -1000, "Laden Alpha", "Einkauf"), U("N2", "2024-03-02", -2000, "Laden Beta", "Einkauf"),
       U("N3", "2024-03-05", 5000, "Arbeitgeber Beispiel GmbH", "Lohn"),
       U("N4", "2024-03-10", -700, "Laden Gamma", "Einkauf")]


def test_umsatz_mit_neuer_kennung_wird_zugeordnet_statt_neu_gebucht(tmp_path, netz_gesperrt):
    _vorher(tmp_path, ALT)
    api = _nachher(tmp_path, NEU)
    vorher = bankbuchungen(api)
    assert _kennungen(api) == [[kennung("A1")], [kennung("A2")], [kennung("A3")]]
    k = _lauf(api)
    assert _zaehlung(k) == (4, 0, 3, 1), "Zuordnungen zählen als zusammengeführt, nicht als neu"
    nachher = bankbuchungen(api)
    assert len(nachher) == 4
    assert _kennungen(api) == sorted([[kennung("A1"), kennung("N1")], [kennung("A2"), kennung("N2")],
                                      [kennung("A3"), kennung("N3")], [kennung("N4")]]), \
        "die Buchung trägt danach alte und neue Kennung"
    je_id = {b["id"]: b for b in nachher}
    for b in vorher:
        assert {x: b[x] for x in ("datum", "betrag", "empfaenger")} == {
            x: je_id[b["id"]][x] for x in ("datum", "betrag", "empfaenger")}, "die Buchung bleibt sonst unverändert"
    assert api.get("/api/dubletten", erwartet=200).daten == [], "kein Dublettenverdacht"
    # der nächste Abruf erkennt die Buchungen an der Kennung
    assert _zaehlung(_lauf(api)) == (4, 4, 0, 0)
    assert len(bankbuchungen(api)) == 4
    netz_gesperrt.pruefe()


def test_ohne_alte_kennungen_wird_neu_gebucht(tmp_path, netz_gesperrt):
    """In einer neuen Datenbank gibt es keine alten Kennungen: Kennungen dieser Fassung sind nie „alt“."""
    _vorher(tmp_path, ALT, markieren=False)
    api = _nachher(tmp_path, NEU)
    assert _zaehlung(_lauf(api)) == (4, 0, 0, 4)
    assert len(bankbuchungen(api)) == 7
    netz_gesperrt.pruefe()


def test_nach_dem_markieren_vergebene_kennungen_sind_nicht_alt(tmp_path, netz_gesperrt):
    """Eine Buchung, die schon alte und neue Kennung trägt, wird kein zweites Mal zugeordnet."""
    _vorher(tmp_path, ALT)
    api = _nachher(tmp_path, NEU)
    assert _zaehlung(_lauf(api)) == (4, 0, 3, 1)
    dritte = [U("M1", "2024-03-01", -1000, "Laden Alpha", "Einkauf"), U("M4", "2024-03-10", -700, "Laden Gamma")]
    api3 = _nachher(tmp_path, dritte, "dritte.json")
    assert _zaehlung(_lauf(api3)) == (2, 0, 0, 2), "nur Buchungen mit ausschließlich alten Kennungen zählen"
    assert len(bankbuchungen(api3)) == 6
    netz_gesperrt.pruefe()


def test_je_betrag_und_tag_so_viele_wie_buchungen(tmp_path, netz_gesperrt):
    alt = [U("A1", "2024-04-01", -999, "Kiosk am Eck"), U("A2", "2024-04-01", -999, "Kiosk am Eck")]
    neu = [U("N1", "2024-04-01", -999, "Kiosk am Eck"), U("N2", "2024-04-01", -999, "Kiosk am Eck"),
           U("N3", "2024-04-01", -999, "Kiosk am Eck")]
    _vorher(tmp_path, alt)
    api = _nachher(tmp_path, neu)
    assert _zaehlung(_lauf(api)) == (3, 0, 2, 1)
    ist = _kennungen(api)
    assert len(ist) == 3 and sorted(len(x) for x in ist) == [1, 2, 2]
    assert sorted(x for b in ist for x in b) == sorted(kennung(u) for u in ("A1", "A2", "N1", "N2", "N3"))
    alte = [b for b in ist if any(x in (kennung("A1"), kennung("A2")) for x in b)]
    assert all(len(b) == 2 for b in alte), "jede alte Buchung bekommt genau eine neue Kennung"
    netz_gesperrt.pruefe()


@pytest.mark.parametrize("neu_name,ziel", [("Tankstelle Süd", "A2"), ("Bäckerei Korn", "A1")])
def test_vorrang_hat_der_passende_empfaengername(tmp_path, neu_name, ziel, netz_gesperrt):
    alt = [U("A1", "2024-04-02", -500, "Bäckerei Korn"), U("A2", "2024-04-02", -500, "Tankstelle Süd")]
    _vorher(tmp_path, alt)
    api = _nachher(tmp_path, [U("N1", "2024-04-02", -500, neu_name)])
    assert _zaehlung(_lauf(api)) == (1, 0, 1, 0)
    andere = "A1" if ziel == "A2" else "A2"
    assert _kennungen(api) == sorted([[kennung(ziel), kennung("N1")], [kennung(andere)]])
    b = next(x for x in bankbuchungen(api) if kennung("N1") in x["kennungen"])
    assert b["empfaenger"] == neu_name
    netz_gesperrt.pruefe()


def test_beide_namen_werden_passend_verteilt(tmp_path, netz_gesperrt):
    alt = [U("A1", "2024-04-02", -500, "Bäckerei Korn"), U("A2", "2024-04-02", -500, "Tankstelle Süd")]
    _vorher(tmp_path, alt)
    api = _nachher(tmp_path, [U("N1", "2024-04-02", -500, "Tankstelle Süd"), U("N2", "2024-04-02", -500,
                                                                               "Bäckerei Korn")])
    assert _zaehlung(_lauf(api)) == (2, 0, 2, 0)
    assert _kennungen(api) == sorted([[kennung("A1"), kennung("N2")], [kennung("A2"), kennung("N1")]])
    netz_gesperrt.pruefe()


def test_ohne_passenden_namen_wird_trotzdem_zugeordnet(tmp_path, netz_gesperrt):
    """Der Empfängername entscheidet nur die Wahl zwischen mehreren; Bedingung sind Konto, Betrag und Buchungstag."""
    _vorher(tmp_path, [U("A1", "2024-04-06", -1234, "Versandhaus Alt GmbH", "Bestellung 1")])
    api = _nachher(tmp_path, [U("N1", "2024-04-06", -1234, "VERSANDHAUS NEU", "ganz anderer Text")])
    assert _zaehlung(_lauf(api)) == (1, 0, 1, 0)
    assert _kennungen(api) == [[kennung("A1"), kennung("N1")]]
    assert bankbuchungen(api)[0]["empfaenger"] == "Versandhaus Alt GmbH", "die Buchung selbst bleibt unverändert"
    netz_gesperrt.pruefe()


def test_alte_kennung_im_selben_abruf_geliefert(tmp_path, netz_gesperrt):
    """Wird die alte Kennung einer Buchung im selben Abruf wieder geliefert, steht die Buchung nicht zur Wahl."""
    alt = [U("A1", "2024-04-03", -800, "Markt Eins"), U("A2", "2024-04-03", -800, "Markt Eins")]
    _vorher(tmp_path, alt)
    api = _nachher(tmp_path, [U("A1", "2024-04-03", -800, "Markt Eins"), U("N9", "2024-04-03", -800, "Markt Eins")])
    assert _zaehlung(_lauf(api)) == (2, 1, 1, 0)
    assert _kennungen(api) == sorted([[kennung("A1")], [kennung("A2"), kennung("N9")]])
    netz_gesperrt.pruefe()


def test_einzige_buchung_wieder_geliefert_dann_neu(tmp_path, netz_gesperrt):
    _vorher(tmp_path, [U("A1", "2024-04-03", -800, "Markt Eins")])
    api = _nachher(tmp_path, [U("A1", "2024-04-03", -800, "Markt Eins"), U("N9", "2024-04-03", -800, "Markt Eins")])
    assert _zaehlung(_lauf(api)) == (2, 1, 0, 1), "die übrigen Umsätze werden wie gewohnt gebucht"
    assert _kennungen(api) == sorted([[kennung("A1")], [kennung("N9")]])
    netz_gesperrt.pruefe()


def test_anderer_tag_betrag_oder_konto_wird_nicht_zugeordnet(tmp_path, netz_gesperrt):
    ibans = (MOCK_IBAN, ZWEITE_IBAN)
    _vorher(tmp_path, [U("A1", "2024-04-04", -300, "Laden Delta")], ibans=ibans)
    neu = [U("N1", "2024-04-05", -300, "Laden Delta"), U("N2", "2024-04-04", -301, "Laden Delta"),
           U("N3", "2024-04-04", 300, "Laden Delta"), U("N4", "2024-04-04", -300, "Laden Delta", iban=ZWEITE_IBAN)]
    api = _nachher(tmp_path, neu, ibans=ibans)
    lauf = sync(api, **ZEITRAUM)
    assert lauf["status"] == "erfolgreich", lauf
    je = {k["iban"]: k for k in lauf["konten"]}
    assert _zaehlung(je[MOCK_IBAN]) == (3, 0, 0, 3)
    assert _zaehlung(je[ZWEITE_IBAN]) == (1, 0, 0, 1)
    assert [kennung("A1")] in _kennungen(api), "die alte Buchung bleibt unberührt"
    assert _kennungen(api, ZWEITE_IBAN) == [[kennung("N4", ZWEITE_IBAN)]]
    netz_gesperrt.pruefe()


def test_zuordnung_gehoert_zur_aenderung_des_laufs_und_ist_rueckgaengig(tmp_path, netz_gesperrt):
    _vorher(tmp_path, ALT)
    api = _nachher(tmp_path, NEU)
    vorher = bankbuchungen(api)
    a0 = letzte_aenderung_id(api)
    assert _zaehlung(_lauf(api)) == (4, 0, 3, 1)
    nachher = bankbuchungen(api)
    neu = aenderungen_seit(api, a0)
    konto = [a for a in neu if a["aktion"] == "sync_konto"]
    assert len(konto) == 1 and konto[0]["quelle"] == "sync", [(a["quelle"], a["aktion"]) for a in neu]
    je_id = {b["id"]: b for b in vorher}
    geaendert = {e["objekt_id"]: e for e in konto[0]["eintraege"] if e["objekt"] == "buchung"
                 and e["art"] == "geaendert"}
    assert set(geaendert) == set(je_id), "die zugeordneten Buchungen stehen als geändert in der Änderung des Laufs"
    for bid, e in geaendert.items():
        alt_k = [x for x in e["vorher"]["extern_ids"] if x.startswith("bank:")]
        neu_k = [x for x in e["nachher"]["extern_ids"] if x.startswith("bank:")]
        assert alt_k == je_id[bid]["kennungen"] and len(neu_k) == 2 and set(alt_k) < set(neu_k)
    # Rückgängig: die Zuordnung verschwindet mit der Änderung des Laufs
    for a in reversed(neu):
        rueckgaengig(api, a["id"])
    assert bankbuchungen(api) == vorher
    # ein erneuter Abruf ordnet dann wieder zu
    assert _zaehlung(_lauf(api)) == (4, 0, 3, 1)
    wieder = bankbuchungen(api)
    assert [b["kennungen"] for b in wieder if len(b["kennungen"]) == 2] == [
        b["kennungen"] for b in nachher if len(b["kennungen"]) == 2]
    assert len(wieder) == 4
    netz_gesperrt.pruefe()


def test_markierung_ist_betriebszustand(tmp_path, netz_gesperrt):
    """Nicht im Änderungsprotokoll, nicht in der Datensicherung (bankzugang.md 3)."""
    erste = _api(tmp_path, mock_datei(tmp_path / "alt.json", ALT))
    _lauf(erste)
    a0 = letzte_aenderung_id(erste)
    bestand = bankbuchungen(erste)
    m0, _ = m9.oeffne(m9.sicherung(erste))
    als_alt_markieren(erste.config)
    als_alt_markieren(erste.config)          # mehrfach aufrufbar
    zweite = _api(tmp_path, mock_datei(tmp_path / "alt.json", ALT))
    assert letzte_aenderung_id(zweite) == a0, "kein Eintrag im Änderungsprotokoll"
    assert bankbuchungen(zweite) == bestand, "der Buchbestand bleibt unverändert"
    roh = m9.sicherung(zweite)
    m1, _ = m9.oeffne(roh)
    assert (m1["anzahl"], m1["inhalt_sha256"]) == (m0["anzahl"], m0["inhalt_sha256"])
    # in eine neue Datenbank eingespielt: dort gibt es keine alten Kennungen
    fremd = Api(mock_config(tmp_path / "fremd", daten=mock_datei(tmp_path / "neu.json", NEU), heute="2024-06-30"))
    m9.einspielen(fremd, roh)
    assert len(bankbuchungen(fremd)) == 3
    assert _zaehlung(_lauf(fremd)) == (4, 0, 0, 4), "die Markierung gehört nicht zur Sicherung"
    # in der ursprünglichen Datenbank wird dagegen zugeordnet
    assert _zaehlung(_lauf(_nachher(tmp_path, NEU))) == (4, 0, 3, 1)
    netz_gesperrt.pruefe()


# ------------------------------------------------------------------ FinTS: Hash-Kennung (MT940) wird Bankreferenz (camt)
def _schluessel(umsaetze: list[dict]) -> Counter:
    return Counter((u["buchungstag"], u["betrag"]) for u in umsaetze if not u["vormerkung"])


def test_fints_umstellung_von_mt940_auf_camt_ohne_doppelte_buchungen(tmp_path, netz_nur_loopback):
    daten, erw = fints_daten()
    zeitraum = {"von": VON.isoformat(), "bis": BIS.isoformat()}
    with FintsAttrappe(daten, profil="mt940", tan_pflicht="nie") as a:
        felder = fints_felder(a, daten)
        erste = echt_api(tmp_path / "db", **felder)
        pin_setzen(erste, daten["pin"])
        lauf = sync(erste, **zeitraum)
        assert lauf["status"] == "erfolgreich", lauf
        anzahl = len(erste.alle_buchungen())
        als_alt_markieren(erste.config)
        a.profil = "camt"                                # die Bank bietet jetzt camt an: andere Kennungen
        zweite = echt_api(tmp_path / "db", **felder)
        pin_setzen(zweite, daten["pin"])
        lauf = sync(zweite, **zeitraum)
        assert lauf["status"] == "erfolgreich", lauf
        neu_gesamt = 0
        for k in lauf["konten"]:
            alt = _schluessel(orakel.erwartete_umsaetze(erw, "mt940", k["iban"], VON, BIS))
            camt = _schluessel(orakel.erwartete_umsaetze(erw, "camt", k["iban"], VON, BIS))
            soll_neu = sum((camt - alt).values())        # nur was es vorher an diesem Tag mit diesem Betrag nicht gab
            assert k["buchungen_neu"] == soll_neu, (k["iban"], k)
            assert k["buchungen_vorhanden"] + k["buchungen_zusammengefuehrt"] == sum(camt.values()) - soll_neu
            neu_gesamt += soll_neu
        assert len(zweite.alle_buchungen()) == anzahl + neu_gesamt, "keine doppelten Buchungen nach der Umstellung"
        dritter = sync(zweite, **zeitraum)
        assert all(k["buchungen_neu"] == 0 and k["buchungen_zusammengefuehrt"] == 0 for k in dritter["konten"])
    assert not a.interne_fehler
