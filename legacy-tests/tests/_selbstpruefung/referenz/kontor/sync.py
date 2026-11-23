"""kontor.sync laut python-api.md 8.3 (Wegwerf-Referenz)."""

from __future__ import annotations

import copy


def planer_takt(app) -> dict | None:
    lauf = app.state.dienst.takt()
    return copy.deepcopy(lauf) if lauf is not None else None
