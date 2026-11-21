"""Eigene Tests zum Betrieb hinter einem HTTPS-Proxy (D-239), so wie ihn `kontor-https` mit Tailscale Serve einrichtet:
ein echter Kontor-Server auf 127.0.0.1 mit den drei Einstellungen des Skripts, davor ein kleiner TLS-Proxy auf
Loopback mit einem für den Test erzeugten Zertifikat. Geprüft wird das Verhalten, auf das es im Betrieb ankommt:
Anmelden, Schreiben, Cookie, Herkunftsprüfung, Sicherheitsköpfe – per HTTP-Client und im Browser.
Nur Loopback, synthetisches Passwort, kein Geheimnis."""

from __future__ import annotations

import contextlib
import datetime as dt
import http.client
import http.server
import ipaddress
import socket
import ssl
import threading

import httpx
import pytest

from kontor import anmeldung

from .test_browser import DESKTOP, HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

PASSWORT = "Synthetisch-Haushalt-2026"
NAME = "localhost"            # Name im Zertifikat und in der Adresse; löst überall auf 127.0.0.1 auf
_NICHT_WEITERGEBEN = {"connection", "keep-alive", "transfer-encoding", "content-length", "te", "upgrade"}


def _zertifikat(verzeichnis):
    """Selbst signiertes Zertifikat für `localhost`/127.0.0.1, nur für diesen Testlauf."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    schluessel = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, NAME)])
    jetzt = dt.datetime.now(dt.timezone.utc)
    zert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(schluessel.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(jetzt - dt.timedelta(minutes=5))
            .not_valid_after(jetzt + dt.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(NAME), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                           critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(schluessel, hashes.SHA256()))
    zert_datei, schluessel_datei = verzeichnis / "zert.pem", verzeichnis / "schluessel.pem"
    zert_datei.write_bytes(zert.public_bytes(serialization.Encoding.PEM))
    schluessel_datei.write_bytes(schluessel.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                         serialization.NoEncryption()))
    return zert_datei, schluessel_datei


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def tls_proxy(verzeichnis, ziel_port: int, port: int, *, host_behalten: bool = True):
    """TLS-Proxy auf 127.0.0.1:`port`, der jede Anfrage unverschlüsselt an 127.0.0.1:`ziel_port` weiterreicht – wie
    Tailscale Serve. `host_behalten=False` ersetzt den Host-Kopf durch die Adresse des Ziels (andere Proxys)."""
    zert, schluessel = _zertifikat(verzeichnis)

    class Weiterreicher(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _weiter(self):
            laenge = int(self.headers.get("Content-Length") or 0)
            koerper = self.rfile.read(laenge) if laenge else None
            koepfe = [(k, v) for k, v in self.headers.items() if k.lower() not in _NICHT_WEITERGEBEN and k.lower() != "host"]
            koepfe.append(("Host", self.headers.get("Host") if host_behalten else f"127.0.0.1:{ziel_port}"))
            con = http.client.HTTPConnection("127.0.0.1", ziel_port, timeout=30)
            try:
                con.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
                for k, v in koepfe:
                    con.putheader(k, v)
                if koerper is not None:
                    con.putheader("Content-Length", str(len(koerper)))
                con.endheaders(koerper)
                antwort = con.getresponse()
                daten = antwort.read()
                self.send_response_only(antwort.status, antwort.reason)
                for k, v in antwort.getheaders():        # mehrere Set-Cookie bleiben einzeln erhalten
                    if k.lower() not in _NICHT_WEITERGEBEN:
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(daten)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(daten)
            finally:
                con.close()

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _weiter

        def log_message(self, *args):  # still
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Weiterreicher)
    kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    kontext.load_cert_chain(zert, schluessel)
    srv.socket = kontext.wrap_socket(srv.socket, server_side=True)
    faden = threading.Thread(target=srv.serve_forever, daemon=True)
    faden.start()
    try:
        yield f"https://{NAME}:{port}", zert
    finally:
        srv.shutdown()
        srv.server_close()
        faden.join(timeout=10)


@contextlib.contextmanager
def hinter_https(tmp_path, *, oeffentlich: bool = True, host_behalten: bool = True, **kw):
    """Kontor so, wie `kontor-https einrichten` es hinterlässt: nur 127.0.0.1, Secure-Cookie, öffentliche Adresse."""
    port = _freier_port()
    adresse = f"https://{NAME}:{port}"
    with server(tmp_path, anmeldung=True, sitzung_cookie_secure=True,
                oeffentliche_url=adresse if oeffentlich else None, **kw) as (intern, config):
        anmeldung.passwort_setzen(config, PASSWORT)
        with tls_proxy(tmp_path, int(intern.rsplit(":", 1)[1]), port, host_behalten=host_behalten) as (url, zert):
            assert url == adresse
            yield url, intern, zert, config


def _client(url, zert=None):
    pruefung = ssl.create_default_context(cafile=str(zert)) if zert else True
    return httpx.Client(base_url=url, verify=pruefung, trust_env=False, timeout=30)


@pytest.mark.parametrize("host_behalten", [True, False], ids=["host-wie-im-browser", "host-vom-proxy-ersetzt"])
def test_anmelden_und_schreiben_ueber_https(tmp_path, host_behalten):
    with hinter_https(tmp_path, host_behalten=host_behalten) as (url, _intern, zert, _config), _client(url, zert) as c:
        # ohne Sitzung: Seiten leiten zur Anmeldung, die API antwortet 401
        r = c.get("/")
        assert r.status_code == 303 and r.headers["location"].startswith("/anmelden")
        assert c.get("/api/konten").status_code == 401
        # Anmelden wie der Browser: Herkunft ist die https-Adresse
        r = c.post("/api/anmeldung", json={"passwort": PASSWORT}, headers={"Origin": url})
        assert r.status_code == 200, r.text
        cookie = r.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie and "samesite" in cookie
        csrf = r.json()["csrf_token"]
        # Lesen und Schreiben mit Sitzung
        assert c.get("/api/konten").status_code == 200
        r = c.post("/api/tags", json={"name": "Urlaub"}, headers={"Origin": url, "X-Kontor-CSRF": csrf})
        assert r.status_code == 201, r.text
        assert [t["name"] for t in c.get("/api/tags").json()] == ["Urlaub"]
        # fremde Herkunft bleibt gesperrt, auch mit gültigem Token
        r = c.post("/api/tags", json={"name": "Fremd"}, headers={"Origin": "https://fremd.example.invalid", "X-Kontor-CSRF": csrf})
        assert r.status_code == 403 and r.json()["fehler"]["code"] == "csrf_ungueltig"
        # Sicherheitsköpfe kommen durch den Proxy an
        kopf = c.get("/anmelden").headers
        assert "script-src 'self'" in kopf["content-security-policy"] and kopf["x-content-type-options"] == "nosniff"


def test_ohne_oeffentliche_adresse_scheitern_anmelden_und_schreiben(tmp_path):
    """Der Fehler, vor dem Kontor beim Start warnt: Secure-Cookie hinter dem Proxy, aber keine öffentliche Adresse."""
    with hinter_https(tmp_path, oeffentlich=False) as (url, _intern, zert, _config), _client(url, zert) as c:
        r = c.post("/api/anmeldung", json={"passwort": PASSWORT}, headers={"Origin": url})
        assert r.status_code == 403 and r.json()["fehler"]["code"] == "csrf_ungueltig"


def test_sitzung_gilt_nicht_ueber_unverschluesseltes_http(tmp_path):
    """Das Secure-Cookie geht nie über http: Wer Kontor direkt (ohne Proxy) anspricht, bleibt abgemeldet."""
    with hinter_https(tmp_path) as (url, intern, zert, _config):
        with _client(url, zert) as c:
            assert c.post("/api/anmeldung", json={"passwort": PASSWORT}, headers={"Origin": url}).status_code == 200
            sitzung = dict(c.cookies)
            assert sitzung and c.get("/api/konten").status_code == 200
        with _client(intern) as direkt:
            # Anmelden über http gelingt technisch (Herkunft = eigene Adresse), das Cookie ist aber „Secure“ …
            r = direkt.post("/api/anmeldung", json={"passwort": PASSWORT}, headers={"Origin": intern})
            assert r.status_code == 200 and "secure" in r.headers["set-cookie"].lower()
            # … und wird vom Client über http nicht zurückgeschickt
            assert direkt.get("/api/konten").status_code == 401


def test_zertifikat_wird_geprueft(tmp_path):
    """Gegenprobe für den Testaufbau: ohne das Testzertifikat lehnt der Client die Verbindung ab."""
    with hinter_https(tmp_path) as (url, *_), _client(url) as c:
        with pytest.raises(httpx.ConnectError):
            c.get("/api/gesundheit")


def test_gesundheit_ueber_https_wie_das_skript_sie_abfragt(tmp_path):
    with hinter_https(tmp_path) as (url, _intern, zert, _config), _client(url, zert) as c:
        r = c.get("/api/gesundheit")
        assert r.status_code == 200 and r.json()["status"] == "ok"


playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


@pytest.mark.parametrize("geraet", [DESKTOP, HANDY], ids=["desktop", "handy"])
def test_browser_arbeitet_ueber_https(tmp_path, browser, geraet):  # noqa: F811
    """Im Browser: Anmelden, Anlegen (schreibende Anfrage mit Herkunft und CSRF-Kopf), Neuladen, Abmelden – alles
    über die https-Adresse (sicherer Ursprung, Cookie nur über HTTPS)."""
    with hinter_https(tmp_path) as (url, _intern, _zert, _config), \
            seite(browser, url, ignore_https_errors=True, **geraet) as page:
        page.goto(url + "/kategorien")
        expect(tid(page, "anmeldung-formular")).to_be_visible()
        assert page.url.startswith(url + "/anmelden?weiter=")
        tid(page, "anmeldung-passwort").fill(PASSWORT)
        tid(page, "anmeldung-passwort").press("Enter")
        bereit(page, "kategorien")
        assert page.evaluate("() => location.protocol") == "https:" and page.evaluate("() => window.isSecureContext")
        cookies = [c for c in page.context.cookies() if c["name"].startswith("kontor")]
        assert cookies and all(c["secure"] and c["httpOnly"] for c in cookies)
        tid(page, "kategorie-anlegen").click()
        tid(page, "konto-name").fill("Spenden")
        tid(page, "konto-speichern").click()
        expect(page.locator('[role="treeitem"][aria-label="Spenden"]')).to_be_visible()
        page.reload()
        bereit(page, "kategorien")
        expect(page.locator('[role="treeitem"][aria-label="Spenden"]')).to_be_visible()
        page.goto(url + "/einstellungen?bereich=sicherheit")
        bereit(page, "einstellungen")
        tid(page, "abmelden").click()
        expect(tid(page, "anmeldung-formular")).to_be_visible()
        assert page.request.get(url + "/api/konten").status == 401
