"""M18: Dokumente an Buchungen – Objekt, Typerkennung, Dateiname, REST, Protokoll, Rückgängig
(dokumente.md 1–3, protokoll.md 15, E-206 bis E-208).

Erwartungen kommen aus den Regeln der Spezifikation (``tests/hilfen/m18.py``: ``typ``, ``dateiname_soll``) und
aus den im Test erzeugten Bytes; nie aus Antworten der Anwendung.
"""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import mock_api, setze_zeit
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m7 import anmelden, m7_api
from tests.hilfen.m18 import (
    JPEG, MAIL, PDF, PNG, WEBP, anhaengen, belege, bestand, dateiname_soll, dokument, dokumente_der_buchung,
    eine_aenderung, fehler, inhalt, jpeg_kopf, mail, ohne_wirkung, operation, orte, pdf, png, pruefe_eintraege,
    rundreise, sha256, typ, webp_kopf, zustand,
)

pytestmark = pytest.mark.kern


@pytest.fixture
def uhr_api(tmp_path):
    """Mock-Modus mit fester App-Uhr (erstellt_am prüfbar)."""
    a = mock_api(tmp_path, heute="2024-06-30")
    setze_zeit(a, "2024-06-30T10:11:12Z")
    return a


def _buchungen(api, n: int = 3) -> tuple[dict, list[int]]:
    k = {"giro": api.konto("Girokonto")["id"], "spar": api.konto("Tagesgeld", "sparkonto")["id"],
         "leb": api.konto("Lebensmittel", "aufwand")["id"], "freizeit": api.konto("Freizeit", "aufwand")["id"]}
    ids = []
    for i in range(n):
        konto = k["giro"] if i % 2 == 0 else k["spar"]
        ids.append(api.buchung(f"2024-05-{i + 1:02d}", [(konto, -(1000 + i)), (k["leb"], 1000 + i)],
                               verwendungszweck=f"Einkauf {i}")["id"])
    return k, ids


# ------------------------------------------------------------------ Objekt und Anhängen (1.1, 1.4, 2.1)


def test_anhaengen_felder_und_belege(uhr_api):
    api = uhr_api
    _, (b1, b2, b3) = _buchungen(api)
    daten = pdf("Kassenbon")
    d = anhaengen(api, [b2, b1, b2], "Kassenbon.pdf", daten)
    assert d == {"id": d["id"], "dateiname": "Kassenbon.pdf", "mime_typ": PDF, "groesse": len(daten),
                 "sha256": sha256(daten), "quelle": "upload", "erstellt_am": "2024-06-30T10:11:12Z",
                 "buchung_ids": [b1, b2]}, "doppelte buchung_id zählen einmal, buchung_ids aufsteigend"
    assert dokument(api, d["id"]) == d
    beleg = {"id": d["id"], "dateiname": "Kassenbon.pdf", "mime_typ": PDF, "groesse": len(daten)}
    assert belege(api, b1) == [beleg] and belege(api, b2) == [beleg] and belege(api, b3) == []
    liste = {b["id"]: b["belege"] for b in api.alle_buchungen()}
    assert liste[b1] == [beleg] and liste[b3] == [], "belege auch in GET /api/buchungen"
    assert dokumente_der_buchung(api, b1) == [d] and dokumente_der_buchung(api, b3) == []
    assert inhalt(api, d["id"]).content == daten
    # zweites Dokument: belege nach id aufsteigend; gleiche Bytes → eigenes Dokument, gleiches sha256
    e = anhaengen(api, [b1], "nochmal.pdf", daten, quelle="kamera")
    assert e["id"] > d["id"] and e["sha256"] == d["sha256"] and e["quelle"] == "kamera"
    assert [x["id"] for x in belege(api, b1)] == [d["id"], e["id"]]
    assert [x["id"] for x in dokumente_der_buchung(api, b1)] == [d["id"], e["id"]]
    m = anhaengen(api, [b3], "quelle.eml", mail(), quelle="mail")
    assert (m["quelle"], m["mime_typ"]) == ("mail", MAIL)
    assert fehlercode(api.get("/api/buchungen/999999/dokumente", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.get("/api/dokumente/999999", erwartet=404)) == "nicht_gefunden"


def test_kontouebergreifend_und_ids_nie_wiederverwendet(api):
    _, (b1, b2, _) = _buchungen(api)
    d = anhaengen(api, [b1, b2], "a.png", png())
    api.delete(f"/api/dokumente/{d['id']}", erwartet=204)
    e = anhaengen(api, [b1], "b.png", png())
    assert e["id"] > d["id"], "IDs von Dokumenten werden nie wiederverwendet (dokumente.md 1.1)"


# ------------------------------------------------------------------ Typerkennung (1.2)

_MAIL_MIN = b"From: shop@example.invalid\r\nSubject: Test\r\n\r\nText\r\n"
TYPEN = [
    ("pdf", pdf(), PDF),
    ("jpeg", jpeg_kopf(), JPEG),
    ("png", png(), PNG),
    ("webp", webp_kopf(), WEBP),
    ("mail_minimal", _MAIL_MIN, MAIL),
    ("mail_gross_klein", b"FROM: a@example.invalid\nmessage-id: <x@example.invalid>\n\nx", MAIL),
    ("mail_leerzeilen_mbox", b"\r\n\nFrom shop@example.invalid Mon Jun  3 09:30:00 2024\nDate: Mon, 3 Jun 2024 "
                             b"09:30:00 +0000\nTo: b@example.invalid\n\nText", MAIL),
    ("mail_received_subject", b"Received: from x.example.invalid\nSubject: Hallo\n\n", MAIL),
    ("mail_voll", mail(), MAIL),
    ("gif", b"GIF89a\x01\x00\x01\x00\x00\x00\x00;", None),
    ("text", "Einfacher Text ohne Kopf\nzweite Zeile\n".encode(), None),
    ("ein_kopf", b"Hallo: Welt\n\nText", None),
    ("zwei_koepfe_ohne_from_subject_date", b"To: a@example.invalid\nReceived: x\n\nText", None),
    ("from_doppelt", b"From: a@example.invalid\nFrom: b@example.invalid\n\nText", None),
    ("mail_mit_nul", b"From: a@example.invalid\nSubject: x\n\nText\x00mehr", None),
    ("ausfuehrbar", b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 40, None),
    ("pdf_nicht_am_anfang", b" %PDF-1.4\n", None),
    ("riff_ohne_webp", b"RIFF\x10\x00\x00\x00WAVEfmt ", None),
]


@pytest.mark.parametrize("name,daten,soll", TYPEN, ids=[t[0] for t in TYPEN])
def test_typerkennung_nur_am_inhalt(api, name, daten, soll):
    assert typ(daten) == soll, "Testfall widerspricht der eigenen Fassung der Regel (dokumente.md 1.2)"
    _, (b1, *_) = _buchungen(api, 1)
    # Dateiname und Browsertyp passen absichtlich nicht zum Inhalt (zählen nicht)
    if soll is None:
        def aufruf():
            r = anhaengen(api, [b1], "beleg.pdf", daten, browsertyp="application/pdf", erwartet=422)
            fehler(r, "dokument_typ_unbekannt")
        ohne_wirkung(api, aufruf)
    else:
        d = anhaengen(api, [b1], "datei.gif", daten, browsertyp="image/gif")
        assert d["mime_typ"] == soll
        assert d["dateiname"] == dateiname_soll("datei.gif", soll)


# ------------------------------------------------------------------ Dateiname (1.3)

NAMEN = [
    ("../../etc/pass\x00wd", PDF, "passwd.pdf"),
    ("", JPEG, "Foto.jpg"),
    ("foto.png", JPEG, "foto.png.jpg"),
    ("Scan.JPEG", JPEG, "Scan.JPEG"),
    ("a" * 500, PDF, "a" * 196 + ".pdf"),
    ("C:\\Belege\\2024\\rechnung.PDF", PDF, "rechnung.PDF"),
    ("  ..beleg..  ", PDF, "beleg.pdf"),
    ("...", PNG, "Bild.png"),
    ("Cafe\u0301 Quittung.png", PNG, "Caf\u00e9 Quittung.png"),
    ("Kassen\u200bbon\n.webp", WEBP, "Kassenbon.webp"),
    ("x" * 250 + ".png", PNG, "x" * 196 + ".png"),
    ("y" * 210 + ".jpeg", JPEG, ("y" * 210 + ".jpeg")[:200]),
    ("nachricht", MAIL, "nachricht.eml"),
    ("ordner/", PDF, "Dokument.pdf"),
]


@pytest.mark.parametrize("name,mime,soll", NAMEN)
def test_dateiname_gesaeubert(api, name, mime, soll):
    assert dateiname_soll(name, mime) == soll, "Testfall widerspricht der eigenen Fassung von dokumente.md 1.3"
    _, (b1, *_) = _buchungen(api, 1)
    daten = {PDF: pdf(), JPEG: jpeg_kopf(), PNG: png(), WEBP: webp_kopf(), MAIL: mail()}[mime]
    steuer = any(ord(c) < 32 for c in name)
    if not steuer:
        # Upload: Dateiname des Formularfelds (roh im Kopf, E-208); eine Mail ohne Namen hieße wie ihr Betreff
        d = anhaengen(api, [b1], name, daten)
        if not (mime == MAIL and name == ""):
            assert d["dateiname"] == soll
    else:
        d = anhaengen(api, [b1], "start", daten)
    # PATCH: dieselben Regeln (dokumente.md 2.4), Typ bleibt; nur Leerraum wäre 422 (eigener Test)
    if name.strip():
        r = api.patch(f"/api/dokumente/{d['id']}", json={"dateiname": name}, erwartet=200).daten
        assert (r["dateiname"], r["mime_typ"]) == (soll, mime)
        assert 1 <= len(r["dateiname"]) <= 200


@pytest.mark.parametrize("betreff,soll", [
    ("Rechnung 4711", "Rechnung 4711.eml"),
    ("x" * 196, "x" * 196 + ".eml"),
    ("x" * 197, "x" * 196 + ".eml"),
    ("y" * 300, "y" * 196 + ".eml"),
    ("", "E-Mail.eml"),
])
def test_mail_ohne_dateinamen_heisst_wie_der_betreff(api, betreff, soll):
    """1.3 und 2.2 (E-208): Betreff auf höchstens 196 Zeichen gekürzt, leer → „E-Mail“, dann Regeln 1–5."""
    _, (b1, *_) = _buchungen(api, 1)
    assert anhaengen(api, [b1], "", mail(betreff=betreff))["dateiname"] == soll


# ------------------------------------------------------------------ Prüfreihenfolge (2.1)


def _koerper(datei: tuple | None = ("a.pdf", None, "application/pdf"), *, feld: str = "datei"):
    """Körper für 2.1: ``datei`` = (Dateiname oder None für ein einfaches Formularfeld, Bytes oder None = PDF, Typ)."""
    from tests.hilfen.m18 import multipart

    name, daten, art = datei
    return multipart([(feld, name, pdf() if daten is None else daten, art)])


PRUEF = [
    # (Fall, Query, Körper-Art, erwarteter Status, Code) – dokumente.md 2.1 Prüfreihenfolge
    ("buchung_id_keine_zahl", [("buchung_id", "abc")], "pdf", 422, "validierung"),
    ("buchung_id_dezimal", [("buchung_id", "1.5")], "pdf", 422, "validierung"),
    ("quelle_unbekannt", [("buchung_id", "B"), ("quelle", "scanner")], "pdf", 422, "validierung"),
    ("parameter_unbekannt", [("buchung_id", "B"), ("unbekannt", "1")], "pdf", 422, "validierung"),
    ("query_vor_buchung", [("buchung_id", "abc"), ("buchung_id", "999999")], "pdf", 422, "validierung"),
    ("kein_multipart", [("buchung_id", "B")], "json", 422, "validierung"),
    ("anderes_feld", [("buchung_id", "B")], "anderes_feld", 422, "validierung"),
    ("kein_dateifeld", [("buchung_id", "B")], "textfeld", 422, "validierung"),
    ("dateifeld_vor_buchung", [("buchung_id", "999999")], "textfeld", 422, "validierung"),
    ("ohne_buchung_id", [], "pdf", 422, "validierung"),
    ("buchung_vor_leer", [("buchung_id", "B"), ("buchung_id", "999999")], "leer", 404, "nicht_gefunden"),
    ("buchung_vor_typ", [("buchung_id", "999999")], "gif", 404, "nicht_gefunden"),
    ("leer", [("buchung_id", "B")], "leer", 422, "dokument_leer"),
    ("typ_unbekannt", [("buchung_id", "B")], "gif", 422, "dokument_typ_unbekannt"),
]


@pytest.mark.parametrize("fall,query,art,status,code", PRUEF, ids=[p[0] for p in PRUEF])
def test_anhaengen_pruefreihenfolge(api, fall, query, art, status, code):
    _, (b1, *_) = _buchungen(api, 1)
    params = [(k, str(b1) if v == "B" else v) for k, v in query]
    kw: dict = {}
    if art == "json":
        kw["json"] = {"datei": "x"}
    else:
        koerper, typ_ = {"pdf": lambda: _koerper(), "anderes_feld": lambda: _koerper(feld="anderes"),
                         "textfeld": lambda: _koerper((None, b"kein Dateifeld", None)),
                         "leer": lambda: _koerper(("a.pdf", b"", "application/pdf")),
                         "gif": lambda: _koerper(("a.gif", b"GIF89a", "image/gif"))}[art]()
        kw = {"content": koerper, "headers": {"Content-Type": typ_}}

    def aufruf():
        r = api.post("/api/dokumente", params=params, erwartet=status, **kw)
        fehler(r, code)
        if fall == "ohne_buchung_id":
            assert any(o[:2] == ["body", "buchung_ids"] for o in orte(r)), orte(r)
    ohne_wirkung(api, aufruf)


def test_anhaengen_groessengrenze(tmp_path):
    """dokumente.md 2.1 Nr. 1, sicherheit.md 8: POST /api/dokumente ist ein Upload-Pfad (upload_max_mib)."""
    from tests.hilfen.api import neue_api

    api = neue_api(tmp_path, upload_max_mib=1, anfrage_max_kib=64)
    _, (b1, *_) = _buchungen(api, 1)
    gross = pdf() + b"0" * (1024 * 1024 + 10)
    ohne_wirkung(api, lambda: fehler(anhaengen(api, [b1], "g.pdf", gross, erwartet=413), "datei_zu_gross"))
    ohne_wirkung(api, lambda: fehler(anhaengen(api, [999999], "g.pdf", gross, erwartet=413), "datei_zu_gross"))
    # über anfrage_max_kib, aber unter upload_max_mib: erlaubt (Upload-Pfad)
    mittel = pdf() + b"0" * (200 * 1024)
    assert anhaengen(api, [b1], "m.pdf", mittel)["groesse"] == len(mittel)


# ------------------------------------------------------------------ Umbenennen, Löschen, Verknüpfen, Lösen (2.4–2.8)


def test_umbenennen(api):
    _, (b1, *_) = _buchungen(api, 1)
    d = anhaengen(api, [b1], "alt.pdf", pdf())
    erg, a, v, n = operation(api, "dokument_umbenennen", lambda: api.patch(
        f"/api/dokumente/{d['id']}", json={"dateiname": "../Neu\u200b"}, erwartet=200).daten)
    assert erg == {**d, "dateiname": "Neu.pdf"}
    assert [e["objekt"] for e in a["eintraege"]] == ["dokument"], "Umbenennen ändert keine Buchung im Protokoll"
    assert belege(api, b1)[0]["dateiname"] == "Neu.pdf"
    rundreise(api, a, v, n)
    # gleicher gesäuberter Name → keine Änderung
    ohne_wirkung(api, lambda: api.patch(f"/api/dokumente/{d['id']}", json={"dateiname": "Neu.pdf"}, erwartet=200))
    ohne_wirkung(api, lambda: api.patch(f"/api/dokumente/{d['id']}", json={"dateiname": " Neu "}, erwartet=200))

    def falsch():
        for koerper in ({}, {"dateiname": 5}, {"dateiname": "   "}, {"dateiname": ""}, {"dateiname": None},
                        {"dateiname": "x", "mime_typ": PNG}, {"quelle": "kamera"}, ["x"]):
            fehler(api.patch(f"/api/dokumente/{d['id']}", json=koerper, erwartet=422), "validierung")
        fehler(api.patch("/api/dokumente/999999", json={"dateiname": "x"}, erwartet=404), "nicht_gefunden")
    ohne_wirkung(api, falsch)


def test_loeschen_entfernt_alle_verknuepfungen(api):
    _, (b1, b2, b3) = _buchungen(api)
    daten = png(2, 2)
    d = anhaengen(api, [b1, b3], "foto.png", daten)
    _, a, v, n = operation(api, "dokument_loeschen",
                           lambda: api.delete(f"/api/dokumente/{d['id']}", erwartet=204))
    assert {(e["objekt"], e["objekt_id"], e["art"]) for e in a["eintraege"]} == {
        ("dokument", d["id"], "geloescht"), ("buchung", b1, "geaendert"), ("buchung", b3, "geaendert")}
    assert belege(api, b1) == [] and belege(api, b3) == []
    fehler(api.get(f"/api/dokumente/{d['id']}", erwartet=404), "nicht_gefunden")
    rundreise(api, a, v, n, {d["id"]: daten})
    ohne_wirkung(api, lambda: fehler(api.delete("/api/dokumente/999999", erwartet=404), "nicht_gefunden"))
    assert b2


def test_verknuepfen(api):
    _, (b1, b2, b3) = _buchungen(api)
    daten = pdf()
    d = anhaengen(api, [b1], "a.pdf", daten)
    erg, a, v, n = operation(api, "dokument_verknuepfen", lambda: api.post(
        f"/api/dokumente/{d['id']}/buchungen", json={"buchung_ids": [b3, b1, b2, b3]}, erwartet=200).daten)
    assert erg == {**d, "buchung_ids": [b1, b2, b3]}
    assert {(e["objekt"], e["objekt_id"]) for e in a["eintraege"]} == {("buchung", b2), ("buchung", b3)}, (
        "nur neu verknüpfte Buchungen geändert, Dokument selbst unverändert")
    rundreise(api, a, v, n, {d["id"]: daten})
    ohne_wirkung(api, lambda: api.post(f"/api/dokumente/{d['id']}/buchungen", json={"buchung_ids": [b1, b2]},
                                       erwartet=200))

    def falsch():
        # Dokument unbekannt vor ungültigem Körper
        fehler(api.post("/api/dokumente/999999/buchungen", json={"x": 1}, erwartet=404), "nicht_gefunden")
        fehler(api.post(f"/api/dokumente/{d['id']}/buchungen", json={"buchung_ids": [b1, 999999]}, erwartet=404),
               "nicht_gefunden")
    ohne_wirkung(api, falsch)


@pytest.mark.parametrize("koerper", [{}, {"buchung_ids": []}, {"buchung_ids": "1"}, {"buchung_ids": ["1"]},
                                     {"buchung_ids": [True]}, {"buchung_ids": [1.0]}, {"buchung_ids": None}, [1]],
                         ids=["leer", "liste_leer", "text", "text_in_liste", "bool", "gleitkomma", "null", "liste"])
def test_verknuepfen_ungueltiger_koerper(api, koerper):
    _, (b1, b2, _) = _buchungen(api)
    d = anhaengen(api, [b1], "a.pdf", pdf())
    ohne_wirkung(api, lambda: fehler(api.post(f"/api/dokumente/{d['id']}/buchungen", json=koerper, erwartet=422),
                                     "validierung"))


def test_loesen_und_letzte_verknuepfung(api):
    _, (b1, b2, b3) = _buchungen(api)
    daten = mail(betreff="Bestellung (fiktiv)")
    d = anhaengen(api, [b1, b2], "", daten)
    erg, a, v, n = operation(api, "dokument_loesen", lambda: api.delete(
        f"/api/dokumente/{d['id']}/buchungen/{b1}", erwartet=200).daten)
    assert erg == {"dokument_id": d["id"], "buchung_ids": [b2], "geloescht": False}
    assert [(e["objekt"], e["objekt_id"]) for e in a["eintraege"]] == [("buchung", b1)]
    assert dokument(api, d["id"])["buchung_ids"] == [b2]
    rundreise(api, a, v, n, {d["id"]: daten})
    ohne_wirkung(api, lambda: fehler(api.delete(f"/api/dokumente/{d['id']}/buchungen/{b3}", erwartet=404),
                                     "nicht_gefunden"))
    ohne_wirkung(api, lambda: fehler(api.delete(f"/api/dokumente/999999/buchungen/{b1}", erwartet=404),
                                     "nicht_gefunden"))
    erg, a, v, n = operation(api, "dokument_loesen", lambda: api.delete(
        f"/api/dokumente/{d['id']}/buchungen/{b2}", erwartet=200).daten)
    assert erg == {"dokument_id": d["id"], "buchung_ids": [], "geloescht": True}
    assert {(e["objekt"], e["art"]) for e in a["eintraege"]} == {("buchung", "geaendert"), ("dokument", "geloescht")}
    fehler(api.get(f"/api/dokumente/{d['id']}", erwartet=404), "nicht_gefunden")
    fehler(api.get(f"/api/dokumente/{d['id']}/inhalt", erwartet=404), "nicht_gefunden")
    # Rückgängig nach geloescht = true: dieselbe ID, derselbe Inhalt
    rundreise(api, a, v, n, {d["id"]: daten})


# ------------------------------------------------------------------ Protokoll (3)


def test_anhaengen_protokoll_und_rueckgaengig(uhr_api):
    api = uhr_api
    _, (b1, b2, _) = _buchungen(api)
    daten = pdf("Rechnung")
    d, a, v, n = operation(api, "dokument_anhaengen", lambda: anhaengen(api, [b1, b2], "r.pdf", daten))
    assert n[("dokument", d["id"])] == zustand(d)
    assert n[("buchung", b1)]["dokument_ids"] == [d["id"]]
    assert {(e["objekt"], e["objekt_id"], e["art"]) for e in a["eintraege"]} == {
        ("dokument", d["id"], "angelegt"), ("buchung", b1, "geaendert"), ("buchung", b2, "geaendert")}
    roh = next(e for e in a["eintraege"] if e["objekt"] == "buchung" and e["objekt_id"] == b1)
    assert "dokument_ids" not in roh["vorher"], "ohne Dokumente ist die Form unverändert gegenüber M17 (3.1)"
    assert roh["nachher"]["dokument_ids"] == [d["id"]]
    # Rückgängig entfernt Dokument und Verknüpfungen; Wiederholen stellt dieselbe ID und denselben Inhalt her
    rundreise(api, a, v, n, {d["id"]: daten})


def test_ohne_dokumente_keine_dokument_ids(api):
    """3.1: Buchungen ohne Dokument tragen in jedem Eintrag kein Feld dokument_ids."""
    k, (b1, *_) = _buchungen(api, 1)
    api.put(f"/api/buchungen/{b1}/kategorie", json={"kategorie_id": k["freizeit"]}, erwartet=200)
    for a in aenderungen_seit(api, 0):
        for e in a["eintraege"]:
            if e["objekt"] == "buchung":
                for form in (e["vorher"], e["nachher"]):
                    assert form is None or "dokument_ids" not in form, (a["aktion"], form)


def test_andere_aenderung_laesst_dokument_ids(api):
    k, (b1, *_) = _buchungen(api, 1)
    d = anhaengen(api, [b1], "a.pdf", pdf())
    _, a, _, _ = operation(api, "kategorie_setzen", lambda: api.put(
        f"/api/buchungen/{b1}/kategorie", json={"kategorie_id": k["freizeit"]}, erwartet=200))
    (e,) = a["eintraege"]
    assert e["vorher"]["dokument_ids"] == e["nachher"]["dokument_ids"] == [d["id"]]
    _, a, _, _ = operation(api, "buchung_aendern", lambda: api.patch(
        f"/api/buchungen/{b1}", json={"verwendungszweck": "geändert"}, erwartet=200))
    assert a["eintraege"][0]["nachher"]["dokument_ids"] == [d["id"]]


def test_buchung_loeschen_entfernt_dokumente_ohne_weitere_buchung(api):
    _, (b1, b2, b3) = _buchungen(api)
    nur, geteilt = pdf("nur b1"), png(3, 1)
    d1 = anhaengen(api, [b1], "nur.pdf", nur)
    d2 = anhaengen(api, [b1, b2], "geteilt.png", geteilt)
    _, a, v, n = operation(api, "buchung_loeschen", lambda: api.delete(f"/api/buchungen/{b1}", erwartet=204))
    assert {(e["objekt"], e["objekt_id"], e["art"]) for e in a["eintraege"]} == {
        ("buchung", b1, "geloescht"), ("dokument", d1["id"], "geloescht")}, (
        "Dokument ohne weitere Buchung entfällt in derselben Änderung; das geteilte bleibt (Buchung b2 unverändert)")
    assert v[("buchung", b1)]["dokument_ids"] == [d1["id"], d2["id"]], "vorher-Form enthält dokument_ids"
    assert dokument(api, d2["id"])["buchung_ids"] == [b2]
    fehler(api.get(f"/api/dokumente/{d1['id']}", erwartet=404), "nicht_gefunden")
    rundreise(api, a, v, n, {d1["id"]: nur, d2["id"]: geteilt})
    # Mehrfachlöschen (M15) ebenso in einer Änderung
    d3 = anhaengen(api, [b3], "drei.pdf", pdf("drei"))
    _, a, v, n = operation(api, "mehrfach_loeschen", lambda: api.post(
        "/api/buchungen/mehrfach/loeschen", json={"buchung_ids": [b2, b3]}, erwartet=200))
    assert {(e["objekt"], e["objekt_id"]) for e in a["eintraege"] if e["objekt"] == "dokument"} == {
        ("dokument", d2["id"]), ("dokument", d3["id"])}
    rundreise(api, a, v, n, {d2["id"]: geteilt, d3["id"]: pdf("drei")})


def test_konto_mit_buchungen_loeschen_entfernt_dokumente(api):
    k, (b1, b2, _) = _buchungen(api)
    d = anhaengen(api, [b1], "a.pdf", pdf())
    e = anhaengen(api, [b2], "b.pdf", pdf("b"))
    _, a, v, n = operation(api, "konto_loeschen_mit_buchungen", lambda: api.post(
        f"/api/konten/{k['giro']}/loeschen", json={"buchungen": "loeschen", "konflikte": "loeschen"}, erwartet=200))
    assert ("dokument", d["id"]) in v and ("dokument", d["id"]) not in n
    assert ("dokument", e["id"]) in n, "Dokument einer Buchung des anderen Kontos bleibt"
    rundreise(api, a, v, n, {d["id"]: pdf()})


def test_rueckgaengig_konflikt_bei_spaeterer_verknuepfung(api):
    """3.3: Rückgängig von dokument_anhaengen → 409 rueckgaengig_konflikt, wenn das Dokument inzwischen an einer
    Buchung hängt, die nicht Teil der Änderung ist."""
    _, (b1, b2, _) = _buchungen(api)
    a0 = letzte_aenderung_id(api)
    d = anhaengen(api, [b1], "a.pdf", pdf())
    a = eine_aenderung(api, a0, "dokument_anhaengen")
    api.post(f"/api/dokumente/{d['id']}/buchungen", json={"buchung_ids": [b2]}, erwartet=200)
    ohne_wirkung(api, lambda: fehler(api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=409),
                                     "rueckgaengig_konflikt"))
    # nach Lösen von b2 ist Rückgängig wieder möglich
    api.delete(f"/api/dokumente/{d['id']}/buchungen/{b2}", erwartet=200)
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    fehler(api.get(f"/api/dokumente/{d['id']}", erwartet=404), "nicht_gefunden")
    assert belege(api, b1) == []


def test_rueckgaengig_buchungsloeschen_stellt_inhalt_her(api):
    """3.3: Inhalte werden durch keine Operation gelöscht; nach Rückgängig liefert …/inhalt dieselben Bytes."""
    _, (b1, *_) = _buchungen(api, 1)
    daten = mail(betreff="Quittung", anhaenge=[("q.pdf", PDF, pdf("q"))])
    d = anhaengen(api, [b1], "q.eml", daten)
    a0 = letzte_aenderung_id(api)
    api.delete(f"/api/buchungen/{b1}", erwartet=204)
    (a,) = aenderungen_seit(api, a0)
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert dokument(api, d["id"]) == d
    r = api.get(f"/api/dokumente/{d['id']}/inhalt", erwartet=200)
    assert r.content == daten


def test_pruefe_eintraege_ohne_dokumente_gleich_m6(api):
    """E-207: Ohne Dokumente ist der Bestand dieser Hilfe genau der aus M6."""
    from tests.hilfen.m6 import bestand as bestand_m6

    _buchungen(api)
    assert bestand(api) == bestand_m6(api)
    a0 = letzte_aenderung_id(api)
    v = bestand(api)
    api.konto("Noch eins", "aufwand")
    pruefe_eintraege(eine_aenderung(api, a0, "konto_anlegen"), v, bestand(api))


# ------------------------------------------------------------------ Schutz (2, sicherheit.md 3.2, 4.6)


def test_geschuetzt(tmp_path):
    api = m7_api(tmp_path)
    for methode, pfad, kw in [
        ("POST", "/api/dokumente?buchung_id=1", {"files": {"datei": ("a.pdf", pdf(), "application/pdf")}}),
        ("POST", "/api/dokumente/aus-mail", {"json": {"nachricht_id": 1, "buchung_ids": [1]}}),
        ("GET", "/api/dokumente/1", {}), ("PATCH", "/api/dokumente/1", {"json": {"dateiname": "x"}}),
        ("DELETE", "/api/dokumente/1", {}), ("POST", "/api/dokumente/1/buchungen", {"json": {"buchung_ids": [1]}}),
        ("DELETE", "/api/dokumente/1/buchungen/1", {}), ("GET", "/api/buchungen/1/dokumente", {}),
        ("GET", "/api/dokumente/1/inhalt", {}), ("GET", "/api/dokumente/1/mail", {}),
        ("GET", "/api/dokumente/1/mail/html", {}), ("GET", "/api/dokumente/1/mail/anhaenge/1", {}),
    ]:
        r = api.anfrage(methode, pfad, erwartet=401, **kw)
        assert fehlercode(r) == "nicht_angemeldet", (methode, pfad)
    anmelden(api)
    _, (b1, *_) = _buchungen(api, 1)
    csrf, api.csrf = api.csrf, None
    r = api.post(f"/api/dokumente?buchung_id={b1}", files={"datei": ("a.pdf", pdf(), "application/pdf")},
                 erwartet=403)
    assert fehlercode(r) == "csrf_ungueltig"
    api.csrf = csrf
    assert belege(api, b1) == [], "abgelehnte Anfrage ohne Wirkung"
    assert anhaengen(api, [b1], "a.pdf", pdf())["buchung_ids"] == [b1]
