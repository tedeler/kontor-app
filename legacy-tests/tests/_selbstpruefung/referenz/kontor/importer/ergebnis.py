"""ImportErgebnis und ImportMeldung laut python-api.md 5 (Wegwerf-Referenz)."""

from __future__ import annotations

from dataclasses import dataclass

ZAEHLER = ["konten_neu", "konten_vorhanden", "kategorien_neu", "kategorien_vorhanden", "empfaenger_neu",
           "empfaenger_vorhanden", "tags_neu", "tags_vorhanden", "buchungen_neu", "buchungen_vorhanden",
           "buchungen_zusammengefuehrt", "buchungen_zur_pruefung", "buchungen_uebersprungen", "splits_neu"]


@dataclass(frozen=True)
class ImportMeldung:
    code: str
    meldung: str
    referenz: str | None = None


@dataclass(frozen=True)
class ImportErgebnis:
    erfolgreich: bool
    format: str | None
    konten_neu: int
    konten_vorhanden: int
    kategorien_neu: int
    kategorien_vorhanden: int
    empfaenger_neu: int
    empfaenger_vorhanden: int
    tags_neu: int
    tags_vorhanden: int
    buchungen_neu: int
    buchungen_vorhanden: int
    buchungen_zusammengefuehrt: int
    buchungen_zur_pruefung: int
    buchungen_uebersprungen: int
    splits_neu: int
    warnungen: tuple[ImportMeldung, ...]
    fehler: tuple[ImportMeldung, ...]
    import_id: int | None

    def als_dict(self) -> dict[str, object]:
        d: dict[str, object] = {"erfolgreich": self.erfolgreich, "format": self.format}
        d.update({z: getattr(self, z) for z in ZAEHLER})
        d["warnungen"] = [{"code": m.code, "meldung": m.meldung, "referenz": m.referenz} for m in self.warnungen]
        d["fehler"] = [{"code": m.code, "meldung": m.meldung, "referenz": m.referenz} for m in self.fehler]
        d["import_id"] = self.import_id
        return d
