"""Gemeinsame Test-Konfiguration für kontor-tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

# Die Wegwerf-Referenz der Selbstprüfung wird nie normal eingesammelt.
collect_ignore_glob = ["_selbstpruefung/*"]

settings.register_profile(
    "standard",
    max_examples=40,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
settings.register_profile(
    "gruendlich",
    max_examples=400,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
settings.register_profile(
    "schnell",
    max_examples=10,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "standard"))

#: Marker, die der Schnelllauf abwählt (E-175)
SCHNELLLAUF_OHNE = ("leistung", "browser", "langsam")


def ist_schnelllauf(config: pytest.Config) -> bool:
    """Schnelllauf (E-175): ohne ``-m``, ohne ``--voll``/``KONTOR_TESTS_VOLL=1`` und ohne Knoten-IDs."""
    if config.getoption("voll") or os.environ.get("KONTOR_TESTS_VOLL") == "1":
        return False
    if config.getoption("markexpr", ""):
        return False
    return not any("::" in str(a) for a in config.args)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--ohne-app",
        action="store_true",
        default=False,
        help="App-Tests überspringen statt fehlschlagen lassen, wenn das Paket kontor fehlt",
    )
    parser.addoption(
        "--voll",
        action="store_true",
        default=False,
        help="Volllauf (E-175): auch leistung, browser, langsam; Hypothesis-Profil standard",
    )


def pytest_configure(config: pytest.Config) -> None:
    # Schnelllauf (E-175): Hypothesis-Profil schnell, sofern HYPOTHESIS_PROFILE nicht gesetzt ist
    if ist_schnelllauf(config) and "HYPOTHESIS_PROFILE" not in os.environ:
        settings.load_profile("schnell")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    _meilenstein_marker(items)
    if ist_schnelllauf(config):
        behalten, abgewaehlt = [], []
        for item in items:
            (abgewaehlt if any(item.get_closest_marker(m) for m in SCHNELLLAUF_OHNE) else behalten).append(item)
        if abgewaehlt:
            config.hook.pytest_deselected(items=abgewaehlt)
            items[:] = behalten


def _meilenstein_marker(items: list[pytest.Item]) -> None:
    app_dir = Path(__file__).parent / "app"
    attrappen_dir = Path(__file__).parent / "attrappen"
    for item in items:
        pfad = Path(str(item.fspath))
        if attrappen_dir in pfad.parents:
            item.add_marker(pytest.mark.m6)
        if app_dir in pfad.parents:
            item.add_marker(pytest.mark.app)
            # Marker je Meilenstein (E-041, E-058, E-097, E-112, E-125, E-139, E-157, E-176, E-181, E-192, E-206, E-211, E-216, E-221, E-223, E-246, E-249, E-252, E-258; m10 entfallen, E-259): tests/app/*.py = m1, tests/app/m<N>/ = m<N>
            if pfad.parent == app_dir:
                item.add_marker(pytest.mark.m1)
            elif (app_dir / "m2") in pfad.parents:
                item.add_marker(pytest.mark.m2)
            elif (app_dir / "m3") in pfad.parents:
                item.add_marker(pytest.mark.m3)
            elif (app_dir / "m4") in pfad.parents:
                item.add_marker(pytest.mark.m4)
            elif (app_dir / "m5") in pfad.parents:
                item.add_marker(pytest.mark.m5)
            elif (app_dir / "m6") in pfad.parents:
                item.add_marker(pytest.mark.m6)
            elif (app_dir / "m9") in pfad.parents:
                item.add_marker(pytest.mark.m9)
            elif (app_dir / "m7") in pfad.parents:
                item.add_marker(pytest.mark.m7)
            elif (app_dir / "m8") in pfad.parents:
                item.add_marker(pytest.mark.m8)
            elif (app_dir / "m11") in pfad.parents:
                item.add_marker(pytest.mark.m11)
            elif (app_dir / "m12") in pfad.parents:
                item.add_marker(pytest.mark.m12)
            elif (app_dir / "m13") in pfad.parents:
                item.add_marker(pytest.mark.m13)
            elif (app_dir / "m15") in pfad.parents:
                item.add_marker(pytest.mark.m15)
            elif (app_dir / "m16") in pfad.parents:
                item.add_marker(pytest.mark.m16)
            elif (app_dir / "m17") in pfad.parents:
                item.add_marker(pytest.mark.m17)
            elif (app_dir / "m18") in pfad.parents:
                item.add_marker(pytest.mark.m18)
            elif (app_dir / "m19") in pfad.parents:
                item.add_marker(pytest.mark.m19)
            elif (app_dir / "m20") in pfad.parents:
                item.add_marker(pytest.mark.m20)
            elif (app_dir / "m21") in pfad.parents:
                item.add_marker(pytest.mark.m21)
            elif (app_dir / "m22") in pfad.parents:
                item.add_marker(pytest.mark.m22)
            elif (app_dir / "m23") in pfad.parents:
                item.add_marker(pytest.mark.m23)
            elif (app_dir / "m24") in pfad.parents:
                item.add_marker(pytest.mark.m24)
            elif (app_dir / "m25") in pfad.parents:
                item.add_marker(pytest.mark.m25)
            elif (app_dir / "m26") in pfad.parents:
                item.add_marker(pytest.mark.m26)
            elif (app_dir / "m27") in pfad.parents:
                item.add_marker(pytest.mark.m27)
            elif (app_dir / "m28") in pfad.parents:
                item.add_marker(pytest.mark.m28)
            elif (app_dir / "m29") in pfad.parents:
                item.add_marker(pytest.mark.m29)
            elif (app_dir / "m30") in pfad.parents:
                item.add_marker(pytest.mark.m30)
            elif (app_dir / "m31") in pfad.parents:
                item.add_marker(pytest.mark.m31)
            elif (app_dir / "m32") in pfad.parents:
                item.add_marker(pytest.mark.m32)


def pytest_report_header(config: pytest.Config) -> list[str]:
    from tests.hilfen import kontor

    fehler = kontor.app_importfehler()
    if fehler is None:
        import kontor as paket  # noqa: PLC0415 - nur für die Kopfzeile

        version = getattr(paket, "__version__", "?")
        return [f"kontor: installiert, Version {version}, Pfad {getattr(paket, '__file__', '?')}", _laufzeile(config)]
    zeilen = [_laufzeile(config)]
    modus = "werden übersprungen" if kontor.ohne_app(config) else "schlagen fehl (E-024)"
    return [f"kontor: NICHT importierbar ({type(fehler).__name__}) – App-Tests {modus}", *zeilen]


def _laufzeile(config: pytest.Config) -> str:
    profil = settings._current_profile  # noqa: SLF001 - nur für die Kopfzeile
    if ist_schnelllauf(config):
        return (f"Schnelllauf (E-175): ohne {', '.join(SCHNELLLAUF_OHNE)}, Hypothesis-Profil {profil}; "
                "Volllauf mit --voll")
    return f"Volllauf bzw. eigene Auswahl, Hypothesis-Profil {profil}"
