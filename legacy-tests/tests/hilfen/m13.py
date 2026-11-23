"""Hilfen für Meilenstein-13-Tests (Versionsnummer und About-Fenster, ``version.md``, ``oberflaeche.md`` 24).

Keine Versionsnummer ist hier fest eingetragen: Die Version ändert sich mit jedem Release; geprüft werden nur
das Schema (``version.md`` 1.1) und die Gleichheit über alle Quellen (1.4).
"""

from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

#: version.md 1.1 (E-177): MAJOR ohne führende Null, MINOR zweistellig 00–99, ab 100 ohne führende Null
VERSION_MUSTER = re.compile(r"^(0|[1-9][0-9]*)\.([0-9]{2}|[1-9][0-9]{2,})$")
COMMIT_MUSTER = re.compile(r"^[0-9a-f]{7,40}$")
BUILD_MUSTER = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$")
FELDER = {"name", "version", "commit", "build_datum", "entwicklungsstand", "python", "repository", "modus",
          "datenbank", "datenbank_schema", "sicherung_schema"}
ENTWICKLUNGSSTAND_TEXT = "Entwicklungsstand (nicht über die Release-CI gebaut)"


ZWEIG_LINK = re.compile(r"""data-testid\s*=\s*["']zweig-link["']""")


def zweig_in_huelle(html: str) -> bool:
    """M31 (version.md 6, E-285): Die Hülle eines Entwicklungsbranchs enthält ``zweig-link``."""
    return ZWEIG_LINK.search(html) is not None


def knopf_text_soll(html: str, version: str) -> str:
    """Text von ``version-knopf``: „Über“ auf einem Entwicklungsbranch, sonst ``Version <version>`` (E-285)."""
    return "Über" if zweig_in_huelle(html) else f"Version {version}"


def version_gueltig(v: object) -> bool:
    return isinstance(v, str) and VERSION_MUSTER.fullmatch(v) is not None


def build_datum_gueltig(v: str) -> bool:
    if not BUILD_MUSTER.fullmatch(v):
        return False
    try:
        dt.datetime.fromisoformat(v[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def repository_gueltig(v: str) -> bool:
    t = urlsplit(v)
    return t.scheme == "https" and bool(t.hostname) and t.username is None and t.password is None


def gleicher_pfad(a: str, b) -> bool:
    return Path(a).is_absolute() and Path(a).resolve() == Path(b).resolve()


def leer(text: str) -> str:
    """Leerraum zusammenfassen (oberflaeche.md 24)."""
    return " ".join(text.split())


_LEER_ELEMENTE = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
                  "track", "wbr"}


class _Knopf(HTMLParser):
    """Sucht in der Hülle alle Elemente mit ``data-testid="version-knopf"`` samt Text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.treffer: list[dict] = []
        self._offen: list[dict] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in _LEER_ELEMENTE:
            return
        for o in self._offen:
            o["tiefe"] += 1
        if a.get("data-testid") == "version-knopf":
            t = {"tag": tag, "attrs": a, "text": "", "tiefe": 0}
            self.treffer.append(t)
            self._offen.append(t)

    def handle_endtag(self, tag):
        for o in list(self._offen):
            if o["tiefe"] == 0:
                self._offen.remove(o)
            else:
                o["tiefe"] -= 1

    def handle_data(self, data):
        for o in self._offen:
            o["text"] += data


def knoepfe_in_huelle(html: str) -> list[dict]:
    p = _Knopf()
    p.feed(html)
    return [{"tag": t["tag"], "attrs": t["attrs"], "text": leer(t["text"])} for t in p.treffer]
