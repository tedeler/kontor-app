"""Hilfen für Meilenstein-30-Tests (Kontor-Ausdrücke, Filter, Regeln mit Ausdruck und Tags).

Nur über die Spezifikation (ausdruecke.md, kategorisierung.md 8, openapi.yaml). Erwartungen rechnet der Test
aus den selbst angelegten Buchungen (``Fall``), nie aus Ausgaben der Anwendung. Lesarten: E-272.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .api import Api
from .vertrag import vertrag

#: Bezugstag aller relativen Datumsangaben in den Tests (ein Montag; Beispiele der Definition)
STICHTAG = "2026-11-16"
CODES = ["syntax", "feld_unbekannt", "methode_unbekannt", "operator_unpassend", "kein_wahrheitswert",
         "wert_ungueltig", "regex_ungueltig", "regex_nicht_unterstuetzt", "referenz_unbekannt", "nur_im_filter",
         "datum_ungueltig", "zeitraum_leer", "dauer_ohne_vorzeichen", "einheit_unbekannt", "zu_lang"]
#: Felder aus ausdruecke.md 2.2: Name → (Kurzform, in Regeln erlaubt)
FELDER = {"empfänger": ("empf", True), "verwendungszweck": ("vwz", True), "betrag": ("bet", True),
          "richtung": ("dir", True), "datum": ("dt", False), "kategorie": (None, True), "status": (None, True),
          "tags": (None, True), "notiz": (None, True), "iban": (None, True), "konto": (None, True),
          "monatstag": (None, True), "monat": (None, True), "quartal": (None, True), "jahr": (None, False),
          "kw": (None, False), "wochentag": (None, True), "letzter_tag": (None, True),
          "verdächtig": (None, False),   # D-263
          "unbestätigt": (None, False)}   # D-297
WIRKUNGEN = ["neu", "abweichend", "bereits_so", "verdeckt", "uebersprungen", "treffer"]


def falte(text: str) -> str:
    """Textvergleich der Sprache (ausdruecke.md 2.3): Kleinschreibung, Umlaute angeglichen."""
    t = text.casefold()   # ß → ss
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        t = t.replace(a, b)
    return t


# ------------------------------------------------------------------ Prüfen
def pruefen(api: Api, ausdruck: str, kontext: str = "filter", *, stichtag: str | None = STICHTAG, **felder) -> dict:
    body = {"ausdruck": ausdruck, "kontext": kontext, **felder}
    if stichtag is not None:
        body["stichtag"] = stichtag
    return api.post("/api/ausdruck/pruefen", json=body, erwartet=200).daten


def gueltig(api: Api, ausdruck: str, kontext: str = "filter", **kw) -> dict:
    p = pruefen(api, ausdruck, kontext, **kw)
    assert p["gueltig"] is True and p["fehler"] == [], f"{ausdruck!r} ({kontext}) sollte gültig sein: {p['fehler']}"
    assert isinstance(p["kanonisch"], str) and p["kanonisch"], f"{ausdruck!r}: kanonisch fehlt"
    assert p["baum"] is not None, f"{ausdruck!r}: baum fehlt"
    return p


def ungueltig(api: Api, ausdruck: str, codes, kontext: str = "filter", **kw) -> dict:
    """Erwartet einen ungültigen Ausdruck, dessen erster Fehler einen der ``codes`` trägt; liefert den Fehler."""
    codes = {codes} if isinstance(codes, str) else set(codes)
    p = pruefen(api, ausdruck, kontext, **kw)
    assert p["gueltig"] is False, f"{ausdruck!r} ({kontext}) sollte ungültig sein, kanonisch {p['kanonisch']!r}"
    assert p["kanonisch"] is None and p["baum"] is None, "ungültig: kanonisch und baum sind null"
    assert p["fehler"], "ungültig, aber keine Fehlerliste"
    f = p["fehler"][0]
    assert f["code"] in codes, f"{ausdruck!r}: Code {f['code']} statt {sorted(codes)} ({f['meldung']})"
    assert f["ende_zeile"] >= f["zeile"], f
    return f


def pruefe_fehlerliste(fehler) -> None:
    """``details.fehler`` eines 422 ``ausdruck_ungueltig`` hat die Form aus ausdruecke.md 4.2."""
    assert isinstance(fehler, list) and fehler, f"details.fehler: nichtleere Liste erwartet, ist {fehler!r}"
    v = vertrag().schema_validator("AusdruckFehler")
    for f in fehler:
        probleme = list(v.iter_errors(f))
        assert not probleme, f"details.fehler-Eintrag verletzt AusdruckFehler: {probleme[0].message}: {f}"


def ausdruck_ungueltig(r, code: str | None = None) -> list[dict]:
    """Antwort 422 ``ausdruck_ungueltig`` mit ``details.fehler``; optional Code des ersten Fehlers."""
    f = r.json()["fehler"]
    assert f["code"] == "ausdruck_ungueltig", f
    pruefe_fehlerliste(f["details"].get("fehler"))
    if code is not None:
        assert f["details"]["fehler"][0]["code"] == code, f["details"]["fehler"]
    return f["details"]["fehler"]


# ------------------------------------------------------------------ Testbestand
@dataclass
class Fall:
    """Eine angelegte Buchung mit den Werten, die die Felder der Sprache für sie haben (ausdruecke.md 2.2)."""
    name: str
    id: int
    datum: dt.date
    empf: str
    zweck: str
    cent: int                      # Summe der Splits auf Bestandskonten (Regelbetrag), mit Vorzeichen
    kategorie: str | None          # voller Pfad oder None (unkategorisiert)
    status: str
    tags: set = field(default_factory=set)
    notiz: str = ""
    konten: set = field(default_factory=set)
    umbuchung: bool = False

    @property
    def betrag(self) -> int:       # in Cent, ohne Vorzeichen
        return abs(self.cent)

    @property
    def richtung(self) -> str:
        return "umbuchung" if self.umbuchung else "ausgabe" if self.cent < 0 else "einnahme"

    @property
    def letzter_tag(self) -> bool:
        return (self.datum + dt.timedelta(days=1)).month != self.datum.month

    @property
    def quartal(self) -> int:
        return (self.datum.month - 1) // 3 + 1

    @property
    def kw(self) -> int:
        return self.datum.isocalendar()[1]

    @property
    def wochentag(self) -> str:
        return ["mo", "di", "mi", "do", "fr", "sa", "so"][self.datum.weekday()]

    def hat(self, text: str, wo: str = "empf") -> bool:
        return falte(text) in falte(getattr(self, wo))

    def freitext(self, *woerter: str) -> bool:
        heu = [falte(x) for x in (self.empf, self.zweck, self.notiz, *self.tags)]
        return all(any(falte(w) in h for h in heu) for w in woerter)


@dataclass
class Bestand:
    api: Api
    k: dict            # Kontoname → ID
    t: dict            # Tagname → ID
    e: dict            # Empfängername → ID
    faelle: list

    def __getitem__(self, name: str) -> Fall:
        return next(f for f in self.faelle if f.name == name)

    def ids(self, *namen: str) -> list[int]:
        return sorted(self[n].id for n in namen)

    def soll(self, bedingung) -> set:
        return {f.name for f in self.faelle if bedingung(f)}

    def namen(self, ids) -> set:
        nach_id = {f.id: f.name for f in self.faelle}
        return {nach_id.get(i, f"?{i}") for i in ids}


#: (Name, Datum, Empfänger, Verwendungszweck, Cent auf dem Giro, Gegenkonto, Status, Tags, Memo des Gegensplits)
_BUCHUNGEN = [
    ("rewe1", "2026-11-16", "REWE Markt GmbH", "Einkauf Wochenmarkt", -2550, "Supermarkt", "importiert",
     ["Urlaub"], "Pfand"),
    ("rewe2", "2026-11-14", "REWE Markt GmbH", "Getränke", -3500, "Lebensmittel", "bestaetigt", [], ""),
    ("mueller", "2026-11-12", "Müller Drogerie", "Shampoo ÜBERWEISUNG", -1250, "Offen", "importiert", [], ""),
    ("gehalt", "2026-10-31", "Arbeitgeber AG (fiktiv)", "Lohn Oktober", 250000, "Gehalt", "abgeglichen", [], ""),
    ("sparen", "2026-11-09", "", "Sparen", -10000, "Spar", "bestaetigt", [], ""),
    ("miete", "2026-02-05", "", "Miete Februar", -80000, "Wohnen", "bestaetigt", [], "Dauerauftrag"),
    ("alt", "2025-12-30", "EDEKA", "Jahresende", -999, "Supermarkt", "vorlaeufig", ["Steuer", "Urlaub"], ""),
    ("edeka", "2026-11-15", "EDEKA", "Brot", -2000, "Supermarkt", "bestaetigt", [], ""),
    ("schalttag", "2024-02-29", "Müller Drogerie", "Vorrat", -4000, "Lebensmittel", "bestaetigt", ["Steuer"], ""),
    ("erstattung", "2026-11-10", "REWE Markt GmbH", "Erstattung Pfand", 1500, "Offen", "importiert", [], ""),
]
#: Kategorien mit vollem Pfad
PFAD = {"Lebensmittel": "Lebensmittel", "Supermarkt": "Lebensmittel:Supermarkt", "Wohnen": "Wohnen",
        "Gehalt": "Gehalt"}


def bestand(api: Api) -> Bestand:
    """Kleiner synthetischer Buchbestand für Ausdrücke: zwei Bestandskonten, Kategorien mit Unterkategorie, ein
    Eigenkapitalkonto („unkategorisiert“), Tags, Empfänger, zehn Buchungen (eine Umbuchung, eine gesperrte)."""
    k = {"Giro": api.konto("Giro", "girokonto")["id"], "Spar": api.konto("Spar", "sparkonto")["id"],
         "Lebensmittel": api.konto("Lebensmittel", "aufwand")["id"], "Wohnen": api.konto("Wohnen", "aufwand")["id"],
         "Gehalt": api.konto("Gehalt", "ertrag")["id"], "Offen": api.konto("Offen", "eigenkapital")["id"]}
    k["Supermarkt"] = api.konto("Supermarkt", "aufwand", eltern_id=k["Lebensmittel"])["id"]
    t = {n: api.tag(n)["id"] for n in ("Urlaub", "Steuer")}
    e = {n: api.empfaenger(n)["id"] for n in ("REWE Markt GmbH", "Müller Drogerie", "EDEKA",
                                               "Arbeitgeber AG (fiktiv)")}
    faelle = []
    for name, datum, empf, zweck, cent, gegen, status, tags, memo in _BUCHUNGEN:
        felder = {"verwendungszweck": zweck, "tag_ids": [t[x] for x in tags],
                  "status": "bestaetigt" if status == "abgeglichen" else status}
        if empf:
            felder["empfaenger_id"] = e[empf]
        b = api.buchung(datum, [(k["Giro"], cent), (k[gegen], -cent, memo)], **felder)
        if status == "abgeglichen":
            api.patch(f"/api/buchungen/{b['id']}", json={"status": "abgeglichen"}, erwartet=200)
        umbuchung = gegen == "Spar"
        faelle.append(Fall(name, b["id"], dt.date.fromisoformat(datum), empf, zweck, 0 if umbuchung else cent,
                           PFAD.get(gegen), status, set(tags), memo, {"Giro", "Spar"} if umbuchung else {"Giro"},
                           umbuchung))
    return Bestand(api, k, t, e, faelle)


def gefiltert(api: Api, ausdruck: str, *, stichtag: str | None = STICHTAG, **params) -> list[dict]:
    """Alle Buchungen von ``GET /api/buchungen`` mit ``filter`` (alle Seiten)."""
    if stichtag is not None:
        params["stichtag"] = stichtag
    return api.alle_buchungen(filter=ausdruck, **params)


def treffer(b: Bestand, ausdruck: str, **params) -> set:
    return b.namen(x["id"] for x in gefiltert(b.api, ausdruck, **params))


# ------------------------------------------------------------------ Regeln
def regel(api: Api, name: str, erwartet: int = 201, **felder):
    r = api.post("/api/regeln", json={"name": name, **felder}, erwartet=erwartet)
    return r.daten if erwartet == 201 else r


def regeln(api: Api) -> list[dict]:
    return api.get("/api/regeln", erwartet=200).daten


def regel_test(api: Api, erwartet: int = 200, **body):
    """``POST /api/regeln/test``; ohne Angabe mit leerer Testmenge (alle Buchungen)."""
    body.setdefault("testmenge", "")
    r = api.post("/api/regeln/test", json=body, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def alle_treffer(api: Api, **body) -> list[dict]:
    """Treffer aller Seiten von ``POST /api/regeln/test``."""
    aus: list[dict] = []
    seite = 1
    while True:
        d = regel_test(api, seite=seite, **body)
        aus.extend(d["treffer"])
        if not d["treffer"] or len(aus) >= d["gesamt"]:
            assert len(aus) == d["gesamt"], f"gesamt {d['gesamt']}, geliefert {len(aus)}"
            return aus
        seite += 1


def wirkungen(api: Api, b: Bestand, **body) -> dict:
    """Name der Buchung → Wirkung."""
    nach_id = {f.id: f.name for f in b.faelle}
    return {nach_id[x["buchung_id"]]: x["wirkung"] for x in alle_treffer(api, **body)}


def als_id(wert, nach_name: dict):
    """Normalisiert einen Verweis offener Form (E-272 Punkt 7): ID, Objekt mit ``id`` oder Name/Pfad."""
    if wert is None or isinstance(wert, int):
        return wert
    if isinstance(wert, dict):
        return wert.get("id")
    assert isinstance(wert, str), wert
    return nach_name[wert]


def einzeln_anwenden(api: Api, regel_id: int, erwartet: int = 200, **body):
    body.setdefault("testmenge", "")
    r = api.post(f"/api/regeln/{regel_id}/anwenden", json=body, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def anwenden(api: Api, erwartet: int = 200, **body):
    r = api.post("/api/regeln/anwenden", json=body, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def tags_von(api: Api, bid: int) -> set:
    return {t["id"] for t in api.buchung_lesen(bid)["tags"]}


def ort_enthaelt(r, *teile: str) -> bool:
    """422 ``validierung``: Irgendein Eintrag in ``details`` nennt einen Ort mit allen ``teile`` (E-272 Punkt 6)."""
    def suche(x) -> bool:
        if isinstance(x, dict):
            ort = x.get("ort") or x.get("loc")
            if isinstance(ort, (list, tuple)) and set(teile) <= {str(o) for o in ort}:
                return True
            return any(suche(v) for v in x.values())
        if isinstance(x, list):
            return any(suche(v) for v in x)
        return False
    return suche(r.json()["fehler"]["details"])
