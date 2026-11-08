"""Kommandozeile: ``python -m kontor`` bzw. ``kontor``.

Unterbefehle:

- ``kontor serve [--host H] [--port P]`` – Weboberfläche und API starten
  (Konfiguration aus den Umgebungsvariablen ``KONTOR_*``).
- ``kontor import DATEI.kmy`` – KMyMoney-Datei in die aktive Datenbank importieren.
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import KontorConfig
from .fehler import KonfigurationsFehler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kontor", description="Kontor – selbst gehostete Finanz-Web-App")
    unter = parser.add_subparsers(dest="befehl", required=True)
    s = unter.add_parser("serve", help="Server starten")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    i = unter.add_parser("import", help="KMyMoney-Datei importieren")
    i.add_argument("datei")
    args = parser.parse_args(argv)
    try:
        config = KontorConfig.from_env()
    except KonfigurationsFehler as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        return 2
    if args.befehl == "serve":
        import uvicorn

        from .app import create_app

        print(f"Kontor ({'Mock-Modus' if config.mock_modus else 'Echtbetrieb'}), Datenbank: "
              f"{config.aktive_datenbank}", file=sys.stderr)
        uvicorn.run(create_app(config), host=args.host, port=args.port)
        return 0
    from .importer.kmymoney import importiere_kmy

    ergebnis = importiere_kmy(config, args.datei)
    print(json.dumps(ergebnis.als_dict(), ensure_ascii=False, indent=2))
    return 0 if ergebnis.erfolgreich else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
