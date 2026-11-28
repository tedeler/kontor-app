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
import json
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

DESKTOP = {"width": 1440, "height": 900}      # Titelbild
GALERIE = {"width": 1200, "height": 668}      # Galerie: nur der Inhalt rechts der Navigation, etwa 16:10
HANDY = {"width": 390, "height": 812}   # Anzeige unter der gezeichneten Statusleiste (390 × 844 mit Leiste)
LEISTE = 32
SCHAERFE = 2           # device_scale_factor: scharf auf hochauflösenden Bildschirmen
FARBEN = 256           # Bilder werden auf eine Palette reduziert (deutlich kleiner, für Oberflächen kaum sichtbar)

# Nur für die Bilder: Hinweisleiste des Mock-Modus und Branch-Anzeige im Fuß ausblenden. Die Bildunterschriften in
# der README sagen, dass es erfundene Demodaten sind.
STIL = ".mock-hinweis, .zweig-link { display: none !important; }"
PERSON = "Anna"        # erste Person der Demodaten (demodaten.DEMO_BENUTZER); verhindert die Frage „Wer bist du?“


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
               KONTOR_MOCK_HEUTE=heute.isoformat(), KONTOR_ANMELDUNG="0", KONTOR_BENUTZER="Anna,Ben", KONTOR_PLANER_STARTEN="0",
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
    treffer = max((b for b in _alle_buchungen(basis, konto) if bedingung(b)),
                  key=lambda b: (b["datum"], b["id"]), default=None)
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
    # kleinster Vorfahr des Regelnamens, der einen Knopf „Bearbeiten…“ enthält: die Karte dieser Regel
    karte = p.get_by_text("Restaurant am Wochenende").first.locator(
        "xpath=ancestor::*[.//button[starts-with(normalize-space(), 'Bearbeiten')]][1]")
    karte.get_by_role("button", name="Bearbeiten").first.click()
    p.wait_for_selector('[data-testid="test-liste"] li')
    p.wait_for_timeout(800)


def _rest(basis: str, methode: str, pfad: str, daten: object) -> dict:
    anfrage = urllib.request.Request(basis + pfad, method=methode, data=json.dumps(daten).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(anfrage) as a:
        return json.load(a)


def _alle_buchungen(basis: str, konto: int) -> list[dict]:
    alle, seite = [], 1
    while True:
        with urllib.request.urlopen(f"{basis}/api/buchungen?konto_id={konto}&pro_seite=500&seite={seite}") as a:
            d = json.load(a)
        alle += d["eintraege"]
        if len(d["eintraege"]) < 500:
            return alle
        seite += 1


# Zuordnung der noch unkategorisierten Demo-Buchungen beim Aufräumen (Teil des Empfängernamens → Kategorie)
NACHTRAG = {"Gartencenter": "Einkäufe", "Schuhhaus": "Einkäufe", "Eisdiele": "Restaurant", "Stadtwerke": "Energie",
            "Tierarzt": "Versicherungen & Gesundheit"}
OFFEN_LASSEN = 2      # so viele der neuesten Vorschläge bleiben offen (gelb), dazu eine unkategorisierte (rot)


def aufraeumen(basis: str) -> None:
    """Girokonto so herrichten, wie es nach der regelmäßigen Durchsicht aussieht.

    Die Demodaten lassen die letzten Wochen absichtlich unbearbeitet (zum Vorführen von Abruf und Vorschlägen). Auf
    den Bildern sollen offene Buchungen die Ausnahme sein: Bis auf die neuesten Vorschläge und eine unkategorisierte
    Buchung werden Vorschläge angenommen, Unkategorisiertes zugeordnet und alles bestätigt – über REST, nur in der
    temporären Demo-Datenbank."""
    kategorien = {k["name"]: k["id"] for k in json.load(urllib.request.urlopen(basis + "/api/konten"))}
    offen = sorted((b for b in _alle_buchungen(basis, 1) if b["status"] in ("vorlaeufig", "importiert")),
                   key=lambda b: (b["datum"], b["id"]), reverse=True)
    vorschlaege = [b for b in offen if b["vorschlag"]]
    unkategorisiert = [b for b in offen if b["kategorie_id"] is None and b["empfaenger"]]
    bleiben = {b["id"] for b in vorschlaege[:OFFEN_LASSEN]} | {b["id"] for b in unkategorisiert[:1]}
    annehmen = [b["id"] for b in vorschlaege if b["id"] not in bleiben]
    if annehmen:
        _rest(basis, "POST", "/api/buchungen/mehrfach/vorschlag", {"buchung_ids": annehmen, "aktion": "annehmen"})
    for b in unkategorisiert:
        ziel = next((k for teil, k in NACHTRAG.items() if teil in b["empfaenger"]["name"]), None)
        if b["id"] not in bleiben and ziel in kategorien:
            _rest(basis, "PUT", f"/api/buchungen/{b['id']}/kategorie", {"kategorie_id": kategorien[ziel]})
    rest = [b["id"] for b in _alle_buchungen(basis, 1)
            if b["status"] in ("vorlaeufig", "importiert") and b["id"] not in bleiben]
    if rest:
        _rest(basis, "POST", "/api/buchungen/mehrfach/aendern", {"buchung_ids": rest, "status": "bestaetigt"})
    # wer bestätigt hat, wie in den Demodaten: abwechselnd die beiden erfundenen Personen
    from kontor.demodaten import PERSONENTAGS
    tags = {t["name"]: t["id"] for t in json.load(urllib.request.urlopen(basis + "/api/tags"))}
    for person in PERSONENTAGS:
        ids = [i for i in set(annehmen) | set(rest) if PERSONENTAGS[i % 3 == 0] == person]
        if ids and person in tags:
            _rest(basis, "POST", "/api/buchungen/mehrfach/tags", {"buchung_ids": ids, "hinzufuegen": [tags[person]]})


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
    # Einzelheiten so weit scrollen, dass Vorschlag und Begründung zu sehen sind
    p.locator('[data-testid="details-vorschlag"]').evaluate("e => e.scrollIntoView({ block: 'start' })")
    p.wait_for_timeout(500)


def einstellungen(p, basis, heute):
    _oeffnen(p, basis, "/einstellungen?bereich=daten")


def handy_konto(p, basis, heute):
    _oeffnen(p, basis, "/konten/1")


def handy_bericht(p, basis, heute):
    _oeffnen(p, basis, "/berichte?art=monat")


LINK_BASIS = "https://kontor.example.net"   # statt der zufälligen lokalen Adresse im geteilten Link


def geteilter_text(p, basis: str) -> str:
    """Kurztext, den Kontor beim „Teilen…“ einer Buchung erzeugt – über das Kontextmenü wie im Browser. Die
    Teilen-Funktion des Geräts wird nur abgefangen, damit der Text hier ankommt."""
    bid = _id_mit(basis, 1, lambda b: b["kategorie_id"] is None and b["empfaenger"] and b["status"] == "importiert")
    ctx = p.context.browser.new_context(viewport=GALERIE, locale="de-DE", timezone_id="Europe/Berlin")
    try:
        ctx.add_init_script("try { localStorage.setItem('kontor.person', '%s'); } catch (e) {}"
                            " navigator.share = async (d) => { window.__geteilt = d.text; };" % PERSON)
        q = ctx.new_page()
        _oeffnen(q, basis, "/konten/1")
        q.locator(f'[data-testid="buchung-{bid}"]').click(button="right")
        q.locator('[data-testid="km-teilen"]').click()
        q.wait_for_function("() => window.__geteilt")
        return q.evaluate("() => window.__geteilt").replace(basis, LINK_BASIS)
    finally:
        ctx.close()


CHAT = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><style>
html, body {{ margin: 0; height: 100%; background: #12151a; color: #e6e8eb; font: 19px/1.35 system-ui, sans-serif; }}
.kopf {{ display: flex; align-items: center; gap: 10px; padding: 12px 16px; background: #1b1f25;
  border-bottom: 1px solid #262b33; }}
.bild {{ width: 36px; height: 36px; border-radius: 50%; background: #3c5a73; display: grid; place-items: center;
  font-weight: 600; }}
.name {{ font-weight: 600; }} .status {{ font-size: 14px; color: #8b94a0; }}
.verlauf {{ padding: 14px 12px; display: flex; flex-direction: column; gap: 8px; }}
.tag {{ align-self: center; font-size: 14px; color: #8b94a0; background: #1b1f25; padding: 3px 10px;
  border-radius: 10px; }}
.blase {{ max-width: 90%; padding: 8px 11px 6px; border-radius: 14px; white-space: pre-wrap; word-break: break-word; }}
.blase .zeit {{ display: block; text-align: right; font-size: 13px; color: #9aa6b2; margin-top: 2px; }}
.ich {{ align-self: flex-end; background: #2c4a63; border-bottom-right-radius: 4px; }}
.du {{ align-self: flex-start; background: #262b33; border-bottom-left-radius: 4px; }}
.zitat {{ border-left: 3px solid #7fb0d8; padding-left: 8px; color: #c9d1da; }}
.link {{ color: #8cc4f0; text-decoration: underline; }}
.eingabe {{ position: fixed; left: 0; right: 0; bottom: 0; display: flex; gap: 8px; padding: 10px 22px 26px;
  background: #1b1f25; }}
.eingabe div {{ flex: 1; background: #262b33; border-radius: 18px; padding: 9px 14px; color: #8b94a0; }}
</style></head><body>
<div class="kopf"><div class="bild">{initiale}</div><div><div class="name">{name}</div>
<div class="status">online</div></div></div>
<div class="verlauf"><div class="tag">Heute</div>
<div class="blase ich">{text}<span class="zeit">18:42</span></div>
<div class="blase ich">Weißt du, was das war?<span class="zeit">18:42</span></div>
<div class="blase du">Impfung für Minka 🐱 – ordne ich gleich zu.<span class="zeit">18:47</span></div>
</div><div class="eingabe"><div>Nachricht</div></div></body></html>"""


def _wie_im_chat(text: str) -> str:
    """Kurztext so darstellen, wie Messenger ihn zeigen: *fett*, „> “ als Zitat, Link unterstrichen."""
    import html
    import re
    zeilen = []
    for z in html.escape(text).split("\n"):
        z = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", z)
        if z.startswith("&gt; "):
            z = f'<div class="zitat">{z[5:]}</div>'
        elif z.startswith("http"):
            z = f'<span class="link">{z}</span>'
        zeilen.append(z)
    return "\n".join(zeilen).replace("</div>\n", "</div>")


def handy_teilen(p, basis, heute):
    """„Teilen…“ einer Buchung: der erzeugte Kurztext in einem schlichten, neutral gestalteten Chat."""
    text = geteilter_text(p, basis)
    from kontor.demodaten import DEMO_BENUTZER
    andere = DEMO_BENUTZER[1]
    p.set_content(CHAT.format(text=_wie_im_chat(text), name=andere, initiale=andere[:1]))
    p.wait_for_timeout(300)


# Name, Funktion, Art (titel, galerie, handy), Designs
ANSICHTEN = [
    ("kontoansicht", kontoansicht, "titel", ("dunkel", "hell")),
    ("monatsbericht", monatsbericht, "galerie", ("dunkel",)),
    ("regeleditor", regeleditor, "galerie", ("dunkel",)),
    ("lernmodell", lernmodell, "galerie", ("dunkel",)),
    ("einstellungen", einstellungen, "galerie", ("dunkel",)),
    ("handy-konto", handy_konto, "handy", ("dunkel",)),
    ("handy-bericht", handy_bericht, "handy", ("dunkel",)),
    ("handy-teilen", handy_teilen, "handy", ("dunkel",)),
]


def ausschnitt(p) -> dict:
    """Galeriebilder zeigen nur den Inhalt: ohne Navigation links und ohne Kopfzeile (in kleinen Bildern lesbarer).
    Ist ein Dialog offen, zeigt das Bild den Dialog (oberer Teil im Seitenverhältnis 16:10)."""
    d = p.evaluate("""() => { const d = document.querySelector('[role="dialog"]');
                              return d ? d.getBoundingClientRect().toJSON() : null; }""")
    if d:
        return {"x": d["x"], "y": d["y"], "width": d["width"], "height": round(d["width"] / 1.6)}
    r = p.evaluate("""() => ({ x: document.querySelector("nav.navigation").getBoundingClientRect().right,
                               y: document.querySelector("header.kopf").getBoundingClientRect().bottom })""")
    v = p.viewport_size
    return {"x": r["x"], "y": r["y"], "width": v["width"] - r["x"], "height": v["height"] - r["y"]}


# Abweichende Fenstergröße und Browser-Speicher je Ansicht
FENSTER = {
    "regeleditor": DESKTOP,
    # breite Einzelheiten, damit die Begründung lesbar ist; Höhe so, dass der Ausschnitt etwa 16:10 bleibt
    "lernmodell": {"width": 1440, "height": 818},
}
SPEICHER = {
    "lernmodell": {"kontor.layout": {"version": 1, "panels": {
        "kategorien": {"bereich": "links", "position": 0, "breite": 240, "eingeklappt": False},
        "details": {"bereich": "rechts", "position": 1, "breite": 560, "eingeklappt": False, "hoehe": 260}}}},
}


def fotografieren(basis: str, heute: dt.date, nur: set[str]) -> list[pathlib.Path]:
    from playwright.sync_api import sync_playwright

    fertig = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(   # deutsche Texte auch in Browser-Elementen (Dateiauswahl)
            channel="chromium", args=["--lang=de-DE"], env={**os.environ, "LANG": "de_DE.UTF-8", "LANGUAGE": "de"})
        try:
            for name, funktion, art, designs in ANSICHTEN:
                handy = art == "handy"
                if nur and name not in nur:
                    continue
                for design in designs:
                    fenster = FENSTER.get(name) or {"titel": DESKTOP, "galerie": GALERIE, "handy": HANDY}[art]
                    optionen = {"viewport": fenster, "device_scale_factor": SCHAERFE, "locale": "de-DE",
                                "color_scheme": "dark" if design == "dunkel" else "light",
                                "timezone_id": "Europe/Berlin"}
                    if handy:
                        optionen.update(is_mobile=True, has_touch=True)
                    ctx = browser.new_context(**optionen)
                    speicher = {"kontor.person": PERSON} | {k: json.dumps(v) for k, v in SPEICHER.get(name, {}).items()}
                    ctx.add_init_script("try { for (const [k, v] of Object.entries(" + json.dumps(speicher) + "))"
                                        " localStorage.setItem(k, v); } catch (e) {}")
                    try:
                        p = ctx.new_page()
                        funktion(p, basis, heute)
                        p.evaluate("() => document.activeElement && document.activeElement.blur()")   # kein Fokusrahmen
                        p.wait_for_timeout(200)
                        png = p.screenshot(animations="disabled", caret="hide",
                                           clip=ausschnitt(p) if art == "galerie" else None)
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
        aufraeumen(basis)
        fotografieren(basis, o.heute, set(o.nur))
    return 0


if __name__ == "__main__":
    sys.exit(main())
