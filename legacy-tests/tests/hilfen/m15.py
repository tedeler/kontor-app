"""Hilfen für Meilenstein-15-Tests (Sammelpaket Bedienung) – nur über die Spezifikation.

- ``Wirksamkeit``: eigenes Modell der Wirksamkeit (``protokoll.md`` 6.5) und der Menge eines „Rückgängig bis“
  (6.2a, E-182) aus den im Test selbst ausgelösten Operationen; nie aus Antworten der Anwendung abgeleitet.
- ``Verlauf``: führt Operationen aus, nimmt vorher einen Abzug des Buchbestands und trägt die neuen Änderungen
  ins Modell ein; prüft „Rückgängig bis“ gegen den Abzug unmittelbar vor der Änderung.
- REST-Kurzformen für ``mehrfach/loeschen``, ``mehrfach/verschieben`` und ``herkunft`` (``datenmodell.md`` 18).
- ``Mitschnitt``: Anfragen an ``/api/`` im Browser (Methode, Pfad, JSON-Körper) für Prüfungen wie „genau eine
  Anfrage“ oder „PATCH nur mit den geänderten Feldern“ (E-187).
"""

from __future__ import annotations

import json
import re
from typing import Callable
from urllib.parse import urlsplit

from .api import Api, fehlercode
from .m3 import aenderungen_seit, letzte_aenderung_id
from .m6 import bestand, pruefe_eintraege

LOESCHEN = "/api/buchungen/mehrfach/loeschen"
VERSCHIEBEN = "/api/buchungen/mehrfach/verschieben"
RUECKGAENGIG = "/api/aenderungen/rueckgaengig"
BESTANDSARTEN = ("girokonto", "sparkonto", "kreditkonto")


# ------------------------------------------------------------------ Modell der Wirksamkeit (protokoll.md 6.5)
class Wirksamkeit:
    """Änderungen mit ihren Zielen (``rueckgaengig_von``); normale Änderungen haben keine Ziele."""

    def __init__(self) -> None:
        self.ziele: dict[int, list[int]] = {}

    def neu(self, aid: int, ziele: list[int] | tuple[int, ...] = ()) -> None:
        assert aid not in self.ziele, f"Änderung {aid} doppelt eingetragen"
        self.ziele[aid] = sorted(ziele)

    def _wirksam(self, zurueck: set[int] = frozenset()) -> dict[int, bool]:
        """Wirksamkeit jeder Änderung, wenn zusätzlich die Änderungen in ``zurueck`` zurückgenommen sind."""
        eff: dict[int, bool] = {}
        for k in sorted(self.ziele, reverse=True):
            eff[k] = k not in zurueck and not any(eff[u] for u in self.ziele if u > k and k in self.ziele[u])
        return eff

    def wirksam(self) -> dict[int, bool]:
        return self._wirksam()

    def rueckgaengig_durch(self) -> dict[int, int | None]:
        eff = self._wirksam()
        aus: dict[int, int | None] = {}
        for a in self.ziele:
            durch = [u for u in self.ziele if a in self.ziele[u] and eff[u]]
            assert len(durch) <= 1, f"Modell: Änderung {a} von mehreren wirksamen Änderungen zurückgenommen"
            aus[a] = durch[0] if durch else None
        return aus

    def bis_menge(self, bis_id: int) -> list[int]:
        """protokoll.md 6.2a Nr. 3: absteigend jede im Zwischenstand wirksame Änderung k ≥ bis_id."""
        zurueck: set[int] = set()
        nachher: dict[int, bool] = {}
        for k in sorted((x for x in self.ziele if x >= bis_id), reverse=True):
            jetzt = not any(nachher.get(u, False) for u in self.ziele if u > k and k in self.ziele[u])
            if jetzt:
                zurueck.add(k)
            # danach ist k nicht wirksam: entweder eben zurückgenommen oder schon vorher unwirksam
            nachher[k] = False
        # Folge: Weil jede neuere Änderung danach unwirksam ist, wirkt jede ältere k ≥ bis_id wieder; die Menge
        # sind also alle Änderungen ab bis_id (auch sich aufhebende Paare, E-182).
        return sorted(zurueck)

    def gruppe_wirksam(self, ids: list[int]) -> list[int]:
        eff = self._wirksam()
        return sorted(i for i in ids if eff[i])


def pruefe_wirksamkeit(api: Api, modell: Wirksamkeit) -> None:
    """``rueckgaengig_durch`` jeder Änderung wie im Modell (protokoll.md 6.5)."""
    soll = modell.rueckgaengig_durch()
    ist = {}
    seite = 1
    while True:
        s = api.get("/api/aenderungen", params={"seite": seite, "pro_seite": 500}, erwartet=200).daten
        for a in s["eintraege"]:
            ist[a["id"]] = a["rueckgaengig_durch"]
        if seite * 500 >= s["gesamt"]:
            break
        seite += 1
    assert set(ist) == set(soll), f"Änderungen {sorted(set(ist) ^ set(soll))} fehlen im Modell oder im Protokoll"
    falsch = {a: (ist[a], soll[a]) for a in soll if ist[a] != soll[a]}
    assert not falsch, f"rueckgaengig_durch (ist, soll) weicht ab: {falsch}"
    wirksam = {a["id"] for a in _alle(api, wirksam="true")}
    assert wirksam == {a for a, d in soll.items() if d is None}, "Filter wirksam=true passt nicht zu rueckgaengig_durch"


def _alle(api: Api, **params) -> list[dict]:
    aus: list[dict] = []
    seite = 1
    while True:
        s = api.get("/api/aenderungen", params={**params, "seite": seite, "pro_seite": 500}, erwartet=200).daten
        aus.extend(s["eintraege"])
        if len(aus) >= s["gesamt"] or not s["eintraege"]:
            return aus
        seite += 1


# ------------------------------------------------------------------ Verlauf mit Abzügen
class Verlauf:
    """Operationen mit Abzug davor; ``vor[aid]`` = Buchbestand unmittelbar vor der ersten Änderung einer
    Operation (für spätere Änderungen derselben Operation gibt es keinen Abzug)."""

    def __init__(self, api: Api) -> None:
        self.api = api
        self.modell = Wirksamkeit()
        self.vor: dict[int, dict] = {}
        self.letzte = letzte_aenderung_id(api)
        for a in sorted(_alle(api), key=lambda x: x["id"]):
            self.modell.neu(a["id"], a["rueckgaengig_von"])

    def schritt(self, aufruf: Callable[[], object], ziele: Callable[[], list[int]] | None = None) -> list[dict]:
        """Führt ``aufruf`` aus; ``ziele`` liefert für Rückgängig-Operationen die erwarteten Ziele (vor dem Aufruf
        berechnet). Rückgabe: die neuen Änderungen (aufsteigend)."""
        z = bestand(self.api)
        erwartet = ziele() if ziele else None
        aufruf()
        neu = aenderungen_seit(self.api, self.letzte)
        for i, a in enumerate(neu):
            if erwartet is not None:
                assert len(neu) == 1, f"Rückgängig erzeugt genau eine Änderung, nicht {len(neu)}"
                assert a["rueckgaengig_von"] == erwartet, (
                    f"rueckgaengig_von {a['rueckgaengig_von']} statt {erwartet} (protokoll.md 6.2a/6.5)")
                self.modell.neu(a["id"], erwartet)
            else:
                assert a["rueckgaengig_von"] == [], a
                self.modell.neu(a["id"])
            if i == 0:
                self.vor[a["id"]] = z
        if neu:
            self.letzte = neu[-1]["id"]
        return neu

    def eine(self, aufruf: Callable[[], object]) -> int:
        neu = self.schritt(aufruf)
        assert len(neu) == 1, f"genau eine Änderung erwartet, erhalten {[a['aktion'] for a in neu]}"
        return neu[0]["id"]

    def bis(self, bis_id: int) -> dict:
        """POST {bis_id}; prüft Antwort, Menge, Nettowirkung, Stand = Abzug vor bis_id und Wirksamkeit. Ist der Stand
        schon der Abzug vor bis_id, wird 409 bereits_rueckgaengig ohne Wirkung erwartet (E-190); Rückgabe dann {}."""
        vorher = bestand(self.api)
        menge = self.modell.bis_menge(bis_id)
        antwort: dict = {}
        if vorher == self.vor[bis_id]:
            # Nettowirkung leer (E-190): nichts zurückzunehmen → 409 bereits_rueckgaengig, keine Änderung
            def leer():
                r = self.api.post(RUECKGAENGIG, json={"bis_id": bis_id}, erwartet=409)
                assert fehlercode(r) == "bereits_rueckgaengig", r.text
            ohne_wirkung(self.api, leer)
            pruefe_wirksamkeit(self.api, self.modell)
            return {}

        def aufruf():
            antwort.update(self.api.post(RUECKGAENGIG, json={"bis_id": bis_id}, erwartet=200).daten)
        (u,) = self.schritt(aufruf, lambda: menge)
        assert antwort == u, "Antwort 200 ist die neue Änderung U"
        assert (u["quelle"], u["aktion"], u["gruppe"], u["rueckgaengig_durch"]) == (
            "rueckgaengig", "rueckgaengig", None, None)
        nachher = bestand(self.api)
        assert nachher == self.vor[bis_id], (
            f"Stand nach Rückgängig bis {bis_id} ist nicht der Stand unmittelbar vor {bis_id}")
        pruefe_eintraege(u, vorher, nachher)
        pruefe_wirksamkeit(self.api, self.modell)
        return u

    def zurueck(self, aid: int) -> dict:
        """Einzelnes Rückgängig (auch Wiederholen) mit Prüfung gegen den Abzug vor ``aid`` bzw. der Nettowirkung."""
        vorher = bestand(self.api)
        (u,) = self.schritt(lambda: self.api.post(f"/api/aenderungen/{aid}/rueckgaengig", erwartet=200),
                            lambda: [aid])
        pruefe_eintraege(u, vorher, bestand(self.api))
        pruefe_wirksamkeit(self.api, self.modell)
        return u


def ohne_wirkung(api: Api, aufruf: Callable[[], object]) -> None:
    """Fehlerantwort oder Operation ohne Wirkung: kein Protokolleintrag, Bestand unverändert."""
    vor = letzte_aenderung_id(api)
    z = bestand(api)
    aufruf()
    assert aenderungen_seit(api, vor) == [], "ohne Wirkung bzw. bei Fehlern darf keine Änderung entstehen"
    assert bestand(api) == z, "ohne Wirkung bzw. bei Fehlern darf sich der Buchbestand nicht ändern"


# ------------------------------------------------------------------ REST (datenmodell.md 18)
def loeschen(api: Api, ids: list[int], erwartet: int | tuple = 200):
    return api.post(LOESCHEN, json={"buchung_ids": ids}, erwartet=erwartet)


def verschieben(api: Api, von: int, nach: int, *, ids: list[int] | None = None, gruppe: str | None = None,
                erwartet: int | tuple = 200, **extra):
    body: dict = {"von_konto_id": von, "nach_konto_id": nach, **extra}
    if ids is not None:
        body["buchung_ids"] = ids
    if gruppe is not None:
        body["gruppe"] = gruppe
    return api.post(VERSCHIEBEN, json=body, erwartet=erwartet)


def herkunft(api: Api, konto_id: int, erwartet: int = 200):
    r = api.get(f"/api/konten/{konto_id}/herkunft", erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def details(r) -> dict:
    return r.json()["fehler"]["details"]


def fehler(r) -> str:
    return fehlercode(r)


def verschoben_soll(form: dict, von: int, nach: int) -> dict:
    """Protokollform nach dem Verschieben: nur konto_id der Splits auf ``von`` wird ``nach`` (datenmodell.md 18.2)."""
    neu = json.loads(json.dumps(form))
    for s in neu["splits"]:
        if s["konto_id"] == von:
            s["konto_id"] = nach
    return neu


def gruppen_buchungen(api: Api, gruppe: str) -> set[int]:
    """IDs der Buchungen, die eine Änderung der Gruppe angelegt hat (E-184), aus dem Protokoll der Gruppe."""
    aus: set[int] = set()
    for a in _alle(api, gruppe=gruppe):
        for e in a["eintraege"]:
            if e["objekt"] == "buchung" and e["art"] == "angelegt":
                aus.add(e["objekt_id"])
    return aus


# ------------------------------------------------------------------ Browser
class Mitschnitt:
    """Zeichnet Anfragen der Seite an ``/api/`` auf: (Methode, Pfad, JSON-Körper oder None)."""

    def __init__(self, seite) -> None:
        self.anfragen: list[tuple[str, str, object]] = []
        self.seite = seite
        seite.on("request", self._anfrage)

    def _anfrage(self, req) -> None:
        pfad = urlsplit(req.url).path
        if not pfad.startswith("/api/"):
            return
        koerper = None
        roh = req.post_data
        if roh:
            try:
                koerper = json.loads(roh)
            except ValueError:
                koerper = roh
        self.anfragen.append((req.method, pfad, koerper))

    def schreibend(self, muster: str | None = None) -> list[tuple[str, str, object]]:
        """Alle Anfragen außer GET (optional nur Pfade, die ``muster`` vollständig treffen)."""
        # Ereignisse der synchronen Playwright-API kommen erst bei einem Aufruf an: einmal anstoßen
        self.seite.wait_for_timeout(100)
        return [a for a in self.anfragen if a[0] != "GET" and (muster is None or re.fullmatch(muster, a[1]))]

    def leeren(self) -> None:
        self.seite.wait_for_timeout(100)
        self.anfragen.clear()


def text_normal(s: str | None) -> str:
    """Leerraum (auch geschützte Leerzeichen) zusammengefasst, Rand entfernt (E-187)."""
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ").replace(" ", " ")).strip()


def prozent_text(promille: int) -> str:
    """oberflaeche.md 25.6: kaufmännisch gerundete ganze Prozent aus Promille."""
    return f"{(promille + 5) // 10} %"
