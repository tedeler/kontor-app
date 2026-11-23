"""Hilfen für Meilenstein-9-Tests (Datensicherung und Wiederherstellung).

Nur über die Spezifikation (sicherung.md, protokoll.md 10, python-api.md 11, openapi.yaml).
Die Tests kennen das Schema von ``kontor.sqlite`` nicht; sie verändern die Datei nur mit
schemaunabhängigen SQL-Befehlen (Views, Tabellen, Trigger anlegen bzw. löschen).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import tempfile
import warnings
import zipfile
from pathlib import Path

from .api import Api, fehlercode
from .m3 import bestand as bestand_m3
from .m3 import zustand_m3
from .vertrag import ohne_zusatzfeld, vertrag

OBJEKTE = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]
NAMEN = {"manifest.json", "kontor.sqlite"}
DATEINAME = re.compile(r'attachment;\s*filename="?(kontor-sicherung-(echt|mock)-(\d{8})T(\d{6})Z\.zip)"?$')


# ------------------------------------------------------------------ Inhalt
def bestand(api: Api, *, vorlagen: bool = True) -> dict[tuple[str, int], dict]:
    """Buchbestand in Protokollform; ohne ``vorlagen`` wird angenommen, dass es keine Vorlagen gibt."""
    aus = bestand_m3(api)
    if vorlagen:
        for v in api.get("/api/vorlagen", erwartet=200).daten:
            aus[("vorlage", v["id"])] = v
    return aus


def inhalt(api: Api, *, vorlagen: bool = True) -> dict[str, list[dict]]:
    """sicherung.md 3.3: je Objektart die Protokollformen nach id aufsteigend."""
    b = bestand(api, vorlagen=vorlagen)
    return {o: [b[k] for k in sorted(k for k in b if k[0] == o)] for o in OBJEKTE}


def inhalt_sha256(i: dict[str, list[dict]]) -> str:
    text = json.dumps(ohne_zusatzfeld(i), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def anzahl(i: dict[str, list[dict]]) -> dict[str, int]:
    return {o: len(v) for o, v in i.items()}


def sync_konten(api: Api) -> list[dict]:
    return api.get("/api/sync/konten", erwartet=200).daten


def lesezustand(api: Api, *, vorlagen: bool = True) -> dict:
    """Alles, was nach einer Rundreise gleich sein muss (E-091): Lese-Endpunkte und Bankkonto-Zustand."""
    z = zustand_m3(api)
    z["bestand"] = bestand(api, vorlagen=vorlagen)
    z["sync_konten"] = sync_konten(api)
    return z


# ------------------------------------------------------------------ Datei
def sicherung(api: Api) -> bytes:
    """GET /api/sicherung mit Prüfung von Content-Type und Dateiname."""
    r = api.get("/api/sicherung", erwartet=200)
    art = (r.headers.get("content-type") or "").split(";")[0].strip()
    assert art == "application/zip", f"Content-Type {art!r} statt application/zip"
    cd = r.headers.get("content-disposition") or ""
    assert DATEINAME.match(cd.strip()), f"Content-Disposition {cd!r} entspricht nicht sicherung.md 3.1"
    return r.content


def dateiname(api: Api) -> str:
    r = api.get("/api/sicherung", erwartet=200)
    return DATEINAME.match(r.headers["content-disposition"].strip()).group(1)


def oeffne(daten: bytes) -> tuple[dict, bytes]:
    """(manifest, Bytes von kontor.sqlite); prüft Aufbau und Manifest-Schema."""
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        namen = z.namelist()
        assert sorted(namen) == sorted(NAMEN), f"ZIP-Einträge {namen} statt genau {sorted(NAMEN)}"
        for info in z.infolist():
            assert not info.is_dir() and not info.flag_bits & 0x1, f"{info.filename}: Verzeichnis oder verschlüsselt"
        roh = z.read("manifest.json")
        db = z.read("kontor.sqlite")
    manifest = json.loads(roh.decode("utf-8"))
    fehler = list(vertrag().schema_validator("SicherungManifest").iter_errors(manifest))
    assert not fehler, f"manifest.json verletzt SicherungManifest: {fehler[0].message}\n{manifest}"
    return manifest, db


def baue(eintraege: dict[str, bytes] | list[tuple[str, bytes]]) -> bytes:
    """ZIP aus (Name, Bytes); Liste erlaubt doppelte und ungewöhnliche Namen."""
    puffer = io.BytesIO()
    paare = eintraege.items() if isinstance(eintraege, dict) else eintraege
    with warnings.catch_warnings(), zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        warnings.simplefilter("ignore")  # doppelte Namen sind hier gewollt
        for name, inh in paare:
            z.writestr(name, inh)
    return puffer.getvalue()


def neu_verpackt(manifest: dict, db: bytes, *, db_sha_neu: bool = True) -> bytes:
    """Sicherung aus Manifest und Datenbank; ``db_sha_neu`` rechnet datenbank_sha256 nach."""
    m = dict(manifest)
    if db_sha_neu:
        m["datenbank_sha256"] = hashlib.sha256(db).hexdigest()
    return baue({"manifest.json": json.dumps(m, ensure_ascii=False).encode("utf-8"), "kontor.sqlite": db})


def db_veraendert(db: bytes, *sql: str) -> bytes:
    """Wendet schemaunabhängige SQL-Befehle auf eine Kopie der Datenbank an."""
    with tempfile.TemporaryDirectory() as d:
        pfad = Path(d) / "x.sqlite"
        pfad.write_bytes(db)
        con = sqlite3.connect(pfad)
        try:
            for s in sql:
                con.execute(s)
            con.commit()
        finally:
            con.close()
        return pfad.read_bytes()


def db_objekte(db: bytes) -> list[tuple[str, str]]:
    """(type, name) aus sqlite_master."""
    with tempfile.TemporaryDirectory() as d:
        pfad = Path(d) / "x.sqlite"
        pfad.write_bytes(db)
        con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            assert ok == "ok", f"integrity_check: {ok}"
            return [(t, n) for t, n in con.execute("SELECT type, name FROM sqlite_master")]
        finally:
            con.close()


def erste_tabelle(db: bytes) -> str:
    namen = sorted(n for t, n in db_objekte(db) if t == "table" and not n.startswith("sqlite_"))
    assert namen, "kontor.sqlite enthält keine Tabelle"
    return namen[0]


def enthaelt(daten: bytes, text: str) -> bool:
    """Kommt ``text`` in den Bytes vor (UTF-8, UTF-16 LE/BE)? ZIP-Einträge werden zusätzlich entpackt."""
    teile = [daten]
    try:
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            teile.extend(z.read(n) for n in z.namelist())
    except zipfile.BadZipFile:
        pass
    muster = [text.encode(k) for k in ("utf-8", "utf-16-le", "utf-16-be")]
    return any(m in t for t in teile for m in muster)


# ------------------------------------------------------------------ Einspielen
def einspielen(api: Api, daten: bytes, *, trocken: bool | None = None, bestaetigt: bool | None = True,
               erwartet: int | tuple = 200, dateiname: str = "sicherung.zip"):
    params = {}
    if trocken is not None:
        params["trocken"] = "true" if trocken else "false"
    if bestaetigt is not None:
        params["bestaetigt"] = "true" if bestaetigt else "false"
    return api.post("/api/sicherung/einspielen", params=params,
                    files={"datei": (dateiname, daten, "application/zip")}, erwartet=erwartet)


def ungueltig(api: Api, daten: bytes, grund: str, **kw) -> None:
    """422 sicherung_ungueltig mit details.grund; prüft auch den Probelauf."""
    for trocken in (False, True):
        r = einspielen(api, daten, trocken=trocken, erwartet=422, **kw)
        assert fehlercode(r) == "sicherung_ungueltig", r.text[:500]
        assert r.json()["fehler"]["details"] == {"grund": grund}, (
            f"details {r.json()['fehler']['details']} statt grund {grund!r} (trocken={trocken})")


def unterschied(vorher: dict, nachher: dict) -> dict[str, dict[str, int]]:
    """sicherung.md 5.2 aus zwei Beständen in Protokollform."""
    aus = {o: {"angelegt": 0, "geaendert": 0, "geloescht": 0} for o in OBJEKTE}
    for k in set(vorher) | set(nachher):
        a, b = vorher.get(k), nachher.get(k)
        if a == b:
            continue
        art = "angelegt" if a is None else "geloescht" if b is None else "geaendert"
        aus[k[0]][art] += 1
    return aus


def null_unterschied() -> dict[str, dict[str, int]]:
    return {o: {"angelegt": 0, "geaendert": 0, "geloescht": 0} for o in OBJEKTE}


def gesperrt_betroffen(vorher: dict, nachher: dict, buchungen: list[dict]) -> int:
    """sicherung.md 5.5: aktuelle abgestimmte/abgeglichene Buchungen, die sich ändern oder verschwinden."""
    n = 0
    for b in buchungen:
        if b["abgestimmt"] or b["status"] == "abgeglichen":
            k = ("buchung", b["id"])
            if vorher.get(k) != nachher.get(k):
                n += 1
    return n


def max_ids(api: Api) -> dict[str, int]:
    """Höchste aktuell sichtbare ID je Objektart (für Zählerprüfungen)."""
    b = bestand(api, vorlagen=False)
    aus: dict[str, int] = {}
    for (o, i) in b:
        aus[o] = max(aus.get(o, 0), i)
    return aus


def aenderungsanzahl(api: Api) -> int:
    return api.get("/api/aenderungen", params={"pro_seite": 1}, erwartet=200).daten["gesamt"]


# ------------------------------------------------------------------ Testbestand
def reicher_bestand(api: Api) -> dict:
    """Bestand mit allen M3-Objektarten (ohne Vorlagen): Import mit Verdachten, Sonderfälle, Empfänger mit
    Aliasen und Standardkategorie, Regeln, Tags, Abstimmung, gelöschte Objekte (Lücken in den IDs)."""
    from .erwartung import lade
    from .m3 import lade_stammdaten, stammdaten_anlegen
    from .normal import ekey
    from .pfade import KMY

    erw = lade("dubletten")
    vb = erw["vorbestand"]
    ref: dict[str, dict] = {}
    for k in vb["konten"]:
        ref[k["ref"]] = api.konto(k["name"], k["art"], **({"iban": k["iban"]} if k["iban"] else {}))
    for e in vb["empfaenger"]:
        ref[e["ref"]] = api.empfaenger(e["name"])
    giro = next(k["ref"] for k in vb["konten"] if k["art"] == "girokonto")
    for b in vb["buchungen"]:
        felder = {"verwendungszweck": f"Vorbestand {b['ref']}"}
        if b["empfaenger"]:
            felder["empfaenger_id"] = ref[b["empfaenger"]]["id"]
        api.buchung(b["datum"], [(ref[giro]["id"], b["betrag"]), (ref[b["kategorie"]]["id"], -b["betrag"])],
                    **felder)
    api.import_kmy(KMY / "dubletten.kmy", erwartet=200)
    api.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200)
    # Stammdaten (m3/stammdaten.json): Kategorien, Empfänger mit Aliasen und Standardkategorie, Regeln;
    # Empfänger, die der Import schon angelegt hat, werden übersprungen.
    sd = lade_stammdaten()
    vorhanden = {ekey(e["name"]) for e in api.get("/api/empfaenger", erwartet=200).daten}
    alias_frei = [e for e in sd["empfaenger"] if ekey(e["name"]) not in vorhanden
                  and not any(ekey(a) in vorhanden for a in e["aliase"])]
    stamm = stammdaten_anlegen(api, {**sd, "empfaenger": alias_frei})
    t1, t2, weg = api.tag("Urlaub 🏖️"), api.tag("Steuer"), api.tag("weg")
    bs = api.alle_buchungen()
    api.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [b["id"] for b in bs[::3]],
                                                    "hinzufuegen": [t1["id"], weg["id"]], "entfernen": []},
             erwartet=200)
    api.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [b["id"] for b in bs[1::4]],
                                                    "hinzufuegen": [t2["id"]], "entfernen": []}, erwartet=200)
    api.delete(f"/api/tags/{weg['id']}", erwartet=204)
    api.delete(f"/api/buchungen/{bs[-1]['id']}", erwartet=204)
    # Abstimmung auf dem Girokonto bis zum mittleren Buchungstag
    kid = ref[giro]["id"]
    tage = sorted(b["datum"] for b in api.alle_buchungen(konto_id=kid))
    stichtag = tage[len(tage) // 2]
    saldo = api.salden(stichtag)[kid]["saldo"]
    ab = api.post("/api/abstimmungen", json={"konto_id": kid, "stichtag": stichtag, "saldo": saldo},
                  erwartet=200).daten
    assert ab["abgestimmt"] is True, ab
    return {"giro": kid, "stamm": stamm, "tags": [t1, t2]}


def kleiner_bestand(api: Api, praefix: str = "A") -> dict:
    """Wenige Objekte, schnell anzulegen."""
    giro = api.konto(f"{praefix} Giro", "girokonto")
    kat = api.konto(f"{praefix} Lebensmittel", "aufwand")
    emp = api.empfaenger(f"{praefix} Markt")
    tag = api.tag(f"{praefix} Tag")
    b = api.buchung("2024-02-01", [(giro["id"], -1234), (kat["id"], 1234)], empfaenger_id=emp["id"],
                    verwendungszweck=f"{praefix} Einkauf", tag_ids=[tag["id"]])
    return {"giro": giro, "kat": kat, "emp": emp, "tag": tag, "buchung": b}
