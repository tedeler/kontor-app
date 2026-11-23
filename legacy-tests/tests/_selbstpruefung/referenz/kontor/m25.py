"""WEGWERF-REFERENZ M25: Betragsfilter wiederkehrender Buchungen – KEIN Anwendungscode.

Eigene Fassung der Regeln aus ``wiederkehrend.md`` 9 (unabhängig von ``tests/hilfen/wiederkehrend_orakel.py``).
Einträge im Format von ``m5._eintraege``: ``{k, e, r, datum, id, x}``. Die Vorgabe liegt als Attribut ``_wk_vorgabe``
am Buch (nicht in der Sicherung), die eigene Einstellung als Feld ``wiederkehrend`` am Empfänger (Protokollform und
Sicherung). Mutanten ``m25_*`` über ``kontor.mutant``.
"""

from __future__ import annotations

import datetime as dt
import json
import re

from fastapi import FastAPI, Request, Response

from . import mutant
from .buch import Fehler

T = 5
BETRAG_MAX = 999_999_999_999
VORGABE = {"modus": "toleranz", "toleranz_prozent": 10}


# ================================================================ Filter
def vorgabe(buch) -> dict:
    return getattr(buch, "_wk_vorgabe", None) or dict(VORGABE)


def filter_fuer(buch, empfaenger_id: int) -> dict:
    e = buch.empfaenger.get(empfaenger_id) or {}
    eigen = e.get("wiederkehrend")
    if eigen:
        return {**eigen, "quelle": "empfaenger"}
    v = vorgabe(buch)
    return {"modus": v["modus"], "toleranz_prozent": v["toleranz_prozent"], "mindestbetrag": None, "quelle": "vorgabe"}


def _zul(f: dict, x: dict) -> bool:
    if f["modus"] != "mindestschwelle":
        return True
    if mutant("m25_schwelle_exklusiv"):
        return abs(x["x"]) > f["mindestbetrag"]
    return abs(x["x"]) >= f["mindestbetrag"]


def _passt(f: dict, c: dict, x: dict) -> bool:
    if not _zul(f, x):
        return False
    if f["modus"] != "toleranz":
        return True
    return abs(x["x"] - c["x"]) * 100 <= f["toleranz_prozent"] * abs(c["x"])


def _plus(d: dt.date, n: int) -> dt.date:
    from .m16 import _plus as p
    return p(d, n)


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _ref(e: dict) -> dict:
    return {"buchung_id": e["id"], "datum": e["datum"], "betrag": e["x"]}


def _schritt(g, tage, m, ergebnis, grund, c, vor, ueb, fremd=None, kandidaten=None):
    erw = _plus(tage[vor], m) if vor is not None else None
    return {"ergebnis": ergebnis, "grund": grund, "von": _ref(g[c]),
            "vorgaenger": _ref(g[vor]) if vor is not None else None,
            "erwartet": erw.isoformat() if erw else None,
            "abweichung_tage": (tage[c] - erw).days if erw else None,
            "uebersprungen": [_ref(g[x]) for x in sorted(ueb)],
            "fremd": _ref(g[fremd]) if fremd is not None else None, "kandidaten": kandidaten or []}


def _lauf(g: list[dict], a: int, m: int, f: dict):
    tage = [_d(x["datum"]) for x in g]
    glieder, extra, schritte = [a], set(), []
    nach = list(range(a + 1, len(g)))
    for x in nach:
        if _passt(f, g[a], g[x]):
            extra.add(x)
    streng = any(not _passt(f, g[a], g[x]) for x in nach) and not mutant("m25_nie_streng")
    c, vorher = a, set()
    while True:
        kand = [x for x in range(c) if _zul(f, g[x]) and abs((tage[c] - _plus(tage[x], m)).days) <= T]
        if not kand:
            passend = [x for x in range(c - 1, -1, -1) if _passt(f, g[c], g[x])]
            nah = [x for x in passend if (tage[c] - tage[x]).days <= T]
            fern = [x for x in passend if (tage[c] - tage[x]).days > T]
            extra.update(nah)
            vor = fern[0] if fern else None
            schritte.append(_schritt(g, tage, m, "bruch", "abstand" if vor is not None else "kein_vorgaenger", c,
                                     vor, nah))
            return glieder, extra, schritte
        if mutant("m25_vorgaenger_ohne_toleranz"):
            p = min(kand, key=lambda x: (g[x]["x"] != g[c]["x"], abs((tage[c] - _plus(tage[x], m)).days), -x))
        else:
            p = min(kand, key=lambda x: (g[x]["x"] != g[c]["x"], not _passt(f, g[c], g[x]),
                                         abs((tage[c] - _plus(tage[x], m)).days), -x))
        ueb, fremd, uebergangen = [], [], False
        for x in range(c - 1, p, -1):
            if not (_passt(f, g[c], g[x]) or _passt(f, g[p], g[x])) and not mutant("m25_dazwischen_bricht"):
                uebergangen = True
                continue
            if (tage[c] - tage[x]).days <= T or (tage[x] - tage[p]).days <= T or x in vorher:
                ueb.append(x)
            else:
                fremd.append(x)
        extra.update(ueb)
        if fremd:
            schritte.append(_schritt(g, tage, m, "bruch", "fremde_zahlung", c, p, ueb, fremd[0]))
            return glieder, extra, schritte
        if not _passt(f, g[c], g[p]) and (streng or uebergangen) and not mutant("m25_ohne_betragsbruch"):
            schritte.append(_schritt(g, tage, m, "bruch", "betrag", c, p, ueb))
            return glieder, extra, schritte
        schritte.append(_schritt(g, tage, m, "verbunden", None, c, p, ueb))
        glieder.append(p)
        streng = streng or uebergangen
        vorher, c = set(kand), p


def kette(g: list[dict], m: int, f: dict) -> dict:
    """Kette mit Filter (Modus ≠ aus): glieder (Indizes aufsteigend), extra (Indizes), schritte."""
    zul = [i for i, x in enumerate(g) if _zul(f, x)]
    if not zul:
        return {"glieder": [], "extra": set(), "schritte": []}
    tage = [_d(x["datum"]) for x in g]
    if f["modus"] == "toleranz" and not mutant("m25_anker_wie_m16"):
        grenze = _plus(tage[-1], -2 * m) - dt.timedelta(days=T)
        kand = [i for i in range(len(g)) if tage[i] >= grenze and all(
            not (_passt(f, g[i], g[j]) and (tage[j] - tage[i]).days > T) for j in range(i + 1, len(g)))]
    else:
        kand = [i for i in zul if (tage[zul[-1]] - tage[i]).days <= T]
    laeufe = {i: _lauf(g, i, m, f) for i in kand}

    def gleich(i):
        gl = laeufe[i][0]
        return len(gl) > 1 and g[i]["x"] == g[gl[1]]["x"]

    a = max(kand, key=lambda i: (len(laeufe[i][0]), gleich(i), i))
    glieder, extra, schritte = laeufe[a]
    if len(kand) > 1:
        schritte = [_schritt(g, tage, m, "anker", None, a, None, [i for i in kand if i != a],
                             kandidaten=[{**_ref(g[i]), "laenge": len(laeufe[i][0]), "gleicher_betrag": gleich(i)}
                                         for i in kand])] + schritte
    return {"glieder": sorted(glieder), "extra": set(extra), "schritte": schritte}


def mehrheit_verletzt(g: list[dict], kt: dict, f: dict) -> bool:
    if f["quelle"] != "vorgabe" or mutant("m25_ohne_mehrheitsregel") or not kt["glieder"]:
        return False
    erstes = kt["glieder"][0]
    rest = [i for i in range(erstes, len(g)) if i not in kt["glieder"] and i not in kt["extra"]]
    return len(rest) > len(kt["glieder"])


def euro(cent: int) -> str:
    e, c = divmod(abs(cent), 100)
    return f"{e:,}".replace(",", ".") + f",{c:02d} €"


def filter_text(f: dict) -> str:
    herkunft = "Vorgabe" if f["quelle"] == "vorgabe" else "Einstellung des Empfängers"
    teil = {"toleranz": lambda: f"Toleranz ±{f['toleranz_prozent']} %",
            "mindestschwelle": lambda: f"nur Beträge ab {euro(f['mindestbetrag'])}", "aus": lambda: "aus"}
    return f"Betragsfilter: {teil[f['modus']]()} ({herkunft})"


# ================================================================ REST
def _pruefe(body, nur_vorgabe: bool) -> dict:
    def fehler(det):
        raise Fehler(422, "validierung", "Ungültige Anfrage", det)

    if not isinstance(body, dict) or set(body) - {"modus", "toleranz_prozent", "mindestbetrag"} \
            or body.get("modus") not in ("aus", "toleranz", "mindestschwelle"):
        fehler([{"ort": ["body"], "meldung": "Körper ungültig"}])
    for k in ("toleranz_prozent", "mindestbetrag"):
        v = body.get(k)
        if v is not None and (type(v) is not int):
            fehler([{"ort": ["body", k], "meldung": "Ganzzahl erwartet"}])
    m, p, b = body["modus"], body.get("toleranz_prozent"), body.get("mindestbetrag")
    det = []
    if nur_vorgabe and m == "mindestschwelle":
        det.append({"ort": ["body", "modus"], "meldung": "Vorgabe nur aus oder toleranz"})
    if (m == "toleranz" and (p is None or not 0 <= p <= 100)) or (m != "toleranz" and p is not None):
        det.append({"ort": ["body", "toleranz_prozent"], "meldung": "Toleranz ungültig"})
    if (m == "mindestschwelle" and (b is None or not 0 < b <= BETRAG_MAX)) or (m != "mindestschwelle" and b is not None):
        det.append({"ort": ["body", "mindestbetrag"], "meldung": "Mindestbetrag ungültig"})
    if det:
        fehler(det)
    return {"modus": m, "toleranz_prozent": p if m == "toleranz" else None,
            "mindestbetrag": b if m == "mindestschwelle" else None}


def _eintrag(e: dict) -> dict:
    w = e["wiederkehrend"]
    return {"empfaenger": {"id": e["id"], "name": e["name"]}, **w}


EMPF_PFAD = re.compile(r"/api/empfaenger(/\d+)?(/zusammenfuehren)?")


def m25_einbinden(app: FastAPI, buch) -> None:
    @app.middleware("http")
    async def ohne_einstellung(request: Request, call_next):
        """GET/PATCH/POST /api/empfaenger… liefern das Feld ``wiederkehrend`` nicht (9.4)."""
        antwort = await call_next(request)
        if not EMPF_PFAD.fullmatch(request.url.path) or mutant("m25_empfaenger_mit_feld"):
            return antwort
        if "application/json" not in antwort.headers.get("content-type", ""):
            return antwort
        roh = b"".join([teil async for teil in antwort.body_iterator])
        daten = json.loads(roh)

        def weg(x):
            return {k: v for k, v in x.items() if k != "wiederkehrend"} if isinstance(x, dict) else x

        daten = [weg(x) for x in daten] if isinstance(daten, list) else weg(daten)
        koepfe = {k: v for k, v in antwort.headers.items() if k.lower() != "content-length"}
        return Response(json.dumps(daten, ensure_ascii=False).encode("utf-8"), status_code=antwort.status_code,
                        headers=koepfe, media_type="application/json")

    @app.get("/api/wiederkehrend/einstellungen")
    def einstellungen():
        v = vorgabe(buch)
        eigen = sorted((e for e in buch.empfaenger.values() if e.get("wiederkehrend")),
                       key=lambda e: (e["name"], e["id"]))
        return {"vorgabe": {"modus": v["modus"], "toleranz_prozent": v["toleranz_prozent"]},
                "empfaenger": [_eintrag(e) for e in eigen]}

    @app.put("/api/wiederkehrend/einstellungen/vorgabe")
    async def vorgabe_setzen(request: Request):
        try:
            body = await request.json()
        except ValueError:
            body = None
        w = _pruefe(body, nur_vorgabe=not mutant("m25_vorgabe_schwelle_erlaubt"))
        buch._wk_vorgabe = {"modus": w["modus"], "toleranz_prozent": w["toleranz_prozent"]}
        return dict(buch._wk_vorgabe)

    @app.put("/api/empfaenger/{empfaenger_id}/wiederkehrend")
    async def filter_setzen(empfaenger_id: int, request: Request):
        try:
            body = await request.json()
        except ValueError:
            body = None
        if not (isinstance(body, dict) and body.get("modus") in ("aus", "toleranz", "mindestschwelle")
                and set(body) <= {"modus", "toleranz_prozent", "mindestbetrag"}
                and all(body.get(k) is None or type(body.get(k)) is int
                        for k in ("toleranz_prozent", "mindestbetrag"))):
            _pruefe(body, nur_vorgabe=False)
        if empfaenger_id not in buch.empfaenger:
            raise Fehler(404, "nicht_gefunden", "Empfänger nicht gefunden")
        w = _pruefe(body, nur_vorgabe=False)
        buch.empfaenger[empfaenger_id]["wiederkehrend"] = w
        return _eintrag(buch.empfaenger[empfaenger_id])

    @app.delete("/api/empfaenger/{empfaenger_id}/wiederkehrend", status_code=204)
    def filter_loeschen(empfaenger_id: int):
        e = buch.empfaenger.get(empfaenger_id)
        if e is None or not e.get("wiederkehrend"):
            raise Fehler(404, "nicht_gefunden", "Keine eigene Einstellung")
        del e["wiederkehrend"]
        return Response(status_code=204)
