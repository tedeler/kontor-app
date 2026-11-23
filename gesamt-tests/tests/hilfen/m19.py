"""Hilfen für Meilenstein-19-Tests (ALF-BanCo-Import, Kategorien zusammenführen) – nur über alfbanco.md.

- ``qif`` baut synthetische QIF-Dateien aus Sätzen (Liste von Feldzeilen) in einer wählbaren Kodierung.
- ``BEISPIEL`` ist das Beispiel aus ``alfbanco.md`` 8 (nur fiktive Namen).
- ``zusammenfuehren_soll`` berechnet die Wirkung von ``POST /api/kategorien/zusammenfuehren`` je Quelle mit dem
  Orakel für „Konto löschen mit Buchungen“ (``loeschen_orakel``, Variante ``elternkonto``/``behalten``) und dem
  gewählten Ziel (alfbanco.md 5.3), ohne Ausgaben der Anwendung als Erwartung.
"""

from __future__ import annotations

import copy
import re

from . import kontor
from . import loeschen_orakel as lo
from .api import Api
from .m18 import multipart
from .vertrag import ZUSATZFELD

KENNUNG = re.compile(r"^alf:([0-9]+):[0-9a-f]{32}$")
KATEGORIE = ("aufwand", "ertrag")
BESTAND = ("girokonto", "sparkonto", "kreditkonto")

CAT = ["!Type:Cat", ["NHaushalt", "E"], ["NHaushalt:Lebensmittel", "E"], ["NGehalt", "I"]]
SAETZE = [
    ["D02.01.2024", "T-12,34", "PSupermarkt Beispiel", "MEinkauf Woche 1", "LHaushalt:Lebensmittel"],
    ["D03.01.2024", "T2.500,00", "PArbeitgeber Muster GmbH", "MLohn Januar", "LGehalt/Steuer"],
    ["D04.01.2024", "T-100,00", "PSparen", "L[Sparkonto]"],
    ["D05.01.2024", "T-50,00", "PKaufhaus Beispiel", "MGemischter Einkauf", "SHaushalt:Lebensmittel", "EEssen",
     "$-30,00", "SKleidung", "EHose", "$-20,00"],
    ["D06.01.2024", "T-3,00", "PCafé Beispiel"],
    ["D06.01.2024", "T-3,00", "PCafé Beispiel"],
]
BEISPIEL = CAT + ["!Type:Bank"] + SAETZE


def qif(teile: list, *, kodierung: str = "cp1252", zeilenende: str = "\r\n", bom: bool = False) -> bytes:
    """``teile``: Kopfzeilen (str, beginnen mit ``!``) und Sätze (Listen von Feldzeilen, enden mit ``^``)."""
    zeilen: list[str] = []
    for t in teile:
        if isinstance(t, str):
            zeilen.append(t)
        else:
            zeilen.extend(t)
            zeilen.append("^")
    text = zeilenende.join(zeilen) + zeilenende
    daten = text.encode(kodierung)
    return (b"\xef\xbb\xbf" if bom else b"") + daten


def bank(*saetze: list[str]) -> bytes:
    return qif(["!Type:Bank", *saetze])


# ------------------------------------------------------------------ Import
def import_rest(api: Api, konto_id, daten: bytes, *, dateiname: str | None = "giro.qif", erwartet: int | tuple = 200,
                felder: list | None = None):
    """POST /api/import/alfbanco mit selbst gebautem multipart (``konto_id`` als Textfeld)."""
    if felder is None:
        felder = [("konto_id", None, str(konto_id).encode(), None), ("datei", dateiname, daten,
                                                                      "application/octet-stream")]
    koerper, art = multipart(felder)
    return api.post("/api/import/alfbanco", content=koerper, headers={"Content-Type": art}, erwartet=erwartet)


def importiere(config, quelle, **kw):
    return kontor.modul("kontor.importer.alfbanco").importiere_alfbanco(config, quelle, **kw)


def erfolg(api: Api, konto_id: int, daten: bytes, **kw) -> dict:
    e = import_rest(api, konto_id, daten, **kw).daten
    assert e["erfolgreich"] is True and e["fehler"] == [], e
    return e


def leer_ergebnis(e: dict, fmt: str | None) -> None:
    """3.3: bei Fehlern alle Zählungen 0, keine Warnungen, import_id null."""
    assert e["erfolgreich"] is False and e["import_id"] is None and e["warnungen"] == [] and e["format"] == fmt, e
    for k, v in e.items():
        if k.endswith(("_neu", "_vorhanden", "_zusammengefuehrt", "_zur_pruefung", "_uebersprungen")):
            assert v == 0, (k, v)


def zaehler(e: dict) -> dict:
    """Zählfelder des ImportErgebnis (ohne das Feld des Erweiterungslaufs, E-124)."""
    return {k: v for k, v in e.items() if k not in ("erfolgreich", "format", "warnungen", "fehler", "import_id",
                                                       ZUSATZFELD)}


def warnungen(e: dict) -> set[tuple[str, str | None]]:
    return {(w["code"], w["referenz"]) for w in e["warnungen"]}


def nach_zweck(api: Api, konto_id: int | None = None) -> dict[str, dict]:
    bs = api.alle_buchungen(**({"konto_id": konto_id} if konto_id else {}))
    aus: dict[str, dict] = {}
    for b in bs:
        aus.setdefault(b["verwendungszweck"], b)
    return aus


def kategorie(api: Api, extern_id: str) -> dict | None:
    ks = [k for k in api.konten() if k["extern_id"] == extern_id]
    assert len(ks) <= 1
    return ks[0] if ks else None


def splits(b: dict) -> list[tuple[int, int, str]]:
    return [(s["konto_id"], s["betrag"], s["memo"]) for s in b["splits"]]


# ------------------------------------------------------------------ Zusammenführen
def zusammenfuehren(api: Api, quelle_ids, ziel_id, erwartet: int | tuple = 200, **felder):
    return api.post("/api/kategorien/zusammenfuehren", json={"quelle_ids": quelle_ids, "ziel_id": ziel_id, **felder},
                    erwartet=erwartet)


def _nachfahre(konten: dict[int, dict], k: int, vorfahr: int) -> bool:
    e = konten[k]["eltern_id"]
    while e is not None:
        if e == vorfahr:
            return True
        e = konten[e]["eltern_id"]
    return False


def zusammenfuehren_soll(api: Api, quelle_ids: list[int], ziel: int, *, loeschen: bool = True) -> dict:
    """Erwartete Antwortlisten und erwarteter Bestand (Konten-Eltern, Buchungen, Regeln, Empfänger,
    extern_id des Ziels) nach alfbanco.md 5.3, je Quelle nacheinander."""
    konten = {k["id"]: dict(k) for k in api.konten()}
    buchungen = api.alle_buchungen()
    regeln = api.get("/api/regeln", erwartet=200).daten
    empfaenger = api.get("/api/empfaenger", erwartet=200).daten
    abstimmungen = api.get("/api/abstimmungen", erwartet=200).daten
    betroffen = sorted(b["id"] for b in buchungen if any(s["konto_id"] in quelle_ids for s in b["splits"]))
    gesperrt = sorted(b["id"] for b in buchungen if b["id"] in betroffen and lo.gesperrt(b))
    konflikt: list[int] = []
    verschoben: list[int] = []
    r_geaendert: list[int] = []
    e_geaendert: list[int] = []
    for q in quelle_ids:
        liste = [dict(v) for v in konten.values()]
        # Orakel mit dem Ziel als „Elternkonto“ der Quelle (nur Buchungen, Regeln, Empfänger)
        fake = [dict(x, eltern_id=ziel) if x["id"] == q else x for x in liste]
        r = lo.berechne(fake, buchungen, q, "elternkonto", "behalten", regeln, empfaenger, abstimmungen)
        konflikt += r["ergebnis"]["konfliktbuchungen"]
        neu_b = list(r["buchungen"].values())
        if loeschen:
            buchungen = neu_b
            regeln = list(r["regeln"].values())
            r_geaendert += r["ergebnis"]["regeln_geaendert"]
            for e in empfaenger:
                if e["standardkategorie_id"] == q:
                    e_geaendert.append(e["id"])
            empfaenger = [dict(e, standardkategorie_id=r["empfaenger"][e["id"]]) for e in empfaenger]
            gleich = (konten[q]["art"] == konten[ziel]["art"]) and not _nachfahre(konten, ziel, q)
            for x in konten.values():
                if x["eltern_id"] == q:
                    if gleich:
                        x["eltern_id"] = ziel
                        verschoben.append(x["id"])
                    else:
                        x["eltern_id"] = konten[q]["eltern_id"]
            del konten[q]
        else:
            buchungen = neu_b
        abstimmungen = [a for a in abstimmungen if a["konto_id"] != q]
    extern = konten[ziel]["extern_id"] if ziel in konten else None
    uebernommen = None
    if loeschen and extern is None:
        alle = {k["id"]: k for k in api.konten()}
        uebernommen = next((alle[q]["extern_id"] for q in quelle_ids if alle[q]["extern_id"]), None)
    return {
        "antwort": {"ziel_id": ziel, "quelle_ids": list(quelle_ids), "quellen_geloescht": loeschen,
                    "buchungen_umgebucht": betroffen, "konfliktbuchungen": sorted(set(konflikt)), "gesperrt": gesperrt,
                    "unterkategorien_verschoben": sorted(verschoben), "regeln_geaendert": sorted(set(r_geaendert)),
                    "empfaenger_geaendert": sorted(set(e_geaendert)), "extern_id_uebernommen": uebernommen},
        "eltern": {k: v["eltern_id"] for k, v in konten.items()},
        "buchungen": {b["id"]: lo.buchung_kern(b) for b in buchungen},
        "regeln": {r_["id"]: {k: r_[k] for k in ("kategorie_id", "bedingungen")} for r_ in regeln},
        "empfaenger": {e["id"]: e["standardkategorie_id"] for e in empfaenger},
        "ziel_extern_id": extern if extern is not None else uebernommen,
    }


def ist_zusammengefuehrt(api: Api, soll: dict) -> None:
    konten = {k["id"]: k for k in api.konten()}
    assert {k: v["eltern_id"] for k, v in konten.items()} == soll["eltern"], "Konten und Elternkonten"
    ist_b = {b["id"]: lo.buchung_kern(b) for b in api.alle_buchungen()}
    assert ist_b == soll["buchungen"], "Buchungen nach dem Zusammenführen"
    regeln = {r["id"]: {k: r[k] for k in ("kategorie_id", "bedingungen")}
              for r in api.get("/api/regeln", erwartet=200).daten}
    assert regeln == soll["regeln"]
    assert {e["id"]: e["standardkategorie_id"] for e in api.get("/api/empfaenger", erwartet=200).daten} == soll[
        "empfaenger"]
    assert konten[soll["antwort"]["ziel_id"]]["extern_id"] == soll["ziel_extern_id"]


def ohne_listen(antwort: dict) -> dict:
    return {k: v for k, v in antwort.items() if k not in ("trocken", "aenderung_id", ZUSATZFELD)}


__all__ = ["copy"]
