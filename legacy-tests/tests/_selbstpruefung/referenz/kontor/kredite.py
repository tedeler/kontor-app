"""Tilgungsplan als Python-Funktion (python-api.md 12.3) der Wegwerf-Referenz. KEIN Anwendungscode."""

from __future__ import annotations

import datetime as dt

from pydantic import ValidationError

from .buch import Fehler
from .fehler import KreditRateZuKlein


def tilgungsplan(parameter) -> dict:
    from .m5 import Parameter, _sortiert, plan, pruefe_parameter

    p = {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in dict(parameter).items()}
    if isinstance(p.get("sondertilgungen"), list):
        p["sondertilgungen"] = [{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in dict(s).items()}
                                for s in p["sondertilgungen"]]
    try:
        x = Parameter(**p).model_dump()
    except (ValidationError, TypeError) as e:
        raise ValueError(str(e)) from None
    x["sondertilgungen"] = _sortiert(x["sondertilgungen"])
    try:
        pruefe_parameter(x)
        return plan(x)
    except Fehler as f:
        if f.code == "kredit_rate_zu_klein":
            raise KreditRateZuKlein(f.meldung) from None
        raise ValueError(f.meldung) from None
