"""Eigene Tests zum Sammelpaket (D-107 bis D-112): Rückgängig bis, Mehrfach löschen, Verschieben, Zuordnung
unbekannter Bankkonten. Ergänzen die Abnahmetests aus kontor-tests, ersetzen sie nicht."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig
from tests.conftest import GIRO, kmy, transaktion


def test_iban(kontonummer: int) -> str:
    """Synthetische IBAN mit Bankleitzahl 00000000 und gültiger Prüfziffer."""
    bban = f"00000000{kontonummer:010d}"
    zahl = int("".join(str(int(c, 36)) for c in bban + "DE00"))
    return f"DE{98 - zahl % 97:02d}{bban}"


test_iban.__test__ = False  # keine Testfunktion


def ok(r, code: int = 200):
    assert r.status_code == code, r.text
    return r.json() if r.content else None


def konto(c: TestClient, name: str, art: str = "girokonto", **mehr) -> int:
    return ok(c.post("/api/konten", json={"name": name, "art": art, **mehr}), 201)["id"]


def buchung(c: TestClient, konto_id: int, gegen: int, betrag: int, tag: int = 1) -> int:
    return ok(c.post("/api/buchungen", json={"datum": f"2026-01-{tag:02d}", "splits": [
        {"konto_id": konto_id, "betrag": -betrag}, {"konto_id": gegen, "betrag": betrag}]}), 201)["id"]


def wirksam(c: TestClient) -> dict[int, int | None]:
    return {a["id"]: a["rueckgaengig_durch"] for a in ok(c.get("/api/aenderungen?pro_seite=500"))["eintraege"]}


def tagnamen(c: TestClient) -> list[str]:
    return sorted(t["name"] for t in ok(c.get("/api/tags")))


# ------------------------------------------------------------------ Rückgängig bis (D-107)
def test_rueckgaengig_bis_einschliesslich(client: TestClient) -> None:
    ids = [ok(client.post("/api/tags", json={"name": f"t{i}"}), 201) and None for i in range(4)]
    ids = sorted(wirksam(client))
    u = ok(client.post("/api/aenderungen/rueckgaengig", json={"bis_id": ids[1]}))
    assert u["rueckgaengig_von"] == ids[1:]
    assert tagnamen(client) == ["t0"]
    # Wiederholen stellt alles wieder her
    ok(client.post(f"/api/aenderungen/{u['id']}/rueckgaengig"))
    assert tagnamen(client) == ["t0", "t1", "t2", "t3"]


def test_rueckgaengig_bis_mit_frueheren_rueckgaengig(client: TestClient) -> None:
    for i in range(5):
        ok(client.post("/api/tags", json={"name": f"t{i}"}), 201)
    a = sorted(wirksam(client))
    u = ok(client.post(f"/api/aenderungen/{a[2]}/rueckgaengig"))            # t2 weg
    ok(client.post(f"/api/aenderungen/{u['id']}/rueckgaengig"))             # t2 wieder da
    ok(client.post("/api/aenderungen/rueckgaengig", json={"bis_id": a[3]}))  # vor t3
    assert tagnamen(client) == ["t0", "t1", "t2"]
    ok(client.post("/api/aenderungen/rueckgaengig", json={"bis_id": a[1]}))  # vor t1
    assert tagnamen(client) == ["t0"]
    # bis mitten in eine frühere Rückgängig-bis-Änderung: Zustand vor t2
    v = ok(client.post("/api/aenderungen/rueckgaengig", json={"bis_id": a[2]}))
    assert tagnamen(client) == ["t0", "t1"]
    ok(client.post(f"/api/aenderungen/{v['id']}/rueckgaengig"))
    assert tagnamen(client) == ["t0"]
    # Wirksamkeit bleibt konsistent: jede Änderung höchstens einmal rückgängig, nur durch wirksame
    w = wirksam(client)
    eintraege = {x["id"]: x for x in ok(client.get("/api/aenderungen?pro_seite=500"))["eintraege"]}
    for aid, durch in w.items():
        if durch is not None:
            assert w[durch] is None and aid in eintraege[durch]["rueckgaengig_von"]


def test_rueckgaengig_bis_fehler(client: TestClient) -> None:
    ok(client.post("/api/tags", json={"name": "x"}), 201)
    assert client.post("/api/aenderungen/rueckgaengig", json={"bis_id": 999}).status_code == 404
    r = client.post("/api/aenderungen/rueckgaengig", json={"bis_id": 1, "gruppe": "g"})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "validierung"
    assert client.post("/api/aenderungen/rueckgaengig", json={"bis_id": "1"}).status_code == 422


# ------------------------------------------------------------------ Mehrfach löschen (D-108)
def test_mehrfach_loeschen_eine_aenderung(client: TestClient) -> None:
    g = konto(client, "Giro")
    k = konto(client, "Essen", "aufwand")
    bs = [buchung(client, g, k, 100 * i, i) for i in range(1, 4)]
    vorher = len(wirksam(client))
    r = ok(client.post("/api/buchungen/mehrfach/loeschen", json={"buchung_ids": [bs[2], bs[0]]}))
    assert r == {"geloescht": [bs[0], bs[2]], "anzahl": 2}
    nachher = ok(client.get("/api/aenderungen?pro_seite=5"))["eintraege"]
    assert len(wirksam(client)) == vorher + 1 and nachher[0]["aktion"] == "mehrfach_loeschen"
    ok(client.post(f"/api/aenderungen/{nachher[0]['id']}/rueckgaengig"))
    assert ok(client.get(f"/api/buchungen?konto_id={g}"))["gesamt"] == 3


def test_mehrfach_loeschen_fehler(client: TestClient) -> None:
    g = konto(client, "Giro")
    k = konto(client, "Essen", "aufwand")
    b = buchung(client, g, k, 100)
    r = client.post("/api/buchungen/mehrfach/loeschen", json={"buchung_ids": [b, 999]})
    assert r.status_code == 422 and r.json()["fehler"]["details"] == {"buchung_ids": [999]}
    ok(client.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [b], "status": "abgeglichen"}))
    r = client.post("/api/buchungen/mehrfach/loeschen", json={"buchung_ids": [b]})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "buchung_gesperrt"
    assert client.post("/api/buchungen/mehrfach/loeschen", json={"buchung_ids": []}).status_code == 422


# ------------------------------------------------------------------ Verschieben (D-109)
def test_verschieben_auswahl(client: TestClient) -> None:
    a = konto(client, "A")
    b = konto(client, "B", "sparkonto")
    k = konto(client, "Essen", "aufwand")
    bs = [buchung(client, a, k, 100 * i, i) for i in range(1, 4)]
    r = ok(client.post("/api/buchungen/mehrfach/verschieben",
                       json={"von_konto_id": a, "nach_konto_id": b, "buchung_ids": bs[:2]}))
    assert r == {"verschoben": bs[:2], "anzahl": 2}
    assert ok(client.get(f"/api/buchungen?konto_id={b}"))["gesamt"] == 2
    letzte = ok(client.get("/api/aenderungen?pro_seite=1"))["eintraege"][0]
    assert letzte["aktion"] == "mehrfach_verschieben"
    ok(client.post(f"/api/aenderungen/{letzte['id']}/rueckgaengig"))
    assert ok(client.get(f"/api/buchungen?konto_id={a}"))["gesamt"] == 3


@pytest.mark.parametrize("koerper, code, fehler", [
    ({"nach_konto_id": "K"}, 422, "konto_ungueltig"),
    ({"nach_konto_id": 999}, 422, "referenz_unbekannt"),
    ({"nach_konto_id": "A"}, 422, "validierung"),
    ({"buchung_ids": [999]}, 422, "referenz_unbekannt"),
    ({"gruppe": "import:77"}, 422, "referenz_unbekannt"),
])
def test_verschieben_fehler(client: TestClient, koerper: dict, code: int, fehler: str) -> None:
    ids = {"A": konto(client, "A"), "B": konto(client, "B"), "K": konto(client, "Essen", "aufwand")}
    buchung(client, ids["A"], ids["K"], 100)
    d = {"von_konto_id": ids["A"], "nach_konto_id": ids["B"], "buchung_ids": [1]}
    d.update({k: ids.get(v, v) if isinstance(v, str) and k != "gruppe" else v for k, v in koerper.items()})
    if "gruppe" in koerper:
        del d["buchung_ids"]
    r = client.post("/api/buchungen/mehrfach/verschieben", json=d)
    assert r.status_code == code and r.json()["fehler"]["code"] == fehler, r.text


def test_verschieben_unmoeglich_und_gesperrt(client: TestClient) -> None:
    a, b = konto(client, "A"), konto(client, "B")
    k = konto(client, "Essen", "aufwand")
    umbuchung = ok(client.post("/api/buchungen", json={"datum": "2026-01-02", "splits": [
        {"konto_id": a, "betrag": -5}, {"konto_id": b, "betrag": 5}]}), 201)["id"]
    r = client.post("/api/buchungen/mehrfach/verschieben",
                    json={"von_konto_id": a, "nach_konto_id": b, "buchung_ids": [umbuchung]})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "verschieben_unmoeglich"
    x = buchung(client, a, k, 100)
    ok(client.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [x], "status": "abgeglichen"}))
    r = client.post("/api/buchungen/mehrfach/verschieben",
                    json={"von_konto_id": a, "nach_konto_id": b, "buchung_ids": [x]})
    assert r.status_code == 409 and r.json()["fehler"]["details"] == {"buchung_ids": [x]}


def test_verschieben_ganzer_import(client: TestClient) -> None:
    daten = kmy(konten=GIRO, transaktionen="".join(
        transaktion(f"T{i}", f"2026-01-0{i}", ("A1", "-10/1"), ("A2", "10/1")) for i in range(1, 4)))
    ok(client.post("/api/import/kmymoney", files={"datei": ("haushalt.kmy", daten)}))
    giro = next(k for k in ok(client.get("/api/konten")) if k["name"] == "Giro")
    ziel = konto(client, "Richtiges Giro")
    h = ok(client.get(f"/api/konten/{giro['id']}/herkunft"))
    assert [(x["art"], x["anzahl"]) for x in h] == [("import", 3)] and "KMyMoney" in h[0]["beschreibung"]
    r = ok(client.post("/api/buchungen/mehrfach/verschieben",
                       json={"von_konto_id": giro["id"], "nach_konto_id": ziel, "gruppe": h[0]["gruppe"]}))
    assert r["anzahl"] == 3
    assert ok(client.get(f"/api/konten/{giro['id']}/herkunft")) == []
    assert ok(client.get(f"/api/konten/{ziel}/herkunft"))[0]["anzahl"] == 3
    assert client.get("/api/konten/999/herkunft").status_code == 404


# ------------------------------------------------------------------ Zuordnung unbekannter Bankkonten (D-110)
def _mock_daten(pfad: Path, iban: str) -> Path:
    d = {"format": "kontor-mock-daten", "version": 1, "mail": {"postfaecher": [], "nachrichten": []},
         "bank": {"konten": [{"iban": iban, "bic": None, "name": "Giro Bank", "art": "girokonto",
                              "inhaber": "Erika Mustermann (fiktiv)", "waehrung": "EUR"}],
                  "umsaetze": [{"umsatz_id": f"U{i}", "iban": iban, "buchungstag": f"2026-01-0{i}", "valuta": None,
                                "betrag": -100 * i, "waehrung": "EUR", "gegenpartei_name": "Laden (fiktiv)",
                                "gegenpartei_iban": None, "verwendungszweck": "Einkauf", "vormerkung": False,
                                "storno": False} for i in range(1, 4)]}}
    datei = pfad / "mock.json"
    datei.write_text(json.dumps(d), encoding="utf-8")
    return datei


def _sync_client(tmp_path: Path, anlegen: bool, iban: str) -> TestClient:
    import datetime as dt
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                              mock_daten=_mock_daten(tmp_path, iban), planer_starten=False,
                                              mock_heute=dt.date(2026, 1, 20), sync_konten_anlegen=anlegen)))


def test_sync_ohne_anlegen_ueberspringt_und_benachrichtigt(tmp_path: Path) -> None:
    iban = test_iban(4711)
    c = _sync_client(tmp_path, False, iban)
    lauf = ok(c.post("/api/sync", json={}))
    assert lauf["status"] == "erfolgreich" and lauf["konten"] == []
    assert lauf["uebersprungen"] == [{"iban": iban, "name": "Giro Bank", "status": "nicht_zugeordnet",
                                      "art": "girokonto"}]
    assert not [k for k in ok(c.get("/api/konten")) if k["iban"] == iban]
    offen = [b for b in ok(c.get("/api/benachrichtigungen")) if b["art"] == "konto_nicht_zugeordnet"]
    assert len(offen) == 1 and not offen[0]["gelesen"]
    # Zuordnung über die Kontoeinstellungen (IBAN): Hinweis erledigt, nächster Lauf übernimmt die Umsätze
    k = konto(c, "Mein Giro")
    ok(c.patch(f"/api/konten/{k}", json={"iban": iban}))
    assert all(b["gelesen"] for b in ok(c.get("/api/benachrichtigungen")) if b["art"] == "konto_nicht_zugeordnet")
    lauf = ok(c.post("/api/sync", json={}))
    assert [(x["konto_id"], x["buchungen_neu"]) for x in lauf["konten"]] == [(k, 3)] and lauf["uebersprungen"] == []


def test_sync_mit_anlegen_wie_bisher(tmp_path: Path) -> None:
    iban = test_iban(4712)
    c = _sync_client(tmp_path, True, iban)
    lauf = ok(c.post("/api/sync", json={}))
    assert lauf["konten"][0]["konto_neu"] is True and lauf["uebersprungen"] == []


def test_konfiguration_sync_konten_anlegen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from kontor.fehler import KonfigurationsFehler
    monkeypatch.setenv("KONTOR_DATENBANK", str(tmp_path / "k.sqlite3"))
    assert KontorConfig.from_env().sync_konten_anlegen is True
    monkeypatch.setenv("KONTOR_SYNC_KONTEN_ANLEGEN", "0")
    assert KontorConfig.from_env().sync_konten_anlegen is False
    with pytest.raises(KonfigurationsFehler):
        KontorConfig(datenbank=tmp_path / "k.sqlite3", sync_konten_anlegen="ja")  # type: ignore[arg-type]


def test_ausgelieferte_umgebung_schaltet_anlegen_ab() -> None:
    from importlib import resources
    text = resources.files("kontor").joinpath("betrieb/kontor.env").read_text(encoding="utf-8")
    assert "\nKONTOR_SYNC_KONTEN_ANLEGEN=0\n" in text


# ------------------------------------------------------------------ Oberfläche: Plotly lokal (D-112)
def test_plotly_wird_lokal_ausgeliefert(client: TestClient) -> None:
    r = client.get("/oeffentlich/vendor/plotly-basic.min.js")
    assert r.status_code == 200 and b"window.Plotly" in r.content and b"new Function" not in r.content
    sw = client.get("/sw.js").text
    assert "/oeffentlich/vendor/plotly-basic.min.js" in sw
