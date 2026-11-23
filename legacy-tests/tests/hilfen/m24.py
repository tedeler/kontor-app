"""Hilfen für Meilenstein-24-Tests (Serien als erwartete Zahlungen, Kategorie bei Erstattungen, eingebaute Mock-Mails)
– nur über ``erwartungen.md`` 13 und ``oberflaeche.md`` 34.

Die erwarteten Serieneinträge werden unabhängig aus dem Buchbestand berechnet: Serien über die Referenzkette
``wiederkehrend_orakel.uebersicht`` (Stichtag = heute der App-Uhr), Felder nach ``erwartungen.md`` 13.1.3.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import wiederkehrend_orakel as wo
from .api import Api
from .m2 import mock_api, sync
from .m6 import EINS, postfach
from .m16 import Abo
from .m20 import liste, mock_datei

SERIE_ID = r"^serie:[0-9]+:[0-9]+:(ausgabe|einnahme)$"


def heute(api: Api) -> str:
    return api.get("/api/mock/zeit", erwartet=200).daten["jetzt"][:10]


def frist_tage(api: Api) -> int:
    return int(getattr(api.config, "mail_abgleich_frist_tage", 5))


def bestand_rest(api: Api) -> tuple[list[dict], list[dict], list[dict]]:
    return api.alle_buchungen(), api.konten(), api.get("/api/kredite", erwartet=200).daten


def serien_orakel(api: Api, stichtag: str | None = None) -> list[dict]:
    """Serien der Referenzkette mit den gesetzten Betragsfiltern (ab M25, wiederkehrend.md 9)."""
    from .m25 import filter_fn, filter_von

    b, k, kr = bestand_rest(api)
    return wo.uebersicht(b, k, kr, stichtag or heute(api), filter_fn(filter_von(api)))["serien"]


def eintrag(s: dict, heute_: str, frist: int) -> dict:
    """Serieneintrag nach erwartungen.md 13.1.3."""
    betrag = abs(s["betrag"])
    richtung = "ausgabe" if s["richtung"] == "ausgabe" else "eingang"
    fr = (dt.date.fromisoformat(s["naechste_faelligkeit"]) + dt.timedelta(days=frist)).isoformat()
    return {"id": "serie:" + s["schluessel"], "grund": "serie", "richtung": richtung, "anbieter": None,
            "kennung": "", "referenz": "", "haendler": s["empfaenger"]["name"],
            "beschreibung": f"{s['rhythmus']}, zuletzt {s['letzte']}", "betrag": betrag, "gesamt": betrag,
            "guthaben": 0, "datum": s["naechste_faelligkeit"], "frist": fr, "zustand": "offen", "bezug_id": None,
            "buchung_ids": [], "mails": [], "dokument_ids": [], "erstellt_am": None, "zugeordnet": 0,
            "offen_betrag": betrag, "ueberfaellig": fr < heute_,
            "vorzeichen_betrag": -betrag if richtung == "ausgabe" else betrag, "konto_id": s["konto_id"],
            "serie": s["schluessel"]}


def soll_serien(api: Api, *, ausgelassen: set[int] = frozenset()) -> list[dict]:
    """Erwartete Serieneinträge (aktiv/ausbleibend, ohne Serien, deren letzte Buchung zugeordnet ist)."""
    h = heute(api)
    f = frist_tage(api)
    return [eintrag(s, h, f) for s in serien_orakel(api, h)
            if s["status"] in ("aktiv", "ausbleibend") and s["buchung_ids"][-1] not in ausgelassen]


def zugeordnete_buchungen(api: Api) -> set[int]:
    alle = liste(api, zustand=["offen", "erfuellt", "guthaben", "storniert", "erledigt"])["eintraege"]
    return {b for e in alle if not str(e["id"]).startswith("serie:") for b in e["buchung_ids"]}


def serien_der_liste(daten: dict) -> list[dict]:
    return [e for e in daten["eintraege"] if isinstance(e["id"], str)]


def gespeicherte_der_liste(daten: dict) -> list[dict]:
    return [e for e in daten["eintraege"] if isinstance(e["id"], int)]


def nach_id(eintraege: list[dict]) -> dict:
    return {e["id"]: e for e in eintraege}


def summen(eintraege: list[dict]) -> tuple[int, int, int]:
    """(anzahl, summe_offen, ueberfaellig) nach erwartungen.md 6.1 / 13.1.4."""
    return (len(eintraege), sum(e["offen_betrag"] * (1 if e["richtung"] == "eingang" else -1) for e in eintraege),
            sum(1 for e in eintraege if e["ueberfaellig"]))


# ------------------------------------------------------------------ Szenario mit Serien
class Serien:
    """Mock-App (heute 2024-06-20) mit Serien unterschiedlichen Status auf einem Girokonto.

    - ``abo``: monatlich −9,99 € am 05. (März–Juni) → aktiv, nächste Fälligkeit 2024-07-05.
    - ``gehalt``: monatlich +2 500,00 € am 28. (Feb.–Mai) → aktiv, Einnahme, nächste 2024-06-28.
    - ``verein``: vierteljährlich −30,00 € (15.08.23, 15.11.23, 15.02.24) → ausbleibend (fällig 2024-05-15).
    - ``altvertrag``: monatlich −12,00 € (Jan.–März 2023) → beendet.
    """

    def __init__(self, tmp_path: Path, *, abgleich: bool = True, heute_: str = "2024-06-20", mails=(), **felder):
        datei = mock_datei(tmp_path / "m24-mock.json", list(mails))
        self.api = mock_api(tmp_path / "app", daten=datei, heute=heute_, mail_erstabruf_tage=365,
                            mail_abgleich=abgleich, **felder)
        a = self.abo_helfer = Abo(self.api)
        self.giro = a.giro
        self.ertrag = self.api.konto("Lohn", "ertrag")["id"]
        self.emp = {n: self.api.empfaenger(t)["id"] for n, t in (
            ("abo", "Streamingdienst (fiktiv)"), ("gehalt", "Arbeitgeber Beispiel GmbH (fiktiv)"),
            ("verein", "Sportverein Musterstadt (fiktiv)"), ("altvertrag", "Altvertrag Beispiel (fiktiv)"))}
        self.abo = a.buchen(self.emp["abo"], ["2024-03-05", "2024-04-05", "2024-05-06", "2024-06-05"], -999)
        self.gehalt = [self.api.buchung(t, [(self.giro, 250000), (self.ertrag, -250000)],
                                        empfaenger_id=self.emp["gehalt"], verwendungszweck="Gehalt")["id"]
                       for t in ("2024-02-28", "2024-03-28", "2024-04-29", "2024-05-28")]
        self.verein = a.buchen(self.emp["verein"], ["2023-08-15", "2023-11-15", "2024-02-15"], -3000)
        self.altvertrag = a.buchen(self.emp["altvertrag"], ["2023-01-10", "2023-02-10", "2023-03-10"], -1200)
        for p in {m["postfach"] for m in mails}:
            postfach(self.api, p)

    def schluessel(self, name: str, richtung: str = "ausgabe") -> str:
        return f"{self.giro}:{self.emp[name]}:{richtung}"


# ------------------------------------------------------------------ Szenario Erstattung
def mock_konto(iban: str) -> dict:
    return {"iban": iban, "bic": None, "name": "Girokonto", "art": "girokonto", "inhaber": "Erika Fiktiv",
            "waehrung": "EUR"}


def umsatz(iban: str, uid: str, tag: str, betrag: int, zweck: str, name: str = "Händler Beispiel (fiktiv)") -> dict:
    return {"umsatz_id": uid, "iban": iban, "buchungstag": tag, "valuta": tag, "betrag": betrag, "waehrung": "EUR",
            "gegenpartei_name": name, "gegenpartei_iban": None, "verwendungszweck": zweck, "vormerkung": False,
            "storno": False}


def mit_unkategorisiert(tmp_path: Path, mails: list[dict], *, iban: str, heute_: str = "2024-06-12",
                        **felder) -> Api:
    """Mock-App, deren erster Lauf das Girokonto und das technische Konto „Unkategorisiert“ anlegt."""
    datei = mock_datei(tmp_path / "m24-erst.json", mails, konten=[mock_konto(iban)],
                       umsaetze=[umsatz(iban, "U-1", "2024-06-01", -100, "Kleinkram")])
    api = mock_api(tmp_path / "app", daten=datei, heute=heute_, mail_erstabruf_tage=365, mail_abgleich=True,
                   **felder)
    lauf = sync(api, von="2024-06-01")
    assert lauf["status"] == "erfolgreich", lauf
    postfach(api, EINS)
    return api


__all__ = ["EINS"]
