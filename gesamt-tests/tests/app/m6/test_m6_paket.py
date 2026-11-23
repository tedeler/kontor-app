"""M6: Module, Fehlerklassen, Konfiguration und Netzregeln (python-api.md 13, geheimnisse.md 7)."""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import neue_api


def Config():  # noqa: N802
    return kontor.KontorConfig()


def F():  # noqa: N802
    return kontor.fehler()


def _c(tmp_path, **f):
    return Config()(datenbank=tmp_path / "k.sqlite3", **f)


@pytest.mark.kern
@pytest.mark.parametrize("modul,namen", [
    ("kontor.plugins.fints", ["FintsBankPlugin"]),
    ("kontor.plugins.imap", ["ImapMailPlugin", "ImapPostfach"]),
    ("kontor.plugins.benachrichtigung", ["BenachrichtigungsPlugin", "PushNachricht"]),
    ("kontor.plugins.mock_benachrichtigung", ["MockBenachrichtigungsPlugin"]),
    ("kontor.plugins.ntfy", ["NtfyPlugin"]),
    ("kontor.plugins", ["erzeuge_bank_plugin", "erzeuge_mail_plugin", "erzeuge_benachrichtigungs_plugin"]),
])
def test_module_und_namen(modul, namen):
    m = kontor.modul(modul)
    for n in namen:
        assert hasattr(m, n), f"{modul}.{n} fehlt"


@pytest.mark.kern
@pytest.mark.parametrize("name,basis,code", [
    ("BankZugangGesperrt", "BankFehler", "bank_zugang_gesperrt"),
    ("MailTokenWiderrufen", "MailFehler", "mail_token_widerrufen"),
    ("MailAnmeldungFehlt", "MailFehler", "mail_anmeldung_fehlt"),
    ("MailAnmeldungAbgelehnt", "MailFehler", "mail_anmeldung_abgelehnt"),
    ("MailOAuthFehler", "MailFehler", "mail_oauth_fehler"),
    ("MailOrdnerUnbekannt", "MailFehler", "mail_ordner_unbekannt"),
    ("BenachrichtigungFehler", "PluginFehler", "benachrichtigung_fehler"),
])
def test_fehlerklassen(name, basis, code):
    f = F()
    cls = getattr(f, name)
    assert issubclass(cls, getattr(f, basis)) and issubclass(cls, f.PluginFehler) and cls.code == code
    e = cls("Meldung", x=1)
    assert str(e) == "Meldung" and e.details == {"x": 1}


@pytest.mark.kern
def test_datenklassen():
    b = kontor.modul("kontor.plugins.benachrichtigung")
    assert dataclasses.is_dataclass(b.PushNachricht) and b.PushNachricht.__dataclass_params__.frozen
    assert [f.name for f in dataclasses.fields(b.PushNachricht)] == [
        "benachrichtigung_id", "titel", "text", "link", "prioritaet", "tags", "schluessel"]
    i = kontor.modul("kontor.plugins.imap")
    assert dataclasses.is_dataclass(i.ImapPostfach) and i.ImapPostfach.__dataclass_params__.frozen
    assert [f.name for f in dataclasses.fields(i.ImapPostfach)] == ["adresse", "ordner"]
    assert i.ImapPostfach("a@example.invalid").ordner == "INBOX"
    assert inspect.isabstract(b.BenachrichtigungsPlugin)


VORGABEN = {
    "bank_pin_quelle": "eingabe", "credentials_verzeichnis": None, "fints_url": None, "fints_blz": None,
    "fints_benutzer": None, "fints_kunden_id": None, "fints_produkt_id": None, "fints_tan_verfahren": None,
    "fints_timeout_sekunden": 30, "imap_host": "imap.gmail.com", "imap_port": 993, "imap_tls": True,
    "imap_timeout_sekunden": 30, "oauth_client_id": None,
    "oauth_autorisierung_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "oauth_token_url": "https://oauth2.googleapis.com/token", "oauth_widerruf_url": "https://oauth2.googleapis.com/revoke",
    "oauth_redirect_uri": "http://127.0.0.1/oauth2/rueckruf", "oauth_timeout_sekunden": 30,
    "oauth_refresh_gueltig_stunden": 168, "oauth_vorwarnung_stunden": 24, "mail_intervall_minuten": 0,
    "mail_erstabruf_tage": 30, "mail_ueberlappung_stunden": 24, "ntfy_url": "https://ntfy.sh", "ntfy_topic": None,
    "ntfy_timeout_sekunden": 10, "zustellung_max_versuche": 10, "zustellung_wiederholung_minuten": 5,
    "tan_erinnerung_minuten": 5, "tan_erinnerung_anzahl": 3, "oeffentliche_url": None,
    "geheimnis_schluessel_datei": None, "tls_ca_datei": None,
}


@pytest.mark.kern
def test_konfiguration_vorgaben(tmp_path):
    c = _c(tmp_path)
    for feld, wert in VORGABEN.items():
        assert getattr(c, feld) == wert, feld
    assert c.benachrichtigung_plugin == "keins"
    m = _c(tmp_path, mock_modus=True)
    assert m.benachrichtigung_plugin == "mock"
    assert list(tmp_path.iterdir()) == [], "die Konstruktion legt nichts an"


@pytest.mark.kern
@pytest.mark.parametrize("felder", [
    {"bank_pin_quelle": "datei"}, {"bank_pin_quelle": "systemd-creds"},
    {"fints_blz": "1234567"}, {"fints_blz": "1234567X"}, {"fints_benutzer": ""}, {"fints_produkt_id": "X" * 26},
    {"fints_tan_verfahren": "91"}, {"fints_timeout_sekunden": 0}, {"fints_timeout_sekunden": True},
    {"fints_timeout_sekunden": 601}, {"imap_port": 0}, {"imap_port": 65536}, {"imap_tls": "ja"},
    {"imap_timeout_sekunden": 30.0}, {"oauth_refresh_gueltig_stunden": -1}, {"oauth_vorwarnung_stunden": 8761},
    {"mail_intervall_minuten": -1}, {"mail_erstabruf_tage": 3651}, {"mail_ueberlappung_stunden": 8761},
    {"benachrichtigung_plugin": "email"}, {"benachrichtigung_plugin": "mock"}, {"benachrichtigung_plugin": "ntfy"},
    {"benachrichtigung_plugin": "ntfy", "ntfy_topic": "mit leerzeichen"},
    {"benachrichtigung_plugin": "ntfy", "ntfy_topic": "x" * 65}, {"ntfy_timeout_sekunden": 0},
    {"zustellung_max_versuche": 0}, {"zustellung_wiederholung_minuten": 0}, {"tan_erinnerung_minuten": -1},
    {"tan_erinnerung_anzahl": 101}, {"imap_host": ""},
], ids=lambda f: ",".join(f"{k}={v!r}" for k, v in f.items())[:60])
def test_konfiguration_ungueltig(tmp_path, felder):
    with pytest.raises(F().KonfigurationsFehler):
        _c(tmp_path, **felder)


@pytest.mark.kern
@pytest.mark.parametrize("feld,wert,gut", [
    ("fints_url", "https://banking.example.invalid/fints", True),
    ("fints_url", "http://banking.example.invalid/fints", False),
    ("fints_url", "http://127.0.0.1:8080/fints", True),
    ("fints_url", "http://[::1]:8080/fints", True),
    ("fints_url", "http://localhost/fints", True),
    ("fints_url", "ftp://127.0.0.1/fints", False),
    ("fints_url", "https:///ohne-host", False),
    ("fints_url", "banking.example.invalid", False),
    ("oauth_token_url", "http://oauth.example.invalid/token", False),
    ("oauth_autorisierung_url", "http://127.0.0.1:9/auth", True),
    ("oauth_widerruf_url", "http://192.168.0.10/revoke", False),
    ("ntfy_url", "http://ntfy.example.invalid", False),
    ("ntfy_url", "https://ntfy.example.invalid", True),
    ("oeffentliche_url", "http://kontor.lan.example.invalid:8000", True),
    ("oeffentliche_url", "javascript:alert(1)", False),
    ("oauth_redirect_uri", "http://kontor.lan.example.invalid/oauth2/rueckruf", True),
])
def test_url_regeln(tmp_path, feld, wert, gut):
    """geheimnisse.md 7: http nur auf Loopback (außer öffentlicher URL und Umleitungsadresse)."""
    if gut:
        assert getattr(_c(tmp_path, **{feld: wert}), feld) == wert
    else:
        with pytest.raises(F().KonfigurationsFehler):
            _c(tmp_path, **{feld: wert})


@pytest.mark.kern
@pytest.mark.parametrize("host,gut", [("127.0.0.1", True), ("localhost", True), ("::1", True),
                                      ("imap.gmail.com", False), ("192.168.1.2", False)])
def test_imap_ohne_tls_nur_loopback(tmp_path, host, gut):
    if gut:
        assert _c(tmp_path, imap_host=host, imap_tls=False).imap_tls is False
    else:
        with pytest.raises(F().KonfigurationsFehler):
            _c(tmp_path, imap_host=host, imap_tls=False)
    assert _c(tmp_path, imap_host=host).imap_tls is True


@pytest.mark.kern
def test_konfiguration_gueltige_kombinationen(tmp_path):
    c = _c(tmp_path, bank_pin_quelle="systemd-creds", credentials_verzeichnis=str(tmp_path / "creds"),
           benachrichtigung_plugin="ntfy", ntfy_topic="kontor-THEMA_1", tls_ca_datei=str(tmp_path / "ca.pem"),
           geheimnis_schluessel_datei=str(tmp_path / "s.key"), fints_blz="00000000", fints_tan_verfahren="913",
           oauth_refresh_gueltig_stunden=0)
    assert c.credentials_verzeichnis == tmp_path / "creds" and c.tls_ca_datei == tmp_path / "ca.pem"
    assert c.geheimnis_schluessel_datei == tmp_path / "s.key" and c.benachrichtigung_plugin == "ntfy"
    m = _c(tmp_path, mock_modus=True, benachrichtigung_plugin="ntfy", ntfy_topic="t")
    assert m.benachrichtigung_plugin == "ntfy", "ntfy ist auch im Mock-Modus erlaubt (E-119)"
    assert _c(tmp_path, mock_modus=True, benachrichtigung_plugin="keins").benachrichtigung_plugin == "keins"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.kern
def test_from_env_alle_m6_felder(tmp_path):
    u = {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_BANK_PIN_QUELLE": "systemd-creds",
         "CREDENTIALS_DIRECTORY": str(tmp_path / "c"), "KONTOR_FINTS_URL": "https://b.example.invalid/f",
         "KONTOR_FINTS_BLZ": "00000000", "KONTOR_FINTS_BENUTZER": "SYNTH-NUTZER", "KONTOR_FINTS_KUNDEN_ID": "SYNTH-K",
         "KONTOR_FINTS_PRODUKT_ID": "SYNTH-PRODUKT", "KONTOR_FINTS_TAN_VERFAHREN": "913",
         "KONTOR_FINTS_TIMEOUT_SEKUNDEN": "12", "KONTOR_IMAP_HOST": "127.0.0.1", "KONTOR_IMAP_PORT": "1143",
         "KONTOR_IMAP_TLS": "nein", "KONTOR_IMAP_TIMEOUT_SEKUNDEN": "7", "KONTOR_OAUTH_CLIENT_ID": "SYNTH-ID",
         "KONTOR_OAUTH_AUTORISIERUNG_URL": "https://o.example.invalid/a", "KONTOR_OAUTH_TOKEN_URL": "https://o.example.invalid/t",
         "KONTOR_OAUTH_WIDERRUF_URL": "https://o.example.invalid/r",
         "KONTOR_OAUTH_REDIRECT_URI": "http://127.0.0.1:9999/oauth2/rueckruf", "KONTOR_OAUTH_TIMEOUT_SEKUNDEN": "8",
         "KONTOR_OAUTH_REFRESH_GUELTIG_STUNDEN": "0", "KONTOR_OAUTH_VORWARNUNG_STUNDEN": "12",
         "KONTOR_MAIL_INTERVALL_MINUTEN": "15", "KONTOR_MAIL_ERSTABRUF_TAGE": "60",
         "KONTOR_MAIL_UEBERLAPPUNG_STUNDEN": "6", "KONTOR_BENACHRICHTIGUNG_PLUGIN": "ntfy",
         "KONTOR_NTFY_URL": "https://n.example.invalid", "KONTOR_NTFY_TOPIC": "THEMA",
         "KONTOR_NTFY_TIMEOUT_SEKUNDEN": "4", "KONTOR_ZUSTELLUNG_MAX_VERSUCHE": "3",
         "KONTOR_ZUSTELLUNG_WIEDERHOLUNG_MINUTEN": "2", "KONTOR_TAN_ERINNERUNG_MINUTEN": "0",
         "KONTOR_TAN_ERINNERUNG_ANZAHL": "9", "KONTOR_OEFFENTLICHE_URL": "http://kontor.lan.example.invalid",
         "KONTOR_GEHEIMNIS_SCHLUESSEL_DATEI": str(tmp_path / "g.key"), "KONTOR_TLS_CA_DATEI": str(tmp_path / "ca")}
    c = Config().from_env(u)
    erwartet = {"bank_pin_quelle": "systemd-creds", "credentials_verzeichnis": tmp_path / "c",
                "fints_url": "https://b.example.invalid/f", "fints_blz": "00000000", "fints_benutzer": "SYNTH-NUTZER",
                "fints_kunden_id": "SYNTH-K", "fints_produkt_id": "SYNTH-PRODUKT", "fints_tan_verfahren": "913",
                "fints_timeout_sekunden": 12, "imap_host": "127.0.0.1", "imap_port": 1143, "imap_tls": False,
                "imap_timeout_sekunden": 7, "oauth_client_id": "SYNTH-ID", "oauth_timeout_sekunden": 8,
                "oauth_refresh_gueltig_stunden": 0, "oauth_vorwarnung_stunden": 12, "mail_intervall_minuten": 15,
                "mail_erstabruf_tage": 60, "mail_ueberlappung_stunden": 6, "benachrichtigung_plugin": "ntfy",
                "ntfy_url": "https://n.example.invalid", "ntfy_topic": "THEMA", "ntfy_timeout_sekunden": 4,
                "zustellung_max_versuche": 3, "zustellung_wiederholung_minuten": 2, "tan_erinnerung_minuten": 0,
                "tan_erinnerung_anzahl": 9, "oeffentliche_url": "http://kontor.lan.example.invalid",
                "geheimnis_schluessel_datei": tmp_path / "g.key", "tls_ca_datei": tmp_path / "ca",
                "oauth_redirect_uri": "http://127.0.0.1:9999/oauth2/rueckruf"}
    for feld, wert in erwartet.items():
        assert getattr(c, feld) == wert, feld
    leer = Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_FINTS_URL": "",
                              "KONTOR_IMAP_TLS": "", "CREDENTIALS_DIRECTORY": ""})
    assert leer.fints_url is None and leer.imap_tls is True and leer.credentials_verzeichnis is None


@pytest.mark.parametrize("name,wert", [("KONTOR_IMAP_PORT", "x"), ("KONTOR_IMAP_TLS", "vielleicht"),
                                       ("KONTOR_TAN_ERINNERUNG_MINUTEN", "-1"), ("KONTOR_FINTS_URL", "http://x.example.invalid"),
                                       ("KONTOR_BENACHRICHTIGUNG_PLUGIN", "mock")])
def test_from_env_ungueltig(tmp_path, name, wert):
    with pytest.raises(F().KonfigurationsFehler):
        Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), name: wert})


def test_pin_quelle_systemd_braucht_verzeichnis(tmp_path):
    with pytest.raises(F().KonfigurationsFehler):
        Config().from_env({"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_BANK_PIN_QUELLE": "systemd-creds"})


# ---------------------------------------------------------------- Plugins erzeugen
@pytest.mark.kern
def test_erzeugen_ohne_verbindung_und_ohne_pin(tmp_path, netz_gesperrt):
    p = kontor.plugins()
    aufrufe = []
    c = _c(tmp_path, fints_url="https://banking.example.invalid/fints", fints_blz="00000000",
           fints_benutzer="SYNTH-NUTZER", fints_produkt_id="SYNTH-PRODUKT")
    b = p.erzeuge_bank_plugin(c, pin_quelle=lambda: aufrufe.append(1) or "SYNTH-PIN")
    assert type(b) is kontor.modul("kontor.plugins.fints").FintsBankPlugin and (b.name, b.ist_mock) == ("fints", False)
    m = p.erzeuge_mail_plugin(c, postfaecher=[kontor.modul("kontor.plugins.imap").ImapPostfach("a@example.invalid")],
                              zugang=lambda a, e: aufrufe.append(2) or "SYNTH-TOKEN")
    assert type(m) is kontor.modul("kontor.plugins.imap").ImapMailPlugin and m.postfaecher() == ["a@example.invalid"]
    assert p.erzeuge_benachrichtigungs_plugin(c) is None
    n = p.erzeuge_benachrichtigungs_plugin(_c(tmp_path, benachrichtigung_plugin="ntfy", ntfy_topic="t",
                                              ntfy_url="https://ntfy.example.invalid"),
                                           token_quelle=lambda: aufrufe.append(3) or "SYNTH")
    assert type(n) is kontor.modul("kontor.plugins.ntfy").NtfyPlugin and (n.name, n.ist_mock) == ("ntfy", False)
    mm = p.erzeuge_benachrichtigungs_plugin(_c(tmp_path, mock_modus=True))
    assert type(mm) is kontor.modul("kontor.plugins.mock_benachrichtigung").MockBenachrichtigungsPlugin
    assert (mm.name, mm.ist_mock, mm.gesendet) == ("mock", True, [])
    assert aufrufe == [], "Erzeugen ruft weder pin_quelle noch zugang noch token_quelle auf"
    # alte Aufrufe ohne Schlüsselwortargumente bleiben gültig
    assert p.erzeuge_bank_plugin(c).name == "fints" and p.erzeuge_mail_plugin(c).name == "imap"
    netz_gesperrt.pruefe()


@pytest.mark.kern
def test_oeffentliche_methoden(tmp_path):
    def oeffentlich(cls):
        return {n for n, _ in inspect.getmembers(cls, callable) if not n.startswith("_")}
    # M29 (fints.md 3, E-261): zusätzlich tan_verfahren
    assert oeffentlich(kontor.modul("kontor.plugins.fints").FintsBankPlugin) == {"konten", "umsaetze", "schliessen",
                                                                                 "tan_verfahren"}
    # D-243 (Kopfabruf): zusätzlich die lesenden Methoden koepfe und inhalte
    assert oeffentlich(kontor.modul("kontor.plugins.imap").ImapMailPlugin) == {"postfaecher", "nachrichten", "koepfe",
                                                                                "inhalte", "schliessen"}
    assert oeffentlich(kontor.modul("kontor.plugins.ntfy").NtfyPlugin) == {"senden", "schliessen"}
    assert oeffentlich(kontor.modul("kontor.plugins.mock_benachrichtigung").MockBenachrichtigungsPlugin) == {
        "senden", "schliessen"}


@pytest.mark.kern
def test_unkonfiguriert_ohne_verbindung(tmp_path, netz_gesperrt):
    """E-017 bleibt: unkonfigurierte echte Plugins werfen PluginNichtVerfuegbar, ohne Verbindung."""
    import datetime as dt
    p, f = kontor.plugins(), F()
    c = _c(tmp_path)
    b = p.erzeuge_bank_plugin(c, pin_quelle=lambda: "SYNTH-PIN")
    for aufruf in (b.konten, lambda: b.umsaetze("DE02000000000000000000", dt.date(2024, 1, 1), dt.date(2024, 1, 2))):
        with pytest.raises(f.PluginNichtVerfuegbar):
            aufruf()
    m = p.erzeuge_mail_plugin(c, postfaecher=[kontor.modul("kontor.plugins.imap").ImapPostfach("a@example.invalid")])
    with pytest.raises(f.PluginNichtVerfuegbar):
        m.nachrichten("a@example.invalid", dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc))
    with pytest.raises(f.PostfachUnbekannt):
        m.nachrichten("b@example.invalid", dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc))
    with pytest.raises(ValueError):
        m.nachrichten("a@example.invalid", dt.datetime(2024, 1, 1))
    netz_gesperrt.pruefe()


@pytest.mark.kern
def test_status_unveraendert(tmp_path):
    """E-029: /api/status meldet weiter nur Bank- und Mail-Plugin."""
    api = neue_api(tmp_path)
    assert api.get("/api/status", erwartet=200).daten["plugins"] == {"bank": {"name": "fints", "mock": False},
                                                                      "mail": {"name": "imap", "mock": False}}
