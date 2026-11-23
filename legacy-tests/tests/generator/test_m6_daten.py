"""M6-Testdaten: FinTS-Attrappe, Postfächer, Benachrichtigungen (ohne App).

Prüft die bekannte Wahrheit des Generators gegen die unabhängigen Orakel in ``tests/hilfen/m6_orakel.py``
(Abbildung nach ``fints.md`` 3.4 und ``mail.md`` 3.3, Erinnerungen nach ``benachrichtigungen.md`` 5) und die
Regeln für synthetische Daten (BLZ 00000000, Adressen unter example.invalid, offensichtlich künstliche Werte).
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import re
import struct
import xml.etree.ElementTree as ET
import zlib

import pytest

from generator.iban import ist_gueltig
from tests.hilfen import m6_orakel as orakel
from tests.hilfen.pfade import FIXTURES, MOCK

pytestmark = pytest.mark.m6
UTC = dt.timezone.utc


def lade(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bank():
    return lade("m6/fints_bank.json"), lade("m6/fints_bank.erwartung.json")


def test_bank_synthetisch(bank):
    daten, erw = bank
    assert daten["format"] == "kontor-fints-attrappe" and daten["version"] == 1
    assert daten["blz"] == "00000000"
    for k in daten["konten"]:
        assert ist_gueltig(k["iban"]) and k["iban"][4:12] == "00000000"
    assert "SYNTH" in daten["pin"] and daten["tan"].isdigit()
    assert erw["konten"] and {k["iban"] for k in erw["konten"]}.isdisjoint(erw["nicht_geliefert"])
    assert [k["iban"] for k in erw["konten"]] == sorted(k["iban"] for k in erw["konten"])


def test_qr_png_gueltig_und_gross_genug(bank):
    daten, erw = bank
    png = base64.b64decode(daten["qr_png"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR"
    assert hashlib.sha256(png).hexdigest() == erw["qr_sha256"]
    # python-fints deutet challenge_hhduc erst ab 256 Bytes als Matrix-Code
    assert 256 < len(png) + 13 < 65536
    breite, hoehe = struct.unpack(">II", png[16:24])
    pos, idat = 8, b""
    while pos < len(png):
        laenge = struct.unpack(">I", png[pos:pos + 4])[0]
        typ = png[pos + 4:pos + 8]
        if typ == b"IDAT":
            idat += png[pos + 8:pos + 8 + laenge]
        assert zlib.crc32(png[pos + 4:pos + 8 + laenge]) & 0xFFFFFFFF == struct.unpack(
            ">I", png[pos + 8 + laenge:pos + 12 + laenge])[0]
        pos += 12 + laenge
    assert len(zlib.decompress(idat)) == hoehe * (breite + 1)


def test_mt940_bruchstuecke_gleich_wahrheit(bank):
    daten, erw = bank
    for u, w in zip(daten["umsaetze"], erw["umsaetze"], strict=True):
        if not u["mt940"]:
            assert w["mt940"] is None
            continue
        for zeile in u["mt940"].split("\n"):
            assert len(zeile) <= 65 and not zeile.startswith("-")
        u["mt940"].encode("iso-8859-1")
        ist = orakel.mt940_umsaetze(u["iban"], u["mt940"])[0]
        soll = dict(w["mt940"])
        assert soll.pop("umsatz_id").startswith("h:")
        ist.pop("umsatz_id")
        assert ist == soll


def test_camt_bruchstuecke_gleich_wahrheit(bank):
    daten, erw = bank
    for u, w in zip(daten["umsaetze"], erw["umsaetze"], strict=True):
        e = ET.fromstring(u["camt"])
        ist = orakel.camt_ntry(u["iban"], e)
        if w["camt"] is None:
            assert ist is None
            continue
        soll = dict(w["camt"])
        if ist["umsatz_id"] is None:
            assert soll["umsatz_id"].startswith("h:")
            soll["umsatz_id"] = None
        assert ist == soll


@pytest.mark.parametrize("profil", ["camt", "mt940"])
def test_hash_kennungen_eindeutig_und_nummeriert(bank, profil):
    _, erw = bank
    je_konto: dict[str, list[str]] = {}
    for w in erw["umsaetze"]:
        if w[profil]:
            je_konto.setdefault(w["iban"], []).append(w[profil]["umsatz_id"])
    for ids in je_konto.values():
        assert len(ids) == len(set(ids))
    hashe = [i for ids in je_konto.values() for i in ids if i.startswith("h:")]
    assert any(i.endswith(":2") for i in hashe), "zwei gleiche Umsätze am selben Tag erwartet"
    for w in erw["umsaetze"]:
        u = w[profil]
        if u and u["umsatz_id"].startswith("h:"):
            assert u["umsatz_id"].rsplit(":", 1)[0] == orakel.hash_kennung(u, 0).rsplit(":", 1)[0]


def test_stoerfaelle_vorhanden(bank):
    _, erw = bank
    camt = [w["camt"] for w in erw["umsaetze"] if w["camt"]]
    mt = [w["mt940"] for w in erw["umsaetze"] if w["mt940"]]
    assert {(u["storno"], u["betrag"] > 0) for u in mt if u["storno"]} == {(True, True), (True, False)}
    assert any(u["vormerkung"] for u in camt) and not any(u["vormerkung"] for u in mt)
    assert any(u["valuta"] is None for u in camt)
    assert any(u["buchungstag"] != u["valuta"] for u in mt)
    assert any(u["buchungstag"].startswith("2023") and u["valuta"].startswith("2024") for u in mt)
    assert any(u["gegenpartei_name"] is None for u in mt) and any(len(u["verwendungszweck"]) > 100 for u in mt)
    assert any(len(u["gegenpartei_name"] or "") > 27 for u in mt)
    assert any(re.search("[äöüß]", u["verwendungszweck"] + (u["gegenpartei_name"] or "")) for u in mt)
    daten, _ = bank
    fremd = [u for u in daten["umsaetze"] if 'Ccy="USD"' in u["camt"]]
    assert fremd and all(not u["mt940"] for u in fremd)


def test_mock_vergleich_gleich_wahrheit(bank):
    _, erw = bank
    mock = json.loads((MOCK / "m6_fints_vergleich.json").read_text(encoding="utf-8"))
    assert mock["format"] == "kontor-mock-daten" and mock["version"] == 1
    assert mock["bank"]["konten"] == erw["konten"]
    gelieferte = {k["iban"] for k in erw["konten"]}
    soll = sorted((w["camt"] for w in erw["umsaetze"]
                   if w["camt"] and not w["vormerkung"] and w["iban"] in gelieferte),
                  key=lambda u: (u["iban"], u["buchungstag"], u["umsatz_id"]))
    assert mock["bank"]["umsaetze"] == soll
    assert mock["bank"]["pin"] == erw["pin"] and mock["bank"]["tan"] == erw["tan"]


# ---------------------------------------------------------------- Mail

@pytest.fixture(scope="module")
def mail():
    return lade("m6/mail/postfaecher.json"), lade("m6/mail.erwartung.json")


def test_mail_synthetisch(mail):
    index, erw = mail
    for adresse, ordner in index["postfaecher"].items():
        assert adresse.endswith("@example.invalid")
        for info in ordner.values():
            inhalt = (FIXTURES / "m6" / "mail" / info["datei"]).read_bytes()
            for zeit, roh in orakel.mbox_lesen(inhalt):
                for a in re.findall(rb"[\w.+-]+@[\w.-]+", roh):
                    assert a.split(b"@")[1] == b"example.invalid" or a.endswith(b".example.invalid"), a


def test_mails_gleich_wahrheit(mail):
    index, erw = mail
    for adresse, ordner in index["postfaecher"].items():
        for name, info in ordner.items():
            liste = orakel.mbox_lesen((FIXTURES / "m6" / "mail" / info["datei"]).read_bytes())
            assert len(liste) == len(info["uids"])
            ist, gesehen = [], set()
            for (zeit, roh), uid in zip(liste, info["uids"], strict=True):
                n = orakel.mail_nachricht(roh, adresse, zeit, info["uidvalidity"], uid)
                if n["nachricht_id"] in gesehen:
                    continue
                gesehen.add(n["nachricht_id"])
                ist.append(n)
            ist.sort(key=lambda n: (n["empfangen"], n["nachricht_id"]))
            soll = [{k: v for k, v in n.items() if k != "uid"} for n in erw["postfaecher"][adresse][name]["nachrichten"]]
            assert ist == soll, (adresse, name)


def test_mail_stoerfaelle(mail):
    index, erw = mail
    alle = [n for o in erw["postfaecher"].values() for v in o.values() for n in v["nachrichten"]]
    assert any(n["nachricht_id"].startswith("imap:") for n in alle)
    assert any("Bücherstube" in n["betreff"] and len(n["betreff"]) > 60 for n in alle)
    assert any("€" in n["text"] and "<" not in n["text"] for n in alle)
    assert any("nicht anzeigen" in n["betreff"] for n in alle) is False
    assert not any("nicht anzeigen" in n["text"] or "Anhang ist kein" in n["text"] for n in alle)
    assert any(n["absender"].startswith("newsletter@") for n in alle)
    roh = (FIXTURES / "m6" / "mail" / index["postfaecher"]["haushalt.eins@example.invalid"]["INBOX"]["datei"]).read_bytes()
    ids = re.findall(rb"(?m)^Message-ID: (.*)$", roh)
    assert len(ids) != len(set(ids)), "doppelte Message-ID erwartet"


def test_mail_mock_vergleich(mail):
    _, erw = mail
    mock = json.loads((MOCK / "m6_mail_vergleich.json").read_text(encoding="utf-8"))
    assert mock["mail"]["postfaecher"] == list(erw["vergleich_ordner"])
    soll = [{k: v for k, v in n.items() if k != "uid"}
            for adresse, ordner in erw["vergleich_ordner"].items()
            for n in erw["postfaecher"][adresse][ordner]["nachrichten"]]
    assert mock["mail"]["nachrichten"] == soll


def test_utf7_imap():
    assert orakel.utf7_imap("Bestellungen/Bücher") == "Bestellungen/B&APw-cher"
    assert orakel.utf7_imap("[Gmail]/Alle Nachrichten") == "[Gmail]/Alle Nachrichten"
    assert orakel.utf7_imap("A&B") == "A&-B"
    assert orakel.utf7_imap("台北") == "&U,BTFw-"     # Beispiel aus RFC 3501 5.1.3


# ---------------------------------------------------------------- Benachrichtigungen

def test_erinnerungen_gleich_orakel():
    erw = lade("m6/benachrichtigungen.erwartung.json")
    z = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    for f in erw["erinnerungen"]:
        ist = orakel.erinnerungen(z(f["erstellt"]), z(f["gueltig_bis"]), f["intervall"], f["anzahl"],
                                  [z(t) for t in f["takte"]])
        assert ist == f["erinnerungen"], f
    fest = erw["erinnerungen"][0]
    assert fest["erinnerungen"] == [[], [1], [], [3], [], []]


def test_ntfy_beispiele():
    erw = lade("m6/benachrichtigungen.erwartung.json")
    for b in erw["beispiele"]:
        k = b["ntfy_koerper"]
        assert set(k) <= {"topic", "title", "message", "priority", "tags", "click"}
        assert k["title"].startswith("[Mock] ") == b["mock_modus"]
        assert k["priority"] == erw["prioritaet"][b["art"]] and k["tags"] == [b["art"]]
        assert ("click" in k) == bool(b["oeffentliche_url"] and b["link"])
        if "click" in k:
            assert k["click"] == b["oeffentliche_url"].rstrip("/") + b["link"] and "//tan" not in k["click"]
