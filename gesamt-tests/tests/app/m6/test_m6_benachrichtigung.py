"""M6: Zustellung von Benachrichtigungen per ntfy und Mock (benachrichtigungen.md 2–4; T 17, T 21)."""

from __future__ import annotations

import json
import logging

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api, fehlercode
from tests.hilfen.m2 import SYNC_DATEN, lade_sync, mock_config, setze_zeit
from tests.hilfen.m6 import (
    NTFY_TOKEN, THEMA, benachrichtigungen, config, geheimnis_setzen, lade, ntfy_felder, zeit, zustellung,
)
from tests.hilfen.ntfy_attrappe import NtfyAttrappe
from tests.hilfen.pfade import FIXTURES
from tests.hilfen.tls import erzeuge_zertifikat

ERW = FIXTURES / "m6" / "benachrichtigungen.erwartung.json"
OEFFENTLICH = "https://kontor.heim.example.invalid:8443"


def F():  # noqa: N802
    return kontor.fehler()


def _push(**f):
    b = kontor.modul("kontor.plugins.benachrichtigung")
    werte = {"benachrichtigung_id": 1, "titel": "Titel", "text": "Text", "link": None, "prioritaet": 3,
             "tags": ("sync_fehler",), "schluessel": "sync_fehler:x"}
    werte.update(f)
    return b.PushNachricht(**werte)


def _ntfy(tmp_path, attrappe, token=None, **extra):
    c = config(tmp_path, **ntfy_felder(attrappe, **extra))
    return kontor.modul("kontor.plugins.ntfy").NtfyPlugin(c, token_quelle=(lambda: token))


# ---------------------------------------------------------------- Plugin
@pytest.mark.kern
def test_ntfy_koerper_wie_erwartung(tmp_path, netz_nur_loopback):
    erw = lade(ERW)
    with NtfyAttrappe() as n:
        p = _ntfy(tmp_path, n)
        for i, b in enumerate(erw["beispiele"], start=1):
            k = b["ntfy_koerper"]
            p.senden(_push(benachrichtigung_id=i, titel=k["title"], text=k["message"], link=k.get("click"),
                           prioritaet=k["priority"], tags=tuple(k["tags"]), schluessel=f"{b['art']}:{i}"))
    assert len(n.versuche) == len(erw["beispiele"])
    for v, b in zip(n.versuche, erw["beispiele"]):
        a = v.anfrage
        assert (a.methode, a.pfad) == ("POST", "/")
        assert a.koepfe["content-type"].split(";")[0] == "application/json"
        assert "authorization" not in a.koepfe, "ohne Token kein Authorization-Kopf"
        assert v.koerper == {**b["ntfy_koerper"], "topic": THEMA}


@pytest.mark.kern
def test_ntfy_token_und_fehler(tmp_path, netz_nur_loopback):
    with NtfyAttrappe(erwartetes_token=NTFY_TOKEN) as n:
        _ntfy(tmp_path / "a", n, token=NTFY_TOKEN).senden(_push())
        assert n.versuche[-1].anfrage.koepfe["authorization"] == f"Bearer {NTFY_TOKEN}"
        with pytest.raises(F().BenachrichtigungFehler) as e:
            _ntfy(tmp_path / "b", n).senden(_push())
        assert e.value.details.get("status") == 401 and NTFY_TOKEN not in str(e.value)
        n.statusfolge = [500]
        with pytest.raises(F().BenachrichtigungFehler) as e:
            _ntfy(tmp_path / "c", n, token=NTFY_TOKEN).senden(_push())
        assert e.value.details.get("status") == 500
        n.verzoegerung = 2.5
        with pytest.raises(F().BenachrichtigungFehler):
            _ntfy(tmp_path / "d", n, token=NTFY_TOKEN, ntfy_timeout_sekunden=1).senden(_push())
        url = n.url
    zu = kontor.modul("kontor.plugins.ntfy").NtfyPlugin(config(tmp_path / "e", benachrichtigung_plugin="ntfy",
                                                               ntfy_url=url, ntfy_topic=THEMA))
    with pytest.raises(F().BenachrichtigungFehler):
        zu.senden(_push())


@pytest.mark.kern
def test_ntfy_tls(tmp_path, netz_nur_loopback):
    z = erzeuge_zertifikat(tmp_path / "tls")
    with NtfyAttrappe(tls=z) as n:
        _ntfy(tmp_path / "a", n, tls_ca_datei=z.zertifikat).senden(_push())
        with pytest.raises(F().BenachrichtigungFehler):
            _ntfy(tmp_path / "b", n).senden(_push())
    assert len(n.angenommen) == 1


@pytest.mark.kern
def test_vertrag_mock_und_ntfy(tmp_path, netz_nur_loopback):
    """T 21: beide Plugins nehmen dieselben Nachrichten an; Mock ohne Netz."""
    mock = kontor.modul("kontor.plugins.mock_benachrichtigung").MockBenachrichtigungsPlugin()
    nachrichten = [_push(benachrichtigung_id=i, titel=f"Ä{i}", link="https://k.example.invalid/tan/1" if i % 2 else None)
                   for i in range(1, 4)]
    with NtfyAttrappe() as n:
        p = _ntfy(tmp_path, n)
        for x in nachrichten:
            mock.senden(x)
            p.senden(x)
    assert mock.gesendet == nachrichten
    assert [k["title"] for k in n.angenommen] == [x.titel for x in nachrichten]
    assert [("click" in k) for k in n.angenommen] == [x.link is not None for x in nachrichten]


# ---------------------------------------------------------------- App: Zustellung
def _app(tmp_path, n=None, **felder):
    if n is not None:
        felder = {**ntfy_felder(n), **felder}
    return Api(mock_config(tmp_path, **felder))


def _sync(api, **body):
    return api.post("/api/sync", json=body, erwartet=200).daten


@pytest.mark.kern
def test_echtmodus_ohne_plugin(api, netz_gesperrt):
    api.post("/api/sync", json={}, erwartet=200)
    (b,) = benachrichtigungen(api)
    assert (b["zustellung"], b["zustellversuche"], b["zugestellt_am"]) == ("keine", 0, None)
    assert zustellung(api) == {"plugin": "keins", "ausstehend": 0, "zugestellt": 0, "aufgegeben": 0,
                               "letzter_fehler": None}
    assert fehlercode(api.get("/api/mock/zustellungen", erwartet=409)) == "nur_mock_modus"
    netz_gesperrt.versuche.clear()


@pytest.mark.kern
def test_mock_plugin_im_mock_modus(tmp_path, netz_gesperrt):
    api = _app(tmp_path, szenario="bankfehler")
    _sync(api)
    (b,) = benachrichtigungen(api)
    assert (b["zustellung"], b["zustellversuche"]) == ("zugestellt", 1)
    assert zeit(b["zugestellt_am"]) == zeit(api.get("/api/mock/zeit", erwartet=200).daten["jetzt"])
    (p,) = api.get("/api/mock/zustellungen", erwartet=200).daten
    assert p == {"benachrichtigung_id": b["id"], "titel": "[Mock] " + b["titel"], "text": b["text"], "link": None,
                 "prioritaet": 3, "tags": ["sync_fehler"], "schluessel": b["schluessel"]}
    assert zustellung(api)["plugin"] == "mock"


@pytest.mark.kern
def test_jeder_ausloeser_genau_eine_nachricht(tmp_path, netz_nur_loopback):
    """T 17: Synchronisationsfehler, TAN und gelöschtes Bankkonto je genau einmal, keine Flut."""
    with NtfyAttrappe() as n:
        fehler = _app(tmp_path / "a", n, szenario="bankfehler")
        for _ in range(3):
            _sync(fehler)
        assert [k["tags"] for k in n.angenommen] == [["sync_fehler"]]
        tan = _app(tmp_path / "b", n, szenario="tan_erforderlich", oeffentliche_url=OEFFENTLICH + "/")
        lauf = _sync(tan, von="2024-01-01")
        tid = lauf["tan_anforderung_id"]
        k = n.angenommen[-1]
        assert k == {"topic": THEMA, "title": "[Mock] " + benachrichtigungen(tan)[0]["titel"],
                     "message": benachrichtigungen(tan)[0]["text"], "priority": 4, "tags": ["tan_erforderlich"],
                     "click": f"{OEFFENTLICH}/tan/{tid}"}
        normal = _app(tmp_path / "c", n)
        _sync(normal, von="2024-01-01")
        konto = next(x for x in normal.konten() if x["iban"])
        normal.post(f"/api/konten/{konto['id']}/loeschen", json={"buchungen": "loeschen", "konflikte": "behalten"},
                    erwartet=200)
        anzahl = len(n.angenommen)
        _sync(normal)
        _sync(normal)
        assert [k["tags"] for k in n.angenommen[anzahl:]] == [["konto_fehlt"]]
        assert n.angenommen[-1]["priority"] == 3 and "click" not in n.angenommen[-1]
    for api in (fehler, tan):
        assert all(b["zustellung"] == "zugestellt" for b in benachrichtigungen(api))


@pytest.mark.kern
def test_wiederholung_nach_fehlschlag(tmp_path, netz_nur_loopback):
    planer = kontor.modul("kontor.sync")
    with NtfyAttrappe() as n:
        n.statusfolge = [500, 503]
        api = _app(tmp_path, n, szenario="bankfehler", zustellung_wiederholung_minuten=5)
        setze_zeit(api, "2024-06-30T12:00:00Z")
        _sync(api)
        (b,) = benachrichtigungen(api)
        assert (b["zustellung"], b["zustellversuche"], b["zugestellt_am"]) == ("ausstehend", 1, None)
        s = zustellung(api)
        assert s["ausstehend"] == 1 and s["letzter_fehler"]["code"] == "benachrichtigung_fehler"
        setze_zeit(api, "2024-06-30T12:04:59Z")
        planer.planer_takt(api.app)
        assert len(n.versuche) == 1, "vor dem nächsten Versuch keine Zustellung"
        setze_zeit(api, "2024-06-30T12:05:00Z")
        planer.planer_takt(api.app)
        assert len(n.versuche) == 2 and benachrichtigungen(api)[0]["zustellversuche"] == 2
        setze_zeit(api, "2024-06-30T12:10:00Z")
        planer.planer_takt(api.app)
        (b,) = benachrichtigungen(api)
        assert (b["zustellung"], b["zustellversuche"], zeit(b["zugestellt_am"])) == (
            "zugestellt", 3, zeit("2024-06-30T12:10:00Z"))
        planer.planer_takt(api.app)
        assert len(n.versuche) == 3 and len(n.angenommen) == 1, "nie zweimal erfolgreich"


@pytest.mark.kern
def test_aufgegeben_nach_hoechstzahl(tmp_path, netz_nur_loopback):
    planer = kontor.modul("kontor.sync")
    with NtfyAttrappe() as n:
        n.statusfolge = [500] * 10
        api = _app(tmp_path, n, szenario="bankfehler", zustellung_max_versuche=2, zustellung_wiederholung_minuten=1)
        setze_zeit(api, "2024-06-30T12:00:00Z")
        _sync(api)
        setze_zeit(api, "2024-06-30T12:01:00Z")
        planer.planer_takt(api.app)
        assert benachrichtigungen(api)[0]["zustellung"] == "aufgegeben"
        setze_zeit(api, "2024-06-30T13:00:00Z")
        planer.planer_takt(api.app)
        assert api.post("/api/benachrichtigungen/zustellen", erwartet=200).daten == {"versucht": 0, "zugestellt": 0}
        assert len(n.versuche) == 2
        assert zustellung(api)["aufgegeben"] == 1


@pytest.mark.kern
def test_sofort_zustellen_und_token_aus_geheimnis(tmp_path, netz_nur_loopback, caplog):
    caplog.set_level(logging.DEBUG)
    with NtfyAttrappe(erwartetes_token=NTFY_TOKEN) as n:
        api = _app(tmp_path, n, szenario="bankfehler")
        _sync(api)
        assert n.versuche[0].status == 401 and benachrichtigungen(api)[0]["zustellung"] == "ausstehend"
        geheimnis_setzen(api, "ntfy_token", NTFY_TOKEN)
        assert api.post("/api/benachrichtigungen/zustellen", erwartet=200).daten == {"versucht": 1, "zugestellt": 1}
        assert benachrichtigungen(api)[0]["zustellung"] == "zugestellt"
        assert api.post("/api/benachrichtigungen/zustellen", erwartet=200).daten == {"versucht": 0, "zugestellt": 0}
    assert NTFY_TOKEN not in caplog.text
    assert all(NTFY_TOKEN not in json.dumps(v.koerper) for v in n.versuche)
    assert NTFY_TOKEN not in api.get("/api/benachrichtigungen/zustellung", erwartet=200).text


@pytest.mark.kern
def test_gelesen_unabhaengig_und_keine_geheimnisse(tmp_path, netz_nur_loopback):
    _, erw = lade_sync()
    with NtfyAttrappe() as n:
        api = Api(mock_config(tmp_path, daten=SYNC_DATEN.with_name("sync_daten_pin.json"), szenario="tan_erforderlich",
                              **ntfy_felder(n)))
        api.put("/api/sync/pin", json={"pin": erw["pin"]}, erwartet=204)
        lauf = _sync(api, von="2024-01-01")
        api.post(f"/api/tan-anforderungen/{lauf['tan_anforderung_id']}/antwort", json={"tan": erw["tan"]},
                 erwartet=200)
        b = benachrichtigungen(api)[0]
        api.post(f"/api/benachrichtigungen/{b['id']}/gelesen", erwartet=200)
        assert benachrichtigungen(api)[0]["zustellung"] == "zugestellt"
    for v in n.versuche:
        t = v.anfrage.koerper.decode("utf-8")
        assert erw["pin"] not in t and erw["tan"] not in t
