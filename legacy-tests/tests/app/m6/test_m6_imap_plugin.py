"""M6: IMAP-Plugin mit XOAUTH2 gegen die lokale IMAP-Attrappe (mail.md 3, 8, 9; T 16, T 21)."""

from __future__ import annotations

import datetime as dt
import logging
import threading

import pytest

from tests.hilfen import kontor
from tests.hilfen.imap_attrappe import ImapAttrappe
from tests.hilfen.m6 import EINS, MAIL_VERGLEICH, ZWEI, config, mail_erwartung, mail_felder, zeit
from tests.hilfen.tls import erzeuge_zertifikat

UTC = dt.timezone.utc
ANFANG = dt.datetime(2024, 1, 1, tzinfo=UTC)
ERLAUBT = {"CAPABILITY", "ID", "NOOP", "AUTHENTICATE XOAUTH2", "EXAMINE", "LIST", "STATUS", "SEARCH", "UID SEARCH",
           "FETCH", "UID FETCH", "CLOSE", "UNSELECT", "LOGOUT"}


def F():  # noqa: N802
    return kontor.fehler()


@pytest.fixture(scope="module")
def erw():
    return mail_erwartung()


class Zugang:
    """zugang(adresse, erneuern) mit Aufzeichnung; liefert Tokens aus einer veränderbaren Tabelle."""

    def __init__(self, tokens, erneuert=None):
        self.tokens, self.erneuert, self.aufrufe = dict(tokens), dict(erneuert or {}), []

    def __call__(self, adresse, erneuern):
        self.aufrufe.append((adresse, erneuern))
        return (self.erneuert if erneuern else self.tokens)[adresse]


def _plugin(tmp_path, imap, zugang, postfaecher=((EINS, "INBOX"),), **extra):
    i = kontor.modul("kontor.plugins.imap")
    c = config(tmp_path, **mail_felder(imap, **extra))
    return i.ImapMailPlugin(c, postfaecher=[i.ImapPostfach(a, o) for a, o in postfaecher], zugang=zugang)


def _soll(erw, adresse, ordner, seit=ANFANG):
    return [{k: v for k, v in n.items() if k != "uid"} for n in erw["postfaecher"][adresse][ordner]["nachrichten"]
            if zeit(n["empfangen"]) >= seit]


def _dicts(liste):
    return [{"nachricht_id": n.nachricht_id, "postfach": n.postfach,
             "empfangen": n.empfangen.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "absender": n.absender,
             "betreff": n.betreff, "text": n.text} for n in liste]


@pytest.mark.kern
@pytest.mark.parametrize("adresse,ordner", [(EINS, "INBOX"), (EINS, "[Gmail]/Alle Nachrichten"), (ZWEI, "INBOX"),
                                            (ZWEI, "Bestellungen/Bücher")])
def test_nachrichten_gleich_wahrheit(tmp_path, erw, adresse, ordner, netz_nur_loopback):
    tokens = {EINS: "SYNTH-ACCESS-EINS", ZWEI: "SYNTH-ACCESS-ZWEI"}
    with ImapAttrappe(tokens=tokens) as a:
        z = Zugang(tokens)
        p = _plugin(tmp_path, a, z, postfaecher=((adresse, ordner),))
        ist = _dicts(p.nachrichten(adresse, ANFANG))
    assert ist == _soll(erw, adresse, ordner), "mail.md 3.3: Abbildung, doppelte Message-ID, Sortierung"
    assert z.aufrufe == [(adresse, False)]
    assert a.verstoesse == [], f"nicht nur lesend: {a.verstoesse}"
    assert set(a.alle_befehle) <= ERLAUBT and "EXAMINE" in a.alle_befehle
    assert not a.interne_fehler


@pytest.mark.kern
def test_seit_genau(tmp_path, erw, netz_nur_loopback):
    tokens = {EINS: "SYNTH-ACCESS-EINS"}
    alle = _soll(erw, EINS, "INBOX")
    with ImapAttrappe(tokens=tokens) as a:
        p = _plugin(tmp_path, a, Zugang(tokens))
        for n in (alle[3], alle[-1]):
            t = zeit(n["empfangen"])
            assert _dicts(p.nachrichten(EINS, t)) == _soll(erw, EINS, "INBOX", t), "empfangen ≥ seit"
            assert _dicts(p.nachrichten(EINS, t + dt.timedelta(seconds=1))) == _soll(
                erw, EINS, "INBOX", t + dt.timedelta(seconds=1))
        berlin = dt.timezone(dt.timedelta(hours=2))
        t = zeit(alle[2]["empfangen"]).astimezone(berlin)
        assert _dicts(p.nachrichten(EINS, t)) == _soll(erw, EINS, "INBOX", t), "seit in anderer Zeitzone"


@pytest.mark.kern
def test_pruefreihenfolge_ohne_verbindung(tmp_path, netz_nur_loopback):
    with ImapAttrappe(tokens={EINS: "SYNTH-ACCESS"}) as a:
        p = _plugin(tmp_path, a, Zugang({EINS: "SYNTH-ACCESS"}), postfaecher=((ZWEI, "INBOX"), (EINS, "INBOX")))
        assert p.postfaecher() == [ZWEI, EINS]
        with pytest.raises(ValueError):
            p.nachrichten(EINS, dt.datetime(2024, 1, 1))
        with pytest.raises(F().PostfachUnbekannt):
            p.nachrichten("drei@example.invalid", ANFANG)
        ohne = _plugin(tmp_path / "x", a, None)
        with pytest.raises(F().PluginNichtVerfuegbar):
            ohne.nachrichten(EINS, ANFANG)

        def abgelaufen(adresse, erneuern):
            raise F().MailTokenAbgelaufen("abgelaufen")
        with pytest.raises(F().MailTokenAbgelaufen):
            _plugin(tmp_path / "y", a, abgelaufen).nachrichten(EINS, ANFANG)
        assert a.sitzungen == [], "keine Verbindung vor gültigem Zugang"
        assert len(p.nachrichten(EINS.upper(), ANFANG)) > 0, "Postfach nach casefold verglichen"


@pytest.mark.kern
def test_abgelehntes_token_wird_einmal_erneuert(tmp_path, erw, netz_nur_loopback):
    with ImapAttrappe(tokens={EINS: "SYNTH-NEU"}) as a:
        z = Zugang({EINS: "SYNTH-ALT"}, {EINS: "SYNTH-NEU"})
        assert _dicts(_plugin(tmp_path, a, z).nachrichten(EINS, ANFANG)) == _soll(erw, EINS, "INBOX")
        assert z.aufrufe == [(EINS, False), (EINS, True)]
        assert a.anmeldungen == [(EINS, False), (EINS, True)]
        z2 = Zugang({EINS: "SYNTH-ALT"}, {EINS: "SYNTH-AUCH-FALSCH"})
        with pytest.raises(F().MailAnmeldungAbgelehnt) as e:
            _plugin(tmp_path / "b", a, z2).nachrichten(EINS, ANFANG)
        assert z2.aufrufe == [(EINS, False), (EINS, True)]
        assert "SYNTH-ALT" not in str(e.value) and "SYNTH-AUCH-FALSCH" not in repr(e.value.details)
        assert a.verstoesse == []


@pytest.mark.kern
def test_ordner_unbekannt_und_ohne_xoauth2(tmp_path, netz_nur_loopback):
    tokens = {EINS: "SYNTH-ACCESS"}
    with ImapAttrappe(tokens=tokens) as a:
        with pytest.raises(F().MailOrdnerUnbekannt):
            _plugin(tmp_path, a, Zugang(tokens), postfaecher=((EINS, "Gibt/Es/Nicht"),)).nachrichten(EINS, ANFANG)
        a.ohne_xoauth2 = True
        with pytest.raises(F().MailFehler) as e:
            _plugin(tmp_path / "b", a, Zugang(tokens)).nachrichten(EINS, ANFANG)
        assert e.value.code == "mail_fehler"
        assert a.verstoesse == []


@pytest.mark.kern
def test_verbindungsfehler(tmp_path, netz_nur_loopback):
    tokens = {EINS: "SYNTH-ACCESS"}
    with ImapAttrappe(tokens=tokens) as a:
        a.abbruch_nach_gruss = True
        with pytest.raises(F().MailVerbindungsFehler):
            _plugin(tmp_path / "a", a, Zugang(tokens)).nachrichten(EINS, ANFANG)
        a.abbruch_nach_gruss = False
        a.verzoegerung = 2.5
        with pytest.raises(F().MailVerbindungsFehler):
            _plugin(tmp_path / "b", a, Zugang(tokens), imap_timeout_sekunden=1).nachrichten(EINS, ANFANG)
        port = a.port
    zu = config(tmp_path / "c", mail_plugin="imap", imap_host="127.0.0.1", imap_port=port, imap_tls=False)
    i = kontor.modul("kontor.plugins.imap")
    with pytest.raises(F().MailVerbindungsFehler):
        i.ImapMailPlugin(zu, postfaecher=[i.ImapPostfach(EINS)], zugang=Zugang(tokens)).nachrichten(EINS, ANFANG)


@pytest.mark.kern
def test_tls_mit_eigenem_vertrauensanker(tmp_path, erw, netz_nur_loopback):
    tokens = {EINS: "SYNTH-ACCESS"}
    z = erzeuge_zertifikat(tmp_path / "tls")
    with ImapAttrappe(tokens=tokens, tls=z) as a:
        p = _plugin(tmp_path / "a", a, Zugang(tokens), tls_ca_datei=z.zertifikat)
        assert _dicts(p.nachrichten(EINS, ANFANG)) == _soll(erw, EINS, "INBOX")
        with pytest.raises(F().MailVerbindungsFehler):
            _plugin(tmp_path / "b", a, Zugang(tokens)).nachrichten(EINS, ANFANG)


@pytest.mark.kern
def test_postfaecher_parallel(tmp_path, erw, netz_nur_loopback):
    """T 16: zwei Postfächer gleichzeitig (eine Instanz, zwei Threads)."""
    tokens = {EINS: "SYNTH-ACCESS-EINS", ZWEI: "SYNTH-ACCESS-ZWEI"}
    with ImapAttrappe(tokens=tokens) as a:
        a.parallel(2)
        p = _plugin(tmp_path, a, Zugang(tokens), postfaecher=((EINS, "INBOX"), (ZWEI, "Bestellungen/Bücher")))
        ergebnis, fehler = {}, []

        def hole(adresse):
            try:
                ergebnis[adresse] = _dicts(p.nachrichten(adresse, ANFANG))
            except Exception as e:  # noqa: BLE001
                fehler.append(e)
        faeden = [threading.Thread(target=hole, args=(x,)) for x in (EINS, ZWEI)]
        for f in faeden:
            f.start()
        for f in faeden:
            f.join(20)
    assert not fehler and a.verstoesse == []
    assert ergebnis == {EINS: _soll(erw, EINS, "INBOX"), ZWEI: _soll(erw, ZWEI, "Bestellungen/Bücher")}


@pytest.mark.kern
def test_token_nicht_in_protokollen(tmp_path, caplog, capfd, netz_nur_loopback):
    caplog.set_level(logging.DEBUG)
    with ImapAttrappe(tokens={EINS: "SYNTH-GEHEIM-NEU"}) as a:
        p = _plugin(tmp_path, a, Zugang({EINS: "SYNTH-GEHEIM-ALT"}, {EINS: "SYNTH-GEHEIM-NEU"}))
        p.nachrichten(EINS, ANFANG)
    raus, err = capfd.readouterr()
    for t in (caplog.text, raus, err, repr(p)):
        assert "SYNTH-GEHEIM" not in t


@pytest.mark.kern
def test_vertrag_mit_mock(tmp_path, erw, netz_nur_loopback):
    """T 21: IMAP gegen die Attrappe und Mock mit denselben Nachrichten liefern dasselbe (mail.md 9)."""
    tokens = {EINS: "SYNTH-ACCESS-EINS", ZWEI: "SYNTH-ACCESS-ZWEI"}
    mock = kontor.modul("kontor.plugins.mock_mail").MockMailPlugin(MAIL_VERGLEICH, "normal", dt.date(2024, 12, 31))
    ordner = erw["vergleich_ordner"]
    with ImapAttrappe(tokens=tokens) as a:
        p = _plugin(tmp_path, a, Zugang(tokens), postfaecher=tuple(ordner.items()))
        assert p.postfaecher() == mock.postfaecher()
        for adresse in ordner:
            for seit in (ANFANG, dt.datetime(2024, 4, 1, tzinfo=UTC), dt.datetime(2024, 12, 1, tzinfo=UTC)):
                assert p.nachrichten(adresse, seit) == mock.nachrichten(adresse, seit), (adresse, seit)
        for plugin in (p, mock):
            with pytest.raises(ValueError):
                plugin.nachrichten(EINS, dt.datetime(2024, 1, 1))
            with pytest.raises(F().PostfachUnbekannt):
                plugin.nachrichten("drei@example.invalid", ANFANG)
            plugin.schliessen()
