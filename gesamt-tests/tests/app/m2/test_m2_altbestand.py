"""M2: Abgleich beim Abruf mit vorhandenem Altbestand aus KMyMoney (synchronisation.md 4.4, T 6).

Erwartung: bekannte Wahrheit des Generators (``abgleich_altbestand``), die in
``tests/generator/test_sync_daten.py`` mit einem unabhängigen Orakel geprüft ist.
"""

from __future__ import annotations

import pytest

from tests.hilfen import sync_orakel as orakel
from tests.hilfen.erwartung import lade
from tests.hilfen.m2 import konto_nach_iban, lade_sync, mock_api, nach_kennung, sync
from tests.hilfen.pfade import KMY

VON = "2024-01-01"


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


@pytest.fixture
def aapi(tmp_path):
    api = mock_api(tmp_path)
    api.import_kmy(KMY / "sync_altbestand.kmy", erwartet=200)
    return api


def _kmy(api) -> dict[str, dict]:
    return nach_kennung(api.alle_buchungen(), "kmy:")


@pytest.mark.kern
def test_abgleich_nach_wahrheit(aapi, sd, netz_gesperrt):
    daten, erw = sd
    vorher = {e: b for e, b in _kmy(aapi).items()}
    lauf = sync(aapi, von=VON)
    assert lauf["status"] == "erfolgreich"
    bs = aapi.alle_buchungen()
    bank = nach_kennung(bs)
    kmy = _kmy(aapi)
    verdachte = {v["buchung_id"]: v for v in aapi.get("/api/dubletten", erwartet=200).daten}
    alle = {u["umsatz_id"]: u for u in daten["bank"]["umsaetze"]}
    for uid, w in erw["abgleich_altbestand"].items():
        u = alle[uid]
        k = orakel.kennung(u)
        if w["ergebnis"] == "vormerkung":
            assert k not in bank
        elif w["ergebnis"] == "zusammengefuehrt":
            (tid,) = w["mit"]
            c = kmy["kmy:" + tid]
            assert bank[k]["id"] == c["id"], f"{uid} nicht mit {tid} zusammengeführt"
            alt = vorher["kmy:" + tid]
            assert {f: c[f] for f in c if f != "extern_ids"} == {f: alt[f] for f in alt if f != "extern_ids"}, \
                "zusammengeführte Buchung darf sich sonst nicht ändern"
        else:
            b = bank[k]
            assert b["extern_ids"] == [k], f"{uid}: neue Buchung erwartet"
            if w["ergebnis"] == "zur_pruefung":
                v = verdachte[b["id"]]
                assert v["status"] == "offen" and v["grund"] == w["grund"]
                assert v["kandidat_ids"] == sorted(kmy["kmy:" + t]["id"] for t in w["kandidaten"])
            else:
                assert b["id"] not in verdachte
    assert len(verdachte) == sum(w["ergebnis"] == "zur_pruefung" for w in erw["abgleich_altbestand"].values())
    for b in bs:
        assert b["extern_ids"] == sorted(b["extern_ids"])


def test_umbuchung_beide_seiten(aapi, sd, netz_gesperrt):
    daten, erw = sd
    sync(aapi, von=VON)
    zf = {}
    for uid, w in erw["abgleich_altbestand"].items():
        if w["ergebnis"] == "zusammengefuehrt":
            zf.setdefault(w["mit"][0], []).append(uid)
    doppelt = {t: us for t, us in zf.items() if len(us) == 2}
    assert doppelt
    alle = {u["umsatz_id"]: u for u in daten["bank"]["umsaetze"]}
    kmy = _kmy(aapi)
    for tid, us in doppelt.items():
        assert kmy["kmy:" + tid]["extern_ids"] == sorted(["kmy:" + tid] + [orakel.kennung(alle[u]) for u in us])


def test_zaehlungen_und_salden(aapi, sd, netz_gesperrt):
    daten, erw = sd
    kmy_erw = lade("sync_altbestand")
    lauf = sync(aapi, von=VON)
    alle = {u["umsatz_id"]: u for u in daten["bank"]["umsaetze"]}
    for sk in lauf["konten"]:
        ws = [w for uid, w in erw["abgleich_altbestand"].items() if alle[uid]["iban"] == sk["iban"]]
        zp = sum(w["ergebnis"] == "zur_pruefung" for w in ws)
        assert sk["buchungen_zusammengefuehrt"] == sum(w["ergebnis"] == "zusammengefuehrt" for w in ws)
        assert sk["buchungen_zur_pruefung"] == zp
        assert sk["buchungen_neu"] == zp + sum(w["ergebnis"] == "neu" for w in ws)
        assert sk["vormerkungen_ignoriert"] == sum(w["ergebnis"] == "vormerkung" for w in ws)
    konten = konto_nach_iban(aapi)
    altsaldo = {k["iban"]: k["saldo"] for k in kmy_erw["konten"] if k["iban"]}
    s = aapi.salden()
    for iban, k in konten.items():
        neu = sum(alle[uid]["betrag"] for uid, w in erw["abgleich_altbestand"].items()
                  if alle[uid]["iban"] == iban and w["ergebnis"] in ("neu", "zur_pruefung"))
        assert s[k["id"]]["saldo"] == altsaldo.get(iban, 0) + neu, k["name"]
    kk = next(sk for sk in lauf["konten"] if sk["iban"] == erw["ibans"]["kredit"])
    assert kk["konto_neu"] is True
    assert all(sk["konto_neu"] is False for sk in lauf["konten"] if sk["iban"] != erw["ibans"]["kredit"])


@pytest.mark.kern
def test_wiederholung_und_reimport_idempotent(aapi, sd, netz_gesperrt):
    sync(aapi, von=VON)
    vorher = aapi.zustand()
    lauf = sync(aapi, von=VON)
    assert all(sk["buchungen_neu"] == sk["buchungen_zusammengefuehrt"] == 0 for sk in lauf["konten"])
    e = aapi.import_kmy(KMY / "sync_altbestand.kmy", erwartet=200).daten
    assert e["buchungen_neu"] == e["buchungen_zusammengefuehrt"] == e["buchungen_zur_pruefung"] == 0
    assert aapi.zustand() == vorher


def test_verdacht_aufloesen_und_merken(aapi, sd, netz_gesperrt):
    sync(aapi, von=VON)
    offen = aapi.get("/api/dubletten", params={"status": "offen"}, erwartet=200).daten
    assert len(offen) >= 2
    v1, v2 = offen[0], offen[1]
    neu = aapi.buchung_lesen(v1["buchung_id"])
    kennung = neu["extern_ids"][0]
    behalten = v1["kandidat_ids"][0]
    aapi.post(f"/api/dubletten/{v1['id']}/aufloesen", json={"entscheidung": "zusammenfuehren",
                                                           "behalten_id": behalten}, erwartet=200)
    assert kennung in aapi.buchung_lesen(behalten)["extern_ids"]
    aapi.post(f"/api/dubletten/{v2['id']}/aufloesen", json={"entscheidung": "keine_dublette"}, erwartet=200)
    vorher = aapi.zustand()
    lauf = sync(aapi, von=VON)
    assert all(sk["buchungen_neu"] == 0 for sk in lauf["konten"]), "aufgelöste Umsätze dürfen nicht wiederkommen"
    assert aapi.zustand() == vorher


def test_manuelle_buchung_ist_kandidat(tmp_path, sd, netz_gesperrt):
    """Eine vorab manuell erfasste Buchung wird beim Abruf exakt erkannt und zusammengeführt."""
    daten, erw = sd
    api = mock_api(tmp_path)
    g = api.konto("Giro", iban=erw["ibans"]["giro"])
    kat = api.konto("Miete", "aufwand")
    e = api.empfaenger("Wohnbau Beispiel eG")
    miete = next(u for u in daten["bank"]["umsaetze"] if u["verwendungszweck"] == "Miete 03/2024")
    m = api.buchung(miete["buchungstag"], [(g["id"], miete["betrag"]), (kat["id"], -miete["betrag"])],
                    empfaenger_id=e["id"], verwendungszweck="von Hand")
    sync(api, von=VON)
    b = api.buchung_lesen(m["id"])
    assert b["extern_ids"] == [orakel.kennung(miete)]
    assert (b["kategorie_id"], b["verwendungszweck"], b["status"]) == (kat["id"], "von Hand", "bestaetigt")
    assert api.get("/api/dubletten", erwartet=200).daten == []
