"""M9: Sicherung einspielen (sicherung.md 5, 6; protokoll.md 10; E-087 bis E-093).

Ersetzen des gesamten Zustands, neue Version im Protokoll, Identität ohne neue Version, Probelauf,
Bestätigung, Modus, IDs und Rückgängig. Erwartungen werden aus den Beständen vor und nach dem Erstellen
der Sicherung abgeleitet, nie aus der Antwort des Einspielens.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m2 import mock_api
from tests.hilfen.m3 import (aenderungen_seit, letzte_aenderung_id, pruefe_eintraege,
                             pruefe_rueckgaengig_rundreise, rueckgaengig)
from tests.hilfen.m9 import (aenderungsanzahl, bestand, einspielen, gesperrt_betroffen, inhalt, inhalt_sha256,
                             kleiner_bestand, lesezustand, null_unterschied, oeffne, reicher_bestand, sicherung,
                             sync_konten, unterschied)


def _pruefe_ergebnis(e: dict, manifest: dict, vorher: dict, nachher: dict, *, trocken: bool) -> None:
    geaendert = vorher != nachher
    assert (e["trocken"], e["geaendert"]) == (trocken, geaendert)
    assert e["manifest"] == manifest
    assert e["unterschied"] == unterschied(vorher, nachher)
    if trocken or not geaendert:
        assert e["aenderung_id"] is None


def _abstimmen_bis_ende(api, kid: int) -> None:
    """Abstimmung bis zur letzten Buchung des Kontos (buchhaltungspflege.md 5)."""
    stichtag = max(b["datum"] for b in api.alle_buchungen(konto_id=kid))
    r = api.post("/api/abstimmungen", json={"konto_id": kid, "stichtag": stichtag,
                                            "saldo": api.salden(stichtag)[kid]["saldo"]}, erwartet=200).daten
    assert r["abgestimmt"] is True, r


@pytest.mark.kern
def test_rundreise_in_leere_instanz(api, tmp_path):
    """T 20/T 23/E-091: Sicherung in eine leere Instanz einspielen ergibt denselben fachlichen Zustand."""
    reicher_bestand(api)
    soll = lesezustand(api, vorlagen=False)
    daten = sicherung(api)
    manifest, _ = oeffne(daten)

    b = neue_api(tmp_path / "b")
    vorher = bestand(b, vorlagen=False)
    start = letzte_aenderung_id(b)
    e = einspielen(b, daten).daten
    _pruefe_ergebnis(e, manifest, vorher, soll["bestand"], trocken=False)
    assert lesezustand(b, vorlagen=False) == soll, "Zustand nach dem Einspielen weicht von der Quelle ab"
    neu = aenderungen_seit(b, start)
    assert len(neu) == 1, f"genau eine Änderung erwartet, nicht {[a['aktion'] for a in neu]}"
    a = neu[0]
    assert (a["id"], a["quelle"], a["aktion"], a["gruppe"], a["rueckgaengig_von"], a["rueckgaengig_durch"]) == (
        e["aenderung_id"], "sicherung", "sicherung_einspielen", None, [], None)
    pruefe_eintraege(a, vorher, soll["bestand"])
    assert b.get("/api/aenderungen", params={"quelle": "sicherung"}, erwartet=200).daten["gesamt"] == 1
    # neue Sicherung der Zielinstanz hat dieselbe Inhaltsprüfsumme
    assert oeffne(sicherung(b))[0]["inhalt_sha256"] == manifest["inhalt_sha256"]


@pytest.mark.kern
def test_ersetzt_gesamten_zustand_und_protokoll_bleibt(api):
    """5.3: Alles nach der Sicherung Angelegte, Geänderte und Gelöschte wird ersetzt; das Protokoll bleibt."""
    k = kleiner_bestand(api)
    soll = lesezustand(api, vorlagen=False)
    daten = sicherung(api)
    # Änderungen nach der Sicherung: anlegen, ändern, löschen
    neu = api.konto("Nach der Sicherung", "sparkonto")
    api.patch(f"/api/konten/{k['giro']['id']}", json={"name": "Umbenannt"}, erwartet=200)
    api.delete(f"/api/buchungen/{k['buchung']['id']}", erwartet=204)
    api.delete(f"/api/tags/{k['tag']['id']}", erwartet=204)
    vorher = bestand(api, vorlagen=False)
    protokoll_vorher = api.get("/api/aenderungen", params={"pro_seite": 500}, erwartet=200).daten["eintraege"]
    e = einspielen(api, daten).daten
    _pruefe_ergebnis(e, oeffne(daten)[0], vorher, soll["bestand"], trocken=False)
    assert e["unterschied"]["konto"] == {"angelegt": 0, "geaendert": 1, "geloescht": 1}
    assert lesezustand(api, vorlagen=False) == soll
    assert neu["id"] not in {x["id"] for x in api.konten()}
    nachher = api.get("/api/aenderungen", params={"pro_seite": 500}, erwartet=200).daten["eintraege"]
    assert nachher[1:] == protokoll_vorher, "das bisherige Protokoll bleibt unverändert erhalten (10.1)"
    assert nachher[0]["id"] == e["aenderung_id"]
    pruefe_eintraege(nachher[0], vorher, soll["bestand"])


@pytest.mark.kern
def test_identisch_keine_neue_version(api, tmp_path):
    """5.3/E-089/T 3.7: gleicher Inhalt → keine Änderung; zweites Einspielen ändert nichts."""
    reicher_bestand(api)
    daten = sicherung(api)
    manifest, _ = oeffne(daten)
    n = aenderungsanzahl(api)
    e = einspielen(api, daten).daten
    assert (e["geaendert"], e["aenderung_id"], e["trocken"]) == (False, None, False)
    assert e["unterschied"] == null_unterschied() and e["abgestimmte_buchungen_betroffen"] == 0
    assert aenderungsanzahl(api) == n

    b = neue_api(tmp_path / "b")
    assert einspielen(b, daten).daten["geaendert"] is True
    z, m = lesezustand(b, vorlagen=False), aenderungsanzahl(b)
    e2 = einspielen(b, daten).daten
    assert (e2["geaendert"], e2["aenderung_id"]) == (False, None)
    assert lesezustand(b, vorlagen=False) == z and aenderungsanzahl(b) == m
    # auch eine neue Sicherung mit anderem Zeitpunkt, aber gleichem Inhalt
    e3 = einspielen(b, sicherung(api)).daten
    assert e3["geaendert"] is False and e3["manifest"]["inhalt_sha256"] == manifest["inhalt_sha256"]


@pytest.mark.kern
def test_rueckgaengig_und_wiederholen(api):
    """6/E-088: Das Einspielen ist eine Änderung, die sich exakt rückgängig machen und wiederholen lässt."""
    reicher_bestand(api)
    soll = bestand(api, vorlagen=False)
    daten = sicherung(api)
    kleiner_bestand(api, "Z")
    bs = [b for b in api.alle_buchungen() if not b["abgestimmt"] and b["status"] != "abgeglichen"]
    api.delete(f"/api/buchungen/{bs[0]['id']}", erwartet=204)
    api.patch(f"/api/buchungen/{bs[1]['id']}", json={"verwendungszweck": "geändert"}, erwartet=200)
    vorher = bestand(api, vorlagen=False)
    aid = einspielen(api, daten).daten["aenderung_id"]
    a = api.get(f"/api/aenderungen/{aid}", erwartet=200).daten
    assert bestand(api, vorlagen=False) == soll
    pruefe_rueckgaengig_rundreise(api, a, vorher, soll)


@pytest.mark.kern
def test_rueckgaengig_nach_spaeterer_aenderung_konflikt(api):
    """6: Zustandsprüfung wie protokoll.md 6.1 – eine spätere Änderung an einem eingespielten Objekt blockiert."""
    k = kleiner_bestand(api)
    daten = sicherung(api)
    api.patch(f"/api/konten/{k['giro']['id']}", json={"name": "anders"}, erwartet=200)
    aid = einspielen(api, daten).daten["aenderung_id"]
    api.patch(f"/api/konten/{k['giro']['id']}", json={"name": "danach"}, erwartet=200)
    vorher = bestand(api, vorlagen=False)
    assert fehlercode(rueckgaengig(api, aid, 409)) == "rueckgaengig_konflikt"
    assert bestand(api, vorlagen=False) == vorher


@pytest.mark.kern
def test_probelauf(api):
    """5.4/5.5: Probelauf ändert nichts und meldet Unterschied und betroffene abgestimmte Buchungen."""
    info = reicher_bestand(api)
    daten = sicherung(api)
    soll = bestand(api, vorlagen=False)
    # danach: abgestimmte Buchungen verändern geht nur über Rückgängig der Abstimmung → Abstimmung aufheben
    abst = api.get("/api/abstimmungen", erwartet=200).daten
    api.delete(f"/api/abstimmungen/{abst[-1]['id']}", erwartet=204)
    api.konto("Neu", "aufwand")
    vorher = bestand(api, vorlagen=False)
    buchungen = api.alle_buchungen()
    n = aenderungsanzahl(api)
    for bestaetigt in (None, False, True):
        e = einspielen(api, daten, trocken=True, bestaetigt=bestaetigt).daten
        _pruefe_ergebnis(e, oeffne(daten)[0], vorher, soll, trocken=True)
        assert e["abgestimmte_buchungen_betroffen"] == gesperrt_betroffen(vorher, soll, buchungen)
    assert bestand(api, vorlagen=False) == vorher and aenderungsanzahl(api) == n
    # umgekehrt: aktuelle abgestimmte Buchungen, die eine leere Sicherung entfernen würde
    leer = sicherung(neue_api())
    _abstimmen_bis_ende(api, info["giro"])
    buchungen = api.alle_buchungen()
    gesperrt = [b for b in buchungen if b["abgestimmt"] or b["status"] == "abgeglichen"]
    assert gesperrt
    e = einspielen(api, leer, trocken=True).daten
    assert e["abgestimmte_buchungen_betroffen"] == len(gesperrt)
    assert e["geaendert"] is True


@pytest.mark.kern
def test_bestaetigung_erforderlich(api, tmp_path):
    """5.1 Schritt 4/E-092: ohne bestaetigt=true → 409, nichts geändert."""
    kleiner_bestand(api)
    daten = sicherung(neue_api(tmp_path / "leer"))
    vorher, n = lesezustand(api, vorlagen=False), aenderungsanzahl(api)
    for bestaetigt in (None, False):
        r = einspielen(api, daten, bestaetigt=bestaetigt, erwartet=409)
        assert fehlercode(r) == "bestaetigung_erforderlich"
    assert lesezustand(api, vorlagen=False) == vorher and aenderungsanzahl(api) == n
    r = einspielen(api, daten, bestaetigt=True).daten
    assert r["geaendert"] is True


@pytest.mark.kern
def test_abgestimmte_buchungen_werden_ersetzt(api, tmp_path):
    """5.3: Sperrregeln gelten nicht; abgestimmte Buchungen werden ersetzt (nach Bestätigung)."""
    info = reicher_bestand(api)
    _abstimmen_bis_ende(api, info["giro"])
    leer = neue_api(tmp_path / "leer")
    soll = lesezustand(leer, vorlagen=False)
    e = einspielen(api, sicherung(leer)).daten
    assert e["geaendert"] is True and e["abgestimmte_buchungen_betroffen"] > 0
    assert lesezustand(api, vorlagen=False)["bestand"] == soll["bestand"]


@pytest.mark.kern
def test_modus_getrennt(api, tmp_path, netz_gesperrt):
    """5.1 Schritt 3/E-092/K 3: Mock-Sicherung nie in die Echtdatenbank und umgekehrt."""
    m = mock_api(tmp_path / "mock")
    m.post("/api/sync", json={"von": "2024-01-01"}, erwartet=200)
    kleiner_bestand(api)
    echt_daten, mock_daten = sicherung(api), sicherung(m)
    for ziel, daten in ((api, mock_daten), (m, echt_daten)):
        vorher, n = lesezustand(ziel, vorlagen=False), aenderungsanzahl(ziel)
        for trocken in (False, True):
            r = einspielen(ziel, daten, trocken=trocken, erwartet=409)
            assert fehlercode(r) == "sicherung_modus"
        assert lesezustand(ziel, vorlagen=False) == vorher and aenderungsanzahl(ziel) == n


@pytest.mark.kern
def test_ids_werden_nie_wiederverwendet(api, tmp_path):
    """5.3 Punkt 3: Nach dem Einspielen sind neue IDs größer als jede hier oder in der Quelle vergebene."""
    k = kleiner_bestand(api)
    weg = [api.konto(f"weg {i}", "aufwand") for i in range(3)]
    for x in weg:
        api.delete(f"/api/konten/{x['id']}", erwartet=204)
    b2 = api.buchung("2024-03-01", [(k["giro"]["id"], -1), (k["kat"]["id"], 1)])
    api.delete(f"/api/buchungen/{b2['id']}", erwartet=204)
    quelle_max = {"konto": weg[-1]["id"], "buchung": b2["id"]}
    daten = sicherung(api)

    b = neue_api(tmp_path / "b")
    hier = [b.konto(f"hier {i}", "aufwand") for i in range(8)]
    hb = [b.buchung("2024-01-01", [(hier[0]["id"], -1), (hier[1]["id"], 1)]) for _ in range(4)]
    hier_max = {"konto": hier[-1]["id"], "buchung": hb[-1]["id"]}
    einspielen(b, daten)
    k2 = b.konto("danach", "aufwand")
    assert k2["id"] > max(quelle_max["konto"], hier_max["konto"]), (k2["id"], quelle_max, hier_max)
    neu = b.buchung("2024-04-01", [(k["kat"]["id"], -2), (k2["id"], 2)])
    assert neu["id"] > max(quelle_max["buchung"], hier_max["buchung"])
    split_max = max([s["id"] for s in b2["splits"]] + [s["id"] for x in hb for s in x["splits"]])
    assert min(s["id"] for s in neu["splits"]) > split_max, "Split-IDs werden nie wiederverwendet"


@pytest.mark.kern
def test_eingespielte_objekte_behalten_ids(api, tmp_path):
    """5.3 Punkt 1: gleiche IDs, auch für Splits; Bezüge bleiben gültig."""
    reicher_bestand(api)
    quelle = {b["id"]: [s["id"] for s in b["splits"]] for b in api.alle_buchungen()}
    b = neue_api(tmp_path / "b")
    b.konto("belegt die ID 1", "aufwand")
    einspielen(b, sicherung(api))
    ziel = {x["id"]: [s["id"] for s in x["splits"]] for x in b.alle_buchungen()}
    assert ziel == quelle


@pytest.mark.kern
def test_vorlagen_in_der_rundreise(api, tmp_path):
    """2.1: Vorlagen (M4) gehören zum Buchbestand und zur Inhaltsprüfsumme."""
    from tests.hilfen.m4 import vorlage

    k = kleiner_bestand(api)
    k2 = api.konto("Hausrat", "aufwand")
    v = vorlage(api, "Versicherung", "Fiktive Versicherung AG", [(k["kat"]["id"], 1000, "Teil 1"),
                                                                  (k2["id"], 2500)])
    i = inhalt(api)
    assert i["vorlage"] == [api.get(f"/api/vorlagen/{v['id']}", erwartet=200).daten]
    daten = sicherung(api)
    m, _ = oeffne(daten)
    assert m["anzahl"]["vorlage"] == 1 and m["inhalt_sha256"] == inhalt_sha256(i)
    b = neue_api(tmp_path / "b")
    einspielen(b, daten)
    assert lesezustand(b) == lesezustand(api)
    assert b.get("/api/vorlagen", erwartet=200).daten == api.get("/api/vorlagen", erwartet=200).daten


TEXT = st.text(st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"), min_size=1, max_size=40)


@given(namen=st.lists(TEXT.filter(lambda s: s.strip()), min_size=1, max_size=4), zweck=TEXT, notiz=TEXT)
def test_texte_unveraendert(api_fabrik, namen, zweck, notiz):
    """Rundreise mit beliebigen Texten (Umlaute, Emoji, Steuerzeichen, Zeilenumbrüche)."""
    a = api_fabrik()
    giro = a.konto("Giro", "girokonto", notiz=notiz)
    kat = a.konto(namen[0], "aufwand")
    for n in namen:
        if n.strip().casefold() not in {t["name"].casefold() for t in a.get("/api/tags", erwartet=200).daten}:
            a.tag(n)
    a.buchung("2024-01-01", [(giro["id"], -1), (kat["id"], 1)], verwendungszweck=zweck)
    soll = lesezustand(a, vorlagen=False)
    b = api_fabrik()
    einspielen(b, sicherung(a))
    assert lesezustand(b, vorlagen=False) == soll


def test_sync_konten_bleiben_ohne_sync_leer(api, tmp_path):
    """Echtmodus ohne Synchronisation: Zustand je Bankkonto bleibt leer."""
    kleiner_bestand(api)
    b = neue_api(tmp_path / "b")
    einspielen(b, sicherung(api))
    assert sync_konten(b) == []
