"""M7: Module, Konfiguration und Passwort-Hash (python-api.md 14, sicherheit.md 2)."""

from __future__ import annotations

import base64
import importlib.util
import unicodedata

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import neue_config
from tests.hilfen.m7 import (HASH_MUSTER, PASSWORT, anmeldung, eigener_hash, einrichtungsdatei, m7_config,
                             unabhaengig_pruefen)

VORGABEN = {
    "anmeldung": False, "sitzung_leerlauf_sekunden": 86400, "sitzung_hoechstdauer_sekunden": 2592000,
    "sitzung_cookie_secure": None, "anmeldung_fehlversuche": 5, "anmeldung_sperre_sekunden": 60,
    "erlaubte_netze": None, "upload_max_mib": 200, "anfrage_max_kib": 4096, "host": "127.0.0.1", "port": 8000,
    "log_stufe": "INFO", "beenden_frist_sekunden": 20, "mock_verzoegerung_ms": 0,
}


def Config():  # noqa: N802
    return kontor.KontorConfig()


def fehler():
    return kontor.fehler().KonfigurationsFehler


def test_module_vorhanden():
    a = anmeldung()
    for name in ("passwort_hash", "passwort_pruefen", "passwort_setzen", "ist_eingerichtet"):
        assert callable(getattr(a, name)), name
    assert callable(kontor.modul("kontor.sicherung").sichere_in_verzeichnis)
    assert importlib.util.find_spec("kontor.__main__") is not None
    assert importlib.util.find_spec("kontor.anmeldung") is not None
    kontor.modul("kontor.betrieb")


@pytest.mark.kern
def test_vorgaben(tmp_path):
    c = neue_config(tmp_path)
    for feld, wert in VORGABEN.items():
        assert getattr(c, feld) == wert and type(getattr(c, feld)) is type(wert), feld


@pytest.mark.kern
@pytest.mark.parametrize("feld,wert", [
    ("anmeldung", 1), ("anmeldung", "ja"), ("sitzung_leerlauf_sekunden", 0), ("sitzung_leerlauf_sekunden", True),
    ("sitzung_leerlauf_sekunden", 31_536_001), ("sitzung_hoechstdauer_sekunden", 0), ("sitzung_cookie_secure", "ja"),
    ("anmeldung_fehlversuche", 0), ("anmeldung_fehlversuche", 101), ("anmeldung_sperre_sekunden", 0),
    ("anmeldung_sperre_sekunden", 86_401), ("erlaubte_netze", []), ("erlaubte_netze", "192.168.0.0/16"),
    ("erlaubte_netze", ["kein netz"]), ("erlaubte_netze", ["192.168.0.0/33"]), ("erlaubte_netze", [192]),
    ("upload_max_mib", 0), ("upload_max_mib", 4097), ("anfrage_max_kib", 15), ("anfrage_max_kib", 1_048_577),
    ("host", ""), ("host", 127), ("port", 0), ("port", 65536), ("port", "8000"), ("log_stufe", "TRACE"),
    ("log_stufe", ""), ("beenden_frist_sekunden", 0), ("beenden_frist_sekunden", 601),
    ("mock_verzoegerung_ms", -1), ("mock_verzoegerung_ms", 60_001), ("mock_verzoegerung_ms", 1.5),
])
def test_ungueltige_werte(tmp_path, feld, wert):
    with pytest.raises(fehler()):
        neue_config(tmp_path, **{feld: wert})


def test_netze_kanonisch(tmp_path):
    c = neue_config(tmp_path, erlaubte_netze=["192.168.1.7/24", "::1", "10.0.0.0/8"])
    assert c.erlaubte_netze == ("192.168.1.0/24", "::1/128", "10.0.0.0/8")
    assert neue_config(tmp_path, erlaubte_netze=("127.0.0.1/32",)).erlaubte_netze == ("127.0.0.1/32",)


def _env(tmp_path, **kw):
    return {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), **kw}


def test_from_env_m7(tmp_path):
    c = Config().from_env(_env(tmp_path))
    for feld, wert in VORGABEN.items():
        assert getattr(c, feld) == wert, feld
    c = Config().from_env(_env(
        tmp_path, KONTOR_ANMELDUNG="ja", KONTOR_SITZUNG_LEERLAUF_SEKUNDEN="120",
        KONTOR_SITZUNG_HOECHSTDAUER_SEKUNDEN="3600", KONTOR_SITZUNG_COOKIE_SECURE="on",
        KONTOR_ANMELDUNG_FEHLVERSUCHE="3", KONTOR_ANMELDUNG_SPERRE_SEKUNDEN="10",
        KONTOR_ERLAUBTE_NETZE=" 192.168.0.0/16 , fe80::/10", KONTOR_UPLOAD_MAX_MIB="50", KONTOR_ANFRAGE_MAX_KIB="64",
        KONTOR_HOST="0.0.0.0", KONTOR_PORT="8080", KONTOR_LOG_STUFE="debug", KONTOR_BEENDEN_FRIST_SEKUNDEN="5",
        KONTOR_MOCK_VERZOEGERUNG_MS="250"))
    assert (c.anmeldung, c.sitzung_leerlauf_sekunden, c.sitzung_hoechstdauer_sekunden, c.sitzung_cookie_secure) == (
        True, 120, 3600, True)
    assert (c.anmeldung_fehlversuche, c.anmeldung_sperre_sekunden, c.erlaubte_netze) == (
        3, 10, ("192.168.0.0/16", "fe80::/10"))
    assert (c.upload_max_mib, c.anfrage_max_kib, c.host, c.port, c.log_stufe, c.beenden_frist_sekunden,
            c.mock_verzoegerung_ms) == (50, 64, "0.0.0.0", 8080, "DEBUG", 5, 250)
    c = Config().from_env(_env(tmp_path, KONTOR_SITZUNG_COOKIE_SECURE="nein", KONTOR_ANMELDUNG="",
                               KONTOR_ERLAUBTE_NETZE=""))
    assert (c.sitzung_cookie_secure, c.anmeldung, c.erlaubte_netze) == (False, False, None)


@pytest.mark.parametrize("var,wert", [("KONTOR_ANMELDUNG", "vielleicht"), ("KONTOR_PORT", "acht"),
                                      ("KONTOR_PORT", "70000"), ("KONTOR_ERLAUBTE_NETZE", "irgendwo"),
                                      ("KONTOR_LOG_STUFE", "laut"), ("KONTOR_SITZUNG_COOKIE_SECURE", "x"),
                                      ("KONTOR_UPLOAD_MAX_MIB", "-1")])
def test_from_env_m7_ungueltig(tmp_path, var, wert):
    with pytest.raises(fehler()):
        Config().from_env(_env(tmp_path, **{var: wert}))


def test_konstruktion_legt_nichts_an(tmp_path):
    neue_config(tmp_path / "x", anmeldung=True)
    assert not (tmp_path / "x").exists()


# ------------------------------------------------------------------ Passwort-Hash
@pytest.mark.kern
def test_hash_textform_und_unabhaengig_pruefbar():
    a = anmeldung()
    h = a.passwort_hash(PASSWORT)
    m = HASH_MUSTER.match(h)
    assert m, h
    assert (m[1], m[2], m[3]) == ("32768", "8", "1")
    assert len(base64.b64decode(m[4], validate=True)) == 16 and len(base64.b64decode(m[5], validate=True)) == 32
    assert unabhaengig_pruefen(PASSWORT, h) and not unabhaengig_pruefen(PASSWORT + "x", h)
    assert PASSWORT not in h
    h2 = a.passwort_hash(PASSWORT)
    assert h2 != h and m[4] != HASH_MUSTER.match(h2)[4], "neues Salz je Hash"


@pytest.mark.kern
def test_pruefen():
    a = anmeldung()
    h = a.passwort_hash(PASSWORT)
    assert a.passwort_pruefen(PASSWORT, h) is True
    assert a.passwort_pruefen(PASSWORT[:-1], h) is False
    assert a.passwort_pruefen(PASSWORT.upper(), h) is False
    # gespeicherte Parameter werden verwendet (spätere Erhöhung möglich)
    assert a.passwort_pruefen("anderes-Passwort-1", eigener_hash("anderes-Passwort-1", n=2 ** 12, r=4, p=2))
    assert not a.passwort_pruefen("anderes-Passwort-2", eigener_hash("anderes-Passwort-1", n=2 ** 12))


@pytest.mark.kern
def test_nfc():
    a = anmeldung()
    nfd = unicodedata.normalize("NFD", "Prüfwörter-Äöü-ßé")
    nfc = unicodedata.normalize("NFC", nfd)
    assert nfd != nfc
    h = a.passwort_hash(nfd)
    assert a.passwort_pruefen(nfc, h) and unabhaengig_pruefen(nfc, h)
    # Länge zählt nach NFC: 12 zerlegte é sind 24 Codepunkte, aber 12 Zeichen
    a.passwort_hash("é" * 12)
    with pytest.raises(ValueError):
        a.passwort_hash("é" * 11)


@pytest.mark.kern
@pytest.mark.parametrize("text", [
    "", "scrypt", "bcrypt$32768$8$1$MDEyMzQ1Njc4OWFiY2RlZg==$" + "A" * 44,
    "scrypt$32768$8$1$MDEyMzQ1Njc4OWFiY2RlZg==", "scrypt$30000$8$1$MDEyMzQ1Njc4OWFiY2RlZg==$" + "A" * 43 + "=",
    "scrypt$32768$8$1$!!!$" + "A" * 43 + "=", "scrypt$32768$8$1$MDEyMzQ1Njc4OWFiY2RlZg==$QUJD",
    "scrypt$32768$0$1$MDEyMzQ1Njc4OWFiY2RlZg==$" + "A" * 43 + "=",
    "scrypt$1$8$1$MDEyMzQ1Njc4OWFiY2RlZg==$" + "A" * 43 + "=",
    "scrypt$032768$8$1$MDEyMzQ1Njc4OWFiY2RlZg==$" + "A" * 43 + "=",
    "scrypt$32768$8$1$MDEyMzQ1Njc4OWFiY2RlZg==$" + "A" * 43 + "=$x",
])
def test_unfoermige_hashes_falsch(text):
    assert anmeldung().passwort_pruefen(PASSWORT, text) is False


@pytest.mark.kern
@pytest.mark.parametrize("pw", ["x" * 11, "", "x" * 1025, " " * 5])
def test_passwortlaenge(pw):
    with pytest.raises(ValueError) as e:
        anmeldung().passwort_hash(pw)
    assert pw.strip() == "" or pw not in str(e.value)
    anmeldung().passwort_hash("x" * 12)
    anmeldung().passwort_hash("x" * 1024)


def test_typen():
    a = anmeldung()
    with pytest.raises(TypeError):
        a.passwort_hash(b"bytes-passwort-123")
    with pytest.raises(TypeError):
        a.passwort_pruefen(None, a.passwort_hash(PASSWORT))


@pytest.mark.kern
def test_passwort_setzen_und_eingerichtet(tmp_path):
    a = anmeldung()
    c = neue_config(tmp_path / "db")
    assert a.ist_eingerichtet(c) is False
    assert not (tmp_path / "db").exists(), "ist_eingerichtet legt die Datenbank nicht an"
    with pytest.raises(ValueError):
        a.passwort_setzen(c, "kurz")
    assert a.ist_eingerichtet(c) is False
    a.passwort_setzen(c, PASSWORT)
    assert a.ist_eingerichtet(c) is True
    assert PASSWORT.encode() not in b"".join(p.read_bytes() for p in (tmp_path / "db").iterdir())


def test_passwort_setzen_loescht_einrichtungscode(tmp_path):
    c = m7_config(tmp_path, passwort=None)
    kontor.create_app(c)
    assert einrichtungsdatei(c).exists()
    anmeldung().passwort_setzen(c, PASSWORT)
    assert not einrichtungsdatei(c).exists()


def test_mock_und_echt_getrennt(tmp_path):
    echt = neue_config(tmp_path)
    mock = neue_config(tmp_path, mock_modus=True)
    anmeldung().passwort_setzen(mock, PASSWORT)
    assert anmeldung().ist_eingerichtet(mock) and not anmeldung().ist_eingerichtet(echt)
