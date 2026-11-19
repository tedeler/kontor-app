"""Weboberfläche (M8): Auslieferung, Navigation, Mock-Hinweis, keine externen Ressourcen, nur spezifizierte REST-Pfade."""

from __future__ import annotations

import json
import re
from pathlib import Path

import kontor

WEB = Path(kontor.__file__).parent / "web"
APP = WEB / "oeffentlich" / "app"
#: oberflaeche.md 3: die acht Ziele aus K 5, danach die weiteren Ziele
#: D-149: Reihenfolge der `nav-`-Links in den Gruppen Buchhaltung, Auswertung, Regeln, Betrieb
NAVIGATION = [("uebersicht", "/", "Finanzübersicht"), ("konten", "/konten", "Konten"),
              ("kategorien", "/kategorien", "Kategorien"), ("empfaenger", "/empfaenger", "Empfänger"),
              ("kredite", "/kredite", "Kredite"), ("berichte", "/berichte", "Berichte"),
              ("regeln", "/regeln", "Regeln"), ("vorlagen", "/vorlagen", "Split-Vorlagen"),
              ("dubletten", "/dubletten", "Dubletten"), ("import", "/import", "Import"),
              ("sync", "/sync", "Synchronisation"), ("protokoll", "/protokoll", "Änderungsprotokoll"),
              ("einstellungen", "/einstellungen", "Einstellungen")]
NAV_GRUPPEN = [("buchhaltung", "Buchhaltung"), ("zahlungen", "Zahlungen"), ("auswertung", "Auswertung"),
               ("regeln", "Regeln"), ("betrieb", "Betrieb")]
#: Pfade der REST-Schnittstelle laut openapy.yaml 2.8.0, als Präfixe der Literale im JavaScript
REST = ["/api/status", "/api/ausdruck",  # D-185
        "/api/konten", "/api/kontenuebersicht", "/api/buchungen", "/api/tags", "/api/empfaenger",
        "/api/version", "/api/import/kmymoney", "/api/import/gnucash", "/api/dubletten", "/api/regeln", "/api/sync", "/api/tan-anforderungen",
        "/api/benachrichtigungen", "/api/aenderungen", "/api/abstimmungen", "/api/suche", "/api/umbuchungen/erkennen",
        "/api/lernmodell", "/api/vorlagen", "/api/sicherung", "/api/kredite", "/api/wiederkehrend", "/api/berichte/kontostand",
        "/api/export/buchungen.csv", "/api/export/buchungen.pdf", "/api/berichte/einnahmen-ausgaben", "/api/mock/zeit", "/api/geheimnisse", "/api/mail/postfaecher",
        "/api/mail/anmeldung/abschluss", "/api/mail/abruf", "/api/anmeldung", "/api/update",  # update: D-107
        "/api/dokumente", "/api/mail/nachrichten",  # Dokumente: D-123
        "/api/mock/lerndaten",  # Mock-Lerndaten: D-184
        "/api/erwartungen",  # Mail-Abgleich: D-128
        "/api/berichte/monat",  # Monatsbericht: D-206, noch nicht im OpenAPI-Vertrag
        # weitere Berichte: D-217, noch nicht im OpenAPI-Vertrag
        "/api/berichte/vertraege",
        "/api/berichte/jahr",
        "/api/berichte/vorschau",
        "/api/berichte/vermoegen",
        "/api/berichte/kategorien",
        "/api/berichte/empfaenger",
        "/api/berichte/geldfluss",
        "/api/berichte/qualitaet",
        "/api/berichte/tags",
        "/api/bank/zugang",  # Bankzugang: D-199, noch nicht im OpenAPI-Vertrag
        "/api/import/alfbanco", "/api/kategorien/zusammenfuehren"]  # ALF-BanCo: D-123, D-126


def test_startseite_echt(client):
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "mock-hinweis" not in r.text
    links = re.findall(r'<a href="([^"]+)" data-testid="nav-([a-z]+)">([^<]+)</a>', r.text)
    assert links == [(p, z, t) for z, p, t in NAVIGATION]
    gruppen = re.findall(r'data-testid="nav-gruppe-([a-z]+)">(.*?)</h2>', r.text)
    assert gruppen == NAV_GRUPPEN
    assert '<script type="module" src="/oeffentlich/app/haupt.js"></script>' in r.text


def test_startseite_mock(mock_client):
    r = mock_client.get("/")
    assert 'id="mock-hinweis"' in r.text and 'data-testid="mock-hinweis"' in r.text and "Mock-Modus" in r.text


def test_routen_liefern_dieselbe_huelle(mock_client):
    start = mock_client.get("/").text
    for pfad in ("/konten/3?von=2024-01-01", "/kredite/2", "/tan/1", "/mail/postfaecher/1", "/buchungen/4", "/sync/konten",
                 "/suche?q=x"):
        r = mock_client.get(pfad)
        assert r.status_code == 200 and r.text == start, pfad
        assert "no-store" in r.headers["cache-control"]
    assert mock_client.get("/gibt-es-nicht").status_code == 404
    assert mock_client.get("/wiederkehrend").status_code == 404  # D-146: Seite aus der Oberfläche genommen
    assert mock_client.get("/konten/abc").status_code == 404


def test_assets(client):
    for pfad, typ in [("/oeffentlich/app/haupt.js", "javascript"), ("/oeffentlich/app.css", "text/css"),
                      ("/oeffentlich/icon.svg", "image/svg+xml"), ("/oeffentlich/icon-192.png", "image/png"),
                      ("/oeffentlich/manifest.webmanifest", "application/manifest+json"), ("/sw.js", "javascript")]:
        r = client.get(pfad)
        assert r.status_code == 200, pfad
        assert typ in r.headers["content-type"], (pfad, r.headers["content-type"])
    m = json.loads(client.get("/oeffentlich/manifest.webmanifest").content)
    assert (m["id"], m["start_url"], m["scope"], m["display"]) == ("/", "/", "/", "standalone")


def test_service_worker_kennt_alle_module():
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    for datei in APP.glob("*.js"):
        assert f'"/oeffentlich/app/{datei.name}"' in sw, f"{datei.name} fehlt im Offline-Cache des Service Workers"
    assert "/api/" in sw and 'startsWith("/api/")' in sw, "Antworten unter /api/ werden nie zwischengespeichert"


def test_keine_externen_ressourcen():
    """Kein CDN, keine Laufzeit-Downloads: alle Ressourcen liegen im Paket."""
    for datei in WEB.rglob("*"):
        # D-113: plotly.js (vendor/) enthält nur Vorgabewerte für Funktionen, die Kontor nicht nutzt
        # (Chart Studio, Geo-Karten); die CSP (connect-src 'self') verhindert jeden Abruf.
        if datei.is_file() and datei.suffix in (".html", ".js", ".css", ".webmanifest", ".svg") and datei.parent.name != "vendor":
            text = datei.read_text(encoding="utf-8")
            treffer = [u for u in re.findall(r"https?://[^\s\"')]+", text) if "www.w3.org/2000/svg" not in u]
            assert not treffer, f"{datei.name}: externe Adresse {treffer}"


def test_csp_konformes_javascript():
    """Kein eval/new Function, kein innerHTML (Texte aus dem Buchbestand nur als Text, oberflaeche.md 1)."""
    for datei in list(APP.glob("*.js")) + [WEB / "sw.js", WEB / "oeffentlich" / "anmelden.js"]:
        js = datei.read_text(encoding="utf-8")
        for verboten in ("eval(", "new Function", "innerHTML", "outerHTML =", "insertAdjacentHTML", "document.write"):
            assert verboten not in js, f"{datei.name}: {verboten}"


def test_oberflaeche_nutzt_nur_spezifizierte_api():
    for datei in APP.glob("*.js"):
        js = datei.read_text(encoding="utf-8")
        for pfad in set(re.findall(r"[\"`](/api/[a-z0-9/._-]+)", js)):
            assert any(pfad.startswith(p) or p.startswith(pfad) for p in REST), f"{datei.name}: {pfad}"
