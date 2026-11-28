"""Screenshots für README und Dokumentation erzeugen (Feature ``screenshots``).

Baut die Demodaten (erfundener Haushalt, ``kontor.demodaten``) in einem temporären Verzeichnis, startet Kontor im
Mock-Modus auf einem freien lokalen Port und fotografiert ausgewählte Ansichten mit Playwright (Chromium).
Die Handy-Ansichten werden in einen schlichten, gezeichneten Handy-Rahmen gesetzt (eigene HTML-Seite, keine fremden
Bilder). Es kommen nur erfundene Angaben vor; keine andere Datenbank wird gelesen.

Aufruf im Wurzelverzeichnis des Repositories::

    python docs/screenshots/erzeugen.py [--heute JJJJ-MM-TT] [--nur NAME ...]

Voraussetzungen: ``pip install -e ".[test]"`` (Playwright) und ``python -m playwright install chromium``.
Die Bilder landen neben diesem Skript (``docs/screenshots/*.png``).
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import io
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ZIEL = pathlib.Path(__file__).resolve().parent
WURZEL = ZIEL.parents[1]

DESKTOP = {"width": 1440, "height": 900}
HANDY = {"width": 390, "height": 812}   # Anzeige unter der gezeichneten Statusleiste (390 × 844 mit Leiste)
LEISTE = 32
SCHAERFE = 2           # device_scale_factor: scharf auf hochauflösenden Bildschirmen
FARBEN = 256           # Bilder werden auf eine Palette reduziert (deutlich kleiner, für Oberflächen kaum sichtbar)

# Nur für die Bilder: Hinweisleiste des Mock-Modus und Branch-Anzeige im Fuß ausblenden. Die Bildunterschriften in
# der README sagen, dass es erfundene Demodaten sind.
STIL = ".mock-hinweis, .zweig-link { display: none !important; }"
PERSON = "Torsten"     # erste Person der Demodaten (pflege.PERSONEN); verhindert die Frage „Wer bist du?“


# ------------------------------------------------------------------------------------------------ Server

def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def server(verzeichnis: pathlib.Path, heute: dt.date):
    """Demodaten bauen und Kontor im Mock-Modus starten; liefert die Basisadresse."""
    sys.path.insert(0, str(WURZEL / "src"))
    from kontor import demodaten

    datenbank = verzeichnis / "demo.sqlite3"
    mockdaten = verzeichnis / "mock.json"
    with contextlib.redirect_stdout(io.StringIO()):
        demodaten.aufbauen(datenbank, mockdaten, heute=heute)
    port = _freier_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("KONTOR_")}
    env.update(KONTOR_DATENBANK=str(verzeichnis / "unbenutzt.sqlite3"), KONTOR_MOCK_MODUS="1",
               KONTOR_MOCK_DATENBANK=str(datenbank), KONTOR_MOCK_DATEN=str(mockdaten),
               KONTOR_MOCK_HEUTE=heute.isoformat(), KONTOR_ANMELDUNG="0", KONTOR_PLANER_STARTEN="0",
               KONTOR_HOST="127.0.0.1", KONTOR_PORT=str(port), KONTOR_LOG_STUFE="WARNING",
               PYTHONPATH=str(WURZEL / "src"))
    proc = subprocess.Popen([sys.executable, "-m", "kontor"], env=env, cwd=verzeichnis,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    basis = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(basis + "/", timeout=1).close()
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError("Kontor ist nicht gestartet:\n" + proc.stderr.read().decode(errors="replace"))
                time.sleep(0.2)
        else:
            raise RuntimeError("Kontor antwortet nicht.")
        yield basis
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(10)
        if proc.poll() is None:
            proc.kill()


# ------------------------------------------------------------------------------------------------ Bilder

def speichern(png: bytes, name: str) -> pathlib.Path:
    """PNG auf eine Palette reduzieren und unter ``docs/screenshots/<name>.png`` ablegen."""
    from PIL import Image

    bild = Image.open(io.BytesIO(png))
    if bild.mode == "RGBA":
        reduziert = bild.quantize(FARBEN, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    else:
        reduziert = bild.convert("RGB").quantize(FARBEN, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pfad = ZIEL / f"{name}.png"
    reduziert.save(pfad, optimize=True)
    return pfad


RAHMEN = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; background: transparent; }}
.handy {{ box-sizing: border-box; width: {aussen_b}px; height: {aussen_h}px; padding: {rand}px; margin: 24px;
  border-radius: 58px; background: linear-gradient(145deg, #3a3f47, #1b1e23 55%, #2a2e35);
  box-shadow: 0 0 0 2px #4b515a inset, 0 18px 40px rgba(0, 0, 0, .35); position: relative; }}
.handy::before, .handy::after {{ content: ""; position: absolute; width: 4px; border-radius: 2px; background: #2f343b; }}
.handy::before {{ left: -4px; top: 150px; height: 64px; }}
.handy::after {{ right: -4px; top: 190px; height: 96px; }}
.schirm {{ width: {b}px; height: {h}px; border-radius: 44px; overflow: hidden; position: relative; background: #000; }}
.leiste {{ height: {leiste}px; background: #1b1e23; color: #e6e8eb; font: 600 13px system-ui, sans-serif;
  display: flex; align-items: center; justify-content: space-between; padding: 0 28px; box-sizing: border-box; }}
.symbole {{ display: flex; gap: 5px; align-items: center; }}
.symbole i {{ display: block; background: #e6e8eb; border-radius: 1px; }}
.schirm img {{ width: 100%; height: {h_bild}px; display: block; }}
.kamera {{ position: absolute; top: 10px; left: 50%; width: 12px; height: 12px; margin-left: -6px; border-radius: 50%;
  background: #0b0c0e; box-shadow: 0 0 0 2px #2a2e35; }}
</style></head><body><div class="handy"><div class="schirm">
<div class="leiste"><span>9:41</span><span class="symbole"><i style="width:3px;height:5px"></i><i style="width:3px;height:7px"></i>
<i style="width:3px;height:9px"></i><i style="width:3px;height:11px"></i><i style="width:20px;height:10px;margin-left:4px;border-radius:3px"></i></span></div>
<img src="data:image/png;base64,{bild}" alt=""><div class="kamera"></div></div></div></body></html>"""


def im_rahmen(browser, png: bytes) -> bytes:
    """Handy-Screenshot in einen neutralen, gezeichneten Rahmen setzen (transparenter Hintergrund)."""
    rand = 14
    b, h = HANDY["width"], HANDY["height"] + LEISTE
    seite = RAHMEN.format(b=b, h=h, h_bild=HANDY["height"], leiste=LEISTE, rand=rand, aussen_b=b + 2 * rand, aussen_h=h + 2 * rand,
                          bild=base64.b64encode(png).decode())
    ctx = browser.new_context(viewport={"width": b + 2 * rand + 48, "height": h + 2 * rand + 64},
                              device_scale_factor=SCHAERFE)
    try:
        p = ctx.new_page()
        p.set_content(seite)
        p.wait_for_load_state("load")
        return p.locator(".handy").screenshot(omit_background=True, animations="disabled")
    finally:
        ctx.close()


# ------------------------------------------------------------------------------------------------ Ansichten

def _bereit(p) -> None:
    p.add_style_tag(content=STIL)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(600)          # Diagramme und Übergänge


def _oeffnen(p, basis: str, pfad: str) -> None:
    p.goto(basis + pfad)
    _bereit(p)


def _id_mit(basis: str, konto: int, bedingung) -> int:
    """Jüngste Buchung des Kontos, auf die ``bedingung`` zutrifft (über die REST-Schnittstelle)."""
    import json
    seite, treffer = 1, None
    while True:
        with urllib.request.urlopen(f"{basis}/api/buchungen?konto_id={konto}&pro_seite=500&seite={seite}") as a:
            d = json.load(a)
        for b in d["eintraege"]:
            if bedingung(b) and (treffer is None or (b["datum"], b["id"]) > (treffer["datum"], treffer["id"])):
                treffer = b
        if len(d["eintraege"]) < 500:
            break
        seite += 1
    if treffer is None:
        raise RuntimeError("Keine passende Buchung in den Demodaten gefunden.")
    return treffer["id"]


def kontoansicht(p, basis, heute):
    """Girokonto mit gewählter Buchung samt Mail-Beleg in den Einzelheiten."""
    bid = _id_mit(basis, 1, lambda b: b["belege"] and b["kategorie_id"] is not None)
    _oeffnen(p, basis, "/konten/1")
    zeile = p.locator(f'[data-testid="buchung-{bid}"]')
    zeile.scroll_into_view_if_needed()
    zeile.click()
    p.wait_for_timeout(800)


def monatsbericht(p, basis, heute):
    _oeffnen(p, basis, "/berichte?art=monat")


def regeleditor(p, basis, heute):
    """Regel „Restaurant am Wochenende“ im Editor, mit Testbereich."""
    _oeffnen(p, basis, "/regeln")
    karte = p.get_by_text("Restaurant am Wochenende").first.locator("xpath=ancestor::*[.//button[normalize-space()='Bearbeiten...' or normalize-space()='Bearbeiten…']][1]")
    karte.get_by_role("button", name="Bearbeiten").first.click()
    p.wait_for_selector('[data-testid="test-liste"] li')
    p.wait_for_timeout(800)


def _rest(basis: str, methode: str, pfad: str, daten: object) -> dict:
    import json
    anfrage = urllib.request.Request(basis + pfad, method=methode, data=json.dumps(daten).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(anfrage) as a:
        return json.load(a)


def lernmodell(p, basis, heute: dt.date):
    """„Warum dieser Vorschlag?“: eine von Hand erfasste Café-Rechnung ohne Kategorie, für die das Lernmodell
    einen Vorschlag macht. Die Buchung entsteht nur in der temporären Demo-Datenbank (REST)."""
    tag = heute - dt.timedelta(days=1)
    b = _rest(basis, "POST", "/api/buchungen/erfassen", {
        "art": "ausgabe", "datum": tag.isoformat(), "konto_id": 1, "betrag": 1260, "empfaenger_name": "Café Zeitlos",
        "verwendungszweck": f"KARTENZAHLUNG {tag:%d.%m} 15:20 CAFÉ ZEITLOS", "status": "vorlaeufig"})
    _rest(basis, "POST", "/api/lernmodell/anwenden", {"buchung_ids": [b["id"]]})
    _oeffnen(p, basis, "/konten/1")
    p.locator(f'[data-testid="buchung-{b["id"]}"]').click()
    p.locator('[data-testid="lern-warum"] summary').first.click()
    p.wait_for_selector('[data-testid="lern-zweck"]')
    p.wait_for_timeout(500)


def einstellungen(p, basis, heute):
    _oeffnen(p, basis, "/einstellungen?bereich=daten")


def handy_konto(p, basis, heute):
    _oeffnen(p, basis, "/konten/1")


def handy_bericht(p, basis, heute):
    _oeffnen(p, basis, "/berichte?art=monat")


# Name, Funktion, Handy?, Designs
ANSICHTEN = [
    ("kontoansicht", kontoansicht, False, ("dunkel", "hell")),
    ("monatsbericht", monatsbericht, False, ("dunkel",)),
    ("regeleditor", regeleditor, False, ("dunkel",)),
    ("lernmodell", lernmodell, False, ("dunkel",)),
    ("einstellungen", einstellungen, False, ("dunkel",)),
    ("handy-konto", handy_konto, True, ("dunkel",)),
    ("handy-bericht", handy_bericht, True, ("dunkel",)),
]


def fotografieren(basis: str, heute: dt.date, nur: set[str]) -> list[pathlib.Path]:
    from playwright.sync_api import sync_playwright

    fertig = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(   # deutsche Texte auch in Browser-Elementen (Dateiauswahl)
            channel="chromium", args=["--lang=de-DE"], env={**os.environ, "LANG": "de_DE.UTF-8", "LANGUAGE": "de"})
        try:
            for name, funktion, handy, designs in ANSICHTEN:
                if nur and name not in nur:
                    continue
                for design in designs:
                    optionen = dict(viewport=HANDY if handy else DESKTOP, device_scale_factor=SCHAERFE,
                                    color_scheme="dark" if design == "dunkel" else "light", locale="de-DE",
                                    timezone_id="Europe/Berlin")
                    if handy:
                        optionen.update(is_mobile=True, has_touch=True)
                    ctx = browser.new_context(**optionen)
                    ctx.add_init_script(f"try {{ localStorage.setItem('kontor.person', '{PERSON}'); }} catch (e) {{}}")
                    try:
                        p = ctx.new_page()
                        funktion(p, basis, heute)
                        p.evaluate("() => document.activeElement && document.activeElement.blur()")   # kein Fokusrahmen
                        p.wait_for_timeout(200)
                        png = p.screenshot(animations="disabled", caret="hide")
                    finally:
                        ctx.close()
                    if handy:
                        png = im_rahmen(browser, png)
                    datei = f"{name}-{design}"
                    fertig.append(speichern(png, datei))
                    print(f"{datei}.png")
        finally:
            browser.close()
    return fertig


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(prog="python docs/screenshots/erzeugen.py", description=__doc__.split("\n\n")[0])
    a.add_argument("--heute", type=dt.date.fromisoformat, default=dt.date.today(),
                   help="Bezugstag der Demodaten JJJJ-MM-TT (Vorgabe: heute)")
    a.add_argument("--nur", nargs="*", default=[], help="nur diese Ansichten (Namen aus ANSICHTEN)")
    o = a.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="kontor-screenshots-") as tmp, server(pathlib.Path(tmp), o.heute) as basis:
        fotografieren(basis, o.heute, set(o.nur))
    return 0


if __name__ == "__main__":
    sys.exit(main())
