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


@pytest.mark.skipif(not NODE, reason="node nicht installiert")
def test_ausgeschriebene_schluessel_paypal_amazon():
    amazon, beitrag, paypal = zerlegen([
        "LASTSCHRIFT / BELASTUNG302-xxxxxxxx-1234567 AMZN MKTP DE 9ABCDEFGH1234XYZEND-TO-END-REF.:9ABCDEFGH1234XYZ"
        "CORE / MANDATSREF.:Q+B-ZZ9Y)ABCD,EF1GH2IJKL-M34NGLÄUBIGER-ID:DE00ZZZ00000000001Ref. 0A1B2C3D4E5F6G7H/2001",
        "LASTSCHRIFT / BELASTUNGMITGLIEDSBEITRAGEND-TO-END-REF.:NOTPROVIDED / MANDATSREF.:M-0001GLÄUBIGER-ID:"
        "DE00ZZZ00000000002Ref. 1B2C3D4E5F6G7H8J/90001",
        "LASTSCHRIFT / BELASTUNG1000xxxxxxx0001/PP.1xxx7.PP/. BEISPIEL-VERLAG GMBH, IHR EINKAUF BEI BEISPIEL-VERLAG GMBH"
        "END-TO-END-REF.:xxxxxxxx / MANDATSREF.:4AB0000CDEFGHGLÄUBIGER-ID:"])
    assert amazon["texte"] == ["AMZN MKTP DE"]   # Ende-zu-Ende-Referenz nicht doppelt
    assert [(a["name"], a["wert"]) for a in amazon["angaben"]] == [
        ("Bestellnummer", "302-xxxxxxxx-1234567"), ("Ende-zu-Ende-Referenz", "9ABCDEFGH1234XYZ"),
        ("Mandatsreferenz", "Q+B-ZZ9Y)ABCD,EF1GH2IJKL-M34N"), ("Gläubiger-ID", "DE00ZZZ00000000001"),
        ("Referenz", "0A1B2C3D4E5F6G7H/2001"), ("Lastschriftverfahren", "Basislastschrift (CORE)")]
    assert beitrag["texte"] == ["MITGLIEDSBEITRAG"]
    assert [a["name"] for a in beitrag["angaben"]] == ["Mandatsreferenz", "Gläubiger-ID", "Referenz"]
    assert paypal["arten"] == ["Lastschrift / Belastung", "PayPal"]
    assert paypal["texte"] == ["Einkauf bei BEISPIEL-VERLAG GMBH"]
    assert [a["name"] for a in paypal["angaben"]] == ["PayPal-Referenz", "Ende-zu-Ende-Referenz", "Mandatsreferenz"]
