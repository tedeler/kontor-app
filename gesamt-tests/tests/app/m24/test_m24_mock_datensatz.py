"""M24: eingebauter Mock-Datensatz mit Amazon-/PayPal-Mails und passenden Umsätzen (erwartungen.md 13.3; E-235).
REST-Test ohne ``kern``."""

from __future__ import annotations

from tests.hilfen.m2 import mock_api
from tests.hilfen.m6 import EINS, ZWEI, abruf, postfach
from tests.hilfen.m20 import abgleich, liste


def test_eingebaute_mails_ende_zu_ende(tmp_path, netz_gesperrt):
    api = mock_api(tmp_path, daten=None, heute="2024-06-30", mail_abgleich=True, mail_erstabruf_tage=366)
    postfach(api, EINS)
    postfach(api, ZWEI)
    lauf = api.post("/api/sync", json={}, erwartet=200).daten
    assert lauf["status"] == "erfolgreich", lauf
    e = abruf(api)
    assert [x["status"] for x in e["postfaecher"]] == ["erfolgreich", "erfolgreich"], e
    abgleich(api)
    erfuellt = liste(api, zustand="erfuellt")["eintraege"]
    gruende = {x["grund"] for x in erfuellt}
    assert {"bestellung", "paypal"} <= gruende, erfuellt
    for x in erfuellt:
        if x["grund"] in ("bestellung", "paypal"):
            assert x["buchung_ids"]
            for bid in x["buchung_ids"]:
                assert api.buchung_lesen(bid)["belege"], f"Buchung {bid} ohne Belege"
    amazon = [x for x in erfuellt if x["grund"] == "bestellung"]
    assert all(x["anbieter"] == "amazon" and len(x["kennung"]) == 19 for x in amazon)
    paypal = [x for x in erfuellt if x["grund"] == "paypal"]
    assert any("Seitenweise" in x["haendler"] for x in paypal)
