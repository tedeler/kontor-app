"""Unabhängige Orakel für Meilenstein 3 (buchhaltungspflege.md, protokoll.md) – nur aus der Spezifikation.

Bewusst anders formuliert als der Generator, damit Fehler in einer der beiden
Rechnungen auffallen.
"""

from __future__ import annotations

import datetime as dt
import unicodedata

from .normal import ekey, norm

BESTAND = {"girokonto", "sparkonto", "kreditkonto"}


# ------------------------------------------------------------------ Suche
def snorm(s: str) -> str:
    """buchhaltungspflege.md 6: NFC, norm, NFKD ohne Kombinationszeichen (Kategorie Mn)."""
    zerlegt = unicodedata.normalize("NFKD", norm(unicodedata.normalize("NFC", s)))
    return "".join(filter(lambda z: unicodedata.category(z) != "Mn", zerlegt))


def woerter(q: str) -> list[str]:
    return [snorm(w) for w in q.split()]


def trifft(q: str, felder: list[str]) -> bool:
    fs = [snorm(f) for f in felder if f]
    return all(any(w in f for f in fs) for w in woerter(q))


def suchfelder_buchung(b: dict, konten: dict[int, dict], empfaenger: dict[int, dict]) -> list[str]:
    f = [b["verwendungszweck"]] + [s["memo"] for s in b["splits"]] + [t["name"] for t in b["tags"]]
    if b["empfaenger"]:
        f.append(b["empfaenger"]["name"])
    f += [konten[s["konto_id"]]["name"] for s in b["splits"]]
    return f


def suche_erwartet(q: str, *, konten: list[dict], empfaenger: list[dict], tags: list[dict],
                   buchungen: list[dict]) -> dict:
    """Erwartetes Suchergebnis aus dem vollständigen REST-Zustand (ohne limit)."""
    kd = {k["id"]: k for k in konten}
    ed = {e["id"]: e for e in empfaenger}
    return {
        "konten": [k["id"] for k in sorted(konten, key=lambda k: k["id"])
                   if trifft(q, [k["name"], k["iban"] or "", k["notiz"]])],
        "empfaenger": [e["id"] for e in sorted(empfaenger, key=lambda e: e["id"])
                       if trifft(q, [e["name"], *e.get("aliase", [])])],
        "tags": [t["id"] for t in sorted(tags, key=lambda t: t["id"]) if trifft(q, [t["name"]])],
        "buchungen": [b["id"] for b in sorted(buchungen, key=lambda b: (b["datum"], b["id"]), reverse=True)
                      if trifft(q, suchfelder_buchung(b, kd, ed))],
    }


# -------------------------------------------------------------- Empfänger
def empfaenger_fuer(name: str | None, empfaenger: list[dict]) -> dict | None:
    """buchhaltungspflege.md 2.3 Schritte 1–2 (ohne Anlegen)."""
    if name is None or not name.strip():
        return None
    n = name.strip()
    for e in empfaenger:
        if e["name"] == n:
            return e
    k = ekey(n)
    if not k:
        return None
    treffer = [e for e in empfaenger if any(ekey(a) == k for a in e.get("aliase", []))]
    assert len(treffer) <= 1, "Aliase müssen eindeutig sein"
    return treffer[0] if treffer else None


# -------------------------------------------------------------- Umbuchung
def ist_kandidat(b: dict, art: dict[int, str], unkategorisiert_id: int | None) -> bool:
    """buchhaltungspflege.md 4.1 auf der REST-Darstellung einer Buchung."""
    if len(b["splits"]) != 2 or b["status"] == "abgeglichen" or b.get("abgestimmt"):
        return False
    bank = [s for s in b["splits"] if art[s["konto_id"]] in BESTAND]
    gegen = [s for s in b["splits"] if art[s["konto_id"]] not in BESTAND]
    return len(bank) == 1 and len(gegen) == 1 and bank[0]["betrag"] != 0 and gegen[0]["konto_id"] == unkategorisiert_id


def bankseite(b: dict, art: dict[int, str]) -> dict:
    (s,) = [s for s in b["splits"] if art[s["konto_id"]] in BESTAND]
    return s


def passen(x: dict, y: dict, art: dict[int, str], iban: dict[int, str | None], fenster: int) -> bool:
    sx, sy = bankseite(x, art), bankseite(y, art)
    if sx["konto_id"] == sy["konto_id"] or sx["betrag"] + sy["betrag"] != 0:
        return False
    tage = abs((dt.date.fromisoformat(x["datum"]) - dt.date.fromisoformat(y["datum"])).days)
    if tage > fenster:
        return False
    ix, iy = iban[sx["konto_id"]], iban[sy["konto_id"]]
    gx, gy = x.get("gegen_iban"), y.get("gegen_iban")
    widerspruch = (gx is not None and gx != iy) or (gy is not None and gy != ix)
    bestaetigt = (gx is not None and gx == iy) or (gy is not None and gy == ix)
    return bestaetigt and not widerspruch


def eindeutige_paare(buchungen: list[dict], konten: list[dict], fenster: int = 3) -> list[tuple[int, int]]:
    """Paare (behalten_id, entfernt_id) nach buchhaltungspflege.md 4.3, aufsteigend."""
    art = {k["id"]: k["art"] for k in konten}
    iban = {k["id"]: k["iban"] for k in konten}
    unk = next((k["id"] for k in konten if k["extern_id"] == "kontor:unkategorisiert"), None)
    c = [b for b in buchungen if ist_kandidat(b, art, unk)]
    p = {b["id"]: {y["id"] for y in c if y["id"] != b["id"] and passen(b, y, art, iban, fenster)} for b in c}
    paare = set()
    for x, ys in p.items():
        if len(ys) == 1:
            (y,) = ys
            if p[y] == {x}:
                paare.add((min(x, y), max(x, y)))
    return sorted(paare)
