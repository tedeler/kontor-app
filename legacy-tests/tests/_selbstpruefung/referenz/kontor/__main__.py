"""WEGWERF-REFERENZ: Startmodul ``python -m kontor`` (betrieb.md 2) – KEIN Anwendungscode."""

import logging
import sys

from .config import KontorConfig
from .fehler import KonfigurationsFehler


def main(argv: list[str]) -> int:
    if argv:
        print("python -m kontor erwartet keine Argumente", file=sys.stderr)
        return 2
    try:
        config = KontorConfig.from_env()
        logging.basicConfig(stream=sys.stderr, level=config.log_stufe, format="%(levelname)s %(name)s: %(message)s")
        from .app import create_app
        app = create_app(config)
    except KonfigurationsFehler as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        return 2
    import uvicorn

    logging.getLogger("kontor").info("Kontor startet (Modus %s)", "mock" if config.mock_modus else "echt")
    uvicorn.run(app, host=config.host, port=config.port, proxy_headers=False, lifespan="on", server_header=False,
                log_config=None)
    logging.getLogger("kontor").info("Kontor beendet")
    return 0


sys.exit(main(sys.argv[1:]))
