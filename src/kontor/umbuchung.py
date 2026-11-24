"""Sammelbranch sammel4 (D-242): Zuordnung von Hand auf ein Bestandskonto – aus der Kategoriezuordnung wird eine
Umbuchung.

``zuordnen`` ersetzt ``buch.kategorie_setzen`` hinter ``PUT /api/buchungen/{id}/kategorie``: Ziel ist eine Kategorie
(wie bisher) oder ein Bestandskonto. Beim Bestandskonto wird der Gegensplit auf dieses Konto gelegt; steht dort schon
der Bankumsatz der Gegenseite als eigene, noch nicht zugeordnete Buchung, werden beide zu einer Buchung
zusammengeführt (wie ``pflege._zusammenfuehren``). Kommt die Gegenseite erst später von der Bank, hängt die
Synchronisation den Umsatz an die Umbuchung an (``sync._abgleichen_und_buchen``).
"""

from __future__ import annotations

import datetime as dt

from . import buch
from .buch import BESTAND, KATEGORIEARTEN, ApiFehler

AUTOMATISCH = "auto"   # Gegenbuchung nicht angegeben: genau eine passende wird genommen, mehrere sind ein Fehler


def _mit_bankumsatz(con, b: dict, konto_id: int) -> bool:
    """Trägt die Seite der Buchung auf diesem Konto einen Bankumsatz (oder ist sie abgestimmt)?"""
    if any(s["konto_id"] == konto_id and s["abstimmung_id"] is not None for s in b["splits"]):
        return True
    r = con.execute("SELECT iban FROM konto WHERE id = ?", (konto_id,)).fetchone()
    if r is None or r["iban"] is None:
        return False
    praefix = f"bank:{r['iban']}:"
    return any(x.startswith(praefix) for x in b["extern_ids"])


def ziel_split(con, b: dict, art_von: dict[int, str], sicht_konto: int | None = None) -> dict | None:
    """Der Split, dessen Konto die Zuordnung ändert.

    Üblicher Fall: der eine Gegensplit (Kategorie, „Unkategorisiert“). Bei einer Umbuchung aus genau zwei Splits
    die Seite ohne Bankumsatz; tragen beide keinen, entscheidet ``sicht_konto`` (das Konto, aus dessen Blatt
    zugeordnet wird, bleibt). Tragen beide einen Bankumsatz, ist nichts zu ändern.
    """
    gegen = [s for s in b["splits"] if art_von[s["konto_id"]] not in BESTAND]
    if gegen:
        return gegen[0] if len(gegen) == 1 and len(b["splits"]) == 2 else None
    if len(b["splits"]) != 2 or b["splits"][0]["konto_id"] == b["splits"][1]["konto_id"]:
        return None
    frei = [s for s in b["splits"] if not _mit_bankumsatz(con, b, s["konto_id"])]
    if len(frei) == 1:
        return frei[0]
    if len(frei) == 2 and sicht_konto is not None:
        andere = [s for s in frei if s["konto_id"] != sicht_konto]
        return andere[0] if len(andere) == 1 else None
    return None


def _nicht_zuordenbar() -> ApiFehler:
    return ApiFehler(422, "nicht_kategorisierbar",
                     "Die Buchung hat nicht genau eine Gegenseite, die sich zuordnen lässt.")


def _kandidaten(con, b: dict, s: dict, ziel_id: int, fenster: int, art_von: dict[int, str]) -> list[dict]:
    """Buchungen auf dem Zielkonto, die der Bankumsatz der Gegenseite sein können: genau zwei Splits, einer auf dem
    Zielkonto mit dem Betrag des Gegensplits, der andere noch nicht zugeordnet („Unkategorisiert“ oder nur ein
    Vorschlag), nicht gesperrt, Datum im Fenster, Gegen-IBAN (falls bekannt) gleich der IBAN des eigenen Kontos."""
    bleibt = next(x for x in b["splits"] if x["id"] != s["id"])
    eigene = con.execute("SELECT iban FROM konto WHERE id = ?", (bleibt["konto_id"],)).fetchone()["iban"]
    unk = con.execute("SELECT id FROM konto WHERE extern_id = ?", (buch.UNKATEGORISIERT,)).fetchone()
    unk_id = None if unk is None else unk["id"]
    tag = dt.date.fromisoformat(b["datum"])
    ids = [r["buchung_id"] for r in con.execute(
        "SELECT s.buchung_id FROM split s WHERE s.konto_id = ? AND s.betrag = ? AND s.buchung_id <> ?"
        " AND (SELECT COUNT(*) FROM split t WHERE t.buchung_id = s.buchung_id) = 2 ORDER BY s.buchung_id",
        (ziel_id, s["betrag"], b["id"]))]
    aus = []
    for teil in buch._stueckweise(ids):
        for y in buch.buchungen_laden(con, teil, art_von=art_von):
            gegen = [t for t in y["splits"] if art_von[t["konto_id"]] not in BESTAND]
            if len(gegen) != 1 or buch.ist_gesperrt(y):
                continue
            if gegen[0]["konto_id"] != unk_id and y["vorschlag"] is None:
                continue
            if abs((dt.date.fromisoformat(y["datum"]) - tag).days) > fenster:
                continue
            if y["gegen_iban"] is not None and eigene is not None and y["gegen_iban"] != eigene:
                continue
            aus.append(y)
    return aus


def _zusammenfuehren(con, b: dict, s: dict, y: dict, ziel_id: int) -> None:
    """Die Buchung ``b`` bleibt; ihr Gegensplit ``s`` entfällt, an seine Stelle tritt die Bankseite von ``y``
    (mit ihrer Split-ID). Kennungen und Tags von ``y`` gehen über, ``y`` entfällt."""
    by = next(t for t in y["splits"] if t["konto_id"] == ziel_id)
    con.execute("DELETE FROM split WHERE id = ?", (s["id"],))
    position = next(i for i, t in enumerate(b["splits"]) if t["id"] == s["id"])
    con.execute("UPDATE split SET buchung_id = ?, position = ? WHERE id = ?", (b["id"], position, by["id"]))
    con.execute("UPDATE buchung_extern SET buchung_id = ? WHERE buchung_id = ?", (b["id"], y["id"]))
    con.execute("INSERT OR IGNORE INTO buchung_tag (buchung_id, tag_id) SELECT ?, tag_id FROM buchung_tag"
                " WHERE buchung_id = ?", (b["id"], y["id"]))
    buch.buchung_entfernen(con, y["id"])


def _ziel(con, ziel_id: int) -> str:
    r = buch.konto_zeile(con, ziel_id)
    if r is None or (r["art"] not in KATEGORIEARTEN and r["art"] not in BESTAND):
        raise ApiFehler(422, "kategorie_ungueltig",
                        "Das Ziel muss eine Kategorie (Aufwand, Ertrag) oder ein Bestandskonto sein.")
    return r["art"]


def _vorbereiten(con, b: dict, ziel_id: int, art: str, art_von: dict[int, str], sicht_konto: int | None) -> dict:
    s = ziel_split(con, b, art_von, sicht_konto)
    if s is None:
        raise _nicht_zuordenbar()
    if art in BESTAND and any(x["konto_id"] == ziel_id for x in b["splits"] if x["id"] != s["id"]):
        raise ApiFehler(422, "konto_ungueltig", "Eine Umbuchung braucht zwei verschiedene Konten.")
    return s


def gegenbuchungen(con, bid: int, ziel_id: int, fenster: int, sicht_konto: int | None = None) -> dict:
    """Lesend: welche Buchungen des Zielkontos kämen beim Zuordnen als Gegenseite in Frage?"""
    b = buch.buchung_lesen(con, bid)
    art = _ziel(con, ziel_id)
    if art not in BESTAND:
        return {"kandidaten": []}
    art_von = buch.kontoarten(con)
    s = _vorbereiten(con, b, ziel_id, art, art_von, sicht_konto)
    return {"kandidaten": _kandidaten(con, b, s, ziel_id, fenster, art_von)}


def _eine(con, b: dict, ziel_id: int, art: str, art_von: dict[int, str], fenster: int, gegenbuchung,
          sicht_konto: int | None) -> None:
    s = _vorbereiten(con, b, ziel_id, art, art_von, sicht_konto)
    y = None
    if art in BESTAND and gegenbuchung is not None:
        kand = _kandidaten(con, b, s, ziel_id, fenster, art_von)
        if gegenbuchung == AUTOMATISCH:
            if len(kand) > 1:
                raise ApiFehler(409, "gegenbuchung_mehrdeutig",
                                "Auf dem Zielkonto passen mehrere Buchungen als Gegenseite; bitte eine wählen.",
                                {"buchung_id": b["id"], "kandidaten": [k["id"] for k in kand]})
            y = kand[0] if kand else None
        else:
            y = next((k for k in kand if k["id"] == gegenbuchung), None)
            if y is None:
                raise ApiFehler(422, "keine_umbuchung", "Die gewählte Buchung passt nicht als Gegenseite.")
    elif gegenbuchung not in (None, AUTOMATISCH):
        raise ApiFehler(422, "keine_umbuchung", "Eine Gegenbuchung gibt es nur bei einem Bestandskonto als Ziel.")
    if y is not None:
        _zusammenfuehren(con, b, s, y, ziel_id)
    else:
        con.execute("UPDATE split SET konto_id = ? WHERE id = ?", (ziel_id, s["id"]))
    buch.vorschlag_entfernen(con, [b["id"]])
    buch.von_hand_zugeordnet(con, [b["id"]])   # D-257


def zuordnen(con, bid: int, ziel_id: int, fenster: int, gegenbuchung=AUTOMATISCH,
             sicht_konto: int | None = None) -> dict:
    """Kategorie oder Bestandskonto als Gegenseite einer Buchung setzen (eine Buchung)."""
    b = buch.buchung_lesen(con, bid)
    if buch.ist_gesperrt(b):
        raise ApiFehler(409, "buchung_gesperrt", "Die Buchung ist gesperrt und kann nicht geändert werden.")
    art = _ziel(con, ziel_id)
    _eine(con, b, ziel_id, art, buch.kontoarten(con), fenster, gegenbuchung, sicht_konto)
    return buch.buchung_lesen(con, bid)


def mehrfach(con, ids: list[int], ziel_id: int, fenster: int, sicht_konto: int | None = None) -> dict:
    """Mehrere Buchungen einer Kategorie oder einem Bestandskonto zuordnen. Passen bei einer Buchung mehrere Gegenseiten oder teilen sich zwei gewählte
    Buchungen eine Gegenseite, wird nichts geändert (409 ``gegenbuchung_mehrdeutig``)."""
    vorhanden = buch._vorhandene_buchungen(con, ids)
    fehlend = sorted(set(ids) - vorhanden)
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    art = _ziel(con, ziel_id)   # Prüfreihenfolge wie bisher: erst die Buchungen, dann das Ziel
    art_von = buch.kontoarten(con)
    buchungen = buch.buchungen_laden(con, sorted(ids), art_von=art_von)
    if art not in BESTAND and not any(b["ist_umbuchung"] for b in buchungen):
        return buch.mehrfach_kategorie(con, ids, ziel_id)   # bisheriger Weg, unverändert
    gesperrt = [b["id"] for b in buchungen if buch.ist_gesperrt(b)]
    if gesperrt:
        raise ApiFehler(409, "buchung_gesperrt", "Gesperrte Buchungen können nicht geändert werden.",
                        {"buchung_ids": gesperrt})
    nicht = [b["id"] for b in buchungen if ziel_split(con, b, art_von, sicht_konto) is None]
    if nicht:
        raise ApiFehler(422, "nicht_kategorisierbar", "Einige Buchungen lassen sich nicht zuordnen.",
                        {"buchung_ids": sorted(nicht)})
    gewaehlt = set(ids)
    wahl: dict[int, int | None] = {}
    mehrdeutig = []
    for b in buchungen:
        s = _vorbereiten(con, b, ziel_id, art, art_von, sicht_konto)
        kand = [] if art not in BESTAND else [
            k["id"] for k in _kandidaten(con, b, s, ziel_id, fenster, art_von) if k["id"] not in gewaehlt]
        if len(kand) > 1:
            mehrdeutig.append(b["id"])
        wahl[b["id"]] = kand[0] if len(kand) == 1 else None
    vergeben = [k for k in wahl.values() if k is not None]
    mehrdeutig += [bid for bid, k in wahl.items() if k is not None and vergeben.count(k) > 1]
    if mehrdeutig:
        raise ApiFehler(409, "gegenbuchung_mehrdeutig",
                        "Bei einigen Buchungen ist die Gegenseite nicht eindeutig; bitte einzeln zuordnen.",
                        {"buchung_ids": sorted(set(mehrdeutig))})
    for b in buchungen:
        _eine(con, b, ziel_id, art, art_von, fenster, wahl[b["id"]], sicht_konto)
    return {"geaendert": sorted(ids), "anzahl": len(ids)}
