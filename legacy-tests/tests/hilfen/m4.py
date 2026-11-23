"""Hilfen für Meilenstein-4-Tests (GnuCash-Import, Lernmodell, Split-Vorlagen).

Nur über die Spezifikation (gnucash.md, lernmodell.md, vorlagen.md, openapi.yaml).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .api import Api, neue_config
from .m3 import bestand as bestand_m3
from .lern_orakel import Modell, merkmale
from .normal import norm
from .pfade import FIXTURES, MOCK

GNC = FIXTURES / "gnc"
M4 = FIXTURES / "m4"
LERN_MOCK = MOCK / "m4_lernen.json"
VORLAGEN_MOCK = MOCK / "m4_vorlagen.json"
BESTAND = {"girokonto", "sparkonto", "kreditkonto"}


def lade(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def gnc_erwartung(name: str) -> dict:
    """name ohne Endung, z. B. 'minimal' → fixtures/gnc/minimal.erwartung.json"""
    return lade(GNC / f"{name}.erwartung.json")


def import_gnc(api: Api, pfad: Path | bytes, *, erwartet=200, dateiname: str = "buch.gnucash"):
    inhalt = pfad if isinstance(pfad, bytes) else Path(pfad).read_bytes()
    name = dateiname if isinstance(pfad, bytes) else Path(pfad).name
    return api.post("/api/import/gnucash", files={"datei": (name, inhalt, "application/octet-stream")},
                    erwartet=erwartet)


def mock_api(basis: Path, daten: Path, heute: str, **felder) -> Api:
    return Api(neue_config(basis, mock_modus=True, mock_daten=daten, mock_heute=dt.date.fromisoformat(heute),
                           **felder))


def zeit(api: Api, heute: str) -> None:
    api.put("/api/mock/zeit", json={"jetzt": f"{heute}T12:00:00Z"}, erwartet=200)


def sync(api: Api, **body) -> dict:
    return api.post("/api/sync", json=body, erwartet=200).daten


def bestand(api: Api) -> dict:
    """Protokollierte Objekte inkl. Vorlagen (protokoll.md 9.1)."""
    aus = bestand_m3(api)
    for v in api.get("/api/vorlagen", erwartet=200).daten:
        aus[("vorlage", v["id"])] = v
    return aus


OBJEKTE_M4 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]


def sortierschluessel(e: dict) -> tuple[int, int]:
    return OBJEKTE_M4.index(e["objekt"]), e["objekt_id"]


def pruefe_eintraege(a: dict, vorher: dict, nachher: dict) -> None:
    """Wie m3.pruefe_eintraege, mit Objekt vorlage (protokoll.md 9.1)."""
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


# ---------------------------------------------------------------- Vorlagen
def trifft(b: dict, empf: str | None, zweck: str, konten: set[int]) -> bool:
    """kategorisierung.md 1.1/4 für Text- und Kontobedingungen."""
    if b["feld"] == "konto_id":
        return b["wert"] in konten
    text = empf if b["feld"] == "empfaenger" else zweck
    if text is None:
        return False
    t, w = norm(text), norm(b["wert"])
    return {"enthaelt": w in t, "gleich": t == w, "beginnt_mit": t.startswith(w)}[b["operator"]]


def erkenne(vorlagen: list[dict], empf: str | None, zweck: str, konten: set[int], r: int):
    """vorlagen.md 3: ('treffer', V) | ('abweichung', V0) | ('keine', None)."""
    k = [v for v in sorted(vorlagen, key=lambda v: (v["prioritaet"], v["id"]))
         if v["aktiv"] and all(trifft(b, empf, zweck, konten) for b in v["bedingungen"])]
    if not k:
        return "keine", None
    for v in k:
        if v["gesamtbetrag"] == r:
            return "treffer", v
    return "abweichung", k[0]


def kategorien_anlegen(api: Api, liste: list[dict]) -> dict[str, int]:
    vorhanden = {k["name"]: k["id"] for k in api.konten() if k["art"] in ("aufwand", "ertrag")}
    for k in liste:
        if k["name"] not in vorhanden:
            vorhanden[k["name"]] = api.konto(k["name"], k["art"])["id"]
    return vorhanden


def vorlage_body(v: dict, kats: dict[str, int], konto_nach_iban: dict[str, int] | None = None) -> dict:
    """Vorlage aus m4/vorlagen.json in den Anfragekörper übersetzen."""
    bed = []
    for b in v["bedingungen"]:
        b = dict(b)
        if isinstance(b["wert"], dict):
            b["wert"] = (konto_nach_iban or {})[b["wert"]["iban"]]
        bed.append(b)
    body = {"name": v["name"], "bedingungen": bed,
            "teile": [{"kategorie_id": kats[t["kategorie"]], "betrag": t["betrag"], "memo": t["memo"]}
                      for t in v["teile"]]}
    if "prioritaet" in v:
        body["prioritaet"] = v["prioritaet"]
    return body


def vorlage(api: Api, name: str, empfaenger: str, teile: list[tuple[int, int]] | list[tuple[int, int, str]], *,
            zweck: str | None = None, erwartet=201, **felder) -> dict:
    bed = [{"feld": "empfaenger", "operator": "gleich", "wert": empfaenger}]
    if zweck:
        bed.append({"feld": "verwendungszweck", "operator": "enthaelt", "wert": zweck})
    body = {"name": name, "bedingungen": bed,
            "teile": [{"kategorie_id": t[0], "betrag": t[1], **({"memo": t[2]} if len(t) > 2 else {})}
                      for t in teile], **felder}
    return api.post("/api/vorlagen", json=body, erwartet=erwartet).daten


def umsatz(uid: str, iban: str, tag: str, betrag: int, name: str | None, zweck: str = "", **extra) -> dict:
    return {"umsatz_id": uid, "iban": iban, "buchungstag": tag, "valuta": tag, "betrag": betrag, "waehrung": "EUR",
            "gegenpartei_name": name, "gegenpartei_iban": None, "verwendungszweck": zweck, "vormerkung": False,
            "storno": False, **extra}


def mock_datei(pfad: Path, konten: list[tuple[str, str, str]], umsaetze: list[dict]) -> Path:
    """Schreibt eine Mock-Datendatei (plugins.md 4); konten = [(iban, name, art)]."""
    d = {"format": "kontor-mock-daten", "version": 1,
         "bank": {"konten": [{"iban": i, "bic": None, "name": n, "art": a, "inhaber": "Erika Mustermann (fiktiv)",
                              "waehrung": "EUR"} for i, n, a in konten], "umsaetze": umsaetze},
         "mail": {"postfaecher": ["haushalt.eins@example.invalid"], "nachrichten": []}}
    pfad.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return pfad


def konto_nach_iban(api: Api) -> dict[str, int]:
    return {k["iban"]: k["id"] for k in api.konten() if k["iban"]}


def bank_buchungen(api: Api) -> dict[str, dict]:
    """Buchungen nach Umsatzkennung (nur die mit bank:-Kennung), Schlüssel = umsatz_id."""
    aus = {}
    for b in api.alle_buchungen():
        for e in b["extern_ids"]:
            if e.startswith("bank:"):
                aus[e.rsplit(":", 1)[1]] = b
    return aus


# ---------------------------------------------------------------- Lernmodell
def vorhersagen(api, eintraege: list[dict]) -> list[dict]:
    aus = []
    for i in range(0, len(eintraege), 1000):
        aus += api.post("/api/lernmodell/vorhersage", json={"eintraege": eintraege[i:i + 1000]},
                        erwartet=200).daten["ergebnisse"]
    assert len(aus) == len(eintraege)
    return aus


class Buch:
    """Legt Buchungen über REST an und führt die Trainingsbeispiele für das Orakel mit."""

    def __init__(self, api):
        self.api = api
        self.giro = api.konto("Giro", "girokonto")["id"]
        self.karte = api.konto("Karte", "kreditkonto")["id"]
        self.ek = api.konto("Eigenkapital", "eigenkapital")["id"]
        self.kats = {n: api.konto(n, a)["id"] for n, a in (("Lebensmittel", "aufwand"), ("Café", "aufwand"),
                                                            ("Tanken", "aufwand"), ("Gehalt", "ertrag"))}
        self.empf: dict[str, int] = {}
        self.beispiele: list[tuple[list[str], int]] = []
        self.buchungen: list[dict] = []

    def empfaenger(self, name):
        if name is None:
            return None
        if name not in self.empf:
            self.empf[name] = self.api.empfaenger(name)["id"]
        return self.empf[name]

    def einfach(self, name, zweck, betrag, kat, konto=None, *, training=True, status="bestaetigt"):
        konto = konto or self.giro
        b = self.api.buchung("2024-03-01", [(konto, betrag), (self.kats[kat] if kat else self.ek, -betrag)],
                             empfaenger_id=self.empfaenger(name), verwendungszweck=zweck, status=status)
        if kat and training:
            self.beispiele.append((merkmale(name, zweck, betrag), self.kats[kat]))
        self.buchungen.append(b)
        return b

    def modell(self) -> Modell:
        return Modell(self.beispiele)
