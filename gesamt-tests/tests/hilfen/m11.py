"""Testhilfen für Meilenstein 11 (kontostand.md, oberflaeche.md 22, datenmodell.md 16, buchhaltungspflege.md 10).

Die Mock-Daten mit Anfangssalden werden im Test aus der Generator-Datei abgeleitet (Kopie im temporären
Verzeichnis mit dem zusätzlichen Schlüssel ``bank.anfangssalden``); die Fixture selbst bleibt unverändert.
Erwartete Salden werden hier unabhängig aus den Umsätzen berechnet.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from tests.hilfen.m2 import SYNC_DATEN

HEUTE = dt.date(2024, 6, 30)
AUSGLEICH_ZWECK = "Saldoausgleich Bank"


def daten_mit_salden(basis: Path, anfangssalden: dict[str, int | None], quelle: Path = SYNC_DATEN) -> Path:
    d = json.loads(quelle.read_text(encoding="utf-8"))
    d["bank"]["anfangssalden"] = anfangssalden
    ziel = basis / "mock_daten_salden.json"
    ziel.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return ziel


def bank_saldo(daten: dict, iban: str, anfang: int, heute: dt.date = HEUTE) -> int:
    """kontostand.md 1.1: Anfangssaldo + gebuchte Umsätze bis heute (unabhängig vom Abrufzeitraum)."""
    return anfang + sum(u["betrag"] for u in daten["bank"]["umsaetze"]
                        if u["iban"] == iban and not u["vormerkung"]
                        and dt.date.fromisoformat(u["buchungstag"]) <= heute)


def gebucht_ab(daten: dict, iban: str, von: dt.date, heute: dt.date = HEUTE) -> int:
    return sum(u["betrag"] for u in daten["bank"]["umsaetze"]
               if u["iban"] == iban and not u["vormerkung"]
               and von <= dt.date.fromisoformat(u["buchungstag"]) <= heute)


def konto_saldo(api, konto_id: int, stichtag: str | None = None) -> int:
    q = f"?stichtag={stichtag}" if stichtag else ""
    u = api.get(f"/api/kontenuebersicht{q}", erwartet=200).daten
    return next(k["saldo"] for k in u["konten"] if k["konto_id"] == konto_id)


def sk(lauf: dict, iban: str) -> dict:
    return next(k for k in lauf["konten"] if k["iban"] == iban)


LEER = {"status": None, "bank_saldo": None, "stichtag": None, "kontor_saldo": None, "differenz": None,
        "buchung_id": None}


def ohne_saldo(status: str) -> dict:
    return {**LEER, "status": status}
