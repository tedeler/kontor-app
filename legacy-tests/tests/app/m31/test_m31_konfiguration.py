"""M31: Konfiguration, ausgelieferte Umgebungsdateien, Testinstanz, Branch-Anzeige in der Hülle und Route
``/lernmodell`` (python-api.md 22, betrieb.md 3 und 9, version.md 6, oberflaeche.md 40.2; E-284, E-285) – kern.
"""

from __future__ import annotations

import importlib.resources
import re
from html.parser import HTMLParser

import pytest

from tests.app.m7.test_m7_betrieb import _haertung
from tests.hilfen import kontor
from tests.hilfen.api import neue_api
from tests.hilfen.m7 import betriebsdatei
from tests.hilfen.m13 import zweig_in_huelle
from tests.hilfen.systemd import Unit, geheimer_name, umgebungsdatei

pytestmark = pytest.mark.kern
FELDER = ("regeln_automatisch", "mail_bestellnummer")
VARIABLE = {"regeln_automatisch": "KONTOR_REGELN_AUTOMATISCH", "mail_bestellnummer": "KONTOR_MAIL_BESTELLNUMMER"}


@pytest.mark.parametrize("feld", FELDER)
def test_konfigurationsfeld(tmp_path, feld):
    K = kontor.KontorConfig()
    F = kontor.fehler().KonfigurationsFehler
    db = tmp_path / "k.db"
    assert getattr(K(datenbank=db), feld) is False
    assert getattr(K(datenbank=db, **{feld: True}), feld) is True
    for falsch in (1, 0, "ja", None):
        with pytest.raises(F) as e:
            K(datenbank=db, **{feld: falsch})
        assert e.value.details.get("feld") == feld
    env = {"KONTOR_DATENBANK": str(db)}
    assert getattr(K.from_env(env), feld) is False
    for w, soll in (("1", True), ("ja", True), ("ON", True), ("0", False), ("nein", False), ("", False)):
        assert getattr(K.from_env({**env, VARIABLE[feld]: w}), feld) is soll, w
    with pytest.raises(F):
        K.from_env({**env, VARIABLE[feld]: "vielleicht"})


def test_ausgelieferte_umgebungsdatei(tmp_path):
    werte, _ = umgebungsdatei(betriebsdatei("kontor.env"))
    assert (werte.get("KONTOR_MAIL_ABGLEICH"), werte.get("KONTOR_MAIL_BESTELLNUMMER"),
            werte.get("KONTOR_REGELN_AUTOMATISCH")) == ("0", "1", "1")
    c = kontor.KontorConfig().from_env({**werte, "KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"),
                                        "CREDENTIALS_DIRECTORY": str(tmp_path)})
    assert (c.mail_abgleich, c.mail_bestellnummer, c.regeln_automatisch) == (False, True, True)


# ------------------------------------------------------------------ Testinstanz (betrieb.md 9)


def test_testinstanz_service():
    u = Unit(betriebsdatei("kontor-test.service"))
    s = "Service"
    assert u.wert(s, "EnvironmentFile") == "/etc/kontor/kontor-test.env"
    assert u.werte(s, "ExecStart") == ["/opt/kontor-test/venv/bin/python -m kontor"]
    assert u.wert(s, "StateDirectory") == "kontor-test"
    assert u.wert(s, "ProtectSystem") == "strict"
    unzugaenglich = " ".join(u.werte(s, "InaccessiblePaths")).split()
    for pfad in ("/var/lib/kontor", "/etc/kontor/kontor.env"):
        assert pfad in [p.lstrip("-") for p in unzugaenglich], pfad
    assert "LoadCredentialEncrypted" not in u.schluessel(s)
    assert "Install" not in u.abschnitte, "startet nicht beim Hochfahren"
    _haertung(u)


def test_testinstanz_umgebungsdatei(tmp_path):
    werte, kommentare = umgebungsdatei(betriebsdatei("kontor-test.env"))
    assert (werte.get("KONTOR_MOCK_MODUS"), werte.get("KONTOR_PORT"), werte.get("KONTOR_MAIL_ABGLEICH")) == (
        "1", "8081", "0")
    if "KONTOR_DATENBANK" in werte:
        assert werte["KONTOR_DATENBANK"].startswith("/var/lib/kontor-test/")
    for k in werte:
        assert not geheimer_name(k), k
    for z in kommentare:
        m = re.match(r"#\s*([A-Z_][A-Z0-9_]*)=(.*)", z)
        if m:
            assert not geheimer_name(m[1]) or not m[2].strip(), z
    c = kontor.KontorConfig().from_env({**werte, "KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"),
                                        "CREDENTIALS_DIRECTORY": str(tmp_path)})
    assert (c.mock_modus, c.port, c.mail_abgleich) == (True, 8081, False)


def test_testinstanz_skript_und_modul():
    skript = importlib.resources.files("kontor.betrieb").joinpath("kontor-test.sh")
    assert skript.is_file() and skript.read_text(encoding="utf-8").strip()
    assert kontor.modul("kontor.testinstanz") is not None


# ------------------------------------------------------------------ Branch (version.md 6)


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict] = []
        self._offen: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if a.get("data-testid") == "zweig-link":
            self._offen = {"tag": tag, "attrs": a, "text": ""}
            self.links.append(self._offen)

    def handle_endtag(self, tag):
        self._offen = None

    def handle_data(self, data):
        if self._offen is not None:
            self._offen["text"] += data


@pytest.mark.parametrize("modus", ["echt", "mock"])
def test_branch_in_der_huelle(tmp_path, modus):
    api = neue_api(tmp_path, mock_modus=modus == "mock")
    html = api.get("/").text
    v = api.get("/api/version", erwartet=200).daten
    p = _Links()
    p.feed(html)
    if not zweig_in_huelle(html):
        assert p.links == [] and f"Version {v['version']}" in " ".join(html.split()), "auf main wie bisher"
        return
    (link,) = p.links
    assert link["tag"] == "a" and link["attrs"].get("target") == "_blank"
    m = re.fullmatch(re.escape(v["repository"].rstrip("/")) + r"/tree/([A-Za-z0-9._/-]+)", link["attrs"]["href"])
    assert m and m[1] != "main", link["attrs"]["href"]


def test_route_lernmodell(api):
    r = api.get("/lernmodell")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert 'data-testid="nav-lernmodell"' not in r.text, "kein Eintrag in der Navigation"
