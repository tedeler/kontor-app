"""Eigene Tests: Zerlegung des Verwendungszwecks für die Anzeige (D-175, app/zweck.js) über Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ZWECK = Path(__file__).resolve().parents[1] / "src/kontor/web/oeffentlich/app/zweck.js"
NODE = shutil.which("node")


def zerlegen(texte):
    skript = (f"import('{ZWECK.as_uri()}').then(m => console.log(JSON.stringify("
              f"{json.dumps(texte)}.map(t => m.zweckZerlegen(t)))))")
    aus = subprocess.run([NODE, "--input-type=module", "-e", skript], capture_output=True, text=True, check=True)
    return json.loads(aus.stdout)


@pytest.mark.skipif(not NODE, reason="node nicht installiert")
def test_zerlegung():
    karte, sepa, schlicht, leer, html = zerlegen([
        "LASTSCHRIFT / BELASTUNGCAFE AM MARKT, MUSTERSTADT DEKARTE NR. 1234 56XX XXXX 0000KARTENZAHLUNG"
        "MUSTERBANK VISA-DEBITKARTE2026-11-11 14:05:00Ref. 9Z8Y7X6W5V4U3T2S/10001",
        "EREF+ZV0001 MREF+MB-0815 CRED+DE00ZZZ00000000000 SVWZ+Rechnung 2026-11 Mobilfunk",
        "Abschlag Strom Kundennummer 4711 01/2024", "", "<b>Lastschriften</b>  Mai"])
    assert karte["arten"] == ["Lastschrift / Belastung", "Kartenzahlung"]
    assert karte["texte"] == ["CAFE AM MARKT, MUSTERSTADT DE"]
    werte = {a["art"]: a["wert"] for a in karte["angaben"]}
    assert werte == {"karte": "1234 56XX XXXX 0000", "kartenart": "MUSTERBANK VISA-DEBITKARTE",
                     "zeitpunkt": "11.11.2026, 14:05 Uhr", "referenz": "9Z8Y7X6W5V4U3T2S/10001"}
    assert sepa["texte"] == ["Rechnung 2026-11 Mobilfunk"]
    assert [(a["name"], a["wert"]) for a in sepa["angaben"]] == [
        ("Ende-zu-Ende-Referenz", "ZV0001"), ("Mandatsreferenz", "MB-0815"), ("Gläubiger-ID", "DE00ZZZ00000000000")]
    assert schlicht == {"arten": [], "texte": ["Abschlag Strom Kundennummer 4711 01/2024"], "angaben": [], "erkannt": False}
    assert leer["texte"] == [] and not leer["erkannt"]
    assert html["texte"] == ["<b>Lastschriften</b> Mai"] and not html["erkannt"]
