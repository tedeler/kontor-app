"""Mock-Modus: eigene Datenbank, sichtbarer Hinweis, keine Verbindungen (K 3, plugins.md 6, E-014)."""

from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api, neue_config
from tests.hilfen.pfade import KMY, MOCK


# --------------------------------------------------------- HTML-Auswertung

LEERE_ELEMENTE = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Knoten:
    def __init__(self, tag, attrs, eltern):
        self.tag, self.attrs, self.eltern = tag, attrs, eltern
        self.kinder: list[_Knoten | str] = []

    def text(self) -> str:
        return "".join(k if isinstance(k, str) else k.text() for k in self.kinder)


class _Baum(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.wurzel = _Knoten(None, {}, None)
        self.stapel = [self.wurzel]

    def handle_starttag(self, tag, attrs):
        k = _Knoten(tag, {n: (v or "") for n, v in attrs}, self.stapel[-1])
        self.stapel[-1].kinder.append(k)
        if tag not in LEERE_ELEMENTE:
            self.stapel.append(k)

    def handle_startendtag(self, tag, attrs):
        self.stapel[-1].kinder.append(_Knoten(tag, {n: (v or "") for n, v in attrs}, self.stapel[-1]))

    def handle_endtag(self, tag):
        for i in range(len(self.stapel) - 1, 0, -1):
            if self.stapel[i].tag == tag:
                del self.stapel[i:]
                return

    def handle_data(self, data):
        self.stapel[-1].kinder.append(data)


def _alle(k: _Knoten):
    yield k
    for c in k.kinder:
        if isinstance(c, _Knoten):
            yield from _alle(c)


def _versteckt(k: _Knoten) -> str | None:
    if k.tag in ("template", "noscript", "head", "script", "style"):
        return f"liegt in <{k.tag}>"
    if "hidden" in k.attrs:
        return "Attribut hidden"
    if k.attrs.get("aria-hidden", "").lower() == "true":
        return "aria-hidden=true"
    stil = re.sub(r"\s+", "", k.attrs.get("style", "").lower())
    for verboten in ("display:none", "visibility:hidden", "opacity:0;", "opacity:0!", "content-visibility:hidden"):
        if verboten in stil + ";":
            return f"style {verboten}"
    return None


def pruefe_mock_hinweis(html: str) -> None:
    baum = _Baum()
    baum.feed(html)
    treffer = [k for k in _alle(baum.wurzel) if k.attrs.get("id") == "mock-hinweis"]
    assert len(treffer) == 1, f"genau ein Element mit id=\"mock-hinweis\" erwartet, gefunden {len(treffer)}"
    el = treffer[0]
    assert "Mock-Modus" in el.text(), f"Text des Hinweises enthält nicht 'Mock-Modus': {el.text()!r}"
    k = el
    while k is not None and k.tag is not None:
        grund = _versteckt(k)
        assert grund is None, f"Mock-Hinweis ist nicht sichtbar: <{k.tag}> {grund}"
        k = k.eltern


def test_html_pruefung_selbst():
    """Selbstkontrolle der HTML-Auswertung."""
    pruefe_mock_hinweis('<html><body><div class="x"><p id="mock-hinweis">Achtung: <b>Mock-Modus</b></p></div></body>')
    for schlecht in ('<body><p id="mock-hinweis" hidden>Mock-Modus</p></body>',
                     '<body><div style="display: none"><p id="mock-hinweis">Mock-Modus</p></div></body>',
                     '<body><template><p id="mock-hinweis">Mock-Modus</p></template></body>',
                     '<body><p id="mock-hinweis">Testbetrieb</p></body>',
                     '<body><p>Mock-Modus</p></body>'):
        with pytest.raises(AssertionError):
            pruefe_mock_hinweis(schlecht)


# --------------------------------------------------------- Datenbanken


def test_mockmodus_eigene_datenbank(tmp_path, netz_gesperrt):
    config = neue_config(tmp_path, mock_modus=True)
    Api(config)
    assert (tmp_path / "kontor-mock.sqlite3").exists(), "Mock-Datenbank wurde nicht angelegt"
    assert not (tmp_path / "kontor.sqlite3").exists(), "Echt-Datenbank darf im Mock-Modus nicht angelegt werden"


def test_echtmodus_legt_keine_mockdatenbank_an(tmp_path, netz_gesperrt):
    api = Api(neue_config(tmp_path))
    api.konto("Giro")
    api.get("/api/status", erwartet=200)
    assert (tmp_path / "kontor.sqlite3").exists()
    assert not (tmp_path / "kontor-mock.sqlite3").exists()


def test_eigener_pfad_und_elternverzeichnisse(tmp_path, netz_gesperrt):
    ziel = tmp_path / "tief" / "verschachtelt" / "mock.db"
    config = kontor.KontorConfig()(datenbank=tmp_path / "echt" / "k.sqlite3", mock_modus=True, mock_datenbank=ziel)
    api = Api(config)
    api.konto("Giro")
    assert ziel.exists() and not (tmp_path / "echt").exists()
    echt = Api(kontor.KontorConfig()(datenbank=tmp_path / "neu" / "unter" / "k.sqlite3"))
    assert (tmp_path / "neu" / "unter" / "k.sqlite3").exists() and echt.konten() == []


def test_daten_getrennt(tmp_path, netz_gesperrt):
    mock = Api(neue_config(tmp_path, mock_modus=True))
    mock.import_kmy(KMY / "minimal.kmy", erwartet=200)
    mock.konto("Nur im Mock")
    echt = Api(neue_config(tmp_path))
    assert echt.konten() == [] and echt.alle_buchungen() == [] and echt.get("/api/importe", erwartet=200).daten == []
    echt.konto("Nur echt")
    assert sorted(k["name"] for k in mock.konten()) == ["Gehalt", "Girokonto", "Lebensmittel", "Nur im Mock"]
    assert [k["name"] for k in echt.konten()] == ["Nur echt"]
    # neue App mit derselben Mock-Konfiguration sieht die Mock-Daten wieder
    wieder = Api(neue_config(tmp_path, mock_modus=True))
    assert len(wieder.alle_buchungen()) == 2


def test_import_python_im_mockmodus(tmp_path, netz_gesperrt):
    config = neue_config(tmp_path, mock_modus=True)
    e = kontor.importiere_kmy(config, KMY / "minimal.kmy")
    assert e.erfolgreich
    assert not (tmp_path / "kontor.sqlite3").exists(), "Import im Mock-Modus berührt die Echt-Datenbank"
    assert len(Api(config).alle_buchungen()) == 2
    assert Api(neue_config(tmp_path)).alle_buchungen() == []


def test_apps_unabhaengig(tmp_path, netz_gesperrt):
    a = Api(neue_config(tmp_path / "a"))
    b = Api(neue_config(tmp_path / "b", mock_modus=True))
    a.import_kmy(KMY / "minimal.kmy", erwartet=200)
    assert b.konten() == []
    assert a.get("/api/status", erwartet=200).daten["modus"] == "echt"
    assert b.get("/api/status", erwartet=200).daten["modus"] == "mock"


# ---------------------------------------------------------------- Hinweis


@pytest.mark.parametrize("szenario", ["normal", "bankfehler", "tan_erforderlich", "token_ablauf"])
def test_status_im_mockmodus(tmp_path, szenario, netz_gesperrt):
    api = Api(neue_config(tmp_path, mock_modus=True, mock_szenario=szenario))
    d = api.get("/api/status", erwartet=200).daten
    assert d["modus"] == "mock" and d["mock"] is True
    assert d["hinweis"] and "Mock" in d["hinweis"]
    assert d["mock_szenario"] == szenario
    assert d["plugins"] == {"bank": {"name": "mock", "mock": True}, "mail": {"name": "mock", "mock": True}}


def test_header_im_mockmodus(mock_api, netz_gesperrt):
    for r in (mock_api.get("/api/status"), mock_api.get("/api/konten"), mock_api.get("/api/gibtsnicht"),
              mock_api.post("/api/konten", json={}), mock_api.delete("/api/status"),
              mock_api.get("/api/buchungen/4711")):
        assert r.headers["x-kontor-modus"] == "mock"


def test_oberflaeche_zeigt_mock_hinweis(mock_api, netz_gesperrt):
    r = mock_api.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].split(";")[0].strip() == "text/html"
    pruefe_mock_hinweis(r.text)


def test_oberflaeche_echt_ohne_hinweis(api, netz_gesperrt):
    r = api.get("/")
    assert r.status_code == 200 and "mock-hinweis" not in r.text


def test_create_app_aus_umgebung(tmp_path, monkeypatch, netz_gesperrt):
    from fastapi.testclient import TestClient

    for k in ("KONTOR_MOCK_DATENBANK", "KONTOR_BANK_PLUGIN", "KONTOR_MAIL_PLUGIN", "KONTOR_MOCK_SZENARIO",
              "KONTOR_MOCK_DATEN", "KONTOR_MOCK_HEUTE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KONTOR_DATENBANK", str(tmp_path / "env.sqlite3"))
    monkeypatch.setenv("KONTOR_MOCK_MODUS", "ja")
    monkeypatch.setenv("KONTOR_MOCK_SZENARIO", "zeitueberschreitung")
    client = TestClient(kontor.create_app(None))
    d = client.get("/api/status").json()
    assert (d["modus"], d["mock_szenario"]) == ("mock", "zeitueberschreitung")
    assert client.get("/").status_code == 200 and "mock-hinweis" in client.get("/").text
    assert (tmp_path / "env-mock.sqlite3").exists() and not (tmp_path / "env.sqlite3").exists()


def test_mock_mit_datendatei_und_heute(tmp_path, netz_gesperrt):
    """Eine App mit vollständiger Mock-Konfiguration startet ohne Netz und meldet ihren Zustand."""
    api = Api(neue_config(tmp_path, mock_modus=True, mock_daten=MOCK / "mock_daten.json",
                          mock_heute=dt.date(2024, 6, 30)))
    d = api.get("/api/status", erwartet=200).daten
    assert d["mock"] is True and d["mock_szenario"] == "normal"
    pruefe_mock_hinweis(api.get("/").text)
