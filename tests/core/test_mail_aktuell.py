"""Core-Tests zum Feature „mail-aktuell“ (D-284).

- Ein offenes Kontoblatt zeigt, was ein Mail-Abruf an Buchungen gehängt hat, ohne dass man es schließen muss:
  ``GET /api/bestand/stand`` nennt die jüngste Änderung am Buchbestand; die Oberfläche fragt sie regelmäßig ab und
  lädt offene Ansichten neu, wenn sie sich ohne eigenes Zutun geändert hat (Planer, anderes Gerät). Nach einem
  Abruf aus der Oberfläche gelten die übrigen Tabs sofort als veraltet. Das Verhalten im Browser prüft
  ``tests/test_browser_mail_aktuell.py``.
- Der Mail-Abruf läuft von selbst im Takt der Kontosynchronisation, solange ``KONTOR_MAIL_INTERVALL_MINUTEN``
  nicht gesetzt ist; der Stand des Abrufs nennt die Automatik.
"""

from __future__ import annotations

from importlib import resources

from fastapi.testclient import TestClient

from kontor import abgleich, db
from kontor.app import create_app
from kontor.config import KontorConfig

NR = "302-1234567-7654321"
ENV = {"KONTOR_DATENBANK": "/tmp/x.sqlite3"}


def _stand(c: TestClient) -> int:
    r = c.get("/api/bestand/stand")
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"stand"} and isinstance(r.json()["stand"], int)
    return r.json()["stand"]


def test_bestand_stand_aendert_sich_mit_dem_buchbestand(tmp_path):
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mail_bestellnummer=True, planer_starten=False)
    c = TestClient(create_app(cfg))
    anfang = _stand(c)
    assert _stand(c) == anfang, "ohne Änderung bleibt der Stand gleich"
    assert c.post("/api/mail/postfaecher", json={"adresse": "erika@example.invalid"}).status_code == 201
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Einkauf", "art": "aufwand"}).json()["id"]
    r = c.post("/api/buchungen", json={"datum": "2024-03-03", "verwendungszweck": f"{NR} AMZN Mktp DE fiktiv",
                                      "splits": [{"konto_id": giro, "betrag": -4990}, {"konto_id": kat, "betrag": 4990}]})
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    von_hand = _stand(c)
    assert von_hand > anfang, "eine Änderung von Hand erhöht den Stand"

    # eine Mail im Spiegel; der Abgleich nach dem Abruf hängt sie an die Buchung
    con = db.verbinde(cfg.aktive_datenbank)
    try:
        with db.transaktion(con):
            con.execute("INSERT INTO mail_nachricht (adresse_cf, nachricht_id, empfangen, absender, betreff, text, roh)"
                        " VALUES ('erika@example.invalid', '<a1@example.invalid>', '2024-03-01T10:00:00Z',"
                        " 'versand@amazon.example.invalid', ?, 'ohne Summe', NULL)", (f"Bestellt: Kabel (fiktiv) {NR}",))
    finally:
        con.close()
    abgleich.nach_ereignis(cfg, c.app.state.sync.jetzt())
    assert len(c.get(f"/api/buchungen/{bid}").json()["belege"]) == 1
    nach_mail = _stand(c)
    assert nach_mail > von_hand, "die Zuordnung einer Mail erhöht den Stand"

    abgleich.nach_ereignis(cfg, c.app.state.sync.jetzt())
    assert _stand(c) == nach_mail, "ein Abgleich ohne Wirkung ändert den Stand nicht"


def test_mail_intervall_folgt_der_kontosynchronisation():
    def mail(**env) -> int:
        return KontorConfig.from_env({**ENV, **env}).mail_intervall_minuten

    assert mail() == 0
    assert mail(KONTOR_SYNC_INTERVALL_MINUTEN="240") == 240, "ohne eigene Angabe wie die Kontosynchronisation"
    assert mail(KONTOR_SYNC_INTERVALL_MINUTEN="240", KONTOR_MAIL_INTERVALL_MINUTEN="0") == 0, "0 schaltet ab"
    assert mail(KONTOR_SYNC_INTERVALL_MINUTEN="240", KONTOR_MAIL_INTERVALL_MINUTEN="30") == 30
    assert mail(KONTOR_MAIL_INTERVALL_MINUTEN="30") == 30
    assert KontorConfig.from_env({**ENV, "KONTOR_MAIL_INTERVALL_MINUTEN": "30"}).sync_intervall_minuten == 0


def test_ausgelieferte_umgebung():
    text = resources.files("kontor.betrieb").joinpath("kontor.env").read_text(encoding="utf-8")
    assert "\nKONTOR_SYNC_INTERVALL_MINUTEN=240\n" in text
    assert "\nKONTOR_MAIL_INTERVALL_MINUTEN=" not in text, "ohne Angabe folgt der Mail-Abruf der Kontosynchronisation"
    test = resources.files("kontor.betrieb").joinpath("kontor-test.env").read_text(encoding="utf-8")
    assert "\nKONTOR_MAIL_INTERVALL_MINUTEN=0\n" in test, "die Testinstanz ruft nicht von selbst ab"


def test_abruf_stand_nennt_die_automatik(tmp_path):
    aus = TestClient(create_app(KontorConfig(datenbank=tmp_path / "a.sqlite3", planer_starten=False)))
    st = aus.get("/api/mail/abruf/stand").json()
    assert (st["automatisch"], st["intervall_minuten"]) == (False, 0)
    an = TestClient(create_app(KontorConfig(datenbank=tmp_path / "b.sqlite3", planer_starten=False,
                                            mail_intervall_minuten=90)))
    st = an.get("/api/mail/abruf/stand").json()
    assert (st["automatisch"], st["intervall_minuten"]) == (True, 90)


def test_oberflaeche_haelt_offene_ansichten_aktuell(auslieferung):
    haupt = auslieferung.get("/oeffentlich/app/haupt.js").text
    assert "/api/bestand/stand" in haupt, "haupt.js fragt den Stand des Buchbestands nicht ab"
    for datei in ("mail.js", "einstellungen.js"):
        js = auslieferung.get(f"/oeffentlich/app/{datei}").text
        assert "bestandGeaendert" in js, f"{datei}: nach dem Mail-Abruf bleiben die übrigen Tabs auf altem Stand"
