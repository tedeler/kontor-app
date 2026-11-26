"""Eigene Tests zu den Sicherungspunkten (D-302), die für die Core-Tests zu lang laufen."""

from __future__ import annotations

import datetime as dt

from kontor import sicherungspunkte as sp
from tests.core.test_sicherung_stuendlich import UTC, punkte, umgebung  # noqa: F401 - Fixture


def test_ausduennen_ueber_siebzig_tage_mit_vorgaben(umgebung):  # noqa: F811 - Fixture
    config, c, buchen = umgebung
    zeiten = []
    t = dt.datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    # 70 Tage, je Tag zwei Punkte mit Änderung
    for tag in range(70):
        for stunde in (8, 20):
            zeit = t + dt.timedelta(days=tag, hours=stunde - 8)
            buchen(tag * 10 + stunde)
            sp.stunde(config, jetzt=zeit, ausduennen=False)
            zeiten.append(zeit)
    jetzt = zeiten[-1]
    sp.ausduennen(config, jetzt=jetzt)
    p = punkte(c)["punkte"]
    behalten = sorted(dt.datetime.fromisoformat(x["zeitpunkt"].replace("Z", "+00:00")) for x in p)
    letzte_48h = [z for z in zeiten if jetzt - z <= dt.timedelta(hours=48)]
    assert all(z in behalten for z in letzte_48h)
    tage = {z.date() for z in behalten if dt.timedelta(hours=48) < jetzt - z <= dt.timedelta(days=30)}
    assert all(z.replace(hour=20) in behalten for z in zeiten
               if dt.timedelta(days=3) < jetzt - z <= dt.timedelta(days=29))
    assert len(tage) >= 27
    alt = [z for z in behalten if jetzt - z > dt.timedelta(days=30)]
    assert len(alt) <= 6   # nur Wochenpunkte (und der Anker-Monatsanfang wird aufgelöst)
    assert len(behalten) < len(zeiten) / 2
    for x in p:
        assert sp.herstellen_pruefen(config, x["kennung"]) is True
        assert x["groesse_herstellen"] <= sum(y["groesse"] for y in p)
    # Ketten bleiben kurz: höchstens Anker → Tagespunkt → Stundenpunkte
    assert max(sp.kettenlaenge(config, x["kennung"]) for x in p) <= 2 + len(letzte_48h)


def test_kuerzen_behaelt_herkunft_und_rueckgaengig_paare(tmp_path):
    from fastapi.testclient import TestClient

    from kontor.app import create_app
    from kontor.config import KontorConfig
    from tests.conftest import GIRO, kmy, transaktion

    config = KontorConfig(datenbank=tmp_path / "k.sqlite3", sicherung_verzeichnis=tmp_path / "s")
    c = TestClient(create_app(config))
    roh = kmy(GIRO, transaktionen=transaktion("T1", "2024-01-02", ("A1", "-500/100"), ("A2", "500/100")))
    assert c.post("/api/import/kmymoney", files={"datei": ("d.kmy", roh, "application/gzip")}).status_code == 200
    giro = next(k["id"] for k in c.get("/api/konten").json() if k["name"] == "Giro")
    spar = c.post("/api/konten", json={"name": "Spar", "art": "sparkonto"}).json()["id"]
    vorher = c.get(f"/api/konten/{giro}/herkunft").json()
    assert [h["gruppe"] for h in vorher] == ["import:1"]
    # alte Änderung mit Rückgängig, das jünger ist als die Grenze: beide bleiben
    t = c.post("/api/tags", json={"name": "Alt"}).json()
    alt_id = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]["id"]
    con = __import__("sqlite3").connect(config.datenbank)
    con.execute("UPDATE aenderung SET zeitpunkt = '2000-01-01T00:00:00Z'")
    con.commit()
    assert c.post(f"/api/aenderungen/{alt_id}/rueckgaengig").status_code == 200
    jetzt = dt.datetime.now(UTC) + dt.timedelta(minutes=30)
    sp.stunde(config, jetzt=jetzt)
    ids = [a["id"] for a in c.get("/api/aenderungen", params={"pro_seite": 500}).json()["eintraege"]]
    assert alt_id in ids and len(ids) == 2      # Paar bleibt zusammen, Import und Konto-Anlage sind weg
    assert c.get(f"/api/konten/{giro}/herkunft").json()[0]["gruppe"] == "import:1"
    r = c.post("/api/buchungen/mehrfach/verschieben", json={"von_konto_id": giro, "nach_konto_id": spar,
                                                          "gruppe": "import:1"})
    assert r.status_code == 200 and r.json()["anzahl"] == 1, r.text
    assert t["name"] == "Alt"


def test_prueflauf_meldet_beschaedigte_punkte(umgebung):  # noqa: F811 - Fixture
    config, c, buchen = umgebung
    buchen(1)
    a = sp.stunde(config, jetzt=dt.datetime(2026, 11, 2, 10, tzinfo=UTC))["punkt"]["kennung"]
    buchen(2)
    b = sp.stunde(config, jetzt=dt.datetime(2026, 11, 2, 11, tzinfo=UTC))["punkt"]["kennung"]
    assert punkte(c)["prueflauf"]["fehler"] == []
    sp.datei_pfad(config, a).write_bytes(b"kaputt")
    with sp.Ablage(config).gesperrt() as ab:
        assert sp.prueflauf(ab, dt.datetime(2026, 11, 3, 0, 5, tzinfo=UTC)) == sorted([a, b])
    assert punkte(c)["prueflauf"]["fehler"] == sorted([a, b])
