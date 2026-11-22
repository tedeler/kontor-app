"""Erwartete Zahlungen (Feature ``mail-abgleich``, D-128).

Eine erwartete Zahlung ist ein Objekt des Buchbestands (Objektart ``erwartung``): Geld, das noch abgehen oder
eingehen soll, jeweils mit **Grund** (Bestellung, PayPal-Zahlung, Rückerstattung, manuell). Sie ist keine Buchung
und ändert keinen Saldo (K 16: keine Kontostandsprognose). Ihr Betrag ist nur der **Bankanteil**: Was aus einem
Guthaben (Amazon-Gutschein, PayPal-Guthaben) bezahlt wurde, bleibt außerhalb der Buchhaltung (Variante A).

Ablauf:

1. ``erkennen``: gespiegelte Mails (Betriebszustand) → erwartete Zahlungen; Mails derselben Bestellung bzw.
   Transaktion landen bei derselben Erwartung (``schluessel``), Stornos schließen die Bestellung.
2. ``automatisch_zuordnen``: eindeutige Bankbuchungen (Kennung im Verwendungszweck, oder einziger Kandidat mit
   gleichem Betrag und Anbietername) werden zugeordnet; die Mails hängen danach als Dokumente an der Buchung.
3. Alles andere bestätigt der Anwender über ``kandidaten`` / ``zuordnen``.

„Überfällig“ ist abgeleitet: offen und die Frist (Datum + ``mail_abgleich_frist_tage``) ist vorbei.
"""

from __future__ import annotations

import datetime as dt
import json
import re

from . import anbieter, buch, dokumente, mailerkennung, wiederkehrend
from .validierung import ApiFehler, Feld, Validierungsfehler, datum_gueltig, fehler_eintrag, pruefe_objekt

GRUENDE = ("bestellung", "paypal", "rueckerstattung", "manuell")
RICHTUNGEN = ("ausgabe", "eingang")
ZUSTAENDE = ("offen", "erfuellt", "guthaben", "storniert", "erledigt")
# Zustände, die der Anwender setzen kann (nur aus „offen“ bzw. zurück nach „offen“)
SCHLIESSEN = ("guthaben", "storniert", "erledigt")
FENSTER_VOR = 3      # Kandidaten: Buchungsdatum frühestens so viele Tage vor dem Datum der Erwartung …
FENSTER_NACH = 45    # … und spätestens so viele Tage danach
MAX_BETRAG = 999999999999

RHYTHMEN = ("monatlich", "vierteljaehrlich", "halbjaehrlich", "jaehrlich")      # D-238
MONATE = {"monatlich": 1, "vierteljaehrlich": 3, "halbjaehrlich": 6, "jaehrlich": 12}
S = Feld
NEU = {"richtung": S("enum", pflicht=True, werte=RICHTUNGEN),
       "haendler": S("str", pflicht=True, min_len=1, max_len=200, strip=True),
       "betrag": S("int", pflicht=True), "datum": S("datum"), "frist": S("datum"),
       "beschreibung": S("str", max_len=2000), "kennung": S("str", max_len=200),
       # D-238: geplante Zahlung mit Wiederholung; „keine“ nimmt sie zurück
       "wiederholung": S("enum", werte=("keine",) + RHYTHMEN), "wiederholung_bis": S("datum", nullbar=True)}
AENDERUNG = {k: S(v.typ, min_len=v.min_len, max_len=v.max_len, strip=v.strip, werte=v.werte, nullbar=v.nullbar)
             for k, v in NEU.items()
             if k != "richtung"}


def _pruefen(d, schema: dict) -> dict:
    fehler: list[dict] = []
    aus = pruefe_objekt(d, schema, ["body"], fehler)
    if fehler:
        raise Validierungsfehler(fehler)
    return aus


def _fehler(code: str, meldung: str, status: int = 422) -> ApiFehler:
    return ApiFehler(status, code, meldung)


def _plus(datum: str, tage: int) -> str:
    return (dt.date.fromisoformat(datum) + dt.timedelta(days=tage)).isoformat()


# ================================================================ Lesen und Protokollform


def _form(r) -> dict:
    return {"id": r["id"], "grund": r["grund"], "richtung": r["richtung"], "anbieter": r["anbieter"],
            "schluessel": r["schluessel"], "kennung": r["kennung"], "referenz": r["referenz"],
            "haendler": r["haendler"], "beschreibung": r["beschreibung"], "betrag": r["betrag"],
            "gesamt": r["gesamt"], "guthaben": r["guthaben"], "datum": r["datum"], "frist": r["frist"],
            "zustand": r["zustand"], "bezug_id": r["bezug_id"], "buchung_ids": json.loads(r["buchung_ids"]),
            "mails": json.loads(r["mails"]), "dokument_ids": json.loads(r["dokument_ids"]),
            "erstellt_am": r["erstellt_am"]}


def _wiederholung_form(w) -> dict:
    return {"rhythmus": w["rhythmus"], "tag": w["tag"], "bis": w["bis"], "vorgaenger_id": w["vorgaenger_id"]}


def formen(con, ids: list[int]) -> dict[int, dict]:
    aus = {}
    for teil in buch._stueckweise(sorted(set(ids))):
        for r in con.execute(f"SELECT * FROM erwartung WHERE id IN ({buch._platzhalter(len(teil))})", teil):
            aus[r["id"]] = _form(r)
        # Wiederholung (D-238): nur in Formen geplanter Zahlungen, die eine haben
        for w in con.execute("SELECT * FROM erwartung_wiederholung WHERE erwartung_id IN"
                             f" ({buch._platzhalter(len(teil))})", teil):
            if w["erwartung_id"] in aus:
                aus[w["erwartung_id"]]["wiederholung"] = _wiederholung_form(w)
    return aus


_SPALTEN = ("id", "grund", "richtung", "anbieter", "schluessel", "kennung", "referenz", "haendler", "beschreibung",
            "betrag", "gesamt", "guthaben", "datum", "frist", "zustand", "bezug_id", "buchung_ids", "mails",
            "dokument_ids", "erstellt_am")


def einfuegen(con, f: dict) -> None:
    """Protokollform → Zeile (Rückgängig, Sicherung)."""
    werte = [json.dumps(f[s], ensure_ascii=False) if s in ("buchung_ids", "mails", "dokument_ids") else f[s]
             for s in _SPALTEN]
    con.execute(f"INSERT INTO erwartung ({', '.join(_SPALTEN)}) VALUES ({', '.join('?' * len(_SPALTEN))})", werte)
    w = f.get("wiederholung")
    if w:
        con.execute("INSERT INTO erwartung_wiederholung (erwartung_id, rhythmus, tag, bis, vorgaenger_id)"
                    " VALUES (?, ?, ?, ?, ?)", (f["id"], w["rhythmus"], w["tag"], w["bis"], w["vorgaenger_id"]))


def _zeile(con, eid: int):
    r = con.execute("SELECT * FROM erwartung WHERE id = ?", (buch.sichere_id(eid),)).fetchone()
    if r is None:
        raise buch.nicht_gefunden("Die erwartete Zahlung")
    return r


def _bankbuchungen(con, ids: list[int]) -> dict[int, dict]:
    """Buchungen mit genau einem Split auf einem Bestandskonto: ID → {datum, betrag, konto_id, …}."""
    aus: dict[int, dict] = {}
    ph_art = ", ".join("?" * len(buch.BESTAND))
    for teil in buch._stueckweise(sorted(set(ids))):
        for r in con.execute(
                "SELECT b.id, b.datum, b.verwendungszweck, e.name AS empfaenger, MIN(s.betrag) AS betrag,"
                " MIN(s.konto_id) AS konto_id, MIN(k.name) AS konto, COUNT(*) AS n"
                " FROM buchung b JOIN split s ON s.buchung_id = b.id"
                f" JOIN konto k ON k.id = s.konto_id AND k.art IN ({ph_art})"
                " LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
                f" WHERE b.id IN ({buch._platzhalter(len(teil))}) GROUP BY b.id",
                (*buch.BESTAND, *teil)):
            if r["n"] == 1:
                aus[r["id"]] = {"id": r["id"], "datum": r["datum"], "betrag": r["betrag"],
                                "konto_id": r["konto_id"], "konto": r["konto"], "empfaenger": r["empfaenger"],
                                "verwendungszweck": r["verwendungszweck"]}
    return aus


def _zugeordnet(con, ids: list[int]) -> int:
    return sum(abs(b["betrag"]) for b in _bankbuchungen(con, ids).values())


def erwartung_dict(con, r, heute: str) -> dict:
    f = _form(r)
    del f["schluessel"]
    zug = _zugeordnet(con, f["buchung_ids"]) if f["buchung_ids"] else 0
    f["zugeordnet"] = zug
    f["offen_betrag"] = max(0, f["betrag"] - zug) if f["zustand"] == "offen" else 0
    f["ueberfaellig"] = f["zustand"] == "offen" and f["frist"] < heute
    f["vorzeichen_betrag"] = -f["betrag"] if f["richtung"] == "ausgabe" else f["betrag"]
    w = con.execute("SELECT * FROM erwartung_wiederholung WHERE erwartung_id = ?", (r["id"],)).fetchone()
    if w is not None:   # D-238: Feld nur bei geplanten Zahlungen mit Wiederholung
        f["wiederholung"] = {"rhythmus": w["rhythmus"], "bis": w["bis"]}
    return f


def _warum(z, b: dict) -> str:
    """Warum diese Buchung zur Erwartung passt, gelesen an Kennung, Betrag und Namen."""
    zweck = _kompakt(b.get("verwendungszweck"))
    empf = _kompakt(b.get("empfaenger"))
    for feld, name in (("kennung", "Kennung"), ("referenz", "Referenz")):
        roh = z[feld] or ""
        k = _kompakt(roh)
        if len(k) < 6:
            continue
        if k in zweck:
            return f"Die {name} „{roh}“ steht im Verwendungszweck."
        if k in empf:
            return f"Die {name} „{roh}“ steht beim Empfänger."
    if abs(b["betrag"]) == z["betrag"] and _anbieter_passt(z, b):
        return "Der Betrag stimmt, und der Name des Händlers oder Anbieters steht in der Buchung."
    return "Manuell zugeordnet. Kennung, Betrag und Name erklären die Buchung nicht von selbst."


def zuordnungen_nach_mail(con, heute: str) -> dict[tuple[str, str], list[dict]]:
    """Je gespiegelter Mail (Postfach, Nachrichten-ID) die Erwartungen, die sie begründet haben, samt Buchungen."""
    zeilen = list(con.execute("SELECT * FROM erwartung"))
    ids: list[int] = []
    gelesen: list[tuple] = []
    for r in zeilen:
        buchung_ids = json.loads(r["buchung_ids"])
        ids.extend(buchung_ids)
        gelesen.append((r, buchung_ids, json.loads(r["mails"])))
    bank = _bankbuchungen(con, ids)
    aus: dict[tuple[str, str], list[dict]] = {}
    for r, buchung_ids, mails in gelesen:
        buchungen = []
        for bid in buchung_ids:
            b = bank.get(bid)
            if b is None:
                continue
            buchungen.append({**b, "warum": _warum(r, b)})
        eintrag = {"erwartung_id": r["id"], "grund": r["grund"], "zustand": r["zustand"],
                   "ueberfaellig": r["zustand"] == "offen" and r["frist"] < heute,
                   "haendler": r["haendler"], "kennung": r["kennung"],
                   "vorzeichen_betrag": -r["betrag"] if r["richtung"] == "ausgabe" else r["betrag"],
                   "buchungen": buchungen}
        for m in mails:
            aus.setdefault((m.get("postfach") or "", m.get("nachricht_id") or ""), []).append(eintrag)
    return aus


def lesen(con, eid: int, heute: str) -> dict:
    aus = erwartung_dict(con, _zeile(con, eid), heute)
    aus["buchungen"] = list(_bankbuchungen(con, aus["buchung_ids"]).values())
    aus["mail_eintraege"] = _mails_lesen(con, aus["mails"])
    return aus


def _mails_lesen(con, mails: list[dict]) -> list[dict]:
    aus = []
    for m in mails:
        r = con.execute("SELECT n.id, n.empfangen, n.absender, n.betreff FROM mail_nachricht n"
                        " WHERE n.adresse_cf = ? AND n.nachricht_id = ?", (m["postfach"], m["nachricht_id"])).fetchone()
        aus.append({"postfach": m["postfach"], "nachricht_id": m["nachricht_id"], "betreff": m.get("betreff", ""),
                    "empfangen": m.get("empfangen"), "spiegel_id": r["id"] if r else None})
    return aus


def _serien(con, heute: str, frist_tage: int) -> list[dict]:
    """D-128: nächste Zahlung jeder aktiven oder ausbleibenden wiederkehrenden Serie als erwartete Zahlung mit
    Grund ``serie`` (abgeleitet, nicht gespeichert; Schließen/Zuordnen geschieht über die Buchungen selbst)."""
    aus = []
    belegt = _alle_zugeordneten(con)   # jede gespeicherte Erwartung, auch manuelle (M24 1.2, D-142)
    for s in wiederkehrend.uebersicht(con, heute)["serien"]:
        if s["status"] not in ("aktiv", "ausbleibend"):
            continue
        if s["buchung_ids"] and s["buchung_ids"][-1] in belegt:
            continue  # regelmäßige Einkäufe, die schon über Bestell-/Zahlungsmails erwartet werden: nicht doppelt
        betrag = abs(s["betrag"])
        frist = _plus(s["naechste_faelligkeit"], frist_tage)
        aus.append({"id": f"serie:{s['schluessel']}", "grund": "serie",
                    "richtung": "ausgabe" if s["richtung"] == "ausgabe" else "eingang", "anbieter": None,
                    "kennung": "", "referenz": "", "haendler": (s["empfaenger"] or {}).get("name") or "",
                    "beschreibung": f"{s['rhythmus']}, zuletzt {s['letzte']}", "betrag": betrag, "gesamt": betrag,
                    "guthaben": 0, "datum": s["naechste_faelligkeit"], "frist": frist, "zustand": "offen",
                    "bezug_id": None, "buchung_ids": [], "mails": [], "dokument_ids": [], "erstellt_am": None,
                    "zugeordnet": 0, "offen_betrag": betrag, "ueberfaellig": frist < heute,
                    "vorzeichen_betrag": -betrag if s["richtung"] == "ausgabe" else betrag,
                    "konto_id": s["konto_id"], "serie": s["schluessel"]})
    return aus


def liste(con, heute: str, gruende: list[str] | None = None, zustaende: list[str] | None = None,
          faellig_bis: str | None = None, suche: str | None = None, richtung: str | None = None,
          frist_tage: int = 5, serien: bool = False) -> dict:
    """„Was kommt noch?“ (D-128). ``zustaende`` kennt zusätzlich ``ueberfaellig``; ohne Angabe: offen. Serien
    (Grund ``serie``) erscheinen bei offenen bzw. überfälligen Einträgen."""
    zustaende = zustaende or ["offen"]
    # Serien nur auf Anfrage (`grund=serie` oder `serien=ja` ohne Grundfilter), damit die Liste ohne diese Angaben
    # unverändert bleibt (D-139)
    mit_serien = (("serie" in (gruende or [])) or (serien and not gruende)) and (
        "offen" in zustaende or "ueberfaellig" in zustaende)
    gruende = [g for g in (gruende or []) if g != "serie"] or (None if not gruende else ["-"])
    wo, par = [], []
    if gruende:
        wo.append(f"grund IN ({', '.join('?' * len(gruende))})")
        par += gruende
    if richtung:
        wo.append("richtung = ?")
        par.append(richtung)
    if faellig_bis:
        wo.append("frist <= ?")
        par.append(faellig_bis)
    teile = []
    echte = [z for z in zustaende if z != "ueberfaellig"]
    if echte:
        teile.append(f"zustand IN ({', '.join('?' * len(echte))})")
        par += echte
    if "ueberfaellig" in zustaende:
        teile.append("(zustand = 'offen' AND frist < ?)")
        par.append(heute)
    wo.append("(" + " OR ".join(teile) + ")")
    zeilen = con.execute("SELECT * FROM erwartung WHERE " + " AND ".join(wo) + " ORDER BY frist, id", par).fetchall()
    eintraege = [erwartung_dict(con, r, heute) for r in zeilen]
    if mit_serien:
        for e in _serien(con, heute, frist_tage):
            if richtung and e["richtung"] != richtung:
                continue
            if faellig_bis and e["frist"] > faellig_bis:
                continue
            if "offen" not in zustaende and not e["ueberfaellig"]:
                continue
            eintraege.append(e)
        eintraege.sort(key=lambda e: (e["frist"], isinstance(e["id"], str),
                                      e["id"] if isinstance(e["id"], int) else 0, str(e["id"])))
    if suche:
        s = suche.casefold()
        eintraege = [e for e in eintraege if any(s in (e[k] or "").casefold()
                                                 for k in ("haendler", "beschreibung", "kennung", "referenz"))]
    summe = sum(e["offen_betrag"] if e["richtung"] == "eingang" else -e["offen_betrag"] for e in eintraege)
    return {"eintraege": eintraege, "anzahl": len(eintraege), "summe_offen": summe,
            "ueberfaellig": sum(1 for e in eintraege if e["ueberfaellig"])}


# ================================================================ Erkennen aus dem Mail-Spiegel


def _mail_eintrag(r) -> dict:
    return {"postfach": r["adresse_cf"], "nachricht_id": r["nachricht_id"], "betreff": r["betreff"][:200],
            "empfangen": r["empfangen"]}


def _mail_hinzu(con, zeile, r) -> None:
    mails = json.loads(zeile["mails"])
    if any(m["postfach"] == r["adresse_cf"] and m["nachricht_id"] == r["nachricht_id"] for m in mails):
        return
    mails.append(_mail_eintrag(r))
    con.execute("UPDATE erwartung SET mails = ? WHERE id = ?", (json.dumps(mails, ensure_ascii=False), zeile["id"]))


def _nach_schluessel(con, schluessel: str):
    return con.execute("SELECT * FROM erwartung WHERE schluessel = ?", (schluessel,)).fetchone()


def _neu(con, *, grund: str, richtung: str, anbieter: str | None, schluessel: str | None, kennung: str,
         referenz: str, haendler: str, beschreibung: str, gesamt: int, guthaben: int, datum: str, frist: str,
         bezug_id: int | None, mails: list[dict], zeitpunkt: str) -> int:
    betrag = max(0, gesamt - guthaben)
    zustand = "offen" if betrag > 0 else "guthaben"
    return con.execute(
        "INSERT INTO erwartung (grund, richtung, anbieter, schluessel, kennung, referenz, haendler, beschreibung,"
        " betrag, gesamt, guthaben, datum, frist, zustand, bezug_id, mails, erstellt_am)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (grund, richtung, anbieter, schluessel, kennung, referenz, haendler[:200], beschreibung[:2000], betrag,
         gesamt, guthaben, datum, frist, zustand, bezug_id, json.dumps(mails, ensure_ascii=False),
         zeitpunkt)).lastrowid


def _beschreibung(e: mailerkennung.Erkennung) -> str:
    return ", ".join(a.name for a in e.artikel)[:2000]


def erkennen(con, frist_tage: int, zeitpunkt: str) -> dict:
    """Alle gespiegelten Mails prüfen (idempotent). Liefert Anzahl neuer bzw. ergänzter Erwartungen."""
    neu = ergaenzt = storniert = 0
    for r in con.execute("SELECT adresse_cf, nachricht_id, empfangen, absender, betreff, text FROM mail_nachricht"
                         " ORDER BY empfangen, id").fetchall():
        e = mailerkennung.erkennen(r["absender"], r["betreff"], r["text"])
        if e is None or (e.gesamt <= 0 and e.art != "storno"):
            continue
        datum = r["empfangen"][:10]
        frist = _plus(datum, frist_tage)
        # D-230: Was eine Mailart bedeutet, sagt die Beschreibung des Anbieters (Rolle, Grund); der Schlüssel der
        # erwarteten Zahlung ist „<anbieter>:<mailart>:<kennung>“.
        modul = anbieter.nach_name(e.anbieter)
        art = modul.art(e.art)
        ausgabe = modul.ausgabe
        if art.rolle == "storno":
            z = _nach_schluessel(con, f"{modul.name}:{ausgabe.name}:{e.kennung}")
            if z is not None and z["zustand"] == "offen" and z["buchung_ids"] == "[]":
                con.execute("UPDATE erwartung SET zustand = 'storniert' WHERE id = ?", (z["id"],))
                _mail_hinzu(con, z, r)
                storniert += 1
            continue
        if art.rolle == "ausgabe":
            schluessel, grund, richtung, bezug = f"{modul.name}:{art.name}:{e.kennung}", art.grund, "ausgabe", None
        else:
            schluessel = f"{modul.name}:{art.name}:{e.kennung}:{e.gesamt}"
            grund, richtung = "rueckerstattung", "eingang"
            ur = _nach_schluessel(con, f"{modul.name}:{ausgabe.name}:{e.bezug}") if e.bezug else None
            bezug = ur["id"] if ur is not None else None
            if ur is not None and e.haendler == modul.titel:   # kein eigener Händler in der Mail: den der Zahlung
                e = mailerkennung.Erkennung(e.anbieter, e.art, e.kennung, ur["haendler"], e.gesamt, e.guthaben,
                                            e.bezug, e.artikel)
        z = _nach_schluessel(con, schluessel)
        if z is not None:
            if z["mails"].find(r["nachricht_id"]) < 0:
                ergaenzt += 1
            _mail_hinzu(con, z, r)
            continue
        _neu(con, grund=grund, richtung=richtung, anbieter=e.anbieter, schluessel=schluessel, kennung=e.kennung,
             referenz=e.bezug if art.rolle == "ausgabe" and e.bezug else "", haendler=e.haendler,
             beschreibung=_beschreibung(e), gesamt=e.gesamt, guthaben=e.guthaben, datum=datum, frist=frist,
             bezug_id=bezug, mails=[_mail_eintrag(r)], zeitpunkt=zeitpunkt)
        neu += 1
    return {"neu": neu, "ergaenzt": ergaenzt, "storniert": storniert}


# ================================================================ Kandidaten und Zuordnung


def _alle_zugeordneten(con, ausser: int | None = None) -> set[int]:
    return {r[0] for r in con.execute(
        "SELECT j.value FROM erwartung e, json_each(e.buchung_ids) j WHERE e.id IS NOT ?", (ausser,))}


def _kompakt(s: str | None) -> str:
    return re.sub(r"\s+", "", (s or "").casefold())


def _kennung_passt(z, b: dict) -> bool:
    text = _kompakt(b["verwendungszweck"]) + "|" + _kompakt(b["empfaenger"])
    return any(len(k) >= 6 and _kompakt(k) in text for k in (z["kennung"], z["referenz"]) if k)


def _anbieter_passt(z, b: dict) -> bool:
    text = ((b["verwendungszweck"] or "") + " " + (b["empfaenger"] or "")).casefold()
    modul = anbieter.nach_name(z["anbieter"])
    # D-230: Namen, unter denen der Anbieter in Bankbuchungen steht, nennt seine Beschreibung (bank.namen)
    namen = list(modul.bank.namen) if modul is not None else ([z["anbieter"]] if z["anbieter"] else [])
    if modul is not None and modul.bank.haendler_noetig:
        # D-232: Der Anbieter steht in jeder seiner Buchungen (PayPal); es zählt nur der Händler der Mail, in Teilen
        roh = (b["verwendungszweck"] or "") + " " + (b["empfaenger"] or "")
        eigene = any(n in text for n in namen) or modul.bank.haendler.search(roh) is not None \
            if modul.bank.haendler is not None else any(n in text for n in namen)
        if not eigene or not z["haendler"] or z["haendler"] == modul.titel:
            return False
        return anbieter.name_in_teilen(z["haendler"], roh, modul.haendler_der_buchung(roh))
    if z["haendler"] and len(z["haendler"]) >= 3:
        namen.append(z["haendler"].casefold())
    if any(n and n in text for n in namen):
        return True
    # D-238: bei von Hand geplanten Zahlungen genügt ein aussagekräftiges Wort des Namens (Banken kürzen Namen)
    return z["grund"] == "manuell" and anbieter.name_in_teilen(
        z["haendler"], (b["verwendungszweck"] or "") + " " + (b["empfaenger"] or ""))


def _fenster(z) -> tuple[int, int]:
    """Tage vor und nach dem Datum der Erwartung, in denen Buchungen als Kandidaten zählen (bank.tage_vor/nach)."""
    modul = anbieter.nach_name(z["anbieter"])
    bank = modul.bank if modul is not None else None
    return (FENSTER_VOR if bank is None or bank.tage_vor is None else bank.tage_vor,
            FENSTER_NACH if bank is None or bank.tage_nach is None else bank.tage_nach)


def _streng(z) -> bool:
    """Zählt für die automatische Zuordnung nur eine Buchung, in der der Name steht? Bei Anbietern mit
    ``haendler_noetig`` (D-232) und bei von Hand geplanten Zahlungen (D-238: der Name ist dort die einzige Angabe
    außer Betrag und Datum; andere Buchungen mit gleichem Betrag stören nicht)."""
    if z["grund"] == "manuell":
        return True
    modul = anbieter.nach_name(z["anbieter"])
    return modul is not None and modul.bank.haendler_noetig


def _kandidaten(con, z) -> list[dict]:
    offen = z["betrag"] - _zugeordnet(con, json.loads(z["buchung_ids"]))
    if z["zustand"] != "offen" or offen <= 0:
        return []
    vor, nach = _fenster(z)
    von, bis = _plus(z["datum"], -vor), _plus(z["datum"], nach)
    vergeben = _alle_zugeordneten(con)
    vz = "< 0" if z["richtung"] == "ausgabe" else "> 0"
    ids = [r[0] for r in con.execute(
        "SELECT DISTINCT b.id FROM buchung b JOIN split s ON s.buchung_id = b.id JOIN konto k ON k.id = s.konto_id"
        f" WHERE b.datum BETWEEN ? AND ? AND s.betrag {vz} AND k.art IN ({', '.join('?' * len(buch.BESTAND))})",
        (von, bis, *buch.BESTAND))]
    aus = []
    for b in _bankbuchungen(con, [i for i in ids if i not in vergeben]).values():
        if (b["betrag"] < 0) != (z["richtung"] == "ausgabe") or abs(b["betrag"]) > offen:
            continue
        kennung = _kennung_passt(z, b)
        gleich = abs(b["betrag"]) == offen
        if not (kennung or gleich):
            continue
        abstand = abs((dt.date.fromisoformat(b["datum"]) - dt.date.fromisoformat(z["datum"])).days)
        aus.append({**b, "kennung_passt": kennung, "betrag_gleich": gleich, "anbieter_passt": _anbieter_passt(z, b),
                    "abstand_tage": abstand})
    aus.sort(key=lambda k: (not k["kennung_passt"], not k["betrag_gleich"], not k["anbieter_passt"],
                            k["abstand_tage"], k["id"]))
    return aus


def kandidaten(con, eid: int) -> dict:
    return {"eintraege": _kandidaten(con, _zeile(con, eid))}


def _dokumente_anhaengen(con, z, buchung_id: int, zeitpunkt: str) -> list[int]:
    """Mails der Erwartung (ganze Mail und PDF-Anhänge) als Dokumente an die Buchung; vorhandene verknüpfen."""
    ids = [d for d in json.loads(z["dokument_ids"])
           if con.execute("SELECT 1 FROM dokument WHERE id = ?", (d,)).fetchone()]
    if ids:
        for d in ids:
            dokumente.verknuepfen(con, d, [buchung_id])
        return ids
    gesehen: set[str] = set()
    for m in json.loads(z["mails"]):
        if m["nachricht_id"] in gesehen:
            continue  # dieselbe Mail in zwei Postfächern nur einmal anhängen
        r = con.execute("SELECT * FROM mail_nachricht WHERE adresse_cf = ? AND nachricht_id = ?",
                        (m["postfach"], m["nachricht_id"])).fetchone()
        if r is None:
            continue  # Spiegel inzwischen entfernt (Postfach gelöscht): nichts anzuhängen
        gesehen.add(m["nachricht_id"])
        roh = dokumente.mail_roh_aus_spiegel(r)
        ids.append(dokumente.anlegen(con, roh, (r["betreff"] or "E-Mail")[:dokumente.MAX_NAME - 4], [buchung_id],
                                     "mail", zeitpunkt)["id"])
        try:
            anhaenge = dokumente.mail_lesen(roh).get("anhaenge", [])
        except Exception:  # noqa: BLE001 - eine unlesbare Mail hängt nur als Ganzes an
            anhaenge = []
        for a in anhaenge:
            try:
                name, typ, inhalt = dokumente.mail_anhang(roh, a["nr"])
            except ApiFehler:
                continue
            if dokumente.typ_erkennen(inhalt) == dokumente.PDF:
                ids.append(dokumente.anlegen(con, inhalt, name, [buchung_id], "mail", zeitpunkt)["id"])
    return ids


def _kategorie_der_ursprungsbuchung(con, z) -> int | None:
    """D-128: Kategorie (einziges Nicht-Bestandskonto) der ersten Buchung der ursprünglichen Bestellung/Zahlung."""
    if z["bezug_id"] is None:
        return None
    u = con.execute("SELECT buchung_ids FROM erwartung WHERE id = ?", (z["bezug_id"],)).fetchone()
    if u is None or u["buchung_ids"] == "[]":
        return None
    ph = ", ".join("?" * len(buch.BESTAND))
    r = con.execute("SELECT s.konto_id FROM split s JOIN konto k ON k.id = s.konto_id"
                    f" WHERE s.buchung_id = ? AND k.art NOT IN ({ph}) ORDER BY s.id",
                    (json.loads(u["buchung_ids"])[0], *buch.BESTAND)).fetchall()
    return r[0]["konto_id"] if len(r) == 1 else None


def _erstattung_kategorisieren(con, z, buchung_id: int) -> None:
    """D-128: Eine Erstattung mindert die Kategorie der ursprünglichen Buchung. Steht die Gutschrift (zwei
    Splits) noch auf „Unkategorisiert“ und ohne Vorschlag, wird die Gegenbuchung auf diese Kategorie gesetzt."""
    if z["grund"] != "rueckerstattung":
        return
    kat = _kategorie_der_ursprungsbuchung(con, z)
    if kat is None:
        return
    splits = con.execute("SELECT s.id, s.konto_id, k.art, k.name FROM split s JOIN konto k ON k.id = s.konto_id"
                         " WHERE s.buchung_id = ?", (buchung_id,)).fetchall()
    if len(splits) != 2 or con.execute("SELECT 1 FROM vorschlag WHERE buchung_id = ?", (buchung_id,)).fetchone():
        return
    gegen = [s for s in splits if s["art"] not in buch.BESTAND]
    unkat = con.execute("SELECT id FROM konto WHERE extern_id = 'kontor:unkategorisiert'").fetchone()
    if len(gegen) == 1 and unkat is not None and gegen[0]["konto_id"] == unkat["id"]:
        con.execute("UPDATE split SET konto_id = ? WHERE id = ?", (kat, gegen[0]["id"]))


def _zuordnen(con, z, buchung_ids: list[int], zeitpunkt: str) -> None:
    vorher = json.loads(z["buchung_ids"])
    neu = sorted(set(vorher) | set(buchung_ids))
    dok = json.loads(z["dokument_ids"])
    for b in buchung_ids:
        if b not in vorher:
            _erstattung_kategorisieren(con, z, b)
            dok = sorted(set(dok) | set(_dokumente_anhaengen(con, {**dict(z), "dokument_ids": json.dumps(dok)}, b,
                                                             zeitpunkt)))
    zustand = "erfuellt" if _zugeordnet(con, neu) >= z["betrag"] else "offen"
    con.execute("UPDATE erwartung SET buchung_ids = ?, dokument_ids = ?, zustand = ? WHERE id = ?",
                (json.dumps(neu), json.dumps(dok), zustand, z["id"]))
    if zustand == "erfuellt":
        folge_anlegen(con, z["id"], zeitpunkt)


def zuordnen(con, eid: int, d, zeitpunkt: str, heute: str) -> dict:
    z = _zeile(con, eid)
    if not isinstance(d, dict) or set(d) != {"buchung_ids"} or not isinstance(d["buchung_ids"], list) \
            or not d["buchung_ids"] or not all(type(b) is int for b in d["buchung_ids"]):
        raise Validierungsfehler([fehler_eintrag(["body", "buchung_ids"], "Liste von Buchungs-IDs erwartet.")])
    ids = sorted(set(d["buchung_ids"]))
    if z["zustand"] != "offen":
        raise _fehler("erwartung_nicht_offen", "Die erwartete Zahlung ist nicht mehr offen.", 409)
    bank = _bankbuchungen(con, ids)
    vorhanden = {r[0] for r in con.execute(
        f"SELECT id FROM buchung WHERE id IN ({buch._platzhalter(len(ids))})", ids)}
    if set(ids) - vorhanden:
        raise buch.nicht_gefunden("Die Buchung")
    if set(ids) - set(bank):
        raise _fehler("zuordnung_ungueltig", "Zuordnen lassen sich nur Buchungen mit genau einem Bestandskonto.")
    if any((bank[i]["betrag"] < 0) != (z["richtung"] == "ausgabe") for i in ids):
        raise _fehler("zuordnung_ungueltig", "Die Richtung der Buchung passt nicht (Ausgabe bzw. Eingang).")
    if set(ids) & _alle_zugeordneten(con, z["id"]):
        raise _fehler("buchung_bereits_zugeordnet", "Eine Buchung gehört schon zu einer anderen erwarteten Zahlung.",
                      409)
    neu = set(ids) - set(json.loads(z["buchung_ids"]))
    if _zugeordnet(con, sorted(set(json.loads(z["buchung_ids"])) | neu)) > z["betrag"]:
        raise _fehler("zuordnung_zu_hoch", "Die Buchungen ergeben mehr als den erwarteten Betrag.")
    _zuordnen(con, z, sorted(neu), zeitpunkt)
    return lesen(con, z["id"], heute)


def loesen(con, eid: int, buchung_id: int, heute: str) -> dict:
    z = _zeile(con, eid)
    ids = json.loads(z["buchung_ids"])
    if buchung_id not in ids:
        raise buch.nicht_gefunden("Die Zuordnung")
    ids.remove(buchung_id)
    dok = json.loads(z["dokument_ids"])
    for d in dok:
        con.execute("DELETE FROM dokument_buchung WHERE dokument_id = ? AND buchung_id = ?", (d, buchung_id))
    zustand = "offen" if z["zustand"] == "erfuellt" else z["zustand"]
    con.execute("UPDATE erwartung SET buchung_ids = ?, zustand = ? WHERE id = ?", (json.dumps(ids), zustand, z["id"]))
    if zustand == "offen":
        folge_entfernen(con, z["id"])
    # Dokumente ohne Buchung entfallen schon hier, damit die Antwort den Stand nach der Änderung zeigt (D-136)
    dokumente.verwaiste_entfernen(con)
    verwaiste_entfernen(con)
    return lesen(con, z["id"], heute)


def automatisch_zuordnen(con, zeitpunkt: str) -> int:
    """Eindeutige Fälle zuordnen: Kennung im Verwendungszweck, oder einziger Kandidat mit vollem Betrag und
    passendem Anbieter-/Händlernamen, der auch für keine andere offene Erwartung infrage kommt."""
    offene = con.execute("SELECT * FROM erwartung WHERE zustand = 'offen' ORDER BY datum, id").fetchall()
    kand = {z["id"]: _kandidaten(con, z) for z in offene}
    zaehler: dict[int, int] = {}
    streng = {z["id"]: _streng(z) for z in offene}
    for eid, liste_ in kand.items():
        for k in liste_:
            # D-232: bei Anbietern mit haendler_noetig konkurrieren nur Buchungen, in denen der Händler steht
            if k["betrag_gleich"] and (k["anbieter_passt"] or not streng[eid]):
                zaehler[k["id"]] = zaehler.get(k["id"], 0) + 1
    n = 0
    vergeben: set[int] = set()
    for z in offene:
        k = [x for x in kand[z["id"]] if x["id"] not in vergeben]
        treffer = [x for x in k if x["kennung_passt"]]
        if not treffer:
            gleich = [x for x in k if x["betrag_gleich"] and x["anbieter_passt"]]
            if len(gleich) == 1 and zaehler.get(gleich[0]["id"]) == 1 \
                    and (streng[z["id"]] or len([x for x in k if x["betrag_gleich"]]) == 1):
                treffer = gleich
        if not treffer:
            continue
        frisch = con.execute("SELECT * FROM erwartung WHERE id = ?", (z["id"],)).fetchone()
        rest = frisch["betrag"] - _zugeordnet(con, json.loads(frisch["buchung_ids"]))
        wahl = []
        for x in treffer:
            if abs(x["betrag"]) <= rest:
                wahl.append(x["id"])
                rest -= abs(x["betrag"])
        if wahl:
            _zuordnen(con, frisch, wahl, zeitpunkt)
            vergeben.update(wahl)
            n += 1
    return n


# ================================================================ Anwender: anlegen, ändern, schließen


def _datum(d: dict, feld: str, vorgabe: str) -> str:
    wert = d.get(feld)
    if wert is None:
        return vorgabe
    if not datum_gueltig(wert):
        raise Validierungsfehler([fehler_eintrag(["body", feld], "Datum im Format YYYY-MM-DD erwartet.")])
    return wert


def _betrag(d: dict) -> int:
    b = d["betrag"]
    if type(b) is not int or not 1 <= b <= MAX_BETRAG:
        raise Validierungsfehler([fehler_eintrag(["body", "betrag"], "Positiver Betrag in Cent erwartet.")])
    return b


def anlegen(con, d, heute: str, frist_tage: int, zeitpunkt: str) -> dict:
    d = _pruefen(d, NEU)
    datum = _datum(d, "datum", heute)
    frist = _datum(d, "frist", _plus(datum, frist_tage))
    eid = _neu(con, grund="manuell", richtung=d["richtung"], anbieter=None, schluessel=None,
               kennung=d.get("kennung") or "", referenz="", haendler=d["haendler"].strip(),
               beschreibung=d.get("beschreibung") or "", gesamt=_betrag(d), guthaben=0, datum=datum, frist=frist,
               bezug_id=None, mails=[], zeitpunkt=zeitpunkt)
    if d.get("wiederholung") not in (None, "keine"):
        bis = _datum(d, "wiederholung_bis", "") or None
        con.execute("INSERT INTO erwartung_wiederholung (erwartung_id, rhythmus, tag, bis, vorgaenger_id)"
                    " VALUES (?, ?, ?, ?, NULL)", (eid, d["wiederholung"], int(datum[8:10]), bis))
    elif d.get("wiederholung_bis") is not None:
        raise _fehler("wiederholung_fehlt", "Ein Ende der Wiederholung braucht eine Wiederholung.")
    return lesen(con, eid, heute)


def aendern(con, eid: int, d, heute: str) -> dict:
    z = _zeile(con, eid)
    d = _pruefen(d, AENDERUNG)
    setzen: dict = {}
    if "haendler" in d:
        setzen["haendler"] = d["haendler"].strip()
    if "beschreibung" in d:
        setzen["beschreibung"] = d["beschreibung"]
    if "kennung" in d:
        setzen["kennung"] = d["kennung"]
    if "datum" in d:
        setzen["datum"] = _datum(d, "datum", z["datum"])
    if "frist" in d:
        setzen["frist"] = _datum(d, "frist", z["frist"])
    if "betrag" in d:
        b = _betrag(d)
        if _zugeordnet(con, json.loads(z["buchung_ids"])) > b:
            raise _fehler("zuordnung_zu_hoch", "Die zugeordneten Buchungen ergeben mehr als diesen Betrag.")
        setzen["betrag"] = b
        setzen["gesamt"] = b + z["guthaben"]
    if setzen:
        con.execute(f"UPDATE erwartung SET {', '.join(f'{k} = ?' for k in setzen)} WHERE id = ?",
                    (*setzen.values(), z["id"]))
        z = _zeile(con, eid)
        if z["zustand"] in ("offen", "erfuellt") and z["buchung_ids"] != "[]":
            zustand = "erfuellt" if _zugeordnet(con, json.loads(z["buchung_ids"])) >= z["betrag"] else "offen"
            con.execute("UPDATE erwartung SET zustand = ? WHERE id = ?", (zustand, z["id"]))
    if "wiederholung" in d or "wiederholung_bis" in d:
        _wiederholung_aendern(con, _zeile(con, eid), d)
    return lesen(con, eid, heute)


def _wiederholung_aendern(con, z, d: dict) -> None:
    """D-238: Wiederholung einer geplanten Zahlung setzen, ändern oder („keine“) zurücknehmen."""
    if z["grund"] != "manuell":
        raise _fehler("wiederholung_nur_geplant", "Nur von Hand angelegte Zahlungen können sich wiederholen.")
    alt = con.execute("SELECT * FROM erwartung_wiederholung WHERE erwartung_id = ?", (z["id"],)).fetchone()
    rhythmus = d.get("wiederholung", alt["rhythmus"] if alt is not None else None)
    if rhythmus in (None, "keine"):
        if d.get("wiederholung_bis") is not None:
            raise _fehler("wiederholung_fehlt", "Ein Ende der Wiederholung braucht eine Wiederholung.")
        con.execute("DELETE FROM erwartung_wiederholung WHERE erwartung_id = ?", (z["id"],))
        return
    bis = (_datum(d, "wiederholung_bis", "") or None) if "wiederholung_bis" in d else (alt["bis"] if alt is not None else None)
    tag = int(z["datum"][8:10]) if alt is None or "datum" in d else alt["tag"]
    con.execute("INSERT INTO erwartung_wiederholung (erwartung_id, rhythmus, tag, bis, vorgaenger_id) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(erwartung_id) DO UPDATE SET rhythmus = excluded.rhythmus, tag = excluded.tag, bis = excluded.bis",
                (z["id"], rhythmus, tag, bis, alt["vorgaenger_id"] if alt is not None else None))


def naechstes_datum(datum: str, rhythmus: str, tag: int) -> str:
    """Nächste Fälligkeit: ``MONATE[rhythmus]`` Monate weiter, am Tag ``tag`` (im kürzeren Monat am Monatsletzten)."""
    d = dt.date.fromisoformat(datum)
    m = d.year * 12 + (d.month - 1) + MONATE[rhythmus]
    jahr, monat = divmod(m, 12)
    letzter = (dt.date(jahr + (monat == 11), (monat + 1) % 12 + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(jahr, monat + 1, min(tag, letzter)).isoformat()


def folge_anlegen(con, eid: int, zeitpunkt: str) -> int | None:
    """D-238: Ist eine geplante Zahlung mit Wiederholung erfüllt oder erledigt, entsteht in derselben Änderung die
    nächste (gleiche Angaben, nächste Fälligkeit, gleiche Frist in Tagen) – außer das Ende ist erreicht oder es
    gibt sie schon."""
    w = con.execute("SELECT * FROM erwartung_wiederholung WHERE erwartung_id = ?", (eid,)).fetchone()
    if w is None or con.execute("SELECT 1 FROM erwartung_wiederholung WHERE vorgaenger_id = ?", (eid,)).fetchone():
        return None
    z = con.execute("SELECT * FROM erwartung WHERE id = ?", (eid,)).fetchone()
    datum = naechstes_datum(z["datum"], w["rhythmus"], w["tag"])
    if w["bis"] and datum > w["bis"]:
        return None
    tage = (dt.date.fromisoformat(z["frist"]) - dt.date.fromisoformat(z["datum"])).days
    neu = _neu(con, grund="manuell", richtung=z["richtung"], anbieter=None, schluessel=None, kennung=z["kennung"],
               referenz="", haendler=z["haendler"], beschreibung=z["beschreibung"], gesamt=z["gesamt"], guthaben=0,
               datum=datum, frist=_plus(datum, max(0, tage)), bezug_id=None, mails=[], zeitpunkt=zeitpunkt)
    con.execute("INSERT INTO erwartung_wiederholung (erwartung_id, rhythmus, tag, bis, vorgaenger_id) VALUES (?, ?, ?, ?, ?)",
                (neu, w["rhythmus"], w["tag"], w["bis"], eid))
    return neu


def folge_entfernen(con, eid: int) -> None:
    """Wird eine geplante Zahlung wieder offen, entfällt ihre noch unberührte Folge (sammel3.md 14.2: seit dem
    Anlegen unverändert – D-243: offen, ohne Buchung, Mails, Dokumente und mit den Angaben, die das Anlegen aus
    der Vorgängerin übernommen hätte)."""
    v = con.execute("SELECT * FROM erwartung WHERE id = ?", (eid,)).fetchone()
    for f in con.execute("SELECT e.*, w.rhythmus, w.tag, w.bis AS w_bis FROM erwartung e JOIN erwartung_wiederholung w"
                         " ON w.erwartung_id = e.id WHERE w.vorgaenger_id = ?", (eid,)).fetchall():
        vw = con.execute("SELECT * FROM erwartung_wiederholung WHERE erwartung_id = ?", (eid,)).fetchone()
        datum = naechstes_datum(v["datum"], f["rhythmus"], f["tag"])
        tage = (dt.date.fromisoformat(v["frist"]) - dt.date.fromisoformat(v["datum"])).days
        unberuehrt = (
            f["zustand"] == "offen" and f["buchung_ids"] == "[]" and f["mails"] == "[]" and f["dokument_ids"] == "[]"
            and (f["richtung"], f["kennung"], f["haendler"], f["beschreibung"], f["gesamt"], f["guthaben"])
            == (v["richtung"], v["kennung"], v["haendler"], v["beschreibung"], v["gesamt"], 0)
            and f["datum"] == datum and f["frist"] == _plus(datum, max(0, tage))
            and vw is not None and (f["rhythmus"], f["w_bis"]) == (vw["rhythmus"], vw["bis"]))
        if unberuehrt:
            con.execute("DELETE FROM erwartung WHERE id = ?", (f["id"],))


def zustand_setzen(con, eid: int, d, heute: str, zeitpunkt: str) -> dict:
    z = _zeile(con, eid)
    if not isinstance(d, dict) or set(d) != {"zustand"} or d["zustand"] not in SCHLIESSEN + ("offen",):
        raise Validierungsfehler([fehler_eintrag(["body", "zustand"],
                                                 "„offen“, „guthaben“, „storniert“ oder „erledigt“ erwartet.")])
    ziel = d["zustand"]
    if ziel == "offen":
        if z["zustand"] not in SCHLIESSEN:
            raise _fehler("zustand_unzulaessig", "Nur geschlossene erwartete Zahlungen lassen sich wieder öffnen.",
                          409)
    elif z["zustand"] != "offen":
        raise _fehler("zustand_unzulaessig", "Nur offene erwartete Zahlungen lassen sich schließen.", 409)
    con.execute("UPDATE erwartung SET zustand = ? WHERE id = ?", (ziel, z["id"]))
    # D-238: „erledigt“ führt die Wiederholung fort, „storniert“ beendet sie; wieder offen nimmt die Folge zurück
    if ziel == "erledigt":
        folge_anlegen(con, z["id"], zeitpunkt)
    elif ziel == "offen":
        folge_entfernen(con, z["id"])
    return lesen(con, eid, heute)


def loeschen(con, eid: int) -> None:
    z = _zeile(con, eid)
    if z["grund"] != "manuell":
        raise _fehler("erwartung_aus_mail", "Aus Mails erkannte Zahlungen lassen sich nur schließen (sonst würden sie "
                      "beim nächsten Abruf wieder erkannt).", 409)
    con.execute("DELETE FROM erwartung WHERE id = ?", (z["id"],))


# ================================================================ Pflege


def verwaiste_entfernen(con) -> None:
    """Am Ende jeder protokollierten Operation: Zuordnungen gelöschter Buchungen und gelöschte Dokumente
    entfallen; eine erfüllte Erwartung, der danach Betrag fehlt, ist wieder offen."""
    for r in con.execute("SELECT id, buchung_ids, dokument_ids, betrag, zustand FROM erwartung"
                         " WHERE buchung_ids <> '[]' OR dokument_ids <> '[]'").fetchall():
        b_alt, d_alt = json.loads(r["buchung_ids"]), json.loads(r["dokument_ids"])
        b_neu = [b for b in b_alt if con.execute("SELECT 1 FROM buchung WHERE id = ?", (b,)).fetchone()]
        d_neu = [d for d in d_alt if con.execute("SELECT 1 FROM dokument WHERE id = ?", (d,)).fetchone()]
        if b_neu == b_alt and d_neu == d_alt:
            continue
        zustand = r["zustand"]
        if zustand == "erfuellt" and _zugeordnet(con, b_neu) < r["betrag"]:
            zustand = "offen"
            folge_entfernen(con, r["id"])
        con.execute("UPDATE erwartung SET buchung_ids = ?, dokument_ids = ?, zustand = ? WHERE id = ?",
                    (json.dumps(b_neu), json.dumps(d_neu), zustand, r["id"]))


def ueberfaellige_melden(con, heute: str, jetzt: str) -> int:
    """Je überfälliger Erwartung höchstens eine Benachrichtigung (nicht Teil des Buchbestands)."""
    n = 0
    for r in con.execute("SELECT * FROM erwartung WHERE zustand = 'offen' AND frist < ?", (heute,)).fetchall():
        betrag = buch_betrag_text(r["betrag"])
        if r["richtung"] == "eingang":
            titel, text = "Erstattung überfällig", (f"Die erwartete Gutschrift von {r['haendler']} über {betrag} ist "
                                                    f"seit {r['frist']} nicht eingegangen.")
        else:
            titel, text = "Zahlung nicht abgebucht", (f"Die erwartete Zahlung an {r['haendler']} über {betrag} ist "
                                                      f"seit {r['frist']} nicht auf dem Konto zu sehen.")
        if buch.benachrichtigung_anlegen(con, "erwartung_ueberfaellig", f"erwartung_ueberfaellig:{r['id']}", titel,
                                         text, f"/erwartet?id={r['id']}", jetzt, "einmal"):
            n += 1
    return n


def buch_betrag_text(cent: int) -> str:
    e, c = divmod(abs(cent), 100)
    return f"{'-' if cent < 0 else ''}{e:,}".replace(",", ".") + f",{c:02d} €"


def pruefe_inhalt(zeilen: list[tuple]) -> bool:
    """Sicherung: Werte der Tabelle ``erwartung`` plausibel?"""
    for r in zeilen:
        f = dict(zip(_SPALTEN, r))
        try:
            ok = (f["grund"] in GRUENDE and f["richtung"] in RICHTUNGEN and f["zustand"] in ZUSTAENDE
                  and (f["anbieter"] is None or (isinstance(f["anbieter"], str)
                                                 and re.fullmatch(r"[a-z][a-z0-9_]{0,29}", f["anbieter"]))) and datum_gueltig(f["datum"])
                  and datum_gueltig(f["frist"]) and all(type(f[k]) is int and 0 <= f[k] <= MAX_BETRAG
                                                        for k in ("betrag", "gesamt", "guthaben"))
                  and all(isinstance(json.loads(f[k]), list) for k in ("buchung_ids", "mails", "dokument_ids")))
        except (ValueError, TypeError):
            ok = False
        if not ok:
            return False
    return True


def pruefe_wiederholung(zeilen: list[tuple], erwartungen: list[tuple]) -> bool:
    """Sicherung: Werte der Tabelle ``erwartung_wiederholung`` plausibel (D-238)?"""
    ids = {r[0] for r in erwartungen}
    for eid, rhythmus, tag, bis, vorgaenger in zeilen:
        if eid not in ids or rhythmus not in RHYTHMEN or type(tag) is not int or not 1 <= tag <= 31:
            return False
        if bis is not None and not datum_gueltig(bis):
            return False
        if vorgaenger is not None and type(vorgaenger) is not int:
            return False
    return True


def geplante(con, heute: str, bis: str) -> list[dict]:
    """Offene, von Hand geplante Zahlungen samt ihrer Wiederholungen bis ``bis`` – für die Vorschau des
    Kontostands (D-238). Schon fällige stehen am Folgetag von ``heute`` (sie werden jeden Tag erwartet)."""
    aus = []
    morgen = _plus(heute, 1)
    for z in con.execute("SELECT e.*, w.rhythmus, w.tag, w.bis AS w_bis FROM erwartung e LEFT JOIN erwartung_wiederholung w"
                         " ON w.erwartung_id = e.id WHERE e.grund = 'manuell' AND e.zustand = 'offen' ORDER BY e.datum, e.id"):
        offen = z["betrag"] - _zugeordnet(con, json.loads(z["buchung_ids"]))
        datum, betrag = z["datum"], offen
        while datum <= bis and betrag > 0:
            aus.append({"id": z["id"], "datum": max(datum, morgen), "betrag": betrag, "richtung": z["richtung"],
                        "haendler": z["haendler"], "rhythmus": z["rhythmus"]})
            if not z["rhythmus"]:
                break
            datum, betrag = naechstes_datum(datum, z["rhythmus"], z["tag"]), z["betrag"]
            if z["w_bis"] and datum > z["w_bis"]:
                break
    return aus
