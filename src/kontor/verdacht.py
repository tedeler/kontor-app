"""Verdächtige Buchungen (D-157).

Eine unbestätigte Buchung bekommt ein Label, wenn ihr Empfänger nur in unbestätigten
Buchungen vorkommt oder ihr Zahlungsbetrag stark von der Streuung der bestätigten
Buchungen dieses Empfängers abweicht. Bestätigte und abgeglichene Buchungen tragen
kein Label. Die Einschätzung wird beim Lesen gebildet und nicht gespeichert.
"""

from __future__ import annotations

from collections import defaultdict

from . import buch
from .statistik import AUSREISSER_HUNDERTSTEL, _mad, _median, _z_hundertstel

BESTAETIGT = frozenset({"bestaetigt", "abgeglichen"})
MIN_BEKANNT = 4
RELATIV_PROZENT = 50
MIN_DIFF = 2_000  # Cent; kleinere Sprünge bei identischen Beträgen gelten nicht als stark


def euro(cent: int) -> str:
    e, c = divmod(abs(cent), 100)
    return f"{'-' if cent < 0 else ''}{e:,}".replace(",", ".") + f",{c:02d} €"


def _z_text(z: int) -> str:
    return f"{z // 100},{z % 100:02d}"


def anreichern(con, buchungen: list[dict]) -> None:
    """Setzt ``verdacht`` nur an unbestätigten Buchungen, auf die eine der beiden Regeln zutrifft."""
    offen = [b for b in buchungen if b.get("empfaenger") and b.get("status") not in BESTAETIGT]
    if not offen:
        return
    lage = _lage(con, sorted({b["empfaenger"]["id"] for b in offen}))
    for b in offen:
        urteil = _urteil(b, lage.get(b["empfaenger"]["id"], []))
        if urteil is not None:
            grund, text = urteil
            b["verdacht"] = {"grund": grund, "text": text}


def _lage(con, empf_ids: list[int]) -> dict[int, list[dict]]:
    """Je Empfänger alle Buchungen mit dem Zahlungsbetrag auf genau einem Giro- oder Sparkonto."""
    aus: dict[int, list[dict]] = defaultdict(list)
    for teil in buch._stueckweise(empf_ids):
        ph = buch._platzhalter(len(teil))
        sql = (
            "SELECT b.id AS id, b.empfaenger_id AS eid, b.status AS status, e.name AS name,"
            " COUNT(DISTINCT CASE WHEN k.art IN ('girokonto','sparkonto') THEN s.konto_id END) AS n,"
            " COALESCE(SUM(CASE WHEN k.art IN ('girokonto','sparkonto') THEN s.betrag ELSE 0 END), 0) AS summe"
            " FROM buchung b JOIN empfaenger e ON e.id = b.empfaenger_id"
            " LEFT JOIN split s ON s.buchung_id = b.id LEFT JOIN konto k ON k.id = s.konto_id"
            f" WHERE b.empfaenger_id IN ({ph}) GROUP BY b.id"
        )
        for r in con.execute(sql, teil):
            aus[r["eid"]].append({"id": r["id"], "status": r["status"], "name": r["name"],
                                  "betrag": r["summe"] if r["n"] == 1 else None})
    return aus


def _urteil(b: dict, eintraege: list[dict]) -> tuple[str, str] | None:
    name = b["empfaenger"]["name"]
    bekannt = [e for e in eintraege if e["status"] in BESTAETIGT]
    if not bekannt:
        n = len(eintraege) or 1
        return "empfaenger", (f"Der Empfänger „{name}“ kommt nur in unbestätigten Buchungen vor "
                              f"({n} {'Buchung' if n == 1 else 'Buchungen'}).")
    werte = [e["betrag"] for e in bekannt if e["betrag"] is not None]
    if len(werte) < MIN_BEKANNT:
        return None
    eigen = next((e["betrag"] for e in eintraege if e["id"] == b["id"]), None)
    if eigen is None:
        return None
    mitte, mad = _median(werte), _mad(werte, _median(werte))
    if mad == 0:
        diff = abs(eigen - mitte)
        if diff * 100 > abs(mitte) * RELATIV_PROZENT and diff >= MIN_DIFF:
            return "betrag", (f"Der Betrag {euro(eigen)} weicht stark von den bekannten Buchungen von „{name}“ ab. "
                              f"Alle {len(werte)} bestätigten Zahlungen lauten auf {euro(mitte)}.")
        return None
    z = _z_hundertstel(eigen, mitte, mad)
    if z is None or z >= AUSREISSER_HUNDERTSTEL:
        zteil = "ohne messbare Streuung" if z is None else f"robustes z {_z_text(z)}"
        return "betrag", (f"Der Betrag {euro(eigen)} weicht stark von den bekannten Buchungen von „{name}“ ab "
                          f"(Median {euro(mitte)}, Streuung {euro(mad)}, {zteil}, "
                          f"{len(werte)} bestätigte Buchungen).")
    return None
