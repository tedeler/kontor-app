"""Fachlogik des Buchs: Konten, Buchungen, Splits, Tags, Empfänger, Dubletten.

Alle Funktionen arbeiten auf einer offenen SQLite-Verbindung; Transaktionen
steuert der Aufrufer (``db.transaktion``). Fehler werden als ``ApiFehler`` mit
den Codes aus openapi.yaml gemeldet.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any, Iterable

from .text import ekey, iban_gueltig, iban_normalisieren, norm
from .validierung import INT64_MAX, ApiFehler

BESTAND = ("girokonto", "sparkonto", "kreditkonto")
KATEGORIEARTEN = ("aufwand", "ertrag")
KLASSE = {"girokonto": "bestand", "sparkonto": "bestand", "kreditkonto": "bestand",
          "aufwand": "aufwand", "ertrag": "ertrag", "eigenkapital": "eigenkapital"}
UEBERGAENGE = {("importiert", "bestaetigt"), ("bestaetigt", "abgeglichen"), ("vorlaeufig", "abgeglichen")}


def nicht_gefunden(was: str) -> ApiFehler:
    return ApiFehler(404, "nicht_gefunden", f"{was} wurde nicht gefunden.")


def sichere_id(x: int) -> int:
    """IDs außerhalb des SQLite-Bereichs können nicht existieren."""
    return x if -INT64_MAX <= x <= INT64_MAX else -1


# ===================================================================== Konten


def konto_dict(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"], "name": r["name"], "art": r["art"], "eltern_id": r["eltern_id"],
        "iban": r["iban"], "waehrung": "EUR", "geschlossen": bool(r["geschlossen"]),
        "eroeffnet_am": r["eroeffnet_am"], "notiz": r["notiz"], "extern_id": r["extern_id"],
        "ist_kategorie": r["art"] in KATEGORIEARTEN,
    }


def konto_zeile(con, konto_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM konto WHERE id = ?", (sichere_id(konto_id),)).fetchone()


def konto_lesen(con, konto_id: int) -> dict:
    r = konto_zeile(con, konto_id)
    if r is None:
        raise nicht_gefunden("Das Konto")
    return konto_dict(r)


def konten_liste(con, arten: list[str] | None = None, geschlossen: bool | None = None) -> list[dict]:
    sql = "SELECT * FROM konto"
    bed, par = [], []
    if arten:
        bed.append("art IN (%s)" % ",".join("?" * len(arten)))
        par.extend(arten)
    if geschlossen is not None:
        bed.append("geschlossen = ?")
        par.append(1 if geschlossen else 0)
    if bed:
        sql += " WHERE " + " AND ".join(bed)
    return [konto_dict(r) for r in con.execute(sql + " ORDER BY id", par)]


def _iban_pruefen(con, art: str, iban: str | None, eigene_id: int | None) -> str | None:
    if iban is None:
        return None
    if KLASSE[art] != "bestand":
        raise ApiFehler(422, "iban_ungueltig", "Eine IBAN ist nur bei Giro-, Spar- und Kreditkonten erlaubt.")
    n = iban_normalisieren(iban)
    if not iban_gueltig(n):
        raise ApiFehler(422, "iban_ungueltig", "Die IBAN ist ungültig (Format oder Prüfziffer).")
    r = con.execute("SELECT id FROM konto WHERE iban = ?", (n,)).fetchone()
    if r is not None and r["id"] != eigene_id:
        raise ApiFehler(409, "iban_existiert", "Diese IBAN ist bereits einem anderen Konto zugeordnet.")
    return n


def _eltern_pruefen(con, art: str, eltern_id: int | None, eigene_id: int | None) -> None:
    if eltern_id is None:
        return
    e = konto_zeile(con, eltern_id)
    if e is None:
        raise ApiFehler(422, "referenz_unbekannt", "Das Elternkonto existiert nicht.")
    if KLASSE[e["art"]] != KLASSE[art]:
        raise ApiFehler(422, "hierarchie_ungueltig", "Das Elternkonto gehört zu einer anderen Kontoklasse.")
    if eigene_id is not None:
        # Zyklus: das neue Elternkonto darf nicht das Konto selbst oder ein Nachfahre sein.
        k = eltern_id
        gesehen = set()
        while k is not None and k not in gesehen:
            if k == eigene_id:
                raise ApiFehler(422, "hierarchie_ungueltig", "Die Kontenhierarchie darf keinen Zyklus enthalten.")
            gesehen.add(k)
            r = con.execute("SELECT eltern_id FROM konto WHERE id = ?", (k,)).fetchone()
            k = r["eltern_id"] if r else None


def konto_anlegen(con, d: dict, extern_id: str | None = None) -> dict:
    art = d["art"]
    eltern_id = d.get("eltern_id")
    _eltern_pruefen(con, art, eltern_id, None)
    iban = _iban_pruefen(con, art, d.get("iban"), None)
    cur = con.execute(
        "INSERT INTO konto (name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz, extern_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (d["name"], art, eltern_id, iban, 1 if d.get("geschlossen") else 0, d.get("eroeffnet_am"),
         d.get("notiz", ""), extern_id))
    _zuordnung_erledigt(con, iban)
    return konto_lesen(con, cur.lastrowid)


def konto_aendern(con, konto_id: int, d: dict) -> dict:
    alt = konto_lesen(con, konto_id)
    neu = dict(alt)
    if "eltern_id" in d:
        _eltern_pruefen(con, alt["art"], d["eltern_id"], konto_id)
        neu["eltern_id"] = d["eltern_id"]
    if "iban" in d:
        neu["iban"] = _iban_pruefen(con, alt["art"], d["iban"], konto_id)
    for f in ("name", "geschlossen", "eroeffnet_am", "notiz"):
        if f in d:
            neu[f] = d[f]
    con.execute(
        "UPDATE konto SET name = ?, eltern_id = ?, iban = ?, geschlossen = ?, eroeffnet_am = ?, notiz = ?"
        " WHERE id = ?",
        (neu["name"], neu["eltern_id"], neu["iban"], 1 if neu["geschlossen"] else 0, neu["eroeffnet_am"],
         neu["notiz"], konto_id))
    _zuordnung_erledigt(con, neu["iban"])
    return konto_lesen(con, konto_id)


def _zuordnung_erledigt(con, iban: str | None) -> None:
    """D-111: Trägt ein Konto die IBAN eines nicht zugeordneten Bankkontos, ist dessen Hinweis erledigt."""
    if iban:
        con.execute("UPDATE benachrichtigung SET gelesen = 1 WHERE schluessel = ? AND gelesen = 0",
                    (f"konto_nicht_zugeordnet:{iban}",))


def konto_loeschen(con, konto_id: int) -> None:
    konto_lesen(con, konto_id)
    from . import kredite
    kredite.konto_pruefen(con, konto_id)  # M5: Kredit verweist auf das Konto (kredite.md 2.3)
    if con.execute("SELECT 1 FROM split WHERE konto_id = ? LIMIT 1", (konto_id,)).fetchone():
        raise ApiFehler(409, "konto_in_verwendung", "Auf das Konto wird noch gebucht.")
    if con.execute("SELECT 1 FROM konto WHERE eltern_id = ? LIMIT 1", (konto_id,)).fetchone():
        raise ApiFehler(409, "konto_in_verwendung", "Das Konto hat noch Unterkonten.")
    if konto_in_regeln(con, konto_id):
        raise ApiFehler(409, "konto_in_verwendung", "Eine Regel verweist auf das Konto.")
    from . import vorlagen
    if vorlagen.konto_in_vorlagen(con, konto_id):
        raise ApiFehler(409, "konto_in_verwendung", "Eine Split-Vorlage verweist auf das Konto.")
    if con.execute("SELECT 1 FROM empfaenger WHERE standardkategorie_id = ? LIMIT 1", (konto_id,)).fetchone():
        raise ApiFehler(409, "konto_in_verwendung", "Das Konto ist Standardkategorie eines Empfängers.")
    if con.execute("SELECT 1 FROM abstimmung WHERE konto_id = ? LIMIT 1", (konto_id,)).fetchone():
        raise ApiFehler(409, "konto_in_verwendung", "Eine Abstimmung verweist auf das Konto.")
    con.execute("DELETE FROM konto WHERE id = ?", (konto_id,))


def konto_in_regeln(con, konto_id: int) -> bool:
    """Verweist eine Regel (Kategorie oder Bedingung ``konto_id``) auf das Konto? (kategorisierung.md 1.2)"""
    for r in con.execute("SELECT kategorie_id, bedingungen FROM regel"):
        if r["kategorie_id"] == konto_id:
            return True
        if any(b.get("feld") == "konto_id" and b.get("wert") == konto_id for b in json.loads(r["bedingungen"])):
            return True
    return False


UNKATEGORISIERT = "kontor:unkategorisiert"


def unkategorisiert_id(con) -> int:
    """Technisches Konto „Unkategorisiert“ (synchronisation.md 4.2); bei Bedarf angelegt."""
    r = con.execute("SELECT id FROM konto WHERE extern_id = ?", (UNKATEGORISIERT,)).fetchone()
    if r is None:
        r = con.execute(
            "INSERT INTO konto (name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz, extern_id)"
            " VALUES ('Unkategorisiert', 'eigenkapital', NULL, NULL, 0, NULL, '', ?) RETURNING id",
            (UNKATEGORISIERT,)).fetchone()
    return r["id"]


def vorschlag_entfernen(con, ids: Iterable[int]) -> None:
    con.executemany("DELETE FROM vorschlag WHERE buchung_id = ?", [(i,) for i in ids])


def kinder_karte(con) -> dict[int, list[int]]:
    kinder: dict[int, list[int]] = defaultdict(list)
    for r in con.execute("SELECT id, eltern_id FROM konto WHERE eltern_id IS NOT NULL ORDER BY id"):
        kinder[r["eltern_id"]].append(r["id"])
    return kinder


def nachfahren(con, konto_id: int) -> set[int]:
    kinder = kinder_karte(con)
    aus, stapel = set(), [konto_id]
    while stapel:
        k = stapel.pop()
        if k in aus:
            continue
        aus.add(k)
        stapel.extend(kinder.get(k, []))
    return aus


def kontenuebersicht(con, stichtag: str | None) -> dict:
    konten = konten_liste(con)
    saldo: dict[int, int] = defaultdict(int)
    anzahl: dict[int, int] = defaultdict(int)
    sql = ("SELECT s.konto_id AS k, SUM(s.betrag) AS summe, COUNT(DISTINCT s.buchung_id) AS n"
           " FROM split s JOIN buchung b ON b.id = s.buchung_id")
    par: list[Any] = []
    if stichtag:
        sql += " WHERE b.datum <= ?"
        par.append(stichtag)
    for r in con.execute(sql + " GROUP BY s.konto_id", par):
        saldo[r["k"]] = r["summe"]
        anzahl[r["k"]] = r["n"]
    kinder: dict[int, list[int]] = defaultdict(list)
    for k in konten:
        if k["eltern_id"] is not None:
            kinder[k["eltern_id"]].append(k["id"])
    gesamt_cache: dict[int, int] = {}

    def gesamt(kid: int, pfad: frozenset = frozenset()) -> int:
        if kid in gesamt_cache:
            return gesamt_cache[kid]
        if kid in pfad:  # pragma: no cover - Zyklen werden beim Ändern verhindert
            return 0
        wert = saldo[kid] + sum(gesamt(c, pfad | {kid}) for c in kinder.get(kid, []))
        gesamt_cache[kid] = wert
        return wert

    eintraege = [{
        "konto_id": k["id"], "name": k["name"], "art": k["art"], "eltern_id": k["eltern_id"],
        "geschlossen": k["geschlossen"], "saldo": saldo[k["id"]], "saldo_gesamt": gesamt(k["id"]),
        "anzahl_buchungen": anzahl[k["id"]],
    } for k in konten]
    return {
        "stichtag": stichtag,
        "konten": eintraege,
        "summe_bestand": sum(e["saldo"] for e in eintraege if e["art"] in BESTAND),
        "summe_gesamt": sum(e["saldo"] for e in eintraege),
    }


# ================================================================ Empfänger


def empfaenger_dict(r, aliase: list[str] | None = None) -> dict:
    return {"id": r["id"], "name": r["name"], "extern_id": r["extern_id"], "aliase": sorted(aliase or []),
            "standardkategorie_id": r["standardkategorie_id"]}


def empfaenger_laden(con, ids: list[int] | None = None) -> list[dict]:
    """Empfänger mit Aliasen (M3), nach ``id`` aufsteigend; ``ids = None``: alle."""
    if ids is None:
        zeilen = con.execute("SELECT * FROM empfaenger ORDER BY id").fetchall()
        aliase: dict[int, list[str]] = defaultdict(list)
        for r in con.execute("SELECT empfaenger_id, alias FROM empfaenger_alias"):
            aliase[r["empfaenger_id"]].append(r["alias"])
        return [empfaenger_dict(r, aliase.get(r["id"])) for r in zeilen]
    aus = []
    for teil in _stueckweise(sorted(set(ids))):
        ph = _platzhalter(len(teil))
        zeilen = con.execute(f"SELECT * FROM empfaenger WHERE id IN ({ph}) ORDER BY id", teil).fetchall()
        aliase = defaultdict(list)
        for r in con.execute(f"SELECT empfaenger_id, alias FROM empfaenger_alias WHERE empfaenger_id IN ({ph})",
                             teil):
            aliase[r["empfaenger_id"]].append(r["alias"])
        aus.extend(empfaenger_dict(r, aliase.get(r["id"])) for r in zeilen)
    return aus


def empfaenger_liste(con) -> list[dict]:
    return empfaenger_laden(con)


def empfaenger_lesen(con, eid: int) -> dict:
    aus = empfaenger_laden(con, [sichere_id(eid)])
    if not aus:
        raise nicht_gefunden("Der Empfänger")
    return aus[0]


def empfaenger_anlegen(con, name: str, extern_id: str | None = None) -> dict:
    if con.execute("SELECT 1 FROM empfaenger WHERE name = ?", (name,)).fetchone():
        raise ApiFehler(409, "empfaenger_existiert", "Ein Empfänger mit diesem Namen existiert bereits.")
    cur = con.execute("INSERT INTO empfaenger (name, extern_id) VALUES (?, ?)", (name, extern_id))
    return empfaenger_lesen(con, cur.lastrowid)


def empfaenger_zu_name(con, name: str) -> int | None:
    """buchhaltungspflege.md 2.3 Schritte 1–2: exakter Name, sonst passender Alias; sonst None."""
    r = con.execute("SELECT id FROM empfaenger WHERE name = ?", (name,)).fetchone()
    if r is not None:
        return r["id"]
    k = ekey(name)
    if not k:
        return None
    r = con.execute("SELECT empfaenger_id FROM empfaenger_alias WHERE ekey = ?", (k,)).fetchone()
    return r["empfaenger_id"] if r is not None else None


def empfaenger_bestimmen(con, name: str) -> int:
    """2.3 vollständig: wie ``empfaenger_zu_name``, sonst neu anlegen."""
    eid = empfaenger_zu_name(con, name)
    if eid is None:
        eid = con.execute("INSERT INTO empfaenger (name, extern_id) VALUES (?, NULL)", (name,)).lastrowid
    return eid


# ===================================================================== Tags


def _tag_dict(r) -> dict:
    return {"id": r["id"], "name": r["name"], "extern_id": r["extern_id"], "anzahl_buchungen": r["anzahl"]}


_TAG_SQL = ("SELECT t.*, (SELECT COUNT(*) FROM buchung_tag bt WHERE bt.tag_id = t.id) AS anzahl FROM tag t")


def tags_liste(con) -> list[dict]:
    return [_tag_dict(r) for r in con.execute(_TAG_SQL + " ORDER BY t.id")]


def tag_lesen(con, tid: int) -> dict:
    r = con.execute(_TAG_SQL + " WHERE t.id = ?", (sichere_id(tid),)).fetchone()
    if r is None:
        raise nicht_gefunden("Der Tag")
    return _tag_dict(r)


def tag_anlegen(con, name: str, extern_id: str | None = None) -> dict:
    if con.execute("SELECT 1 FROM tag WHERE name_cf = ?", (name.casefold(),)).fetchone():
        raise ApiFehler(409, "tag_existiert", "Ein Tag mit diesem Namen existiert bereits.")
    cur = con.execute("INSERT INTO tag (name, name_cf, extern_id) VALUES (?, ?, ?)",
                      (name, name.casefold(), extern_id))
    return tag_lesen(con, cur.lastrowid)


def tag_umbenennen(con, tid: int, name: str) -> dict:
    tag_lesen(con, tid)
    r = con.execute("SELECT id FROM tag WHERE name_cf = ?", (name.casefold(),)).fetchone()
    if r is not None and r["id"] != tid:
        raise ApiFehler(409, "tag_existiert", "Ein anderer Tag trägt bereits diesen Namen.")
    con.execute("UPDATE tag SET name = ?, name_cf = ? WHERE id = ?", (name, name.casefold(), tid))
    return tag_lesen(con, tid)


def tag_loeschen(con, tid: int) -> None:
    tag_lesen(con, tid)
    con.execute("DELETE FROM buchung_tag WHERE tag_id = ?", (tid,))
    con.execute("DELETE FROM tag WHERE id = ?", (tid,))


# ================================================================= Buchungen


def _platzhalter(n: int) -> str:
    return ",".join("?" * n)


def _stueckweise(ids: list[int], groesse: int = 500) -> Iterable[list[int]]:
    for i in range(0, len(ids), groesse):
        yield ids[i:i + groesse]


def kategorie_aus_splits(splits: list[dict], art_von: dict[int, str]) -> int | None:
    gegen = [s for s in splits if art_von[s["konto_id"]] not in BESTAND]
    if len(gegen) == 1 and art_von[gegen[0]["konto_id"]] in KATEGORIEARTEN:
        return gegen[0]["konto_id"]
    return None


def kontoarten(con) -> dict[int, str]:
    return {r["id"]: r["art"] for r in con.execute("SELECT id, art FROM konto")}


def buchungen_laden(con, ids: list[int], konto_id: int | None = None,
                    art_von: dict[int, str] | None = None, konten: set[int] | None = None) -> list[dict]:
    """Lädt vollständige Buchungen in der Reihenfolge von ``ids``.

    ``betrag`` ist die Summe der Splits auf ``konten`` (M11, ``unterkonten``), sonst auf ``konto_id``."""
    if konten is None and konto_id is not None:
        konten = {konto_id}
    if not ids:
        return []
    if art_von is None:
        art_von = kontoarten(con)
    kopf: dict[int, sqlite3.Row] = {}
    splits: dict[int, list[dict]] = defaultdict(list)
    tags: dict[int, list[dict]] = defaultdict(list)
    extern: dict[int, list[str]] = defaultdict(list)
    vorschlaege: dict[int, dict] = {}
    for teil in _stueckweise(ids):
        ph = _platzhalter(len(teil))
        for r in con.execute(
                "SELECT b.*, e.name AS e_name FROM buchung b LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
                f" WHERE b.id IN ({ph})", teil):
            kopf[r["id"]] = r
        for r in con.execute(f"SELECT * FROM split WHERE buchung_id IN ({ph}) ORDER BY buchung_id, position",
                             teil):
            splits[r["buchung_id"]].append({"id": r["id"], "konto_id": r["konto_id"], "betrag": r["betrag"],
                                            "memo": r["memo"], "abstimmung_id": r["abstimmung_id"]})
        for r in con.execute(
                "SELECT bt.buchung_id, t.id, t.name FROM buchung_tag bt JOIN tag t ON t.id = bt.tag_id"
                f" WHERE bt.buchung_id IN ({ph}) ORDER BY bt.buchung_id, t.id", teil):
            tags[r["buchung_id"]].append({"id": r["id"], "name": r["name"]})
        for r in con.execute(f"SELECT * FROM buchung_extern WHERE buchung_id IN ({ph})", teil):
            extern[r["buchung_id"]].append(r["extern_id"])
        for r in con.execute(f"SELECT * FROM vorschlag WHERE buchung_id IN ({ph})", teil):
            v = {"kategorie_id": r["kategorie_id"], "regel_id": r["regel_id"], "quelle": r["quelle"],
                 "vorher_konto_id": r["vorher_konto_id"]}
            if r["quelle"] == "lernmodell":  # M4: Sicherheit nur bei Vorschlägen des Lernmodells
                v["sicherheit"] = r["sicherheit"]
            vorschlaege[r["buchung_id"]] = v
    aus = []
    for bid in ids:
        r = kopf.get(bid)
        if r is None:
            continue
        sp = splits[bid]
        if konten is not None:
            betrag = sum(s["betrag"] for s in sp if s["konto_id"] in konten)
        else:
            betrag = sum(s["betrag"] for s in sp if s["betrag"] > 0)
        aus.append({
            "id": bid,
            "datum": r["datum"],
            "empfaenger": None if r["empfaenger_id"] is None else {"id": r["empfaenger_id"], "name": r["e_name"]},
            "verwendungszweck": r["verwendungszweck"],
            "status": r["status"],
            "splits": sp,
            "tags": tags[bid],
            "kategorie_id": kategorie_aus_splits(sp, art_von),
            "betrag": betrag,
            "extern_ids": sorted(extern[bid]),
            "belege": [],
            "vorschlag": vorschlaege.get(bid),
            "gegen_iban": r["gegen_iban"],
            "ist_umbuchung": all(art_von[s["konto_id"]] in BESTAND for s in sp) and len({s["konto_id"] for s in sp}) >= 2,
            "abgestimmt": any(s["abstimmung_id"] is not None for s in sp),
        })
    return aus


def buchung_lesen(con, bid: int) -> dict:
    aus = buchungen_laden(con, [sichere_id(bid)])
    if not aus:
        raise nicht_gefunden("Die Buchung")
    return aus[0]


def _splits_regeln(con, splits: list[dict]) -> None:
    if len(splits) < 2:
        raise ApiFehler(422, "zu_wenige_splits", "Eine Buchung braucht mindestens zwei Splits.")
    if sum(s["betrag"] for s in splits) != 0:
        raise ApiFehler(422, "buchung_unausgeglichen", "Die Summe der Splits muss genau 0 sein.")
    konten = {s["konto_id"] for s in splits}
    vorhanden = {r["id"] for r in con.execute(
        f"SELECT id FROM konto WHERE id IN ({_platzhalter(len(konten))})", [sichere_id(k) for k in konten])}
    if konten - vorhanden:
        raise ApiFehler(422, "referenz_unbekannt", "Ein Split verweist auf ein unbekanntes Konto.",
                        {"konto_ids": sorted(konten - vorhanden)})


def _empfaenger_pruefen(con, eid: int | None) -> None:
    if eid is not None and con.execute("SELECT 1 FROM empfaenger WHERE id = ?",
                                       (sichere_id(eid),)).fetchone() is None:
        raise ApiFehler(422, "referenz_unbekannt", "Der Empfänger existiert nicht.")


def _tags_pruefen(con, tag_ids: list[int]) -> list[int]:
    eindeutig = sorted(set(tag_ids))
    if not eindeutig:
        return []
    vorhanden = {r["id"] for r in con.execute(
        f"SELECT id FROM tag WHERE id IN ({_platzhalter(len(eindeutig))})", [sichere_id(t) for t in eindeutig])}
    fehlend = [t for t in eindeutig if t not in vorhanden]
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Ein Tag existiert nicht.", {"tag_ids": fehlend})
    return eindeutig


def splits_schreiben(con, bid: int, splits: list[dict]) -> None:
    con.execute("DELETE FROM split WHERE buchung_id = ?", (bid,))
    con.executemany("INSERT INTO split (buchung_id, position, konto_id, betrag, memo) VALUES (?, ?, ?, ?, ?)",
                    [(bid, i, s["konto_id"], s["betrag"], s.get("memo", "")) for i, s in enumerate(splits)])


def buchung_einfuegen(con, datum: str, empfaenger_id: int | None, verwendungszweck: str, status: str,
                      splits: list[dict], tag_ids: Iterable[int] = (), extern_ids: Iterable[str] = (),
                      gegen_iban: str | None = None) -> int:
    cur = con.execute("INSERT INTO buchung (datum, empfaenger_id, verwendungszweck, status, gegen_iban)"
                      " VALUES (?, ?, ?, ?, ?)", (datum, empfaenger_id, verwendungszweck, status, gegen_iban))
    bid = cur.lastrowid
    splits_schreiben(con, bid, splits)
    con.executemany("INSERT OR IGNORE INTO buchung_tag (buchung_id, tag_id) VALUES (?, ?)",
                    [(bid, t) for t in tag_ids])
    con.executemany("INSERT INTO buchung_extern (buchung_id, extern_id) VALUES (?, ?)",
                    [(bid, e) for e in extern_ids])
    return bid


def buchung_anlegen(con, d: dict) -> dict:
    _splits_regeln(con, d["splits"])
    _empfaenger_pruefen(con, d.get("empfaenger_id"))
    tag_ids = _tags_pruefen(con, d.get("tag_ids") or [])
    bid = buchung_einfuegen(con, d["datum"], d.get("empfaenger_id"), d.get("verwendungszweck", ""),
                            d.get("status", "bestaetigt"), d["splits"], tag_ids)
    return buchung_lesen(con, bid)


def _gesperrt() -> ApiFehler:
    return ApiFehler(409, "buchung_gesperrt",
                     "Die Buchung ist abgeglichen oder abgestimmt und gegen Änderungen gesperrt.")


def ist_gesperrt(b: dict) -> bool:
    """buchhaltungspflege.md 1.3: abgeglichen oder abgestimmt."""
    return b["status"] == "abgeglichen" or b["abgestimmt"]


def buchung_aendern(con, bid: int, d: dict) -> dict:
    alt = buchung_lesen(con, bid)
    if "empfaenger_id" in d:
        _empfaenger_pruefen(con, d["empfaenger_id"])
    tag_ids = _tags_pruefen(con, d["tag_ids"]) if "tag_ids" in d else None
    if ist_gesperrt(alt):
        alt_empf = alt["empfaenger"]["id"] if alt["empfaenger"] else None
        if (("datum" in d and d["datum"] != alt["datum"])
                or ("empfaenger_id" in d and d["empfaenger_id"] != alt_empf)
                or ("verwendungszweck" in d and d["verwendungszweck"] != alt["verwendungszweck"])):
            raise _gesperrt()
    if "status" in d and d["status"] != alt["status"] and (alt["status"], d["status"]) not in UEBERGAENGE:
        raise ApiFehler(409, "status_uebergang_unzulaessig",
                        f"Der Statuswechsel von {alt['status']} nach {d['status']} ist nicht zulässig.")
    felder, werte = [], []
    for f in ("datum", "empfaenger_id", "verwendungszweck", "status"):
        if f in d:
            felder.append(f"{f} = ?")
            werte.append(d[f])
    if felder:
        con.execute(f"UPDATE buchung SET {', '.join(felder)} WHERE id = ?", (*werte, bid))
    if "status" in d and d["status"] != alt["status"] and d["status"] in ("bestaetigt", "abgeglichen"):
        vorschlag_entfernen(con, [bid])  # Bestätigung erledigt den Vorschlag (kategorisierung.md 5)
    if tag_ids is not None:
        con.execute("DELETE FROM buchung_tag WHERE buchung_id = ?", (bid,))
        con.executemany("INSERT INTO buchung_tag (buchung_id, tag_id) VALUES (?, ?)", [(bid, t) for t in tag_ids])
    return buchung_lesen(con, bid)


def splits_ersetzen(con, bid: int, splits: list[dict]) -> dict:
    alt = buchung_lesen(con, bid)
    if ist_gesperrt(alt):
        raise _gesperrt()
    _splits_regeln(con, splits)
    splits_schreiben(con, bid, splits)
    vorschlag_entfernen(con, [bid])
    return buchung_lesen(con, bid)


def _kategorie_ziel(con, kategorie_id: int) -> None:
    r = konto_zeile(con, kategorie_id)
    if r is None or r["art"] not in KATEGORIEARTEN:
        raise ApiFehler(422, "kategorie_ungueltig", "Die Zielkategorie muss ein Aufwands- oder Ertragskonto sein.")


def _gegensplit(b: dict, art_von: dict[int, str]) -> dict | None:
    gegen = [s for s in b["splits"] if art_von[s["konto_id"]] not in BESTAND]
    return gegen[0] if len(gegen) == 1 else None


def kategorie_setzen(con, bid: int, kategorie_id: int) -> dict:
    b = buchung_lesen(con, bid)
    if ist_gesperrt(b):
        raise _gesperrt()
    _kategorie_ziel(con, kategorie_id)
    s = _gegensplit(b, kontoarten(con))
    if s is None:
        raise ApiFehler(422, "nicht_kategorisierbar",
                        "Die Buchung hat nicht genau einen Gegensplit und lässt sich nicht kategorisieren.")
    con.execute("UPDATE split SET konto_id = ? WHERE id = ?", (kategorie_id, s["id"]))
    vorschlag_entfernen(con, [bid])
    return buchung_lesen(con, bid)


def _offene_verdachte_entfernen(con, bid: int) -> None:
    con.execute(
        "DELETE FROM dublettenverdacht WHERE status = 'offen' AND (buchung_id = ?"
        " OR id IN (SELECT verdacht_id FROM verdacht_kandidat WHERE buchung_id = ?))", (bid, bid))


def buchung_entfernen(con, bid: int) -> None:
    con.execute("DELETE FROM buchung WHERE id = ?", (bid,))
    _offene_verdachte_entfernen(con, bid)


def buchung_loeschen(con, bid: int) -> None:
    b = buchung_lesen(con, bid)
    if ist_gesperrt(b):
        raise _gesperrt()
    buchung_entfernen(con, bid)


def _vorhandene_buchungen(con, ids: list[int]) -> set[int]:
    gefunden: set[int] = set()
    for teil in _stueckweise(sorted(set(ids))):
        gefunden |= {r["id"] for r in con.execute(
            f"SELECT id FROM buchung WHERE id IN ({_platzhalter(len(teil))})", [sichere_id(x) for x in teil])}
    return gefunden


def mehrfach_kategorie(con, ids: list[int], kategorie_id: int) -> dict:
    vorhanden = _vorhandene_buchungen(con, ids)
    fehlend = sorted(set(ids) - vorhanden)
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    _kategorie_ziel(con, kategorie_id)
    art_von = kontoarten(con)
    buchungen = buchungen_laden(con, sorted(ids), art_von=art_von)
    gesperrt = [b["id"] for b in buchungen if ist_gesperrt(b)]
    if gesperrt:
        raise ApiFehler(409, "buchung_gesperrt", "Gesperrte Buchungen können nicht geändert werden.",
                        {"buchung_ids": gesperrt})
    gegen = {b["id"]: _gegensplit(b, art_von) for b in buchungen}
    nicht = [bid for bid, s in gegen.items() if s is None]
    if nicht:
        raise ApiFehler(422, "nicht_kategorisierbar", "Einige Buchungen lassen sich nicht kategorisieren.",
                        {"buchung_ids": sorted(nicht)})
    con.executemany("UPDATE split SET konto_id = ? WHERE id = ?",
                    [(kategorie_id, s["id"]) for s in gegen.values()])
    vorschlag_entfernen(con, ids)
    return {"geaendert": sorted(ids), "anzahl": len(ids)}


def mehrfach_tags(con, ids: list[int], hinzufuegen: list[int], entfernen: list[int]) -> dict:
    vorhanden = _vorhandene_buchungen(con, ids)
    fehlend = sorted(set(ids) - vorhanden)
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    hinzu = _tags_pruefen(con, hinzufuegen)
    weg = _tags_pruefen(con, entfernen)
    for bid in ids:
        con.executemany("DELETE FROM buchung_tag WHERE buchung_id = ? AND tag_id = ?", [(bid, t) for t in weg])
        con.executemany("INSERT OR IGNORE INTO buchung_tag (buchung_id, tag_id) VALUES (?, ?)",
                        [(bid, t) for t in hinzu])
    return {"geaendert": sorted(ids), "anzahl": len(ids)}


def _aenderung_an_gesperrter(b: dict, d: dict) -> bool:
    """E-026: nur tatsächliche Änderungen von Datum, Empfänger oder Verwendungszweck zählen."""
    alt_empf = b["empfaenger"]["id"] if b["empfaenger"] else None
    return (("datum" in d and d["datum"] != b["datum"])
            or ("empfaenger_id" in d and d["empfaenger_id"] != alt_empf)
            or ("verwendungszweck" in d and d["verwendungszweck"] != b["verwendungszweck"]))


def mehrfach_aendern(con, d: dict) -> dict:
    """M12 (datenmodell.md 17.2): Status, Datum, Empfänger und Verwendungszweck mehrerer Buchungen, atomar.

    Freie Statusübergänge; das Verlassen von ``abgeglichen`` verlangt ``entsperren``. Prüfreihenfolge:
    unbekannte Buchungen, unbekannter Empfänger, ``buchung_gesperrt``, ``bestaetigung_erforderlich``.
    """
    ids = sorted(d["buchung_ids"])
    fehlend = sorted(set(ids) - _vorhandene_buchungen(con, ids))
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    if "empfaenger_id" in d:
        _empfaenger_pruefen(con, d["empfaenger_id"])
    buchungen = buchungen_laden(con, ids)
    gesperrt = [b["id"] for b in buchungen if ist_gesperrt(b) and _aenderung_an_gesperrter(b, d)]
    if gesperrt:
        raise ApiFehler(409, "buchung_gesperrt", "Gesperrte Buchungen können nicht geändert werden.",
                        {"buchung_ids": gesperrt})
    status = d.get("status")
    wechsel = [b for b in buchungen if status is not None and b["status"] != status]
    if not d.get("entsperren"):
        zu_bestaetigen = [b["id"] for b in wechsel if b["status"] == "abgeglichen"]
        if zu_bestaetigen:
            raise ApiFehler(409, "bestaetigung_erforderlich",
                            "Abgeglichene Buchungen werden nur mit Bestätigung (entsperren) geändert.",
                            {"buchung_ids": zu_bestaetigen})
    felder = [f for f in ("datum", "empfaenger_id", "verwendungszweck", "status") if f in d]
    zuweisung = ", ".join(f"{f} = ?" for f in felder)
    werte = [d[f] for f in felder]
    for teil in _stueckweise(ids):
        con.execute(f"UPDATE buchung SET {zuweisung} WHERE id IN ({_platzhalter(len(teil))})",
                    [*werte, *(sichere_id(x) for x in teil)])
    if status in ("bestaetigt", "abgeglichen") and wechsel:
        vorschlag_entfernen(con, [b["id"] for b in wechsel])  # Bestätigung erledigt den Vorschlag
    return {"geaendert": ids, "anzahl": len(ids)}


def mehrfach_loeschen(con, ids: list[int]) -> dict:
    """Sammelpaket (D-109): mehrere Buchungen in einer Änderung löschen, atomar. Prüfreihenfolge wie beim
    einzelnen Löschen: unbekannte Buchungen (422), gesperrte Buchungen (409, alle aufgezählt)."""
    ids = sorted(ids)
    fehlend = sorted(set(ids) - _vorhandene_buchungen(con, ids))
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    gesperrt = [b["id"] for b in buchungen_laden(con, ids) if ist_gesperrt(b)]
    if gesperrt:
        raise ApiFehler(409, "buchung_gesperrt", "Gesperrte Buchungen können nicht gelöscht werden.",
                        {"buchung_ids": gesperrt})
    for bid in ids:
        buchung_entfernen(con, bid)
    return {"geloescht": ids, "anzahl": len(ids)}


# ============================================================ Buchungsliste

SORTIERUNGEN = ("datum", "-datum", "betrag", "-betrag", "empfaenger", "-empfaenger")
_GRENZE = 2**62


def _klemme(x: int) -> int:
    return max(-_GRENZE, min(_GRENZE, x))


def buchungsliste(con, f: dict) -> dict:
    """Filter laut openapi.yaml; alle UND-verknüpft."""
    konto_id = f.get("konto_id")
    par: list[Any] = []
    konten = _listenkonten(con, konto_id, bool(f.get("unterkonten")))
    if konten is not None:
        ph = _platzhalter(len(konten))
        betrag_sql = (f"(SELECT COALESCE(SUM(s.betrag), 0) FROM split s WHERE s.buchung_id = b.id"
                      f" AND +s.konto_id IN ({ph}))")
        par.extend(konten)
    else:
        betrag_sql = "(SELECT COALESCE(SUM(s.betrag), 0) FROM split s WHERE s.buchung_id = b.id AND +s.betrag > 0)"
    bed: list[str] = []
    if konten is not None:
        bed.append(f"b.id IN (SELECT s.buchung_id FROM split s WHERE s.konto_id IN ({_platzhalter(len(konten))}))")
        par.extend(konten)
    if f.get("von"):
        bed.append("b.datum >= ?")
        par.append(f["von"])
    if f.get("bis"):
        bed.append("b.datum <= ?")
        par.append(f["bis"])
    if f.get("kategorie_id") is not None:
        kid = sichere_id(f["kategorie_id"])
        ziel = nachfahren(con, kid) if f.get("unterkategorien") else {kid}
        bed.append(f"b.id IN (SELECT s.buchung_id FROM split s WHERE s.konto_id IN ({_platzhalter(len(ziel))}))")
        par.extend(sorted(ziel))
    for t in sorted(set(f.get("tag_id") or [])):
        bed.append("b.id IN (SELECT bt.buchung_id FROM buchung_tag bt WHERE bt.tag_id = ?)")
        par.append(sichere_id(t))
    if f.get("empfaenger_id") is not None:
        bed.append("b.empfaenger_id = ?")
        par.append(sichere_id(f["empfaenger_id"]))
    if f.get("ohne_empfaenger"):
        bed.append("b.empfaenger_id IS NULL")
    if f.get("verwendungszweck"):
        bed.append("instr(norm(b.verwendungszweck), ?) > 0")
        par.append(norm(f["verwendungszweck"]))
    if f.get("suche"):
        n = norm(f["suche"])
        bed.append("(instr(norm(e.name), ?) > 0 OR instr(norm(b.verwendungszweck), ?) > 0"
                   " OR b.id IN (SELECT s.buchung_id FROM split s WHERE s.memo <> '' AND instr(norm(s.memo), ?) > 0)"
                   " OR b.id IN (SELECT bt.buchung_id FROM buchung_tag bt JOIN tag t ON t.id = bt.tag_id"
                   " WHERE instr(norm(t.name), ?) > 0))")
        par.extend([n, n, n, n])
    if f.get("vorschlag") is not None:
        bed.append(("" if f["vorschlag"] else "NOT ") + "EXISTS (SELECT 1 FROM vorschlag v WHERE v.buchung_id = b.id)")
    if f.get("abgestimmt") is not None:
        bed.append(("" if f["abgestimmt"] else "NOT ")
                   + "b.id IN (SELECT s.buchung_id FROM split s WHERE s.abstimmung_id IS NOT NULL)")
    if f.get("status"):
        st = sorted(set(f["status"]))
        bed.append(f"b.status IN ({_platzhalter(len(st))})")
        par.extend(st)
    innen = (f"SELECT b.id AS id, b.datum AS datum, {betrag_sql} AS betrag, norm(e.name) AS e_norm"
             f" FROM buchung b LEFT JOIN empfaenger e ON e.id = b.empfaenger_id")
    if bed:
        innen += " WHERE " + " AND ".join(bed)
    aussen_bed, aussen_par = [], []
    if f.get("betrag_min") is not None:
        aussen_bed.append("betrag >= ?")
        aussen_par.append(_klemme(f["betrag_min"]))
    if f.get("betrag_max") is not None:
        aussen_bed.append("betrag <= ?")
        aussen_par.append(_klemme(f["betrag_max"]))
    basis = f"SELECT * FROM ({innen})"
    if aussen_bed:
        basis += " WHERE " + " AND ".join(aussen_bed)
    alle_par = par + aussen_par
    r = con.execute(f"SELECT COUNT(*) AS n, COALESCE(SUM(betrag), 0) AS summe FROM ({basis})", alle_par).fetchone()
    gesamt, summe = r["n"], r["summe"]

    sortierung = f.get("sortierung") or "datum"
    absteigend = sortierung.startswith("-")
    feld = sortierung.lstrip("-")
    richtung = "DESC" if absteigend else "ASC"
    if feld == "empfaenger":
        order = f"(e_norm IS NULL) ASC, e_norm {richtung}, id ASC"
    else:
        order = f"{feld} {richtung}, id ASC"
    seite, pro_seite = f.get("seite", 1), f.get("pro_seite", 50)
    offset = (seite - 1) * pro_seite
    eintraege: list[dict] = []
    if offset < gesamt:
        zeilen = con.execute(f"{basis} ORDER BY {order} LIMIT ? OFFSET ?", alle_par + [pro_seite, offset])
        ids = [z["id"] for z in zeilen]
        eintraege = buchungen_laden(con, ids, konten=None if konten is None else set(konten))
    return {"eintraege": eintraege, "gesamt": gesamt, "seite": seite, "pro_seite": pro_seite, "summe": summe}


def _listenkonten(con, konto_id: int | None, unterkonten: bool) -> list[int] | None:
    """Kontenmenge K der Buchungsliste: ``konto_id``, mit ``unterkonten`` samt allen Nachfahren (datenmodell.md
    16.1); None ohne ``konto_id``."""
    if konto_id is None:
        return None
    kid = sichere_id(konto_id)
    return sorted(nachfahren(con, kid)) if unterkonten else [kid]


# ================================================================== Importe


def importe_liste(con) -> list[dict]:
    return [{"id": r["id"], "art": r["art"], "dateiname": r["dateiname"], "sha256": r["sha256"],
             "importiert_am": r["importiert_am"], "ergebnis": json.loads(r["ergebnis"])}
            for r in con.execute("SELECT * FROM importvorgang ORDER BY id")]


# ================================================================ Dubletten


def _verdacht_dict(con, r) -> dict:
    kandidaten = [k["buchung_id"] for k in con.execute(
        "SELECT buchung_id FROM verdacht_kandidat WHERE verdacht_id = ? ORDER BY buchung_id", (r["id"],))]
    return {"id": r["id"], "buchung_id": r["buchung_id"], "kandidat_ids": kandidaten, "grund": r["grund"],
            "status": r["status"], "erstellt_am": r["erstellt_am"]}


def dubletten_liste(con, status: str | None) -> list[dict]:
    if status:
        zeilen = con.execute("SELECT * FROM dublettenverdacht WHERE status = ? ORDER BY id", (status,))
    else:
        zeilen = con.execute("SELECT * FROM dublettenverdacht ORDER BY id")
    return [_verdacht_dict(con, r) for r in zeilen.fetchall()]


def verdacht_lesen(con, vid: int) -> dict:
    r = con.execute("SELECT * FROM dublettenverdacht WHERE id = ?", (sichere_id(vid),)).fetchone()
    if r is None:
        raise nicht_gefunden("Der Dublettenverdacht")
    return _verdacht_dict(con, r)


def verdacht_aufloesen(con, vid: int, entscheidung: str, behalten_id: int | None) -> dict:
    v = verdacht_lesen(con, vid)
    if v["status"] != "offen":
        raise ApiFehler(409, "konflikt", "Der Dublettenverdacht ist bereits aufgelöst.")
    if entscheidung == "keine_dublette":
        con.execute("UPDATE dublettenverdacht SET status = 'keine_dublette' WHERE id = ?", (vid,))
        return verdacht_lesen(con, vid)
    if behalten_id is None:
        raise ApiFehler(422, "validierung", "Beim Zusammenführen ist behalten_id Pflicht.",
                        [{"ort": ["body", "behalten_id"], "meldung": "Pflichtfeld fehlt."}])
    if behalten_id not in v["kandidat_ids"]:
        raise ApiFehler(422, "validierung", "behalten_id muss einer der Kandidaten sein.",
                        [{"ort": ["body", "behalten_id"], "meldung": "Kein Kandidat dieses Verdachts."}])
    neu = buchung_lesen(con, v["buchung_id"])
    if ist_gesperrt(neu):
        raise ApiFehler(409, "buchung_gesperrt",
                        "Die verdächtige Buchung ist gesperrt (abgeglichen oder abgestimmt) und kann nicht entfernt werden.")
    con.execute("UPDATE dublettenverdacht SET status = 'zusammengefuehrt' WHERE id = ?", (vid,))
    con.execute("DELETE FROM buchung_extern WHERE buchung_id = ?", (neu["id"],))
    buchung_entfernen(con, neu["id"])
    con.executemany("INSERT INTO buchung_extern (buchung_id, extern_id) VALUES (?, ?)",
                    [(behalten_id, e) for e in neu["extern_ids"]])
    return verdacht_lesen(con, vid)


# ========================================================= Benachrichtigungen


def _benachrichtigung_dict(r) -> dict:
    return {"id": r["id"], "art": r["art"], "schluessel": r["schluessel"], "titel": r["titel"], "text": r["text"],
            "link": r["link"], "erstellt_am": r["erstellt_am"], "gelesen": bool(r["gelesen"]),
            "zustellung": r["zustellung"], "zustellversuche": r["zustellversuche"], "zugestellt_am": r["zugestellt_am"]}


def benachrichtigung_anlegen(con, art: str, schluessel: str, titel: str, text: str, link: str | None,
                             jetzt: str, entprellung: str = "ungelesen") -> int | None:
    """Legt eine Benachrichtigung an; ``entprellung`` = ``ungelesen`` (keine ungelesene mit diesem Schlüssel),
    ``einmal`` (überhaupt keine mit diesem Schlüssel) oder ``keine``. Liefert die ID oder None."""
    if entprellung == "ungelesen" and con.execute(
            "SELECT 1 FROM benachrichtigung WHERE schluessel = ? AND gelesen = 0", (schluessel,)).fetchone():
        return None
    if entprellung == "einmal" and con.execute(
            "SELECT 1 FROM benachrichtigung WHERE schluessel = ? LIMIT 1", (schluessel,)).fetchone():
        return None
    return con.execute("INSERT INTO benachrichtigung (art, schluessel, titel, text, link, erstellt_am, gelesen)"
                       " VALUES (?, ?, ?, ?, ?, ?, 0)", (art, schluessel, titel, text, link, jetzt)).lastrowid


def benachrichtigungen_liste(con, gelesen: bool | None) -> list[dict]:
    if gelesen is None:
        zeilen = con.execute("SELECT * FROM benachrichtigung ORDER BY id")
    else:
        zeilen = con.execute("SELECT * FROM benachrichtigung WHERE gelesen = ? ORDER BY id", (1 if gelesen else 0,))
    return [_benachrichtigung_dict(r) for r in zeilen]


def benachrichtigung_gelesen(con, nid: int) -> dict:
    r = con.execute("SELECT * FROM benachrichtigung WHERE id = ?", (sichere_id(nid),)).fetchone()
    if r is None:
        raise nicht_gefunden("Die Benachrichtigung")
    con.execute("UPDATE benachrichtigung SET gelesen = 1 WHERE id = ?", (nid,))
    return _benachrichtigung_dict(con.execute("SELECT * FROM benachrichtigung WHERE id = ?", (nid,)).fetchone())
