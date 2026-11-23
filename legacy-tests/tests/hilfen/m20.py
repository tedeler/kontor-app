"""Hilfen für Meilenstein-20-Tests (Mail-Abgleich, erwartete Zahlungen) – nur über erwartungen.md.

- Synthetische Mails im Stil von Amazon und PayPal (Absender unter ``*.example.invalid``, Inhalte fiktiv,
  erwartungen.md 2.1 und 10) als Einträge einer Mock-Datendatei.
- ``app`` baut eine Mock-App mit Mails (und optional Bankumsätzen) und legt die Postfächer an.
- ``bestand`` erweitert den Bestand aus M18 um das Objekt ``erwartung`` in der Protokollform (erwartungen.md 12).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .api import Api
from .m2 import mock_api
from .m6 import EINS, ZWEI, abruf, postfach
from .m18 import bestand as bestand_m18

AMAZON = "Amazon.de <bestellbestaetigung@amazon.example.invalid>"
PAYPAL = "PayPal <service@paypal.example.invalid>"
NR = "302-1234567-7654321"
CODE = "1AB23456CD789012E"
ZUSTAENDE = ("offen", "erfuellt", "guthaben", "storniert", "erledigt")
FORM = ("id", "grund", "richtung", "anbieter", "kennung", "referenz", "haendler", "beschreibung", "betrag", "gesamt",
        "guthaben", "datum", "frist", "zustand", "bezug_id", "buchung_ids", "mails", "dokument_ids", "erstellt_am")
ABGELEITET = ("zugeordnet", "offen_betrag", "ueberfaellig", "vorzeichen_betrag")
_zaehler = [0]


def nachricht(absender: str, betreff: str, text: str, empfangen: str = "2024-06-03T09:30:00Z", *,
              postfach: str = EINS, nid: str | None = None) -> dict:
    _zaehler[0] += 1
    return {"nachricht_id": nid or f"M-{_zaehler[0]:05d}", "postfach": postfach, "empfangen": empfangen,
            "absender": absender, "betreff": betreff, "text": text}


def amazon_bestellung(nr: str = NR, **kw) -> dict:
    """Beispiel aus erwartungen.md 2.3 (gesamt 5990, guthaben 1000, betrag 4990)."""
    text = (f"Hallo,\nvielen Dank für Ihre Bestellung.\nBestellnr. {nr}\n1 x USB-Kabel (fiktiv) 9,99 €\n"
            "1 x Ladegerät (fiktiv) 49,91 €\nGesamtsumme: 59,90 €\nGeschenkgutschein: -10,00 €\n")
    return nachricht(AMAZON, f"Ihre Amazon.de Bestellung von „USB-Kabel (fiktiv)“ ({nr})", text, **kw)


def amazon_storno(nr: str = NR, **kw) -> dict:
    return nachricht(AMAZON, f"Ihre Bestellung {nr} wurde storniert", "Die Bestellung wurde storniert.", **kw)


def amazon_erstattung(nr: str = NR, betrag: str = "9,99 €", **kw) -> dict:
    return nachricht(AMAZON, "Ihre Erstattung", f"Bestellnr. {nr}\nErstattungsbetrag: {betrag}\n", **kw)


def paypal_zahlung(code: str = CODE, haendler: str = "Fiktiver Shop", **kw) -> dict:
    """Beispiel aus erwartungen.md 2.4 (gesamt 2500, guthaben 500, betrag 2000, referenz R-4711)."""
    text = (f"Sie haben 25,00 € an {haendler} gesendet.\nTransaktionscode: {code}\nGesendeter Betrag: -25,00 €\n"
            "Bezahlt mit\nPayPal-Guthaben 5,00 €\nLastschrift Testbank\nBestellnummer: R-4711\n")
    return nachricht(PAYPAL, f"Sie haben eine Zahlung an {haendler} gesendet", text, **kw)


def paypal_rueckzahlung(code: str = "9ZZ23456CD789012E", ursprung: str = CODE, *, guthaben: bool = False,
                        **kw) -> dict:
    text = f"Rückzahlungsbetrag: 25,00 €\nTransaktionscode: {code}\nUrsprünglicher Transaktionscode: {ursprung}\n"
    if guthaben:
        text += "Der Betrag wurde Ihrem PayPal-Guthaben gutgeschrieben auf Ihr PayPal-Guthaben.\n"
    return nachricht(PAYPAL, "Rückzahlung von Fiktiver Shop erhalten", text, **kw)


def mock_datei(pfad: Path, nachrichten: list[dict], *, postfaecher=(EINS, ZWEI), konten=(), umsaetze=()) -> Path:
    pfad.write_text(json.dumps({"format": "kontor-mock-daten", "version": 1,
                                "bank": {"konten": list(konten), "umsaetze": list(umsaetze)},
                                "mail": {"postfaecher": list(postfaecher), "nachrichten": nachrichten}},
                               ensure_ascii=False), encoding="utf-8")
    return pfad


def app(tmp_path: Path, nachrichten: list[dict], *, heute: str = "2024-06-05", abgleich: bool = True,
        postfaecher=(EINS,), konten=(), umsaetze=(), name: str = "a", **felder) -> Api:
    datei = mock_datei(tmp_path / f"{name}-mock.json", nachrichten, konten=konten, umsaetze=umsaetze)
    api = mock_api(tmp_path / name, daten=datei, heute=heute, mail_erstabruf_tage=365, mail_abgleich=abgleich,
                   **felder)
    for p in postfaecher:
        postfach(api, p)
    return api


def konten(api: Api) -> dict:
    return {"giro": api.konto("Girokonto")["id"], "spar": api.konto("Tagesgeld", "sparkonto")["id"],
            "einkauf": api.konto("Einkauf", "aufwand")["id"], "ertrag": api.konto("Erstattungen", "ertrag")["id"]}


def ausgabe(api: Api, k: dict, datum: str, betrag: int, zweck: str = "", empfaenger: str | None = None) -> int:
    felder: dict = {"verwendungszweck": zweck}
    if empfaenger:
        felder["empfaenger_id"] = _empfaenger(api, empfaenger)
    return api.buchung(datum, [(k["giro"], -betrag), (k["einkauf"], betrag)], **felder)["id"]


def eingang(api: Api, k: dict, datum: str, betrag: int, zweck: str = "", empfaenger: str | None = None) -> int:
    felder: dict = {"verwendungszweck": zweck}
    if empfaenger:
        felder["empfaenger_id"] = _empfaenger(api, empfaenger)
    return api.buchung(datum, [(k["giro"], betrag), (k["ertrag"], -betrag)], **felder)["id"]


def _empfaenger(api: Api, name: str) -> int:
    for e in api.get("/api/empfaenger", erwartet=200).daten:
        if e["name"] == name:
            return e["id"]
    return api.empfaenger(name)["id"]


# ------------------------------------------------------------------ Lesen
def liste(api: Api, erwartet: int = 200, **params):
    p = []
    for k, v in params.items():
        for x in (v if isinstance(v, (list, tuple)) else [v]):
            p.append((k, x))
    r = api.get("/api/erwartungen", params=p or None, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def alle(api: Api) -> list[dict]:
    return liste(api, zustand=list(ZUSTAENDE))["eintraege"]


def detail(api: Api, eid: int) -> dict:
    return api.get(f"/api/erwartungen/{eid}", erwartet=200).daten


def form(e: dict) -> dict:
    return {k: e[k] for k in FORM} | {"mails": [{k: m[k] for k in ("postfach", "nachricht_id", "betreff",
                                                                    "empfangen")} for m in e["mails"]]}


def abgleich(api: Api, erwartet: int = 200):
    r = api.post("/api/erwartungen/abgleich", erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def bestand(api: Api) -> dict[tuple[str, int], dict]:
    """Buchbestand in Protokollform mit Dokumenten und Erwartungen (E-217)."""
    aus = bestand_m18(api)
    for e in alle(api):
        aus[("erwartung", e["id"])] = form(e)
    return aus


def heute_plus(datum: str, tage: int) -> str:
    return (dt.date.fromisoformat(datum) + dt.timedelta(days=tage)).isoformat()


def utc_datum(zeitstempel: str) -> str:
    return zeitstempel[:10]


__all__ = ["EINS", "ZWEI", "abruf"]
