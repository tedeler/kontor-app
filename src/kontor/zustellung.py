"""Zustellung der Benachrichtigungen über ein Benachrichtigungs-Plugin (benachrichtigungen.md 4, Meilenstein 6).

Die interne Liste bleibt die einzige Quelle; jede Benachrichtigung wird höchstens einmal erfolgreich gesendet.
Erster Versuch unmittelbar nach dem Entstehen (am Ende derselben Anfrage bzw. desselben Planer-Takts),
Wiederholung nur nach einem Fehlschlag. Höchstens ein Zustellvorgang gleichzeitig je App.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
from collections.abc import Callable

from . import db
from .config import KontorConfig
from .fehler import KontorFehler
from .plugins import erzeuge_benachrichtigungs_plugin
from .plugins.benachrichtigung import PushNachricht

log = logging.getLogger("kontor.zustellung")
UTC = dt.timezone.utc
PRIORITAET_4 = ("tan_erforderlich", "tan_erinnerung", "mail_token_abgelaufen", "mail_token_widerrufen")


def _zeit(z: dt.datetime) -> str:
    return z.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class Zustelldienst:
    def __init__(self, config: KontorConfig, jetzt: Callable[[], dt.datetime],
                 token_quelle: Callable[[], str | None]) -> None:
        self._config = config
        self._jetzt = jetzt
        self._pfad = config.aktive_datenbank
        self.plugin = erzeuge_benachrichtigungs_plugin(config, token_quelle=token_quelle)
        self._sperre = threading.Lock()

    def __repr__(self) -> str:
        return f"Zustelldienst(plugin={self.plugin_name!r})"

    @property
    def plugin_name(self) -> str:
        return self._config.benachrichtigung_plugin or "keins"

    def vorbereiten(self) -> None:
        """Hält in der Datenbank fest, ob neue Benachrichtigungen zugestellt werden (Trigger in db.py)."""
        con = db.verbinde(self._pfad)
        try:
            con.execute("INSERT INTO meta (schluessel, wert) VALUES ('zustellung_neu', ?) ON CONFLICT(schluessel)"
                        " DO UPDATE SET wert = excluded.wert",
                        ("keine" if self.plugin is None else "ausstehend",))
        finally:
            con.close()

    # ------------------------------------------------------------ Nachricht
    def _nachricht(self, r) -> PushNachricht:
        c = self._config
        titel = ("[Mock] " if c.mock_modus else "") + r["titel"]
        link = None
        if c.oeffentliche_url and r["link"]:
            link = c.oeffentliche_url.rstrip("/") + r["link"]
        return PushNachricht(benachrichtigung_id=r["id"], titel=titel, text=r["text"], link=link,
                             prioritaet=4 if r["art"] in PRIORITAET_4 else 3, tags=(r["art"],),
                             schluessel=r["schluessel"])

    # ------------------------------------------------------------ Zustellen
    def neue(self) -> None:
        """Erster Versuch für alle neuen (noch nie versuchten) Benachrichtigungen."""
        if self.plugin is not None:
            self._zustellen("zustellversuche = 0")

    def faellige(self) -> None:
        """Planer-Takt (synchronisation.md 18.2 Schritt 6): ausstehende, deren nächster Versuch fällig ist."""
        if self.plugin is not None:
            self._zustellen("(naechster_versuch IS NULL OR naechster_versuch <= ?)", (_zeit(self._jetzt()),))

    def alle(self) -> dict:
        """POST /api/benachrichtigungen/zustellen: alle ausstehenden sofort."""
        if self.plugin is None:
            return {"versucht": 0, "zugestellt": 0}
        return self._zustellen("1 = 1")

    def _zustellen(self, bedingung: str, parameter: tuple = ()) -> dict:
        ergebnis = {"versucht": 0, "zugestellt": 0}
        with self._sperre:
            con = db.verbinde(self._pfad)
            try:
                zeilen = con.execute(f"SELECT * FROM benachrichtigung WHERE zustellung = 'ausstehend' AND {bedingung}"
                                     " ORDER BY id", parameter).fetchall()
                for r in zeilen:
                    ergebnis["versucht"] += 1
                    if self._einmal(con, r):
                        ergebnis["zugestellt"] += 1
            finally:
                con.close()
        return ergebnis

    def _einmal(self, con, r) -> bool:
        try:
            self.plugin.senden(self._nachricht(r))
        except Exception as e:  # noqa: BLE001 - ein Fehlschlag ändert nichts an der auslösenden Operation
            jetzt = self._jetzt()
            versuche = r["zustellversuche"] + 1
            aufgegeben = versuche >= self._config.zustellung_max_versuche
            naechster = _zeit(jetzt + dt.timedelta(minutes=self._config.zustellung_wiederholung_minuten))
            code = e.code if isinstance(e, KontorFehler) else "benachrichtigung_fehler"
            meldung = (e.meldung if isinstance(e, KontorFehler) else "") or "Die Zustellung ist fehlgeschlagen."
            with db.transaktion(con):
                con.execute("UPDATE benachrichtigung SET zustellversuche = ?, zustellung = ?, naechster_versuch = ?"
                            " WHERE id = ?", (versuche, "aufgegeben" if aufgegeben else "ausstehend",
                                              None if aufgegeben else naechster, r["id"]))
                con.execute("INSERT INTO meta (schluessel, wert) VALUES ('zustellung_fehler', ?)"
                            " ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
                            (json.dumps({"code": code, "meldung": meldung, "zeitpunkt": _zeit(jetzt)},
                                        ensure_ascii=False),))
            if not isinstance(e, KontorFehler):
                log.warning("Unerwarteter Fehler bei der Zustellung: %s", type(e).__name__)
            return False
        with db.transaktion(con):
            con.execute("UPDATE benachrichtigung SET zustellversuche = zustellversuche + 1, zustellung = 'zugestellt',"
                        " zugestellt_am = ?, naechster_versuch = NULL WHERE id = ?", (_zeit(self._jetzt()), r["id"]))
        return True

    def testnachricht(self) -> dict:
        """Test-Benachrichtigung aus der Oberfläche (D-076): direkt über das Plugin, nicht in der internen Liste.
        Im Mock-Plugin landet sie nicht in ``gesendet`` (dort stehen nur Benachrichtigungen der Liste)."""
        from .validierung import ApiFehler
        if self.plugin is None:
            raise ApiFehler(409, "kein_benachrichtigungs_plugin",
                            "Es ist kein Benachrichtigungs-Plugin eingerichtet (benachrichtigung_plugin = keins).")
        if self.plugin.ist_mock:
            return {"gesendet": True, "plugin": self.plugin_name}
        n = PushNachricht(benachrichtigung_id=0, titel=("[Mock] " if self._config.mock_modus else "")
                          + "Kontor: Test-Benachrichtigung",
                          text="Diese Nachricht bestätigt, dass Kontor Benachrichtigungen zustellen kann.",
                          link=(self._config.oeffentliche_url.rstrip("/") + "/") if self._config.oeffentliche_url else None,
                          prioritaet=3, tags=("test",), schluessel="test")
        with self._sperre:
            try:
                self.plugin.senden(n)
            except KontorFehler as e:
                raise ApiFehler(409, e.code, e.meldung or "Die Zustellung ist fehlgeschlagen.",
                                {"status": e.details.get("status")}) from None
        return {"gesendet": True, "plugin": self.plugin_name}

    # ------------------------------------------------------------ Lesen
    def status(self, con) -> dict:
        anzahl = {z: 0 for z in ("ausstehend", "zugestellt", "aufgegeben")}
        for r in con.execute("SELECT zustellung, COUNT(*) AS n FROM benachrichtigung GROUP BY zustellung"):
            if r["zustellung"] in anzahl:
                anzahl[r["zustellung"]] = r["n"]
        r = con.execute("SELECT wert FROM meta WHERE schluessel = 'zustellung_fehler'").fetchone()
        return {"plugin": self.plugin_name, **anzahl, "letzter_fehler": json.loads(r["wert"]) if r else None}

    def mock_gesendet(self) -> list[dict]:
        gesendet = getattr(self.plugin, "gesendet", None) if self.plugin is not None and self.plugin.ist_mock else None
        return [{"benachrichtigung_id": n.benachrichtigung_id, "titel": n.titel, "text": n.text, "link": n.link,
                 "prioritaet": n.prioritaet, "tags": list(n.tags), "schluessel": n.schluessel}
                for n in (gesendet or [])]


__all__ = ["Zustelldienst"]
