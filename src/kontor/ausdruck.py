"""Kontor-Ausdrücke: gemeinsame Ausdruckssprache für Regeln und den Filter im Kontoblatt (D-178).

Syntax nach Python-Ausdrücken (``and``, ``or``, ``not``, ``in``, ``is None``, verkettete Vergleiche,
``.startswith()``, ``.endswith()``, ``.search(r"…")``), C-Operatoren ``&&``, ``||``, ``!`` als Alias.
Feldnamen deutsch nach den Spalten des Kontoblatts mit Kurzformen (``empf``, ``vwz``, ``bet``, ``dir``,
``dt``). Datumsangaben (``5.2.``, ``-5d``, ``1.1.2017 + 1y``, ``letzter_monat`` …) und Freitext gibt es nur im
Kontext ``filter``.

Ablauf: ``lexen`` → ``_Parser`` (Rohbaum) → ``_Pruefer`` (typisierter Baum, Verweise als IDs) → ``drucken``
(kanonischer Text) bzw. ``auswerten``/``erklaeren``. Der typisierte Baum ist JSON-fähig und wird bei Regeln
gespeichert. Reguläre Ausdrücke laufen über RE2 (lineare Laufzeit); ausgewertet wird nie mit ``eval``.
"""

from __future__ import annotations

import calendar
import datetime as dt
import difflib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import re2

from .buch import BESTAND, KATEGORIEARTEN

KONTEXTE = ("regel", "filter")
MAX_AUSDRUCK = 4000
MAX_MUSTER = 500

# =================================================================== Felder


@dataclass(frozen=True)
class Feld:
    name: str
    kurz: str | None
    typ: str            # text, betrag, auswahl, int, bool, datum, konto, kategorie, tags
    label: str
    nur_filter: bool = False
    werte: tuple[str, ...] = ()
    bereich: tuple[int, int] | None = None


WOCHENTAGE = ("mo", "di", "mi", "do", "fr", "sa", "so")
WOCHENTAG_GRUPPEN = {"werktag": set(WOCHENTAGE[:5]), "wochenende": {"sa", "so"}}
RICHTUNGEN = ("ausgabe", "einnahme", "umbuchung")
STATUSWERTE = ("importiert", "vorlaeufig", "bestaetigt", "abgeglichen")

FELDER: dict[str, Feld] = {f.name: f for f in (
    Feld("empfänger", "empf", "text", "Empfänger"),
    Feld("verwendungszweck", "vwz", "text", "Verwendungszweck"),
    Feld("betrag", "bet", "betrag", "Betrag"),
    Feld("richtung", "dir", "auswahl", "Richtung", werte=RICHTUNGEN),
    Feld("datum", "dt", "datum", "Datum", nur_filter=True),
    Feld("kategorie", None, "kategorie", "Kategorie"),
    Feld("status", None, "auswahl", "Status", werte=STATUSWERTE),
    Feld("tags", None, "tags", "Tags"),
    Feld("notiz", None, "text", "Notiz"),
    Feld("iban", None, "text", "IBAN"),
    Feld("konto", None, "konto", "Konto"),
    Feld("monatstag", None, "int", "Monatstag", bereich=(1, 31)),
    Feld("monat", None, "int", "Monat", bereich=(1, 12)),
    Feld("quartal", None, "int", "Quartal", bereich=(1, 4)),
    Feld("jahr", None, "int", "Jahr", nur_filter=True, bereich=(1900, 2200)),
    Feld("kw", None, "int", "Kalenderwoche", nur_filter=True, bereich=(1, 53)),
    Feld("wochentag", None, "auswahl", "Wochentag", werte=WOCHENTAGE + tuple(WOCHENTAG_GRUPPEN)),
    Feld("letzter_tag", None, "bool", "Letzter Tag des Monats"),
)}

SCHLUESSELWOERTER = {"and", "or", "not", "in", "is", "none", "null", "true", "false"}
METHODEN = ("startswith", "endswith", "search")
KWARGS = ("case", "fold")

MONATE = {"jan": 1, "januar": 1, "feb": 2, "februar": 2, "mär": 3, "maer": 3, "mrz": 3, "märz": 3, "maerz": 3,
          "apr": 4, "april": 4, "mai": 5, "jun": 6, "juni": 6, "jul": 7, "juli": 7, "aug": 8, "august": 8,
          "sep": 9, "sept": 9, "september": 9, "okt": 10, "oktober": 10, "nov": 11, "november": 11,
          "dez": 12, "dezember": 12}
MONATSKURZ = ("", "jan", "feb", "mär", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "dez")
TAGWOERTER = ("heute", "gestern", "vorgestern", "morgen")
ZEITWOERTER = ("diese_woche", "letzte_woche", "naechste_woche", "dieser_monat", "letzter_monat",
               "naechster_monat", "dieses_quartal", "letztes_quartal", "naechstes_quartal", "dieses_jahr",
               "letztes_jahr", "vorjahr", "naechstes_jahr")
EINHEITEN = {"d": "d", "t": "d", "w": "w", "m": "m", "q": "q", "y": "y", "j": "y"}


def _fold_ident(s: str) -> str:
    return s.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


_FELDNAMEN: dict[str, str] = {}
for _f in FELDER.values():
    _FELDNAMEN[_fold_ident(_f.name)] = _f.name
    if _f.kurz:
        _FELDNAMEN[_fold_ident(_f.kurz)] = _f.name
_MONATE_FOLD = {_fold_ident(k): v for k, v in MONATE.items()}
_ZEITWORT_FOLD = {_fold_ident(w): w for w in TAGWOERTER + ZEITWOERTER}


def feld_name(ident: str) -> str | None:
    return _FELDNAMEN.get(_fold_ident(ident))


def sprache(kontext: str) -> dict:
    """GET /api/ausdruck/sprache: Felder, Operatoren, Schlüsselwörter, Datumswörter (Konzept 6.1)."""
    ops = {"text": ["==", "!=", "in", "not in", "startswith", "endswith", "search"],
           "betrag": ["==", "!=", "<", "<=", ">", ">="], "int": ["==", "!=", "<", "<=", ">", ">=", "in"],
           "auswahl": ["==", "!=", "in", "not in"], "bool": ["==", "!="],
           "datum": ["==", "!=", "<", "<=", ">", ">=", "in", "not in"],
           "konto": ["==", "!=", "in", "not in"], "kategorie": ["==", "!=", "in", "not in", "is None", "is not None"],
           "tags": ["in", "not in"]}
    felder = [{"name": f.name, "kurz": f.kurz, "typ": f.typ, "bezeichnung": f.label, "operatoren": ops[f.typ],
               "werte": list(f.werte), "nur_filter": f.nur_filter}
              for f in FELDER.values() if kontext == "filter" or not f.nur_filter]
    aus: dict[str, Any] = {"kontext": kontext, "felder": felder, "schluesselwoerter": ["and", "or", "not", "in", "is",
                           "None", "True", "False"], "aliase": {"&&": "and", "||": "or", "!": "not"},
                           "methoden": list(METHODEN), "kwargs": list(KWARGS)}
    if kontext == "filter":
        aus["datum"] = {"tagwoerter": list(TAGWOERTER), "zeitwoerter": list(ZEITWOERTER),
                        "einheiten": ["d", "w", "m", "q", "y"], "monate": MONATSKURZ[1:]}
    return aus


# =================================================================== Fehler


class AusdruckFehler(Exception):
    def __init__(self, fehler: list[dict]):
        super().__init__(fehler[0]["meldung"] if fehler else "Ausdruck ungültig")
        self.fehler = fehler


def _pos(quelle: str, off: int) -> tuple[int, int]:
    zeile = quelle.count("\n", 0, off) + 1
    spalte = off - (quelle.rfind("\n", 0, off) + 1) + 1
    return zeile, spalte


def _fehler(quelle: str, code: str, meldung: str, start: int, ende: int, erwartet: list[str] | None = None) -> dict:
    z, s = _pos(quelle, start)
    ez, es = _pos(quelle, max(ende, start))
    return {"code": code, "meldung": meldung, "zeile": z, "spalte": s, "ende_zeile": ez, "ende_spalte": es,
            "erwartet": erwartet or []}


# ==================================================================== Lexer


@dataclass
class Tok:
    art: str
    text: str
    start: int
    ende: int


_LEX = re.compile(r"""
 (?P<ws>\s+)
|(?P<kommentar>\#[^\n]*)
|(?P<str>[rR]?(?:"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'))
|(?P<offen>[rR]?["'])
|(?P<isodatum>\d{4}-\d{2}-\d{2}(?!\d))
|(?P<isoq>\d{4}-[qQ][1-4](?!\w))
|(?P<isomonat>\d{4}-\d{2}(?!\d))
|(?P<tag>\d{1,2}\.\d{1,2}\.(?:\d{4}(?!\d)|\d{2}(?!\d))?(?!\d))
|(?P<monatjahr>\d{1,2}/\d{4}(?!\d))
|(?P<dauer>\d+[dDtTwWmMqQyYjJ](?!\w))
|(?P<zahl>\d[\d_]*(?:\.\d+)?(?![\w]))
|(?P<ident>[^\W\d]\w*)
|(?P<op>==|!=|<=|>=|&&|\|\||\.\.|[<>!()\[\],.+\-/=])
""", re.VERBOSE)


def lexen(quelle: str) -> list[Tok]:
    aus: list[Tok] = []
    i = 0
    while i < len(quelle):
        m = _LEX.match(quelle, i)
        if m is None:
            raise AusdruckFehler([_fehler(quelle, "syntax", f"Unerwartetes Zeichen „{quelle[i]}“.", i, i + 1)])
        art = m.lastgroup or ""
        if art == "offen":
            raise AusdruckFehler([_fehler(quelle, "syntax", "Text ohne schließendes Anführungszeichen.",
                                          i, len(quelle))])
        if art not in ("ws", "kommentar"):
            aus.append(Tok(art, m.group(), i, m.end()))
        i = m.end()
    aus.append(Tok("ende", "", len(quelle), len(quelle)))
    return aus


def _str_wert(text: str) -> tuple[str, bool]:
    roh = text[0] in "rR"
    inhalt = text[2:-1] if roh else text[1:-1]
    if roh:
        return inhalt, True
    aus, i = [], 0
    while i < len(inhalt):
        c = inhalt[i]
        if c == "\\" and i + 1 < len(inhalt):
            n = inhalt[i + 1]
            aus.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'"}.get(n, "\\" + n))
            i += 2
        else:
            aus.append(c)
            i += 1
    return "".join(aus), False


# =================================================================== Parser
# Rohknoten: dict mit "k" (Art), "s"/"e" (Quelltext-Bereich) und Inhalt.


class _Parser:
    def __init__(self, quelle: str, kontext: str):
        self.q = quelle
        self.kontext = kontext
        self.toks = lexen(quelle)
        self.i = 0

    # ----------------------------------------------------------- Hilfen
    @property
    def t(self) -> Tok:
        return self.toks[self.i]

    def ist(self, *texte: str) -> bool:
        t = self.t
        if t.art == "op":
            return t.text in texte
        if t.art == "ident":
            return t.text.lower() in texte
        return False

    def weiter(self) -> Tok:
        t = self.t
        self.i += 1
        return t

    def fehler(self, meldung: str, tok: Tok | None = None, erwartet: list[str] | None = None,
               code: str = "syntax") -> AusdruckFehler:
        t = tok or self.t
        return AusdruckFehler([_fehler(self.q, code, meldung, t.start, t.ende or t.start + 1, erwartet)])

    def erwarte(self, text: str) -> Tok:
        if not self.ist(text):
            gefunden = "das Ende" if self.t.art == "ende" else f"„{self.t.text}“"
            raise self.fehler(f"„{text}“ erwartet, gefunden {gefunden}.", erwartet=[text])
        return self.weiter()

    # ----------------------------------------------------------- Regeln
    def ganz(self) -> dict:
        if self.t.art == "ende":
            raise self.fehler("Der Ausdruck ist leer.")
        teile = [self.oder()]
        while self.t.art != "ende":
            if self.kontext == "filter" and not self.ist(")", "]", ","):
                teile.append(self.oder())   # Nebeneinander im Filter: wie „and“ (Konzept 4.9)
                continue
            if self.ist("="):
                raise self.fehler("Für Vergleiche „==“ verwenden.", erwartet=["=="])
            raise self.fehler(f"Unerwartet: „{self.t.text}“.", erwartet=["and", "or"])
        if len(teile) == 1:
            return teile[0]
        return {"k": "und", "teile": teile, "s": teile[0]["s"], "e": teile[-1]["e"], "neben": True}

    def oder(self) -> dict:
        teile = [self.und()]
        while self.ist("or", "||"):
            self.weiter()
            teile.append(self.und())
        return teile[0] if len(teile) == 1 else {"k": "oder", "teile": teile, "s": teile[0]["s"], "e": teile[-1]["e"]}

    def und(self) -> dict:
        teile = [self.nicht()]
        while self.ist("and", "&&"):
            self.weiter()
            teile.append(self.nicht())
        return teile[0] if len(teile) == 1 else {"k": "und", "teile": teile, "s": teile[0]["s"], "e": teile[-1]["e"]}

    def nicht(self) -> dict:
        if self.ist("not", "!") and not (self.t.text.lower() == "not" and self.toks[self.i + 1].text == "in"):
            t = self.weiter()
            x = self.nicht()
            return {"k": "nicht", "x": x, "s": t.start, "e": x["e"]}
        return self.kette()

    def vergleichsop(self) -> str | None:
        if self.ist("==", "!=", "<", "<=", ">", ">="):
            return self.weiter().text
        if self.ist("in"):
            self.weiter()
            return "in"
        if self.ist("not") and self.toks[self.i + 1].art == "ident" and self.toks[self.i + 1].text.lower() == "in":
            self.weiter()
            self.weiter()
            return "not in"
        if self.ist("is"):
            self.weiter()
            if self.ist("not"):
                self.weiter()
                return "is not"
            return "is"
        if self.ist("="):
            raise self.fehler("Für Vergleiche „==“ verwenden.", erwartet=["=="])
        return None

    def kette(self) -> dict:
        terme = [self.bereich()]
        ops: list[str] = []
        while True:
            op = self.vergleichsop()
            if op is None:
                break
            ops.append(op)
            terme.append(self.bereich())
        if not ops:
            return terme[0]
        return {"k": "kette", "terme": terme, "ops": ops, "s": terme[0]["s"], "e": terme[-1]["e"]}

    def bereich(self) -> dict:
        a = self.summe()
        if self.ist(".."):
            self.weiter()
            b = self.summe()
            return {"k": "bereich", "von": a, "bis": b, "s": a["s"], "e": b["e"]}
        return a

    def summe(self) -> dict:
        x = self.unaer()
        if self.ist("+", "-"):
            vz = self.weiter().text
            if self.t.art != "dauer":
                raise self.fehler("Nach „+“ oder „-“ folgt eine Dauer wie „5d“, „2w“, „1m“ oder „1y“.",
                                  erwartet=["5d", "2w", "1m", "1q", "1y"])
            d = self.weiter()
            return {"k": "plus", "basis": x, "vz": vz, "dauer": d.text, "s": x["s"], "e": d.ende}
        return x

    def unaer(self) -> dict:
        if self.ist("+", "-"):
            t = self.weiter()
            if self.t.art != "dauer":
                raise self.fehler("Nach „+“ oder „-“ folgt eine Dauer wie „5d“, „2w“, „1m“ oder „1y“.",
                                  erwartet=["5d", "2w", "1m", "1q", "1y"])
            d = self.weiter()
            return {"k": "rel", "vz": t.text, "dauer": d.text, "s": t.start, "e": d.ende}
        return self.postfix()

    def postfix(self) -> dict:
        x = self.primaer()
        if self.ist(".") and x["k"] == "ident":
            self.weiter()
            if self.t.art != "ident":
                raise self.fehler("Methodenname erwartet.", erwartet=list(METHODEN))
            m = self.weiter()
            self.erwarte("(")
            args: list[dict] = []
            kwargs: dict[str, dict] = {}
            while not self.ist(")"):
                if self.t.art == "ident" and self.toks[self.i + 1].text == "=":
                    k = self.weiter()
                    self.weiter()
                    v = self.primaer()
                    kwargs[k.text] = {**v, "name_s": k.start, "name_e": k.ende}
                else:
                    args.append(self.oder())
                if not self.ist(","):
                    break
                self.weiter()
            ende = self.erwarte(")")
            return {"k": "methode", "obj": x, "name": m.text, "name_s": m.start, "name_e": m.ende, "args": args,
                    "kwargs": kwargs, "s": x["s"], "e": ende.ende}
        return x

    def primaer(self) -> dict:
        t = self.t
        if t.art == "str":
            self.weiter()
            wert, roh = _str_wert(t.text)
            return {"k": "str", "wert": wert, "roh": roh, "s": t.start, "e": t.ende}
        if t.art == "zahl":
            self.weiter()
            return {"k": "zahl", "text": t.text, "s": t.start, "e": t.ende}
        if t.art in ("isodatum", "isoq", "isomonat", "tag", "monatjahr"):
            self.weiter()
            return {"k": t.art, "text": t.text, "s": t.start, "e": t.ende}
        if t.art == "dauer":
            raise self.fehler(f"„{t.text}“ braucht ein Vorzeichen: „-{t.text}“ (zurück) oder „+{t.text}“ (voraus).",
                              code="dauer_ohne_vorzeichen")
        if t.art == "ident":
            low = t.text.lower()
            if low in ("and", "or", "in", "is"):
                raise self.fehler(f"Hier wird ein Wert oder Feld erwartet, nicht „{t.text}“.")
            self.weiter()
            if low in ("true", "false"):
                return {"k": "bool", "wert": low == "true", "s": t.start, "e": t.ende}
            if low in ("none", "null"):
                return {"k": "none", "s": t.start, "e": t.ende}
            knoten = {"k": "ident", "name": t.text, "s": t.start, "e": t.ende}
            if self.ist("/") and self.toks[self.i + 1].art == "zahl":
                self.weiter()
                j = self.weiter()
                knoten = {"k": "ident_jahr", "name": t.text, "jahr": j.text, "s": t.start, "e": j.ende}
            return knoten
        if t.art == "op" and t.text == "(":
            self.weiter()
            if self.ist(")"):
                raise self.fehler("Leere Klammer.")
            x = self.oder()
            if self.ist(","):
                elemente = [x]
                while self.ist(","):
                    self.weiter()
                    if self.ist(")"):
                        break
                    elemente.append(self.oder())
                e = self.erwarte(")")
                return {"k": "liste", "elemente": elemente, "s": t.start, "e": e.ende}
            e = self.erwarte(")")
            return {**x, "klammer": True, "s": t.start, "e": e.ende}
        if t.art == "op" and t.text == "[":
            self.weiter()
            elemente: list[dict] = []
            while not self.ist("]"):
                elemente.append(self.oder())
                if not self.ist(","):
                    break
                self.weiter()
            e = self.erwarte("]")
            return {"k": "liste", "elemente": elemente, "s": t.start, "e": e.ende}
        if t.art == "ende":
            raise self.fehler("Der Ausdruck endet zu früh.", erwartet=["Feld", "Wert"])
        if t.text == "=":
            raise self.fehler("Für Vergleiche „==“ verwenden.", erwartet=["=="])
        raise self.fehler(f"Unerwartet: „{t.text}“.")


# ============================================================= Typprüfung
# Typisierte Knoten (gespeichert, JSON): {"t": …}
#   oder/und {teile}, nicht {x}, kette {terme, ops}, methode {feld, name, muster, case, fold},
#   freitext {wert}, feld {name}, text {wert}, betrag {cent}, int {wert}, bool {wert}, none, auswahl {wert},
#   ref {art, id}, liste {werte}, zeit {z}.
# Zeitangaben z: {"a": "tag", j|None, m, d} | {"a": "wort", w} | {"a": "jahr", j} | {"a": "monat", j|None, m}
#   | {"a": "quartal", j|None, q} | {"a": "kw", j|None, w} | {"a": "rel", vz, n, e}
#   | {"a": "plus", basis, vz, n, e} | {"a": "bereich", von, bis}


@dataclass
class Bezuege:
    """Namen ↔ IDs für Konten, Kategorien und Tags (aus der Datenbank)."""
    konto_pfad: dict[int, str] = field(default_factory=dict)
    kategorie_pfad: dict[int, str] = field(default_factory=dict)
    tag_name: dict[int, str] = field(default_factory=dict)

    @classmethod
    def laden(cls, con) -> "Bezuege":
        zeilen = {r["id"]: r for r in con.execute("SELECT id, name, art, eltern_id FROM konto")}

        def pfad(kid: int) -> str:
            teile, k, gesehen = [], kid, set()
            while k is not None and k in zeilen and k not in gesehen:
                gesehen.add(k)
                teile.append(zeilen[k]["name"])
                k = zeilen[k]["eltern_id"]
            return ":".join(reversed(teile))

        b = cls()
        for kid, r in zeilen.items():
            if r["art"] in BESTAND:
                b.konto_pfad[kid] = pfad(kid)
            elif r["art"] in KATEGORIEARTEN:
                b.kategorie_pfad[kid] = pfad(kid)
        b.tag_name = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM tag")}
        return b

    @staticmethod
    def _suchen(karte: dict[int, str], name: str) -> list[int]:
        n = _fold_ident(name.strip())
        voll = [k for k, p in karte.items() if _fold_ident(p) == n]
        if voll:
            return voll
        return [k for k, p in karte.items() if _fold_ident(p.rsplit(":", 1)[-1]) == n]

    def name(self, art: str, rid: int) -> str:
        karte = {"konto": self.konto_pfad, "kategorie": self.kategorie_pfad, "tag": self.tag_name}[art]
        return karte.get(rid, f"#{rid}")

    def aufloesen(self, art: str, name: str) -> list[int]:
        karte = {"konto": self.konto_pfad, "kategorie": self.kategorie_pfad, "tag": self.tag_name}[art]
        m = re.fullmatch(r"#(\d+)", name.strip())
        if m and int(m.group(1)) in karte:
            return [int(m.group(1))]
        return self._suchen(karte, name)


ART_DER_REF = {"konto": "konto", "kategorie": "kategorie", "tags": "tag"}


class _Pruefer:
    def __init__(self, quelle: str, kontext: str, bezuege: Bezuege):
        self.q = quelle
        self.kontext = kontext
        self.bez = bezuege
        self.fehler: list[dict] = []
        self.hinweise: list[dict] = []
        self.freitexte: list[dict] = []

    def melden(self, n: dict, code: str, meldung: str) -> None:
        self.fehler.append(_fehler(self.q, code, meldung, n["s"], n["e"]))

    # ------------------------------------------------------- Wahrheitswerte
    def bool_knoten(self, n: dict) -> dict:
        k = n["k"]
        if k in ("oder", "und"):
            teile: list[dict] = []
            for x in n["teile"]:
                y = self.bool_knoten(x)
                teile.extend(y["teile"] if y["t"] == k else [y])   # gleichartige Verschachtelung abflachen
            return {"t": k, "teile": teile}
        if k == "nicht":
            return {"t": "nicht", "x": self.bool_knoten(n["x"])}
        if k == "kette":
            return self.kette(n)
        if k == "methode":
            return self.methode(n)
        if k == "ident":
            fname = feld_name(n["name"])
            if fname and FELDER[fname].typ == "bool":
                return {"t": "feld", "name": fname}
            if self.kontext == "filter" and fname is None and n["name"].lower() not in SCHLUESSELWOERTER:
                return self.freitext(n, n["name"])
            if fname:
                beispiel = ('"REWE" in ' + fname) if FELDER[fname].typ == "text" else (fname + " == …")
                self.melden(n, "kein_wahrheitswert", f"„{n['name']}“ allein ist keine Bedingung. Vergleichen Sie, "
                            f"z. B. „{beispiel}“.")
            else:
                self.melden(n, "feld_unbekannt", self.unbekannt_text(n["name"]))
            return {"t": "bool", "wert": False}
        if k == "str" and self.kontext == "filter":
            return self.freitext(n, n["wert"])
        if k == "zahl" and self.kontext == "filter":
            return self.freitext(n, n["text"])
        if k == "bool":
            return {"t": "bool", "wert": n["wert"]}
        if k in ("tag", "isodatum", "monatjahr", "isomonat", "isoq", "rel", "plus", "bereich", "ident_jahr"):
            self.melden(n, "kein_wahrheitswert", "Eine Datumsangabe allein ist keine Bedingung. "
                        "Schreiben Sie z. B. „datum in …“.")
            return {"t": "bool", "wert": False}
        self.melden(n, "kein_wahrheitswert", "Dieser Teil ergibt keinen Wahrheitswert (True oder False).")
        return {"t": "bool", "wert": False}

    def freitext(self, n: dict, wert: str) -> dict:
        if not wert.strip():
            self.melden(n, "wert_ungueltig", "Leerer Freitext.")
        name = wert if isinstance(wert, str) else str(wert)
        if re.fullmatch(r"[^\W\d]\w*", name):
            nahe = difflib.get_close_matches(_fold_ident(name), list(_FELDNAMEN), n=1, cutoff=0.8)
            if nahe and len(name) > 3:
                self.hinweise.append({**_fehler(self.q, "freitext", f"„{name}“ wird als Freitext gesucht. Meinten Sie "
                                                f"das Feld „{_FELDNAMEN[nahe[0]]}“?", n["s"], n["e"])})
        self.freitexte.append({"wert": name, "s": n["s"], "e": n["e"]})
        return {"t": "freitext", "wert": name}

    def unbekannt_text(self, name: str) -> str:
        if name.lower() == "contains":
            return "„contains“ gibt es nicht. Schreiben Sie „\"REWE\" in empfänger“."
        nahe = difflib.get_close_matches(_fold_ident(name), list(_FELDNAMEN), n=1, cutoff=0.6)
        tipp = f" Meinten Sie „{_FELDNAMEN[nahe[0]]}“?" if nahe else ""
        if _fold_ident(name) in _ZEITWORT_FOLD or _fold_ident(name) in _MONATE_FOLD:
            return f"„{name}“ ist eine Datumsangabe und gehört an ein Datumsfeld, z. B. „datum in {name}“."
        return f"Unbekanntes Feld „{name}“.{tipp}"

    # -------------------------------------------------------------- Methoden
    def methode(self, n: dict) -> dict:
        obj = n["obj"]
        fname = feld_name(obj["name"]) if obj["k"] == "ident" else None
        leer = {"t": "bool", "wert": False}
        if fname is None:
            self.melden(obj, "feld_unbekannt", self.unbekannt_text(obj.get("name", "?")))
            return leer
        f = FELDER[fname]
        if f.typ != "text":
            self.melden(n, "methode_unbekannt", f"„.{n['name']}()“ gibt es nur für Textfelder (Empfänger, "
                        "Verwendungszweck, Notiz, IBAN).")
            return leer
        name = n["name"].lower()
        if name not in METHODEN:
            tipp = " Schreiben Sie „\"…\" in " + fname + "“." if name in ("contains", "find", "includes") else ""
            self.fehler.append(_fehler(self.q, "methode_unbekannt", f"Die Methode „{n['name']}“ gibt es nicht. "
                                       f"Erlaubt: {', '.join(METHODEN)}.{tipp}", n["name_s"], n["name_e"]))
            return leer
        if len(n["args"]) != 1 or n["args"][0]["k"] != "str":
            self.melden(n, "wert_ungueltig", f"„.{name}()“ erwartet genau einen Text in Anführungszeichen.")
            return leer
        muster = n["args"][0]["wert"]
        opts = {"case": False, "fold": True}
        for k, v in n["kwargs"].items():
            if k not in KWARGS:
                self.fehler.append(_fehler(self.q, "wert_ungueltig", f"Unbekanntes Argument „{k}“. Erlaubt: case, fold.",
                                           v["name_s"], v["name_e"]))
            elif v["k"] != "bool":
                self.melden(v, "wert_ungueltig", f"„{k}“ erwartet True oder False.")
            else:
                opts[k] = v["wert"]
        if name == "search":
            fehler = regex_pruefen(muster)
            if fehler:
                a = n["args"][0]
                off = a["s"] + (2 if a.get("roh") else 1) + fehler[1]
                self.fehler.append(_fehler(self.q, fehler[0], fehler[2], off, min(off + 1, a["e"])))
                return leer
        elif not muster:
            self.melden(n["args"][0], "wert_ungueltig", "Leerer Text.")
        return {"t": "methode", "feld": fname, "name": name, "muster": muster, "case": opts["case"],
                "fold": opts["fold"]}

    # ----------------------------------------------------------- Vergleiche
    def term_feld(self, n: dict) -> str | None:
        if n["k"] == "ident" and not n.get("klammer"):
            return feld_name(n["name"])
        return None

    def kette(self, n: dict) -> dict:
        terme, ops = n["terme"], n["ops"]
        leer = {"t": "bool", "wert": False}
        felder = [self.term_feld(x) for x in terme]
        if len(ops) > 1:
            return self.lange_kette(n, felder)
        a, b = terme
        op = ops[0]
        fa, fb = felder
        if op in ("in", "not in"):
            return self.vgl_in(n, a, b, fa, fb, op)
        if op in ("is", "is not"):
            if fa is None or b["k"] != "none":
                self.melden(n, "operator_unpassend", "„is“ gibt es nur als „kategorie is None“ bzw. "
                            "„kategorie is not None“.")
                return leer
            if FELDER[fa].typ != "kategorie":
                tipp = " Leere Texte prüfen Sie mit „== \"\"“." if FELDER[fa].typ == "text" else ""
                self.melden(n, "operator_unpassend", f"„{fa}“ ist nie None.{tipp}")
                return leer
            return {"t": "kette", "terme": [{"t": "feld", "name": fa}, {"t": "none"}], "ops": [op]}
        if fa is None and fb is None:
            for x in (a, b):
                if x["k"] == "ident" and feld_name(x["name"]) is None and x["name"].lower() not in SCHLUESSELWOERTER:
                    if not (self.kontext == "filter" and self.ist_zeit_roh(x)):
                        self.melden(x, "feld_unbekannt", self.unbekannt_text(x["name"]))
                        return leer
            self.melden(n, "operator_unpassend", "Ein Vergleich braucht auf einer Seite ein Feld, z. B. "
                        "„betrag > 10“.")
            return leer
        if fa is not None and fb is not None:
            self.melden(n, "operator_unpassend", "Zwei Felder lassen sich nicht miteinander vergleichen.")
            return leer
        if fa is None:   # Wert links, Feld rechts: Operator spiegeln
            spiegel = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}
            wert = self.wert_fuer(fb, a, op)
            if wert is None:
                return leer
            return {"t": "kette", "terme": [wert, {"t": "feld", "name": fb}], "ops": [op],
                    "_norm": spiegel[op]}
        wert = self.wert_fuer(fa, b, op)
        if wert is None:
            return leer
        return {"t": "kette", "terme": [{"t": "feld", "name": fa}, wert], "ops": [op]}

    def lange_kette(self, n: dict, felder: list[str | None]) -> dict:
        leer = {"t": "bool", "wert": False}
        ops = n["ops"]
        nur_feld = [f for f in felder if f]
        if len(nur_feld) != 1 or any(op not in ("<", "<=", ">", ">=") for op in ops):
            self.melden(n, "operator_unpassend", "Verkettete Vergleiche sind nur wie „30 <= betrag <= 40“ erlaubt: "
                        "ein Feld, nur <, <=, >, >=.")
            return leer
        steigend = all(op in ("<", "<=") for op in ops)
        fallend = all(op in (">", ">=") for op in ops)
        if not (steigend or fallend):
            self.melden(n, "operator_unpassend", "Verkettete Vergleiche müssen in eine Richtung gehen, "
                        "z. B. „30 <= betrag <= 40“.")
            return leer
        fname = nur_feld[0]
        terme = []
        for x, f in zip(n["terme"], felder):
            if f:
                terme.append({"t": "feld", "name": f})
            else:
                w = self.wert_fuer(fname, x, "<")
                if w is None:
                    return leer
                terme.append(w)
        return {"t": "kette", "terme": terme, "ops": list(ops)}

    def vgl_in(self, n: dict, a: dict, b: dict, fa: str | None, fb: str | None, op: str) -> dict:
        leer = {"t": "bool", "wert": False}
        if fb is not None and fa is None:   # "x" in feld
            typ = FELDER[fb].typ
            if typ == "text":
                if a["k"] != "str":
                    self.melden(a, "operator_unpassend", f"Links von „{op} {fb}“ steht ein Text in Anführungszeichen.")
                    return leer
                if not a["wert"]:
                    self.melden(a, "wert_ungueltig", "Leerer Text.")
                return {"t": "kette", "terme": [{"t": "text", "wert": a["wert"]}, {"t": "feld", "name": fb}], "ops": [op]}
            if typ == "tags":
                w = self.ref_wert("tags", a)
                return leer if w is None else {"t": "kette", "terme": [w, {"t": "feld", "name": fb}], "ops": [op]}
            self.melden(n, "operator_unpassend", f"„… in {fb}“ geht nur bei Textfeldern und Tags. "
                        f"Meinten Sie „{fb} in [...]“?")
            return leer
        if fa is None:
            self.melden(n, "operator_unpassend", "Bei „in“ steht ein Feld links oder rechts.")
            return leer
        typ = FELDER[fa].typ
        if typ == "datum" and b["k"] != "liste":
            z = self.zeit(b)
            return leer if z is None else {"t": "kette", "terme": [{"t": "feld", "name": fa}, z], "ops": [op]}
        if b["k"] != "liste":
            if typ == "text" and b["k"] == "str":
                self.melden(n, "operator_unpassend", f"Für Teiltexte schreiben Sie „\"{b['wert']}\" in {fa}“.")
            else:
                self.melden(b, "operator_unpassend", f"Nach „{fa} {op}“ folgt eine Liste, z. B. [\"a\", \"b\"].")
            return leer
        if typ in ("tags", "bool"):
            self.melden(n, "operator_unpassend", f"„{fa} in [...]“ ist nicht möglich.")
            return leer
        werte = []
        for x in b["elemente"]:
            w = self.wert_fuer(fa, x, "==")
            if w is None:
                return leer
            werte.append(w)
        if not werte:
            self.melden(b, "wert_ungueltig", "Leere Liste.")
            return leer
        return {"t": "kette", "terme": [{"t": "feld", "name": fa}, {"t": "liste", "werte": werte}], "ops": [op]}

    # -------------------------------------------------------------- Werte
    def wert_fuer(self, fname: str, x: dict, op: str) -> dict | None:
        f = FELDER[fname]
        if f.nur_filter and self.kontext == "regel":
            self.melden(x, "nur_im_filter", "Datumsangaben gibt es nur im Filter. Für Regeln eignen sich "
                        "„monatstag“, „monat“ oder „wochentag“." if f.typ == "datum" else
                        f"„{fname}“ gibt es nur im Filter.")
            return None
        if op in ("<", "<=", ">", ">=") and f.typ not in ("betrag", "int", "datum"):
            tipp = f" Meinten Sie „\"…\" in {fname}“ oder „{fname}.startswith(\"…\")“?" if f.typ == "text" else ""
            self.melden(x, "operator_unpassend", f"„{op}“ ist für „{fname}“ nicht möglich.{tipp}")
            return None
        if f.typ == "text":
            if x["k"] != "str":
                self.melden(x, "operator_unpassend", f"„{fname}“ wird mit einem Text in Anführungszeichen verglichen.")
                return None
            return {"t": "text", "wert": x["wert"]}
        if f.typ == "betrag":
            return self.betrag(x)
        if f.typ == "int":
            return self.ganzzahl(f, x)
        if f.typ == "bool":
            if x["k"] != "bool":
                self.melden(x, "operator_unpassend", f"„{fname}“ wird mit True oder False verglichen.")
                return None
            return {"t": "bool", "wert": x["wert"]}
        if f.typ == "auswahl":
            if x["k"] != "str" or _fold_ident(x["wert"]) not in f.werte:
                self.melden(x, "wert_ungueltig", f"Erlaubte Werte für „{fname}“: "
                            + ", ".join(f'"{w}"' for w in f.werte) + ".")
                return None
            return {"t": "auswahl", "wert": _fold_ident(x["wert"])}
        if f.typ in ("konto", "kategorie"):
            if x["k"] == "none":
                if f.typ == "kategorie":
                    self.melden(x, "operator_unpassend", "Schreiben Sie „kategorie is None“.")
                else:
                    self.melden(x, "operator_unpassend", "„konto“ ist nie None.")
                return None
            return self.ref_wert(fname, x)
        if f.typ == "datum":
            return self.zeit(x)
        if f.typ == "tags":
            self.melden(x, "operator_unpassend", "Tags prüfen Sie mit „\"Name\" in tags“.")
        return None

    def ref_wert(self, fname: str, x: dict) -> dict | None:
        art = ART_DER_REF[fname]
        if x["k"] != "str":
            self.melden(x, "operator_unpassend", f"„{fname}“ wird mit einem Namen in Anführungszeichen verglichen.")
            return None
        ids = self.bez.aufloesen(art, x["wert"])
        wort = {"konto": "Konto", "kategorie": "Kategorie", "tag": "Tag"}[art]
        if not ids:
            self.melden(x, "referenz_unbekannt", f"{wort} „{x['wert']}“ gibt es nicht.")
            return None
        if len(ids) > 1:
            self.melden(x, "referenz_unbekannt", f"{wort} „{x['wert']}“ ist mehrdeutig. Geben Sie den vollen Pfad an, "
                        "z. B. " + " oder ".join(f"„{self.bez.name(art, i)}“" for i in sorted(ids)[:2]) + ".")
            return None
        return {"t": "ref", "art": art, "id": ids[0]}

    def betrag(self, x: dict) -> dict | None:
        if x["k"] != "zahl":
            self.melden(x, "operator_unpassend", "Ein Betrag ist eine Zahl wie 12 oder 12.50.")
            return None
        m = re.fullmatch(r"(\d[\d_]*)(?:\.(\d+))?", x["text"])
        if m is None or m.group(1).endswith("_") or "__" in m.group(1):
            self.melden(x, "wert_ungueltig", "Ungültige Zahl.")
            return None
        nach = m.group(2) or ""
        if len(nach) > 2:
            self.melden(x, "wert_ungueltig", "Beträge haben höchstens zwei Nachkommastellen.")
            return None
        cent = int(m.group(1).replace("_", "")) * 100 + int((nach + "00")[:2])
        if cent > 10 ** 13:
            self.melden(x, "wert_ungueltig", "Betrag zu groß.")
            return None
        return {"t": "betrag", "cent": cent}

    def ganzzahl(self, f: Feld, x: dict) -> dict | None:
        if f.name == "monat" and x["k"] == "ident" and _fold_ident(x["name"]) in _MONATE_FOLD:
            return {"t": "int", "wert": _MONATE_FOLD[_fold_ident(x["name"])], "monat": True}
        if x["k"] != "zahl" or not re.fullmatch(r"\d+", x["text"]):
            self.melden(x, "wert_ungueltig", f"„{f.name}“ wird mit einer ganzen Zahl verglichen.")
            return None
        w = int(x["text"])
        lo, hi = f.bereich or (0, 10 ** 9)
        if not lo <= w <= hi:
            self.melden(x, "wert_ungueltig", f"„{f.name}“ liegt zwischen {lo} und {hi}.")
            return None
        return {"t": "int", "wert": w}

    # -------------------------------------------------------------- Zeit
    def ist_zeit_roh(self, x: dict) -> bool:
        if x["k"] == "ident":
            n = _fold_ident(x["name"])
            return n in _ZEITWORT_FOLD or n in _MONATE_FOLD or bool(re.fullmatch(r"q[1-4]|kw\d{1,2}", n))
        return x["k"] in ("tag", "isodatum", "monatjahr", "isomonat", "isoq", "rel", "plus", "bereich", "ident_jahr")

    def zeit(self, x: dict) -> dict | None:
        if self.kontext == "regel":
            self.melden(x, "nur_im_filter", "Datumsangaben gibt es nur im Filter. Für Regeln eignen sich "
                        "„monatstag“, „monat“ oder „wochentag“.")
            return None
        try:
            z = self._zeit(x)
        except _ZeitFehler as e:
            self.melden(x, e.code, e.meldung)
            return None
        return {"t": "zeit", "z": z}

    def _zeit(self, x: dict) -> dict:
        k = x["k"]
        if k == "str":
            unter = _Parser(x["wert"], "filter")
            try:
                roh = unter.bereich()
                if unter.t.art != "ende":
                    raise _ZeitFehler("datum_ungueltig", f"„{x['wert']}“ ist keine Datumsangabe.")
            except AusdruckFehler:
                raise _ZeitFehler("datum_ungueltig", f"„{x['wert']}“ ist keine Datumsangabe.") from None
            return self._zeit(roh)
        if k == "tag":
            teile = x["text"].split(".")
            d, m = int(teile[0]), int(teile[1])
            j = _jahr_aus(teile[2]) if teile[2] else None
            _tag_pruefen(j, m, d)
            return {"a": "tag", "j": j, "m": m, "d": d}
        if k == "isodatum":
            j, m, d = (int(t) for t in x["text"].split("-"))
            _tag_pruefen(j, m, d)
            return {"a": "tag", "j": j, "m": m, "d": d}
        if k == "isomonat":
            j, m = (int(t) for t in x["text"].split("-"))
            if not 1 <= m <= 12:
                raise _ZeitFehler("datum_ungueltig", f"Den Monat {m} gibt es nicht.")
            return {"a": "monat", "j": j, "m": m}
        if k == "isoq":
            return {"a": "quartal", "j": int(x["text"][:4]), "q": int(x["text"][-1])}
        if k == "monatjahr":
            m, j = (int(t) for t in x["text"].split("/"))
            if not 1 <= m <= 12:
                raise _ZeitFehler("datum_ungueltig", f"Den Monat {m} gibt es nicht.")
            return {"a": "monat", "j": j, "m": m}
        if k == "zahl":
            if re.fullmatch(r"\d{4}", x["text"]):
                return {"a": "jahr", "j": int(x["text"])}
            if re.fullmatch(r"\d{1,2}\.\d{1,2}", x["text"]):
                raise _ZeitFehler("datum_ungueltig", f"„{x['text']}“ ist eine Zahl. Meinten Sie „{x['text']}.“?")
            raise _ZeitFehler("datum_ungueltig", f"„{x['text']}“ ist keine Datumsangabe.")
        if k in ("ident", "ident_jahr"):
            n = _fold_ident(x["name"])
            j = int(x["jahr"]) if k == "ident_jahr" else None
            if j is not None and not re.fullmatch(r"\d{4}", x["jahr"]):
                raise _ZeitFehler("datum_ungueltig", "Nach „/“ folgt eine vierstellige Jahreszahl.")
            if n in _MONATE_FOLD:
                return {"a": "monat", "j": j, "m": _MONATE_FOLD[n]}
            if m := re.fullmatch(r"q([1-4])", n):
                return {"a": "quartal", "j": j, "q": int(m.group(1))}
            if m := re.fullmatch(r"kw(\d{1,2})", n):
                w = int(m.group(1))
                if not 1 <= w <= 53 or (j is not None and w > dt.date(j, 12, 28).isocalendar()[1]):
                    raise _ZeitFehler("datum_ungueltig", f"Die Kalenderwoche {w} gibt es nicht.")
                return {"a": "kw", "j": j, "w": w}
            if n in _ZEITWORT_FOLD and j is None:
                w = _ZEITWORT_FOLD[n]
                return {"a": "wort", "w": "letztes_jahr" if w == "vorjahr" else w}
            if feld_name(x["name"]):
                raise _ZeitFehler("operator_unpassend", "Zwei Felder lassen sich nicht miteinander vergleichen.")
            raise _ZeitFehler("datum_ungueltig", f"„{x['name']}“ ist keine Datumsangabe.")
        if k == "rel":
            n, e = _dauer(x["dauer"])
            return {"a": "rel", "vz": x["vz"], "n": n, "e": e}
        if k == "plus":
            n, e = _dauer(x["dauer"])
            basis = self._zeit(x["basis"])
            if basis["a"] in ("plus", "rel", "bereich"):
                raise _ZeitFehler("datum_ungueltig", "Je Seite ist nur eine Dauer erlaubt.")
            return {"a": "plus", "basis": basis, "vz": x["vz"], "n": n, "e": e}
        if k == "bereich":
            von, bis = self._zeit(x["von"]), self._zeit(x["bis"])
            if von["a"] == "bereich" or bis["a"] == "bereich":
                raise _ZeitFehler("datum_ungueltig", "Nur ein „..“ je Zeitraum.")
            if von.get("j") is not None and bis.get("j") is not None:
                a, _ = zeitraum(von, dt.date(2000, 1, 1))
                _, b = zeitraum(bis, dt.date(2000, 1, 1))
                if a > b:
                    raise _ZeitFehler("zeitraum_leer", "Der Zeitraum endet vor seinem Beginn.")
            return {"a": "bereich", "von": von, "bis": bis}
        raise _ZeitFehler("datum_ungueltig", "Hier wird eine Datumsangabe erwartet, z. B. „5.2.“, „2017“ oder „-30d“.")


class _ZeitFehler(Exception):
    def __init__(self, code: str, meldung: str):
        super().__init__(meldung)
        self.code, self.meldung = code, meldung


def _jahr_aus(text: str, bezug_jahr: int | None = None) -> int:
    if len(text) == 4:
        return int(text)
    jj = int(text)
    bezug = bezug_jahr or dt.date.today().year
    j = 2000 + jj
    return j if j <= bezug + 10 else 1900 + jj


def _tag_pruefen(j: int | None, m: int, d: int) -> None:
    if not 1 <= m <= 12:
        raise _ZeitFehler("datum_ungueltig", f"Den Monat {m} gibt es nicht.")
    if j is None:
        if d > (29 if m == 2 else calendar.monthrange(2001, m)[1]) or d < 1:
            raise _ZeitFehler("datum_ungueltig", f"Den {d:02d}.{m:02d}. gibt es nicht.")
        return
    if not 1 <= d <= calendar.monthrange(j, m)[1]:
        grund = f" {j} ist kein Schaltjahr." if m == 2 and d == 29 else ""
        raise _ZeitFehler("datum_ungueltig", f"Den {d:02d}.{m:02d}.{j} gibt es nicht.{grund}")


def _dauer(text: str) -> tuple[int, str]:
    n, e = int(text[:-1]), EINHEITEN.get(text[-1].lower())
    if e is None:  # pragma: no cover - Lexer lässt nur bekannte Einheiten durch
        raise _ZeitFehler("einheit_unbekannt", "Einheiten: d, w, m, q, y.")
    if n > 10000:
        raise _ZeitFehler("datum_ungueltig", "Dauer zu groß.")
    return n, e


# =========================================================== Zeitrechnung


def monat_plus(d: dt.date, n: int) -> dt.date:
    """Wie ``wiederkehrend``/``kredite``: gibt es den Tag im Zielmonat nicht, gilt der Monatsletzte."""
    m0 = d.year * 12 + d.month - 1 + n
    j, m = divmod(m0, 12)
    return dt.date(j, m + 1, min(d.day, calendar.monthrange(j, m + 1)[1]))


def _plus(d: dt.date, n: int, e: str) -> dt.date:
    if e == "d":
        return d + dt.timedelta(days=n)
    if e == "w":
        return d + dt.timedelta(weeks=n)
    return monat_plus(d, n * {"m": 1, "q": 3, "y": 12}[e])


def _monat(j: int, m: int) -> tuple[dt.date, dt.date]:
    return dt.date(j, m, 1), dt.date(j, m, calendar.monthrange(j, m)[1])


def _quartal(j: int, q: int) -> tuple[dt.date, dt.date]:
    return dt.date(j, 3 * q - 2, 1), _monat(j, 3 * q)[1]


def zeitraum(z: dict, heute: dt.date) -> tuple[dt.date, dt.date]:
    """Erster und letzter Tag (beide eingeschlossen) einer Zeitangabe (Konzept 4.6)."""
    a = z["a"]
    if a == "tag":
        j = z["j"] if z["j"] is not None else heute.year
        try:
            d = dt.date(j, z["m"], z["d"])
        except ValueError:  # 29.2. ohne Jahr in einem Nichtschaltjahr
            d = dt.date(j, 2, 28)
        return d, d
    if a == "jahr":
        return dt.date(z["j"], 1, 1), dt.date(z["j"], 12, 31)
    if a == "monat":
        return _monat(z["j"] if z["j"] is not None else heute.year, z["m"])
    if a == "quartal":
        return _quartal(z["j"] if z["j"] is not None else heute.year, z["q"])
    if a == "kw":
        j = z["j"] if z["j"] is not None else heute.isocalendar()[0]
        mo = dt.date.fromisocalendar(j, min(z["w"], dt.date(j, 12, 28).isocalendar()[1]), 1)
        return mo, mo + dt.timedelta(days=6)
    if a == "wort":
        return _wort(z["w"], heute)
    if a == "rel":
        return zeitraum({"a": "plus", "basis": {"a": "wort", "w": "heute"}, "vz": z["vz"], "n": z["n"], "e": z["e"]},
                        heute)
    if a == "plus":
        x0, x1 = zeitraum(z["basis"], heute)
        if z["vz"] == "+":
            return x0, _plus(x0, z["n"], z["e"]) - dt.timedelta(days=1)
        return _plus(x1 + dt.timedelta(days=1), -z["n"], z["e"]), x1
    if a == "bereich":
        return zeitraum(z["von"], heute)[0], zeitraum(z["bis"], heute)[1]
    raise ValueError(a)  # pragma: no cover


def _wort(w: str, h: dt.date) -> tuple[dt.date, dt.date]:
    tage = {"heute": 0, "gestern": -1, "vorgestern": -2, "morgen": 1}
    if w in tage:
        d = h + dt.timedelta(days=tage[w])
        return d, d
    art, versatz = {"diese_woche": ("w", 0), "letzte_woche": ("w", -1), "naechste_woche": ("w", 1),
                    "dieser_monat": ("m", 0), "letzter_monat": ("m", -1), "naechster_monat": ("m", 1),
                    "dieses_quartal": ("q", 0), "letztes_quartal": ("q", -1), "naechstes_quartal": ("q", 1),
                    "dieses_jahr": ("y", 0), "letztes_jahr": ("y", -1), "naechstes_jahr": ("y", 1)}[w]
    if art == "w":
        mo = h - dt.timedelta(days=h.weekday()) + dt.timedelta(weeks=versatz)
        return mo, mo + dt.timedelta(days=6)
    if art == "m":
        d = monat_plus(dt.date(h.year, h.month, 1), versatz)
        return _monat(d.year, d.month)
    if art == "q":
        q0 = (h.year * 4 + (h.month - 1) // 3) + versatz
        return _quartal(q0 // 4, q0 % 4 + 1)
    return dt.date(h.year + versatz, 1, 1), dt.date(h.year + versatz, 12, 31)


def ist_relativ(z: dict) -> bool:
    a = z["a"]
    if a in ("wort", "rel"):
        return True
    if a in ("tag", "monat", "quartal", "kw"):
        return z["j"] is None
    if a == "plus":
        return ist_relativ(z["basis"])
    if a == "bereich":
        return ist_relativ(z["von"]) or ist_relativ(z["bis"])
    return False


def festschreiben(z: dict, heute: dt.date) -> dict:
    """„Jahr festschreiben“ (Konzept 4.6.8): relative Angaben → feste."""
    a = z["a"]
    if a in ("tag", "monat", "quartal") and z["j"] is None:
        return {**z, "j": heute.year}
    if a == "kw" and z["j"] is None:
        return {**z, "j": heute.isocalendar()[0]}
    if a in ("wort", "rel"):
        x0, x1 = zeitraum(z, heute)
        if x0 == x1:
            return {"a": "tag", "j": x0.year, "m": x0.month, "d": x0.day}
        return {"a": "bereich", "von": {"a": "tag", "j": x0.year, "m": x0.month, "d": x0.day},
                "bis": {"a": "tag", "j": x1.year, "m": x1.month, "d": x1.day}}
    if a == "plus":
        return {**z, "basis": festschreiben(z["basis"], heute)}
    if a == "bereich":
        return {**z, "von": festschreiben(z["von"], heute), "bis": festschreiben(z["bis"], heute)}
    return z


# ============================================================ Drucken


_PRIO = {"oder": 1, "und": 2, "nicht": 3}


def _text(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def _muster(s: str) -> str:
    if '"' not in s and "\n" not in s and not s.endswith("\\"):
        return 'r"' + s + '"'
    return _text(s)


def _zahl_cent(c: int) -> str:
    e, r = divmod(c, 100)
    return str(e) if r == 0 else f"{e}.{r:02d}"


def zeit_text(z: dict) -> str:
    a = z["a"]
    if a == "tag":
        return f"{z['d']:02d}.{z['m']:02d}." + (str(z["j"]) if z["j"] is not None else "")
    if a == "jahr":
        return str(z["j"])
    if a == "monat":
        return f"{z['m']}/{z['j']}" if z["j"] is not None else MONATSKURZ[z["m"]]
    if a == "quartal":
        return f"q{z['q']}" + (f"/{z['j']}" if z["j"] is not None else "")
    if a == "kw":
        return f"kw{z['w']}" + (f"/{z['j']}" if z["j"] is not None else "")
    if a == "wort":
        return z["w"]
    if a == "rel":
        return f"{z['vz']}{z['n']}{z['e']}"
    if a == "plus":
        return f"{zeit_text(z['basis'])} {z['vz']} {z['n']}{z['e']}"
    return f"{zeit_text(z['von'])} .. {zeit_text(z['bis'])}"


def drucken(n: dict, bez: Bezuege | None = None, prio: int = 0) -> str:
    """Kanonischer Text (Konzept 4.8)."""
    t = n["t"]
    if t in ("oder", "und"):
        s = f" {'or' if t == 'oder' else 'and'} ".join(drucken(x, bez, _PRIO[t]) for x in n["teile"])
        return f"({s})" if prio > _PRIO[t] else s
    if t == "nicht":
        s = "not " + drucken(n["x"], bez, _PRIO["nicht"])
        return f"({s})" if prio > _PRIO["nicht"] else s
    if t == "kette":
        teile = [drucken(n["terme"][0], bez, 9)]
        for op, x in zip(n["ops"], n["terme"][1:]):
            teile += [op, drucken(x, bez, 9)]
        return " ".join(teile)
    if t == "methode":
        kw = (", case=True" if n["case"] else "") + ("" if n["fold"] else ", fold=False")
        arg = _muster(n["muster"]) if n["name"] == "search" else _text(n["muster"])
        return f"{n['feld']}.{n['name']}({arg}{kw})"
    if t == "freitext":
        return _text(n["wert"])
    if t == "feld":
        return n["name"]
    if t in ("text", "auswahl"):
        return _text(n["wert"])
    if t == "betrag":
        return _zahl_cent(n["cent"])
    if t == "int":
        return MONATSKURZ[n["wert"]] if n.get("monat") else str(n["wert"])
    if t == "bool":
        return "True" if n["wert"] else "False"
    if t == "none":
        return "None"
    if t == "ref":
        return _text(bez.name(n["art"], n["id"]) if bez else f"#{n['id']}")
    if t == "liste":
        return "[" + ", ".join(drucken(x, bez, 9) for x in n["werte"]) + "]"
    if t == "zeit":
        return zeit_text(n["z"])
    raise ValueError(t)  # pragma: no cover


# ============================================================ Prüfen (API)


def _ohne_hilfsfelder(n: Any) -> Any:
    if isinstance(n, dict):
        return {k: _ohne_hilfsfelder(v) for k, v in n.items() if not k.startswith("_")}
    if isinstance(n, list):
        return [_ohne_hilfsfelder(x) for x in n]
    return n


def _freitext_rueckfall(quelle: str) -> dict | None:
    """Reiner Freitext (Konzept 4.9): keine Operatorzeichen, kein Feld → Volltextsuche aller Wörter."""
    if re.search(r"[=<>!()\[\]\"'&|]", quelle):
        return None
    worte = quelle.split()
    if not worte or any(feld_name(w) for w in worte):
        return None
    if any(w.lower() in SCHLUESSELWOERTER - {"none", "null", "true", "false"} for w in worte):
        teile = [{"t": "freitext", "wert": w} for w in worte if w.lower() not in SCHLUESSELWOERTER]
    else:
        teile = [{"t": "freitext", "wert": w} for w in worte]
    if not teile:
        return None
    return teile[0] if len(teile) == 1 else {"t": "und", "teile": teile}


@dataclass
class Ergebnis:
    baum: dict
    hinweise: list[dict]
    freitexte: list[dict]


def uebersetzen(quelle: str, kontext: str, bez: Bezuege) -> Ergebnis:
    """Parst und prüft; wirft ``AusdruckFehler``. Ergebnis: typisierter Baum."""
    if kontext not in KONTEXTE:  # pragma: no cover - Aufrufer prüfen
        raise ValueError(kontext)
    if len(quelle) > MAX_AUSDRUCK:
        raise AusdruckFehler([_fehler(quelle, "zu_lang", f"Höchstens {MAX_AUSDRUCK} Zeichen.", 0, len(quelle))])
    try:
        roh = _Parser(quelle, kontext).ganz()
    except AusdruckFehler:
        if kontext == "filter":
            ft = _freitext_rueckfall(quelle)
            if ft is not None:
                return Ergebnis(ft, [], [{"wert": x["wert"]} for x in (ft["teile"] if ft["t"] == "und" else [ft])])
        raise
    p = _Pruefer(quelle, kontext, bez)
    baum = p.bool_knoten(roh)
    if p.fehler:
        p.fehler.sort(key=lambda f: (f["zeile"], f["spalte"]))
        raise AusdruckFehler(p.fehler)
    return Ergebnis(_ohne_hilfsfelder(baum), p.hinweise, p.freitexte)


def baukasten_faehig(n: dict) -> bool:
    """Oberste Ebene nur and oder nur or, höchstens eine Gruppenebene, not nur vor einem Vergleich."""
    def blatt(x: dict) -> bool:
        if x["t"] == "nicht":
            return x["x"]["t"] in ("kette", "methode", "freitext")
        return x["t"] in ("kette", "methode", "freitext", "feld")

    def gruppe(x: dict) -> bool:
        return blatt(x) or (x["t"] in ("und", "oder") and all(blatt(y) for y in x["teile"]))

    if blatt(n):
        return True
    return n["t"] in ("und", "oder") and all(gruppe(x) for x in n["teile"])


def zeitangaben(n: Any) -> list[dict]:
    aus: list[dict] = []
    if isinstance(n, dict):
        if n.get("t") == "zeit":
            aus.append(n["z"])
        else:
            for v in n.values():
                aus.extend(zeitangaben(v))
    elif isinstance(n, list):
        for v in n:
            aus.extend(zeitangaben(v))
    return aus


def _zusammenfassung_teil(n: dict, bez: Bezuege, heute: dt.date) -> str:
    t = n["t"]
    if t == "freitext":
        return f"Freitext „{n['wert']}“"
    if t == "kette" and len(n["ops"]) == 1:
        a, b = n["terme"]
        f = a if a["t"] == "feld" else b
        w = b if a["t"] == "feld" else a
        label = FELDER[f["name"]].label
        if w["t"] == "zeit":
            x0, x1 = zeitraum(w["z"], heute)
            bereich = x0.strftime("%d.%m.%Y") + ("" if x0 == x1 else " – " + x1.strftime("%d.%m.%Y"))
            return f"{label} {n['ops'][0]} {bereich}"
    return drucken(n, bez)


def pruefen(con, quelle: str, kontext: str, heute: dt.date, festschreiben_: bool = False) -> dict:
    """POST /api/ausdruck/pruefen (Konzept 6.2). Antwort auch bei Fehlern im Ausdruck."""
    bez = Bezuege.laden(con)
    try:
        e = uebersetzen(quelle, kontext, bez)
    except AusdruckFehler as f:
        return {"gueltig": False, "fehler": f.fehler, "kanonisch": None, "baum": None, "baukasten_faehig": False,
                "hinweise": [], "datumsangaben": [], "freitext": [], "zusammenfassung": []}
    if festschreiben_:
        e.baum = baum_festschreiben(e.baum, heute)
    aus: dict[str, Any] = {"gueltig": True, "fehler": [], "kanonisch": drucken(e.baum, bez), "baum": e.baum,
                           "baukasten_faehig": baukasten_faehig(e.baum), "hinweise": e.hinweise}
    if kontext == "filter":
        dz = []
        for z in zeitangaben(e.baum):
            x0, x1 = zeitraum(z, heute)
            dz.append({"text": zeit_text(z), "von": x0.isoformat(), "bis": x1.isoformat(),
                       "tage": (x1 - x0).days + 1, "relativ": ist_relativ(z)})
        aus["datumsangaben"] = dz
        aus["freitext"] = [f["wert"] for f in e.freitexte]
        teile = e.baum["teile"] if e.baum["t"] == "und" else [e.baum]
        aus["zusammenfassung"] = [_zusammenfassung_teil(x, bez, heute) for x in teile]
    else:
        aus["datumsangaben"], aus["freitext"], aus["zusammenfassung"] = [], [], []
    return aus


def filter_baum(con, quelle: str) -> dict:
    """Filtertext → Baum; 422 ``ausdruck_ungueltig`` mit ``details.fehler`` (Konzept 6.7)."""
    from .validierung import ApiFehler
    try:
        return uebersetzen(quelle, "filter", Bezuege.laden(con)).baum
    except AusdruckFehler as e:
        raise ApiFehler(422, "ausdruck_ungueltig", e.fehler[0]["meldung"], {"fehler": e.fehler}) from None


def text_aus_baum(baum: dict, bez: Bezuege) -> str:
    return drucken(baum, bez)


def baum_festschreiben(baum: Any, heute: dt.date) -> Any:
    if isinstance(baum, dict):
        if baum.get("t") == "zeit":
            return {"t": "zeit", "z": festschreiben(baum["z"], heute)}
        return {k: baum_festschreiben(v, heute) for k, v in baum.items()}
    if isinstance(baum, list):
        return [baum_festschreiben(v, heute) for v in baum]
    return baum


def verweise(baum: Any, art: str) -> set[int]:
    """IDs aller Verweise der Art ``konto``/``kategorie``/``tag`` im Baum."""
    aus: set[int] = set()
    if isinstance(baum, dict):
        if baum.get("t") == "ref" and baum.get("art") == art:
            aus.add(baum["id"])
        for v in baum.values():
            aus |= verweise(v, art)
    elif isinstance(baum, list):
        for v in baum:
            aus |= verweise(v, art)
    return aus


def verweise_ersetzen(baum: Any, art: str, alt: int, neu: int) -> Any:
    if isinstance(baum, dict):
        if baum.get("t") == "ref" and baum.get("art") == art and baum.get("id") == alt:
            return {**baum, "id": neu}
        return {k: verweise_ersetzen(v, art, alt, neu) for k, v in baum.items()}
    if isinstance(baum, list):
        return [verweise_ersetzen(v, art, alt, neu) for v in baum]
    return baum


# ======================================================= Reguläre Ausdrücke


_UNERLAUBT = [(re.compile(r"\\[1-9]|\(\?P="), "Rückverweise (\\1) sind nicht erlaubt."),
              (re.compile(r"\(\?<?[=!]"), "Lookarounds wie (?=…) oder (?!…) sind nicht erlaubt."),
              (re.compile(r"\(\?>|[*+?}]\+"), "Atomare Gruppen und possessive Quantoren sind nicht erlaubt.")]


def _re2_optionen(case: bool) -> Any:
    o = re2.Options()
    o.case_sensitive = case
    o.log_errors = False
    return o


def regex_pruefen(muster: str) -> tuple[str, int, str] | None:
    """(code, Versatz im Muster, Meldung) oder None. Erlaubt ist die RE2-Teilmenge (lineare Laufzeit)."""
    if len(muster) > MAX_MUSTER:
        return ("zu_lang", 0, f"Ein regulärer Ausdruck hat höchstens {MAX_MUSTER} Zeichen.")
    if not muster:
        return ("regex_ungueltig", 0, "Leerer regulärer Ausdruck.")
    for muster_re, meldung in _UNERLAUBT:
        m = muster_re.search(muster)
        if m:
            return ("regex_nicht_unterstuetzt", m.start(), meldung)
    try:
        re.compile(muster)
    except re.error as e:
        return ("regex_ungueltig", e.pos or 0, f"Ungültiger regulärer Ausdruck: {_re_meldung(e.msg)}.")
    try:
        re2.compile(muster, _re2_optionen(False))
    except re2.error:
        return ("regex_nicht_unterstuetzt", 0, "Dieses Konstrukt wird nicht unterstützt (erlaubt ist die "
                "RE2-Syntax ohne Rückverweise und Lookarounds).")
    return None


def _re_meldung(msg: str) -> str:
    return {"missing ), unterminated subpattern": "„)“ fehlt",
            "unbalanced parenthesis": "„)“ ohne „(“",
            "nothing to repeat": "Quantor ohne Zeichen davor",
            "unterminated character set": "„]“ fehlt",
            "multiple repeat": "doppelter Quantor"}.get(msg, msg)


# ============================================================== Auswertung


@dataclass
class Sicht:
    """Was ein Ausdruck von einer Buchung sieht. ``regelbetrag``: vorzeichenbehaftete Summe der Splits auf den
    betrachteten Bestandskonten (Ausgabe negativ)."""
    empfaenger: str | None
    verwendungszweck: str
    regelbetrag: int
    konten: set[int] = field(default_factory=set)
    datum: str | None = None
    iban: str | None = None
    notiz: str = ""
    kategorie_id: int | None = None
    status: str = "importiert"
    tag_ids: frozenset[int] = frozenset()
    tag_namen: tuple[str, ...] = ()
    umbuchung: bool = False

    @property
    def betrag(self) -> int:
        return abs(self.regelbetrag)

    @property
    def richtung(self) -> str:
        if self.umbuchung:
            return "umbuchung"
        return "ausgabe" if self.regelbetrag < 0 else "einnahme"

    def text(self, feld: str) -> str:
        if feld == "empfänger":
            return self.empfaenger or ""
        if feld == "verwendungszweck":
            return self.verwendungszweck or ""
        if feld == "notiz":
            return self.notiz or ""
        if feld == "iban":
            return self.iban or ""
        raise KeyError(feld)  # pragma: no cover

    def datum_d(self) -> dt.date | None:
        return dt.date.fromisoformat(self.datum) if self.datum else None


def _falten(s: str, case: bool, fold: bool) -> tuple[str, list[int]]:
    """Text für Vergleiche und Zuordnung Index → Originalindex (für Markierungen)."""
    aus: list[str] = []
    idx: list[int] = []
    for i, c in enumerate(s):
        f = c if case else c.casefold()
        if fold:
            f = (f.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                 .replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue"))
            if case:
                f = f.replace("ß", "ss")
        aus.append(f)
        idx.extend([i] * len(f))
    idx.append(len(s))
    return "".join(aus), idx


def _muster_falten(m: str, fold: bool) -> str:
    if not fold:
        return m
    return (m.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("Ä", "Ae").replace("Ö", "Oe")
            .replace("Ü", "Ue").replace("ß", "ss"))


_RE_CACHE: dict[tuple[str, bool], Any] = {}


def _regex(muster: str, case: bool) -> Any:
    k = (muster, case)
    r = _RE_CACHE.get(k)
    if r is None:
        if len(_RE_CACHE) > 512:
            _RE_CACHE.clear()
        r = re2.compile(muster, _re2_optionen(case))
        _RE_CACHE[k] = r
    return r


@dataclass
class Auswerter:
    heute: dt.date
    markieren: bool = False
    markierungen: list[dict] = field(default_factory=list)
    _zeiten: dict[str, tuple[dt.date, dt.date]] = field(default_factory=dict)

    def zeit(self, z: dict) -> tuple[dt.date, dt.date]:
        k = json.dumps(z, sort_keys=True)
        r = self._zeiten.get(k)
        if r is None:
            r = self._zeiten[k] = zeitraum(z, self.heute)
        return r

    # --------------------------------------------------------------- Werte
    def feldwert(self, name: str, s: Sicht) -> Any:
        f = FELDER[name]
        if f.typ == "text":
            return s.text(name)
        if name == "betrag":
            return s.betrag
        if name == "richtung":
            return s.richtung
        if name == "status":
            return s.status
        if name == "kategorie":
            return s.kategorie_id
        if name == "konto":
            return s.konten
        if name == "tags":
            return s.tag_ids
        d = s.datum_d()
        if d is None:
            return None
        if name == "datum":
            return d
        if name == "monatstag":
            return d.day
        if name == "monat":
            return d.month
        if name == "quartal":
            return (d.month - 1) // 3 + 1
        if name == "jahr":
            return d.year
        if name == "kw":
            return d.isocalendar()[1]
        if name == "wochentag":
            return WOCHENTAGE[d.weekday()]
        if name == "letzter_tag":
            return d.day == calendar.monthrange(d.year, d.month)[1]
        raise KeyError(name)  # pragma: no cover

    def textsuche(self, nadel: str, feld: str, s: Sicht, case: bool = False, fold: bool = True,
                  art: str = "in") -> bool:
        heu, idx = _falten(s.text(feld), case, fold)
        n, _ = _falten(nadel, case, fold)
        if art == "in":
            pos = heu.find(n)
            ok = pos >= 0 and bool(n)
            span = (pos, pos + len(n))
        elif art == "startswith":
            ok = heu.startswith(n)
            span = (0, len(n))
        elif art == "endswith":
            ok = heu.endswith(n)
            span = (len(heu) - len(n), len(heu))
        else:
            m = _regex(_muster_falten(nadel, fold), case).search(heu)
            ok = m is not None
            span = m.span() if m else (0, 0)
        if ok and self.markieren and span[1] > span[0]:
            self.markierungen.append({"feld": feld, "start": idx[span[0]], "ende": idx[span[1] - 1] + 1})
        return ok

    def gleich_text(self, a: str, b: str) -> bool:
        return _falten(a, False, True)[0] == _falten(b, False, True)[0]

    # ------------------------------------------------------------ Knoten
    def wahr(self, n: dict, s: Sicht) -> bool:
        t = n["t"]
        if t == "und":
            return all(self.wahr(x, s) for x in n["teile"])
        if t == "oder":
            return any(self.wahr(x, s) for x in n["teile"])
        if t == "nicht":
            alt = self.markieren
            self.markieren = False
            try:
                return not self.wahr(n["x"], s)
            finally:
                self.markieren = alt
        if t == "bool":
            return n["wert"]
        if t == "feld":
            return bool(self.feldwert(n["name"], s))
        if t == "freitext":
            gefunden = [self.textsuche(n["wert"], f, s) for f in ("empfänger", "verwendungszweck", "notiz")]
            if any(gefunden):
                return True
            nadel = _falten(n["wert"], False, True)[0]
            return any(nadel in _falten(tn, False, True)[0] for tn in s.tag_namen)
        if t == "methode":
            return self.textsuche(n["muster"], n["feld"], s, n["case"], n["fold"], n["name"])
        if t == "kette":
            return self.kette(n, s)
        raise ValueError(t)  # pragma: no cover

    def kette(self, n: dict, s: Sicht) -> bool:
        terme, ops = n["terme"], n["ops"]
        for i, op in enumerate(ops):
            if not self.vergleich(terme[i], op, terme[i + 1], s):
                return False
        return True

    def vergleich(self, a: dict, op: str, b: dict, s: Sicht) -> bool:
        if op in ("in", "not in"):
            r = self.enthalten(a, b, s)
            return r if op == "in" else not r
        if op in ("is", "is not"):
            r = self.feldwert(a["name"], s) is None
            return r if op == "is" else not r
        if a["t"] == "feld":
            feld, wert, op2 = a, b, op
        else:
            feld, wert = b, a
            op2 = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}[op]
        name = feld["name"]
        v = self.feldwert(name, s)
        typ = FELDER[name].typ
        if typ == "datum":
            if v is None:
                return False
            x0, x1 = self.zeit(wert["z"])
            return {"==": x0 <= v <= x1, "!=": not x0 <= v <= x1, "<": v < x0, "<=": v <= x1,
                    ">": v > x1, ">=": v >= x0}[op2]
        if typ == "text":
            r = self.gleich_text(v, wert["wert"])
            return r if op2 == "==" else not r
        if typ in ("konto", "kategorie"):
            r = (wert["id"] in v) if typ == "konto" else (v == wert["id"])
            return r if op2 == "==" else not r
        if typ == "auswahl":
            r = self._auswahl_gleich(name, v, wert["wert"])
            return r if op2 == "==" else not r
        w = wert["cent"] if wert["t"] == "betrag" else wert["wert"]
        if v is None:
            return False
        return {"==": v == w, "!=": v != w, "<": v < w, "<=": v <= w, ">": v > w, ">=": v >= w}[op2]

    @staticmethod
    def _auswahl_gleich(name: str, v: str, w: str) -> bool:
        if name == "wochentag" and w in WOCHENTAG_GRUPPEN:
            return v in WOCHENTAG_GRUPPEN[w]
        return v == w

    def enthalten(self, a: dict, b: dict, s: Sicht) -> bool:
        if b["t"] == "feld":   # "x" in feld / "Tag" in tags
            name = b["name"]
            if FELDER[name].typ == "tags":
                return a["id"] in s.tag_ids
            return self.textsuche(a["wert"], name, s)
        name = a["name"]
        typ = FELDER[name].typ
        v = self.feldwert(name, s)
        if typ == "datum":
            if v is None:
                return False
            werte = b["werte"] if b["t"] == "liste" else [b]
            return any(self.zeit(w["z"])[0] <= v <= self.zeit(w["z"])[1] for w in werte)
        werte = b["werte"]
        if typ == "text":
            return any(self.gleich_text(v, w["wert"]) for w in werte)
        if typ == "konto":
            return any(w["id"] in v for w in werte)
        if typ == "kategorie":
            return any(v == w["id"] for w in werte)
        if typ == "auswahl":
            return any(self._auswahl_gleich(name, v, w["wert"]) for w in werte)
        return v is not None and any(v == (w["cent"] if w["t"] == "betrag" else w["wert"]) for w in werte)


def auswerten(baum: dict, s: Sicht, heute: dt.date | None = None) -> bool:
    return Auswerter(heute or dt.date.today()).wahr(baum, s)


# ============================================================== Erklären


def erklaeren(baum: dict, s: Sicht, heute: dt.date, bez: Bezuege) -> dict:
    """„Warum?“ (Konzept 5.3): Baum mit Ergebnis je Knoten; Kurzschluss → ``nicht_ausgewertet``."""
    aw = Auswerter(heute)

    def wert_text(n: dict) -> str | None:
        if n["t"] == "kette":
            for x in n["terme"]:
                if x["t"] == "feld":
                    v = aw.feldwert(x["name"], s)
                    return _wert_lesbar(x["name"], v, bez)
        if n["t"] == "methode":
            return _wert_lesbar(n["feld"], aw.feldwert(n["feld"], s), bez)
        return None

    def knoten(n: dict, auswerten_: bool) -> dict:
        t = n["t"]
        aus: dict[str, Any] = {"text": drucken(n, bez), "art": t}
        if t in ("und", "oder"):
            kinder, ergebnis, weiter = [], (t == "und"), auswerten_
            for x in n["teile"]:
                k = knoten(x, weiter)
                kinder.append(k)
                if weiter:
                    r = k["ergebnis"] == "wahr"
                    if t == "und" and not r:
                        ergebnis, weiter = False, False
                    elif t == "oder" and r:
                        ergebnis, weiter = True, False
            aus["kinder"] = kinder
            aus["ergebnis"] = ("wahr" if ergebnis else "falsch") if auswerten_ else "nicht_ausgewertet"
            return aus
        if t == "nicht":
            k = knoten(n["x"], auswerten_)
            aus["kinder"] = [k]
            aus["ergebnis"] = ({"wahr": "falsch", "falsch": "wahr"}[k["ergebnis"]] if auswerten_
                               else "nicht_ausgewertet")
            return aus
        if not auswerten_:
            aus["ergebnis"] = "nicht_ausgewertet"
            return aus
        aus["ergebnis"] = "wahr" if aw.wahr(n, s) else "falsch"
        w = wert_text(n)
        if w is not None:
            aus["wert"] = w
        return aus

    return knoten(baum, True)


def _wert_lesbar(name: str, v: Any, bez: Bezuege) -> str:
    typ = FELDER[name].typ
    if v is None:
        return "None"
    if typ == "betrag":
        e, c = divmod(v, 100)
        return f"{e},{c:02d} €"
    if typ == "datum":
        return v.strftime("%d.%m.%Y")
    if typ == "konto":
        return ", ".join(bez.name("konto", k) for k in sorted(v))
    if typ == "kategorie":
        return bez.name("kategorie", v)
    if typ == "tags":
        return ", ".join(bez.name("tag", k) for k in sorted(v)) or "–"
    if typ == "text":
        return _text(v)
    return str(v)


# ====================================================== Sichten aus Buchungen


def sicht_aus_buchung(b: dict, art_von: dict[int, str], konten: set[int] | None = None) -> Sicht:
    """Sicht für Regeln (``konten`` None: alle Bestandssplits, wie ``regeln.anwenden``) bzw. für die Liste eines
    Kontos (Summe der Splits auf ``konten``)."""
    sp = b["splits"]
    if konten is None:
        bestand = [x for x in sp if art_von.get(x["konto_id"]) in BESTAND]
        betrag = sum(x["betrag"] for x in bestand)
        kset = {x["konto_id"] for x in bestand}
    else:
        betrag = sum(x["betrag"] for x in sp if x["konto_id"] in konten)
        kset = {x["konto_id"] for x in sp if art_von.get(x["konto_id"]) in BESTAND}
    return Sicht(
        empfaenger=b["empfaenger"]["name"] if b["empfaenger"] else None,
        verwendungszweck=b["verwendungszweck"], regelbetrag=betrag, konten=kset, datum=b["datum"],
        iban=b.get("gegen_iban"), notiz=" ".join(x["memo"] for x in sp if x["memo"]),
        kategorie_id=b["kategorie_id"], status=b["status"],
        tag_ids=frozenset(t["id"] for t in b["tags"]), tag_namen=tuple(t["name"] for t in b["tags"]),
        umbuchung=bool(b.get("ist_umbuchung")))


def filtern(con, baum: dict, ids: Iterable[int], konten: set[int] | None, heute: dt.date,
            laden: Callable[..., list[dict]]) -> list[int]:
    """IDs der Buchungen, auf die der Filterbaum zutrifft (Reihenfolge von ``ids``)."""
    from . import buch
    art_von = buch.kontoarten(con)
    aw = Auswerter(heute)
    aus: list[int] = []
    for teil in buch._stueckweise(list(ids)):
        for b in laden(con, teil, art_von=art_von):
            if aw.wahr(baum, sicht_aus_buchung(b, art_von, konten)):
                aus.append(b["id"])
    return aus


def markierungen(baum: dict, s: Sicht, heute: dt.date) -> list[dict]:
    aw = Auswerter(heute, markieren=True)
    aw.wahr(baum, s)
    gesehen, aus = set(), []
    for m in aw.markierungen:
        k = (m["feld"], m["start"], m["ende"])
        if k not in gesehen:
            gesehen.add(k)
            aus.append(m)
    return aus


# ============================================================ Filter → Regel


def _nur_filter(n: Any) -> bool:
    if isinstance(n, dict):
        if n.get("t") in ("zeit", "freitext") or (n.get("t") == "feld" and FELDER[n["name"]].nur_filter):
            return True
        return any(_nur_filter(v) for v in n.values())
    if isinstance(n, list):
        return any(_nur_filter(v) for v in n)
    return False


def als_regel(con, quelle: str, freitext_feld: str = "empfänger") -> dict:
    """„Als Regel speichern…“ (Konzept 5.4): Teile auf oberster Ebene, die nur im Filter gehen, entfallen;
    allein stehender Freitext wird zu ``"x" in <freitext_feld>``."""
    bez = Bezuege.laden(con)
    baum_ = filter_baum(con, quelle)
    teile = baum_["teile"] if baum_["t"] == "und" else [baum_]
    behalten, entfernt = [], []
    for x in teile:
        if x["t"] == "freitext":
            behalten.append({"t": "kette", "terme": [{"t": "text", "wert": x["wert"]},
                                                     {"t": "feld", "name": freitext_feld}], "ops": ["in"]})
        elif _nur_filter(x):
            entfernt.append(drucken(x, bez))
        else:
            behalten.append(x)
    if not behalten:
        return {"ausdruck": None, "entfernt": entfernt}
    neu = behalten[0] if len(behalten) == 1 else {"t": "und", "teile": behalten}
    return {"ausdruck": drucken(neu, bez), "entfernt": entfernt}
