"""M6: echtes FinTS-Plugin gegen die lokale FinTS-Attrappe (fints.md 3, 6, 7; T 7, T 21)."""

from __future__ import annotations

import base64
import datetime as dt
import logging

import pytest

from tests.hilfen import kontor
from tests.hilfen import m6_orakel as orakel
from tests.hilfen.fints_attrappe import LESEND, FintsAttrappe
from tests.hilfen.m6 import (
    BIS, FINTS_VERGLEICH, PRODUKT, VON, alles_protokollieren, config, fints_daten, fints_felder, giro,
)
from tests.hilfen.tls import erzeuge_zertifikat

UTC = dt.timezone.utc
SPAETER = dt.date(2024, 7, 5)    # alle Vormerkungen abgelaufen, alle Umsätze gebucht


def F():  # noqa: N802
    return kontor.fehler()


@pytest.fixture(scope="module")
def bank():
    return fints_daten()


class Pin:
    """pin_quelle, die Aufrufe zählt."""

    def __init__(self, wert):
        self.wert, self.aufrufe = wert, 0

    def __call__(self):
        self.aufrufe += 1
        return self.wert


def _plugin(tmp_path, attrappe, daten, pin=None, **extra):
    c = config(tmp_path, **fints_felder(attrappe, daten, **extra))
    p = Pin(daten["pin"] if pin is None else pin)
    return kontor.modul("kontor.plugins.fints").FintsBankPlugin(c, pin_quelle=p), p


def _tan_antwort(anforderung_id, tan):
    return kontor.modul("kontor.plugins.bank").TanAntwort(anforderung_id, tan)


def _mit_tan(plugin, daten, iban, von, bis):
    with pytest.raises(F().TanErforderlich) as e:
        plugin.umsaetze(iban, von, bis)
    return plugin.umsaetze(iban, von, bis, tan=_tan_antwort(e.value.anforderung_id, daten["tan"]))


def _dicts(liste):
    return [{"iban": u.iban, "buchungstag": u.buchungstag.isoformat(),
             "valuta": u.valuta.isoformat() if u.valuta else None, "betrag": u.betrag, "waehrung": u.waehrung,
             "gegenpartei_name": u.gegenpartei_name, "gegenpartei_iban": u.gegenpartei_iban,
             "verwendungszweck": u.verwendungszweck, "vormerkung": u.vormerkung, "storno": u.storno,
             "umsatz_id": u.umsatz_id} for u in liste]


@pytest.fixture(params=["camt", "mt940"])
def profil(request):
    return request.param


@pytest.mark.kern
def test_konten(tmp_path, bank, profil, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, profil=profil) as a:
        plugin, pin = _plugin(tmp_path, a, daten)
        assert pin.aufrufe == 0, "pin_quelle erst bei Bedarf"
        konten = plugin.konten()
    ist = [{"iban": k.iban, "bic": k.bic, "name": k.name, "art": k.art, "inhaber": k.inhaber, "waehrung": k.waehrung}
           for k in konten]
    assert ist == erw["konten"], "fints.md 3.2 (Fassung M29, E-261): Kontoarten, SEPA und Währung, nach IBAN sortiert"
    assert pin.aufrufe >= 1 and not a.interne_fehler


@pytest.mark.kern
def test_umsaetze_mit_tan_gleich_wahrheit(tmp_path, bank, profil, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, profil=profil, seitengroesse=25) as a:
        plugin, _ = _plugin(tmp_path, a, daten)
        for k in sorted(erw["konten"], key=lambda k: k["art"] != "girokonto"):   # erst Giro mit TAN, dann frei
            ist = _dicts(_mit_tan(plugin, daten, k["iban"], VON, BIS) if k["art"] == "girokonto"
                         else plugin.umsaetze(k["iban"], VON, BIS))
            assert ist == orakel.erwartete_umsaetze(erw, profil, k["iban"], VON, BIS), k["iban"]
    assert a.segmentarten <= LESEND, f"nicht lesende Segmente: {a.segmentarten - LESEND}"
    assert {x.produkt_id for x in a.anfragen if x.produkt_id} == {PRODUKT}
    assert not a.interne_fehler


@pytest.mark.kern
@pytest.mark.parametrize("von,bis", [("2023-12-29", "2023-12-29"), ("2024-02-05", "2024-02-07"),
                                     ("2024-04-09", "2024-04-09"), ("2024-04-01", "2024-04-30"),
                                     ("2024-06-28", "2024-07-31"), ("2024-08-01", "2024-08-31")])
def test_zeitraeume_und_stabile_kennungen(tmp_path, bank, profil, von, bis, netz_nur_loopback):
    daten, erw = bank
    von, bis = dt.date.fromisoformat(von), dt.date.fromisoformat(bis)
    iban = giro(erw)
    with FintsAttrappe(daten, profil=profil, tan_pflicht="nie", seitengroesse=7) as a:
        plugin, _ = _plugin(tmp_path, a, daten)
        ist = _dicts(plugin.umsaetze(iban, von, bis))
        gesamt = {u["umsatz_id"]: u for u in _dicts(plugin.umsaetze(iban, VON, BIS))}
    assert ist == orakel.erwartete_umsaetze(erw, profil, iban, von, bis)
    for u in ist:
        assert gesamt.get(u["umsatz_id"]) == u, "umsatz_id muss über verschiedene Zeiträume stabil sein"


@pytest.mark.kern
def test_vormerkungen_zeitlich(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    iban = giro(erw)
    for heute in ("2024-06-28", "2024-06-30", "2024-07-01", "2024-07-05"):
        h = dt.date.fromisoformat(heute)
        with FintsAttrappe(daten, tan_pflicht="nie", heute=h) as a:
            plugin, _ = _plugin(tmp_path / heute, a, daten)
            ist = _dicts(plugin.umsaetze(iban, dt.date(2024, 6, 20), dt.date(2024, 7, 31)))
        assert ist == orakel.erwartete_umsaetze(erw, "camt", iban, dt.date(2024, 6, 20), dt.date(2024, 7, 31), h)
    assert any(u["vormerkung"] for u in orakel.erwartete_umsaetze(erw, "camt", iban, VON, BIS, dt.date(2024, 6, 30)))


@pytest.mark.kern
def test_tan_anforderung_mit_qr_bild(tmp_path, bank, profil, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, profil=profil) as a:
        plugin, _ = _plugin(tmp_path, a, daten)
        vorher = dt.datetime.now(UTC)
        with pytest.raises(F().TanErforderlich) as e:
            plugin.umsaetze(giro(erw), VON, BIS)
    t = e.value
    assert t.code == "tan_erforderlich" and t.anforderung_id
    assert t.challenge == daten["challenge"]
    assert t.bild == base64.b64decode(daten["qr_png"]) and t.bild_mime_typ == "image/png"
    assert t.gueltig_bis.tzinfo is not None
    abstand = (t.gueltig_bis - vorher).total_seconds()
    assert 9 * 60 - 5 <= abstand <= 10 * 60 + 5, "challenge_valid_until (Europe/Berlin) in UTC umgerechnet"
    assert daten["pin"] not in repr(t) and daten["pin"] not in str(t.details)


@pytest.mark.kern
def test_falsche_tan_dann_richtige(tmp_path, bank, profil, netz_nur_loopback):
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, profil=profil) as a:
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().TanErforderlich) as e:
            plugin.umsaetze(iban, VON, BIS)
        aid = e.value.anforderung_id
        with pytest.raises(F().TanUngueltig):
            plugin.umsaetze(iban, VON, BIS, tan=_tan_antwort(aid, "000000"))
        with pytest.raises(F().TanUngueltig):
            plugin.umsaetze(iban, VON, BIS, tan=_tan_antwort(aid + "-falsch", daten["tan"]))
        ist = _dicts(plugin.umsaetze(iban, VON, BIS, tan=_tan_antwort(aid, daten["tan"])))
        assert ist == orakel.erwartete_umsaetze(erw, profil, iban, VON, BIS)
        # Freigabe der Bank: weitere Abrufe ohne TAN
        assert _dicts(plugin.umsaetze(iban, VON, BIS)) == ist


@pytest.mark.kern
def test_tan_abgelaufen(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten) as a:
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().TanErforderlich) as e:
            plugin.umsaetze(iban, VON, BIS)
        a.lasse_tan_ablaufen()
        with pytest.raises(F().TanAbgelaufen):
            plugin.umsaetze(iban, VON, BIS, tan=_tan_antwort(e.value.anforderung_id, daten["tan"]))
        with pytest.raises(F().TanErforderlich) as e2:
            plugin.umsaetze(iban, VON, BIS)
        assert e2.value.anforderung_id != e.value.anforderung_id
        assert plugin.umsaetze(iban, VON, BIS, tan=_tan_antwort(e2.value.anforderung_id, daten["tan"]))


@pytest.mark.kern
def test_pin_fehlt_falsch_gesperrt(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten) as a:
        plugin, pin = _plugin(tmp_path / "a", a, daten, pin="")
        pin.wert = None
        with pytest.raises(F().BankPinFehlt):
            plugin.konten()
        assert a.anfragen == [], "ohne PIN keine Verbindung"
        falsch, _ = _plugin(tmp_path / "b", a, daten, pin="SYNTH-FALSCH-1")
        with pytest.raises(F().BankPinFalsch) as e:
            falsch.konten()
        assert "SYNTH-FALSCH-1" not in str(e.value) and "SYNTH-FALSCH-1" not in repr(e.value.details)
        a.gesperrt = True
        richtig, _ = _plugin(tmp_path / "c", a, daten)
        with pytest.raises(F().BankZugangGesperrt):
            richtig.konten()


@pytest.mark.kern
def test_verbindungsfehler(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.http_status = 500
        plugin, _ = _plugin(tmp_path / "a", a, daten)
        with pytest.raises(F().BankVerbindungsFehler):
            plugin.konten()
        a.http_status = 200
        a.verzoegerung = 2.5
        langsam, _ = _plugin(tmp_path / "b", a, daten, fints_timeout_sekunden=1)
        with pytest.raises(F().BankZeitueberschreitung):
            langsam.konten()
        a.verzoegerung = 0
        url = a.url
    c = config(tmp_path / "c", bank_plugin="fints", fints_url=url, fints_blz=daten["blz"],
               fints_benutzer=daten["benutzer"], fints_produkt_id=PRODUKT)
    p = kontor.modul("kontor.plugins.fints").FintsBankPlugin(c, pin_quelle=lambda: daten["pin"])
    with pytest.raises(F().BankVerbindungsFehler):
        p.konten()


@pytest.mark.kern
def test_auftrag_abgelehnt_und_unbekanntes_konto(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.fehler_iban.add(iban)
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().BankFehler) as e:
            plugin.umsaetze(iban, VON, BIS)
        assert e.value.code == "bank_fehler" and e.value.details.get("rueckmeldung") == "9380"
        with pytest.raises(F().BankKontoUnbekannt):
            plugin.umsaetze(erw["nicht_geliefert"][0], VON, BIS)
        with pytest.raises(F().BankKontoUnbekannt):
            plugin.umsaetze("DE02000000000000009999", VON, BIS)
        anzahl = len(a.anfragen)
        with pytest.raises(ValueError):
            plugin.umsaetze(iban, BIS, VON)
        assert len(a.anfragen) == anzahl, "von > bis ohne Verbindung"
        b = erw["konten"][1]["iban"]
        klein = " ".join(b[i:i + 4] for i in range(0, len(b), 4)).lower()
        assert _dicts(plugin.umsaetze(klein, VON, BIS)) == orakel.erwartete_umsaetze(erw, "camt", b, VON, BIS)


@pytest.mark.kern
def test_tls_mit_eigenem_vertrauensanker(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    z = erzeuge_zertifikat(tmp_path / "tls")
    with FintsAttrappe(daten, tls=z) as a:
        assert a.url.startswith("https://127.0.0.1:")
        plugin, _ = _plugin(tmp_path / "a", a, daten, tls_ca_datei=z.zertifikat)
        assert len(plugin.konten()) == len(erw["konten"])
        fremd, _ = _plugin(tmp_path / "b", a, daten)
        with pytest.raises(F().BankVerbindungsFehler):
            fremd.konten()


@pytest.mark.kern
def test_keine_geheimnisse_in_protokollen(tmp_path, bank, caplog, capfd, netz_nur_loopback):
    daten, erw = bank
    alles_protokollieren(caplog)
    with FintsAttrappe(daten) as a:
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().TanErforderlich) as e:
            plugin.umsaetze(giro(erw), VON, BIS)
        with pytest.raises(F().TanUngueltig) as e2:
            plugin.umsaetze(giro(erw), VON, BIS, tan=_tan_antwort(e.value.anforderung_id, "918273"))
        plugin.umsaetze(giro(erw), VON, BIS, tan=_tan_antwort(e.value.anforderung_id, daten["tan"]))
    raus, err = capfd.readouterr()
    texte = [caplog.text, raus, err, repr(plugin), str(e2.value), repr(e2.value.details)]
    texte += [r.getMessage() for r in caplog.records]
    for geheim in (daten["pin"], daten["tan"], "918273"):
        for t in texte:
            assert geheim not in t, f"Geheimnis {geheim!r} in Protokoll/Fehler"


@pytest.mark.kern
def test_vertrag_mit_mock(tmp_path, bank, netz_nur_loopback):
    """T 21: FinTS gegen die Attrappe und Mock mit gleichwertigen Daten liefern dasselbe (fints.md 7)."""
    daten, erw = bank
    mock = kontor.modul("kontor.plugins.mock_bank").MockBankPlugin(FINTS_VERGLEICH, "normal", SPAETER,
                                                                    pin_quelle=lambda: daten["pin"])
    with FintsAttrappe(daten, tan_pflicht="nie", heute=SPAETER) as a:
        plugin, _ = _plugin(tmp_path, a, daten)
        assert sorted(plugin.konten(), key=lambda k: k.iban) == sorted(mock.konten(), key=lambda k: k.iban)
        for k in erw["konten"]:
            for von, bis in ((VON, BIS), (dt.date(2024, 3, 1), dt.date(2024, 3, 31)), (dt.date(2024, 4, 9),) * 2):
                assert plugin.umsaetze(k["iban"], von, bis) == mock.umsaetze(k["iban"], von, bis), (k["iban"], von)
        for p in (plugin, mock):
            with pytest.raises(ValueError):
                p.umsaetze(giro(erw), BIS, VON)
            with pytest.raises(F().BankKontoUnbekannt):
                p.umsaetze("DE02000000000000009999", VON, BIS)
            p.schliessen()


def test_kreditkarte_und_tagesgeld_ohne_tan_im_selben_lauf(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten) as a:
        plugin, pin = _plugin(tmp_path, a, daten)
        _mit_tan(plugin, daten, giro(erw), VON, BIS)
        for k in erw["konten"]:
            assert _dicts(plugin.umsaetze(k["iban"], VON, BIS)) == orakel.erwartete_umsaetze(erw, "camt", k["iban"],
                                                                                             VON, BIS)
    assert a.tans_empfangen == 1


def test_protokoll_der_bibliothek_ohne_tan(tmp_path, bank, caplog, netz_nur_loopback):
    """fints.md 3.8: auch der Logger ``fints`` gibt auf DEBUG keine TAN aus."""
    daten, erw = bank
    caplog.set_level(logging.DEBUG, logger="fints")
    with FintsAttrappe(daten) as a:
        plugin, _ = _plugin(tmp_path, a, daten)
        _mit_tan(plugin, daten, giro(erw), VON, BIS)
    assert daten["tan"] not in caplog.text and daten["pin"] not in caplog.text
