"""Buchhaltungspflege – Meilenstein 3 (buchhaltungspflege.md, loeschen.md).

Empfängerverwaltung, Erfassungshilfe, Umbuchungen, Kontenabstimmung,
Volltextsuche und das Löschen benutzter Konten. Alle Funktionen arbeiten auf
einer offenen Verbindung innerhalb einer (protokollierten) Transaktion.
"""

from __future__ import annotations

import datetime as dt
import json
import unicodedata
from collections import defaultdict

from . import buch, regeln
from .buch import BESTAND, KATEGORIEARTEN, ApiFehler, nicht_gefunden, sichere_id
from .protokoll import abstimmung_dict
from .text import ekey, iban_gueltig, iban_normalisieren, norm
from .validierung import Validierungsfehler, fehler_eintrag

KORREKTUR = "kontor:korrektur"


# ============================================================ Empfänger (2)


def aliase_bereinigen(aliase: list[str], ort: list) -> list[str]:
    """2.1: gestrippt (schon durch die Schemaprüfung), ekey nicht leer, nach ekey zusammengefasst, sortiert."""
    fehler = [fehler_eintrag(ort + [i], "Der Alias braucht mindestens einen Buchstaben oder eine Ziffer.")
              for i, a in enumerate(aliase) if not ekey(a)]
    if fehler:
        raise Validierungsfehler(fehler)
    gesehen: dict[str, str] = {}
    for a in aliase:
        gesehen.setdefault(ekey(a), a)
    return sorted(gesehen.values())


def _aliase_pruefen(con, aliase: list[str], eigene_id: int | None) -> None:
    for a in aliase:
        r = con.execute("SELECT empfaenger_id FROM empfaenger_alias WHERE ekey = ?", (ekey(a),)).fetchone()
        if r is not None and r["empfaenger_id"] != eigene_id:
            raise ApiFehler(409, "alias_existiert", "Dieser Alias gehört bereits zu einem anderen Empfänger.",
                            {"alias": a, "empfaenger_id": r["empfaenger_id"]})


def _standardkategorie_pruefen(con, kid: int | None) -> None:
    if kid is None:
        return
    r = buch.konto_zeile(con, kid)
    if r is None or r["art"] not in KATEGORIEARTEN:
        raise ApiFehler(422, "kategorie_ungueltig", "Die Standardkategorie muss ein Aufwands- oder Ertragskonto sein.")


def _aliase_schreiben(con, eid: int, aliase: list[str]) -> None:
    con.execute("DELETE FROM empfaenger_alias WHERE empfaenger_id = ?", (eid,))
    con.executemany("INSERT INTO empfaenger_alias (empfaenger_id, alias, ekey) VALUES (?, ?, ?)",
                    [(eid, a, ekey(a)) for a in aliase])


def empfaenger_anlegen(con, d: dict) -> dict:
    aliase = aliase_bereinigen(d.get("aliase") or [], ["body", "aliase"])
    if con.execute("SELECT 1 FROM empfaenger WHERE name = ?", (d["name"],)).fetchone():
        raise ApiFehler(409, "empfaenger_existiert", "Ein Empfänger mit diesem Namen existiert bereits.")
    _aliase_pruefen(con, aliase, None)
    _standardkategorie_pruefen(con, d.get("standardkategorie_id"))
    eid = con.execute("INSERT INTO empfaenger (name, extern_id, standardkategorie_id) VALUES (?, NULL, ?)",
                      (d["name"], d.get("standardkategorie_id"))).lastrowid
    _aliase_schreiben(con, eid, aliase)
    return buch.empfaenger_lesen(con, eid)


def empfaenger_aendern(con, eid: int, d: dict) -> dict:
    alt = buch.empfaenger_lesen(con, eid)
    aliase = aliase_bereinigen(d["aliase"], ["body", "aliase"]) if "aliase" in d else None
    if "name" in d and d["name"] != alt["name"]:
        if con.execute("SELECT 1 FROM empfaenger WHERE name = ? AND id <> ?", (d["name"], eid)).fetchone():
            raise ApiFehler(409, "empfaenger_existiert", "Ein anderer Empfänger trägt bereits diesen Namen.")
    if aliase is not None:
        _aliase_pruefen(con, aliase, eid)
    if "standardkategorie_id" in d:
        _standardkategorie_pruefen(con, d["standardkategorie_id"])
    con.execute("UPDATE empfaenger SET name = ?, standardkategorie_id = ? WHERE id = ?",
                (d.get("name", alt["name"]), d.get("standardkategorie_id", alt["standardkategorie_id"]), eid))
    if aliase is not None and aliase != alt["aliase"]:
        _aliase_schreiben(con, eid, aliase)
    return buch.empfaenger_lesen(con, eid)


def empfaenger_loeschen(con, eid: int) -> None:
    buch.empfaenger_lesen(con, eid)
    if con.execute("SELECT 1 FROM buchung WHERE empfaenger_id = ? LIMIT 1", (eid,)).fetchone():
        raise ApiFehler(409, "empfaenger_in_verwendung", "Auf den Empfänger verweisen noch Buchungen.")
    con.execute("DELETE FROM empfaenger WHERE id = ?", (eid,))


def empfaenger_zusammenfuehren(con, ziel_id: int, quelle_ids: list[int]) -> dict:
    ziel = buch.empfaenger_lesen(con, ziel_id)
    if ziel_id in quelle_ids:
        raise Validierungsfehler([fehler_eintrag(["body", "quelle_ids"], "Das Ziel darf keine Quelle sein.")])
    quellen = buch.empfaenger_laden(con, quelle_ids)
    fehlend = sorted(set(quelle_ids) - {q["id"] for q in quellen})
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Empfänger.", {"empfaenger_ids": fehlend})
    beteiligt = {ziel_id, *quelle_ids}
    belegt = {r["ekey"] for r in con.execute("SELECT ekey, empfaenger_id FROM empfaenger_alias")
              if r["empfaenger_id"] not in beteiligt}
    zielkey = ekey(ziel["name"])
    neu: list[str] = []
    schluessel: set[str] = set()
    for kand in list(ziel["aliase"]) + [x for q in sorted(quellen, key=lambda q: q["id"])
                                        for x in [q["name"], *q["aliase"]]]:
        k = ekey(kand)
        if not k or k == zielkey or k in schluessel or k in belegt:
            continue
        schluessel.add(k)
        neu.append(kand)
    ph = buch._platzhalter(len(quelle_ids))
    con.execute(f"UPDATE buchung SET empfaenger_id = ? WHERE empfaenger_id IN ({ph})", (ziel_id, *quelle_ids))
    con.execute(f"DELETE FROM empfaenger WHERE id IN ({ph})", quelle_ids)
    _aliase_schreiben(con, ziel_id, sorted(neu))
    return buch.empfaenger_lesen(con, ziel_id)


# ================================================== Erfassungshilfe (3)


def korrektur_id(con) -> int:
    r = con.execute("SELECT id FROM konto WHERE extern_id = ?", (KORREKTUR,)).fetchone()
    if r is None:
        r = con.execute(
            "INSERT INTO konto (name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz, extern_id)"
            " VALUES ('Korrekturen', 'eigenkapital', NULL, NULL, 0, NULL, '', ?) RETURNING id", (KORREKTUR,)).fetchone()
    return r["id"]


def erfassen(con, d: dict, lernmodell_automatisch: bool = False) -> dict:
    art, betrag = d["art"], d["betrag"]
    fehler = []
    if art == "korrektur" and betrag == 0:
        fehler.append(fehler_eintrag(["body", "betrag"], "Eine Korrektur braucht einen Betrag ungleich 0."))
    if art != "korrektur" and betrag <= 0:
        fehler.append(fehler_eintrag(["body", "betrag"], "Der Betrag muss größer als 0 sein."))
    if art == "umbuchung" and d.get("kategorie_id") is not None:
        fehler.append(fehler_eintrag(["body", "kategorie_id"], "Bei einer Umbuchung gibt es keine Kategorie."))
    if art != "umbuchung" and "gegenkonto_id" in d:
        fehler.append(fehler_eintrag(["body", "gegenkonto_id"], "Ein Gegenkonto gibt es nur bei Umbuchungen."))
    if art == "umbuchung" and "gegenkonto_id" not in d:
        fehler.append(fehler_eintrag(["body", "gegenkonto_id"], "Bei einer Umbuchung ist das Gegenkonto Pflicht."))
    if d.get("empfaenger_id") is not None and "empfaenger_name" in d:
        fehler.append(fehler_eintrag(["body", "empfaenger_name"], "Nur empfaenger_id oder empfaenger_name angeben."))
    if fehler:
        raise Validierungsfehler(fehler)
    konto = buch.konto_zeile(con, d["konto_id"])
    gegen = buch.konto_zeile(con, d["gegenkonto_id"]) if art == "umbuchung" else None
    if konto is None or (art == "umbuchung" and gegen is None):
        raise ApiFehler(422, "referenz_unbekannt", "Das Konto existiert nicht.")
    buch._empfaenger_pruefen(con, d.get("empfaenger_id"))
    tag_ids = buch._tags_pruefen(con, d.get("tag_ids") or [])
    if konto["art"] not in BESTAND or (gegen is not None and (gegen["art"] not in BESTAND or gegen["id"] == konto["id"])):
        raise ApiFehler(422, "konto_ungueltig", "Erfasst wird auf Bestandskonten; Konto und Gegenkonto verschieden.")
    kat = d.get("kategorie_id")
    if kat is not None:
        buch._kategorie_ziel(con, kat)
    empf_id = d.get("empfaenger_id")
    lern = None
    if lernmodell_automatisch and art in ("ausgabe", "einnahme") and kat is None:
        # M4 (buchhaltungspflege.md 9): Trainingsmenge zu Beginn der Anfrage
        from . import lernmodell
        if "empfaenger_name" in d:
            lern_name = d["empfaenger_name"]
        elif empf_id is not None:
            lern_name = con.execute("SELECT name FROM empfaenger WHERE id = ?", (empf_id,)).fetchone()["name"]
        else:
            lern_name = None
        lern = lernmodell.trainieren(con).vorhersage(lernmodell.merkmale(
            lern_name, d.get("verwendungszweck", ""), -betrag if art == "ausgabe" else betrag))
    if "empfaenger_name" in d:
        empf_id = buch.empfaenger_bestimmen(con, d["empfaenger_name"])
    k = konto["id"]
    vorschlag = None
    if art == "umbuchung":
        splits = [(k, -betrag), (gegen["id"], betrag)]
    else:
        if kat is not None:
            g = kat
        elif art == "korrektur":
            g = korrektur_id(con)
        else:
            std = None
            if empf_id is not None:
                std = con.execute("SELECT standardkategorie_id FROM empfaenger WHERE id = ?",
                                  (empf_id,)).fetchone()["standardkategorie_id"]
            unk = buch.unkategorisiert_id(con)
            g = unk
            if std is not None:
                g = std
                vorschlag = (std, unk, "standardkategorie", None)
            elif lern is not None and lern.kategorie_id is not None:
                g = lern.kategorie_id
                vorschlag = (g, unk, "lernmodell", lern.sicherheit)
        vorzeichen = {"ausgabe": -1, "einnahme": 1, "korrektur": 1}[art]
        splits = [(k, vorzeichen * betrag), (g, -vorzeichen * betrag)]
    memo = d.get("memo", "")
    bid = buch.buchung_einfuegen(con, d["datum"], empf_id, d.get("verwendungszweck", ""),
                                 d.get("status", "bestaetigt"),
                                 [{"konto_id": kid, "betrag": b, "memo": memo} for kid, b in splits], tag_ids)
    if vorschlag:
        con.execute("INSERT INTO vorschlag (buchung_id, kategorie_id, regel_id, quelle, vorher_konto_id, sicherheit)"
                    " VALUES (?, ?, NULL, ?, ?, ?)", (bid, vorschlag[0], vorschlag[2], vorschlag[1], vorschlag[3]))
    return buch.buchung_lesen(con, bid)


# ======================================================== Umbuchungen (4)


def _kandidaten(con) -> list[dict]:
    """4.1: genau zwei Splits, einer auf einem Bestandskonto (≠ 0), einer auf „Unkategorisiert“."""
    r = con.execute("SELECT id FROM konto WHERE extern_id = ?", (buch.UNKATEGORISIERT,)).fetchone()
    if r is None:
        return []
    unk = r["id"]
    ids = [z["buchung_id"] for z in con.execute(
        "SELECT s.buchung_id FROM split s WHERE s.konto_id = ? GROUP BY s.buchung_id"
        " HAVING (SELECT COUNT(*) FROM split t WHERE t.buchung_id = s.buchung_id) = 2 ORDER BY s.buchung_id",
        (unk,))]
    art_von = buch.kontoarten(con)
    iban = {z["id"]: z["iban"] for z in con.execute("SELECT id, iban FROM konto")}
    aus = []
    for teil in buch._stueckweise(ids):
        for b in buch.buchungen_laden(con, teil, art_von=art_von):
            if buch.ist_gesperrt(b) or b["vorschlag"] is not None:
                continue
            bank = [s for s in b["splits"] if art_von[s["konto_id"]] in BESTAND]
            gegen = [s for s in b["splits"] if s["konto_id"] == unk]
            if len(bank) != 1 or len(gegen) != 1 or bank[0]["betrag"] == 0:
                continue
            aus.append({"id": b["id"], "datum": dt.date.fromisoformat(b["datum"]), "konto": bank[0]["konto_id"],
                        "betrag": bank[0]["betrag"], "gegen_iban": b["gegen_iban"], "iban": iban[bank[0]["konto_id"]],
                        "bank": bank[0], "unk": gegen[0]})
    return aus


def _passen(x: dict, y: dict, fenster: int) -> bool:
    if x["konto"] == y["konto"] or x["betrag"] != -y["betrag"]:
        return False
    if abs((x["datum"] - y["datum"]).days) > fenster:
        return False
    gx, gy = x["gegen_iban"], y["gegen_iban"]
    if (gx is not None and gx != y["iban"]) or (gy is not None and gy != x["iban"]):
        return False
    return (gx is not None and gx == y["iban"]) or (gy is not None and gy == x["iban"])


def eindeutige_paare(con, fenster: int) -> list[tuple[int, int]]:
    """4.3: gegenseitig eindeutige Paare (behalten_id, entfernt_id), aufsteigend."""
    c = _kandidaten(con)
    nach_betrag: dict[int, list[dict]] = defaultdict(list)
    for x in c:
        nach_betrag[x["betrag"]].append(x)
    partner: dict[int, set[int]] = {}
    for x in c:
        partner[x["id"]] = {y["id"] for y in nach_betrag.get(-x["betrag"], []) if y["id"] != x["id"]
                            and _passen(x, y, fenster)}
    paare = set()
    for x, ys in partner.items():
        if len(ys) == 1:
            (y,) = ys
            if partner[y] == {x}:
                paare.add((min(x, y), max(x, y)))
    return sorted(paare)


def _zusammenfuehren(con, xid: int, yid: int) -> None:
    """4.3 Zusammenführen: X bleibt, Y entfällt; Bankseiten behalten ihre Split-IDs."""
    art_von = buch.kontoarten(con)
    x, y = buch.buchungen_laden(con, [xid, yid], art_von=art_von)
    bx = next(s for s in x["splits"] if art_von[s["konto_id"]] in BESTAND)
    by = next(s for s in y["splits"] if art_von[s["konto_id"]] in BESTAND)
    con.execute("DELETE FROM split WHERE buchung_id = ? AND id <> ?", (xid, bx["id"]))
    con.execute("UPDATE split SET position = 0 WHERE id = ?", (bx["id"],))
    con.execute("UPDATE split SET buchung_id = ?, position = 1 WHERE id = ?", (xid, by["id"]))
    con.execute("UPDATE buchung_extern SET buchung_id = ? WHERE buchung_id = ?", (xid, yid))
    con.execute("INSERT OR IGNORE INTO buchung_tag (buchung_id, tag_id) SELECT ?, tag_id FROM buchung_tag"
                " WHERE buchung_id = ?", (xid, yid))
    con.execute("DELETE FROM vorschlag WHERE buchung_id = ?", (xid,))
    buch.buchung_entfernen(con, yid)


def umbuchungen_erkennen(con, trocken: bool, fenster: int, nur_mit: set[int] | None = None) -> dict:
    paare = eindeutige_paare(con, fenster)
    if nur_mit is not None:
        paare = [p for p in paare if p[0] in nur_mit or p[1] in nur_mit]
    if not trocken:
        for x, y in paare:
            _zusammenfuehren(con, x, y)
    return {"trocken": trocken, "anzahl": len(paare),
            "paare": [{"behalten_id": x, "entfernt_id": y} for x, y in paare]}


def umbuchung_von_hand(con, ids: list[int]) -> dict:
    vorhanden = buch._vorhandene_buchungen(con, ids)
    fehlend = sorted(set(ids) - vorhanden)
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    bs = buch.buchungen_laden(con, sorted(ids))
    gesperrt = [b["id"] for b in bs if buch.ist_gesperrt(b)]
    if gesperrt:
        raise ApiFehler(409, "buchung_gesperrt", "Gesperrte Buchungen können nicht zusammengeführt werden.",
                        {"buchung_ids": gesperrt})
    kand = {c["id"]: c for c in _kandidaten(con) if c["id"] in ids}
    if len(kand) != 2:
        raise ApiFehler(422, "keine_umbuchung", "Beide Buchungen müssen einzelne, unkategorisierte Bankumsätze sein.")
    x, y = kand[min(ids)], kand[max(ids)]
    if x["konto"] == y["konto"] or x["betrag"] != -y["betrag"]:
        raise ApiFehler(422, "keine_umbuchung", "Die Buchungen sind keine Gegenbuchungen auf verschiedenen Konten.")
    _zusammenfuehren(con, x["id"], y["id"])
    return buch.buchung_lesen(con, x["id"])


# ==================================================== Kontenabstimmung (5)


def abstimmen(con, d: dict, jetzt: str) -> dict:
    k = buch.konto_zeile(con, d["konto_id"])
    if k is None:
        raise ApiFehler(422, "referenz_unbekannt", "Das Konto existiert nicht.")
    if k["art"] not in BESTAND:
        raise ApiFehler(422, "konto_ungueltig", "Abgestimmt werden nur Bestandskonten.")
    kid, stichtag = k["id"], d["stichtag"]
    berechnet = con.execute("SELECT COALESCE(SUM(s.betrag), 0) AS s FROM split s JOIN buchung b ON b.id = s.buchung_id"
                            " WHERE s.konto_id = ? AND b.datum <= ?", (kid, stichtag)).fetchone()["s"]
    m = [r["id"] for r in con.execute("SELECT s.id FROM split s JOIN buchung b ON b.id = s.buchung_id"
                                      " WHERE s.konto_id = ? AND s.abstimmung_id IS NULL AND b.datum <= ?",
                                      (kid, stichtag))]
    differenz = d["saldo"] - berechnet
    abstimmung = None
    if differenz == 0 and not d.get("trocken", False):
        aid = con.execute("INSERT INTO abstimmung (konto_id, stichtag, saldo, erstellt_am) VALUES (?, ?, ?, ?)",
                          (kid, stichtag, d["saldo"], jetzt)).lastrowid
        con.executemany("UPDATE split SET abstimmung_id = ? WHERE id = ?", [(aid, s) for s in m])
        abstimmung = abstimmung_lesen(con, aid)
    return {"konto_id": kid, "stichtag": stichtag, "saldo": d["saldo"], "berechneter_saldo": berechnet,
            "differenz": differenz, "stimmt": differenz == 0, "abgestimmt": abstimmung is not None,
            "anzahl_splits": len(m), "abstimmung": abstimmung}


def abstimmungen_liste(con, konto_id: int | None) -> list[dict]:
    if konto_id is None:
        zeilen = con.execute("SELECT * FROM abstimmung ORDER BY id")
    else:
        zeilen = con.execute("SELECT * FROM abstimmung WHERE konto_id = ? ORDER BY id", (sichere_id(konto_id),))
    return [abstimmung_dict(r) for r in zeilen]


def abstimmung_lesen(con, aid: int) -> dict:
    r = con.execute("SELECT * FROM abstimmung WHERE id = ?", (sichere_id(aid),)).fetchone()
    if r is None:
        raise nicht_gefunden("Die Abstimmung")
    return abstimmung_dict(r)


def abstimmung_aufheben(con, aid: int) -> None:
    a = abstimmung_lesen(con, aid)
    letzte = con.execute("SELECT id FROM abstimmung WHERE konto_id = ? ORDER BY stichtag DESC, id DESC LIMIT 1",
                         (a["konto_id"],)).fetchone()
    if letzte["id"] != aid:
        raise ApiFehler(409, "abstimmung_nicht_letzte", "Nur die letzte Abstimmung eines Kontos kann aufgehoben werden.")
    con.execute("UPDATE split SET abstimmung_id = NULL WHERE abstimmung_id = ?", (aid,))
    con.execute("DELETE FROM abstimmung WHERE id = ?", (aid,))


# ======================================================== Volltextsuche (6)


def snorm(s: str | None) -> str:
    if not s:
        return ""
    z = unicodedata.normalize("NFKD", norm(unicodedata.normalize("NFC", s)))
    return "".join(c for c in z if unicodedata.category(c) != "Mn")


def _trifft(woerter: list[str], felder: list[str]) -> bool:
    return all(any(w in f for f in felder) for w in woerter)


def suche(con, q: str, limit: int) -> dict:
    woerter = [snorm(w) for w in q.split()]
    konten = [k for k in buch.konten_liste(con)
              if _trifft(woerter, [snorm(k["name"]), snorm(k["iban"]), snorm(k["notiz"])])]
    empfaenger = [e for e in buch.empfaenger_liste(con)
                  if _trifft(woerter, [snorm(e["name"])] + [snorm(a) for a in e["aliase"]])]
    tags = [t for t in buch.tags_liste(con) if _trifft(woerter, [snorm(t["name"])])]
    kontoname = {r["id"]: snorm(r["name"]) for r in con.execute("SELECT id, name FROM konto")}
    tagname = {r["id"]: snorm(r["name"]) for r in con.execute("SELECT id, name FROM tag")}
    empfname = {r["id"]: snorm(r["name"]) for r in con.execute("SELECT id, name FROM empfaenger")}
    felder: dict[int, list[str]] = {}
    reihe: list[tuple[str, int]] = []
    for r in con.execute("SELECT id, datum, empfaenger_id, verwendungszweck FROM buchung"):
        f = [snorm(r["verwendungszweck"])]
        if r["empfaenger_id"] is not None:
            f.append(empfname.get(r["empfaenger_id"], ""))
        felder[r["id"]] = f
        reihe.append((r["datum"], r["id"]))
    for r in con.execute("SELECT buchung_id, konto_id, memo FROM split"):
        f = felder.get(r["buchung_id"])
        if f is not None:
            f.append(snorm(r["memo"]))
            f.append(kontoname.get(r["konto_id"], ""))
    for r in con.execute("SELECT buchung_id, tag_id FROM buchung_tag"):
        f = felder.get(r["buchung_id"])
        if f is not None:
            f.append(tagname.get(r["tag_id"], ""))
    treffer = [bid for datum, bid in sorted(reihe, reverse=True) if _trifft(woerter, felder[bid])]
    return {"q": q, "konten": konten, "empfaenger": empfaenger, "tags": tags,
            "buchungen": buch.buchungen_laden(con, treffer[:limit]), "buchungen_gesamt": len(treffer)}


# ============================================== Konto mit Buchungen löschen


def _regel_bezieht(r: dict, kid: int) -> bool:
    return r["kategorie_id"] == kid or any(b["feld"] == "konto_id" and b["wert"] == kid for b in r["bedingungen"])


def konto_loeschen_mit_buchungen(con, kid: int, d: dict) -> dict:
    """loeschen.md 2–4; im Probelauf wird alles in einem Sicherungspunkt gerechnet und verworfen."""
    k = buch.konto_lesen(con, kid)
    variante, konflikte = d["buchungen"], d["konflikte"]
    trocken = d.get("trocken", False)
    if variante == "elternkonto" and k["eltern_id"] is None:
        raise ApiFehler(422, "kein_elternkonto", "Ein Wurzelkonto hat kein übergeordnetes Konto.")
    if variante == "unkategorisiert" and k["extern_id"] == buch.UNKATEGORISIERT:
        raise ApiFehler(422, "ziel_ungueltig", "„Unkategorisiert“ kann nicht nach „Unkategorisiert“ gelöscht werden.")
    betroffen = [r["buchung_id"] for r in con.execute(
        "SELECT DISTINCT buchung_id FROM split WHERE konto_id = ? ORDER BY buchung_id", (kid,))]
    gesperrt = [b["id"] for b in buch.buchungen_laden(con, betroffen) if buch.ist_gesperrt(b)]
    if not trocken and not d.get("gesperrte_einbeziehen", False) and gesperrt:
        raise ApiFehler(409, "buchung_gesperrt", "Betroffene Buchungen sind gesperrt (abgeglichen oder abgestimmt).",
                        {"buchung_ids": gesperrt})
    if trocken:
        con.execute("SAVEPOINT probelauf")
        try:
            unk_vorher = con.execute("SELECT 1 FROM konto WHERE extern_id = ?", (buch.UNKATEGORISIERT,)).fetchone()
            erg = _loeschen_ausfuehren(con, k, variante, konflikte, betroffen, gesperrt)
            if variante == "unkategorisiert" and unk_vorher is None:
                erg["ziel_konto_id"] = None
        finally:
            con.execute("ROLLBACK TO probelauf")
            con.execute("RELEASE probelauf")
    else:
        erg = _loeschen_ausfuehren(con, k, variante, konflikte, betroffen, gesperrt)
    erg["trocken"] = trocken
    return erg


def _loeschen_ausfuehren(con, k: dict, variante: str, konflikte: str, betroffen: list[int],
                         gesperrt: list[int]) -> dict:
    kid = k["id"]
    ziel = None
    if variante == "elternkonto":
        ziel = k["eltern_id"]
    elif variante == "unkategorisiert":
        ziel = buch.unkategorisiert_id(con)
    # 3.6 Abstimmungen von K (vor dem Umbuchen)
    abst = [r["id"] for r in con.execute("SELECT id FROM abstimmung WHERE konto_id = ? ORDER BY id", (kid,))]
    for a in abst:
        con.execute("UPDATE split SET abstimmung_id = NULL WHERE abstimmung_id = ?", (a,))
        con.execute("DELETE FROM abstimmung WHERE id = ?", (a,))
    # 3.1 Unterkonten
    unter = [r["id"] for r in con.execute("SELECT id FROM konto WHERE eltern_id = ? ORDER BY id", (kid,))]
    con.execute("UPDATE konto SET eltern_id = ? WHERE eltern_id = ?", (k["eltern_id"], kid))
    # 3.2/3.3 Buchungen
    geloescht, konfliktb = [], []
    for b in buch.buchungen_laden(con, betroffen):
        if variante == "loeschen":
            buch.buchung_entfernen(con, b["id"])
            geloescht.append(b["id"])
            continue
        splits = [{**s, "konto_id": ziel if s["konto_id"] == kid else s["konto_id"]} for s in b["splits"]]
        if all(s["konto_id"] == ziel for s in splits):
            konfliktb.append(b["id"])
            if konflikte == "loeschen":
                buch.buchung_entfernen(con, b["id"])
                geloescht.append(b["id"])
                continue
        else:
            frei = [s for s in splits if s["konto_id"] == ziel and s["abstimmung_id"] is None]
            if len(frei) >= 2:
                erster = frei[0]
                memos: list[str] = []
                for s in frei:
                    if s["memo"] and s["memo"] not in memos:
                        memos.append(s["memo"])
                weg = {s["id"] for s in frei[1:]}
                erster.update(betrag=sum(s["betrag"] for s in frei), memo=" / ".join(memos))
                splits = [s for s in splits if s["id"] not in weg]
                con.executemany("DELETE FROM split WHERE id = ?", [(i,) for i in sorted(weg)])
        for pos, s in enumerate(splits):
            con.execute("UPDATE split SET konto_id = ?, betrag = ?, memo = ?, position = ? WHERE id = ?",
                        (s["konto_id"], s["betrag"], s["memo"], pos, s["id"]))
        con.execute("DELETE FROM vorschlag WHERE buchung_id = ?", (b["id"],))
    # 3.4 Regeln
    r_geaendert, r_geloescht = [], []
    for r in regeln.regeln_liste(con):
        if not _regel_bezieht(r, kid):
            continue
        if variante == "elternkonto":
            neu_b = [{**b, "wert": ziel} if b["feld"] == "konto_id" and b["wert"] == kid else b
                     for b in r["bedingungen"]]
            con.execute("UPDATE regel SET kategorie_id = ?, bedingungen = ? WHERE id = ?",
                        (ziel if r["kategorie_id"] == kid else r["kategorie_id"],
                         json.dumps(neu_b, ensure_ascii=False), r["id"]))
            r_geaendert.append(r["id"])
        else:
            regeln.regel_loeschen(con, r["id"])
            r_geloescht.append(r["id"])
    # M4 (loeschen.md 6): Split-Vorlagen wie Regeln
    from . import vorlagen
    vorlagen.konto_loeschen(con, kid, ziel if variante == "elternkonto" else None)
    # 3.5 Standardkategorien
    empf = [r["id"] for r in con.execute("SELECT id FROM empfaenger WHERE standardkategorie_id = ? ORDER BY id",
                                         (kid,))]
    con.execute("UPDATE empfaenger SET standardkategorie_id = ? WHERE standardkategorie_id = ?",
                (ziel if variante == "elternkonto" else None, kid))
    # 3.7 Konto
    con.execute("DELETE FROM konto WHERE id = ?", (kid,))
    return {
        "konto_id": kid, "buchungen": variante, "konflikte": konflikte, "ziel_konto_id": ziel,
        "buchungen_betroffen": betroffen, "buchungen_geloescht": sorted(geloescht),
        "buchungen_umgebucht": sorted(set(betroffen) - set(geloescht)), "konfliktbuchungen": sorted(konfliktb),
        "gesperrt": gesperrt, "unterkonten": unter, "regeln_geaendert": sorted(r_geaendert),
        "regeln_geloescht": sorted(r_geloescht), "empfaenger_geaendert": empf, "abstimmungen_geloescht": abst,
        "aenderung_id": None,
    }


def gegen_iban(roh) -> str | None:
    """1.1: Gegen-IBAN normalisiert, wenn gültig, sonst None."""
    if not isinstance(roh, str):
        return None
    n = iban_normalisieren(roh)
    return n if iban_gueltig(n) else None
