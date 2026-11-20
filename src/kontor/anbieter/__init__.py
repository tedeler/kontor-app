"""Anbieter-Module für den Abgleich von Mails und Buchungen (D-230).

Ein Anbieter (Amazon, PayPal, …) ist eine **Beschreibung** in einer TOML-Datei: Welche Mails gehören dazu, welche
Mailarten gibt es, wo stehen Kennung, Händler und Beträge (reguläre Ausdrücke), und woran ist die Bankbuchung zu
erkennen. Dieses Modul liest die Beschreibungen, prüft sie und wertet sie aus; es kennt keinen Anbieter beim Namen.
Reine Funktionen ohne Datenbank und ohne Netz. Aufbau der Dateien: ``ANBIETER.md``.

Mitgeliefert sind ``amazon.toml`` und ``paypal.toml``; weitere Dateien ``*.toml`` liegen im Verzeichnis der
Konfiguration ``anbieter_verzeichnis`` (``KONTOR_ANBIETER_VERZEICHNIS``). Eine fehlerhafte Zusatzdatei wird mit
einer Warnung übergangen, eine fehlerhafte mitgelieferte ist ein Programmfehler.
"""

from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

log = logging.getLogger("kontor")

ROLLEN = ("ausgabe", "erstattung", "storno")
GRUENDE = ("bestellung", "paypal")       # Grund der erwarteten Zahlung bei Rolle „ausgabe“
MAX_MUSTER = 500                          # Zeichen je regulärem Ausdruck
MAX_TEXT = 200_000                        # so viele Zeichen einer Mail werden höchstens ausgewertet
EINGEBAUT = ("amazon", "paypal")

# Betrag im deutschen Format: 1.234,56 / 1234,56 / 12 – optional mit €/EUR davor oder danach, optional Vorzeichen.
_BETRAG_RE = re.compile(r"(?P<vz>[-−–+]?)\s*(?:€|EUR)?\s*(?P<zahl>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<cent>\d{2}))?"
                        r"\s*(?:€|EUR)?")


class BeschreibungsFehler(ValueError):
    """Eine Anbieter-Beschreibung ist ungültig."""


@dataclass(frozen=True)
class Artikel:
    name: str
    betrag: int | None  # Cent, None wenn nicht angegeben


@dataclass(frozen=True)
class Erkennung:
    anbieter: str
    art: str
    kennung: str            # z. B. Amazon-Bestellnummer, PayPal-Transaktionscode
    haendler: str
    gesamt: int             # Cent, immer >= 0
    guthaben: int = 0       # Anteil aus Guthaben/Gutschein (Cent, >= 0, <= gesamt)
    bezug: str | None = None  # Verweis auf die ursprüngliche Zahlung bzw. die Bestellung beim Händler
    artikel: tuple[Artikel, ...] = field(default_factory=tuple)

    @property
    def bankanteil(self) -> int:
        return max(0, self.gesamt - self.guthaben)


def betrag_lesen(text: str) -> int | None:
    """Erster Betrag in ``text`` als positive Cent (Vorzeichen wird ignoriert)."""
    m = _BETRAG_RE.search(text)
    if m is None or not (m.group("cent") or re.search(r"€|EUR", m.group(0))):
        return None
    euro = int(m.group("zahl").replace(".", ""))
    return euro * 100 + int(m.group("cent") or 0)


def _zeilen(text: str) -> list[str]:
    return [z.strip() for z in text.replace("\r", "").split("\n") if z.strip()]


def _betrag_nach(zeilen: list[str], rx: re.Pattern) -> int | None:
    """Betrag in der Zeile mit dem Muster (hinter dem Treffer), sonst in der folgenden Zeile."""
    for i, z in enumerate(zeilen):
        m = rx.search(z)
        if not m:
            continue
        rest = z[m.end():]
        wert = betrag_lesen(rest) if rest.strip(" :\t") else None
        if wert is None and i + 1 < len(zeilen):
            wert = betrag_lesen(zeilen[i + 1])
        if wert is not None:
            return wert
    return None


def _betrag_summe_nach(zeilen: list[str], rx: re.Pattern) -> int:
    """Summe der Beträge, die in einer Zeile hinter dem (letzten) Treffer des Musters stehen."""
    summe = 0
    for z in zeilen:
        treffer = list(rx.finditer(z))
        if treffer:
            wert = betrag_lesen(z[treffer[-1].end():])
            if wert is not None:
                summe += wert
    return summe


# ================================================================ Beschreibung lesen und prüfen


def _muster(wert, wo: str) -> re.Pattern:
    if not isinstance(wert, str) or not wert:
        raise BeschreibungsFehler(f"{wo}: Es fehlt ein regulärer Ausdruck.")
    if len(wert) > MAX_MUSTER:
        raise BeschreibungsFehler(f"{wo}: Der Ausdruck ist länger als {MAX_MUSTER} Zeichen.")
    try:
        return re.compile(wert)
    except re.error as e:
        raise BeschreibungsFehler(f"{wo}: Der Ausdruck ist ungültig ({e.msg}).") from None


def _nur(d: dict, erlaubt: set[str], wo: str) -> None:
    if not isinstance(d, dict):
        raise BeschreibungsFehler(f"{wo}: Erwartet wird eine Tabelle.")
    fremd = sorted(set(d) - erlaubt)
    if fremd:
        raise BeschreibungsFehler(f"{wo}: Unbekannte Angabe {', '.join(fremd)}.")


_BEREICHE = ("betreff", "text")


@dataclass(frozen=True)
class Wert:
    """Ein Baustein, der aus einer Mail einen Wert holt (siehe ANBIETER.md, „Bausteine“)."""
    art: str                      # fest | betrag_nach | betrag_summe_nach | text | wenn | kennung
    rx: re.Pattern | None = None
    fest: object = None
    bereich: str = "text"
    saeubern: bool = False


def _wert(d, wo: str, betrag: bool) -> tuple[Wert, ...]:
    """Baustein oder Liste von Bausteinen (der erste mit Ergebnis gilt)."""
    if isinstance(d, list):
        if not d:
            raise BeschreibungsFehler(f"{wo}: Die Liste ist leer.")
        return tuple(w for i, x in enumerate(d) for w in _wert(x, f"{wo}[{i}]", betrag))
    _nur(d, {"fest", "betrag_nach", "betrag_summe_nach", "text", "suche_in", "saeubern", "wenn", "dann", "kennung"}, wo)
    arten = [k for k in ("fest", "betrag_nach", "betrag_summe_nach", "text", "wenn", "kennung") if k in d]
    if len(arten) != 1:
        raise BeschreibungsFehler(f"{wo}: Genau einer der Bausteine fest, betrag_nach, betrag_summe_nach, text, wenn,"
                                  " kennung ist anzugeben.")
    art = arten[0]
    if betrag != (art in ("betrag_nach", "betrag_summe_nach", "wenn") or (art == "fest" and type(d["fest"]) is int)):
        raise BeschreibungsFehler(f"{wo}: Der Baustein {art} passt hier nicht ("
                                  + ("erwartet wird ein Betrag" if betrag else "erwartet wird ein Text") + ").")
    bereich = d.get("suche_in", "text")
    if bereich not in _BEREICHE:
        raise BeschreibungsFehler(f"{wo}: suche_in ist betreff oder text.")
    if art == "fest":
        if betrag and d["fest"] < 0:
            raise BeschreibungsFehler(f"{wo}: Ein fester Betrag ist nicht negativ.")
        if not betrag and not isinstance(d["fest"], str):
            raise BeschreibungsFehler(f"{wo}: fest ist ein Text.")
        return (Wert("fest", fest=d["fest"]),)
    if art == "kennung":
        if d["kennung"] is not True:
            raise BeschreibungsFehler(f"{wo}: kennung = true.")
        return (Wert("kennung"),)
    if art == "wenn":
        if d.get("dann") != "gesamt":
            raise BeschreibungsFehler(f'{wo}: Zu wenn gehört dann = "gesamt".')
        return (Wert("wenn", _muster(d["wenn"], wo), bereich=bereich),)
    rx = _muster(d[art], wo)
    if art == "text" and rx.groups < 1:
        raise BeschreibungsFehler(f"{wo}: Der Ausdruck braucht eine Gruppe (…) für den Wert.")
    return (Wert(art, rx, bereich=bereich, saeubern=d.get("saeubern") is True),)


@dataclass(frozen=True)
class Mailart:
    name: str
    rolle: str
    grund: str | None
    betreff: re.Pattern
    gesamt: tuple[Wert, ...]
    guthaben: tuple[Wert, ...] = ()
    haendler: tuple[Wert, ...] = ()
    bezug: tuple[Wert, ...] = ()
    artikel_zeile: re.Pattern | None = None
    artikel_ausser: re.Pattern | None = None


@dataclass(frozen=True)
class Bank:
    namen: tuple[str, ...]
    kennung: re.Pattern | None = None
    glob: str | None = None
    ohne_leerraum: bool = False
    alle_mails: bool = False      # Kennung in allen Mails suchen, nicht nur in denen des Anbieters
    haendler: re.Pattern | None = None   # Händler im Text der Buchung (Gruppe ``haendler`` oder 1)
    haendler_noetig: bool = False        # ohne Kennung zählt nur eine Buchung, in der der Händler der Mail steht
    tage_vor: int | None = None          # Zeitfenster um das Maildatum; None: Vorgabe des Abgleichs
    tage_nach: int | None = None


@dataclass(frozen=True)
class Anbieter:
    name: str
    titel: str
    absender: re.Pattern
    kennung: re.Pattern
    kennung_in: tuple[str, ...]
    arten: tuple[Mailart, ...]
    bank: Bank
    quelle: str = ""

    @property
    def ausgabe(self) -> Mailart | None:
        """Die Mailart, aus der die erwartete Zahlung entsteht (erste mit Rolle „ausgabe“)."""
        return next((a for a in self.arten if a.rolle == "ausgabe"), None)

    def art(self, name: str) -> Mailart | None:
        return next((a for a in self.arten if a.name == name), None)

    # ---------------------------------------------------------------- Mail lesen

    def gehoert(self, absender: str) -> bool:
        dom = absender.casefold().rsplit("@", 1)[-1].rstrip(">").strip()
        return self.absender.search(dom) is not None

    def lesen(self, betreff: str, text: str) -> Erkennung | None:
        """Mail dieses Anbieters lesen; ``None``, wenn Kennung, Mailart oder Betrag fehlen."""
        betreff, text = betreff[:MAX_TEXT], text[:MAX_TEXT]
        bereiche = {"betreff": betreff, "text": text}
        kennung = None
        for b in self.kennung_in:
            m = self.kennung.search(bereiche[b])
            if m:
                kennung = m.group(1)
                break
        if not kennung:
            return None
        art = next((a for a in self.arten if a.betreff.search(betreff)), None)
        if art is None:
            return None
        zeilen = _zeilen(text)
        gesamt = self._betrag(art.gesamt, bereiche, zeilen, None)
        if gesamt is None:
            return None
        guthaben = self._betrag(art.guthaben, bereiche, zeilen, gesamt) or 0
        haendler = self._text(art.haendler, bereiche, kennung) or self.titel
        return Erkennung(self.name, art.name, kennung, haendler, gesamt, min(guthaben, gesamt),
                         bezug=self._text(art.bezug, bereiche, kennung) or None,
                         artikel=self._artikel(art, zeilen))

    @staticmethod
    def _betrag(werte: tuple[Wert, ...], bereiche: dict, zeilen: list[str], gesamt: int | None) -> int | None:
        for w in werte:
            if w.art == "fest":
                return w.fest
            if w.art == "wenn":
                return gesamt if w.rx.search(bereiche[w.bereich]) else 0
            quelle = zeilen if w.bereich == "text" else _zeilen(bereiche[w.bereich])
            wert = _betrag_nach(quelle, w.rx) if w.art == "betrag_nach" else _betrag_summe_nach(quelle, w.rx)
            if wert is not None:
                return wert
        return None

    @staticmethod
    def _text(werte: tuple[Wert, ...], bereiche: dict, kennung: str) -> str:
        for w in werte:
            if w.art == "fest":
                return w.fest
            if w.art == "kennung":
                return kennung
            m = w.rx.search(bereiche[w.bereich])
            if not m:
                continue
            wert = m.group("wert") if "wert" in w.rx.groupindex else m.group(1)
            wert = wert or ""
            if w.saeubern:
                wert = wert.strip().strip("\"'„“”»«").strip()[:200]
            if wert:
                return wert
        return ""

    @staticmethod
    def _artikel(art: Mailart, zeilen: list[str]) -> tuple[Artikel, ...]:
        if art.artikel_zeile is None:
            return ()
        aus = []
        for z in zeilen:
            m = art.artikel_zeile.match(z)
            if not m:
                continue
            name = m.group("name").strip(" .:-")
            if art.artikel_ausser is not None and art.artikel_ausser.search(name):
                continue
            aus.append(Artikel(name[:200], betrag_lesen(m.group("betrag"))))
        return tuple(aus[:50])

    # ---------------------------------------------------------------- Bankseite

    def haendler_der_buchung(self, text: str | None) -> str | None:
        """Händler, wie ihn die Bankbuchung nennt (``bank.haendler``), sonst None."""
        if self.bank.haendler is None or not text:
            return None
        m = self.bank.haendler.search(text[:MAX_TEXT])
        if not m:
            return None
        wert = m.group("haendler") if "haendler" in self.bank.haendler.groupindex else m.group(1)
        return (wert or "").strip() or None

    def kennungen(self, *texte: str | None, mit_leerraum_variante: bool = True) -> list[str]:
        """Kennungen dieses Anbieters in Bank- oder Mailtexten, in der Reihenfolge des ersten Auftretens. Mit
        ``ohne_leerraum`` wird zusätzlich ohne Leerraum gesucht (Bankzeilen brechen Nummern manchmal um)."""
        aus: list[str] = []
        if self.bank.kennung is None:
            return aus
        for t in texte:
            if not t:
                continue
            t = t[:MAX_TEXT]
            fassungen = (t, re.sub(r"\s+", "", t)) if (self.bank.ohne_leerraum and mit_leerraum_variante) else (t,)
            for fassung in fassungen:
                for m in self.bank.kennung.finditer(fassung):
                    if m.group(0) not in aus:
                        aus.append(m.group(0))
        return aus


# Wörter, die in vielen Firmennamen stehen und deshalb nichts über den Händler sagen
_FUELLWOERTER = frozenset("""gmbh mbh ag kg ug ohg gbr se co ltd limited inc llc sarl sa bv nv oy ab the und and der die
das von fuer für shop store online europe europa deutschland germany international service services com de www net
handel versand vertrieb group gruppe holding""".split())


def _woerter(text: str) -> list[str]:
    return [w for w in re.findall(r"[0-9a-zäöüß]+", text.casefold()) if len(w) >= 3 and w not in _FUELLWOERTER]


def name_in_teilen(name: str | None, text: str | None, bank_haendler: str | None = None) -> bool:
    """Steht der Händlername der Mail in Teilen im Text der Buchung (D-232)? Es genügt ein aussagekräftiges Wort
    des Namens (mindestens 4 Zeichen irgendwo im Text, 3 Zeichen nur als ganzes Wort). Banken kürzen Namen und
    schreiben sie zusammen: Deshalb zählt auch, wenn ein Wort des Händlers aus der Buchung (``bank_haendler``,
    mindestens 5 Zeichen) der Anfang des zusammengeschriebenen Namens ist."""
    if not name or not text:
        return False
    kompakt = re.sub(r"[^0-9a-zäöüß]", "", text.casefold())
    woerter = _woerter(name)
    if not woerter:   # Name nur aus Allerweltswörtern („Shop GmbH“): dann muss er ganz dastehen
        ganz = re.sub(r"[^0-9a-zäöüß]", "", name.casefold())
        return len(ganz) >= 4 and ganz in kompakt
    ganze = set(_woerter(text))
    if any((len(w) >= 4 and w in kompakt) or w in ganze for w in woerter):
        return True
    name_kompakt = "".join(re.findall(r"[0-9a-zäöüß]+", (name or "").casefold()))
    return any(len(w) >= 5 and name_kompakt.startswith(w) for w in _woerter(bank_haendler or ""))


def _art(d, wo: str) -> Mailart:
    _nur(d, {"name", "rolle", "grund", "betreff", "gesamt", "guthaben", "haendler", "bezug", "artikel"}, wo)
    name = d.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,29}", name):
        raise BeschreibungsFehler(f"{wo}: name besteht aus Kleinbuchstaben, Ziffern und _ (höchstens 30 Zeichen).")
    if d.get("rolle") not in ROLLEN:
        raise BeschreibungsFehler(f"{wo}: rolle ist eine von {', '.join(ROLLEN)}.")
    grund = d.get("grund")
    if d["rolle"] == "ausgabe":
        if grund not in GRUENDE:
            raise BeschreibungsFehler(f"{wo}: Zur Rolle ausgabe gehört grund ({' oder '.join(GRUENDE)}).")
    elif grund is not None:
        raise BeschreibungsFehler(f"{wo}: grund gibt es nur bei der Rolle ausgabe.")
    if "gesamt" not in d:
        raise BeschreibungsFehler(f"{wo}: gesamt fehlt.")
    zeile = ausser = None
    if "artikel" in d:
        _nur(d["artikel"], {"zeile", "ausser"}, f"{wo}.artikel")
        zeile = _muster(d["artikel"].get("zeile"), f"{wo}.artikel.zeile")
        if not {"name", "betrag"} <= set(zeile.groupindex):
            raise BeschreibungsFehler(f"{wo}.artikel.zeile: Es braucht die Gruppen (?P<name>…) und (?P<betrag>…).")
        if "ausser" in d["artikel"]:
            ausser = _muster(d["artikel"]["ausser"], f"{wo}.artikel.ausser")
    return Mailart(name, d["rolle"], grund, _muster(d.get("betreff"), f"{wo}.betreff"),
                   _wert(d["gesamt"], f"{wo}.gesamt", True),
                   _wert(d["guthaben"], f"{wo}.guthaben", True) if "guthaben" in d else (),
                   _wert(d["haendler"], f"{wo}.haendler", False) if "haendler" in d else (),
                   _wert(d["bezug"], f"{wo}.bezug", False) if "bezug" in d else (),
                   zeile, ausser)


def aus_beschreibung(d: dict, quelle: str = "") -> Anbieter:
    """Geprüfter Anbieter aus einer gelesenen Beschreibung; ``BeschreibungsFehler`` mit der fehlerhaften Stelle."""
    _nur(d, {"name", "titel", "absender", "kennung", "art", "bank"}, "Beschreibung")
    name = d.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,29}", name):
        raise BeschreibungsFehler("name besteht aus Kleinbuchstaben, Ziffern und _ (höchstens 30 Zeichen).")
    titel = d.get("titel")
    if not isinstance(titel, str) or not titel.strip() or len(titel) > 200:
        raise BeschreibungsFehler("titel fehlt (höchstens 200 Zeichen).")
    kennung = d.get("kennung")
    _nur(kennung if kennung is not None else {}, {"muster", "suche_in"}, "kennung")
    rx = _muster((kennung or {}).get("muster"), "kennung.muster")
    if rx.groups < 1:
        raise BeschreibungsFehler("kennung.muster: Der Ausdruck braucht eine Gruppe (…) für die Kennung.")
    bereiche = (kennung or {}).get("suche_in", ["text"])
    if not isinstance(bereiche, list) or not bereiche or any(b not in _BEREICHE for b in bereiche):
        raise BeschreibungsFehler("kennung.suche_in: Liste aus betreff und text.")
    arten = d.get("art")
    if not isinstance(arten, list) or not arten:
        raise BeschreibungsFehler("Es braucht mindestens eine Mailart ([[art]]).")
    gelesen = tuple(_art(a, f"art[{i}]") for i, a in enumerate(arten))
    if len({a.name for a in gelesen}) != len(gelesen):
        raise BeschreibungsFehler("Die Namen der Mailarten müssen verschieden sein.")
    if any(a.rolle != "ausgabe" for a in gelesen) and not any(a.rolle == "ausgabe" for a in gelesen):
        raise BeschreibungsFehler("Erstattung und Storno brauchen eine Mailart mit der Rolle ausgabe.")
    b = d.get("bank", {})
    _nur(b, {"namen", "kennung", "glob", "ohne_leerraum", "alle_mails", "haendler", "haendler_noetig", "tage_vor",
             "tage_nach"}, "bank")
    for feld in ("tage_vor", "tage_nach"):
        if feld in b and (type(b[feld]) is not int or not 0 <= b[feld] <= 366):
            raise BeschreibungsFehler(f"bank.{feld}: ganze Zahl von 0 bis 366.")
    haendler = _muster(b["haendler"], "bank.haendler") if "haendler" in b else None
    if haendler is not None and haendler.groups < 1:
        raise BeschreibungsFehler("bank.haendler: Der Ausdruck braucht eine Gruppe (…) für den Händler.")
    namen = b.get("namen", [name])
    if not isinstance(namen, list) or not namen or any(not isinstance(n, str) or len(n.strip()) < 3 for n in namen):
        raise BeschreibungsFehler("bank.namen: Liste von Namen mit mindestens 3 Zeichen.")
    glob = b.get("glob")
    if glob is not None and (not isinstance(glob, str) or not glob or len(glob) > MAX_MUSTER):
        raise BeschreibungsFehler("bank.glob: Text (SQLite-GLOB) mit höchstens 500 Zeichen.")
    bank = Bank(tuple(n.strip().casefold() for n in namen),
                _muster(b["kennung"], "bank.kennung") if "kennung" in b else None, glob, b.get("ohne_leerraum") is True,
                b.get("alle_mails") is True, haendler, b.get("haendler_noetig") is True, b.get("tage_vor"),
                b.get("tage_nach"))
    return Anbieter(name, titel.strip(), _muster(d.get("absender"), "absender"), rx, tuple(bereiche), gelesen, bank,
                    quelle)


def aus_toml(text: str, quelle: str = "") -> Anbieter:
    try:
        return aus_beschreibung(tomllib.loads(text), quelle)
    except tomllib.TOMLDecodeError as e:
        raise BeschreibungsFehler(f"Die Datei ist kein gültiges TOML ({e}).") from None


# ================================================================ Register


_eingebaut: tuple[Anbieter, ...] | None = None
_zusatz: dict[str, tuple[tuple, tuple[Anbieter, ...]]] = {}


def eingebaute() -> tuple[Anbieter, ...]:
    global _eingebaut
    if _eingebaut is None:
        paket = resources.files(__package__)
        _eingebaut = tuple(aus_toml((paket / f"{n}.toml").read_text(encoding="utf-8"), f"eingebaut:{n}")
                           for n in EINGEBAUT)
    return _eingebaut


def alle(verzeichnis: str | Path | None = None) -> tuple[Anbieter, ...]:
    """Mitgelieferte Anbieter, danach die aus ``verzeichnis`` (nach Dateiname). Eine Zusatzdatei mit dem Namen
    eines mitgelieferten Anbieters ersetzt ihn an seiner Stelle. Die Reihenfolge entscheidet bei Mails, deren
    Absender zu mehreren Anbietern passt."""
    liste = list(eingebaute())
    if not verzeichnis:
        return tuple(liste)
    ordner = Path(verzeichnis)
    try:
        dateien = sorted(p for p in ordner.glob("*.toml") if p.is_file())
        stand = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in dateien)
    except OSError:
        return tuple(liste)
    gemerkt = _zusatz.get(str(ordner))
    if gemerkt is None or gemerkt[0] != stand:
        gelesen = []
        for p in dateien:
            try:
                gelesen.append(aus_toml(p.read_text(encoding="utf-8"), str(p)))
            except (BeschreibungsFehler, OSError, UnicodeDecodeError) as e:
                log.warning("Anbieter-Beschreibung %s wird übergangen: %s", p.name, e)
        gemerkt = (stand, tuple(gelesen))
        _zusatz[str(ordner)] = gemerkt
    for a in gemerkt[1]:
        stelle = next((i for i, x in enumerate(liste) if x.name == a.name), None)
        if stelle is None:
            liste.append(a)
        else:
            liste[stelle] = a
    return tuple(liste)


_verzeichnis: str | None = None


def einrichten(verzeichnis: str | Path | None) -> None:
    """Verzeichnis der Zusatzbeschreibungen dieses Prozesses festlegen (App-Start, Abgleichsläufe)."""
    global _verzeichnis
    _verzeichnis = str(verzeichnis) if verzeichnis else None


def aktive() -> tuple[Anbieter, ...]:
    """Mitgelieferte und zugeladene Anbieter; geänderte Dateien werden beim nächsten Aufruf neu gelesen."""
    return alle(_verzeichnis)


def nach_name(name: str | None, anbieter: tuple[Anbieter, ...] | None = None) -> Anbieter | None:
    return next((a for a in (anbieter if anbieter is not None else aktive()) if a.name == name), None)


def erkennen(absender: str, betreff: str, text: str,
             anbieter: tuple[Anbieter, ...] | None = None) -> Erkennung | None:
    """Erkennt eine Mail eines bekannten Anbieters; ``None`` wenn nicht eindeutig."""
    for a in (anbieter if anbieter is not None else aktive()):
        if a.gehoert(absender or ""):
            try:
                return a.lesen(betreff or "", text or "")
            except (ValueError, IndexError):
                return None
    return None


def signatur(anbieter: tuple[Anbieter, ...]) -> str:
    """Kurzfassung der Bank-Kennungsmuster; ändert sie sich, werden gemerkte Kennungen der Mails neu gesucht."""
    return "|".join(f"{a.name}:{a.bank.kennung.pattern if a.bank.kennung else ''}:{int(a.bank.alle_mails)}"
                    f":{a.absender.pattern}" for a in anbieter)
