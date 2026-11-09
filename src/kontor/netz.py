"""Ausgehende Verbindungen zu Fremdsystemen (geheimnisse.md 7).

- TLS prüft immer Zertifikat und Hostnamen; mit ``tls_ca_datei`` gelten ausschließlich deren Zertifikate als
  Vertrauensanker, sonst die des Systems.
- HTTP über ``http.client``: keine Umleitungen, keine Proxys aus der Umgebung, keine Zugangsdaten aus ``.netrc``;
  die Verbindung geht nur an den Host der konfigurierten URL.
- Nichts hier protokolliert Anfragen oder Antworten (Körper und Köpfe können Geheimnisse enthalten).
"""

from __future__ import annotations

import http.client
import ssl
import urllib.parse
from dataclasses import dataclass

from .config import KontorConfig


def tls_kontext(config: KontorConfig) -> ssl.SSLContext:
    if config.tls_ca_datei is not None:
        k = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(config.tls_ca_datei))
    else:
        k = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    k.check_hostname = True
    k.verify_mode = ssl.CERT_REQUIRED
    # Eigene Vertrauensanker (z. B. ein selbst signiertes Zertifikat des Heimservers) haben oft keine
    # Schlüsselkennungen; die strenge X.509-Prüfung von Python ≥ 3.13 würde sie trotz passendem Anker ablehnen.
    if config.tls_ca_datei is not None and hasattr(ssl, "VERIFY_X509_STRICT"):
        k.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return k


@dataclass(frozen=True)
class HttpAntwort:
    status: int
    koepfe: dict[str, str]
    koerper: bytes

    def __repr__(self) -> str:  # Körper kann Tokens enthalten
        return f"HttpAntwort(status={self.status})"


def http_anfrage(config: KontorConfig, methode: str, url: str, koerper: bytes | None, koepfe: dict[str, str],
                 timeout: float) -> HttpAntwort:
    """Genau eine HTTP-Anfrage ohne Umleitungen. Wirft ``OSError`` (inkl. ``TimeoutError``, ``ssl.SSLError``) und
    ``http.client.HTTPException`` bei Verbindungsfehlern."""
    teile = urllib.parse.urlsplit(url)
    host = teile.hostname or ""
    pfad = teile.path or "/"
    if teile.query:
        pfad += "?" + teile.query
    if teile.scheme == "https":
        verbindung: http.client.HTTPConnection = http.client.HTTPSConnection(
            host, teile.port, timeout=timeout, context=tls_kontext(config))
    else:
        verbindung = http.client.HTTPConnection(host, teile.port, timeout=timeout)
    try:
        verbindung.request(methode, pfad, body=koerper, headers=koepfe)
        antwort = verbindung.getresponse()
        daten = antwort.read()
        return HttpAntwort(antwort.status, {k.lower(): v for k, v in antwort.getheaders()}, daten)
    finally:
        verbindung.close()


__all__ = ["tls_kontext", "http_anfrage", "HttpAntwort"]
