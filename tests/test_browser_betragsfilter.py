"""Der Betragsfilter wiederkehrender Buchungen ist aus den Einstellungen genommen (D-146).

Die REST-Prüfung bleibt in ``test_betragsfilter_eigen.py``.
"""

from pathlib import Path

import kontor


def test_einstellungen_ohne_betragsfilter():
    text = (Path(kontor.__file__).parent / "web" / "oeffentlich" / "app" / "seiten.js").read_text(encoding="utf-8")
    assert "wk-vorgabe-modus" not in text
    assert "/api/wiederkehrend/einstellungen" not in text
