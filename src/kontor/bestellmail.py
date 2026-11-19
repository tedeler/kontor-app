"""Mails über die Amazon-Bestellnummer an Buchungen hängen (Feature ``amazon-bestellnummer``, D-208).

Trägt eine Buchung im Verwendungszweck oder Empfängernamen eine Amazon-Bestellnummer (``ddd-ddddddd-ddddddd``),
werden alle gespiegelten Mails, die dieselbe Nummer im Betreff oder Text nennen, als Dokumente an die Buchung
gehängt (die ganze Mail und ihre PDF-Anhänge). Es entsteht keine erwartete Zahlung; Beträge spielen keine Rolle.

Läuft nach jedem Mail-Abruf und nach jedem Synchronisationslauf, nur mit ``mail_bestellnummer``. Erzeugt genau
dann eine Änderung (Quelle ``mail``, Aktion ``bestellmail_anhaengen``), wenn etwas angehängt wurde.

Die Tabelle ``bestellmail`` merkt je (Buchung, Nachrichten-ID), dass die Mail schon behandelt ist
(Betriebszustand, nicht protokolliert, nicht gesichert). Löst der Anwender ein so angehängtes Dokument oder macht
er die Änderung rückgängig, kommt die Mail deshalb nicht von selbst wieder.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import threading

from . import db, dokumente, protokoll
from .config import KontorConfig
from .validierung import ApiFehler

log = logging.getLogger("kontor.bestellmail")
_SPERRE = threading.Lock()

NUMMER = re.compile(r"(?<!\d)\d{3}-\d{7}-\d{7}(?!\d)")
# Grobfilter in SQL, damit nur Texte mit einer möglichen Nummer gelesen werden
_GLOB = "*[0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9]*"
_GLOB_GROB = "*[0-9]-*[0-9]*-*[0-9]*"


def nummern(*texte: str | None) -> list[str]:
    """Amazon-Bestellnummern in den Texten, in der Reihenfolge des ersten Auftretens. Bankzeilen brechen die
    Nummer manchmal um, deshalb wird zusätzlich ohne Leerraum gesucht."""
    aus: list[str] = []
    for t in texte:
        if not t:
            continue
        for fassung in (t, re.sub(r"\s+", "", t)):
            for n in NUMMER.findall(fassung):
                if n not in aus:
                    aus.append(n)
    return aus


def _mails_je_nummer(con) -> dict[str, list]:
    """Bestellnummer → gespiegelte Mails (je Nachrichten-ID einmal, auch bei zwei Postfächern)."""
    aus: dict[str, list] = {}
    gesehen: set[tuple[str, str]] = set()
    for r in con.execute("SELECT id, adresse_cf, nachricht_id, betreff, text FROM mail_nachricht"
                         " WHERE betreff GLOB ? OR text GLOB ? ORDER BY empfangen, id", (_GLOB, _GLOB)):
        for n in NUMMER.findall(f"{r['betreff']}\n{r['text']}"):
            if (n, r["nachricht_id"]) not in gesehen:
                gesehen.add((n, r["nachricht_id"]))
                aus.setdefault(n, []).append(r)
    return aus


def _buchungen_mit_nummer(con) -> list[tuple[int, list[str]]]:
    aus = []
    for r in con.execute("SELECT b.id, b.verwendungszweck, e.name FROM buchung b"
                         " LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
                         " WHERE b.verwendungszweck GLOB ? OR e.name GLOB ? ORDER BY b.id", (_GLOB_GROB, _GLOB_GROB)):
        gefunden = nummern(r["verwendungszweck"], r["name"])
        if gefunden:
            aus.append((r["id"], gefunden))
    return aus


def _anhaengen(con, zeile, buchung_id: int, zeitpunkt: str) -> tuple[int, int]:
    """Die Mail und ihre PDF-Anhänge an die Buchung; was mit gleichem Inhalt schon dort hängt, bleibt wie es ist.
    Antwort: (ID des Dokuments der Mail an dieser Buchung, Anzahl neu entstandener Dokumente)."""
    vorhanden = {r["sha256"]: r["id"] for r in con.execute(
        "SELECT d.id, d.sha256 FROM dokument d JOIN dokument_buchung x ON x.dokument_id = d.id"
        " WHERE x.buchung_id = ? ORDER BY d.id DESC", (buchung_id,))}
    neu = 0

    def eins(inhalt: bytes, name: str) -> int:
        nonlocal neu
        sha = hashlib.sha256(inhalt).hexdigest()
        if sha in vorhanden:
            return vorhanden[sha]
        neu += 1
        vorhanden[sha] = dokumente.anlegen(con, inhalt, name, [buchung_id], "mail", zeitpunkt)["id"]
        return vorhanden[sha]

    voll = con.execute("SELECT * FROM mail_nachricht WHERE id = ?", (zeile["id"],)).fetchone()
    roh = dokumente.mail_roh_aus_spiegel(voll)
    ids = [eins(roh, (voll["betreff"] or "E-Mail")[:dokumente.MAX_NAME - 4])]
    try:
        anhaenge = dokumente.mail_lesen(roh).get("anhaenge", [])
    except Exception:  # noqa: BLE001 - eine unlesbare Mail hängt nur als Ganzes an
        anhaenge = []
    for a in anhaenge:
        try:
            name, _typ, inhalt = dokumente.mail_anhang(roh, a["nr"])
        except ApiFehler:
            continue
        if dokumente.typ_erkennen(inhalt) == dokumente.PDF:
            ids.append(eins(inhalt, name))
    return ids[0], neu


def zuordnen(con, zeitpunkt: str) -> dict:
    """Alle noch nicht behandelten Paare (Buchung, Mail) mit gleicher Bestellnummer anhängen."""
    con.execute("DELETE FROM bestellmail WHERE NOT EXISTS (SELECT 1 FROM buchung b WHERE b.id = bestellmail.buchung_id)")
    erg = {"buchungen": 0, "mails": 0}
    mails = _mails_je_nummer(con)
    if not mails:
        return erg
    erledigt = {(r[0], r[1]) for r in con.execute("SELECT buchung_id, nachricht_id FROM bestellmail")}
    for buchung_id, gefunden in _buchungen_mit_nummer(con):
        neu = 0
        for nummer in gefunden:
            for m in mails.get(nummer, []):
                if (buchung_id, m["nachricht_id"]) in erledigt:
                    continue
                erledigt.add((buchung_id, m["nachricht_id"]))
                dokument_id, entstanden = _anhaengen(con, m, buchung_id, zeitpunkt)
                if entstanden:
                    neu += 1
                con.execute("INSERT INTO bestellmail (buchung_id, nachricht_id, nummer, dokument_id)"
                            " VALUES (?, ?, ?, ?)", (buchung_id, m["nachricht_id"], nummer, dokument_id))
        if neu:
            erg["buchungen"] += 1
            erg["mails"] += neu
    return erg


def angehaengt_nach_mail(con) -> dict[str, list[dict]]:
    """Je Nachrichten-ID die Buchungen, an denen die Mail über die Bestellnummer (noch) hängt."""
    aus: dict[str, list[dict]] = {}
    for r in con.execute(
            "SELECT m.nachricht_id, m.nummer, b.id, b.datum, b.verwendungszweck, e.name AS empfaenger,"
            " (SELECT s.konto_id FROM split s JOIN konto k ON k.id = s.konto_id"
            "   WHERE s.buchung_id = b.id ORDER BY k.art IN ('girokonto','sparkonto','kreditkonto') DESC, s.id LIMIT 1)"
            "   AS konto_id"
            " FROM bestellmail m JOIN buchung b ON b.id = m.buchung_id"
            " JOIN dokument_buchung x ON x.dokument_id = m.dokument_id AND x.buchung_id = m.buchung_id"
            " LEFT JOIN empfaenger e ON e.id = b.empfaenger_id ORDER BY b.datum, b.id"):
        aus.setdefault(r["nachricht_id"], []).append({
            "id": r["id"], "datum": r["datum"], "konto_id": r["konto_id"], "empfaenger": r["empfaenger"],
            "verwendungszweck": r["verwendungszweck"], "nummer": r["nummer"],
            "warum": f"Die Bestellnummer „{r['nummer']}“ steht in der Buchung."})
    return aus


def laufen(config: KontorConfig, jetzt: dt.datetime) -> dict | None:
    if not config.mail_bestellnummer:
        return None
    zeit = jetzt.astimezone(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _SPERRE:
        con = db.verbinde(config.aktive_datenbank)
        try:
            with protokoll.protokolliert(con, "mail", "bestellmail_anhaengen", zeit):
                return zuordnen(con, zeit)
        except Exception:  # noqa: BLE001 - darf Abruf, Lauf und Planer nie scheitern lassen
            log.exception("Anhängen der Bestellmails fehlgeschlagen")
            return None
        finally:
            con.close()
