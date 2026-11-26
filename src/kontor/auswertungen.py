"""Weitere Berichte (Feature ``berichte``, D-217): Verträge, Jahr, Vorschau, Vermögen, Kategorien, Empfänger,
Geldfluss, Datenqualität, Tags.

Alle nur lesend und ohne gespeicherten Zustand. Grundlage ist dieselbe Wirkung einer Buchung wie im Monatsbericht
(``monatsbericht._laden``): Umbuchungen zwischen eigenen Konten und Buchungen gegen Eigenkapital zählen nicht.
Alle Beträge sind ganze Cent.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from . import buch, erwartung, wiederkehrend
from .buch import BESTAND, ApiFehler
from .monatsbericht import (_Posten, _grenzen, _konten_waehlen, _laden, _monat_plus, _schluessel, monat_lesen)
from .statistik import _median
from . import sonderposten as sp

TOP = 10
MONATE_JE_RHYTHMUS = {name: m for name, m, _ in wiederkehrend.RHYTHMEN}
VORSCHAU_TAGE = (30, 60, 90)
ZEITRAEUME = (12, 24, 60, 0)          # Monate; 0 = alles


# ------------------------------------------------------------------ Hilfen
def _heute(heute: str) -> dt.date:
    return dt.date.fromisoformat(heute)


def _konten_kurz(gewaehlt: list[int], konten: dict[int, dict]) -> list[dict]:
    return [{"id": i, "name": konten[i]["name"], "art": konten[i]["art"]} for i in gewaehlt]


def _serien(con, menge: set[int], stichtag: dt.date, umbuchungen: bool = False) -> list[dict]:
    """Serien der gewählten Konten zum Stichtag, jeweils mit ihren Zahlungen (Datum, Betrag mit Vorzeichen).

    Serien, deren letzte Buchung nur Bestands- und Eigenkapitalkonten berührt (Sparrate, Kreditkartenausgleich),
    sind Umbuchungen und entfallen, außer mit ``umbuchungen=True`` (Liquiditätsvorschau).
    """
    wahl = wiederkehrend.Filterwahl(con)
    aus = []
    for (kid, eid, _), g in wiederkehrend.gruppen(wiederkehrend.eintraege(con, stichtag.isoformat())).items():
        if kid not in menge:
            continue
        s = wiederkehrend.serie(g, stichtag, wahl(eid))
        if s is not None:
            je = {e.buchung_id: e for e in g}
            s["_zahlungen"] = [(i, je[i].datum, je[i].betrag) for i in s["buchung_ids"]]
            aus.append(s)
    if umbuchungen or not aus:
        return aus
    letzte = [s["buchung_ids"][-1] for s in aus]
    wirksam: set[int] = set()
    for teil in buch._stueckweise(letzte):
        wirksam |= {r["b"] for r in con.execute(
            f"SELECT DISTINCT s.buchung_id AS b FROM split s JOIN konto k ON k.id = s.konto_id"
            f" WHERE s.buchung_id IN ({buch._platzhalter(len(teil))})"
            f" AND (k.art IN ('aufwand', 'ertrag') OR k.extern_id = ?)", teil + [buch.UNKATEGORISIERT])}
    return [s for s in aus if s["buchung_ids"][-1] in wirksam]


def _fix_setzen(posten: list[_Posten], serien: list[dict]) -> None:
    fix = {i for s in serien if s["richtung"] == "ausgabe" for i in s["buchung_ids"]}
    for p in posten:
        p.fix = p.art == "ausgabe" and p.id in fix


def _monatsreihe(von: tuple[int, int], bis: tuple[int, int]) -> list[str]:
    aus, (j, m) = [], von
    while (j, m) <= bis:
        aus.append(f"{j:04d}-{m:02d}")
        j, m = _monat_plus(j, m, 1)
    return aus


def _summen(ps: list[_Posten]) -> dict:
    aus = sum(p.netto for p in ps)
    ein = sum(p.betrag for p in ps if p.art == "einnahme")
    return {"ausgaben": aus, "einnahmen": ein, "saldo": ein - aus,
            "sparquote_promille": (ein - aus) * 1000 // ein if ein > 0 else None,
            "anzahl": sum(1 for p in ps if p.art == "ausgabe")}


def _top_empfaenger(ps: list[_Posten], grenze: int = TOP) -> list[dict]:
    je: dict[int | None, list] = {}
    for p in ps:
        if p.art == "ausgabe":
            e = je.setdefault(p.empfaenger_id, [0, 0, p.empfaenger])
            e[0] += p.betrag
            e[1] += 1
    aus = [{"empfaenger": {"id": eid, "name": n} if eid is not None else None, "summe": s, "anzahl": a}
           for eid, (s, a, n) in je.items()]
    aus.sort(key=lambda e: (-e["summe"], (e["empfaenger"] or {}).get("name") or ""))
    return aus[:grenze]


def _erster_monat(con) -> tuple[str | None, str | None]:
    r = con.execute("SELECT MIN(datum) AS a, MAX(datum) AS b FROM buchung").fetchone()
    return (r["a"][:7] if r["a"] else None, r["b"][:7] if r["b"] else None)


def _stand(con, konto_ids: list[int], bis: dt.date) -> int:
    n = 0
    for teil in buch._stueckweise(konto_ids):
        n += con.execute(f"SELECT COALESCE(SUM(s.betrag), 0) AS n FROM split s JOIN buchung b ON b.id = s.buchung_id"
                         f" WHERE s.konto_id IN ({buch._platzhalter(len(teil))}) AND b.datum <= ?",
                         teil + [bis.isoformat()]).fetchone()["n"]
    return n


def _unkategorisiert(con) -> int | None:
    r = con.execute("SELECT id FROM konto WHERE extern_id = ?", (buch.UNKATEGORISIERT,)).fetchone()
    return r["id"] if r else None


# ------------------------------------------------------------------ Verträge und Abos
def vertraege(con, konto_ids: list[int], heute: str) -> dict:
    """``GET /api/berichte/vertraege``."""
    h = _heute(heute)
    gewaehlt, konten = _konten_waehlen(con, konto_ids)
    serien = _serien(con, set(gewaehlt), h)
    jahr_zurueck = h.replace(year=h.year - 1) if (h.month, h.day) != (2, 29) else h.replace(year=h.year - 1, day=28)
    neu_ab = (h - dt.timedelta(days=90)).isoformat()
    listen: dict[str, list[dict]] = {"ausgabe": [], "einnahme": []}
    for s in serien:
        vz = -1 if s["richtung"] == "ausgabe" else 1
        zahl = [{"id": i, "datum": d, "betrag": vz * b} for i, d, b in s["_zahlungen"]]
        aenderungen = [{"datum": zahl[i]["datum"], "vorher": zahl[i - 1]["betrag"], "betrag": zahl[i]["betrag"]}
                       for i in range(1, len(zahl)) if zahl[i]["betrag"] != zahl[i - 1]["betrag"]]
        betrag = vz * s["betrag"]
        je_jahr = betrag * (12 // MONATE_JE_RHYTHMUS[s["rhythmus"]])
        listen[s["richtung"]].append({
            "schluessel": s["schluessel"], "empfaenger": s["empfaenger"], "konto_id": s["konto_id"],
            "rhythmus": s["rhythmus"], "status": s["status"], "betrag": betrag, "jahreskosten": je_jahr,
            "monatlich": je_jahr // 12, "erste": s["erste"], "letzte": s["letzte"],
            "naechste_faelligkeit": s["naechste_faelligkeit"], "anzahl": s["anzahl"], "zahlungen": zahl,
            "aenderungen": aenderungen, "erster_betrag": zahl[0]["betrag"],
            "summe_12": sum(z["betrag"] for z in zahl if z["datum"] > jahr_zurueck.isoformat()),
            "neu": s["erste"] >= neu_ab})
    for liste in listen.values():
        liste.sort(key=lambda v: (v["status"] == "beendet", -v["jahreskosten"], v["empfaenger"]["name"]))
    posten, _ = _laden(con, set(gewaehlt), konten, jahr_zurueck + dt.timedelta(days=1), h)
    ausgaben_12 = sum(p.netto for p in posten)
    laufend = [v for v in listen["ausgabe"] if v["status"] != "beendet"]
    ein = [v for v in listen["einnahme"] if v["status"] != "beendet"]
    jahr = sum(v["jahreskosten"] for v in laufend)
    return {
        "stichtag": heute, "konten": _konten_kurz(gewaehlt, konten),
        "summen": {"anzahl": len(laufend), "monatlich": jahr // 12, "jaehrlich": jahr,
                   "einnahmen_monatlich": sum(v["jahreskosten"] for v in ein) // 12,
                   "ausgaben_12": ausgaben_12, "anteil_promille": jahr * 1000 // ausgaben_12 if ausgaben_12 > 0 else None,
                   "neu": sum(1 for v in laufend if v["neu"]),
                   "geaendert": sum(1 for v in laufend if v["aenderungen"]
                                    and v["aenderungen"][-1]["datum"] > jahr_zurueck.isoformat()),
                   "ausbleibend": sum(1 for v in laufend if v["status"] == "ausbleibend"),
                   "beendet": sum(1 for v in listen["ausgabe"] if v["status"] == "beendet")},
        "ausgaben": listen["ausgabe"], "einnahmen": listen["einnahme"],
    }


# ------------------------------------------------------------------ Jahresbericht
def jahr(con, jahr_nr: int, konto_ids: list[int], heute: str, sonderposten: str = "ohne") -> dict:
    """``GET /api/berichte/jahr``."""
    h = _heute(heute)
    gewaehlt, konten = _konten_waehlen(con, konto_ids)
    von, bis = dt.date(jahr_nr - 1, 1, 1), dt.date(jahr_nr, 12, 31)
    laufend = h.year == jahr_nr
    stichtag = h if laufend else bis
    posten, umb = _laden(con, set(gewaehlt), konten, von, bis)
    posten, sonder = sp.trennen(con, posten, sonderposten)   # D-300
    _fix_setzen(posten, [] if h.year < jahr_nr else _serien(con, set(gewaehlt), stichtag))
    je: dict[str, list[_Posten]] = defaultdict(list)
    for p in posten:
        je[_schluessel(p.datum)].append(p)

    def reihe(j: int) -> list[dict]:
        aus = []
        for m in range(1, 13):
            ps = je.get(f"{j:04d}-{m:02d}", [])
            s = _summen(ps)
            fix = sum(p.betrag for p in ps if p.fix)
            aus.append({"monat": f"{j:04d}-{m:02d}", **s, "fix": fix, "variabel": s["ausgaben"] - fix,
                        "buchungen": len(ps)})
        return aus

    dieses, vorjahr = reihe(jahr_nr), reihe(jahr_nr - 1)
    im_jahr = [p for p in posten if p.datum.year == jahr_nr]
    ausgaben = [p for p in im_jahr if p.art == "ausgabe"]
    bis_monat = h.month if laufend else 12
    nach_betrag = sorted(ausgaben, key=lambda p: (-p.betrag, p.datum, p.id))
    vor_emp: dict[int | None, int] = defaultdict(int)
    for p in posten:
        if p.datum.year == jahr_nr - 1 and p.art == "ausgabe":
            vor_emp[p.empfaenger_id] += p.betrag
    emp = _top_empfaenger(im_jahr)
    for e in emp:
        e["vorjahr"] = vor_emp.get(e["empfaenger"]["id"] if e["empfaenger"] else None, 0)
    erster, letzter = _erster_monat(con)
    mit = [m for m in dieses[:bis_monat] if m["buchungen"]]
    return {
        "jahr": jahr_nr, "heute": heute, "laufend": laufend, "zukunft": h.year < jahr_nr, "bis_monat": bis_monat,
        "konten": _konten_kurz(gewaehlt, konten),
        "erstes_jahr": int(erster[:4]) if erster else None, "letztes_jahr": int(letzter[:4]) if letzter else None,
        "summen": {**_summen(im_jahr), "fix": sum(p.betrag for p in ausgaben if p.fix),
                   "je_monat": sum(m["ausgaben"] for m in mit) // len(mit) if mit else 0,
                   "vorjahr": sum(m["ausgaben"] for m in vorjahr) if any(m["buchungen"] for m in vorjahr) else None,
                   # vergleichbar nur, wenn das Vorjahr in jedem dieser Monate Buchungen hat
                   "vorjahr_bis_monat": (sum(m["ausgaben"] for m in vorjahr[:bis_monat])
                                         if all(m["buchungen"] for m in vorjahr[:bis_monat]) else None),
                   "vorjahr_einnahmen": (sum(m["einnahmen"] for m in vorjahr[:bis_monat])
                                         if any(m["buchungen"] for m in vorjahr) else None)},
        "monate": dieses, "vorjahr": vorjahr,
        "top_buchungen": {"eintraege": [p.kurz() for p in nach_betrag[:TOP]],
                          "summe": sum(p.betrag for p in nach_betrag[:TOP]), "gesamt": sum(p.betrag for p in ausgaben)},
        "top_empfaenger": emp,
        "ausgeschlossen": {"umbuchungen": sum(n for m, n in umb.items() if m.startswith(f"{jahr_nr:04d}-"))},
        "sonderposten": sonder.abschnitt(dt.date(jahr_nr, 1, 1), bis),
    }


# ------------------------------------------------------------------ Liquiditätsvorschau
def vorschau(con, tage: int, konto_ids: list[int], heute: str) -> dict:
    """``GET /api/berichte/vorschau``."""
    h = _heute(heute)
    if konto_ids:
        gewaehlt, konten = _konten_waehlen(con, konto_ids)
    else:
        alle, konten = _konten_waehlen(con, [])
        giro = [i for i in alle if konten[i]["art"] == "girokonto" and not konten[i].get("geschlossen")]
        gewaehlt = giro or alle
    menge = set(gewaehlt)
    ende = h + dt.timedelta(days=tage)
    serien = _serien(con, menge, h, umbuchungen=True)
    ereignisse = []
    for s in serien:
        if s["status"] != "aktiv":
            continue
        schritt = MONATE_JE_RHYTHMUS[s["rhythmus"]]
        f = dt.date.fromisoformat(s["naechste_faelligkeit"])
        tag = f.day
        while f <= ende:
            if f > h:
                ereignisse.append({"datum": f.isoformat(), "betrag": s["betrag"], "art": s["richtung"],
                                   "empfaenger": s["empfaenger"], "konto_id": s["konto_id"],
                                   "rhythmus": s["rhythmus"], "quelle": "serie"})
            j, m = _monat_plus(f.year, f.month, schritt)
            f = dt.date(j, m, min(tag, _grenzen(j, m)[1].day))
    feste = {(e["konto_id"], -e["betrag"]) for e in ereignisse if e["art"] == "ausgabe"}
    for k in con.execute("SELECT name, zahlungskonto_id, rate, erste_faelligkeit FROM kredit WHERE aktiv = 1"):
        if k["zahlungskonto_id"] not in menge or (k["zahlungskonto_id"], k["rate"]) in feste:
            continue          # die Rate ist schon als wiederkehrende Zahlung erkannt
        tag = int(k["erste_faelligkeit"][8:10])
        j, m = h.year, h.month
        while True:
            f = dt.date(j, m, min(tag, _grenzen(j, m)[1].day))
            if f > ende:
                break
            if f > h and f.isoformat() >= k["erste_faelligkeit"]:
                ereignisse.append({"datum": f.isoformat(), "betrag": -k["rate"], "art": "ausgabe",
                                   "empfaenger": {"id": None, "name": k["name"]}, "konto_id": k["zahlungskonto_id"],
                                   "rhythmus": "monatlich", "quelle": "kredit"})
            j, m = _monat_plus(j, m, 1)
    # D-238: von Hand geplante Zahlungen (samt Wiederholungen). Sie haben kein Konto und zählen bei jeder Kontenwahl.
    for g in erwartung.geplante(con, heute, ende.isoformat()):
        ereignisse.append({"datum": g["datum"], "betrag": -g["betrag"] if g["richtung"] == "ausgabe" else g["betrag"],
                           "art": "ausgabe" if g["richtung"] == "ausgabe" else "einnahme",
                           "empfaenger": {"id": None, "name": g["haendler"]}, "konto_id": None,
                           "rhythmus": g["rhythmus"] or "einmalig", "quelle": "geplant", "erwartung_id": g["id"]})
    ereignisse.sort(key=lambda e: (e["datum"], e["betrag"], e["empfaenger"]["name"]))
    basis_von = h - dt.timedelta(days=89)
    posten, _ = _laden(con, menge, konten, basis_von, h)
    _fix_setzen(posten, serien)
    var_tag = max(0, sum(p.netto for p in posten if not p.fix) // 90)
    start = _stand(con, gewaehlt, h)
    je_tag: dict[str, int] = defaultdict(int)
    for e in ereignisse:
        je_tag[e["datum"]] += e["betrag"]
    tage_liste, fest, erwartet = [heute], [start], [start]
    for n in range(1, tage + 1):
        d = (h + dt.timedelta(days=n)).isoformat()
        tage_liste.append(d)
        fest.append(fest[-1] + je_tag.get(d, 0))
        erwartet.append(erwartet[-1] + je_tag.get(d, 0) - var_tag)
    tief = min(range(len(erwartet)), key=lambda i: (erwartet[i], i))
    tief_fest = min(range(len(fest)), key=lambda i: (fest[i], i))
    negativ = next((tage_liste[i] for i, w in enumerate(erwartet) if w < 0), None)
    eingaenge = [e for e in ereignisse if e["art"] == "einnahme"]
    naechster = max(eingaenge[:1] + [e for e in eingaenge if e["datum"] == eingaenge[0]["datum"]],
                    key=lambda e: e["betrag"]) if eingaenge else None
    frei = None
    if naechster:
        n_tage = (dt.date.fromisoformat(naechster["datum"]) - h).days
        feste_bis = sum(-e["betrag"] for e in ereignisse if e["art"] == "ausgabe" and e["datum"] < naechster["datum"])
        frei = {"bis": naechster["datum"], "tage": n_tage, "feste_ausgaben": feste_bis, "variabel": var_tag * n_tage,
                "betrag": start - feste_bis, "nach_variabel": start - feste_bis - var_tag * n_tage}
    return {
        "heute": heute, "tage": tage, "bis": ende.isoformat(), "konten": _konten_kurz(gewaehlt, konten),
        "start": start, "variabel_pro_tag": var_tag, "verlauf": {"tage": tage_liste, "fest": fest, "erwartet": erwartet},
        "ereignisse": ereignisse, "naechster_eingang": naechster, "frei": frei,
        "tiefststand": {"datum": tage_liste[tief], "betrag": erwartet[tief]},
        "tiefststand_fest": {"datum": tage_liste[tief_fest], "betrag": fest[tief_fest]},
        "erster_tag_negativ": negativ, "ende": {"fest": fest[-1], "erwartet": erwartet[-1]},
        "summen": {"eingaenge": sum(e["betrag"] for e in eingaenge),
                   "feste_ausgaben": sum(-e["betrag"] for e in ereignisse if e["art"] == "ausgabe"),
                   "variabel": var_tag * tage},
    }


# ------------------------------------------------------------------ Vermögensentwicklung
def vermoegen(con, monate: int, heute: str) -> dict:
    """``GET /api/berichte/vermoegen``."""
    h = _heute(heute)
    konten = {k["id"]: k for k in buch.konten_liste(con)}
    bestand = [i for i in sorted(konten) if konten[i]["art"] in BESTAND]
    darlehen = {r["konto_id"]: r["name"] for r in con.execute("SELECT konto_id, name FROM kredit")}
    erster, _ = _erster_monat(con)
    aktuell = (h.year, h.month)
    start = _monat_plus(*aktuell, -(monate - 1)) if monate else aktuell
    if erster:
        e = (int(erster[:4]), int(erster[5:]))
        start = max(start, e) if monate else min(e, aktuell)
    reihe = _monatsreihe(start, aktuell)
    je: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for teil in buch._stueckweise(bestand):
        for r in con.execute(
                f"SELECT s.konto_id AS k, substr(b.datum, 1, 7) AS m, SUM(s.betrag) AS n FROM split s"
                f" JOIN buchung b ON b.id = s.buchung_id WHERE s.konto_id IN ({buch._platzhalter(len(teil))})"
                f" AND b.datum <= ? GROUP BY s.konto_id, substr(b.datum, 1, 7)", teil + [heute]):
            je[r["k"]][r["m"]] += r["n"]
    zeilen, hoechst = [], {}
    for i in bestand:
        lauf = sum(n for m, n in je[i].items() if m < reihe[0])
        tief = min([0] + [n for n in _laufend(je[i])])
        werte = []
        for m in reihe:
            lauf += je[i].get(m, 0)
            werte.append(lauf)
        hoechst[i] = -tief
        if any(werte) or not konten[i].get("geschlossen"):
            zeilen.append({"id": i, "name": konten[i]["name"], "art": konten[i]["art"], "darlehen": i in darlehen,
                           "werte": werte})
    n = len(reihe)
    plus = [sum(max(z["werte"][i], 0) for z in zeilen) for i in range(n)]
    minus = [sum(-min(z["werte"][i], 0) for z in zeilen) for i in range(n)]
    netto = [plus[i] - minus[i] for i in range(n)]
    gewaehlt = [i for i in bestand if i not in darlehen]
    posten, _ = _laden(con, set(gewaehlt), konten, _grenzen(*start)[0], h)
    je_monat: dict[str, list[_Posten]] = defaultdict(list)
    for p in posten:
        je_monat[_schluessel(p.datum)].append(p)
    sparen = [{"monat": m, **_summen(je_monat.get(m, []))} for m in reihe]
    quoten = [s for s in sparen if s["einnahmen"] > 0]
    ein, aus = sum(s["einnahmen"] for s in quoten), sum(s["ausgaben"] for s in quoten)
    kredite = []
    for z in zeilen:
        if z["darlehen"] or (z["art"] == "kreditkonto" and z["werte"][-1] < 0):
            schuld = max(-z["werte"][-1], 0)
            spitze = max(hoechst[z["id"]], schuld)
            kredite.append({"konto_id": z["id"], "name": darlehen.get(z["id"], z["name"]), "schuld": schuld,
                            "hoechststand": spitze,
                            "getilgt_promille": (spitze - schuld) * 1000 // spitze if spitze > 0 else None})
    i12 = max(0, n - 13)
    return {
        "heute": heute, "monate": reihe, "zeitraum": monate, "konten": zeilen, "vermoegen": plus, "schulden": minus,
        "netto": netto, "sparen": sparen, "kredite": kredite,
        "kennzahlen": {"netto": netto[-1], "vermoegen": plus[-1], "schulden": minus[-1],
                       "veraenderung": netto[-1] - netto[0], "seit": reihe[0],
                       "veraenderung_12": netto[-1] - netto[i12] if n > 1 else None, "seit_12": reihe[i12],
                       "sparquote_promille": (ein - aus) * 1000 // ein if ein > 0 else None},
    }


def _laufend(je_monat: dict[str, int]) -> list[int]:
    lauf, aus = 0, []
    for m in sorted(je_monat):
        lauf += je_monat[m]
        aus.append(lauf)
    return aus


# ------------------------------------------------------------------ Kategorien
def _baum(konten: dict[int, dict], arten: tuple[str, ...], extra: int | None) -> list[tuple[int, int]]:
    """Kategorien in Baumfolge als (Konto, Ebene); *extra* („Unkategorisiert“) hängt am Ende."""
    kinder: dict[int | None, list[int]] = defaultdict(list)
    for i, k in konten.items():
        if k["art"] in arten:
            e = k.get("eltern_id")
            kinder[e if e in konten and konten[e]["art"] in arten else None].append(i)
    aus: list[tuple[int, int]] = []

    def ab(eltern, ebene):
        for i in sorted(kinder.get(eltern, []), key=lambda x: konten[x]["name"].casefold()):
            aus.append((i, ebene))
            ab(i, ebene + 1)
    ab(None, 0)
    if extra is not None:
        aus.append((extra, 0))
    return aus


def _kategorie_zeilen(konten, arten, extra, eigen: dict[int, list[int]], zahl: dict[int, int], n_frueher: int) -> list[dict]:
    folge = _baum(konten, arten, extra)
    summe = {i: list(eigen.get(i, [0] * 13)) for i, _ in folge}
    anzahl = {i: zahl.get(i, 0) for i, _ in folge}
    for i, _ in reversed(folge):          # Kinder stehen hinter den Eltern: von hinten aufrollen
        e = konten[i].get("eltern_id")
        if i != extra and e in summe:
            summe[e] = [a + b for a, b in zip(summe[e], summe[i])]
            anzahl[e] += anzahl[i]
    aus = []
    for i, ebene in folge:
        v = summe[i]
        if not any(v):
            continue
        basis = v[12 - n_frueher:12] if n_frueher else []
        schnitt = sum(basis) // n_frueher if n_frueher else None
        aus.append({"id": i, "name": konten[i]["name"], "ebene": ebene,
                    "eltern_id": konten[i].get("eltern_id") if ebene else None, "summe": v[12],
                    "eigen": eigen.get(i, [0] * 13)[12], "anzahl": anzahl[i], "schnitt": schnitt,
                    "abweichung": v[12] - schnitt if schnitt is not None else None, "verlauf": v,
                    "unkategorisiert": i == extra})
    return aus


def kategorien(con, monat: tuple[int, int], konto_ids: list[int], heute: str, sonderposten: str = "ohne") -> dict:
    """``GET /api/berichte/kategorien``."""
    jahr_nr, mon = monat
    gewaehlt, konten = _konten_waehlen(con, konto_ids)
    von, bis = _grenzen(jahr_nr, mon)
    reihe = _monatsreihe(_monat_plus(jahr_nr, mon, -12), (jahr_nr, mon))
    index = {m: i for i, m in enumerate(reihe)}
    posten, _ = _laden(con, set(gewaehlt), konten, _grenzen(*_monat_plus(jahr_nr, mon, -12))[0], bis)
    posten, sonder = sp.trennen(con, posten, sonderposten)   # D-300
    unkat = _unkategorisiert(con)
    aus: dict[int, list[int]] = defaultdict(lambda: [0] * 13)
    ein: dict[int, list[int]] = defaultdict(lambda: [0] * 13)
    zahl_aus: dict[int, int] = defaultdict(int)
    zahl_ein: dict[int, int] = defaultdict(int)
    mit_daten = set()
    for p in posten:
        i = index[_schluessel(p.datum)]
        mit_daten.add(i)
        for kid, w in p.teile:
            art = konten[kid]["art"]
            # Unkategorisiertes folgt der Richtung der Buchung, Kategorien ihrer Art
            ausgabe = art == "aufwand" or (art != "ertrag" and w < 0)
            (aus if ausgabe else ein)[kid][i] += -w if ausgabe else w
            if i == 12:
                (zahl_aus if ausgabe else zahl_ein)[kid] += 1
    n_frueher = len([i for i in range(6, 12) if i in mit_daten])
    extra = unkat if unkat in konten else None
    z_aus = _kategorie_zeilen(konten, ("aufwand",), extra, aus, zahl_aus, n_frueher)
    z_ein = _kategorie_zeilen(konten, ("ertrag",), extra, ein, zahl_ein, n_frueher)
    h = _heute(heute)
    erster, letzter = _erster_monat(con)
    im_monat = [p for p in posten if p.datum >= von]
    return {
        "monat": _schluessel(von), "heute": heute, "laufend": von <= h < bis, "monate": reihe,
        "sonderposten": sonder.abschnitt(von, bis),
        "vergleich_monate": n_frueher, "konten": _konten_kurz(gewaehlt, konten),
        "erster_monat": erster, "letzter_monat": letzter,
        "summen": {"ausgaben": sum(z["summe"] for z in z_aus if z["ebene"] == 0),
                   "einnahmen": sum(z["summe"] for z in z_ein if z["ebene"] == 0),
                   "unkategorisiert": sum(z["summe"] for z in z_aus if z["unkategorisiert"])},
        "ausgaben": z_aus, "einnahmen": z_ein,
        "buchungen": [{**p.kurz(), "teile": [{"konto_id": k, "betrag": w} for k, w in p.teile]} for p in im_monat],
    }


# ------------------------------------------------------------------ Empfänger
def empfaenger(con, empfaenger_id: int | None, konto_ids: list[int], heute: str, sonderposten: str = "ohne") -> dict:
    """``GET /api/berichte/empfaenger``: ohne ``empfaenger_id`` die Rangliste der letzten zwölf Monate."""
    h = _heute(heute)
    gewaehlt, konten = _konten_waehlen(con, konto_ids)
    kopf = {"heute": heute, "konten": _konten_kurz(gewaehlt, konten)}
    if empfaenger_id is None:
        von = _grenzen(*_monat_plus(h.year, h.month, -11))[0]
        posten, _ = _laden(con, set(gewaehlt), konten, von, h)
        posten, sonder = sp.trennen(con, posten, sonderposten)   # D-300
        je: dict[int, dict] = {}
        for p in posten:
            if p.empfaenger_id is None:
                continue
            e = je.setdefault(p.empfaenger_id, {"empfaenger": {"id": p.empfaenger_id, "name": p.empfaenger},
                                                "ausgaben": 0, "einnahmen": 0, "anzahl": 0, "letzte": ""})
            e["ausgaben"] += p.netto
            e["einnahmen"] += p.betrag if p.art == "einnahme" else 0
            e["anzahl"] += 1
            e["letzte"] = max(e["letzte"], p.datum.isoformat())
        liste = sorted(je.values(), key=lambda e: (-(e["ausgaben"] + e["einnahmen"]), e["empfaenger"]["name"]))
        return {**kopf, "empfaenger": None, "von": von.isoformat(), "rangliste": liste[:100], "anzahl": len(liste),
                "sonderposten": sonder.abschnitt(von, h)}
    r = con.execute("SELECT id, name FROM empfaenger WHERE id = ?", (empfaenger_id,)).fetchone()
    if r is None:
        raise ApiFehler(404, "nicht_gefunden", "Empfänger nicht gefunden.")
    erster, _ = _erster_monat(con)
    von = dt.date(int(erster[:4]), int(erster[5:]), 1) if erster else h
    posten = [p for p in _laden(con, set(gewaehlt), konten, von, h)[0] if p.empfaenger_id == empfaenger_id]
    posten, sonder = sp.trennen(con, posten, sonderposten)   # D-300
    serien = [s for s in _serien(con, set(gewaehlt), h) if s["empfaenger"]["id"] == empfaenger_id]
    _fix_setzen(posten, serien)
    reihe = _monatsreihe(_monat_plus(h.year, h.month, -23), (h.year, h.month))
    je_monat: dict[str, list[_Posten]] = defaultdict(list)
    je_jahr: dict[int, list[_Posten]] = defaultdict(list)
    kat: dict[int, int] = defaultdict(int)
    for p in posten:
        je_monat[_schluessel(p.datum)].append(p)
        je_jahr[p.datum.year].append(p)
        for kid, w in p.teile:
            kat[kid] += -w
    ausgaben = [p for p in posten if p.art == "ausgabe"]
    daten = sorted({p.datum for p in ausgaben})
    abstaende = [(b - a).days for a, b in zip(daten, daten[1:])]
    grenze = _grenzen(*_monat_plus(h.year, h.month, -11))[0]
    return {
        **kopf, "empfaenger": {"id": r["id"], "name": r["name"]}, "sonderposten": sonder.abschnitt(),
        "tag_ids": [t["tag_id"] for t in con.execute(
            "SELECT tag_id FROM empfaenger_tag WHERE empfaenger_id = ? ORDER BY tag_id", (empfaenger_id,))],
        "kennzahlen": {"ausgaben": sum(p.netto for p in posten),
                       "einnahmen": sum(p.betrag for p in posten if p.art == "einnahme"),
                       "ausgaben_12": sum(p.netto for p in posten if p.datum >= grenze),
                       "anzahl": len(posten), "anzahl_12": sum(1 for p in posten if p.datum >= grenze),
                       "median": _median([p.betrag for p in ausgaben]) if ausgaben else None,
                       "groesste": max((p.betrag for p in ausgaben), default=None),
                       "erste": posten[0].datum.isoformat() if posten else None,
                       "letzte": posten[-1].datum.isoformat() if posten else None,
                       "abstand_tage": _median(abstaende) if abstaende else None},
        "monate": [{"monat": m, **_summen(je_monat.get(m, [])), "buchungen": len(je_monat.get(m, []))} for m in reihe],
        "jahre": [{"jahr": j, **_summen(ps), "buchungen": len(ps)} for j, ps in sorted(je_jahr.items())],
        "kategorien": sorted(({"konto_id": k, "name": konten[k]["name"], "summe": s} for k, s in kat.items() if s),
                             key=lambda x: -abs(x["summe"])),
        "serien": [{"rhythmus": s["rhythmus"], "richtung": s["richtung"], "status": s["status"],
                    "betrag": abs(s["betrag"]), "naechste_faelligkeit": s["naechste_faelligkeit"],
                    "konto_id": s["konto_id"]} for s in serien],
        "buchungen": [p.kurz() for p in posten[-500:]], "buchungen_gesamt": len(posten),
    }


# ------------------------------------------------------------------ Geldfluss
def geldfluss(con, zeitraum: tuple, konto_ids: list[int], heute: str, sonderposten: str = "ohne") -> dict:
    """``GET /api/berichte/geldfluss``: *zeitraum* ist ``("monat", (Jahr, Monat))`` oder ``("jahr", Jahr)``."""
    gewaehlt, konten = _konten_waehlen(con, konto_ids)
    if zeitraum[0] == "jahr":
        von, bis = dt.date(zeitraum[1], 1, 1), dt.date(zeitraum[1], 12, 31)
    else:
        von, bis = _grenzen(*zeitraum[1])
    posten, _ = _laden(con, set(gewaehlt), konten, von, bis)
    posten, sonder = sp.trennen(con, posten, sonderposten)   # D-300

    def oberste(kid: int) -> int:
        art = konten[kid]["art"]
        while True:
            e = konten[kid].get("eltern_id")
            if e not in konten or konten[e]["art"] != art:
                return kid
            kid = e

    aus: dict[int, int] = defaultdict(int)
    ein: dict[int, int] = defaultdict(int)
    for p in posten:
        for kid, w in p.teile:
            art = konten[kid]["art"]
            ausgabe = art == "aufwand" or (art != "ertrag" and w < 0)
            (aus if ausgabe else ein)[oberste(kid)] += -w if ausgabe else w
    unkat = _unkategorisiert(con)

    def knoten(je: dict[int, int], andere: dict[int, int], erstattung: str) -> list[dict]:
        liste = [{"id": k, "name": konten[k]["name"], "betrag": b, "unkategorisiert": k == unkat, "art": "kategorie"}
                 for k, b in je.items() if b > 0]
        # eine im Saldo negative Kategorie der anderen Seite (mehr Erstattungen als Kosten) fließt hier mit
        liste += [{"id": k, "name": f"{erstattung} {konten[k]['name']}", "betrag": -b, "unkategorisiert": False,
                   "art": "gegenlaeufig"} for k, b in andere.items() if b < 0]
        liste.sort(key=lambda x: (-x["betrag"], x["name"]))
        return liste

    quellen = knoten(ein, aus, "Erstattung")
    ziele = knoten(aus, ein, "Rückzahlung")
    s_ein, s_aus = sum(q["betrag"] for q in quellen), sum(z["betrag"] for z in ziele)
    if s_ein > s_aus:
        ziele.append({"id": None, "name": "Übrig", "betrag": s_ein - s_aus, "unkategorisiert": False, "art": "uebrig"})
    elif s_aus > s_ein:
        quellen.append({"id": None, "name": "Aus dem Bestand", "betrag": s_aus - s_ein, "unkategorisiert": False,
                        "art": "bestand"})
    erster, letzter = _erster_monat(con)
    return {
        "zeitraum": zeitraum[0], "monat": _schluessel(von) if zeitraum[0] == "monat" else None,
        "sonderposten": sonder.abschnitt(von, bis),
        "jahr": von.year, "von": von.isoformat(), "bis": bis.isoformat(), "heute": heute,
        "konten": _konten_kurz(gewaehlt, konten), "erster_monat": erster, "letzter_monat": letzter,
        "einnahmen": s_ein, "ausgaben": s_aus, "summe": max(s_ein, s_aus), "quellen": quellen, "ziele": ziele,
    }


# ------------------------------------------------------------------ Datenqualität
def qualitaet(con, heute: str) -> dict:
    """``GET /api/berichte/qualitaet``."""
    h = _heute(heute)
    gewaehlt, konten = _konten_waehlen(con, [])
    alle = [i for i in sorted(konten) if konten[i]["art"] in BESTAND]
    unkat = _unkategorisiert(con)
    reihe = _monatsreihe(_monat_plus(h.year, h.month, -11), (h.year, h.month))
    posten, _ = _laden(con, set(alle), konten, _grenzen(*_monat_plus(h.year, h.month, -11))[0], h)
    mit_tag = {r["buchung_id"] for r in con.execute(
        "SELECT DISTINCT t.buchung_id FROM buchung_tag t JOIN buchung b ON b.id = t.buchung_id WHERE b.datum >= ?",
        (posten[0].datum.isoformat() if posten else heute,))}
    emp_tag = {r["empfaenger_id"] for r in con.execute("SELECT DISTINCT empfaenger_id FROM empfaenger_tag")}
    je: dict[str, dict] = {m: {"monat": m, "anzahl": 0, "unkategorisiert": 0, "ohne_empfaenger": 0} for m in reihe}
    offen_kat, offen_emp = [], []
    summe_unkat = ohne_tag = 0
    for p in posten:
        m = je[_schluessel(p.datum)]
        m["anzahl"] += 1
        if any(k == unkat for k, _ in p.teile):
            m["unkategorisiert"] += 1
            summe_unkat += sum(abs(w) for k, w in p.teile if k == unkat)
            offen_kat.append(p)
        if p.empfaenger_id is None:
            m["ohne_empfaenger"] += 1
            offen_emp.append(p)
        if p.id not in mit_tag and p.empfaenger_id not in emp_tag:
            ohne_tag += 1
    n = len(posten)
    konten_liste = []
    for i in alle:
        if konten[i].get("geschlossen"):
            continue
        b = con.execute("SELECT MAX(b.datum) AS d, COUNT(DISTINCT b.id) AS n FROM split s JOIN buchung b"
                        " ON b.id = s.buchung_id WHERE s.konto_id = ?", (i,)).fetchone()
        a = con.execute("SELECT MAX(stichtag) AS d FROM abstimmung WHERE konto_id = ?", (i,)).fetchone()
        seit = con.execute("SELECT COUNT(DISTINCT b.id) AS n FROM split s JOIN buchung b ON b.id = s.buchung_id"
                           " WHERE s.konto_id = ? AND b.datum > ?", (i, a["d"] or "0000-00-00")).fetchone()["n"]
        konten_liste.append({"id": i, "name": konten[i]["name"], "art": konten[i]["art"], "letzte_buchung": b["d"],
                             "buchungen": b["n"], "letzte_abstimmung": a["d"], "seit_abstimmung": seit,
                             "tage_seit_abstimmung": (h - dt.date.fromisoformat(a["d"])).days if a["d"] else None})
    verdacht = con.execute("SELECT COUNT(*) AS n FROM dublettenverdacht WHERE status = 'offen'").fetchone()["n"]
    gut = lambda teil: (n - teil) * 1000 // n if n else None   # noqa: E731
    return {
        "heute": heute, "von": reihe[0], "monate": [je[m] for m in reihe],
        "kennzahlen": {"buchungen": n, "unkategorisiert": len(offen_kat), "unkategorisiert_summe": summe_unkat,
                       "ohne_empfaenger": len(offen_emp), "ohne_tag": ohne_tag, "verdacht_offen": verdacht,
                       "kategorisiert_promille": gut(len(offen_kat)), "mit_empfaenger_promille": gut(len(offen_emp)),
                       "nicht_abgestimmt": sum(1 for k in konten_liste if k["letzte_abstimmung"] is None)},
        "konten": konten_liste, "unkategorisiert_konto_id": unkat,
        "unkategorisiert": [p.kurz() for p in sorted(offen_kat, key=lambda p: (-p.betrag, p.id))[:200]],
        "ohne_empfaenger": [p.kurz() for p in sorted(offen_emp, key=lambda p: (-p.betrag, p.id))[:200]],
    }


# ------------------------------------------------------------------ Tags
def tags(con, tag_ids: list[int], monate: int, konto_ids: list[int], heute: str) -> dict:
    """``GET /api/berichte/tags``: Übersicht aller Tags; für jede ``tag_id`` zusätzlich die Einzelsicht."""
    h = _heute(heute)
    gewaehlt, konten = _konten_waehlen(con, konto_ids)
    namen = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM tag")}
    fehlend = sorted(set(tag_ids) - set(namen))
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Tags.", {"tag_ids": fehlend})
    erster, _ = _erster_monat(con)
    aktuell = (h.year, h.month)
    if monate:
        start = _monat_plus(*aktuell, -(monate - 1))
    else:
        start = (int(erster[:4]), int(erster[5:])) if erster else aktuell
    von = _grenzen(*start)[0]
    posten, _ = _laden(con, set(gewaehlt), konten, von, h)
    je_buchung: dict[int, set[int]] = defaultdict(set)
    for r in con.execute("SELECT t.buchung_id AS b, t.tag_id AS t FROM buchung_tag t JOIN buchung b ON b.id = t.buchung_id"
                         " WHERE b.datum BETWEEN ? AND ?", (von.isoformat(), heute)):
        je_buchung[r["b"]].add(r["t"])
    je_emp: dict[int, set[int]] = defaultdict(set)
    for r in con.execute("SELECT empfaenger_id AS e, tag_id AS t FROM empfaenger_tag"):
        je_emp[r["e"]].add(r["t"])
    reihe = _monatsreihe(max(start, _monat_plus(*aktuell, -23)), aktuell)
    index = {m: i for i, m in enumerate(reihe)}
    ueber: dict[int, dict] = {}
    ohne = {"ausgaben": 0, "anzahl": 0}
    gesamt = 0
    je_tag: dict[int, list[_Posten]] = defaultdict(list)
    for p in posten:
        p.tags = frozenset(je_buchung.get(p.id, set()) | je_emp.get(p.empfaenger_id, set()))
        gesamt += p.netto
        if not p.tags:
            ohne["ausgaben"] += p.netto
            ohne["anzahl"] += 1
        for t in p.tags:
            je_tag[t].append(p)
            u = ueber.setdefault(t, {"id": t, "name": namen[t], "ausgaben": 0, "einnahmen": 0, "anzahl": 0,
                                     "erste": p.datum.isoformat(), "letzte": p.datum.isoformat(),
                                     "verlauf": [0] * len(reihe)})
            u["ausgaben"] += p.netto
            u["einnahmen"] += p.betrag if p.art == "einnahme" else 0
            u["anzahl"] += 1
            u["letzte"] = p.datum.isoformat()
            i = index.get(_schluessel(p.datum))
            if i is not None:
                u["verlauf"][i] += p.netto
    liste = sorted(ueber.values(), key=lambda u: (-u["ausgaben"], u["name"].casefold()))
    liste += [{"id": t, "name": n, "ausgaben": 0, "einnahmen": 0, "anzahl": 0, "erste": None, "letzte": None,
               "verlauf": [0] * len(reihe)} for t, n in sorted(namen.items(), key=lambda x: x[1].casefold())
              if t not in ueber]
    einzeln = []
    for t in dict.fromkeys(tag_ids):
        ps = je_tag.get(t, [])
        kat: dict[int, int] = defaultdict(int)
        for p in ps:
            for kid, w in p.teile:
                kat[kid] += -w
        ausgaben = sorted((p for p in ps if p.art == "ausgabe"), key=lambda p: (-p.betrag, p.datum, p.id))
        je_m: dict[str, list[_Posten]] = defaultdict(list)
        for p in ps:
            je_m[_schluessel(p.datum)].append(p)
        einzeln.append({
            "id": t, "name": namen[t], **_summen(ps), "buchungen_anzahl": len(ps),
            "erste": ps[0].datum.isoformat() if ps else None, "letzte": ps[-1].datum.isoformat() if ps else None,
            "monate": [{"monat": m, **_summen(je_m.get(m, []))} for m in reihe],
            "kategorien": sorted(({"konto_id": k, "name": konten[k]["name"], "summe": s} for k, s in kat.items() if s),
                                 key=lambda x: -x["summe"]),
            "empfaenger": _top_empfaenger(ps), "top_buchungen": [p.kurz() for p in ausgaben[:TOP]],
            "buchungen": [p.kurz() for p in ps[-500:]]})
    return {
        "heute": heute, "zeitraum": monate, "von": von.isoformat(), "monate": reihe,
        "konten": _konten_kurz(gewaehlt, konten), "tags": liste, "ohne_tag": ohne, "ausgaben": gesamt,
        "einzeln": einzeln,
    }


# ------------------------------------------------------------------ Parameter der Endpunkte
def _jahr_lesen(q, heute: str) -> int:
    n = q.ganzzahl("jahr", 1900, 9998)
    return n if n is not None else _heute(heute).year


def _monat(q, heute: str):
    try:
        return monat_lesen(q.text("monat"), heute)
    except ValueError:
        q.fehler_melden("monat", "Erwartet wird ein Monat der Form JJJJ-MM.")
        return None


def _zeitraum(q, name: str, werte: tuple[int, ...], vorgabe: int) -> int:
    w = q.auswahl(name, tuple(str(x) for x in werte))
    return int(w) if w is not None else vorgabe


def _geldfluss_zeitraum(q, heute: str):
    if "jahr" in q.params and "monat" in q.params:
        q.fehler_melden("monat", "Entweder monat oder jahr, nicht beides.")
    if "jahr" in q.params:
        return ("jahr", _jahr_lesen(q, heute))
    return ("monat", _monat(q, heute))


#: Name → (Funktion, erlaubte Parameter, Leser der Argumente nach ``con``)
BERICHTE = {
    "vertraege": (vertraege, ("konto_id",), lambda q, h: (q.ganzzahlen("konto_id"), h)),
    "jahr": (jahr, ("jahr", "konto_id", "sonderposten"),
             lambda q, h: (_jahr_lesen(q, h), q.ganzzahlen("konto_id"), h, sp.modus_lesen(q))),
    "vorschau": (vorschau, ("tage", "konto_id"),
                 lambda q, h: (_zeitraum(q, "tage", VORSCHAU_TAGE, 60), q.ganzzahlen("konto_id"), h)),
    "vermoegen": (vermoegen, ("monate",), lambda q, h: (_zeitraum(q, "monate", ZEITRAEUME, 24), h)),
    "kategorien": (kategorien, ("monat", "konto_id", "sonderposten"),
                   lambda q, h: (_monat(q, h), q.ganzzahlen("konto_id"), h, sp.modus_lesen(q))),
    "empfaenger": (empfaenger, ("empfaenger_id", "konto_id", "sonderposten"),
                   lambda q, h: (q.ganzzahl("empfaenger_id", 1), q.ganzzahlen("konto_id"), h, sp.modus_lesen(q))),
    "geldfluss": (geldfluss, ("monat", "jahr", "konto_id", "sonderposten"),
                  lambda q, h: (_geldfluss_zeitraum(q, h), q.ganzzahlen("konto_id"), h, sp.modus_lesen(q))),
    "qualitaet": (qualitaet, (), lambda q, h: (h,)),
    "tags": (tags, ("tag_id", "monate", "konto_id"),
             lambda q, h: (q.ganzzahlen("tag_id"), _zeitraum(q, "monate", ZEITRAEUME, 12), q.ganzzahlen("konto_id"), h)),
}

__all__ = ["BERICHTE"]
