"""Strenge Validierung von Anfragekörpern und Query-Parametern.

Bewusst ohne Pydantic-Lax-Modus: Gleitkommazahlen (auch ``12.0``),
Zeichenketten und Booleans an Ganzzahlstellen sind ungültig; unbekannte Felder
ebenfalls (``additionalProperties: false``).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from typing import Any

BETRAG_MAX = 999_999_999_999
INT64_MAX = 2**63 - 1

_DATUM = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_GANZZAHL = re.compile(r"^[+-]?[0-9]+$")

KONTOARTEN = ("girokonto", "sparkonto", "kreditkonto", "aufwand", "ertrag", "eigenkapital")
STATUS = ("importiert", "vorlaeufig", "bestaetigt", "abgeglichen")


class ApiFehler(Exception):
    """Fehlerantwort der REST-API: ``{"fehler": {code, meldung, details}}``."""

    def __init__(self, status: int, code: str, meldung: str, details: Any = None) -> None:
        super().__init__(meldung)
        self.status = status
        self.code = code
        self.meldung = meldung
        self.details = details


class Validierungsfehler(ApiFehler):
    def __init__(self, fehler: list[dict]) -> None:
        super().__init__(422, "validierung", "Die Anfrage ist ungültig.", fehler)


def fehler_eintrag(ort: list, meldung: str) -> dict:
    return {"ort": list(ort), "meldung": meldung}


# ----------------------------------------------------------- Feldtypen


@dataclass
class Feld:
    typ: str  # str, int, betrag, bool, datum, enum, int_liste, splits
    pflicht: bool = False
    nullbar: bool = False
    min_len: int | None = None
    max_len: int | None = None
    werte: tuple[str, ...] = ()
    eindeutig: bool = False
    min_items: int | None = None
    max_items: int | None = None
    strip: bool = False  # Namen: Ränder entfernen, danach nicht leer
    unter: dict[str, "Feld"] = field(default_factory=dict)


INT64 = 2 ** 63 - 1  # sicherheit.md 7.4: übergroße Ganzzahlen → 422


def ist_int(x: Any) -> bool:
    return type(x) is int


def datum_gueltig(s: Any) -> bool:
    if not isinstance(s, str) or not _DATUM.match(s):
        return False
    try:
        dt.date.fromisoformat(s)
    except ValueError:
        return False
    return True


def _pruefe_wert(f: Feld, wert: Any, ort: list, fehler: list[dict]) -> Any:
    if wert is None:
        if f.nullbar:
            return None
        fehler.append(fehler_eintrag(ort, "Wert darf nicht null sein."))
        return None
    t = f.typ
    if t == "str":
        if not isinstance(wert, str):
            fehler.append(fehler_eintrag(ort, "Zeichenkette erwartet."))
            return None
        if f.strip:
            wert = wert.strip()
        if f.min_len is not None and len(wert) < f.min_len:
            fehler.append(fehler_eintrag(ort, f"Mindestens {f.min_len} Zeichen erforderlich."))
        if f.max_len is not None and len(wert) > f.max_len:
            fehler.append(fehler_eintrag(ort, f"Höchstens {f.max_len} Zeichen erlaubt."))
        return wert
    if t == "int":
        if not ist_int(wert):
            fehler.append(fehler_eintrag(ort, "Ganzzahl erwartet."))
        elif not -INT64 <= wert <= INT64:
            fehler.append(fehler_eintrag(ort, "Ganzzahl außerhalb des zulässigen Bereichs."))
        return wert
    if t == "betrag":
        if not ist_int(wert):
            fehler.append(fehler_eintrag(ort, "Betrag muss eine Ganzzahl in Cent sein."))
        elif not -BETRAG_MAX <= wert <= BETRAG_MAX:
            fehler.append(fehler_eintrag(ort, "Betrag liegt außerhalb des zulässigen Bereichs."))
        return wert
    if t == "bool":
        if not isinstance(wert, bool):
            fehler.append(fehler_eintrag(ort, "Wahrheitswert erwartet."))
        return wert
    if t == "datum":
        if not datum_gueltig(wert):
            fehler.append(fehler_eintrag(ort, "Datum im Format YYYY-MM-DD erwartet."))
        return wert
    if t == "enum":
        if not isinstance(wert, str) or wert not in f.werte:
            fehler.append(fehler_eintrag(ort, f"Erlaubt sind: {', '.join(f.werte)}."))
        return wert
    if t == "int_liste":
        if not isinstance(wert, list):
            fehler.append(fehler_eintrag(ort, "Liste von Ganzzahlen erwartet."))
            return None
        for i, x in enumerate(wert):
            if not ist_int(x):
                fehler.append(fehler_eintrag(ort + [i], "Ganzzahl erwartet."))
        if f.min_items is not None and len(wert) < f.min_items:
            fehler.append(fehler_eintrag(ort, f"Mindestens {f.min_items} Einträge erforderlich."))
        if f.max_items is not None and len(wert) > f.max_items:
            fehler.append(fehler_eintrag(ort, f"Höchstens {f.max_items} Einträge erlaubt."))
        if f.eindeutig and all(ist_int(x) for x in wert) and len(set(wert)) != len(wert):
            fehler.append(fehler_eintrag(ort, "Einträge müssen eindeutig sein."))
        return wert
    if t == "str_liste":
        if not isinstance(wert, list):
            fehler.append(fehler_eintrag(ort, "Liste von Zeichenketten erwartet."))
            return None
        aus = []
        for i, x in enumerate(wert):
            if not isinstance(x, str):
                fehler.append(fehler_eintrag(ort + [i], "Zeichenkette erwartet."))
                continue
            x = x.strip() if f.strip else x
            if f.min_len is not None and len(x) < f.min_len:
                fehler.append(fehler_eintrag(ort + [i], f"Mindestens {f.min_len} Zeichen erforderlich."))
            if f.max_len is not None and len(x) > f.max_len:
                fehler.append(fehler_eintrag(ort + [i], f"Höchstens {f.max_len} Zeichen erlaubt."))
            aus.append(x)
        if f.max_items is not None and len(wert) > f.max_items:
            fehler.append(fehler_eintrag(ort, f"Höchstens {f.max_items} Einträge erlaubt."))
        return aus
    if t == "objekte":
        if not isinstance(wert, list):
            fehler.append(fehler_eintrag(ort, "Liste erwartet."))
            return None
        aus = []
        for i, x in enumerate(wert):
            aus.append(pruefe_objekt(x, f.unter, ort + [i], fehler))
        return aus
    raise AssertionError(t)  # pragma: no cover


def pruefe_objekt(daten: Any, schema: dict[str, Feld], ort: list, fehler: list[dict]) -> dict:
    if not isinstance(daten, dict):
        fehler.append(fehler_eintrag(ort, "JSON-Objekt erwartet."))
        return {}
    aus: dict[str, Any] = {}
    for name in daten:
        if name not in schema:
            fehler.append(fehler_eintrag(ort + [name], "Unbekanntes Feld."))
    for name, f in schema.items():
        if name not in daten:
            if f.pflicht:
                fehler.append(fehler_eintrag(ort + [name], "Pflichtfeld fehlt."))
            continue
        aus[name] = _pruefe_wert(f, daten[name], ort + [name], fehler)
    return aus


def json_koerper(roh: bytes) -> Any:
    try:
        return json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Validierungsfehler([fehler_eintrag(["body"], "Kein gültiges JSON.")]) from None


def pruefe_koerper(roh: bytes, schema: dict[str, Feld]) -> dict:
    daten = json_koerper(roh)
    fehler: list[dict] = []
    aus = pruefe_objekt(daten, schema, ["body"], fehler)
    if fehler:
        raise Validierungsfehler(fehler)
    return aus


# -------------------------------------------------------- Query-Parameter


class Query:
    """Liest Query-Parameter streng; sammelt Fehler."""

    def __init__(self, params) -> None:
        self.params = params
        self.fehler: list[dict] = []

    def _ort(self, name: str) -> list:
        return ["query", name]

    def ganzzahl(self, name: str, minimum: int | None = None, maximum: int | None = None) -> int | None:
        if name not in self.params:
            return None
        return self._ganz(name, self.params.get(name), minimum, maximum)

    def _ganz(self, name, text, minimum, maximum):
        if not _GANZZAHL.match(text or ""):
            self.fehler.append(fehler_eintrag(self._ort(name), "Ganzzahl erwartet."))
            return None
        wert = int(text)
        if minimum is not None and wert < minimum:
            self.fehler.append(fehler_eintrag(self._ort(name), f"Mindestens {minimum}."))
        if maximum is not None and wert > maximum:
            self.fehler.append(fehler_eintrag(self._ort(name), f"Höchstens {maximum}."))
        return wert

    def ganzzahlen(self, name: str) -> list[int]:
        aus = []
        for text in self.params.getlist(name):
            w = self._ganz(name, text, None, None)
            if w is not None:
                aus.append(w)
        return aus

    def wahrheitswert(self, name: str) -> bool | None:
        if name not in self.params:
            return None
        text = self.params.get(name).strip().lower()
        if text in ("true", "1"):
            return True
        if text in ("false", "0"):
            return False
        self.fehler.append(fehler_eintrag(self._ort(name), "true oder false erwartet."))
        return None

    def datum(self, name: str) -> str | None:
        if name not in self.params:
            return None
        text = self.params.get(name)
        if not datum_gueltig(text):
            self.fehler.append(fehler_eintrag(self._ort(name), "Datum im Format YYYY-MM-DD erwartet."))
            return None
        return text

    def text(self, name: str, min_len: int = 0) -> str | None:
        if name not in self.params:
            return None
        text = self.params.get(name)
        if len(text) < min_len:
            self.fehler.append(fehler_eintrag(self._ort(name), f"Mindestens {min_len} Zeichen."))
            return None
        return text

    def auswahl(self, name: str, werte: tuple[str, ...]) -> str | None:
        if name not in self.params:
            return None
        text = self.params.get(name)
        if text not in werte:
            self.fehler.append(fehler_eintrag(self._ort(name), f"Erlaubt sind: {', '.join(werte)}."))
            return None
        return text

    def auswahlen(self, name: str, werte: tuple[str, ...]) -> list[str]:
        aus = []
        for text in self.params.getlist(name):
            if text not in werte:
                self.fehler.append(fehler_eintrag(self._ort(name), f"Erlaubt sind: {', '.join(werte)}."))
            else:
                aus.append(text)
        return aus

    def fehler_melden(self, ort: str, meldung: str) -> None:
        self.fehler.append(fehler_eintrag(self._ort(ort), meldung))

    def pruefen(self) -> None:
        if self.fehler:
            raise Validierungsfehler(self.fehler)
