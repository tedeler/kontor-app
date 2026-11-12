"""Mail-Abgleich als protokollierte Änderung (D-128): erkennen → automatisch zuordnen → Überfällige melden.

Läuft nach jedem Mail-Abruf, nach jedem Synchronisationslauf und in jedem Planer-Takt, nur mit
``mail_abgleich``. Erzeugt genau dann eine Änderung (Quelle ``mail``), wenn sich der Buchbestand ändert.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading

from . import db, erwartung, protokoll
from .config import KontorConfig

log = logging.getLogger("kontor.abgleich")
_SPERRE = threading.Lock()


def laufen(config: KontorConfig, jetzt: dt.datetime) -> dict | None:
    if not config.mail_abgleich:
        return None
    zeit = jetzt.astimezone(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    heute = jetzt.date().isoformat()
    with _SPERRE:
        con = db.verbinde(config.aktive_datenbank)
        try:
            erg: dict = {}
            with protokoll.protokolliert(con, "mail", "erwartung_erkennen", zeit):
                erg = erwartung.erkennen(con, config.mail_abgleich_frist_tage, zeit)
                erg["zugeordnet"] = erwartung.automatisch_zuordnen(con, zeit)
            with db.transaktion(con):
                erg["gemeldet"] = erwartung.ueberfaellige_melden(con, heute, zeit)
            return erg
        except Exception:  # noqa: BLE001 - der Abgleich darf Abruf, Lauf und Planer nie scheitern lassen
            log.exception("Mail-Abgleich fehlgeschlagen")
            return None
        finally:
            con.close()
