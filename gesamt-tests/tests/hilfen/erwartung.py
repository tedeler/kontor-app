"""Laden der Erwartungsdateien des Generators und Vergleich mit dem Buchbestand."""

from __future__ import annotations

import json
from collections import Counter

from .pfade import FIXTURES, KMY


def lade(name: str) -> dict:
    """name ohne Endung, z. B. 'minimal' → fixtures/kmy/minimal.erwartung.json"""
    with open(KMY / f"{name}.erwartung.json", encoding="utf-8") as f:
        return json.load(f)


def lade_mock() -> tuple[dict, dict]:
    with open(FIXTURES / "mock" / "mock_daten.json", encoding="utf-8") as f:
        daten = json.load(f)
    with open(FIXTURES / "mock" / "mock_daten.erwartung.json", encoding="utf-8") as f:
        erw = json.load(f)
    return daten, erw


ZAEHLFELDER = [
    "konten_neu", "konten_vorhanden", "kategorien_neu", "kategorien_vorhanden",
    "empfaenger_neu", "empfaenger_vorhanden", "tags_neu", "tags_vorhanden",
    "buchungen_neu", "buchungen_vorhanden", "buchungen_zusammengefuehrt",
    "buchungen_zur_pruefung", "buchungen_uebersprungen", "splits_neu",
]


def pruefe_ergebnis(ergebnis: dict, erwartet: dict, *, warnungen: list[dict] | None = None) -> None:
    assert ergebnis["erfolgreich"] is True, f"Import fehlgeschlagen: {ergebnis['fehler']}"
    assert ergebnis["fehler"] == []
    assert ergebnis["format"] == erwartet["format"]
    abw = {f: (ergebnis[f], erwartet[f]) for f in ZAEHLFELDER if ergebnis[f] != erwartet[f]}
    assert not abw, f"Zählungen weichen ab (ist, soll): {abw}"
    if warnungen is not None:
        ist = Counter((w["code"], w["referenz"]) for w in ergebnis["warnungen"])
        soll = Counter((w["code"], w["referenz"]) for w in warnungen)
        assert ist == soll, f"Warnungen weichen ab.\nzu viel: {ist - soll}\nfehlen: {soll - ist}"
        for w in ergebnis["warnungen"]:
            assert w["meldung"].strip(), "Warnung ohne Meldungstext"


def pruefe_buchbestand(api, erw: dict, *, nur_import: bool = True) -> None:
    """Vergleicht den Bestand der App mit der Erwartung eines Imports in ein leeres Buch."""
    konten = api.konten()
    nach_id = {k["id"]: k for k in konten}
    nach_ext = {k["extern_id"]: k for k in konten if k["extern_id"]}
    if nur_import:
        assert len(konten) == len(erw["konten"]), (
            f"Anzahl Konten {len(konten)} ≠ erwartet {len(erw['konten'])}: "
            f"{sorted(k['name'] for k in konten)}")
    for ke in erw["konten"]:
        assert ke["extern_id"] in nach_ext, f"Konto {ke['extern_id']} ({ke['name']}) fehlt"
        k = nach_ext[ke["extern_id"]]
        eltern = nach_id[k["eltern_id"]]["extern_id"] if k["eltern_id"] else None
        ist = {"name": k["name"], "art": k["art"], "eltern_extern_id": eltern,
               "geschlossen": k["geschlossen"], "iban": k["iban"], "eroeffnet_am": k["eroeffnet_am"],
               "notiz": k["notiz"], "ist_kategorie": k["ist_kategorie"]}
        soll = {f: ke[f] for f in ist}
        assert ist == soll, f"Konto {ke['extern_id']} weicht ab:\nist  {ist}\nsoll {soll}"
        assert k["waehrung"] == "EUR"

    salden = api.salden()
    for ke in erw["konten"]:
        s = salden[nach_ext[ke["extern_id"]]["id"]]
        ist = (s["saldo"], s["saldo_gesamt"], s["anzahl_buchungen"])
        soll = (ke["saldo"], ke["saldo_gesamt"], ke["anzahl_buchungen"])
        assert ist == soll, f"Saldo {ke['name']} (saldo, saldo_gesamt, anzahl) ist {ist}, soll {soll}"

    empf = api.get("/api/empfaenger", erwartet=200).daten
    if nur_import:
        assert sorted((e["extern_id"], e["name"]) for e in empf) == sorted(
            (e["extern_id"], e["name"]) for e in erw["empfaenger"])
    tags = api.get("/api/tags", erwartet=200).daten
    tag_ext = {t["id"]: t["extern_id"] for t in tags}
    if nur_import:
        assert sorted((t["extern_id"], t["name"], t["anzahl_buchungen"]) for t in tags) == sorted(
            (t["extern_id"], t["name"], t["anzahl_buchungen"]) for t in erw["tags"])

    buchungen = api.alle_buchungen()
    if nur_import:
        assert len(buchungen) == len(erw["buchungen"])
    nach_bext: dict[str, dict] = {}
    for b in buchungen:
        for e in b["extern_ids"]:
            nach_bext[e] = b
    for be in erw["buchungen"]:
        assert be["extern_id"] in nach_bext, f"Buchung {be['extern_id']} fehlt"
        b = nach_bext[be["extern_id"]]
        ist = {
            "datum": b["datum"],
            "empfaenger": b["empfaenger"]["name"] if b["empfaenger"] else None,
            "verwendungszweck": b["verwendungszweck"],
            "status": b["status"],
            "tags": sorted(tag_ext[t["id"]] for t in b["tags"]),
            "splits": [{"konto_extern_id": nach_id[s["konto_id"]]["extern_id"], "betrag": s["betrag"],
                        "memo": s["memo"]} for s in b["splits"]],
            "kategorie_extern_id": nach_id[b["kategorie_id"]]["extern_id"] if b["kategorie_id"] else None,
            "umsatz": b["betrag"],
        }
        soll = {f: be[f] for f in ist}
        assert ist == soll, f"Buchung {be['extern_id']} weicht ab:\nist  {ist}\nsoll {soll}"
        assert b["belege"] == []
