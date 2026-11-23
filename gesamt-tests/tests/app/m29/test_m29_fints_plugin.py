"""M29: FinTS-Plugin gegen die lokale FinTS-Attrappe – TAN-Verfahren, Kontenliste, camt-Version, Datumsformen,
TAN bei der Anmeldung (fints.md 3.0–3.5a in der Fassung M29; bankzugang.md 1; E-263, E-265).

Erwartete Umsätze kommen aus dem M6-Orakel (Generatorwahrheit), erwartete Konten aus ``m29.soll_konten``.
"""

from __future__ import annotations

import base64
import datetime as dt
import inspect

import pytest

from tests.hilfen import kontor
from tests.hilfen import m6_orakel as orakel
from tests.hilfen.fints_attrappe import LESEND, FintsAttrappe, camt_format
from tests.hilfen.m6 import BIS, PRODUKT, VON, config, fints_daten, fints_felder, giro
from tests.hilfen.m29 import (
    GESCHAEFTSVORFAELLE, NUR_IBAN_BIC, ZUSATZ_VERFAHREN, Pin, fints_plugin, konten_dicts, paare, soll_konten,
    tan_antwort, umsatz_dicts,
)

pytestmark = pytest.mark.kern
UTC = dt.timezone.utc


def F():  # noqa: N802
    return kontor.fehler()


@pytest.fixture(scope="module")
def bank():
    return fints_daten()


def _plugin(tmp_path, attrappe, daten, pin=None, **extra):
    c = config(tmp_path, **fints_felder(attrappe, daten, **extra))
    p = Pin(daten["pin"] if pin is None else pin)
    return fints_plugin(c, p), p


def _soll(erw, iban, von=VON, bis=BIS):
    return orakel.erwartete_umsaetze(erw, "camt", iban, von, bis)


# ------------------------------------------------------------------ 3 / 3.0 öffentliche Methoden, TAN-Verfahren
def test_oeffentliche_methoden(tmp_path):
    def oeffentlich(cls):
        return {n for n, _ in inspect.getmembers(cls, callable) if not n.startswith("_")}
    assert oeffentlich(kontor.modul("kontor.plugins.fints").FintsBankPlugin) == {"konten", "umsaetze", "schliessen",
                                                                                 "tan_verfahren"}
    mock = oeffentlich(kontor.modul("kontor.plugins.mock_bank").MockBankPlugin)
    assert mock == {"konten", "umsaetze", "schliessen", "setze_heute"}, "Mock-Plugin unverändert"
    assert "tan" in inspect.signature(kontor.modul("kontor.plugins.fints").FintsBankPlugin.konten).parameters


def test_tan_verfahren_erlaubte(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    haupt = (daten["tan_verfahren"]["funktion"], daten["tan_verfahren"]["name"])
    zusatz = (ZUSATZ_VERFAHREN["funktion"], ZUSATZ_VERFAHREN["name"])
    with FintsAttrappe(daten) as a:
        a.verfahren_zusatz = [ZUSATZ_VERFAHREN]
        a.erlaubte_verfahren = [haupt[0]]
        plugin, pin = _plugin(tmp_path / "a", a, daten)
        assert pin.aufrufe == 0
        assert paare(plugin.tan_verfahren()) == {haupt}, "nur die für den Zugang erlaubten (3920)"
        a.erlaubte_verfahren = [haupt[0], zusatz[0]]
        beide, _ = _plugin(tmp_path / "b", a, daten)
        assert paare(beide.tan_verfahren()) == {haupt, zusatz}
        a.erlaubte_verfahren = [zusatz[0], "999"]
        nur_zusatz, _ = _plugin(tmp_path / "c", a, daten)
        assert paare(nur_zusatz.tan_verfahren()) == {zusatz}, "Ein-Schritt-Verfahren 999 gehört nie dazu"
    assert pin.aufrufe >= 1, "braucht die PIN"
    assert not (a.segmentarten & GESCHAEFTSVORFAELLE), "tan_verfahren sendet keinen Geschäftsvorfall"
    assert a.tans_empfangen == 0 and a.offene_auftraege == 0 and a.segmentarten <= LESEND
    assert not a.interne_fehler


def test_tan_verfahren_ohne_angabe_der_bank(tmp_path, bank, netz_nur_loopback):
    """Nennt die Bank keine erlaubten Verfahren, kommen alle Zwei-Schritt-Verfahren aus den Bankparametern."""
    daten, _ = bank
    with FintsAttrappe(daten) as a:
        a.verfahren_zusatz = [ZUSATZ_VERFAHREN]
        a.erlaubte_verfahren = None
        plugin, _ = _plugin(tmp_path, a, daten)
        assert paare(plugin.tan_verfahren()) == {
            (daten["tan_verfahren"]["funktion"], daten["tan_verfahren"]["name"]),
            (ZUSATZ_VERFAHREN["funktion"], ZUSATZ_VERFAHREN["name"])}
    assert not a.interne_fehler


def test_tan_verfahren_ohne_tan_trotz_tan_bei_der_anmeldung(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten) as a:
        a.tan_anmeldung = "immer"
        plugin, _ = _plugin(tmp_path, a, daten)
        assert paare(plugin.tan_verfahren()) == {(daten["tan_verfahren"]["funktion"],
                                                  daten["tan_verfahren"]["name"])}
    assert a.anmeldungs_tans == 0 and a.tans_empfangen == 0, "tan_verfahren verlangt keine TAN"
    assert not (a.segmentarten & GESCHAEFTSVORFAELLE) and not a.interne_fehler


def test_tan_verfahren_pin(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten) as a:
        ohne, pin = _plugin(tmp_path / "a", a, daten, pin="")
        pin.wert = None
        with pytest.raises(F().BankPinFehlt):
            ohne.tan_verfahren()
        assert a.anfragen == [], "ohne PIN keine Verbindung"
        falsch, _ = _plugin(tmp_path / "b", a, daten, pin="SYNTH-FALSCH-29")
        with pytest.raises(F().BankPinFalsch) as e:
            falsch.tan_verfahren()
        assert "SYNTH-FALSCH-29" not in str(e.value) and "SYNTH-FALSCH-29" not in repr(e.value.details)


# ------------------------------------------------------------------ 3.1 unvollständiger Zugang
@pytest.mark.parametrize("fehlt", ["fints_url", "fints_blz", "fints_benutzer", "fints_produkt_id"])
def test_unvollstaendig_ohne_verbindung(tmp_path, fehlt, netz_gesperrt):
    felder = {"bank_plugin": "fints", "fints_url": "https://banking.example.invalid/fints", "fints_blz": "00000000",
              "fints_benutzer": "SYNTH-NUTZER", "fints_produkt_id": PRODUKT}
    del felder[fehlt]
    pin = Pin("SYNTH-PIN")
    plugin = fints_plugin(config(tmp_path, **felder), pin)
    aufrufe = [plugin.konten, plugin.tan_verfahren,
               lambda: plugin.umsaetze("DE95000000000000006601", VON, BIS)]
    for aufruf in aufrufe:
        with pytest.raises(F().PluginNichtVerfuegbar) as e:
            aufruf()
        assert e.value.code == "plugin_nicht_verfuegbar"
        assert "Einstellungen" in str(e.value), "die Meldung verweist auf die Einstellungen der Oberfläche"
        assert "SYNTH-PIN" not in str(e.value)
    assert pin.aufrufe == 0, "ohne vollständigen Zugang wird die PIN nicht abgefragt"
    netz_gesperrt.pruefe()


# ------------------------------------------------------------------ 3.2 Kontenliste
@pytest.mark.parametrize("upd", ["normal", "ohne_kontoart", "ohne_iban", "ohne_konten"])
@pytest.mark.parametrize("hispa", ["normal", "mit_nicht_sepa", "ohne_bic"])
def test_kontenliste(tmp_path, bank, upd, hispa, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        if upd != "normal":
            setattr(a, "upd_" + upd, True)
        a.hispa_mit_nicht_sepa = hispa == "mit_nicht_sepa"
        a.hispa_ohne_bic = hispa == "ohne_bic"
        plugin, _ = _plugin(tmp_path, a, daten)
        ist = konten_dicts(plugin.konten())
    soll = soll_konten(daten, upd=upd, ohne_bic=hispa == "ohne_bic")
    assert ist == soll, "fints.md 3.2: je SEPA-Kontoverbindung mit IBAN ein Konto, ergänzt um die Benutzerparameter"
    assert ist == sorted(ist, key=lambda k: k["iban"])
    if upd == "normal" and hispa == "normal":
        assert ist == erw["konten"], "mit den Generatordaten dieselbe Liste wie in M6 (E-261)"
    if upd == "ohne_kontoart":
        assert {k["art"] for k in ist} == {"girokonto"} and "DE14000000000000006604" in {k["iban"] for k in ist}, \
            "ohne Kontoart ist die Art girokonto (auch das Depot wird dann geliefert)"
        assert "DE57000000000000006606" not in {k["iban"] for k in ist}, "ausdrücklich andere Währung"
    if upd == "ohne_konten":
        assert all(k["name"] == "" and k["inhaber"] == "" and k["art"] == "girokonto" for k in ist)
        assert len(ist) == 5
    assert "DE84000000000000006605" not in {k["iban"] for k in ist}, "kein SEPA-Konto"
    assert a.segmentarten <= LESEND and not a.interne_fehler


def test_umsaetze_mit_konto_nur_aus_der_sepa_liste(tmp_path, bank, netz_nur_loopback):
    """Ein Konto ohne Eintrag in den Benutzerparametern lässt sich abrufen."""
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.upd_ohne_konten = True
        plugin, _ = _plugin(tmp_path, a, daten)
        assert umsatz_dicts(plugin.umsaetze(iban, VON, BIS)) == _soll(erw, iban)
    assert not a.interne_fehler


# ------------------------------------------------------------------ 3.3 camt-Version
@pytest.mark.parametrize("angebot,gewaehlt", [([8], 8), ([2], 2), ([2, 4, 6], 6), ([2, 3, 4, 5, 6, 7, 8], 8),
                                              ([7, 8], 8), ([8, 7, 5], 8), ([3, 9], 3), ([5, 7], 7), ([4, 2], 4)])
@pytest.mark.parametrize("profil", ["camt", "beide"])
def test_camt_version(tmp_path, bank, profil, angebot, gewaehlt, netz_nur_loopback):
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, profil=profil, tan_pflicht="nie", seitengroesse=30) as a:
        a.camt_formate = [camt_format(n) for n in angebot]
        plugin, _ = _plugin(tmp_path, a, daten)
        ist = umsatz_dicts(plugin.umsaetze(iban, VON, BIS))
    assert a.camt_angefordert and all(x == [camt_format(gewaehlt)] for x in a.camt_angefordert), \
        f"verlangt wird genau ein Format: .08, sonst die höchste von .07 bis .02 – verlangt: {a.camt_angefordert}"
    assert ist == _soll(erw, iban), "alle Abbildungsregeln gelten für jede Version unverändert"
    assert "HKKAZ" not in a.segmentarten, "bietet die Bank camt an, wird immer camt abgerufen"
    assert all(kv == NUR_IBAN_BIC for kv in a.camt_kontoverbindungen), \
        f"Kontoverbindung im camt-Auftrag nur mit IBAN und BIC: {a.camt_kontoverbindungen}"
    assert a.segmentarten <= LESEND and not a.interne_fehler


@pytest.mark.parametrize("angebot", [[camt_format(1)], [camt_format(9), camt_format(10)],
                                     ["urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"]])
def test_camt_ohne_lesbare_version_kein_mt940(tmp_path, bank, angebot, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, profil="beide", tan_pflicht="nie") as a:
        a.camt_formate = list(angebot)
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().BankFehler) as e:
            plugin.umsaetze(giro(erw), VON, BIS)
    assert e.value.code == "bank_fehler"
    assert "HKKAZ" not in a.segmentarten, "auf MT940 wird nicht ausgewichen"
    assert not a.interne_fehler


def test_mt940_nur_ohne_camt_angebot(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, profil="mt940", tan_pflicht="nie") as a:
        plugin, _ = _plugin(tmp_path, a, daten)
        ist = umsatz_dicts(plugin.umsaetze(iban, VON, BIS))
    assert ist == orakel.erwartete_umsaetze(erw, "mt940", iban, VON, BIS)
    assert "HKKAZ" in a.segmentarten and "HKCAZ" not in a.segmentarten and not a.interne_fehler


# ------------------------------------------------------------------ 3.4 Datumsformen, unlesbare Werte
@pytest.mark.parametrize("form", ["zone", "z", "zeitpunkt", "zeitpunkt_dt"])
def test_datum_mit_zeitzone_und_als_zeitpunkt(tmp_path, bank, form, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie", seitengroesse=30) as a:
        a.datum_form = form
        plugin, _ = _plugin(tmp_path, a, daten)
        for k in erw["konten"]:
            ist = umsatz_dicts(plugin.umsaetze(k["iban"], VON, BIS))
            assert ist == _soll(erw, k["iban"]), f"{form}: ausgewertet werden Jahr, Monat und Tag ({k['iban']})"
    assert not a.interne_fehler


@pytest.mark.parametrize("feld,wert", [("datum_kaputt", "03.06.2024"), ("datum_kaputt", "2024-13-45"),
                                       ("datum_kaputt", "gestern"), ("betrag_kaputt", "12,5a"),
                                       ("betrag_kaputt", "zwölf")])
def test_unlesbarer_wert_laesst_den_ganzen_abruf_scheitern(tmp_path, bank, feld, wert, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        setattr(a, feld, wert)
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().BankFehler) as e:
            plugin.umsaetze(giro(erw), VON, BIS)
        assert e.value.code == "bank_fehler", "einzelne Einträge werden nicht stillschweigend ausgelassen"
        setattr(a, feld, None)
        assert umsatz_dicts(plugin.umsaetze(giro(erw), VON, BIS)) == _soll(erw, giro(erw))
    assert not a.interne_fehler


# ------------------------------------------------------------------ 3.5a TAN bei der Anmeldung
def _pruefe_anforderung(t, daten, vorher):
    assert t.code == "tan_erforderlich" and t.anforderung_id
    assert t.challenge == daten["challenge"]
    assert t.bild == base64.b64decode(daten["qr_png"]) and t.bild_mime_typ == "image/png"
    assert t.gueltig_bis.tzinfo is not None
    abstand = (t.gueltig_bis - vorher).total_seconds()
    assert 9 * 60 - 5 <= abstand <= 10 * 60 + 5
    for geheim in (daten["pin"], daten["tan"]):
        assert geheim not in repr(t) and geheim not in str(t) and geheim not in repr(t.details)


def test_konten_mit_tan_bei_der_anmeldung(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        plugin, _ = _plugin(tmp_path, a, daten)
        vorher = dt.datetime.now(UTC)
        with pytest.raises(F().TanErforderlich) as e:
            plugin.konten()
        _pruefe_anforderung(e.value, daten, vorher)
        ist = konten_dicts(plugin.konten(tan=tan_antwort(e.value.anforderung_id, daten["tan"])))
        assert ist == soll_konten(daten)
        assert a.anmeldungs_tans == 1, "derselbe Aufruf mit der TAN setzt denselben Dialog fort"
        assert a.tans_empfangen == 1 and a.offene_auftraege == 0
    assert a.segmentarten <= LESEND and not a.interne_fehler


def test_umsaetze_mit_tan_bei_der_anmeldung(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        plugin, _ = _plugin(tmp_path, a, daten)
        vorher = dt.datetime.now(UTC)
        with pytest.raises(F().TanErforderlich) as e:
            plugin.umsaetze(iban, VON, BIS)
        _pruefe_anforderung(e.value, daten, vorher)
        ist = umsatz_dicts(plugin.umsaetze(iban, VON, BIS, tan=tan_antwort(e.value.anforderung_id, daten["tan"])))
        assert ist == _soll(erw, iban)
        assert a.anmeldungs_tans == 1 and a.tans_empfangen == 1
    assert a.segmentarten <= LESEND and not a.interne_fehler


def test_umsaetze_zweite_tan_fuer_den_abruf(tmp_path, bank, netz_nur_loopback):
    """Nach der TAN zur Anmeldung kann eine zweite TAN-Anforderung für den Abruf selbst folgen."""
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, tan_pflicht="immer") as a:
        a.tan_anmeldung = "immer"
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().TanErforderlich) as e1:
            plugin.umsaetze(iban, VON, BIS)
        with pytest.raises(F().TanErforderlich) as e2:
            plugin.umsaetze(iban, VON, BIS, tan=tan_antwort(e1.value.anforderung_id, daten["tan"]))
        assert e2.value.anforderung_id and e2.value.anforderung_id != e1.value.anforderung_id
        assert e2.value.challenge == daten["challenge"]
        ist = umsatz_dicts(plugin.umsaetze(iban, VON, BIS, tan=tan_antwort(e2.value.anforderung_id, daten["tan"])))
        assert ist == _soll(erw, iban)
        assert a.anmeldungs_tans == 1 and a.tans_empfangen == 2
    assert not a.interne_fehler


@pytest.mark.parametrize("aufruf", ["konten", "umsaetze"])
def test_anmeldung_falsche_tan_bleibt_offen(tmp_path, bank, aufruf, netz_nur_loopback):
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        plugin, _ = _plugin(tmp_path, a, daten)

        def rufe(**kw):
            return plugin.konten(**kw) if aufruf == "konten" else plugin.umsaetze(iban, VON, BIS, **kw)
        with pytest.raises(F().TanErforderlich) as e:
            rufe()
        aid = e.value.anforderung_id
        with pytest.raises(F().TanUngueltig) as f:
            rufe(tan=tan_antwort(aid, "000000"))
        assert "000000" not in str(f.value) and "000000" not in repr(f.value.details)
        with pytest.raises(F().TanUngueltig):
            rufe(tan=tan_antwort(aid + "-falsch", daten["tan"]))
        ergebnis = rufe(tan=tan_antwort(aid, daten["tan"]))
        if aufruf == "konten":
            assert konten_dicts(ergebnis) == soll_konten(daten)
        else:
            assert umsatz_dicts(ergebnis) == _soll(erw, iban)
        assert a.anmeldungs_tans == 1, "die Anforderung blieb nach der falschen TAN offen"
    assert not a.interne_fehler


def test_anmeldung_tan_abgelaufen(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().TanErforderlich) as e:
            plugin.konten()
        a.lasse_tan_ablaufen()
        with pytest.raises(F().TanAbgelaufen):
            plugin.konten(tan=tan_antwort(e.value.anforderung_id, daten["tan"]))
        with pytest.raises(F().TanErforderlich) as e2:
            plugin.konten()
        assert e2.value.anforderung_id != e.value.anforderung_id
        assert konten_dicts(plugin.konten(tan=tan_antwort(e2.value.anforderung_id, daten["tan"]))) == soll_konten(daten)
    assert not a.interne_fehler


def test_anmeldung_einmal_danach_ohne_tan(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "einmal"
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().TanErforderlich) as e:
            plugin.konten()
        assert konten_dicts(plugin.konten(tan=tan_antwort(e.value.anforderung_id, daten["tan"]))) == soll_konten(daten)
        assert konten_dicts(plugin.konten()) == soll_konten(daten)
        for k in erw["konten"]:
            assert umsatz_dicts(plugin.umsaetze(k["iban"], VON, BIS)) == _soll(erw, k["iban"])
        assert a.anmeldungs_tans == 1 and a.tans_empfangen == 1
    assert not a.interne_fehler


@pytest.mark.parametrize("aufruf", ["konten", "umsaetze"])
def test_entkoppelte_freigabe_ist_bankfehler(tmp_path, bank, aufruf, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung, a.anmeldung_entkoppelt = "immer", True
        plugin, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(F().BankFehler) as e:
            plugin.konten() if aufruf == "konten" else plugin.umsaetze(giro(erw), VON, BIS)
    assert e.value.code == "bank_fehler", "entkoppelte Freigabe wird nicht unterstützt"
    assert a.tans_empfangen == 0 and not a.interne_fehler


def test_offene_anforderung_verfaellt_mit_der_instanz(tmp_path, bank, netz_nur_loopback):
    """Nach einem Neustart (neue Plugin-Instanz) ist eine offene Anforderung verfallen."""
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        erste, _ = _plugin(tmp_path / "a", a, daten)
        with pytest.raises(F().TanErforderlich) as e:
            erste.konten()
        zweite, _ = _plugin(tmp_path / "b", a, daten)
        with pytest.raises(F().TanUngueltig):
            zweite.konten(tan=tan_antwort(e.value.anforderung_id, daten["tan"]))
    assert not a.interne_fehler
