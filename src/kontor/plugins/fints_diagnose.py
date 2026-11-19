"""Diagnoseprotokoll des FinTS-Plugins (D-203): was mit der Bank ausgetauscht wird – ohne persönliche Daten.

Grundsatz ist eine Positivliste: Aus jeder Nachricht werden nur Strukturangaben übernommen (Segmentarten und
-versionen, Rückmeldecodes, angebotene Formate und TAN-Verfahren, Kontoart, Währung, erlaubte Geschäftsvorfälle,
Längen und Anzahlen). Nie übernommen werden PIN, TAN, Auftragsreferenzen, Benutzerkennung, Kunden-ID,
Kundensystem-ID, Produkt-ID, IBAN, Kontonummer, Inhaber, Kontobezeichnung, Beträge, Umsätze oder der Wortlaut
einer TAN-Anforderung. Konten heißen im Protokoll „Konto 1“, „Konto 2“ … in der Reihenfolge der Bank. Freitexte
der Bank (Rückmeldungstexte) laufen zusätzlich durch ``bereinigen``. Die Nachrichten selbst werden nie
geschrieben; das Protokoll liegt nur im Arbeitsspeicher (und, eingeschaltet, im Log des Dienstes).
"""

from __future__ import annotations

import collections
import datetime as dt
import logging
import re
import threading

_LOG = logging.getLogger("kontor.fints.diagnose")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{8,30}\b")
_ZIFFERN = re.compile(r"\d{5,}")
MAX_ZEILEN = 600
MAX_TEXT = 160


def bereinigen(text: object, geheim: tuple[str, ...] = ()) -> str:
    """Freitext der Bank ohne alles, was wie eine Kennung aussieht: bekannte Kennungen, IBANs und Ziffernfolgen
    ab fünf Stellen werden ersetzt, Steuerzeichen entfernt, die Länge begrenzt."""
    t = "".join(ch if ch.isprintable() else " " for ch in str(text or ""))
    for g in sorted({g for g in geheim if g and len(g) >= 3}, key=len, reverse=True):
        t = re.sub(re.escape(g), "‹entfernt›", t, flags=re.IGNORECASE)
    t = _IBAN.sub("‹IBAN›", t)
    t = _ZIFFERN.sub("‹Ziffern›", t)
    return t[:MAX_TEXT]


class Diagnose:
    """Ringpuffer der Protokollzeilen einer App-Instanz (nur Arbeitsspeicher)."""

    def __init__(self) -> None:
        self._zeilen: collections.deque[str] = collections.deque(maxlen=MAX_ZEILEN)
        self._sperre = threading.Lock()
        self.aktiv = False
        self.geheim: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return f"Diagnose(aktiv={self.aktiv})"

    def einschalten(self, an: bool) -> None:
        with self._sperre:
            if an and not self.aktiv:
                self._zeilen.clear()
            self.aktiv = bool(an)

    def zeilen(self) -> list[str]:
        with self._sperre:
            return list(self._zeilen)

    def eintrag(self, text: str) -> None:
        if not self.aktiv:
            return
        zeile = f"{dt.datetime.now().strftime('%H:%M:%S')} {text}"
        with self._sperre:
            self._zeilen.append(zeile)
        _LOG.info("%s", text)

    # ------------------------------------------------------------ Nachrichten
    def nachricht(self, richtung: str, nachricht: object) -> None:
        """Eine Zeile mit den Segmenten der Nachricht, danach je aussagekräftigem Segment eine Zeile."""
        if not self.aktiv:
            return
        try:
            segmente = list(nachricht.find_segments())  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - Diagnose darf den Abruf nie stören
            self.eintrag(f"{richtung} Nachricht nicht auswertbar")
            return
        self.eintrag(f"{richtung} " + " ".join(_kurz(s) for s in segmente))
        for s in segmente:
            try:
                for zeile in _einzelheiten(s, self.geheim):
                    self.eintrag(f"   {zeile}")
            except Exception:  # noqa: BLE001
                self.eintrag(f"   {_kurz(s)}: nicht auswertbar")


def _kurz(s: object) -> str:
    kopf = getattr(s, "header", None)
    return f"{getattr(kopf, 'type', '?')}{getattr(kopf, 'version', '')}"


def _ja(wert: object) -> str:
    return "ja" if wert else "nein"


def _verbindung(konto: object) -> str:
    """Welche Felder einer Kontoverbindung gefüllt sind – nie deren Werte."""
    if konto is None:
        return "keine"
    teile = []
    for feld, name in (("iban", "IBAN"), ("bic", "BIC"), ("account_number", "Kontonummer"),
                       ("subaccount_number", "Unterkonto")):
        if getattr(konto, feld, None):
            teile.append(name)
    blz = getattr(getattr(konto, "bank_identifier", None), "bank_code", None)
    if blz:
        teile.append("BLZ")
    return "+".join(teile) or "leer"


def _einzelheiten(s: object, geheim: tuple[str, ...]) -> list[str]:  # noqa: C901 - eine Tabelle je Segmentart
    art = getattr(getattr(s, "header", None), "type", "")
    aus: list[str] = []
    if art in ("HIRMG", "HIRMS"):
        bezug = getattr(s.header, "reference", None)
        for r in s.responses or []:
            code = str(r.code)
            parameter = [str(p) for p in (r.parameters or [])]
            zusatz = ""
            if code == "3920":   # erlaubte TAN-Verfahren: dreistellige Sicherheitsfunktionen
                zusatz = " Verfahren: " + ",".join(p for p in parameter if p.isdigit() and len(p) <= 3)
            elif parameter:
                zusatz = f" ({len(parameter)} Parameter)"
            aus.append(f"{art} zu Segment {bezug if bezug is not None else '-'}: {code} "
                       f"„{bereinigen(r.text, geheim)}“{zusatz}")
    elif art == "HKTAN":
        aus.append(f"HKTAN Prozess {getattr(s, 'tan_process', '?')}, für {getattr(s, 'segment_type', None) or '-'}, "
                   f"TAN-Medium angegeben: {_ja(getattr(s, 'tan_medium_name', None))}")
    elif art == "HITAN":
        aus.append(f"HITAN Prozess {getattr(s, 'tan_process', '?')}, Auftragsreferenz: "
                   f"{_ja(getattr(s, 'task_reference', None))}, Text der Anforderung: "
                   f"{len(str(getattr(s, 'challenge', '') or ''))} Zeichen, Grafik/HHD: "
                   f"{len(getattr(s, 'challenge_hhduc', None) or b'')} Bytes")
    elif art == "HNSHK":
        profil = getattr(s, "security_profile", None)
        aus.append(f"HNSHK Sicherheitsfunktion {getattr(s, 'security_function', '?')}, Profil "
                   f"{getattr(profil, 'security_method', '?')}:{getattr(profil, 'security_method_version', '?')}")
    elif art == "HKVVB":
        aus.append(f"HKVVB BPD-Version {getattr(s, 'bpd_version', '?')}, UPD-Version {getattr(s, 'upd_version', '?')}")
    elif art == "HIBPA":
        aus.append(f"HIBPA BPD-Version {getattr(s, 'bpd_version', '?')}")
    elif art == "HIUPA":
        aus.append(f"HIUPA UPD-Version {getattr(s, 'upd_version', '?')}, UPD-Verwendung "
                   f"{getattr(s, 'upd_usage', '?')}")
    elif art == "HISYN":
        aus.append(f"HISYN Kundensystem-ID erhalten: {_ja(getattr(s, 'system_id', None))}")
    elif art == "HITANS":
        par = getattr(s, "parameter", None)
        verfahren = []
        for p in getattr(par, "twostep_parameters", None) or []:
            entkoppelt = getattr(p, "decoupled_max_poll_number", None) is not None
            verfahren.append(f"{p.security_function}={bereinigen(getattr(p, 'name', ''), geheim)}"
                             f"[{getattr(p, 'tan_process', '?')}{', entkoppelt' if entkoppelt else ''}]")
        aus.append(f"{_kurz(s)} TAN-Verfahren der Bank: " + "; ".join(verfahren))
    elif art in ("HICAZS", "HIKAZS", "HISALS", "HISPAS"):
        par = getattr(s, "parameter", None)
        zeile = f"{_kurz(s)} angeboten"
        formate = getattr(par, "supported_camt_formats", None)
        if formate:
            zeile += ", Formate: " + ", ".join(str(f).rsplit(":", 1)[-1] for f in formate)
        tage = getattr(par, "storage_period", None)
        if tage is not None:
            zeile += f", Speicherzeitraum {tage} Tage"
        aus.append(zeile)
    elif art in ("HKCAZ", "HKKAZ", "HKSAL"):
        zeile = f"{_kurz(s)} Kontoverbindung mit {_verbindung(getattr(s, 'account', None))}"
        if art != "HKSAL":
            zeile += (f", Zeitraum {getattr(s, 'date_start', None)} bis {getattr(s, 'date_end', None)}, "
                      f"Aufsetzpunkt: {_ja(getattr(s, 'touchdown_point', None))}")
        formate = getattr(getattr(s, "supported_camt_messages", None), "expected_type", None)
        if formate:
            zeile += ", verlangt: " + ", ".join(str(f).rsplit(":", 1)[-1] for f in formate)
        aus.append(zeile)
    elif art == "HISPA":
        konten = list(getattr(s, "accounts", None) or [])
        aus.append(f"HISPA {len(konten)} Kontoverbindungen")
        for i, k in enumerate(konten, 1):
            aus.append(f"  Konto {i}: SEPA {_ja(getattr(k, 'is_sepa', None))}, Felder {_verbindung(k)}")
    elif art == "HIUPD":
        erlaubt = sorted({str(t.transaction) for t in (getattr(s, "allowed_transactions", None) or [])
                          if getattr(t, "transaction", None)})
        abruf = [t for t in erlaubt if t in ("HKCAZ", "HKKAZ", "HKSAL", "HKSPA")]
        aus.append(f"{_kurz(s)} Kontoart {getattr(s, 'account_type', None)}, Währung "
                   f"{getattr(s, 'account_currency', None)}, IBAN angegeben: {_ja(getattr(s, 'iban', None))}, "
                   f"Kontonummer angegeben: "
                   f"{_ja(getattr(getattr(s, 'account_information', None), 'account_number', None))}, "
                   f"{len(erlaubt)} erlaubte Geschäftsvorfälle, davon Abruf: {','.join(abruf) or '-'}")
    elif art == "HICAZ":
        gebucht = getattr(getattr(s, "statement_booked", None), "camt_statements", None) or []
        vorgemerkt = getattr(s, "statement_pending", None)
        aus.append(f"HICAZ {len(gebucht)} camt-Dokumente gebucht ({sum(len(x or b'') for x in gebucht)} Bytes), "
                   f"vorgemerkt: {len(vorgemerkt or b'')} Bytes")
    elif art == "HIKAZ":
        aus.append(f"HIKAZ MT940 gebucht {len(getattr(s, 'statement_booked', None) or b'')} Bytes, vorgemerkt "
                   f"{len(getattr(s, 'statement_pending', None) or b'')} Bytes")
    elif art == "HISAL":
        aus.append(f"{_kurz(s)} Saldo erhalten")
    return aus
