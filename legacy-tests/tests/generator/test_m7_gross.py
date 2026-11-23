"""M7: großer Datensatz für Leistungstests (leistung.md 1, E-134) – reproduzierbar, Probewerte unabhängig geprüft."""

from __future__ import annotations

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter

import pytest

from generator import STARTWERT
from generator.__main__ import gross_dateien
from tests.hilfen.pfade import FIXTURES

pytestmark = [pytest.mark.m7, pytest.mark.langsam]


@pytest.fixture(scope="module")
def gross():
    return gross_dateien(STARTWERT)


def test_reproduzierbar_und_im_manifest(gross):
    assert gross == gross_dateien(STARTWERT)
    m = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))["auf_abruf"]
    assert set(m) == {"gross/gross.kmy", "gross/gross.erwartung.json"}
    for name, inhalt in gross.items():
        if inhalt[:2] == b"\x1f\x8b":
            assert hashlib.sha256(gzip.decompress(inhalt)).hexdigest() == m[name]["sha256_entpackt"], name
        else:
            assert hashlib.sha256(inhalt).hexdigest() == m[name]["sha256"], name


def test_nicht_eingecheckt():
    ignoriert = (FIXTURES.parent / ".gitignore").read_text(encoding="utf-8").split()
    assert "fixtures/gross/" in ignoriert


def test_probewerte_aus_der_datei(gross):
    """Zählt unabhängig im KMyMoney-XML nach (ohne die Erwartungsberechnung des Generators)."""
    erw = json.loads(gross["gross/gross.erwartung.json"])
    wurzel = ET.fromstring(gzip.decompress(gross["gross/gross.kmy"]))
    trx = wurzel.findall("./TRANSACTIONS/TRANSACTION")
    assert len(trx) == erw["anzahl"]["buchungen"] == 50_000
    payees = {p.get("id"): p.get("name") for p in wurzel.findall("./PAYEES/PAYEE")}
    assert len(payees) == 400
    konten = {a.get("id"): a for a in wurzel.findall("./ACCOUNTS/ACCOUNT")}
    name_von = {k: a.get("name") for k, a in konten.items()}
    giro = next(k for k, n in name_von.items() if n == "Girokonto Haushalt")
    probe = next(k for k, n in payees.items() if n == erw["proben"]["empfaenger"]["name"])

    def splits(t):
        return t.findall("./SPLITS/SPLIT")

    jahre = Counter(t.get("postdate")[:4] for t in trx)
    assert dict(sorted(jahre.items())) == erw["jahre"]
    assert sum(1 for t in trx if "ZEBRA4711" in (t.get("memo") or "")) == erw["proben"]["zebra"]["anzahl"] == 250
    assert sum(1 for t in trx if any(s.get("payee") == probe for s in splits(t))) == 500
    assert erw["proben"]["empfaenger"]["anzahl"] == 500
    assert sum(1 for t in trx if any(s.get("account") == giro for s in splits(t))) == erw["proben"]["konto"]["anzahl"]
    assert erw["proben"]["zeitraum"]["anzahl"] == jahre["2023"]
    # ausgeglichen, mindestens zwei Splits, ganze Cent
    for t in trx:
        werte = [s.get("value") for s in splits(t)]
        assert len(werte) >= 2 and all(w.endswith("/100") for w in werte)
        assert sum(int(w.split("/")[0]) for w in werte) == 0
    assert 0.03 <= sum(1 for t in trx if len(splits(t)) >= 3) / len(trx) <= 0.04
    kategorien = [a for k, a in konten.items() if a.get("type") in ("12", "13") and not k.startswith("AStd")]
    assert len(kategorien) == 60 and len(wurzel.findall("./TAGS/TAG")) == 12
    # nur fiktive IBANs (BLZ 00000000)
    for a in konten.values():
        for kv in a.findall("./KEYVALUEPAIRS/PAIR"):
            if kv.get("key") == "iban":
                assert kv.get("value")[4:12] == "00000000"
