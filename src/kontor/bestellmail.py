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
import email
import hashlib
import logging
import threading

from . import anbieter, db, dokumente, protokoll
from .config import KontorConfig
from .validierung import ApiFehler

log = logging.getLogger("kontor.bestellmail")
_SPERRE = threading.Lock()

def _mit_kennung() -> list:
    """Anbieter, deren Beschreibung eine Kennung im Verwendungszweck nennt (D-230; bisher nur die
    Amazon-Bestellnummer)."""
    return [a for a in anbieter.aktive() if a.bank.kennung is not None]


def nummern(*texte: str | None) -> list[str]:
    """Kennungen aller Anbieter in den Texten (z. B. Amazon-Bestellnummern), in der Reihenfolge des ersten
    Auftretens je Anbieter. Bankzeilen brechen die Nummer manchmal um; Anbieter mit ``ohne_leerraum`` werden
    deshalb zusätzlich ohne Leerraum gesucht."""
    aus: list[str] = []
    for a in _mit_kennung():
        for n in a.kennungen(*texte):
            if n not in aus:
                aus.append(n)
    return aus


def nummern_der_mail(betreff: str | None, text: str | None, roh: bytes | None,
                     absender: str | None = None) -> list[str]:
    """Kennungen einer Mail (Anbieter ohne ``alle_mails`` nur in ihren eigenen Mails): Betreff, gespiegelter Text und – mit Rohfassung – alle Textteile im Quelltext.
    Der gespiegelte Text ist nur der erste Klartextteil; Amazon nennt die Nummer oft nur im HTML-Teil oder in
    den Adressen der Verweise (``orderId=…``), die beim Entfernen der Auszeichnung verloren gehen."""
    texte = [betreff, text]
    if roh:
        try:
            for teil in email.message_from_bytes(bytes(roh)).walk():
                if teil.get_content_maintype() != "text":
                    continue
                inhalt = teil.get_payload(decode=True) or b""
                try:
                    texte.append(inhalt.decode(teil.get_content_charset() or "utf-8", errors="replace"))
                except LookupError:
                    texte.append(inhalt.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001 - eine unlesbare Rohfassung zählt nur mit Betreff und Text
            pass
    aus: list[str] = []
    for a in _mit_kennung():
        if not a.bank.alle_mails and not a.gehoert(absender or "", betreff or ""):
            continue
        for n in a.kennungen(*texte, mit_leerraum_variante=False):
            if n not in aus:
                aus.append(n)
    return aus


def _mails_je_nummer(con) -> dict[str, list]:
    """Bestellnummer → gespiegelte Mails (je Nachrichten-ID einmal, auch bei zwei Postfächern). Jede Mail wird
    nur einmal durchsucht; das Ergebnis steht in ``bestellmail_nummer`` (leere Nummer = durchsucht)."""
    con.execute("DELETE FROM bestellmail_nummer WHERE NOT EXISTS"
                " (SELECT 1 FROM mail_nachricht m WHERE m.id = bestellmail_nummer.spiegel_id)")
    # D-230: Mit geänderten Mustern (neuer Anbieter, geänderte Beschreibung) werden alle Mails neu durchsucht
    stand = anbieter.signatur(tuple(_mit_kennung()))
    gemerkt = con.execute("SELECT wert FROM meta WHERE schluessel = 'bestellmail_muster'").fetchone()
    if gemerkt is None or gemerkt["wert"] != stand:
        con.execute("DELETE FROM bestellmail_nummer")
        con.execute("INSERT INTO meta (schluessel, wert) VALUES ('bestellmail_muster', ?)"
                    " ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert", (stand,))
    neu = con.execute("SELECT id, absender, betreff, text, roh FROM mail_nachricht WHERE id NOT IN"
                      " (SELECT spiegel_id FROM bestellmail_nummer)").fetchall()
    for r in neu:
        con.executemany("INSERT INTO bestellmail_nummer (spiegel_id, nummer) VALUES (?, ?)",
                        [(r["id"], n) for n in ["", *nummern_der_mail(r["betreff"], r["text"], r["roh"],
                                                                      r["absender"])]])
    aus: dict[str, list] = {}
    gesehen: set[tuple[str, str]] = set()
    for r in con.execute("SELECT x.nummer, m.id, m.nachricht_id FROM bestellmail_nummer x"
                         " JOIN mail_nachricht m ON m.id = x.spiegel_id WHERE x.nummer <> ''"
                         " ORDER BY m.empfangen, m.id"):
        if (r["nummer"], r["nachricht_id"]) not in gesehen:
            gesehen.add((r["nummer"], r["nachricht_id"]))
            aus.setdefault(r["nummer"], []).append(r)
    return aus


def _buchungen_mit_nummer(con) -> list[tuple[int, list[str]]]:
    aus = []
    # Grobfilter in SQL (bank.glob), damit nur Texte mit einer möglichen Kennung gelesen werden; nennt ein Anbieter
    # keinen, werden alle Buchungen gelesen
    globs = [a.bank.glob for a in _mit_kennung()]
    if not globs:
        return aus
    wo, par = "", []
    if all(globs):
        wo = " WHERE " + " OR ".join("b.verwendungszweck GLOB ? OR e.name GLOB ?" for _ in globs)
        par = [g for g in globs for _ in (0, 1)]
    for r in con.execute("SELECT b.id, b.verwendungszweck, e.name FROM buchung b"
                         " LEFT JOIN empfaenger e ON e.id = b.empfaenger_id" + wo + " ORDER BY b.id", par):
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
            "   AS konto_id,"
            " (SELECT SUM(s.betrag) FROM split s JOIN konto k ON k.id = s.konto_id"
            "   WHERE s.buchung_id = b.id AND k.art IN ('girokonto','sparkonto','kreditkonto')) AS betrag"
            " FROM bestellmail m JOIN buchung b ON b.id = m.buchung_id"
            " JOIN dokument_buchung x ON x.dokument_id = m.dokument_id AND x.buchung_id = m.buchung_id"
            " LEFT JOIN empfaenger e ON e.id = b.empfaenger_id ORDER BY b.datum, b.id"):
        aus.setdefault(r["nachricht_id"], []).append({
            "id": r["id"], "datum": r["datum"], "konto_id": r["konto_id"], "empfaenger": r["empfaenger"],
            "verwendungszweck": r["verwendungszweck"], "nummer": r["nummer"],
            # Betrag auf den Bestandskonten (D-236: steht in der Mailliste vor dem Namen); None ohne Bestandskonto
            "betrag": r["betrag"],
            "warum": (f"Die Bestellnummer „{r['nummer']}“ steht in der Buchung." if r["nummer"]
                      else "Von Hand zugeordnet.")})
    return aus


def von_hand_vorhanden(con) -> bool:
    return con.execute("SELECT 1 FROM bestellmail WHERE nummer = '' LIMIT 1").fetchone() is not None


def von_hand(con, nachricht_db_id: int, buchung_id: int, zeitpunkt: str) -> dict:
    """D-226: eine gespiegelte Mail von Hand als Dokument an eine Buchung hängen. Der Vermerk in ``bestellmail``
    (leere Nummer) lässt das Mail-Blatt die Zuordnung zeigen; er entfällt mit dem Dokument an der Buchung."""
    from . import buch
    r = con.execute("SELECT nachricht_id FROM mail_nachricht WHERE id = ?", (buch.sichere_id(nachricht_db_id),)).fetchone()
    if r is None:
        raise buch.nicht_gefunden("Die E-Mail")
    dok = dokumente.aus_mail(con, nachricht_db_id, [buchung_id], zeitpunkt)
    con.execute("INSERT INTO bestellmail (buchung_id, nachricht_id, nummer, dokument_id) VALUES (?, ?, '', ?)"
                " ON CONFLICT(buchung_id, nachricht_id) DO UPDATE SET dokument_id = excluded.dokument_id",
                (buchung_id, r["nachricht_id"], dok["id"]))
    return dok


def laufen(config: KontorConfig, jetzt: dt.datetime) -> dict | None:
    if not config.mail_bestellnummer:
        return None
    anbieter.einrichten(config.anbieter_verzeichnis)
    zeit = jetzt.astimezone(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _SPERRE:
        con = db.verbinde(config.aktive_datenbank)
        try:
            with protokoll.protokolliert(con, "mail", "bestellmail_anhaengen", zeit):
                erg = zuordnen(con, zeit)
            log.info("Bestellmails: %d Mails an %d Buchungen gehängt", erg["mails"], erg["buchungen"])
            return erg
        except Exception:  # noqa: BLE001 - darf Abruf, Lauf und Planer nie scheitern lassen
            log.exception("Anhängen der Bestellmails fehlgeschlagen")
            return None
        finally:
            con.close()
