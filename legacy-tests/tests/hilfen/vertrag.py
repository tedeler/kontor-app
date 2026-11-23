"""Prüft HTTP-Antworten gegen spec/api/openapi.yaml (eigene Validierung mit jsonschema).

OpenAPI 3.1 verwendet JSON Schema 2020-12; Schemas werden daher direkt mit
``jsonschema.Draft202012Validator`` geprüft. ``$ref`` werden relativ zum
gesamten OpenAPI-Dokument aufgelöst.
"""

from __future__ import annotations

import functools
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from .pfade import OPENAPI

_FORMATE = FormatChecker()

#: Erweiterungslauf (E-124): Mit ``KONTOR_TESTS_ZUSATZFELDER=1`` bekommt jedes JSON-Objekt einer Antwort,
#: dessen Schema feste Eigenschaften hat (keine Abbildung wie ``anzahl``), nach der Schemaprüfung ein
#: zusätzliches optionales Feld. So zeigt sich, ob ein Test spätere optionale Felder (E-029) verbieten würde.
ZUSATZFELD = "zusatz_spaeter_e029"


def zusatzfelder_aktiv() -> bool:
    return os.environ.get("KONTOR_TESTS_ZUSATZFELDER", "").strip().lower() in ("1", "true", "ja", "yes", "on")


def _zeiger(teile: list[str]) -> str:
    return "#/" + "/".join(t.replace("~", "~0").replace("/", "~1") for t in teile)


@dataclass(frozen=True)
class Operation:
    vorlage: str
    methode: str
    daten: dict


class Vertrag:
    def __init__(self, pfad=OPENAPI) -> None:
        with open(pfad, encoding="utf-8") as f:
            self.dok: dict = yaml.safe_load(f)
        self._muster: list[tuple[re.Pattern, str]] = []
        self._zweige: dict[int, Draft202012Validator] = {}
        for vorlage in self.dok["paths"]:
            rx = "^" + re.sub(r"\{[^/]+\}", r"[^/]+", re.escape(vorlage).replace(r"\{", "{").replace(r"\}", "}")) + "$"
            self._muster.append((re.compile(rx), vorlage))
        # feste Pfade vor Vorlagen mit Parametern bevorzugen
        self._muster.sort(key=lambda m: m[1].count("{"))

    def vorlage(self, pfad: str) -> str | None:
        for rx, v in self._muster:
            if rx.match(pfad):
                return v
        return None

    def operation(self, methode: str, pfad: str) -> Operation | None:
        v = self.vorlage(pfad)
        if v is None:
            return None
        op = self.dok["paths"][v].get(methode.lower())
        return Operation(v, methode.lower(), op) if op else None

    @functools.lru_cache(maxsize=None)
    def _validator(self, zeiger: str) -> Draft202012Validator:
        schema = dict(self.dok)
        schema["$ref"] = zeiger
        return Draft202012Validator(schema, format_checker=_FORMATE)

    def schema_validator(self, name: str) -> Draft202012Validator:
        return self._validator(_zeiger(["components", "schemas", name]))

    def _aufloesen(self, obj: dict, teile: list[str]) -> tuple[dict, list[str]]:
        while "$ref" in obj:
            ref = obj["$ref"]
            assert ref.startswith("#/")
            teile = [t.replace("~1", "/").replace("~0", "~") for t in ref[2:].split("/")]
            obj = self.dok
            for t in teile:
                obj = obj[t]
        return obj, teile

    def pruefe_antwort(self, methode: str, pfad: str, status: int, inhalt: bytes,
                       content_type: str | None) -> Any:
        """Validiert eine Antwort; liefert das geparste JSON (oder None)."""
        op = self.operation(methode, pfad)
        if op is None:
            # unbekannter Pfad/Methode: muss ein Fehlerobjekt sein
            assert status in (404, 405) or str(status) in self.dok.get("x-allgemeine-antworten", {}), (
                f"{methode} {pfad}: nicht spezifizierter Endpunkt muss 404/405 (oder 401/403/413/429, E-127) liefern, "
                f"nicht {status}")
            daten = _json(inhalt, content_type, methode, pfad, status)
            fehler = list(self.schema_validator("Fehler").iter_errors(daten))
            assert not fehler, f"{methode} {pfad} → {status}: kein gültiges Fehlerobjekt: {fehler[0].message}"
            return daten
        antworten = op.daten["responses"]
        schl = str(status)
        if schl not in antworten and schl in self.dok.get("x-allgemeine-antworten", {}):
            # für jede Operation zulässige Antworten (M7, E-127)
            antworten = self.dok["x-allgemeine-antworten"]
            teile_basis = ["x-allgemeine-antworten"]
        else:
            teile_basis = ["paths", op.vorlage, op.methode, "responses"]
        assert schl in antworten, (
            f"{methode.upper()} {op.vorlage}: Statuscode {status} ist nicht spezifiziert "
            f"(erlaubt: {sorted(antworten)}). Antwort: {inhalt[:500]!r}")
        teile = teile_basis + [schl]
        antw, teile = self._aufloesen(antworten[schl], teile)
        inhaltsarten = antw.get("content")
        if not inhaltsarten:
            assert inhalt in (b"", b"null"), f"{methode} {pfad} → {status}: Körper muss leer sein: {inhalt[:200]!r}"
            return None
        if "application/json" not in inhaltsarten:
            # Nicht-JSON-Antwort (z. B. image/* für TAN-Bilder, E-042): nur der Inhaltstyp wird geprüft.
            art = (content_type or "").split(";")[0].strip()
            assert any(_passt(art, muster) for muster in inhaltsarten), (
                f"{methode} {pfad} → {status}: Content-Type {content_type!r} nicht erlaubt (erlaubt: "
                f"{sorted(inhaltsarten)})")
            return None
        daten = _json(inhalt, content_type, methode, pfad, status)
        zeiger = _zeiger(teile + ["content", "application/json", "schema"])
        fehler = sorted(self._validator(zeiger).iter_errors(daten), key=lambda e: list(e.absolute_path))
        if fehler:
            e = fehler[0]
            raise AssertionError(
                f"{methode.upper()} {pfad} → {status}: Antwort verletzt das Schema an "
                f"{'/'.join(map(str, e.absolute_path)) or '(Wurzel)'}: {e.message}\n"
                f"Antwort: {json.dumps(daten, ensure_ascii=False)[:1500]}")
        return self.markiere(inhaltsarten["application/json"]["schema"], daten, zusatz=zusatzfelder_aktiv())

    # ------------------------------------------- Antwortobjekte und Erweiterungslauf (E-124)
    def _gueltig(self, schema: dict, daten: Any) -> bool:
        v = self._zweige.get(id(schema))
        if v is None:
            v = self._zweige[id(schema)] = Draft202012Validator({**self.dok, **schema}, format_checker=_FORMATE)
        return v.is_valid(daten)

    def _grob(self, schema: dict, daten: Any) -> bool:
        """Schnelle Vorprüfung eines oneOf/anyOf-Zweigs (Typ, Pflicht- und erlaubte Felder)."""
        schema, _ = self._aufloesen(schema, [])
        typ = schema.get("type")
        if typ is not None:
            typen = typ if isinstance(typ, list) else [typ]
            if not any(_typ_passt(t, daten) for t in typen):
                return False
        if isinstance(daten, dict) and "properties" in schema:
            if not set(schema.get("required", [])) <= set(daten):
                return False
            if schema.get("additionalProperties") is False and not set(daten) <= set(schema["properties"]):
                return False
        for art in ("oneOf", "anyOf"):
            if art in schema and not any(self._grob(z, daten) for z in schema[art]):
                return False
        return True

    def _zweig(self, zweige: list[dict], daten: Any) -> dict | None:
        kandidaten = [z for z in zweige if self._grob(z, daten)]
        if len(kandidaten) > 1:
            kandidaten = [z for z in kandidaten if self._gueltig(z, daten)]
        return kandidaten[0] if kandidaten else None

    def markiere(self, schema: dict, daten: Any, *, zusatz: bool = False) -> Any:
        """Wandelt gültige Antwortdaten in :class:`Antwortobjekt`-Strukturen (Objekte mit festen Feldern).

        Mit ``zusatz`` bekommt jedes solche Objekt zusätzlich :data:`ZUSATZFELD` (Erweiterungslauf).
        """
        schema, _ = self._aufloesen(schema, [])
        for art in ("oneOf", "anyOf"):
            if art in schema:
                z = self._zweig(schema[art], daten)
                return daten if z is None else self.markiere(z, daten, zusatz=zusatz)
        teile = [schema] + [self._aufloesen(z, [])[0] for z in schema.get("allOf", [])]
        optional: set[str] = set()
        eigen: dict = {}
        rest = None
        for t in teile:
            eigen.update(t.get("properties") or {})
            optional |= set(t.get("properties") or {}) - set(t.get("required", []))
            if isinstance(t.get("additionalProperties"), dict):
                rest = t["additionalProperties"]
            if isinstance(daten, list) and isinstance(t.get("items"), dict):
                return [self.markiere(t["items"], x, zusatz=zusatz) for x in daten]
        if isinstance(daten, list):
            return daten
        if not isinstance(daten, dict):
            return daten
        aus = {}
        for k, v in daten.items():
            if k in eigen:
                aus[k] = self.markiere(eigen[k], v, zusatz=zusatz)
            elif rest is not None:
                aus[k] = self.markiere(rest, v, zusatz=zusatz)
            else:
                aus[k] = v
        if not eigen:
            return aus
        obj = Antwortobjekt(aus)
        obj.optional = frozenset(optional)
        if zusatz and ZUSATZFELD not in obj:
            obj[ZUSATZFELD] = None
            obj.optional = obj.optional | {ZUSATZFELD}
        return obj


def _typ_passt(typ: str, daten: Any) -> bool:
    return {"object": isinstance(daten, dict), "array": isinstance(daten, list),
            "string": isinstance(daten, str), "null": daten is None, "boolean": isinstance(daten, bool),
            "integer": isinstance(daten, int) and not isinstance(daten, bool),
            "number": isinstance(daten, (int, float)) and not isinstance(daten, bool)}.get(typ, True)


class Antwortobjekt(dict):
    """JSON-Objekt einer Antwort mit festen Feldern laut Schema (E-124).

    Vergleich mit einem gewöhnlichen ``dict`` (Erwartung des Tests): Jedes Feld der Erwartung muss
    vorhanden und gleich sein; zusätzliche Felder der Antwort sind nur erlaubt, wenn das Schema sie als
    optional führt (spätere Meilensteine fügen Felder optional hinzu, E-029). Zwei Antwortobjekte
    (beide von der Anwendung) werden exakt verglichen. Das Schema selbst (``additionalProperties:
    false``) hat die Antwort vorher schon geprüft.
    """

    optional: frozenset = frozenset()
    __hash__ = None  # type: ignore[assignment]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, dict):
            return NotImplemented
        if isinstance(other, Antwortobjekt):
            return dict.__eq__(self, other)
        if not set(other) <= set(self):
            return False
        if not set(self) - set(other) <= self.optional:
            return False
        return all(self[k] == other[k] for k in other)

    def __ne__(self, other: object) -> bool:
        r = self.__eq__(other)
        return r if r is NotImplemented else not r

    def __copy__(self) -> "Antwortobjekt":
        obj = Antwortobjekt(self)
        obj.optional = self.optional
        return obj


def _passt(art: str, muster: str) -> bool:
    if muster.endswith("/*"):
        return art.startswith(muster[:-1]) and len(art) > len(muster) - 1
    return art == muster


def _json(inhalt: bytes, content_type: str | None, methode: str, pfad: str, status: int) -> Any:
    assert content_type and content_type.split(";")[0].strip() == "application/json", (
        f"{methode} {pfad} → {status}: Content-Type muss application/json sein, ist {content_type!r}")
    try:
        return json.loads(inhalt)
    except ValueError as e:  # pragma: no cover - Meldung für Implementierer
        raise AssertionError(f"{methode} {pfad} → {status}: kein JSON: {inhalt[:300]!r}") from e


@functools.lru_cache(maxsize=1)
def vertrag() -> Vertrag:
    return Vertrag()


def ohne(obj: dict, *schluessel: str) -> dict:
    """Kopie ohne die genannten Schlüssel; ein :class:`Antwortobjekt` bleibt eines (E-124)."""
    kopie = {k: v for k, v in obj.items() if k not in schluessel}
    if isinstance(obj, Antwortobjekt):
        aus = Antwortobjekt(kopie)
        aus.optional = obj.optional
        return aus
    return kopie


def pruefe_felder(obj: dict, felder) -> None:
    """Genau diese Felder, zusätzlich nur solche, die das Schema als optional führt (E-029, E-124)."""
    felder = set(felder)
    assert felder <= set(obj), f"fehlende Felder: {sorted(felder - set(obj))}"
    rest = set(obj) - felder
    erlaubt = obj.optional if isinstance(obj, Antwortobjekt) else frozenset()
    assert rest <= erlaubt, f"Felder außerhalb des Vertrags: {sorted(rest - erlaubt)}"


def ohne_zusatzfeld(daten: Any) -> Any:
    """Entfernt das künstliche Feld des Erweiterungslaufs (nur dort vorhanden), z. B. vor Prüfsummen über
    REST-Daten, die die Anwendung selbst ebenso berechnet (sicherung.md 3.3)."""
    if isinstance(daten, dict):
        return {k: ohne_zusatzfeld(v) for k, v in daten.items() if k != ZUSATZFELD}
    if isinstance(daten, list):
        return [ohne_zusatzfeld(x) for x in daten]
    return daten
