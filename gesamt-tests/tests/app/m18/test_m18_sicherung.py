"""M18: Dokumente in der Sicherung (dokumente.md 4, sicherung.md 2.7, E-207).

Die Inhaltsprüfsumme wird unabhängig aus den Lese-Endpunkten berechnet (Protokollformen mit ``dokument`` und
``dokument_ids``); das Schema von ``kontor.sqlite`` ist Sache der Implementierung.
"""

from __future__ import annotations

import pytest

from tests.hilfen.api import neue_api
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m9 import einspielen, inhalt_sha256, oeffne, sicherung
from tests.hilfen.m18 import anhaengen, bestand, dokument, inhalt, mail, pdf, png, pruefe_eintraege

pytestmark = pytest.mark.kern

OBJEKTE_M9 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]


def _inhalt(b: dict, objekte: list[str]) -> dict:
    return {o: [b[k] for k in sorted(k for k in b if k[0] == o)] for o in objekte}


def _aufbau(api) -> dict:
    g = api.konto("Girokonto")["id"]
    s = api.konto("Tagesgeld", "sparkonto")["id"]
    k = api.konto("Haushalt", "aufwand")["id"]
    b = [api.buchung(f"2024-04-{i + 1:02d}", [(g if i % 2 == 0 else s, -(500 + i)), (k, 500 + i)],
                     verwendungszweck=f"Posten {i}")["id"] for i in range(4)]
    daten = {"pdf": pdf("Sicherung"), "png": png(4, 3), "mail": mail(betreff="Beleg per Mail (fiktiv)")}
    d = {"pdf": anhaengen(api, [b[0], b[1]], "beleg.pdf", daten["pdf"]),
         "png": anhaengen(api, [b[1]], "foto.png", daten["png"], quelle="kamera"),
         "mail": anhaengen(api, [b[2]], "", daten["mail"], quelle="mail")}
    # gelöschtes Dokument: Lücke in den IDs
    weg = anhaengen(api, [b[3]], "weg.pdf", pdf("weg"))
    api.delete(f"/api/dokumente/{weg['id']}", erwartet=204)
    return {"b": b, "d": d, "daten": daten}


def test_ohne_dokumente_wie_vorher(api):
    g = api.konto("Girokonto")["id"]
    k = api.konto("Haushalt", "aufwand")["id"]
    api.buchung("2024-04-01", [(g, -100), (k, 100)])
    m, _ = oeffne(sicherung(api))
    assert set(m["anzahl"]) == set(OBJEKTE_M9), "ohne Dokumente kein Schlüssel dokument (nur bei Vorhandensein)"
    assert m["inhalt_sha256"] == inhalt_sha256(_inhalt(bestand(api), OBJEKTE_M9))


def test_mit_dokumenten_manifest_und_rundreise(tmp_path):
    a = neue_api(tmp_path / "a")
    x = _aufbau(a)
    quelle = bestand(a)
    m, _ = oeffne(sicherung(a))
    assert m["anzahl"]["dokument"] == 3 and set(m["anzahl"]) == set(OBJEKTE_M9) | {"dokument"}
    assert m["inhalt_sha256"] == inhalt_sha256(_inhalt(quelle, OBJEKTE_M9 + ["dokument"])), (
        "Inhaltsprüfsumme mit den Protokollformen 3.1 (dokument, dokument_ids)")
    assert quelle[("buchung", x["b"][1])]["dokument_ids"] == [x["d"]["pdf"]["id"], x["d"]["png"]["id"]]
    # Rundreise in eine leere App
    b = neue_api(tmp_path / "b")
    a0 = letzte_aenderung_id(b)
    e = einspielen(b, sicherung(a)).daten
    assert e["geaendert"] is True and e["unterschied"]["dokument"] == {"angelegt": 3, "geaendert": 0,
                                                                         "geloescht": 0}
    (aenderung,) = aenderungen_seit(b, a0)
    pruefe_eintraege(aenderung, {}, bestand(b))
    assert bestand(b) == quelle
    for name, d in x["d"].items():
        assert dokument(b, d["id"]) == dokument(a, d["id"]), name
        assert inhalt(b, d["id"]).content == x["daten"][name], f"Inhalt {name} nach der Rundreise"
    for bid in x["b"]:
        assert b.buchung_lesen(bid)["belege"] == a.buchung_lesen(bid)["belege"]
    # ID-Zähler: ein neues Dokument erhält eine größere ID als jede der Quelle (auch die gelöschte)
    neu = anhaengen(b, [x["b"][0]], "neu.pdf", pdf("neu"))
    assert neu["id"] > max(d["id"] for d in x["d"].values()) + 1
    # Rückgängig des Einspielens entfernt die Dokumente, Wiederholen bringt sie samt Inhalt zurück
    b.delete(f"/api/dokumente/{neu['id']}", erwartet=204)
    u = b.post(f"/api/aenderungen/{aenderung['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(b) == {}
    b.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(b) == quelle
    assert inhalt(b, x["d"]["mail"]["id"]).content == x["daten"]["mail"]


def test_einspielen_ersetzt_dokumente(api):
    x = _aufbau(api)
    gesichert = sicherung(api)
    vorher = bestand(api)
    pdf_id = x["d"]["pdf"]["id"]
    api.delete(f"/api/dokumente/{pdf_id}", erwartet=204)
    spaeter = anhaengen(api, [x["b"][3]], "spaeter.png", png(1, 5))
    nachher = bestand(api)
    a0 = letzte_aenderung_id(api)
    e = einspielen(api, gesichert).daten
    assert e["unterschied"]["dokument"] == {"angelegt": 1, "geaendert": 0, "geloescht": 1}
    assert bestand(api) == vorher
    assert inhalt(api, pdf_id).content == x["daten"]["pdf"], "gelöschtes Dokument samt Inhalt aus der Sicherung"
    (aenderung,) = aenderungen_seit(api, a0)
    pruefe_eintraege(aenderung, nachher, vorher)
    api.post(f"/api/aenderungen/{aenderung['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == nachher and dokument(api, spaeter["id"])["buchung_ids"] == [x["b"][3]]


def test_sicherung_ohne_dokumente_in_bestand_mit_dokumenten(tmp_path):
    """4: unterschied enthält dokument, wenn Sicherung oder Bestand eines enthält."""
    leer = neue_api(tmp_path / "leer")
    leer.konto("Girokonto")
    gesichert = sicherung(leer)
    m, _ = oeffne(gesichert)
    assert "dokument" not in m["anzahl"]
    api = neue_api(tmp_path / "voll")
    _aufbau(api)
    e = einspielen(api, gesichert, trocken=True).daten
    assert e["unterschied"]["dokument"] == {"angelegt": 0, "geaendert": 0, "geloescht": 3}
    e = einspielen(api, gesichert).daten
    assert e["geaendert"] is True
    assert all(k[0] != "dokument" for k in bestand(api))
    assert all(b["belege"] == [] for b in api.alle_buchungen())
