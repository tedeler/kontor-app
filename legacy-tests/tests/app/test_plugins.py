"""Bank- und Mail-Plugins: Schnittstelle, Mock-Varianten, Szenarien, Auswahl per Konfiguration (plugins.md).

Alle Abrufe laufen mit gesperrtem Netzwerk (Fixture ``netz_gesperrt``): Die
Mock-Plugins dürfen keinerlei Verbindung aufbauen (T 21).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import inspect
import json

import pytest
from hypothesis import given, strategies as st

from generator.iban import ist_gueltig
from tests.hilfen import kontor
from tests.hilfen.api import neue_config
from tests.hilfen.erwartung import lade_mock
from tests.hilfen.pfade import MOCK

DATEN = MOCK / "mock_daten.json"
UTC = dt.timezone.utc
SZENARIEN = ["normal", "bankfehler", "zeitueberschreitung", "tan_erforderlich", "token_ablauf"]


def bank():
    return kontor.modul("kontor.plugins.bank")


def mail():
    return kontor.modul("kontor.plugins.mail")


def MockBank(*a, **kw):  # noqa: N802
    return kontor.modul("kontor.plugins.mock_bank").MockBankPlugin(*a, **kw)


def MockMail(*a, **kw):  # noqa: N802
    return kontor.modul("kontor.plugins.mock_mail").MockMailPlugin(*a, **kw)


def F():  # noqa: N802
    return kontor.fehler()


@pytest.fixture(scope="module")
def daten():
    return lade_mock()[0]


def _datum(s):
    return None if s is None else dt.date.fromisoformat(s)


def _zeit(s: str) -> dt.datetime:
    assert s.endswith("Z")
    return dt.datetime.fromisoformat(s[:-1]).replace(tzinfo=UTC)


def soll_umsaetze(daten, iban, von, bis, heute):
    aus = [u for u in daten["bank"]["umsaetze"] if u["iban"] == iban
           and von <= _datum(u["buchungstag"]) <= bis and _datum(u["buchungstag"]) <= heute]
    aus.sort(key=lambda u: (u["buchungstag"], u["umsatz_id"]))
    return [bank().BankUmsatz(**{**u, "buchungstag": _datum(u["buchungstag"]), "valuta": _datum(u["valuta"])})
            for u in aus]


def soll_nachrichten(daten, postfach, seit, heute):
    aus = [m for m in daten["mail"]["nachrichten"] if m["postfach"] == postfach
           and _zeit(m["empfangen"]) >= seit and _zeit(m["empfangen"]).date() <= heute]
    aus.sort(key=lambda m: (_zeit(m["empfangen"]), m["nachricht_id"]))
    return [mail().MailNachricht(**{**m, "empfangen": _zeit(m["empfangen"])}) for m in aus]


# ----------------------------------------------------------- Schnittstellen


def test_abstrakte_schnittstellen():
    bp, mp = bank().BankPlugin, mail().MailPlugin
    assert inspect.isabstract(bp) and inspect.isabstract(mp)
    assert bp.__abstractmethods__ == frozenset({"konten", "umsaetze"})
    assert mp.__abstractmethods__ == frozenset({"postfaecher", "nachrichten"})
    for cls in (bp, mp):
        assert callable(cls.schliessen) and "schliessen" not in cls.__abstractmethods__


@pytest.mark.parametrize("modul,name,felder", [
    ("bank", "BankKonto", {"iban", "bic", "name", "art", "inhaber", "waehrung"}),
    ("bank", "BankUmsatz", {"umsatz_id", "iban", "buchungstag", "valuta", "betrag", "waehrung", "gegenpartei_name",
                            "gegenpartei_iban", "verwendungszweck", "vormerkung", "storno"}),
    ("mail", "MailNachricht", {"nachricht_id", "postfach", "empfangen", "absender", "betreff", "text"}),
])
def test_datenklassen(modul, name, felder):
    cls = getattr(bank() if modul == "bank" else mail(), name)
    assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen
    assert {f.name for f in dataclasses.fields(cls)} == felder


def _oeffentliche_methoden(plugin) -> set[str]:
    cls = type(plugin)
    return {n for n in dir(cls) if not n.startswith("_") and callable(getattr(cls, n))}


@pytest.mark.parametrize("art", ["mock", "echt"])
def test_nur_lesende_oeffentliche_methoden(tmp_path, art, netz_gesperrt):
    """T 7/T 16: Es gibt keine Methode zum Überweisen, Senden, Löschen oder Verschieben."""
    p = kontor.plugins()
    config = neue_config(tmp_path, mock_modus=(art == "mock"))
    b, m = p.erzeuge_bank_plugin(config), p.erzeuge_mail_plugin(config)
    zusatz = {"setze_heute"} if art == "mock" else set()
    # M29 (plugins.md 12, E-261): das echte Bank-Plugin hat zusätzlich tan_verfahren
    bank_zusatz = zusatz if art == "mock" else {"tan_verfahren"}
    assert _oeffentliche_methoden(b) == {"konten", "umsaetze", "schliessen"} | bank_zusatz
    assert _oeffentliche_methoden(m) == {"postfaecher", "nachrichten", "schliessen"} | zusatz
    assert isinstance(b, bank().BankPlugin) and isinstance(m, mail().MailPlugin)
    assert b.schliessen() is None and m.schliessen() is None


# ------------------------------------------------------------- Mock-Bank


def test_mock_bank_konten(daten, netz_gesperrt):
    p = MockBank(DATEN, "normal", dt.date(2024, 12, 31))
    assert p.name == "mock" and p.ist_mock is True
    soll = [bank().BankKonto(**k) for k in daten["bank"]["konten"]]
    ist = p.konten()
    assert isinstance(ist, list)
    assert sorted(ist, key=lambda k: k.iban) == sorted(soll, key=lambda k: k.iban)
    for k in ist:
        assert ist_gueltig(k.iban) and k.waehrung == "EUR" and k.art in ("girokonto", "sparkonto", "kreditkonto")


def test_mock_bank_umsaetze_exakt(daten, netz_gesperrt):
    _, erw = lade_mock()
    p = MockBank(DATEN, heute=dt.date(2024, 12, 31))
    gesamt = 0
    for k in daten["bank"]["konten"]:
        ist = p.umsaetze(k["iban"], dt.date(2024, 1, 1), dt.date(2024, 12, 31))
        assert ist == soll_umsaetze(daten, k["iban"], dt.date(2024, 1, 1), dt.date(2024, 12, 31),
                                    dt.date(2024, 12, 31))
        assert len(ist) == erw["anzahl_umsaetze"][k["iban"]]
        assert sum(u.betrag for u in ist) == erw["saldo_veraenderung"][k["iban"]]
        assert all(type(u.betrag) is int for u in ist)
        gesamt += len(ist)
    assert gesamt == len(daten["bank"]["umsaetze"])
    alle = [u for k in daten["bank"]["konten"] for u in p.umsaetze(k["iban"], dt.date(2000, 1, 1), dt.date(2100, 1, 1))]
    assert {u.umsatz_id for u in alle if u.vormerkung} == set(erw["vormerkungen"])
    assert {u.umsatz_id for u in alle if u.storno} == set(erw["stornos"])
    assert any(u.valuta is None for u in alle) and any(u.gegenpartei_iban is None for u in alle)


def test_mock_bank_iban_normalisiert_und_unbekannt(daten, netz_gesperrt):
    p = MockBank(DATEN, heute=dt.date(2024, 12, 31))
    iban = daten["bank"]["konten"][0]["iban"]
    locker = " ".join(iban[i:i + 4] for i in range(0, len(iban), 4)).lower()
    von, bis = dt.date(2024, 3, 1), dt.date(2024, 3, 31)
    assert p.umsaetze(locker, von, bis) == p.umsaetze(iban, von, bis)
    with pytest.raises(F().BankKontoUnbekannt):
        p.umsaetze("DE02000000000000000000", von, bis)
    with pytest.raises(ValueError):
        p.umsaetze(iban, bis, von)
    assert p.umsaetze(iban, von, von) == soll_umsaetze(daten, iban, von, von, dt.date(2024, 12, 31))


def test_mock_bank_zeitlich_fortlaufend(daten, netz_gesperrt):
    iban = daten["bank"]["konten"][0]["iban"]
    von, bis = dt.date(2024, 1, 1), dt.date(2024, 12, 31)
    p = MockBank(DATEN, heute=dt.date(2024, 3, 31))
    frueh = p.umsaetze(iban, von, bis)
    assert frueh == soll_umsaetze(daten, iban, von, bis, dt.date(2024, 3, 31))
    assert max(u.buchungstag for u in frueh) <= dt.date(2024, 3, 31)
    p.setze_heute(dt.date(2024, 9, 30))
    spaeter = p.umsaetze(iban, von, bis)
    assert len(spaeter) > len(frueh)
    assert [u for u in spaeter if u.buchungstag <= dt.date(2024, 3, 31)] == frueh, "Geliefertes bleibt unverändert"
    p.setze_heute(None)  # heute = date.today() (liegt nach 2024)
    assert p.umsaetze(iban, von, bis) == soll_umsaetze(daten, iban, von, bis, dt.date.today())


def test_mock_bank_heute_none_ist_heute(daten, netz_gesperrt):
    iban = daten["bank"]["konten"][0]["iban"]
    p = MockBank(DATEN)
    assert p.umsaetze(iban, dt.date(2024, 1, 1), dt.date(2024, 12, 31)) == soll_umsaetze(
        daten, iban, dt.date(2024, 1, 1), dt.date(2024, 12, 31), dt.date.today())


@given(st.dates(min_value=dt.date(2023, 12, 1), max_value=dt.date(2025, 1, 31)),
       st.dates(min_value=dt.date(2023, 12, 1), max_value=dt.date(2025, 1, 31)),
       st.dates(min_value=dt.date(2023, 12, 1), max_value=dt.date(2025, 1, 31)),
       st.integers(0, 1))
def test_mock_bank_filter_eigenschaft(von, bis, heute, konto_nr):
    daten = lade_mock()[0]
    iban = daten["bank"]["konten"][konto_nr]["iban"]
    p = MockBank(DATEN, heute=heute)
    if von > bis:
        with pytest.raises(ValueError):
            p.umsaetze(iban, von, bis)
        return
    assert p.umsaetze(iban, von, bis) == soll_umsaetze(daten, iban, von, bis, heute)


def test_mock_bank_deterministisch(daten, netz_gesperrt):
    heute = dt.date(2024, 8, 15)
    a, b = MockBank(DATEN, heute=heute), MockBank(DATEN, heute=heute)
    ibans = [k["iban"] for k in daten["bank"]["konten"]]
    teil = b.umsaetze(ibans[1], dt.date(2024, 5, 1), dt.date(2024, 5, 31))
    ganz_b = [b.umsaetze(i, dt.date(2024, 1, 1), dt.date(2024, 12, 31)) for i in reversed(ibans)][::-1]
    ganz_a = [a.umsaetze(i, dt.date(2024, 1, 1), dt.date(2024, 12, 31)) for i in ibans]
    assert ganz_a == ganz_b
    assert teil == [u for u in ganz_a[1] if dt.date(2024, 5, 1) <= u.buchungstag <= dt.date(2024, 5, 31)]
    assert a.konten() == b.konten()


def test_umsatz_ids_eindeutig_und_stabil(daten, netz_gesperrt):
    p = MockBank(DATEN, heute=dt.date(2024, 12, 31))
    for k in daten["bank"]["konten"]:
        us = p.umsaetze(k["iban"], dt.date(2024, 1, 1), dt.date(2024, 12, 31))
        assert len({u.umsatz_id for u in us}) == len(us)
        assert all(u.iban == k["iban"] for u in us)
        assert us == sorted(us, key=lambda u: (u.buchungstag, u.umsatz_id))


# ------------------------------------------------------------- Mock-Mail


def test_mock_mail_exakt(daten, netz_gesperrt):
    _, erw = lade_mock()
    p = MockMail(DATEN, "normal", dt.date(2024, 12, 31))
    assert p.name == "mock" and p.ist_mock is True
    assert sorted(p.postfaecher()) == sorted(daten["mail"]["postfaecher"])
    seit = dt.datetime(2024, 1, 1, tzinfo=UTC)
    for pf in daten["mail"]["postfaecher"]:
        ist = p.nachrichten(pf, seit)
        assert ist == soll_nachrichten(daten, pf, seit, dt.date(2024, 12, 31))
        assert len(ist) == erw["anzahl_nachrichten"][pf]
        for m in ist:
            assert m.empfangen.tzinfo is not None and m.empfangen.utcoffset() == dt.timedelta(0)


def test_mock_mail_seit_und_fehler(daten, netz_gesperrt):
    p = MockMail(DATEN, heute=dt.date(2024, 12, 31))
    pf = daten["mail"]["postfaecher"][0]
    alle = p.nachrichten(pf, dt.datetime(2000, 1, 1, tzinfo=UTC))
    grenze = alle[len(alle) // 2].empfangen
    ab = p.nachrichten(pf, grenze)
    assert ab == [m for m in alle if m.empfangen >= grenze] and ab[0].empfangen == grenze
    andere_zone = grenze.astimezone(dt.timezone(dt.timedelta(hours=2)))
    assert p.nachrichten(pf, andere_zone) == ab
    with pytest.raises(ValueError):
        p.nachrichten(pf, dt.datetime(2024, 1, 1))
    with pytest.raises(F().PostfachUnbekannt):
        p.nachrichten("niemand@example.invalid", dt.datetime(2024, 1, 1, tzinfo=UTC))


def test_mock_mail_zeitlich_fortlaufend(daten, netz_gesperrt):
    pf = daten["mail"]["postfaecher"][1]
    seit = dt.datetime(2024, 1, 1, tzinfo=UTC)
    p = MockMail(DATEN, heute=dt.date(2024, 4, 30))
    frueh = p.nachrichten(pf, seit)
    assert frueh == soll_nachrichten(daten, pf, seit, dt.date(2024, 4, 30))
    p.setze_heute(dt.date(2024, 12, 31))
    spaeter = p.nachrichten(pf, seit)
    assert len(spaeter) > len(frueh) and spaeter[:len(frueh)] == frueh


# --------------------------------------------------------------- Szenarien


@pytest.mark.parametrize("szenario,fehler", [("bankfehler", "BankVerbindungsFehler"),
                                             ("zeitueberschreitung", "BankZeitueberschreitung")])
def test_szenario_bankfehler(daten, szenario, fehler, netz_gesperrt):
    cls = getattr(F(), fehler)
    p = MockBank(DATEN, szenario, dt.date(2024, 12, 31))
    with pytest.raises(cls) as info:
        p.konten()
    assert isinstance(info.value, F().PluginFehler) and info.value.code == cls.code
    with pytest.raises(cls):
        p.umsaetze(daten["bank"]["konten"][0]["iban"], dt.date(2024, 1, 1), dt.date(2024, 1, 31))
    m = MockMail(DATEN, szenario, dt.date(2024, 12, 31))
    assert sorted(m.postfaecher()) == sorted(daten["mail"]["postfaecher"])


def test_szenario_tan_erforderlich(daten, netz_gesperrt):
    heute = dt.date(2024, 7, 1)
    p = MockBank(DATEN, "tan_erforderlich", heute)
    assert len(p.konten()) == len(daten["bank"]["konten"])
    with pytest.raises(F().TanErforderlich) as info:
        p.umsaetze(daten["bank"]["konten"][0]["iban"], dt.date(2024, 1, 1), dt.date(2024, 1, 31))
    e = info.value
    assert isinstance(e.anforderung_id, str) and e.anforderung_id.strip()
    assert e.gueltig_bis == dt.datetime(2024, 7, 1, 23, 59, 59, tzinfo=UTC)
    assert e.gueltig_bis.utcoffset() == dt.timedelta(0)
    assert e.code == "tan_erforderlich" and isinstance(e, F().BankFehler)


def test_szenario_token_ablauf(daten, netz_gesperrt):
    m = MockMail(DATEN, "token_ablauf", dt.date(2024, 12, 31))
    with pytest.raises(F().MailTokenAbgelaufen):
        m.postfaecher()
    with pytest.raises(F().MailTokenAbgelaufen) as info:
        m.nachrichten(daten["mail"]["postfaecher"][0], dt.datetime(2024, 1, 1, tzinfo=UTC))
    assert isinstance(info.value, F().MailFehler)
    b = MockBank(DATEN, "token_ablauf", dt.date(2024, 12, 31))
    assert len(b.konten()) == len(daten["bank"]["konten"])


def test_fehlermeldungen_ohne_geheimnisse(daten, netz_gesperrt):
    for szenario in ("bankfehler", "zeitueberschreitung", "tan_erforderlich"):
        p = MockBank(DATEN, szenario, dt.date(2024, 12, 31))
        try:
            p.umsaetze(daten["bank"]["konten"][0]["iban"], dt.date(2024, 1, 1), dt.date(2024, 1, 31))
        except F().PluginFehler as e:
            assert str(e) == e.meldung and e.meldung.strip(), "Fehler brauchen eine deutsche Meldung"
            assert "pin" not in e.meldung.lower().split()


@pytest.mark.parametrize("cls", ["MockBank", "MockMail"])
def test_unbekanntes_szenario(cls):
    # E-095: ein Name, der in keinem Meilenstein ein Szenario ist
    with pytest.raises(F().KonfigurationsFehler):
        globals()[cls](DATEN, "gibtsnicht_m1")


# --------------------------------------------------------- Mock-Datendatei


def _schreibe(tmp_path, inhalt) -> object:
    p = tmp_path / "daten.json"
    p.write_text(inhalt if isinstance(inhalt, str) else json.dumps(inhalt), encoding="utf-8")
    return p


def _gueltig():
    return json.loads(DATEN.read_text(encoding="utf-8"))


@pytest.mark.parametrize("veraendern", [
    lambda d: "kein json {",
    lambda d: {**d, "format": "anders"},
    lambda d: {**d, "version": 2},
    lambda d: {k: v for k, v in d.items() if k != "bank"},
    lambda d: {k: v for k, v in d.items() if k != "mail"},
    lambda d: {**d, "bank": {"konten": d["bank"]["konten"]}},
    lambda d: {**d, "bank": {**d["bank"], "umsaetze": [{k: v for k, v in d["bank"]["umsaetze"][0].items()
                                                         if k != "betrag"}]}},
    lambda d: {**d, "mail": {**d["mail"], "nachrichten": [{k: v for k, v in d["mail"]["nachrichten"][0].items()
                                                            if k != "empfangen"}]}},
    lambda d: [],
], ids=["kein_json", "format", "version", "ohne_bank", "ohne_mail", "ohne_umsaetze", "umsatz_ohne_betrag",
        "nachricht_ohne_empfangen", "liste"])
@pytest.mark.parametrize("cls", ["MockBank", "MockMail"])
def test_ungueltige_datendatei(tmp_path, veraendern, cls):
    pfad = _schreibe(tmp_path, veraendern(_gueltig()))
    with pytest.raises(F().KonfigurationsFehler):
        globals()[cls](pfad, "normal", dt.date(2024, 12, 31))


@pytest.mark.parametrize("cls", ["MockBank", "MockMail"])
def test_fehlende_datendatei(tmp_path, cls):
    with pytest.raises(F().KonfigurationsFehler):
        globals()[cls](tmp_path / "gibtsnicht.json")


def test_unbekannte_schluessel_ignoriert(tmp_path, daten, netz_gesperrt):
    d = _gueltig()
    d["zusatz"] = {"egal": True}
    d["bank"]["konten"][0]["zusatzfeld"] = 1
    d["bank"]["umsaetze"][0]["kategorie"] = "Gehalt"
    d["mail"]["nachrichten"][0]["anhang"] = None
    pfad = _schreibe(tmp_path, d)
    heute = dt.date(2024, 12, 31)
    a, b = MockBank(pfad, heute=heute), MockBank(DATEN, heute=heute)
    iban = daten["bank"]["konten"][0]["iban"]
    assert a.umsaetze(iban, dt.date(2024, 1, 1), heute) == b.umsaetze(iban, dt.date(2024, 1, 1), heute)
    pf = daten["mail"]["postfaecher"][0]
    seit = dt.datetime(2024, 1, 1, tzinfo=UTC)
    assert MockMail(pfad, heute=heute).nachrichten(pf, seit) == MockMail(DATEN, heute=heute).nachrichten(pf, seit)


# ------------------------------------------------------ eingebauter Datensatz


@pytest.mark.parametrize("heute", [dt.date.today(), dt.date(2024, 6, 30), dt.date(2031, 2, 28)])
def test_eingebauter_datensatz(heute, netz_gesperrt):
    b = MockBank(None, "normal", heute)
    konten = b.konten()
    arten = {k.art for k in konten}
    assert {"girokonto", "sparkonto"} <= arten
    for k in konten:
        assert ist_gueltig(k.iban) and k.iban[4:12] == "00000000", f"IBAN {k.iban} nicht offensichtlich fiktiv"
        us = b.umsaetze(k.iban, heute - dt.timedelta(days=365), heute)
        assert us, f"kein Umsatz für {k.iban} im Jahr vor {heute}"
        assert all(u.buchungstag <= heute for u in us)
    assert b.konten() == MockBank(None, "normal", heute).konten()
    m = MockMail(None, "normal", heute)
    pf = m.postfaecher()
    assert len(pf) >= 2 and all(p.endswith("@example.invalid") for p in pf)
    seit = dt.datetime(1970, 1, 1, tzinfo=UTC)
    alle = [n for p in pf for n in m.nachrichten(p, seit)]
    assert alle and all(n.empfangen.date() <= heute for n in alle)
    assert alle == [n for p in pf for n in MockMail(None, "normal", heute).nachrichten(p, seit)]


# ------------------------------------------------ Auswahl per Konfiguration


def test_erzeuge_mock_plugins_aus_konfiguration(tmp_path, daten, netz_gesperrt):
    p = kontor.plugins()
    c = neue_config(tmp_path, mock_modus=True, mock_daten=DATEN, mock_heute=dt.date(2024, 6, 30))
    b, m = p.erzeuge_bank_plugin(c), p.erzeuge_mail_plugin(c)
    assert isinstance(b, kontor.modul("kontor.plugins.mock_bank").MockBankPlugin)
    assert isinstance(m, kontor.modul("kontor.plugins.mock_mail").MockMailPlugin)
    iban = daten["bank"]["konten"][0]["iban"]
    assert b.umsaetze(iban, dt.date(2024, 1, 1), dt.date(2024, 12, 31)) == soll_umsaetze(
        daten, iban, dt.date(2024, 1, 1), dt.date(2024, 12, 31), dt.date(2024, 6, 30))
    pf = daten["mail"]["postfaecher"][0]
    seit = dt.datetime(2024, 1, 1, tzinfo=UTC)
    assert m.nachrichten(pf, seit) == soll_nachrichten(daten, pf, seit, dt.date(2024, 6, 30))


@pytest.mark.parametrize("szenario", SZENARIEN)
def test_szenario_aus_konfiguration(tmp_path, szenario, netz_gesperrt):
    p = kontor.plugins()
    c = neue_config(tmp_path, mock_modus=True, mock_daten=DATEN, mock_szenario=szenario,
                    mock_heute=dt.date(2024, 12, 31))
    b, m = p.erzeuge_bank_plugin(c), p.erzeuge_mail_plugin(c)
    erwartet_bank = {"bankfehler": F().BankVerbindungsFehler, "zeitueberschreitung": F().BankZeitueberschreitung}
    if szenario in erwartet_bank:
        with pytest.raises(erwartet_bank[szenario]):
            b.konten()
    else:
        assert b.konten()
    if szenario == "token_ablauf":
        with pytest.raises(F().MailTokenAbgelaufen):
            m.postfaecher()
    else:
        assert m.postfaecher()


def test_mock_daten_ungueltig_ueber_konfiguration(tmp_path):
    c = neue_config(tmp_path, mock_modus=True, mock_daten=tmp_path / "fehlt.json")
    with pytest.raises(F().KonfigurationsFehler):
        kontor.plugins().erzeuge_bank_plugin(c)


def test_echte_plugins_erzeugbar_ohne_verbindung(tmp_path, netz_gesperrt):
    """E-017: fints/imap sind wählbar, ist_mock False; Erzeugen baut keine Verbindung auf."""
    p = kontor.plugins()
    c = neue_config(tmp_path)
    b, m = p.erzeuge_bank_plugin(c), p.erzeuge_mail_plugin(c)
    assert (b.name, b.ist_mock, m.name, m.ist_mock) == ("fints", False, "imap", False)
    assert isinstance(b, bank().BankPlugin) and isinstance(m, mail().MailPlugin)
    assert not isinstance(b, kontor.modul("kontor.plugins.mock_bank").MockBankPlugin)
    assert not isinstance(m, kontor.modul("kontor.plugins.mock_mail").MockMailPlugin)
    netz_gesperrt.pruefe()
    # Abrufe dürfen in Meilenstein 1 mit PluginNichtVerfuegbar scheitern – nie mit anderen Ausnahmen.
    for aufruf in (b.konten, lambda: b.umsaetze("DE02000000000000000000", dt.date(2024, 1, 1), dt.date(2024, 1, 2)),
                   m.postfaecher, lambda: m.nachrichten("x@example.invalid", dt.datetime(2024, 1, 1, tzinfo=UTC))):
        try:
            aufruf()
        except F().PluginFehler:
            pass
    netz_gesperrt.versuche.clear()  # Versuche wurden abgefangen; Verbindungen zu echten Diensten gab es nicht


def test_plugins_frisch_je_konfiguration(tmp_path, netz_gesperrt):
    p = kontor.plugins()
    c1 = neue_config(tmp_path / "a", mock_modus=True, mock_szenario="bankfehler", mock_heute=dt.date(2024, 1, 1))
    c2 = neue_config(tmp_path / "b", mock_modus=True, mock_heute=dt.date(2024, 1, 1))
    with pytest.raises(F().BankVerbindungsFehler):
        p.erzeuge_bank_plugin(c1).konten()
    assert p.erzeuge_bank_plugin(c2).konten()
