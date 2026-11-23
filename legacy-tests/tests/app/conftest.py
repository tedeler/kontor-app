"""Fixtures für App-Tests. Jede App bekommt eine eigene temporäre Datenbank.

Verhalten bei fehlender Anwendung (Entscheidung E-024): Ist das Paket
``kontor`` nicht importierbar, schlägt jeder App-Test mit einer deutlichen
Meldung fehl. Mit ``pytest --ohne-app`` oder der Umgebungsvariable
``KONTOR_TESTS_OHNE_APP=1`` werden die App-Tests stattdessen übersprungen.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api, neue_api
from tests.hilfen.pfade import KMY
from tests.hilfen.browser_fixtures import _playwright, browser, neue_seite, starte_server  # noqa: F401  (M8, M11)


@pytest.fixture(scope="session", autouse=True)
def _app_vorhanden(request):
    """Fehlt die Anwendung, schlagen App-Tests mit klarer Meldung fehl (E-024)."""
    fehler = kontor.app_importfehler()
    if fehler is not None:
        text = f"{kontor.MELDUNG_FEHLT}\nUrsache: {type(fehler).__name__}: {fehler}"
        if kontor.ohne_app(request.config):
            pytest.skip(text)
        pytest.fail(text, pytrace=False)


@pytest.fixture
def api(tmp_path: Path) -> Api:
    """App im Echtmodus mit leerer Datenbank (Plugins fints/imap, ohne Verbindungen)."""
    return neue_api(tmp_path)


@pytest.fixture
def mock_api(tmp_path: Path) -> Api:
    return neue_api(tmp_path, mock_modus=True)


@pytest.fixture(scope="session")
def api_fabrik(tmp_path_factory):
    """Erzeugt bei jedem Aufruf eine frische App (für Hypothesis-Tests)."""
    def fabrik(**felder) -> Api:
        return neue_api(tmp_path_factory.mktemp("hyp"), **felder)
    return fabrik


@pytest.fixture(scope="module")
def standard_api(tmp_path_factory) -> Api:
    """Nur lesend verwenden: App mit importiertem standard.kmy."""
    a = neue_api(tmp_path_factory.mktemp("standard"))
    a.import_kmy(KMY / "standard.kmy", erwartet=200)
    return a


class _Netzsperre:
    """Zeichnet Verbindungsversuche ins Netz auf und lässt sie scheitern."""

    def __init__(self) -> None:
        self.versuche: list[str] = []

    def pruefe(self) -> None:
        assert not self.versuche, f"Unerlaubte Netzwerkzugriffe: {self.versuche}"


@pytest.fixture
def netz_gesperrt(monkeypatch):
    """Sperrt TCP/UDP-Verbindungen und Namensauflösung (Unix-Sockets bleiben erlaubt).

    Der TestClient von FastAPI arbeitet ohne Netzwerk; jeder Versuch der
    Anwendung, eine Verbindung aufzubauen, wird aufgezeichnet und mit
    ``OSError`` beantwortet. Am Testende muss die Liste leer sein.
    """
    sperre = _Netzsperre()
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def _netz(fam) -> bool:
        return fam in (socket.AF_INET, socket.AF_INET6)

    def connect(self, adresse):
        if _netz(self.family):
            sperre.versuche.append(f"connect {adresse!r}")
            raise OSError("Netzwerk im Test gesperrt")
        return original_connect(self, adresse)

    def connect_ex(self, adresse):
        if _netz(self.family):
            sperre.versuche.append(f"connect_ex {adresse!r}")
            raise OSError("Netzwerk im Test gesperrt")
        return original_connect_ex(self, adresse)

    def getaddrinfo(host, *a, **kw):
        sperre.versuche.append(f"getaddrinfo {host!r}")
        raise socket.gaierror("Namensauflösung im Test gesperrt")

    def gethostbyname(host):
        sperre.versuche.append(f"gethostbyname {host!r}")
        raise socket.gaierror("Namensauflösung im Test gesperrt")

    def create_connection(adresse, *a, **kw):
        sperre.versuche.append(f"create_connection {adresse!r}")
        raise OSError("Netzwerk im Test gesperrt")

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "gethostbyname", gethostbyname)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    yield sperre
    sperre.pruefe()


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_PROXY_VARIABLEN = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


@pytest.fixture
def netz_nur_loopback(monkeypatch):
    """Wie ``netz_gesperrt``, aber Verbindungen und Namensauflösung zu 127.0.0.1/::1/localhost sind erlaubt
    (lokale Attrappen, E-028, E-122). Proxy-Umgebungsvariablen werden entfernt, damit nichts über einen
    Proxy nach außen geht. Am Testende darf es keinen Versuch zu einem anderen Ziel gegeben haben.
    """
    sperre = _Netzsperre()
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_create_connection = socket.create_connection
    for name in _PROXY_VARIABLEN:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost,::1")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost,::1")

    def _host(adresse) -> str | None:
        if isinstance(adresse, tuple) and adresse:
            return str(adresse[0])
        return None

    def _erlaubt(fam, adresse) -> bool:
        if fam not in (socket.AF_INET, socket.AF_INET6):
            return True
        return _host(adresse) in _LOOPBACK

    def connect(self, adresse):
        if not _erlaubt(self.family, adresse):
            sperre.versuche.append(f"connect {adresse!r}")
            raise OSError("Netzwerk im Test gesperrt (nur Loopback)")
        return original_connect(self, adresse)

    def connect_ex(self, adresse):
        if not _erlaubt(self.family, adresse):
            sperre.versuche.append(f"connect_ex {adresse!r}")
            raise OSError("Netzwerk im Test gesperrt (nur Loopback)")
        return original_connect_ex(self, adresse)

    def getaddrinfo(host, *a, **kw):
        h = host.decode() if isinstance(host, bytes) else host
        if h not in _LOOPBACK:
            sperre.versuche.append(f"getaddrinfo {host!r}")
            raise socket.gaierror("Namensauflösung im Test gesperrt (nur Loopback)")
        return original_getaddrinfo(host, *a, **kw)

    def gethostbyname(host):
        if host not in _LOOPBACK:
            sperre.versuche.append(f"gethostbyname {host!r}")
            raise socket.gaierror("Namensauflösung im Test gesperrt (nur Loopback)")
        return "127.0.0.1" if host != "::1" else host

    def create_connection(adresse, *a, **kw):
        if _host(adresse) not in _LOOPBACK:
            sperre.versuche.append(f"create_connection {adresse!r}")
            raise OSError("Netzwerk im Test gesperrt (nur Loopback)")
        return original_create_connection(adresse, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "gethostbyname", gethostbyname)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    yield sperre
    sperre.pruefe()
