"""M4: Zuordnung über Quellen hinweg und Dublettenerkennung beim GnuCash-Import (gnucash.md 7, 8; T 6).

Kernaussage T 6: „Überschneidende Zeiträume aus KMyMoney und GnuCash ergeben
keine doppelten Salden.“ Die Wahrheit (welche GnuCash-Buchung zu welcher
KMyMoney-Transaktion gehört) stammt aus dem Generator
(``gnc/ueberlappung.erwartung.json``, Feld ``quelle``).
"""

from __future__ import annotations

import pytest

from generator.gnucash import GBuch, GBuchung, GKonto, GSplit, als_gnc_xml, aus_kbuch, guid
from generator.iban import fiktive_iban
from generator.szenarien import minimal_buch
from tests.hilfen.erwartung import ZAEHLFELDER, lade as lade_kmy
from tests.hilfen.m4 import GNC, gnc_erwartung, import_gnc
from tests.hilfen.pfade import KMY


def _nach_ext(api) -> dict[str, dict]:
    return {e: b for b in api.alle_buchungen() for e in b["extern_ids"]}


def _salden_nach_ext(api) -> dict[str, tuple[int, int, int]]:
    s = api.salden()
    return {k["extern_id"]: (s[k["id"]]["saldo"], s[k["id"]]["saldo_gesamt"], s[k["id"]]["anzahl_buchungen"])
            for k in api.konten()}


@pytest.mark.kern
def test_kmy_dann_gnucash_gleicher_inhalt(api):
    """Dasselbe Buch zuerst aus KMyMoney, dann aus GnuCash: alles wird zugeordnet bzw. zusammengeführt."""
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    vorher = _salden_nach_ext(api)
    konten = api.konten()
    r = import_gnc(api, GNC / "minimal.gnucash").daten
    assert {f: r[f] for f in ZAEHLFELDER} == {
        "konten_neu": 0, "konten_vorhanden": 1, "kategorien_neu": 0, "kategorien_vorhanden": 2,
        "empfaenger_neu": 0, "empfaenger_vorhanden": 2, "tags_neu": 0, "tags_vorhanden": 0, "buchungen_neu": 0,
        "buchungen_vorhanden": 0, "buchungen_zusammengefuehrt": 2, "buchungen_zur_pruefung": 0,
        "buchungen_uebersprungen": 0, "splits_neu": 0}
    assert api.konten() == konten, "zugeordnete Konten behalten ihre kmy:-Kennung und bleiben unverändert"
    assert _salden_nach_ext(api) == vorher, "keine doppelten Salden"
    _, abb = aus_kbuch(minimal_buch(), "minimal")
    for b in api.alle_buchungen():
        assert len(b["extern_ids"]) == 2 and b["extern_ids"] == sorted(b["extern_ids"])
        assert {e[:4] for e in b["extern_ids"]} == {"kmy:", "gnc:"}
    # beide Importe bleiben idempotent
    zustand = api.zustand()
    assert import_gnc(api, GNC / "minimal.gnucash").daten["buchungen_vorhanden"] == 2
    assert api.import_kmy(KMY / "minimal.kmy").daten["buchungen_vorhanden"] == 2
    assert api.zustand() == zustand


@pytest.mark.kern
def test_gnucash_dann_kmy_gleicher_inhalt(api):
    """Umgekehrte Reihenfolge (gnucash.md 7, KMyMoney-Import nach GnuCash-Import)."""
    import_gnc(api, GNC / "minimal.sqlite.gnucash")
    vorher = _salden_nach_ext(api)
    konten = api.konten()
    r = api.import_kmy(KMY / "minimal.kmy").daten
    assert (r["konten_neu"], r["konten_vorhanden"], r["kategorien_neu"], r["kategorien_vorhanden"]) == (0, 1, 0, 2)
    assert (r["buchungen_neu"], r["buchungen_zusammengefuehrt"], r["empfaenger_neu"], r["empfaenger_vorhanden"]) == (
        0, 2, 0, 2)
    assert api.konten() == konten, "gnc:-Konten behalten ihre Kennung"
    assert _salden_nach_ext(api) == vorher
    zustand = api.zustand()
    api.import_kmy(KMY / "minimal.kmy")
    import_gnc(api, GNC / "minimal.sqlite.gnucash")
    assert api.zustand() == zustand


def _buch(praefix: str, konten: list[tuple[str, str, str, str | None, str]], buchungen=()) -> GBuch:
    """konten = [(schluessel, name, typ, eltern-schluessel|None, code)]"""
    g = lambda n: guid(f"{praefix}:{n}")  # noqa: E731
    gb = GBuch(g("buch"), g("root"))
    gb.konten = [GKonto(g(s), n, t, g(e) if e else gb.root_guid, code=c) for s, n, t, e, c in konten]
    for i, (datum, splits, besch) in enumerate(buchungen):
        gb.buchungen.append(GBuchung(g(f"t{i}"), f"{datum} 10:59:00 +0000",
                                     [GSplit(g(k), w, guid=g(f"s{i}:{j}")) for j, (k, w) in enumerate(splits)],
                                     beschreibung=besch))
    return gb


@pytest.mark.kern
def test_vorhandenes_konto_hoechstens_einmal(api):
    """Ab M32 (sammel3.md 1.3, E-307): die zweite gleichnamige Kategorie der Datei wird in das vorhandene Konto
    zusammengeführt (Warnung ``konto_zusammengefasst``) und behält keine eigene Kennung; ein zweiter Import legt sie
    kurz an und führt sie wieder zusammen (Bestand gleich, ``kategorien_neu`` erneut 1)."""
    k = api.konto("Lebensmittel", "aufwand")
    gb = _buch("einmal", [("a", "Lebensmittel", "EXPENSE", None, ""), ("b", "Lebensmittel", "EXPENSE", None, "")])
    r = import_gnc(api, als_gnc_xml(gb)).daten
    assert (r["kategorien_vorhanden"], r["kategorien_neu"]) == (1, 1)
    assert any(w["code"] == "konto_zusammengefasst" and "Lebensmittel" in (w["referenz"] or "")
               for w in r["warnungen"]), r["warnungen"]
    konten = {x["id"]: x for x in api.konten()}
    assert konten[k["id"]]["extern_id"] == "gnc:" + guid("einmal:a"), "erstes in Dokumentreihenfolge, erhält Kennung"
    assert [x["id"] for x in konten.values() if x["name"].casefold() == "lebensmittel"] == [k["id"]]
    vorher = api.zustand()
    r2 = import_gnc(api, als_gnc_xml(gb)).daten
    assert (r2["kategorien_vorhanden"], r2["kategorien_neu"]) == (1, 1)
    assert api.zustand() == vorher


def test_technische_konten_werden_nicht_zugeordnet(api):
    """Konten mit kontor:-Kennung („Unausgeglichen“) sind nie Ziel von Regel 2 (gnucash.md 7)."""
    api.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200)
    tech = next(k for k in api.konten() if k["extern_id"] == "kontor:unausgeglichen")
    gb = _buch("tech", [("u", "Unausgeglichen", "EQUITY", None, "")])
    r = import_gnc(api, als_gnc_xml(gb)).daten
    assert (r["konten_neu"], r["konten_vorhanden"]) == (1, 0)
    assert next(k for k in api.konten() if k["id"] == tech["id"]) == tech


def test_iban_regel_nicht_fuer_fremdes_gnucash_konto(api):
    """Ein Konto mit gnc:-Kennung wird nicht über die IBAN einem anderen GnuCash-Konto zugeordnet."""
    iban = fiktive_iban(7201)
    import_gnc(api, als_gnc_xml(_buch("buch-a", [("g", "Giro A", "BANK", None, iban)])))
    gb = _buch("buch-b", [("g", "Giro B", "BANK", None, iban)])
    r = import_gnc(api, als_gnc_xml(gb)).daten
    assert (r["konten_neu"], r["konten_vorhanden"]) == (1, 0)
    assert ("iban_doppelt", guid("buch-b:g")) in {(w["code"], w["referenz"]) for w in r["warnungen"]}
    neu = next(k for k in api.konten() if k["extern_id"] == "gnc:" + guid("buch-b:g"))
    assert neu["iban"] is None


def test_iban_regel_fuer_konto_mit_kmy_kennung_und_manuell(api):
    iban1, iban2 = fiktive_iban(7301), fiktive_iban(7302)
    manuell = api.konto("Mein Giro", "girokonto", iban=iban1)
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    kmy_giro = next(k for k in api.konten() if k["extern_id"] == "kmy:A000001")
    gb = _buch("iban", [("m", "Anders", "BANK", None, iban1), ("k", "Auch anders", "BANK", None, kmy_giro["iban"]),
                        ("n", "Neu", "BANK", None, iban2)])
    r = import_gnc(api, als_gnc_xml(gb)).daten
    assert (r["konten_vorhanden"], r["konten_neu"]) == (2, 1)
    konten = {k["id"]: k for k in api.konten()}
    assert konten[manuell["id"]]["extern_id"] == "gnc:" + guid("iban:m"), "ohne Kennung: erhält sie"
    assert konten[manuell["id"]]["name"] == "Mein Giro"
    assert konten[kmy_giro["id"]]["extern_id"] == "kmy:A000001", "mit kmy:-Kennung: behält sie"


def test_kategorie_ueber_art_name_eltern(api):
    eltern = api.konto("Wohnen", "aufwand")
    kind = api.konto("Miete", "aufwand", eltern_id=eltern["id"])
    andere = api.konto("Miete", "aufwand")  # gleicher Name, anderes Elternkonto
    gb = _buch("kat", [("w", "Wohnen", "EXPENSE", None, ""), ("m", "Miete", "EXPENSE", "w", ""),
                       ("e", "Miete", "INCOME", None, "")])
    r = import_gnc(api, als_gnc_xml(gb)).daten
    assert (r["kategorien_vorhanden"], r["kategorien_neu"]) == (2, 1)
    konten = {k["id"]: k for k in api.konten()}
    assert konten[kind["id"]]["extern_id"] == "gnc:" + guid("kat:m")
    assert konten[andere["id"]]["extern_id"] is None


@pytest.mark.kern
def test_dubletten_gegen_manuelle_buchungen(api):
    """gnucash.md 8: exakt eindeutig → zusammengeführt; einen Tag daneben → Verdacht „aehnlich“."""
    iban = fiktive_iban(7401)
    giro = api.konto("Giro", "girokonto", iban=iban)
    leb = api.konto("Lebensmittel", "aufwand")
    m = api.empfaenger("Markt")
    a = api.buchung("2024-05-02", [(giro["id"], -1500), (leb["id"], 1500)], empfaenger_id=m["id"])
    b = api.buchung("2024-05-10", [(giro["id"], -2200), (leb["id"], 2200)], empfaenger_id=m["id"])
    gb = _buch("dub", [("g", "Giro", "BANK", None, iban), ("l", "Lebensmittel", "EXPENSE", None, "")],
               [("2024-05-02", [("g", -1500), ("l", 1500)], " MARKT "),
                ("2024-05-11", [("g", -2200), ("l", 2200)], "Markt"),
                ("2024-05-20", [("g", -900), ("l", 900)], "Markt")])
    r = import_gnc(api, als_gnc_xml(gb)).daten
    assert (r["buchungen_zusammengefuehrt"], r["buchungen_neu"], r["buchungen_zur_pruefung"]) == (1, 2, 1)
    nach = {x["id"]: x for x in api.alle_buchungen()}
    assert nach[a["id"]]["extern_ids"] == ["gnc:" + guid("dub:t0")]
    assert nach[a["id"]]["splits"] == a["splits"] and nach[a["id"]]["empfaenger"] == a["empfaenger"]
    (v,) = api.get("/api/dubletten", erwartet=200).daten
    neu = next(x for x in nach.values() if x["extern_ids"] == ["gnc:" + guid("dub:t1")])
    assert (v["buchung_id"], v["kandidat_ids"], v["grund"], v["status"]) == (neu["id"], [b["id"]], "aehnlich", "offen")


def test_gnucash_buchungen_sind_keine_kandidaten_untereinander(api):
    """Zwei gleiche Transaktionen eines GnuCash-Buchs werden nie miteinander abgeglichen (gnucash.md 8)."""
    zeilen = [("g", "Giro", "BANK", None, fiktive_iban(7501)), ("c", "Café", "EXPENSE", None, "")]
    import_gnc(api, als_gnc_xml(_buch("kaffee", zeilen, [("2024-06-01", [("g", -330), ("c", 330)], "Café")])))
    r = import_gnc(api, als_gnc_xml(_buch("kaffee", zeilen, [("2024-06-01", [("g", -330), ("c", 330)], "Café"),
                                                             ("2024-06-01", [("g", -330), ("c", 330)], "Café")]))).daten
    assert (r["buchungen_vorhanden"], r["buchungen_neu"], r["buchungen_zur_pruefung"]) == (1, 1, 0)
    assert api.get("/api/dubletten", erwartet=200).daten == []


# ------------------------------------------------- große Überschneidung (T 6)
def _aufloesen_nach_wahrheit(api, wahr_von: dict[int, int | None]) -> None:
    for v in api.get("/api/dubletten", params={"status": "offen"}, erwartet=200).daten:
        ziel = wahr_von[v["buchung_id"]]
        if ziel is None:
            api.post(f"/api/dubletten/{v['id']}/aufloesen", json={"entscheidung": "keine_dublette"}, erwartet=200)
        else:
            assert ziel in v["kandidat_ids"], v
            api.post(f"/api/dubletten/{v['id']}/aufloesen",
                     json={"entscheidung": "zusammenfuehren", "behalten_id": ziel}, erwartet=200)


@pytest.mark.langsam
@pytest.mark.kern
def test_ueberlappung_kmy_dann_gnucash_keine_doppelten_salden(api):
    erw = gnc_erwartung("ueberlappung")
    n = erw["nach_kmy"]
    voll = lade_kmy("standard")
    api.import_kmy(KMY / "standard_bis_2023.kmy", erwartet=200)
    konten = api.konten()
    r = import_gnc(api, GNC / "ueberlappung.sqlite.gnucash").daten
    assert {f: r[f] for f in ZAEHLFELDER} == n["ergebnis"]
    assert api.konten() == konten, "alle GnuCash-Konten wurden vorhandenen KMyMoney-Konten zugeordnet"
    nach = _nach_ext(api)
    for g, k in n["zusammengefuehrt"].items():
        assert nach[g] is nach[k] or nach[g]["id"] == nach[k]["id"], (g, k)
    verdacht = {nach[v["extern_id"]]["id"]: v for v in n["verdacht"]}
    offen = api.get("/api/dubletten", params={"status": "offen"}, erwartet=200).daten
    assert {v["buchung_id"] for v in offen} == set(verdacht)
    id_von = {e: b["id"] for e, b in nach.items()}
    for v in offen:
        soll = verdacht[v["buchung_id"]]
        assert v["kandidat_ids"] == sorted(id_von[k] for k in soll["kandidaten"]) and v["grund"] == soll["grund"]
    _aufloesen_nach_wahrheit(api, {i: (id_von[v["wahr"]] if v["wahr"] else None) for i, v in verdacht.items()})
    # jetzt ist jeder Vorgang genau einmal im Buch: Salden wie das ganze KMyMoney-Buch 2022–2024
    ist = _salden_nach_ext(api)
    for k in voll["konten"]:
        assert ist[k["extern_id"]] == (k["saldo"], k["saldo_gesamt"], k["anzahl_buchungen"]), k["name"]
    assert len(api.alle_buchungen()) == len(voll["buchungen"])
    assert api.uebersicht()["summe_gesamt"] == 0


@pytest.mark.langsam
def test_ueberlappung_gnucash_dann_kmy_keine_doppelten_salden(api):
    erw = gnc_erwartung("ueberlappung")
    zu_kmy = erw["nach_kmy"]["konto_zuordnung"]
    quelle = {b["extern_id"]: "kmy:" + b["quelle"] for b in erw["buchungen"]}
    voll = lade_kmy("standard")
    import_gnc(api, GNC / "ueberlappung.sqlite.gnucash")
    konten = api.konten()
    r = api.import_kmy(KMY / "standard_bis_2023.kmy").daten
    assert r["konten_neu"] == 0 and r["kategorien_neu"] == 0
    assert api.konten() == konten, "KMyMoney-Konten werden den GnuCash-Konten zugeordnet (auch ohne IBAN)"
    assert r["buchungen_zusammengefuehrt"] > 250
    nach = _nach_ext(api)
    gnc_von_kmy = {q: g for g, q in quelle.items()}
    wahr = {}
    for v in api.get("/api/dubletten", params={"status": "offen"}, erwartet=200).daten:
        b = next(x for x in api.alle_buchungen() if x["id"] == v["buchung_id"])
        kmy = next(e for e in b["extern_ids"] if e.startswith("kmy:"))
        g = gnc_von_kmy.get(kmy)
        wahr[v["buchung_id"]] = nach[g]["id"] if g else None
    _aufloesen_nach_wahrheit(api, wahr)
    ist = _salden_nach_ext(api)
    von_kmy = {v: k for k, v in zu_kmy.items()}
    for k in voll["konten"]:
        assert ist[von_kmy[k["extern_id"]]] == (k["saldo"], k["saldo_gesamt"], k["anzahl_buchungen"]), k["name"]
    assert len(api.alle_buchungen()) == len(voll["buchungen"])
