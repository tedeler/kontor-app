"""Hilfen für Meilenstein-8-Tests (Oberfläche, ``oberflaeche.md``) – nur über die Spezifikation.

- ``LaufenderServer``: ``kontor.app.create_app(config)`` unter uvicorn auf 127.0.0.1 in einem Thread
  (``oberflaeche.md`` 21). ``server.api`` ist eine ``Api`` (Vertragsprüfung wie überall) über HTTP gegen
  dieselbe laufende App.
- Browserhilfen: Öffnen und Warten auf Zustände, Gesten (CDP-Touch), Maus-Drag, Betragsformat.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import kontor
from .api import Api, anmeldelauf_aktiv, neue_config
from .pfade import FIXTURES

M8 = FIXTURES / "m8"
OBERFLAECHE = M8 / "oberflaeche.kmy"
VIELE = M8 / "viele.kmy"
HEUTE = "2024-12-31"
PASSWORT = "Kontor-Oberflaeche-2026"
DESKTOP = {"viewport": {"width": 1280, "height": 800}, "device_scale_factor": 1}
HANDY = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}
GERAETE = {"desktop": DESKTOP, "handy": HANDY}
#: Einträge ``nav-<ziel>`` der Navigation in Dokumentreihenfolge (ab M28 in Themengruppen, oberflaeche.md 37.2,
#: E-254; ``nav-wiederkehrend`` entfällt). Ziel, Pfad, Seitentitel (oberflaeche.md 3).
NAV = [("uebersicht", "/", "Finanzübersicht"), ("konten", "/konten", "Konten"),
       ("kategorien", "/kategorien", "Kategorien"), ("empfaenger", "/empfaenger", "Empfänger"),
       ("kredite", "/kredite", "Kredite"), ("berichte", "/berichte", "Berichte"), ("regeln", "/regeln", "Regeln"),
       ("vorlagen", "/vorlagen", "Split-Vorlagen"), ("dubletten", "/dubletten", "Dubletten"),
       ("import", "/import", "Import"), ("sync", "/sync", "Synchronisation"),
       ("protokoll", "/protokoll", "Änderungsprotokoll"), ("einstellungen", "/einstellungen", "Einstellungen")]
#: Die fest geordneten Links der Navigation (``a[data-testid]``) in Dokumentreihenfolge mit Ziel (37.2; ab M32
#: 41.1: ``navlink-tags`` nach Kategorien, ohne ``navlink-statistik``, E-306/E-307)
NAV_LINKS = [("nav-uebersicht", "/"), ("nav-konten", "/konten"), ("nav-kategorien", "/kategorien"),
             ("navlink-tags", "/tags"), ("nav-empfaenger", "/empfaenger"), ("nav-kredite", "/kredite"),
             ("navlink-erwartet", "/erwartet"), ("navlink-mail", "/mail"), ("nav-berichte", "/berichte"),
             ("nav-regeln", "/regeln"), ("nav-vorlagen", "/vorlagen"), ("nav-dubletten", "/dubletten"),
             ("nav-import", "/import"), ("nav-sync", "/sync"), ("nav-protokoll", "/protokoll"),
             ("nav-einstellungen", "/einstellungen")]
#: Links mit freier Stelle in ihrer Gruppe (41.1): Kennung → (Gruppe, Ziel); am Handy nicht sichtbar
NAV_LOSE = {"navlink-konfiguration": ("betrieb", "/konfiguration")}
#: Grenzen der Gruppen in NAV_LINKS (ohne NAV_LOSE)
NAV_GRUPPEN_SCHNITTE = [(0, 6), (6, 8), (8, 9), (9, 12), (12, 16)]
NAV_GRUPPEN = ["buchhaltung", "zahlungen", "auswertung", "regeln", "betrieb"]
#: Alt+1 … Alt+7 (37.2; Alt+8 ohne Wirkung)
ALT_ZIELE = [("uebersicht", "/"), ("konten", "/konten"), ("kategorien", "/kategorien"), ("kredite", "/kredite"),
             ("berichte", "/berichte"), ("import", "/import"), ("einstellungen", "/einstellungen")]
#: „Gehe zu“-Einträge der Befehlspalette in dieser Reihenfolge (37.2)
PALETTE_GEHE = ["uebersicht", "konten", "kategorien", "kredite", "berichte", "import", "einstellungen", "protokoll",
                "empfaenger", "regeln", "vorlagen", "dubletten", "sync", "erwartet", "mail",
                "benachrichtigungen"]
#: Ab M32 (41.1, E-306): Einträge mit freier Stelle unter den „Gehe zu“-Einträgen; ``statistik`` entfällt
GEHE_LOSE = ["tags", "konfiguration"]


def ohne_lose_links(ids: list) -> list:
    """Navigationseinträge ohne die frei stehenden (``NAV_LOSE``); Einträge als Kennung oder [Kennung, …]."""
    return [x for x in ids if (x[0] if isinstance(x, (list, tuple)) else x) not in NAV_LOSE]


def gehe_geordnet(gehe: list[str]) -> list[str]:
    """„Gehe zu“-Kennungen ohne die frei stehenden (``GEHE_LOSE``); prüft, dass diese genau einmal vorkommen."""
    for z in GEHE_LOSE:
        assert gehe.count(f"befehl-gehe-{z}") == 1, f"befehl-gehe-{z} fehlt oder doppelt: {gehe}"
    return [x for x in gehe if x.removeprefix("befehl-gehe-") not in GEHE_LOSE]
WARTEN_MS = 10_000
#: Person, die alle Browsertests vorab setzen (oberflaeche.md 37.1, M28, E-253)
PERSON = "Torsten"


def person_skript(person: str) -> str:
    """Init-Skript: merkt die Person im Browser, bevor die Hülle startet (M28 1, letzter Punkt). Ist der
    Speicher gesperrt, bleibt es wirkungslos; dann beantwortet ``person_waehlen`` den Pflichtdialog."""
    return ("try { if (!localStorage.getItem('kontor.person')) localStorage.setItem('kontor.person', "
            + json.dumps(person) + "); } catch (e) {}")


def person_waehlen(seite, person: str = PERSON, *, pflicht: bool = True) -> None:
    """Beantwortet den Pflichtdialog ``person-dialog`` (M28 1) über ``person-<name>`` und wartet auf das Neuladen.
    ``pflicht=True``: der Dialog muss erscheinen (z. B. bei gesperrtem Speicher)."""
    from playwright.sync_api import expect

    dialog = tid(seite, "person-dialog")
    if pflicht:
        expect(dialog).to_be_visible()
    elif not (dialog.count() and dialog.is_visible()):
        return
    tid(seite, f"person-{person.lower()}").click()
    expect(tid(seite, "person-dialog")).to_be_hidden()
    expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja", timeout=WARTEN_MS)


def lade_erwartung(name: str = "oberflaeche") -> dict:
    return json.loads((M8 / f"{name}.erwartung.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ Server
def _freier_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LaufenderServer:
    """Die App unter uvicorn auf 127.0.0.1 (eigener Thread, eigene Ereignisschleife)."""

    def __init__(self, config) -> None:
        import uvicorn  # kommt mit der Anwendung (betrieb.md 2)

        self.config = config
        self.app = kontor.create_app(config)
        self.port = _freier_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.herkunft = self.url
        cfg = uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="on",
                             proxy_headers=False, server_header=False, access_log=False)
        self._server = uvicorn.Server(cfg)
        self._thread = threading.Thread(target=self._server.run, name=f"kontor-m8-{self.port}", daemon=True)
        self._thread.start()
        ende = time.monotonic() + 30
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > ende:
                raise RuntimeError("Server der App startet nicht (uvicorn)")
            time.sleep(0.02)
        self.api = http_api(self)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=30)
        try:
            self.api.client.close()
        except Exception:  # noqa: BLE001
            pass


def http_api(server: LaufenderServer) -> Api:
    """``Api`` (mit Vertragsprüfung) über HTTP gegen die laufende App; meldet sich bei Bedarf an."""
    import httpx

    api = Api.__new__(Api)
    api.config, api.app, api.csrf = server.config, server.app, None
    api.modus_erwartet = "mock" if server.config.mock_modus else "echt"
    api.client = httpx.Client(base_url=server.url, trust_env=False, timeout=60, follow_redirects=False)
    if getattr(server.config, "anmeldung", False) and kontor.modul("kontor.anmeldung").ist_eingerichtet(server.config):
        r = api.client.post("/api/anmeldung", json={"passwort": PASSWORT})
        assert r.status_code == 200, f"Anmeldung der Prüf-API fehlgeschlagen: {r.status_code} {r.text[:300]}"
        api.csrf = r.json()["csrf_token"]
    return api


def m8_config(basis: Path, *, mock: bool = True, anmeldung: bool | None = None, heute: str | None = HEUTE,
              einrichten: bool = True, **felder):
    """Konfiguration für Browsertests: Mock-Modus mit fester Uhr; Anmeldung im Anmeldelauf (E-125) an."""
    import datetime as dt

    if anmeldung is None:
        anmeldung = anmeldelauf_aktiv()
    if mock:
        felder.setdefault("mock_modus", True)
        if heute:
            felder.setdefault("mock_heute", dt.date.fromisoformat(heute))
    config = neue_config(basis, anmeldung=anmeldung, **felder)
    if anmeldung and einrichten:
        kontor.modul("kontor.anmeldung").passwort_setzen(config, PASSWORT)
    return config


# ------------------------------------------------------------------ Daten
def importiere(api: Api, pfad: Path = OBERFLAECHE) -> dict:
    erg = api.import_kmy(pfad, erwartet=200).daten
    assert erg["erfolgreich"], erg["fehler"]
    return erg


class Ids:
    """Zuordnung extern_id → REST-ID für Konten, Empfänger, Tags und Buchungen."""

    def __init__(self, api: Api) -> None:
        self.konto = {k["extern_id"]: k["id"] for k in api.konten() if k["extern_id"]}
        self.empfaenger = {e["extern_id"]: e["id"] for e in api.get("/api/empfaenger", erwartet=200).daten
                           if e["extern_id"]}
        self.empfaenger_name = {e["name"]: e["id"] for e in api.get("/api/empfaenger", erwartet=200).daten}
        self.tag = {t["extern_id"]: t["id"] for t in api.get("/api/tags", erwartet=200).daten if t["extern_id"]}
        self.buchung: dict[str, int] = {}
        for b in api.alle_buchungen():
            for e in b["extern_ids"]:
                self.buchung[e] = b["id"]


def oberflaeche(server: LaufenderServer) -> tuple[dict, Ids]:
    importiere(server.api)
    erw = lade_erwartung()
    return erw, Ids(server.api)


def _wahrheit_je_id(erw: dict, ids: Ids) -> dict[int, dict]:
    nach_extern = {b["extern_id"]: b for b in erw["buchungen"]}
    return {bid: nach_extern[e] for e, bid in ids.buchung.items() if e in nach_extern}


def ist_kategorisierbar(erw: dict, b: dict) -> bool:
    """datenmodell.md 3.2 nach der bekannten Wahrheit: genau ein Gegensplit (Konto, das kein Bestandskonto ist)."""
    kein_bestand = {k["extern_id"] for k in erw["konten"] if k["ist_kategorie"] or k["art"] == "eigenkapital"}
    return sum(1 for s in b["splits"] if s["konto_extern_id"] in kein_bestand) == 1


def kategorisierbare(erw: dict, ids: Ids, reihen: list[int], anzahl: int = 1, *, ohne: tuple[int, ...] = (),
                     ab: int = 0, folge: bool = False) -> list[int]:
    """``anzahl`` Zeilen aus ``reihen`` (ab Position ``ab``), die nach der bekannten Wahrheit kategorisierbar sind
    und deren Kategorie keine der REST-IDs aus ``ohne`` ist (W-007: nie nach Listenposition auf eine Umbuchung
    oder Splitbuchung treffen). ``folge=True``: lückenlos benachbarte Zeilen (für Umschalt-Bereiche)."""
    wahr = _wahrheit_je_id(erw, ids)
    ohne_ext = {e for e, kid in ids.konto.items() if kid in ohne}

    def passt(bid: int) -> bool:
        b = wahr[bid]
        return ist_kategorisierbar(erw, b) and b["kategorie_extern_id"] not in ohne_ext
    if folge:
        for i in range(ab, len(reihen) - anzahl + 1):
            if all(passt(x) for x in reihen[i:i + anzahl]):
                return reihen[i:i + anzahl]
    else:
        treffer = [x for x in reihen[ab:] if passt(x)][:anzahl]
        if len(treffer) == anzahl:
            return treffer
    raise AssertionError(f"Testdaten: keine {anzahl} kategorisierbaren Zeilen ab Position {ab}")


def umbuchung_zeile(erw: dict, ids: Ids, reihen: list[int]) -> int:
    """Erste Zeile aus ``reihen``, die nach der bekannten Wahrheit eine Umbuchung zwischen Bestandskonten ist."""
    wahr = _wahrheit_je_id(erw, ids)
    return next(x for x in reihen if wahr[x]["umbuchung"] and not ist_kategorisierbar(erw, wahr[x]))


def rest_liste(api: Api, konto_id: int, **params) -> list[int]:
    """IDs der Buchungsliste wie die Oberfläche sie zeigen muss (oberflaeche.md 7.2), alle Seiten."""
    params.setdefault("sortierung", "-datum")
    return [b["id"] for b in api.alle_buchungen(konto_id=konto_id, **params)]


def betrag_text(cent: int) -> str:
    """oberflaeche.md 5: Intl.NumberFormat('de-DE', EUR)."""
    v = "-" if cent < 0 else ""
    euro, rest = divmod(abs(cent), 100)
    gruppen = f"{euro:,}".replace(",", ".")
    return f"{v}{gruppen},{rest:02d} €"


def eingabe_betrag(cent: int) -> str:
    """Betragseingabe in deutscher Schreibweise (oberflaeche.md 5)."""
    v = "-" if cent < 0 else ""
    euro, rest = divmod(abs(cent), 100)
    return f"{v}{euro},{rest:02d}"


def lies_betrag(text: str) -> int:
    """Betragseingabe nach oberflaeche.md 5 (deutsch, Tausenderpunkte erlaubt) → Cent."""
    import re

    s = text.strip()
    m = re.fullmatch(r"(-?)((?:\d{1,3}(?:\.\d{3})+)|\d+)(?:,(\d{1,2}))?", s)
    assert m, f"keine gültige Betragseingabe: {text!r}"
    cent = int(m.group(2).replace(".", "")) * 100 + int((m.group(3) or "0").ljust(2, "0"))
    return -cent if m.group(1) else cent


def de_datum(iso: str) -> str:
    j, m, t = iso[:10].split("-")
    return f"{t}.{m}.{j}"


def letzte_aenderung(api: Api) -> dict | None:
    s = api.get("/api/aenderungen", params={"pro_seite": 1}, erwartet=200).daten
    return s["eintraege"][0] if s["eintraege"] else None


def aenderungen_seit(api: Api, ab_id: int) -> list[dict]:
    s = api.get("/api/aenderungen", params={"pro_seite": 500}, erwartet=200).daten
    return sorted((a for a in s["eintraege"] if a["id"] > ab_id), key=lambda a: a["id"])


def max_aenderung(api: Api) -> int:
    a = letzte_aenderung(api)
    return a["id"] if a else 0


def warte_bis(bedingung, *, zeit: float = WARTEN_MS / 1000, text: str = "Bedingung") -> Any:
    """Wartet auf einen Zustand des Servers (REST), ohne feste Wartezeit."""
    ende = time.monotonic() + zeit
    letzter = None
    while time.monotonic() < ende:
        letzter = bedingung()
        if letzter:
            return letzter
        time.sleep(0.05)
    raise AssertionError(f"{text} nicht erreicht (zuletzt: {letzter!r})")


# ------------------------------------------------------------------ Browser
def tid(seite, x: str):
    return seite.get_by_test_id(x)


def oeffnen(seite, server: LaufenderServer, pfad: str = "/", *, seitenname: str | None = None):
    """Direkter Aufruf einer Route; wartet auf ``app[data-bereit=ja]`` und die geladene Seite."""
    from playwright.sync_api import expect

    seite.goto(server.url + pfad)
    expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja", timeout=WARTEN_MS)
    if seitenname:
        warte_geladen(seite, seitenname)
    return seite


def warte_geladen(seite, seitenname: str):
    from playwright.sync_api import expect

    s = tid(seite, f"seite-{seitenname}")
    expect(s).to_be_visible(timeout=WARTEN_MS)
    expect(s).to_have_attribute("data-geladen", "ja", timeout=WARTEN_MS)
    return s


def ist_mobil(seite) -> bool:
    return tid(seite, "app").get_attribute("data-layout") == "mobil"


def navigiere(seite, ziel: str, seitenname: str | None = None):
    """Über die Navigation (mobil über das einblendbare Menü)."""
    from playwright.sync_api import expect

    if ist_mobil(seite):
        knopf = tid(seite, "menue-knopf")
        if knopf.get_attribute("aria-expanded") != "true":
            knopf.click()
        expect(tid(seite, "navigation")).to_be_visible()
    tid(seite, f"nav-{ziel}").click()
    return warte_geladen(seite, seitenname or ziel)


FILTER_UMSCHALTER = "filter-baukasten-umschalten"


def filter_aufklappen(seite) -> None:
    """Blendet die Filterleiste (ab M30 den Baukasten) der Kontoansicht ein, falls sie eingeklappt ist
    (oberflaeche.md 39.2; anfangs eingeklappt: 23.1, E-174; Umschalter ab M30 ``filter-baukasten-umschalten``,
    E-271)."""
    from playwright.sync_api import expect

    if tid(seite, "filter-leiste").is_hidden():
        tid(seite, FILTER_UMSCHALTER).click()
    expect(tid(seite, "filter-leiste")).to_be_visible()


def ansicht_aufklappen(seite) -> None:
    """Ab M32 am Handy (oberflaeche.md 41.11, E-307): Filterfeld, Zeitraum und Gruppierung sind eingeklappt;
    ``ansicht-umschalten`` klappt sie auf. Am Desktop ohne Wirkung."""
    from playwright.sync_api import expect

    if ist_mobil(seite) and tid(seite, "filter-ausdruck").is_hidden():
        tid(seite, "ansicht-umschalten").click()
        expect(tid(seite, "ansicht-umschalten")).to_have_attribute("aria-expanded", "true")
    expect(tid(seite, "filter-ausdruck")).to_be_visible()


def filter_ausdruck_setzen(seite, ausdruck: str, *, gueltig: bool = True) -> None:
    """Schreibt einen Kontor-Ausdruck in das Filterfeld des Kontoblatts und bestätigt mit Enter
    (oberflaeche.md 39.1, 39.2). Wartet auf das Ergebnis der Prüfung (``filter-ausdruck-status``)."""
    from playwright.sync_api import expect

    ansicht_aufklappen(seite)
    feld = tid(seite, "filter-ausdruck")
    feld.fill(ausdruck)
    feld.press("Enter")
    status = "leer" if not ausdruck.strip() else "ok" if gueltig else "fehler"
    expect(tid(seite, "filter-ausdruck-status")).to_have_attribute("data-status", status)


def filter_ausdruck_wert(seite) -> str:
    """Text des Filterfelds (Eingabeelement oder editierbares Element); am Handy vorher aufgeklappt (41.11)."""
    ansicht_aufklappen(seite)
    feld = tid(seite, "filter-ausdruck")
    return feld.evaluate("e => 'value' in e ? e.value : e.textContent")


def filter_zuruecksetzen(seite) -> None:
    """``filter-zuruecksetzen`` bedienen; klappt den Baukasten auf, falls der Knopf nicht sichtbar ist (E-274),
    am Handy zuerst die Ansicht (41.11)."""
    if not tid(seite, "filter-zuruecksetzen").is_visible():
        ansicht_aufklappen(seite)
    if not tid(seite, "filter-zuruecksetzen").is_visible():
        filter_aufklappen(seite)
    tid(seite, "filter-zuruecksetzen").click()


def filter_aktiv(seite, aktiv: bool = True) -> None:
    """``filter-anzahl``: 0 ohne Filter, sonst ungleich 0 (die Zählweise nennt die Definition nicht, E-271)."""
    from playwright.sync_api import expect

    if aktiv:
        expect(tid(seite, "filter-anzahl")).not_to_have_attribute("data-anzahl", "0")
    else:
        expect(tid(seite, "filter-anzahl")).to_have_attribute("data-anzahl", "0")


def zeile(seite, bid: int):
    return tid(seite, f"buchung-{bid}")


JS_AUSSCHNITT = """async (liste) => {
  const rc = parseInt(liste.getAttribute('aria-rowcount') || '0', 10);
  const zeilen = () => [...liste.querySelectorAll('[role="row"][aria-rowindex]')];
  if (!(rc > 0) || zeilen().length === 0) return null;
  let s = zeilen()[0].parentElement;
  while (s && s !== document.body && !(s.scrollHeight > s.clientHeight + 1 &&
         ['auto', 'scroll'].includes(getComputedStyle(s).overflowY))) s = s.parentElement;
  const roller = (s && s !== document.body) ? s : document.scrollingElement;
  const anfang = roller.scrollTop;
  const gesehen = new Map();
  const sammeln = () => { for (const z of zeilen()) gesehen.set(parseInt(z.getAttribute('aria-rowindex'), 10),
    z.getAttribute('data-testid') || ''); };
  const warte = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  roller.scrollTop = 0; await warte(); sammeln();
  for (let i = 0; i < 2000 && roller.scrollTop + roller.clientHeight < roller.scrollHeight - 1; i++) {
    roller.scrollTop += Math.max(50, roller.clientHeight * 0.7); await warte(); sammeln();
  }
  roller.scrollTop = anfang; await warte();
  return {anzahl: rc, eintraege: [...gesehen.entries()].sort((a, b) => a[0] - b[0]).map(e => e[1])};
}"""


def zellen_ids(seite) -> list[int]:
    """IDs der Buchungszeilen in Anzeigereihenfolge. Zeichnet die Liste ab M28 nur einen Ausschnitt
    (mehr als 100 Einträge, ``aria-rowcount``/``aria-rowindex``, oberflaeche.md 37.7, E-254), wird gerollt und nach
    ``aria-rowindex`` gesammelt; Periodenbalken zählen nicht."""
    liste = seite.locator('[data-testid="buchungsliste"]')
    aus = liste.evaluate(JS_AUSSCHNITT) if liste.count() == 1 else None
    if aus and len(aus["eintraege"]) >= aus["anzahl"] - 1:
        return [int(t[8:]) for t in aus["eintraege"] if t.startswith("buchung-")]
    return [int(x) for x in seite.locator('[data-testid="buchungsliste"] [data-testid^="buchung-"][role="row"]')
            .evaluate_all("els => els.map(e => e.getAttribute('data-testid').slice(8))")]


def ausgewaehlt(seite) -> set[int]:
    return {int(x) for x in seite.locator('[data-testid="buchungsliste"] [role="row"][aria-selected="true"]')
            .evaluate_all("els => els.map(e => e.getAttribute('data-testid').slice(8))")}


def warte_liste(seite, erwartet: list[int]):
    """Wartet, bis die Buchungsliste genau diese IDs in dieser Reihenfolge zeigt."""
    ende = time.monotonic() + WARTEN_MS / 1000
    ist: list[int] = []
    while time.monotonic() < ende:
        if tid(seite, "seite-konto").get_attribute("data-geladen") == "ja":
            ist = zellen_ids(seite)
            if ist == erwartet:
                return
        seite.wait_for_timeout(50)
    raise AssertionError(f"Buchungsliste zeigt {ist[:20]}… ({len(ist)}), erwartet {erwartet[:20]}… ({len(erwartet)})")


def zweck_editor(seite, bid: int):
    """Öffnet den Inline-Editor des Verwendungszwecks mit F2 auf der Zeile (ab M28 kein Doppelklick-Bearbeiten,
    oberflaeche.md 37.8, E-254) und gibt ihn zurück (fokussiert, ``data-feld="verwendungszweck"``)."""
    from playwright.sync_api import expect

    zeile(seite, bid).locator('[data-feld="betrag"]').click()
    seite.keyboard.press("F2")
    e = zeile(seite, bid).get_by_test_id("inline-editor")
    expect(e).to_be_visible()
    return e


def stift(seite, bid: int, feld: str):
    """Wählt die Zeile und betätigt ``stift-<feld>`` im Panel Einzelheiten (37.8); bei Feldern mit Editor in den
    Einzelheiten wird dieser zurückgegeben."""
    from playwright.sync_api import expect

    zeile(seite, bid).locator('[data-feld="betrag"]').click()
    d = tid(seite, "panel-details")
    expect(d).to_be_visible()
    knopf = d.get_by_test_id(f"stift-{feld}")
    expect(knopf).to_be_enabled()
    knopf.click()
    if feld in ("splits", "tags"):
        return None
    e = d.get_by_test_id("inline-editor")
    expect(e).to_be_visible()
    expect(e).to_have_attribute("data-feld", feld)
    return e


def strg() -> str:
    return "Control"


# ---------------------------------------------------------------- Gesten (oberflaeche.md 21)
def _mitte(locator) -> tuple[float, float]:
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    assert box, "Element nicht sichtbar"
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _cdp(seite):
    if not hasattr(seite, "_kontor_cdp"):
        seite._kontor_cdp = seite.context.new_cdp_session(seite)
    return seite._kontor_cdp


def lange_beruehrung(seite, locator, dauer_ms: int = 800) -> None:
    x, y = _mitte(locator)
    cdp = _cdp(seite)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
    seite.wait_for_timeout(dauer_ms)  # Dauer der Geste selbst, keine Wartezeit auf einen Zustand
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def wischen(seite, locator, richtung: str, weite: int = 160) -> None:
    x, y = _mitte(locator)
    if richtung == "links":
        x = min(x + weite / 2, seite.viewport_size["width"] - 5)
        dx = -weite
    else:
        x = max(x - weite / 2, 5)
        dx = weite
    cdp = _cdp(seite)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
    for i in range(1, 9):
        seite.wait_for_timeout(25)  # Geschwindigkeit der Geste (≈ 200 ms)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x + dx * i / 8, "y": y}]})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def auswahlmenue_mobil(seite, zeile_locator):
    """Mobil (M26, oberflaeche.md 36.3): lange Berührung wählt die Zeile aus (Auswahlmodus), ``mehrfach-mehr``
    öffnet das Kontextmenü der Auswahl. Gibt das sichtbare ``kontextmenue`` zurück (E-248)."""
    from playwright.sync_api import expect

    lange_beruehrung(seite, zeile_locator)
    expect(zeile_locator).to_have_attribute("aria-selected", "true")
    expect(tid(seite, "mehrfach-mehr")).to_be_visible()
    tid(seite, "mehrfach-mehr").click()
    m = tid(seite, "kontextmenue")
    expect(m).to_be_visible()
    return m


def tippen(seite, locator) -> None:
    locator.scroll_into_view_if_needed()
    locator.tap()


def maus_ziehen(seite, quelle, ziel, *, ziel_dx: float = 0, ziel_dy: float = 0) -> None:
    """Taste drücken, 10 px bewegen, in Schritten zum Ziel, loslassen (oberflaeche.md 21)."""
    x, y = _mitte(quelle)
    seite.mouse.move(x, y)
    seite.mouse.down()
    seite.mouse.move(x + 10, y + 3, steps=3)
    zx, zy = _mitte(ziel) if not callable(ziel) else ziel()
    seite.mouse.move(zx + ziel_dx, zy + ziel_dy, steps=12)
    seite.mouse.move(zx + ziel_dx + 1, zy + ziel_dy + 1, steps=2)
    seite.mouse.up()


def maus_ziehen_um(seite, griff, dx: float) -> None:
    x, y = _mitte(griff)
    seite.mouse.move(x, y)
    seite.mouse.down()
    seite.mouse.move(x + dx / 2, y, steps=6)
    seite.mouse.move(x + dx, y, steps=6)
    seite.mouse.up()


# ---------------------------------------------------------------- Farben (oberflaeche.md 17)
JS_HINTERGRUND = """el => {
  let e = el;
  while (e) {
    const c = getComputedStyle(e).backgroundColor;
    const m = c.match(/rgba?\\(([^)]+)\\)/);
    if (m) { const t = m[1].split(',').map(Number); if (t.length < 4 || t[3] > 0.5) return t.slice(0, 3); }
    e = e.parentElement;
  }
  return [255, 255, 255];
}"""
JS_TEXTFARBE = """el => getComputedStyle(el).color.match(/rgba?\\(([^)]+)\\)/)[1].split(',').slice(0, 3).map(Number)"""


def leuchtdichte(rgb) -> float:
    def kanal(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (kanal(float(x)) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrast(a, b) -> float:
    la, lb = sorted((leuchtdichte(a), leuchtdichte(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def gleiche_herkunft(url: str, herkunft: str) -> bool:
    if url.startswith(("data:", "blob:", "about:")):
        return True
    t = urlsplit(url)
    return f"{t.scheme}://{t.netloc}" == herkunft


def chromium_pfad() -> str | None:
    return os.environ.get("KONTOR_TESTS_CHROMIUM") or None
