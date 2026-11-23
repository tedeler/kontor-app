"""Unabhängiges Orakel für wiederkehrende Buchungen (wiederkehrend.md 2 und 3; Kette nach M16, E-192, E-193).

Arbeitet auf der REST-Darstellung (Buchungen, Konten, Kredite) und liefert Serien im Schema
``WiederkehrendSerie`` sowie die Ereignisschlüssel.

Ab M25 (``wiederkehrend.md`` 9, E-240) mit Betragsfilter: ``filt`` = ``{"modus", "toleranz_prozent",
"mindestbetrag", "quelle"}`` je Gruppe (``None`` bzw. Modus ``aus`` = Regeln von M16 unverändert). Funktionen mit
dem Parameter ``filter_von`` erhalten eine Abbildung Empfänger-ID → Filter.
"""

from __future__ import annotations

import datetime as dt

from .kredit_orakel import monat_plus

T = 5
RHYTHMEN = [("monatlich", 1, 3), ("vierteljaehrlich", 3, 3), ("jaehrlich", 12, 2)]
BESTAND = {"girokonto", "sparkonto", "kreditkonto"}


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def eintraege(buchungen: list[dict], konten: list[dict], kredite: list[dict] = ()) -> list[dict]:
    art = {k["id"]: k["art"] for k in konten}
    darlehen = {k["konto_id"] for k in kredite}
    aus = []
    for b in buchungen:
        if b["empfaenger"] is None:
            continue
        summe: dict[int, int] = {}
        for s in b["splits"]:
            if art[s["konto_id"]] in BESTAND and s["konto_id"] not in darlehen:
                summe[s["konto_id"]] = summe.get(s["konto_id"], 0) + s["betrag"]
        for k in sorted(summe):
            x = summe[k]
            if x != 0:
                aus.append({"konto_id": k, "empfaenger": b["empfaenger"], "richtung": "ausgabe" if x < 0 else "einnahme",
                            "datum": b["datum"], "buchung_id": b["id"], "betrag": x})
    return aus


def gruppen(eintr: list[dict]) -> dict[tuple, list[dict]]:
    g: dict[tuple, list[dict]] = {}
    for e in eintr:
        g.setdefault((e["konto_id"], e["empfaenger"]["id"], e["richtung"]), []).append(e)
    for v in g.values():
        v.sort(key=lambda e: (e["datum"], e["buchung_id"]))
    return g


def _kurz(e: dict) -> dict:
    return {"buchung_id": e["buchung_id"], "datum": e["datum"], "betrag": e["betrag"]}


def _schritt(ergebnis: str, grund: str | None, von: dict, vorgaenger: dict | None, m: int,
             uebersprungen: list[dict], fremd: dict | None = None, kandidaten: list[dict] | None = None) -> dict:
    erwartet = monat_plus(_d(vorgaenger["datum"]), m) if vorgaenger else None
    return {"ergebnis": ergebnis, "grund": grund, "von": _kurz(von),
            "vorgaenger": _kurz(vorgaenger) if vorgaenger else None,
            "erwartet": erwartet.isoformat() if erwartet else None,
            "abweichung_tage": (_d(von["datum"]) - erwartet).days if erwartet else None,
            "uebersprungen": [_kurz(x) for x in uebersprungen], "fremd": _kurz(fremd) if fremd else None,
            "kandidaten": kandidaten or []}


def _kette_ab(g: list[dict], a: int, m: int) -> tuple[list[int], set[int], list[dict]]:
    """Rückwärts verketten ab Index ``a`` (M16-Definition 1.2, E-193).

    Ergebnis: Glieder (Indizes, jüngstes zuerst), als zusätzlich erkannte Indizes, Schritte ab dem ersten
    ``verbunden`` bis zum ``bruch``.
    """
    d = [_d(e["datum"]) for e in g]
    glieder, zus, schritte = [a], set(), []
    c, vorige = a, set()
    while True:
        kand = [x for x in range(c) if abs((d[c] - monat_plus(d[x], m)).days) <= T]
        if not kand:
            k, ueb = c - 1, []
            while k >= 0 and (d[c] - d[k]).days <= T:
                ueb.append(k)
                k -= 1
            zus.update(ueb)
            schritte.append(_schritt("bruch", "abstand" if k >= 0 else "kein_vorgaenger", g[c],
                                     g[k] if k >= 0 else None, m, [g[x] for x in sorted(ueb)]))
            return glieder, zus, schritte
        p = min(kand, key=lambda x: (g[x]["betrag"] != g[c]["betrag"], abs((d[c] - monat_plus(d[x], m)).days), -x))

        def ist_zusaetzlich(x: int) -> bool:
            return (d[c] - d[x]).days <= T or (d[x] - d[p]).days <= T or x in vorige

        dazwischen = range(p + 1, c)
        ueb = [x for x in dazwischen if ist_zusaetzlich(x)]
        fremd = [x for x in dazwischen if not ist_zusaetzlich(x)]
        zus.update(ueb)
        if fremd:
            schritte.append(_schritt("bruch", "fremde_zahlung", g[c], g[p], m, [g[x] for x in ueb], g[max(fremd)]))
            return glieder, zus, schritte
        schritte.append(_schritt("verbunden", None, g[c], g[p], m, [g[x] for x in ueb]))
        glieder.append(p)
        vorige, c = set(kand), p


def kette(g: list[dict], m: int) -> dict:
    """Kette einer Gruppe (sortiert nach datum, buchung_id) für ``m`` Monate nach M16-Definition 1.

    Ergebnis: ``glieder`` (Einträge in zeitlicher Reihenfolge), ``zusaetzlich`` (Menge der buchung_id),
    ``schritte`` (Kettenprotokoll wie ``BegruendungSchritt`` ohne ``text``).
    """
    if not g:
        return {"glieder": [], "zusaetzlich": set(), "schritte": []}
    jung = _d(g[-1]["datum"])
    anker_kand = [i for i in range(len(g)) if (jung - _d(g[i]["datum"])).days <= T]
    ketten = {i: _kette_ab(g, i, m) for i in anker_kand}

    def gleich(i: int) -> bool:
        gl = ketten[i][0]
        return len(gl) >= 2 and g[i]["betrag"] == g[gl[1]]["betrag"]

    a = max(anker_kand, key=lambda i: (len(ketten[i][0]), gleich(i), i))
    glieder, zus, schritte = ketten[a]
    zus = zus | {i for i in anker_kand if i != a}
    if len(anker_kand) > 1:
        kandidaten = [{**_kurz(g[i]), "laenge": len(ketten[i][0]), "gleicher_betrag": gleich(i)} for i in anker_kand]
        schritte = [_schritt("anker", None, g[a], None, m, [g[i] for i in anker_kand if i != a],
                             kandidaten=kandidaten)] + schritte
    assert not zus & set(glieder)
    return {"glieder": [g[i] for i in reversed(glieder)], "zusaetzlich": {g[i]["buchung_id"] for i in zus},
            "schritte": schritte}


# ------------------------------------------------------------------ M25: Betragsfilter (wiederkehrend.md 9)
AUS = {"modus": "aus", "toleranz_prozent": None, "mindestbetrag": None, "quelle": "vorgabe"}
VORGABE = {"modus": "toleranz", "toleranz_prozent": 10, "mindestbetrag": None, "quelle": "vorgabe"}


def aktiv(filt: dict | None) -> bool:
    return bool(filt) and filt["modus"] != "aus"


def zugelassen(filt: dict | None, x: dict) -> bool:
    return not (filt and filt["modus"] == "mindestschwelle") or abs(x["betrag"]) >= filt["mindestbetrag"]


def passt(filt: dict | None, c: dict, x: dict) -> bool:
    """passt(c, x) nach 9.1: x zugelassen und bei Toleranz |x − c| · 100 ≤ p · |c|."""
    if not zugelassen(filt, x):
        return False
    if filt and filt["modus"] == "toleranz":
        return abs(x["betrag"] - c["betrag"]) * 100 <= filt["toleranz_prozent"] * abs(c["betrag"])
    return True


def _kette_gefiltert_ab(g: list[dict], a: int, m: int, filt: dict) -> tuple[list[int], set[int], list[dict]]:
    """Kette ab Anker ``a`` mit Betragsfilter (9.2.2–9.2.4)."""
    d = [_d(e["datum"]) for e in g]
    glieder, zus, schritte = [a], set(), []
    juenger = [x for x in range(a + 1, len(g))]
    zus.update(x for x in juenger if passt(filt, g[a], g[x]))
    streng = any(not passt(filt, g[a], g[x]) for x in juenger)
    anker_zus = sorted(x for x in juenger if x in zus)
    c, vorige = a, set()
    while True:
        kand = [x for x in range(c) if zugelassen(filt, g[x]) and abs((d[c] - monat_plus(d[x], m)).days) <= T]
        if not kand:
            aelter = [x for x in range(c - 1, -1, -1) if passt(filt, g[c], g[x])]
            ueb = [x for x in aelter if (d[c] - d[x]).days <= T]
            weiter = [x for x in aelter if (d[c] - d[x]).days > T]
            zus.update(ueb)
            k = weiter[0] if weiter else None
            schritte.append(_schritt("bruch", "abstand" if k is not None else "kein_vorgaenger", g[c],
                                     g[k] if k is not None else None, m, [g[x] for x in sorted(ueb)]))
            return glieder, zus, schritte, anker_zus
        p = min(kand, key=lambda x: (g[x]["betrag"] != g[c]["betrag"], not passt(filt, g[c], g[x]),
                                     abs((d[c] - monat_plus(d[x], m)).days), -x))

        def ist_zusaetzlich(x: int) -> bool:
            return (d[c] - d[x]).days <= T or (d[x] - d[p]).days <= T or x in vorige

        dazwischen = range(p + 1, c)
        zaehlt = [x for x in dazwischen if passt(filt, g[c], g[x]) or passt(filt, g[p], g[x])]
        uebergangen = [x for x in dazwischen if x not in zaehlt]
        ueb = [x for x in zaehlt if ist_zusaetzlich(x)]
        fremd = [x for x in zaehlt if not ist_zusaetzlich(x)]
        zus.update(ueb)
        if fremd:
            schritte.append(_schritt("bruch", "fremde_zahlung", g[c], g[p], m, [g[x] for x in ueb], g[max(fremd)]))
            return glieder, zus, schritte, anker_zus
        if not passt(filt, g[c], g[p]) and (streng or uebergangen):
            schritte.append(_schritt("bruch", "betrag", g[c], g[p], m, [g[x] for x in ueb]))
            return glieder, zus, schritte, anker_zus
        schritte.append(_schritt("verbunden", None, g[c], g[p], m, [g[x] for x in ueb]))
        glieder.append(p)
        streng = streng or bool(uebergangen)
        vorige, c = set(kand), p


def kette_gefiltert(g: list[dict], m: int, filt: dict) -> dict:
    """Kette nach 9.2 (Modus toleranz oder mindestschwelle); Ergebnis wie :func:`kette`."""
    zul = [i for i in range(len(g)) if zugelassen(filt, g[i])]
    if not zul:
        return {"glieder": [], "zusaetzlich": set(), "schritte": []}
    d = [_d(e["datum"]) for e in g]
    if filt["modus"] == "toleranz":
        grenze = monat_plus(d[-1], -2 * m) - dt.timedelta(days=T)
        anker_kand = [i for i in range(len(g)) if d[i] >= grenze and not any(
            passt(filt, g[i], g[j]) and (d[j] - d[i]).days > T for j in range(i + 1, len(g)))]
    else:
        jung = d[zul[-1]]
        anker_kand = [i for i in zul if (jung - d[i]).days <= T]
    ketten = {i: _kette_gefiltert_ab(g, i, m, filt) for i in anker_kand}

    def gleich(i: int) -> bool:
        gl = ketten[i][0]
        return len(gl) >= 2 and g[i]["betrag"] == g[gl[1]]["betrag"]

    a = max(anker_kand, key=lambda i: (len(ketten[i][0]), gleich(i), i))
    glieder, zus, schritte, anker_zus = ketten[a]
    if len(anker_kand) > 1:
        kandidaten = [{**_kurz(g[i]), "laenge": len(ketten[i][0]), "gleicher_betrag": gleich(i)} for i in anker_kand]
        # uebersprungen des Ankerschritts: die anderen Kandidaten (wiederkehrend.md 8.3, E-240 Nr. 3)
        schritte = [_schritt("anker", None, g[a], None, m, [g[i] for i in anker_kand if i != a],
                             kandidaten=kandidaten)] + schritte
    assert not zus & set(glieder)
    return {"glieder": [g[i] for i in reversed(glieder)], "zusaetzlich": {g[i]["buchung_id"] for i in zus},
            "schritte": schritte}


def kette_mit_filter(g: list[dict], m: int, filt: dict | None) -> dict:
    return kette_gefiltert(g, m, filt) if aktiv(filt) else kette(g, m)


def uebergangen_ab_beginn(g: list[dict], k: dict) -> int:
    """Mehrheitsregel 9.2.5: Einträge ab dem ältesten Glied bis zum jüngsten, die weder Glied noch zusätzlich sind."""
    if not k["glieder"]:
        return 0
    erstes = (k["glieder"][0]["datum"], k["glieder"][0]["buchung_id"])
    glied = {e["buchung_id"] for e in k["glieder"]}
    return sum(1 for e in g if (e["datum"], e["buchung_id"]) >= erstes and e["buchung_id"] not in glied
               and e["buchung_id"] not in k["zusaetzlich"])


def serie_mit_rhythmen(gruppe: list[dict], stichtag: dt.date | None, filt: dict | None = None
                       ) -> tuple[dict | None, list[dict], dict | None]:
    """(Serie, geprüfte Rhythmen mit Kette, Kette des ersten erfüllten Rhythmus) nach wiederkehrend.md 2.3
    (ab M25 mit Betragsfilter und Mehrheitsregel 9.2.5)."""
    geprueft = []
    for name, m, mindest in RHYTHMEN:
        k = kette_mit_filter(gruppe, m, filt)
        erfuellt = len(k["glieder"]) >= mindest
        if erfuellt and aktiv(filt) and filt["quelle"] == "vorgabe":
            erfuellt = uebergangen_ab_beginn(gruppe, k) <= len(k["glieder"])
        geprueft.append({"rhythmus": name, "monate": m, "mindestanzahl": mindest, "laenge": len(k["glieder"]),
                         "erfuellt": erfuellt, "kette": k})
        if not erfuellt:
            continue
        glieder = k["glieder"]
        letzte = _d(glieder[-1]["datum"])
        f, f2 = monat_plus(letzte, m), monat_plus(letzte, 2 * m)
        status = None
        if stichtag is not None:
            tol = dt.timedelta(days=T)
            status = "aktiv" if stichtag <= f + tol else "ausbleibend" if stichtag <= f2 + tol else "beendet"
        e0 = glieder[-1]
        s = {"schluessel": f"{e0['konto_id']}:{e0['empfaenger']['id']}:{e0['richtung']}",
             "konto_id": e0["konto_id"], "empfaenger": e0["empfaenger"], "richtung": e0["richtung"],
             "rhythmus": name, "anzahl": len(glieder), "erste": glieder[0]["datum"], "letzte": e0["datum"],
             "betrag": e0["betrag"], "jahreskosten": -e0["betrag"] * 12 // m,
             "naechste_faelligkeit": f.isoformat(), "status": status,
             "buchung_ids": [e["buchung_id"] for e in glieder]}
        return s, geprueft, k
    return None, geprueft, None


def serie(gruppe: list[dict], stichtag: dt.date | None, filt: dict | None = None) -> dict | None:
    """Serie einer Gruppe nach wiederkehrend.md 2.3 mit der Kette aus M16 (2.2 ersetzt, E-192), ab M25 gefiltert."""
    return serie_mit_rhythmen(gruppe, stichtag, filt)[0]


def _filter(filter_von, empfaenger_id: int) -> dict | None:
    if filter_von is None:
        return None
    return filter_von(empfaenger_id) if callable(filter_von) else filter_von.get(empfaenger_id)


def uebersicht(buchungen: list[dict], konten: list[dict], kredite: list[dict], stichtag: str,
               filter_von=None) -> dict:
    h = _d(stichtag)
    bis = [b for b in buchungen if b["datum"] <= stichtag]
    serien = []
    for _, g in sorted(gruppen(eintraege(bis, konten, kredite)).items(),
                       key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] != "ausgabe")):
        s = serie(g, h, _filter(filter_von, _[1]))
        if s:
            serien.append(s)
    return {"stichtag": stichtag, "serien": serien,
            "summe_jahreskosten": sum(s["jahreskosten"] for s in serien
                                      if s["richtung"] == "ausgabe" and s["status"] != "beendet")}


def ereignisse(buchungen: list[dict], konten: list[dict], kredite: list[dict], buchung_ids: list[int],
               heute: str, filter_von=None) -> list[tuple[str, str]]:
    """(art, schluessel) in Entstehungsreihenfolge nach wiederkehrend.md 4 (ohne Entprellung)."""
    nach_id = {b["id"]: b for b in buchungen}
    alle = eintraege(buchungen, konten, kredite)
    g = gruppen(alle)
    aus: list[tuple[str, str]] = []
    for bid in sorted(buchung_ids):
        b = nach_id[bid]
        eig = [e for e in alle if e["buchung_id"] == bid]
        if any(e["richtung"] == "ausgabe" for e in eig):
            e_id = b["empfaenger"]["id"]
            frueher = [x for x in buchungen if x["empfaenger"] and x["empfaenger"]["id"] == e_id and x["id"] != bid
                       and (x["datum"], x["id"]) < (b["datum"], b["id"])]
            if not frueher:
                aus.append(("neuer_empfaenger", f"neuer_empfaenger:{e_id}"))
        for e in eig:
            filt = _filter(filter_von, e["empfaenger"]["id"])
            if not zugelassen(filt, e):
                continue
            hist = [x for x in g[(e["konto_id"], e["empfaenger"]["id"], e["richtung"])]
                    if (x["datum"], x["buchung_id"]) < (e["datum"], e["buchung_id"])]
            s = serie(hist, None, filt) if hist else None
            if s and abs((_d(b["datum"]) - _d(s["naechste_faelligkeit"])).days) <= T and e["betrag"] != s["betrag"]:
                aus.append(("wiederkehrend_betrag", f"wiederkehrend_betrag:{bid}"))
                break
    for s in uebersicht(buchungen, konten, kredite, heute, filter_von)["serien"]:
        if s["status"] == "ausbleibend":
            aus.append(("wiederkehrend_ausbleibend",
                        f"wiederkehrend_ausbleibend:{s['schluessel']}:{s['naechste_faelligkeit']}"))
    return aus
