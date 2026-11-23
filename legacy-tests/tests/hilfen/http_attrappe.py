"""Gemeinsame Grundlage der HTTP-Attrappen (OAuth2, ntfy) – nur 127.0.0.1, optional TLS (E-028, E-122)."""

from __future__ import annotations

import http.server
import json
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from .tls import TestZertifikat


@dataclass
class HttpAnfrage:
    methode: str
    pfad: str                       # mit Abfrage
    koepfe: dict[str, str]          # Namen klein geschrieben
    koerper: bytes
    zeitpunkt: float = field(default_factory=time.time)

    @property
    def json(self) -> Any:
        return json.loads(self.koerper.decode("utf-8"))

    @property
    def formular(self) -> dict[str, str]:
        from urllib.parse import parse_qsl  # noqa: PLC0415
        return dict(parse_qsl(self.koerper.decode("ascii"), keep_blank_values=True))


class HttpAttrappe:
    """Basis: Unterklassen implementieren ``antworte(anfrage) -> (status, koepfe, koerper)``."""

    name = "http-attrappe"

    def __init__(self, *, tls: TestZertifikat | None = None) -> None:
        self.tls = tls
        self.anfragen: list[HttpAnfrage] = []
        self.interne_fehler: list[str] = []
        self.verzoegerung = 0.0
        self._sperre = threading.Lock()
        self._server: http.server.ThreadingHTTPServer | None = None

    # ------------------------------------------------------------ Betrieb
    def starte(self):
        attrappe = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _bearbeiten(self):
                laenge = int(self.headers.get("Content-Length") or 0)
                koerper = self.rfile.read(laenge) if laenge else b""
                a = HttpAnfrage(self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, koerper)
                with attrappe._sperre:
                    attrappe.anfragen.append(a)
                if attrappe.verzoegerung:
                    time.sleep(attrappe.verzoegerung)
                try:
                    status, koepfe, antwort = attrappe.antworte(a)
                except Exception:  # noqa: BLE001
                    attrappe.interne_fehler.append(traceback.format_exc())
                    status, koepfe, antwort = 500, {}, b""
                self.send_response(status)
                for k, v in koepfe.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(antwort)))
                self.end_headers()
                self.wfile.write(antwort)

            do_GET = do_POST = do_PUT = do_DELETE = _bearbeiten  # noqa: N815

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        if self.tls is not None:
            self._server.socket = self.tls.server_kontext().wrap_socket(self._server.socket, server_side=True)
        threading.Thread(target=self._server.serve_forever, name=self.name, daemon=True).start()
        return self

    def stoppe(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self):
        return self.starte()

    def __exit__(self, *a) -> None:
        self.stoppe()

    @property
    def basis(self) -> str:
        assert self._server is not None, "Attrappe nicht gestartet"
        host, port = self._server.server_address[:2]
        return f"{'https' if self.tls else 'http'}://{host}:{port}"

    def antworte(self, anfrage: HttpAnfrage) -> tuple[int, dict[str, str], bytes]:  # pragma: no cover
        raise NotImplementedError


def json_antwort(status: int, obj: Any) -> tuple[int, dict[str, str], bytes]:
    return status, {"Content-Type": "application/json"}, json.dumps(obj).encode("utf-8")
