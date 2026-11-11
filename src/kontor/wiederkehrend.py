"""Wiederkehrende Buchungen und unerwartete Buchungen (wiederkehrend.md, Meilenstein 5).

Die Erkennung ist eine Funktion des Buchbestands ohne eigenen Zustand: Bei jeder Abfrage werden die Einträge
(Buchung mit Empfänger × Bestandskonto) gebildet, je (Konto, Empfänger, Richtung) gruppiert und von der jüngsten
Zahlung rückwärts zu einer Kette mit dem Rhythmus monatlich, vierteljährlich oder jährlich verbunden. Nichts davon
wird gespeichert, protokolliert oder gesichert. Benachrichtigungen entstehen nur bei der Prüfung (4, 5); je
Ereignisschlüssel höchstens eine (gelesen oder nicht, E-100).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from . import buch
from .buch import ApiFehler
from .kredite import monat_plus
from .text import euro

T = 5
RHYTHMEN = (("monatlich", 1, 3), ("vierteljaehrlich", 3, 3), ("jaehrlich", 12, 2))
RHYTHMUS_TEXT = {"monatlich": "monatlich", "vierteljaehrlich": "vierteljährlich", "jaehrlich": "jährlich"}


@dataclass(frozen=True)
class Eintrag:
    konto_id: int
    empfaenger_id: int
    empfaenger_name: str
    richtung: str
    datum: str
    buchung_id: int
    betrag: int

    @property
    def gruppe(self) -> tuple[int, int, str]:
        return (self.konto_id, self.empfaenger_id, self.richtung)


def eintraege(con, stichtag: str | None = None, buchung_ids: list[int] | None = None,
              empfaenger_id: int | None = None) -> list[Eintrag]:
    """wiederkehrend.md 2.1 (sortiert nach Gruppe, Datum, Buchung)."""
    sql = ("SELECT b.id AS bid, b.datum AS datum, b.empfaenger_id AS eid, e.name AS ename, s.konto_id AS kid,"
           " SUM(s.betrag) AS x FROM buchung b JOIN empfaenger e ON e.id = b.empfaenger_id"
           " JOIN split s ON s.buchung_id = b.id JOIN konto k ON k.id = s.konto_id"
           " WHERE k.art IN ('girokonto','sparkonto','kreditkonto')"
           " AND NOT EXISTS (SELECT 1 FROM kredit kr WHERE kr.konto_id = s.konto_id)")
    par: list = []
    if stichtag is not None:
        sql += " AND b.datum <= ?"
        par.append(stichtag)
    if buchung_ids is not None:
        sql += f" AND b.id IN ({buch._platzhalter(len(buchung_ids))})"
        par.extend(buchung_ids)
    if empfaenger_id is not None:
        sql += " AND b.empfaenger_id = ?"
        par.append(empfaenger_id)
    sql += " GROUP BY b.id, s.konto_id HAVING SUM(s.betrag) <> 0"
    aus = [Eintrag(r["kid"], r["eid"], r["ename"], "ausgabe" if r["x"] < 0 else "einnahme", r["datum"], r["bid"],
                   r["x"]) for r in con.execute(sql, par)]
    aus.sort(key=lambda e: (e.gruppe, e.datum, e.buchung_id))
    return aus


def gruppen(eintr: list[Eintrag]) -> dict[tuple[int, int, str], list[Eintrag]]:
    g: dict[tuple[int, int, str], list[Eintrag]] = defaultdict(list)
    for e in eintr:
        g[e.gruppe].append(e)
    for v in g.values():
        v.sort(key=lambda e: (e.datum, e.buchung_id))
    return g


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


@dataclass
class Kette:
    """Ergebnis der Kettenbildung für einen Rhythmus (Indizes in die Gruppe)."""
    glieder: list[int]          # absteigend vom jüngsten Eintrag
    zusaetzlich: list[int]      # übersprungene Einträge um einen Termin
    schritte: list[dict]        # Kettenprotokoll (verbunden … bruch)


def _passend(c: Eintrag, kandidaten: list[int], gruppe: list[Eintrag], m: int) -> int:
    """Wählt unter den Kandidaten für den Vorgänger von ``c``: gleicher Betrag vor Datumsnähe, bei Gleichstand der
    jüngere Eintrag."""
    cd = _d(c.datum)
    return min(kandidaten, key=lambda i: (gruppe[i].betrag != c.betrag,
                                           abs((cd - monat_plus(_d(gruppe[i].datum), m)).days), -i))


def kette_bilden(gruppe: list[Eintrag], m: int) -> Kette:
    """Kette vom jüngsten Eintrag rückwärts (D-108).

    Vorgänger eines Glieds ``c`` sind alle älteren Einträge ``x`` mit ``|c.datum − monat_plus(x.datum, m)| ≤ T``
    (Termin-Fenster); davon zählt der passendste (gleicher Betrag, dann Datumsnähe). Einträge zwischen Vorgänger und
    ``c`` sind **zusätzliche Zahlungen** und brechen die Kette nicht, wenn sie höchstens ``T`` Tage von ``c`` oder vom
    Vorgänger entfernt liegen oder selbst im Termin-Fenster lagen. Jeder andere Eintrag dazwischen und ein fehlender
    Vorgänger beenden die Kette.
    """
    c = len(gruppe) - 1
    glieder, zusaetzlich, schritte = [c], [], []
    fenster_vorher: set[int] = set()
    while True:
        cd = _d(gruppe[c].datum)
        kand = []
        for i in range(c - 1, -1, -1):  # absteigend; monat_plus ist monoton, also früh abbrechen
            ab = (cd - monat_plus(_d(gruppe[i].datum), m)).days
            if ab > T:
                break
            if ab >= -T:
                kand.append(i)
        kand.reverse()
        if not kand:
            # Einträge am selben Termin wie das erste Glied sind zusätzliche Zahlungen, kein Grund für den Bruch.
            v = c - 1
            neben = []
            while v >= 0 and abs((_d(gruppe[v].datum) - cd).days) <= T:
                neben.append(v)
                v -= 1
            zusaetzlich.extend(neben)
            schritte.append({"ergebnis": "bruch", "grund": "kein_vorgaenger" if v < 0 else "abstand",
                             "von": c, "vorgaenger": v if v >= 0 else None, "uebersprungen": neben})
            break
        p = _passend(gruppe[c], kand, gruppe, m)
        dazwischen = list(range(p + 1, c))
        pd = _d(gruppe[p].datum)
        fremd = [i for i in dazwischen if i not in fenster_vorher and i not in kand
                 and abs((_d(gruppe[i].datum) - cd).days) > T and abs((_d(gruppe[i].datum) - pd).days) > T]
        if fremd:
            schritte.append({"ergebnis": "bruch", "grund": "fremde_zahlung", "von": c, "vorgaenger": p,
                             "fremd": fremd[-1], "uebersprungen": []})
            break
        schritte.append({"ergebnis": "verbunden", "von": c, "vorgaenger": p, "uebersprungen": dazwischen[::-1]})
        zusaetzlich.extend(dazwischen[::-1])
        fenster_vorher = set(kand)
        glieder.append(p)
        c = p
    return Kette(glieder, zusaetzlich, schritte)


def serie(gruppe: list[Eintrag], stichtag: dt.date | None) -> dict | None:
    """wiederkehrend.md 2.2–2.4 mit D-108; ``None``, wenn die Gruppe keine Serie ist."""
    for name, m, mindest in RHYTHMEN:
        k = kette_bilden(gruppe, m)
        if len(k.glieder) < mindest:
            continue
        kt = [gruppe[i] for i in reversed(k.glieder)]
        letzte = _d(kt[-1].datum)
        f, f2 = monat_plus(letzte, m), monat_plus(letzte, 2 * m)
        status = None
        if stichtag is not None:
            tol = dt.timedelta(days=T)
            status = "aktiv" if stichtag <= f + tol else "ausbleibend" if stichtag <= f2 + tol else "beendet"
        e0 = kt[-1]
        return {"schluessel": f"{e0.konto_id}:{e0.empfaenger_id}:{e0.richtung}", "konto_id": e0.konto_id,
                "empfaenger": {"id": e0.empfaenger_id, "name": e0.empfaenger_name}, "richtung": e0.richtung,
                "rhythmus": name, "anzahl": len(kt), "erste": kt[0].datum, "letzte": kt[-1].datum,
                "betrag": e0.betrag, "jahreskosten": -e0.betrag * (12 // m), "naechste_faelligkeit": f.isoformat(),
                "status": status, "buchung_ids": [e.buchung_id for e in kt]}
    return None


def uebersicht(con, stichtag: str) -> dict:
    """``GET /api/wiederkehrend`` (2.5)."""
    h = _d(stichtag)
    serien = []
    for _, g in sorted(gruppen(eintraege(con, stichtag)).items(),
                       key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] != "ausgabe")):
        s = serie(g, h)
        if s is not None:
            serien.append(s)
    return {"stichtag": stichtag, "serien": serien,
            "summe_jahreskosten": sum(s["jahreskosten"] for s in serien
                                      if s["richtung"] == "ausgabe" and s["status"] != "beendet")}


# ================================================================ Begründung (D-109)

MONATE_TEXT = {1: "1 Monat", 3: "3 Monate", 12: "12 Monate"}


def _kurz(e: Eintrag) -> dict:
    return {"buchung_id": e.buchung_id, "datum": e.datum, "betrag": e.betrag}


def _kurz_text(e: Eintrag) -> str:
    return f"{_de(e.datum)} ({euro(e.betrag)})"


def _schritt_text(sch: dict, gruppe: list[Eintrag], m: int) -> dict:
    """Ein Schritt des Kettenprotokolls mit Daten und deutschem Satz."""
    c = gruppe[sch["von"]]
    cd = _d(c.datum)
    v = gruppe[sch["vorgaenger"]] if sch["vorgaenger"] is not None else None
    aus = {"ergebnis": sch["ergebnis"], "grund": sch.get("grund"), "von": _kurz(c),
           "vorgaenger": _kurz(v) if v else None, "erwartet": None, "abweichung_tage": None,
           "uebersprungen": [_kurz(gruppe[i]) for i in sch["uebersprungen"]],
           "fremd": _kurz(gruppe[sch["fremd"]]) if "fremd" in sch else None}
    rechnung = ""
    if v is not None:
        erw = monat_plus(_d(v.datum), m)
        aus["erwartet"] = erw.isoformat()
        aus["abweichung_tage"] = (cd - erw).days
        rechnung = (f"Vorgänger {_kurz_text(v)} + {MONATE_TEXT[m]} = {_de(erw.isoformat())}, "
                    f"Abweichung {abs((cd - erw).days)} Tage")
    if sch["ergebnis"] == "verbunden":
        t = f"{_kurz_text(c)}: {rechnung} ≤ {T} – verbunden."
        if v is not None and v.betrag != c.betrag:
            t += " Der Betrag weicht ab; es gab keinen Kandidaten mit gleichem Betrag."
        if aus["uebersprungen"]:
            t += " Als zusätzliche Zahlung übersprungen: " + ", ".join(
                _kurz_text(gruppe[i]) for i in sch["uebersprungen"]) + "."
    elif sch["grund"] == "kein_vorgaenger":
        t = f"{_kurz_text(c)}: Es gibt keine ältere Buchung in der Gruppe – die Kette beginnt hier."
    elif sch["grund"] == "abstand" and v is not None:
        t = (f"{_kurz_text(c)}: Nächste ältere Buchung {_kurz_text(v)}; + {MONATE_TEXT[m]} = "
             f"{_de(aus['erwartet'])}, Abweichung {abs(aus['abweichung_tage'])} Tage > {T} – die Kette beginnt hier.")
    else:
        f = gruppe[sch["fremd"]]
        t = (f"{_kurz_text(c)}: {rechnung} ≤ {T}, aber dazwischen liegt {_kurz_text(f)}, mehr als {T} Tage von "
             f"beiden Terminen entfernt – die Kette beginnt hier.")
    if aus["uebersprungen"] and sch["ergebnis"] == "bruch":
        t += " Am selben Termin als zusätzliche Zahlung übersprungen: " + ", ".join(
            _kurz_text(gruppe[i]) for i in sch["uebersprungen"]) + "."
    aus["text"] = t
    return aus


def _gruppe_begruenden(gruppe: list[Eintrag], e: Eintrag, h: dt.date, konto_name: str) -> dict:
    idx = next(i for i, x in enumerate(gruppe) if x.buchung_id == e.buchung_id)
    rhythmen: list[dict] = []
    treffer = None
    for name, m, mindest in RHYTHMEN:
        k = kette_bilden(gruppe, m)
        ok = len(k.glieder) >= mindest
        rhythmen.append({"rhythmus": name, "monate": m, "mindestanzahl": mindest, "laenge": len(k.glieder),
                         "erfuellt": ok, "schritte": [_schritt_text(sch, gruppe, m) for sch in k.schritte]})
        if ok:
            treffer = (name, k)
            break
    s = serie(gruppe, h)
    juengste = gruppe[-1]
    kopf = f"Gruppe {konto_name} · {e.empfaenger_name} · {'Ausgabe' if e.richtung == 'ausgabe' else 'Einnahme'}"
    if treffer is not None:
        name, k = treffer
        glieder = list(reversed(k.glieder))
        rt = RHYTHMUS_TEXT[name]
        if idx in glieder:
            urteil, glied = "glied", glieder.index(idx) + 1
            text = f"Wiederkehrend: Glied {glied} von {len(glieder)} der {rt}en Serie ({s['status'] if s is not None else ''})."
        elif idx in k.zusaetzlich:
            urteil, glied = "zusaetzlich", None
            sch = next(x for x in k.schritte if idx in x["uebersprungen"])
            nah = min((i for i in (sch["von"], sch["vorgaenger"]) if i is not None),
                      key=lambda i: abs((_d(gruppe[i].datum) - _d(e.datum)).days))
            text = (f"Nicht wiederkehrend: zusätzliche Zahlung neben dem Glied {_kurz_text(gruppe[nah])} der {rt}en "
                    "Serie. Am selben Termin zählt nur eine Buchung: zuerst die mit gleichem Betrag wie das "
                    "Nachfolgeglied, dann die mit dem genaueren Datum.")
        else:
            urteil, glied = "vor_beginn", None
            erste = gruppe[glieder[0]]
            text = (f"Nicht wiederkehrend: Die {rt}e Serie beginnt erst am {_de(erste.datum)}; ältere Buchungen gehören "
                    "nicht dazu, weil die Kette dort reißt.")
    else:
        urteil, glied = "keine_serie", None
        teile = [f"{RHYTHMUS_TEXT[str(r['rhythmus'])]} {r['laenge']} von mindestens {r['mindestanzahl']}" for r in rhythmen]
        text = ("Nicht wiederkehrend: Ab der jüngsten Buchung " + _kurz_text(juengste) +
                " erreicht keine Kette die Mindestanzahl (" + "; ".join(teile) + ").")
    return {"konto": {"id": e.konto_id, "name": konto_name}, "richtung": e.richtung, "betrag": e.betrag,
            "gruppe": kopf, "gruppe_anzahl": len(gruppe), "juengste": _kurz(juengste), "urteil": urteil,
            "glied": glied, "text": text, "serie": s, "rhythmen": rhythmen}


def begruendung(con, buchung_id: int, stichtag: str) -> dict:
    """``GET /api/buchungen/{id}/wiederkehrend`` (D-109): warum eine Buchung (nicht) wiederkehrend ist."""
    b = con.execute("SELECT b.id, b.datum, b.empfaenger_id, e.name AS ename FROM buchung b"
                    " LEFT JOIN empfaenger e ON e.id = b.empfaenger_id WHERE b.id = ?", (buchung_id,)).fetchone()
    if b is None:
        raise buch.nicht_gefunden("Die Buchung")
    aus: dict = {"buchung_id": buchung_id, "stichtag": stichtag, "urteil": "ausgeschlossen", "text": "",
                 "eintraege": [], "ausgeschlossen": []}
    if b["empfaenger_id"] is None:
        aus["text"] = "Nicht wiederkehrend: Die Buchung hat keinen Empfänger; nur Buchungen mit Empfänger zählen."
        return aus
    if b["datum"] > stichtag:
        aus["text"] = f"Nicht berücksichtigt: Die Buchung liegt nach dem Stichtag {_de(stichtag)}."
        return aus
    namen = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM konto")}
    for r in con.execute(
            "SELECT s.konto_id AS kid, k.art AS art, SUM(s.betrag) AS x,"
            " EXISTS (SELECT 1 FROM kredit kr WHERE kr.konto_id = s.konto_id) AS darlehen"
            " FROM split s JOIN konto k ON k.id = s.konto_id WHERE s.buchung_id = ? AND k.art IN"
            " ('girokonto','sparkonto','kreditkonto') GROUP BY s.konto_id ORDER BY s.konto_id", (buchung_id,)):
        if r["darlehen"]:
            aus["ausgeschlossen"].append({"konto": {"id": r["kid"], "name": namen[r["kid"]]}, "grund": "darlehenskonto",
                                          "text": "Darlehenskonto eines Kredits – wird nicht betrachtet."})
        elif r["x"] == 0:
            aus["ausgeschlossen"].append({"konto": {"id": r["kid"], "name": namen[r["kid"]]}, "grund": "summe_null",
                                          "text": "Die Splits auf diesem Konto ergeben zusammen 0."})
    h = _d(stichtag)
    g = gruppen(eintraege(con, stichtag, empfaenger_id=b["empfaenger_id"]))
    for gr in sorted(g.values(), key=lambda v: (v[0].konto_id, v[0].richtung != "ausgabe")):
        e = next((x for x in gr if x.buchung_id == buchung_id), None)
        if e is not None:
            aus["eintraege"].append(_gruppe_begruenden(gr, e, h, namen[e.konto_id]))
    if not aus["eintraege"]:
        aus["text"] = "Nicht wiederkehrend: Die Buchung berührt kein betrachtetes Bestandskonto (Giro, Spar, Karte)."
        return aus
    if any(x["urteil"] == "glied" for x in aus["eintraege"]):
        aus["urteil"] = "wiederkehrend"
    else:
        aus["urteil"] = "nicht_wiederkehrend"
    aus["text"] = " ".join(x["text"] for x in aus["eintraege"]) if len(aus["eintraege"]) == 1 else " ".join(
        f"{x['konto']['name']}: {x['text']}" for x in aus["eintraege"])
    return aus


# ================================================================ Ereignisse


def _ereignisse(con, buchung_ids: list[int], heute: str) -> list[dict]:
    """wiederkehrend.md 3 in Entstehungsreihenfolge (ohne Entprellung): je Ereignis art, schluessel, titel, text,
    link."""
    aus: list[dict] = []
    ids = sorted(set(buchung_ids))
    if ids:
        alle = eintraege(con)
        g = gruppen(alle)
        je_buchung: dict[int, list[Eintrag]] = defaultdict(list)
        for e in alle:
            je_buchung[e.buchung_id].append(e)
        for teil in buch._stueckweise(ids):
            koepfe = {r["id"]: r for r in con.execute(
                "SELECT b.id, b.datum, b.empfaenger_id, e.name AS ename FROM buchung b"
                " LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
                f" WHERE b.id IN ({buch._platzhalter(len(teil))})", teil)}
            for bid in teil:
                b = koepfe.get(bid)
                eig = sorted(je_buchung.get(bid, []), key=lambda e: e.konto_id)
                if b is None or not eig:
                    continue
                ausgabe = next((e for e in eig if e.richtung == "ausgabe"), None)
                if ausgabe is not None:
                    frueher = con.execute(
                        "SELECT 1 FROM buchung WHERE empfaenger_id = ? AND id <> ? AND (datum < ? OR (datum = ? AND id < ?))"
                        " LIMIT 1", (b["empfaenger_id"], bid, b["datum"], b["datum"], bid)).fetchone()
                    if frueher is None:
                        aus.append({"art": "neuer_empfaenger", "schluessel": f"neuer_empfaenger:{b['empfaenger_id']}",
                                    "titel": f"Neuer Empfänger: {b['ename']}",
                                    "text": f"Erste Zahlung an „{b['ename']}“ über {euro(ausgabe.betrag)} am "
                                            f"{_de(b['datum'])}. Bitte prüfen, ob die Buchung erwartet ist.",
                                    "link": f"/buchungen/{bid}"})
                for e in eig:
                    hist = [x for x in g[e.gruppe] if (x.datum, x.buchung_id) < (e.datum, e.buchung_id)]
                    s = serie(hist, None) if hist else None
                    if (s is not None and abs((_d(e.datum) - _d(s["naechste_faelligkeit"])).days) <= T
                            and e.betrag != s["betrag"]):
                        aus.append({"art": "wiederkehrend_betrag", "schluessel": f"wiederkehrend_betrag:{bid}",
                                    "titel": f"Geänderter Betrag: {e.empfaenger_name}",
                                    "text": f"Die {RHYTHMUS_TEXT[s['rhythmus']]}e Zahlung an bzw. von "
                                            f"„{e.empfaenger_name}“ am {_de(e.datum)} beträgt {euro(e.betrag)} statt "
                                            f"bisher {euro(s['betrag'])}.",
                                    "link": f"/buchungen/{bid}"})
                        break
    for s in uebersicht(con, heute)["serien"]:
        if s["status"] == "ausbleibend":
            aus.append({"art": "wiederkehrend_ausbleibend",
                        "schluessel": f"wiederkehrend_ausbleibend:{s['schluessel']}:{s['naechste_faelligkeit']}",
                        "titel": f"Zahlung ausgeblieben: {s['empfaenger']['name']}",
                        "text": f"Die {RHYTHMUS_TEXT[s['rhythmus']]}e Zahlung "
                                f"{'an' if s['richtung'] == 'ausgabe' else 'von'} „{s['empfaenger']['name']}“ über "
                                f"{euro(s['betrag'])}, fällig am {_de(s['naechste_faelligkeit'])}, ist nicht "
                                "eingegangen.",
                        "link": "/wiederkehrend"})
    return aus


def _de(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def pruefen(con, buchung_ids: list[int], heute: str, jetzt: str) -> list[dict]:
    """Erzeugt die Benachrichtigungen neuer Ereignisse (4 Schritt 3) und gibt sie in Entstehungsreihenfolge
    zurück. ``con`` muss in einer Schreibtransaktion sein."""
    neu = []
    for e in _ereignisse(con, buchung_ids, heute):
        if con.execute("SELECT 1 FROM benachrichtigung WHERE schluessel = ? LIMIT 1", (e["schluessel"],)).fetchone():
            continue
        nid = con.execute("INSERT INTO benachrichtigung (art, schluessel, titel, text, link, erstellt_am, gelesen)"
                          " VALUES (?, ?, ?, ?, ?, ?, 0)",
                          (e["art"], e["schluessel"], e["titel"], e["text"], e["link"], jetzt)).lastrowid
        neu.append(buch._benachrichtigung_dict(
            con.execute("SELECT * FROM benachrichtigung WHERE id = ?", (nid,)).fetchone()))
    return neu


def pruefen_rest(con, buchung_ids: list[int], heute: str, jetzt: str) -> dict:
    """``POST /api/wiederkehrend/pruefen``."""
    fehlend = sorted(set(buchung_ids) - buch._vorhandene_buchungen(con, buchung_ids)) if buchung_ids else []
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    return {"stichtag": heute, "benachrichtigungen": pruefen(con, buchung_ids, heute, jetzt)}


__all__ = ["uebersicht", "pruefen", "begruendung"]
