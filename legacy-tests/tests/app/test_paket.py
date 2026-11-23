"""Paket, Fehlerklassen und Konfiguration (python-api.md Abschnitte 1–3)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from pathlib import Path

import pytest

from tests.hilfen import kontor

# PEP 440, Anhang B (kanonischer regulärer Ausdruck)
PEP440 = re.compile(r"""
    v?
    (?:
        (?:(?P<epoch>[0-9]+)!)?
        (?P<release>[0-9]+(?:\.[0-9]+)*)
        (?P<pre>[-_\.]?(?P<pre_l>alpha|a|beta|b|preview|pre|c|rc)[-_\.]?(?P<pre_n>[0-9]+)?)?
        (?P<post>(?:-(?P<post_n1>[0-9]+))|(?:[-_\.]?(?P<post_l>post|rev|r)[-_\.]?(?P<post_n2>[0-9]+)?))?
        (?P<dev>[-_\.]?(?P<dev_l>dev)[-_\.]?(?P<dev_n>[0-9]+)?)?
    )
    (?:\+(?P<local>[a-z0-9]+(?:[-_\.][a-z0-9]+)*))?
""", re.VERBOSE | re.IGNORECASE)

MODULE_NAMEN = [
    ("kontor", ["__version__"]),
    ("kontor.fehler", ["KontorFehler", "KonfigurationsFehler", "PluginFehler", "PluginNichtVerfuegbar",
                       "BankFehler", "BankVerbindungsFehler", "BankZeitueberschreitung", "BankKontoUnbekannt",
                       "TanErforderlich", "MailFehler", "MailVerbindungsFehler", "MailTokenAbgelaufen",
                       "PostfachUnbekannt"]),
    ("kontor.config", ["KontorConfig"]),
    ("kontor.app", ["create_app"]),
    ("kontor.importer.kmymoney", ["importiere_kmy", "ImportErgebnis", "ImportMeldung"]),
    ("kontor.importer.ergebnis", ["ImportErgebnis", "ImportMeldung"]),
    ("kontor.plugins", ["erzeuge_bank_plugin", "erzeuge_mail_plugin"]),
    ("kontor.plugins.bank", ["BankPlugin", "BankKonto", "BankUmsatz"]),
    ("kontor.plugins.mail", ["MailPlugin", "MailNachricht"]),
    ("kontor.plugins.mock_bank", ["MockBankPlugin"]),
    ("kontor.plugins.mock_mail", ["MockMailPlugin"]),
]


@pytest.mark.parametrize("modulname,namen", MODULE_NAMEN, ids=[m for m, _ in MODULE_NAMEN])
def test_module_und_namen_vorhanden(modulname, namen):
    m = kontor.modul(modulname)
    fehlend = [n for n in namen if not hasattr(m, n)]
    assert not fehlend, f"{modulname} exportiert nicht: {fehlend}"


def test_version_pep440():
    v = kontor.modul("kontor").__version__
    assert isinstance(v, str) and PEP440.fullmatch(v.strip()) and v == v.strip(), \
        f"__version__ {v!r} ist keine PEP-440-Version"


def test_import_ergebnis_reexportiert():
    km = kontor.modul("kontor.importer.kmymoney")
    erg = kontor.modul("kontor.importer.ergebnis")
    assert km.ImportErgebnis is erg.ImportErgebnis
    assert km.ImportMeldung is erg.ImportMeldung
    for cls in (erg.ImportErgebnis, erg.ImportMeldung):
        assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen


# ------------------------------------------------------------------ Fehler

FEHLERBAUM = [
    # (Klasse, Basisklasse, code)
    ("KontorFehler", Exception, None),
    ("KonfigurationsFehler", "KontorFehler", "konfiguration_ungueltig"),
    ("PluginFehler", "KontorFehler", "plugin_fehler"),
    ("PluginNichtVerfuegbar", "PluginFehler", "plugin_nicht_verfuegbar"),
    ("BankFehler", "PluginFehler", "bank_fehler"),
    ("BankVerbindungsFehler", "BankFehler", "bank_verbindung"),
    ("BankZeitueberschreitung", "BankFehler", "bank_zeitueberschreitung"),
    ("BankKontoUnbekannt", "BankFehler", "bank_konto_unbekannt"),
    ("TanErforderlich", "BankFehler", "tan_erforderlich"),
    ("MailFehler", "PluginFehler", "mail_fehler"),
    ("MailVerbindungsFehler", "MailFehler", "mail_verbindung"),
    ("MailTokenAbgelaufen", "MailFehler", "mail_token_abgelaufen"),
    ("PostfachUnbekannt", "MailFehler", "mail_postfach_unbekannt"),
]


@pytest.mark.parametrize("name,basis,code", FEHLERBAUM, ids=[f[0] for f in FEHLERBAUM])
def test_fehlerklassen(name, basis, code):
    f = kontor.fehler()
    cls = getattr(f, name)
    basis_cls = basis if isinstance(basis, type) else getattr(f, basis)
    assert issubclass(cls, basis_cls)
    assert isinstance(cls.code, str) and cls.code, f"{name}.code fehlt"
    if code is not None:
        assert cls.code == code


@pytest.mark.parametrize("name", [f[0] for f in FEHLERBAUM if f[0] != "TanErforderlich"])
def test_fehler_meldung_und_details(name):
    cls = getattr(kontor.fehler(), name)
    e = cls("Etwas ist schiefgegangen – Ärger", konto="A1", anzahl=3)
    assert str(e) == "Etwas ist schiefgegangen – Ärger"
    assert e.meldung == "Etwas ist schiefgegangen – Ärger"
    assert e.details == {"konto": "A1", "anzahl": 3}
    assert cls().details == {}
    assert isinstance(e, Exception)


def test_fehlercodes_eindeutig():
    f = kontor.fehler()
    codes = [getattr(f, n).code for n, _, c in FEHLERBAUM if c]
    assert len(codes) == len(set(codes))


# ----------------------------------------------------------- Konfiguration


def Config():  # noqa: N802
    return kontor.KontorConfig()


def KonfigFehler():  # noqa: N802
    return kontor.fehler().KonfigurationsFehler


def test_vorgaben_echtmodus(tmp_path):
    c = Config()(datenbank=tmp_path / "kontor.sqlite3")
    assert c.mock_modus is False
    assert c.bank_plugin == "fints" and c.mail_plugin == "imap"
    assert c.mock_szenario == "normal"
    assert c.mock_daten is None and c.mock_heute is None
    assert c.aktive_datenbank == tmp_path / "kontor.sqlite3"


def test_vorgaben_mockmodus(tmp_path):
    c = Config()(datenbank=tmp_path / "kontor.sqlite3", mock_modus=True)
    assert c.bank_plugin == "mock" and c.mail_plugin == "mock"
    assert c.aktive_datenbank == tmp_path / "kontor-mock.sqlite3"
    c2 = Config()(datenbank=tmp_path / "daten.db", mock_modus=True)
    assert c2.aktive_datenbank == tmp_path / "daten-mock.db"
    eigene = tmp_path / "anders" / "m.sqlite3"
    c3 = Config()(datenbank=tmp_path / "kontor.sqlite3", mock_modus=True, mock_datenbank=eigene)
    assert c3.aktive_datenbank == eigene


def test_pfade_werden_path(tmp_path):
    c = Config()(datenbank=str(tmp_path / "k.sqlite3"), mock_modus=True,
                 mock_datenbank=str(tmp_path / "m.sqlite3"), mock_daten=str(tmp_path / "d.json"))
    assert isinstance(c.datenbank, Path) and c.datenbank == tmp_path / "k.sqlite3"
    assert isinstance(c.mock_datenbank, Path) and c.mock_datenbank == tmp_path / "m.sqlite3"
    assert isinstance(c.mock_daten, Path) and c.mock_daten == tmp_path / "d.json"
    assert isinstance(c.aktive_datenbank, Path)


def test_config_unveraenderlich(tmp_path):
    c = Config()(datenbank=tmp_path / "k.sqlite3")
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.mock_modus = True  # type: ignore[misc]


@pytest.mark.parametrize("felder", [
    {"bank_plugin": "hbci"},
    {"bank_plugin": "aqbanking"},  # E-259: M10 ist mit M29 entfallen
    {"mail_plugin": "pop3"},
    {"bank_plugin": "Mock"},
    {"mock_modus": True, "bank_plugin": "fints"},
    {"mock_modus": True, "mail_plugin": "imap"},
    {"mock_modus": False, "bank_plugin": "mock"},
    {"mock_modus": False, "mail_plugin": "mock"},
    {"mock_szenario": "gibtsnicht"},
    {"mock_modus": True, "mock_szenario": "gibtsnicht_m1"},  # E-095: kein künftiges Szenario
], ids=lambda f: ",".join(f"{k}={v}" for k, v in f.items()))
def test_ungueltige_konfiguration(tmp_path, felder):
    with pytest.raises(KonfigFehler()) as info:
        Config()(datenbank=tmp_path / "k.sqlite3", **felder)
    assert info.value.code == "konfiguration_ungueltig"


@pytest.mark.parametrize("szenario", ["normal", "bankfehler", "zeitueberschreitung", "tan_erforderlich",
                                      "token_ablauf"])
def test_bekannte_szenarien(tmp_path, szenario):
    c = Config()(datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_szenario=szenario)
    assert c.mock_szenario == szenario


def test_mock_datenbank_gleich_echtdatenbank(tmp_path):
    (tmp_path / "unter").mkdir()
    with pytest.raises(KonfigFehler()):
        Config()(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                 mock_datenbank=tmp_path / "unter" / ".." / "k.sqlite3")


def test_konstruktion_legt_nichts_an(tmp_path):
    ziel = tmp_path / "gibt" / "es" / "nicht"
    Config()(datenbank=ziel / "k.sqlite3")
    Config()(datenbank=ziel / "k.sqlite3", mock_modus=True)
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------- from_env


def _env(tmp_path, **kw) -> dict[str, str]:
    return {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), **kw}


def test_from_env_minimal(tmp_path):
    c = Config().from_env(_env(tmp_path))
    assert c.datenbank == tmp_path / "k.sqlite3"
    assert c.mock_modus is False and c.bank_plugin == "fints" and c.mail_plugin == "imap"
    assert c.mock_szenario == "normal" and c.mock_daten is None and c.mock_heute is None


@pytest.mark.parametrize("umgebung", [{}, {"KONTOR_DATENBANK": ""}], ids=["fehlt", "leer"])
def test_from_env_datenbank_pflicht(umgebung):
    with pytest.raises(KonfigFehler()):
        Config().from_env(umgebung)


@pytest.mark.parametrize("wert", ["1", "true", "TRUE", "ja", "Ja", "yes", "on", "On"])
def test_from_env_mock_wahr(tmp_path, wert):
    c = Config().from_env(_env(tmp_path, KONTOR_MOCK_MODUS=wert))
    assert c.mock_modus is True and c.bank_plugin == "mock" and c.mail_plugin == "mock"


@pytest.mark.parametrize("wert", ["0", "false", "False", "nein", "NEIN", "no", "off", ""])
def test_from_env_mock_falsch(tmp_path, wert):
    assert Config().from_env(_env(tmp_path, KONTOR_MOCK_MODUS=wert)).mock_modus is False


@pytest.mark.parametrize("wert", ["vielleicht", "2", "wahr", "y"])
def test_from_env_mock_ungueltig(tmp_path, wert):
    with pytest.raises(KonfigFehler()):
        Config().from_env(_env(tmp_path, KONTOR_MOCK_MODUS=wert))


def test_from_env_alle_felder(tmp_path):
    c = Config().from_env(_env(
        tmp_path, KONTOR_MOCK_MODUS="ja", KONTOR_MOCK_DATENBANK=str(tmp_path / "m.sqlite3"),
        KONTOR_BANK_PLUGIN="mock", KONTOR_MAIL_PLUGIN="mock", KONTOR_MOCK_SZENARIO="tan_erforderlich",
        KONTOR_MOCK_DATEN=str(tmp_path / "d.json"), KONTOR_MOCK_HEUTE="2024-06-30"))
    assert c.mock_modus is True
    assert c.aktive_datenbank == tmp_path / "m.sqlite3"
    assert c.mock_szenario == "tan_erforderlich"
    assert c.mock_daten == tmp_path / "d.json"
    assert c.mock_heute == dt.date(2024, 6, 30)


def test_from_env_leere_werte(tmp_path):
    c = Config().from_env(_env(tmp_path, KONTOR_MOCK_DATENBANK="", KONTOR_BANK_PLUGIN="",
                               KONTOR_MAIL_PLUGIN="", KONTOR_MOCK_SZENARIO="", KONTOR_MOCK_DATEN="",
                               KONTOR_MOCK_HEUTE=""))
    assert c.bank_plugin == "fints" and c.mail_plugin == "imap" and c.mock_szenario == "normal"
    assert c.mock_daten is None and c.mock_heute is None


@pytest.mark.parametrize("umgebung", [
    {"KONTOR_MOCK_HEUTE": "30.06.2024"},
    {"KONTOR_MOCK_HEUTE": "2024-02-30"},
    {"KONTOR_BANK_PLUGIN": "hbci"},
    {"KONTOR_MOCK_SZENARIO": "chaos"},
    {"KONTOR_BANK_PLUGIN": "mock"},
], ids=lambda u: ",".join(f"{k}={v}" for k, v in u.items()))
def test_from_env_ungueltig(tmp_path, umgebung):
    with pytest.raises(KonfigFehler()):
        Config().from_env(_env(tmp_path, **umgebung))


def test_from_env_none_liest_os_environ(tmp_path, monkeypatch):
    for k in ("KONTOR_MOCK_MODUS", "KONTOR_MOCK_DATENBANK", "KONTOR_BANK_PLUGIN", "KONTOR_MAIL_PLUGIN",
              "KONTOR_MOCK_SZENARIO", "KONTOR_MOCK_DATEN", "KONTOR_MOCK_HEUTE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KONTOR_DATENBANK", str(tmp_path / "aus-env.sqlite3"))
    monkeypatch.setenv("KONTOR_MOCK_MODUS", "on")
    c = Config().from_env()
    assert c.datenbank == tmp_path / "aus-env.sqlite3" and c.mock_modus is True
