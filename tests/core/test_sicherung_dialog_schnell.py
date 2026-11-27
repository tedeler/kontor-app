"""Core-Tests zum Feature „sicherung-dialog-schnell“ (D-314, sicherungspunkte.md 7).

Der Vergleich eines Sicherungspunkts mit dem aktuellen Stand (`GET /api/sicherung/punkte/{kennung}/vergleich`)
liefert dieselben Zählungen wie der Probelauf mit der Sicherungsdatei des Punkts, aber ohne deren Manifest; er
ist genau dann „geändert“, wenn ein Wechsel auf den Punkt nicht als unverändert abgelehnt wird. Beschädigte
Glieder der Kette werden weiter erkannt.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from kontor import sicherungspunkte as sp
from kontor.app import create_app
from kontor.config import KontorConfig

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 11, 2, 10, 0, tzinfo=UTC)


@pytest.fixture
def umgebung(tmp_path):
    config = KontorConfig(datenbank=tmp_path / "kontor.sqlite3", sicherung_verzeichnis=tmp_path / "sicherungen")
    c = TestClient(create_app(config))
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Lebensmittel", "art": "aufwand"}).json()["id"]

    def buchen(betrag=1234, zweck="Einkauf"):
        r = c.post("/api/buchungen", json={"datum": "2026-11-01", "verwendungszweck": zweck, "splits": [
            {"konto_id": giro, "betrag": -betrag}, {"konto_id": kat, "betrag": betrag}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    return config, c, buchen


def probelauf_mit_datei(c, kennung):
    datei = c.get(f"/api/sicherung/punkte/{kennung}/datei")
    assert datei.status_code == 200
    r = c.post("/api/sicherung/einspielen", params={"trocken": "true"},
               files={"datei": ("punkt.zip", datei.content, "application/zip")})
    assert r.status_code == 200, r.text
    return r.json()


def vergleich(c, kennung):
    r = c.get(f"/api/sicherung/punkte/{kennung}/vergleich")
    assert r.status_code == 200, r.text
    return r.json()


def test_vergleich_zaehlt_wie_der_probelauf(umgebung):
    config, c, buchen = umgebung
    b1 = buchen(100)
    buchen(200)
    a = sp.stunde(config, jetzt=T0)["punkt"]["kennung"]
    buchen(300)
    sp.stunde(config, jetzt=T0 + dt.timedelta(hours=1))
    # danach: eine Buchung geändert, eine gelöscht, eine neu, ein Tag neu
    assert c.patch(f"/api/buchungen/{b1}", json={"verwendungszweck": "anders"}).status_code == 200
    buchen(400)
    c.post("/api/tags", json={"name": "Urlaub"})
    v = vergleich(c, a)
    p = probelauf_mit_datei(c, a)
    assert v["trocken"] is True and v["geaendert"] is True
    assert v["unterschied"] == p["unterschied"]
    assert v["abgestimmte_buchungen_betroffen"] == p["abgestimmte_buchungen_betroffen"]
    assert v["unterschied"]["buchung"] == {"angelegt": 0, "geaendert": 1, "geloescht": 2}
    assert v["unterschied"]["tag"]["geloescht"] == 1
    assert "manifest" not in v and "aenderung_id" not in v


def test_gleicher_stand_ist_unveraendert_wie_beim_wechsel(umgebung):
    config, c, buchen = umgebung
    buchen()
    k = sp.stunde(config, jetzt=T0)["punkt"]["kennung"]
    v = vergleich(c, k)
    assert v["geaendert"] is False
    assert all(z == {"angelegt": 0, "geaendert": 0, "geloescht": 0} for z in v["unterschied"].values())
    r = c.post(f"/api/sicherung/punkte/{k}/wechseln", params={"bestaetigt": "true"})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "stand_unveraendert"
    buchen(5)
    assert vergleich(c, k)["geaendert"] is True


def test_unbekannt_und_beschaedigte_kette(umgebung):
    config, c, buchen = umgebung
    assert c.get("/api/sicherung/punkte/gibtsnicht/vergleich").status_code == 404
    buchen(1)
    a = sp.stunde(config, jetzt=T0)["punkt"]["kennung"]
    buchen(2)
    b = sp.stunde(config, jetzt=T0 + dt.timedelta(hours=1))["punkt"]["kennung"]
    buchen(3)
    neu = sp.stunde(config, jetzt=T0 + dt.timedelta(hours=2))["punkt"]["kennung"]
    sp.datei_pfad(config, b).write_bytes(b"kaputt")   # mittleres Glied der Kette von „neu“
    for k in (b, neu):
        r = c.get(f"/api/sicherung/punkte/{k}/vergleich")
        assert r.status_code == 409 and r.json()["fehler"]["code"] == "punkt_nicht_herstellbar", k
    assert vergleich(c, a)["geaendert"] is True
