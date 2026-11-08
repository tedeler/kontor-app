"""Ergebnis eines Imports (python-api.md Abschnitt 5, datenmodell.md 10.5)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields

ZAEHLFELDER = (
    "konten_neu", "konten_vorhanden", "kategorien_neu", "kategorien_vorhanden",
    "empfaenger_neu", "empfaenger_vorhanden", "tags_neu", "tags_vorhanden",
    "buchungen_neu", "buchungen_vorhanden", "buchungen_zusammengefuehrt",
    "buchungen_zur_pruefung", "buchungen_uebersprungen", "splits_neu",
)


@dataclass(frozen=True)
class ImportMeldung:
    code: str
    meldung: str
    referenz: str | None = None

    def als_dict(self) -> dict[str, object]:
        return {"code": self.code, "meldung": self.meldung, "referenz": self.referenz}


@dataclass(frozen=True)
class ImportErgebnis:
    erfolgreich: bool
    format: str | None
    konten_neu: int = 0
    konten_vorhanden: int = 0
    kategorien_neu: int = 0
    kategorien_vorhanden: int = 0
    empfaenger_neu: int = 0
    empfaenger_vorhanden: int = 0
    tags_neu: int = 0
    tags_vorhanden: int = 0
    buchungen_neu: int = 0
    buchungen_vorhanden: int = 0
    buchungen_zusammengefuehrt: int = 0
    buchungen_zur_pruefung: int = 0
    buchungen_uebersprungen: int = 0
    splits_neu: int = 0
    warnungen: tuple[ImportMeldung, ...] = field(default_factory=tuple)
    fehler: tuple[ImportMeldung, ...] = field(default_factory=tuple)
    import_id: int | None = None

    def als_dict(self) -> dict[str, object]:
        aus: dict[str, object] = {}
        for f in fields(self):
            wert = getattr(self, f.name)
            if f.name in ("warnungen", "fehler"):
                aus[f.name] = [m.als_dict() for m in wert]
            else:
                aus[f.name] = wert
        return aus


__all__ = ["ImportErgebnis", "ImportMeldung", "ZAEHLFELDER"]
