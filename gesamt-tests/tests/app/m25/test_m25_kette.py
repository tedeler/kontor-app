"""M25: Kettenbildung mit Betragsfilter – Übersicht, Begründung und Ereignisse (wiederkehrend.md 9.1, 9.2, 9.3.5,
9.5; E-240). Erwartungen aus der erweiterten Referenzkette (``tests/hilfen/m25``) und den Beispielen."""

from __future__ import annotations

import datetime as dt
import random

import pytest

from tests.hilfen.api import neue_api
from tests.hilfen.m16 import Abo, eintrag, rhythmus, schritte
from tests.hilfen import wiederkehrend_orakel as wo
from tests.hilfen.m25 import (
    filter_loeschen, filter_setzen, filter_text, pruefe_begruendung, uebersicht_ist, uebersicht_soll, vorgabe,
)

pytestmark = pytest.mark.kern


@pytest.fixture
def abo(tmp_path):
    return Abo(neue_api(tmp_path))


def _rollen(antwort) -> dict[int, str]:
    return {x["buchung_id"]: x["rolle"] for x in eintrag(antwort)["buchungen"]}


def _alle(abo, ids, stichtag):
    for b in ids:
        pruefe_begruendung(abo.api, b, stichtag)
    assert uebersicht_ist(abo.api, stichtag) == uebersicht_soll(abo.api, stichtag)


# ------------------------------------------------------------------ Beispiele 9.5
def _gehalt(abo, juengste_erstattung=False):
    e = abo.empfaenger("Arbeitgeber Beispiel (fiktiv)")
    gehalt, erst = [], []
    for mon in range(1, 7):
        gehalt += abo.buchen(e, [f"2024-{mon:02d}-28"], 250000)
        erst += abo.buchen(e, [f"2024-{mon:02d}-{10 + mon:02d}"], 3740 if mon % 2 else 11200)
    if juengste_erstattung:
        erst += abo.buchen(e, ["2024-07-02"], 3740)
    return e, gehalt, erst


def test_beispiel_1_gehalt_mit_erstattungen(abo):
    e, gehalt, erst = _gehalt(abo)
    a = pruefe_begruendung(abo.api, gehalt[0], "2024-07-10")
    x = eintrag(a)
    assert x["serie"]["buchung_ids"] == gehalt and x["serie"]["rhythmus"] == "monatlich"
    assert _rollen(a)[erst[0]] == "vor_beginn", "zugelassen und vor Kettenbeginn"
    assert all(_rollen(a)[b] == "anderer_betrag" for b in erst[1:])
    assert [s[0] for s in schritte(x)][1:-1] == ["verbunden"] * 5
    _alle(abo, gehalt + erst, "2024-07-10")
    vorgabe(abo.api, "aus")
    x = eintrag(pruefe_begruendung(abo.api, gehalt[-1], "2024-07-10"))
    assert ("bruch", "fremde_zahlung") in [s[:2] for s in schritte(x)], "mit aus: fremde Zahlung"


def test_beispiel_2_juengste_ist_erstattung(abo):
    e, gehalt, erst = _gehalt(abo, juengste_erstattung=True)
    a = pruefe_begruendung(abo.api, erst[-1], "2024-07-10")
    x = eintrag(a)
    assert x["urteil"] == "anderer_betrag" and a["urteil"] == "nicht_wiederkehrend"
    assert x["serie"]["buchung_ids"] == gehalt and x["serie"]["letzte"] == "2024-06-28"
    assert rhythmus(x, "monatlich")["schritte"][0]["von"]["buchung_id"] == gehalt[-1], "Anker bleibt das Gehalt"


def test_beispiel_3_anker_nach_betrag(abo):
    e = abo.empfaenger("Versicherung (fiktiv)")
    ids = abo.buchen(e, ["2024-08-04", "2024-09-04", "2024-10-05", "2024-11-04", "2024-11-04"],
                     [-32032] * 4 + [-5000])
    a = pruefe_begruendung(abo.api, ids[-1], "2024-11-20")
    x = eintrag(a)
    assert x["serie"]["buchung_ids"] == ids[:4] and x["urteil"] == "anderer_betrag"
    anker = rhythmus(x, "monatlich")["schritte"][0]
    assert anker["ergebnis"] == "anker" and {k["buchung_id"] for k in anker["kandidaten"]} == {ids[3], ids[4]}
    vorgabe(abo.api, "aus")
    assert eintrag(pruefe_begruendung(abo.api, ids[-1], "2024-11-20"))["urteil"] == "zusaetzlich"


def test_beispiel_4_preisaenderung(abo):
    e = abo.empfaenger("Streaming (fiktiv)")
    ids = abo.buchen(e, ["2024-01-15", "2024-02-15", "2024-03-15", "2024-04-15"], [-999, -999, -1299, -1299])
    x = eintrag(pruefe_begruendung(abo.api, ids[0], "2024-04-20"))
    assert x["serie"]["buchung_ids"] == ids and x["serie"]["betrag"] == -1299
    assert ("verbunden", None, ids[2], ids[1]) in schritte(x)


def test_beispiel_5_preisaenderung_nach_uebergehen(abo):
    e = abo.empfaenger("Streaming (fiktiv)")
    ids = abo.buchen(e, ["2024-01-15", "2024-02-15", "2024-03-15", "2024-04-15"], [-999, -999, -1299, -1299])
    extra = abo.buchen(e, ["2024-03-20"], -100)
    x = eintrag(pruefe_begruendung(abo.api, ids[0], "2024-04-20"))
    m = rhythmus(x, "monatlich")
    assert ("bruch", "betrag", ids[2], ids[1]) in schritte(x) and m["laenge"] == 2 and not m["erfuellt"]
    assert x["serie"] is None or x["serie"]["rhythmus"] != "monatlich"
    _alle(abo, ids + extra, "2024-04-20")


def test_beispiel_6_mehrheitsregel(abo):
    e = abo.empfaenger("Verein (fiktiv)")
    ids = abo.buchen(e, ["2024-01-10", "2024-02-10", "2024-03-10"], -5000)
    andere = abo.buchen(e, ["2024-01-20", "2024-02-01", "2024-02-20", "2024-03-01"], [-1000, -2000, -3000, -9000])
    x = eintrag(pruefe_begruendung(abo.api, ids[0], "2024-03-20"))
    m = rhythmus(x, "monatlich")
    assert m["laenge"] == 3 and m["erfuellt"] is False and x["serie"] is None
    _alle(abo, ids + andere, "2024-03-20")
    filter_setzen(abo.api, e, modus="toleranz", toleranz_prozent=10)
    x = eintrag(pruefe_begruendung(abo.api, ids[0], "2024-03-20"))
    assert x["serie"]["buchung_ids"] == ids and x["betragsfilter"]["quelle"] == "empfaenger"
    _alle(abo, ids + andere, "2024-03-20")


def test_beispiel_7_mindestschwelle(abo):
    e = abo.empfaenger("Kunde (fiktiv)")
    ids = abo.buchen(e, ["2024-01-05", "2024-02-05", "2024-03-05", "2024-04-05"], 150000)
    klein = abo.buchen(e, ["2023-12-20", "2024-02-12", "2024-03-25"], [50000, 99999, 20000])
    filter_setzen(abo.api, e, modus="mindestschwelle", mindestbetrag=100000)
    a = pruefe_begruendung(abo.api, ids[0], "2024-04-10")
    assert all(_rollen(a)[b] == "anderer_betrag" for b in klein), "auch vor Kettenbeginn"
    assert eintrag(a)["serie"]["buchung_ids"] == ids
    _alle(abo, ids + klein, "2024-04-10")


def test_vorgaenger_passender_betrag_vor_abweichung(abo):
    """9.2.3: Wahl zuerst gleicher Betrag, dann Betrag passt, erst dann geringste Abweichung vom Termin."""
    e = abo.empfaenger("Lieferdienst (fiktiv)")
    ids = abo.buchen(e, ["2024-01-15", "2024-02-12", "2024-02-15", "2024-03-15"], [-1000, -1000, -3000, -1050])
    x = eintrag(pruefe_begruendung(abo.api, ids[0], "2024-03-20"))
    assert ("verbunden", None, ids[3], ids[1]) in schritte(x), "12.02. passt (±10 %), 15.02. liegt näher, passt nicht"
    assert x["serie"]["buchung_ids"] == [ids[0], ids[1], ids[3]]
    _alle(abo, ids, "2024-03-20")


# ------------------------------------------------------------------ Felder und Texte (9.3.5)
def test_felder_und_texte(abo):
    e = abo.empfaenger("Arbeitgeber Beispiel (fiktiv)")
    ids = abo.buchen(e, ["2024-01-28", "2024-02-28", "2024-03-28"], 250000)
    a = pruefe_begruendung(abo.api, ids[0], "2024-04-10")
    assert a["empfaenger"] == {"id": e, "name": "Arbeitgeber Beispiel (fiktiv)"}
    x = eintrag(a)
    assert x["betragsfilter"] == {"modus": "toleranz", "toleranz_prozent": 10, "mindestbetrag": None,
                                  "quelle": "vorgabe"}
    assert filter_text(x["betragsfilter"]) == "Betragsfilter: Toleranz ±10 % (Vorgabe)"
    filter_setzen(abo.api, e, modus="mindestschwelle", mindestbetrag=250000)
    x = eintrag(pruefe_begruendung(abo.api, ids[0], "2024-04-10"))
    assert filter_text(x["betragsfilter"]) == "Betragsfilter: nur Beträge ab 2.500,00 € (Einstellung des Empfängers)"
    filter_loeschen(abo.api, e)
    vorgabe(abo.api, "aus")
    x = eintrag(pruefe_begruendung(abo.api, ids[0], "2024-04-10"))
    assert filter_text(x["betragsfilter"]) == "Betragsfilter: aus (Vorgabe)"
    ohne = abo.api.buchung("2024-03-01", [(abo.giro, -500), (abo.kat, 500)])["id"]
    a = abo.api.get(f"/api/buchungen/{ohne}/wiederkehrend", params={"stichtag": "2024-04-10"}, erwartet=200).daten
    assert a["empfaenger"] is None and a["urteil"] == "ausgeschlossen"


def test_vorgabe_wirkt_sofort(abo):
    e = abo.empfaenger("Verein (fiktiv)")
    ids = abo.buchen(e, ["2024-01-10", "2024-02-10", "2024-03-10"], -5000)
    andere = abo.buchen(e, ["2024-01-20", "2024-02-01", "2024-02-20", "2024-03-01"], [-1000, -2000, -3000, -9000])
    assert uebersicht_ist(abo.api, "2024-03-20")["serien"] == []
    vorgabe(abo.api, "toleranz", 0)
    _alle(abo, ids + andere, "2024-03-20")
    vorgabe(abo.api, "aus")
    _alle(abo, ids + andere, "2024-03-20")


# ------------------------------------------------------------------ Zufallsgruppen je Modus
MODI = {"vorgabe_toleranz": None, "vorgabe_aus": None, "toleranz_20": {"modus": "toleranz", "toleranz_prozent": 20},
        "toleranz_0": {"modus": "toleranz", "toleranz_prozent": 0},
        "schwelle": {"modus": "mindestschwelle", "mindestbetrag": 5000}, "eigen_aus": {"modus": "aus"}}


def _zufallsgruppe(rnd: random.Random) -> list[tuple[str, int]]:
    m = rnd.choice([1, 1, 1, 3, 12])
    start = dt.date(2022, rnd.randint(1, 12), rnd.randint(1, 28))
    basis = rnd.choice([-999, -5000, -32032, 250000])
    aus = []
    for k in range(rnd.randint(2, 8)):
        d = wo.monat_plus(start, k * m) + dt.timedelta(days=rnd.randint(-4, 4))
        if rnd.random() < 0.85:
            aus.append((d.isoformat(), basis if rnd.random() < 0.75 else int(basis * rnd.choice([1.05, 1.3, 0.5]))))
        if rnd.random() < 0.45:
            x = rnd.choice([basis, 100, 3740, 11200, abs(basis) // 2])
            aus.append(((d + dt.timedelta(days=rnd.randint(-25, 25))).isoformat(), abs(x) if basis > 0 else -abs(x)))
    return sorted(aus)


@pytest.mark.parametrize("modus", list(MODI))
@pytest.mark.parametrize("saat", [1, 2, 3])
def test_zufallsgruppen_gleich_referenz(tmp_path, modus, saat):
    abo = Abo(neue_api(tmp_path))
    if modus == "vorgabe_aus":
        vorgabe(abo.api, "aus")
    rnd = random.Random(f"m25-{modus}-{saat}")
    ids = []
    for _ in range(4):
        gruppe = _zufallsgruppe(rnd)
        if not gruppe:
            continue
        e = abo.empfaenger()
        ids += abo.buchen(e, [t for t, _ in gruppe], [b for _, b in gruppe])
        if MODI[modus]:
            filter_setzen(abo.api, e, **MODI[modus])
    for stichtag in ("2023-06-30", "2025-06-30"):
        _alle(abo, [b for b in ids if abo.api.buchung_lesen(b)["datum"] <= stichtag], stichtag)


# ------------------------------------------------------------------ Ereignisse (9.2.7)
def _pruefen(api, ids) -> list[str]:
    r = api.post("/api/wiederkehrend/pruefen", json={"buchung_ids": ids}, erwartet=200).daten
    return [b["schluessel"] for b in r["benachrichtigungen"]]


def test_ereignisse_mit_filter(tmp_path):
    abo = Abo(neue_api(tmp_path, mock_modus=True, mock_heute=dt.date(2024, 5, 20)))
    e = abo.empfaenger("Kunde (fiktiv)")
    hist = abo.buchen(e, ["2024-01-05", "2024-02-05", "2024-03-05"], 150000)
    filter_setzen(abo.api, e, modus="mindestschwelle", mindestbetrag=100000)
    (klein,) = abo.buchen(e, ["2024-04-05"], 50000)
    assert not [s for s in _pruefen(abo.api, [klein]) if s.startswith("wiederkehrend_betrag")], \
        "unter der Mindestschwelle nie eine Meldung"
    t = abo.empfaenger("Streaming (fiktiv)")
    abo.buchen(t, ["2024-01-15", "2024-02-15", "2024-03-15"], -999)
    (teuer,) = abo.buchen(t, ["2024-04-15"], -1999)
    assert f"wiederkehrend_betrag:{teuer}" in _pruefen(abo.api, [teuer]), "am Termin, außerhalb der Toleranz"
    assert hist
