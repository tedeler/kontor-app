"""M8: Finanzübersicht und Kontoansicht mit Filtern, Sortierung, Seiten und Vorschlägen
(oberflaeche.md 5–7.3; K 5, K 7; T 19: Finanzübersicht, Kontoansicht, Filtern – desktop und mobil)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import betrag_text, de_datum, oeffnen, tid, zeile

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


@pytest.fixture
def daten(starte_server):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    return server, erw, ids


def _konto_oeffnen(seite, server, kid, abfrage=""):
    oeffnen(seite, server, f"/konten/{kid}{abfrage}", seitenname="konto")


# ------------------------------------------------------------------ Finanzübersicht (6)
def test_uebersicht_salden_aus_der_wahrheit(daten, neue_seite, geraet):
    server, erw, ids = daten
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    bestand = [k for k in erw["konten"] if k["art"] in ("girokonto", "sparkonto", "kreditkonto")]
    offen = [k for k in bestand if not k["geschlossen"]]
    zeilen = seite.locator('[data-testid="uebersicht-tabelle"] [data-testid^="uebersicht-konto-"]')
    expect(zeilen).to_have_count(len(offen))
    for k in offen:
        z = tid(seite, f"uebersicht-konto-{ids.konto[k['extern_id']]}")
        expect(z.locator('[data-feld="name"]')).to_have_text(k["name"])
        saldo = z.locator('[data-feld="saldo"]')
        expect(saldo).to_have_attribute("data-betrag", str(k["saldo_gesamt"]))
        expect(saldo).to_have_text(betrag_text(k["saldo_gesamt"]))
    summe = sum(k["saldo"] for k in bestand)
    expect(tid(seite, "uebersicht-summe")).to_have_attribute("data-betrag", str(summe))
    # geschlossene Konten auf Wunsch
    geschlossen = ids.konto[erw["m8"]["konten"]["sparbuch_geschlossen"]]
    expect(tid(seite, f"uebersicht-konto-{geschlossen}")).to_have_count(0)
    tid(seite, "uebersicht-geschlossene").check()
    expect(tid(seite, f"uebersicht-konto-{geschlossen}")).to_have_attribute("data-geschlossen", "ja")
    # Klick öffnet die Kontoansicht
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    tid(seite, f"uebersicht-konto-{giro}").locator('[data-feld="name"]').click()
    m8.warte_geladen(seite, "konto")
    assert seite.url == f"{server.url}/konten/{giro}"


def test_uebersicht_unterkonten_und_negative_betraege(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    giro = api.konto("Gemeinschaftskonto", "girokonto")["id"]
    unter = api.konto("Unterkonto Urlaub", "girokonto", eltern_id=giro)["id"]
    kat = api.konto("Testausgaben", "aufwand")["id"]
    api.buchung("2024-05-01", [(unter, -123456), (kat, 123456)])
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    expect(tid(seite, f"uebersicht-konto-{giro}")).to_have_attribute("aria-level", "1")
    expect(tid(seite, f"uebersicht-konto-{unter}")).to_have_attribute("aria-level", "2")
    reihen = seite.locator('[data-testid^="uebersicht-konto-"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
    assert reihen.index(f"uebersicht-konto-{giro}") + 1 == reihen.index(f"uebersicht-konto-{unter}")
    s = tid(seite, f"uebersicht-konto-{giro}").locator('[data-feld="saldo"]')
    expect(s).to_have_attribute("data-betrag", "-123456")
    expect(s).to_have_text("-1.234,56 €")


# ------------------------------------------------------------------ Liste (7.2)
def test_liste_gleich_rest_und_darstellung(daten, neue_seite, geraet):
    server, erw, ids = daten
    api = server.api
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server, geraet)
    _konto_oeffnen(seite, server, giro)
    expect(seite.locator("h1")).to_have_text("Girokonto")
    reihen = m8.rest_liste(api, giro)
    assert len(reihen) == erw["m8"]["giro_anzahl"]
    m8.warte_liste(seite, reihen)
    expect(tid(seite, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", str(erw["m8"]["giro_anzahl"]))
    expect(tid(seite, "buchungsliste-summe")).to_have_attribute("data-betrag", str(erw["m8"]["giro_saldo"]))
    expect(tid(seite, "buchungsliste")).to_have_attribute("data-kompakt", "ja" if geraet == "handy" else "nein")
    expect(tid(seite, "buchungsliste-mehr")).to_be_hidden()
    pfade = erw["m8"]["pfade"]
    nach_ext = {e: b for b in erw["buchungen"] for e in [b["extern_id"]]}
    rest = {b["id"]: b for b in api.alle_buchungen(konto_id=giro)}
    for ext, b in list(nach_ext.items())[:40]:
        bid = ids.buchung.get(ext)
        if bid not in rest:
            continue
        z = zeile(seite, bid)
        r = rest[bid]
        expect(z).to_have_attribute("data-status", "importiert")
        d = z.locator('[data-feld="datum"]')
        expect(d).to_have_attribute("data-datum", b["datum"][:10])
        expect(d).to_have_text(de_datum(b["datum"]))
        betrag = z.locator('[data-feld="betrag"]')
        expect(betrag).to_have_attribute("data-betrag", str(r["betrag"]))
        expect(betrag).to_have_text(betrag_text(r["betrag"]))
        kat = z.locator('[data-feld="kategorie"]')
        if b["kategorie_extern_id"]:
            expect(kat).to_have_attribute("data-kategorie-id", str(ids.konto[b["kategorie_extern_id"]]))
            expect(kat).to_contain_text(pfade[b["kategorie_extern_id"]])
        e = z.locator('[data-feld="empfaenger"]')
        expect(e).to_have_attribute("data-empfaenger-id", str(r["empfaenger"]["id"]) if r["empfaenger"] else "")
        if geraet == "desktop":
            expect(z.locator('[data-feld="verwendungszweck"]')).to_have_text(b["verwendungszweck"])
            expect(z.locator('[data-feld="status"]')).to_have_text("Importiert")
    split = ids.buchung[erw["m8"]["split_buchung"]]
    k = zeile(seite, split).locator('[data-feld="kategorie"]')
    expect(k).to_have_attribute("data-kategorie-id", "")
    expect(k).to_have_text("Gesplittet")
    umbuchung = next(ids.buchung[b["extern_id"]] for b in erw["buchungen"] if b["umbuchung"])
    k = zeile(seite, umbuchung).locator('[data-feld="kategorie"]')
    expect(k).to_have_attribute("data-kategorie-id", "")
    expect(k).to_have_text("Umbuchung")


def test_texte_nur_als_text(daten, neue_seite):
    """oberflaeche.md 1 Nr. 5: ein HTML-artiger Verwendungszweck erscheint wörtlich, nichts wird ausgeführt."""
    server, erw, ids = daten
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server)
    seite.on("dialog", lambda d: (_ for _ in ()).throw(AssertionError(f"Dialog geöffnet: {d.message}")))
    _konto_oeffnen(seite, server, giro)
    bid = next(ids.buchung[b["extern_id"]] for b in erw["buchungen"] if b["verwendungszweck"] == erw["m8"]["html_text"])
    expect(zeile(seite, bid).locator('[data-feld="verwendungszweck"]')).to_have_text(erw["m8"]["html_text"])
    expect(tid(seite, "buchungsliste").locator("img, b")).to_have_count(0)
    tid(seite, "suche-feld").fill("Café")
    tid(seite, "suche-feld").press("Enter")
    m8.warte_geladen(seite, "suche")
    expect(tid(seite, "seite-suche").locator("img, b")).to_have_count(0)
    expect(tid(seite, "seite-suche")).to_contain_text(erw["m8"]["html_text"])


def _rest_parameter(fall: dict, ids: m8.Ids) -> dict:
    p = dict(fall["parameter"])
    if "kategorie_extern_id" in p:
        p["kategorie_id"] = ids.konto[p.pop("kategorie_extern_id")]
    if "tag_extern_id" in p:
        p["tag_id"] = ids.tag[p.pop("tag_extern_id")]
    if "empfaenger_name" in p:
        p["empfaenger_id"] = ids.empfaenger_name[p.pop("empfaenger_name")]
    return p


#: Adressparameter ohne Entsprechung im Ausdruck (oberflaeche.md 39.2): bleiben als ``filter-alt-<name>``
OHNE_ENTSPRECHUNG = ("betrag_min", "betrag_max", "zweck_aehnlich", "empfaenger_aehnlich")


def _adresse(p: dict) -> str:
    teile = []
    for k, v in p.items():
        for w in (v if isinstance(v, list) else [v]):
            teile.append((k, ("true" if w else "false") if isinstance(w, bool) else str(w)))
    return "?" + urlencode(teile)


FAELLE = [f["name"] for f in m8.lade_erwartung()["m8"]["filterfaelle"]]


@pytest.mark.parametrize("fall_name", FAELLE)
def test_filter(daten, neue_seite, geraet, fall_name):
    """Ab M30 (oberflaeche.md 39.2, E-271): Die Einzelfelder der Filterleiste gibt es nicht mehr. Die Filterfälle
    der Wahrheit werden als alte Adresse geöffnet: Parameter mit Entsprechung wandern in den Ausdruck, die übrigen
    erscheinen als ``filter-alt-<name>``; die Liste zeigt dieselben Buchungen wie REST mit den Parametern."""
    server, erw, ids = daten
    fall = next(f for f in erw["m8"]["filterfaelle"] if f["name"] == fall_name)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    p = _rest_parameter(fall, ids)
    reihen = m8.rest_liste(server.api, giro, **p)
    assert sorted(reihen) == sorted(ids.buchung[e] for e in fall["erwartet"]), "REST stimmt mit der Wahrheit überein"
    seite = neue_seite(server, geraet)
    _konto_oeffnen(seite, server, giro, _adresse(p))
    expect(tid(seite, "filter-leiste")).to_be_hidden()   # Baukasten anfangs eingeklappt (39.2)
    if geraet == "handy":   # ab M32: am Handy eingeklappt, ansicht-umschalten klappt auf (41.11, E-307)
        expect(tid(seite, "filter-ausdruck")).to_be_hidden()
        expect(tid(seite, "ansicht-umschalten")).to_have_attribute("aria-expanded", "false")
        m8.ansicht_aufklappen(seite)
    expect(tid(seite, "filter-ausdruck")).to_be_visible()
    m8.warte_liste(seite, reihen)
    expect(tid(seite, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", str(len(reihen)))
    m8.filter_aktiv(seite)
    alt = [k for k in p if k in OHNE_ENTSPRECHUNG] + (["kategorie_id"] if p.get("unterkategorien") else [])
    for name in alt:
        expect(tid(seite, f"filter-alt-{name}")).to_be_visible()
    if len(alt) < len([k for k in p if k != "unterkategorien"]):
        m8.warte_bis(lambda: m8.filter_ausdruck_wert(seite).strip() != "", text="alte Adresse im Ausdruck")
        m8.warte_bis(lambda: "filter" in parse_qs(urlsplit(seite.url).query), text="filter= in der Adresse")
    # Neuladen behält den Filter (URL), Zurücksetzen hebt ihn auf
    seite.reload()
    m8.warte_geladen(seite, "konto")
    m8.warte_liste(seite, reihen)
    m8.filter_zuruecksetzen(seite)
    m8.warte_liste(seite, m8.rest_liste(server.api, giro))
    m8.filter_aktiv(seite, False)
    assert m8.filter_ausdruck_wert(seite).strip() == ""


def test_filter_aus_der_url_und_status(daten, neue_seite):
    server, erw, ids = daten
    api = server.api
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    alle = m8.rest_liste(api, giro)
    for bid in alle[:5]:
        api.patch(f"/api/buchungen/{bid}", json={"status": "bestaetigt"}, erwartet=200)
    seite = neue_seite(server)
    _konto_oeffnen(seite, server, giro, "?von=2024-01-01&bis=2024-12-31&status=bestaetigt")
    reihen = m8.rest_liste(api, giro, von="2024-01-01", bis="2024-12-31", status=["bestaetigt"])
    assert sorted(reihen) == sorted(alle[:5])
    m8.warte_liste(seite, reihen)
    # ab M30 stehen die alten Parameter im Ausdruck (39.2)
    m8.warte_bis(lambda: "bestaetigt" in m8.filter_ausdruck_wert(seite), text="Status im Ausdruck")
    assert "importiert" not in m8.filter_ausdruck_wert(seite)
    for bid in reihen:
        expect(zeile(seite, bid)).to_have_attribute("data-status", "bestaetigt")
        expect(zeile(seite, bid).locator('[data-feld="status"]')).to_have_text("Bestätigt")
    ausdruck = 'status in ["bestaetigt", "importiert"] and datum in 2024-01-01 .. 2024-12-31'
    m8.filter_ausdruck_setzen(seite, ausdruck)
    soll = m8.rest_liste(api, giro, von="2024-01-01", bis="2024-12-31", status=["bestaetigt", "importiert"])
    assert sorted(m8.rest_liste(api, giro, filter=ausdruck)) == sorted(soll)
    m8.warte_liste(seite, soll)


def test_ungueltiger_filterausdruck(daten, neue_seite):
    """Ersetzt ab M30 die ungültige Betragseingabe (E-271): Bei einem Fehler bleibt die letzte gültige Liste
    stehen, das Feld trägt ``aria-invalid``, die Adresse bleibt ohne Filter (oberflaeche.md 39.1, 39.2)."""
    server, erw, ids = daten
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server)
    _konto_oeffnen(seite, server, giro)
    vorher = m8.zellen_ids(seite)
    feld = tid(seite, "filter-ausdruck")
    m8.filter_ausdruck_setzen(seite, "betrag >", gueltig=False)
    expect(feld).to_have_attribute("aria-invalid", "true")
    expect(tid(seite, "filter-ausdruck-fehler")).not_to_be_empty()
    assert m8.zellen_ids(seite) == vorher
    assert "filter=" not in seite.url
    m8.filter_ausdruck_setzen(seite, "betrag >= 1_000.00")
    expect(feld).not_to_have_attribute("aria-invalid", "true")
    m8.warte_liste(seite, m8.rest_liste(server.api, giro, filter="betrag >= 1_000.00"))
    m8.warte_bis(lambda: "filter" in parse_qs(urlsplit(seite.url).query), text="filter= in der Adresse")


@pytest.mark.parametrize("spalte,folge", [("betrag", ["betrag", "-betrag"]), ("empfaenger", ["empfaenger", "-empfaenger"]),
                                          ("datum", ["datum", "-datum"])])
def test_sortierung(daten, neue_seite, spalte, folge):
    server, erw, ids = daten
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server)
    _konto_oeffnen(seite, server, giro)
    kopf = tid(seite, f"spalte-{spalte}")
    kopfzelle = kopf.locator("xpath=ancestor-or-self::*[@role='columnheader'][1]")
    if spalte != "datum":
        expect(kopfzelle).to_have_attribute("aria-sort", "none")
    else:
        expect(kopfzelle).to_have_attribute("aria-sort", "descending")   # Vorgabe -datum
    for s in folge:
        kopf.click()
        m8.warte_liste(seite, m8.rest_liste(server.api, giro, sortierung=s))
        expect(kopfzelle).to_have_attribute("aria-sort", "descending" if s.startswith("-") else "ascending")
        assert parse_qs(urlsplit(seite.url).query).get("sortierung") == [s]


def test_weitere_seiten_laden(starte_server, neue_seite):
    server = starte_server()
    m8.importiere(server.api, m8.VIELE)
    konto = next(k["id"] for k in server.api.konten() if k["name"] == "Haushaltskonto")
    alle = m8.rest_liste(server.api, konto)
    assert len(alle) == 450
    seite = neue_seite(server)
    _konto_oeffnen(seite, server, konto)
    m8.warte_liste(seite, alle[:200])
    expect(tid(seite, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", "450")
    tid(seite, "buchungsliste-mehr").click()
    m8.warte_liste(seite, alle[:400])
    tid(seite, "buchungsliste-mehr").click()
    m8.warte_liste(seite, alle)
    expect(tid(seite, "buchungsliste-mehr")).to_be_hidden()


def test_leere_liste(daten, neue_seite):
    server, erw, ids = daten
    darlehen = ids.konto[erw["m8"]["konten"]["darlehen"]]
    seite = neue_seite(server)
    _konto_oeffnen(seite, server, darlehen)
    expect(tid(seite, "buchungsliste-leer")).to_be_visible()
    expect(tid(seite, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", "0")


def test_kategorie_als_konto_oeffnen(daten, neue_seite):
    server, erw, ids = daten
    miete = ids.konto[erw["m8"]["konten"]["miete"]]
    seite = neue_seite(server)
    _konto_oeffnen(seite, server, miete)
    expect(seite.locator("h1")).to_have_text("Miete")
    m8.warte_liste(seite, m8.rest_liste(server.api, miete))


def test_vorschlaege_annehmen_und_ablehnen(daten, neue_seite, geraet):
    server, erw, ids = daten
    api = server.api
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    haushalt = ids.konto[erw["m8"]["konten"]["haushalt"]]
    regel = api.post("/api/regeln", json={"name": "Tanken als Haushalt", "kategorie_id": haushalt, "bedingungen": [
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "Tankstelle"}]}, erwartet=201).daten
    api.post("/api/regeln/anwenden", json={"regel_ids": [regel["id"]], "nur_unkategorisiert": False}, erwartet=200)
    mit = [b for b in api.alle_buchungen(konto_id=giro) if b.get("vorschlag")]
    assert len(mit) >= 3
    seite = neue_seite(server, geraet)
    _konto_oeffnen(seite, server, giro)
    for b in mit:
        expect(zeile(seite, b["id"])).to_have_attribute("data-vorschlag", "ja")
        expect(zeile(seite, b["id"]).get_by_test_id("vorschlag-marke")).to_be_visible()
    ohne = next(b["id"] for b in api.alle_buchungen(konto_id=giro) if not b.get("vorschlag"))
    expect(zeile(seite, ohne)).to_have_attribute("data-vorschlag", "nein")
    a, b2 = mit[0]["id"], mit[1]["id"]
    # D-305: keine Knöpfe in der Zeile mehr; Desktop über das Kontextmenü, Handy über Wischen und Einzelheiten
    expect(zeile(seite, a).get_by_test_id(f"vorschlag-annehmen-{a}")).to_have_count(0)

    if geraet == "handy":
        # Handy: Annehmen durch Wischen nach rechts (Bestätigen nimmt den Vorschlag an). Ablehnen geht mobil über
        # Kontextmenü oder Einzelheiten; hier über die Schnittstelle, damit der Rest des Tests gleich bleibt.
        m8.wischen(seite, zeile(seite, a), "rechts")
        api.post(f"/api/buchungen/{b2}/vorschlag", json={"aktion": "ablehnen"}, erwartet=200)
    else:
        zeile(seite, a).click(button="right")
        tid(seite, "km-vorschlag-annehmen").click()
        m8.warte_bis(lambda: api.buchung_lesen(a)["vorschlag"] is None)
        zeile(seite, b2).click(button="right")
        tid(seite, "km-vorschlag-ablehnen").click()
    m8.warte_bis(lambda: api.buchung_lesen(a)["vorschlag"] is None and api.buchung_lesen(a)["kategorie_id"] == haushalt)
    expect(zeile(seite, a)).to_have_attribute("data-vorschlag", "nein")
    m8.warte_bis(lambda: api.buchung_lesen(b2)["vorschlag"] is None)
    assert api.buchung_lesen(b2)["kategorie_id"] == mit[1]["vorschlag"]["vorher_konto_id"]
