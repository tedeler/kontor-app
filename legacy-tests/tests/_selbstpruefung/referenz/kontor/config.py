"""KontorConfig laut python-api.md 3 und 8.2 (Wegwerf-Referenz)."""

from __future__ import annotations

import datetime
import os
import pathlib
import re
from dataclasses import dataclass

from .m6_config import M6Felder, m6_env, m6_pruefen
from .m7_config import M7Felder, m7_env, m7_pruefen

from .fehler import KonfigurationsFehler

SZENARIEN = {"normal", "bankfehler", "zeitueberschreitung", "tan_erforderlich", "token_ablauf", "beitragsaenderung"}
_WAHR = {"1", "true", "ja", "yes", "on"}
_FALSCH = {"0", "false", "nein", "no", "off", ""}


@dataclass(frozen=True)
class KontorConfig(M7Felder, M6Felder):
    datenbank: pathlib.Path
    mock_modus: bool = False
    mock_datenbank: pathlib.Path | None = None
    bank_plugin: str | None = None
    mail_plugin: str | None = None
    mock_szenario: str = "normal"
    mock_daten: pathlib.Path | None = None
    mock_heute: datetime.date | None = None
    sync_intervall_minuten: int = 0
    sync_wiederholung_minuten: int = 30
    sync_erstabruf_tage: int = 90
    sync_ueberlappung_tage: int = 14
    planer_starten: bool = True
    umbuchung_automatisch: bool = False
    umbuchung_fenster_tage: int = 3
    lernmodell_automatisch: bool = False
    wiederkehrend_automatisch: bool = False
    sync_saldo_angleichen: bool = True   # M11, kontostand.md 2
    sync_konten_anlegen: bool = True     # M15, synchronisation.md 20

    def __post_init__(self) -> None:
        setze = object.__setattr__
        setze(self, "datenbank", pathlib.Path(self.datenbank))
        for feld in ("mock_datenbank", "mock_daten"):
            if getattr(self, feld) is not None:
                setze(self, feld, pathlib.Path(getattr(self, feld)))
        if self.bank_plugin is None:
            setze(self, "bank_plugin", "mock" if self.mock_modus else "fints")
        if self.mail_plugin is None:
            setze(self, "mail_plugin", "mock" if self.mock_modus else "imap")
        if self.bank_plugin not in ("mock", "fints"):   # M29: aqbanking entfällt (python-api.md 21.1)
            raise KonfigurationsFehler("Unbekanntes Bank-Plugin", feld="bank_plugin")
        if self.mail_plugin not in ("mock", "imap"):
            raise KonfigurationsFehler("Unbekanntes Plugin")
        if self.mock_modus != (self.bank_plugin == "mock") or self.mock_modus != (self.mail_plugin == "mock"):
            raise KonfigurationsFehler("Mock-Plugins nur im Mock-Modus")
        if self.mock_szenario not in SZENARIEN:
            raise KonfigurationsFehler("Unbekanntes Szenario")
        if self.mock_modus and self.aktive_datenbank.resolve() == self.datenbank.resolve():
            raise KonfigurationsFehler("Mock-Datenbank gleich Echt-Datenbank")
        for feld, minimum in (("sync_intervall_minuten", 0), ("sync_wiederholung_minuten", 1),
                              ("sync_erstabruf_tage", 0), ("sync_ueberlappung_tage", 0)):
            wert = getattr(self, feld)
            if type(wert) is not int or wert < minimum:
                raise KonfigurationsFehler(f"{feld} ungültig")
        if type(self.planer_starten) is not bool:
            raise KonfigurationsFehler("planer_starten ungültig")
        if type(self.umbuchung_automatisch) is not bool:
            raise KonfigurationsFehler("umbuchung_automatisch ungültig")
        if type(self.sync_saldo_angleichen) is not bool:
            raise KonfigurationsFehler("sync_saldo_angleichen ungültig")
        if type(self.sync_konten_anlegen) is not bool:
            raise KonfigurationsFehler("sync_konten_anlegen ungültig")
        if type(self.umbuchung_fenster_tage) is not int or not 0 <= self.umbuchung_fenster_tage <= 366:
            raise KonfigurationsFehler("umbuchung_fenster_tage ungültig")
        if type(self.lernmodell_automatisch) is not bool:
            raise KonfigurationsFehler("lernmodell_automatisch ungültig")
        if type(self.wiederkehrend_automatisch) is not bool:
            raise KonfigurationsFehler("wiederkehrend_automatisch ungültig")
        m6_pruefen(self)
        m7_pruefen(self)

    @property
    def aktive_datenbank(self) -> pathlib.Path:
        if not self.mock_modus:
            return self.datenbank
        if self.mock_datenbank is not None:
            return self.mock_datenbank
        d = self.datenbank
        return d.with_name(d.stem + "-mock" + d.suffix)

    @classmethod
    def from_env(cls, umgebung=None) -> "KontorConfig":
        u = os.environ if umgebung is None else umgebung

        def text(n):
            return (u.get(n) or "").strip()

        def wahr(n, vorgabe):
            w = text(n).lower()
            if w == "":
                return vorgabe
            if w in _WAHR:
                return True
            if w in _FALSCH:
                return False
            raise KonfigurationsFehler(f"{n} ungültig")

        def zahl(n, vorgabe):
            w = text(n)
            if w == "":
                return vorgabe
            if not re.fullmatch(r"[0-9]+", w):
                raise KonfigurationsFehler(f"{n} ungültig")
            return int(w)

        if not text("KONTOR_DATENBANK"):
            raise KonfigurationsFehler("KONTOR_DATENBANK fehlt")
        heute = text("KONTOR_MOCK_HEUTE")
        try:
            heute_d = datetime.date.fromisoformat(heute) if heute else None
        except ValueError as e:
            raise KonfigurationsFehler("KONTOR_MOCK_HEUTE ungültig") from e
        return cls(datenbank=pathlib.Path(text("KONTOR_DATENBANK")), mock_modus=wahr("KONTOR_MOCK_MODUS", False),
                   mock_datenbank=pathlib.Path(text("KONTOR_MOCK_DATENBANK")) if text("KONTOR_MOCK_DATENBANK") else None,
                   bank_plugin=text("KONTOR_BANK_PLUGIN") or None, mail_plugin=text("KONTOR_MAIL_PLUGIN") or None,
                   mock_szenario=text("KONTOR_MOCK_SZENARIO") or "normal",
                   mock_daten=pathlib.Path(text("KONTOR_MOCK_DATEN")) if text("KONTOR_MOCK_DATEN") else None,
                   mock_heute=heute_d,
                   sync_intervall_minuten=zahl("KONTOR_SYNC_INTERVALL_MINUTEN", 0),
                   sync_wiederholung_minuten=zahl("KONTOR_SYNC_WIEDERHOLUNG_MINUTEN", 30),
                   sync_erstabruf_tage=zahl("KONTOR_SYNC_ERSTABRUF_TAGE", 90),
                   sync_ueberlappung_tage=zahl("KONTOR_SYNC_UEBERLAPPUNG_TAGE", 14),
                   planer_starten=wahr("KONTOR_PLANER_STARTEN", True),
                   umbuchung_automatisch=wahr("KONTOR_UMBUCHUNG_AUTOMATISCH", False),
                   umbuchung_fenster_tage=zahl("KONTOR_UMBUCHUNG_FENSTER_TAGE", 3),
                   lernmodell_automatisch=wahr("KONTOR_LERNMODELL_AUTOMATISCH", False),
                   wiederkehrend_automatisch=wahr("KONTOR_WIEDERKEHREND_AUTOMATISCH", False),
                   sync_saldo_angleichen=wahr("KONTOR_SYNC_SALDO_ANGLEICHEN", True),
                   sync_konten_anlegen=wahr("KONTOR_SYNC_KONTEN_ANLEGEN", True),
                   **m6_env(text, wahr, zahl), **m7_env(text, wahr, zahl))
