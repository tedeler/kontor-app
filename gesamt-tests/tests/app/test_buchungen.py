"""Buchungen, Splits, Status, Sperre, Kategorie und Betrag (datenmodell.md 3 und 4, T 4)."""

from __future__ import annotations

import itertools

import pytest

from tests.hilfen.api import fehlercode

STATUS = ["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"]
UEBERGAENGE = {("importiert", "bestaetigt"), ("bestaetigt", "abgeglichen"), ("vorlaeufig", "abgeglichen")}


@pytest.fixture
def k(api):
    """Ein kleiner Kontenrahmen."""
    return {
        "giro": api.konto("Giro")["id"],
        "spar": api.konto("Spar", "sparkonto")["id"],
        "kk": api.konto("Karte", "kreditkonto")["id"],
        "leb": api.konto("Lebensmittel", "aufwand")["id"],
        "cafe": api.konto("Café", "aufwand")["id"],
        "geh": api.konto("Gehalt", "ertrag")["id"],
        "ek": api.konto("Anfang", "eigenkapital")["id"],
    }


def _body(datum, splits, **felder):
    return {"datum": datum, "splits": [{"konto_id": s[0], "betrag": s[1], **({"memo": s[2]} if len(s) > 2 else {})}
                                       for s in splits], **felder}


# ---------------------------------------------------------------- Anlegen


def test_buchung_anlegen_vorgaben(api, k):
    b = api.buchung("2024-02-29", [(k["giro"], -1234), (k["leb"], 1234)])
    assert b["datum"] == "2024-02-29" and b["empfaenger"] is None and b["verwendungszweck"] == ""
    assert b["status"] == "bestaetigt" and b["tags"] == [] and b["extern_ids"] == [] and b["belege"] == []
    assert [(s["konto_id"], s["betrag"], s["memo"]) for s in b["splits"]] == [(k["giro"], -1234, ""), (k["leb"], 1234, "")]
    assert len({s["id"] for s in b["splits"]}) == 2
    assert b["kategorie_id"] == k["leb"] and b["betrag"] == 1234
    assert api.buchung_lesen(b["id"]) == b


def test_buchung_alle_felder(api, k):
    e = api.empfaenger("Supermarkt")
    t = api.tag("Haushalt")
    text = "Einkauf „Ölfass“ <b>&amp;</b>\nZeile 2 – ☃ " + "x" * 9000
    b = api.buchung("2024-01-05", [(k["giro"], -5000, "Memo Giro"), (k["leb"], 4000, "Lebensmittel"),
                                   (k["cafe"], 1000, "Kaffee")],
                    empfaenger_id=e["id"], verwendungszweck=text, status="vorlaeufig", tag_ids=[t["id"]])
    assert b["empfaenger"] == {"id": e["id"], "name": "Supermarkt"}
    assert b["verwendungszweck"] == text and b["status"] == "vorlaeufig"
    assert [s["memo"] for s in b["splits"]] == ["Memo Giro", "Lebensmittel", "Kaffee"]
    assert b["tags"] == [{"id": t["id"], "name": "Haushalt"}]


def test_reihenfolge_der_splits_bleibt(api, k):
    reihen = [(k["leb"], 300), (k["giro"], -1000), (k["cafe"], 200), (k["spar"], 500)]
    b = api.buchung("2024-01-01", reihen)
    assert [(s["konto_id"], s["betrag"]) for s in b["splits"]] == reihen
    assert [(s["konto_id"], s["betrag"]) for s in api.buchung_lesen(b["id"])["splits"]] == reihen


@pytest.mark.kern
@pytest.mark.parametrize("splits,code", [
    ([], "zu_wenige_splits"),
    ([("giro", 0)], "zu_wenige_splits"),
    ([("giro", -100)], "zu_wenige_splits"),
    ([("giro", -100), ("leb", 99)], "buchung_unausgeglichen"),
    ([("giro", -100), ("leb", 101)], "buchung_unausgeglichen"),
    ([("giro", -100), ("leb", 50), ("cafe", 49)], "buchung_unausgeglichen"),
    ([("giro", 1), ("leb", 1)], "buchung_unausgeglichen"),
], ids=["keine", "ein_nullsplit", "ein_split", "ein_cent_zu_wenig", "ein_cent_zu_viel", "drei_splits", "gleich"])
def test_ungueltige_splits_abgelehnt(api, k, splits, code):
    r = api.post("/api/buchungen", json=_body("2024-01-01", [(k[a], b) for a, b in splits]), erwartet=422)
    assert fehlercode(r) == code
    assert api.alle_buchungen() == []
    assert all(s["saldo"] == 0 for s in api.salden().values())


def test_nullsplits_zulaessig(api, k):
    b = api.buchung("2024-01-01", [(k["giro"], 0), (k["leb"], 0)])
    assert b["betrag"] == 0 and [s["betrag"] for s in b["splits"]] == [0, 0]
    b = api.buchung("2024-01-01", [(k["giro"], -500), (k["leb"], 500), (k["cafe"], 0)])
    assert len(b["splits"]) == 3


@pytest.mark.parametrize("feld,wert", [
    ("konto_id", 4711), ("empfaenger_id", 4711), ("tag_ids", [4711]),
])
def test_unbekannte_referenzen(api, k, feld, wert):
    body = _body("2024-01-01", [(k["giro"], -1), (k["leb"], 1)])
    if feld == "konto_id":
        body["splits"][1]["konto_id"] = wert
    else:
        body[feld] = wert
    assert fehlercode(api.post("/api/buchungen", json=body, erwartet=422)) == "referenz_unbekannt"
    assert api.alle_buchungen() == []


@pytest.mark.parametrize("aenderung", [
    {"status": "abgeglichen"}, {"status": "storniert"}, {"datum": "2024-02-30"}, {"datum": "2024-1-1"},
    {"datum": None}, {"verwendungszweck": "x" * 10001}, {"extern_ids": ["kmy:T1"]}, {"belege": []},
    {"kategorie_id": None}, {"splits": "keine"},
], ids=lambda a: next(iter(a)) + "=" + str(next(iter(a.values())))[:12])
def test_anlegen_validierung(api, k, aenderung):
    body = {**_body("2024-01-01", [(k["giro"], -1), (k["leb"], 1)]), **aenderung}
    assert fehlercode(api.post("/api/buchungen", json=body, erwartet=422)) == "validierung"
    assert api.alle_buchungen() == []


def test_split_memo_zu_lang(api, k):
    body = _body("2024-01-01", [(k["giro"], -1, "m" * 10001), (k["leb"], 1)])
    assert fehlercode(api.post("/api/buchungen", json=body, erwartet=422)) == "validierung"
    body = _body("2024-01-01", [(k["giro"], -1, "m" * 10000), (k["leb"], 1)])
    api.post("/api/buchungen", json=body, erwartet=201)


def test_ids_steigend_nie_wiederverwendet(api, k):
    a = api.buchung("2024-01-01", [(k["giro"], -1), (k["leb"], 1)])
    b = api.buchung("2023-01-01", [(k["giro"], -1), (k["leb"], 1)])
    assert b["id"] > a["id"]
    assert min(s["id"] for s in b["splits"]) > max(s["id"] for s in a["splits"])
    api.delete(f"/api/buchungen/{b['id']}", erwartet=204)
    c = api.buchung("2024-01-01", [(k["giro"], -1), (k["leb"], 1)])
    assert c["id"] > b["id"]
    assert min(s["id"] for s in c["splits"]) > max(s["id"] for s in b["splits"])


# --------------------------------------------------------------- Kategorie


@pytest.mark.parametrize("splits,kategorie", [
    ([("giro", -100), ("leb", 100)], "leb"),
    ([("giro", 100), ("geh", -100)], "geh"),
    ([("giro", -100), ("spar", 100)], None),                       # Umbuchung
    ([("giro", -100), ("leb", 60), ("cafe", 40)], None),           # Splitbuchung
    ([("giro", -100), ("ek", 100)], None),                         # Eigenkapital ist keine Kategorie
    ([("giro", -100), ("spar", 50), ("leb", 50)], "leb"),          # genau ein Gegensplit
    ([("leb", 100), ("cafe", -100)], None),                        # zwei Gegensplits
    ([("giro", -100), ("leb", 100), ("leb", 0)], None),            # zwei Gegensplits, gleiches Konto
    ([("kk", -100), ("cafe", 100)], "cafe"),
], ids=["aufwand", "ertrag", "umbuchung", "split", "eigenkapital", "ein_gegensplit", "nur_kategorien",
        "zwei_auf_gleicher", "kreditkarte"])
def test_kategorie_abgeleitet(api, k, splits, kategorie):
    b = api.buchung("2024-01-01", [(k[a], x) for a, x in splits])
    assert b["kategorie_id"] == (k[kategorie] if kategorie else None)


def test_kategorie_setzen(api, k):
    t = api.tag("T")
    e = api.empfaenger("E")
    b = api.buchung("2024-01-01", [(k["giro"], -100, "m1"), (k["ek"], 100, "m2")], tag_ids=[t["id"]],
                    empfaenger_id=e["id"], verwendungszweck="vz", status="importiert")
    assert b["kategorie_id"] is None
    r = api.put(f"/api/buchungen/{b['id']}/kategorie", json={"kategorie_id": k["leb"]}, erwartet=200).daten
    erwartet = dict(b)
    erwartet["splits"] = [b["splits"][0], {**b["splits"][1], "konto_id": k["leb"]}]
    erwartet["kategorie_id"] = k["leb"]
    assert r == erwartet
    assert api.buchung_lesen(b["id"]) == erwartet
    r = api.put(f"/api/buchungen/{b['id']}/kategorie", json={"kategorie_id": k["geh"]}, erwartet=200).daten
    assert r["kategorie_id"] == k["geh"] and r["splits"][1]["id"] == b["splits"][1]["id"]
    s = api.salden()
    assert (s[k["ek"]]["saldo"], s[k["leb"]]["saldo"], s[k["geh"]]["saldo"]) == (0, 0, 100)


def test_kategorie_setzen_fehler(api, k):
    umb = api.buchung("2024-01-01", [(k["giro"], -100), (k["spar"], 100)])
    spl = api.buchung("2024-01-01", [(k["giro"], -100), (k["leb"], 60), (k["cafe"], 40)])
    ok = api.buchung("2024-01-01", [(k["giro"], -100), (k["leb"], 100)])
    for b in (umb, spl):
        r = api.put(f"/api/buchungen/{b['id']}/kategorie", json={"kategorie_id": k["cafe"]}, erwartet=422)
        assert fehlercode(r) == "nicht_kategorisierbar"
        assert api.buchung_lesen(b["id"]) == b
    # D-242: Ein Bestandskonto ist als Ziel zulässig (Umbuchung, eigene Tests in tests/test_umbuchung_zuordnen_eigen.py);
    # ungültig bleiben das eigene Konto der Buchung und Konten, die weder Kategorie noch Bestandskonto sind.
    for ziel, code in (("giro", "konto_ungueltig"), ("ek", "kategorie_ungueltig")):
        r = api.put(f"/api/buchungen/{ok['id']}/kategorie", json={"kategorie_id": k[ziel]}, erwartet=422)
        assert fehlercode(r) == code
    r = api.put(f"/api/buchungen/{ok['id']}/kategorie", json={"kategorie_id": 4711}, erwartet=422)
    assert fehlercode(r) == "kategorie_ungueltig"
    assert fehlercode(api.put(f"/api/buchungen/{ok['id']}/kategorie", json={}, erwartet=422)) == "validierung"
    assert api.buchung_lesen(ok["id"]) == ok


# ------------------------------------------------------------------ Betrag


def test_betrag_umsatz_und_kontosicht(api, k):
    b = api.buchung("2024-01-01", [(k["giro"], -1000), (k["leb"], 600), (k["cafe"], 300), (k["spar"], 100)])
    assert b["betrag"] == 1000
    assert api.buchung_lesen(b["id"])["betrag"] == 1000
    for konto, erwartet in (("giro", -1000), ("leb", 600), ("spar", 100)):
        seite = api.seite(konto_id=k[konto])
        assert [e["betrag"] for e in seite["eintraege"]] == [erwartet]
        assert seite["summe"] == erwartet
    g = api.buchung("2024-01-02", [(k["giro"], 300), (k["giro"], -100), (k["geh"], -200)])
    assert g["betrag"] == 300
    assert {e["id"]: e["betrag"] for e in api.seite(konto_id=k["giro"])["eintraege"]} == {b["id"]: -1000, g["id"]: 200}


# ------------------------------------------------------------ Statuswechsel


def _mit_status(api, k, status):
    if status == "abgeglichen":
        b = api.buchung("2024-01-01", [(k["giro"], -100), (k["leb"], 100)], status="bestaetigt")
        return api.patch(f"/api/buchungen/{b['id']}", json={"status": "abgeglichen"}, erwartet=200).daten
    return api.buchung("2024-01-01", [(k["giro"], -100), (k["leb"], 100)], status=status)


@pytest.mark.parametrize("von,nach", list(itertools.product(STATUS, STATUS)))
def test_statusuebergaenge(api, k, von, nach):
    b = _mit_status(api, k, von)
    assert b["status"] == von
    r = api.patch(f"/api/buchungen/{b['id']}", json={"status": nach})
    if von == nach or (von, nach) in UEBERGAENGE:
        assert r.status_code == 200, r.text
        assert r.daten == {**b, "status": nach}
    else:
        assert r.status_code == 409 and fehlercode(r) == "status_uebergang_unzulaessig", r.text
        assert api.buchung_lesen(b["id"]) == b


def test_statuskette(api, k):
    b = _mit_status(api, k, "importiert")
    for s in ("bestaetigt", "abgeglichen"):
        assert api.patch(f"/api/buchungen/{b['id']}", json={"status": s}, erwartet=200).daten["status"] == s
    b = _mit_status(api, k, "vorlaeufig")
    assert api.patch(f"/api/buchungen/{b['id']}", json={"status": "abgeglichen"}, erwartet=200).daten["status"] == \
        "abgeglichen"


# --------------------------------------------------------------- Sperre


@pytest.mark.parametrize("aenderung", [
    {"datum": "2024-05-05"}, {"verwendungszweck": "neu"}, {"empfaenger_id": "E"}, {"empfaenger_id": None},
    {"datum": "2024-05-05", "status": "abgeglichen"},
], ids=["datum", "verwendungszweck", "empfaenger", "empfaenger_null", "mit_status"])
def test_abgeglichen_gesperrt_patch(api, k, aenderung):
    e = api.empfaenger("E")
    andere = api.empfaenger("Anderer")
    b = api.buchung("2024-01-01", [(k["giro"], -100), (k["leb"], 100)], status="bestaetigt", empfaenger_id=e["id"])
    b = api.patch(f"/api/buchungen/{b['id']}", json={"status": "abgeglichen"}, erwartet=200).daten
    if aenderung.get("empfaenger_id") == "E":
        aenderung = {"empfaenger_id": andere["id"]}
    r = api.patch(f"/api/buchungen/{b['id']}", json=aenderung, erwartet=409)
    assert fehlercode(r) == "buchung_gesperrt"
    assert api.buchung_lesen(b["id"]) == b


def test_abgeglichen_gesperrt_splits_kategorie_loeschen(api, k):
    b = _mit_status(api, k, "abgeglichen")
    r = api.put(f"/api/buchungen/{b['id']}/splits", json={"splits": [{"konto_id": k["giro"], "betrag": -5},
                                                                    {"konto_id": k["leb"], "betrag": 5}]},
                erwartet=409)
    assert fehlercode(r) == "buchung_gesperrt"
    assert fehlercode(api.put(f"/api/buchungen/{b['id']}/kategorie", json={"kategorie_id": k["cafe"]},
                              erwartet=409)) == "buchung_gesperrt"
    assert fehlercode(api.delete(f"/api/buchungen/{b['id']}", erwartet=409)) == "buchung_gesperrt"
    assert api.buchung_lesen(b["id"]) == b
    r = api.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": [b["id"]], "kategorie_id": k["cafe"]},
                 erwartet=409)
    assert fehlercode(r) == "buchung_gesperrt"
    assert api.buchung_lesen(b["id"]) == b


def test_abgeglichen_tags_aenderbar(api, k):
    t = api.tag("Steuer")
    b = _mit_status(api, k, "abgeglichen")
    r = api.patch(f"/api/buchungen/{b['id']}", json={"tag_ids": [t["id"]]}, erwartet=200).daten
    assert r == {**b, "tags": [{"id": t["id"], "name": "Steuer"}]}
    r = api.patch(f"/api/buchungen/{b['id']}", json={"tag_ids": [], "status": "abgeglichen"}, erwartet=200).daten
    assert r == b


def test_sperre_vor_statuspruefung(api, k):
    """Prüfreihenfolge PATCH: 422, dann 409 buchung_gesperrt, dann 409 status_uebergang_unzulaessig."""
    b = _mit_status(api, k, "abgeglichen")
    r = api.patch(f"/api/buchungen/{b['id']}", json={"verwendungszweck": "x", "status": "importiert"}, erwartet=409)
    assert fehlercode(r) == "buchung_gesperrt"
    r = api.patch(f"/api/buchungen/{b['id']}", json={"verwendungszweck": 5, "status": "importiert"}, erwartet=422)
    assert fehlercode(r) == "validierung"
    r = api.patch(f"/api/buchungen/{b['id']}", json={"status": "importiert"}, erwartet=409)
    assert fehlercode(r) == "status_uebergang_unzulaessig"


# ---------------------------------------------------------------- Ändern


def test_patch_felder(api, k):
    e1, e2 = api.empfaenger("Eins"), api.empfaenger("Zwei")
    b = api.buchung("2024-01-01", [(k["giro"], -100), (k["leb"], 100)], empfaenger_id=e1["id"],
                    verwendungszweck="alt")
    r = api.patch(f"/api/buchungen/{b['id']}", json={"datum": "2023-12-31", "empfaenger_id": e2["id"]},
                  erwartet=200).daten
    assert r == {**b, "datum": "2023-12-31", "empfaenger": {"id": e2["id"], "name": "Zwei"}}
    r = api.patch(f"/api/buchungen/{b['id']}", json={"empfaenger_id": None, "verwendungszweck": ""}, erwartet=200).daten
    assert r["empfaenger"] is None and r["verwendungszweck"] == "" and r["datum"] == "2023-12-31"
    assert fehlercode(api.patch(f"/api/buchungen/{b['id']}", json={"empfaenger_id": 4711},
                                erwartet=422)) == "referenz_unbekannt"
    for falsch in ({"splits": []}, {"betrag": 5}, {"kategorie_id": k["cafe"]}, {"datum": "31.12.2023"}):
        assert fehlercode(api.patch(f"/api/buchungen/{b['id']}", json=falsch, erwartet=422)) == "validierung"
    assert api.buchung_lesen(b["id"]) == r


# ---------------------------------------------------------- Splits ersetzen


@pytest.mark.kern
def test_splits_ersetzen_splitten_und_zusammenfuehren(api, k):
    b = api.buchung("2024-01-01", [(k["giro"], -1000), (k["leb"], 1000)], verwendungszweck="Einkauf")
    alte_ids = {s["id"] for s in b["splits"]}
    neu = [{"konto_id": k["giro"], "betrag": -1000, "memo": "gesamt"},
           {"konto_id": k["leb"], "betrag": 700}, {"konto_id": k["cafe"], "betrag": 300, "memo": "Kaffee"}]
    r = api.put(f"/api/buchungen/{b['id']}/splits", json={"splits": neu}, erwartet=200).daten
    assert [(s["konto_id"], s["betrag"], s["memo"]) for s in r["splits"]] == [
        (k["giro"], -1000, "gesamt"), (k["leb"], 700, ""), (k["cafe"], 300, "Kaffee")]
    assert not ({s["id"] for s in r["splits"]} & alte_ids), "Ersetzen vergibt neue Split-IDs"
    assert r["kategorie_id"] is None and r["verwendungszweck"] == "Einkauf" and r["id"] == b["id"]
    s = api.salden()
    assert (s[k["leb"]]["saldo"], s[k["cafe"]]["saldo"]) == (700, 300)
    r = api.put(f"/api/buchungen/{b['id']}/splits", json={"splits": [
        {"konto_id": k["giro"], "betrag": -1000}, {"konto_id": k["cafe"], "betrag": 1000}]}, erwartet=200).daten
    assert r["kategorie_id"] == k["cafe"] and len(r["splits"]) == 2
    s = api.salden()
    assert (s[k["leb"]]["saldo"], s[k["cafe"]]["saldo"], s[k["giro"]]["saldo"]) == (0, 1000, -1000)


@pytest.mark.kern
@pytest.mark.parametrize("splits,code", [
    ([], "zu_wenige_splits"), ([("giro", -5)], "zu_wenige_splits"),
    ([("giro", -5), ("leb", 4)], "buchung_unausgeglichen"), ([("giro", -5), (4711, 5)], "referenz_unbekannt"),
])
def test_splits_ersetzen_ungueltig(api, k, splits, code):
    b = api.buchung("2024-01-01", [(k["giro"], -1000), (k["leb"], 1000)])
    body = {"splits": [{"konto_id": k.get(a, a), "betrag": x} for a, x in splits]}
    assert fehlercode(api.put(f"/api/buchungen/{b['id']}/splits", json=body, erwartet=422)) == code
    assert api.buchung_lesen(b["id"]) == b


def test_splits_ersetzen_float_abgelehnt(api, k):
    b = api.buchung("2024-01-01", [(k["giro"], -1000), (k["leb"], 1000)])
    body = {"splits": [{"konto_id": k["giro"], "betrag": -10.0}, {"konto_id": k["leb"], "betrag": 10.0}]}
    assert fehlercode(api.put(f"/api/buchungen/{b['id']}/splits", json=body, erwartet=422)) == "validierung"
    assert api.buchung_lesen(b["id"]) == b


# ---------------------------------------------------------------- Löschen


def test_buchung_loeschen(api, k):
    b = api.buchung("2024-01-01", [(k["giro"], -1000), (k["leb"], 1000)])
    c = api.buchung("2024-01-02", [(k["giro"], -1), (k["leb"], 1)])
    api.delete(f"/api/buchungen/{b['id']}", erwartet=204)
    api.get(f"/api/buchungen/{b['id']}", erwartet=404)
    api.delete(f"/api/buchungen/{b['id']}", erwartet=404)
    assert [x["id"] for x in api.alle_buchungen()] == [c["id"]]
    assert api.salden()[k["giro"]]["saldo"] == -1


def test_belege_immer_leer(api, k):
    b = api.buchung("2024-01-01", [(k["giro"], -1000), (k["leb"], 1000)])
    assert b["belege"] == [] and api.buchung_lesen(b["id"])["belege"] == []
    assert all(x["belege"] == [] for x in api.alle_buchungen())
