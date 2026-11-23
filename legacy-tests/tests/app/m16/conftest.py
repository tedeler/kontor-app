"""Fixtures der M16-Tests: Browser und Server aus tests/app/conftest.py (wie M8, M11, M15).

Ab M25 (wiederkehrend.md 9.6, E-244): Die M16-Erwartungen gelten mit der Vorgabe des Betragsfilters ``aus``. Jede in
diesen Tests erzeugte App (``Api`` und ``LaufenderServer``) setzt deshalb gleich nach dem Start
``PUT /api/wiederkehrend/einstellungen/vorgabe {"modus": "aus"}``; sonst sind die Tests unverändert.
"""

import pytest

from tests.app.m8.conftest import _erwartung_zeit  # noqa: F401  (autouse, je Test)
from tests.hilfen import m8
from tests.hilfen.api import Api

VORGABE_AUS = {"modus": "aus"}


def vorgabe_aus(api: Api) -> None:
    api.put("/api/wiederkehrend/einstellungen/vorgabe", json=VORGABE_AUS, erwartet=200)


@pytest.fixture(scope="module", autouse=True)
def _m16_vorgabe_aus():
    mp = pytest.MonkeyPatch()
    api_init = Api.__init__
    server_init = m8.LaufenderServer.__init__

    def neu_api(self, *a, **kw):
        api_init(self, *a, **kw)
        vorgabe_aus(self)

    def neu_server(self, *a, **kw):
        server_init(self, *a, **kw)
        vorgabe_aus(self.api)

    mp.setattr(Api, "__init__", neu_api)
    mp.setattr(m8.LaufenderServer, "__init__", neu_server)
    yield
    mp.undo()
