"""Eigene Tests von kontor-app; gemeinsame Fixtures, Marker und Zeitbudget (TESTUMBAU.md)."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig

from kontor import version as _version

# ---------------------------------------------------------------------------------------------------------------
# Tempo: Starlettes TestClient startet sonst für jede einzelne Anfrage einen Thread mit eigener Ereignisschleife
# (rund die Hälfte der Laufzeit einer Anfrage, TESTUMBAU.md). Alle Clients eines Testprozesses teilen sich
# deshalb eine Schleife; ``with TestClient(app)`` (Lifespan) benutzt weiter seine eigene.
_PORTAL = None
_client_init = TestClient.__init__


def _gemeinsames_portal():
    global _PORTAL
    if _PORTAL is None:
        import atexit

        import anyio.from_thread

        cm = anyio.from_thread.start_blocking_portal(backend="asyncio")
        _PORTAL = cm.__enter__()
        atexit.register(cm.__exit__, None, None, None)
    return _PORTAL


def _init_mit_portal(self, *args, **kw):
    _client_init(self, *args, **kw)
    self.portal = _gemeinsames_portal()


TestClient.__init__ = _init_mit_portal

# Die Tests hängen nicht vom Git-Branch des Checkouts ab: Ohne ausdrücklichen Startpfad meldet ``version.zweig``
# keinen Branch (wie auf main bzw. in einem Release). Tests des Branch-Hinweises setzen ihn selbst.
_zweig_echt = _version.zweig
_version.zweig = lambda start=None: _zweig_echt(start) if start is not None else None

KMY_KOPF = '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE KMYMONEY-FILE>\n'


def kmy(konten: str = "", payees: str = "", tags: str = "", transaktionen: str = "", gz: bool = True) -> bytes:
    """Baut eine kleine synthetische KMyMoney-Datei."""
    xml = (KMY_KOPF + "<KMYMONEY-FILE>"
           f"<PAYEES>{payees}</PAYEES><TAGS>{tags}</TAGS>"
           '<ACCOUNTS><ACCOUNT id="AStd::Asset" name="Anlage" type="9" parentaccount="" currency="EUR"/>'
           '<ACCOUNT id="AStd::Expense" name="Ausgabe" type="13" parentaccount="" currency="EUR"/>'
           f"{konten}</ACCOUNTS><TRANSACTIONS>{transaktionen}</TRANSACTIONS></KMYMONEY-FILE>").encode("utf-8")
    return gzip.compress(xml, mtime=0) if gz else xml


GIRO = ('<ACCOUNT id="A1" name="Giro" type="1" parentaccount="AStd::Asset" currency="EUR">'
        '<KEYVALUEPAIRS><PAIR key="iban" value="DE57 0000 0000 0532 0130 00"/></KEYVALUEPAIRS></ACCOUNT>'
        '<ACCOUNT id="A2" name="Lebensmittel" type="13" parentaccount="AStd::Expense" currency="EUR"/>')


def transaktion(tid: str, datum: str, *splits: tuple[str, str], memo: str = "") -> str:
    s = "".join(f'<SPLIT account="{k}" value="{v}" memo=""/>' for k, v in splits)
    return f'<TRANSACTION id="{tid}" postdate="{datum}" memo="{memo}" commodity="EUR"><SPLITS>{s}</SPLITS></TRANSACTION>'


@pytest.fixture
def config(tmp_path: Path) -> KontorConfig:
    return KontorConfig(datenbank=tmp_path / "kontor.sqlite3")


@pytest.fixture
def client(config) -> TestClient:
    return TestClient(create_app(config))


@pytest.fixture(scope="session")
def auslieferung(tmp_path_factory) -> TestClient:
    """Eine App für den ganzen Lauf, nur zum Lesen ausgelieferter Dateien (Hülle, Stile, Module). Spart den Aufbau
    einer App je Test (rund 0,2 s); Tests mit Anfragen an den Buchbestand nehmen ``client``."""
    return TestClient(create_app(KontorConfig(datenbank=tmp_path_factory.mktemp("auslieferung") / "kontor.sqlite3")))


@pytest.fixture
def mock_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "kontor.sqlite3", mock_modus=True)))


# ---------------------------------------------------------------------------------------------------------------
# Marker und Zeitbudget (TESTUMBAU.md): tests/core = ``core`` (Entwicklungsschleife, zusammen höchstens
# CORE_BUDGET_SEKUNDEN), tests/test_browser*.py = ``browser`` (eigener CI-Job).
CORE_BUDGET_SEKUNDEN = 30.0
_core_dauer: dict[str, float] = {}


def pytest_collection_modifyitems(config, items):
    core = Path(__file__).parent / "core"
    for item in items:
        pfad = Path(str(item.fspath))
        if core in pfad.parents:
            item.add_marker(pytest.mark.core)
        if pfad.name.startswith("test_browser"):
            item.add_marker(pytest.mark.browser)


def pytest_runtest_logreport(report):
    if report.skipped:
        _uebersprungen.append(report.nodeid)
    if "/core/" in report.nodeid.replace("\\", "/"):
        _core_dauer[report.nodeid] = _core_dauer.get(report.nodeid, 0.0) + report.duration


def pytest_sessionfinish(session, exitstatus):
    summe = sum(_core_dauer.values())
    if summe > CORE_BUDGET_SEKUNDEN and getattr(session.config, "workerinput", None) is None:
        langsam = sorted(_core_dauer.items(), key=lambda x: -x[1])[:5]
        print(f"\nCore-Tests über dem Zeitbudget: {summe:.1f} s statt höchstens {CORE_BUDGET_SEKUNDEN:.0f} s. "
              "Langsamste: " + ", ".join(f"{n.split('::')[-1]} {d:.1f} s" for n, d in langsam))
        if session.exitstatus == 0:
            session.exitstatus = 1
    _pflicht_pruefen(session)


# ---------------------------------------------------------------------------------------------------------------
# Browser-Job der CI: Mit KONTOR_TESTS_BROWSER_PFLICHT=1 ist ein übersprungener Test ein Fehler, damit ein
# fehlender Browser nicht unbemerkt alle Browsertests ausfallen lässt.
_uebersprungen: list[str] = []


def _pflicht() -> bool:
    import os
    return os.environ.get("KONTOR_TESTS_BROWSER_PFLICHT") == "1"


def pytest_collectreport(report):
    if report.skipped:
        _uebersprungen.append(report.nodeid)


def _pflicht_pruefen(session):
    if _pflicht() and _uebersprungen and getattr(session.config, "workerinput", None) is None:
        print(f"\nKONTOR_TESTS_BROWSER_PFLICHT: {len(_uebersprungen)} Tests übersprungen, z. B. {_uebersprungen[0]}")
        if session.exitstatus == 0:
            session.exitstatus = 1
