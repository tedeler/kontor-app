"""Eigene Tests zu den Sicherungspunkten (D-302), die für die Core-Tests zu lang laufen."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from kontor import sicherungspunkte as sp
from kontor.app import create_app
from kontor.config import KontorConfig
from tests.core.test_sicherung_stuendlich import T0, UTC, inhalt, punkte, umgebung  # noqa: F401 - Fixture


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

def test_jeder_punkt_als_eigenstaendige_datei(umgebung, tmp_path):  # noqa: F811 - Fixture
    config, c, buchen = umgebung
    staende = []
    for i in range(3):
        buchen(100 + i)
        k = sp.stunde(config, jetzt=T0 + dt.timedelta(hours=i))["punkt"]["kennung"]
        staende.append((k, inhalt(c)))
    # in einer anderen Instanz einspielbar und gleich dem damaligen Stand
    frisch = TestClient(create_app(KontorConfig(datenbank=tmp_path / "neu.sqlite3",
                                                sicherung_verzeichnis=tmp_path / "s-neu")))
    for k, soll in reversed(staende):
        r = c.get(f"/api/sicherung/punkte/{k}/datei")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        e = frisch.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
                        files={"datei": ("s.zip", r.content, "application/zip")})
        assert e.status_code == 200, e.text
        assert inhalt(frisch) == soll
    assert c.get("/api/sicherung/punkte/unbekannt/datei").status_code == 404


def test_zurueck_und_vorwaerts(umgebung):  # noqa: F811 - Fixture
    config, c, buchen = umgebung
    buchen(1)
    a = sp.stunde(config, jetzt=T0)["punkt"]["kennung"]
    stand_a = inhalt(c)
    buchen(2)
    b = sp.stunde(config, jetzt=T0 + dt.timedelta(hours=1))["punkt"]["kennung"]
    buchen(3)   # noch nicht gesichert
    stand_jetzt = inhalt(c)
    assert c.post(f"/api/sicherung/punkte/{a}/wechseln").status_code == 409   # Bestätigung fehlt
    r = c.post(f"/api/sicherung/punkte/{a}/wechseln", params={"bestaetigt": "true"})
    assert r.status_code == 200, r.text
    vorher = r.json()["vorher"]
    assert vorher not in (a, b) and r.json()["ziel"] == a
    assert inhalt(c) == stand_a
    p = punkte(c)
    assert p["bezugspunkt"] == a and p["unveraendert"] is True
    vp = next(x for x in p["punkte"] if x["kennung"] == vorher)
    assert "vor_wiederherstellung" in vp["marken"]
    # Vorwärts auf den ungesicherten Stand vor dem Wechsel
    r = c.post(f"/api/sicherung/punkte/{vorher}/wechseln", params={"bestaetigt": "true"})
    assert r.status_code == 200, r.text
    assert inhalt(c) == stand_jetzt
    # derselbe Stand: nichts zu tun; Stand vor dem Wechsel war schon gesichert (Marke am bestehenden Punkt)
    r = c.post(f"/api/sicherung/punkte/{vorher}/wechseln", params={"bestaetigt": "true"})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "stand_unveraendert"
    p = punkte(c)["punkte"]
    assert len(p) == 3   # a, b, vorher; beim Vorwärts entsprach der Stand a, a erhielt nur die Marke
    assert "vor_wiederherstellung" in next(x for x in p if x["kennung"] == a)["marken"]
    assert c.post("/api/sicherung/punkte/xyz/wechseln", params={"bestaetigt": "true"}).status_code == 404


def test_einspielen_sichert_vorher_und_scheitert_ohne_sicherung(umgebung, tmp_path):  # noqa: F811 - Fixture
    config, c, buchen = umgebung
    buchen(1)
    datei = c.get("/api/sicherung").content
    buchen(2)
    stand = inhalt(c)
    r = c.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
               files={"datei": ("s.zip", datei, "application/zip")})
    assert r.status_code == 200, r.text
    p = punkte(c)
    marken = {m for x in p["punkte"] for m in x["marken"]}
    assert {"vor_wiederherstellung", "aus_datei"} <= marken
    vor = next(x for x in p["punkte"] if "vor_wiederherstellung" in x["marken"])
    assert c.post(f"/api/sicherung/punkte/{vor['kennung']}/wechseln", params={"bestaetigt": "true"}).status_code == 200
    assert inhalt(c) == stand
    # Ablage nicht beschreibbar: nichts wird gelöscht
    kaputt = tmp_path / "blockiert"
    kaputt.write_text("keine Ablage")
    c2 = TestClient(create_app(KontorConfig(datenbank=config.datenbank, sicherung_verzeichnis=kaputt)))
    r = c2.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
                files={"datei": ("s.zip", datei, "application/zip")})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "sicherung_vorher_fehlgeschlagen"
    assert inhalt(c2) == stand


def test_ausduennen_behaelt_stufen_und_alles_bleibt_herstellbar(umgebung):  # noqa: F811 - Fixture
    config, c, buchen = umgebung
    import dataclasses
    config = dataclasses.replace(config, sicherung_tage=8)   # kleine Stufen halten den Test schnell
    t = dt.datetime(2026, 10, 10, 20, 0, tzinfo=UTC)
    zeiten = [t + dt.timedelta(days=tag) for tag in range(20)]          # ein Punkt je Tag
    zeiten += [zeiten[-1] + dt.timedelta(hours=h) for h in (2, 4, 6)]   # und drei in den letzten Stunden
    for i, zeit in enumerate(zeiten):
        buchen(100 + i)
        sp.stunde(config, jetzt=zeit, ausduennen=False)
    jetzt = zeiten[-1]
    sp.ausduennen(config, jetzt=jetzt)
    p = punkte(c)["punkte"]
    behalten = sorted(dt.datetime.fromisoformat(x["zeitpunkt"].replace("Z", "+00:00")) for x in p)
    stunden = [z for z in zeiten if jetzt - z <= dt.timedelta(hours=48)]
    tage = [z for z in zeiten if dt.timedelta(hours=48) < jetzt - z <= dt.timedelta(days=8)]
    alt = [z for z in zeiten if jetzt - z > dt.timedelta(days=8)]
    assert all(z in behalten for z in stunden + tage)
    wochen = {tuple(z.isocalendar())[:2] for z in alt}
    assert sorted(z for z in behalten if z in alt) == sorted(max(z for z in alt if tuple(z.isocalendar())[:2] == w)
                                                           for w in wochen)
    for x in p:
        assert sp.herstellen_pruefen(config, x["kennung"]) is True
    # Ketten bleiben kurz: höchstens Anker → Tages-/Wochenpunkt → Stundenpunkte
    assert max(sp.kettenlaenge(config, x["kennung"]) for x in p) <= 2 + len(stunden)
    assert sum(1 for x in p if x["anker"]) <= 2   # je Monat höchstens ein Anker
    # angeheftete Punkte bleiben auch nach Ablauf aller Stufen
    k = p[-1]["kennung"]
    assert c.patch(f"/api/sicherung/punkte/{k}", json={"angeheftet": True}).status_code == 200
    sp.ausduennen(dataclasses.replace(config, sicherung_wochen=0, sicherung_monate=0), jetzt=jetzt)
    assert k in {x["kennung"] for x in punkte(c)["punkte"]}
    assert sp.herstellen_pruefen(config, k) is True
