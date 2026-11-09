"""Export der gefilterten Buchungsliste als CSV und PDF (berichte.md 4, 5, Meilenstein 5). Nur lesend.

- CSV: UTF-8 mit BOM, ``;``, ``\\r\\n``, Quoting wie ``csv.writer`` mit ``QUOTE_MINIMAL``; eine Zeile je Split.
- PDF: ``reportlab`` (reine Python-Bibliothek, Standardschrift Helvetica, keine Schriften aus dem Netz). Je
  Buchung genau eine Textzeile mit der Marke ``[#<id>]``, Datum ``TT.MM.JJJJ`` und Betrag; Texte der Anwender
  werden so bereinigt, dass sie keine Marke und keine Zeile „Anzahl Buchungen:“ vortäuschen können.
"""

from __future__ import annotations

import csv
import io
import json
import re

from . import __version__, buch

SPALTEN = ["buchung_id", "datum", "empfaenger", "verwendungszweck", "status", "kategorie", "tags", "extern_ids",
           "gegen_iban", "split_nr", "split_id", "konto_id", "konto", "betrag", "memo", "abstimmung_id"]


def betrag_text(cent: int) -> str:
    """berichte.md 4.2: Euro mit Dezimalkomma, genau zwei Nachkommastellen, Minus vorangestellt."""
    v = "-" if cent < 0 else ""
    e, c = divmod(abs(cent), 100)
    return f"{v}{e},{c:02d}"


def alle_buchungen(con, f: dict) -> list[dict]:
    """Alle Buchungen der Buchungsliste mit Filtern und Sortierung, ohne Paginierung."""
    erste = buch.buchungsliste(con, {**f, "seite": 1, "pro_seite": 1})
    if erste["gesamt"] == 0:
        return []
    return buch.buchungsliste(con, {**f, "seite": 1, "pro_seite": erste["gesamt"]})["eintraege"]


def csv_bytes(con, f: dict) -> bytes:
    buchungen = alle_buchungen(con, f)
    namen = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM konto")}
    puffer = io.StringIO(newline="")
    w = csv.writer(puffer, delimiter=";", quotechar='"', lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(SPALTEN)
    for b in buchungen:
        kopf = [b["id"], b["datum"], b["empfaenger"]["name"] if b["empfaenger"] else "", b["verwendungszweck"],
                b["status"], namen[b["kategorie_id"]] if b["kategorie_id"] is not None else "",
                json.dumps([t["name"] for t in b["tags"]], ensure_ascii=False),
                json.dumps(b["extern_ids"], ensure_ascii=False), b["gegen_iban"] or ""]
        for nr, s in enumerate(b["splits"], 1):
            w.writerow(kopf + [nr, s["id"], s["konto_id"], namen[s["konto_id"]], betrag_text(s["betrag"]), s["memo"],
                               "" if s["abstimmung_id"] is None else s["abstimmung_id"]])
    return b"\xef\xbb\xbf" + puffer.getvalue().encode("utf-8")


# ===================================================================== PDF

_STEUER = re.compile(r"[\x00-\x1f\x7f-\x9f  ]+")
_ANZAHL = re.compile(r"anzahl\s+buchungen\s*:", re.IGNORECASE)


def _sauber(s: str | None) -> str:
    """Anwendertext für eine PDF-Zeile: ohne Steuerzeichen, ohne Marken-Klammern, ohne „Anzahl Buchungen:“."""
    s = _STEUER.sub(" ", s or "").replace("[", "(").replace("]", ")")
    return _ANZAHL.sub("Anzahl Buchungen -", s).strip()


def _de(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def pdf_bytes(con, f: dict, heute: str, beschreibung: str) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    buchungen = alle_buchungen(con, f)
    namen = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM konto")}
    puffer = io.BytesIO()
    breite, hoehe = landscape(A4)
    rand = 36
    c = canvas.Canvas(puffer, pagesize=(breite, hoehe), invariant=1, pageCompression=1)
    c.setTitle("Kontor – Buchungen")
    c.setCreator(f"Kontor {__version__}")
    schrift, groesse, zeile = "Helvetica", 8, 11
    seite = [0]

    def kopf() -> float:
        seite[0] += 1
        c.setFont("Helvetica-Bold", 12)
        c.drawString(rand, hoehe - rand, "Kontor – Buchungen")
        c.setFont(schrift, groesse)
        c.drawRightString(breite - rand, hoehe - rand, f"Stand {_de(heute)} · Seite {seite[0]}")
        y = hoehe - rand - 16
        if seite[0] == 1:
            c.drawString(rand, y, _sauber(beschreibung)[:200])
            y -= zeile
            summe = sum(b["betrag"] for b in buchungen)
            c.drawString(rand, y, f"Anzahl Buchungen: {len(buchungen)}")
            c.drawString(rand + 160, y, f"Summe der Beträge: {betrag_text(summe)} EUR")
            y -= zeile
        c.setFont("Helvetica-Bold", groesse)
        c.drawString(rand, y, "Nr. / Datum / Betrag (EUR) / Empfänger / Verwendungszweck / Kategorie / Status")
        c.setFont(schrift, groesse)
        return y - zeile * 1.4

    y = kopf()
    platz = breite - 2 * rand
    for b in buchungen:
        if y < rand:
            c.showPage()
            y = kopf()
        fest = f"[#{b['id']}]  {_de(b['datum'])}  {betrag_text(b['betrag'])}"
        rest = "  ".join(x for x in (
            _sauber(b["empfaenger"]["name"] if b["empfaenger"] else "–"), _sauber(b["verwendungszweck"]),
            _sauber(namen[b["kategorie_id"]]) if b["kategorie_id"] is not None else "",
            b["status"]) if x)
        text = f"{fest}  {rest}"
        if stringWidth(text, schrift, groesse) > platz:
            # kürzen, bis die Zeile passt (die Marke mit Datum und Betrag bleibt immer vollständig)
            lo, hi = 0, len(rest)
            while lo < hi:
                mitte = (lo + hi + 1) // 2
                if stringWidth(f"{fest}  {rest[:mitte]}…", schrift, groesse) <= platz:
                    lo = mitte
                else:
                    hi = mitte - 1
            text = f"{fest}  {rest[:lo]}…"
        c.drawString(rand, y, text)
        y -= zeile
    c.showPage()
    c.save()
    return puffer.getvalue()


__all__ = ["csv_bytes", "pdf_bytes", "betrag_text"]
