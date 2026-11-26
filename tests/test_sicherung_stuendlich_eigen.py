"""Eigene Tests zu den Sicherungspunkten (D-302), die für die Core-Tests zu lang laufen."""

from __future__ import annotations

import datetime as dt

from kontor import sicherungspunkte as sp
from tests.core.test_sicherung_stuendlich import UTC, punkte, umgebung  # noqa: F401 - Fixture


def test_ausduennen_ueber_siebzig_tage_mit_vorgaben(umgebung):
    config, c, buchen = umgebung
    zeiten = []
    t = dt.datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    # 70 Tage, je Tag zwei Punkte mit Änderung
    for tag in range(70):
        for stunde in (8, 20):
            zeit = t + dt.timedelta(days=tag, hours=stunde - 8)
            buchen(tag * 10 + stunde)
            sp.stunde(config, jetzt=zeit, ausduennen=False)
            zeiten.append(zeit)
    jetzt = zeiten[-1]
    sp.ausduennen(config, jetzt=jetzt)
    p = punkte(c)["punkte"]
    behalten = sorted(dt.datetime.fromisoformat(x["zeitpunkt"].replace("Z", "+00:00")) for x in p)
    letzte_48h = [z for z in zeiten if jetzt - z <= dt.timedelta(hours=48)]
    assert all(z in behalten for z in letzte_48h)
    tage = {z.date() for z in behalten if dt.timedelta(hours=48) < jetzt - z <= dt.timedelta(days=30)}
    assert all(z.replace(hour=20) in behalten for z in zeiten if dt.timedelta(days=3) < jetzt - z <= dt.timedelta(days=29))
    assert len(tage) >= 27
    alt = [z for z in behalten if jetzt - z > dt.timedelta(days=30)]
    assert len(alt) <= 6   # nur Wochenpunkte (und der Anker-Monatsanfang wird aufgelöst)
    assert len(behalten) < len(zeiten) / 2
    for x in p:
        assert sp.herstellen_pruefen(config, x["kennung"]) is True
        assert x["groesse_herstellen"] <= sum(y["groesse"] for y in p)
    # Ketten bleiben kurz: höchstens Anker → Tagespunkt → Stundenpunkte
    assert max(sp.kettenlaenge(config, x["kennung"]) for x in p) <= 2 + len(letzte_48h)
