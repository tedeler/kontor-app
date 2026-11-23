"""Fixtures der Oberflächentests (oberflaeche.md 21, E-139).

``browser``, ``starte_server`` und ``neue_seite`` stehen seit M11 in ``tests/hilfen/browser_fixtures.py`` und
werden in ``tests/app/conftest.py`` eingebunden (gemeinsam mit ``tests/app/m11/``).

- ``browser``: ein Chromium je Testlauf (headless, ohne Proxy, Namensauflösung nur 127.0.0.1). Startet er
  nicht oder fehlt Playwright, werden die Browsertests mit klarer Meldung übersprungen.
- ``starte_server(**felder)``: App unter uvicorn auf 127.0.0.1 mit eigener temporärer Datenbank.
- ``neue_seite(server, geraet="desktop", **kontext)``: Seite in einem frischen Browserkontext; am Testende
  dürfen keine Skriptfehler, CSP-Verletzungen oder Anfragen an fremde Herkünfte aufgetreten sein.
- ``geraet``: parametrisiert über ``desktop`` und ``handy`` (``@pytest.mark.parametrize("geraet", ...)``).
"""

from __future__ import annotations

import pytest

from tests.hilfen import m8


@pytest.fixture(params=["desktop", "handy"])
def geraet(request):
    return request.param


@pytest.fixture(autouse=True)
def _erwartung_zeit():
    """Voreinstellung für expect(): höchstens 10 s je Erwartung (oberflaeche.md 21)."""
    try:
        from playwright.sync_api import expect
    except ImportError:
        yield
        return
    expect.set_options(timeout=m8.WARTEN_MS)
    yield
