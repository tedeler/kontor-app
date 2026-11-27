"""Nachweis markierter Buchungen als PDF im Stil eines Kontoauszugs (Feature ``nachweis-pdf``). Nur lesend.

Der Nachweis zeigt Kontoinhaber, Kontoart, BIC (falls bekannt), Auszugsdatum (Tag der Erstellung) und je Buchung
Datum, Empfänger, Verwendungszweck und Betrag, am Ende die Summe der Buchungen. Kontostände kommen nicht vor. Von der
IBAN bleiben nur Ländercode, Prüfziffer und die letzten vier Stellen; der Rest wird nie in die Datei geschrieben.

Der Auszug weist sich als Auszug aus der Homebanking-Software aus, trägt kein Banklogo und kennzeichnet Buchungen, die
nicht von der Bank stammen oder nach dem Abruf geändert wurden.

Seit D-310 auch aus dem Kontoblatt einer Kategorie („Buchungsnachweis“): Buchungen der Kategorie oder ihrer
Unterkategorien, Betrag = Anteil der Kategorie aus Sicht des Bankkontos, je Buchung das Bankkonto mit gekürzter IBAN.
"""

from __future__ import annotations

import io
import re

from . import __version__, bankumsatz, bankzugang, buch
from .validierung import ApiFehler

MAX_BUCHUNGEN = 500
MAX_INHABER = 200

HINWEIS = ("Auszug aus der Homebanking-Software Kontor – kein Dokument der Bank. Enthalten sind nur ausgewählte "
           "Buchungen; die IBAN ist gekürzt.")

_STEUER = re.compile(r"[\x00-\x1f\x7f-\x9f   ]+")


def _sauber(s: str | None) -> str:
    return _STEUER.sub(" ", s or "").strip()


def iban_maskiert(iban: str) -> str:
    """Ländercode und Prüfziffer sowie die letzten vier Stellen bleiben; dazwischen immer vier Gruppen „XXXX“,
    damit auch die Länge der IBAN nicht erkennbar ist. (Kein „•“: Die Standardschrift des PDF kodiert es so, dass
    es beim Kopieren als Steuerzeichen herauskommt.)"""
    n = re.sub(r"\s+", "", iban or "").upper()
    if not n:
        return "–"
    if len(n) < 9:
        return "XXXX XXXX XXXX XXXX"
    return f"{n[:4]} XXXX XXXX XXXX XXXX {n[-4:]}"


def betrag_text(cent: int) -> str:
    """Euro mit Tausenderpunkten und Dezimalkomma, Vorzeichen „+“/„-“; nur Ganzzahlarithmetik."""
    e, c = divmod(abs(cent), 100)
    gruppen = f"{e:,}".replace(",", ".")
    return f"{'-' if cent < 0 else '+' if cent > 0 else ''}{gruppen},{c:02d}"


def _de(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def _umbrechen(text: str, schrift: str, groesse: float, platz: float, max_zeilen: int = 4) -> list[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    zeilen: list[str] = []
    akt = ""
    for w in text.split():
        probe = f"{akt} {w}".strip()
        if stringWidth(probe, schrift, groesse) <= platz:
            akt = probe
            continue
        if akt:
            zeilen.append(akt)
        while stringWidth(w, schrift, groesse) > platz:   # überlange Wörter hart trennen
            n = len(w)
            while n > 1 and stringWidth(w[:n], schrift, groesse) > platz:
                n -= 1
            zeilen.append(w[:n])
            w = w[n:]
        akt = w
    if akt:
        zeilen.append(akt)
    if len(zeilen) > max_zeilen:
        zeilen = zeilen[:max_zeilen]
        zeilen[-1] = zeilen[-1][:-1] + "…"
    return zeilen or [""]


def _kuerzen(text: str, schrift: str, groesse: float, platz: float) -> str:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    while stringWidth(text, schrift, groesse) > platz and len(text) > 2:
        text = text[:-2] + "…"
    return text


def pdf_bytes(*, inhaber: str, iban: str, bic: str | None, kontoart: str, datum: str,
              buchungen: list[dict], kategorie: dict | None = None) -> bytes:
    """``buchungen``: Liste von {datum, empfaenger, verwendungszweck, betrag (Cent), hinweis (Text oder ""),
    optional zusatz (Liste kleiner Zeilen)}, bereits sortiert. ``kategorie`` = {pfad, konten} für den
    Buchungsnachweis einer Kategorie (D-310). Zwei Durchläufe, damit jede Seite „Seite n von m“ tragen kann."""
    _, seiten = _zeichnen(inhaber, iban, bic, kontoart, datum, buchungen, 0, kategorie)
    daten, _ = _zeichnen(inhaber, iban, bic, kontoart, datum, buchungen, seiten, kategorie)
    return daten


def _zeichnen(inhaber, iban, bic, kontoart, datum, buchungen, gesamt, kategorie=None) -> tuple[bytes, int]:  # noqa: C901
    # C901: eine Zeichenfolge von oben nach unten; die Teile teilen sich Lage und Canvas
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    puffer = io.BytesIO()
    breite, hoehe = A4
    rand = 56
    rechts = breite - rand
    c = canvas.Canvas(puffer, pagesize=A4, invariant=1, pageCompression=1)
    dokument = "Buchungsnachweis" if kategorie else "Kontoauszug"
    c.setTitle(f"{dokument} – Auszug aus Kontor")
    c.setCreator(f"Kontor {__version__}")
    c.setAuthor("")
    c.setSubject("")
    tinte, grau, hell, linie, haar = (HexColor("#111827"), HexColor("#4b5563"), HexColor("#6b7280"),
                                      HexColor("#111827"), HexColor("#e5e7eb"))
    akzent, warn = HexColor("#1e3a5f"), HexColor("#b45309")
    x_text, spalte_betrag = rand + 78, 96
    text_platz = rechts - spalte_betrag - x_text
    seite = [0]

    def etikett(x: float, y: float, text: str, rechtsbuendig: bool = False) -> None:
        c.setFont("Helvetica", 6.5)
        c.setFillColor(hell)
        if rechtsbuendig:
            c.drawRightString(x, y, text.upper(), charSpace=0.8)
        else:
            c.drawString(x, y, text.upper(), charSpace=0.8)

    def fuss() -> None:
        c.setStrokeColor(haar)
        c.setLineWidth(0.5)
        c.line(rand, 64, rechts, 64)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(hell)
        for i, z in enumerate(_umbrechen(HINWEIS, "Helvetica", 6.5, rechts - rand - 70, 3)):
            c.drawString(rand, 52 - i * 8.5, z)
        c.drawRightString(rechts, 52, f"Seite {seite[0]} von {max(gesamt, seite[0])}")

    def tabellenkopf(y: float) -> float:
        etikett(rand, y, "Buchungstag")
        etikett(x_text, y, "Empfänger / Verwendungszweck")
        etikett(rechts, y, "Betrag in EUR", True)
        c.setStrokeColor(linie)
        c.setLineWidth(0.75)
        c.line(rand, y - 6, rechts, y - 6)
        return y - 22

    def kopf() -> float:
        seite[0] += 1
        c.setFillColor(akzent)
        c.rect(0, hoehe - 6, breite, 6, stroke=0, fill=1)
        y = hoehe - 44
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(akzent)
        c.drawString(rand, y, "KONTOR", charSpace=2)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(hell)
        c.drawString(rand + 52, y, "Homebanking-Software")
        etikett(rechts - 56, y, "Auszugsdatum", True)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(tinte)
        c.drawRightString(rechts, y, _de(datum))
        y -= 40
        if seite[0] == 1:
            c.setFont("Helvetica", 24)
            c.setFillColor(tinte)
            c.drawString(rand, y, dokument)
            c.setFont("Helvetica", 9)
            c.setFillColor(grau)
            c.drawString(rand, y - 18, "Ausgewählte Buchungen einer Kategorie · kein Dokument der Bank" if kategorie
                         else "Nachweis ausgewählter Buchungen · kein Dokument der Bank")
            y -= 44
            c.setStrokeColor(haar)
            c.setLineWidth(0.5)
            c.line(rand, y, rechts, y)
            spalten = (((rand, "Kontoinhaber", _sauber(inhaber) or "–", 150),
                        (rand + 160, "Kategorie", _sauber(kategorie["pfad"]), 168),
                        (rand + 336, "Bankkonten", _sauber(kategorie["konten"]) or "–", rechts - rand - 336))
                       if kategorie else
                       ((rand, "Kontoinhaber", _sauber(inhaber) or "–", 150),
                        (rand + 160, "IBAN", iban_maskiert(iban), 168),
                        (rand + 336, "BIC", _sauber(bic) or "–", 78),
                        (rand + 422, "Konto", kontoart, rechts - rand - 422)))
            for x, titel, wert, platz in spalten:
                etikett(x, y - 16, titel)
                c.setFont("Helvetica", 9.5)
                c.setFillColor(tinte)
                c.drawString(x, y - 30, _kuerzen(wert, "Helvetica", 9.5, platz))
            y -= 44
            c.line(rand, y, rechts, y)
            y -= 34
        else:
            c.setFont("Helvetica", 11)
            c.setFillColor(tinte)
            c.drawString(rand, y, f"{dokument} (Fortsetzung)")
            y -= 30
        return tabellenkopf(y)

    y = kopf()
    for b in buchungen:
        zweck = _umbrechen(_sauber(b["verwendungszweck"]) or "–", "Helvetica", 8.5, text_platz)
        hinweis = _sauber(b.get("hinweis"))
        zusatz = [_kuerzen(_sauber(z), "Helvetica", 7.5, text_platz) for z in b.get("zusatz", ()) if _sauber(z)]
        hoehe_eintrag = 12 + 11 * len(zweck) + 10 * len(zusatz) + (12 if hinweis else 0) + 8
        if y - hoehe_eintrag < 86:
            fuss()
            c.showPage()
            y = kopf()
        oben = y
        c.setFont("Helvetica", 9)
        c.setFillColor(tinte)
        c.drawString(rand, y, _de(b["datum"]))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x_text, y, _kuerzen(_sauber(b["empfaenger"]) or "–", "Helvetica-Bold", 9, text_platz))
        c.setFont("Helvetica", 9.5)
        c.drawRightString(rechts, y, betrag_text(b["betrag"]))
        yy = y - 12
        c.setFont("Helvetica", 8.5)
        c.setFillColor(grau)
        for z in zweck:
            c.drawString(x_text, yy, z)
            yy -= 11
        c.setFont("Helvetica", 7.5)
        c.setFillColor(hell)
        for z in zusatz:
            c.drawString(x_text, yy, z)
            yy -= 10
        if hinweis:
            yy -= 1
            c.setFont("Helvetica-Oblique", 7.5)
            c.setFillColor(warn)
            c.drawString(x_text, yy, f"Hinweis: {hinweis}")
            yy -= 11
        if hinweis:   # schmaler Balken links markiert die Buchung
            c.setFillColor(warn)
            c.rect(rand - 10, yy + 7, 2, oben - yy + 2, stroke=0, fill=1)
        c.setStrokeColor(haar)
        c.setLineWidth(0.5)
        c.line(rand, yy + 3, rechts, yy + 3)
        y = yy - 11
    if y < 100:
        fuss()
        c.showPage()
        y = kopf()
    summe = sum(b["betrag"] for b in buchungen)
    c.setStrokeColor(linie)
    c.setLineWidth(0.75)
    c.line(rand, y + 8, rechts, y + 8)
    y -= 8
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(tinte)
    anzahl = len(buchungen)
    c.drawString(rand, y, f"Summe der {anzahl} ausgewählten Buchung{'' if anzahl == 1 else 'en'}")
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(rechts, y, betrag_text(summe))
    fuss()
    c.showPage()
    c.save()
    return puffer.getvalue(), seite[0]


# ===================================================================== Daten

KATEGORIE = ("aufwand", "ertrag")


def _konto(con, konto_id: int) -> dict:
    k = buch.konto_lesen(con, konto_id)
    if k["art"] not in buch.BESTAND and k["art"] not in KATEGORIE:
        raise ApiFehler(422, "kein_bestandskonto", "Ein Nachweis ist nur für Bankkonten und Kategorien möglich.")
    return k


def angaben(con, konto_id: int) -> dict:
    """Vorbelegung des Dialogs: Kontoinhaber und BIC aus den Kontodaten, die die Bank gemeldet hat. Für eine Kategorie
    (D-310) der erste bekannte Kontoinhaber eines Bankkontos, ohne BIC."""
    k = _konto(con, konto_id)
    gemeldet = bankzugang.konten(con)
    if k["art"] in KATEGORIE:
        ibans = {r["iban"] for r in con.execute("SELECT iban FROM konto WHERE iban IS NOT NULL AND iban != ''")}
        inhaber = next((str(x["inhaber"]) for x in gemeldet if x.get("iban") in ibans and x.get("inhaber")), "")
        return {"inhaber": inhaber, "bic": None}
    bank = next((x for x in gemeldet if k["iban"] and x.get("iban") == k["iban"]), {})
    return {"inhaber": str(bank.get("inhaber") or ""), "bic": bank.get("bic") or None}


_FELDER = (("datum", "Datum"), ("empfaenger", "Empfänger"), ("verwendungszweck", "Verwendungszweck"),
           ("betrag", "Betrag"))


def hinweis(con, b: dict, konto: dict) -> str:
    """Leer, wenn die Buchung so auf dem Nachweis steht, wie die Bank den Umsatz geliefert hat; sonst ein kurzer
    Hinweis. Maßstab ist ``bank_umsatz`` (D-303), nicht das Änderungsprotokoll (wird gekürzt, D-302)."""
    praefix = f"bank:{konto['iban']}:" if konto["iban"] else None
    kennungen = [k for k in b["extern_ids"] if praefix and k.startswith(praefix)]
    if not kennungen:
        return "Nicht von der Bank abgerufen (von Hand erfasst oder importiert)"
    bank = bankumsatz.lesen(con, kennungen)
    if bank is None:
        return "Abgleich mit dem Umsatz der Bank nicht möglich"
    jetzt = {"datum": b["datum"], "empfaenger": (b["empfaenger"] or {}).get("name", ""),
             "verwendungszweck": b["verwendungszweck"], "betrag": b["betrag"]}
    abweichend = [text for feld, text in _FELDER if jetzt[feld] != bank[feld]]
    return f"Weicht vom Umsatz der Bank ab: {', '.join(abweichend)}" if abweichend else ""


_KONTOART = {"girokonto": "Girokonto", "sparkonto": "Sparkonto", "kreditkonto": "Kreditkonto"}


def erstellen(con, konto_id: int, ids: list[int], inhaber: str | None, heute: str) -> bytes:
    konto = _konto(con, konto_id)
    ids = list(dict.fromkeys(buch.sichere_id(i) for i in ids))
    if konto["art"] in KATEGORIE:
        return _kategorie_erstellen(con, konto, ids, inhaber, heute)
    geladen = {b["id"]: b for b in buch.buchungen_laden(con, ids, konto_id=konto_id)}
    fehlend = [i for i in ids if i not in geladen]
    if fehlend:
        raise buch.nicht_gefunden("Die Buchung")
    fremd = [i for i in ids if not any(s["konto_id"] == konto_id for s in geladen[i]["splits"])]
    if fremd:
        raise ApiFehler(422, "buchung_nicht_im_konto", "Nicht alle Buchungen gehören zu diesem Konto.",
                        {"buchung_ids": fremd})
    vorgabe = angaben(con, konto_id)
    zeilen = [{"datum": b["datum"], "empfaenger": (b["empfaenger"] or {}).get("name", ""),
               "verwendungszweck": b["verwendungszweck"], "betrag": b["betrag"], "hinweis": hinweis(con, b, konto)}
              for b in sorted(geladen.values(), key=lambda x: (x["datum"], x["id"]))]
    return pdf_bytes(inhaber=vorgabe["inhaber"] if inhaber is None else inhaber, iban=konto["iban"] or "",
                     bic=vorgabe["bic"], kontoart=_KONTOART[konto["art"]], datum=heute, buchungen=zeilen)


def _teilbaum(con, konto: dict) -> set[int]:
    alle = {r["id"]: r["eltern_id"] for r in con.execute("SELECT id, eltern_id FROM konto WHERE art = ?", (konto["art"],))}
    menge, neu = {konto["id"]}, True
    while neu:
        neu = False
        for i, e in alle.items():
            if e in menge and i not in menge:
                menge.add(i)
                neu = True
    return menge


def _pfad(con, konto: dict) -> str:
    teile, k = [], konto
    while k is not None and len(teile) < 50:
        teile.append(k["name"])
        k = buch.konto_dict(r) if (r := buch.konto_zeile(con, k["eltern_id"]) if k["eltern_id"] else None) else None
        if k is not None and k["art"] != konto["art"]:
            break
    return " › ".join(reversed(teile))


def _kategorie_erstellen(con, konto: dict, ids: list[int], inhaber: str | None, heute: str) -> bytes:
    """Buchungsnachweis einer Kategorie (D-310)."""
    menge = _teilbaum(con, konto)
    geladen = {b["id"]: b for b in buch.buchungen_laden(con, ids, konten=menge)}
    if any(i not in geladen for i in ids):
        raise buch.nicht_gefunden("Die Buchung")
    fremd = [i for i in ids if not any(s["konto_id"] in menge for s in geladen[i]["splits"])]
    if fremd:
        raise ApiFehler(422, "buchung_nicht_im_konto", "Nicht alle Buchungen gehören zu dieser Kategorie.",
                        {"buchung_ids": fremd})
    bank = {r["id"]: buch.konto_dict(r) for r in con.execute(
        f"SELECT * FROM konto WHERE art IN ({buch._platzhalter(len(buch.BESTAND))})", buch.BESTAND)}
    zeilen, benutzt = [], {}
    for b in sorted(geladen.values(), key=lambda x: (x["datum"], x["id"])):
        anteil = -b["betrag"]                    # Sicht des Bankkontos: Ausgaben negativ
        auf_bank = sorted({s["konto_id"] for s in b["splits"] if s["konto_id"] in bank})
        zusatz, text = [], "Keinem Bankkonto zugeordnet"
        if len(auf_bank) == 1:
            bk = bank[auf_bank[0]]
            benutzt[bk["id"]] = bk
            gezahlt = sum(s["betrag"] for s in b["splits"] if s["konto_id"] == bk["id"])
            zusatz.append(f"{bk['name']} · {iban_maskiert(bk['iban'] or '')}" if bk["iban"] else bk["name"])
            if gezahlt != anteil:
                zusatz.append(f"Anteil an einer Zahlung über {betrag_text(gezahlt)}")
            text = hinweis(con, {**b, "betrag": gezahlt}, bk)
        elif auf_bank:
            text = "Mehrere Bankkonten beteiligt"
        zeilen.append({"datum": b["datum"], "empfaenger": (b["empfaenger"] or {}).get("name", ""),
                       "verwendungszweck": b["verwendungszweck"], "betrag": anteil, "hinweis": text,
                       "zusatz": zusatz})
    vorgabe = angaben(con, konto["id"])
    konten = ", ".join(k["name"] for k in sorted(benutzt.values(), key=lambda k: k["name"].casefold()))
    return pdf_bytes(inhaber=vorgabe["inhaber"] if inhaber is None else inhaber, iban="", bic=None, kontoart="",
                     datum=heute, buchungen=zeilen, kategorie={"pfad": _pfad(con, konto), "konten": konten})


__all__ = ["pdf_bytes", "iban_maskiert", "betrag_text", "angaben", "hinweis", "erstellen", "HINWEIS"]
