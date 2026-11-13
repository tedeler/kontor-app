"""D-142: statische Dateien werden bei jedem Abruf geprüft (kein Zeigen alter Stände nach einem Update)."""
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


def test_statische_dateien_no_cache(tmp_path):
    client = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True)))
    for pfad in ("/oeffentlich/app.css", "/oeffentlich/app/haupt.js", "/oeffentlich/app/seiten.js"):
        r = client.get(pfad)
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache", pfad
        assert r.headers.get("etag"), pfad
        r2 = client.get(pfad, headers={"If-None-Match": r.headers["etag"]})
        assert r2.status_code == 304, pfad
        assert r2.headers["cache-control"] == "no-cache", pfad
