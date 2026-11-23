"""Hilfen für Meilenstein-6-Tests (echte Anbindungen gegen lokale Attrappen) – nur über die Spezifikation."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import kontor
from .api import Api, fehlercode, neue_config
from .m2 import db_dateien
from .m3 import aenderungen_seit, letzte_aenderung_id
from .m5 import bestand as bestand_m5
from .pfade import FIXTURES, MOCK

M6 = FIXTURES / "m6"
FINTS_DATEN = M6 / "fints_bank.json"
FINTS_VERGLEICH = MOCK / "m6_fints_vergleich.json"
MAIL_VERGLEICH = MOCK / "m6_mail_vergleich.json"
PRODUKT = "KONTOR-TEST-PRODUKT"
THEMA = "kontor-test-THEMA"
CLIENT_ID = "SYNTH-CLIENT-ID.apps.example.invalid"
CLIENT_SECRET = "SYNTH-CLIENT-SECRET-7f3a9c"
NTFY_TOKEN = "SYNTH-NTFY-TOKEN-b41d"
REDIRECT = "http://127.0.0.1/oauth2/rueckruf"
EINS = "haushalt.eins@example.invalid"
ZWEI = "haushalt.zwei@example.invalid"
UTC = dt.timezone.utc
OBJEKTE_M6 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage", "kredit",
              "postfach"]
VON, BIS = dt.date(2023, 12, 1), dt.date(2024, 7, 31)


def lade(pfad: Path) -> dict:
    return json.loads(Path(pfad).read_text(encoding="utf-8"))


def fints_daten() -> tuple[dict, dict]:
    return lade(FINTS_DATEN), lade(M6 / "fints_bank.erwartung.json")


def mail_erwartung() -> dict:
    return lade(M6 / "mail.erwartung.json")


def giro(erw: dict) -> str:
    return next(k["iban"] for k in erw["konten"] if k["art"] == "girokonto")


def zeit(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def zs(d: dt.datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def jetzt() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


# ------------------------------------------------------------------ Konfiguration
def fints_felder(attrappe, daten: dict, **extra) -> dict:
    f = {"bank_plugin": "fints", "fints_url": attrappe.url, "fints_blz": daten["blz"],
         "fints_benutzer": daten["benutzer"], "fints_produkt_id": PRODUKT, "fints_timeout_sekunden": 10}
    f.update(extra)
    return f


def mail_felder(imap=None, oauth=None, **extra) -> dict:
    f: dict = {"mail_plugin": "imap"}
    if imap is not None:
        f.update(imap_host="127.0.0.1", imap_port=imap.port, imap_tls=imap.tls is not None, imap_timeout_sekunden=10)
    if oauth is not None:
        f.update(oauth_client_id=CLIENT_ID, oauth_autorisierung_url=oauth.autorisierung_url,
                 oauth_token_url=oauth.token_url, oauth_widerruf_url=oauth.widerruf_url, oauth_redirect_uri=REDIRECT,
                 oauth_timeout_sekunden=10)
    f.update(extra)
    return f


def ntfy_felder(ntfy, **extra) -> dict:
    f = {"benachrichtigung_plugin": "ntfy", "ntfy_url": ntfy.url, "ntfy_topic": THEMA, "ntfy_timeout_sekunden": 5}
    f.update(extra)
    return f


def echt_api(basis: Path, **felder) -> Api:
    return Api(neue_config(basis, **felder))


def config(basis: Path, **felder):
    return neue_config(basis, **felder)


# ------------------------------------------------------------------ REST-Kurzformen
def pin_setzen(api: Api, pin: str) -> None:
    api.put("/api/sync/pin", json={"pin": pin}, erwartet=204)


def sync(api: Api, **body) -> dict:
    return api.post("/api/sync", json=body, erwartet=200).daten


def tan_antwort(api: Api, tan_id: int, tan: str, erwartet=200):
    return api.post(f"/api/tan-anforderungen/{tan_id}/antwort", json={"tan": tan}, erwartet=erwartet)


def benachrichtigungen(api: Api, **params) -> list[dict]:
    p = {k: ("true" if v else "false") if isinstance(v, bool) else v for k, v in params.items()}
    return api.get("/api/benachrichtigungen", params=p or None, erwartet=200).daten


def zustellung(api: Api) -> dict:
    return api.get("/api/benachrichtigungen/zustellung", erwartet=200).daten


def geheimnis_setzen(api: Api, name: str, wert: str) -> None:
    api.put(f"/api/geheimnisse/{name}", json={"wert": wert}, erwartet=204)


def geheimnisse(api: Api) -> dict:
    return api.get("/api/geheimnisse", erwartet=200).daten


def postfach(api: Api, adresse: str, **felder) -> dict:
    return api.post("/api/mail/postfaecher", json={"adresse": adresse, **felder}, erwartet=201).daten


def postfach_status(api: Api, pid: int) -> dict:
    return api.get(f"/api/mail/postfaecher/{pid}/status", erwartet=200).daten


def abruf(api: Api) -> dict:
    return api.post("/api/mail/abruf", erwartet=200).daten


def nachrichten(api: Api, **params) -> list[dict]:
    aus, seite = [], 1
    while True:
        d = api.get("/api/mail/nachrichten", params={**params, "seite": seite, "pro_seite": 500}, erwartet=200).daten
        aus.extend(d["eintraege"])
        if len(aus) >= d["gesamt"] or not d["eintraege"]:
            return aus
        seite += 1


def anmelden(api: Api, oauth, pid: int, *, adresse: str | None = None) -> dict:
    """Anmeldung über die OAuth-Attrappe: Start, Zustimmung „im Browser“, Abschluss mit der Umleitungs-URL."""
    start = api.post(f"/api/mail/postfaecher/{pid}/anmeldung", erwartet=200).daten
    antwort = oauth.genehmige(start["autorisierung_url"], adresse=adresse)
    return api.post("/api/mail/anmeldung/abschluss", json={"antwort_url": antwort}, erwartet=200).daten


def url_parameter(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}


# ------------------------------------------------------------------ Geheimnisse nirgends
def geheimnisse_nirgends(api: Api, werte: list[str], *, texte: list[str] = (), caplog=None, capfd=None) -> None:
    """geheimnisse.md 6: kein Wert in DB-Dateien, Logs, Antworten, Benachrichtigungen, Zustellungen."""
    werte = [w for w in werte if w]
    pruef = list(texte)
    for pfad in ("/api/status", "/api/sync/status", "/api/sync/laeufe", "/api/tan-anforderungen",
                 "/api/benachrichtigungen", "/api/benachrichtigungen/zustellung", "/api/geheimnisse",
                 "/api/mail/postfaecher", "/api/aenderungen"):
        pruef.append(api.get(pfad, erwartet=200).text)
    for p in api.get("/api/mail/postfaecher", erwartet=200).daten:
        pruef.append(api.get(f"/api/mail/postfaecher/{p['id']}/status", erwartet=200).text)
    pruef.append(api.get("/api/mail/nachrichten", erwartet=200).text)
    if capfd is not None:
        raus, err = capfd.readouterr()
        pruef += [raus, err]
    if caplog is not None:
        pruef.append(caplog.text)
        pruef += [r.getMessage() for r in caplog.records]
        pruef += [repr(r.args) for r in caplog.records]
    pruef.append(repr(api.config))
    for w in werte:
        for t in pruef:
            assert w not in t, f"Geheimnis im Klartext gefunden: …{t[max(0, t.find(w) - 80):t.find(w) + 80]}…"
        for datei in db_dateien(api):
            inhalt = datei.read_bytes()
            for kodierung in ("utf-8", "utf-16-le", "utf-16-be"):
                assert w.encode(kodierung) not in inhalt, f"Geheimnis im Klartext in {datei.name}"


def alles_protokollieren(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    for name in ("", "fints", "urllib3", "httpx", "httpcore", "requests", "imaplib", "kontor"):
        logging.getLogger(name).setLevel(logging.DEBUG)


# ------------------------------------------------------------------ Bestand und Protokoll (mit Postfächern)
def bestand(api: Api) -> dict[tuple[str, int], dict]:
    aus = bestand_m5(api)
    for p in api.get("/api/mail/postfaecher", erwartet=200).daten:
        aus[("postfach", p["id"])] = p
    return aus


def sortierschluessel(e: dict) -> tuple[int, int]:
    return OBJEKTE_M6.index(e["objekt"]), e["objekt_id"]


def pruefe_eintraege(a: dict, vorher: dict, nachher: dict) -> None:
    erwartet = {k: (vorher.get(k), nachher.get(k)) for k in set(vorher) | set(nachher)
                if vorher.get(k) != nachher.get(k)}
    ist = {(e["objekt"], e["objekt_id"]): e for e in a["eintraege"]}
    assert len(ist) == len(a["eintraege"]) and set(ist) == set(erwartet), (sorted(ist), sorted(erwartet))
    for k, (v, n) in erwartet.items():
        e = ist[k]
        assert e["art"] == ("angelegt" if v is None else "geloescht" if n is None else "geaendert"), k
        assert (e["vorher"], e["nachher"]) == (v, n), k
    assert a["eintraege"] == sorted(a["eintraege"], key=sortierschluessel)


def eine_aenderung(api: Api, a0: int, aktion: str) -> dict:
    neu = aenderungen_seit(api, a0)
    assert [(x["quelle"], x["aktion"], x["gruppe"]) for x in neu] == [("manuell", aktion, None)], neu
    return neu[0]


def rundreise(api: Api, a: dict, vorher: dict, nachher: dict) -> None:
    u = api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(api) == vorher
    pruefe_eintraege(u, nachher, vorher)
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == nachher


def fehler(r) -> str:
    return fehlercode(r)


def plugins():
    return kontor.plugins()


def modul(name: str):
    return kontor.modul(name)


__all__ = ["aenderungen_seit", "letzte_aenderung_id", "fehlercode"]
