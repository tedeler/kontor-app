"""Hilfen für Meilenstein-3-Tests (Protokoll, Rückgängig, Empfänger, Umbuchungen, Abstimmung, Suche).

Nur über die Spezifikation (protokoll.md, buchhaltungspflege.md, openapi.yaml).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .api import Api, fehlercode, neue_config
from .normal import ekey
from .pfade import FIXTURES, MOCK
from .vertrag import ohne

M3_DATEN = MOCK / "m3_daten.json"
STAMMDATEN = FIXTURES / "m3" / "stammdaten.json"
SUCHE = FIXTURES / "m3" / "suche.json"
UNKATEGORISIERT = "kontor:unkategorisiert"
KORREKTUR = "kontor:korrektur"
OBJEKTE = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung"]
BESTAND = {"girokonto", "sparkonto", "kreditkonto"}


def lade_m3() -> tuple[dict, dict]:
    return (json.loads(M3_DATEN.read_text(encoding="utf-8")),
            json.loads((MOCK / "m3_daten.erwartung.json").read_text(encoding="utf-8")))


def lade_stammdaten() -> dict:
    return json.loads(STAMMDATEN.read_text(encoding="utf-8"))


def m3_api(basis: Path, *, daten: Path | None = M3_DATEN, heute: str | None = "2024-06-30", **felder) -> Api:
    return Api(neue_config(basis, mock_modus=True, mock_daten=daten,
                           mock_heute=dt.date.fromisoformat(heute) if heute else None, **felder))


def stammdaten_anlegen(api: Api, d: dict | None = None, *, regeln: bool = True) -> dict:
    """Kategorien, Empfänger (mit Aliasen) und Regeln aus m3/stammdaten.json.

    Ab M32 gibt es keine Standardkategorie mehr (sammel3.md 2.1, E-307): Wie die Umwandlung der Anwendung (D-219)
    entsteht je Standardkategorie der Stammdaten die Regel „Empfänger ist <Name>“ → Kategorie am Ende der Regelliste
    (auch mit ``regeln=False``); ``std_regeln`` nennt sie je Empfängername."""
    d = d or lade_stammdaten()
    kats = {k["name"]: k["id"] for k in api.konten() if k["art"] in ("aufwand", "ertrag")}
    for k in d["kategorien"]:
        if k["name"] not in kats:
            kats[k["name"]] = api.konto(k["name"], k["art"])["id"]
    emp = {}
    for e in d["empfaenger"]:
        body = {"name": e["name"], "aliase": e["aliase"]}
        emp[e["name"]] = api.post("/api/empfaenger", json=body, erwartet=201).daten
    rs = {}
    if regeln:
        for r in d["regeln"]:
            body = {"name": r["name"], "aktiv": r["aktiv"], "prioritaet": r["prioritaet"],
                    "kategorie_id": kats[r["kategorie"]], "bedingungen": r["bedingungen"]}
            rs[r["name"]] = api.post("/api/regeln", json=body, erwartet=201).daten
    std = {}
    for e in d["empfaenger"]:
        if e["standardkategorie"]:
            body = {"name": f"Empfänger ist {e['name']}", "kategorie_id": kats[e["standardkategorie"]],
                    "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": e["name"]}]}
            std[e["name"]] = api.post("/api/regeln", json=body, erwartet=201).daten
    return {"kategorien": kats, "empfaenger": emp, "regeln": rs, "std_regeln": std}


def vorschlag_soll(w: dict, s: dict) -> tuple[str, int | None]:
    """(quelle, regel_id) eines Vorschlags aus der Wahrheit des Generators ab M32: ``standardkategorie`` wird zur
    umgewandelten Regel des Stammempfängers (``stammdaten_anlegen``, E-307)."""
    if w["quelle"] == "standardkategorie":
        return "regel", s["std_regeln"][w["stamm_empfaenger"]]["id"]
    return w["quelle"], s["regeln"][w["regel"]]["id"] if w["regel"] else None


def konto_id(api: Api, extern_id: str) -> int | None:
    ks = [k["id"] for k in api.konten() if k["extern_id"] == extern_id]
    assert len(ks) <= 1, f"mehrere Konten mit extern_id {extern_id}"
    return ks[0] if ks else None


def erfassen(api: Api, erwartet: int | tuple = 201, **body) -> dict:
    return api.post("/api/buchungen/erfassen", json=body, erwartet=erwartet).daten


# ---------------------------------------------------------- Protokollform
def buchung_zustand(b: dict) -> dict:
    """protokoll.md 2: Protokollform einer Buchung aus ihrer REST-Darstellung."""
    for f in ("gegen_iban", "ist_umbuchung", "abgestimmt"):
        assert f in b, f"M3: Buchung ohne Feld {f}: {b}"
    for s in b["splits"]:
        assert "abstimmung_id" in s, f"M3: Split ohne Feld abstimmung_id: {s}"
    return {"id": b["id"], "datum": b["datum"], "empfaenger_id": b["empfaenger"]["id"] if b["empfaenger"] else None,
            "verwendungszweck": b["verwendungszweck"], "status": b["status"], "splits": b["splits"],
            "tag_ids": [t["id"] for t in b["tags"]], "extern_ids": b["extern_ids"], "vorschlag": b["vorschlag"],
            "gegen_iban": b["gegen_iban"]}


def regel_zustand(r: dict) -> dict:
    """protokoll.md 22 (M30): Protokollform einer Regel aus ihrer REST-Darstellung – ohne ``ausdruck`` und
    ``ausdruck_form``, ``tag_ids`` nur, wenn die Regel Tags hat. Ohne diese Felder (vor M30, Referenz der
    Selbstprüfung) bleibt die Darstellung unverändert (E-271)."""
    weg = [f for f in ("ausdruck", "ausdruck_form") if f in r]
    if "tag_ids" in r and not r["tag_ids"]:
        weg.append("tag_ids")
    return ohne(r, *weg) if weg else r


def bestand(api: Api) -> dict[tuple[str, int], dict]:
    """Alle protokollierten Objekte in Protokollform, Schlüssel (objekt, id)."""
    aus: dict[tuple[str, int], dict] = {}
    for k in api.konten():
        aus[("konto", k["id"])] = k
    for e in api.get("/api/empfaenger", erwartet=200).daten:
        assert "aliase" in e and "standardkategorie_id" in e, f"M3: Empfänger ohne M3-Felder: {e}"
        aus[("empfaenger", e["id"])] = e
    for t in api.get("/api/tags", erwartet=200).daten:
        aus[("tag", t["id"])] = {"id": t["id"], "name": t["name"], "extern_id": t["extern_id"]}
    for b in api.alle_buchungen():
        aus[("buchung", b["id"])] = buchung_zustand(b)
    for r in api.get("/api/regeln", erwartet=200).daten:
        aus[("regel", r["id"])] = regel_zustand(r)
    for v in api.get("/api/dubletten", erwartet=200).daten:
        aus[("verdacht", v["id"])] = v
    for a in api.get("/api/abstimmungen", erwartet=200).daten:
        aus[("abstimmung", a["id"])] = a
    return aus


def zustand_m3(api: Api) -> dict:
    """Vollständiger Lesezustand des Buchbestands inkl. abgeleiteter Sichten (protokoll.md 8.2)."""
    z = api.zustand()
    z["regeln"] = api.get("/api/regeln", erwartet=200).daten
    z["abstimmungen"] = api.get("/api/abstimmungen", erwartet=200).daten
    return z


def zeitstempel_ok(s: str) -> bool:
    """date-time in UTC mit Z, ohne Sekundenbruchteile (synchronisation.md 8)."""
    try:
        dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return False
    return True


def letzte_aenderung_id(api: Api) -> int:
    s = api.get("/api/aenderungen", params={"pro_seite": 1}, erwartet=200).daten
    return s["eintraege"][0]["id"] if s["eintraege"] else 0


def aenderungen_seit(api: Api, ab_id: int) -> list[dict]:
    """Alle Änderungen mit id > ab_id, aufsteigend."""
    aus: list[dict] = []
    seite = 1
    while True:
        s = api.get("/api/aenderungen", params={"seite": seite, "pro_seite": 500}, erwartet=200).daten
        neu = [a for a in s["eintraege"] if a["id"] > ab_id]
        aus.extend(neu)
        if len(neu) < len(s["eintraege"]) or not s["eintraege"] or seite * 500 >= s["gesamt"]:
            break
        seite += 1
    return sorted(aus, key=lambda a: a["id"])


def alle_aenderungen(api: Api, **params) -> list[dict]:
    aus: list[dict] = []
    seite = 1
    p = {k: ("true" if v else "false") if isinstance(v, bool) else v for k, v in params.items()}
    while True:
        s = api.get("/api/aenderungen", params={**p, "seite": seite, "pro_seite": 500}, erwartet=200).daten
        aus.extend(s["eintraege"])
        if len(aus) >= s["gesamt"] or not s["eintraege"]:
            assert len(aus) == s["gesamt"]
            return aus
        seite += 1


def diff(vorher: dict, nachher: dict) -> dict[tuple[str, int], tuple[dict | None, dict | None]]:
    aus = {}
    for k in set(vorher) | set(nachher):
        a, b = vorher.get(k), nachher.get(k)
        if a != b:
            aus[k] = (a, b)
    return aus


def sortierschluessel(e: dict) -> tuple[int, int]:
    return OBJEKTE.index(e["objekt"]), e["objekt_id"]


def pruefe_eintraege(a: dict, vorher: dict, nachher: dict) -> None:
    """protokoll.md 3.2: genau ein Eintrag je geändertem Objekt, Nettowirkung, sortiert."""
    erwartet = diff(vorher, nachher)
    ist = {(e["objekt"], e["objekt_id"]): e for e in a["eintraege"]}
    assert len(ist) == len(a["eintraege"]), f"Änderung {a['id']}: Objekt mehrfach eingetragen"
    assert set(ist) == set(erwartet), (
        f"Änderung {a['id']} ({a['aktion']}): Einträge {sorted(ist)} statt der geänderten Objekte "
        f"{sorted(erwartet)}")
    for k, (v, n) in erwartet.items():
        e = ist[k]
        art = "angelegt" if v is None else "geloescht" if n is None else "geaendert"
        assert e["art"] == art, f"{k}: art {e['art']} statt {art}"
        assert e["vorher"] == v, f"{k}: vorher weicht ab:\n{e['vorher']}\nerwartet\n{v}"
        assert e["nachher"] == n, f"{k}: nachher weicht ab:\n{e['nachher']}\nerwartet\n{n}"
    assert a["eintraege"] == sorted(a["eintraege"], key=sortierschluessel), "Einträge falsch sortiert"


def rueckgaengig(api: Api, aid: int, erwartet: int | tuple = 200):
    return api.post(f"/api/aenderungen/{aid}/rueckgaengig", erwartet=erwartet)


def pruefe_rueckgaengig_rundreise(api: Api, a: dict, vorher: dict, nachher: dict) -> None:
    """Rückgängig stellt `vorher` exakt her, Wiederholen wieder `nachher` (T 3.6, protokoll.md 6)."""
    u = rueckgaengig(api, a["id"]).daten
    assert (u["quelle"], u["aktion"], u["gruppe"], u["rueckgaengig_von"]) == ("rueckgaengig", "rueckgaengig",
                                                                              None, [a["id"]])
    assert bestand(api) == vorher, f"Rückgängig von {a['aktion']} stellt den Zustand nicht exakt her"
    pruefe_eintraege(u, nachher, vorher)
    assert api.get(f"/api/aenderungen/{a['id']}", erwartet=200).daten["rueckgaengig_durch"] == u["id"]
    assert fehlercode(rueckgaengig(api, a["id"], 409)) == "bereits_rueckgaengig"
    r = rueckgaengig(api, u["id"]).daten
    assert bestand(api) == nachher, f"Wiederholen von {a['aktion']} stellt den Zustand nicht exakt her"
    assert api.get(f"/api/aenderungen/{a['id']}", erwartet=200).daten["rueckgaengig_durch"] is None
    assert api.get(f"/api/aenderungen/{u['id']}", erwartet=200).daten["rueckgaengig_durch"] == r["id"]


def bezuege_ok(z: dict) -> bool:
    """Bezugs- und Eindeutigkeitsregeln aus protokoll.md 6.1 Schritt 5 auf einem Bestand (Protokollform)."""
    def ids(o):
        return {k[1] for k in z if k[0] == o}
    konten, emp, tags, regeln, buch, abst = (ids("konto"), ids("empfaenger"), ids("tag"), ids("regel"),
                                             ids("buchung"), ids("abstimmung"))
    for (o, _), x in z.items():
        if o == "konto":
            if x["eltern_id"] is not None and x["eltern_id"] not in konten:
                return False
            seen, e = set(), x["eltern_id"]
            while e is not None:
                if e in seen or e == x["id"]:
                    return False
                seen.add(e)
                e = z[("konto", e)]["eltern_id"] if ("konto", e) in z else None
        elif o == "buchung":
            if any(s["konto_id"] not in konten or (s["abstimmung_id"] is not None and s["abstimmung_id"] not in abst)
                   for s in x["splits"]):
                return False
            if x["empfaenger_id"] is not None and x["empfaenger_id"] not in emp:
                return False
            if not set(x["tag_ids"]) <= tags:
                return False
            if x["vorschlag"] and x["vorschlag"]["regel_id"] is not None and x["vorschlag"]["regel_id"] not in regeln:
                return False
        elif o == "regel":
            if (x["kategorie_id"] is not None and x["kategorie_id"] not in konten) or any(
                    b["feld"] == "konto_id" and b["wert"] not in konten for b in x["bedingungen"]):
                return False
            if not set(x.get("tag_ids", ())) <= tags:   # M30: Tags, die die Regel vergibt
                return False
        elif o == "empfaenger":
            if x["standardkategorie_id"] is not None and x["standardkategorie_id"] not in konten:
                return False
        elif o == "abstimmung":
            if x["konto_id"] not in konten:
                return False
        elif o == "verdacht":
            if x["status"] == "offen" and not ({x["buchung_id"], *x["kandidat_ids"]} <= buch):
                return False
    ibans = [x["iban"] for (o, _), x in z.items() if o == "konto" and x["iban"]]
    namen = [x["name"] for (o, _), x in z.items() if o == "empfaenger"]
    aliase = [ekey(a) for (o, _), x in z.items() if o == "empfaenger" for a in x["aliase"]]
    tagn = [x["name"].casefold() for (o, _), x in z.items() if o == "tag"]
    return all(len(v) == len(set(v)) for v in (ibans, namen, aliase, tagn))
