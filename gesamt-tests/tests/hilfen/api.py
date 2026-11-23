"""Testclient, der jede Antwort gegen openapi.yaml prüft."""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path
from typing import Any

from . import kontor
from .vertrag import vertrag


_PORTAL = None


def gemeinsames_portal():
    """Ein Ereignisschleifen-Thread je Testprozess für alle ``TestClient``-Anfragen.

    Ohne ihn startet Starlette für jede einzelne Anfrage einen eigenen Thread mit eigener Ereignisschleife;
    das war rund die Hälfte der Laufzeit einer Anfrage (TESTUMBAU.md). Der Lifespan der App läuft dadurch
    nicht (wie bisher nur mit ``with TestClient(app)``).
    """
    global _PORTAL
    if _PORTAL is None:
        import atexit

        import anyio.from_thread

        cm = anyio.from_thread.start_blocking_portal(backend="asyncio")
        _PORTAL = cm.__enter__()
        atexit.register(cm.__exit__, None, None, None)
    return _PORTAL


class Api:
    """Dünne Hülle um ``fastapi.testclient.TestClient``.

    Jede Antwort unter /api/ wird gegen den Vertrag validiert und muss den
    Header ``X-Kontor-Modus`` tragen.
    """

    def __init__(self, config, **client_kw: Any) -> None:
        from fastapi.testclient import TestClient  # kommt mit der Anwendung

        self.config = config
        self.app = kontor.create_app(config)
        self.client = TestClient(self.app, raise_server_exceptions=False, **client_kw)
        self.client.portal = gemeinsames_portal()
        self.modus_erwartet = "mock" if config.mock_modus else "echt"
        #: CSRF-Token der angemeldeten Sitzung (M7, sicherheit.md 4.6); wird bei schreibenden Anfragen gesendet
        self.csrf: str | None = None
        if id(config) in _ANMELDELAUF:
            self._anmeldelauf_anmelden()

    def _anmeldelauf_anmelden(self) -> None:
        """Anmeldelauf (E-125): Passwort einrichten (falls nötig) und anmelden; Tests bleiben unverändert."""
        anm = kontor.modul("kontor.anmeldung")
        if not anm.ist_eingerichtet(self.config):
            anm.passwort_setzen(self.config, ANMELDELAUF_PASSWORT)
        r = self.client.post("/api/anmeldung", json={"passwort": ANMELDELAUF_PASSWORT})
        assert r.status_code == 200, f"Anmeldelauf: Anmeldung fehlgeschlagen: {r.status_code} {r.text[:500]}"
        self.csrf = r.json()["csrf_token"]

    # ------------------------------------------------------------ Rohzugriff
    def anfrage(self, methode: str, pfad: str, *, erwartet: int | tuple[int, ...] | None = None,
                **kw: Any):
        if self.csrf and methode.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            kw["headers"] = {"X-Kontor-CSRF": self.csrf, **(kw.get("headers") or {})}
        r = self.client.request(methode, pfad, **kw)
        r.daten = None
        if pfad.startswith("/api/") or pfad == "/api":
            assert r.headers.get("x-kontor-modus") == self.modus_erwartet, (
                f"{methode} {pfad}: Header X-Kontor-Modus muss {self.modus_erwartet!r} sein, "
                f"ist {r.headers.get('x-kontor-modus')!r}")
            if r.status_code >= 500:
                raise AssertionError(f"{methode} {pfad} → {r.status_code} (Serverfehler): {r.text[:2000]}")
            r.daten = vertrag().pruefe_antwort(methode, pfad.split("?")[0], r.status_code, r.content,
                                               r.headers.get("content-type"))
        if erwartet is not None:
            erw = (erwartet,) if isinstance(erwartet, int) else erwartet
            assert r.status_code in erw, (
                f"{methode} {pfad}: erwartet {erw}, erhalten {r.status_code}: {r.text[:2000]}")
        return r

    def get(self, pfad, **kw):
        return self.anfrage("GET", pfad, **kw)

    def post(self, pfad, **kw):
        return self.anfrage("POST", pfad, **kw)

    def put(self, pfad, **kw):
        return self.anfrage("PUT", pfad, **kw)

    def patch(self, pfad, **kw):
        return self.anfrage("PATCH", pfad, **kw)

    def delete(self, pfad, **kw):
        return self.anfrage("DELETE", pfad, **kw)

    # ------------------------------------------------------------- Komfort
    def konto(self, name: str = "Girokonto", art: str = "girokonto", **felder) -> dict:
        return self.post("/api/konten", json={"name": name, "art": art, **felder}, erwartet=201).daten

    def empfaenger(self, name: str) -> dict:
        return self.post("/api/empfaenger", json={"name": name}, erwartet=201).daten

    def tag(self, name: str) -> dict:
        return self.post("/api/tags", json={"name": name}, erwartet=201).daten

    def buchung(self, datum: str, splits: list[tuple[int, int] | tuple[int, int, str]], **felder) -> dict:
        body = {"datum": datum, "splits": [_split(s) for s in splits], **felder}
        return self.post("/api/buchungen", json=body, erwartet=201).daten

    def buchung_lesen(self, bid: int) -> dict:
        return self.get(f"/api/buchungen/{bid}", erwartet=200).daten

    def konten(self) -> list[dict]:
        return self.get("/api/konten", erwartet=200).daten

    def uebersicht(self, stichtag: str | None = None) -> dict:
        params = {"stichtag": stichtag} if stichtag else None
        return self.get("/api/kontenuebersicht", params=params, erwartet=200).daten

    def salden(self, stichtag: str | None = None) -> dict[int, dict]:
        return {k["konto_id"]: k for k in self.uebersicht(stichtag)["konten"]}

    def seite(self, **params) -> dict:
        return self.get("/api/buchungen", params=_params(params), erwartet=200).daten

    def alle_buchungen(self, **params) -> list[dict]:
        aus: list[dict] = []
        seite = 1
        while True:
            d = self.seite(**params, seite=seite, pro_seite=500)
            aus.extend(d["eintraege"])
            if len(aus) >= d["gesamt"] or not d["eintraege"]:
                assert len(aus) == d["gesamt"], "Paginierung liefert nicht genau 'gesamt' Einträge"
                return aus
            seite += 1

    def import_kmy(self, pfad: Path, *, erwartet=200, dateiname: str | None = None):
        inhalt = Path(pfad).read_bytes()
        return self.post("/api/import/kmymoney",
                         files={"datei": (dateiname or Path(pfad).name, inhalt, "application/octet-stream")},
                         erwartet=erwartet)

    def zustand(self) -> dict:
        """Vollständiger Buchbestand für Vorher/Nachher-Vergleiche."""
        return {
            "konten": self.konten(),
            "empfaenger": self.get("/api/empfaenger", erwartet=200).daten,
            "tags": self.get("/api/tags", erwartet=200).daten,
            "buchungen": self.alle_buchungen(),
            "uebersicht": self.uebersicht(),
            "dubletten": self.get("/api/dubletten", erwartet=200).daten,
        }


def _split(s) -> dict:
    if isinstance(s, dict):
        return s
    d = {"konto_id": s[0], "betrag": s[1]}
    if len(s) > 2:
        d["memo"] = s[2]
    return d


def _params(p: dict) -> dict:
    aus = {}
    for k, v in p.items():
        if v is None:
            continue
        if isinstance(v, bool):
            aus[k] = "true" if v else "false"
        else:
            aus[k] = v
    return aus


def fehlercode(r) -> str:
    return r.json()["fehler"]["code"]


#: Anmeldelauf (E-125): Mit ``KONTOR_TESTS_ANMELDUNG=1`` laufen alle über ``neue_config`` erzeugten Apps
#: mit eingeschalteter Anmeldung; ``Api`` meldet sich an und sendet den CSRF-Kopf.
ANMELDELAUF_PASSWORT = "Anmeldelauf-Haushalt-2026"
_ANMELDELAUF: dict[int, object] = {}


def anmeldelauf_aktiv() -> bool:
    return os.environ.get("KONTOR_TESTS_ANMELDUNG", "").strip().lower() in ("1", "true", "ja", "yes", "on")


def neue_config(basis: Path | None = None, **felder):
    """KontorConfig mit frischer temporärer Datenbank."""
    if basis is None:
        basis = Path(tempfile.mkdtemp(prefix="kontor-test-"))
    cls = kontor.KontorConfig()
    anmelden = anmeldelauf_aktiv() and "anmeldung" not in felder
    if anmelden:
        try:
            anmelden = "anmeldung" in inspect.signature(cls).parameters
        except (TypeError, ValueError):
            anmelden = False
    if anmelden:
        felder["anmeldung"] = True
    config = cls(datenbank=basis / "kontor.sqlite3", **felder)
    if anmelden:
        _ANMELDELAUF[id(config)] = config
    return config


def neue_api(basis: Path | None = None, **felder) -> Api:
    return Api(neue_config(basis, **felder))
