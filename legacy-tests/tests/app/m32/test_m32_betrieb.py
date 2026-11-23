"""M32: Konfiguration ansehen und Betrieb hinter HTTPS (sammel3.md 11, 15; betrieb.md 10; D-235, D-239; E-304,
E-305) – kern. Die Skripte werden nie ausgeführt (root, systemd, Tailscale)."""

from __future__ import annotations

import logging
import re

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api, fehlercode, neue_api
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m7 import angemeldet, betriebsdatei, m7_config
from tests.hilfen.systemd import umgebungsdatei

pytestmark = pytest.mark.kern
GEHEIM = {"KONTOR_FINTS_BENUTZER": "SYNTH-GEHEIM-NUTZER-4711", "KONTOR_FINTS_KUNDEN_ID": "SYNTH-GEHEIM-KUNDE-4711",
          "KONTOR_NTFY_TOKEN": "tk_synth_geheim_4711", "KONTOR_OAUTH_CLIENT_SECRET": "synth-secret-4711",
          "KONTOR_PASSWORT": "synth-passwort-4711"}
OFFEN = {"KONTOR_LOG_STUFE": "INFO", "KONTOR_OAUTH_TOKEN_URL": "https://oauth.example.invalid/token",
         "KONTOR_BANK_PIN_QUELLE": "abfrage"}
UNBEKANNT = "KONTOR_UNSINN_M32"


@pytest.fixture
def konfiguration(tmp_path, monkeypatch):
    for k, v in {**GEHEIM, **OFFEN, UNBEKANNT: "ja", "M32_FREMDE_VARIABLE": "fremd-4711",
                 "CREDENTIALS_DIRECTORY": str(tmp_path / "creds")}.items():
        monkeypatch.setenv(k, v)
    api = neue_api(tmp_path / "k", mail_abgleich=True, anbieter_verzeichnis=tmp_path / "anbieter")
    r = api.get("/api/konfiguration", erwartet=200)
    return api, r


def test_umgebung(konfiguration):
    _, r = konfiguration
    u = {x["variable"]: x for x in r.daten["umgebung"]}
    assert len(u) == len(r.daten["umgebung"]), "je Variable ein Eintrag"
    assert all(v.startswith("KONTOR_") or v == "CREDENTIALS_DIRECTORY" for v in u), sorted(u)
    assert "M32_FREMDE_VARIABLE" not in u and "fremd-4711" not in r.text, "andere Variablen erscheinen nicht"
    assert "CREDENTIALS_DIRECTORY" in u
    for k in GEHEIM:
        assert u[k]["verborgen"] is True, k
    for k, v in OFFEN.items():
        assert u[k]["verborgen"] is False and u[k]["bekannt"] is True and v in str(u[k]["wert"]), k
    assert u[UNBEKANNT]["bekannt"] is False and u[UNBEKANNT]["verborgen"] is False
    for v in GEHEIM.values():
        assert v not in r.text, "geheime Werte erscheinen nirgends"


def test_wirksam(konfiguration):
    _, r = konfiguration
    w = {x["name"]: x for x in r.daten["wirksam"]}
    assert len(w) == len(r.daten["wirksam"])
    for name in ("mail_abgleich", "regeln_automatisch", "anbieter_verzeichnis", "mail_bestellnummer"):
        assert w[name]["variable"] == "KONTOR_" + name.upper(), name
    assert w["mail_abgleich"]["geaendert"] is True and w["anbieter_verzeichnis"]["geaendert"] is True
    assert w["regeln_automatisch"]["geaendert"] is False
    assert w["regeln_automatisch"]["gesetzt"] is False, "KONTOR_REGELN_AUTOMATISCH steht nicht in der Umgebung"
    for name in ("fints_benutzer", "fints_kunden_id", "ntfy_token"):
        if name in w:
            assert w[name]["verborgen"] is True, name
    assert w["log_stufe"]["gesetzt"] is True and w["log_stufe"]["verborgen"] is False


def test_nur_lesend_und_geschuetzt(tmp_path):
    api = neue_api(tmp_path / "a")
    a0 = letzte_aenderung_id(api)
    api.get("/api/konfiguration", erwartet=200)
    assert aenderungen_seit(api, a0) == []
    geschuetzt = Api(m7_config(tmp_path / "b"))
    assert fehlercode(geschuetzt.get("/api/konfiguration", erwartet=401)) == "nicht_angemeldet"


# ------------------------------------------------------------------ 15 HTTPS


def _ohne_kommentare(text: str) -> str:
    return "\n".join(z for z in text.splitlines() if not z.lstrip().startswith("#"))


def test_skript_kontor_https_ausgeliefert():
    t = betriebsdatei("kontor-https.sh")
    assert t.startswith("#!"), "ausführbares Skript"
    for wort in ("einrichten", "status", "zurueck", "--tailscale-installieren", "--name", "--test-port",
                 "KONTOR_OEFFENTLICHE_URL", "KONTOR_SITZUNG_COOKIE_SECURE", "KONTOR_HOST"):
        assert wort in t, wort
    for name in ("kontor-https.sh", "kontor-test.sh"):
        assert not re.search(r"\bfunnel\b", _ohne_kommentare(betriebsdatei(name))), f"{name}: nie tailscale funnel"


def test_ausgelieferte_umgebungsdatei_bleibt_offen():
    werte, _ = umgebungsdatei(betriebsdatei("kontor.env"))
    assert werte.get("KONTOR_HOST") == "0.0.0.0"


def _kontor_warnungen(caplog, config) -> list[str]:
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        kontor.create_app(config)
    return [r.getMessage() for r in caplog.records if r.name.startswith("kontor") and r.levelno >= logging.WARNING]


def test_warnung_secure_cookie_ohne_oeffentliche_adresse(tmp_path, caplog):
    ohne = _kontor_warnungen(caplog, m7_config(tmp_path / "a", sitzung_cookie_secure=True))
    mit = _kontor_warnungen(caplog, m7_config(tmp_path / "b", sitzung_cookie_secure=True,
                                              oeffentliche_url="https://kontor.example.invalid"))
    unsicher = _kontor_warnungen(caplog, m7_config(tmp_path / "c"))
    assert len(ohne) > len(mit), (ohne, mit)
    assert len(mit) == len(unsicher), "ohne Secure-Cookie keine zusätzliche Warnung"


def test_herkunft_hinter_tls_proxy(tmp_path):
    """Kontor sieht http auf Loopback, der Browser meldet die https-Herkunft (sammel3.md 15, sicherheit.md 4.6)."""
    api = angemeldet(tmp_path / "a", oeffentliche_url="https://kontor.example.invalid")
    api.post("/api/konten", json={"name": "A", "art": "girokonto"},
             headers={"origin": "https://kontor.example.invalid"}, erwartet=201)
    r = api.post("/api/konten", json={"name": "B", "art": "girokonto"},
                 headers={"origin": "https://andere.example.invalid"}, erwartet=403)
    assert fehlercode(r) == "csrf_ungueltig"
    ohne = angemeldet(tmp_path / "b")
    r = ohne.post("/api/konten", json={"name": "C", "art": "girokonto"},
                  headers={"origin": "https://kontor.example.invalid"}, erwartet=403)
    assert fehlercode(r) == "csrf_ungueltig", "ohne oeffentliche_url wird die https-Herkunft abgelehnt"


@pytest.mark.parametrize("pfad", ["/tags", "/tags?tag=1", "/konfiguration"])
def test_neue_routen_liefern_die_huelle(api, pfad):
    """oberflaeche.md 41.1: direkter Aufruf liefert die Hülle (HTTP 200)."""
    r = api.get(pfad)
    assert r.status_code == 200 and r.headers["content-type"].split(";")[0].strip() == "text/html"
    assert r.text == api.get("/").text
