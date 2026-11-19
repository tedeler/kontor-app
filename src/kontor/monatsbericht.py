"""Monatsbericht: Ausgaben eines Monats rein statistisch, ohne Kategorien (Feature ``monatsbericht``, D-206).

Nur lesend, kein gespeicherter Zustand. Grundlage ist die **Wirkung** einer Buchung auf den Haushalt: die negierte
Summe ihrer Splits auf Konten, die keine Bestandskonten sind. Eine Umbuchung zwischen Bestandskonten hat die
Wirkung 0 und bleibt draußen, von einer Kreditrate zählt nur der Zinsanteil. Negative Wirkung ist eine Ausgabe,
positive eine Einnahme; ein Eingang, der nur gegen Aufwandskonten gebucht ist, gilt als Erstattung und mindert
die Ausgaben. Alle Beträge sind ganze Cent.
"""

from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict

from . import buch, wiederkehrend
from .buch import BESTAND, ApiFehler
from .statistik import AUSREISSER_HUNDERTSTEL, _mad, _median, _z_hundertstel

VERGLEICH_MONATE = 6          # Durchschnittslinie des Verlaufs und „üblich“ je Empfänger
RUECKBLICK_MONATE = 12        # Monatsvergleich, neue Empfänger, Basis der Ausreißer
TOP = 10
MIN_AUSREISSER_BASIS = 4      # frühere Ausgaben beim selben Empfänger
MIN_AUSREISSER_CENT = 500     # Abweichung vom Üblichen, ab der ein Ausreißer genannt wird
# Obergrenzen der Größenklassen in Cent (ausschließlich); die letzte Klasse ist nach oben offen
KLASSEN = (1_000, 5_000, 20_000, 100_000)
WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _monat_plus(jahr: int, monat: int, n: int) -> tuple[int, int]:
    i = jahr * 12 + (monat - 1) + n
    return i // 12, i % 12 + 1


def _grenzen(jahr: int, monat: int) -> tuple[dt.date, dt.date]:
    return dt.date(jahr, monat, 1), dt.date(jahr, monat, calendar.monthrange(jahr, monat)[1])


def _schluessel(d: dt.date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def monat_lesen(text: str | None, heute: str) -> tuple[int, int]:
    """``YYYY-MM`` → (Jahr, Monat); ohne Angabe der Monat von *heute*. ``ValueError`` bei ungültiger Angabe."""
    if text is None:
        h = dt.date.fromisoformat(heute)
        return h.year, h.month
    if len(text) != 7 or text[4] != "-" or not (text[:4] + text[5:]).isdigit():
        raise ValueError(text)
    jahr, monat = int(text[:4]), int(text[5:])
    if not (1 <= monat <= 12 and 1900 <= jahr <= 9998):
        raise ValueError(text)
    return jahr, monat


def klasse_von(betrag: int) -> int:
    for i, grenze in enumerate(KLASSEN):
        if betrag < grenze:
            return i
    return len(KLASSEN)


class _Posten:
    __slots__ = ("id", "datum", "betrag", "art", "empfaenger_id", "empfaenger", "zweck", "konto_id", "fix")

    def __init__(self, bid, datum, betrag, art, eid, ename, zweck, konto_id):
        self.id = bid
        self.datum = datum
        self.betrag = betrag          # immer positiv; ``art`` trägt die Richtung
        self.art = art                # ausgabe, erstattung, einnahme
        self.empfaenger_id = eid
        self.empfaenger = ename
        self.zweck = zweck
        self.konto_id = konto_id
        self.fix = False

    @property
    def netto(self) -> int:
        """Beitrag zu den Ausgaben: Erstattungen mindern, Einnahmen zählen nicht."""
        return self.betrag if self.art == "ausgabe" else -self.betrag if self.art == "erstattung" else 0

    def kurz(self) -> dict:
        return {"id": self.id, "datum": self.datum.isoformat(), "betrag": self.betrag, "art": self.art,
                "empfaenger": ({"id": self.empfaenger_id, "name": self.empfaenger}
                               if self.empfaenger_id is not None else None),
                "verwendungszweck": self.zweck, "konto_id": self.konto_id, "fix": self.fix,
                "klasse": klasse_von(self.betrag)}


def _konten_waehlen(con, ids: list[int]) -> tuple[list[int], dict[int, dict]]:
    konten = {k["id"]: k for k in buch.konten_liste(con)}
    fehlend = sorted({i for i in ids if i not in konten})
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Konten.", {"konto_ids": fehlend})
    if any(konten[i]["art"] not in BESTAND for i in ids):
        raise ApiFehler(422, "konto_ungueltig", "Nur Bestandskonten (Giro-, Spar-, Kreditkonto) sind erlaubt.")
    if ids:
        return sorted(set(ids)), konten
    darlehen = {r["konto_id"] for r in con.execute("SELECT konto_id FROM kredit")}
    return [i for i in sorted(konten) if konten[i]["art"] in BESTAND and i not in darlehen], konten


def _laden(con, gewaehlt: set[int], konten: dict[int, dict], von: dt.date, bis: dt.date) -> tuple[list[_Posten], dict]:
    """Posten mit Wirkung im Zeitraum und die Zahl der ausgeschlossenen Umbuchungen je Monat."""
    zeilen = con.execute(
        "SELECT b.id AS bid, b.datum AS datum, b.verwendungszweck AS zweck, b.empfaenger_id AS eid, e.name AS ename,"
        " s.konto_id AS kid, s.betrag AS betrag FROM buchung b JOIN split s ON s.buchung_id = b.id"
        " LEFT JOIN empfaenger e ON e.id = b.empfaenger_id WHERE b.datum BETWEEN ? AND ?"
        " ORDER BY b.datum, b.id, s.position", (von.isoformat(), bis.isoformat())).fetchall()
    posten: list[_Posten] = []
    umbuchungen: dict[str, int] = defaultdict(int)
    i, n = 0, len(zeilen)
    while i < n:
        kopf = zeilen[i]
        konto_id = None
        fremd = aufwand = ertrag = 0
        while i < n and zeilen[i]["bid"] == kopf["bid"]:
            r = zeilen[i]
            i += 1
            art = konten[r["kid"]]["art"] if r["kid"] in konten else ""
            if r["kid"] in gewaehlt:
                if konto_id is None:
                    konto_id = r["kid"]
            elif art not in BESTAND:
                fremd += r["betrag"]
                if art == "aufwand":
                    aufwand += r["betrag"]
                elif art == "ertrag":
                    ertrag += r["betrag"]
        if konto_id is None:
            continue
        datum = dt.date.fromisoformat(kopf["datum"])
        wirkung = -fremd
        if wirkung == 0:
            umbuchungen[_schluessel(datum)] += 1
            continue
        if wirkung < 0:
            art = "ausgabe"
        elif aufwand < 0 and ertrag == 0:
            art = "erstattung"
        else:
            art = "einnahme"
        posten.append(_Posten(kopf["bid"], datum, abs(wirkung), art, kopf["eid"], kopf["ename"], kopf["zweck"] or "",
                              konto_id))
    return posten, umbuchungen


def _serien(con, gewaehlt: set[int], stichtag: dt.date) -> list[dict]:
    wahl = wiederkehrend.Filterwahl(con)
    aus = []
    for (kid, eid, _), g in wiederkehrend.gruppen(wiederkehrend.eintraege(con, stichtag.isoformat())).items():
        if kid not in gewaehlt:
            continue
        s = wiederkehrend.serie(g, stichtag, wahl(eid))
        if s is not None:
            s["_betraege"] = {e.buchung_id: e.betrag for e in g}
            aus.append(s)
    return aus


def _kumuliert(posten: list[_Posten], tage: int) -> list[int]:
    """Laufende Summe der Ausgaben je Tag des Monats (Index 0 = der 1.)."""
    je_tag = [0] * tage
    for p in posten:
        je_tag[min(p.datum.day, tage) - 1] += p.netto
    lauf, aus = 0, []
    for v in je_tag:
        lauf += v
        aus.append(lauf)
    return aus


def _auf_laenge(werte: list[int], tage: int) -> list[int]:
    """Verlauf eines anderen Monats auf die Tageszahl dieses Monats bringen (letzter Wert bleibt stehen)."""
    if len(werte) >= tage:
        return werte[:tage - 1] + [werte[-1]]
    return werte + [werte[-1]] * (tage - len(werte))


def _kennzahlen(monat: list[_Posten], tage_vergangen: int, vormonat: int | None, schnitt: int | None) -> dict:
    ausgaben = [p for p in monat if p.art == "ausgabe"]
    brutto = sum(p.betrag for p in ausgaben)
    erstattungen = sum(p.betrag for p in monat if p.art == "erstattung")
    einnahmen = sum(p.betrag for p in monat if p.art == "einnahme")
    netto = brutto - erstattungen
    saldo = einnahmen - netto
    betraege = [p.betrag for p in ausgaben]
    return {
        "ausgaben": netto, "ausgaben_brutto": brutto, "erstattungen": erstattungen, "einnahmen": einnahmen,
        "saldo": saldo, "sparquote_promille": saldo * 1000 // einnahmen if einnahmen > 0 else None,
        "anzahl": len(ausgaben), "median": _median(betraege), "durchschnitt": brutto // len(ausgaben) if ausgaben else 0,
        "pro_tag": netto // tage_vergangen if tage_vergangen else 0,
        "vormonat": vormonat, "durchschnitt_monate": schnitt,
    }


def _groessenklassen(ausgaben: list[_Posten]) -> list[dict]:
    aus = []
    for i in range(len(KLASSEN) + 1):
        ps = [p for p in ausgaben if klasse_von(p.betrag) == i]
        aus.append({"klasse": i, "ab": KLASSEN[i - 1] if i else 0, "unter": KLASSEN[i] if i < len(KLASSEN) else None,
                    "anzahl": len(ps), "summe": sum(p.betrag for p in ps)})
    return aus


def _top_empfaenger(ausgaben: list[_Posten], frueher: list[_Posten], monate_frueher: int) -> list[dict]:
    summe: dict[int | None, list] = {}
    for p in ausgaben:
        e = summe.setdefault(p.empfaenger_id, [0, 0, p.empfaenger])
        e[0] += p.betrag
        e[1] += 1
    davor: dict[int | None, int] = defaultdict(int)
    for p in frueher:
        if p.art == "ausgabe":
            davor[p.empfaenger_id] += p.betrag
    aus = [{"empfaenger": {"id": eid, "name": name} if eid is not None else None, "summe": s, "anzahl": n,
            "ueblich": davor[eid] // monate_frueher if monate_frueher and eid is not None else None}
           for eid, (s, n, name) in summe.items()]
    aus.sort(key=lambda e: (-e["summe"], (e["empfaenger"] or {}).get("name") or ""))
    return aus


def _ausreisser(ausgaben: list[_Posten], historie: list[_Posten]) -> list[dict]:
    frueher: dict[int, list[int]] = defaultdict(list)
    for p in historie:
        if p.art == "ausgabe" and p.empfaenger_id is not None:
            frueher[p.empfaenger_id].append(p.betrag)
    aus = []
    for p in ausgaben:
        basis = frueher.get(p.empfaenger_id) if p.empfaenger_id is not None else None
        if p.fix or not basis or len(basis) < MIN_AUSREISSER_BASIS:   # feste Zahlungen meldet die Serie
            continue
        mitte = _median(basis)
        if p.betrag - mitte < MIN_AUSREISSER_CENT:
            continue
        z = _z_hundertstel(p.betrag, mitte, _mad(basis, mitte))
        if z is None or z >= AUSREISSER_HUNDERTSTEL:
            aus.append({"buchung": p.kurz(), "ueblich": mitte, "basis_anzahl": len(basis)})
    aus.sort(key=lambda a: -(a["buchung"]["betrag"] - a["ueblich"]))
    return aus


def _serien_auffaellig(serien: list[dict], von: dt.date, bis: dt.date, stichtag: dt.date) -> list[dict]:
    aus = []
    for s in serien:
        if s["richtung"] != "ausgabe":
            continue
        kopf = {"empfaenger": s["empfaenger"], "konto_id": s["konto_id"], "rhythmus": s["rhythmus"]}
        ids = s["buchung_ids"]
        letzte = dt.date.fromisoformat(s["letzte"])
        if len(ids) >= 2 and von <= letzte <= bis:
            neu, alt = -s["_betraege"][ids[-1]], -s["_betraege"][ids[-2]]
            if neu != alt:
                aus.append({**kopf, "art": "betrag_geaendert", "buchung_id": ids[-1], "betrag": neu, "vorher": alt})
        faellig = dt.date.fromisoformat(s["naechste_faelligkeit"])
        if s["status"] == "ausbleibend" and von <= faellig <= min(bis, stichtag):
            aus.append({**kopf, "art": "ausgeblieben", "buchung_id": ids[-1], "betrag": -s["betrag"],
                        "faellig": faellig.isoformat()})
    aus.sort(key=lambda a: (a["art"], a["empfaenger"]["name"]))
    return aus


def _kontostand(con, gewaehlt: list[int], von: dt.date, ende: dt.date) -> dict:
    anfang = 0
    je_tag: dict[str, int] = defaultdict(int)
    for teil in buch._stueckweise(gewaehlt):
        ph = buch._platzhalter(len(teil))
        r = con.execute(f"SELECT COALESCE(SUM(s.betrag), 0) AS n FROM split s JOIN buchung b ON b.id = s.buchung_id"
                        f" WHERE s.konto_id IN ({ph}) AND b.datum < ?", teil + [von.isoformat()]).fetchone()
        anfang += r["n"]
        for r in con.execute(f"SELECT b.datum AS d, SUM(s.betrag) AS n FROM split s JOIN buchung b ON b.id = s.buchung_id"
                             f" WHERE s.konto_id IN ({ph}) AND b.datum BETWEEN ? AND ? GROUP BY b.datum",
                             teil + [von.isoformat(), ende.isoformat()]):
            je_tag[r["d"]] += r["n"]
    tage, werte, lauf = [], [], anfang
    d = von
    while d <= ende:
        lauf += je_tag.get(d.isoformat(), 0)
        tage.append(d.isoformat())
        werte.append(lauf)
        d += dt.timedelta(days=1)
    tief = min(range(len(werte)), key=lambda i: (werte[i], i)) if werte else None
    return {"anfang": anfang, "ende": werte[-1] if werte else anfang, "tage": tage, "werte": werte,
            "tiefststand": {"datum": tage[tief], "betrag": werte[tief]} if tief is not None else None}


def bericht(con, monat: tuple[int, int], konto_ids: list[int], heute: str) -> dict:
    """``GET /api/berichte/monat``."""
    jahr, mon = monat
    gewaehlt, konten = _konten_waehlen(con, konto_ids)
    menge = set(gewaehlt)
    von, bis = _grenzen(jahr, mon)
    h = dt.date.fromisoformat(heute)
    laufend = von <= h < bis
    zukunft = h < von
    stichtag = h if laufend else bis
    tage = bis.day
    tage_vergangen = 0 if zukunft else stichtag.day
    lade_von = _grenzen(*_monat_plus(jahr, mon, -RUECKBLICK_MONATE))[0]
    posten, umbuchungen = _laden(con, menge, konten, lade_von, bis)
    serien = [] if zukunft else _serien(con, menge, stichtag)
    fix_ids = {i for s in serien if s["richtung"] == "ausgabe" for i in s["buchung_ids"]}
    je_monat: dict[str, list[_Posten]] = defaultdict(list)
    for p in posten:
        p.fix = p.art == "ausgabe" and p.id in fix_ids
        je_monat[_schluessel(p.datum)].append(p)
    aktuell = je_monat.get(_schluessel(von), [])
    ausgaben = [p for p in aktuell if p.art == "ausgabe"]
    historie = [p for p in posten if p.datum < von]

    # Monatsvergleich: die zwölf Monate davor und dieser
    monate = []
    for n in range(-RUECKBLICK_MONATE, 1):
        j, m = _monat_plus(jahr, mon, n)
        ps = je_monat.get(f"{j:04d}-{m:02d}", [])
        fix = sum(p.betrag for p in ps if p.fix)
        netto = sum(p.netto for p in ps)
        monate.append({"monat": f"{j:04d}-{m:02d}", "ausgaben": netto, "fix": fix, "variabel": netto - fix,
                       "einnahmen": sum(p.betrag for p in ps if p.art == "einnahme"), "anzahl": len(ps)})
    mit_daten = [m for m in monate[:-1] if m["anzahl"]]
    schnitt = sum(m["ausgaben"] for m in mit_daten) // len(mit_daten) if mit_daten else None
    vormonat = monate[-2]["ausgaben"] if monate[-2]["anzahl"] else None

    # Verlauf: kumuliert, Vormonat, Durchschnitt der letzten Monate mit Daten, Hochrechnung
    kum = _kumuliert(aktuell, tage)
    vergleich = []
    for n in range(1, VERGLEICH_MONATE + 1):
        j, m = _monat_plus(jahr, mon, -n)
        ps = je_monat.get(f"{j:04d}-{m:02d}", [])
        if ps:
            vergleich.append(_auf_laenge(_kumuliert(ps, _grenzen(j, m)[1].day), tage))
    vj, vm = _monat_plus(jahr, mon, -1)
    vor = je_monat.get(f"{vj:04d}-{vm:02d}", [])
    verlauf = {
        "tage": tage, "bis_tag": tage_vergangen, "kumuliert": kum[:tage_vergangen],
        "vormonat": _auf_laenge(_kumuliert(vor, _grenzen(vj, vm)[1].day), tage) if vor else None,
        "durchschnitt": ([sum(v[i] for v in vergleich) // len(vergleich) for i in range(tage)] if vergleich else None),
        "durchschnitt_monate": len(vergleich),
    }

    # Fix und variabel; erwartete feste Zahlungen bis zum Monatsende und Hochrechnung
    fix_posten = [p for p in ausgaben if p.fix]
    fix_summe = sum(p.betrag for p in fix_posten)
    netto = sum(p.netto for p in aktuell)
    erwartet = []
    if laufend:
        for s in serien:
            f = dt.date.fromisoformat(s["naechste_faelligkeit"])
            if s["richtung"] == "ausgabe" and s["status"] == "aktiv" and stichtag < f <= bis:
                erwartet.append({"empfaenger": s["empfaenger"], "konto_id": s["konto_id"], "faellig": f.isoformat(),
                                 "betrag": -s["betrag"], "rhythmus": s["rhythmus"]})
        erwartet.sort(key=lambda e: (e["faellig"], e["empfaenger"]["name"]))
    prognose = None
    if laufend:
        basis_von = von - dt.timedelta(days=90)
        var_frueher = sum(p.netto for p in historie if p.datum >= basis_von and not p.fix)
        hat_basis = any(p.datum >= basis_von for p in historie)
        var_tag = var_frueher // 90 if hat_basis else (netto - fix_summe) // max(tage_vergangen, 1)
        rest = tage - tage_vergangen
        fix_offen = sum(e["betrag"] for e in erwartet)
        prognose = {"summe": netto + fix_offen + max(var_tag, 0) * rest, "fix_offen": fix_offen,
                    "variabel_pro_tag": max(var_tag, 0), "resttage": rest,
                    "grundlage": "letzte_90_tage" if hat_basis else "dieser_monat"}

    # Kalender und Wochentage
    kal_summe: dict[int, int] = defaultdict(int)
    kal_anzahl: dict[int, int] = defaultdict(int)
    for p in ausgaben:
        kal_summe[p.datum.day] += p.betrag
        kal_anzahl[p.datum.day] += 1
    kalender = [{"datum": dt.date(jahr, mon, t).isoformat(), "wochentag": dt.date(jahr, mon, t).weekday(),
                 "summe": kal_summe.get(t, 0), "anzahl": kal_anzahl.get(t, 0)} for t in range(1, tage + 1)]
    wochentage = []
    for w in range(7):
        ks = [k for k in kalender[:tage_vergangen] if k["wochentag"] == w]
        s = sum(k["summe"] for k in ks)
        wochentage.append({"wochentag": w, "name": WOCHENTAGE[w], "summe": s, "anzahl": sum(k["anzahl"] for k in ks),
                           "tage": len(ks), "pro_tag": s // len(ks) if ks else 0})

    # Auffälligkeiten
    bekannt = {p.empfaenger_id for p in historie if p.empfaenger_id is not None}
    neu: dict[int, dict] = {}
    for p in ausgaben:
        if p.empfaenger_id is not None and p.empfaenger_id not in bekannt:
            e = neu.setdefault(p.empfaenger_id, {"empfaenger": {"id": p.empfaenger_id, "name": p.empfaenger},
                                                 "summe": 0, "anzahl": 0})
            e["summe"] += p.betrag
            e["anzahl"] += 1
    neue = sorted(neu.values(), key=lambda e: (-e["summe"], e["empfaenger"]["name"]))

    nach_betrag = sorted(ausgaben, key=lambda p: (-p.betrag, p.datum, p.id))
    brutto = sum(p.betrag for p in ausgaben)
    grenzen = con.execute("SELECT MIN(datum) AS a, MAX(datum) AS b FROM buchung").fetchone()
    monate_frueher = len([1 for n in range(1, VERGLEICH_MONATE + 1)
                          if je_monat.get("%04d-%02d" % _monat_plus(jahr, mon, -n))])
    basis_empf = [p for p in historie if p.datum >= _grenzen(*_monat_plus(jahr, mon, -VERGLEICH_MONATE))[0]]
    return {
        "monat": _schluessel(von), "von": von.isoformat(), "bis": bis.isoformat(), "stichtag": stichtag.isoformat(),
        "heute": heute, "laufend": laufend, "zukunft": zukunft,
        "konten": [{"id": i, "name": konten[i]["name"], "art": konten[i]["art"]} for i in gewaehlt],
        "erster_monat": grenzen["a"][:7] if grenzen["a"] else None,
        "letzter_monat": grenzen["b"][:7] if grenzen["b"] else None,
        "kennzahlen": _kennzahlen(aktuell, tage_vergangen, vormonat, schnitt),
        "verlauf": verlauf, "prognose": prognose, "monate": monate,
        "fix_variabel": {"fix": fix_summe, "variabel": netto - fix_summe, "fix_anzahl": len(fix_posten),
                         "variabel_anzahl": len(ausgaben) - len(fix_posten), "erwartet": erwartet},
        "groessenklassen": _groessenklassen(ausgaben),
        "top_buchungen": {"eintraege": [p.kurz() for p in nach_betrag[:TOP]],
                          "summe": sum(p.betrag for p in nach_betrag[:TOP]), "gesamt": brutto},
        "top_empfaenger": _top_empfaenger(ausgaben, basis_empf, monate_frueher)[:TOP],
        "empfaenger_anzahl": len({p.empfaenger_id for p in ausgaben}),
        "auffaellig": {"ausreisser": _ausreisser(ausgaben, historie), "neue_empfaenger": neue,
                       "serien": _serien_auffaellig(serien, von, bis, stichtag)},
        "kalender": kalender, "wochentage": wochentage,
        "kontostand": _kontostand(con, gewaehlt, von, bis if zukunft else stichtag),
        "ausgeschlossen": {"umbuchungen": umbuchungen.get(_schluessel(von), 0)},
        "buchungen": [p.kurz() for p in aktuell if p.art != "einnahme"],
    }


__all__ = ["bericht", "monat_lesen", "klasse_von", "KLASSEN"]
