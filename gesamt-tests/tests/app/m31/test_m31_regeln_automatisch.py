"""M31: automatisch angelegte Regeln aus dem Gelernten (lernmodell.md 9, protokoll.md 23, sicherung.md 13;
E-279) – REST, kern.

Die Erwartung, ob eine Regel entsteht, folgt aus den Bedingungen 9.1 über die selbst angelegten Buchungen.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen.api import neue_api
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id, regel_zustand, rueckgaengig
from tests.hilfen.m4 import mock_api as m4_mock_api, mock_datei, umsatz
from tests.hilfen.m6 import pruefe_eintraege
from tests.hilfen.m9 import einspielen, oeffne, sicherung
from tests.hilfen.m30 import alle_treffer
from tests.hilfen.m31 import automatische, bedingung_ok, bestand, einstellungen_setzen

pytestmark = pytest.mark.kern
NAME = "Markt Fiktiv"
IBAN = "DE02000000000000004711"


class Bestand:
    def __init__(self, api):
        self.api = api
        self.giro = api.konto("Giro", "girokonto")["id"]
        self.ek = api.konto("Eigenkapital", "eigenkapital")["id"]
        self.k = {n: api.konto(n, "aufwand")["id"] for n in ("Lebensmittel", "Café", "Drogerie")}
        self.e: dict[str, int] = {}

    def empf(self, name: str = NAME) -> int:
        if name not in self.e:
            self.e[name] = self.api.empfaenger(name)["id"]
        return self.e[name]

    def buchen(self, datum: str = "2026-03-02", kat: str | None = "Lebensmittel", name: str = NAME,
               betrag: int = 1234) -> dict:
        gegen = self.k[kat] if kat else self.ek
        return self.api.buchung(datum, [(self.giro, -betrag), (gegen, betrag)], empfaenger_id=self.empf(name),
                                verwendungszweck="Einkauf")

    def reihe(self, n: int, *, start: str = "2026-01-05", kat: str | None = "Lebensmittel", name: str = NAME):
        d0 = dt.date.fromisoformat(start)
        return [self.buchen((d0 + dt.timedelta(days=i)).isoformat(), kat, name) for i in range(n)]


def _app(tmp_path, **felder):
    return neue_api(tmp_path, **{"regeln_automatisch": True, **felder})


def _lernmodell_aenderungen(api, a0):
    return [a for a in aenderungen_seit(api, a0) if a["quelle"] == "lernmodell"]


def _patch_zweck(api, bid, text):
    api.patch(f"/api/buchungen/{bid}", json={"verwendungszweck": text}, erwartet=200)


# ------------------------------------------------------------------ 9.1–9.3


def test_regel_nach_der_fuenften_buchung(tmp_path):
    api = _app(tmp_path)
    b = Bestand(api)
    a0 = letzte_aenderung_id(api)
    erste = b.reihe(4)
    assert automatische(api) == {} and _lernmodell_aenderungen(api, a0) == []
    fuenfte = b.buchen("2026-02-01")
    folge = aenderungen_seit(api, a0)
    ausloeser = [x for x in folge if x["quelle"] == "manuell"][-1]
    assert ausloeser["aktion"] == "buchung_anlegen"
    (a,) = _lernmodell_aenderungen(api, a0)
    assert (a["quelle"], a["aktion"], a["id"]) == ("lernmodell", "regel_automatisch", ausloeser["id"] + 1)
    assert folge[-1]["id"] == a["id"], "direkt nach der auslösenden Änderung, keine weitere"
    (r,) = automatische(api).values()
    assert (r["name"], r["kategorie_id"], r["aktiv"], r["empfaenger_id"], r["automatisch"]) == (
        NAME, b.k["Lebensmittel"], True, b.empf(), True)
    assert r["prioritaet"] == 100, "Priorität wie beim Anlegen ohne Angabe (ohne andere Regeln 100)"
    assert r.get("tag_ids", []) == []
    assert bedingung_ok(r, NAME)
    (e,) = a["eintraege"]
    assert (e["objekt"], e["objekt_id"], e["art"], e["vorher"]) == ("regel", r["id"], "angelegt", None)
    assert e["nachher"] == regel_zustand(r)
    assert e["nachher"]["automatisch"] is True and e["nachher"]["empfaenger_id"] == b.empf()
    ids = {x["buchung_id"] for x in alle_treffer(api, regel_id=r["id"])}
    assert {x["id"] for x in erste} | {fuenfte["id"]} <= ids, "die Regel trifft die Buchungen des Empfängers"


def test_andere_regeln_tragen_die_felder_nicht(api):
    k = api.konto("Lebensmittel", "aufwand")["id"]
    r = api.post("/api/regeln", json={"name": "Hand", "kategorie_id": k, "bedingungen": [
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "Markt"}]}, erwartet=201).daten
    assert "automatisch" not in r and "empfaenger_id" not in r
    assert automatische(api) == {}


def test_vorgabe_aus_und_einschalten_ueber_die_einstellung(tmp_path):
    api = neue_api(tmp_path)
    b = Bestand(api)
    a0 = letzte_aenderung_id(api)
    bs = b.reihe(6)
    assert automatische(api) == {}, "Vorgabe regeln_automatisch = False"
    einstellungen_setzen(api, regeln_automatisch=True)
    assert automatische(api) == {} and _lernmodell_aenderungen(api, a0) == [], "die Einstellung löst nichts aus"
    _patch_zweck(api, bs[0]["id"], "Einkauf Samstag")
    assert set(automatische(api)) == {b.empf()}


@pytest.mark.parametrize("anders,gleich,regel", [(1, 19, True), (2, 18, False), (1, 4, False)])
def test_quote_von_95_prozent(tmp_path, anders, gleich, regel):
    api = _app(tmp_path)
    b = Bestand(api)
    b.reihe(anders, kat="Café", start="2026-01-01")
    b.reihe(gleich, start="2026-02-01")
    ist = automatische(api)
    assert (b.empf() in ist) is regel, f"{gleich} von {anders + gleich}"
    if regel:
        assert ist[b.empf()]["kategorie_id"] == b.k["Lebensmittel"]


@pytest.mark.parametrize("abweichend_alt,regel", [(True, True), (False, False)])
def test_fenster_von_365_tagen(tmp_path, abweichend_alt, regel):
    """D-184: auch in den 365 Tagen bis zur jüngsten Buchung mindestens 95 % (insgesamt 77 von 80)."""
    api = _app(tmp_path)
    b = Bestand(api)
    b.reihe(3, kat="Café", start="2023-01-01" if abweichend_alt else "2025-05-01")
    b.reihe(17, start="2025-06-01")
    b.reihe(60, start="2023-02-01")
    assert (b.empf() in automatische(api)) is regel


def test_aktive_regel_trifft_die_juengste_buchung_schon(tmp_path):
    api = _app(tmp_path)
    b = Bestand(api)
    api.post("/api/regeln", json={"name": "Hand", "kategorie_id": b.k["Drogerie"], "bedingungen": [
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "markt"}]}, erwartet=201)
    b.reihe(6)
    assert automatische(api) == {}


def test_kategorie_setzen_loest_aus(tmp_path):
    api = _app(tmp_path)
    b = Bestand(api)
    bs = b.reihe(5, kat=None)
    assert automatische(api) == {}, "ohne Kategorie nicht in der Trainingsmenge"
    for x in bs[:4]:
        api.put(f"/api/buchungen/{x['id']}/kategorie", json={"kategorie_id": b.k["Café"]}, erwartet=200)
    assert automatische(api) == {}
    a0 = letzte_aenderung_id(api)
    api.put(f"/api/buchungen/{bs[4]['id']}/kategorie", json={"kategorie_id": b.k["Café"]}, erwartet=200)
    folge = aenderungen_seit(api, a0)
    assert [x["quelle"] for x in folge] == ["manuell", "lernmodell"]
    assert automatische(api)[b.empf()]["kategorie_id"] == b.k["Café"]


def test_mehrere_empfaenger_in_einer_aenderung(tmp_path):
    api = _app(tmp_path)
    b = Bestand(api)
    for name in ("Markt Eins", "Markt Zwei"):
        b.reihe(4, name=name)
    ids = [b.buchen("2026-03-01", name="Markt Eins")["id"], b.buchen("2026-03-01", name="Markt Zwei")["id"]]
    assert set(automatische(api)) == {b.e["Markt Eins"], b.e["Markt Zwei"]}
    a0 = letzte_aenderung_id(api)
    api.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": ids, "kategorie_id": b.k["Lebensmittel"]},
             erwartet=200)
    assert _lernmodell_aenderungen(api, a0) == [], "keine zweite Regel je Empfänger"


# ------------------------------------------------------------------ 9.2: was nichts auslöst


def test_sync_regeln_lernmodell_und_rueckgaengig_loesen_nichts_aus(tmp_path):
    datei = mock_datei(tmp_path / "mock.json", [(IBAN, "Girokonto", "girokonto")],
                       [umsatz("U-1", IBAN, "2026-03-10", -1500, NAME, "Einkauf")])
    api = m4_mock_api(tmp_path / "app", datei, "2026-03-20")
    b = Bestand(api)
    bs = b.reihe(5)
    sechste = b.buchen("2026-02-20")
    a_sechste = letzte_aenderung_id(api)
    assert automatische(api) == {}
    einstellungen_setzen(api, regeln_automatisch=True)
    a0 = letzte_aenderung_id(api)
    rueckgaengig(api, a_sechste)
    api.post("/api/regeln/anwenden", json={}, erwartet=200)
    api.post("/api/lernmodell/anwenden", json={}, erwartet=200)
    lauf = api.post("/api/sync", json={}, erwartet=200).daten
    assert lauf["status"] == "erfolgreich", lauf
    assert any(x["empfaenger"] and x["empfaenger"]["name"] == NAME and x["datum"] == "2026-03-10"
               for x in api.alle_buchungen()), "Voraussetzung: der Umsatz wurde gebucht"
    assert automatische(api) == {} and _lernmodell_aenderungen(api, a0) == []
    assert sechste["id"] not in {x["id"] for x in api.alle_buchungen()}
    _patch_zweck(api, bs[0]["id"], "Einkauf Montag")
    assert set(automatische(api)) == {b.empf()}, "eine manuelle Änderung löst aus"


# ------------------------------------------------------------------ 9.4 Löschen, Rückgängig, Umbenennen


def test_loeschen_sperrt_nicht_rueckgaengig_bringt_zurueck(tmp_path):
    """D-305: Das Löschen sperrt den Empfänger nicht mehr; die Regel darf wieder entstehen."""
    api = _app(tmp_path)
    b = Bestand(api)
    bs = b.reihe(5)
    (r,) = automatische(api).values()
    vorher = bestand(api)
    a0 = letzte_aenderung_id(api)
    api.delete(f"/api/regeln/{r['id']}", erwartet=204)
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"]) == ("manuell", "regel_loeschen")
    nachher = bestand(api)  # ohne Sperre
    pruefe_eintraege(a, vorher, nachher)
    assert {(e["objekt"], e["art"]) for e in a["eintraege"]} == {("regel", "geloescht")}
    a1 = letzte_aenderung_id(api)
    u = rueckgaengig(api, a["id"]).daten
    assert u["aktion"] == "rueckgaengig"
    assert automatische(api)[b.empf()] == r, "Regel wieder da"
    assert _lernmodell_aenderungen(api, a1) == []
    api.delete(f"/api/regeln/{r['id']}", erwartet=204)
    _patch_zweck(api, bs[1]["id"], "Einkauf Dienstag")
    neu = automatische(api)
    assert set(neu) == {b.empf()} and neu[b.empf()]["id"] != r["id"], "nach dem Löschen entsteht sie wieder"


def test_deaktivierte_regel_verhindert_neue(tmp_path):
    api = _app(tmp_path)
    b = Bestand(api)
    bs = b.reihe(5)
    (r,) = automatische(api).values()
    api.patch(f"/api/regeln/{r['id']}", json={"aktiv": False}, erwartet=200)
    _patch_zweck(api, bs[1]["id"], "Einkauf Dienstag")
    b.buchen("2026-04-01")
    assert [x["id"] for x in automatische(api).values()] == [r["id"]], "keine zweite Regel"


def test_rueckgaengig_der_anlage_und_erneute_anlage(tmp_path):
    api = _app(tmp_path)
    b = Bestand(api)
    bs = b.reihe(5)
    a = next(x for x in aenderungen_seit(api, 0) if x["aktion"] == "regel_automatisch")
    a1 = letzte_aenderung_id(api)
    rueckgaengig(api, a["id"])
    assert automatische(api) == {} and _lernmodell_aenderungen(api, a1) == [], "Rückgängig löst nichts aus"
    bestand(api)  # keine Sperre: Rückgängig ist kein Löschen
    _patch_zweck(api, bs[2]["id"], "Einkauf Mittwoch")
    assert set(automatische(api)) == {b.empf()}


def test_umbenennen_keine_zweite_regel(tmp_path):
    api = _app(tmp_path)
    b = Bestand(api)
    bs = b.reihe(5)
    (r,) = automatische(api).values()
    api.patch(f"/api/empfaenger/{b.empf()}", json={"name": "Markt Neu Fiktiv"}, erwartet=200)
    _patch_zweck(api, bs[0]["id"], "Einkauf Freitag")
    b.buchen("2026-04-02")
    assert list(automatische(api).values()) == [r], "Regel bleibt unverändert, keine zweite"
    assert bedingung_ok(r, NAME)


# ------------------------------------------------------------------ Sicherung (sicherung.md 13)


def test_sicherung_rundreise(tmp_path):
    quelle = _app(tmp_path / "q")
    b = Bestand(quelle)
    b.reihe(5)
    b.reihe(5, name="Drogerie Fiktiv", kat="Drogerie")
    auto = automatische(quelle)
    aus = b.e["Drogerie Fiktiv"]
    quelle.patch(f"/api/regeln/{auto[aus]['id']}", json={"aktiv": False}, erwartet=200)  # D-305 statt Sperre
    bs = bestand(quelle)
    m, _ = oeffne(sicherung(quelle))
    assert m["schemaversion"] >= 9
    ziel = _app(tmp_path / "z")
    einspielen(ziel, sicherung(quelle))
    assert bestand(ziel) == bs
    assert automatische(ziel) == automatische(quelle)
    m2, _ = oeffne(sicherung(ziel))
    assert m2["inhalt_sha256"] == m["inhalt_sha256"] and m2["anzahl"] == m["anzahl"]
    d = [x for x in ziel.alle_buchungen() if x["empfaenger"] and x["empfaenger"]["id"] == aus]
    _patch_zweck(ziel, d[0]["id"], "Seife")
    assert automatische(ziel) == automatische(quelle), "die deaktivierte Regel wirkt auch nach dem Einspielen"


def test_pruefsumme_ohne_automatische_regeln_unveraendert(tmp_path):
    """Bestände ohne automatische Regeln behalten ihre Prüfsumme (sicherung.md 13)."""
    ein, aus = _app(tmp_path / "ein"), neue_api(tmp_path / "aus")
    for api in (ein, aus):
        Bestand(api).reihe(3)
    assert automatische(ein) == {}
    assert oeffne(sicherung(ein))[0]["inhalt_sha256"] == oeffne(sicherung(aus))[0]["inhalt_sha256"]
