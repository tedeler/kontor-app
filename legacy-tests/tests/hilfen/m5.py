"""Hilfen für Meilenstein-5-Tests (Kredite, wiederkehrende Buchungen, Berichte, Export).

Nur über die Spezifikation (kredite.md, wiederkehrend.md, berichte.md, protokoll.md 11, sicherung.md 2.5,
openapi.yaml). Erwartungen kommen aus dem Generator (``fixtures/m5``, ``fixtures/mock/m5_*``) oder aus den
unabhängigen Orakeln ``kredit_orakel`` und ``wiederkehrend_orakel``.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from pathlib import Path

from .api import Api, fehlercode, neue_config
from .m3 import KORREKTUR, UNKATEGORISIERT, aenderungen_seit, letzte_aenderung_id
from .m4 import bestand as bestand_m4
from .pfade import FIXTURES, MOCK

M5 = FIXTURES / "m5"
KREDIT_MOCK = MOCK / "m5_kredit.json"
WIEDER_MOCK = MOCK / "m5_wiederkehrend.json"
OBJEKTE_M5 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage", "kredit"]
BESTAND = {"girokonto", "sparkonto", "kreditkonto"}
SPALTEN = ["buchung_id", "datum", "empfaenger", "verwendungszweck", "status", "kategorie", "tags", "extern_ids",
           "gegen_iban", "split_nr", "split_id", "konto_id", "konto", "betrag", "memo", "abstimmung_id"]
_ = (KORREKTUR, UNKATEGORISIERT)


def lade(pfad: Path) -> dict:
    return json.loads(Path(pfad).read_text(encoding="utf-8"))


def kreditfaelle() -> list[dict]:
    return lade(M5 / "kredite.json")["faelle"]


def lade_kredit_sync() -> tuple[dict, dict]:
    return lade(KREDIT_MOCK), lade(MOCK / "m5_kredit.erwartung.json")


def lade_wiederkehrend() -> tuple[dict, dict]:
    return lade(WIEDER_MOCK), lade(MOCK / "m5_wiederkehrend.erwartung.json")


def mock_api(basis: Path, daten: Path, heute: str, **felder) -> Api:
    return Api(neue_config(basis, mock_modus=True, mock_daten=daten, mock_heute=dt.date.fromisoformat(heute),
                           **felder))


def zeit(api: Api, heute: str) -> None:
    api.put("/api/mock/zeit", json={"jetzt": f"{heute}T12:00:00Z"}, erwartet=200)


def sync(api: Api, **body) -> dict:
    return api.post("/api/sync", json=body, erwartet=200).daten


def konto_nach_iban(api: Api) -> dict[str, int]:
    return {k["iban"]: k["id"] for k in api.konten() if k["iban"]}


def nach_kennung(api: Api) -> dict[str, dict]:
    """Buchungen nach umsatz_id (aus bank:-Kennungen)."""
    aus = {}
    for b in api.alle_buchungen():
        for e in b["extern_ids"]:
            if e.startswith("bank:"):
                aus[e.rsplit(":", 1)[1]] = b
    return aus


# ------------------------------------------------------------------ Bestand und Protokoll
def bestand(api: Api) -> dict[tuple[str, int], dict]:
    """Protokollierte Objekte inkl. Vorlagen und Kredite (protokoll.md 11.1)."""
    aus = bestand_m4(api)
    for k in api.get("/api/kredite", erwartet=200).daten:
        aus[("kredit", k["id"])] = k
    return aus


def sortierschluessel(e: dict) -> tuple[int, int]:
    return OBJEKTE_M5.index(e["objekt"]), e["objekt_id"]


def pruefe_eintraege(a: dict, vorher: dict, nachher: dict) -> None:
    """protokoll.md 3.2 mit Objekt kredit: genau ein Eintrag je geändertem Objekt, Nettowirkung, sortiert."""
    erwartet = {k: (vorher.get(k), nachher.get(k)) for k in set(vorher) | set(nachher)
                if vorher.get(k) != nachher.get(k)}
    ist = {(e["objekt"], e["objekt_id"]): e for e in a["eintraege"]}
    assert len(ist) == len(a["eintraege"]), f"Änderung {a['id']}: Objekt mehrfach eingetragen"
    assert set(ist) == set(erwartet), (
        f"Änderung {a['id']} ({a['aktion']}): Einträge {sorted(ist)} statt {sorted(erwartet)}")
    for k, (v, n) in erwartet.items():
        e = ist[k]
        assert e["art"] == ("angelegt" if v is None else "geloescht" if n is None else "geaendert"), k
        assert e["vorher"] == v, f"{k}: vorher weicht ab:\n{e['vorher']}\nerwartet\n{v}"
        assert e["nachher"] == n, f"{k}: nachher weicht ab:\n{e['nachher']}\nerwartet\n{n}"
    assert a["eintraege"] == sorted(a["eintraege"], key=sortierschluessel), "Einträge falsch sortiert"


def eine_aenderung(api: Api, a0: int, quelle: str, aktion: str) -> dict:
    neu = aenderungen_seit(api, a0)
    assert len(neu) == 1, f"genau eine Änderung erwartet, erhalten {[(x['quelle'], x['aktion']) for x in neu]}"
    (a,) = neu
    assert (a["quelle"], a["aktion"], a["gruppe"]) == (quelle, aktion, None), (a["quelle"], a["aktion"], a["gruppe"])
    return a


def rundreise(api: Api, a: dict, vorher: dict, nachher: dict) -> None:
    """Rückgängig stellt `vorher` exakt her, Wiederholen wieder `nachher` (T 3.6)."""
    u = api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200).daten
    assert (u["quelle"], u["aktion"], u["rueckgaengig_von"]) == ("rueckgaengig", "rueckgaengig", [a["id"]])
    assert bestand(api) == vorher, f"Rückgängig von {a['aktion']} stellt den Zustand nicht exakt her"
    pruefe_eintraege(u, nachher, vorher)
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == nachher, f"Wiederholen von {a['aktion']} stellt den Zustand nicht exakt her"


__all__ = ["aenderungen_seit", "letzte_aenderung_id", "fehlercode"]


# ------------------------------------------------------------------ Kredite
def parameter(f: dict) -> dict:
    """Kreditparameter ohne Vorgaben-Felder für POST /api/kredite/tilgungsplan."""
    return dict(f)


def _konto(api: Api, name: str, art: str) -> int:
    """Ab M32 sind Kontonamen je Ebene eindeutig (sammel3.md 1, E-307): ein vorhandenes gleichnamiges Konto der
    obersten Ebene mit derselben Art wird verwendet, sonst angelegt."""
    for k in api.konten():
        if k["eltern_id"] is None and k["art"] == art and k["name"].strip().casefold() == name.casefold():
            return k["id"]
    return api.konto(name, art)["id"]


class Kreditbuch:
    """Konten für Kredittests: Giro, Darlehen (kreditkonto), Zinsen (aufwand), Lebensmittel."""

    def __init__(self, api: Api, giro: int | None = None):
        self.api = api
        self.giro = giro or _konto(api, "Girokonto", "girokonto")
        self.darlehen = _konto(api, "Darlehen Fiktivbank", "kreditkonto")
        self.zinsen = _konto(api, "Zinsen", "aufwand")
        self.lebensmittel = _konto(api, "Lebensmittel", "aufwand")
        self.bank = api.empfaenger("Fiktivbank AG")["id"]

    def body(self, **felder) -> dict:
        d = {"name": "Baufinanzierung", "konto_id": self.darlehen, "zahlungskonto_id": self.giro,
             "zins_konto_id": self.zinsen, "restschuld": 1_000_000, "stand_datum": "2024-01-15", "sollzins": 36_000,
             "rate": 50_000, "erste_faelligkeit": "2024-02-01",
             "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "Fiktivbank AG"}]}
        d.update(felder)
        return d

    def anlegen(self, erwartet: int = 201, **felder):
        return self.api.post("/api/kredite", json=self.body(**felder), erwartet=erwartet)

    def zahlung(self, datum: str, betrag: int, *, empfaenger: int | None | str = "bank", zweck: str = "Rate Darlehen",
                gegen: int | None = None, status: str = "importiert") -> dict:
        """Abbuchung vom Giro mit Gegenkonto (Vorgabe: Lebensmittel als beliebige Kategorie)."""
        e = self.bank if empfaenger == "bank" else empfaenger
        return self.api.buchung(datum, [(self.giro, -betrag), (gegen or self.lebensmittel, betrag)],
                                empfaenger_id=e, verwendungszweck=zweck, status=status)


def saldo(api: Api, konto_id: int, stichtag: str | None = None) -> int:
    return api.salden(stichtag)[konto_id]["saldo"]


def kredit(api: Api, kid: int) -> dict:
    return api.get(f"/api/kredite/{kid}", erwartet=200).daten


# ------------------------------------------------------------------ Export
def betrag_text(cent: int) -> str:
    """berichte.md 4.2: Euro mit Dezimalkomma, zwei Nachkommastellen, Minus vorangestellt."""
    v = "-" if cent < 0 else ""
    a = abs(cent)
    return f"{v}{a // 100},{a % 100:02d}"


def text_betrag(s: str) -> int:
    m = re.fullmatch(r"(-?)(0|[1-9][0-9]*),([0-9]{2})", s)
    assert m, f"Betrag {s!r} entspricht nicht berichte.md 4.2"
    cent = int(m.group(2)) * 100 + int(m.group(3))
    return -cent if m.group(1) else cent


def csv_lesen(roh: bytes) -> list[list[str]]:
    assert roh.startswith(b"\xef\xbb\xbf"), "CSV ohne UTF-8-BOM"
    text = roh[3:].decode("utf-8")
    assert text.endswith("\r\n"), "CSV endet nicht mit \\r\\n"
    zeilen = list(csv.reader(io.StringIO(text, newline=""), delimiter=";", quotechar='"', strict=True))
    assert zeilen and zeilen[0] == SPALTEN, f"Kopfzeile {zeilen[0] if zeilen else None} statt {SPALTEN}"
    for z in zeilen[1:]:
        assert len(z) == len(SPALTEN), f"Zeile mit {len(z)} Feldern: {z}"
    return zeilen[1:]


def csv_buchungen(zeilen: list[list[str]]) -> list[dict]:
    """Buchungen aus den CSV-Zeilen zurückgewinnen (Reihenfolge der Datei)."""
    aus: list[dict] = []
    for z in zeilen:
        f = dict(zip(SPALTEN, z))
        if not aus or aus[-1]["id"] != int(f["buchung_id"]):
            aus.append({"id": int(f["buchung_id"]), "datum": f["datum"], "empfaenger": f["empfaenger"] or None,
                        "verwendungszweck": f["verwendungszweck"], "status": f["status"],
                        "kategorie": f["kategorie"] or None, "tags": json.loads(f["tags"]),
                        "extern_ids": json.loads(f["extern_ids"]), "gegen_iban": f["gegen_iban"] or None,
                        "splits": []})
        b = aus[-1]
        assert int(f["split_nr"]) == len(b["splits"]) + 1, "split_nr nicht fortlaufend"
        b["splits"].append({"id": int(f["split_id"]), "konto_id": int(f["konto_id"]), "konto": f["konto"],
                            "betrag": text_betrag(f["betrag"]), "memo": f["memo"],
                            "abstimmung_id": int(f["abstimmung_id"]) if f["abstimmung_id"] else None})
    return aus


def rest_als_csv_form(api: Api, buchungen: list[dict]) -> list[dict]:
    """Dieselbe Form aus der REST-Darstellung (unabhängige Erwartung)."""
    name = {k["id"]: k["name"] for k in api.konten()}
    aus = []
    for b in buchungen:
        aus.append({"id": b["id"], "datum": b["datum"], "empfaenger": b["empfaenger"]["name"] if b["empfaenger"] else None,
                    "verwendungszweck": b["verwendungszweck"], "status": b["status"],
                    "kategorie": name[b["kategorie_id"]] if b["kategorie_id"] else None,
                    "tags": [t["name"] for t in b["tags"]], "extern_ids": b["extern_ids"], "gegen_iban": b["gegen_iban"],
                    "splits": [{"id": s["id"], "konto_id": s["konto_id"], "konto": name[s["konto_id"]],
                                "betrag": s["betrag"], "memo": s["memo"], "abstimmung_id": s["abstimmung_id"]}
                               for s in b["splits"]]})
    return aus


def export(api: Api, endung: str, **params):
    from .api import _params
    r = api.get(f"/api/export/buchungen.{endung}", params=_params(params), erwartet=200)
    art = (r.headers.get("content-type") or "").split(";")[0].strip()
    assert art == ("text/csv" if endung == "csv" else "application/pdf"), art
    cd = r.headers.get("content-disposition") or ""
    assert re.fullmatch(rf'attachment;\s*filename="?kontor-buchungen-\d{{8}}\.{endung}"?', cd.strip()), cd
    return r


def pdf_text(roh: bytes) -> str:
    from pypdf import PdfReader
    assert roh.startswith(b"%PDF-1."), "keine PDF-Datei"
    assert b"%%EOF" in roh[-1024:], "%%EOF fehlt am Ende"
    r = PdfReader(io.BytesIO(roh))
    assert len(r.pages) >= 1
    return "\n".join(p.extract_text() or "" for p in r.pages)


MARKE = re.compile(r"\[#([0-9]+)\]")


def pdf_marken(text: str) -> list[int]:
    return [int(m) for m in MARKE.findall(text)]


def pdf_zeile(text: str, bid: int) -> str:
    zeilen = [z for z in text.splitlines() if f"[#{bid}]" in z]
    assert len(zeilen) == 1, f"Marke [#{bid}] steht in {len(zeilen)} Zeilen"
    return zeilen[0]


def de_datum(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


# ------------------------------------------------------------------ Berichte
def kontostand(api: Api, erwartet: int = 200, **params):
    from .api import _params
    return api.get("/api/berichte/kontostand", params=_params(params), erwartet=erwartet)


def einnahmen_ausgaben(api: Api, erwartet: int = 200, **params):
    from .api import _params
    return api.get("/api/berichte/einnahmen-ausgaben", params=_params(params), erwartet=erwartet)


def stichtage(von: str, bis: str, intervall: str) -> list[str]:
    """berichte.md 1/2 unabhängig: von, alle Intervallenden dazwischen, bis."""
    a, b = dt.date.fromisoformat(von), dt.date.fromisoformat(bis)
    aus = [a]
    d = a + dt.timedelta(days=1)
    while d < b:
        morgen = d + dt.timedelta(days=1)
        if intervall == "tag" or (intervall == "woche" and d.isoweekday() == 7) or (
                intervall == "monat" and morgen.month != d.month) or (intervall == "jahr" and morgen.year != d.year):
            aus.append(d)
        d = morgen
    if b > a:
        aus.append(b)
    return [x.isoformat() for x in aus]


def saldo_aus_splits(buchungen: list[dict], konto_ids: set[int], stichtag: str) -> int:
    return sum(s["betrag"] for b in buchungen if b["datum"] <= stichtag for s in b["splits"]
               if s["konto_id"] in konto_ids)


def unterkonten(konten: list[dict], kid: int) -> set[int]:
    aus, neu = {kid}, {kid}
    while neu:
        neu = {k["id"] for k in konten if k["eltern_id"] in neu} - aus
        aus |= neu
    return aus


def benachrichtigungen(api: Api, **params) -> list[dict]:
    from .api import _params
    return api.get("/api/benachrichtigungen", params=_params(params), erwartet=200).daten


def pruefen(api: Api, buchung_ids: list[int] | None = None, erwartet: int = 200):
    body = {} if buchung_ids is None else {"buchung_ids": buchung_ids}
    return api.post("/api/wiederkehrend/pruefen", json=body, erwartet=erwartet)


def uebersicht(api: Api, stichtag: str | None = None) -> dict:
    params = {"stichtag": stichtag} if stichtag else None
    return api.get("/api/wiederkehrend", params=params, erwartet=200).daten
