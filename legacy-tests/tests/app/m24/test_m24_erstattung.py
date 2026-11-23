"""M24: Kategorie bei Erstattungen – Umbuchung von „Unkategorisiert“ auf die Kategorie der ursprünglichen Buchung
beim Zuordnen, in derselben Änderung (erwartungen.md 13.2, protokoll.md 19; E-234)."""

from __future__ import annotations

import pytest

from generator.iban import fiktive_iban
from tests.hilfen.m2 import UNKATEGORISIERT, unkategorisiert
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m6 import abruf
from tests.hilfen.m20 import NR, alle, amazon_bestellung, amazon_erstattung, bestand, detail
from tests.hilfen.m24 import mit_unkategorisiert

pytestmark = pytest.mark.kern

IBAN = fiktive_iban(2401)
MAILS = [amazon_bestellung(empfangen="2024-06-03T08:00:00Z"), amazon_erstattung(empfangen="2024-06-08T08:00:00Z")]


class Fall:
    """Bestellung U (4 990 Ausgabe) mit ursprünglicher Buchung O auf „Elektronik“, Erstattung E (999) mit Bezug U."""

    def __init__(self, tmp_path, mails=MAILS):
        self.api = api = mit_unkategorisiert(tmp_path, mails, iban=IBAN)
        self.giro = next(k["id"] for k in api.konten() if k["iban"] == IBAN)
        u = unkategorisiert(api)
        assert u is not None and u["extern_id"] == UNKATEGORISIERT and u["name"] == "Unkategorisiert"
        self.unkat = u["id"]
        self.k = api.konto("Elektronik (fiktiv)", "aufwand")["id"]
        self.k2 = api.konto("Haushalt (fiktiv)", "aufwand")["id"]
        self.ertrag = api.konto("Sonstige Erträge (fiktiv)", "ertrag")["id"]
        abruf(api)
        es = {e["grund"]: e for e in alle(api)}
        self.u, self.e = es.get("bestellung"), es.get("rueckerstattung")

    def buchung(self, datum, splits, zweck="Kartenzahlung") -> int:
        return self.api.buchung(datum, splits, verwendungszweck=zweck)["id"]

    def ursprung(self, kat=None, betrag=4990) -> int:
        return self.buchung("2024-06-04", [(self.giro, -betrag), (kat or self.k, betrag)])

    def gutschrift(self, zweck="Gutschrift", splits=None) -> int:
        return self.buchung("2024-06-09", splits or [(self.giro, 999), (self.unkat, -999)], zweck)

    def zuordnen(self, eid, *bids):
        return self.api.post(f"/api/erwartungen/{eid}/buchungen", json={"buchung_ids": list(bids)}, erwartet=200).daten

    def gegenkonten(self, bid) -> list[int]:
        return sorted(s["konto_id"] for s in self.api.buchung_lesen(bid)["splits"] if s["konto_id"] != self.giro)


@pytest.fixture
def fall(tmp_path):
    f = Fall(tmp_path)
    assert f.u and f.e and f.e["bezug_id"] == f.u["id"], alle(f.api)
    return f


def test_manuell_umbuchen_mit_protokoll_und_rueckgaengig(fall):
    api = fall.api
    o = fall.ursprung()
    fall.zuordnen(fall.u["id"], o)
    g = fall.gutschrift()
    status = api.buchung_lesen(g)["status"]
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    fall.zuordnen(fall.e["id"], g)
    assert fall.gegenkonten(g) == [fall.k]
    b = api.buchung_lesen(g)
    assert sorted(s["betrag"] for s in b["splits"]) == [-999, 999] and b["status"] == status
    nachher = bestand(api)
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("manuell", "erwartung_zuordnen", None)
    objekte = {(x["objekt"], x["objekt_id"]) for x in a["eintraege"]}
    assert {("erwartung", fall.e["id"]), ("buchung", g)} <= objekte
    assert {o for o, _ in objekte} <= {"erwartung", "buchung", "dokument"}, "dazu nur Dokumente der Mail (M20 5.3)"
    assert [i for o, i in objekte if o == "buchung"] == [g]
    eintr = {(x["objekt"], x["objekt_id"]): x for x in a["eintraege"]}
    assert (eintr[("buchung", g)]["vorher"], eintr[("buchung", g)]["nachher"]) == (vorher[("buchung", g)],
                                                                                   nachher[("buchung", g)])
    u = api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(api) == vorher and fall.gegenkonten(g) == [fall.unkat]
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == nachher and fall.gegenkonten(g) == [fall.k]


def test_loesen_setzt_nicht_zurueck(fall):
    o = fall.ursprung()
    fall.zuordnen(fall.u["id"], o)
    g = fall.gutschrift()
    fall.zuordnen(fall.e["id"], g)
    fall.api.delete(f"/api/erwartungen/{fall.e['id']}/buchungen/{g}", erwartet=200)
    assert fall.gegenkonten(g) == [fall.k]


def test_automatisch_im_abgleich(fall):
    api = fall.api
    o = fall.ursprung()
    fall.zuordnen(fall.u["id"], o)
    g = fall.gutschrift(zweck=f"Erstattung {NR}")
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    api.post("/api/erwartungen/abgleich", erwartet=200)
    assert detail(api, fall.e["id"])["buchung_ids"] == [g]
    assert fall.gegenkonten(g) == [fall.k]
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"]) == ("mail", "erwartung_erkennen")
    assert ("buchung", g) in {(x["objekt"], x["objekt_id"]) for x in a["eintraege"]}
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == vorher and fall.gegenkonten(g) == [fall.unkat]


def test_kleinste_buchung_der_bestellung_zaehlt(fall):
    o1 = fall.buchung("2024-06-04", [(fall.giro, -2000), (fall.k2, 2000)])
    o2 = fall.buchung("2024-06-05", [(fall.giro, -2990), (fall.k, 2990)])
    fall.zuordnen(fall.u["id"], o2, o1)
    g = fall.gutschrift()
    fall.zuordnen(fall.e["id"], g)
    assert fall.gegenkonten(g) == [fall.k2], "ursprüngliche Buchung = kleinste ID"


def _keine_umbuchung(fall, g, vorher_konten):
    e = fall.zuordnen(fall.e["id"], g)
    assert g in e["buchung_ids"], "die Zuordnung geschieht in jedem Fall"
    assert fall.gegenkonten(g) == vorher_konten


def test_bestellung_ohne_buchung(fall):
    g = fall.gutschrift()
    _keine_umbuchung(fall, g, [fall.unkat])


def test_ursprung_mit_zwei_kategorien(fall):
    o = fall.buchung("2024-06-04", [(fall.giro, -4990), (fall.k, 2990), (fall.k2, 2000)])
    fall.zuordnen(fall.u["id"], o)
    g = fall.gutschrift()
    _keine_umbuchung(fall, g, [fall.unkat])


def test_ursprung_auf_unkategorisiert(fall):
    o = fall.ursprung(kat=fall.unkat)
    fall.zuordnen(fall.u["id"], o)
    g = fall.gutschrift()
    _keine_umbuchung(fall, g, [fall.unkat])


def test_gutschrift_mit_drei_splits(fall):
    fall.zuordnen(fall.u["id"], fall.ursprung())
    g = fall.gutschrift(splits=[(fall.giro, 999), (fall.unkat, -500), (fall.k2, -499)])
    _keine_umbuchung(fall, g, sorted([fall.unkat, fall.k2]))


def test_gutschrift_schon_kategorisiert(fall):
    fall.zuordnen(fall.u["id"], fall.ursprung())
    g = fall.gutschrift(splits=[(fall.giro, 999), (fall.ertrag, -999)])
    _keine_umbuchung(fall, g, [fall.ertrag])


def test_nur_neu_zugeordnete(fall):
    g = fall.gutschrift()
    fall.zuordnen(fall.e["id"], g)
    fall.zuordnen(fall.u["id"], fall.ursprung())
    fall.api.patch(f"/api/erwartungen/{fall.e['id']}", json={"betrag": 2000}, erwartet=200)
    assert detail(fall.api, fall.e["id"])["zustand"] == "offen"
    a0 = letzte_aenderung_id(fall.api)
    fall.zuordnen(fall.e["id"], g)
    assert fall.gegenkonten(g) == [fall.unkat], "schon zugeordnete Buchung ist nicht neu"
    assert letzte_aenderung_id(fall.api) == a0


def test_erstattung_ohne_bezug(tmp_path):
    f = Fall(tmp_path, mails=[amazon_erstattung(empfangen="2024-06-08T08:00:00Z")])
    assert f.u is None and f.e["bezug_id"] is None
    g = f.gutschrift()
    e = f.zuordnen(f.e["id"], g)
    assert e["buchung_ids"] == [g] and f.gegenkonten(g) == [f.unkat]


def test_andere_gruende_buchen_nicht_um(fall):
    m = fall.api.post("/api/erwartungen", json={"richtung": "eingang", "haendler": "Rückzahlung (fiktiv)",
                                                "betrag": 999}, erwartet=201).daten
    fall.zuordnen(fall.u["id"], fall.ursprung())
    g = fall.gutschrift()
    fall.zuordnen(m["id"], g)
    assert fall.gegenkonten(g) == [fall.unkat]
