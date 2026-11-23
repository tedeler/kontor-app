"""M28: Routen ohne Browser (oberflaeche.md 37.3; E-252, E-255). Nicht kern (Definition: neue Tests nicht kern)."""

from __future__ import annotations

import pytest

from tests.hilfen.api import neue_api


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    return neue_api(tmp_path_factory.mktemp("m28"), mock_modus=True)


@pytest.mark.parametrize("pfad", ["/mail", "/mail?postfach=1&filter=erwartet&seite=2&id=3"])   # /statistik: E-298
def test_neue_routen_liefern_die_huelle(api, pfad):
    r = api.get(pfad)
    assert r.status_code == 200
    assert r.headers["content-type"].split(";")[0].strip() == "text/html"
    assert r.text == api.get("/").text


@pytest.mark.parametrize("pfad", ["/wiederkehrend", "/wiederkehrend?x=1"])
def test_wiederkehrend_404_ohne_huelle(api, pfad):
    r = api.get(pfad)
    assert r.status_code == 404
    assert r.text != api.get("/").text


def test_rest_der_erkennung_bleibt(api):
    assert api.get("/api/wiederkehrend", erwartet=200).daten is not None
