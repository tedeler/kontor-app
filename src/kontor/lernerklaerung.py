"""Transparenz des Lernmodells (Feature `lernmodell-transparenz`, D-183).

- ``erklaeren``: warum das Lernmodell für eine Buchung diese Kategorie vorschlägt (oder keine). Das Verfahren aus
  lernmodell.md 4 ist ein Produkt von Faktoren je Merkmal; jeder Faktor beruht auf Zählungen der Trainingsmenge.
  Die Erklärung gibt genau diese Zählungen und das Verhältnis der Faktoren der besten zur zweitbesten Kategorie
  wieder – keine Näherung. Dazu die ähnlichsten Trainingsbuchungen (die Merkmale mit der Buchung teilen).
- ``uebersicht``: Güte auf den eigenen Daten wie lernmodell.md 6 (ältere 80 % Training, neueste 20 % Prüfung),
  Abdeckung und Genauigkeit je Schwelle, Verlässlichkeit der Prozentangabe, Kategorien mit Verwechslungen und
  stärksten Merkmalen.
- ``einstellungen``: Schwelle und automatische Regeln als Einstellung der Instanz in ``meta`` (wie D-137).

Alles Lesezugriffe ohne Protokolleintrag, außer ``einstellungen_setzen`` (Einstellung, nicht Buchbestand).
"""

from __future__ import annotations

import threading
from collections import Counter, defaultdict
from fractions import Fraction

from . import buch, lernmodell
from .buch import ApiFehler

SCHWELLEN = tuple(range(500, 1000, 50))
MAX_PRUEFUNG = 2000
MAX_AEHNLICHE = 5
MAX_MERKMALE_JE_KATEGORIE = 5


# ======================================================================== Einstellungen


def regeln_automatisch(con, vorgabe: bool) -> bool:
    r = con.execute("SELECT wert FROM meta WHERE schluessel = 'lern_regeln_automatisch'").fetchone()
    return vorgabe if r is None else r["wert"] == "1"


def einstellungen(con, vorgabe_regeln: bool, lernmodell_automatisch: bool) -> dict:
    return {"schwelle_promille": lernmodell.schwelle_promille(con),
            "regeln_automatisch": regeln_automatisch(con, vorgabe_regeln),
            "lernmodell_automatisch": lernmodell_automatisch}


def einstellungen_setzen(con, d: dict, vorgabe_regeln: bool, lernmodell_automatisch: bool) -> dict:
    werte = []
    if "schwelle_promille" in d:
        s = d["schwelle_promille"]
        if not 500 <= s <= 990:
            raise ApiFehler(422, "validierung", "Die Anfrage ist ungültig.",
                            [{"ort": ["body", "schwelle_promille"], "meldung": "Ganzzahl von 500 bis 990 erwartet."}])
        werte.append(("lern_schwelle_promille", str(s)))
    if "regeln_automatisch" in d:
        werte.append(("lern_regeln_automatisch", "1" if d["regeln_automatisch"] else "0"))
    con.executemany("INSERT INTO meta (schluessel, wert) VALUES (?, ?) ON CONFLICT(schluessel)"
                    " DO UPDATE SET wert = excluded.wert", werte)
    return einstellungen(con, vorgabe_regeln, lernmodell_automatisch)


# ======================================================================== Erklärung je Buchung


def betrag_text(merkmal: str) -> str:
    """``b:-4`` → „Ausgabe 10,00–99,99 €“ (Größenordnung des Regelbetrags, lernmodell.md 2)."""
    if merkmal == "b:0":
        return "Betrag 0,00 €"
    art = "Einnahme" if merkmal[2] == "+" else "Ausgabe"
    stellen = int(merkmal[3:])
    return f"{art} {_euro(10 ** (stellen - 1))}–{_euro(10 ** stellen - 1)} €"


def _euro(cent: int) -> str:
    e, c = divmod(cent, 100)
    return f"{e:,}".replace(",", ".") + f",{c:02d}"


def _promille(p: Fraction) -> int:
    return (1000 * p.numerator) // p.denominator


def _art(f: str) -> str:
    return {"e": "empfaenger", "v": "wort", "b": "betrag"}[f[0]]


def _faktor(modell: lernmodell.Modell, f: str | None, c: int) -> Fraction:
    """Faktor der Kategorie c für Merkmal f (lernmodell.md 4, Schritt 3); f = None: Grundwert N_c / n."""
    if f is None:
        return Fraction(modell.nk[c], modell.n)
    return Fraction(modell.nkf[f][c] + 1, modell.nk[c] + 2)


def erklaeren(con, buchung_id: int) -> dict:
    """``GET /api/buchungen/{id}/lernmodell``: Einschätzung des Lernmodells mit Begründung."""
    daten = lernmodell.buchungsmerkmale(con, [buchung_id])
    if buchung_id not in daten:
        raise buch.nicht_gefunden("Die Buchung")
    m = daten[buchung_id][0]
    alle = lernmodell.buchungsmerkmale(con)
    training = {bid: (mm, kat) for bid, (mm, kat, offen) in alle.items() if kat is not None and not offen}
    modell = lernmodell.Modell([training[b] for b in sorted(training)], lernmodell.schwelle_promille(con))
    reihe = modell.rangfolge(m)
    v = modell.vorhersage(m)
    if modell.n == 0:
        grund = "kein_modell"
    elif not reihe:
        grund = "unbekannt"
    elif v.kategorie_id is None:
        grund = "unter_schwelle"
    else:
        grund = "vorschlag"
    beste = reihe[0][1] if reihe else None
    zweite = reihe[1][1] if len(reihe) > 1 else None
    b = buch.buchungen_laden(con, [buchung_id])[0]
    merkmale = []
    for f in sorted(m, key=lambda x: ("evb".index(x[0]), x)):
        e = {"merkmal": f, "art": _art(f), "anzahl": modell.nf[f], "bekannt": modell.nf[f] > 0}
        if f[0] == "e":
            e["text"] = b["empfaenger"]["name"] if b["empfaenger"] else f[2:]
        elif f[0] == "v":
            e["text"] = f[2:]
        else:
            e["text"] = betrag_text(f)
        if beste is not None and e["bekannt"]:
            e["anzahl_kategorie"] = modell.nkf[f][beste]
            e["verteilung"] = [{"kategorie_id": c, "anzahl": n} for c, n in modell.nkf[f].most_common(3)]
            if zweite is not None:
                e["faktor_promille"] = _promille(_faktor(modell, f, beste) / _faktor(modell, f, zweite))
                e["anzahl_vergleich"] = modell.nkf[f][zweite]
        merkmale.append(e)
    aus = {
        "buchung_id": buchung_id, "grund": grund, "schwelle_promille": lernmodell.schwelle_promille(con),
        "kategorie_id": v.kategorie_id, "sicherheit": v.sicherheit,
        "kandidaten": [{"kategorie_id": c, "sicherheit": s} for c, s in v.kandidaten],
        "beste_kategorie_id": beste, "vergleich_kategorie_id": zweite,
        "trainingsbuchungen": modell.n, "merkmale": merkmale,
        "grundwert": None if beste is None else {
            "anzahl_kategorie": modell.nk[beste], "anzahl_vergleich": modell.nk[zweite] if zweite else None,
            "faktor_promille": _promille(_faktor(modell, None, beste) / _faktor(modell, None, zweite))
            if zweite else None},
        "aehnliche": _aehnliche(con, buchung_id, m, training),
    }
    return aus


def _aehnliche(con, buchung_id: int, m: frozenset[str], training: dict) -> list[dict]:
    """Trainingsbuchungen, die die meisten Merkmale teilen (Empfänger zählt dreifach, Betrag nicht)."""
    def punkte(mm):
        gemeinsam = (m & mm) - {f for f in m if f[0] == "b"}
        return sum(3 if f[0] == "e" else 1 for f in gemeinsam), gemeinsam

    wertung = []
    for bid, (mm, kat) in training.items():
        if bid == buchung_id:
            continue
        p, gemeinsam = punkte(mm)
        if p:
            wertung.append((p, bid, gemeinsam, kat))
    wertung.sort(key=lambda x: (-x[0], -x[1]))
    beste = wertung[:MAX_AEHNLICHE]
    if not beste:
        return []
    geladen = {b["id"]: b for b in buch.buchungen_laden(con, [x[1] for x in beste])}
    aus = []
    for p, bid, gemeinsam, kat in beste:
        b = geladen[bid]
        aus.append({"buchung_id": bid, "datum": b["datum"],
                    "empfaenger": b["empfaenger"]["name"] if b["empfaenger"] else None,
                    "verwendungszweck": b["verwendungszweck"], "betrag": _regelbetrag(con, b), "kategorie_id": kat,
                    "gemeinsam": sorted(gemeinsam, key=lambda x: ("evb".index(x[0]), x))})
    return aus


def _regelbetrag(con, b: dict) -> int:
    art_von = buch.kontoarten(con)
    return sum(s["betrag"] for s in b["splits"] if art_von[s["konto_id"]] in buch.BESTAND)


# ======================================================================== Übersicht


_cache: dict[tuple, dict] = {}
_cache_sperre = threading.Lock()


def uebersicht(con, vorgabe_regeln: bool, lernmodell_automatisch: bool) -> dict:
    """``GET /api/lernmodell/uebersicht`` (zwischengespeichert bis zur nächsten Änderung am Buchbestand)."""
    stand = con.execute("SELECT COALESCE(MAX(id), 0) AS m FROM aenderung").fetchone()["m"]
    schwelle = lernmodell.schwelle_promille(con)
    schluessel = (stand, schwelle)
    with _cache_sperre:
        treffer = _cache.get(schluessel)
    if treffer is None:
        treffer = _berechnen(con, schwelle)
        with _cache_sperre:
            _cache.clear()
            _cache[schluessel] = treffer
    return {**treffer, "einstellungen": einstellungen(con, vorgabe_regeln, lernmodell_automatisch)}


def _berechnen(con, schwelle: int) -> dict:
    zeilen = {r["id"]: r["datum"] for r in con.execute("SELECT id, datum FROM buchung")}
    t = sorted(((zeilen[bid], bid, mm, kat) for bid, (mm, kat, offen) in lernmodell.buchungsmerkmale(con).items()
                if kat is not None and not offen))
    gesamt = lernmodell.Modell([(mm, kat) for _d, _b, mm, kat in t], schwelle)
    aus: dict = {"trainingsbuchungen": gesamt.n, "kategorien": len(gesamt.nk),
                 "merkmale": sum(1 for f in gesamt.nf if gesamt.nf[f] > 0)}
    n_pruef = min(len(t) - int(len(t) * 4 // 5), MAX_PRUEFUNG) if len(t) >= 20 else 0
    namen = {}
    for r in con.execute("SELECT name FROM empfaenger ORDER BY id"):
        namen.setdefault("e:" + (buch.ekey(r["name"]) or ""), r["name"])
    aus["kategorie_liste"] = _kategorien(gesamt, namen)
    if not n_pruef:
        aus["pruefung"] = None
        return aus
    lern, pruef = t[:-n_pruef], t[-n_pruef:]
    modell = lernmodell.Modell([(mm, kat) for _d, _b, mm, kat in lern], schwelle)
    ergebnisse = []  # (P der besten Kategorie oder None, beste Kategorie, wahre Kategorie)
    for _d, _b, mm, kat in pruef:
        reihe = modell.rangfolge(mm)
        ergebnisse.append((reihe[0][0], reihe[0][1], kat) if reihe else (None, None, kat))
    s_frac = Fraction(schwelle, 1000)
    je_schwelle = []
    for s in sorted(set(SCHWELLEN) | {schwelle}):
        grenze = Fraction(s, 1000)
        v = [e for e in ergebnisse if e[0] is not None and e[0] >= grenze]
        je_schwelle.append({"schwelle_promille": s, "vorschlaege": len(v), "richtig": sum(e[1] == e[2] for e in v)})
    eimer = defaultdict(lambda: [0, 0])
    for p, c, wahr in ergebnisse:
        if p is None:
            continue
        i = min(_promille(p) // 100, 9)
        eimer[i][0] += 1
        eimer[i][1] += c == wahr
    v = [e for e in ergebnisse if e[0] is not None and e[0] >= s_frac]
    aus["pruefung"] = {
        "von": pruef[0][0], "bis": pruef[-1][0], "pruefbuchungen": len(pruef),
        "ohne_einschaetzung": sum(e[0] is None for e in ergebnisse),
        "vorschlaege": len(v), "richtig": sum(e[1] == e[2] for e in v),
        "je_schwelle": je_schwelle,
        "verlaesslichkeit": [{"von_promille": i * 100, "bis_promille": i * 100 + 100, "anzahl": n, "richtig": r}
                             for i, (n, r) in sorted(eimer.items())],
    }
    je_kat: dict[int, dict] = defaultdict(lambda: {"pruef": 0, "vorschlaege": 0, "richtig": 0, "verwechslung": Counter()})
    for p, c, wahr in ergebnisse:
        k = je_kat[wahr]
        k["pruef"] += 1
        if p is not None and p >= s_frac:
            k["vorschlaege"] += 1
            if c == wahr:
                k["richtig"] += 1
            else:
                k["verwechslung"][c] += 1
    for k in aus["kategorie_liste"]:
        g = je_kat.get(k["kategorie_id"])
        if g is None:
            k.update(pruef=0, vorschlaege=0, richtig=0, verwechslungen=[])
        else:
            k.update(pruef=g["pruef"], vorschlaege=g["vorschlaege"], richtig=g["richtig"],
                     verwechslungen=[{"kategorie_id": c, "anzahl": n} for c, n in g["verwechslung"].most_common(3)])
    return aus


def _kategorien(modell: lernmodell.Modell, namen: dict[str, str]) -> list[dict]:
    """Je Kategorie: Beispiele und die Merkmale, die am stärksten für sie sprechen (gegenüber allen anderen)."""
    staerke: dict[int, list] = defaultdict(list)
    for f, je in modell.nkf.items():
        if f[0] == "b":
            continue
        for c, n in je.items():
            if n < 2:
                continue
            nc = modell.nk[c]
            rest_n, rest_f = modell.n - nc, modell.nf[f] - n
            verhaeltnis = Fraction(n + 1, nc + 2) / Fraction(rest_f + 1, rest_n + 2)
            staerke[c].append((verhaeltnis, n, f))
    aus = []
    for c, nc in sorted(modell.nk.items()):
        beste = sorted(staerke[c], key=lambda x: (-x[0], x[2]))[:MAX_MERKMALE_JE_KATEGORIE]
        aus.append({"kategorie_id": c, "beispiele": nc,
                    "merkmale": [{"merkmal": f, "art": _art(f), "text": namen.get(f, f[2:]), "anzahl_kategorie": n,
                                  "anzahl": modell.nf[f]} for _v, n, f in beste]})
    return aus
