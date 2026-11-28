"""Core-Tests zum Feature benutzer (D-324): Die Personen des Haushalts stehen in der Konfiguration
(``KONTOR_BENUTZER``), nicht mehr fest im Code."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig
from kontor.fehler import KonfigurationsFehler


def _env(tmp_path: Path, **zusatz: str) -> dict[str, str]:
    return {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), **zusatz}


@pytest.mark.parametrize(("wert", "soll"), [
    ("Torsten,Tina", ("Torsten", "Tina")),
    (" Anna , Ben ,Clara ", ("Anna", "Ben", "Clara")),
    ("Jörg", ("Jörg",)),
    ("Anna-Lena,Ole", ("Anna-Lena", "Ole")),
    ("Mari Ann,Bo", ("Mari Ann", "Bo")),
    ("", ()),
])
def test_benutzer_aus_der_umgebung(tmp_path, wert, soll):
    assert KontorConfig.from_env(_env(tmp_path, KONTOR_BENUTZER=wert)).benutzer == soll


def test_ohne_angabe_keine_benutzer(tmp_path):
    assert KontorConfig.from_env(_env(tmp_path)).benutzer == ()
    assert KontorConfig(datenbank=tmp_path / "k.sqlite3").benutzer == ()


@pytest.mark.parametrize("wert", [
    "Anna,anna",          # doppelt (ohne Groß-/Kleinschreibung)
    "Anna,,Ben",          # leerer Eintrag
    "Anna,Ben,",          # leerer Eintrag am Ende
    "Anna;Ben",           # Satzzeichen im Namen
    "1Anna",              # beginnt nicht mit einem Buchstaben
    "Anna<b>",            # Zeichen, die nie in einen Namen gehören
    "A" * 41,             # zu lang
    ",".join(f"P{chr(97 + i // 26)}{chr(97 + i % 26)}" for i in range(21)),   # mehr als 20
])
def test_ungueltige_benutzer_sind_ein_konfigurationsfehler(tmp_path, wert):
    with pytest.raises(KonfigurationsFehler) as f:
        KontorConfig.from_env(_env(tmp_path, KONTOR_BENUTZER=wert))
    assert f.value.details.get("variable") == "KONTOR_BENUTZER"


def test_benutzer_direkt_in_der_config(tmp_path):
    c = KontorConfig(datenbank=tmp_path / "k.sqlite3", benutzer=["Anna", "Ben"])
    assert c.benutzer == ("Anna", "Ben")
    with pytest.raises(KonfigurationsFehler):
        KontorConfig(datenbank=tmp_path / "k.sqlite3", benutzer=("Anna", "ANNA"))


@pytest.mark.parametrize("liste", [[], ["Anna"], ["Torsten", "Tina"], ["Anna", "Ben", "Clara", "Dora"]])
def test_rest_liefert_die_benutzer(tmp_path, liste):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", benutzer=liste)))
    r = c.get("/api/benutzer")
    assert r.status_code == 200
    assert r.json() == {"benutzer": liste}


def test_konfiguration_zeigt_die_benutzer(tmp_path):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", benutzer=["Anna", "Ben"])))
    eintrag = next(e for e in c.get("/api/konfiguration").json()["wirksam"] if e["name"] == "benutzer")
    assert eintrag["variable"] == "KONTOR_BENUTZER"
    assert eintrag["wert"] == ["Anna", "Ben"] and eintrag["vorgabe"] == [] and eintrag["geaendert"] is True


def test_bestaetigungs_tag_eines_neuen_benutzers_ist_ein_gewoehnliches_tag(tmp_path):
    """Die Bestätigung ist REST-seitig ein gewöhnliches Tag „<Name>-Bestätigt“ (D-262); für beliebige Namen."""
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", benutzer=["Jörg", "Anna-Lena"])))
    for name in ("Jörg", "Anna-Lena"):
        r = c.post("/api/tags", json={"name": f"{name}-Bestätigt"})
        assert r.status_code == 201, r.text


def test_neustart_mit_anderen_benutzern_laesst_tags_stehen(tmp_path):
    """Wer aus der Konfiguration verschwindet, behält seine Bestätigungs-Tags (gewöhnliche Tags)."""
    pfad = tmp_path / "k.sqlite3"
    c = TestClient(create_app(KontorConfig(datenbank=pfad, benutzer=["Anna", "Ben"])))
    c.post("/api/tags", json={"name": "Anna-Bestätigt"})
    c.post("/api/tags", json={"name": "Ben-Bestätigt"})
    c = TestClient(create_app(KontorConfig(datenbank=pfad, benutzer=["Clara"])))
    assert sorted(t["name"] for t in c.get("/api/tags").json()) == ["Anna-Bestätigt", "Ben-Bestätigt"]
    assert c.get("/api/benutzer").json() == {"benutzer": ["Clara"]}


def test_ausgelieferte_umgebungsdatei_nennt_die_variable():
    from importlib import resources
    text = (resources.files("kontor") / "betrieb" / "kontor.env").read_text(encoding="utf-8")
    assert re.search(r"^#\s*KONTOR_BENUTZER=", text, re.M), "auskommentierte Vorlage der Variablen"
    assert not re.search(r"^KONTOR_BENUTZER=", text, re.M), "keine Namen ausliefern"


def test_oberflaeche_kennt_keine_festen_namen(auslieferung):
    """Weder Module noch Stile enthalten die früheren festen Namen; die Oberfläche liest die Liste vom Server."""
    for pfad in ("/oeffentlich/app/kern.js", "/oeffentlich/app/haupt.js", "/oeffentlich/app/konto.js",
                 "/oeffentlich/app/seiten.js", "/oeffentlich/app.css"):
        text = auslieferung.get(pfad).text
        assert "Torsten" not in text and "Tina" not in text, pfad
    assert "/api/benutzer" in auslieferung.get("/oeffentlich/app/kern.js").text
