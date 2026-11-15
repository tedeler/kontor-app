"""Experimentelle statistische Analyse eines Kontoblatts (D-145).

Nur lesend, kein gespeicherter Zustand. Drei Bestandteile:

- **Regelmäßig:** Gegenpartei (IBAN, sonst Empfängername), bei mehreren Betragsgruppen
  getrennt. Median und MAD der Abstände und Beträge. Eine Reihe ist regelmäßig, wenn
  der Medianabstand in einem bekannten Raster liegt und beide Streuungen klein sind.
- **Rauschen:** der Rest je Aufwand- oder Ertragskategorie, als Verteilung der Monatssummen.
- **Ungewöhnlich:** robustes z gegenüber einer genannten Basis (die Reihe oder das Rauschen).

Jahresraten verwenden den Medianbetrag und ``365 / Medianabstand``, nicht den letzten Betrag.
Umbuchungen auf eigene Konten und Tilgung ohne Zinsaufwand bleiben draußen. Ganze Cent.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from . import buch
from .buch import BESTAND, ApiFehler
from .text import ekey, iban_normalisieren

# Experimentelle Schwellen, bewusst fest und im Ergebnis mitgeliefert.
ABSTAND_MAD_PROZENT = 15
BETRAG_MAD_PROZENT = 10
MODUS_PROZENT = 15
AUSREISSER_HUNDERTSTEL = 350  # robustes z von 3,50
MIN_REGELMAESSIG = 4
MIN_KANDIDAT = 3
MIN_RAUSCHEN = 4
MIN_EINZEL = 8
_ROBUST_Z = 14826  # 1,4826 · 10000
_ROBUST_N = 10000
# (name, soll-tage, untere grenze, obere grenze) des Medianabstands
RASTER = (
    ("woechentlich", 7, 5, 9),
    ("vierzehntaegig", 14, 12, 17),
    ("monatlich", 30, 26, 35),
    ("vierteljaehrlich", 91, 80, 100),
    ("jaehrlich", 365, 330, 400),
)


def _median(werte: list[int]) -> int:
    s = sorted(werte)
    n = len(s)
    if n == 0:
        return 0
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) // 2


def _mad(werte: list[int], mitte: int) -> int:
    return _median([abs(v - mitte) for v in werte]) if werte else 0


def _quartil(werte: list[int], zahl: int) -> int:
    """Unteres (1) oder oberes (3) Quartil, Index ``zahl * n // 4``."""
    s = sorted(werte)
    if not s:
        return 0
    return s[min(zahl * len(s) // 4, len(s) - 1)]


def _perzentil(werte: list[int], promille: int) -> int:
    s = sorted(werte)
    if not s:
        return 0
    if len(s) == 1:
        return s[0]
    idx = (promille * (len(s) - 1) + 500) // 1000
    return s[min(max(idx, 0), len(s) - 1)]


def _streut_wenig(mad: int, mitte: int, prozent: int) -> bool:
    return mad * 100 <= abs(mitte) * prozent


def _z_hundertstel(wert: int, mitte: int, mad: int) -> int | None:
    """Robustes z in Hundertsteln. ``None``, wenn die MAD 0 ist und der Wert abweicht."""
    if mad == 0:
        return 0 if wert == mitte else None
    skala = mad * _ROBUST_Z // _ROBUST_N
    if skala == 0:
        return 0 if wert == mitte else None
    return abs(wert - mitte) * 100 // skala


def _faellig_grenze(median_abstand: int, mad_abstand: int) -> int:
    """Tage nach der letzten Buchung, ab denen eine Lücke ungewöhnlich ist."""
    skala = mad_abstand * _ROBUST_Z // _ROBUST_N
    aus_z = skala * AUSREISSER_HUNDERTSTEL // 100
    boden = max(median_abstand * ABSTAND_MAD_PROZENT // 100, 3)
    return median_abstand + max(aus_z, boden)


def _rhythmus(median_tage: int) -> str | None:
    for name, _soll, unten, oben in RASTER:
        if unten <= median_tage <= oben:
            return name
    return None


def _jahresrate(basis: int, abstand: int) -> int:
    if basis <= 0 or abstand <= 0:
        return 0
    return basis * 365 // abstand


class _Posten:
    __slots__ = ("buchung_id", "datum", "betrag", "empfaenger_id", "empfaenger", "gegen_iban", "zweck",
                 "kosten", "einnahme", "kategorie_id", "kategorie_name", "kategorie_art")

    def __init__(self, buchung_id, datum, betrag, empfaenger_id, empfaenger, gegen_iban, zweck,
                 kosten, einnahme, kategorie_id, kategorie_name, kategorie_art):
        self.buchung_id = buchung_id
        self.datum = datum
        self.betrag = betrag
        self.empfaenger_id = empfaenger_id
        self.empfaenger = empfaenger
        self.gegen_iban = gegen_iban
        self.zweck = zweck
        self.kosten = kosten
        self.einnahme = einnahme
        self.kategorie_id = kategorie_id
        self.kategorie_name = kategorie_name
        self.kategorie_art = kategorie_art

    @property
    def richtung(self) -> str:
        return "ausgabe" if self.betrag < 0 else "einnahme"

    def identitaet(self) -> str:
        if self.gegen_iban:
            return "iban:" + self.gegen_iban
        k = ekey(self.empfaenger)
        if k:
            return "name:" + k
        return f"ohne:{self.buchung_id}"

    def basis_betrag(self) -> int:
        """Aufwand, sonst der Betrag, der das Konto verlassen oder erreicht hat."""
        if self.richtung == "ausgabe":
            return self.kosten if self.kosten > 0 else abs(self.betrag)
        return self.einnahme if self.einnahme > 0 else abs(self.betrag)


def _laden(con, konto_id: int, stichtag: str) -> tuple[list[_Posten], dict]:
    darlehen = {r["konto_id"] for r in con.execute("SELECT konto_id FROM kredit")}
    zeilen = con.execute(
        "SELECT b.id AS bid, b.datum AS datum, b.verwendungszweck AS zweck, b.gegen_iban AS gegen_iban,"
        " b.empfaenger_id AS eid, e.name AS ename, s.konto_id AS kid, s.betrag AS betrag, k.art AS art,"
        " k.name AS kname FROM buchung b JOIN split s ON s.buchung_id = b.id"
        " JOIN konto k ON k.id = s.konto_id LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
        " WHERE b.datum <= ? AND b.id IN (SELECT buchung_id FROM split WHERE konto_id = ?)"
        " ORDER BY b.datum, b.id, s.position",
        (stichtag, konto_id)).fetchall()
    gruppen: dict[int, list] = defaultdict(list)
    kopf: dict[int, dict] = {}
    for r in zeilen:
        gruppen[r["bid"]].append(r)
        kopf.setdefault(r["bid"], r)
    posten: list[_Posten] = []
    ausgeschlossen = {"umbuchungen": 0, "umbuchungen_summe": 0, "tilgung_ohne_zins": 0}
    for bid, splits in gruppen.items():
        h = kopf[bid]
        eigene = [s for s in splits if s["kid"] == konto_id]
        if not eigene:
            continue
        betrag = sum(s["betrag"] for s in eigene)
        if betrag == 0:
            continue
        andere = [s for s in splits if s["kid"] != konto_id]
        aufwand: dict[int, list] = defaultdict(lambda: [0, ""])
        ertrag: dict[int, list] = defaultdict(lambda: [0, ""])
        fremdbestand = False
        tilgung = False
        for s in andere:
            if s["kid"] in darlehen:
                tilgung = True
            elif s["art"] in BESTAND:
                fremdbestand = True
            elif s["art"] == "aufwand" and s["betrag"] > 0:
                aufwand[s["kid"]][0] += s["betrag"]
                aufwand[s["kid"]][1] = s["kname"]
            elif s["art"] == "ertrag" and s["betrag"] < 0:
                ertrag[s["kid"]][0] += -s["betrag"]
                ertrag[s["kid"]][1] = s["kname"]
        if fremdbestand and not aufwand and not ertrag:
            ausgeschlossen["umbuchungen"] += 1
            ausgeschlossen["umbuchungen_summe"] += betrag
            continue
        if tilgung and not aufwand and not ertrag:
            ausgeschlossen["tilgung_ohne_zins"] += 1
            continue
        kosten = sum(v[0] for v in aufwand.values())
        einnahme = sum(v[0] for v in ertrag.values())
        if betrag < 0 and aufwand:
            kid, (betr, name) = max(aufwand.items(), key=lambda kv: (kv[1][0], -kv[0]))
            kat_id, kat_name, kat_art = kid, name, "aufwand"
        elif betrag > 0 and ertrag:
            kid, (betr, name) = max(ertrag.items(), key=lambda kv: (kv[1][0], -kv[0]))
            kat_id, kat_name, kat_art = kid, name, "ertrag"
        else:
            kat_id = kat_name = kat_art = None
        iban = None
        if h["gegen_iban"]:
            n = iban_normalisieren(h["gegen_iban"])
            iban = n or None
        posten.append(_Posten(bid, dt.date.fromisoformat(h["datum"]), betrag, h["eid"], h["ename"], iban,
                              h["zweck"] or "", kosten, einnahme, kat_id, kat_name, kat_art))
    posten.sort(key=lambda p: (p.datum, p.buchung_id))
    return posten, ausgeschlossen


def _modi(posten: list[_Posten]) -> list[list[_Posten]]:
    """Betragsgruppen: ein neuer Modus, wenn der Betrag mehr als 15 % vom Median der Gruppe abweicht."""
    if not posten:
        return []
    geordnet = sorted(posten, key=lambda p: (abs(p.betrag), p.datum, p.buchung_id))
    gruppen: list[list[_Posten]] = [[geordnet[0]]]
    for p in geordnet[1:]:
        mitte = _median([abs(x.betrag) for x in gruppen[-1]])
        grenze = max(abs(mitte) * MODUS_PROZENT // 100, 100)
        if abs(abs(p.betrag) - mitte) <= grenze:
            gruppen[-1].append(p)
        else:
            gruppen.append([p])
    return gruppen


def _bewerten(gruppe: list[_Posten], stichtag: dt.date) -> dict | None:
    if len(gruppe) < MIN_KANDIDAT:
        return None
    gruppe = sorted(gruppe, key=lambda p: (p.datum, p.buchung_id))
    abstaende = [(b.datum - a.datum).days for a, b in zip(gruppe, gruppe[1:])]
    if not abstaende or min(abstaende) < 0:
        return None
    med_ab = _median(abstaende)
    mad_ab = _mad(abstaende, med_ab)
    rhythmus = _rhythmus(med_ab)
    if rhythmus is None:
        return None
    betraege = [p.betrag for p in gruppe]
    med_be = _median(betraege)
    mad_be = _mad(betraege, med_be)
    abstand_ok = _streut_wenig(mad_ab, med_ab, ABSTAND_MAD_PROZENT)
    betrag_ok = med_be != 0 and _streut_wenig(mad_be, med_be, BETRAG_MAD_PROZENT)
    if len(gruppe) >= MIN_REGELMAESSIG and abstand_ok and betrag_ok:
        status, grund = "regelmaessig", None
    elif len(gruppe) == MIN_KANDIDAT and abstand_ok and betrag_ok:
        status, grund = "moeglich", "zu_wenige"
    elif len(gruppe) >= MIN_KANDIDAT and (not abstand_ok or not betrag_ok):
        status = "kandidat"
        grund = "abstand_streut" if not abstand_ok else "betrag_streut"
    else:
        return None
    kosten = [p.basis_betrag() for p in gruppe]
    med_kosten = _median(kosten)
    letzte = gruppe[-1]
    kat = None
    if letzte.kategorie_id is not None or any(p.kategorie_id for p in gruppe):
        zaehler: dict[int, list] = defaultdict(lambda: [0, None, None])
        for p in gruppe:
            if p.kategorie_id is None:
                continue
            ein = zaehler[p.kategorie_id]
            ein[0] += p.basis_betrag()
            ein[1], ein[2] = p.kategorie_name, p.kategorie_art
        if zaehler:
            kid, (betr, name, art) = max(zaehler.items(), key=lambda kv: (kv[1][0], -kv[0]))
            kat = {"id": kid, "name": name, "art": art}
    namen = {p.empfaenger for p in gruppe if p.empfaenger}
    bezeichnung = next(iter(namen)) if len(namen) == 1 else (gruppe[0].gegen_iban or "Ohne Empfänger")
    return {
        "status": status, "grund": grund, "bezeichnung": bezeichnung,
        "empfaenger": ({"id": gruppe[0].empfaenger_id, "name": bezeichnung}
                       if len(namen) == 1 and gruppe[0].empfaenger_id is not None else None),
        "richtung": gruppe[0].richtung, "rhythmus": rhythmus, "anzahl": len(gruppe),
        "abstand_median_tage": med_ab, "abstand_mad_tage": mad_ab,
        "betrag_median": med_be, "betrag_mad": mad_be,
        "betrag_quartil_unten": _quartil(betraege, 1), "betrag_quartil_oben": _quartil(betraege, 3),
        "kosten_median": med_kosten, "jahresrate": _jahresrate(med_kosten, med_ab),
        "kategorie": kat, "erste": gruppe[0].datum.isoformat(), "letzte": letzte.datum.isoformat(),
        "buchung_ids": [p.buchung_id for p in gruppe],
        "_posten": gruppe, "_med_ab": med_ab, "_mad_ab": mad_ab, "_med_be": med_be, "_mad_be": mad_be,
    }


def _ungewoehnlich_reihe(reihe: dict, stichtag: dt.date) -> list[dict]:
    if reihe["status"] not in ("regelmaessig", "moeglich"):
        return []
    aus = []
    for p in reihe["_posten"]:
        z = _z_hundertstel(p.betrag, reihe["_med_be"], reihe["_mad_be"])
        if z is None or z >= AUSREISSER_HUNDERTSTEL:
            aus.append(_ungewoehnlich(p, "betrag", f"Betrag der Reihe „{reihe['bezeichnung']}“", z))
    letzte = reihe["_posten"][-1].datum
    if reihe["status"] == "regelmaessig" and (stichtag - letzte).days > _faellig_grenze(reihe["_med_ab"], reihe["_mad_ab"]):
        aus.append(_ungewoehnlich(reihe["_posten"][-1], "luecke",
                                  f"Abstand der Reihe „{reihe['bezeichnung']}“", None))
    return aus


def _ungewoehnlich(p: _Posten, grund: str, basis: str, z: int | None) -> dict:
    return {"buchung_id": p.buchung_id, "datum": p.datum.isoformat(), "betrag": p.betrag,
            "empfaenger": p.empfaenger, "grund": grund, "basis": basis, "z_hundertstel": z,
            "kategorie": ({"id": p.kategorie_id, "name": p.kategorie_name, "art": p.kategorie_art}
                          if p.kategorie_id is not None else None)}


def _rauschen(rest: list[_Posten]) -> list[dict]:
    nach_kat: dict[int, list[_Posten]] = defaultdict(list)
    for p in rest:
        if p.kategorie_id is not None and p.kategorie_art in ("aufwand", "ertrag"):
            nach_kat[p.kategorie_id].append(p)
    aus = []
    for kid, ps in sorted(nach_kat.items(), key=lambda kv: (kv[1][0].kategorie_name or "", kv[0])):
        monate: dict[str, int] = defaultdict(int)
        for p in ps:
            monate[p.datum.strftime("%Y-%m")] += p.basis_betrag()
        werte = list(monate.values())
        if len(ps) < MIN_RAUSCHEN and len(werte) < 3:
            continue
        aus.append({"kategorie": {"id": kid, "name": ps[0].kategorie_name, "art": ps[0].kategorie_art},
                    "monate": len(werte), "anzahl_buchungen": len(ps), "median": _median(werte),
                    "band_unten": _perzentil(werte, 100), "band_oben": _perzentil(werte, 900),
                    "band_stabil": len(werte) >= MIN_RAUSCHEN})
    return aus


def _rest_ungewoehnlich(rest: list[_Posten]) -> list[dict]:
    aus = []
    gesehen: set[int] = set()
    nach_kat: dict[int, list[_Posten]] = defaultdict(list)
    for p in rest:
        if p.kategorie_id is not None:
            nach_kat[p.kategorie_id].append(p)
    for ps in nach_kat.values():
        if len(ps) < MIN_RAUSCHEN:
            continue
        werte = [p.basis_betrag() for p in ps]
        mitte, mad = _median(werte), _mad(werte, _median(werte))
        for p in ps:
            z = _z_hundertstel(p.basis_betrag(), mitte, mad)
            if (z is None or z >= AUSREISSER_HUNDERTSTEL) and p.buchung_id not in gesehen:
                gesehen.add(p.buchung_id)
                name = p.kategorie_name or "Kategorie"
                aus.append(_ungewoehnlich(p, "rauschen", f"Rauschen der Kategorie „{name}“", z))
    if len(rest) >= MIN_EINZEL:
        werte = [abs(p.betrag) for p in rest]
        mitte, mad = _median(werte), _mad(werte, _median(werte))
        haeufig: dict[str, int] = defaultdict(int)
        for p in rest:
            haeufig[p.identitaet()] += 1
        for p in rest:
            if haeufig[p.identitaet()] != 1 or p.buchung_id in gesehen:
                continue
            z = _z_hundertstel(abs(p.betrag), mitte, mad)
            if z is None or z >= AUSREISSER_HUNDERTSTEL:
                gesehen.add(p.buchung_id)
                aus.append(_ungewoehnlich(p, "einzel", "Übrige Buchungen dieses Kontos", z))
    aus.sort(key=lambda u: (u["datum"], u["buchung_id"], u["grund"]))
    return aus


def _fixkosten(reihen: list[dict], stichtag: dt.date) -> dict:
    von = stichtag - dt.timedelta(days=365)
    nach: dict[int | None, dict] = {}
    for r in reihen:
        if r["status"] != "regelmaessig" or r["richtung"] != "ausgabe":
            continue
        kat = r["kategorie"]
        kid = kat["id"] if kat else None
        ein = nach.setdefault(kid, {"kategorie": kat, "jahresrate": 0, "letzte_zwoelf_monate": 0, "reihen": []})
        ein["jahresrate"] += r["jahresrate"]
        ein["reihen"].append(r["bezeichnung"])
        for p in r["_posten"]:
            if von < p.datum <= stichtag:
                ein["letzte_zwoelf_monate"] += p.basis_betrag()
    kategorien = sorted(nach.values(), key=lambda k: (-(k["jahresrate"]), (k["kategorie"] or {}).get("name") or ""))
    for k in kategorien:
        k["reihen"] = sorted(set(k["reihen"]))
    return {"kategorien": kategorien,
            "summe_jahresrate": sum(k["jahresrate"] for k in kategorien),
            "summe_letzte_zwoelf_monate": sum(k["letzte_zwoelf_monate"] for k in kategorien)}


def _oeffentlich(reihe: dict) -> dict:
    return {k: v for k, v in reihe.items() if not k.startswith("_")}


def analyse(con, konto_id: int, stichtag: str) -> dict:
    """``GET /api/statistik``."""
    k = buch.konto_zeile(con, konto_id)
    if k is None:
        raise buch.nicht_gefunden("Das Konto")
    if k["art"] not in BESTAND:
        raise ApiFehler(422, "konto_ungueltig", "Die statistische Analyse gibt es nur für Bestandskonten.")
    tag = dt.date.fromisoformat(stichtag)
    posten, ausgeschlossen = _laden(con, konto_id, stichtag)
    vergeben: set[int] = set()
    reihen = []
    nach_id: dict[tuple[str, str], list[_Posten]] = defaultdict(list)
    for p in posten:
        nach_id[(p.identitaet(), p.richtung)].append(p)
    for _key, gruppe in sorted(nach_id.items(), key=lambda kv: (kv[1][0].datum, kv[1][0].buchung_id)):
        for modus in _modi(gruppe):
            if len(modus) < MIN_KANDIDAT:
                continue
            reihe = _bewerten(modus, tag)
            if reihe is None:
                continue
            reihen.append(reihe)
            vergeben.update(p.buchung_id for p in reihe["_posten"])
    rest = [p for p in posten if p.buchung_id not in vergeben]
    ungewoehnlich = []
    for reihe in reihen:
        ungewoehnlich.extend(_ungewoehnlich_reihe(reihe, tag))
    ungewoehnlich.extend(_rest_ungewoehnlich(rest))
    ungewoehnlich.sort(key=lambda u: (u["datum"], u["buchung_id"], u["grund"]))
    return {
        "experimentell": True,
        "konto": {"id": k["id"], "name": k["name"], "art": k["art"]},
        "stichtag": stichtag,
        "schwellen": {"abstand_mad_prozent": ABSTAND_MAD_PROZENT, "betrag_mad_prozent": BETRAG_MAD_PROZENT,
                      "ausreisser_z_hundertstel": AUSREISSER_HUNDERTSTEL, "mindestens_regelmaessig": MIN_REGELMAESSIG},
        "ausgeschlossen": ausgeschlossen,
        "reihen": [_oeffentlich(r) for r in reihen],
        "fixkosten": _fixkosten(reihen, tag),
        "rauschen": _rauschen(rest),
        "ungewoehnlich": ungewoehnlich,
    }
