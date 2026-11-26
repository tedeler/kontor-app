"""Sicherungspunkte: stündliche inkrementelle Sicherung, Ausdünnen, Herstellen, Zurück und Vorwärts (D-302).

Spezifikation: ``spec/api/sicherungspunkte.md``. Ein Punkt hält den gesicherten Zustand (Tabellen der
Sicherungsdatei, ``sicherung.SPALTEN``) als Zeilendifferenz zu seiner Basis oder, als Anker, vollständig. Gespeichert
wird je Punkt eine mit LZMA gepackte JSON-Datei; das Verzeichnis ``punkte.json`` hält die Angaben aller Punkte, den
Bezugspunkt und den Zeitpunkt der letzten Prüfung. ``zustand.json.gz`` hält die Zeilen-Hashes des Bezugspunkts, damit
der stündliche Lauf ohne Herstellen vergleichen kann.

Zustand im Arbeitsspeicher: ``{tabelle: {schlüssel: zeile}}``; der Schlüssel ist die JSON-Form der
Schlüsselspalten, die Zeile ein Tupel in der Spaltenfolge von ``SPALTEN``. Beleginhalte (``dokument_inhalt``) sind
inhaltsadressiert: ihr Hash ist der Schlüssel, der Inhalt wird nur für neue Zeilen gelesen.

Sperren: eine Dateisperre auf ``.sperre`` je Ablage (auch zwischen Dienst und Kommandozeile); sie wird immer vor
einer Schreibtransaktion der Datenbank genommen, nie danach.
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import lzma
import os
import pathlib
import secrets
import shutil
import sqlite3
import tempfile
import zlib
from collections.abc import Callable, Iterator
from typing import Any

from . import db, dokumente, protokoll, sicherung
from .config import KontorConfig
from .validierung import ApiFehler

UTC = dt.timezone.utc
FORMAT = "kontor-punkt"
FORMATVERSION = 1
BEGLEIT = ("id_zaehler", "sync_konto_zustand")   # nicht im Prüfwert, vollständig in jedem Punkt (2.3)
MARKEN = ("stuendlich", "von_hand", "vor_wiederherstellung", "aus_datei", "vor_update")
GESCHUETZT = ("von_hand", "vor_wiederherstellung", "aus_datei", "vor_update")
SCHUTZ_TAGE = 30
Zustand = dict[str, dict[str, tuple]]
Hashes = dict[str, dict[str, str]]


class NichtHerstellbar(Exception):
    """Ein Punkt (oder ein Glied seiner Kette) fehlt oder passt nicht zu seiner Prüfsumme bzw. seinem Prüfwert."""


# ======================================================================== Zeit, Schlüssel, Hashes


def zeit_text(z: dt.datetime) -> str:
    return z.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def zeit_lesen(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _schluessel_spalten(tabelle: str) -> list[int]:
    namen = [s[0] for s in sicherung.SPALTEN[tabelle]]
    if namen[0] == "id":
        return [0]
    pk = sicherung._SCHLUESSEL.get(tabelle)
    if pk is None:
        return list(range(len(namen)))
    teile = [t.strip() for t in pk[pk.index("(") + 1:pk.rindex(")")].split(",")]
    return [namen.index(t) for t in teile]


SCHLUESSEL = {t: _schluessel_spalten(t) for t in sicherung.SPALTEN}


def _schluessel(tabelle: str, zeile: tuple) -> str:
    return json.dumps([zeile[i] for i in SCHLUESSEL[tabelle]], ensure_ascii=False, separators=(",", ":"))


def _zeilen_hash(tabelle: str, zeile: tuple) -> str:
    if tabelle == "dokument_inhalt":   # inhaltsadressiert: der Schlüssel ist der Hash des Inhalts
        return zeile[0]
    text = json.dumps(list(zeile), ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def hashes(zustand: Zustand) -> Hashes:
    return {t: {k: _zeilen_hash(t, z) for k, z in zeilen.items()} for t, zeilen in zustand.items()}


def pruefwert(h: Hashes) -> str:
    """Prüfwert (1): SHA-256 über alle Zeilen außer dem Begleitzustand, in fester Reihenfolge."""
    sha = hashlib.sha256()
    for t in sorted(h):
        if t in BEGLEIT:
            continue
        for k in sorted(h[t]):
            sha.update(f"{t}\t{k}\t{h[t][k]}\n".encode())
    return sha.hexdigest()


# ======================================================================== Zustand lesen


def zustand_lesen(con) -> Zustand:
    """Gesicherter Zustand aus einer App-Datenbank (Lesen in der laufenden Transaktion des Aufrufers)."""
    aus: Zustand = {}
    for tabelle, spalten in sicherung.SPALTEN.items():
        if tabelle == "id_zaehler":
            zeilen = [tuple(x) for x in sorted(sicherung._zaehler_lesen(con).items())]
        elif tabelle == "dokument_inhalt":
            zeilen = [(r[0], None) for r in con.execute(
                "SELECT sha256 FROM dokument_inhalt WHERE sha256 IN (SELECT sha256 FROM dokument)")]
        elif tabelle == "einstellung":
            zeilen = sicherung.einstellungen_lesen(con)
        else:
            namen = ", ".join(s[0] for s in spalten)
            zeilen = [tuple(r) for r in con.execute(f"SELECT {namen} FROM {tabelle}")]
        aus[tabelle] = {_schluessel(tabelle, z): tuple(z) for z in zeilen}
    return aus


# ======================================================================== Differenzen


def differenz(alt: Hashes, neu: Zustand, neu_h: Hashes, inhalt: Callable[[str], bytes]) -> dict:
    """Zeilendifferenz von ``alt`` (nur Hashes) nach ``neu``; Begleitzustand gehört nicht dazu."""
    d: dict[str, dict] = {"neu": {}, "geaendert": {}, "geloescht": {}}
    for t, zeilen in neu.items():
        if t in BEGLEIT:
            continue
        a = alt.get(t, {})
        neue = [k for k in zeilen if k not in a]
        geaendert = [k for k in zeilen if k in a and a[k] != neu_h[t][k]]
        weg = sorted(k for k in a if k not in zeilen)
        if t == "dokument_inhalt":
            neue_zeilen = [(zeilen[k][0], zeilen[k][1] if zeilen[k][1] is not None else inhalt(zeilen[k][0]))
                           for k in sorted(neue)]
        else:
            neue_zeilen = [zeilen[k] for k in sorted(neue)]
        if neue_zeilen:
            d["neu"][t] = neue_zeilen
        if geaendert:
            d["geaendert"][t] = [zeilen[k] for k in sorted(geaendert)]
        if weg:
            d["geloescht"][t] = weg
    return d


def anwenden(basis: Zustand | None, inhalt: dict) -> Zustand:
    """Zustand nach Anwenden der Differenz eines Punkts (auf die Basis bzw. bei einem Anker auf leer)."""
    aus: Zustand = {t: dict(basis.get(t, {})) if basis else {} for t in sicherung.SPALTEN}
    for t, keys in inhalt["geloescht"].items():
        for k in keys:
            aus[t].pop(k, None)
    for art in ("neu", "geaendert"):
        for t, zeilen in inhalt[art].items():
            for z in zeilen:
                aus[t][_schluessel(t, z)] = z
    for t in BEGLEIT:
        aus[t] = {_schluessel(t, z): z for z in inhalt["begleit"][t]}
    return aus


def zaehlen(alt: Hashes, neu_h: Hashes) -> dict:
    """Anzahl neuer, geänderter und gelöschter Zeilen je Tabelle (ohne Begleitzustand)."""
    aus: dict[str, dict[str, int]] = {}
    for t in neu_h:
        if t in BEGLEIT:
            continue
        a, n = alt.get(t, {}), neu_h[t]
        z = {"neu": sum(1 for k in n if k not in a), "geaendert": sum(1 for k in n if k in a and a[k] != n[k]),
             "geloescht": sum(1 for k in a if k not in n)}
        if any(z.values()):
            aus[t] = z
    return aus


def anzahlen(d: dict) -> dict:
    aus: dict[str, dict[str, int]] = {}
    for art in ("neu", "geaendert", "geloescht"):
        for t, zeilen in d[art].items():
            aus.setdefault(t, {"neu": 0, "geaendert": 0, "geloescht": 0})[art] = len(zeilen)
    return aus


def _wert_kodieren(w: Any) -> Any:
    return {"b": base64.b64encode(w).decode("ascii")} if isinstance(w, bytes) else w


def _wert_lesen(w: Any) -> Any:
    return base64.b64decode(w["b"]) if isinstance(w, dict) else w


def _packen(obj: dict) -> bytes:
    def zeilen(x: dict) -> dict:
        return {t: [[_wert_kodieren(w) for w in z] for z in zs] for t, zs in x.items()}

    roh = dict(obj, neu=zeilen(obj["neu"]), geaendert=zeilen(obj["geaendert"]), begleit=zeilen(obj["begleit"]))
    return lzma.compress(json.dumps(roh, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), preset=6)


def _entpacken(daten: bytes) -> dict:
    try:
        obj = json.loads(lzma.decompress(daten).decode("utf-8"))
    except (lzma.LZMAError, ValueError, UnicodeDecodeError):
        raise NichtHerstellbar("Datei unlesbar") from None
    if not isinstance(obj, dict) or obj.get("format") != FORMAT:
        raise NichtHerstellbar("fremde Datei")
    for art in ("neu", "geaendert", "begleit"):
        obj[art] = {t: [tuple(_wert_lesen(w) for w in z) for z in zs] for t, zs in obj[art].items()}
    return obj


# ======================================================================== Ablage


class Ablage:
    """Verzeichnis der Sicherungspunkte eines Modus samt Angaben (``punkte.json``)."""

    def __init__(self, config: KontorConfig) -> None:
        self.config = config
        self.pfad = config.sicherungspunkte_verzeichnis
        self._stand: dict | None = None
        self._cache: dict[str, Zustand] = {}

    # ---------------------------------------------------------------- Dateien
    def anlegen(self) -> None:
        for p in (self.pfad.parent, self.pfad):
            if not p.is_dir():
                p.mkdir(parents=True, mode=0o700)
                os.chmod(p, 0o700)

    @contextlib.contextmanager
    def gesperrt(self) -> Iterator[Ablage]:
        self.anlegen()
        fd = os.open(self.pfad / ".sperre", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._stand = None
            self._cache = {}
            yield self
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _schreiben(self, name: str, daten: bytes) -> None:
        fd, tmp = tempfile.mkstemp(prefix=".neu-", dir=self.pfad)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(daten)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.pfad / name)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    @property
    def stand(self) -> dict:
        if self._stand is None:
            p = self.pfad / "punkte.json"
            if p.exists():
                self._stand = json.loads(p.read_text("utf-8"))
            else:
                self._stand = {"punkte": {}, "bezug": None, "zuletzt_geprueft": None, "letzte_aenderung": 0}
        return self._stand

    def speichern(self) -> None:
        self._schreiben("punkte.json", json.dumps(self.stand, ensure_ascii=False, indent=1).encode("utf-8"))

    @property
    def punkte(self) -> dict[str, dict]:
        return self.stand["punkte"]

    def datei(self, kennung: str) -> pathlib.Path:
        return self.pfad / self.punkte[kennung]["datei"]

    def zustandsliste(self) -> tuple[str | None, Hashes | None]:
        p = self.pfad / "zustand.json.gz"
        try:
            obj = json.loads(zlib.decompress(p.read_bytes()))
            return obj["kennung"], obj["hashes"]
        except (OSError, zlib.error, ValueError, KeyError):
            return None, None

    def zustandsliste_setzen(self, kennung: str, h: Hashes) -> None:
        self._schreiben("zustand.json.gz", zlib.compress(json.dumps({"kennung": kennung, "hashes": h}).encode(), 1))

    # ---------------------------------------------------------------- Herstellen
    def kette(self, kennung: str) -> list[str]:
        """Kennungen von ``kennung`` bis zum Anker (einschließlich)."""
        aus = []
        k: str | None = kennung
        while k is not None:
            if k not in self.punkte or k in aus:
                raise NichtHerstellbar("Kette unterbrochen")
            aus.append(k)
            k = None if self.punkte[k]["anker"] else self.punkte[k]["basis"]
        return aus

    def pruefsumme_ok(self, kennung: str) -> bool:
        try:
            return hashlib.sha256(self.datei(kennung).read_bytes()).hexdigest() == self.punkte[kennung]["datei_sha256"]
        except OSError:
            return False

    def lesen(self, kennung: str) -> dict:
        m = self.punkte.get(kennung)
        if m is None:
            raise NichtHerstellbar("unbekannt")
        try:
            daten = self.datei(kennung).read_bytes()
        except OSError:
            raise NichtHerstellbar("Datei fehlt") from None
        if hashlib.sha256(daten).hexdigest() != m["datei_sha256"]:
            raise NichtHerstellbar("Prüfsumme")
        return _entpacken(daten)

    def herstellen(self, kennung: str) -> Zustand:
        """Zustand eines Punkts; prüft Prüfsummen aller Glieder und den Prüfwert jedes Glieds."""
        if kennung in self._cache:
            return self._cache[kennung]
        kette = self.kette(kennung)
        zustand: Zustand | None = None
        start = len(kette)
        for i, k in enumerate(kette):
            if k in self._cache:
                zustand, start = self._cache[k], i
                break
        for k in reversed(kette[:start]):
            zustand = anwenden(zustand, self.lesen(k))
            if pruefwert(hashes(zustand)) != self.punkte[k]["pruefwert"]:
                raise NichtHerstellbar("Prüfwert")
            self._cache[k] = zustand
        assert zustand is not None
        return zustand

    def herstellbar(self, kennung: str) -> bool:
        try:
            self.herstellen(kennung)
            return True
        except NichtHerstellbar:
            return False

    # ---------------------------------------------------------------- Schreiben eines Punkts
    def punkt_schreiben(self, meta: dict, inhalt: dict) -> None:
        """Datei schreiben und Angaben setzen (noch nicht ``punkte.json``)."""
        daten = _packen(inhalt)
        name = f"{meta['kennung']}.{secrets.token_hex(2)}.kpunkt"
        self._schreiben(name, daten)
        meta.update(datei=name, groesse=len(daten), datei_sha256=hashlib.sha256(daten).hexdigest())
        self.punkte[meta["kennung"]] = meta

    def aufraeumen(self) -> None:
        """Dateien ersetzter oder entfernter Punkte löschen (erst nach ``speichern``)."""
        bekannt = {m["datei"] for m in self.punkte.values()} | {"punkte.json", "zustand.json.gz", ".sperre"}
        for p in self.pfad.iterdir():
            if p.name not in bekannt and p.suffix == ".kpunkt":
                with contextlib.suppress(OSError):
                    p.unlink()


# ======================================================================== Punkt anlegen


def _chronik(con, ab_id: int) -> tuple[list[dict], int]:
    zeilen = con.execute("SELECT id, zeitpunkt, quelle, aktion, beschreibung FROM aenderung WHERE id > ? ORDER BY id",
                         (ab_id,)).fetchall()
    hoechste = con.execute("SELECT COALESCE(MAX(id), 0) FROM aenderung").fetchone()[0]
    return ([{"zeitpunkt": r[1], "quelle": r[2], "aktion": r[3], "beschreibung": r[4]} for r in zeilen][-500:],
            max(int(hoechste), ab_id))


def _anker_noetig(ab: Ablage, jetzt: dt.datetime) -> bool:
    bezug = ab.stand["bezug"]
    if bezug is None or bezug not in ab.punkte:
        return True
    if ab.punkte[bezug].get("schema_db") != db.SCHEMA_VERSION:
        return True
    monat = (jetzt.year, jetzt.month)
    if not any((zeit_lesen(m["zeitpunkt"]).year, zeit_lesen(m["zeitpunkt"]).month) == monat
               for m in ab.punkte.values()):
        return True
    try:
        return not all(ab.pruefsumme_ok(k) for k in ab.kette(bezug))
    except NichtHerstellbar:
        return True


def _alte_hashes(ab: Ablage, bezug: str) -> Hashes:
    k, h = ab.zustandsliste()
    if k == bezug and h is not None:
        return h
    return hashes(ab.herstellen(bezug))


def _marke_setzen(meta: dict, marke: str, name: str | None) -> None:
    if marke != "stuendlich" and marke not in meta["marken"]:
        meta["marken"].append(marke)
    if name and not meta.get("name"):
        meta["name"] = name


def punkt_anlegen(ab: Ablage, con, jetzt: dt.datetime, marke: str, name: str | None = None,
                  anker: bool = False) -> tuple[dict, bool]:
    """Legt einen Punkt an, wenn der Stand vom Bezugspunkt abweicht (3.1). Aufrufer hält Sperre und Transaktion."""
    zustand = zustand_lesen(con)
    h = hashes(zustand)
    pw = pruefwert(h)
    bezug = ab.stand["bezug"]
    jetzt_text = zeit_text(jetzt)
    if bezug in ab.punkte and ab.punkte[bezug]["pruefwert"] == pw:
        meta = ab.punkte[bezug]
        _marke_setzen(meta, marke, name)
        ab.stand["zuletzt_geprueft"] = jetzt_text
        ab.stand["letzte_aenderung"] = _chronik(con, ab.stand["letzte_aenderung"])[1]
        ab.speichern()
        return meta, False
    chronik, hoechste = _chronik(con, ab.stand["letzte_aenderung"])
    kennung = jetzt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    ist_anker = anker or _anker_noetig(ab, jetzt)

    def inhalt_von(sha: str) -> bytes:
        return dokumente.inhalt_bytes(con, sha)

    if not ist_anker:
        try:
            alt = _alte_hashes(ab, bezug)
        except NichtHerstellbar:
            ist_anker = True
    d = differenz({} if ist_anker else alt, zustand, h, inhalt_von)
    meta = {"kennung": kennung, "zeitpunkt": jetzt_text, "marken": [marke], "name": name, "angeheftet": False,
            "anker": ist_anker, "basis": None if ist_anker else bezug, "eltern": bezug if bezug in ab.punkte else None,
            "pruefwert": pw, "schema_db": db.SCHEMA_VERSION, "geprueft_am": None,
            "aenderungen": anzahlen(d) if bezug in ab.punkte or ist_anker else {}, "chronik_anzahl": len(chronik)}
    if ist_anker and bezug in ab.punkte:
        meta["aenderungen"] = zaehlen(_sicher_hashes(ab, bezug), h)
    inhalt = dict(d, format=FORMAT, formatversion=FORMATVERSION, kennung=kennung, zeitpunkt=jetzt_text,
                  pruefwert=pw, schema_db=db.SCHEMA_VERSION, chronik=chronik,
                  begleit={t: list(zustand[t].values()) for t in BEGLEIT})
    ab.punkt_schreiben(meta, inhalt)
    if not _sofort_pruefen(ab, kennung, {} if ist_anker else alt):   # misslingt sie bei einer Differenz: Anker
        if ist_anker:
            del ab.punkte[kennung]
            raise OSError("Der neue Sicherungspunkt ließ sich nicht prüfen.")
        meta["anker"], meta["basis"] = True, None
        inhalt.update(differenz({}, zustand, h, inhalt_von))
        ab.punkt_schreiben(meta, inhalt)
        if not _sofort_pruefen(ab, kennung, {}):
            del ab.punkte[kennung]
            raise OSError("Der neue Sicherungspunkt ließ sich nicht prüfen.")
    meta["geprueft_am"] = jetzt_text
    ab.stand.update(bezug=kennung, zuletzt_geprueft=jetzt_text, letzte_aenderung=hoechste)
    ab.speichern()
    ab.zustandsliste_setzen(kennung, h)
    ab.aufraeumen()
    return meta, True


def _sofort_pruefen(ab: Ablage, kennung: str, alt: Hashes) -> bool:
    """Sofortprüfung: Datei wieder lesen, auf die Hashes der Basis anwenden, Prüfwert vergleichen."""
    try:
        inhalt = ab.lesen(kennung)
    except NichtHerstellbar:
        return False
    h = {t: dict(alt.get(t, {})) for t in sicherung.SPALTEN}
    for t, keys in inhalt["geloescht"].items():
        for k in keys:
            h[t].pop(k, None)
    for art in ("neu", "geaendert"):
        for t, zeilen in inhalt[art].items():
            for z in zeilen:
                h[t][_schluessel(t, z)] = _zeilen_hash(t, z)
    return pruefwert(h) == ab.punkte[kennung]["pruefwert"]


def _sicher_hashes(ab: Ablage, kennung: str) -> Hashes:
    try:
        return _alte_hashes(ab, kennung)
    except NichtHerstellbar:
        return {}


# ======================================================================== Ausdünnen


def _monate(jetzt: dt.datetime, z: dt.datetime) -> int:
    return (jetzt.year * 12 + jetzt.month) - (z.year * 12 + z.month)


def _eimer(cfg: KontorConfig, jetzt: dt.datetime, z: dt.datetime) -> tuple | None:
    alter = jetzt - z
    if cfg.sicherung_tage and alter <= dt.timedelta(days=cfg.sicherung_tage):
        return ("t", z.date())
    if cfg.sicherung_wochen and alter <= dt.timedelta(weeks=cfg.sicherung_wochen):
        return ("w", tuple(z.isocalendar())[:2])
    if cfg.sicherung_monate and _monate(jetzt, z) <= cfg.sicherung_monate:
        return ("m", z.year, z.month)
    return None


def behalten(ab: Ablage, jetzt: dt.datetime) -> set[str]:
    """Kennungen, die nach den Stufen aus 4 bleiben."""
    cfg = ab.config
    fenster = dt.timedelta(hours=cfg.sicherung_stunden)
    bleibt: set[str] = set()
    if ab.stand["bezug"] in ab.punkte:
        bleibt.add(ab.stand["bezug"])
    eimer: dict[tuple, tuple[dt.datetime, str]] = {}
    for k, m in ab.punkte.items():
        z = zeit_lesen(m["zeitpunkt"])
        if m["angeheftet"] or jetzt - z <= fenster or (
                set(m["marken"]) & set(GESCHUETZT) and jetzt - z <= dt.timedelta(days=SCHUTZ_TAGE)):
            bleibt.add(k)
            continue
        e = _eimer(cfg, jetzt, z)
        if e is not None and (e not in eimer or eimer[e][0] < z):
            eimer[e] = (z, k)
    bleibt |= {k for _, k in eimer.values()}
    return bleibt


def _umstellen(ab: Ablage, kennung: str, basis: str | None) -> None:
    """Punkt mit gleichem Zustand neu schreiben: als Anker (``basis`` None) oder als Differenz zu ``basis``."""
    zustand = ab.herstellen(kennung)
    h = hashes(zustand)
    alt = {} if basis is None else hashes(ab.herstellen(basis))
    inhalt = ab.lesen(kennung)
    inhalt.update(differenz(alt, zustand, h, lambda sha: b""))
    meta = dict(ab.punkte[kennung], anker=basis is None, basis=basis)
    ab.punkt_schreiben(meta, inhalt)
    ab._cache.pop(kennung, None)
    if not ab.herstellbar(kennung):
        raise OSError(f"Umgestellter Sicherungspunkt {kennung} ließ sich nicht prüfen.")
    ab._cache[kennung] = zustand


def _ausduennen(ab: Ablage, jetzt: dt.datetime) -> None:
    bleibt = behalten(ab, jetzt)
    fenster = dt.timedelta(hours=ab.config.sicherung_stunden)
    gruppen: dict[str, list[str]] = {}
    for k in bleibt:
        try:
            gruppen.setdefault(ab.kette(k)[-1], []).append(k)
        except NichtHerstellbar:
            continue
    for anker, mitglieder in gruppen.items():
        mitglieder.sort(key=lambda k: ab.punkte[k]["zeitpunkt"])
        try:
            neu = anker if anker in bleibt else mitglieder[0]
            if neu != anker:
                _umstellen(ab, neu, None)
            for k in mitglieder:
                m = ab.punkte[k]
                if k == neu or m["anker"]:
                    continue
                alt = jetzt - zeit_lesen(m["zeitpunkt"]) > fenster
                if m["basis"] not in bleibt or (alt and m["basis"] != neu):
                    _umstellen(ab, k, neu)
        except NichtHerstellbar:
            continue   # beschädigte Kette: unverändert lassen, sie wird im Stand gemeldet
    noch_basis = {m["basis"] for k, m in ab.punkte.items() if k in bleibt and not m["anker"]}
    for k in [k for k in ab.punkte if k not in bleibt and k not in noch_basis]:
        del ab.punkte[k]
    ab.speichern()
    ab.aufraeumen()


# ======================================================================== Herstellen als Sicherungsdatei


def _in_datenbank(zustand: Zustand, pfad: pathlib.Path) -> None:
    db.schema_anlegen(pfad)
    con = db.verbinde(pfad)
    try:
        zeilen = {t: list(zustand[t].values()) for t in sicherung.SPALTEN}
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("BEGIN")
        sicherung.laden(con, zeilen)
        con.executemany("INSERT INTO sync_kennung (kennung) VALUES (?)", zeilen["sync_kennung"])
        con.executemany("INSERT INTO sync_konto_zustand (iban, konto_id, letzter_abruf_bis, letzter_erfolg_am,"
                        " entscheidung, entscheidung_buchungen) VALUES (?, ?, ?, ?, ?, ?)", zeilen["sync_konto_zustand"])
        sicherung.einstellungen_setzen(con, zeilen["einstellung"])
        for objekt, hoechste in zeilen["id_zaehler"]:
            tabelle = sicherung.ZAEHLER.get(objekt)
            if tabelle:
                con.execute("DELETE FROM sqlite_sequence WHERE name = ?", (tabelle,))
                con.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (tabelle, hoechste))
        con.execute("COMMIT")
    finally:
        con.close()


def sicherungsdatei(ab: Ablage, kennung: str) -> tuple[bytes, str]:
    """Eigenständige Sicherungsdatei (sicherung.md 3) eines Punkts; geprüft gegen den Prüfwert."""
    zustand = ab.herstellen(kennung)
    m = ab.punkte[kennung]
    with tempfile.TemporaryDirectory(prefix="kontor-punkt-") as tmp:
        pfad = pathlib.Path(tmp) / "k.sqlite3"
        _in_datenbank(zustand, pfad)
        con = db.verbinde(pfad)
        try:
            if pruefwert(hashes(zustand_lesen(con))) != m["pruefwert"]:
                raise NichtHerstellbar("Sicherungsdatei")
        finally:
            con.close()
        modus = "mock" if ab.config.mock_modus else "echt"
        return sicherung.erstellen(pfad, modus, zeit_lesen(m["zeitpunkt"]))


# ======================================================================== Öffentliche Sicht


def _stufe(cfg: KontorConfig, jetzt: dt.datetime, m: dict) -> str:
    if m["angeheftet"]:
        return "angeheftet"
    z = zeit_lesen(m["zeitpunkt"])
    if jetzt - z <= dt.timedelta(hours=cfg.sicherung_stunden):
        return "stunden"
    e = _eimer(cfg, jetzt, z)
    return {"t": "tage", "w": "wochen", "m": "monate"}.get(e[0] if e else "", "basis")


def _vorfahren(ab: Ablage, k: str | None) -> list[str]:
    aus = []
    while k is not None and k in ab.punkte and k not in aus:
        aus.append(k)
        k = ab.punkte[k]["eltern"]
    return aus


def oeffentlich(ab: Ablage, m: dict, kette_groesse: int | None = None) -> dict:
    aus = {f: m[f] for f in ("kennung", "zeitpunkt", "marken", "name", "angeheftet", "anker", "basis", "eltern",
                             "groesse", "aenderungen", "geprueft_am", "chronik_anzahl")}
    if kette_groesse is None:
        try:
            kette_groesse = sum(ab.punkte[k]["groesse"] for k in ab.kette(m["kennung"]))
        except NichtHerstellbar:
            kette_groesse = m["groesse"]
    aus["groesse_herstellen"] = kette_groesse
    return aus


def liste(ab: Ablage, jetzt: dt.datetime, aktueller_pruefwert: str | None) -> dict:
    bezug = ab.stand["bezug"] if ab.stand["bezug"] in ab.punkte else None
    vorfahren = set(_vorfahren(ab, bezug))
    unveraendert = bezug is not None and ab.punkte[bezug]["pruefwert"] == aktueller_pruefwert
    stufen = dict.fromkeys(("stunden", "tage", "wochen", "monate", "angeheftet", "basis"), 0)
    punkte = []
    for m in sorted(ab.punkte.values(), key=lambda x: x["zeitpunkt"], reverse=True):
        p = oeffentlich(ab, m)
        vorwaerts = bezug is not None and bezug in _vorfahren(ab, m["kennung"]) and m["kennung"] != bezug
        p.update(aktuell=m["kennung"] == bezug and unveraendert, vorwaerts=vorwaerts,
                 verlassen=m["kennung"] not in vorfahren and not vorwaerts)
        stufen[_stufe(ab.config, jetzt, m)] += m["groesse"]
        punkte.append(p)
    try:
        frei = shutil.disk_usage(ab.pfad).free
    except OSError:
        frei = None
    naechster = (jetzt.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1))
    return {"punkte": punkte,
            "gesamt": {"groesse": sum(m["groesse"] for m in ab.punkte.values()), "anzahl": len(ab.punkte),
                       "stufen": stufen},
            "bezugspunkt": bezug, "unveraendert": unveraendert, "zuletzt_geprueft": ab.stand["zuletzt_geprueft"],
            "naechster_lauf": zeit_text(naechster), "frei": frei}


# ======================================================================== Einspielen (5.1)


def soll_pruefwert(s: sicherung.Sicherung) -> str:
    """Prüfwert, den der Bestand nach dem Einspielen von ``s`` haben muss (mit denselben Nacharbeiten)."""
    mem = db.verbinde(":memory:")  # type: ignore[arg-type]
    try:
        mem.executescript(db.SCHEMA)
        db._migrieren(mem)
        mem.execute("PRAGMA foreign_keys = OFF")
        mem.execute("BEGIN")
        sicherung.laden(mem, s.zeilen)
        mem.executemany("INSERT INTO sync_kennung (kennung) VALUES (?)", s.zeilen["sync_kennung"])
        sicherung.nacharbeiten(mem, s)
        mem.execute("COMMIT")
        if s.manifest["schemaversion"] < 11:
            return ""   # Einstellungen bleiben die der Instanz: Soll erst nach dem Einspielen bekannt
        return pruefwert(hashes(zustand_lesen(mem)))
    finally:
        mem.close()


def nach_einspielen_pruefen(con, soll: str) -> None:
    if soll and pruefwert(hashes(zustand_lesen(con))) != soll:
        raise ApiFehler(500, "interner_fehler", "Der eingespielte Stand stimmt nicht mit der Sicherung überein; nichts wurde"
                                       " geändert.")


@contextlib.contextmanager
def _ablage_gesperrt(config: KontorConfig) -> Iterator[Ablage]:
    ab = Ablage(config)
    try:
        sperre = ab.gesperrt()
        sperre.__enter__()
    except OSError:
        raise ApiFehler(409, "sicherung_vorher_fehlgeschlagen",
                        "Der bestehende Stand ließ sich nicht sichern; es wurde nichts geändert.") from None
    try:
        yield ab
    finally:
        sperre.__exit__(None, None, None)


def einspielen(config: KontorConfig, s: sicherung.Sicherung, jetzt: dt.datetime, zeitpunkt: str,
               ziel: str | None = None) -> dict:
    """Ablauf 5.1: bestehenden Stand sichern, alles löschen, ``s`` einspielen, prüfen; Bezugspunkt setzen."""
    soll = soll_pruefwert(s)
    with _ablage_gesperrt(config) as ab:
        vorher: dict = {}

        def sichern(con) -> None:
            try:
                meta, _ = punkt_anlegen(ab, con, jetzt, "vor_wiederherstellung")
            except (OSError, ValueError, sqlite3.DatabaseError):
                raise ApiFehler(409, "sicherung_vorher_fehlgeschlagen",
                                "Der bestehende Stand ließ sich nicht sichern; es wurde nichts geändert.") from None
            vorher["kennung"] = meta["kennung"]

        con = db.verbinde(config.aktive_datenbank)
        try:
            erg = sicherung.einspielen(con, s, zeitpunkt, vor_einspielen=sichern,
                                       nach_einspielen=lambda c: nach_einspielen_pruefen(c, soll))
            if ziel is not None:
                ab.stand["bezug"] = ziel
                ab.stand["zuletzt_geprueft"] = zeit_text(jetzt)
                ab.speichern()
                ab.zustandsliste_setzen(ziel, hashes(ab.herstellen(ziel)))
            else:
                con.execute("BEGIN")
                try:
                    punkt_anlegen(ab, con, jetzt, "aus_datei", anker=True)
                finally:
                    con.execute("ROLLBACK")
        finally:
            con.close()
    erg["vorher"] = vorher.get("kennung")
    erg["ziel"] = ziel
    return erg


def wechsel_vorbereiten(config: KontorConfig, kennung: str,
                        unveraendert_erlaubt: bool = False) -> tuple[sicherung.Sicherung, str]:
    """Punkt herstellen und als geprüfte Sicherung liefern; 404/409 nach 5.2."""
    with _ablage_gesperrt(config) as ab:
        if kennung not in ab.punkte:
            raise ApiFehler(404, "nicht_gefunden", "Den Sicherungspunkt gibt es nicht.")
        try:
            daten, _ = sicherungsdatei(ab, kennung)
        except NichtHerstellbar:
            raise ApiFehler(409, "punkt_nicht_herstellbar",
                            "Der Sicherungspunkt lässt sich nicht herstellen (Datei fehlt oder ist beschädigt).") from None
        ziel_pw = ab.punkte[kennung]["pruefwert"]
        con = db.verbinde(config.aktive_datenbank)
        try:
            con.execute("BEGIN")
            try:
                aktuell = pruefwert(hashes(zustand_lesen(con)))
            finally:
                con.execute("ROLLBACK")
        finally:
            con.close()
    if aktuell == ziel_pw and not unveraendert_erlaubt:
        raise ApiFehler(409, "stand_unveraendert", "Der aktuelle Stand entspricht bereits diesem Sicherungspunkt.")
    return sicherung.pruefen(daten), kennung


# ======================================================================== Einstieg


def jetzt_von(config: KontorConfig) -> dt.datetime:
    from .sync import SyncDienst

    return SyncDienst(config).jetzt()


def stunde(config: KontorConfig, *, jetzt: dt.datetime | None = None, marke: str = "stuendlich",
           ausduennen: bool = True) -> dict:
    """Stündlicher Lauf (8): Punkt bei Änderung, Ausdünnen, danach Änderungsprotokoll kürzen."""
    jetzt = jetzt or jetzt_von(config)
    sicherung._schema_sicherstellen(config.aktive_datenbank)
    with Ablage(config).gesperrt() as ab:
        con = db.verbinde(config.aktive_datenbank)
        try:
            con.execute("BEGIN")
            try:
                meta, neu = punkt_anlegen(ab, con, jetzt, marke)
            finally:
                con.execute("ROLLBACK")
        finally:
            con.close()
        gedeckt = ab.stand["letzte_aenderung"]
        if ausduennen:
            _ausduennen(ab, jetzt)
        aus = {"neu": neu, "punkt": oeffentlich(ab, meta)}
    if config.protokoll_stunden:
        grenze = zeit_text(jetzt - dt.timedelta(hours=config.protokoll_stunden))
        con = db.verbinde(config.aktive_datenbank)
        try:
            protokoll.kuerzen(con, grenze, gedeckt)
        finally:
            con.close()
    return aus


def ausduennen(config: KontorConfig, *, jetzt: dt.datetime | None = None) -> None:
    with Ablage(config).gesperrt() as ab:
        _ausduennen(ab, jetzt or jetzt_von(config))


def von_hand(config: KontorConfig, jetzt: dt.datetime, name: str | None) -> tuple[dict, bool]:
    with _ablage_gesperrt(config) as ab:
        con = db.verbinde(config.aktive_datenbank)
        try:
            con.execute("BEGIN")
            try:
                meta, neu = punkt_anlegen(ab, con, jetzt, "von_hand", name)
            finally:
                con.execute("ROLLBACK")
        finally:
            con.close()
        return oeffentlich(ab, meta), neu


def aktueller_pruefwert(config: KontorConfig) -> str:
    con = db.verbinde(config.aktive_datenbank)
    try:
        con.execute("BEGIN")
        try:
            return pruefwert(hashes(zustand_lesen(con)))
        finally:
            con.execute("ROLLBACK")
    finally:
        con.close()


# Hilfen für Tests und Kommandozeile
def datei_pfad(config: KontorConfig, kennung: str) -> pathlib.Path:
    return Ablage(config).datei(kennung)


def herstellen_pruefen(config: KontorConfig, kennung: str) -> bool:
    """Ganze Kette lesen und jeden Prüfwert prüfen."""
    with Ablage(config).gesperrt() as ab:
        return ab.herstellbar(kennung)


def kettenlaenge(config: KontorConfig, kennung: str) -> int:
    return len(Ablage(config).kette(kennung))


__all__ = ["Ablage", "NichtHerstellbar", "ausduennen", "einspielen", "liste", "punkt_anlegen", "sicherungsdatei",
           "stunde", "von_hand", "wechsel_vorbereiten"]
