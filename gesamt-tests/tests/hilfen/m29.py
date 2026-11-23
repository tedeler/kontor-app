"""Hilfen für Meilenstein 29 (Bankabruf über FinTS/camt, Bankzugang; bankzugang.md, fints.md) – nur über die Spezifikation.

Erwartungswerte kommen aus den Generatordaten der FinTS-Attrappe (``fixtures/m6/fints_bank.json``) und werden hier
unabhängig nach den Regeln der Spezifikation berechnet (Kontenliste: ``fints.md`` 3.2).
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from . import kontor
from .api import Api
from .m6 import PRODUKT

FELDER = ("url", "blz", "benutzer", "kunden_id", "produkt_id", "tan_verfahren")
PFLICHT = ("url", "blz", "benutzer", "produkt_id")
ZUGANG = "/api/bank/zugang"
ZUSATZ_VERFAHREN = {"funktion": "921", "name": "pushTAN synthetisch", "technische_id": "PUSH"}
GESCHAEFTSVORFAELLE = {"HKSPA", "HKCAZ", "HKKAZ", "HKSAL"}
NUR_IBAN_BIC = {"iban": True, "bic": True, "kontonummer": False, "unterkonto": False, "bankleitzahl": False}


# ------------------------------------------------------------------ Plugin
class Pin:
    """pin_quelle, die Aufrufe zählt."""

    def __init__(self, wert):
        self.wert, self.aufrufe = wert, 0

    def __call__(self):
        self.aufrufe += 1
        return self.wert


def fints_plugin(config, pin):
    return kontor.modul("kontor.plugins.fints").FintsBankPlugin(config, pin_quelle=pin)


def tan_antwort(anforderung_id: str, tan: str):
    return kontor.modul("kontor.plugins.bank").TanAntwort(anforderung_id, tan)


def konten_dicts(konten) -> list[dict]:
    return [{"iban": k.iban, "bic": k.bic, "name": k.name, "art": k.art, "inhaber": k.inhaber, "waehrung": k.waehrung}
            for k in konten]


def umsatz_dicts(liste) -> list[dict]:
    return [{"iban": u.iban, "buchungstag": u.buchungstag.isoformat(),
             "valuta": u.valuta.isoformat() if u.valuta else None, "betrag": u.betrag, "waehrung": u.waehrung,
             "gegenpartei_name": u.gegenpartei_name, "gegenpartei_iban": u.gegenpartei_iban,
             "verwendungszweck": u.verwendungszweck, "vormerkung": u.vormerkung, "storno": u.storno,
             "umsatz_id": u.umsatz_id} for u in liste]


def paare(verfahren) -> set[tuple[str, str]]:
    """Ergebnis von ``tan_verfahren()`` als Menge von Paaren (Reihenfolge frei, Liste oder Tupel; E-265)."""
    aus = set()
    for p in verfahren:
        assert len(p) == 2, f"kein Paar: {p!r}"
        aus.add((str(p[0]), str(p[1])))
    assert len(aus) == len(list(verfahren)), "Verfahren doppelt geliefert"
    return aus


def _art(kontoart: int | None) -> str | None:
    if kontoart is None:
        return "girokonto"
    if 1 <= kontoart <= 9:
        return "girokonto"
    if 10 <= kontoart <= 29:
        return "sparkonto"
    if 40 <= kontoart <= 59:
        return "kreditkonto"
    return None


def soll_konten(daten: dict, *, upd: str = "normal", ohne_bic: bool = False) -> list[dict]:
    """Erwartete Kontenliste nach ``fints.md`` 3.2 (Fassung M29) aus den Generatordaten der Attrappe.

    ``upd``: ``normal`` | ``ohne_kontoart`` | ``ohne_iban`` | ``ohne_konten`` (Betriebsarten der Attrappe).
    Konten mit ``sepa: false`` stehen nicht oder als Nicht-SEPA-Konto in HISPA und werden nie geliefert.
    """
    aus = []
    for k in daten["konten"]:
        if not k.get("sepa", True):
            continue
        if upd == "ohne_konten":
            aus.append({"iban": k["iban"], "bic": None if ohne_bic else k["bic"], "name": "", "art": "girokonto",
                        "inhaber": "", "waehrung": "EUR"})
            continue
        # Eintrag der Benutzerparameter: über die IBAN, bei ``ohne_iban`` über die Kontonummer – derselbe Eintrag
        if k["waehrung"] != "EUR":
            continue
        art = _art(None if upd == "ohne_kontoart" else k["kontoart"])
        if art is None:
            continue
        inhaber = " ".join(x for x in (k["inhaber"], k.get("inhaber2")) if x)
        aus.append({"iban": k["iban"], "bic": None if ohne_bic else k["bic"], "name": k["produkt"], "art": art,
                    "inhaber": inhaber, "waehrung": "EUR"})
    return sorted(aus, key=lambda x: x["iban"])


def zugang_konten(soll: list[dict], aktiv: dict[str, bool] | None = None) -> list[dict]:
    """Kontenliste des Bankzugangs (bankzugang.md 4.4) aus der erwarteten Plugin-Liste."""
    return [{"iban": k["iban"], "bic": k["bic"], "name": k["name"], "art": k["art"], "inhaber": k["inhaber"],
             "aktiv": (aktiv or {}).get(k["iban"], True)} for k in soll]


# ------------------------------------------------------------------ REST
def zugang(api: Api) -> dict:
    return api.get(ZUGANG, erwartet=200).daten


def zugang_setzen(api: Api, erwartet=200, **felder):
    r = api.put(ZUGANG, json=felder, erwartet=erwartet)
    return r.daten if r.status_code == 200 else r


def verfahren(api: Api, erwartet=200):
    r = api.post(ZUGANG + "/tan-verfahren", erwartet=erwartet)
    return r.daten["verfahren"] if r.status_code == 200 else r


def konten_abrufen(api: Api, erwartet=200, **body):
    kw = {"json": body} if body else {}
    r = api.post(ZUGANG + "/konten/abrufen", erwartet=erwartet, **kw)
    return r.daten if r.status_code == 200 else r


def konten_mit_tan(api: Api, tan: str) -> list[dict]:
    """Kontenabruf, der eine TAN zur Anmeldung verlangt: Anforderung prüfen, beantworten, Konten liefern."""
    erg = konten_abrufen(api)
    assert erg["konten"] is None and erg["tan_erforderlich"] is not None, erg
    erg = konten_abrufen(api, vorgang=erg["tan_erforderlich"]["vorgang"], tan=tan)
    assert erg["tan_erforderlich"] is None, erg
    return erg["konten"]


def konten_waehlen(api: Api, ibans: list[str], erwartet=200):
    r = api.put(ZUGANG + "/konten", json={"ibans": ibans}, erwartet=erwartet)
    return r.daten if r.status_code == 200 else r


def diagnose(api: Api) -> dict:
    return api.get(ZUGANG + "/diagnose", erwartet=200).daten


def diagnose_schalten(api: Api, aktiv: bool, erwartet=200):
    r = api.put(ZUGANG + "/diagnose", json={"aktiv": aktiv}, erwartet=erwartet)
    return r.daten if r.status_code == 200 else r


def code(r) -> str:
    return r.json()["fehler"]["code"]


def orte(r) -> list[list]:
    """Orte der Validierungsfehler (``details`` bei ``validierung``)."""
    return [list(d["ort"]) for d in (r.json()["fehler"]["details"] or [])]


def bild_bytes(daten_url: str) -> tuple[str, bytes]:
    m = re.fullmatch(r"data:([^;,]+);base64,(.*)", daten_url, flags=re.S)
    assert m, "bild ist keine Daten-URL der Form data:<MIME>;base64,…"
    return m[1], base64.b64decode(m[2])


def neustart(api: Api) -> Api:
    """Neue App-Instanz auf derselben Datenbank."""
    return Api(api.config)


# ------------------------------------------------------------------ Mock-Daten für den Übergang (bankzugang.md 3)
MOCK_IBAN = "DE28000000000000008001"


def mock_umsatz(uid: str, tag: str, betrag: int, name: str | None = "Empfänger Beispiel", zweck: str = "Zahlung",
                iban: str = MOCK_IBAN) -> dict:
    return {"umsatz_id": uid, "iban": iban, "buchungstag": tag, "valuta": tag, "betrag": betrag, "waehrung": "EUR",
            "gegenpartei_name": name, "gegenpartei_iban": None, "verwendungszweck": zweck, "vormerkung": False,
            "storno": False}


def mock_datei(pfad: Path, umsaetze: list[dict], ibans: tuple[str, ...] = (MOCK_IBAN,)) -> Path:
    """Mock-Datendatei (plugins.md 4) mit einem Girokonto je IBAN und den angegebenen Umsätzen."""
    daten = {"format": "kontor-mock-daten", "version": 1,
             "bank": {"konten": [{"iban": i, "bic": "TESTDEFFXXX", "name": f"Girokonto {n + 1}", "art": "girokonto",
                                  "inhaber": "Erika Mustermann (fiktiv)", "waehrung": "EUR"}
                                 for n, i in enumerate(ibans)],
                      "umsaetze": umsaetze},
             "mail": {"postfaecher": [], "nachrichten": []}}
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    return pfad


def als_alt_markieren(config) -> None:
    """Naht für den Zustand „vor der Umstellung“ (bankzugang.md 3.1, python-api.md 21.3, E-264)."""
    assert kontor.modul("kontor.sync").kennungen_als_alt_markieren(config) is None


def bankbuchungen(api: Api, iban: str = MOCK_IBAN) -> list[dict]:
    """Buchungen am Bankkonto: Datum, Betrag am Bankkonto, Empfängername, Bank-Kennungen dieses Kontos."""
    konto = next(k["id"] for k in api.konten() if k["iban"] == iban)
    aus = []
    for b in api.alle_buchungen():
        teile = [s for s in b["splits"] if s["konto_id"] == konto]
        if not teile:
            continue
        name = b["empfaenger"]["name"] if b["empfaenger"] else None
        aus.append({"id": b["id"], "datum": b["datum"], "betrag": sum(s["betrag"] for s in teile), "empfaenger": name,
                    "kennungen": sorted(x for x in b["extern_ids"] if x.startswith(f"bank:{iban}:"))})
    return sorted(aus, key=lambda x: (x["datum"], x["betrag"], x["id"]))


def kennung(uid: str, iban: str = MOCK_IBAN) -> str:
    return f"bank:{iban}:{uid}"


# ------------------------------------------------------------------ Diagnoseprotokoll (bankzugang.md 5)
def verbotene_werte(daten: dict, attrappe=None, *, extra: tuple[str, ...] = ()) -> list[str]:
    """Alles, was nach bankzugang.md 5 nie im Diagnoseprotokoll stehen darf (Werte der Attrappe).

    Mit ``attrappe`` zusätzlich Server-Adresse, ausgegebene Auftragsreferenzen und Kundensystem-IDs.
    """
    werte = [daten["pin"], daten["tan"], daten["benutzer"], PRODUKT, daten["challenge"]]
    api_url = attrappe.letzte_url if attrappe is not None else None
    if attrappe is not None:
        werte += list(attrappe.referenzen) + list(attrappe.system_ids)
    if daten.get("kunden_id"):
        werte.append(daten["kunden_id"])
    if api_url:
        werte.append(api_url)
        werte.append(api_url.split("//", 1)[1].split("/", 1)[0])     # Rechner:Port der Server-Adresse
    for k in daten["konten"]:
        werte += [k["iban"], k["kontonummer"], k["inhaber"]]
        if " " in k["produkt"]:         # einzelne Wörter wie „Kreditkarte“ könnten als Kontoart-Angabe vorkommen
            werte.append(k["produkt"])
        if k.get("inhaber2"):
            werte.append(k["inhaber2"])
    for u in daten["umsaetze"]:
        # Empfänger, Verwendungszweck, Referenzen, Gegen-IBAN. Beträge stehen nicht in der Liste: Ziffernfolgen wie
        # „125.50“ ließen sich nicht von Größen und Dauern des Protokolls unterscheiden (E-265).
        for m in re.finditer(r"<(Nm|Ustrd|AcctSvcrRef|EndToEndId|MndtId|IBAN)>([^<]+)</\1>", u["camt"]):
            werte.append(m[2])
    werte += list(extra)
    return sorted({w for w in werte if w and len(w) >= 6})


def pruefe_ohne_persoenliches(texte: list[str], verboten: list[str]) -> None:
    for t in texte:
        for w in verboten:
            assert w not in t, f"persönliche Angabe im Diagnoseprotokoll/Log: …{t[max(0, t.find(w) - 60):t.find(w) + 60]}…"


# ------------------------------------------------------------------ Oberfläche (oberflaeche.md 38)
def bankzugang_oeffnen(seite, server):
    """Öffnet den Bereich ``bank`` der Einstellungen (M31, E-286) und liefert den Abschnitt ``bankzugang``
    (eine Stelle für spätere Wege, E-265)."""
    from playwright.sync_api import expect

    from . import m8
    from .m31 import einstellungen_oeffnen

    einstellungen_oeffnen(seite, server, "bank")
    abschnitt = m8.tid(seite, "bankzugang")
    expect(abschnitt).to_be_visible()
    expect(abschnitt).to_have_attribute("data-aenderbar", re.compile("^(ja|nein)$"))
    erweitert_aufklappen(abschnitt)
    return abschnitt


def erweitert_aufklappen(abschnitt) -> None:
    """Klappt „Erweitert“ (``<details>``, oberflaeche.md 40.3) im Abschnitt auf, damit Kunden-ID, Produkt-ID und
    Diagnoseprotokoll bedienbar sind (W-020, E-310). Den Anfangszustand prüft ``test_erweitert_offen_ohne_produkt_id``
    (M31) ohne diese Hilfe."""
    abschnitt.evaluate("a => a.querySelectorAll('details').forEach(d => { d.open = true; })")
