"""WEGWERF-REFERENZ: Datensicherung (sicherung.md) – nur für die Selbstprüfung, kein Anwendungscode.

Die Referenz hält das Buch im Arbeitsspeicher; die Sicherung schreibt seine Tabellen als JSON-Zeilen in
eine frisch angelegte SQLite-Datei (dadurch ohne Reste). Mutanten: siehe ``tests/_selbstpruefung``.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import Response

from . import __version__, mutant
from .buch import Fehler, buch_fuer

OBJEKTE = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]
# M5 (sicherung.md 2.5): Objektarten ab M5 stehen nur bei Vorhandensein in anzahl/inhalt/unterschied
SPAETER = ["kredit", "postfach"]
TABELLE = {"konto": "konten", "empfaenger": "empfaenger", "tag": "tags", "buchung": "buchungen", "regel": "regeln",
           "verdacht": "verdachte", "abstimmung": "abstimmungen", "vorlage": "vorlagen", "kredit": "kredite",
           "postfach": "postfaecher"}
ZAEHLER = ["konto", "empfaenger", "tag", "buchung", "split", "regel", "verdacht", "abstimmung", "vorlage", "kredit",
           "postfach"]


def objektarten(*formen: dict) -> list[str]:
    vorhanden = {k[0] for f in formen for k in f}
    return OBJEKTE + [o for o in SPAETER if o in vorhanden or (o == "kredit" and mutant("kredit_sicherung_immer_schluessel"))
                      or (o == "postfach" and mutant("postfach_sicherung_immer_schluessel"))]
SCHEMA = {
    "objekte": ["art", "id", "daten"],
    "kennungen": ["kennung"],
    "bankkonten": ["iban", "daten"],
    "zaehler": ["art", "wert"],
}
SCHEMAVERSION = 6  # M25: eigene Betragsfilter der Empfänger (wiederkehrend.md 9.4)
FELDER = ["format", "formatversion", "erstellt", "modus", "app_version", "schemaversion", "anzahl", "inhalt_sha256",
          "datenbank_sha256"]


def _kodiere(o):
    if isinstance(o, set):
        return {"__menge__": sorted(o)}
    raise TypeError(type(o))


def _dekodiere(d: dict):
    if set(d) == {"__menge__"}:
        return set(d["__menge__"])
    return d


def _json(o) -> str:
    return json.dumps(o, default=_kodiere, ensure_ascii=False, sort_keys=True)


def inhalt(buch) -> dict[str, list]:
    from .m3 import protokollform
    form = protokollform(buch)
    return {o: [form[k] for k in sorted(k for k in form if k[0] == o)] for o in objektarten(form)}


def inhalt_sha(i: dict) -> str:
    text = json.dumps(i, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ Erstellen
def _datenbank(buch) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        pfad = Path(d) / "k.sqlite"
        con = sqlite3.connect(pfad)
        con.execute("CREATE TABLE objekte (art TEXT NOT NULL, id INTEGER NOT NULL, daten TEXT NOT NULL, "
                    "PRIMARY KEY (art, id))")
        con.execute("CREATE TABLE kennungen (kennung TEXT PRIMARY KEY)")
        con.execute("CREATE TABLE bankkonten (iban TEXT PRIMARY KEY, daten TEXT NOT NULL)")
        con.execute("CREATE TABLE zaehler (art TEXT PRIMARY KEY, wert INTEGER NOT NULL)")
        for o, tab in TABELLE.items():
            if o == "kredit" and mutant("kredit_sicherung_fehlt"):
                continue
            if o == "postfach" and mutant("postfach_sicherung_fehlt"):
                continue
            for oid, x in getattr(buch, tab).items():
                if o == "buchung" and x.get("vorschlag") and mutant("sicherung_vorschlag_ohne_sicherheit"):
                    x = {**x, "vorschlag": {k: v for k, v in x["vorschlag"].items() if k != "sicherheit"}}
                con.execute("INSERT INTO objekte VALUES (?, ?, ?)", (o, oid, _json(x)))
        if not mutant("sicherung_ohne_kennungen"):
            kennungen = sorted(buch.gemerkt)
            if mutant("sicherung_kennungen_nur_vorhandene"):
                an = {e for b in buch.buchungen.values() for e in b["extern_ids"]}
                kennungen = [k for k in kennungen if k in an]
            con.executemany("INSERT INTO kennungen VALUES (?)", [(k,) for k in kennungen])
        for iban, z in buch.sync_konten.items():
            if mutant("sicherung_ohne_entscheidung"):
                z = {k: v for k, v in z.items() if k != "_entscheidung"}
            con.execute("INSERT INTO bankkonten VALUES (?, ?)", (iban, _json(z)))
        for art in ZAEHLER:
            wert = 0 if art == "vorlage" and mutant("sicherung_zaehler_ohne_vorlage") else buch.zaehler.get(art, 0)
            con.execute("INSERT INTO zaehler VALUES (?, ?)", (art, wert))
        if mutant("m7_sicherung_mit_hash"):
            from .anmeldung import ZUSTAND
            con.execute("CREATE TABLE anmeldung (hash TEXT)")
            con.executemany("INSERT INTO anmeldung VALUES (?)", [(z["hash"],) for z in ZUSTAND.values()])
        if mutant("sicherung_mit_protokoll"):
            con.execute("CREATE TABLE protokoll (daten TEXT)")
            con.execute("INSERT INTO protokoll VALUES (?)", (_json(list(buch.aenderungen.values())),))
        con.commit()
        con.close()
        return pfad.read_bytes()


def erstelle(buch, modus: str, jetzt: dt.datetime) -> tuple[bytes, str]:
    db = _datenbank(buch)
    i = inhalt(buch)
    erstellt = jetzt.strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {"format": "kontor-sicherung", "formatversion": 1, "erstellt": erstellt, "modus": modus,
                "app_version": __version__, "schemaversion": SCHEMAVERSION, "anzahl": {o: len(v) for o, v in i.items()},
                "inhalt_sha256": inhalt_sha(i), "datenbank_sha256": hashlib.sha256(db).hexdigest()}
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        z.writestr("kontor.sqlite", db)
    name = f"kontor-sicherung-{modus}-{jetzt.strftime('%Y%m%dT%H%M%SZ')}.zip"
    return puffer.getvalue(), name


def erstelle_sicherung(config) -> bytes:
    buch = buch_fuer(config.aktive_datenbank)
    if config.mock_modus and config.mock_heute is not None:
        jetzt = dt.datetime.combine(config.mock_heute, dt.time(12), dt.timezone.utc)
    else:
        jetzt = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    return erstelle(buch, "mock" if config.mock_modus else "echt", jetzt)[0]


def sichere_in_verzeichnis(config, verzeichnis, *, behalten: int = 14) -> Path:
    """betrieb.md 8 (M7)."""
    import os
    import re

    if type(behalten) is not int or behalten < 1:
        raise ValueError("behalten muss eine ganze Zahl ≥ 1 sein")
    ziel = Path(verzeichnis)
    if not ziel.exists():
        ziel.mkdir(parents=True, mode=0o700)
        os.chmod(ziel, 0o700)
    daten = erstelle_sicherung(config)
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        erstellt = json.loads(z.read("manifest.json"))["erstellt"]
    modus = "mock" if config.mock_modus else "echt"
    name = f"kontor-sicherung-{modus}-{erstellt.replace('-', '').replace(':', '')}"
    pfad = ziel / (name if name.endswith("Z") else name + "Z")
    pfad = pfad.with_name(pfad.name + ".zip")
    tmp = ziel / (".tmp-" + pfad.name)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(daten)
    os.chmod(tmp, 0o600)
    os.replace(tmp, pfad)
    muster = re.compile(r"^kontor-sicherung-(echt|mock)-([0-9]{8}T[0-9]{6})Z\.zip$")
    eigene = sorted((m[2], q) for q in ziel.iterdir() if (m := muster.match(q.name))
                    and (m[1] == modus or mutant("m7_aufbewahrung_alle_modi")))
    if mutant("m7_aufbewahrung_aelteste"):
        eigene.reverse()
    for _, q in eigene[:-behalten]:
        q.unlink()
    return pfad


def main(argv: list[str]) -> int:
    import argparse
    import sys

    from .config import KontorConfig
    from .fehler import KonfigurationsFehler

    a = argparse.ArgumentParser(prog="python -m kontor.sicherung")
    a.add_argument("--verzeichnis", required=True)
    a.add_argument("--behalten", type=int, default=14)
    args = a.parse_args(argv)
    try:
        config = KontorConfig.from_env()
    except KonfigurationsFehler as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        return 2
    try:
        print(sichere_in_verzeichnis(config, args.verzeichnis, behalten=args.behalten))
    except (OSError, ValueError) as e:
        print(f"Sicherung fehlgeschlagen: {e}", file=sys.stderr)
        return 1
    return 0


# ------------------------------------------------------------------ Lesen und prüfen
def _ungueltig(grund: str) -> Fehler:
    return Fehler(422, "sicherung_ungueltig", "Die Datei ist keine gültige Kontor-Sicherung", {"grund": grund})


def _manifest_ok(m) -> bool:
    if not isinstance(m, dict) or sorted(m) != sorted(FELDER):
        return False
    hexa = set("0123456789abcdef")
    try:
        dt.datetime.strptime(m["erstellt"], "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return False
    return (isinstance(m["format"], str) and type(m["formatversion"]) is int and m["modus"] in ("echt", "mock")
            and isinstance(m["app_version"], str) and m["app_version"] and type(m["schemaversion"]) is int
            and m["schemaversion"] >= 1 and isinstance(m["anzahl"], dict)
            and all(type(v) is int and v >= 0 for v in m["anzahl"].values())
            and set(OBJEKTE) <= set(m["anzahl"]) <= set(OBJEKTE) | set(SPAETER)
            and all(isinstance(m[f], str) and len(m[f]) == 64 and set(m[f]) <= hexa
                    for f in ("inhalt_sha256", "datenbank_sha256")))


def lies(daten: bytes):
    """Prüft nach sicherung.md 5.1 Schritt 2; liefert (manifest, Tabellen)."""
    if not daten:
        raise _ungueltig("datei_leer")
    try:
        z = zipfile.ZipFile(io.BytesIO(daten))
        infos = z.infolist()
    except (zipfile.BadZipFile, ValueError, OSError):
        raise _ungueltig("kein_zip") from None
    namen = [i.filename for i in infos]
    if sorted(namen) != ["kontor.sqlite", "manifest.json"] or any(i.flag_bits & 0x1 or i.is_dir() for i in infos):
        raise _ungueltig("zip_inhalt")
    try:
        roh_m, db = z.read("manifest.json"), z.read("kontor.sqlite")
    except Exception:  # noqa: BLE001
        raise _ungueltig("zip_inhalt") from None
    try:
        m = json.loads(roh_m.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _ungueltig("manifest_ungueltig") from None
    if not _manifest_ok(m):
        raise _ungueltig("manifest_ungueltig")
    if m["format"] != "kontor-sicherung":
        raise _ungueltig("format_unbekannt")
    if m["formatversion"] > 1 or m["schemaversion"] > SCHEMAVERSION:
        raise _ungueltig("version_nicht_unterstuetzt")
    if hashlib.sha256(db).hexdigest() != m["datenbank_sha256"] and not mutant("sicherung_db_pruefsumme_ungeprueft"):
        raise _ungueltig("datenbank_pruefsumme")
    with tempfile.TemporaryDirectory() as d:
        pfad = Path(d) / "s.sqlite"
        pfad.write_bytes(db)
        try:
            con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("integrity")
            master = con.execute("SELECT type, name, tbl_name FROM sqlite_master").fetchall()
        except sqlite3.DatabaseError:
            raise _ungueltig("datenbank_ungueltig") from None
        try:
            if not mutant("sicherung_fremde_tabellen_erlaubt"):
                tabellen = {n for t, n, _ in master if t == "table"}
                if any(t not in ("table", "index") for t, _, _ in master) or tabellen != set(SCHEMA):
                    raise _ungueltig("datenbank_fremd")
                for tab, spalten in SCHEMA.items():
                    ist = [r[1] for r in con.execute(f'PRAGMA table_info("{tab}")')]
                    if ist != spalten:
                        raise _ungueltig("datenbank_fremd")
            tabellen = {
                "objekte": con.execute("SELECT art, id, daten FROM objekte").fetchall(),
                "kennungen": [r[0] for r in con.execute("SELECT kennung FROM kennungen")],
                "bankkonten": con.execute("SELECT iban, daten FROM bankkonten").fetchall(),
                "zaehler": dict(con.execute("SELECT art, wert FROM zaehler").fetchall()),
            }
        except sqlite3.DatabaseError:
            raise _ungueltig("datenbank_fremd") from None
        finally:
            con.close()
    return m, tabellen


def _neues_buch(buch, tabellen):
    """Kopie des Buchs mit dem Bestand der Sicherung (Protokoll, Läufe usw. bleiben)."""
    from .m3 import bezuege_ok
    neu = buch.kopie()
    try:
        for tab in TABELLE.values():
            setattr(neu, tab, {})
        for art, oid, daten in tabellen["objekte"]:
            if art not in TABELLE:
                raise ValueError(art)
            getattr(neu, TABELLE[art])[oid] = json.loads(daten, object_hook=_dekodiere)
        for b in neu.buchungen.values():
            if sum(s["betrag"] for s in b["splits"]) != 0 or len(b["splits"]) < 2:
                raise ValueError("Splits")
    except (ValueError, KeyError, TypeError):
        raise _ungueltig("inhalt_ungueltig") from None
    if not bezuege_ok(neu):
        raise _ungueltig("inhalt_ungueltig")
    if not mutant("sicherung_ohne_kennungen"):
        neu.gemerkt = set(tabellen["kennungen"])
    if not mutant("sicherung_sync_konten_bleiben"):
        neu.sync_konten = {iban: json.loads(d, object_hook=_dekodiere) for iban, d in tabellen["bankkonten"]}
        for z in neu.sync_konten.values():  # JSON kennt keine Tupel (gespeicherte Entscheidung, 16.3)
            if isinstance(z.get("_entscheidung"), list):
                z["_entscheidung"] = tuple(z["_entscheidung"])
    if not mutant("sicherung_zaehler_nicht_uebernommen"):
        for art in ZAEHLER:
            neu.zaehler[art] = max(buch.zaehler.get(art, 0), int(tabellen["zaehler"].get(art, 0)))
    return neu


def _unterschied(vorher: dict, nachher: dict) -> dict:
    aus = {o: {"angelegt": 0, "geaendert": 0, "geloescht": 0} for o in objektarten(vorher, nachher)}
    for k in set(vorher) | set(nachher):
        if k[0] == "kennung" or vorher.get(k) == nachher.get(k):
            continue
        art = "angelegt" if k not in vorher else "geloescht" if k not in nachher else "geaendert"
        aus[k[0]][art] += 1
    return aus


# ------------------------------------------------------------------ REST
def sicherung_einbinden(app: FastAPI, config, buch) -> None:
    from . import m3
    dienst = app.state.dienst
    modus = "mock" if config.mock_modus else "echt"

    @app.get("/api/sicherung")
    def sicherung_erstellen():
        daten, name = erstelle(buch, modus, dienst.jetzt())
        return Response(daten, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/sicherung/einspielen")
    async def einspielen(datei: UploadFile = File(...), trocken: bool = Query(False),
                         bestaetigt: bool = Query(False)):
        m, tabellen = lies(await datei.read())
        neu = _neues_buch(buch, tabellen)
        i = inhalt(neu)
        if (not mutant("sicherung_pruefsumme_ungeprueft")
                and ({o: len(v) for o, v in i.items()} != m["anzahl"]
                     or inhalt_sha(i) != m["inhalt_sha256"])):
            raise _ungueltig("inhalt_pruefsumme")
        if m["modus"] != modus and not mutant("sicherung_modus_ungeprueft"):
            raise Fehler(409, "sicherung_modus", "Sicherung aus dem anderen Modus (Mock/Echt)")
        vorher = m3.protokollform(buch)
        nachher = m3.protokollform(neu)
        ohne = {k: v for k, v in vorher.items() if k[0] != "kennung"}
        ohne_n = {k: v for k, v in nachher.items() if k[0] != "kennung"}
        identisch = ohne == ohne_n and not mutant("sicherung_identisch_neue_version")
        betroffen = sum(1 for b in buch.buchungen.values()
                        if (b["status"] == "abgeglichen" or any(s.get("abstimmung_id") for s in b["splits"]))
                        and vorher.get(("buchung", b["id"])) != nachher.get(("buchung", b["id"])))
        ergebnis = {"trocken": trocken, "geaendert": not identisch, "aenderung_id": None, "manifest": m,
                    "unterschied": _unterschied(vorher, nachher), "abgestimmte_buchungen_betroffen": betroffen}
        if trocken and not mutant("sicherung_probelauf_schreibt"):
            return ergebnis
        if not bestaetigt and not mutant("sicherung_ohne_bestaetigung"):
            raise Fehler(409, "bestaetigung_erforderlich", "Einspielen muss bestätigt werden")
        laeufe = {lf["status"] for lf in buch.laeufe.values()}
        if "laeuft" in laeufe:
            raise Fehler(409, "sync_laeuft", "Synchronisation läuft")
        if "wartet_auf_tan" in laeufe and not mutant("sicherung_tan_ignoriert"):
            raise Fehler(409, "tan_ausstehend", "Synchronisation wartet auf TAN")
        if identisch:
            return {**ergebnis, "trocken": False}
        sync_vorher = copy.deepcopy(buch.sync_konten)
        buch.uebernehme(neu)
        jetzt = dienst.jetzt().strftime("%Y-%m-%dT%H:%M:%SZ")
        a = m3.protokolliere(buch, vorher, "sicherung", "sicherung_einspielen", None, jetzt, "Sicherung eingespielt")
        if a is None:
            a = m3._neu(buch, "sicherung", "sicherung_einspielen", None, jetzt, "Sicherung eingespielt", [], [], [],
                        None)
        if not mutant("sicherung_undo_ohne_sync"):
            a["_sync"] = (sync_vorher, copy.deepcopy(buch.sync_konten))
        return {**ergebnis, "trocken": False, "aenderung_id": a["id"]}


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(main(_sys.argv[1:]))
