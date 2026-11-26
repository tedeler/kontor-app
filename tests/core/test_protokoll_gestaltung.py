"""Core-Tests zum Feature „protokoll-gestaltung“ (D-294): Jede Aktion des Änderungsprotokolls hat eine lesbare
Beschreibung; die Liste lässt sich nach Quellen filtern, wie die neue Ansicht es nutzt."""

from __future__ import annotations

import pathlib
import re

from kontor import protokoll

QUELLE = pathlib.Path(protokoll.__file__).parent


def test_jede_benutzte_aktion_hat_eine_beschreibung():
    texte = "\n".join(p.read_text(encoding="utf-8") for p in QUELLE.rglob("*.py"))
    benutzt = set(re.findall(r'protokolliert\(\s*con,\s*"[a-z]+",\s*"([a-z_]+)"', texte))
    benutzt |= set(re.findall(r'aendern\(\s*(?:con,\s*)?"[a-z]+",\s*"([a-z_]+)"', texte))
    assert "sync_saldoausgleich" in benutzt, "Suchmuster passt nicht mehr"
    fehlend = sorted(a for a in benutzt if a not in protokoll.BESCHREIBUNG)
    assert not fehlend, f"ohne Beschreibung: {fehlend}"
    assert all(not re.fullmatch(r"[a-z_]+", t) for t in protokoll.BESCHREIBUNG.values())


def test_liste_nach_mehreren_quellen_filtern(client):
    konto = client.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()
    client.post("/api/tags", json={"name": "Urlaub"})
    alle = client.get("/api/aenderungen").json()
    assert alle["gesamt"] == 2 and {a["quelle"] for a in alle["eintraege"]} == {"manuell"}
    leer = client.get("/api/aenderungen?quelle=sync&quelle=regeln").json()
    assert leer == {**leer, "gesamt": 0, "eintraege": []}
    client.post(f"/api/aenderungen/{alle['eintraege'][0]['id']}/rueckgaengig")
    beide = client.get("/api/aenderungen?quelle=manuell&quelle=rueckgaengig").json()
    assert beide["gesamt"] == 3
    nur = client.get("/api/aenderungen?quelle=rueckgaengig").json()
    assert [a["quelle"] for a in nur["eintraege"]] == ["rueckgaengig"] and nur["eintraege"][0]["rueckgaengig_von"]
    assert konto["id"]
