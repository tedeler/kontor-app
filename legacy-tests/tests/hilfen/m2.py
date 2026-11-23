"""Hilfen für Meilenstein-2-Tests (Synchronisation, TAN, PIN, Regeln) – nur über die Spezifikation."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import kontor
from .api import Api, neue_config
from .pfade import FIXTURES, MOCK

SYNC_DATEN = MOCK / "sync_daten.json"
SYNC_DATEN_PIN = MOCK / "sync_daten_pin.json"
REGELN = FIXTURES / "sync" / "regeln.json"
UNKATEGORISIERT = "kontor:unkategorisiert"
UTC = dt.timezone.utc


def lade_sync() -> tuple[dict, dict]:
    daten = json.loads(SYNC_DATEN.read_text(encoding="utf-8"))
    erw = json.loads((MOCK / "sync_daten.erwartung.json").read_text(encoding="utf-8"))
    return daten, erw


def lade_regeln() -> dict:
    return json.loads(REGELN.read_text(encoding="utf-8"))


def mock_config(basis: Path, *, daten: Path | None = SYNC_DATEN, heute: str | None = "2024-06-30",
                szenario: str = "normal", **felder):
    return neue_config(basis, mock_modus=True, mock_daten=daten, mock_szenario=szenario,
                       mock_heute=dt.date.fromisoformat(heute) if heute else None, **felder)


def mock_api(basis: Path, **kw) -> Api:
    return Api(mock_config(basis, **kw))


def zeit(s: str) -> dt.datetime:
    """Zeitstempel der API (``…Z``) als zeitzonenbehaftetes datetime."""
    assert isinstance(s, str) and s.endswith("Z"), s
    return dt.datetime.fromisoformat(s[:-1]).replace(tzinfo=UTC)


def zeitstempel(d: dt.datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sync(api: Api, erwartet: int = 200, **body) -> dict:
    r = api.post("/api/sync", json=body, erwartet=erwartet)
    return r.daten


def setze_zeit(api: Api, jetzt: str) -> dict:
    return api.put("/api/mock/zeit", json={"jetzt": jetzt}, erwartet=200).daten


def status(api: Api) -> dict:
    return api.get("/api/sync/status", erwartet=200).daten


def laeufe(api: Api) -> list[dict]:
    return api.get("/api/sync/laeufe", erwartet=200).daten


def tans(api: Api) -> list[dict]:
    return api.get("/api/tan-anforderungen", erwartet=200).daten


def benachrichtigungen(api: Api, **params) -> list[dict]:
    p = {k: ("true" if v else "false") if isinstance(v, bool) else v for k, v in params.items()}
    return api.get("/api/benachrichtigungen", params=p or None, erwartet=200).daten


def konto_nach_iban(api: Api) -> dict[str, dict]:
    return {k["iban"]: k for k in api.konten() if k["iban"]}


def unkategorisiert(api: Api) -> dict | None:
    ks = [k for k in api.konten() if k["extern_id"] == UNKATEGORISIERT]
    assert len(ks) <= 1, f"mehrere Konten mit extern_id {UNKATEGORISIERT}: {ks}"
    return ks[0] if ks else None


def nach_kennung(buchungen: list[dict], praefix: str = "bank:") -> dict[str, dict]:
    aus: dict[str, dict] = {}
    for b in buchungen:
        for e in b["extern_ids"]:
            if e.startswith(praefix):
                assert e not in aus, f"Kennung {e} an zwei Buchungen"
                aus[e] = b
    return aus


def regeln_anlegen(api: Api, regeldatei: dict | None = None, *, konten_anlegen: bool = True) -> dict:
    """Legt Konten (falls nötig), Kategorien und Regeln aus sync/regeln.json an.

    Rückgabe: {"konten": {iban: id}, "kategorien": {name: id}, "regeln": {name: Regel}, "liste": [Regel]}.
    """
    d = regeldatei or lade_regeln()
    vorhanden = konto_nach_iban(api)
    konten: dict[str, int] = {}
    for k in d["konten"]:
        if k["iban"] in vorhanden:
            konten[k["iban"]] = vorhanden[k["iban"]]["id"]
        elif konten_anlegen:
            konten[k["iban"]] = api.konto(k["name"], k["art"], iban=k["iban"])["id"]
    kats = {k["name"]: k["id"] for k in api.konten() if k["art"] in ("aufwand", "ertrag")}
    for k in d["kategorien"]:
        if k["name"] not in kats:
            kats[k["name"]] = api.konto(k["name"], k["art"])["id"]
    regeln: dict[str, dict] = {}
    liste = []
    for r in d["regeln"]:
        bed = [{**b, "wert": konten[b["wert"]["iban"]]} if b["feld"] == "konto_id" else b for b in r["bedingungen"]]
        body = {"name": r["name"], "aktiv": r["aktiv"], "prioritaet": r["prioritaet"],
                "kategorie_id": kats[r["kategorie"]], "bedingungen": bed}
        neu = api.post("/api/regeln", json=body, erwartet=201).daten
        regeln[r["name"]] = neu
        liste.append(neu)
    return {"konten": konten, "kategorien": kats, "regeln": regeln, "liste": liste}


def gegensplit(b: dict, bestand_ids: set[int]) -> dict:
    gs = [s for s in b["splits"] if s["konto_id"] not in bestand_ids]
    assert len(gs) == 1, b
    return gs[0]


def mock_bank(daten: Path | None = SYNC_DATEN, szenario: str = "normal", heute: str = "2024-06-30", **kw):
    return kontor.modul("kontor.plugins.mock_bank").MockBankPlugin(daten, szenario, dt.date.fromisoformat(heute),
                                                                   **kw)


def db_dateien(api: Api) -> list[Path]:
    """Alle Dateien neben der aktiven Datenbank (inkl. -wal, -journal, -shm)."""
    pfad = Path(api.config.aktive_datenbank)
    return sorted(p for p in pfad.parent.iterdir() if p.is_file() and p.name.startswith(pfad.name))


def alle_antworten(api: Api) -> str:
    """Textabzug aller lesenden Endpunkte (für Geheimnissuche)."""
    teile = []
    for pfad in ("/api/status", "/api/sync/status", "/api/sync/laeufe", "/api/sync/konten", "/api/tan-anforderungen",
                 "/api/benachrichtigungen", "/api/konten", "/api/empfaenger", "/api/tags", "/api/dubletten",
                 "/api/importe", "/api/regeln", "/api/kontenuebersicht"):
        teile.append(api.get(pfad, erwartet=200).text)
    teile.append(json.dumps(api.alle_buchungen(), ensure_ascii=False))
    return "\n".join(teile)
