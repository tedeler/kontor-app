"""Konfiguration von Kontor (python-api.md Abschnitt 3)."""

from __future__ import annotations

import datetime as dt
import os
import pathlib
from collections.abc import Mapping
from dataclasses import dataclass

from .fehler import KonfigurationsFehler

BANK_PLUGINS = ("mock", "fints")
MAIL_PLUGINS = ("mock", "imap")
SZENARIEN = ("normal", "bankfehler", "zeitueberschreitung", "tan_erforderlich", "token_ablauf", "beitragsaenderung")

_WAHR = {"1", "true", "ja", "yes", "on"}
_FALSCH = {"0", "false", "nein", "no", "off", ""}


def _als_pfad(wert: object, feld: str) -> pathlib.Path:
    if isinstance(wert, pathlib.Path):
        return wert
    if isinstance(wert, (str, os.PathLike)):
        return pathlib.Path(wert)
    raise KonfigurationsFehler(f"{feld} muss ein Pfad sein.", feld=feld)


@dataclass(frozen=True)
class KontorConfig:
    datenbank: pathlib.Path
    mock_modus: bool = False
    mock_datenbank: pathlib.Path | None = None
    bank_plugin: str | None = None
    mail_plugin: str | None = None
    mock_szenario: str = "normal"
    mock_daten: pathlib.Path | None = None
    mock_heute: dt.date | None = None
    # Meilenstein 2: Synchronisation und Planer (python-api.md 8.2)
    sync_intervall_minuten: int = 0
    sync_wiederholung_minuten: int = 30
    sync_erstabruf_tage: int = 90
    sync_ueberlappung_tage: int = 14
    planer_starten: bool = True
    # Meilenstein 3: Umbuchungserkennung (python-api.md 9.1)
    umbuchung_automatisch: bool = False
    umbuchung_fenster_tage: int = 3
    # Meilenstein 4: Lernmodell bei neuen Buchungen (python-api.md 10.1)
    lernmodell_automatisch: bool = False

    def __post_init__(self) -> None:
        setze = object.__setattr__
        if not isinstance(self.lernmodell_automatisch, bool):
            raise KonfigurationsFehler("lernmodell_automatisch muss wahr oder falsch sein.",
                                       feld="lernmodell_automatisch")
        if not isinstance(self.umbuchung_automatisch, bool):
            raise KonfigurationsFehler("umbuchung_automatisch muss wahr oder falsch sein.",
                                       feld="umbuchung_automatisch")
        f = self.umbuchung_fenster_tage
        if type(f) is not int or not 0 <= f <= 366:
            raise KonfigurationsFehler("umbuchung_fenster_tage muss eine Ganzzahl von 0 bis 366 sein.",
                                       feld="umbuchung_fenster_tage")
        for feld, minimum in (("sync_intervall_minuten", 0), ("sync_wiederholung_minuten", 1),
                              ("sync_erstabruf_tage", 0), ("sync_ueberlappung_tage", 0)):
            wert = getattr(self, feld)
            if type(wert) is not int or wert < minimum:
                raise KonfigurationsFehler(f"{feld} muss eine Ganzzahl ≥ {minimum} sein.", feld=feld)
        if not isinstance(self.planer_starten, bool):
            raise KonfigurationsFehler("planer_starten muss wahr oder falsch sein.", feld="planer_starten")
        setze(self, "datenbank", _als_pfad(self.datenbank, "datenbank"))
        if self.mock_datenbank is not None:
            setze(self, "mock_datenbank", _als_pfad(self.mock_datenbank, "mock_datenbank"))
        if self.mock_daten is not None:
            setze(self, "mock_daten", _als_pfad(self.mock_daten, "mock_daten"))
        if not isinstance(self.mock_modus, bool):
            raise KonfigurationsFehler("mock_modus muss wahr oder falsch sein.", feld="mock_modus")
        if self.mock_heute is not None and (
            not isinstance(self.mock_heute, dt.date) or isinstance(self.mock_heute, dt.datetime)
        ):
            raise KonfigurationsFehler("mock_heute muss ein Datum sein.", feld="mock_heute")

        standard = "mock" if self.mock_modus else None
        bank = self.bank_plugin if self.bank_plugin is not None else (standard or "fints")
        mail = self.mail_plugin if self.mail_plugin is not None else (standard or "imap")
        if bank not in BANK_PLUGINS:
            raise KonfigurationsFehler(f"Unbekanntes Bank-Plugin {bank!r} (erlaubt: mock, fints).",
                                       feld="bank_plugin")
        if mail not in MAIL_PLUGINS:
            raise KonfigurationsFehler(f"Unbekanntes Mail-Plugin {mail!r} (erlaubt: mock, imap).",
                                       feld="mail_plugin")
        if self.mock_modus and (bank != "mock" or mail != "mock"):
            raise KonfigurationsFehler("Im Mock-Modus sind nur Mock-Plugins erlaubt.", feld="mock_modus")
        if not self.mock_modus and (bank == "mock" or mail == "mock"):
            raise KonfigurationsFehler(
                "Mock-Plugins sind nur im Mock-Modus erlaubt (Mock-Daten dürfen nie in die Echt-Datenbank).",
                feld="mock_modus")
        if self.mock_szenario not in SZENARIEN:
            raise KonfigurationsFehler(f"Unbekanntes Mock-Szenario {self.mock_szenario!r}.",
                                       feld="mock_szenario")
        setze(self, "bank_plugin", bank)
        setze(self, "mail_plugin", mail)
        if self.mock_modus and self.aktive_datenbank.resolve() == self.datenbank.resolve():
            raise KonfigurationsFehler("Die Mock-Datenbank darf nicht die Echt-Datenbank sein.",
                                       feld="mock_datenbank")

    @property
    def standard_mock_datenbank(self) -> pathlib.Path:
        d = self.datenbank
        return d.with_name(d.stem + "-mock" + d.suffix)

    @property
    def aktive_datenbank(self) -> pathlib.Path:
        if not self.mock_modus:
            return self.datenbank
        return self.mock_datenbank if self.mock_datenbank is not None else self.standard_mock_datenbank

    @classmethod
    def from_env(cls, umgebung: Mapping[str, str] | None = None) -> "KontorConfig":
        env = os.environ if umgebung is None else umgebung

        def wert(name: str) -> str:
            return (env.get(name) or "").strip()

        datenbank = wert("KONTOR_DATENBANK")
        if not datenbank:
            raise KonfigurationsFehler("KONTOR_DATENBANK ist nicht gesetzt.", variable="KONTOR_DATENBANK")
        mock_modus = _wahrheitswert(wert("KONTOR_MOCK_MODUS"), "KONTOR_MOCK_MODUS", False)
        planer_starten = _wahrheitswert(wert("KONTOR_PLANER_STARTEN"), "KONTOR_PLANER_STARTEN", True)
        ganz = {}
        for feld in ("sync_intervall_minuten", "sync_wiederholung_minuten", "sync_erstabruf_tage",
                     "sync_ueberlappung_tage"):
            variable = "KONTOR_" + feld.upper()
            text = wert(variable)
            if text:
                if not text.isascii() or not text.isdigit():
                    raise KonfigurationsFehler(f"{variable} muss eine nicht negative Ganzzahl sein.",
                                               variable=variable)
                ganz[feld] = int(text)
        umbuchung_automatisch = _wahrheitswert(wert("KONTOR_UMBUCHUNG_AUTOMATISCH"),
                                               "KONTOR_UMBUCHUNG_AUTOMATISCH", False)
        lernmodell_automatisch = _wahrheitswert(wert("KONTOR_LERNMODELL_AUTOMATISCH"),
                                                "KONTOR_LERNMODELL_AUTOMATISCH", False)
        text = wert("KONTOR_UMBUCHUNG_FENSTER_TAGE")
        if text:
            if not text.isascii() or not text.isdigit() or int(text) > 366:
                raise KonfigurationsFehler("KONTOR_UMBUCHUNG_FENSTER_TAGE muss eine Ganzzahl von 0 bis 366 sein.",
                                           variable="KONTOR_UMBUCHUNG_FENSTER_TAGE")
            ganz["umbuchung_fenster_tage"] = int(text)
        heute_text = wert("KONTOR_MOCK_HEUTE")
        mock_heute = None
        if heute_text:
            try:
                if len(heute_text) != 10:
                    raise ValueError(heute_text)
                mock_heute = dt.date.fromisoformat(heute_text)
            except ValueError:
                raise KonfigurationsFehler("KONTOR_MOCK_HEUTE muss das Format YYYY-MM-DD haben.",
                                           variable="KONTOR_MOCK_HEUTE") from None
        return cls(
            datenbank=pathlib.Path(datenbank),
            mock_modus=mock_modus,
            mock_datenbank=pathlib.Path(wert("KONTOR_MOCK_DATENBANK")) if wert("KONTOR_MOCK_DATENBANK") else None,
            bank_plugin=wert("KONTOR_BANK_PLUGIN") or None,
            mail_plugin=wert("KONTOR_MAIL_PLUGIN") or None,
            mock_szenario=wert("KONTOR_MOCK_SZENARIO") or "normal",
            mock_daten=pathlib.Path(wert("KONTOR_MOCK_DATEN")) if wert("KONTOR_MOCK_DATEN") else None,
            mock_heute=mock_heute,
            planer_starten=planer_starten,
            umbuchung_automatisch=umbuchung_automatisch,
            lernmodell_automatisch=lernmodell_automatisch,
            **ganz,
        )


def _wahrheitswert(text: str, variable: str, leer: bool) -> bool:
    t = text.lower()
    if not t:
        return leer
    if t in _WAHR:
        return True
    if t in _FALSCH:
        return False
    raise KonfigurationsFehler(f"{variable} hat einen ungültigen Wert.", variable=variable)


__all__ = ["KontorConfig"]
