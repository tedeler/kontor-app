"""Eigene Entwicklungstests zum Feature „betragsfilter-wiederkehrend“ (D-137): Einträge desselben Empfängers mit
anderem Betrag (z. B. Auslagenerstattungen neben dem Gehalt) brechen die Kette nicht. Toleranz (Vorgabe ±10 %) oder
Mindestschwelle je Empfänger. Alle Beträge sind synthetisch."""

from __future__ import annotations

import pytest

GEHALT = 312_345  # 3.123,45 €


@pytest.fixture
def bb(client):
    g = client.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = client.post("/api/konten", json={"name": "Lohn", "art": "ertrag"}).json()["id"]
    e = client.post("/api/empfaenger", json={"name": "Beispiel GmbH"}).json()["id"]

    def buchen(datum, betrag=GEHALT, empf=e):
        r = client.post("/api/buchungen", json={"datum": datum, "empfaenger_id": empf,
                                                "splits": [{"konto_id": g, "betrag": betrag},
                                                           {"konto_id": kat, "betrag": -betrag}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    return client, buchen, e


def serien(client, stichtag):
    return client.get("/api/wiederkehrend", params={"stichtag": stichtag}).json()["serien"]


def warum(client, bid, stichtag):
    r = client.get(f"/api/buchungen/{bid}/wiederkehrend", params={"stichtag": stichtag})
    assert r.status_code == 200, r.text
    return r.json()


def _gehalt_mit_auslagen(buchen):
    gehalt = [buchen(t) for t in ("2024-01-30", "2024-02-29", "2024-03-28", "2024-04-30")]
    auslagen = [buchen("2024-02-12", 4_250), buchen("2024-03-15", 18_990), buchen("2024-05-10", 2_300)]
    return gehalt, auslagen


def test_ohne_filter_brechen_auslagen_die_kette(bb):
    c, buchen, _ = bb
    assert c.put("/api/wiederkehrend/einstellungen/vorgabe", json={"modus": "aus"}).status_code == 200
    _gehalt_mit_auslagen(buchen)
    assert serien(c, "2024-05-15") == []


def test_toleranz_vorgabe_uebergeht_auslagen(bb):
    c, buchen, _ = bb
    gehalt, auslagen = _gehalt_mit_auslagen(buchen)
    (s,) = serien(c, "2024-05-15")
    assert s["buchung_ids"] == gehalt and s["betrag"] == GEHALT and s["rhythmus"] == "monatlich"
    w = warum(c, auslagen[-1], "2024-05-15")  # jüngste Buchung ist eine Auslage – verdrängt das Gehalt nicht
    (e,) = w["eintraege"]
    assert e["urteil"] == "anderer_betrag" and w["urteil"] == "nicht_wiederkehrend"
    assert e["betragsfilter"] == {"modus": "toleranz", "toleranz_prozent": 10, "mindestbetrag": None,
                                  "quelle": "vorgabe"}
    rollen = {b["buchung_id"]: b["rolle"] for b in e["buchungen"]}
    assert all(rollen[a] == "anderer_betrag" for a in auslagen)
    assert all(rollen[g] == "glied" for g in gehalt)


def test_gehaltserhoehung_innerhalb_der_toleranz(bb):
    c, buchen, _ = bb
    ids = [buchen("2024-01-30"), buchen("2024-02-29"), buchen("2024-03-28", GEHALT + 9_000)]
    (s,) = serien(c, "2024-03-31")
    assert s["buchung_ids"] == ids and s["betrag"] == GEHALT + 9_000


def test_mindestschwelle_je_empfaenger(bb):
    c, buchen, e = bb
    r = c.put(f"/api/empfaenger/{e}/wiederkehrend", json={"modus": "mindestschwelle", "mindestbetrag": 250_000})
    assert r.status_code == 200, r.text
    # Gehalt mit Sonderzahlung (fast doppelt): Toleranz würde brechen, die Mindestschwelle nicht.
    ids = [buchen("2024-10-30"), buchen("2024-11-29", 2 * GEHALT - 1_000), buchen("2024-12-30")]
    buchen("2024-12-10", 9_999)
    (s,) = serien(c, "2025-01-05")
    assert s["buchung_ids"] == ids
    w = warum(c, ids[0], "2025-01-05")
    assert w["eintraege"][0]["betragsfilter"]["quelle"] == "empfaenger"
    # Einstellung entfernen → Vorgabe (Toleranz) → Sonderzahlung passt nicht, Kette nur noch 1 Glied
    assert c.delete(f"/api/empfaenger/{e}/wiederkehrend").status_code == 204
    assert serien(c, "2025-01-05") == []


def test_geaenderter_betrag_nicht_bei_auslage(bb):
    """Mit Mindestschwelle meldet eine kleine Zahlung am Termin keinen geänderten Betrag; mit Toleranz schon (eine
    Preisänderung außerhalb der Toleranz soll gemeldet werden)."""
    c, buchen, e = bb
    c.put(f"/api/empfaenger/{e}/wiederkehrend", json={"modus": "mindestschwelle", "mindestbetrag": 250_000})
    for t in ("2024-01-30", "2024-02-29", "2024-03-28"):
        buchen(t)
    auslage = buchen("2024-04-27", 5_000)  # am Fälligkeitstermin, unter der Mindestschwelle
    erhoehung = buchen("2024-04-30", GEHALT + 5_000)
    r = c.post("/api/wiederkehrend/pruefen", json={"buchung_ids": [auslage, erhoehung]})
    arten = [(b["art"], b["link"]) for b in r.json()["benachrichtigungen"]]
    assert ("wiederkehrend_betrag", f"/buchungen/{erhoehung}") in arten
    assert ("wiederkehrend_betrag", f"/buchungen/{auslage}") not in arten


def test_einstellungen_lesen_und_pruefen(bb):
    c, _, e = bb
    assert c.get("/api/wiederkehrend/einstellungen").json() == {
        "vorgabe": {"modus": "toleranz", "toleranz_prozent": 10}, "empfaenger": []}
    for koerper in ({"modus": "mindestschwelle", "mindestbetrag": 100}, {"modus": "toleranz"},
                    {"modus": "toleranz", "toleranz_prozent": 101}, {"modus": "aus", "toleranz_prozent": 5}):
        assert c.put("/api/wiederkehrend/einstellungen/vorgabe", json=koerper).status_code == 422, koerper
    for koerper in ({"modus": "mindestschwelle"}, {"modus": "mindestschwelle", "mindestbetrag": 0},
                    {"modus": "toleranz", "toleranz_prozent": 5, "mindestbetrag": 1}, {"modus": "egal"}):
        assert c.put(f"/api/empfaenger/{e}/wiederkehrend", json=koerper).status_code == 422, koerper
    assert c.put("/api/empfaenger/999999/wiederkehrend", json={"modus": "aus"}).status_code == 404
    assert c.delete(f"/api/empfaenger/{e}/wiederkehrend").status_code == 404
    assert c.put("/api/wiederkehrend/einstellungen/vorgabe",
                 json={"modus": "toleranz", "toleranz_prozent": 15}).json() == {"modus": "toleranz",
                                                                               "toleranz_prozent": 15}
    c.put(f"/api/empfaenger/{e}/wiederkehrend", json={"modus": "toleranz", "toleranz_prozent": 3})
    d = c.get("/api/wiederkehrend/einstellungen").json()
    assert d["vorgabe"]["toleranz_prozent"] == 15
    assert d["empfaenger"] == [{"empfaenger": {"id": e, "name": "Beispiel GmbH"}, "modus": "toleranz",
                                "toleranz_prozent": 3, "mindestbetrag": None}]


def test_empfaenger_einstellung_rueckgaengig_und_sicherung(bb):
    c, _, e = bb
    c.put(f"/api/empfaenger/{e}/wiederkehrend", json={"modus": "mindestschwelle", "mindestbetrag": 100_000})
    c.put(f"/api/empfaenger/{e}/wiederkehrend", json={"modus": "aus"})
    a = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert a["aktion"] == "wiederkehrend_filter_setzen"
    r = c.post(f"/api/aenderungen/{a['id']}/rueckgaengig")
    assert r.status_code == 200, r.text
    (x,) = c.get("/api/wiederkehrend/einstellungen").json()["empfaenger"]
    assert x["modus"] == "mindestschwelle" and x["mindestbetrag"] == 100_000
    # Sicherung enthält die Einstellung und lässt sich probeweise einspielen
    roh = c.get("/api/sicherung").content
    c.delete(f"/api/empfaenger/{e}/wiederkehrend")
    r = c.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
               files={"datei": ("s.zip", roh, "application/zip")})
    assert r.status_code == 200, r.text
    (x,) = c.get("/api/wiederkehrend/einstellungen").json()["empfaenger"]
    assert x["mindestbetrag"] == 100_000


def test_preisaenderung_ohne_uebergangene_zahlungen_bleibt_moeglich(bb):
    """Abo-Preis steigt um mehr als die Toleranz: Ohne Zahlungen dazwischen hält die Kette (wie bisher)."""
    c, buchen, _ = bb
    ids = [buchen(t, -1_299) for t in ("2024-01-15", "2024-02-15", "2024-03-15")] + [buchen("2024-04-15", -1_799)]
    (s,) = serien(c, "2024-04-30")
    assert s["buchung_ids"] == ids and s["betrag"] == -1_799


def test_zufallsbetraege_mit_luecken_ergeben_keine_serie(bb):
    """Übergehen setzt passende Beträge voraus: Monatliche Termine mit zufälligen Beträgen und Zahlungen dazwischen
    sind keine Serie (Bruch mit Grund ``betrag`` oder ``fremde_zahlung``)."""
    c, buchen, _ = bb
    for t, b in (("2024-01-10", -205), ("2024-01-25", -1_400), ("2024-02-10", -834), ("2024-02-24", -77),
                 ("2024-03-11", -1_505), ("2024-03-27", -310), ("2024-04-10", -281)):
        buchen(t, b)
    assert serien(c, "2024-04-30") == []


def test_mehrheitsregel_der_vorgabe(bb):
    """Vorgabe-Toleranz: Übergeht die Kette mehr Zahlungen, als sie Glieder hat, ist sie keine Serie; mit eigener
    Einstellung des Empfängers gilt die Regel nicht."""
    c, buchen, e = bb
    for t in ("2024-01-30", "2024-02-29", "2024-03-28"):
        buchen(t)
    for t in ("2024-02-05", "2024-02-12", "2024-02-19", "2024-03-05", "2024-03-12"):
        buchen(t, 1_000)
    assert serien(c, "2024-04-10") == []
    c.put(f"/api/empfaenger/{e}/wiederkehrend", json={"modus": "toleranz", "toleranz_prozent": 10})
    assert len(serien(c, "2024-04-10")) == 1
