"""Unabhängiges Orakel für „Konto löschen mit Buchungen“ (spec/api/loeschen.md).

Arbeitet nur auf REST-Momentaufnahmen (Listen von Konten, Buchungen, Regeln,
Empfängern) und berechnet daraus Ergebnis und erwarteten Bestand. Kein
Anwendungscode, keine Ausgabe der Anwendung als Erwartung.
"""

from __future__ import annotations

import copy

UNKATEGORISIERT = "kontor:unkategorisiert"
NEU = "NEU"  # Platzhalter für ein erst anzulegendes Konto „Unkategorisiert“


def unkategorisiert_id(konten: list[dict]) -> int | None:
    ks = [k["id"] for k in konten if k["extern_id"] == UNKATEGORISIERT]
    return ks[0] if ks else None


def gesperrt(b: dict) -> bool:
    return b["status"] == "abgeglichen" or bool(b.get("abgestimmt")) or any(
        s.get("abstimmung_id") is not None for s in b["splits"])


def fehler(konten: list[dict], buchungen: list[dict], k: int, variante: str, *, trocken: bool = False,
           gesperrte_einbeziehen: bool = False) -> tuple[int, str] | None:
    """Erwarteter Fehler (Status, Code) nach loeschen.md 2 oder None (Körper als gültig vorausgesetzt)."""
    ks = {x["id"]: x for x in konten}
    if k not in ks:
        return 404, "nicht_gefunden"
    if variante == "elternkonto" and ks[k]["eltern_id"] is None:
        return 422, "kein_elternkonto"
    if variante == "unkategorisiert" and ks[k]["extern_id"] == UNKATEGORISIERT:
        return 422, "ziel_ungueltig"
    if not trocken and not gesperrte_einbeziehen and any(
            gesperrt(b) for b in buchungen if any(s["konto_id"] == k for s in b["splits"])):
        return 409, "buchung_gesperrt"
    return None


def _memo(memos: list[str]) -> str:
    aus: list[str] = []
    for m in memos:
        if m and m not in aus:
            aus.append(m)
    return " / ".join(aus)


def berechne(konten: list[dict], buchungen: list[dict], k: int, variante: str, konflikte: str,
             regeln: list[dict] | None = None, empfaenger: list[dict] | None = None,
             abstimmungen: list[dict] | None = None) -> dict:
    """Erwartetes Ergebnis und erwarteter Bestand nach erfolgreichem Löschen (ohne Probelauf).

    Rückgabe:
      ergebnis: Felder von KontoLoeschErgebnis (ohne trocken, aenderung_id); ziel_konto_id ggf. NEU
      konten:   {id: eltern_id} aller verbleibenden Konten (ein neues „Unkategorisiert“ nicht enthalten)
      buchungen:{id: Buchung} aller verbleibenden Buchungen; Splits mit konto_id ggf. NEU
      regeln:   {id: Regel} verbleibender Regeln
      empfaenger: {id: standardkategorie_id}
    """
    ks = {x["id"]: x for x in konten}
    regeln = regeln or []
    empfaenger = empfaenger or []
    abstimmungen = abstimmungen or []
    kk = ks[k]
    if variante == "elternkonto":
        z = kk["eltern_id"]
    elif variante == "unkategorisiert":
        z = unkategorisiert_id(konten) or NEU
    else:
        z = None

    betroffen = sorted(b["id"] for b in buchungen if any(s["konto_id"] == k for s in b["splits"]))
    gesp = sorted(b["id"] for b in buchungen if b["id"] in betroffen and gesperrt(b))
    abst_weg = sorted(a["id"] for a in abstimmungen if a["konto_id"] == k)
    unterkonten = sorted(x["id"] for x in konten if x["eltern_id"] == k)

    neue_buchungen: dict[int, dict] = {}
    geloescht: list[int] = []
    konflikt: list[int] = []
    for b in buchungen:
        if b["id"] not in betroffen:
            neue_buchungen[b["id"]] = copy.deepcopy(b)
            continue
        if variante == "loeschen":
            geloescht.append(b["id"])
            continue
        splits = []
        for s in b["splits"]:
            s2 = copy.deepcopy(s)
            if s["konto_id"] == k:
                s2["konto_id"] = z
                if "abstimmung_id" in s2:
                    s2["abstimmung_id"] = None  # Abstimmungen von K entfallen (3.6)
            splits.append(s2)
        if all(s["konto_id"] == z for s in splits):
            konflikt.append(b["id"])
            if konflikte == "loeschen":
                geloescht.append(b["id"])
                continue
        else:
            gruppe = [i for i, s in enumerate(splits) if s["konto_id"] == z and s.get("abstimmung_id") is None]
            if len(gruppe) >= 2:
                erst = splits[gruppe[0]]
                erst["betrag"] = sum(splits[i]["betrag"] for i in gruppe)
                erst["memo"] = _memo([splits[i]["memo"] for i in gruppe])
                splits = [s for i, s in enumerate(splits) if i not in gruppe[1:]]
        nb = copy.deepcopy(b)
        nb["splits"] = splits
        nb["vorschlag"] = None
        neue_buchungen[b["id"]] = nb

    umgebucht = sorted(set(betroffen) - set(geloescht))

    # Regeln (3.4)
    neue_regeln: dict[int, dict] = {}
    geaendert_r: list[int] = []
    geloescht_r: list[int] = []
    for r in regeln:
        bezug = r["kategorie_id"] == k or any(b["feld"] == "konto_id" and b["wert"] == k for b in r["bedingungen"])
        if not bezug:
            r2 = copy.deepcopy(r)
            if any(b["feld"] == "konto_id" for b in r2["bedingungen"]):
                # W-029 (E-314): der Ausdruck nennt das Konto mit vollem Pfad; der ändert sich, wenn ein
                # Elternkonto gelöscht wird – offen lassen wie bei umgestellten Regeln
                r2 = {f: w for f, w in r2.items() if f != "ausdruck"}
            neue_regeln[r["id"]] = r2
        elif variante == "elternkonto":
            r2 = copy.deepcopy(r)
            if r2["kategorie_id"] == k:
                r2["kategorie_id"] = z
            for b in r2["bedingungen"]:
                if b["feld"] == "konto_id" and b["wert"] == k:
                    b["wert"] = z
                    # M30: der übersetzte Ausdruck nennt das Konto beim Namen und ändert sich mit; die Erwartung
                    # lässt ihn deshalb offen (gewöhnliches dict: zusätzliche optionale Felder erlaubt, E-124, E-271)
                    r2 = {f: w for f, w in r2.items() if f != "ausdruck"}
            neue_regeln[r["id"]] = r2
            geaendert_r.append(r["id"])
        else:
            geloescht_r.append(r["id"])
    for b in neue_buchungen.values():
        v = b.get("vorschlag")
        if v and v.get("regel_id") in geloescht_r:
            v["regel_id"] = None

    # Standardkategorien (3.5)
    neue_empf: dict[int, int | None] = {}
    geaendert_e: list[int] = []
    for e in empfaenger:
        sk = e.get("standardkategorie_id")
        if sk == k:
            neue_empf[e["id"]] = z if variante == "elternkonto" else None
            geaendert_e.append(e["id"])
        else:
            neue_empf[e["id"]] = sk

    # Splitmarken gelöschter Abstimmungen (auch auf anderen Konten gibt es sie nicht: Marken liegen auf K)
    for b in neue_buchungen.values():
        for s in b["splits"]:
            if s.get("abstimmung_id") in abst_weg:
                s["abstimmung_id"] = None

    neue_konten = {x["id"]: (kk["eltern_id"] if x["eltern_id"] == k else x["eltern_id"])
                   for x in konten if x["id"] != k}

    return {
        "ergebnis": {
            "konto_id": k, "buchungen": variante, "konflikte": konflikte, "ziel_konto_id": z,
            "buchungen_betroffen": betroffen, "buchungen_geloescht": sorted(geloescht),
            "buchungen_umgebucht": umgebucht, "konfliktbuchungen": sorted(konflikt), "gesperrt": gesp,
            "unterkonten": unterkonten, "regeln_geaendert": sorted(geaendert_r),
            "regeln_geloescht": sorted(geloescht_r), "empfaenger_geaendert": sorted(geaendert_e),
            "abstimmungen_geloescht": abst_weg,
        },
        "konten": neue_konten,
        "buchungen": neue_buchungen,
        "regeln": neue_regeln,
        "empfaenger": neue_empf,
    }


def ersetze_neu(wert, neu_id: int):
    """Ersetzt den Platzhalter NEU rekursiv durch die tatsächliche ID des neuen Kontos."""
    if wert == NEU:
        return neu_id
    if isinstance(wert, dict):
        return {k: ersetze_neu(v, neu_id) for k, v in wert.items()}
    if isinstance(wert, list):
        return [ersetze_neu(v, neu_id) for v in wert]
    return wert


SPLITFELDER = ("id", "konto_id", "betrag", "memo")
BUCHUNGSFELDER = ("id", "datum", "empfaenger", "verwendungszweck", "status", "tags", "extern_ids", "vorschlag")


def buchung_kern(b: dict) -> dict:
    """Vergleichsform einer Buchung: unveränderliche Felder und Splits (ohne abgeleitete Werte)."""
    d = {f: b.get(f) for f in BUCHUNGSFELDER}
    d["splits"] = [{f: s[f] for f in SPLITFELDER} | ({"abstimmung_id": s["abstimmung_id"]}
                                                      if "abstimmung_id" in s else {}) for s in b["splits"]]
    return d
