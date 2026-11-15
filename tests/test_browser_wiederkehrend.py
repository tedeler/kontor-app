"""Die Seite „Wiederkehrende Buchungen“ ist aus der Oberfläche genommen (D-146).

Die Erkennung bleibt über die REST-Schnittstelle prüfbar (``test_wiederkehrend_eigen.py``).
"""

from pathlib import Path

import kontor


def test_navigation_ohne_wiederkehrend():
    text = (Path(kontor.__file__).parent / "web" / "index.html").read_text(encoding="utf-8")
    assert 'data-testid="nav-wiederkehrend"' not in text
    assert "/wiederkehrend" not in text
