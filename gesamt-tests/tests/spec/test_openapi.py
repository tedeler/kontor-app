"""openapi.yaml ist gültig und deckt den Umfang der Meilensteine 1 bis 7 und 9 ab (ohne App)."""

import re

import pytest
import yaml
from jsonschema import Draft202012Validator

from tests.hilfen.pfade import OPENAPI
from tests.hilfen.vertrag import vertrag

OPERATIONEN_M1 = {
    ("get", "/api/status"),
    ("get", "/api/konten"), ("post", "/api/konten"),
    ("get", "/api/konten/{konto_id}"), ("patch", "/api/konten/{konto_id}"), ("delete", "/api/konten/{konto_id}"),
    ("get", "/api/kategorien"), ("get", "/api/kontenuebersicht"),
    ("get", "/api/buchungen"), ("post", "/api/buchungen"),
    ("get", "/api/buchungen/{buchung_id}"), ("patch", "/api/buchungen/{buchung_id}"),
    ("delete", "/api/buchungen/{buchung_id}"),
    ("put", "/api/buchungen/{buchung_id}/splits"), ("put", "/api/buchungen/{buchung_id}/kategorie"),
    ("post", "/api/buchungen/mehrfach/kategorie"), ("post", "/api/buchungen/mehrfach/tags"),
    ("get", "/api/tags"), ("post", "/api/tags"), ("patch", "/api/tags/{tag_id}"), ("delete", "/api/tags/{tag_id}"),
    ("get", "/api/empfaenger"), ("post", "/api/empfaenger"), ("get", "/api/empfaenger/{empfaenger_id}"),
    ("post", "/api/import/kmymoney"), ("get", "/api/importe"),
    ("get", "/api/dubletten"), ("post", "/api/dubletten/{verdacht_id}/aufloesen"),
}

OPERATIONEN_M2 = {
    ("post", "/api/sync"), ("get", "/api/sync/status"), ("get", "/api/sync/laeufe"),
    ("get", "/api/sync/laeufe/{lauf_id}"), ("get", "/api/sync/konten"), ("post", "/api/sync/konten/{iban}/entscheidung"),
    ("put", "/api/sync/pin"), ("delete", "/api/sync/pin"),
    ("get", "/api/tan-anforderungen"), ("get", "/api/tan-anforderungen/{tan_id}"),
    ("get", "/api/tan-anforderungen/{tan_id}/bild"), ("post", "/api/tan-anforderungen/{tan_id}/antwort"),
    ("post", "/api/tan-anforderungen/{tan_id}/abbrechen"),
    ("get", "/api/benachrichtigungen"), ("post", "/api/benachrichtigungen/{benachrichtigung_id}/gelesen"),
    ("get", "/api/mock/zeit"), ("put", "/api/mock/zeit"),
    ("get", "/api/regeln"), ("post", "/api/regeln"), ("post", "/api/regeln/anwenden"),
    ("get", "/api/regeln/{regel_id}"), ("patch", "/api/regeln/{regel_id}"), ("delete", "/api/regeln/{regel_id}"),
    ("post", "/api/buchungen/{buchung_id}/vorschlag"), ("post", "/api/buchungen/mehrfach/vorschlag"),
}

OPERATIONEN_M3 = {
    ("patch", "/api/empfaenger/{empfaenger_id}"), ("delete", "/api/empfaenger/{empfaenger_id}"),
    ("post", "/api/empfaenger/{empfaenger_id}/zusammenfuehren"),
    ("post", "/api/buchungen/erfassen"),
    ("post", "/api/umbuchungen/erkennen"), ("post", "/api/umbuchungen/zusammenfuehren"),
    # D-280: Ausgleichsbuchungen aufräumen (kontostand.md 5)
    ("get", "/api/saldoausgleich/paare"), ("post", "/api/saldoausgleich/paare/zusammenfuehren"),
    ("post", "/api/saldoausgleich/paare/getrennt"),
    ("get", "/api/abstimmungen"), ("post", "/api/abstimmungen"),
    ("get", "/api/abstimmungen/{abstimmung_id}"), ("delete", "/api/abstimmungen/{abstimmung_id}"),
    ("get", "/api/suche"),
    ("get", "/api/aenderungen"), ("get", "/api/aenderungen/{aenderung_id}"),
    ("post", "/api/aenderungen/{aenderung_id}/rueckgaengig"), ("post", "/api/aenderungen/rueckgaengig"),
    ("post", "/api/konten/{konto_id}/loeschen"),
}

OPERATIONEN_M4 = {
    ("post", "/api/import/gnucash"),
    ("get", "/api/lernmodell"), ("post", "/api/lernmodell/vorhersage"), ("post", "/api/lernmodell/anwenden"),
    ("get", "/api/vorlagen"), ("post", "/api/vorlagen"), ("post", "/api/vorlagen/anwenden"),
    ("get", "/api/vorlagen/{vorlage_id}"), ("patch", "/api/vorlagen/{vorlage_id}"),
    ("delete", "/api/vorlagen/{vorlage_id}"),
}

OPERATIONEN_M9 = {("get", "/api/sicherung"), ("post", "/api/sicherung/einspielen"),
                  # D-302: Sicherungspunkte (sicherungspunkte.md 7)
                  ("get", "/api/sicherung/punkte"), ("post", "/api/sicherung/punkte"),
                  ("patch", "/api/sicherung/punkte/{kennung}"), ("get", "/api/sicherung/punkte/{kennung}/chronik"),
                  ("get", "/api/sicherung/punkte/{kennung}/vergleich"), ("get", "/api/sicherung/punkte/{kennung}/datei"),
                  ("post", "/api/sicherung/punkte/{kennung}/wechseln")}

OPERATIONEN_M5 = {
    ("get", "/api/kredite"), ("post", "/api/kredite"), ("post", "/api/kredite/tilgungsplan"),
    ("get", "/api/kredite/{kredit_id}"), ("patch", "/api/kredite/{kredit_id}"), ("delete", "/api/kredite/{kredit_id}"),
    ("get", "/api/kredite/{kredit_id}/plan"), ("post", "/api/kredite/{kredit_id}/zuordnen"),
    ("post", "/api/kredite/{kredit_id}/jahresabgleich"),
    ("get", "/api/wiederkehrend"), ("post", "/api/wiederkehrend/pruefen"),
    ("get", "/api/berichte/kontostand"), ("get", "/api/berichte/einnahmen-ausgaben"),
    ("get", "/api/export/buchungen.csv"), ("get", "/api/export/buchungen.pdf"),
}

OPERATIONEN_M6 = {
    ("get", "/api/benachrichtigungen/zustellung"), ("post", "/api/benachrichtigungen/zustellen"),
    ("get", "/api/mock/zustellungen"),
    ("get", "/api/geheimnisse"), ("put", "/api/geheimnisse/{name}"), ("delete", "/api/geheimnisse/{name}"),
    ("get", "/api/mail/postfaecher"), ("post", "/api/mail/postfaecher"),
    ("get", "/api/mail/postfaecher/{postfach_id}"), ("patch", "/api/mail/postfaecher/{postfach_id}"),
    ("delete", "/api/mail/postfaecher/{postfach_id}"), ("get", "/api/mail/postfaecher/{postfach_id}/status"),
    ("post", "/api/mail/postfaecher/{postfach_id}/anmeldung"),
    ("delete", "/api/mail/postfaecher/{postfach_id}/anmeldung"),
    ("post", "/api/mail/anmeldung/abschluss"), ("post", "/api/mail/abruf"), ("get", "/api/mail/nachrichten"),
}

OPERATIONEN_M7 = {
    ("get", "/api/anmeldung"), ("post", "/api/anmeldung"), ("post", "/api/anmeldung/einrichten"),
    ("post", "/api/anmeldung/abmelden"), ("put", "/api/anmeldung/passwort"), ("get", "/api/gesundheit"),
}

# M8 (E-138): einzige neue Operation; die Oberfläche nutzt sonst nur bestehende Endpunkte (oberflaeche.md 1)
OPERATIONEN_M8 = {("post", "/api/benachrichtigungen/test")}
OPERATIONEN_M12 = {("post", "/api/buchungen/mehrfach/aendern")}
OPERATIONEN_M13 = {("get", "/api/version")}
OPERATIONEN_M15 = {("post", "/api/buchungen/mehrfach/loeschen"), ("post", "/api/buchungen/mehrfach/verschieben"),
                   ("get", "/api/konten/{konto_id}/herkunft")}
OPERATIONEN_M16 = {("get", "/api/buchungen/{buchung_id}/wiederkehrend")}
# M18 (dokumente.md 2, E-210)
OPERATIONEN_M18 = {("post", "/api/dokumente"), ("post", "/api/dokumente/aus-mail"),
                   ("get", "/api/dokumente/{dokument_id}"), ("patch", "/api/dokumente/{dokument_id}"),
                   ("delete", "/api/dokumente/{dokument_id}"), ("post", "/api/dokumente/{dokument_id}/buchungen"),
                   ("delete", "/api/dokumente/{dokument_id}/buchungen/{buchung_id}"),
                   ("get", "/api/buchungen/{buchung_id}/dokumente"), ("get", "/api/dokumente/{dokument_id}/inhalt"),
                   ("get", "/api/dokumente/{dokument_id}/mail"), ("get", "/api/dokumente/{dokument_id}/mail/html"),
                   ("get", "/api/dokumente/{dokument_id}/mail/anhaenge/{nr}")}
# M19 (alfbanco.md 2.1, E-215)
OPERATIONEN_M19 = {("post", "/api/import/alfbanco"), ("post", "/api/kategorien/zusammenfuehren"),
                   ("post", "/api/kategorien/verschieben")}  # D-326
# M20 (erwartungen.md 6, E-220)
OPERATIONEN_M20 = {("get", "/api/erwartungen"), ("post", "/api/erwartungen"), ("post", "/api/erwartungen/abgleich"),
                   ("get", "/api/erwartungen/{erwartung_id}"), ("patch", "/api/erwartungen/{erwartung_id}"),
                   ("delete", "/api/erwartungen/{erwartung_id}"), ("post", "/api/erwartungen/{erwartung_id}/zustand"),
                   ("get", "/api/erwartungen/{erwartung_id}/kandidaten"),
                   ("post", "/api/erwartungen/{erwartung_id}/buchungen"),
                   ("delete", "/api/erwartungen/{erwartung_id}/buchungen/{buchung_id}")}
# M23 (geheimnisschutz.md 2, 5, 6, E-232)
OPERATIONEN_M23 = {("get", "/api/geheimnisse/schutz"), ("post", "/api/geheimnisse/schutz"),
                   ("post", "/api/geheimnisse/schutz/ausschalten"), ("post", "/api/geheimnisse/entsperren"),
                   ("post", "/api/geheimnisse/sperren"), ("put", "/api/sync/pin/gemerkt"),
                   ("delete", "/api/sync/pin/gemerkt"), ("put", "/api/mail/postfaecher/{postfach_id}/app-passwort"),
                   ("delete", "/api/mail/postfaecher/{postfach_id}/app-passwort")}
# M25 (wiederkehrend.md 9.3, E-242)
OPERATIONEN_M25 = {("get", "/api/wiederkehrend/einstellungen"), ("put", "/api/wiederkehrend/einstellungen/vorgabe"),
                   ("put", "/api/empfaenger/{empfaenger_id}/wiederkehrend"),
                   ("delete", "/api/empfaenger/{empfaenger_id}/wiederkehrend")}
# M27 (sammel.md 4.1, 6; E-251)
OPERATIONEN_M27 = {("post", "/api/dubletten")}  # GET /api/statistik entfällt mit M32 (E-298)
# M29 (bankzugang.md 4, E-262)
OPERATIONEN_M29 = {("get", "/api/bank/zugang"), ("put", "/api/bank/zugang"),
                   ("post", "/api/bank/zugang/tan-verfahren"), ("post", "/api/bank/zugang/konten/abrufen"),
                   ("put", "/api/bank/zugang/konten"), ("get", "/api/bank/zugang/diagnose"),
                   ("put", "/api/bank/zugang/diagnose")}
OPERATIONEN_M30 = {("get", "/api/ausdruck/sprache"), ("post", "/api/ausdruck/pruefen"),
                   ("post", "/api/ausdruck/als-regel"), ("post", "/api/regeln/reihenfolge"),
                   ("post", "/api/regeln/test"), ("post", "/api/regeln/erklaeren"),
                   ("post", "/api/regeln/{regel_id}/anwenden"),
                   # D-295: automatisch angelegte Regel als eigene übernehmen (kategorisierung.md 8.10)
                   ("post", "/api/regeln/{regel_id}/uebernehmen"),
                   ("get", "/api/regeln/pruefung")}  # D-308
OPERATIONEN_M31 = {("get", "/api/buchungen/{buchung_id}/lernmodell"), ("get", "/api/lernmodell/uebersicht"),
                   ("get", "/api/lernmodell/einstellungen"), ("put", "/api/lernmodell/einstellungen"),
                   ("post", "/api/mock/lerndaten"), ("get", "/api/berichte/monat")} | {
    ("get", f"/api/berichte/{n}") for n in ("vertraege", "jahr", "vorschau", "vermoegen", "kategorien", "empfaenger",
                                             "geldfluss", "qualitaet", "tags")}
# M32 (sammel3.md, E-294)
OPERATIONEN_M32 = {("get", "/api/empfaenger/anzahlen"), ("get", "/api/empfaenger/{empfaenger_id}/konten"),
                   ("post", "/api/mail/nachrichten/{nachricht_id}/buchung"),
                   ("get", "/api/dokumente/{dokument_id}/mail/bilder"), ("get", "/api/konfiguration")}
# Feature benutzer (D-324): Personen aus KONTOR_BENUTZER
OPERATIONEN_D324 = {("get", "/api/benutzer")}
ERWARTETE_OPERATIONEN = (OPERATIONEN_D324 | OPERATIONEN_M1 | OPERATIONEN_M2 | OPERATIONEN_M3 | OPERATIONEN_M4 | OPERATIONEN_M9
                         | OPERATIONEN_M5 | OPERATIONEN_M6 | OPERATIONEN_M7 | OPERATIONEN_M8 | OPERATIONEN_M12
                         | OPERATIONEN_M13 | OPERATIONEN_M15 | OPERATIONEN_M16 | OPERATIONEN_M18
                         | OPERATIONEN_M19 | OPERATIONEN_M20 | OPERATIONEN_M23 | OPERATIONEN_M25 | OPERATIONEN_M27
                         | OPERATIONEN_M29 | OPERATIONEN_M30 | OPERATIONEN_M31 | OPERATIONEN_M32)


@pytest.fixture(scope="module")
def dok():
    with open(OPENAPI, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_openapi_gueltig(dok):
    from openapi_spec_validator import validate

    validate(dok)
    assert dok["openapi"].startswith("3.1")


def test_alle_operationen_vorhanden(dok):
    ist = {(m, p) for p, ops in dok["paths"].items() for m in ops if m in ("get", "post", "put", "patch", "delete")}
    assert ist == ERWARTETE_OPERATIONEN


def test_m1_schemas_rueckwaertskompatibel(dok):
    """E-029: Erweiterungen bestehender M1-Schemas sind nie Pflichtfelder."""
    s = dok["components"]["schemas"]
    buchung = s["Buchung"]
    assert "vorschlag" in buchung["properties"] and "vorschlag" not in buchung["required"]
    assert buchung["required"] == ["id", "datum", "empfaenger", "verwendungszweck", "status", "splits", "tags",
                                   "kategorie_id", "betrag", "extern_ids", "belege"]
    assert s["Status"]["required"] == ["version", "modus", "mock", "hinweis", "plugins", "mock_szenario"]


def test_m3_schemas_rueckwaertskompatibel(dok):
    """E-029: M3-Felder an M1/M2-Schemas sind optional; Pflichtfelder unverändert."""
    s = dok["components"]["schemas"]
    for feld in ("gegen_iban", "ist_umbuchung", "abgestimmt"):
        assert feld in s["Buchung"]["properties"] and feld not in s["Buchung"]["required"]
    assert s["Split"]["required"] == ["id", "konto_id", "betrag", "memo"]
    assert "abstimmung_id" in s["Split"]["properties"]
    assert s["Empfaenger"]["required"] == ["id", "name", "extern_id"]
    assert {"aliase", "standardkategorie_id"} <= set(s["Empfaenger"]["properties"])
    assert s["EmpfaengerNeu"]["required"] == ["name"]
    assert s["Tag"]["required"] == ["id", "name", "extern_id", "anzahl_buchungen"]
    # E-078: spätere Meilensteine dürfen Aufzählungen erweitern und die Version erhöhen
    assert set(s["Vorschlag"]["properties"]["quelle"]["enum"]) >= {"regel", "standardkategorie"}
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 1, 0)


def test_m4_schemas_rueckwaertskompatibel(dok):
    """E-029: M4-Felder an bestehenden Schemas sind optional; Pflichtfelder unverändert."""
    s = dok["components"]["schemas"]
    # E-084: der M3-Nachtrag (gelöschte Bankkonten) erhöht die Version auf 2.3.0
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 2, 0)
    assert s["Vorschlag"]["required"] == ["kategorie_id", "regel_id", "quelle", "vorher_konto_id"]
    assert "sicherheit" in s["Vorschlag"]["properties"]
    assert set(s["Vorschlag"]["properties"]["quelle"]["enum"]) == {"regel", "standardkategorie", "lernmodell"}
    for feld in ("buchungen_gesplittet", "vorlage_abweichungen"):
        assert feld in s["SyncKonto"]["properties"] and feld not in s["SyncKonto"]["required"]
    assert not {"vorlagen_geaendert", "vorlagen_geloescht"} & set(s["KontoLoeschErgebnis"]["properties"]), "E-094"
    assert "split_abweichung" in s["Benachrichtigung"]["properties"]["art"]["enum"]
    assert set(s["Aenderungsquelle"]["enum"]) >= {"lernmodell", "vorlage"}
    # E-109: M5 hängt kredit an; vorlage bleibt die Objektart nach abstimmung
    assert s["Objektart"]["enum"][:8] == ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung",
                                          "vorlage"]
    assert {"gnc-xml-gzip", "gnc-xml", "gnc-sqlite"} <= set(s["ImportErgebnis"]["properties"]["format"]["enum"])
    assert s["Importvorgang"]["properties"]["art"]["enum"][:2] == ["kmymoney", "gnucash"]  # E-215: ab M19 alfbanco
    assert s["Buchung"]["required"] == ["id", "datum", "empfaenger", "verwendungszweck", "status", "splits", "tags",
                                        "kategorie_id", "betrag", "extern_ids", "belege"]
    assert s["BuchungZustand"]["required"] == ["id", "datum", "empfaenger_id", "verwendungszweck", "status",
                                               "splits", "tag_ids", "extern_ids", "vorschlag", "gegen_iban"]


def test_m3_nachtrag_geloeschte_bankkonten(dok):
    """E-080 bis E-084: neue Felder optional, Entscheidung mit zwei Pflichtfeldern ohne Vorgabe."""
    s = dok["components"]["schemas"]
    # E-093: M9 erhöht die Version auf 2.4.0; die exakte Prüfung steht in test_m9_sicherung
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 3, 0)
    assert s["SyncKontoZustand"]["required"] == ["iban", "konto_id", "letzter_abruf_bis", "letzter_erfolg_am"]
    for feld in ("status", "wiederherstellen_buchungen"):
        assert feld in s["SyncKontoZustand"]["properties"]
    assert s["SyncKontoZustand"]["properties"]["status"]["enum"] == ["aktiv", "konto_fehlt", "ignoriert",
                                                                     "wiederherstellen"]
    assert "uebersprungen" in s["SyncLauf"]["properties"] and "uebersprungen" not in s["SyncLauf"]["required"]
    # E-189: M15 hängt nicht_zugeordnet an; die beiden Werte des Nachtrags bleiben vorn
    assert s["SyncUebersprungen"]["properties"]["status"]["enum"][:2] == ["konto_fehlt", "ignoriert"]
    assert s["SyncUebersprungen"]["required"] == ["iban", "name", "status"]
    e = s["SyncKontoEntscheidung"]
    assert e["required"] == ["aktion", "buchungen"] and e["additionalProperties"] is False
    assert all("default" not in e["properties"][f] for f in ("aktion", "buchungen"))
    assert "konto_fehlt" in s["Benachrichtigung"]["properties"]["art"]["enum"]
    op = dok["paths"]["/api/sync/konten/{iban}/entscheidung"]["post"]
    assert set(op["responses"]) == {"200", "404", "409", "422"}


def test_m9_sicherung(dok):
    """sicherung.md, E-085 bis E-093: Endpunkte, Manifest, Ergebnis, neue Quelle; Rückwärtskompatibel."""
    s = dok["components"]["schemas"]
    # E-109: M5 erhöht die Version auf 2.5.0; die exakte Prüfung steht in test_m5_schemas
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 4, 0)
    assert "sicherung" in s["Aenderungsquelle"]["enum"]
    assert s["Aenderungsquelle"]["enum"][:8] == ["manuell", "import", "sync", "regeln", "umbuchung", "rueckgaengig",
                                                 "lernmodell", "vorlage"]
    m = s["SicherungManifest"]
    assert m["additionalProperties"] is False
    assert m["required"] == ["format", "formatversion", "erstellt", "modus", "app_version", "schemaversion",
                             "anzahl", "inhalt_sha256", "datenbank_sha256"]
    assert m["properties"]["anzahl"]["required"] == ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht",
                                                     "abstimmung", "vorlage"]
    # E-109/E-118: Objektarten ab M5 (kredit, postfach) stehen nur bei Vorhandensein in anzahl, sind also nicht Pflicht
    # E-210: ab M18 dokument, ab M20 erwartung ebenfalls nur bei Vorhandensein
    assert set(s["Objektart"]["enum"]) - {"kredit", "postfach", "dokument", "erwartung"} == set(m["properties"]["anzahl"]["required"])
    e = s["SicherungErgebnis"]
    assert e["required"] == ["trocken", "geaendert", "aenderung_id", "manifest", "unterschied",
                             "abgestimmte_buchungen_betroffen"]
    get = dok["paths"]["/api/sicherung"]["get"]
    assert set(get["responses"]) == {"200"} and set(get["responses"]["200"]["content"]) == {"application/zip"}
    post = dok["paths"]["/api/sicherung/einspielen"]["post"]
    assert set(post["responses"]) == {"200", "409", "422"}
    assert {p["name"]: p["schema"]["default"] for p in post["parameters"]} == {"trocken": False, "bestaetigt": False}
    assert "datei" in post["requestBody"]["content"]["multipart/form-data"]["schema"]["required"]


def test_vorlage_ohne_betragsbedingung(dok):
    """vorlagen.md 1: Vorlagen erkennen über Empfänger und Muster, der Betrag steckt in den Teilen."""
    s = dok["components"]["schemas"]
    refs = {x["$ref"].rsplit("/", 1)[1] for x in s["VorlageBedingung"]["oneOf"]}
    assert refs == {"BedingungText", "BedingungKonto"}
    assert s["Vorlage"]["properties"]["teile"]["minItems"] == 2


def test_protokollform_buchung_aus_buchung_ableitbar(dok):
    """protokoll.md 2: BuchungZustand nutzt nur Felder, die Buchung liefert (bzw. empfaenger_id/tag_ids)."""
    s = dok["components"]["schemas"]
    zustand = set(s["BuchungZustand"]["required"])
    buchung = set(s["Buchung"]["properties"])
    assert zustand - buchung == {"empfaenger_id", "tag_ids"}
    assert not ({"kategorie_id", "betrag", "ist_umbuchung", "abgestimmt", "belege"} & zustand)


def test_vertrag_bild_antwort():
    v = vertrag()
    v.pruefe_antwort("GET", "/api/tan-anforderungen/1/bild", 200, b"\x89PNG\r\n\x1a\n", "image/png")
    with pytest.raises(AssertionError):
        v.pruefe_antwort("GET", "/api/tan-anforderungen/1/bild", 200, b"{}", "application/json")


def test_alle_schemas_gueltiges_json_schema(dok):
    for name, schema in dok["components"]["schemas"].items():
        Draft202012Validator.check_schema(schema)


def test_fehlerantworten_verwenden_fehlerschema(dok):
    v = vertrag()
    for pfad, ops in dok["paths"].items():
        for m, op in ops.items():
            if m == "parameters":
                continue
            for code, antw in op["responses"].items():
                antw, _ = v._aufloesen(antw, [])
                if int(code) >= 400:
                    assert list(antw["content"]) == ["application/json"], (m, pfad, code)
                    schema = antw["content"]["application/json"]["schema"]
                    assert schema == {"$ref": "#/components/schemas/Fehler"}, (m, pfad, code)


def test_betraege_sind_ganzzahlen(dok):
    s = dok["components"]["schemas"]
    assert s["Betrag"]["type"] == "integer"
    for name in ("Split", "SplitNeu"):
        assert s[name]["properties"]["betrag"] == {"$ref": "#/components/schemas/Betrag"}
    for name in ("KontoSaldo",):
        assert s[name]["properties"]["saldo"]["type"] == "integer"


def test_vertrag_ordnet_pfade_zu():
    v = vertrag()
    assert v.vorlage("/api/buchungen/mehrfach/kategorie") == "/api/buchungen/mehrfach/kategorie"
    assert v.vorlage("/api/buchungen/17") == "/api/buchungen/{buchung_id}"
    assert v.vorlage("/api/buchungen/17/splits") == "/api/buchungen/{buchung_id}/splits"
    assert v.vorlage("/api/gibtsnicht") is None


def test_vertrag_erkennt_schemaverletzung():
    v = vertrag()
    gut = b'{"fehler": {"code": "nicht_gefunden", "meldung": "x", "details": null}}'
    v.pruefe_antwort("GET", "/api/konten/1", 404, gut, "application/json")
    with pytest.raises(AssertionError):
        v.pruefe_antwort("GET", "/api/konten/1", 404, b'{"detail": "Not Found"}', "application/json")
    with pytest.raises(AssertionError):
        v.pruefe_antwort("GET", "/api/konten/1", 418, gut, "application/json")
    konto = (b'{"id": 1, "name": "G", "art": "girokonto", "eltern_id": null, "iban": null, "waehrung": "EUR",'
             b' "geschlossen": false, "eroeffnet_am": null, "notiz": "", "extern_id": null, "ist_kategorie": false}')
    v.pruefe_antwort("GET", "/api/konten/1", 200, konto, "application/json")
    with pytest.raises(AssertionError):
        v.pruefe_antwort("GET", "/api/konten/1", 200, konto.replace(b'"id": 1', b'"id": 1.5'), "application/json")
    with pytest.raises(AssertionError):
        v.pruefe_antwort("GET", "/api/konten/1", 200, konto.replace(b'"eroeffnet_am": null', b'"eroeffnet_am": "01.02.2024"'),
                         "application/json")


def test_konto_loeschen_ohne_vorgabe(dok):
    """E-061: Umgang mit Buchungen und Konflikten muss ausdrücklich gewählt werden."""
    s = dok["components"]["schemas"]["KontoLoeschen"]
    assert s["required"] == ["buchungen", "konflikte"]
    assert "default" not in s["properties"]["buchungen"] and "default" not in s["properties"]["konflikte"]
    assert s["properties"]["buchungen"]["enum"] == ["loeschen", "elternkonto", "unkategorisiert"]
    assert s["properties"]["konflikte"]["enum"] == ["loeschen", "behalten"]


def test_m5_schemas(dok):
    """kredite.md, wiederkehrend.md, berichte.md, E-097 bis E-110: Version, neue Werte, rückwärtskompatibel."""
    s = dok["components"]["schemas"]
    # E-118: M6 erhöht die Version auf 2.6.0 und hängt postfach an; die exakte Prüfung steht in test_m6_schemas
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 5, 0)
    assert s["Aenderungsquelle"]["enum"][9] == "kredit"  # E-220: ab M20 folgt mail
    assert s["Aenderungsquelle"]["enum"][:9] == ["manuell", "import", "sync", "regeln", "umbuchung", "rueckgaengig",
                                                 "lernmodell", "vorlage", "sicherung"]
    assert s["Objektart"]["enum"][:9] == ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung",
                                          "vorlage", "kredit"]
    assert {"$ref": "#/components/schemas/Kredit"} in s["Objektzustand"]["anyOf"]
    # Pflichtfelder bestehender Schemas unverändert (E-029), neue Felder optional
    assert s["SicherungManifest"]["properties"]["anzahl"]["required"] == [
        "konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]
    assert "buchungen_kredit" in s["SyncKonto"]["properties"]
    assert "buchungen_kredit" not in s["SyncKonto"]["required"]
    assert {"neuer_empfaenger", "wiederkehrend_betrag", "wiederkehrend_ausbleibend"} <= set(
        s["Benachrichtigung"]["properties"]["art"]["enum"])
    k = s["Kredit"]
    assert k["additionalProperties"] is False
    assert set(k["required"]) == set(k["properties"])
    assert {"zuordnungen", "abgleiche"} <= set(k["required"])
    assert not {"zuordnungen", "abgleiche", "id"} & set(s["KreditNeu"]["properties"])
    assert "konto_id" not in s["KreditAenderung"]["properties"]
    assert s["Zinsmethode"]["enum"] == ["30/360", "act/360", "act/365"]
    assert s["KreditNeu"]["properties"]["zinsmethode"]["default"] == "30/360"
    for name in ("Kreditbetrag", "Sollzins"):
        assert s[name]["type"] == "integer"
    # Export: dieselben Filter wie die Buchungsliste, ohne Paginierung
    liste = {p["name"] for p in dok["paths"]["/api/buchungen"]["get"]["parameters"]}
    for endung, art in (("csv", "text/csv"), ("pdf", "application/pdf")):
        op = dok["paths"][f"/api/export/buchungen.{endung}"]["get"]
        # E-251: „verdacht“ (M27) ist kein Filter und gehört nur zur Buchungsliste
        assert {p["name"] for p in op["parameters"]} == liste - {"seite", "pro_seite", "verdacht", "position_id"}   # D-271
        assert set(op["responses"]["200"]["content"]) == {art}


def test_vertrag_export_antworten():
    v = vertrag()
    v.pruefe_antwort("GET", "/api/export/buchungen.csv", 200, b"\xef\xbb\xbfbuchung_id\r\n", "text/csv; charset=utf-8")
    v.pruefe_antwort("GET", "/api/export/buchungen.pdf", 200, b"%PDF-1.4", "application/pdf")
    with pytest.raises(AssertionError):
        v.pruefe_antwort("GET", "/api/export/buchungen.csv", 200, b"{}", "application/json")
    assert v.vorlage("/api/kredite/tilgungsplan") == "/api/kredite/tilgungsplan"
    assert v.vorlage("/api/kredite/3") == "/api/kredite/{kredit_id}"


def test_m6_schemas(dok):
    """fints.md, mail.md, benachrichtigungen.md, geheimnisse.md, E-112 bis E-122: Version, neue Werte, rückwärtskompatibel."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 6, 0)  # exakt in test_m7_schemas (E-127)
    assert s["Objektart"]["enum"][:10] == ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung",  # E-210
                                      "vorlage", "kredit", "postfach"]
    assert s["Aenderungsquelle"]["enum"][:10] == ["manuell", "import", "sync", "regeln", "umbuchung", "rueckgaengig",  # E-220
                                             "lernmodell", "vorlage", "sicherung", "kredit"]
    assert {"$ref": "#/components/schemas/Postfach"} in s["Objektzustand"]["anyOf"]
    # Pflichtfelder bestehender Schemas unverändert (E-029), neue Felder optional
    b = s["Benachrichtigung"]
    assert b["required"] == ["id", "art", "schluessel", "titel", "text", "link", "erstellt_am", "gelesen"]
    assert {"zustellung", "zustellversuche", "zugestellt_am"} <= set(b["properties"])
    assert b["properties"]["art"]["enum"][:8] == ["sync_fehler", "tan_erforderlich", "tan_abgelaufen",
                                                  "split_abweichung", "konto_fehlt", "neuer_empfaenger",
                                                  "wiederkehrend_betrag", "wiederkehrend_ausbleibend"]
    # E-162: M11 hängt saldo_ausgeglichen an; die M6-Werte bleiben an ihrer Stelle
    assert b["properties"]["art"]["enum"][8:13] == ["tan_erinnerung", "mail_token_laeuft_ab", "mail_token_abgelaufen",
                                                    "mail_token_widerrufen", "mail_fehler"]
    assert b["properties"]["zustellung"]["enum"] == ["keine", "ausstehend", "zugestellt", "aufgegeben"]
    assert "pin_quelle" in s["SyncStatus"]["properties"] and "pin_quelle" not in s["SyncStatus"]["required"]
    assert s["SicherungManifest"]["properties"]["anzahl"]["required"] == [
        "konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]
    # Postfach: Protokollform ohne Betriebszustand, Adresse unveränderlich
    p = s["Postfach"]
    assert set(p["required"]) == set(p["properties"]) == {"id", "adresse", "bezeichnung", "ordner",
                                                           "absender_filter", "aktiv"}
    assert "adresse" not in s["PostfachAenderung"]["properties"]
    assert s["PostfachNeu"]["required"] == ["adresse"]
    # Geheimnisse: keine Antwort enthält ein Feld für Werte
    for name in ("GeheimnisUebersicht", "GeheimnisEintrag", "PostfachStatus", "ZustellStatus", "PushNachricht",
                 "AnmeldungStart", "SyncStatus"):
        felder = set(s[name]["properties"])
        assert not felder & {"wert", "token", "access_token", "refresh_token", "pin", "tan", "client_secret",
                             "code_verifier", "state"}, name
    assert s["GeheimnisEingabe"]["required"] == ["wert"]
    for pfad, code in (("/api/sync/pin", "409"),):
        assert code in dok["paths"][pfad]["put"]["responses"] and code in dok["paths"][pfad]["delete"]["responses"]
    put = dok["paths"]["/api/geheimnisse/{name}"]["put"]
    assert set(put["responses"]) == {"204", "404", "409", "422"}
    assert set(dok["paths"]["/api/mail/anmeldung/abschluss"]["post"]["responses"]) == {"200", "409", "422"}
    assert {t["name"] for t in dok["tags"]} >= {"geheimnisse", "mail"}


def test_vertrag_m6_pfade():
    v = vertrag()
    assert v.vorlage("/api/mail/postfaecher/3") == "/api/mail/postfaecher/{postfach_id}"
    assert v.vorlage("/api/mail/postfaecher/3/status") == "/api/mail/postfaecher/{postfach_id}/status"
    assert v.vorlage("/api/mail/postfaecher/3/anmeldung") == "/api/mail/postfaecher/{postfach_id}/anmeldung"
    assert v.vorlage("/api/benachrichtigungen/zustellung") == "/api/benachrichtigungen/zustellung"
    assert v.vorlage("/api/benachrichtigungen/7/gelesen") == "/api/benachrichtigungen/{benachrichtigung_id}/gelesen"
    assert v.vorlage("/api/geheimnisse/ntfy_token") == "/api/geheimnisse/{name}"


def test_m7_schemas(dok):
    """sicherheit.md, betrieb.md, E-125 bis E-127: Version, allgemeine Antworten, Anmeldeschemas ohne Geheimnisse."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 7, 0)  # exakt in test_m8_schemas (E-138)
    allg = dok["x-allgemeine-antworten"]
    assert set(allg) == {"401", "403", "413", "429"}
    for antwort in allg.values():
        ziel = dok["components"]["responses"][antwort["$ref"].rsplit("/", 1)[1]]
        assert ziel["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/Fehler"}
    assert "Retry-After" in dok["components"]["responses"]["Gesperrt"]["headers"]
    st = s["AnmeldeStatus"]
    assert set(st["required"]) == set(st["properties"]) == {"aktiv", "eingerichtet", "angemeldet", "csrf_token",
                                                             "sitzung_ablauf", "gesperrt_bis"}
    for name in ("AnmeldeStatus", "Gesundheit", "Status", "SyncStatus"):
        assert not set(s[name]["properties"]) & {"passwort", "passwort_hash", "hash", "sitzung", "token",
                                                  "einrichtungscode"}, name
    assert s["AnmeldeEingabe"]["required"] == ["passwort"]
    assert s["EinrichtungEingabe"]["required"] == ["einrichtungscode", "passwort"]
    assert s["PasswortAenderung"]["required"] == ["altes_passwort", "neues_passwort"]
    assert set(s["Gesundheit"]["properties"]) == {"status", "version"}
    # öffentliche Pfade haben keine eigene 401 außer der Anmeldung selbst
    assert "401" not in dok["paths"]["/api/anmeldung"]["get"]["responses"]
    assert "401" in dok["paths"]["/api/anmeldung"]["post"]["responses"]
    assert {t["name"] for t in dok["tags"]} >= {"anmeldung", "betrieb"}
    # bestehende Schemas unverändert (E-029)
    assert s["Status"]["required"] == ["version", "modus", "mock", "hinweis", "plugins", "mock_szenario"]


def test_vertrag_allgemeine_antworten():
    """E-127: 401/403/413/429 sind für jede Operation zulässig, andere nicht spezifizierte Codes nicht."""
    v = vertrag()
    fehler = b'{"fehler": {"code": "nicht_angemeldet", "meldung": "Bitte anmelden", "details": {}}}'
    for status in (401, 403, 413, 429):
        assert v.pruefe_antwort("GET", "/api/konten", status, fehler, "application/json")["fehler"]["code"]
    with pytest.raises(AssertionError):
        v.pruefe_antwort("GET", "/api/konten", 418, fehler, "application/json")
    with pytest.raises(AssertionError):
        v.pruefe_antwort("GET", "/api/konten", 401, b'{"x": 1}', "application/json")


def test_antwortobjekt_vergleich():
    """E-124: Antwortobjekte erlauben gegenüber Erwartungen nur zusätzliche optionale Felder."""
    v = vertrag()
    s = v.dok["components"]["schemas"]["SyncStatus"]
    d = {"automatisch": False, "intervall_minuten": 0, "laeuft": False, "jetzt": "2024-06-30T12:00:00Z",
         "naechster_lauf": None, "letzter_lauf": None, "offene_tan_anforderung": None, "pin_vorhanden": False}
    ist = v.markiere(s, {**d, "pin_quelle": "eingabe"})
    assert ist == d and d == ist and not ist != d
    assert ist != {**d, "pin_vorhanden": True}
    assert ist != {**d, "fehlt_im_schema": 1}
    ohne_pflicht = dict(d)
    del ohne_pflicht["laeuft"]
    assert v.markiere(s, ohne_pflicht) != d, "Pflichtfeld fehlt in der Antwort"
    # zwei Antwortobjekte werden exakt verglichen
    assert ist != v.markiere(s, d) and v.markiere(s, d) == v.markiere(s, dict(d))
    # zusätzliche Pflichtfelder (nicht optional) sind nicht erlaubt
    k = v.dok["components"]["schemas"]["Konto"]
    konto = v.markiere(k, {f: None for f in k["required"]})
    teil = {f: None for f in k["required"][:-1]}
    assert konto != teil
    # Listen und verschachtelte Objekte
    assert [ist] == [d] and {"a": [ist]} == {"a": [d]}



def test_m8_schemas(dok):
    """benachrichtigungen.md 8, E-138: Test-Benachrichtigung; sonst keine neuen Endpunkte in M8 (oberflaeche.md)."""
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 8, 0)
    op = dok["paths"]["/api/benachrichtigungen/test"]
    assert set(op) == {"post"}
    post = op["post"]
    assert post["operationId"] == "testBenachrichtigung"
    assert "requestBody" not in post
    assert set(post["responses"]) == {"200", "409"}
    s = dok["components"]["schemas"]["TestBenachrichtigung"]
    assert s["additionalProperties"] is False
    assert set(s["required"]) == set(s["properties"]) == {"plugin", "zugestellt", "gesendet", "fehler"}
    assert s["properties"]["plugin"]["enum"] == ["mock", "ntfy"]
    fehler = next(x for x in s["properties"]["fehler"]["oneOf"] if x.get("type") == "object")
    assert set(fehler["required"]) == {"code", "meldung", "status"}
    # bestehende Schemas unverändert (E-029)
    assert dok["components"]["schemas"]["ZustellErgebnis"]["required"] == ["versucht", "zugestellt"]
    assert "benachrichtigung_id" in dok["components"]["schemas"]["PushNachricht"]["required"]


def test_m11_schemas(dok):
    """kontostand.md, datenmodell.md 16, buchhaltungspflege.md 10, E-158 bis E-165: nur optionale Erweiterungen."""
    s = dok["components"]["schemas"]
    # E-173: M12 erhöht auf 2.11.0, die exakte Prüfung steht in test_m12_schemas
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 10, 0)
    assert "saldo_abgleich" in s["SyncKonto"]["properties"] and "saldo_abgleich" not in s["SyncKonto"]["required"]
    sa = s["SaldoAbgleich"]
    assert sa["required"] == ["status", "bank_saldo", "stichtag", "kontor_saldo", "differenz", "buchung_id"]
    assert sa["properties"]["status"]["enum"] == ["aus", "nicht_verfuegbar", "stimmt", "ausgeglichen"]
    # E-189: M15 hängt konto_nicht_zugeordnet hinter saldo_ausgeglichen an
    assert "saldo_ausgeglichen" in s["Benachrichtigung"]["properties"]["art"]["enum"]
    z = s["EmpfaengerZusammenfuehren"]
    assert z["required"] == ["quelle_ids"] and "name" in z["properties"]
    assert "409" in dok["paths"]["/api/empfaenger/{empfaenger_id}/zusammenfuehren"]["post"]["responses"]
    for pfad in ("/api/buchungen", "/api/export/buchungen.csv", "/api/export/buchungen.pdf"):
        p = {x["name"]: x for x in dok["paths"][pfad]["get"]["parameters"]}
        assert p["unterkonten"]["schema"] == {"type": "boolean", "default": False}, pfad


def test_m12_schemas(dok):
    """datenmodell.md 17, E-168 bis E-173: neuer Endpunkt mehrfach/aendern, bestehende Schemas unverändert."""
    s = dok["components"]["schemas"]
    # E-178: M13 erhöht auf 2.12.0, die exakte Prüfung steht in test_m13_schemas
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 11, 0)
    post = dok["paths"]["/api/buchungen/mehrfach/aendern"]["post"]
    assert set(post["responses"]) == {"200", "409", "422"}
    assert post["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MehrfachErgebnis"}
    m = s["MehrfachAenderung"]
    assert m["additionalProperties"] is False and m["required"] == ["buchung_ids"]
    assert set(m["properties"]) == {"buchung_ids", "status", "datum", "empfaenger_id", "verwendungszweck",
                                    "entsperren"}
    assert m["properties"]["entsperren"] == {"type": "boolean", "default": False}
    assert sorted(x["required"][0] for x in m["anyOf"]) == ["datum", "empfaenger_id", "status", "verwendungszweck"]
    v = Draft202012Validator({**m, "components": dok["components"]})
    assert v.is_valid({"buchung_ids": [1], "status": "importiert"})
    assert v.is_valid({"buchung_ids": [1], "empfaenger_id": None})
    assert not v.is_valid({"buchung_ids": [1]}), "mindestens ein Feld"
    assert not v.is_valid({"buchung_ids": [], "status": "importiert"})
    assert not v.is_valid({"buchung_ids": [1, 1], "status": "importiert"})
    assert not v.is_valid({"buchung_ids": [1], "status": "erledigt"})
    assert not v.is_valid({"buchung_ids": [1], "tag_ids": [1]})
    # bestehende Schemas unverändert (E-029)
    assert s["MehrfachErgebnis"]["required"] == ["geaendert", "anzahl"]
    assert set(s["BuchungAenderung"]["properties"]) == {"datum", "empfaenger_id", "verwendungszweck", "status",
                                                       "tag_ids"}


def test_m13_schemas(dok):
    """version.md 3, E-177, E-178: neuer Endpunkt GET /api/version, bestehende Schemas unverändert."""
    from tests.hilfen.m13 import FELDER, VERSION_MUSTER

    s = dok["components"]["schemas"]
    # E-189: M15 erhöht auf 2.13.0, die exakte Prüfung steht in test_m15_schemas
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 12, 0)
    get = dok["paths"]["/api/version"]["get"]
    assert set(dok["paths"]["/api/version"]) == {"get"}
    assert "parameters" not in get and "requestBody" not in get
    assert set(get["responses"]) == {"200"}
    assert get["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Versionsangaben"}
    v = s["Versionsangaben"]
    assert v["additionalProperties"] is False
    assert set(v["required"]) == set(v["properties"]) == FELDER
    assert v["properties"]["version"]["pattern"] == VERSION_MUSTER.pattern
    assert v["properties"]["datenbank_schema"] == {"type": "integer", "minimum": 1}
    assert v["properties"]["sicherung_schema"] == {"type": "integer", "minimum": 1}
    val = Draft202012Validator({**v, "components": dok["components"]})
    gut = {"name": "Kontor", "version": "0.01", "commit": None, "build_datum": None, "entwicklungsstand": True,
           "python": "3.12.4", "repository": "https://example.invalid/kontor", "modus": "mock",
           "datenbank": "/tmp/kontor-mock.sqlite3", "datenbank_schema": 1, "sicherung_schema": 1}
    assert val.is_valid(gut)
    assert val.is_valid({**gut, "commit": "0123abc", "build_datum": "2026-11-10T12:00:00Z",
                         "entwicklungsstand": False})
    for falsch in ({"version": "0.1"}, {"version": "1.0"}, {"name": "kontor"}, {"commit": "0123AB"},
                   {"commit": "XYZ1234"}, {"build_datum": "2026-11-10T12:00:00+01:00"},
                   {"repository": "http://example.invalid/kontor"},
                   {"repository": "https://nutzer:geheim@example.invalid/kontor"}, {"modus": "test"},
                   {"datenbank_schema": 0}, {"sicherung_schema": "1"}, {"zusatz": 1}):
        assert not val.is_valid({**gut, **falsch}), falsch
    # bestehende Schemas unverändert (E-029, version.md 5)
    assert set(s["Gesundheit"]["properties"]) == {"status", "version"}
    assert s["Gesundheit"]["required"] == ["status", "version"]
    assert s["Status"]["required"] == ["version", "modus", "mock", "hinweis", "plugins", "mock_szenario"]
    assert "pattern" not in s["Status"]["properties"]["version"]
    assert s["SicherungManifest"]["properties"]["app_version"] == {"type": "string", "minLength": 1}


def test_m15_schemas(dok):
    """protokoll.md 6.2a, datenmodell.md 18, synchronisation.md 20, E-189: neue Endpunkte, nur optionale
    Erweiterungen bestehender Schemas."""
    s = dok["components"]["schemas"]
    # E-198: M16 erhöht auf 2.14.0, die exakte Prüfung steht in test_m16_schemas
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 13, 0)
    # Rückgängig bis: drittes Feld, 404 für unbekannte bis_id
    r = s["Rueckgaengig"]
    assert set(r["properties"]) == {"aenderung_ids", "gruppe", "bis_id"} and "required" not in r
    assert r["properties"]["bis_id"]["type"] == "integer"
    assert set(dok["paths"]["/api/aenderungen/rueckgaengig"]["post"]["responses"]) == {"200", "404", "409", "422"}
    # mehrfach/loeschen
    post = dok["paths"]["/api/buchungen/mehrfach/loeschen"]["post"]
    assert set(post["responses"]) == {"200", "409", "422"}
    assert post["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MehrfachLoeschErgebnis"}
    m = s["MehrfachLoeschen"]
    assert m["additionalProperties"] is False and m["required"] == ["buchung_ids"] and set(m["properties"]) == {
        "buchung_ids"}
    v = Draft202012Validator({**m, "components": dok["components"]})
    assert v.is_valid({"buchung_ids": [1, 2]})
    for falsch in ({"buchung_ids": []}, {"buchung_ids": [1, 1]}, {}, {"buchung_ids": [1], "x": 1}):
        assert not v.is_valid(falsch), falsch
    e = s["MehrfachLoeschErgebnis"]
    assert e["additionalProperties"] is False and set(e["required"]) == set(e["properties"]) == {"geloescht", "anzahl"}
    # mehrfach/verschieben
    post = dok["paths"]["/api/buchungen/mehrfach/verschieben"]["post"]
    assert set(post["responses"]) == {"200", "409", "422"}
    assert post["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MehrfachVerschiebeErgebnis"}
    m = s["MehrfachVerschieben"]
    assert m["additionalProperties"] is False and m["required"] == ["von_konto_id", "nach_konto_id"]
    assert set(m["properties"]) == {"von_konto_id", "nach_konto_id", "buchung_ids", "gruppe"}
    v = Draft202012Validator({**m, "components": dok["components"]})
    assert v.is_valid({"von_konto_id": 1, "nach_konto_id": 2, "buchung_ids": [3]})
    assert v.is_valid({"von_konto_id": 1, "nach_konto_id": 2, "gruppe": "import:1"})
    for falsch in ({"von_konto_id": 1, "nach_konto_id": 2},
                   {"von_konto_id": 1, "nach_konto_id": 2, "buchung_ids": [3], "gruppe": "sync:1"},
                   {"von_konto_id": 1, "nach_konto_id": 2, "buchung_ids": []},
                   {"von_konto_id": 1, "nach_konto_id": 2, "gruppe": ""},
                   {"nach_konto_id": 2, "buchung_ids": [3]}):
        assert not v.is_valid(falsch), falsch
    e = s["MehrfachVerschiebeErgebnis"]
    assert e["additionalProperties"] is False and set(e["required"]) == set(e["properties"]) == {"verschoben",
                                                                                              "anzahl"}
    # herkunft
    get = dok["paths"]["/api/konten/{konto_id}/herkunft"]["get"]
    assert set(get["responses"]) == {"200", "404"} and "requestBody" not in get
    h = s["Herkunft"]
    assert h["additionalProperties"] is False
    assert set(h["required"]) == set(h["properties"]) == {"gruppe", "art", "beschreibung", "zeitpunkt", "anzahl"}
    v = Draft202012Validator({**h, "components": dok["components"]})
    gut = {"gruppe": "sync:7", "art": "sync", "beschreibung": "Synchronisation #7", "zeitpunkt": None, "anzahl": 1}
    assert v.is_valid(gut) and v.is_valid({**gut, "zeitpunkt": "2024-06-30T12:00:00Z"})
    for falsch in ({"gruppe": "manuell"}, {"art": "manuell"}, {"anzahl": 0}, {"beschreibung": ""}):
        assert not v.is_valid({**gut, **falsch}), falsch
    # Synchronisation: Aufzählungen erweitert, neues Feld optional (E-029)
    u = s["SyncUebersprungen"]
    assert u["properties"]["status"]["enum"] == ["konto_fehlt", "ignoriert", "nicht_zugeordnet"]
    assert u["required"] == ["iban", "name", "status"]
    assert u["properties"]["art"]["enum"] == ["girokonto", "sparkonto", "kreditkonto"]
    assert "konto_nicht_zugeordnet" in s["Benachrichtigung"]["properties"]["art"]["enum"]  # E-220
    assert "verschieben_unmoeglich" in s["Fehler"]["properties"]["fehler"]["properties"]["code"]["description"]
    # bestehende Schemas unverändert (E-029)
    assert s["MehrfachErgebnis"]["required"] == ["geaendert", "anzahl"]
    assert s["KontoAenderung"].get("required") is None
    # D-312: Kontotyp und Inhaber kamen hinzu
    assert set(s["KontoAenderung"]["properties"]) == {"name", "eltern_id", "iban", "geschlossen", "eroeffnet_am",
                                                     "notiz", "art", "inhaber"}
    assert s["Aenderung"]["required"] == ["id", "zeitpunkt", "quelle", "aktion", "beschreibung", "gruppe",
                                          "eintraege", "rueckgaengig_von", "rueckgaengig_durch"]


@pytest.mark.parametrize("v,gueltig", [
    ("0.00", True), ("0.01", True), ("0.07", True), ("0.99", True), ("0.100", True), ("0.1000", True),
    ("1.00", True), ("2.13", True), ("12.05", True), ("10.100", True),
    ("0.1", False), ("0.7", False), ("1.0", False), ("01.00", False), ("00.01", False), ("0.012", False),
    ("0.099", False), ("0.01.1", False), ("v0.01", False), ("0.01.dev0", False), (" 0.01", False),
    ("0.01 ", False), ("0.01\n", False), ("", False), ("1", False), ("-1.00", False), ("1.0a", False),
])
def test_m13_versionsschema(v, gueltig):
    """version.md 1.1 (E-177): Beispiele der Definition und Grenzfälle; der Ausdruck der Tests ist der des
    Schemas ``Versionsangaben``."""
    from tests.hilfen.m13 import version_gueltig

    assert version_gueltig(v) is gueltig
    assert bool(re.fullmatch(r"(0|[1-9][0-9]*)\.([0-9]{2}|[1-9][0-9]{2,})", v)) is gueltig


def test_m16_schemas(dok):
    """wiederkehrend.md 8, E-198: neuer Endpunkt der Begründung; bestehende Schemas unverändert."""
    s = dok["components"]["schemas"]
    # E-210: M18 erhöht auf 2.15.0, die exakte Prüfung steht im jeweils jüngsten Schematest
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 14, 0)
    get = dok["paths"]["/api/buchungen/{buchung_id}/wiederkehrend"]["get"]
    assert set(dok["paths"]["/api/buchungen/{buchung_id}/wiederkehrend"]) == {"get", "parameters"}
    assert "requestBody" not in get and set(get["responses"]) == {"200", "404", "422"}
    assert [p["name"] for p in get["parameters"]] == ["stichtag"]
    assert get["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WiederkehrendBegruendung"}
    felder = {
        "WiederkehrendBegruendung": {"buchung_id", "stichtag", "urteil", "text", "eintraege", "ausgeschlossen"},
        "BegruendungEintrag": {"konto", "richtung", "datum", "betrag", "gruppe", "gruppe_anzahl", "juengste",
                               "urteil", "glied", "text", "serie", "rhythmen", "buchungen"},
        "BegruendungRhythmus": {"rhythmus", "monate", "mindestanzahl", "laenge", "erfuellt", "schritte"},
        "BegruendungSchritt": {"ergebnis", "grund", "von", "vorgaenger", "erwartet", "abweichung_tage",
                               "uebersprungen", "fremd", "kandidaten", "text"},
    }
    for name, f in felder.items():
        assert s[name]["additionalProperties"] is False, name
        # E-242, E-244: M25 ergänzt optionale Felder; Pflichtfelder unverändert
        assert set(s[name]["required"]) == f and f <= set(s[name]["properties"]), name
    assert s["WiederkehrendBegruendung"]["properties"]["urteil"]["enum"] == [
        "wiederkehrend", "zusaetzlich", "nicht_wiederkehrend", "ausgeschlossen"]
    assert s["BegruendungEintrag"]["properties"]["urteil"]["enum"][:4] == [
        "glied", "zusaetzlich", "vor_beginn", "keine_serie"]
    assert s["BegruendungSchritt"]["properties"]["ergebnis"]["enum"] == ["anker", "verbunden", "bruch"]
    v = Draft202012Validator({**s["BegruendungSchritt"], "components": dok["components"]})
    ref = {"buchung_id": 3, "datum": "2024-03-15", "betrag": -999}
    gut = {"ergebnis": "verbunden", "grund": None, "von": ref, "vorgaenger": {**ref, "buchung_id": 2,
           "datum": "2024-02-15"}, "erwartet": "2024-03-15", "abweichung_tage": 0, "uebersprungen": [],
           "fremd": None, "kandidaten": [], "text": "Verbunden."}
    assert v.is_valid(gut)
    assert v.is_valid({**gut, "ergebnis": "bruch", "grund": "kein_vorgaenger", "vorgaenger": None, "erwartet": None,
                       "abweichung_tage": None})
    assert v.is_valid({**gut, "ergebnis": "anker", "vorgaenger": None, "erwartet": None, "abweichung_tage": None,
                       "kandidaten": [{**ref, "laenge": 3, "gleicher_betrag": True}]})
    for falsch in ({"grund": "unbekannt"}, {"ergebnis": "ende"}, {"text": ""}, {"abweichung_tage": 1.5},
                   {"kandidaten": [{**ref, "laenge": 0, "gleicher_betrag": True}]}, {"zusatz": 1}):
        assert not v.is_valid({**gut, **falsch}), falsch
    # bestehende Schemas unverändert (E-029, Definition M16 Einleitung)
    assert set(s["WiederkehrendSerie"]["required"]) == set(s["WiederkehrendSerie"]["properties"]) == {
        "schluessel", "konto_id", "empfaenger", "richtung", "rhythmus", "anzahl", "erste", "letzte", "betrag",
        "jahreskosten", "naechste_faelligkeit", "status", "buchung_ids"}
    assert s["WiederkehrendUebersicht"]["required"] == ["stichtag", "serien", "summe_jahreskosten"]


def test_m18_schemas(dok):
    """dokumente.md 2.15, E-210: neue Pfade und Schemas; Erweiterungen bestehender Schemas nur optional."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 15, 0)
    felder = {"id", "dateiname", "mime_typ", "groesse", "sha256", "quelle", "erstellt_am"}
    assert set(s["DokumentZustand"]["required"]) == set(s["DokumentZustand"]["properties"]) == felder
    assert set(s["Dokument"]["required"]) == set(s["Dokument"]["properties"]) == felder | {"buchung_ids"}
    assert s["Dokumenttyp"]["enum"] == ["application/pdf", "image/jpeg", "image/png", "image/webp", "message/rfc822"]
    assert set(s["DokumentGeloest"]["required"]) == {"dokument_id", "buchung_ids", "geloescht"}
    assert set(s["MailAnsicht"]["required"]) == set(s["MailAnsicht"]["properties"]) == {
        "von", "an", "cc", "datum", "betreff", "text", "html", "anhaenge"}
    assert set(s["MailAnhang"]["required"]) == {"nr", "dateiname", "mime_typ", "groesse", "inline"}
    for name in ("Dokument", "DokumentZustand", "DokumentGeloest", "MailAnsicht", "MailAnhang", "DokumentAusMail",
                 "DokumentAenderung", "DokumentBuchungen"):
        assert s[name]["additionalProperties"] is False, name
    # Rückwärtskompatibel (E-029): dokument_ids optional, Buchung und Beleg unverändert
    bz = s["BuchungZustand"]
    assert "dokument_ids" in bz["properties"] and "dokument_ids" not in bz["required"]
    assert bz["required"] == ["id", "datum", "empfaenger_id", "verwendungszweck", "status", "splits", "tag_ids",
                              "extern_ids", "vorschlag", "gegen_iban"]
    assert s["Beleg"]["required"] == ["id", "dateiname", "mime_typ", "groesse"]
    assert s["Objektart"]["enum"][10] == "dokument"
    assert {"$ref": "#/components/schemas/DokumentZustand"} in s["Objektzustand"]["anyOf"]
    inhalt = dok["paths"]["/api/dokumente/{dokument_id}/inhalt"]["get"]["responses"]["200"]["content"]
    assert set(inhalt) == {"application/pdf", "image/*", "application/octet-stream"}
    assert set(dok["paths"]["/api/dokumente/{dokument_id}/mail/html"]["get"]["responses"]["200"]["content"]) == {
        "text/html"}
    v = Draft202012Validator({**s["Dokument"], "components": dok["components"]})
    gut = {"id": 1, "dateiname": "Beleg.pdf", "mime_typ": "application/pdf", "groesse": 9, "sha256": "0" * 64,
           "quelle": "upload", "erstellt_am": "2024-06-30T12:00:00Z", "buchung_ids": [1]}
    assert v.is_valid(gut)
    for falsch in ({"buchung_ids": []}, {"mime_typ": "image/gif"}, {"quelle": "scanner"}, {"groesse": 0},
                   {"dateiname": ""}, {"dateiname": "x" * 201}, {"sha256": "A" * 64}):
        assert not v.is_valid({**gut, **falsch}), falsch


def test_m19_schemas(dok):
    """alfbanco.md 2.1, E-215: neue Aufzählungswerte und Endpunkte, nichts Bestehendes entfernt."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 16, 0)
    assert s["ImportErgebnis"]["properties"]["format"]["enum"] == [
        "kmy-gzip", "kmy-xml", "gnc-xml-gzip", "gnc-xml", "gnc-sqlite", "qif", None]
    assert s["Importvorgang"]["properties"]["art"]["enum"] == ["kmymoney", "gnucash", "alfbanco"]
    k = s["KategorienZusammenfuehren"]
    assert k["additionalProperties"] is False and k["required"] == ["quelle_ids", "ziel_id"]
    assert set(k["properties"]) == {"quelle_ids", "ziel_id", "quellen_loeschen", "gesperrte_einbeziehen", "trocken"}
    v = Draft202012Validator({**k, "components": dok["components"]})
    assert v.is_valid({"quelle_ids": [1, 2], "ziel_id": 3})
    for falsch in ({"quelle_ids": [], "ziel_id": 1}, {"quelle_ids": [1, 1], "ziel_id": 2},
                   {"quelle_ids": list(range(1001)), "ziel_id": 2000}, {"quelle_ids": [1]},
                   {"quelle_ids": [1], "ziel_id": 2, "x": 1}):
        assert not v.is_valid(falsch), falsch
    e = s["ZusammenfuehrenErgebnis"]
    assert e["additionalProperties"] is False and set(e["required"]) == set(e["properties"]) == {
        "ziel_id", "quelle_ids", "quellen_geloescht", "buchungen_umgebucht", "konfliktbuchungen", "gesperrt",
        "unterkategorien_verschoben", "regeln_geaendert", "empfaenger_geaendert", "extern_id_uebernommen", "trocken",
        "aenderung_id"}
    post = dok["paths"]["/api/import/alfbanco"]["post"]
    assert set(post["responses"]) == {"200", "422"}
    assert post["requestBody"]["content"]["multipart/form-data"]["schema"]["required"] == ["datei", "konto_id"]
    assert set(dok["paths"]["/api/kategorien/zusammenfuehren"]["post"]["responses"]) == {"200", "409", "422"}


def test_m20_schemas(dok):
    """erwartungen.md 6, 11, E-220: neue Pfade und Schemas; Aufzählungen nur erweitert."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 17, 0)
    form = {"id", "grund", "richtung", "anbieter", "kennung", "referenz", "haendler", "beschreibung", "betrag",
            "gesamt", "guthaben", "datum", "frist", "zustand", "bezug_id", "buchung_ids", "mails", "dokument_ids",
            "erstellt_am"}
    abgeleitet = {"zugeordnet", "offen_betrag", "ueberfaellig", "vorzeichen_betrag"}
    # M32 (E-294): optionales Feld wiederholung nur bei Erwartungen mit Wiederholung
    assert set(s["ErwartungZustand"]["required"]) == set(s["ErwartungZustand"]["properties"]) - {"wiederholung"} == form
    assert set(s["Erwartung"]["required"]) == set(s["Erwartung"]["properties"]) - {"wiederholung"} == form | abgeleitet
    assert set(s["ErwartungDetail"]["required"]) == form | abgeleitet | {"buchungen", "mail_eintraege"}
    for name in ("ErwartungZustand", "Erwartung", "ErwartungDetail", "ErwartungListe", "ErwartungNeu",
                 "ErwartungAenderung", "Kandidat", "ErwartungMail"):
        assert s[name]["additionalProperties"] is False, name
        assert "schluessel" not in s[name]["properties"], name
    assert s["ErwartungNeu"]["required"] == ["richtung", "haendler", "betrag"]
    assert "richtung" not in s["ErwartungAenderung"]["properties"]
    assert set(s["Kandidat"]["required"]) == {"id", "datum", "betrag", "konto_id", "konto", "empfaenger",
                                              "verwendungszweck", "kennung_passt", "betrag_gleich", "anbieter_passt",
                                              "abstand_tage"}
    assert s["Aenderungsquelle"]["enum"][-1] == "mail" and s["Objektart"]["enum"][-1] == "erwartung"
    assert s["Benachrichtigung"]["properties"]["art"]["enum"][-1] == "erwartung_ueberfaellig"
    v = Draft202012Validator({**s["AbgleichErgebnis"], "components": dok["components"]})
    assert v.is_valid({"neu": 1, "ergaenzt": 0, "storniert": 0, "zugeordnet": 2, "gemeldet": 0}) and v.is_valid({})
    assert not v.is_valid({"neu": 1})


def test_m23_schemas(dok):
    """geheimnisschutz.md 2, 5, 6, E-232: neue Pfade und Schemas; bestehende Schemas unverändert."""
    s, pf = dok["components"]["schemas"], dok["paths"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 18, 0)
    g = s["GeheimnisSchutz"]
    assert g["additionalProperties"] is False and set(g["required"]) == set(g["properties"]) == {
        "aktiv", "entsperrt", "gesperrt", "geschuetzt", "pin_gemerkt"}
    e = s["AppPasswortErgebnis"]
    assert e["additionalProperties"] is False and set(e["required"]) == set(e["properties"]) == {
        "postfach_id", "ordner", "nachrichten_im_ordner"}
    for name, laenge in (("SchutzPasswort", 4096), ("AppPasswortEingabe", 256)):
        assert s[name]["required"] == ["passwort"] and s[name]["properties"]["passwort"]["maxLength"] == laenge
    for pfad in ("/api/geheimnisse/schutz", "/api/geheimnisse/schutz/ausschalten", "/api/geheimnisse/entsperren",
                 "/api/geheimnisse/sperren"):
        assert pf[pfad]["post"]["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/GeheimnisSchutz"}, pfad
    assert set(pf["/api/sync/pin/gemerkt"]) == {"put", "delete"}
    assert set(pf["/api/mail/postfaecher/{postfach_id}/app-passwort"]) == {"parameters", "put", "delete"}
    assert set(s["GeheimnisEintrag"]["required"]) == {"name", "gesetzt_am", "lesbar"}
    assert set(s["SyncStatus"]["required"]) >= {"pin_vorhanden"}
    assert set(s["PostfachStatus"]["properties"]["anmeldung"]["enum"]) == {
        "nicht_erforderlich", "fehlt", "angemeldet", "abgelaufen", "widerrufen"}


def test_m24_schemas(dok):
    """erwartungen.md 13, E-237: Serien nur über die Abfrage; ErwartungGrund der gespeicherten unverändert."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 19, 0)
    assert s["ErwartungGrund"]["enum"] == ["bestellung", "paypal", "rueckerstattung", "manuell"]
    assert s["ErwartungGrundAbfrage"]["enum"] == ["bestellung", "paypal", "rueckerstattung", "manuell", "serie"]
    params = {x["name"]: x for x in dok["paths"]["/api/erwartungen"]["get"]["parameters"]}
    assert params["serien"]["schema"]["enum"] == ["ja", "nein"]
    assert params["grund"]["schema"]["items"] == {"$ref": "#/components/schemas/ErwartungGrundAbfrage"}
    assert s["ErwartungListe"]["properties"]["eintraege"]["items"]["oneOf"] == [
        {"$ref": "#/components/schemas/Erwartung"}, {"$ref": "#/components/schemas/ErwartungSerie"}]
    e = s["ErwartungSerie"]
    assert e["additionalProperties"] is False
    assert set(e["required"]) == set(e["properties"]) == (set(s["Erwartung"]["properties"]) - {"wiederholung"}
                                                          | {"konto_id", "serie"})  # M32: wiederholung (E-294)
    v = Draft202012Validator({**s["ErwartungListe"], "components": dok["components"]})
    serie = {"id": "serie:1:1:ausgabe", "grund": "serie", "richtung": "ausgabe", "anbieter": None, "kennung": "",
             "referenz": "", "haendler": "Streamingdienst (fiktiv)", "beschreibung": "monatlich, zuletzt 2026-10-05",
             "betrag": 999, "gesamt": 999, "guthaben": 0, "datum": "2026-11-05", "frist": "2026-11-19",
             "zustand": "offen", "bezug_id": None, "buchung_ids": [], "mails": [], "dokument_ids": [],
             "erstellt_am": None, "zugeordnet": 0, "offen_betrag": 999, "ueberfaellig": False,
             "vorzeichen_betrag": -999, "konto_id": 1, "serie": "1:1:ausgabe"}
    liste = {"eintraege": [serie], "anzahl": 1, "summe_offen": -999, "ueberfaellig": 0, "aktiv": False}
    assert v.is_valid(liste)
    for falsch in ({"id": 7}, {"id": "serie:1:1:x"}, {"grund": "manuell"}, {"zustand": "erfuellt"},
                   {"buchung_ids": [1]}, {"erstellt_am": "2026-11-05T00:00:00Z"}, {"konto_id": None}):
        assert not v.is_valid({**liste, "eintraege": [{**serie, **falsch}]}), falsch


def test_m25_schemas(dok):
    """wiederkehrend.md 9.3, 9.4, E-242: Einstellungen, optionale Begründungsfelder, Empfänger-Protokollform."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 20, 0)  # exakt: test_m27_schemas (E-251)
    assert s["Betragsfilter"]["required"] == ["modus"]
    assert set(s["Betragsfilter"]["properties"]) == {"modus", "toleranz_prozent", "mindestbetrag"}
    assert s["BetragsfilterVorgabe"]["properties"]["modus"]["enum"] == ["aus", "toleranz"]
    assert set(s["BetragsfilterAngabe"]["required"]) == {"modus", "toleranz_prozent", "mindestbetrag", "quelle"}
    assert "empfaenger" not in s["WiederkehrendBegruendung"]["required"]
    assert "empfaenger" in s["WiederkehrendBegruendung"]["properties"]
    e = s["BegruendungEintrag"]
    assert {"betragsfilter", "betragsfilter_text"} <= set(e["properties"]) - set(e["required"])
    assert e["properties"]["urteil"]["enum"][-1] == "anderer_betrag"
    assert "betrag" in s["BegruendungSchritt"]["properties"]["grund"]["enum"]
    assert "wiederkehrend" not in s["Empfaenger"]["properties"], "GET /api/empfaenger bleibt unverändert"
    assert {"$ref": "#/components/schemas/EmpfaengerZustand"} in s["Objektzustand"]["anyOf"]
    v = Draft202012Validator({**s["EmpfaengerZustand"], "components": dok["components"]})
    gut = {"id": 1, "name": "Arbeitgeber (fiktiv)", "extern_id": None, "aliase": [], "standardkategorie_id": None,
           "wiederkehrend": {"modus": "toleranz", "toleranz_prozent": 10, "mindestbetrag": None}}
    assert v.is_valid(gut)
    assert not v.is_valid({k: x for k, x in gut.items() if k != "wiederkehrend"})


def test_m27_schemas(dok):
    """sammel.md, mail.md 6.6, E-251: alles optional bzw. nur auf Anfrage; Pflichtfelder unverändert."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 21, 0)  # exakt: test_m29_schemas (E-262)
    b = s["Buchung"]
    assert "verdacht" in b["properties"] and "verdacht" not in b["required"]
    assert s["BuchungVerdacht"]["properties"]["grund"]["enum"] == ["empfaenger", "betrag"]
    for pfad in ("/api/buchungen", "/api/buchungen/{buchung_id}", "/api/suche"):
        params = {x["name"]: x for x in dok["paths"][pfad]["get"].get("parameters", [])}
        assert params["verdacht"]["schema"]["enum"] == ["ja", "nein"], pfad
        assert params["verdacht"]["schema"]["default"] == "nein"
    liste = {x["name"] for x in dok["paths"]["/api/buchungen"]["get"]["parameters"]}
    assert {"zweck_gleich", "zweck_leer", "zweck_aehnlich", "empfaenger_aehnlich"} <= liste
    for name in ("Empfaenger", "EmpfaengerZustand"):
        assert "tags" in s[name]["properties"] and "tags" not in s[name]["required"], name
        assert s[name]["properties"]["tags"]["minItems"] == 1
    assert s["Empfaenger"]["required"] == ["id", "name", "extern_id"]
    assert "tag_ids" in s["EmpfaengerAenderung"]["properties"]
    assert "tag_ids" not in s["EmpfaengerNeu"]["properties"], "POST /api/empfaenger kennt tag_ids nicht"
    assert s["Dublettenverdacht"]["properties"]["grund"]["enum"] == ["mehrdeutig", "aehnlich"]
    assert set(s["Dublettenverdacht"]["required"]) == set(s["Dublettenverdacht"]["properties"])
    v = Draft202012Validator({**s["DublettenVorschlag"], "components": dok["components"]})
    vorschlag = {"vorschlag": True, "id": None, "buchung_id": 1, "kandidat_ids": [2], "grund": "gleich",
                 "status": "offen", "erstellt_am": None}
    assert v.is_valid(vorschlag)
    for falsch in ({"id": 3}, {"grund": "aehnlich"}, {"vorschlag": False}, {"erstellt_am": "2024-01-01T00:00:00Z"}):
        assert not v.is_valid({**vorschlag, **falsch}), falsch
    assert "stand" not in s["MailNachrichtenSeite"]["required"]
    assert not {"postfach", "zuordnung"} & set(s["MailNachrichtEintrag"]["required"])
    params = {x["name"]: x for x in dok["paths"]["/api/mail/nachrichten"]["get"]["parameters"]}
    assert params["reihenfolge"]["schema"]["enum"] == ["aelteste", "neueste"]
    assert params["zuordnung"]["schema"]["enum"] == ["zugeordnet", "erwartet", "keine"]
    assert "Statistik" not in s, "M32 (E-298): Schema Statistik entfällt"


def test_m29_schemas(dok):
    """bankzugang.md 4, E-259, E-262: Bankzugang unter dem Tag bank; aqbanking entfällt aus PluginInfo."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 22, 0)  # exakt: test_m30_schemas (E-270)
    assert s["PluginInfo"]["properties"]["name"]["enum"] == ["mock", "fints", "imap"]
    assert s["PluginInfo"]["required"] == ["name", "mock"]
    assert "bank" in {t["name"] for t in dok["tags"]}
    erwartet = {"/api/bank/zugang": {"get", "put"}, "/api/bank/zugang/tan-verfahren": {"post"},
                "/api/bank/zugang/konten/abrufen": {"post"}, "/api/bank/zugang/konten": {"put"},
                "/api/bank/zugang/diagnose": {"get", "put"}}
    for pfad, methoden in erwartet.items():
        assert set(dok["paths"][pfad]) == methoden, pfad
        for m in methoden:
            assert dok["paths"][pfad][m]["tags"] == ["bank"], (pfad, m)
    felder = {"url", "blz", "benutzer", "kunden_id", "produkt_id", "tan_verfahren"}
    z = s["Bankzugang"]
    assert z["additionalProperties"] is False
    assert set(z["required"]) == set(z["properties"]) == felder | {"plugin", "aenderbar", "gespeichert",
                                                                    "vollstaendig", "konten"}
    assert set(s["BankzugangAenderung"]["properties"]) == felder, "kein Feld pin (bankzugang.md 4.2)"
    assert s["BankzugangAenderung"]["additionalProperties"] is False and "required" not in s["BankzugangAenderung"]
    assert set(s["BankzugangKonto"]["required"]) == {"iban", "bic", "name", "art", "inhaber", "aktiv"}
    v = Draft202012Validator({**s["BankKontenAbruf"], "components": dok["components"]})
    konto = {"iban": "DE95000000000000006601", "bic": None, "name": "", "art": "girokonto", "inhaber": "",
             "aktiv": True}
    assert v.is_valid({"konten": [konto], "tan_erforderlich": None})
    assert v.is_valid({"konten": None, "tan_erforderlich": {"vorgang": "v", "challenge": "c", "bild": None}})
    assert not v.is_valid({"konten": None, "tan_erforderlich": {"vorgang": "v", "challenge": "", "bild": None}})
    assert not v.is_valid({"konten": [konto]})
    a = Draft202012Validator(s["BankKontenAbrufAnfrage"])
    assert a.is_valid({}) and a.is_valid({"vorgang": "v", "tan": "1"})
    assert not a.is_valid({"vorgang": "v"}) and not a.is_valid({"tan": "1"}) and not a.is_valid({"pin": "x"})
    assert s["BankDiagnose"]["properties"]["zeilen"]["maxItems"] == 600
    assert s["BankKontenAuswahl"]["required"] == ["ibans"]
    code = s["Fehler"]["properties"]["fehler"]["properties"]["code"]["description"]
    for c in ("bankzugang_nicht_aenderbar", "bankzugang_unvollstaendig", "tan_offen"):
        assert c in code, c


def test_m30_schemas(dok):
    """ausdruecke.md, kategorisierung.md 8, E-270: Ausdrücke, Filter, Regeln mit Ausdruck und Tags."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 23, 0)
    assert "ausdruck" in {t["name"] for t in dok["tags"]}
    for pfad in ("/api/ausdruck/sprache", "/api/ausdruck/pruefen", "/api/ausdruck/als-regel"):
        for m, op in dok["paths"][pfad].items():
            assert op["tags"] == ["ausdruck"], (pfad, m)
    for pfad in ("/api/buchungen", "/api/export/buchungen.csv", "/api/export/buchungen.pdf"):
        params = {x["name"]: x for x in dok["paths"][pfad]["get"]["parameters"]}
        assert params["filter"]["schema"]["maxLength"] == 4000, pfad
        assert params["stichtag"]["schema"] == {"type": "string", "format": "date"}, pfad
    b = s["Buchung"]
    assert "markierungen" in b["properties"] and "markierungen" not in b["required"]
    assert s["Markierung"]["required"] == ["feld", "start", "ende"]
    r = s["Regel"]
    assert r["required"] == ["id", "name", "aktiv", "prioritaet", "kategorie_id", "bedingungen"], "E-029"
    assert {"ausdruck", "ausdruck_form", "tag_ids"} <= set(r["properties"])
    assert r["properties"]["ausdruck_form"]["enum"] == ["ausdruck", "bedingungen"]
    v = Draft202012Validator({**r, "components": dok["components"]})
    alt = {"id": 1, "name": "n", "aktiv": True, "prioritaet": 100, "kategorie_id": 3,
           "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt", "wert": "REWE"}]}
    assert v.is_valid(alt), "Regel der bisherigen Form (auch Protokollform) bleibt gültig"
    neu = {**alt, "kategorie_id": None, "tag_ids": [2, 5], "ausdruck": '"REWE" in empfänger',
           "ausdruck_form": "ausdruck",
           "bedingungen": [{"feld": "ausdruck", "operator": "ausdruck", "wert": {"art": "vergleich"}}]}
    assert v.is_valid(neu)
    assert not v.is_valid({**neu, "ausdruck_form": "text"}) and not v.is_valid({**neu, "tag_ids": [2, 2]})
    assert not v.is_valid({**neu, "bedingungen": [{"feld": "ausdruck", "operator": "gleich", "wert": {}}]})
    n = Draft202012Validator({**s["RegelNeu"], "components": dok["components"]})
    assert n.is_valid({"name": "n", "kategorie_id": 3, "ausdruck": "betrag > 5"})
    assert n.is_valid({"name": "n", "tag_ids": [1], "bedingungen": alt["bedingungen"]})
    assert not n.is_valid({"name": "n", "kategorie_id": 3}), "eines von ausdruck und bedingungen"
    assert not n.is_valid({"name": "n", "kategorie_id": 3, "ausdruck": "betrag > 5", "bedingungen": alt["bedingungen"]})
    assert "tags" in s["RegelAnwendung"]["properties"] and "tags" not in s["RegelAnwendung"]["required"]
    f = s["AusdruckFehler"]
    assert f["required"] == ["code", "meldung", "zeile", "spalte", "ende_zeile", "ende_spalte", "erwartet"]
    assert f["properties"]["code"]["enum"] == [
        "syntax", "feld_unbekannt", "methode_unbekannt", "operator_unpassend", "kein_wahrheitswert", "wert_ungueltig",
        "regex_ungueltig", "regex_nicht_unterstuetzt", "referenz_unbekannt", "nur_im_filter", "datum_ungueltig",
        "zeitraum_leer", "dauer_ohne_vorzeichen", "einheit_unbekannt", "zu_lang"]
    pr = s["AusdruckPruefung"]
    assert set(pr["required"]) == set(pr["properties"]) == {
        "gueltig", "fehler", "kanonisch", "baum", "baukasten_faehig", "hinweise", "datumsangaben", "freitext",
        "zusammenfassung"}
    assert set(s["AusdruckDatumsangabe"]["required"]) == {"text", "von", "bis", "tage", "relativ"}
    sp = s["AusdruckSprache"]
    assert set(sp["required"]) == {"kontext", "felder", "schluesselwoerter", "aliase", "methoden", "kwargs"}
    assert set(sp["properties"]["felder"]["items"]["required"]) == {"name", "kurz", "typ", "bezeichnung",
                                                                      "operatoren", "werte", "nur_filter"}
    assert s["RegelWirkung"]["enum"] == ["neu", "abweichend", "bereits_so", "verdeckt", "uebersprungen", "treffer"]
    assert set(s["RegelTestErgebnis"]["required"]) == {
        "testmenge_anzahl", "anzahl", "zaehlung", "tags_anzahl", "gesperrt_anzahl", "gesamt", "seite", "pro_seite",
        "treffer", "nicht_erfasst"}
    assert s["ErklaerKnoten"]["properties"]["ergebnis"]["enum"] == ["wahr", "falsch", "nicht_ausgewertet"]
    assert s["RegelEinzelAnwendung"]["required"] == ["geaendert", "anzahl"]
    assert s["AusdruckAlsRegel"]["required"] == ["ausdruck", "entfernt"]
    code = s["Fehler"]["properties"]["fehler"]["properties"]["code"]["description"]
    for c in ("ausdruck_ungueltig", "regel_ohne_aktion"):
        assert c in code, c


def test_m31_schemas(dok):
    """lernmodell.md 8–10, berichte.md 6, erwartungen.md 14, E-278: übrige Features vor sammel3."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 24, 0)  # exakt: test_m32_schemas
    sp = s["LernZustand"]["properties"]["schwelle_promille"]
    assert (sp["minimum"], sp["maximum"]) == (500, 990)
    assert s["LernVorhersage"]["properties"]["sicherheit"]["minimum"] == 500
    assert set(s["LernEinstellungen"]["required"]) == {"schwelle_promille", "regeln_automatisch"}
    assert "required" not in s["LernEinstellungenAenderung"]
    e = s["LernErklaerung"]
    assert e["properties"]["grund"]["enum"] == ["vorschlag", "unter_schwelle", "unbekannt", "kein_modell"]
    assert {"beste_kategorie_id", "vergleich_kategorie_id", "merkmale", "aehnliche"} <= set(e["required"])
    assert {"anzahl", "anzahl_kategorie", "anzahl_vergleich", "faktor_promille"} <= set(s["LernMerkmal"]["required"])
    for name in ("Empfaenger", "EmpfaengerZustand"):
        assert s[name]["properties"]["lernregel_gesperrt"] == {
            "description": s[name]["properties"]["lernregel_gesperrt"]["description"], "const": True}
        assert "lernregel_gesperrt" not in s[name]["required"]
    r = s["Regel"]
    assert {"automatisch", "empfaenger_id"} <= set(r["properties"]) and "automatisch" not in r["required"]
    m = s["MailNachrichtEintrag"]
    assert "angehaengt" in m["properties"] and "angehaengt" not in m["required"]
    assert set(s["MailAngehaengt"]["required"]) == {"id", "datum", "konto_id", "empfaenger", "verwendungszweck",
                                                     "nummer", "warum"}
    assert {"monat", "ausgaben", "einnahmen", "fest", "variabel", "umbuchungen"} <= set(s["MonatsBericht"]["required"])
    code = s["Fehler"]["properties"]["fehler"]["properties"]["code"]["description"]
    assert "bestand_nicht_leer" in code


def test_m32_schemas(dok):
    """sammel3.md, E-294: Sammelbranch sammel3 (nicht rückwärtskompatibel)."""
    s = dok["components"]["schemas"]
    assert tuple(map(int, dok["info"]["version"].split("."))) >= (2, 25, 0)   # D-312: 2.26.0
    assert ("get", "/api/statistik") not in {(m, p) for p, x in dok["paths"].items() for m in x}
    m = s["MailNachrichtEintrag"]
    assert "gruppe" in m["properties"] and "gruppe" not in m["required"]
    a = s["MailAngehaengt"]
    assert "betrag" in a["properties"] and "betrag" not in a["required"] and "pattern" not in a["properties"]["nummer"]
    params = {x["name"]: x for x in dok["paths"]["/api/mail/nachrichten"]["get"]["parameters"]}
    assert params["gruppieren"]["schema"]["enum"] == ["ja", "nein"] and "suche" in params
    html = {x["name"]: x for x in dok["paths"]["/api/dokumente/{dokument_id}/mail/html"]["get"]["parameters"]}
    assert html["bilder"]["schema"]["enum"] == ["ja", "nein"]
    for name in ("Erwartung", "ErwartungZustand", "ErwartungDetail"):
        assert "wiederholung" in s[name]["properties"] and "wiederholung" not in s[name]["required"], name
    for name in ("ErwartungNeu", "ErwartungAenderung"):
        assert s[name]["properties"]["wiederholung"]["enum"] == ["keine", "monatlich", "vierteljaehrlich",
                                                                 "halbjaehrlich", "jaehrlich"], name
        assert "wiederholung_bis" in s[name]["properties"]
    v = Draft202012Validator({**s["Erwartung"]["properties"]["anbieter"], "components": dok["components"]})
    assert v.is_valid("kaufhaus") and v.is_valid(None) and not v.is_valid("Kauf Haus")
    assert set(s["Konfiguration"]["required"]) == {"umgebung", "wirksam"}
    assert set(s["EmpfaengerKonto"]["required"]) == {"konto_id", "anzahl"}
    assert set(s["EmpfaengerAnzahl"]["required"]) == {"empfaenger_id", "anzahl"}
    code = s["Fehler"]["properties"]["fehler"]["properties"]["code"]["description"]
    for c in ("konto_existiert", "wiederholung_nur_geplant", "wiederholung_fehlt"):
        assert c in code, c
