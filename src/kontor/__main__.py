"""Startmodul ``python -m kontor`` (betrieb.md 2).

Liest die Konfiguration ausschließlich aus der Umgebung (``KONTOR_*``), richtet das Logging ein und startet
uvicorn mit genau einem Arbeitsprozess. Kommandozeilenargumente werden nicht ausgewertet (K 6); jedes Argument
ergibt Rückgabecode 2.
"""

from __future__ import annotations

import logging
import sys

from . import __version__
from .config import KontorConfig
from .fehler import KonfigurationsFehler

log = logging.getLogger("kontor")


def logging_einrichten(stufe: str) -> None:
    """betrieb.md 7: eine Zeile je Eintrag ``<STUFE> <logger>: <Meldung>`` nach stderr."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    wurzel = logging.getLogger()
    for h in list(wurzel.handlers):
        wurzel.removeHandler(h)
    wurzel.addHandler(handler)
    wurzel.setLevel(stufe)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("Aufruf: python -m kontor (ohne Argumente; Konfiguration über KONTOR_*-Umgebungsvariablen)",
              file=sys.stderr)
        return 2
    try:
        config = KontorConfig.from_env()
    except KonfigurationsFehler as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        return 2
    logging_einrichten(config.log_stufe)
    import uvicorn

    from .app import create_app, protokolle_absichern

    try:
        app = create_app(config)
    except KonfigurationsFehler as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        return 2
    modus = "Mock-Modus" if config.mock_modus else "Echtbetrieb"
    log.info("Kontor %s startet (%s) auf %s:%d, Datenbank %s, Anmeldung %s", __version__, modus, config.host,
             config.port, config.aktive_datenbank, "an" if config.anmeldung else "aus")
    protokolle_absichern()
    try:
        uvicorn.run(app, host=config.host, port=config.port, proxy_headers=False, lifespan="on",
                    server_header=False, workers=1, log_config=None, log_level=config.log_stufe.lower())
    except KeyboardInterrupt:  # pragma: no cover
        pass
    log.info("Kontor beendet")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
