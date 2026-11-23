"""Hilfen für Meilenstein-31-Tests (Definition 3: Lernmodell-Transparenz, automatische Regeln, Berichte,
Bestellnummer-Mails, Branch-Anzeige, Testinstanz, Einstellungen in Bereichen, Gruppierung).

Nur über die Spezifikation (``lernmodell.md`` 8–10, ``berichte.md`` 6, ``erwartungen.md`` 14, ``version.md`` 6,
``betrieb.md`` 9, ``oberflaeche.md`` 40). Erwartungen werden hier unabhängig berechnet.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from fractions import Fraction

from .api import Api

# ------------------------------------------------------------------ Einstellungen in Bereichen (40.3, E-286)
BEREICHE = ("allgemein", "bank", "mail", "benachrichtigungen", "sicherheit", "daten")
#: Zuordnung bisheriger Elemente zu Bereichen (E-286) – eine Stelle für alle Tests
BEREICH_VON = {
    "einstellung-thema": "allgemein", "layout-zuruecksetzen": "allgemein", "status-modus": "allgemein",
    "bankzugang": "bank", "pin-status": "bank", "pin-verwerfen": "bank",
    "postfaecher": "mail", "postfach-neu-adresse": "mail", "mail-abrufen": "mail",
    "geheimnis-oauth_client_secret": "mail",
    "zustellung-status": "benachrichtigungen", "benachrichtigung-test": "benachrichtigungen",
    "geheimnis-ntfy_token": "benachrichtigungen",
    "abmelden": "sicherheit", "schutz-status": "sicherheit",
    "sicherung-herunterladen": "daten", "sicherung-datei": "daten",
}
#: je Bereich ein Element, das dort im Mock-Modus ohne weitere Konfiguration sichtbar ist
LEITELEMENT = {"allgemein": "einstellung-thema", "bank": "pin-status", "mail": "postfaecher",
               "benachrichtigungen": "zustellung-status", "sicherheit": "schutz-status",
               "daten": "sicherung-herunterladen"}


def einstellungen_oeffnen(seite, server, bereich: str):
    """Öffnet ``/einstellungen?bereich=<bereich>`` und wartet auf die geladene Seite (E-286)."""
    from . import m8

    assert bereich in BEREICHE, bereich
    m8.oeffnen(seite, server, f"/einstellungen?bereich={bereich}", seitenname="einstellungen")
    return m8.tid(seite, "seite-einstellungen")


def einstellung_oeffnen(seite, server, testid: str):
    """Öffnet den Bereich, in dem das bisherige Element ``testid`` liegt (``BEREICH_VON``)."""
    return einstellungen_oeffnen(seite, server, BEREICH_VON[testid])


# ------------------------------------------------------------------ Lernmodell: Einstellungen und Erklärung (8)
EINSTELLUNGEN = "/api/lernmodell/einstellungen"


def einstellungen(api: Api) -> dict:
    return api.get(EINSTELLUNGEN, erwartet=200).daten


def einstellungen_setzen(api: Api, erwartet=200, **body):
    r = api.put(EINSTELLUNGEN, json=body, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def erklaerung(api: Api, bid: int, erwartet=200):
    r = api.get(f"/api/buchungen/{bid}/lernmodell", erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def rangfolge(modell, m: list[str]) -> list[tuple[Fraction, int]]:
    """(P, Kategorie) absteigend nach P, bei Gleichstand ID aufsteigend (lernmodell.md 4.5); leer ohne
    bekanntes E/V-Merkmal."""
    bekannt = sorted({f for f in m if modell.nf[f] > 0})
    if not any(f[0] in "ev" for f in bekannt):
        return []
    s = {}
    for c, nc in modell.nk.items():
        p = Fraction(nc, modell.n)
        for f in bekannt:
            p *= Fraction(modell.nkf[f][c] + 1, nc + 2)
        s[c] = p
    summe = sum(s.values())
    return sorted(((p / summe, c) for c, p in s.items()), key=lambda x: (-x[0], x[1]))


def faktor(modell, f: str, c: int) -> Fraction:
    return Fraction(modell.nkf[f][c] + 1, modell.nk[c] + 2)


def erklaerung_soll(modell, m: list[str], schwelle: int = 700) -> dict:
    """lernmodell.md 8.1 aus dem Orakel: grund, beste, vergleich, je bekanntem Merkmal die Zählungen."""
    if modell.n == 0:
        return {"grund": "kein_modell", "beste": None, "vergleich": None, "merkmale": {}}
    reihe = rangfolge(modell, m)
    if not reihe:
        # W-017 (E-309): auch bei „unbekannt“ hat jedes bekannte Merkmal (z. B. der Betrag) anzahl = N(f); die
        # übrigen Zählungen hängen an c* und sind ohne beste Kategorie nicht festgelegt.
        return {"grund": "unbekannt", "beste": None, "vergleich": None,
                "merkmale": {f: {"anzahl": modell.nf[f]} for f in sorted(set(m)) if modell.nf[f] > 0}}
    p, beste = reihe[0]
    vergleich = reihe[1][1] if len(reihe) > 1 else None
    grund = "vorschlag" if p >= Fraction(schwelle, 1000) else "unter_schwelle"
    merk = {}
    for f in sorted({f for f in m if modell.nf[f] > 0}):
        merk[f] = {"anzahl": modell.nf[f], "anzahl_kategorie": modell.nkf[f][beste],
                   "anzahl_vergleich": modell.nkf[f][vergleich] if vergleich is not None else 0,
                   "faktor_promille": (int(1000 * faktor(modell, f, beste) / faktor(modell, f, vergleich))
                                       if vergleich is not None else None)}
    return {"grund": grund, "beste": beste, "vergleich": vergleich, "merkmale": merk}


def vorhersage_soll(modell, m: list[str], schwelle: int = 700) -> dict:
    reihe = rangfolge(modell, m)
    kand = [{"kategorie_id": c, "sicherheit": int(p * 1000)} for p, c in reihe[:5]]
    if reihe and reihe[0][0] >= Fraction(schwelle, 1000):
        return {"kategorie_id": reihe[0][1], "sicherheit": int(reihe[0][0] * 1000), "kandidaten": kand}
    return {"kategorie_id": None, "sicherheit": None, "kandidaten": kand}


def gewicht(a: list[str], b: list[str]) -> int:
    """8.1 ``aehnliche``: gemeinsame Merkmale, Empfänger dreifach, Wort einfach, Betrag nicht."""
    return sum(3 if f[0] == "e" else 1 if f[0] == "v" else 0 for f in set(a) & set(b))


# ------------------------------------------------------------------ automatische Regeln (9)
def regelbetrag(b: dict, bestand_ids: set[int]) -> int:
    return sum(s["betrag"] for s in b["splits"] if s["konto_id"] in bestand_ids)


def trainingsmenge(buchungen: list[dict]) -> list[dict]:
    """lernmodell.md 3: kategorie_id ≠ null und kein offener Vorschlag."""
    return [b for b in buchungen if b["kategorie_id"] is not None and b["vorschlag"] is None]


def _quote_ok(kats: list[int], k: int) -> bool:
    return bool(kats) and 100 * sum(1 for x in kats if x == k) >= 95 * len(kats)


def automatische_soll(buchungen: list[dict], heute: str) -> tuple[dict[int, int], set[int]]:
    """lernmodell.md 9.1 (Bedingungen 1–3) über die REST-Darstellung der Buchungen.

    Liefert (Empfänger → Kategorie der zu erwartenden Regel, unsichere Empfänger). Unsicher ist ein Empfänger,
    bei dem die beiden Lesarten der Fenstergrenze (E-279 Punkt 2) verschieden ausfallen.
    """
    je: dict[int, list[dict]] = {}
    for b in trainingsmenge(buchungen):
        if b["empfaenger"] is not None:
            je.setdefault(b["empfaenger"]["id"], []).append(b)
    soll, unsicher = {}, set()
    h = dt.date.fromisoformat(heute)
    for eid, bs in je.items():
        kats = [b["kategorie_id"] for b in bs]
        k = Counter(kats).most_common(1)[0][0]
        if sum(1 for x in kats if x == k) < 5 or not _quote_ok(kats, k):
            continue
        ende = min(max(dt.date.fromisoformat(b["datum"]) for b in bs), h)
        lesarten = []
        for tage in (364, 365):          # Beginn ende−364 bzw. ende−365 (einschließlich)
            beginn = ende - dt.timedelta(days=tage)
            fenster = [b["kategorie_id"] for b in bs if beginn <= dt.date.fromisoformat(b["datum"]) <= ende]
            lesarten.append(_quote_ok(fenster, k))
        if lesarten[0] != lesarten[1]:
            unsicher.add(eid)
        elif lesarten[0]:
            soll[eid] = k
    return soll, unsicher


def regeln(api: Api) -> list[dict]:
    return api.get("/api/regeln", erwartet=200).daten


def automatische(api: Api) -> dict[int, dict]:
    """Automatische Regeln nach ``empfaenger_id``; andere Regeln tragen die Felder nicht (9.3)."""
    aus = {}
    for r in regeln(api):
        if "automatisch" in r or "empfaenger_id" in r:
            assert r.get("automatisch") is True and isinstance(r.get("empfaenger_id"), int), r
            assert r["empfaenger_id"] not in aus, "höchstens eine automatische Regel je Empfänger"
            aus[r["empfaenger_id"]] = r
    return aus


def bedingung_ok(r: dict, name: str) -> bool:
    """E-279 Punkt 3: bisherige Form ``empfaenger gleich <Name>`` oder ein Ausdruck mit dem Namen."""
    if r["bedingungen"] == [{"feld": "empfaenger", "operator": "gleich", "wert": name}]:
        return True
    return r.get("ausdruck_form") == "ausdruck" and name in r.get("ausdruck", "")


def bestand(api: Api, gesperrt: set[int] = frozenset()) -> dict:
    """Bestand in Protokollform wie M27; Empfänger aus ``gesperrt`` mit ``lernregel_gesperrt: true``
    (lernmodell.md 9.4, E-279 Punkt 5 – ob REST das Feld liefert, ist offen)."""
    from .m27 import bestand as bestand_m27

    aus = bestand_m27(api)
    for (o, i), v in list(aus.items()):
        if o != "empfaenger":
            continue
        if i in gesperrt:
            aus[(o, i)] = {**v, "lernregel_gesperrt": True}
        else:
            assert "lernregel_gesperrt" not in v, f"Empfänger {i} unerwartet gesperrt"
    return aus


# ------------------------------------------------------------------ Berichte (berichte.md 6)
BERICHTE = ("vertraege", "jahr", "vorschau", "vermoegen", "kategorien", "empfaenger", "geldfluss", "qualitaet",
            "tags")


def monat(api: Api, erwartet=200, **params):
    p = []
    for k, v in params.items():
        for x in (v if isinstance(v, (list, tuple)) else [v]):
            p.append((k, x))
    r = api.get("/api/berichte/monat", params=p or None, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


# ------------------------------------------------------------------ Bestellnummer (erwartungen.md 14)
NUMMER = re.compile(r"(?<![0-9])[0-9]{3}-[0-9]{7}-[0-9]{7}(?![0-9])")


def nummern(text: str | None) -> set[str]:
    """14.2: Bestellnummern im Text, auch ohne Leerraum."""
    if not text:
        return set()
    return set(NUMMER.findall(text)) | set(NUMMER.findall(re.sub(r"\s+", "", text)))


__all__ = ["BEREICHE", "BEREICH_VON", "LEITELEMENT", "einstellungen_oeffnen", "einstellung_oeffnen", "Api",
           "Counter", "Fraction", "dt", "re"]
