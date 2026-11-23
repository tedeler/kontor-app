"""Hilfen für Meilenstein-7-Tests (Anmeldung, Härtung, Betrieb) – nur über die Spezifikation.

``sicherheit.md``, ``betrieb.md``, ``leistung.md``, ``python-api.md`` 14.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.resources
import re
import unicodedata
from http.cookies import SimpleCookie
from pathlib import Path

from . import kontor
from .api import Api, fehlercode, neue_config

#: synthetisches Testpasswort (kein Geheimnis, nur für Tests)
PASSWORT = "Kontor-Testhaushalt-0815"
NEUES_PASSWORT = "Neues-Testpasswort-4711!"
CSRF = "X-Kontor-CSRF"
COOKIE = "kontor_sitzung"
OEFFENTLICH = {("get", "/api/anmeldung"), ("post", "/api/anmeldung"), ("post", "/api/anmeldung/einrichten"),
               ("get", "/api/gesundheit")}
HASH_MUSTER = re.compile(r"^scrypt\$([1-9][0-9]*)\$([1-9][0-9]*)\$([1-9][0-9]*)\$([A-Za-z0-9+/=]+)\$([A-Za-z0-9+/=]+)$")


def anmeldung():
    return kontor.modul("kontor.anmeldung")


def m7_config(basis: Path, *, passwort: str | None = PASSWORT, **felder):
    """Konfiguration mit eingeschalteter Anmeldung; mit ``passwort`` gleich eingerichtet."""
    felder.setdefault("anmeldung", True)
    config = neue_config(basis, **felder)
    if passwort is not None:
        anmeldung().passwort_setzen(config, passwort)
    return config


def m7_api(basis: Path, *, passwort: str | None = PASSWORT, client_kw: dict | None = None, **felder) -> Api:
    return Api(m7_config(basis, passwort=passwort, **felder), **(client_kw or {}))


def anmelden(api: Api, passwort: str = PASSWORT, *, erwartet: int = 200, **kw):
    """POST /api/anmeldung; bei Erfolg merkt sich die Api das CSRF-Token."""
    r = api.post("/api/anmeldung", json={"passwort": passwort}, erwartet=erwartet, **kw)
    if r.status_code == 200:
        api.csrf = r.daten["csrf_token"]
    return r


def angemeldet(basis: Path, **felder) -> Api:
    api = m7_api(basis, **felder)
    anmelden(api)
    return api


def zweiter_client(api: Api, **client_kw) -> Api:
    """Weitere Api auf derselben App (eigenes Cookie-Glas), ohne Sitzung."""
    from fastapi.testclient import TestClient

    neu = Api.__new__(Api)
    neu.config, neu.app, neu.modus_erwartet, neu.csrf = api.config, api.app, api.modus_erwartet, None
    neu.client = TestClient(api.app, raise_server_exceptions=False, **client_kw)
    return neu


def set_cookie(r) -> SimpleCookie | None:
    """Das Cookie ``kontor_sitzung`` aus den Set-Cookie-Köpfen (oder None)."""
    for kopf in r.headers.get_list("set-cookie"):
        c = SimpleCookie()
        c.load(kopf)
        if COOKIE in c:
            return c
    return None


def set_cookie_roh(r) -> str | None:
    for kopf in r.headers.get_list("set-cookie"):
        if kopf.split("=", 1)[0].strip() == COOKIE:
            return kopf
    return None


def cookie_attribute(kopf: str) -> dict[str, str | bool]:
    teile = [t.strip() for t in kopf.split(";")]
    aus: dict[str, str | bool] = {}
    for t in teile[1:]:
        if "=" in t:
            k, v = t.split("=", 1)
            aus[k.strip().lower()] = v.strip()
        elif t:
            aus[t.lower()] = True
    return aus


def sitzungstoken(api: Api) -> str | None:
    werte = [c.value for c in api.client.cookies.jar if c.name == COOKIE and c.value]
    return werte[-1] if werte else None


def unabhaengig_pruefen(passwort: str, text: str) -> bool:
    """sicherheit.md 2.2 unabhängig nachgerechnet."""
    m = HASH_MUSTER.match(text)
    if not m:
        return False
    n, r, p = (int(m[i]) for i in (1, 2, 3))
    salz, schluessel = base64.b64decode(m[4]), base64.b64decode(m[5])
    ist = hashlib.scrypt(unicodedata.normalize("NFC", passwort).encode("utf-8"), salt=salz, n=n, r=r, p=p,
                         maxmem=64 * 1024 * 1024, dklen=len(schluessel))
    return hmac.compare_digest(ist, schluessel)


def eigener_hash(passwort: str, *, n: int = 2 ** 14, r: int = 8, p: int = 1, salz: bytes = b"0123456789abcdef") -> str:
    k = hashlib.scrypt(unicodedata.normalize("NFC", passwort).encode("utf-8"), salt=salz, n=n, r=r, p=p,
                       maxmem=64 * 1024 * 1024, dklen=32)
    return f"scrypt${n}${r}${p}${base64.b64encode(salz).decode()}${base64.b64encode(k).decode()}"


def einrichtungsdatei(config) -> Path:
    db = Path(config.aktive_datenbank)
    return db.with_name(db.name + ".einrichtung")


def betriebsdatei(name: str) -> str:
    return importlib.resources.files("kontor.betrieb").joinpath(name).read_text(encoding="utf-8")


def alle_dateibytes(verzeichnis: Path) -> bytes:
    return b"".join(p.read_bytes() for p in sorted(Path(verzeichnis).rglob("*")) if p.is_file())


def csp(kopf: str) -> dict[str, list[str]]:
    aus: dict[str, list[str]] = {}
    for teil in kopf.split(";"):
        w = teil.split()
        if w:
            aus[w[0].lower()] = w[1:]
    return aus


__all__ = ["PASSWORT", "NEUES_PASSWORT", "CSRF", "COOKIE", "OEFFENTLICH", "HASH_MUSTER", "anmeldung", "m7_config",
           "m7_api", "anmelden", "angemeldet", "zweiter_client", "set_cookie", "set_cookie_roh", "cookie_attribute",
           "sitzungstoken", "unabhaengig_pruefen", "eigener_hash", "einrichtungsdatei", "betriebsdatei",
           "alle_dateibytes", "csp", "fehlercode"]
