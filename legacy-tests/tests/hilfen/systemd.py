"""Statischer Leser für systemd-Unit-Dateien und Umgebungsdateien (betrieb.md 3, 4) – ohne systemd."""

from __future__ import annotations

import re

_ABSCHNITT = re.compile(r"^\[([A-Za-z]+)\]$")


class Unit:
    """Abschnitte → Liste von (Schlüssel, Wert) in Dateireihenfolge."""

    def __init__(self, text: str) -> None:
        self.abschnitte: dict[str, list[tuple[str, str]]] = {}
        aktuell: list[tuple[str, str]] | None = None
        for nr, zeile in enumerate(text.splitlines(), start=1):
            z = zeile.strip()
            if not z or z[0] in "#;":
                continue
            assert not z.endswith("\\"), f"Zeile {nr}: Fortsetzungszeilen sind nicht vorgesehen"
            m = _ABSCHNITT.match(z)
            if m:
                assert m[1] not in self.abschnitte, f"Abschnitt [{m[1]}] doppelt"
                aktuell = self.abschnitte.setdefault(m[1], [])
                continue
            assert aktuell is not None, f"Zeile {nr} außerhalb eines Abschnitts: {zeile!r}"
            assert "=" in z, f"Zeile {nr} ohne '=': {zeile!r}"
            k, v = z.split("=", 1)
            aktuell.append((k.strip(), v.strip()))

    def werte(self, abschnitt: str, schluessel: str) -> list[str]:
        return [v for k, v in self.abschnitte.get(abschnitt, []) if k == schluessel]

    def wert(self, abschnitt: str, schluessel: str) -> str | None:
        w = self.werte(abschnitt, schluessel)
        assert len(w) <= 1, f"[{abschnitt}] {schluessel} mehrfach: {w}"
        return w[0] if w else None

    def schluessel(self, abschnitt: str) -> list[str]:
        return [k for k, _ in self.abschnitte.get(abschnitt, [])]


def umgebungsdatei(text: str) -> tuple[dict[str, str], list[str]]:
    """Liefert (Variablen, Kommentarzeilen) einer EnvironmentFile."""
    werte: dict[str, str] = {}
    kommentare: list[str] = []
    for nr, zeile in enumerate(text.splitlines(), start=1):
        z = zeile.strip()
        if not z:
            continue
        if z.startswith("#"):
            kommentare.append(z)
            continue
        assert "=" in z, f"Zeile {nr} ohne '=': {zeile!r}"
        k, v = z.split("=", 1)
        assert re.fullmatch(r"[A-Z_][A-Z0-9_]*", k), f"Zeile {nr}: ungültiger Name {k!r}"
        assert k not in werte, f"{k} doppelt"
        assert not (v.startswith(("'", '"')) or " " in v), f"{k}: Wert ohne Anführungszeichen und Leerzeichen"
        werte[k] = v
    return werte, kommentare


GEHEIM = ("PIN", "PASSWORT", "PASSWORD", "TOKEN", "SECRET", "GEHEIM", "KEY", "SCHLUESSEL")


def geheimer_name(name: str) -> bool:
    """betrieb.md 3: Name nach der Geheimnisregel (außer ``…_QUELLE``/``…_DATEI``)."""
    n = name.upper()
    return any(g in n for g in GEHEIM) and not n.endswith(("_QUELLE", "_DATEI"))
