"""Hilfen für Meilenstein-32-Tests (Sammelbranch sammel3, Definition 4) – nur über sammel3.md und
oberflaeche.md 41 (E-293 bis E-306).

- ``erfolgsmeldung_einschalten``: schaltet die Erfolgsmeldung mit „Rückgängig“ über die Einstellung
  ``einstellung-erfolgsmeldung`` ein (41.9, E-306); ``browser_fixtures.neue_seite(..., erfolgsmeldung=True)`` tut
  das vor dem ersten Laden der eigentlichen Seite.
- Kontonamen (1): ``kontoname_schluessel``, ``konto_existiert``.
- Geplante Zahlungen (14): ``plus_monate`` (Tag der ersten Fälligkeit, Monatsletzter), ``geplant``.
- Vorschau (14.4): ``geplante_ereignisse`` sucht Ereignisse mit ``quelle = "geplant"`` irgendwo in der Antwort.
- Anbieter-Beschreibungen (9.1): ``kaufhaus_toml`` nach ``ANBIETER.md`` mit Absender unter ``example.invalid``.
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Any

from .api import Api, fehlercode

KLASSE = {"girokonto": "bestand", "sparkonto": "bestand", "kreditkonto": "bestand", "aufwand": "aufwand",
          "ertrag": "ertrag", "eigenkapital": "eigenkapital"}
RHYTHMUS_MONATE = {"monatlich": 1, "vierteljaehrlich": 3, "halbjaehrlich": 6, "jaehrlich": 12}


# ------------------------------------------------------------------ Oberfläche
def erfolgsmeldung_einschalten(seite, server) -> None:
    """Einstellungen → Allgemein → ``einstellung-erfolgsmeldung`` einschalten (oberflaeche.md 41.9)."""
    from playwright.sync_api import expect

    from . import m8
    from .m31 import einstellungen_oeffnen

    einstellungen_oeffnen(seite, server, "allgemein")
    schalter = m8.tid(seite, "einstellung-erfolgsmeldung")
    schalter.check()
    expect(schalter).to_be_checked()


# ------------------------------------------------------------------ 1 Kontonamen
def kontoname_schluessel(k: dict) -> tuple:
    """(Ebene, Name) nach sammel3.md 1.1: Elternkonto bzw. Klasse auf oberster Ebene, ``strip().casefold()``."""
    ebene = k["eltern_id"] if k["eltern_id"] is not None else "oben:" + KLASSE[k["art"]]
    return ebene, k["name"].strip().casefold()


def namen_eindeutig(konten: list[dict]) -> bool:
    s = [kontoname_schluessel(k) for k in konten]
    return len(s) == len(set(s))


def konto_existiert(r, *konto_ids: int) -> None:
    """409 ``konto_existiert`` mit ``details.konto_ids`` (nicht leer, enthält die genannten IDs, E-295)."""
    assert r.status_code == 409 and fehlercode(r) == "konto_existiert", r.text[:300]
    ids = r.json()["fehler"]["details"]["konto_ids"]
    assert isinstance(ids, list) and ids and all(isinstance(i, int) for i in ids), ids
    for i in konto_ids:
        assert i in ids, (i, ids)


# ------------------------------------------------------------------ 14 Geplante Zahlungen
def plus_monate(erste: str, monate: int) -> str:
    """Datum ``monate`` nach der ersten Fälligkeit, am Tag im Monat der ersten Fälligkeit, in kürzeren Monaten am
    Monatsletzten (sammel3.md 14.2)."""
    d = dt.date.fromisoformat(erste)
    j, m = divmod(d.month - 1 + monate, 12)
    jahr, monat = d.year + j, m + 1
    return dt.date(jahr, monat, min(d.day, calendar.monthrange(jahr, monat)[1])).isoformat()


def tage(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def geplant(api: Api, betrag: int, datum: str, *, haendler: str = "Stadtwerke Musterstadt", erwartet: int = 201,
            **felder) -> Any:
    r = api.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": haendler, "betrag": betrag,
                                           "datum": datum, **felder}, erwartet=erwartet)
    return r.daten if erwartet == 201 else r


def alle_erwartungen(api: Api) -> list[dict]:
    p = [("zustand", z) for z in ("offen", "erfuellt", "guthaben", "storniert", "erledigt")]
    return api.get("/api/erwartungen", params=p, erwartet=200).daten["eintraege"]


def geplante_ereignisse(daten: Any) -> list[dict]:
    """Alle Objekte mit ``quelle == "geplant"`` in einer beliebig verschachtelten Antwort (E-303)."""
    aus: list[dict] = []

    def gehe(x):
        if isinstance(x, dict):
            if x.get("quelle") == "geplant":
                aus.append(x)
            for v in x.values():
                gehe(v)
        elif isinstance(x, list):
            for v in x:
                gehe(v)
    gehe(daten)
    return aus


# ------------------------------------------------------------------ 9 Anbieter-Beschreibungen
KAUFHAUS_ABSENDER = "Kaufhaus Muster <auftrag@kaufhaus.example.invalid>"


def kaufhaus_toml(*, gesamt_ausdruck: str = "(?i)zu zahlen") -> str:
    """Beschreibung nach ANBIETER.md (Beispiel „kaufhaus“), Domain unter ``example.invalid``."""
    return f"""name = "kaufhaus"
titel = "Kaufhaus Muster"
absender = '(^|\\.)kaufhaus\\.example\\.invalid$'

[kennung]
muster = 'Auftrag\\s+(K\\d{{6}})'
suche_in = ["betreff", "text"]

[[art]]
name = "bestellung"
rolle = "ausgabe"
grund = "bestellung"
betreff = '(?i)auftragsbestätigung'
gesamt = {{ betrag_nach = '{gesamt_ausdruck}' }}

[bank]
namen = ["kaufhaus muster"]
kennung = '(?<![A-Z0-9])K\\d{{6}}(?!\\d)'
"""


def kaufhaus_mail(nummer: str = "K123456", betrag: str = "42,50 €", **kw) -> dict:
    from .m20 import nachricht
    return nachricht(KAUFHAUS_ABSENDER, f"Auftragsbestätigung Auftrag {nummer}",
                     f"Vielen Dank für Ihren Auftrag {nummer}.\nZu zahlen: {betrag}\n", **kw)


def bestand(api: Api) -> dict[tuple[str, int], dict]:
    """Bestand in Protokollform wie ``m20.bestand``, Erwartungen mit ``wiederholung`` nur, wo eine besteht
    (sammel3.md 14.1, 14.5)."""
    from .m20 import bestand as bestand_m20

    aus = bestand_m20(api)
    for e in alle_erwartungen(api):
        if "wiederholung" in e:
            aus[("erwartung", e["id"])] = {**aus[("erwartung", e["id"])], "wiederholung": e["wiederholung"]}
    return aus
