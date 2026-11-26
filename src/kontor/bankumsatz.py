"""Umsätze, wie die Bank sie geliefert hat (Feature ``nachweis-pdf``, D-303).

Die Synchronisation merkt sich je Bankkennung Buchungstag, Empfängername (nach Auflösung der Aliase, also so, wie
Kontor ihn beim Abruf vergeben hat), Verwendungszweck und Betrag. Der Nachweis als PDF vergleicht die Buchung damit
und kennzeichnet Abweichungen. Die Tabelle ``bank_umsatz`` ist Betriebszustand wie ``buchung_herkunft`` (D-302): nicht
im Änderungsprotokoll, nicht in der Sicherung. Schlüssel ist die Bankkennung, nicht die Buchung; so bleibt die Angabe
richtig, wenn Rückgängig, Wiederholen oder Einspielen die Buchungen neu anlegen.
"""

from __future__ import annotations

import json

NACHGETRAGEN = "bank_umsatz_nachgetragen"


def merken(con, kennung: str, datum: str, empfaenger: str | None, verwendungszweck: str | None, betrag: int) -> None:
    """Hält einen Umsatz der Bank fest; ein schon bekannter bleibt unverändert."""
    con.execute("INSERT OR IGNORE INTO bank_umsatz (kennung, datum, empfaenger, verwendungszweck, betrag)"
                " VALUES (?, ?, ?, ?, ?)", (kennung, datum, empfaenger or "", verwendungszweck or "", betrag))


def lesen(con, kennungen: list[str]) -> dict | None:
    """Erster gemerkter Umsatz zu einer der Kennungen (in Sortierreihenfolge) oder None."""
    for k in sorted(kennungen):
        r = con.execute("SELECT datum, empfaenger, verwendungszweck, betrag FROM bank_umsatz WHERE kennung = ?",
                        (k,)).fetchone()
        if r is not None:
            return dict(r)
    return None


def nachtragen(con) -> int:
    """Einmalig beim Start (Schema 20): Bankumsätze aus dem Änderungsprotokoll nachtragen, soweit es sie noch enthält.
    Maßstab ist der Stand, mit dem die Synchronisation eine Buchung angelegt hat (an vorhandene Buchungen angehängte
    Kennungen tragen keine Angaben der Bank und bleiben aus). Liefert die Zahl der nachgetragenen Umsätze."""
    if con.execute("SELECT 1 FROM meta WHERE schluessel = ?", (NACHGETRAGEN,)).fetchone() is not None:
        return 0
    konten = {r["iban"]: r["id"] for r in con.execute("SELECT id, iban FROM konto WHERE iban IS NOT NULL")}
    anzahl = 0
    for r in con.execute(
            "SELECT e.aenderung_id AS aid, e.nachher AS nachher FROM aenderung_eintrag e"
            " JOIN aenderung a ON a.id = e.aenderung_id"
            " WHERE a.quelle = 'sync' AND e.objekt = 'buchung' AND e.art = 'angelegt' AND e.nachher IS NOT NULL"
            " ORDER BY e.aenderung_id, e.position").fetchall():
        stand = json.loads(r["nachher"])
        name = _empfaengername(con, stand.get("empfaenger_id"), r["aid"])
        for kennung in stand.get("extern_ids") or []:
            teile = kennung.split(":")
            if len(teile) < 3 or teile[0] != "bank" or teile[1] not in konten:
                continue
            kid = konten[teile[1]]
            betrag = sum(s["betrag"] for s in stand.get("splits") or [] if s.get("konto_id") == kid)
            vorher = con.total_changes
            merken(con, kennung, stand.get("datum") or "", name, stand.get("verwendungszweck"), betrag)
            anzahl += con.total_changes - vorher
    con.execute("INSERT INTO meta (schluessel, wert) VALUES (?, '1')", (NACHGETRAGEN,))
    return anzahl


def _empfaengername(con, eid: int | None, bis_aenderung: int) -> str:
    if eid is None:
        return ""
    r = con.execute("SELECT nachher FROM aenderung_eintrag WHERE objekt = 'empfaenger' AND objekt_id = ?"
                    " AND aenderung_id <= ? AND nachher IS NOT NULL ORDER BY aenderung_id DESC, position DESC LIMIT 1",
                    (eid, bis_aenderung)).fetchone()
    if r is not None:
        return json.loads(r["nachher"]).get("name") or ""
    r = con.execute("SELECT name FROM empfaenger WHERE id = ?", (eid,)).fetchone()
    return r["name"] if r is not None else ""


__all__ = ["merken", "lesen", "nachtragen"]
