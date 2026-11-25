"""Demodaten für die Testinstanz (Feature ``demodaten``): ein erfundener Haushalt zum Vorführen.

``aufbauen`` schreibt die Mock-Datendatei der erfundenen Welt (``demowelt``) und baut daraus eine neue
Mock-Datenbank – ausschließlich über die REST-Schnittstelle der Anwendung, so wie ein Anwender über drei Jahre
gearbeitet hätte: Konten, Kategorien, Regeln, Split-Vorlage und Kredite anlegen, dann in Abständen Konten und Mails
abrufen, Buchungen zuordnen und bestätigen, zum Jahreswechsel abstimmen. Dabei läuft die simulierte Uhr des
Mock-Modus mit; Protokoll, Abrufe und Benachrichtigungen tragen deshalb glaubwürdige Zeiten.

Der Aufbau endet ``VORLAUF_TAGE`` vor „heute“ und lässt die letzten Wochen unbearbeitet: In der Vorführung liefern
„Konten abrufen“ und „Mails abrufen“ neue Einträge, und es gibt Vorschläge zu prüfen.

Aufruf (durch ``python -m kontor.testinstanz demo``)::

    python -m kontor.demodaten <Mock-Datenbank> <Mock-Datendatei> [--heute JJJJ-MM-TT] [--monate N]

Hier wird keine andere Datenbank gelesen; echte Daten kommen nicht vor.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import io
import json
import os
import pathlib
import sys
import urllib.parse

from . import demowelt as W
from .config import KontorConfig
from .demowelt import welt  # noqa: F401 – öffentliche Schnittstelle

MONATE = 36
VORLAUF_TAGE = 3      # der Aufbau endet so viele Tage vor „heute“
OFFEN_TAGE = 18       # so viele Tage davor bleiben unbearbeitet (Vorschläge, Unkategorisiertes)
ABSTAND_TAGE = 90     # Abstand der Arbeitsgänge davor
ZINSKORREKTUR = 312   # Cent: so viel mehr Zinsen nennt der erfundene Jahresauszug des Wohnungsdarlehens


class DemoFehler(Exception):
    pass


def konfiguration(datenbank: pathlib.Path, mock_datei: pathlib.Path, **mehr) -> KontorConfig:
    """Konfiguration einer Instanz auf den Demodaten: Mock-Modus, Verhalten wie die ausgelieferte Testinstanz."""
    datenbank = pathlib.Path(datenbank)
    werte = dict(datenbank=datenbank.with_name("unbenutzt.sqlite3"), mock_modus=True, mock_datenbank=datenbank,
                 mock_daten=pathlib.Path(mock_datei), umbuchung_automatisch=True, lernmodell_automatisch=True,
                 regeln_automatisch=True, wiederkehrend_automatisch=True, sync_konten_anlegen=False,
                 mail_bestellnummer=True, mail_nur_koepfe=True, planer_starten=False)
    werte.update(mehr)
    return KontorConfig(**werte)


# ------------------------------------------------------------------------------------------------ Aufrufe

class _Rest:
    """Ruft die Anwendung im selben Prozess über ASGI auf (kein Netz, kein Server)."""

    def __init__(self, app) -> None:
        self.app = app
        self.schleife = asyncio.new_event_loop()

    def schliessen(self) -> None:
        self.schleife.close()

    def roh(self, methode: str, pfad: str, koerper: bytes = b"", typ: str = "application/json") -> tuple[int, bytes]:
        pfad, _, abfrage = pfad.partition("?")
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": methode,
                 "path": pfad, "raw_path": pfad.encode(), "query_string": abfrage.encode(), "scheme": "http",
                 "headers": [(b"host", b"127.0.0.1"), (b"content-type", typ.encode()),
                             (b"content-length", str(len(koerper)).encode())],
                 "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 80)}
        antwort = {"status": 0, "koerper": b""}
        gelesen = False

        async def receive():
            nonlocal gelesen
            if gelesen:
                await asyncio.sleep(3600)
            gelesen = True
            return {"type": "http.request", "body": koerper, "more_body": False}

        async def send(nachricht):
            if nachricht["type"] == "http.response.start":
                antwort["status"] = nachricht["status"]
            elif nachricht["type"] == "http.response.body":
                antwort["koerper"] += nachricht.get("body", b"")

        self.schleife.run_until_complete(self.app(scope, receive, send))
        return antwort["status"], antwort["koerper"]

    def __call__(self, methode: str, pfad: str, daten: object = None):
        koerper = json.dumps(daten).encode("utf-8") if daten is not None else b""
        status, roh = self.roh(methode, pfad, koerper)
        if not 200 <= status < 300:
            raise DemoFehler(f"{methode} {pfad} antwortet mit {status}: {roh[:400].decode('utf-8', 'replace')}")
        return json.loads(roh) if roh else None

    def seiten(self, pfad: str) -> list[dict]:
        """Alle Einträge einer seitenweisen Liste."""
        aus: list[dict] = []
        seite = 1
        while True:
            d = self("GET", f"{pfad}{'&' if '?' in pfad else '?'}pro_seite=500&seite={seite}")
            aus.extend(d["eintraege"])
            if len(aus) >= d["gesamt"] or not d["eintraege"]:
                return aus
            seite += 1

    def hochladen(self, pfad: str, name: str, inhalt: bytes) -> dict:
        grenze = "kontor-demodaten-grenze"
        koerper = (f'--{grenze}\r\nContent-Disposition: form-data; name="datei"; filename="{name}"\r\n'
                   "Content-Type: application/pdf\r\n\r\n").encode() + inhalt + f"\r\n--{grenze}--\r\n".encode()
        status, roh = self.roh("POST", pfad, koerper, f"multipart/form-data; boundary={grenze}")
        if status != 201:
            raise DemoFehler(f"POST {pfad} antwortet mit {status}: {roh[:400].decode('utf-8', 'replace')}")
        return json.loads(roh)


def _beleg(u: W.Umsatz) -> bytes:
    """Eine erfundene Rechnung als PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    puffer = io.BytesIO()
    c = canvas.Canvas(puffer, pagesize=A4, invariant=1)
    c.setTitle(f"Beleg {u.name} (Demodaten)")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 770, u.name)
    c.setFont("Helvetica", 11)
    betrag = abs(u.betrag)
    for i, zeile in enumerate((f"Beleg vom {u.datum:%d.%m.%Y}", "Familie Mustermann, Lindenhof 7, 00000 Musterstadt", "",
                               u.zweck, "", f"Betrag: {betrag // 100},{betrag % 100:02d} EUR",
                               "", "Erfundener Beleg – Demodaten von Kontor, kein echtes Dokument.")):
        c.drawString(72, 735 - 18 * i, zeile)
    c.save()
    return puffer.getvalue()


# ------------------------------------------------------------------------------------------------- Aufbau

class _Aufbau:
    def __init__(self, rest: _Rest, w: W.Welt) -> None:
        self.r, self.w = rest, w
        self.ende = w.heute - dt.timedelta(days=VORLAUF_TAGE)
        self.umsatz = {f"bank:{u.iban}:{u.nr}": u for u in w.umsaetze}
        self.konto: dict[str, int] = {}
        self.tag: dict[str, int] = {}
        self.kredit: dict[str, int] = {}
        self.mail_von_paypal = {(m.haendler, m.betrag): m.nr for m in w.mails if m.haendler}
        self.erledigte_jahre: set[int] = set()
        self.belege = 0

    # ---------------------------------------------------------------------------------------- Uhr
    def uhr(self, tag: dt.date, stunde: int = 18) -> None:
        self.r("PUT", "/api/mock/zeit", {"jetzt": f"{tag.isoformat()}T{stunde:02d}:00:00Z"})

    def arbeitsgaenge(self) -> list[dt.date]:
        letzter_voller = self.ende - dt.timedelta(days=OFFEN_TAGE)
        tage, t = [], self.w.start + dt.timedelta(days=ABSTAND_TAGE)
        while t < letzter_voller - dt.timedelta(days=20):
            tage.append(t)
            t += dt.timedelta(days=ABSTAND_TAGE)
        if letzter_voller > self.w.start:
            tage.append(letzter_voller)
        return tage

    # ------------------------------------------------------------------------------------ Stammdaten
    def konto_anlegen(self, schluessel: str, name: str, art: str, **mehr) -> int:
        self.konto[schluessel] = self.r("POST", "/api/konten", {"name": name, "art": art, **mehr})["id"]
        return self.konto[schluessel]

    def tag_id(self, name: str) -> int:
        if name not in self.tag:
            self.tag[name] = self.r("POST", "/api/tags", {"name": name})["id"]
        return self.tag[name]

    def stammdaten(self) -> None:
        r, start = self.r, self.w.start
        vortag = (start - dt.timedelta(days=1)).isoformat()
        self.konto_anlegen("giro", "Girokonto", "girokonto", iban=W.GIRO, eroeffnet_am=vortag,
                           notiz="Gemeinsames Konto bei der Musterbank (Demodaten)")
        self.konto_anlegen("sparbuch", "Sparbuch", "sparkonto", iban=W.SPARBUCH, eroeffnet_am=vortag,
                           notiz="Rücklagen und Urlaubskasse (Demodaten)")
        self.konto_anlegen("wohnung", W.WOHNUNG["name"], "kreditkonto")
        self.konto_anlegen("auto", W.AUTO["name"], "kreditkonto")
        for art, pfade in (("aufwand", W.AUFWAND), ("ertrag", W.ERTRAG)):
            for pfad in pfade:
                ober, _, unter = pfad.rpartition(":")
                self.konto_anlegen(pfad, unter, art, eltern_id=self.konto[ober] if ober else None)
        anfang = self.konto_anlegen("anfang", "Anfangsbestand", "eigenkapital")
        for schluessel, betrag in (("giro", W.ANFANG_GIRO), ("sparbuch", W.ANFANG_SPARBUCH)):
            r("POST", "/api/buchungen", {"datum": vortag, "verwendungszweck": "Anfangsbestand", "status": "bestaetigt",
                                         "splits": [{"konto_id": self.konto[schluessel], "betrag": betrag},
                                                    {"konto_id": anfang, "betrag": -betrag}]})
        r("POST", "/api/empfaenger", {"name": "Supermarkt Frischekorb", "aliase": [W.FRISCHEKORB_ALIAS]})
        for adresse, name in zip(W.POSTFAECHER, ("Erika", "Max")):
            r("POST", "/api/mail/postfaecher", {"adresse": adresse, "bezeichnung": f"Postfach {name}"})
        self.regeln()
        self.kredite()

    def regeln(self) -> None:
        r, k = self.r, self.konto
        auto = self.tag_id("Auto")
        for name, ausdruck, kategorie, tags in (
                ("Supermärkte und Bäcker",
                 'empfänger in ["Supermarkt Frischekorb", "Discounter Preisfuchs", "Biomarkt Grünkern", '
                 '"Bäckerei Kornblume"]', "Lebensmittel", []),
                ("Gehalt und Bezüge", 'richtung == "einnahme" and ("GEHALT" in verwendungszweck or '
                                      '"BEZUEGE" in verwendungszweck)', "Einkommen:Gehalt", []),
                ("Tanken", '"Tankstelle" in empfänger', "Mobilität:Tanken", [auto]),
                ("Streaming und Abos", 'empfänger in ["Filmkiste Streaming", "Musikstrom", "Morgenpost Verlag"]',
                 "Freizeit", []),
                ("Hausgeld", '"HAUSGELD" in verwendungszweck', "Wohnen:Nebenkosten", []),
                ("Kfz-Versicherung", '"KFZ-VERSICHERUNG" in verwendungszweck', "Versicherungen & Gesundheit", [auto]),
                ("Restaurant am Wochenende", 'wochentag in ["sa", "so"] and empfänger in ["Trattoria Bella Vista", '
                                             '"Sushi Hanami", "Burgerwerk Musterstadt"]', "Freizeit:Restaurant", [])):
            r("POST", "/api/regeln", {"name": name, "ausdruck": ausdruck, "kategorie_id": k[kategorie],
                                      "tag_ids": tags})
        # Regel ohne Kategorie: vergibt nur ein Tag
        r("POST", "/api/regeln", {"name": "Große Ausgaben markieren", "ausdruck": 'richtung == "ausgabe" and betrag >= 500',
                                  "tag_ids": [self.tag_id("Große Ausgabe")]})
        r("POST", "/api/vorlagen", {
            "name": "Stadtwerke: Abschlag aufteilen",
            "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": W.STADTWERKE},
                            {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "ABSCHLAG"}],
            "teile": [{"kategorie_id": k[pfad], "betrag": betrag, "memo": memo}
                      for pfad, betrag, memo in W.ABSCHLAG_TEILE]})

    def kredite(self) -> None:
        start = self.w.start
        sonder = W.sondertilgung_monat(self.w)
        for schluessel, k in (("wohnung", W.WOHNUNG), ("auto", W.AUTO)):
            self.kredit[schluessel] = self.r("POST", "/api/kredite", {
                "name": k["name"], "konto_id": self.konto[schluessel], "zahlungskonto_id": self.konto["giro"],
                "zins_konto_id": self.konto["Zinsen"], "restschuld": k["restschuld"],
                "stand_datum": (start - dt.timedelta(days=1)).isoformat(), "sollzins": k["sollzins"],
                "rate": k["rate"], "erste_faelligkeit": start.replace(day=k["tag"]).isoformat(),
                "sondertilgungen": ([{"datum": dt.date(sonder[0], sonder[1], 10).isoformat(),
                                      "betrag": W.SONDERTILGUNG}] if sonder and schluessel == "wohnung" else []),
                "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": k["bank"]},
                                {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "RATE"}]})["id"]

    # --------------------------------------------------------------------------------------- Abrufe
    def abrufen(self, von: dt.date | None = None) -> None:
        lauf = self.r("POST", "/api/sync", {"von": von.isoformat()} if von else {})
        if lauf["status"] != "erfolgreich":
            raise DemoFehler(f"Der Kontoabruf ist nicht gelungen: {lauf['status']} {lauf.get('fehler')}")
        abruf = self.r("POST", "/api/mail/abruf")
        if any(p["status"] != "erfolgreich" for p in abruf["postfaecher"]):
            raise DemoFehler("Der Mail-Abruf ist nicht gelungen.")

    # --------------------------------------------------------------------------------- Nacharbeiten
    def offene(self) -> list[tuple[dict, W.Umsatz]]:
        aus = []
        for b in self.r.seiten("/api/buchungen?status=importiert&status=vorlaeufig"):
            u = next((self.umsatz[x] for x in b["extern_ids"] if x in self.umsatz), None)
            if u is not None:
                aus.append((b, u))
        return aus

    def nacharbeiten(self) -> None:
        """Was ein Anwender nach einem Abruf tut: zuordnen, Tags vergeben, Belege anhängen, bestätigen."""
        r, k = self.r, self.konto
        nach_kategorie: dict[int, list[int]] = {}
        nach_tag: dict[int, list[int]] = {}
        fertig: list[int] = []
        mails = None
        for b, u in self.offene():
            bid = b["id"]
            if u.merkmal == "abschlag" and len(b["splits"]) < 3:
                continue      # der Abschlag passt nicht mehr zur Vorlage: bleibt zum Vorführen liegen
            if u.merkmal == "sondertilgung":
                r("PUT", f"/api/buchungen/{bid}/kategorie", {"kategorie_id": k["wohnung"], "konto_id": k["giro"]})
            elif u.kategorie is not None and b["kategorie_id"] != k[u.kategorie]:
                nach_kategorie.setdefault(k[u.kategorie], []).append(bid)
            vorhanden = {t["name"] for t in b["tags"]}
            for name in u.tags:
                if name not in vorhanden:
                    nach_tag.setdefault(self.tag_id(name), []).append(bid)
            if u.merkmal == "beleg":
                r.hochladen(f"/api/dokumente?buchung_id={bid}", f"Beleg {u.name} {u.datum.isoformat()}.pdf", _beleg(u))
                self.belege += 1
            if u.merkmal == "paypal" and bid % 2 == 0:
                if mails is None:
                    mails = {m["nachricht_id"]: m["id"] for m in r.seiten("/api/mail/nachrichten")}
                haendler = u.zweck.rpartition("Ihr Einkauf bei ")[2]
                nid = mails.get(self.mail_von_paypal.get((haendler, -u.betrag)))
                if nid is not None:
                    r("POST", f"/api/mail/nachrichten/{nid}/buchung", {"buchung_id": bid})
            fertig.append(bid)
            person = W_PERSONEN[bid % 3 == 0]
            nach_tag.setdefault(self.tag_id(person), []).append(bid)
        for kategorie_id, ids in nach_kategorie.items():
            r("POST", "/api/buchungen/mehrfach/kategorie", {"buchung_ids": ids, "kategorie_id": kategorie_id})
        for tag_id, ids in nach_tag.items():
            r("POST", "/api/buchungen/mehrfach/tags", {"buchung_ids": ids, "hinzufuegen": [tag_id]})
        if fertig:
            r("POST", "/api/buchungen/mehrfach/aendern", {"buchung_ids": fertig, "status": "bestaetigt"})
        for n in r("GET", "/api/benachrichtigungen"):
            if not n.get("gelesen_am") and not n.get("gelesen"):
                r("POST", f"/api/benachrichtigungen/{n['id']}/gelesen")

    def jahresabschluss(self, tag: dt.date) -> None:
        """Im neuen Jahr: Jahresabgleich der Kredite und Abstimmung der Konten zum 31.12. des Vorjahres."""
        r = self.r
        for jahr in range(self.w.start.year, tag.year):
            if jahr in self.erledigte_jahre or tag < dt.date(jahr + 1, 1, 20):
                continue
            self.erledigte_jahre.add(jahr)
            for schluessel, zuschlag in (("wohnung", ZINSKORREKTUR), ("auto", 0)):
                kid = self.kredit[schluessel]
                probe = r("POST", f"/api/kredite/{kid}/jahresabgleich",
                          {"jahr": jahr, "restschuld": 0, "zinsen": 0, "trocken": True})
                r("POST", f"/api/kredite/{kid}/jahresabgleich",
                  {"jahr": jahr, "restschuld": probe["restschuld_berechnet"] + zuschlag,
                   "zinsen": probe["zinsen_berechnet"] + zuschlag})
            stichtag = f"{jahr}-12-31"
            for schluessel in ("giro", "sparbuch"):
                probe = r("POST", "/api/abstimmungen", {"konto_id": self.konto[schluessel], "stichtag": stichtag,
                                                        "saldo": 0, "trocken": True})
                r("POST", "/api/abstimmungen", {"konto_id": self.konto[schluessel], "stichtag": stichtag,
                                                "saldo": probe["berechneter_saldo"]})
            ids = [b["id"] for b in r.seiten(f"/api/buchungen?status=bestaetigt&bis={stichtag}")]
            if ids:
                r("POST", "/api/buchungen/mehrfach/aendern", {"buchung_ids": ids, "status": "abgeglichen"})

    # ------------------------------------------------------------------------------------- Schluss
    def von_hand_erfasst(self) -> None:
        """Eine von Hand notierte Ausgabe, die der nächste Abruf noch einmal von der Bank bringt: Dublettenverdacht."""
        grenze = self.ende - dt.timedelta(days=OFFEN_TAGE)
        u = next((u for u in self.w.umsaetze if grenze + dt.timedelta(days=2) < u.datum <= self.ende
                  and u.kategorie == "Freizeit:Restaurant"), None)
        if u is None:
            return
        self.r("POST", "/api/buchungen/erfassen", {
            "art": "ausgabe", "datum": (u.datum - dt.timedelta(days=1)).isoformat(), "konto_id": self.konto["giro"],
            "betrag": -u.betrag, "kategorie_id": self.konto["Freizeit:Restaurant"],
            "empfaenger_name": "Abendessen mit Freunden", "verwendungszweck": "mit Karte bezahlt, von Hand notiert",
            "status": "vorlaeufig"})

    def geplant(self) -> None:
        h = self.w.heute

        def tag(n: int) -> str:
            return (h + dt.timedelta(days=n)).isoformat()
        for d in ({"richtung": "ausgabe", "haendler": "Hauptzollamt Musterstadt", "betrag": 9_600, "datum": tag(12),
                   "beschreibung": "Kfz-Steuer M-US 4711", "wiederholung": "jaehrlich"},
                  {"richtung": "ausgabe", "haendler": "Malerbetrieb Farbenfroh", "betrag": 48_000, "datum": tag(20),
                   "beschreibung": "Flur streichen, Angebot 2026-118"},
                  {"richtung": "ausgabe", "haendler": "Musikschule Taktvoll", "betrag": 6_200, "datum": tag(6),
                   "beschreibung": "Klavierunterricht", "wiederholung": "monatlich"},
                  {"richtung": "eingang", "haendler": "Krankenkasse Gesundbund", "betrag": 8_450, "datum": tag(-9),
                   "beschreibung": "Erstattung Zahnreinigung (überfällig)"}):
            self.r("POST", "/api/erwartungen", d)

    # ---------------------------------------------------------------------------------------- alles
    def alles(self) -> None:
        self.uhr(self.w.start, 9)
        self.stammdaten()
        erster = True
        for t in self.arbeitsgaenge():
            self.uhr(t)
            self.abrufen(self.w.start if erster else None)
            erster = False
            self.uhr(t, 20)
            self.nacharbeiten()
            self.jahresabschluss(t)
        self.uhr(self.ende, 7)
        self.von_hand_erfasst()
        self.abrufen(self.w.start if erster else None)
        self.geplant()

    def bericht(self) -> dict:
        r = self.r
        konten = r("GET", "/api/konten")
        return {"heute": self.w.heute.isoformat(), "von": self.w.start.isoformat(), "bis": self.ende.isoformat(),
                "buchungen": r("GET", "/api/buchungen?pro_seite=1")["gesamt"],
                "mails": r("GET", "/api/mail/nachrichten?pro_seite=1")["gesamt"],
                "kategorien": sum(1 for x in konten if x["art"] in ("aufwand", "ertrag") and not x["extern_id"]),
                "kredite": len(r("GET", "/api/kredite")), "regeln": len(r("GET", "/api/regeln")),
                "belege": self.belege}


def _personen() -> tuple[str, str]:
    from .pflege import PERSONEN, personentag
    return personentag(PERSONEN[0]), personentag(PERSONEN[1])


W_PERSONEN = _personen()


def _weg(datenbank: pathlib.Path) -> None:
    for endung in ("", "-wal", "-shm", "-journal"):
        with contextlib.suppress(FileNotFoundError):
            datenbank.with_name(datenbank.name + endung).unlink()


def aufbauen(datenbank: pathlib.Path, mock_datei: pathlib.Path, heute: dt.date | None = None,
             monate: int = MONATE) -> dict:
    """Mock-Datendatei schreiben und die Mock-Datenbank neu aufbauen (eine vorhandene wird ersetzt)."""
    from . import db
    from .app import create_app

    datenbank, mock_datei = pathlib.Path(datenbank), pathlib.Path(mock_datei)
    heute = heute or dt.date.today()
    w = W.welt(heute, monate)
    datenbank.parent.mkdir(parents=True, exist_ok=True)
    mock_datei.parent.mkdir(parents=True, exist_ok=True)
    neu = mock_datei.with_name(mock_datei.name + ".neu")
    neu.write_text(json.dumps(w.mock_daten(), ensure_ascii=False), encoding="utf-8")
    os.replace(neu, mock_datei)
    os.chmod(mock_datei, 0o600)
    _weg(datenbank)
    # Beim Aufbau reicht der erste Mail-Abruf über den ganzen ersten Arbeitsgang zurück
    config = konfiguration(datenbank, mock_datei, mail_erstabruf_tage=ABSTAND_TAGE + 31)
    rest = _Rest(create_app(config))
    try:
        aufbau = _Aufbau(rest, w)
        aufbau.alles()
        bericht = aufbau.bericht()
    finally:
        rest.schliessen()
    db.checkpoint(datenbank)
    os.chmod(datenbank, 0o600)
    return bericht


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m kontor.demodaten",
                                description="Baut eine Mock-Datenbank mit einem erfundenen Haushalt (Vorführung).")
    p.add_argument("datenbank", type=pathlib.Path, help="Mock-Datenbank, die neu entsteht (eine vorhandene wird ersetzt)")
    p.add_argument("mock_datei", type=pathlib.Path, help="Mock-Datendatei für Bank und Postfächer (wird geschrieben)")
    p.add_argument("--heute", type=dt.date.fromisoformat, default=None, help="Bezugstag JJJJ-MM-TT (Vorgabe: heute)")
    p.add_argument("--monate", type=int, default=MONATE, help=f"Zeitraum in Monaten (Vorgabe {MONATE})")
    args = p.parse_args(argv)
    try:
        b = aufbauen(args.datenbank, args.mock_datei, args.heute, args.monate)
    except (DemoFehler, ValueError, OSError) as fehler:
        print(f"Die Demodaten ließen sich nicht aufbauen: {fehler}", file=sys.stderr)
        return 1
    print(f"Demodaten vom {b['von']} bis {b['bis']}: {b['buchungen']} Buchungen, {b['mails']} Mails, "
          f"{b['kategorien']} Kategorien, {b['kredite']} Kredite, {b['regeln']} Regeln, {b['belege']} Belege.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
