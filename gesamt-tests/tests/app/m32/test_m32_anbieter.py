"""M32: Anbieter-Beschreibungen und PayPal-Zuordnung nach Betrag, Zeitfenster und Händler (sammel3.md 9; D-230,
D-232; E-301, E-302) – kern. Mails aus einer Mock-Datendatei je Test, Beschreibungen nach ANBIETER.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.hilfen import kontor
from tests.hilfen.m6 import abruf
from tests.hilfen.m20 import PAYPAL, abgleich, alle, app, ausgabe, konten, nachricht, paypal_zahlung
from tests.hilfen.m32 import kaufhaus_mail, kaufhaus_toml

pytestmark = pytest.mark.kern
PP = "PP.1234.PP . {h}, Ihr Einkauf bei {h}"   # Verwendungszweck einer PayPal-Lastschrift (D-232)
LANG = "Auftrag\\s+(K\\d{6})(?:" + "a?" * 260 + ")"   # gültiger Ausdruck mit mehr als 500 Zeichen


# ------------------------------------------------------------------ 9.1 Konfiguration


def test_konfiguration_anbieter_verzeichnis(tmp_path):
    K = kontor.KontorConfig()
    F = kontor.fehler().KonfigurationsFehler
    db = tmp_path / "k.db"
    assert K(datenbank=db).anbieter_verzeichnis is None
    assert Path(K(datenbank=db, anbieter_verzeichnis=tmp_path / "anb").anbieter_verzeichnis) == tmp_path / "anb"
    assert Path(K(datenbank=db, anbieter_verzeichnis=str(tmp_path)).anbieter_verzeichnis) == tmp_path
    for falsch in (5, True, ["x"]):
        with pytest.raises(F) as e:
            K(datenbank=db, anbieter_verzeichnis=falsch)
        assert e.value.details.get("feld") == "anbieter_verzeichnis"
    env = {"KONTOR_DATENBANK": str(db)}
    assert K.from_env(env).anbieter_verzeichnis is None
    assert K.from_env({**env, "KONTOR_ANBIETER_VERZEICHNIS": ""}).anbieter_verzeichnis is None
    assert Path(K.from_env({**env, "KONTOR_ANBIETER_VERZEICHNIS": str(tmp_path / "x")}).anbieter_verzeichnis) == \
        tmp_path / "x"
    assert K(datenbank=db, anbieter_verzeichnis=tmp_path / "gibt-es-nicht").anbieter_verzeichnis is not None, \
        "die Konstruktion prüft das Verzeichnis nicht"


# ------------------------------------------------------------------ 9.1 eigene Beschreibung


def _verzeichnis(tmp_path, dateien: dict[str, str]) -> Path:
    v = tmp_path / "anbieter"
    v.mkdir()
    for name, text in dateien.items():
        (v / name).write_text(text, encoding="utf-8")
    return v


def test_eigene_beschreibung_erkennt_und_ordnet_zu(tmp_path):
    v = _verzeichnis(tmp_path, {"kaufhaus.toml": kaufhaus_toml()})
    api = app(tmp_path, [kaufhaus_mail(empfangen="2024-06-03T08:00:00Z")], heute="2024-06-20",
              anbieter_verzeichnis=v)
    abruf(api)
    abgleich(api)
    (e,) = alle(api)
    assert (e["anbieter"], e["grund"], e["richtung"], e["haendler"], e["kennung"]) == (
        "kaufhaus", "bestellung", "ausgabe", "Kaufhaus Muster", "K123456")
    assert (e["betrag"], e["gesamt"], e["guthaben"], e["buchung_ids"]) == (4250, 4250, 0, [])
    k = konten(api)
    andere = ausgabe(api, k, "2024-06-05", 4250, "Lastschrift ohne Bezug")
    b = ausgabe(api, k, "2024-06-06", 4250, "Kaufhaus Muster Auftrag K123456")
    abgleich(api)
    (e,) = alle(api)
    assert e["buchung_ids"] == [b] and e["zustand"] == "erfuellt" and andere not in e["buchung_ids"]


def test_fehlerhafte_beschreibungen_werden_uebergangen(tmp_path):
    lang = kaufhaus_toml().replace('name = "kaufhaus"', 'name = "lang"').replace(
        "muster = 'Auftrag\\s+(K\\d{6})'", "muster = '" + LANG + "'")
    assert len(LANG) > 500 and 'name = "lang"' in lang and LANG in lang
    v = _verzeichnis(tmp_path, {"kaufhaus.toml": kaufhaus_toml(), "kaputt.toml": "name = [unvollständig\n",
                                "ohne_kennung.toml": 'name = "ohne"\ntitel = "Ohne"\nabsender = \'.*\'\n',
                                "lang.toml": lang})
    api = app(tmp_path, [kaufhaus_mail(empfangen="2024-06-03T08:00:00Z")], heute="2024-06-20",
              anbieter_verzeichnis=v)
    abruf(api)
    assert abgleich(api) is not None
    assert [e["anbieter"] for e in alle(api)] == ["kaufhaus"], "die übrigen Dateien sind übergangen"


def test_ohne_verzeichnis_keine_erwartung(tmp_path):
    api = app(tmp_path, [kaufhaus_mail()], heute="2024-06-20", anbieter_verzeichnis=tmp_path / "gibt-es-nicht")
    abruf(api)
    abgleich(api)
    assert alle(api) == []


def test_mitgelieferte_paypal_beschreibung_bleibt(tmp_path):
    api = app(tmp_path, [paypal_zahlung(empfangen="2024-06-03T08:00:00Z")], heute="2024-06-20")
    abruf(api)
    (e,) = alle(api)
    assert (e["anbieter"], e["grund"], e["haendler"], e["betrag"]) == ("paypal", "paypal", "Fiktiver Shop", 2000)


# ------------------------------------------------------------------ 9.2 PayPal


def _paypal(tmp_path, haendler="Fiktiver Shop", buchungen=(), betreff=None):
    m = paypal_zahlung(haendler=haendler, empfangen="2024-06-03T08:00:00Z")
    if betreff is not None:
        m = nachricht(PAYPAL, betreff, m["text"], "2024-06-03T08:00:00Z")
    api = app(tmp_path, [m], heute="2024-06-20")
    k = konten(api)
    ids = [ausgabe(api, k, d, betrag, zweck) for d, betrag, zweck in buchungen]
    abruf(api)
    abgleich(api)
    (e,) = alle(api)
    return api, e, ids


def test_andere_buchungen_gleichen_betrags_stoeren_nicht(tmp_path):
    _, e, (ohne, mit) = _paypal(tmp_path, buchungen=[("2024-06-04", 2000, "Lastschrift Testbank"),
                                                     ("2024-06-05", 2000, PP.format(h="FIKTIVER SHOP"))])
    assert e["buchung_ids"] == [mit] and e["zustand"] == "erfuellt"


def test_zwei_buchungen_mit_haendler_bleiben_offen(tmp_path):
    _, e, _ = _paypal(tmp_path, buchungen=[("2024-06-04", 2000, PP.format(h="FIKTIVER SHOP")),
                                           ("2024-06-05", 2000, "PAYPAL *FIKTIVER")])
    assert e["buchung_ids"] == [] and e["zustand"] == "offen"


@pytest.mark.parametrize("datum,zugeordnet", [("2024-05-29", True), ("2024-06-08", True), ("2024-05-28", False),
                                              ("2024-06-09", False)])
def test_zeitfenster_fuenf_tage(tmp_path, datum, zugeordnet):
    _, e, (b,) = _paypal(tmp_path, buchungen=[(datum, 2000, PP.format(h="FIKTIVER SHOP"))])
    assert e["buchung_ids"] == ([b] if zugeordnet else [])


@pytest.mark.parametrize("zweck,zugeordnet", [
    ("PAYPAL Dom", True),                    # kurzes Wort als ganzes Wort
    ("PAYPAL Domino", False),                # kurzes Wort nicht als Teil eines Wortes
    ("PAYPAL KALINOWSKYS", True),            # Wort ab 4 Zeichen irgendwo im Text
    (PP.format(h="DOMKALINOW"), True),       # gekürzter, zusammengeschriebener Name der Bank (bank.haendler)
    ("PAYPAL Zahlung", False),
])
def test_haendler_in_teilen(tmp_path, zweck, zugeordnet):
    _, e, (b,) = _paypal(tmp_path, haendler="Dom Kalinowsky", buchungen=[("2024-06-04", 2000, zweck)])
    assert e["buchung_ids"] == ([b] if zugeordnet else []), zweck


def test_allerweltswort_allein_genuegt_nicht(tmp_path):
    _, e, _ = _paypal(tmp_path, buchungen=[("2024-06-04", 2000, "PAYPAL Shop GmbH")])
    assert e["buchung_ids"] == []


def test_mail_ohne_haendler_nie_automatisch(tmp_path):
    _, e, _ = _paypal(tmp_path, betreff="Ihre Zahlung", buchungen=[("2024-06-04", 2000, "PAYPAL Zahlung")])
    assert e["haendler"] == "PayPal" and e["buchung_ids"] == []
