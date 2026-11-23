"""WEGWERF-REFERENZ M16: Kette mit zusätzlichen Zahlungen und Begründung je Buchung – KEIN Anwendungscode.

Eigene, von ``tests/hilfen/wiederkehrend_orakel.py`` unabhängig geschriebene Fassung (E-193 Nr. 6). Einträge im
Format von ``m5._eintraege``: ``{k, e, r, datum, id, x}``. Mutanten ``m16_*`` über ``kontor.mutant``.
"""

from __future__ import annotations

import datetime as dt

from fastapi import FastAPI, Request

from . import mutant
from .buch import KLASSE, Fehler

T = 5


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _plus(d: dt.date, n: int) -> dt.date:
    j, m = divmod(d.month - 1 + n, 12)
    j += d.year
    m += 1
    import calendar
    return dt.date(j, m, min(d.day, calendar.monthrange(j, m)[1]))


def _ref(e: dict) -> dict:
    return {"buchung_id": e["id"], "datum": e["datum"], "betrag": e["x"]}


class _Lauf:
    """Rückwärtsverkettung ab einem Anker (Definition 1.2)."""

    def __init__(self, g: list[dict], a: int, m: int, tol: int):
        self.glieder: list[int] = [a]
        self.extra: set[int] = set()
        self.schritte: list[dict] = []
        tage = [_d(x["datum"]) for x in g]

        def abw(c: int, x: int) -> int:
            return (tage[c] - _plus(tage[x], m)).days

        def schritt(ergebnis, grund, c, vor, ueb, fremd=None):
            erw = _plus(tage[vor], m) if vor is not None else None
            a_t = (tage[c] - erw).days if erw else None
            if a_t is not None and mutant("m16_abweichung_ohne_vorzeichen"):
                a_t = abs(a_t)
            self.schritte.append({"ergebnis": ergebnis, "grund": grund, "von": _ref(g[c]),
                                  "vorgaenger": _ref(g[vor]) if vor is not None else None,
                                  "erwartet": erw.isoformat() if erw else None, "abweichung_tage": a_t,
                                  "uebersprungen": [_ref(g[x]) for x in ueb],
                                  "fremd": _ref(g[fremd]) if fremd is not None else None, "kandidaten": []})

        c, vorher = a, set()
        while True:
            kand = [x for x in range(c - 1, -1, -1) if abs(abw(c, x)) <= tol]
            if mutant("m16_ohne_ueberspringen"):
                kand = [c - 1] if c > 0 and abs(abw(c, c - 1)) <= tol else []
            if not kand:
                ueb, k = [], c - 1
                if not mutant("m16_ohne_ueberspringen"):
                    while k >= 0 and (tage[c] - tage[k]).days <= tol:
                        ueb.append(k)
                        k -= 1
                self.extra.update(ueb)
                schritt("bruch", "abstand" if k >= 0 else "kein_vorgaenger", c, k if k >= 0 else None, ueb)
                return
            if mutant("m16_vorgaenger_ohne_betrag"):
                p = sorted(kand, key=lambda x: (abs(abw(c, x)), -x))[0]
            else:
                p = sorted(kand, key=lambda x: (g[x]["x"] != g[c]["x"], abs(abw(c, x)), -x))[0]
            ueb, fremd = [], []
            for x in range(c - 1, p, -1):
                nah = (tage[c] - tage[x]).days <= tol or (
                    (tage[x] - tage[p]).days <= tol and not mutant("m16_zusaetzlich_nur_nahe_c"))
                if nah or (x in vorher and not mutant("m16_ohne_vorige_kandidaten")):
                    ueb.append(x)
                else:
                    fremd.append(x)
            self.extra.update(ueb)
            if fremd:
                schritt("bruch", "fremde_zahlung", c, p, ueb, fremd[0])
                return
            schritt("verbunden", None, c, p, ueb)
            self.glieder.append(p)
            vorher, c = set(kand), p


def kette(g: list[dict], m: int, tol: int = T) -> dict:
    """Kette einer sortierten Gruppe: glieder (Indizes aufsteigend), extra (Indizes), schritte."""
    letzte = _d(g[-1]["datum"])
    kand = [i for i, x in enumerate(g) if (letzte - _d(x["datum"])).days <= tol]
    if mutant("m16_ohne_ueberspringen"):
        kand = [len(g) - 1]
    laeufe = {i: _Lauf(g, i, m, tol) for i in kand}

    def gleich(i: int) -> bool:
        lf = laeufe[i]
        return len(lf.glieder) > 1 and g[i]["x"] == g[lf.glieder[1]]["x"]

    if mutant("m16_anker_juengster"):
        a = kand[-1]
    elif mutant("m16_anker_ohne_betrag"):
        a = max(kand, key=lambda i: (len(laeufe[i].glieder), i))
    else:
        a = max(kand, key=lambda i: (len(laeufe[i].glieder), gleich(i), i))
    lf = laeufe[a]
    extra = set(lf.extra) | (set(kand) - {a})
    schritte = list(lf.schritte)
    if len(kand) > 1 and not mutant("m16_ohne_ankerschritt"):
        schritte.insert(0, {"ergebnis": "anker", "grund": None, "von": _ref(g[a]), "vorgaenger": None,
                            "erwartet": None, "abweichung_tage": None,
                            "uebersprungen": [_ref(g[i]) for i in kand if i != a], "fremd": None,
                            "kandidaten": [{**_ref(g[i]), "laenge": len(laeufe[i].glieder),
                                            "gleicher_betrag": gleich(i)} for i in kand]})
    return {"glieder": sorted(lf.glieder), "extra": extra, "schritte": schritte}


# ================================================================ Begründung (wiederkehrend.md 8)
def begruendung(buch, bid: int, stichtag: str) -> dict:
    from . import m5
    b = buch.buchungen[bid]
    leer = {"buchung_id": bid, "stichtag": stichtag, "eintraege": [], "ausgeschlossen": [],
            "empfaenger": ({"id": b["empfaenger_id"], "name": buch.empfaenger[b["empfaenger_id"]]["name"]}
                           if b["empfaenger_id"] is not None else None)}
    if b["empfaenger_id"] is None:
        return {**leer, "urteil": "ausgeschlossen", "text": "Die Buchung hat keinen Empfänger."}
    if b["datum"] > stichtag and not mutant("m16_stichtag_ignoriert"):
        return {**leer, "urteil": "ausgeschlossen", "text": "Die Buchung liegt nach dem Stichtag."}
    bis = None if mutant("m16_stichtag_ignoriert") else stichtag
    alle = m5._eintraege(buch, bis)
    eigene = [x for x in alle if x["id"] == bid]
    darlehen = {k["konto_id"] for k in buch.kredite.values()}
    konten = sorted({s["konto_id"] for s in b["splits"] if KLASSE[buch.konten[s["konto_id"]]["art"]] == "bestand"})
    mit = {x["k"] for x in eigene}
    aus = [{"konto": {"id": k, "name": buch.konten[k]["name"]},
            "grund": "darlehenskonto" if k in darlehen else "summe_null",
            "text": "Darlehenskonto eines Kredits." if k in darlehen else "Die Beträge auf diesem Konto heben sich auf."}
           for k in konten if k not in mit]
    if not eigene:
        return {**leer, "ausgeschlossen": aus, "urteil": "ausgeschlossen", "text": "Kein Eintrag."}
    gruppen = m5._gruppen(alle)
    h = _d(stichtag)
    eintraege = []
    from . import m25
    filt = m25.filter_fuer(buch, b["empfaenger_id"])
    gefiltert = filt["modus"] != "aus"
    for x in sorted(eigene, key=lambda x: (x["k"], x["r"] != "ausgabe")):
        g = gruppen[(x["k"], x["e"], x["r"])]
        serie = m5._serie(buch, g, h)
        rhythmen, gewaehlt = [], None
        for name, mo, mindest in m5.RHYTHMEN:
            kt = m25.kette(g, mo, filt) if gefiltert else kette(g, mo)
            n = len(kt["glieder"])
            erfuellt = n >= mindest and not (gefiltert and m25.mehrheit_verletzt(g, kt, filt))
            rhythmen.append({"rhythmus": name, "monate": mo, "mindestanzahl": mindest, "laenge": n,
                             "erfuellt": erfuellt, "schritte": [{**s, "text": "Schritt."} for s in kt["schritte"]]})
            if erfuellt:
                gewaehlt = kt
                break
        rolle = {}
        for i, y in enumerate(g):
            if gewaehlt is None:
                rolle[y["id"]] = ("keine_serie", None)
            elif i in gewaehlt["glieder"]:
                rolle[y["id"]] = ("glied", gewaehlt["glieder"].index(i) + 1)
            elif i in gewaehlt["extra"]:
                rolle[y["id"]] = ("zusaetzlich", None)
            elif gefiltert and (not m25._zul(filt, y) or i > gewaehlt["glieder"][0]) \
                    and not mutant("m25_rolle_vor_beginn"):
                rolle[y["id"]] = ("anderer_betrag", None)
            else:
                rolle[y["id"]] = ("keine_serie" if mutant("m16_vor_beginn_als_keine_serie") else "vor_beginn", None)
        liste = [{"buchung_id": y["id"], "datum": y["datum"], "betrag": y["x"], "rolle": rolle[y["id"]][0],
                  "glied": rolle[y["id"]][1]} for y in g]
        if not mutant("m16_buchungen_aelteste_zuerst"):
            liste.reverse()
        emp = buch.empfaenger[x["e"]]["name"]
        eintraege.append({"konto": {"id": x["k"], "name": buch.konten[x["k"]]["name"]}, "richtung": x["r"],
                          "datum": x["datum"], "betrag": x["x"],
                          "gruppe": f"{buch.konten[x['k']]['name']} · {emp} · {x['r']}", "gruppe_anzahl": len(g),
                          "juengste": {"buchung_id": g[-1]["id"], "datum": g[-1]["datum"], "betrag": g[-1]["x"]},
                          "urteil": rolle[bid][0], "glied": rolle[bid][1], "text": "Eintrag.", "serie": serie,
                          "betragsfilter": dict(filt), "betragsfilter_text": m25.filter_text(filt),
                          "rhythmen": rhythmen, "buchungen": liste})
    u = {e["urteil"] for e in eintraege}
    if "glied" in u:
        urteil = "wiederkehrend"
    elif "zusaetzlich" in u and not mutant("m16_urteil_zusaetzlich_als_nicht"):
        urteil = "zusaetzlich"
    else:
        urteil = "nicht_wiederkehrend"
    emp = buch.empfaenger[b["empfaenger_id"]]
    return {"buchung_id": bid, "stichtag": stichtag, "urteil": urteil, "text": "Begründung.",
            "empfaenger": {"id": emp["id"], "name": emp["name"]}, "eintraege": eintraege, "ausgeschlossen": aus}


def m16_einbinden(app: FastAPI, buch) -> None:
    dienst = app.state.dienst

    @app.get("/api/buchungen/{buchung_id}/wiederkehrend")
    def wk_begruendung(buchung_id: int, request: Request, stichtag: dt.date | None = None):
        if set(request.query_params) - {"stichtag"} and not mutant("m16_unbekannter_parameter_erlaubt"):
            raise Fehler(422, "validierung", "Ungültige Anfrage",
                         [{"ort": ["query"], "meldung": "unbekannter Parameter"}])
        if buchung_id not in buch.buchungen:
            raise Fehler(404, "nicht_gefunden", "Buchung nicht gefunden")
        return begruendung(buch, buchung_id, (stichtag or dienst.heute()).isoformat())
