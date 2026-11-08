"""Änderungsprotokoll und Rückgängig (protokoll.md, Meilenstein 3).

Funktionsweise:

- Jede Operation auf dem Buchbestand läuft in genau einer Transaktion im
  Kontext ``protokolliert``. Temporäre Trigger (nur auf dieser Verbindung)
  merken sich, welche Objekte (Konto, Empfänger, Tag, Buchung, Regel,
  Verdacht, Abstimmung) berührt wurden und welche Umsatzkennungen
  hinzukamen oder wegfielen.
- Am Ende der Operation wird für jedes berührte Objekt die Protokollform
  *nachher* auf der schreibenden Verbindung und *vorher* auf einer zweiten,
  lesenden Verbindung bestimmt. Wegen WAL sieht diese den letzten
  bestätigten Stand, also genau den Zustand vor der Operation. Nur Objekte
  mit tatsächlich geänderter Form werden eingetragen (Nettowirkung).
- Rückgängig stellt die Protokollform ``vorher`` mit denselben IDs wieder
  her und ist selbst eine protokollierte Operation.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from typing import Any, Callable

from . import buch, db, regeln, vorlagen
from .validierung import ApiFehler

OBJEKTE = ("konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage")
QUELLEN = ("manuell", "import", "sync", "regeln", "umbuchung", "rueckgaengig", "lernmodell", "vorlage")

# Tabelle → (Objektart, Spalte mit der Objekt-ID)
_TABELLEN = {
    "konto": ("konto", "id"),
    "empfaenger": ("empfaenger", "id"),
    "empfaenger_alias": ("empfaenger", "empfaenger_id"),
    "tag": ("tag", "id"),
    "buchung": ("buchung", "id"),
    "split": ("buchung", "buchung_id"),
    "buchung_tag": ("buchung", "buchung_id"),
    "buchung_extern": ("buchung", "buchung_id"),
    "vorschlag": ("buchung", "buchung_id"),
    "regel": ("regel", "id"),
    "dublettenverdacht": ("verdacht", "id"),
    "verdacht_kandidat": ("verdacht", "verdacht_id"),
    "abstimmung": ("abstimmung", "id"),
    "vorlage": ("vorlage", "id"),
}

BESCHREIBUNG = {
    "konto_anlegen": "Konto angelegt", "konto_aendern": "Konto geändert", "konto_loeschen": "Konto gelöscht",
    "konto_loeschen_mit_buchungen": "Konto mit Buchungen gelöscht",
    "buchung_anlegen": "Buchung angelegt", "buchung_erfassen": "Buchung erfasst",
    "buchung_aendern": "Buchung geändert", "buchung_loeschen": "Buchung gelöscht",
    "splits_ersetzen": "Splits ersetzt", "kategorie_setzen": "Kategorie gesetzt",
    "mehrfach_kategorie": "Kategorie für mehrere Buchungen gesetzt",
    "mehrfach_tags": "Tags mehrerer Buchungen geändert",
    "vorschlag_entscheiden": "Vorschlag entschieden", "mehrfach_vorschlag": "Vorschläge entschieden",
    "tag_anlegen": "Tag angelegt", "tag_umbenennen": "Tag umbenannt", "tag_loeschen": "Tag gelöscht",
    "empfaenger_anlegen": "Empfänger angelegt", "empfaenger_aendern": "Empfänger geändert",
    "empfaenger_loeschen": "Empfänger gelöscht", "empfaenger_zusammenfuehren": "Empfänger zusammengeführt",
    "dublette_aufloesen": "Dublettenverdacht aufgelöst",
    "regel_anlegen": "Regel angelegt", "regel_aendern": "Regel geändert", "regel_loeschen": "Regel gelöscht",
    "abstimmung_anlegen": "Konto abgestimmt", "abstimmung_aufheben": "Abstimmung aufgehoben",
    "umbuchung_zusammenfuehren": "Umbuchung zusammengeführt", "umbuchung_erkennen": "Umbuchungen erkannt",
    "import_kmymoney": "KMyMoney-Import", "import_gnucash": "GnuCash-Import", "sync_kontozuordnung": "Synchronisation: Konten zugeordnet",
    "sync_konto": "Synchronisation: Umsätze eines Kontos übernommen", "regeln_anwenden": "Regeln angewendet",
    "rueckgaengig": "Rückgängig gemacht",
    "vorlage_anlegen": "Split-Vorlage angelegt", "vorlage_aendern": "Split-Vorlage geändert",
    "vorlage_loeschen": "Split-Vorlage gelöscht", "vorlagen_anwenden": "Split-Vorlagen angewendet",
    "lernmodell_anwenden": "Lernmodell angewendet",
}


# ================================================================ Trigger


def _vorbereiten(con: sqlite3.Connection) -> None:
    """Temporäre Merktabellen und Trigger dieser Verbindung (idempotent)."""
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _pr_beruehrt (objekt TEXT NOT NULL, objekt_id INTEGER NOT NULL,"
                " PRIMARY KEY (objekt, objekt_id)) WITHOUT ROWID")
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _pr_kennung (nr INTEGER PRIMARY KEY, kennung TEXT NOT NULL,"
                " neu INTEGER NOT NULL)")
    def merken(objekt: str, wert: str) -> str:
        # Kein „OR IGNORE“: die Konfliktbehandlung der äußeren Anweisung (z. B. UPSERT) würde sie überschreiben.
        return (f" INSERT INTO _pr_beruehrt SELECT '{objekt}', {wert} WHERE NOT EXISTS (SELECT 1 FROM _pr_beruehrt"
                f" WHERE objekt = '{objekt}' AND objekt_id = {wert});")

    for tabelle, (objekt, spalte) in _TABELLEN.items():
        con.execute(f"CREATE TEMP TRIGGER IF NOT EXISTS _pr_{tabelle}_i AFTER INSERT ON main.{tabelle} BEGIN"
                    f"{merken(objekt, 'NEW.' + spalte)} END")
        con.execute(f"CREATE TEMP TRIGGER IF NOT EXISTS _pr_{tabelle}_u AFTER UPDATE ON main.{tabelle} BEGIN"
                    f"{merken(objekt, 'OLD.' + spalte)}{merken(objekt, 'NEW.' + spalte)} END")
        con.execute(f"CREATE TEMP TRIGGER IF NOT EXISTS _pr_{tabelle}_d AFTER DELETE ON main.{tabelle} BEGIN"
                    f"{merken(objekt, 'OLD.' + spalte)} END")
    con.execute("CREATE TEMP TRIGGER IF NOT EXISTS _pr_kennung_i AFTER INSERT ON main.sync_kennung BEGIN"
                " INSERT INTO _pr_kennung (kennung, neu) VALUES (NEW.kennung, 1); END")
    con.execute("CREATE TEMP TRIGGER IF NOT EXISTS _pr_kennung_d AFTER DELETE ON main.sync_kennung BEGIN"
                " INSERT INTO _pr_kennung (kennung, neu) VALUES (OLD.kennung, 0); END")


def _leeren(con) -> None:
    con.execute("DELETE FROM _pr_beruehrt")
    con.execute("DELETE FROM _pr_kennung")


def _beruehrt(con) -> dict[str, list[int]]:
    aus: dict[str, list[int]] = defaultdict(list)
    for r in con.execute("SELECT objekt, objekt_id FROM _pr_beruehrt ORDER BY objekt, objekt_id"):
        aus[r["objekt"]].append(r["objekt_id"])
    return aus


def _kennungen_netto(con) -> tuple[list[str], list[str]]:
    erstes: dict[str, int] = {}
    letztes: dict[str, int] = {}
    for r in con.execute("SELECT kennung, neu FROM _pr_kennung ORDER BY nr"):
        erstes.setdefault(r["kennung"], r["neu"])
        letztes[r["kennung"]] = r["neu"]
    neu = sorted(k for k in letztes if erstes[k] == 1 and letztes[k] == 1)
    weg = sorted(k for k in letztes if erstes[k] == 0 and letztes[k] == 0)
    return neu, weg


# ============================================================ Protokollform


def _buchung_zustand(b: dict) -> dict:
    return {"id": b["id"], "datum": b["datum"], "empfaenger_id": b["empfaenger"]["id"] if b["empfaenger"] else None,
            "verwendungszweck": b["verwendungszweck"], "status": b["status"], "splits": b["splits"],
            "tag_ids": [t["id"] for t in b["tags"]], "extern_ids": b["extern_ids"], "vorschlag": b["vorschlag"],
            "gegen_iban": b["gegen_iban"]}


def formen(con, objekt: str, ids: list[int]) -> dict[int, dict]:
    """Protokollformen (protokoll.md 2) der vorhandenen Objekte unter ``ids``."""
    if not ids:
        return {}
    aus: dict[int, dict] = {}
    ids = sorted(set(ids))
    if objekt == "buchung":
        arten = defaultdict(lambda: "eigenkapital", buch.kontoarten(con))
        for teil in buch._stueckweise(ids):
            for b in buch.buchungen_laden(con, teil, art_von=arten):
                aus[b["id"]] = _buchung_zustand(b)
        return aus
    if objekt == "empfaenger":
        return {e["id"]: e for e in buch.empfaenger_laden(con, ids)}
    for teil in buch._stueckweise(ids):
        ph = buch._platzhalter(len(teil))
        if objekt == "konto":
            for r in con.execute(f"SELECT * FROM konto WHERE id IN ({ph})", teil):
                aus[r["id"]] = buch.konto_dict(r)
        elif objekt == "tag":
            for r in con.execute(f"SELECT id, name, extern_id FROM tag WHERE id IN ({ph})", teil):
                aus[r["id"]] = {"id": r["id"], "name": r["name"], "extern_id": r["extern_id"]}
        elif objekt == "regel":
            for r in con.execute(f"SELECT * FROM regel WHERE id IN ({ph})", teil):
                aus[r["id"]] = regeln.regel_dict(r)
        elif objekt == "verdacht":
            for r in con.execute(f"SELECT * FROM dublettenverdacht WHERE id IN ({ph})", teil).fetchall():
                aus[r["id"]] = buch._verdacht_dict(con, r)
        elif objekt == "abstimmung":
            for r in con.execute(f"SELECT * FROM abstimmung WHERE id IN ({ph})", teil):
                aus[r["id"]] = abstimmung_dict(r)
        elif objekt == "vorlage":
            for r in con.execute(f"SELECT * FROM vorlage WHERE id IN ({ph})", teil):
                aus[r["id"]] = vorlagen.vorlage_dict(r)
        else:  # pragma: no cover
            raise AssertionError(objekt)
    return aus


def abstimmung_dict(r) -> dict:
    return {"id": r["id"], "konto_id": r["konto_id"], "stichtag": r["stichtag"], "saldo": r["saldo"],
            "erstellt_am": r["erstellt_am"]}


def _pfad(con) -> str:
    for r in con.execute("PRAGMA database_list"):
        if r["name"] == "main":
            return r["file"]
    raise AssertionError("keine Hauptdatenbank")  # pragma: no cover


def _nettowirkung(con) -> list[dict]:
    """Einträge (sortiert nach Objektart in der Reihenfolge von 2, dann ID)."""
    beruehrt = _beruehrt(con)
    if not beruehrt:
        return []
    leser = db.verbinde(_pfad(con))
    try:
        eintraege = []
        for objekt in OBJEKTE:
            ids = beruehrt.get(objekt)
            if not ids:
                continue
            nachher = formen(con, objekt, ids)
            vorher = formen(leser, objekt, ids)
            for oid in sorted(ids):
                v, n = vorher.get(oid), nachher.get(oid)
                if v == n:
                    continue
                art = "angelegt" if v is None else "geloescht" if n is None else "geaendert"
                eintraege.append({"objekt": objekt, "objekt_id": oid, "art": art, "vorher": v, "nachher": n})
        return eintraege
    finally:
        leser.close()


def _speichern(con, quelle: str, aktion: str, zeitpunkt: str, gruppe: str | None, eintraege: list[dict],
               rueckgaengig_von: list[int], beschreibung: str | None) -> int:
    neu, weg = _kennungen_netto(con)
    text = beschreibung or BESCHREIBUNG.get(aktion, aktion)
    anzahl = len(eintraege)
    text = f"{text} ({anzahl} {'Objekt' if anzahl == 1 else 'Objekte'})"
    aid = con.execute(
        "INSERT INTO aenderung (zeitpunkt, quelle, aktion, beschreibung, gruppe, rueckgaengig_von, kennungen_neu,"
        " kennungen_weg) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (zeitpunkt, quelle, aktion, text, gruppe, json.dumps(sorted(rueckgaengig_von)), json.dumps(neu),
         json.dumps(weg))).lastrowid
    con.executemany(
        "INSERT INTO aenderung_eintrag (aenderung_id, position, objekt, objekt_id, art, vorher, nachher)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(aid, i, e["objekt"], e["objekt_id"], e["art"],
          None if e["vorher"] is None else json.dumps(e["vorher"], ensure_ascii=False),
          None if e["nachher"] is None else json.dumps(e["nachher"], ensure_ascii=False))
         for i, e in enumerate(eintraege)])
    return aid


class Kontext:
    """Wird im ``with protokolliert(...)``-Block zurückgegeben; Felder können noch gesetzt werden."""

    def __init__(self, gruppe: str | None, beschreibung: str | None) -> None:
        self.gruppe = gruppe
        self.beschreibung = beschreibung
        self.rueckgaengig_von: list[int] = []
        self.aenderung_id: int | None = None
        self.eintraege: list[dict] = []
        self.pruefung: Callable[[list[dict]], None] | None = None
        # Wird nach dem Speichern der Änderung (in derselben Transaktion) mit ihrer ID aufgerufen.
        self.danach: list[Callable[[int], None]] = []


@contextlib.contextmanager
def protokolliert(con, quelle: str, aktion: str, zeitpunkt: str, gruppe: str | None = None,
                  beschreibung: str | None = None) -> Iterator[Kontext]:
    """Eine Transaktion; erzeugt genau dann eine Änderung, wenn sich eine Protokollform ändert."""
    k = Kontext(gruppe, beschreibung)
    with db.transaktion(con):
        _vorbereiten(con)
        _leeren(con)
        yield k
        eintraege = _nettowirkung(con)
        if k.pruefung is not None:
            k.pruefung(eintraege)
        k.eintraege = eintraege
        if eintraege or k.rueckgaengig_von:
            k.aenderung_id = _speichern(con, quelle, aktion, zeitpunkt, k.gruppe, eintraege, k.rueckgaengig_von,
                                        k.beschreibung)
            for a in k.rueckgaengig_von:
                _durch_setzen(con, a, k.aenderung_id)
            for f in k.danach:
                f(k.aenderung_id)
        _leeren(con)


def ausfuehren(con, quelle: str, aktion: str, zeitpunkt: str, f: Callable, *args, gruppe: str | None = None):
    """Führt ``f(con, *args)`` protokolliert aus und gibt sein Ergebnis zurück."""
    with protokolliert(con, quelle, aktion, zeitpunkt, gruppe) as k:
        erg = f(con, *args)
    return erg if not isinstance(erg, _MitAenderung) else erg.fertig(k.aenderung_id)


class _MitAenderung:
    """Ergebnis, das die ID der entstandenen Änderung nachträglich erhält."""

    def __init__(self, daten: dict, feld: str = "aenderung_id") -> None:
        self.daten = daten
        self.feld = feld

    def fertig(self, aid: int | None) -> dict:
        return {**self.daten, self.feld: aid}


def mit_aenderung_id(daten: dict) -> _MitAenderung:
    return _MitAenderung(daten)


# ============================================================ Wirksamkeit


def _von(con, aid: int) -> list[int]:
    r = con.execute("SELECT rueckgaengig_von FROM aenderung WHERE id = ?", (aid,)).fetchone()
    return json.loads(r["rueckgaengig_von"]) if r else []


def _durch_setzen(con, aid: int, wert: int | None) -> None:
    """protokoll.md 6.5; wird eine Änderung (un)wirksam, ändern sich die von ihr rückgängig gemachten."""
    r = con.execute("SELECT rueckgaengig_durch FROM aenderung WHERE id = ?", (aid,)).fetchone()
    if r is None or r["rueckgaengig_durch"] == wert:
        return
    con.execute("UPDATE aenderung SET rueckgaengig_durch = ? WHERE id = ?", (wert, aid))
    war, ist = r["rueckgaengig_durch"] is None, wert is None
    if war != ist:
        for k in _von(con, aid):
            _durch_setzen(con, k, aid if ist else None)


# ================================================================== Lesen


def _aenderungen_dicts(con, zeilen: list) -> list[dict]:
    if not zeilen:
        return []
    ids = [z["id"] for z in zeilen]
    eintraege: dict[int, list[dict]] = defaultdict(list)
    for teil in buch._stueckweise(ids):
        for e in con.execute(f"SELECT * FROM aenderung_eintrag WHERE aenderung_id IN ({buch._platzhalter(len(teil))})"
                             " ORDER BY aenderung_id, position", teil):
            eintraege[e["aenderung_id"]].append({
                "objekt": e["objekt"], "objekt_id": e["objekt_id"], "art": e["art"],
                "vorher": None if e["vorher"] is None else json.loads(e["vorher"]),
                "nachher": None if e["nachher"] is None else json.loads(e["nachher"])})
    return [{"id": z["id"], "zeitpunkt": z["zeitpunkt"], "quelle": z["quelle"], "aktion": z["aktion"],
             "beschreibung": z["beschreibung"], "gruppe": z["gruppe"], "eintraege": eintraege[z["id"]],
             "rueckgaengig_von": json.loads(z["rueckgaengig_von"]), "rueckgaengig_durch": z["rueckgaengig_durch"]}
            for z in zeilen]


def aenderung_lesen(con, aid: int) -> dict:
    z = con.execute("SELECT * FROM aenderung WHERE id = ?", (buch.sichere_id(aid),)).fetchall()
    if not z:
        raise buch.nicht_gefunden("Die Änderung")
    return _aenderungen_dicts(con, z)[0]


def aenderungen_liste(con, f: dict) -> dict:
    bed, par = [], []
    if f.get("quelle"):
        q = sorted(set(f["quelle"]))
        bed.append(f"a.quelle IN ({buch._platzhalter(len(q))})")
        par.extend(q)
    if f.get("aktion") is not None:
        bed.append("a.aktion = ?")
        par.append(f["aktion"])
    if f.get("gruppe") is not None:
        bed.append("a.gruppe = ?")
        par.append(f["gruppe"])
    if f.get("objekt") is not None:
        if f.get("objekt_id") is not None:
            bed.append("EXISTS (SELECT 1 FROM aenderung_eintrag e WHERE e.aenderung_id = a.id AND e.objekt = ?"
                       " AND e.objekt_id = ?)")
            par.extend([f["objekt"], buch.sichere_id(f["objekt_id"])])
        else:
            bed.append("EXISTS (SELECT 1 FROM aenderung_eintrag e WHERE e.aenderung_id = a.id AND e.objekt = ?)")
            par.append(f["objekt"])
    if f.get("wirksam") is not None:
        bed.append("a.rueckgaengig_durch IS " + ("NULL" if f["wirksam"] else "NOT NULL"))
    wo = (" WHERE " + " AND ".join(bed)) if bed else ""
    gesamt = con.execute(f"SELECT COUNT(*) AS n FROM aenderung a{wo}", par).fetchone()["n"]
    seite, pro_seite = f.get("seite") or 1, f.get("pro_seite") or 50
    offset = (seite - 1) * pro_seite
    zeilen = []
    if offset < gesamt:
        zeilen = con.execute(f"SELECT * FROM aenderung a{wo} ORDER BY a.id DESC LIMIT ? OFFSET ?",
                             par + [pro_seite, offset]).fetchall()
    return {"eintraege": _aenderungen_dicts(con, zeilen), "gesamt": gesamt, "seite": seite, "pro_seite": pro_seite}


# ============================================================== Rückgängig


def _konflikt(meldung: str) -> ApiFehler:
    return ApiFehler(409, "rueckgaengig_konflikt", meldung)


def _entfernen(con, objekt: str, oid: int, schritt: set[tuple[str, int]]) -> None:
    if objekt == "konto":
        con.execute("DELETE FROM konto WHERE id = ?", (oid,))
    elif objekt == "empfaenger":
        con.execute("DELETE FROM empfaenger WHERE id = ?", (oid,))
    elif objekt == "tag":
        # Ein Tag, den Buchungen außerhalb dieser Änderung tragen, darf nicht verschwinden (Bezug).
        for r in con.execute("SELECT buchung_id FROM buchung_tag WHERE tag_id = ?", (oid,)).fetchall():
            if ("buchung", r["buchung_id"]) not in schritt:
                raise _konflikt("Ein Tag wird inzwischen von einer Buchung verwendet.")
        con.execute("DELETE FROM tag WHERE id = ?", (oid,))
    elif objekt == "buchung":
        con.execute("DELETE FROM buchung WHERE id = ?", (oid,))
    elif objekt == "regel":
        con.execute("DELETE FROM regel WHERE id = ?", (oid,))
    elif objekt == "verdacht":
        con.execute("DELETE FROM dublettenverdacht WHERE id = ?", (oid,))
    elif objekt == "abstimmung":
        con.execute("DELETE FROM abstimmung WHERE id = ?", (oid,))
    elif objekt == "vorlage":
        con.execute("DELETE FROM vorlage WHERE id = ?", (oid,))


def _einfuegen(con, objekt: str, f: dict) -> None:
    if objekt == "konto":
        con.execute("INSERT INTO konto (id, name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz, extern_id)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f["id"], f["name"], f["art"], f["eltern_id"], f["iban"], 1 if f["geschlossen"] else 0,
                     f["eroeffnet_am"], f["notiz"], f["extern_id"]))
    elif objekt == "empfaenger":
        con.execute("INSERT INTO empfaenger (id, name, extern_id, standardkategorie_id) VALUES (?, ?, ?, ?)",
                    (f["id"], f["name"], f["extern_id"], f["standardkategorie_id"]))
        con.executemany("INSERT INTO empfaenger_alias (empfaenger_id, alias, ekey) VALUES (?, ?, ?)",
                        [(f["id"], a, buch.ekey(a)) for a in f["aliase"]])
    elif objekt == "tag":
        con.execute("INSERT INTO tag (id, name, name_cf, extern_id) VALUES (?, ?, ?, ?)",
                    (f["id"], f["name"], f["name"].casefold(), f["extern_id"]))
    elif objekt == "buchung":
        con.execute("INSERT INTO buchung (id, datum, empfaenger_id, verwendungszweck, status, gegen_iban)"
                    " VALUES (?, ?, ?, ?, ?, ?)", (f["id"], f["datum"], f["empfaenger_id"], f["verwendungszweck"],
                                                   f["status"], f["gegen_iban"]))
        con.executemany("INSERT INTO split (id, buchung_id, position, konto_id, betrag, memo, abstimmung_id)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [(s["id"], f["id"], i, s["konto_id"], s["betrag"], s["memo"], s["abstimmung_id"])
                         for i, s in enumerate(f["splits"])])
        con.executemany("INSERT INTO buchung_tag (buchung_id, tag_id) VALUES (?, ?)",
                        [(f["id"], t) for t in f["tag_ids"]])
        con.executemany("INSERT INTO buchung_extern (buchung_id, extern_id) VALUES (?, ?)",
                        [(f["id"], e) for e in f["extern_ids"]])
        v = f["vorschlag"]
        if v is not None:
            con.execute("INSERT INTO vorschlag (buchung_id, kategorie_id, regel_id, quelle, vorher_konto_id,"
                        " sicherheit) VALUES (?, ?, ?, ?, ?, ?)",
                        (f["id"], v["kategorie_id"], v["regel_id"], v["quelle"], v["vorher_konto_id"],
                         v.get("sicherheit")))
    elif objekt == "regel":
        con.execute("INSERT INTO regel (id, name, aktiv, prioritaet, kategorie_id, bedingungen) VALUES (?, ?, ?, ?, ?, ?)",
                    (f["id"], f["name"], 1 if f["aktiv"] else 0, f["prioritaet"], f["kategorie_id"],
                     json.dumps(f["bedingungen"], ensure_ascii=False)))
    elif objekt == "verdacht":
        con.execute("INSERT INTO dublettenverdacht (id, buchung_id, grund, status, erstellt_am) VALUES (?, ?, ?, ?, ?)",
                    (f["id"], f["buchung_id"], f["grund"], f["status"], f["erstellt_am"]))
        con.executemany("INSERT INTO verdacht_kandidat (verdacht_id, buchung_id) VALUES (?, ?)",
                        [(f["id"], b) for b in f["kandidat_ids"]])
    elif objekt == "abstimmung":
        con.execute("INSERT INTO abstimmung (id, konto_id, stichtag, saldo, erstellt_am) VALUES (?, ?, ?, ?, ?)",
                    (f["id"], f["konto_id"], f["stichtag"], f["saldo"], f["erstellt_am"]))
    elif objekt == "vorlage":
        vorlagen.einfuegen(con, f)


def _eintraege_von(con, aid: int) -> list[dict]:
    return aenderung_lesen(con, aid)["eintraege"]


def _schritt(con, aid: int) -> set[tuple[str, int]]:
    """Macht eine Änderung auf dem aktuellen Zwischenstand rückgängig (6.1 Schritte 3–4)."""
    eintraege = _eintraege_von(con, aid)
    je_objekt: dict[str, list[dict]] = defaultdict(list)
    for e in eintraege:
        je_objekt[e["objekt"]].append(e)
    for objekt, es in je_objekt.items():
        aktuell = formen(con, objekt, [e["objekt_id"] for e in es])
        for e in es:
            if aktuell.get(e["objekt_id"]) != e["nachher"]:
                raise _konflikt("Eine spätere Änderung hat dasselbe Objekt verändert.")
    schritt = {(e["objekt"], e["objekt_id"]) for e in eintraege}
    for e in eintraege:
        if e["nachher"] is None:
            continue
        if e["objekt"] == "tag" and e["vorher"] is not None:
            # Umbenennen zurücknehmen: Zeile bleibt (Zuordnungen zu Buchungen), Name erst vorläufig freigeben.
            con.execute("UPDATE tag SET name_cf = ? WHERE id = ?", (f"\x00{e['objekt_id']}", e["objekt_id"]))
            continue
        _entfernen(con, e["objekt"], e["objekt_id"], schritt)
    for objekt in OBJEKTE:
        for e in je_objekt.get(objekt, []):
            v = e["vorher"]
            if v is None:
                continue
            if objekt == "tag" and e["nachher"] is not None:
                con.execute("UPDATE tag SET name = ?, name_cf = ?, extern_id = ? WHERE id = ?",
                            (v["name"], v["name"].casefold(), v["extern_id"], v["id"]))
                continue
            _einfuegen(con, objekt, v)
    r = con.execute("SELECT kennungen_neu, kennungen_weg FROM aenderung WHERE id = ?", (aid,)).fetchone()
    con.executemany("DELETE FROM sync_kennung WHERE kennung = ?", [(k,) for k in json.loads(r["kennungen_neu"])])
    con.executemany("INSERT OR IGNORE INTO sync_kennung (kennung) VALUES (?)",
                    [(k,) for k in json.loads(r["kennungen_weg"])])
    return schritt


def _fehlt(con, sql: str) -> bool:
    return con.execute(sql + " LIMIT 1").fetchone() is not None


def bezuege_pruefen(con) -> None:
    """protokoll.md 6.1 Schritt 5 auf dem gesamten Buchbestand."""
    pruefungen = (
        "SELECT 1 FROM split s WHERE NOT EXISTS (SELECT 1 FROM konto k WHERE k.id = s.konto_id)",
        "SELECT 1 FROM split s WHERE s.abstimmung_id IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM abstimmung a WHERE a.id = s.abstimmung_id)",
        "SELECT 1 FROM split s WHERE NOT EXISTS (SELECT 1 FROM buchung b WHERE b.id = s.buchung_id)",
        "SELECT 1 FROM buchung b WHERE b.empfaenger_id IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM empfaenger e WHERE e.id = b.empfaenger_id)",
        "SELECT 1 FROM buchung_tag bt WHERE NOT EXISTS (SELECT 1 FROM tag t WHERE t.id = bt.tag_id)",
        "SELECT 1 FROM konto k WHERE k.eltern_id IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM konto e WHERE e.id = k.eltern_id)",
        "SELECT 1 FROM regel r WHERE NOT EXISTS (SELECT 1 FROM konto k WHERE k.id = r.kategorie_id)",
        "SELECT 1 FROM vorschlag v WHERE v.regel_id IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM regel r WHERE r.id = v.regel_id)",
        "SELECT 1 FROM empfaenger e WHERE e.standardkategorie_id IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM konto k WHERE k.id = e.standardkategorie_id)",
        "SELECT 1 FROM abstimmung a WHERE NOT EXISTS (SELECT 1 FROM konto k WHERE k.id = a.konto_id)",
        "SELECT 1 FROM dublettenverdacht d WHERE d.status = 'offen'"
        " AND NOT EXISTS (SELECT 1 FROM buchung b WHERE b.id = d.buchung_id)",
        "SELECT 1 FROM dublettenverdacht d JOIN verdacht_kandidat vk ON vk.verdacht_id = d.id"
        " WHERE d.status = 'offen' AND NOT EXISTS (SELECT 1 FROM buchung b WHERE b.id = vk.buchung_id)",
    )
    for sql in pruefungen:
        if _fehlt(con, sql):
            raise _konflikt("Der wiederhergestellte Zustand verweist auf nicht mehr vorhandene Objekte.")
    konten = {r["id"] for r in con.execute("SELECT id FROM konto")}
    for r in con.execute("SELECT bedingungen FROM regel"):
        for b in json.loads(r["bedingungen"]):
            if b.get("feld") == "konto_id" and b.get("wert") not in konten:
                raise _konflikt("Eine Regel verweist auf ein nicht mehr vorhandenes Konto.")
    for v in vorlagen.vorlagen_liste(con):  # M4 (protokoll.md 9.1)
        if any(t["kategorie_id"] not in konten for t in v["teile"]) or any(
                b["feld"] == "konto_id" and b["wert"] not in konten for b in v["bedingungen"]):
            raise _konflikt("Eine Split-Vorlage verweist auf ein nicht mehr vorhandenes Konto.")
    eltern = {r["id"]: r["eltern_id"] for r in con.execute("SELECT id, eltern_id FROM konto")}
    for k in eltern:
        gesehen, e = {k}, eltern[k]
        while e is not None:
            if e in gesehen:
                raise _konflikt("Die Kontenhierarchie enthielte einen Zyklus.")
            gesehen.add(e)
            e = eltern.get(e)


def rueckgaengig(con, ids: list[int], zeitpunkt: str) -> dict:
    """Macht die Änderungen ``ids`` (alle wirksam) als eine neue Änderung rückgängig (6.1, 6.2)."""
    try:
        with protokolliert(con, "rueckgaengig", "rueckgaengig", zeitpunkt) as k:
            con.execute("PRAGMA defer_foreign_keys = ON")
            erlaubt: set[tuple[str, int]] = set()
            for aid in sorted(ids, reverse=True):
                erlaubt |= _schritt(con, aid)
            _sync_zustand_nach_rueckgaengig(con, ids)
            bezuege_pruefen(con)
            k.rueckgaengig_von = sorted(ids)

            def pruefen(eintraege: list[dict]) -> None:
                if any((e["objekt"], e["objekt_id"]) not in erlaubt for e in eintraege):
                    raise _konflikt("Rückgängig würde Objekte außerhalb der Änderung verändern.")
            k.pruefung = pruefen
    except sqlite3.IntegrityError:
        raise _konflikt("Der wiederhergestellte Zustand verletzt eine Eindeutigkeits- oder Bezugsregel.") from None
    return aenderung_lesen(con, k.aenderung_id)


def _sync_zustand_nach_rueckgaengig(con, ids: list[int]) -> None:
    """protokoll.md 6.4: Entfernt eine rückgängig gemachte Kontozuordnung ein Konto, entfällt dessen Eintrag in
    /api/sync/konten – außer die Zuordnung hat ein gelöschtes Bankkonto wiederhergestellt
    (synchronisation.md 16.2 Regel 3); dann bleibt er (Status konto_fehlt, ohne Entscheidung)."""
    for aid in ids:
        r = con.execute("SELECT aktion FROM aenderung WHERE id = ?", (aid,)).fetchone()
        if r is None or r["aktion"] != "sync_kontozuordnung":
            continue
        wieder = {z["iban"] for z in con.execute("SELECT iban FROM sync_wiederherstellung WHERE aenderung_id = ?",
                                                 (aid,))}
        for e in _eintraege_von(con, aid):
            if e["objekt"] != "konto" or e["art"] != "angelegt" or not e["nachher"].get("iban"):
                continue
            kid, iban = e["objekt_id"], e["nachher"]["iban"]
            if con.execute("SELECT 1 FROM konto WHERE id = ?", (kid,)).fetchone():
                continue
            if iban in wieder:
                con.execute("UPDATE sync_konto_zustand SET entscheidung = NULL, entscheidung_buchungen = NULL"
                            " WHERE iban = ?", (iban,))
            else:
                con.execute("DELETE FROM sync_konto_zustand WHERE iban = ? AND konto_id = ?", (iban, kid))


def _wirksam(con, aid: int) -> bool:
    r = con.execute("SELECT rueckgaengig_durch FROM aenderung WHERE id = ?", (aid,)).fetchone()
    return r is not None and r["rueckgaengig_durch"] is None


def einzeln_rueckgaengig(con, aid: int, zeitpunkt: str) -> dict:
    aenderung_lesen(con, aid)  # 404
    if not _wirksam(con, aid):
        raise ApiFehler(409, "bereits_rueckgaengig", "Die Änderung ist bereits rückgängig gemacht.")
    return rueckgaengig(con, [aid], zeitpunkt)


def mehrere_rueckgaengig(con, d: dict, zeitpunkt: str) -> dict:
    if "aenderung_ids" in d:
        ids = d["aenderung_ids"]
        vorhanden = set()
        for teil in buch._stueckweise(sorted(set(ids))):
            vorhanden |= {r["id"] for r in con.execute(
                f"SELECT id FROM aenderung WHERE id IN ({buch._platzhalter(len(teil))})",
                [buch.sichere_id(x) for x in teil])}
        fehlend = sorted(set(ids) - vorhanden)
        if fehlend:
            raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Änderungen.", {"aenderung_ids": fehlend})
        nicht = sorted(a for a in ids if not _wirksam(con, a))
        if nicht:
            raise ApiFehler(409, "bereits_rueckgaengig", "Einige Änderungen sind bereits rückgängig gemacht.",
                            {"aenderung_ids": nicht})
        return rueckgaengig(con, ids, zeitpunkt)
    zeilen = con.execute("SELECT id, rueckgaengig_durch FROM aenderung WHERE gruppe = ?", (d["gruppe"],)).fetchall()
    if not zeilen:
        raise ApiFehler(422, "referenz_unbekannt", "Keine Änderung mit dieser Gruppe.")
    ids = [z["id"] for z in zeilen if z["rueckgaengig_durch"] is None]
    if not ids:
        raise ApiFehler(409, "bereits_rueckgaengig", "Alle Änderungen dieser Gruppe sind bereits rückgängig gemacht.")
    return rueckgaengig(con, ids, zeitpunkt)


__all__: list[Any] = ["protokolliert", "ausfuehren", "rueckgaengig", "aenderungen_liste", "aenderung_lesen"]
