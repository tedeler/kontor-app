"""M9: Vollständigkeit der Sicherung für alle fachlichen Zustände bis M4 und den M3-Nachtrag (sicherung.md 2.1,
2.4; E-096).

Rundreisen für Zustände, die die übrigen M9-Tests nicht abdecken: Split-Vorlagen mit Bezügen und ID-Zähler,
Vorschläge aller Quellen (Regel, Standardkategorie, Lernmodell mit Sicherheit), Aliase, Lernmodell als Funktion
des eingespielten Bestands, Kennungen gelöschter Buchungen, gespeicherte Entscheidungen je Bankkonto (auch
vermerkte Wiederherstellungen und von einem Konto mit der IBAN verdeckte), Import nach dem Einspielen.

Erwartungen kommen aus dem Zustand der Quelle beim Erstellen der Sicherung, aus der Mock-Datendatei
(``tests/hilfen/sync_orakel``) und aus denselben Folgeoperationen auf Quelle und Ziel – nie aus der Antwort des
Einspielens.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import sync_orakel as orakel
from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m2 import konto_nach_iban, lade_sync, mock_api, nach_kennung, sync
from tests.hilfen.m3 import UNKATEGORISIERT, erfassen, konto_id
from tests.hilfen.m4 import GNC, Buch, import_gnc, vorlage
from tests.hilfen.m9 import bestand, einspielen, inhalt, inhalt_sha256, lesezustand, oeffne, sicherung, sync_konten
from tests.hilfen.pfade import KMY

pytestmark = pytest.mark.kern

VON = "2024-01-01"
HEUTE = dt.date(2024, 6, 30)


# ------------------------------------------------------------------ Hilfen
def _gebucht(daten, iban: str) -> list[dict]:
    geliefert = orakel.im_zeitraum(daten["bank"]["umsaetze"], iban, dt.date.fromisoformat(VON), HEUTE, HEUTE)
    return [u for u in geliefert if not u["vormerkung"]]


def _sk(lauf: dict, iban: str) -> dict | None:
    return next((k for k in lauf["konten"] if k["iban"] == iban), None)


def _zustand(api, iban: str) -> dict:
    return next(z for z in sync_konten(api) if z["iban"] == iban)


def _loeschen(api, kid: int) -> None:
    api.post(f"/api/konten/{kid}/loeschen", json={"buchungen": "loeschen", "konflikte": "behalten"}, erwartet=200)


def _entscheiden(api, iban: str, aktion: str, buchungen: str) -> dict:
    return api.post(f"/api/sync/konten/{iban}/entscheidung", json={"aktion": aktion, "buchungen": buchungen},
                    erwartet=200).daten


def _vorschlag(api, bid: int, aktion: str) -> None:
    api.post(f"/api/buchungen/{bid}/vorschlag", json={"aktion": aktion}, erwartet=200)


def _lernzustand(api) -> dict:
    d = api.get("/api/lernmodell", erwartet=200).daten
    return {k: v for k, v in d.items() if k != "automatisch"}


# ------------------------------------------------------------------ Split-Vorlagen (M4)
def test_vorlagen_mit_bezuegen_reihenfolge_und_zaehler(api, tmp_path):
    """2.1 Punkt 1 und 4: Vorlagen mit allen Feldern, Bezügen auf Konten und eigenem ID-Zähler."""
    giro = api.konto("Giro", "girokonto")
    haft, hausrat = api.konto("Haftpflicht", "aufwand"), api.konto("Hausrat", "aufwand")
    v1 = vorlage(api, "Versicherung", "Fiktive Versicherung AG",
                 [(haft["id"], 1000, "Vertrag 0001"), (hausrat["id"], 2500, "Vertrag 0002")], zweck="Beitrag")
    alt = [{f: b[f] for f in ("feld", "operator", "wert")} for b in v1["bedingungen"]]  # E-124
    api.patch(f"/api/vorlagen/{v1['id']}", json={"bedingungen": alt + [
        {"feld": "konto_id", "operator": "gleich", "wert": giro["id"]}]}, erwartet=200)
    v2 = vorlage(api, "Alt", "Fiktive Versicherung AG", [(haft["id"], 700), (hausrat["id"], 800)], aktiv=False,
                 prioritaet=5)
    weg = vorlage(api, "weg", "Niemand", [(haft["id"], 1), (hausrat["id"], 1)])
    api.delete(f"/api/vorlagen/{weg['id']}", erwartet=204)
    erfassen(api, art="ausgabe", datum="2024-02-01", konto_id=giro["id"], betrag=3500,
             empfaenger_name="Fiktive Versicherung AG", verwendungszweck="Beitrag Februar")
    i = inhalt(api)
    assert [v["id"] for v in i["vorlage"]] == sorted([v1["id"], v2["id"]])
    daten = sicherung(api)
    m, _ = oeffne(daten)
    assert m["anzahl"]["vorlage"] == 2 and m["inhalt_sha256"] == inhalt_sha256(i)

    b = neue_api(tmp_path / "b")
    einspielen(b, daten)
    assert lesezustand(b) == lesezustand(api)
    assert b.get("/api/vorlagen", erwartet=200).daten == api.get("/api/vorlagen", erwartet=200).daten, (
        "Reihenfolge nach prioritaet, inaktive Vorlage bleibt inaktiv")
    # gleiche Wirkung wie in der Quelle (Erkennung über Empfänger, Muster, konto_id)
    probe = {"trocken": True}
    assert (b.post("/api/vorlagen/anwenden", json=probe, erwartet=200).daten
            == api.post("/api/vorlagen/anwenden", json=probe, erwartet=200).daten)
    assert b.post("/api/vorlagen/anwenden", json=probe, erwartet=200).daten["anzahl"] == 1
    # Bezüge der Vorlagen wirken weiter (vorlagen.md 1)
    assert fehlercode(b.delete(f"/api/konten/{haft['id']}", erwartet=409)) == "konto_in_verwendung"
    # Zähler: auch die gelöschte Vorlage der Quelle belegt ihre ID
    neu = vorlage(b, "neu", "Fiktive Versicherung AG", [(haft["id"], 1), (hausrat["id"], 2)])
    assert neu["id"] > weg["id"], "Vorlagen-IDs werden nach dem Einspielen nie wiederverwendet"


# ------------------------------------------------------------------ Vorschläge, Aliase, Lernmodell
def test_vorschlaege_aller_quellen_aliase_und_lernmodell(tmp_path):
    """Vorschläge mit quelle regel und lernmodell (mit sicherheit) gehören zur Buchung; das Lernmodell ergibt sich aus
    dem eingespielten Bestand, ``automatisch`` bleibt Konfiguration des Ziels. Ab M32 ohne Standardkategorie: an ihre
    Stelle tritt die Regel „Empfänger ist Bäckerei Korn“ (sammel3.md 2.1, E-307)."""
    a = neue_api(tmp_path / "a")
    buch = Buch(a)
    for i in range(3):
        buch.einfach("Supermarkt", f"Einkauf {i}", -1500, "Lebensmittel")
    buch.einfach("Café Bohne", "Kartenzahlung", -340, "Café")
    g = buch.giro
    a.post("/api/regeln", json={"name": "Tanken", "kategorie_id": buch.kats["Tanken"],
                                "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt", "wert": "Tankstelle"}]},
           erwartet=201)
    a.post("/api/empfaenger", json={"name": "Bäckerei Korn", "aliase": ["BAECKEREI KORN GMBH"]}, erwartet=201)
    a.post("/api/regeln", json={"name": "Empfänger ist Bäckerei Korn", "kategorie_id": buch.kats["Café"],
                                "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "Bäckerei Korn"}]},
           erwartet=201)
    tank = erfassen(a, art="ausgabe", datum="2024-04-01", konto_id=g, betrag=5000, empfaenger_name="Tankstelle Nord")
    std = erfassen(a, art="ausgabe", datum="2024-04-02", konto_id=g, betrag=420,
                   empfaenger_name="Baeckerei Korn GmbH")
    a.post("/api/regeln/anwenden", json={}, erwartet=200)
    lern = erfassen(a, art="ausgabe", datum="2024-04-03", konto_id=g, betrag=1700, empfaenger_name="Supermarkt",
                    verwendungszweck="Einkauf")
    a.post("/api/lernmodell/anwenden", json={}, erwartet=200)
    vs = {x["id"]: a.buchung_lesen(x["id"])["vorschlag"] for x in (tank, std, lern)}
    assert [vs[x["id"]]["quelle"] for x in (tank, std, lern)] == ["regel", "regel", "lernmodell"], vs
    assert "sicherheit" in vs[lern["id"]] and "sicherheit" not in vs[std["id"]]
    alle = [{"buchung_id": x["id"]} for x in a.alle_buchungen()] + [
        {"empfaenger": "Supermarkt", "verwendungszweck": "", "betrag": -10}]
    soll_lern = _lernzustand(a)
    soll_vorh = a.post("/api/lernmodell/vorhersage", json={"eintraege": alle}, erwartet=200).daten
    daten = sicherung(a)

    b = neue_api(tmp_path / "b", lernmodell_automatisch=True)
    einspielen(b, daten)
    assert lesezustand(b) == lesezustand(a)
    assert {x["id"]: b.buchung_lesen(x["id"])["vorschlag"] for x in (tank, std, lern)} == vs
    assert _lernzustand(b) == soll_lern, "das Lernmodell ist eine Funktion des eingespielten Bestands"
    assert b.get("/api/lernmodell", erwartet=200).daten["automatisch"] is True, "Konfiguration des Ziels"
    assert a.get("/api/lernmodell", erwartet=200).daten["automatisch"] is False
    assert b.post("/api/lernmodell/vorhersage", json={"eintraege": alle}, erwartet=200).daten == soll_vorh

    # dieselben Folgeoperationen auf Quelle und Ziel ergeben denselben Bestand
    for x in (a, b):
        _vorschlag(x, tank["id"], "annehmen")
        _vorschlag(x, std["id"], "ablehnen")
        _vorschlag(x, lern["id"], "ablehnen")
        erfassen(x, art="ausgabe", datum="2024-04-04", konto_id=g, betrag=380, empfaenger_name="baeckerei korn gmbh")
    assert bestand(b) == bestand(a)
    unk = konto_id(b, UNKATEGORISIERT)
    for bid in (std["id"], lern["id"]):
        assert b.buchung_lesen(bid)["kategorie_id"] is None, "Ablehnen setzt auf vorher_konto_id zurück"
        assert any(s["konto_id"] == unk for s in b.buchung_lesen(bid)["splits"])
    letzte = max(b.alle_buchungen(), key=lambda x: x["id"])
    assert letzte["empfaenger"]["name"] == "Bäckerei Korn" and letzte["vorschlag"] is None, "Alias wirkt weiter"
    assert len(b.get("/api/empfaenger", erwartet=200).daten) == len(a.get("/api/empfaenger", erwartet=200).daten)


# ------------------------------------------------------------------ Synchronisation
@pytest.fixture
def sd():
    return lade_sync()


def test_geloeschte_buchung_kommt_nach_einspielen_nicht_wieder(tmp_path, sd, netz_gesperrt):
    """2.1 Punkt 2: alle gemerkten Kennungen, auch die gelöschter Buchungen (synchronisation.md 4.3, E-034)."""
    a = mock_api(tmp_path / "a")
    sync(a, von=VON)
    kennung, weg = sorted(nach_kennung(a.alle_buchungen()).items())[0]
    a.delete(f"/api/buchungen/{weg['id']}", erwartet=204)
    daten = sicherung(a)
    b = mock_api(tmp_path / "b")
    einspielen(b, daten)
    lauf = sync(b, von=VON)
    assert all(k["buchungen_neu"] == 0 for k in lauf["konten"]), "gelöschte Buchung käme sonst wieder"
    assert kennung not in nach_kennung(b.alle_buchungen())
    sync(a, von=VON)
    assert bestand(b) == bestand(a)


def test_konto_fehlt_bleibt_nach_einspielen(tmp_path, sd, netz_gesperrt):
    """2.1 Punkt 3: Eintrag eines Bankkontos, dessen Konto gelöscht ist; konto_id zeigt auf das gelöschte Konto."""
    daten, erw = sd
    a = mock_api(tmp_path / "a")
    sync(a, von=VON)
    giro = erw["ibans"]["giro"]
    alt = konto_nach_iban(a)[giro]
    _loeschen(a, alt["id"])
    soll = sync_konten(a)
    assert (_zustand(a, giro)["status"], _zustand(a, giro)["konto_id"]) == ("konto_fehlt", alt["id"])
    b = mock_api(tmp_path / "b")
    einspielen(b, sicherung(a))
    assert sync_konten(b) == soll
    lauf = sync(b, von=VON)
    assert lauf["uebersprungen"] == [{"iban": giro, "name": erw["konto_namen"][giro], "status": "konto_fehlt"}]
    assert giro not in konto_nach_iban(b), "kein stilles Neuanlegen nach dem Einspielen"
    assert b.konto("Neu", "aufwand")["id"] > alt["id"], "die ID des gelöschten Kontos bleibt belegt"


def test_vermerkte_wiederherstellung_alle(tmp_path, sd, netz_gesperrt):
    """2.1 Punkt 3: Eine gespeicherte Entscheidung "wiederherstellen"/"alle" wirkt nach dem Einspielen beim
    nächsten Lauf (synchronisation.md 16.2 Regel 3) – dafür braucht es auch die gemerkten Kennungen."""
    daten, erw = sd
    a = mock_api(tmp_path / "a")
    sync(a, von=VON)
    giro = erw["ibans"]["giro"]
    _loeschen(a, konto_nach_iban(a)[giro]["id"])
    _entscheiden(a, giro, "wiederherstellen", "alle")
    soll = sync_konten(a)
    b = mock_api(tmp_path / "b")
    einspielen(b, sicherung(a))
    assert sync_konten(b) == soll
    z = _zustand(b, giro)
    assert (z["status"], z["wiederherstellen_buchungen"], z["letzter_abruf_bis"]) == (
        "wiederherstellen", "alle", "2024-06-30")
    lauf = sync(b, von=VON)
    sk = _sk(lauf, giro)
    gebucht = _gebucht(daten, giro)
    assert (sk["konto_neu"], sk["buchungen_neu"]) == (True, len(gebucht))
    assert set(nach_kennung(b.alle_buchungen(), f"bank:{giro}:")) == {orakel.kennung(u) for u in gebucht}
    sync(a, von=VON)
    assert lesezustand(b) == lesezustand(a), "gleiches Ergebnis wie in der Quelle"


def test_verdeckte_entscheidung_bleibt_erhalten(tmp_path, sd, netz_gesperrt):
    """2.1 Punkt 3: Eine gespeicherte Entscheidung gehört zur Sicherung, auch solange ein Konto mit der IBAN sie
    verdeckt (Status aktiv; verworfen wird sie erst im nächsten Lauf, synchronisation.md 16.2 Regel 1)."""
    _, erw = sd
    a = mock_api(tmp_path / "a")
    sync(a, von=VON)
    giro = erw["ibans"]["giro"]
    _loeschen(a, konto_nach_iban(a)[giro]["id"])
    _entscheiden(a, giro, "wiederherstellen", "nur_neue")
    _entscheiden(a, giro, "ignorieren", "alle")
    hand = a.konto("Mein Giro", "girokonto", iban=giro)
    assert _zustand(a, giro)["status"] == "aktiv"
    b = mock_api(tmp_path / "b")
    einspielen(b, sicherung(a))
    assert sync_konten(b) == sync_konten(a)
    for x in (a, b):
        x.delete(f"/api/konten/{hand['id']}", erwartet=204)
        z = _zustand(x, giro)
        assert (z["status"], z["wiederherstellen_buchungen"]) == ("ignoriert", None), "letzte Entscheidung zählt"


# ------------------------------------------------------------------ Import nach dem Einspielen
def test_import_nach_einspielen_wie_auf_der_quelle(api, tmp_path):
    """7: KMyMoney- und GnuCash-Import nach dem Einspielen ordnen über extern_id zu (Idempotenz);
    Importvorgänge der Quelle gehören nicht zur Sicherung (2.2)."""
    api.import_kmy(KMY / "standard.kmy", erwartet=200)
    import_gnc(api, GNC / "sonderfaelle.gnucash")
    soll = lesezustand(api)
    b = neue_api(tmp_path / "b")
    einspielen(b, sicherung(api))
    assert b.get("/api/importe", erwartet=200).daten == []
    b.import_kmy(KMY / "standard.kmy", erwartet=200)
    import_gnc(b, GNC / "sonderfaelle.gnucash")
    assert lesezustand(b) == soll, "Wiederholter Import auf dem eingespielten Bestand ändert nichts"
    assert len(b.get("/api/importe", erwartet=200).daten) == 2
