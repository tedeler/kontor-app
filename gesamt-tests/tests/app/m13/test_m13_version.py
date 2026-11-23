"""M13: Versionsnummer und ``GET /api/version`` (version.md 1, 3, 5; E-176 bis E-178) – ohne Browser.

Keine Versionsnummer ist fest eingetragen (E-176): geprüft werden das Schema 1.1 und die Gleichheit aller
Quellen 1.4. Erwartungen kommen aus der Konfiguration des Tests, dem laufenden Python und frisch erzeugten
Sicherungen.
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api, fehlercode, neue_api, neue_config
from tests.hilfen.m3 import aenderungen_seit, bestand, letzte_aenderung_id
from tests.hilfen.m7 import PASSWORT, anmelden, m7_api, sitzungstoken
from tests.hilfen.m9 import oeffne, sicherung
from tests.hilfen.m13 import COMMIT_MUSTER, FELDER, build_datum_gueltig, gleicher_pfad, knoepfe_in_huelle, \
    knopf_text_soll, repository_gueltig, version_gueltig

PFAD = "/api/version"
MODI = ["echt", "mock"]


def _api(tmp_path: Path, modus: str, **felder) -> Api:
    return neue_api(tmp_path / modus, mock_modus=(modus == "mock"), **felder)


def _version(api: Api, **kw) -> dict:
    return api.get(PFAD, erwartet=200, **kw).daten


def _daten(api: Api) -> None:
    """Etwas Buchbestand, damit „ohne Wirkung“ nicht trivial ist."""
    g = api.konto("Girokonto", "girokonto")["id"]
    k = api.konto("Lebensmittel", "aufwand")["id"]
    e = api.empfaenger("Bäckerei Version")["id"]
    api.buchung("2024-03-01", [(g, -1250), (k, 1250)], empfaenger_id=e, verwendungszweck="Brot")


# ------------------------------------------------------------------ 1.1, 1.4, 1.5


@pytest.mark.kern
def test_paketversion_im_schema():
    """version.md 1.1, 1.5: ``kontor.__version__`` ist MAJOR.MINOR (und damit PEP-440-gültig)."""
    v = kontor.modul("kontor").__version__
    assert version_gueltig(v), f"kontor.__version__ {v!r} entspricht nicht dem Schema MAJOR.MINOR (version.md 1.1)"


@pytest.mark.kern
@pytest.mark.parametrize("modus", MODI)
def test_eine_version_ueberall(tmp_path, modus):
    """version.md 1.4: Paket, /api/status, /api/gesundheit, /api/version, Hülle und app_version einer frisch
    erzeugten Sicherung nennen dieselbe Zeichenkette."""
    api = _api(tmp_path, modus)
    v = kontor.modul("kontor").__version__
    assert version_gueltig(v)
    assert api.get("/api/status", erwartet=200).daten["version"] == v
    assert api.get("/api/gesundheit", erwartet=200).daten["version"] == v
    assert _version(api)["version"] == v
    manifest, _ = oeffne(sicherung(api))
    assert manifest["app_version"] == v
    huelle = api.get("/").text
    knoepfe = knoepfe_in_huelle(huelle)
    assert len(knoepfe) == 1, f"Hülle: genau ein version-knopf erwartet, gefunden {len(knoepfe)} (oberflaeche.md 24.1)"
    assert knoepfe[0]["text"] == knopf_text_soll(huelle, v), "M31 (E-285): „Über“ nur auf einem Entwicklungsbranch"


@pytest.mark.kern
@pytest.mark.parametrize("modus", MODI)
def test_versionsknopf_in_der_huelle(tmp_path, modus):
    """oberflaeche.md 24.1: Die ausgelieferte Hülle enthält den Knopf (auch offline), auf jeder Route gleich."""
    api = _api(tmp_path, modus)
    v = kontor.modul("kontor").__version__
    for route in ("/", "/kategorien", "/einstellungen"):
        huelle = api.get(route).text
        knoepfe = knoepfe_in_huelle(huelle)
        assert len(knoepfe) == 1, route
        k = knoepfe[0]
        assert k["tag"] == "button", f"version-knopf ist <{k['tag']}> statt <button>"
        assert k["attrs"].get("aria-haspopup") == "dialog"
        assert k["text"] == knopf_text_soll(huelle, v)              # M31 (E-285)
        assert not k["attrs"]["data-testid"].startswith("nav-")


# ------------------------------------------------------------------ 3.2 Felder


@pytest.mark.kern
@pytest.mark.parametrize("modus", MODI)
def test_felder_und_typen(tmp_path, modus):
    """version.md 3.2 (E-178): alle Felder mit Typen und Bedeutung."""
    api = _api(tmp_path, modus)
    d = _version(api)
    assert FELDER <= set(d), f"fehlende Felder: {FELDER - set(d)}"
    assert d["name"] == "Kontor"
    assert version_gueltig(d["version"])
    assert type(d["entwicklungsstand"]) is bool
    if d["entwicklungsstand"]:
        assert d["commit"] is None and d["build_datum"] is None, "Entwicklungsstand: commit und build_datum null"
    else:
        assert isinstance(d["commit"], str) and COMMIT_MUSTER.fullmatch(d["commit"]), d["commit"]
        assert isinstance(d["build_datum"], str) and build_datum_gueltig(d["build_datum"]), d["build_datum"]
    assert d["python"] == platform.python_version()
    assert isinstance(d["repository"], str) and repository_gueltig(d["repository"]), d["repository"]
    status = api.get("/api/status", erwartet=200).daten
    assert d["modus"] == status["modus"] == modus
    assert isinstance(d["datenbank"], str) and gleicher_pfad(d["datenbank"], api.config.aktive_datenbank), (
        f"datenbank {d['datenbank']!r} ist nicht der absolute Pfad von {api.config.aktive_datenbank}")
    for feld in ("datenbank_schema", "sicherung_schema"):
        assert type(d[feld]) is int and d[feld] >= 1, (feld, d[feld])
    manifest, _ = oeffne(sicherung(api))
    assert d["sicherung_schema"] == manifest["schemaversion"]


@pytest.mark.kern
def test_mock_datenbank_ist_die_aktive(tmp_path):
    """version.md 3.2: im Mock-Modus die Mock-Datenbank (auch eine ausdrücklich gesetzte), nie die Echt-Datenbank."""
    eigene = tmp_path / "anderswo" / "eigene-mock.sqlite3"
    api = neue_api(tmp_path / "m", mock_modus=True, mock_datenbank=eigene)
    d = _version(api)
    assert gleicher_pfad(d["datenbank"], eigene)
    assert not gleicher_pfad(d["datenbank"], api.config.datenbank)


@pytest.mark.kern
@pytest.mark.parametrize("modus", MODI)
def test_relativer_pfad_wird_absolut(tmp_path, monkeypatch, modus):
    """version.md 3.2 (E-178): absoluter Pfad, auch wenn die Konfiguration einen relativen nennt."""
    monkeypatch.chdir(tmp_path)
    config = neue_config(Path("relativ"), mock_modus=(modus == "mock"))
    erwartet = (tmp_path / config.aktive_datenbank).resolve()
    api = Api(config)
    d = _version(api)
    assert Path(d["datenbank"]).is_absolute(), d["datenbank"]
    assert Path(d["datenbank"]).resolve() == erwartet


@pytest.mark.kern
def test_entwicklungsstand_folgt_den_build_angaben(tmp_path):
    """version.md 3.2: entwicklungsstand ⇔ commit und build_datum null; die Angaben sind je App beständig."""
    a = _version(_api(tmp_path, "echt"))
    b = _version(_api(tmp_path, "mock"))
    for d in (a, b):
        assert d["entwicklungsstand"] is (d["commit"] is None) is (d["build_datum"] is None)
    for feld in ("name", "version", "commit", "build_datum", "entwicklungsstand", "python", "repository"):
        assert a[feld] == b[feld], f"{feld} hängt nicht vom Modus ab"


@pytest.mark.kern
def test_schemaversionen_folgen_der_sicherung_in_beiden_modi(tmp_path):
    """version.md 3.2: sicherung_schema = schemaversion einer frischen Sicherung, auch mit Buchbestand."""
    for modus in MODI:
        api = _api(tmp_path, modus)
        _daten(api)
        d = _version(api)
        manifest, _ = oeffne(sicherung(api))
        assert manifest["schemaversion"] == d["sicherung_schema"], modus
        assert _version(api)["datenbank_schema"] == d["datenbank_schema"]


# ------------------------------------------------------------------ 3.1 Methoden, Abfrage, Schutz


@pytest.mark.kern
@pytest.mark.parametrize("methode", ["POST", "PUT", "PATCH", "DELETE"])
def test_andere_methoden_405(api, methode):
    r = api.anfrage(methode, PFAD, erwartet=405)
    assert fehlercode(r) == "methode_nicht_erlaubt"


@pytest.mark.kern
def test_query_parameter_ohne_wirkung(api):
    """version.md 3.1: Query-Parameter haben keine Wirkung (auch kein 422)."""
    ohne = _version(api)
    for params in ({"x": "1"}, {"version": "9.99", "modus": "mock"}, {"seite": "abc", "pro_seite": "-1"}):
        assert _version(api, params=params) == ohne, params


@pytest.mark.kern
def test_geschuetzt_bei_aktiver_anmeldung(tmp_path):
    """version.md 3.1, sicherheit.md 3.2: ohne Sitzung 401 für jede Methode; angemeldet 200."""
    api = m7_api(tmp_path)
    for methode in ("GET", "POST", "DELETE"):
        r = api.anfrage(methode, PFAD, erwartet=401)
        assert fehlercode(r) == "nicht_angemeldet"
        assert kontor.modul("kontor").__version__ not in r.text, "401 ohne Inhalt der Versionsangaben"
    assert api.get("/api/gesundheit", erwartet=200).daten["version"] == kontor.modul("kontor").__version__
    anmelden(api)
    d = _version(api)
    assert d["version"] == kontor.modul("kontor").__version__
    assert api.anfrage("POST", PFAD, erwartet=405) is not None


# ------------------------------------------------------------------ 3.3 Kein Zustand, keine Geheimnisse


@pytest.mark.kern
@pytest.mark.parametrize("modus", MODI)
def test_ohne_wirkung_und_ohne_protokoll(tmp_path, modus):
    """version.md 3.3: keine Änderung, kein Protokolleintrag, nichts in der Sicherung."""
    api = _api(tmp_path, modus)
    _daten(api)
    vor = letzte_aenderung_id(api)
    z = bestand(api)
    m_vor, _ = oeffne(sicherung(api))
    for _ in range(3):
        _version(api)
    assert aenderungen_seit(api, vor) == [], "GET /api/version darf keine Änderung im Protokoll erzeugen"
    assert bestand(api) == z
    m_nach, _ = oeffne(sicherung(api))
    assert m_nach["anzahl"] == m_vor["anzahl"]
    assert m_nach["inhalt_sha256"] == m_vor["inhalt_sha256"]


@pytest.mark.kern
def test_keine_geheimnisse(tmp_path):
    """version.md 3.3: kein Passwort, kein Sitzungs- oder CSRF-Token in der Antwort."""
    api = m7_api(tmp_path)
    anmelden(api)
    r = api.get(PFAD, erwartet=200)
    text = r.text
    assert PASSWORT not in text
    assert api.csrf and api.csrf not in text
    token = sitzungstoken(api)
    assert token and token not in text
    assert "@" not in r.daten["repository"].split("//", 1)[1].split("/", 1)[0]


# ------------------------------------------------------------------ 5 Abgrenzung


@pytest.mark.kern
@pytest.mark.parametrize("modus", MODI)
def test_gesundheit_unveraendert(tmp_path, modus):
    """version.md 5: /api/gesundheit bleibt öffentlich und hat genau status und version."""
    api = m7_api(tmp_path, mock_modus=(modus == "mock"))
    d = api.get("/api/gesundheit", erwartet=200).daten
    assert d == {"status": "ok", "version": kontor.modul("kontor").__version__}
