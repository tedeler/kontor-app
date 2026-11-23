"""Gemeinsame Browser-Fixtures der Oberflächentests (M8, M11; oberflaeche.md 21, E-139).

Sie stehen in ``tests/app/conftest.py``, damit Playwright und Chromium je Testlauf (bzw. je xdist-Arbeiter) genau
einmal gestartet werden, auch wenn Tests aus mehreren Meilenstein-Verzeichnissen laufen (zwei Session-Fixtures
``_playwright`` in getrennten conftest-Dateien starteten sonst Playwright zweimal im selben Prozess).

- ``browser``: ein Chromium je Testlauf (headless, ohne Proxy, Namensauflösung nur 127.0.0.1). Startet er
  nicht oder fehlt Playwright, werden die Browsertests mit klarer Meldung übersprungen.
- ``starte_server(**felder)``: App unter uvicorn auf 127.0.0.1 mit eigener temporärer Datenbank.
- ``neue_seite(server, geraet="desktop", person="Torsten", **kontext)``: Seite in einem frischen Browserkontext;
  am Testende dürfen keine Skriptfehler, CSP-Verletzungen oder Anfragen an fremde Herkünfte aufgetreten sein.
  Ab M28 setzt ein Init-Skript des Kontexts vor dem ersten Laden die Person (``localStorage["kontor.person"]``,
  ``oberflaeche.md`` 37.1, E-253); ``person=None`` lässt sie weg (Pflichtdialog). Ab M32 ist die Erfolgsmeldung
  mit „Rückgängig“ ausgeschaltet (41.9); ``erfolgsmeldung=True`` schaltet sie vorab in einer Hilfsseite desselben
  Kontexts über die Einstellung ein (``m32.erfolgsmeldung_einschalten``, E-306/E-307).
"""

from __future__ import annotations

import pytest

from tests.hilfen import m8

_BROWSER_FEHLT: str | None = None


@pytest.fixture(scope="session")
def _playwright():
    global _BROWSER_FEHLT
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover - abhängig von der Umgebung
        _BROWSER_FEHLT = f"Playwright für Python fehlt ({e}); pip install playwright"
        yield None
        return
    p = sync_playwright().start()
    try:
        yield p
    finally:
        p.stop()


@pytest.fixture(scope="session")
def browser(_playwright):
    global _BROWSER_FEHLT
    if _playwright is None:
        pytest.skip(f"Browsertests übersprungen: {_BROWSER_FEHLT}")
    args = ["--no-proxy-server", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
            "--disable-features=Translate,OptimizationHints,MediaRouter", "--no-first-run"]
    pfad = m8.chromium_pfad()
    versuche = [{"executable_path": pfad}] if pfad else [{}, {"channel": "chrome"},
                                                          {"executable_path": "/usr/bin/google-chrome"}]
    fehler = []
    for v in versuche:
        try:
            b = _playwright.chromium.launch(headless=True, args=args, **v)
            break
        except Exception as e:  # noqa: BLE001
            fehler.append(f"{v or 'gebündeltes Chromium'}: {str(e).splitlines()[0][:200]}")
    else:
        _BROWSER_FEHLT = "kein Chromium startbar – " + "; ".join(fehler)
        pytest.skip(f"Browsertests übersprungen: {_BROWSER_FEHLT}")
    try:
        yield b
    finally:
        b.close()


@pytest.fixture
def starte_server(tmp_path):
    laufend: list[m8.LaufenderServer] = []

    def starte(*, mock: bool = True, anmeldung: bool | None = None, heute: str | None = m8.HEUTE,
               einrichten: bool = True, **felder):
        basis = tmp_path / f"server{len(laufend)}"
        s = m8.LaufenderServer(m8.m8_config(basis, mock=mock, anmeldung=anmeldung, heute=heute,
                                            einrichten=einrichten, **felder))
        laufend.append(s)
        return s
    yield starte
    for s in laufend:
        s.stop()


class _Beobachter:
    def __init__(self, herkunft: str) -> None:
        self.herkunft = herkunft
        self.fehler: list[str] = []
        self.csp: list[str] = []
        self.fremd: list[str] = []
        self.erlaubt_offline = False

    def anschliessen(self, seite) -> None:
        seite.on("pageerror", lambda e: self.fehler.append(str(e)))
        seite.on("console", self._konsole)
        seite.on("request", self._anfrage)

    def _konsole(self, msg) -> None:
        text = msg.text
        if "Content Security Policy" in text or "Content-Security-Policy" in text:
            self.csp.append(text)

    def _anfrage(self, req) -> None:
        if not m8.gleiche_herkunft(req.url, self.herkunft):
            self.fremd.append(req.url)

    def pruefe(self) -> None:
        assert not self.fehler, f"Unbehandelte Fehler der Seite: {self.fehler}"
        assert not self.csp, f"CSP-Verletzungen: {self.csp}"
        assert not self.fremd, f"Anfragen an fremde Herkünfte (oberflaeche.md 1 Nr. 3): {self.fremd}"


@pytest.fixture
def neue_seite(browser):
    kontexte = []

    def neu(server: m8.LaufenderServer, geraet: str = "desktop", *, ohne_anmeldung: bool = False,
            person: str | None = m8.PERSON, erfolgsmeldung: bool = False, **kw):
        optionen = {**m8.GERAETE[geraet], "locale": "de-DE", "timezone_id": "Europe/Berlin",
                    "reduced_motion": "reduce", "color_scheme": "light", "accept_downloads": True}
        optionen.update(kw)
        kontext = browser.new_context(**optionen)
        kontext.set_default_timeout(m8.WARTEN_MS)
        if person is not None:
            kontext.add_init_script(m8.person_skript(person))
        beobachter = _Beobachter(server.herkunft)
        kontexte.append((kontext, beobachter))
        if getattr(server.config, "anmeldung", False) and not ohne_anmeldung:
            r = kontext.request.post(server.url + "/api/anmeldung", data={"passwort": m8.PASSWORT})
            assert r.status == 200, f"Anmeldung im Browserkontext fehlgeschlagen: {r.status}"
        if erfolgsmeldung:
            from tests.hilfen import m32
            hilfe = kontext.new_page()
            m32.erfolgsmeldung_einschalten(hilfe, server)
            hilfe.close()
        seite = kontext.new_page()
        beobachter.anschliessen(seite)
        seite._kontor_beobachter = beobachter
        return seite
    yield neu
    fehler = []
    for kontext, beobachter in kontexte:
        try:
            beobachter.pruefe()
        except AssertionError as e:
            fehler.append(str(e))
        finally:
            kontext.close()
    assert not fehler, "\n".join(fehler)
