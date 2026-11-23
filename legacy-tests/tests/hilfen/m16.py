"""Hilfen für Meilenstein 16: Begründung wiederkehrender Buchungen (wiederkehrend.md 2.2 und 8, E-193, E-195).

Die Erwartung der Begründung wird hier unabhängig von der Anwendung aus der REST-Darstellung (Buchungen,
Konten, Kredite) berechnet; die Kette selbst kommt aus ``wiederkehrend_orakel.kette``. Verglichen wird ohne
die Textfelder ``text`` und ``gruppe`` (nicht Teil der Abnahme), ``uebersprungen`` ohne Reihenfolge (E-195).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import wiederkehrend_orakel as wo
from .api import Api
from .vertrag import ZUSATZFELD

BESTAND = wo.BESTAND
TEXTFELDER = ("text", "gruppe")
#: ab M25 optionale Felder der Begründung (wiederkehrend.md 9.3.5, E-029/E-124, E-244); M16 vergleicht ohne sie
M25_FELDER = ("betragsfilter", "betragsfilter_text")


# ------------------------------------------------------------------ Aufbau über REST
class Abo:
    """Ein Girokonto, eine Aufwandskategorie und Empfänger für kleine, handgebaute Gruppen."""

    def __init__(self, api: Api, giro: int | None = None):
        self.api = api
        self.giro = giro or api.konto("Girokonto", "girokonto")["id"]
        self.kat = api.konto("Abos", "aufwand")["id"]
        self._n = 0

    def empfaenger(self, name: str | None = None) -> int:
        self._n += 1
        return self.api.empfaenger(name or f"Abo {self._n} (fiktiv)")["id"]

    def buchen(self, emp: int | None, tage: list[str], betraege: int | list[int] = -999,
               konto: int | None = None) -> list[int]:
        """Je Tag eine Buchung ``konto → kat`` (Vorgabe Giro) in der angegebenen Reihenfolge (IDs aufsteigend)."""
        if isinstance(betraege, int):
            betraege = [betraege] * len(tage)
        k = konto or self.giro
        return [self.api.buchung(t, [(k, b), (self.kat, -b)], empfaenger_id=emp, verwendungszweck="Abo")["id"]
                for t, b in zip(tage, betraege)]


def begruendung_api(api: Api, bid: int, stichtag: str | None = None, erwartet: int = 200, **params):
    p = {**({"stichtag": stichtag} if stichtag else {}), **params}
    return api.get(f"/api/buchungen/{bid}/wiederkehrend", params=p or None, erwartet=erwartet)


def begruendung(api: Api, bid: int, stichtag: str | None = None) -> dict:
    return begruendung_api(api, bid, stichtag).daten


def uebersicht(api: Api, stichtag: str) -> dict:
    return api.get("/api/wiederkehrend", params={"stichtag": stichtag}, erwartet=200).daten


def kredite(api: Api) -> list[dict]:
    return api.get("/api/kredite", erwartet=200).daten


# ------------------------------------------------------------------ Erwartung
def _kurz(e: dict) -> dict:
    return {"buchung_id": e["buchung_id"], "datum": e["datum"], "betrag": e["betrag"]}


def rollen(gruppe: list[dict], kette: dict | None) -> dict[int, tuple[str, int | None]]:
    """Rolle je buchung_id nach wiederkehrend.md 8.5 (``kette`` = Kette des ersten erfüllten Rhythmus)."""
    if kette is None:
        return {e["buchung_id"]: ("keine_serie", None) for e in gruppe}
    nummer = {e["buchung_id"]: i + 1 for i, e in enumerate(kette["glieder"])}
    erstes = (kette["glieder"][0]["datum"], kette["glieder"][0]["buchung_id"])
    aus = {}
    for e in gruppe:
        b = e["buchung_id"]
        if b in nummer:
            aus[b] = ("glied", nummer[b])
        elif b in kette["zusaetzlich"]:
            aus[b] = ("zusaetzlich", None)
        else:
            assert (e["datum"], b) < erstes, "nach dem ersten Glied ist jeder Eintrag Glied oder zusätzlich"
            aus[b] = ("vor_beginn", None)
    return aus


def erwartung(buchungen: list[dict], konten: list[dict], kredite_: list[dict], bid: int, stichtag: str) -> dict:
    """Erwartete ``WiederkehrendBegruendung`` ohne Textfelder; ``ausgeschlossen`` ist ``None``, wenn es nach E-195
    Nr. 3 nicht geprüft wird."""
    nach_id = {b["id"]: b for b in buchungen}
    b = nach_id[bid]
    kopf = {"buchung_id": bid, "stichtag": stichtag}
    if b["empfaenger"] is None or b["datum"] > stichtag:
        return {**kopf, "urteil": "ausgeschlossen", "eintraege": [], "ausgeschlossen": None}
    art = {k["id"]: k["art"] for k in konten}
    name = {k["id"]: k["name"] for k in konten}
    darlehen = {k["konto_id"] for k in kredite_}
    eigene = wo.eintraege([b], konten, kredite_)
    mit_eintrag = {e["konto_id"] for e in eigene}
    bestand = sorted({s["konto_id"] for s in b["splits"] if art[s["konto_id"]] in BESTAND})
    ausgeschlossen = [{"konto": {"id": k, "name": name[k]}, "grund": "darlehenskonto" if k in darlehen else "summe_null"}
                      for k in bestand if k not in mit_eintrag]
    if not eigene:
        return {**kopf, "urteil": "ausgeschlossen", "eintraege": [], "ausgeschlossen": ausgeschlossen}
    bis = [x for x in buchungen if x["datum"] <= stichtag]
    gruppen = wo.gruppen(wo.eintraege(bis, konten, kredite_))
    h = dt.date.fromisoformat(stichtag)
    eintraege = []
    for e in sorted(eigene, key=lambda e: (e["konto_id"], e["richtung"] != "ausgabe")):
        g = gruppen[(e["konto_id"], e["empfaenger"]["id"], e["richtung"])]
        s, geprueft, k = wo.serie_mit_rhythmen(g, h)
        r = rollen(g, k)
        eintraege.append({
            "konto": {"id": e["konto_id"], "name": name[e["konto_id"]]}, "richtung": e["richtung"],
            "datum": e["datum"], "betrag": e["betrag"], "gruppe_anzahl": len(g), "juengste": _kurz(g[-1]),
            "urteil": r[bid][0], "glied": r[bid][1], "serie": s,
            "rhythmen": [{"rhythmus": x["rhythmus"], "monate": x["monate"], "mindestanzahl": x["mindestanzahl"],
                          "laenge": x["laenge"], "erfuellt": x["erfuellt"], "schritte": x["kette"]["schritte"]}
                         for x in geprueft],
            "buchungen": [{**_kurz(x), "rolle": r[x["buchung_id"]][0], "glied": r[x["buchung_id"]][1]}
                          for x in reversed(g)]})
    urteile = {x["urteil"] for x in eintraege}
    gesamt = "wiederkehrend" if "glied" in urteile else "zusaetzlich" if "zusaetzlich" in urteile \
        else "nicht_wiederkehrend"
    return {**kopf, "urteil": gesamt, "eintraege": eintraege, "ausgeschlossen": ausgeschlossen}


def erwartung_api(api: Api, bid: int, stichtag: str) -> dict:
    return erwartung(api.alle_buchungen(), api.konten(), kredite(api), bid, stichtag)


# ------------------------------------------------------------------ Vergleich
def vergleichbar(daten: Any, *, ohne_ausgeschlossen: bool = False) -> Any:
    """Plain-JSON ohne ``text``/``gruppe`` und ohne Zusatzfeld (E-124); ``uebersprungen`` sortiert."""
    if isinstance(daten, dict):
        aus = {}
        for k, v in daten.items():
            if k in TEXTFELDER or k == ZUSATZFELD or k in M25_FELDER:
                continue
            if k == "ausgeschlossen" and ohne_ausgeschlossen:
                continue
            v = vergleichbar(v)
            if k == "uebersprungen":
                v = sorted(v, key=lambda x: (x["datum"], x["buchung_id"]))
            aus[k] = v
        return aus
    if isinstance(daten, list):
        return [vergleichbar(x) for x in daten]
    return daten


def pruefe_texte(daten: Any, pfad: str = "") -> None:
    """``text`` und ``gruppe`` sind überall nicht leere Zeichenketten (Inhalt nicht Teil der Abnahme)."""
    if isinstance(daten, dict):
        for k, v in daten.items():
            if k in TEXTFELDER:
                assert isinstance(v, str) and v.strip(), f"{pfad}.{k} muss ein nicht leerer Text sein: {v!r}"
            else:
                pruefe_texte(v, f"{pfad}.{k}")
    elif isinstance(daten, list):
        for i, x in enumerate(daten):
            pruefe_texte(x, f"{pfad}[{i}]")


def pruefe_begruendung(api: Api, bid: int, stichtag: str, *, soll: dict | None = None) -> dict:
    """Antwort gleich der unabhängig berechneten Erwartung (E-195 Nr. 2); liefert die Antwort."""
    ist = begruendung(api, bid, stichtag)
    soll = soll if soll is not None else erwartung_api(api, bid, stichtag)
    pruefe_texte(ist)
    ohne = soll["ausgeschlossen"] is None
    if "empfaenger" not in soll:
        ist = {k: v for k, v in ist.items() if k != "empfaenger"}
    assert vergleichbar(ist, ohne_ausgeschlossen=ohne) == vergleichbar(
        {k: v for k, v in soll.items() if not (ohne and k == "ausgeschlossen")}), f"Begründung für Buchung {bid}"
    return ist


def eintrag(antwort: dict, konto_id: int | None = None) -> dict:
    """Der (einzige bzw. zum Konto gehörende) Eintrag einer Begründung."""
    e = antwort["eintraege"] if konto_id is None else [x for x in antwort["eintraege"] if x["konto"]["id"] == konto_id]
    assert len(e) == 1, e
    return e[0]


def rhythmus(e: dict, name: str) -> dict:
    (r,) = [x for x in e["rhythmen"] if x["rhythmus"] == name]
    return r


def schritte(e: dict, name: str = "monatlich") -> list[tuple]:
    """Kurzform des Kettenprotokolls: (ergebnis, grund, von.buchung_id, vorgaenger.buchung_id | None)."""
    return [(s["ergebnis"], s["grund"], s["von"]["buchung_id"], s["vorgaenger"] and s["vorgaenger"]["buchung_id"])
            for s in rhythmus(e, name)["schritte"]]


def beteiligt(schritt: dict, bid: int) -> bool:
    """Ist die Buchung an einem Schritt beteiligt (oberflaeche.md 26.1: von, vorgaenger, übersprungen, fremd)?"""
    teile = [schritt["von"], schritt["vorgaenger"], schritt["fremd"], *schritt["uebersprungen"]]
    return any(t and t["buchung_id"] == bid for t in teile)


ROLLE_TEXT = {"zusaetzlich": "zusätzlich", "vor_beginn": "vor Beginn", "keine_serie": "–"}


def rolle_text(rolle: str, glied: int | None) -> str:
    return f"Glied {glied}" if rolle == "glied" else ROLLE_TEXT[rolle]
