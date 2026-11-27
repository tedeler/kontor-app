"""Core-Tests zum Feature „teilen-format“ (D-306): Der Kurztext von „Teilen…“ (D-304) ist für WhatsApp gesetzt –
Empfänger und Betrag fett, Datum/Konto/Kategorie/Tags je eine Zeile mit Symbol, Verwendungszweck als Zitat (nur der
lesbare Teil), zuletzt allein der Link. Geprüft über die reine Funktion `teilenText` in `app/teilen.js` (Node)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

TEILEN = Path(__file__).resolve().parents[2] / "src/kontor/web/oeffentlich/app/teilen.js"
NODE = shutil.which("node")
LINK = "https://kontor.example.invalid/konten/12?buchung=345"

pytestmark = pytest.mark.skipif(not NODE, reason="node nicht installiert")


def texte(faelle):
    skript = (f"import('{TEILEN.as_uri()}').then(m => console.log(JSON.stringify("
              f"{json.dumps(faelle)}.map(a => m.teilenText(a)))))")
    aus = subprocess.run([NODE, "--input-type=module", "-e", skript], capture_output=True, text=True, check=True)
    return json.loads(aus.stdout)


def grund(**k):
    a = {"empfaenger": "Markt Beispiel (fiktiv)", "betrag": -2340, "art": "ausgabe", "datum": "2026-11-14",
         "konto": "Girokonto", "kategorie": "Lebensmittel:Supermarkt", "tags": [], "zweck": "Einkauf Woche 46",
         "link": LINK}
    a.update(k)
    return a


def test_aufbau():
    (t,) = texte([grund(tags=["Urlaub", "B-Tina"])])
    assert t.split("\n") == [
        "*Markt Beispiel (fiktiv)*",
        "*−23,40 €* · Ausgabe",
        "",
        "📅 Sa, 14.11.2026",
        "🏦 Girokonto",
        "🏷️ Lebensmittel:Supermarkt",
        "🔖 Urlaub, B-Tina",
        "",
        "> Einkauf Woche 46",
        "",
        LINK,
    ]


def test_einnahme_umbuchung_und_fehlende_angaben():
    ein, um, leer = texte([
        grund(betrag=123456, art="einnahme", zweck=""),
        grund(betrag=-50000, art="umbuchung", kategorie="Umbuchung → Tagesgeld", zweck="   "),
        grund(empfaenger="", kategorie="", zweck=None)])
    assert ein.split("\n")[:2] == ["*Markt Beispiel (fiktiv)*", "*+1.234,56 €* · Einnahme"]
    assert ">" not in ein and ein.endswith("🏷️ Lebensmittel:Supermarkt\n\n" + LINK)
    assert um.split("\n")[1] == "*−500,00 €* · Umbuchung"
    assert "🏷️ Umbuchung → Tagesgeld" in um and ">" not in um
    zeilen = leer.split("\n")
    assert zeilen[0] == "*Buchung*" and not any(z.startswith("🏷️") for z in zeilen) and "🔖" not in leer
    assert zeilen[-1] == LINK and zeilen[-2] == ""


def test_zweck_nur_lesbar_und_gekuerzt():
    sepa, lang, gleich = texte([
        grund(zweck="EREF+ZV0001 MREF+MB-0815 CRED+DE00ZZZ00000000000 SVWZ+Rechnung 2026-11 Mobilfunk"),
        grund(zweck="Wort " * 60),
        grund(zweck="markt beispiel (FIKTIV)")])
    assert "> Rechnung 2026-11 Mobilfunk" in sepa.split("\n")
    assert "EREF" not in sepa and "MB-0815" not in sepa and "DE00ZZZ" not in sepa
    z = next(x for x in lang.split("\n") if x.startswith("> "))
    assert len(z) - 2 <= 140 and z.endswith("…")
    assert ">" not in gleich   # Zweck wiederholt nur den Empfänger


def test_auszeichnung_im_text_bleibt_wirkungslos():
    """Sternchen, Unterstriche, Tilden und Backticks aus dem Buchbestand dürfen die Formatierung nicht stören."""
    (t,) = texte([grund(empfaenger="*Sale* ~50%~", kategorie="A_b_c", zweck="REF_12_AB `x`", tags=["*neu*"])])
    zeilen = t.split("\n")
    kopf = zeilen[0]
    assert kopf.startswith("*") and kopf.endswith("*") and kopf.count("*") == 2
    for z in zeilen[2:]:
        if z == LINK:
            continue
        assert not any(c in z for c in "*_~`"), z
    assert zeilen[-1] == LINK


def test_kontoblatt_nutzt_das_modul():
    js = (TEILEN.parent / "konto.js").read_text(encoding="utf-8")
    assert 'from "./teilen.js"' in js
    sw = (TEILEN.parents[2] / "sw.js").read_text(encoding="utf-8")
    assert '"/oeffentlich/app/teilen.js"' in sw
