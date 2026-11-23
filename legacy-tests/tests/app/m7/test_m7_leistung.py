"""M7: Leistung mit 50 000 Buchungen (leistung.md, T 20, E-133).

Ein Aufwärmlauf, dann fünf Läufe; maßgeblich ist der Median. Jede Messung prüft zusätzlich das Ergebnis
gegen die Generatorwahrheit (``gross.erwartung.json``). ``KONTOR_LEISTUNG_FAKTOR`` skaliert die Grenzen.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import time

import pytest

from generator import STARTWERT
from generator.__main__ import gross_dateien
from tests.hilfen import kontor
from tests.hilfen.api import Api, neue_config
from tests.hilfen.pfade import FIXTURES
from tests.hilfen.vertrag import vertrag

pytestmark = [pytest.mark.leistung, pytest.mark.langsam]
FAKTOR = float(os.environ.get("KONTOR_LEISTUNG_FAKTOR", "1") or "1")
GROSS = FIXTURES / "gross"


def _dateien() -> tuple[bytes, dict]:
    """gross.kmy auf Abruf erzeugen (E-134) und gegen MANIFEST.json prüfen."""
    kmy, erw = GROSS / "gross.kmy", GROSS / "gross.erwartung.json"
    soll = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))["auf_abruf"]
    if not (kmy.exists() and erw.exists()
            and hashlib.sha256(kmy.read_bytes()).hexdigest() == soll["gross/gross.kmy"]["sha256"]
            and hashlib.sha256(erw.read_bytes()).hexdigest() == soll["gross/gross.erwartung.json"]["sha256"]):
        GROSS.mkdir(parents=True, exist_ok=True)
        for name, inhalt in gross_dateien(STARTWERT).items():
            (FIXTURES / name).write_bytes(inhalt)
    return kmy.read_bytes(), json.loads(erw.read_text(encoding="utf-8"))


class Messung:
    def __init__(self, tmp_path_factory) -> None:
        self.datei, self.erw = _dateien()
        self.config = neue_config(tmp_path_factory.mktemp("leistung"))
        self.api = Api(self.config)
        beginn = time.perf_counter()
        r = self.api.client.post("/api/import/kmymoney",
                                 files={"datei": ("gross.kmy", self.datei, "application/octet-stream")})
        self.import_dauer = time.perf_counter() - beginn
        self.import_antwort = r
        konten = self.api.konten()
        self.konto = {k["name"]: k["id"] for k in konten}
        self.empfaenger = {e["name"]: e["id"] for e in self.api.get("/api/empfaenger", erwartet=200).daten}
        self.tag = {t["name"]: t["id"] for t in self.api.get("/api/tags", erwartet=200).daten}

    def zeit(self, methode: str, pfad: str, *, wiederholungen: int = 5, **kw):
        """Median der Dauer (Sekunden) und die letzte, gegen den Vertrag geprüfte Antwort."""
        self.api.client.request(methode, pfad, **kw)  # Aufwärmen
        dauern, r = [], None
        for _ in range(wiederholungen):
            beginn = time.perf_counter()
            r = self.api.client.request(methode, pfad, **kw)
            dauern.append(time.perf_counter() - beginn)
        assert r.status_code < 300, f"{methode} {pfad} → {r.status_code}: {r.text[:500]}"
        daten = vertrag().pruefe_antwort(methode, pfad.split("?")[0], r.status_code, r.content,
                                         r.headers.get("content-type"))
        return statistics.median(dauern), daten


def grenze(sekunden: float) -> float:
    return sekunden * FAKTOR


@pytest.fixture(scope="module")
def m(tmp_path_factory):
    kontor.app_importfehler()
    return Messung(tmp_path_factory)


def test_l1_import(m):
    r = m.import_antwort
    assert r.status_code == 200, r.text[:500]
    erg = vertrag().pruefe_antwort("POST", "/api/import/kmymoney", 200, r.content, r.headers.get("content-type"))
    for k, v in m.erw["ergebnis"].items():
        assert erg[k] == v, k
    assert m.import_dauer <= grenze(120), f"L1 Import {m.import_dauer:.1f} s > 120 s"
    salden = m.api.salden()
    for name, saldo in m.erw["salden"].items():
        assert salden[m.konto[name]]["saldo"] == saldo, name


def test_l2_zweiter_import(m):
    beginn = time.perf_counter()
    r = m.api.client.post("/api/import/kmymoney", files={"datei": ("gross.kmy", m.datei, "application/octet-stream")})
    dauer = time.perf_counter() - beginn
    assert r.status_code == 200
    d = r.json()
    assert d["buchungen_neu"] == 0 and d["buchungen_vorhanden"] == 50_000
    assert dauer <= grenze(120), f"L2 zweiter Import {dauer:.1f} s > 120 s"


def test_l3_l4_buchungsliste(m):
    t, d = m.zeit("GET", "/api/buchungen", params={"pro_seite": 100})
    assert d["gesamt"] == 50_000 and len(d["eintraege"]) == 100
    assert t <= grenze(1.0), f"L3 Buchungsliste {t:.3f} s > 1 s"
    t, d = m.zeit("GET", "/api/buchungen", params={"pro_seite": 100, "seite": 500})
    assert len(d["eintraege"]) == 100
    assert t <= grenze(1.0), f"L4 letzte Seite {t:.3f} s > 1 s"


def _filter(m) -> list[tuple[str, dict, int | None]]:
    p = m.erw["proben"]
    return [
        ("konto_id", {"konto_id": m.konto[p["konto"]["name"]]}, p["konto"]["anzahl"]),
        ("von/bis", {"von": p["zeitraum"]["von"], "bis": p["zeitraum"]["bis"]}, p["zeitraum"]["anzahl"]),
        ("kategorie", {"kategorie_id": m.konto[p["kategorie"]["name"]], "unterkategorien": "true"},
         p["kategorie"]["anzahl"]),
        ("empfaenger_id", {"empfaenger_id": m.empfaenger[p["empfaenger"]["name"]]}, p["empfaenger"]["anzahl"]),
        ("verwendungszweck", {"verwendungszweck": p["zebra"]["text"]}, p["zebra"]["anzahl"]),
        ("suche", {"suche": p["zebra"]["text"]}, p["zebra"]["anzahl"]),
        ("betrag", {"betrag_min": p["betrag"]["min"], "betrag_max": p["betrag"]["max"]}, p["betrag"]["anzahl"]),
        ("tag_id", {"tag_id": m.tag[p["tag"]["name"]]}, p["tag"]["anzahl"]),
        ("sortierung", {"sortierung": "-betrag"}, 50_000),
    ]


@pytest.mark.parametrize("nr", range(9))
def test_l5_filter(m, nr):
    name, params, anzahl = _filter(m)[nr]
    t, d = m.zeit("GET", "/api/buchungen", params={**params, "pro_seite": 100})
    assert d["gesamt"] == anzahl, (name, d["gesamt"], anzahl)
    if name == "sortierung":
        betraege = [b["betrag"] for b in d["eintraege"]]
        assert betraege == sorted(betraege, reverse=True)
    assert t <= grenze(1.0), f"L5 Filter {name}: {t:.3f} s > 1 s"


def test_l6_kombination(m):
    p = m.erw["proben"]["kombination"]
    t, d = m.zeit("GET", "/api/buchungen", params={"konto_id": m.konto[p["konto"]], "von": p["von"], "bis": p["bis"],
                                                     "suche": p["suche"], "pro_seite": 100})
    assert d["gesamt"] == p["anzahl"]
    assert t <= grenze(1.0), f"L6 kombinierte Filter {t:.3f} s > 1 s"


def test_l7_suche_und_uebersicht(m):
    t, d = m.zeit("GET", "/api/suche", params={"q": m.erw["proben"]["zebra"]["text"]})
    assert t <= grenze(1.0), f"L7 Volltextsuche {t:.3f} s > 1 s"
    t, d = m.zeit("GET", "/api/kontenuebersicht")
    assert t <= grenze(1.0), f"L7 Kontenübersicht {t:.3f} s > 1 s"
    assert d["summe_gesamt"] == 0


def test_l10_berichte(m):
    t, d = m.zeit("GET", "/api/berichte/kontostand", params={"intervall": "monat", "von": "2019-01-01",
                                                               "bis": "2024-12-31"})
    assert t <= grenze(3.0), f"L10 Kontostandsverlauf {t:.3f} s > 3 s"
    t, d = m.zeit("GET", "/api/berichte/einnahmen-ausgaben", params={"von": "2019-01-01", "bis": "2024-12-31"})
    assert t <= grenze(3.0), f"L10 Einnahmen/Ausgaben {t:.3f} s > 3 s"


def test_l11_lernmodell(m):
    eintraege = [{"empfaenger": m.erw["proben"]["empfaenger"]["name"] if i % 2 else "Unbekannt GmbH",
                  "verwendungszweck": f"Einkauf {i}", "betrag": -1000 - i} for i in range(100)]
    t, d = m.zeit("POST", "/api/lernmodell/vorhersage", json={"eintraege": eintraege})
    assert len(d["ergebnisse"]) == 100
    assert t <= grenze(3.0), f"L11 Lernmodell {t:.3f} s > 3 s"


def test_l12_wiederkehrend(m):
    t, _ = m.zeit("GET", "/api/wiederkehrend", wiederholungen=3, params={"stichtag": "2024-12-31"})
    assert t <= grenze(10.0), f"L12 wiederkehrende Buchungen {t:.3f} s > 10 s"


def test_l13_csv(m):
    beginn = time.perf_counter()
    r = m.api.client.get("/api/export/buchungen.csv")
    dauer = time.perf_counter() - beginn
    assert r.status_code == 200 and r.content.count(b"\n") > 50_000
    assert dauer <= grenze(20.0), f"L13 CSV-Export {dauer:.1f} s > 20 s"


def test_l14_sicherung(m):
    beginn = time.perf_counter()
    r = m.api.client.get("/api/sicherung")
    dauer = time.perf_counter() - beginn
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert dauer <= grenze(30.0), f"L14 Sicherung {dauer:.1f} s > 30 s"


def test_l15_neustart(m):
    beginn = time.perf_counter()
    kontor.create_app(m.config)
    dauer = time.perf_counter() - beginn
    assert dauer <= grenze(5.0), f"L15 create_app {dauer:.2f} s > 5 s"


# schreibende Messungen zuletzt (verändern den Bestand)
def test_l8_mehrfachbearbeitung(m):
    p = m.erw["proben"]["kategorie"]
    ids: list[int] = []
    seite = 1
    while len(ids) < 1000:
        d = m.api.get("/api/buchungen", params={"kategorie_id": m.konto[p["name"]], "unterkategorien": "true",
                                                "pro_seite": 500, "seite": seite}, erwartet=200).daten
        ids += [b["id"] for b in d["eintraege"] if len(b["splits"]) == 2 and b["kategorie_id"] is not None]
        seite += 1
    ids = ids[:1000]
    ziel = m.konto["Freizeit – Abos"]
    beginn = time.perf_counter()
    r = m.api.client.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": ids, "kategorie_id": ziel})
    dauer = time.perf_counter() - beginn
    assert r.status_code == 200, r.text[:500]
    assert r.json()["anzahl"] == 1000
    assert dauer <= grenze(10.0), f"L8 Mehrfachbearbeitung {dauer:.2f} s > 10 s"


def test_l9_einzelaenderung(m):
    b = m.api.get("/api/buchungen", params={"pro_seite": 1}, erwartet=200).daten["eintraege"][0]
    beginn = time.perf_counter()
    r = m.api.client.patch(f"/api/buchungen/{b['id']}", json={"verwendungszweck": "Geändert für L9"})
    dauer = time.perf_counter() - beginn
    assert r.status_code == 200 and r.json()["verwendungszweck"] == "Geändert für L9"
    assert dauer <= grenze(1.0), f"L9 Einzeländerung {dauer:.3f} s > 1 s"
