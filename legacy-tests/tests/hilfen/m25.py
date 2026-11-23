"""Hilfen für Meilenstein 25: Betragsfilter wiederkehrender Buchungen (wiederkehrend.md 9; E-238 bis E-242).

Erwartete Übersicht und Begründung werden unabhängig mit der um die Filter erweiterten Referenzkette
(``wiederkehrend_orakel``) aus der REST-Darstellung berechnet. Der geltende Filter einer Gruppe kommt aus den im Test
gesetzten Einstellungen (Eingabe, nicht Ergebnis der Erkennung).
"""

from __future__ import annotations

import datetime as dt

from . import wiederkehrend_orakel as wo
from .api import Api
from .m16 import BESTAND, _kurz, kredite, vergleichbar

VORGABE_PFAD = "/api/wiederkehrend/einstellungen/vorgabe"


# ------------------------------------------------------------------ REST
def einstellungen(api: Api) -> dict:
    return api.get("/api/wiederkehrend/einstellungen", erwartet=200).daten


def vorgabe(api: Api, modus: str = "toleranz", prozent: int | None = 10, erwartet=200):
    body = {"modus": modus} if modus == "aus" else {"modus": modus, "toleranz_prozent": prozent}
    return api.put(VORGABE_PFAD, json=body, erwartet=erwartet)


def filter_setzen(api: Api, eid: int, erwartet=200, **body):
    return api.put(f"/api/empfaenger/{eid}/wiederkehrend", json=body, erwartet=erwartet)


def filter_loeschen(api: Api, eid: int, erwartet=204):
    return api.delete(f"/api/empfaenger/{eid}/wiederkehrend", erwartet=erwartet)


def filter_von(api: Api) -> dict:
    """Empfänger-ID → geltender Filter (mit ``quelle``) aus den gesetzten Einstellungen; Vorgabe unter ``None``."""
    e = einstellungen(api)
    v = e["vorgabe"]
    vor = {"modus": v["modus"], "toleranz_prozent": v["toleranz_prozent"], "mindestbetrag": None, "quelle": "vorgabe"}
    eigen = {x["empfaenger"]["id"]: {"modus": x["modus"], "toleranz_prozent": x["toleranz_prozent"],
                                     "mindestbetrag": x["mindestbetrag"], "quelle": "empfaenger"}
             for x in e["empfaenger"]}
    return {"vorgabe": vor, "eigen": eigen}


def filter_fn(fv: dict):
    return lambda eid: fv["eigen"].get(eid, fv["vorgabe"])


# ------------------------------------------------------------------ Texte (9.3.5)
def euro(cent: int) -> str:
    e, c = divmod(abs(cent), 100)
    return f"{e:,}".replace(",", ".") + f",{c:02d} €"


def filter_text(f: dict) -> str:
    herkunft = "Vorgabe" if f["quelle"] == "vorgabe" else "Einstellung des Empfängers"
    if f["modus"] == "toleranz":
        teil = f"Toleranz ±{f['toleranz_prozent']} %"
    elif f["modus"] == "mindestschwelle":
        teil = f"nur Beträge ab {euro(f['mindestbetrag'])}"
    else:
        teil = "aus"
    return f"Betragsfilter: {teil} ({herkunft})"


# ------------------------------------------------------------------ Erwartungen
def rollen(gruppe: list[dict], kette: dict | None, filt: dict | None) -> dict[int, tuple[str, int | None]]:
    """Rolle je buchung_id nach 9.3.5 (anderer_betrag für übergangene, sonst wie wiederkehrend.md 8.5)."""
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
        elif not wo.zugelassen(filt, e) or (e["datum"], b) > erstes:
            assert wo.aktiv(filt), "ohne Filter ist nach dem ersten Glied jeder Eintrag Glied oder zusätzlich"
            aus[b] = ("anderer_betrag", None)
        else:
            aus[b] = ("vor_beginn", None)
    return aus


def uebersicht_soll(api: Api, stichtag: str) -> dict:
    fv = filter_von(api)
    return wo.uebersicht(api.alle_buchungen(), api.konten(), kredite(api), stichtag, filter_fn(fv))


def uebersicht_ist(api: Api, stichtag: str) -> dict:
    return api.get("/api/wiederkehrend", params={"stichtag": stichtag}, erwartet=200).daten


def erwartung(buchungen: list[dict], konten: list[dict], kredite_: list[dict], bid: int, stichtag: str,
              fv: dict) -> dict:
    """Erwartete Begründung mit den Feldern aus 9.3.5 (ohne Textfelder; ``ausgeschlossen`` ungeprüft)."""
    nach_id = {b["id"]: b for b in buchungen}
    b = nach_id[bid]
    emp = b["empfaenger"]
    kopf = {"buchung_id": bid, "stichtag": stichtag,
            "empfaenger": {"id": emp["id"], "name": emp["name"]} if emp else None}
    if emp is None or b["datum"] > stichtag:
        return {**kopf, "urteil": "ausgeschlossen", "eintraege": []}
    name = {k["id"]: k["name"] for k in konten}
    eigene = wo.eintraege([b], konten, kredite_)
    if not eigene:
        return {**kopf, "urteil": "ausgeschlossen", "eintraege": []}
    bis = [x for x in buchungen if x["datum"] <= stichtag]
    gruppen = wo.gruppen(wo.eintraege(bis, konten, kredite_))
    h = dt.date.fromisoformat(stichtag)
    filt = filter_fn(fv)(emp["id"])
    eintraege = []
    for e in sorted(eigene, key=lambda e: (e["konto_id"], e["richtung"] != "ausgabe")):
        g = gruppen[(e["konto_id"], e["empfaenger"]["id"], e["richtung"])]
        s, geprueft, k = wo.serie_mit_rhythmen(g, h, filt)
        r = rollen(g, k, filt)
        eintraege.append({
            "konto": {"id": e["konto_id"], "name": name[e["konto_id"]]}, "richtung": e["richtung"],
            "datum": e["datum"], "betrag": e["betrag"], "gruppe_anzahl": len(g), "juengste": _kurz(g[-1]),
            "urteil": r[bid][0], "glied": r[bid][1], "serie": s,
            "betragsfilter": dict(filt), "betragsfilter_text": filter_text(filt),
            "rhythmen": [{"rhythmus": x["rhythmus"], "monate": x["monate"], "mindestanzahl": x["mindestanzahl"],
                          "laenge": x["laenge"], "erfuellt": x["erfuellt"], "schritte": x["kette"]["schritte"]}
                         for x in geprueft],
            "buchungen": [{**_kurz(x), "rolle": r[x["buchung_id"]][0], "glied": r[x["buchung_id"]][1]}
                          for x in reversed(g)]})
    urteile = {x["urteil"] for x in eintraege}
    gesamt = "wiederkehrend" if "glied" in urteile else "zusaetzlich" if "zusaetzlich" in urteile \
        else "nicht_wiederkehrend"
    return {**kopf, "urteil": gesamt, "eintraege": eintraege}


def erwartung_api(api: Api, bid: int, stichtag: str) -> dict:
    return erwartung(api.alle_buchungen(), api.konten(), kredite(api), bid, stichtag, filter_von(api))


def _normal(daten):
    """Vergleichsform: ohne Texte und ``ausgeschlossen``; ``betragsfilter_text`` mit normalem Leerraum."""
    import re

    d = vergleichbar({k: v for k, v in daten.items() if k != "ausgeschlossen"})
    if "empfaenger" in daten:
        d["empfaenger"] = vergleichbar(daten["empfaenger"])
    for e, roh in zip(d["eintraege"], daten["eintraege"]):
        if "betragsfilter_text" in roh:
            e["betragsfilter_text"] = re.sub(r"\s+", " ", roh["betragsfilter_text"].replace("\u202f", " ")).strip()
        if "betragsfilter" in roh:
            e["betragsfilter"] = vergleichbar(roh["betragsfilter"])
    return d


def unterschied(a, b, pfad="") -> str | None:
    """Erster abweichender Pfad (für Meldungen)."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{pfad}.{k}: nur in {'Antwort' if k in a else 'Erwartung'}"
            u = unterschied(a[k], b[k], f"{pfad}.{k}")
            if u:
                return u
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{pfad}: Länge {len(a)} statt {len(b)}: {a} / {b}"
        for i, (x, y) in enumerate(zip(a, b)):
            u = unterschied(x, y, f"{pfad}[{i}]")
            if u:
                return u
        return None
    return None if a == b else f"{pfad}: {a!r} statt {b!r}"


def pruefe_begruendung(api: Api, bid: int, stichtag: str) -> dict:
    ist = api.get(f"/api/buchungen/{bid}/wiederkehrend", params={"stichtag": stichtag}, erwartet=200).daten
    soll = erwartung_api(api, bid, stichtag)
    a, b = _normal(ist), _normal(soll)
    assert a == b, f"Begründung für Buchung {bid}: {unterschied(a, b)}"
    return ist


# ------------------------------------------------------------------ Bestand mit eigener Einstellung (9.4)
def bestand(api: Api) -> dict[tuple[str, int], dict]:
    """Bestand in Protokollform (M6, ohne Dokumente und Erwartungen, die M25 nicht berührt) mit dem Feld
    ``wiederkehrend`` an Empfängern mit eigener Einstellung."""
    from .m6 import bestand as bestand_m6

    aus = bestand_m6(api)
    for x in einstellungen(api)["empfaenger"]:
        k = ("empfaenger", x["empfaenger"]["id"])
        aus[k] = {**dict(aus[k]), "wiederkehrend": {f: x[f] for f in ("modus", "toleranz_prozent",
                                                                       "mindestbetrag")}}
    return aus


def protokollformen(a: dict) -> dict[tuple[str, int], tuple]:
    return {(e["objekt"], e["objekt_id"]): (e["art"], e["vorher"], e["nachher"]) for e in a["eintraege"]}


__all__ = ["BESTAND"]
