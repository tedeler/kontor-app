"""Bank-Plugin über AqBanking 6 (aqbanking.md, Meilenstein 10). Nur lesend.

Das Plugin ruft die Programme ``aqbanking-cli`` und ``aqhbci-tool4`` mit einer vom Betreiber eingerichteten
AqBanking-Konfiguration auf (immer ``-D <aqbanking_verzeichnis>``) und verwendet nur die Befehle ``listaccs``,
``request --transactions`` und ``aqhbci-tool4 listusers`` (6). ``konten()`` liest offline aus der lokalen
Konfiguration; ``umsaetze()`` macht genau einen nicht interaktiven Abruf ohne Wiederholung.

Geheimnisse: Die PIN geht ausschließlich über eine Pipe als PIN-Datei (``-P /dev/fd/N``) an AqBanking, nie in
Argumente, Umgebung oder Dateien (5.3). Ausgaben von AqBanking werden nur im Arbeitsspeicher ausgewertet und nie
an Logger, stdout oder stderr weitergereicht; Meldungen enthalten weder PIN noch Benutzerkennung noch Pfade.

Erfolg und Fehler erkennt das Plugin an der Diagnoseausgabe bei ``AQHBCI_LOGLEVEL=info`` (5.2): Rückmeldungen
der Bank (``Result: … (NNNN: …)``), Status des Auftrags ``JobGetTransactions`` und der Hinweis auf eine fehlende
TAN-Eingabe. Der Rückgabecode von ``aqbanking-cli`` ist auch bei Fehlern meist 0.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from ..config import KontorConfig
from ..fehler import (BankFehler, BankKontoUnbekannt, BankPinFalsch, BankPinFehlt, BankTanNichtUnterstuetzt,
                      BankVerbindungsFehler, BankZeitueberschreitung, BankZugangGesperrt, PluginNichtVerfuegbar,
                      TanUngueltig)
from ..text import iban_gueltig, iban_normalisieren
from .bank import BankKonto, BankPlugin, BankSaldo, BankUmsatz, TanAntwort, Umsatzliste
from .fints import PIN_CODES, _Roh, kennungen_vergeben

CLI = "aqbanking-cli"
TOOL = "aqhbci-tool4"

#: AqBanking-Kontotyp (``typeAsString``) → Kontoart in Kontor (aqbanking.md 4.1); andere Typen entfallen.
KONTOARTEN = {"bank": "girokonto", "checking": "girokonto", "unknown": "girokonto", "unspecified": "girokonto",
              "savings": "sparkonto", "moneymarket": "sparkonto",
              "creditcard": "kreditkonto", "credit": "kreditkonto", "loan": "kreditkonto"}

#: Sammelcodes, die nur gelten, wenn keine genauere Rückmeldung vorliegt (5.1).
SAMMELCODES = ("9050", "9800")

# Trennzeichen der Kontoliste: Datensatz- und Feldtrenner (kommen in Namen praktisch nie vor)
_SATZ, _FELD = "\x1e", "\x1f"
_VORLAGE = _SATZ + _FELD.join(("$(iban)", "$(bic)", "$(typeAsString)", "$(accountName)", "$(ownerName)"))

# Diagnosezeilen von AqBanking (Format „<stufe>:<datum> <zeit>:<modul>(<pid>):<datei>: <zeile>: <text>“)
_KOPF = r"^\d:\S+ \S+:[A-Za-z0-9_-]+\(\d+\):[A-Za-z0-9_.]+:\s*\d+: "
_RUECKMELDUNG = re.compile(_KOPF + r"Result: [A-Za-z]+ \((\d{4})[:)]", re.MULTILINE)
_STATUS = re.compile(_KOPF + r'Changing status of job "JobGetTransactions" from "[^"]*" \(-?\d+\) to "([^"]*)"',
                     re.MULTILINE)
_OHNE_TAN = re.compile(_KOPF + r".*No TAN input in non-interactive mode", re.MULTILINE)

#: Umgebungsvariablen, die nicht an AqBanking gehen (keine Proxys; Sprache fest, damit die Ausgabe auswertbar ist)
_PROXY = re.compile(r"proxy", re.IGNORECASE)
_SPRACHE = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")

# Pipe-Puffer unter Linux mindestens 64 KiB: die PIN-Datei wird vor dem Start vollständig hineingeschrieben.
_PIPE_GRENZE = 60_000
_DATUM_LAENGE = 8          # JJJJMMTT
_KONTO_FELDER = 5          # Felder je Satz der Kontoliste (_VORLAGE)
_NACHLAUF_SEKUNDEN = 2


@dataclass
class _Lauf:
    """Ergebnis eines Programmaufrufs (nur im Arbeitsspeicher, nie ausgegeben)."""
    rc: int
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)


# ================================================================ Auswertung (aqbanking.md 5)


def fehler_aus_ausgabe(rc: int, stderr: str) -> None:
    """Fehlerzuordnung nach 5.1 für einen abgeschlossenen ``request`` (Zeitüberschreitung prüft der Aufrufer).

    Wirft die passende Ausnahme oder kehrt zurück, wenn der Abruf erfolgreich war."""
    codes = _RUECKMELDUNG.findall(stderr)
    if any(c in PIN_CODES for c in codes):
        raise BankPinFalsch("Die Bank hat die PIN abgelehnt.")
    if "3938" in codes:
        raise BankZugangGesperrt("Der Bankzugang ist gesperrt. Bitte bei der Bank entsperren lassen.")
    if "9210" in codes:
        raise BankKontoUnbekannt("Das Konto ist der Bank unbekannt.")
    if "0030" in codes or _OHNE_TAN.search(stderr):
        raise BankTanNichtUnterstuetzt(
            "Die Bank verlangt eine TAN. Bitte die Freigabe einmal direkt in AqBanking erteilen (z. B. mit "
            "KMyMoney, GnuCash oder aqbanking-cli im Terminal); danach ruft Kontor wieder ohne TAN ab.")
    abgelehnt = [c for c in codes if c.startswith("9")]
    genau = [c for c in abgelehnt if c not in SAMMELCODES]
    for liste in (genau, abgelehnt):
        if liste:
            raise BankFehler(f"Die Bank hat den Auftrag abgelehnt (Rückmeldung {liste[0]}).", rueckmeldung=liste[0])
    status = _STATUS.findall(stderr)
    if rc != 0 or not status or status[-1] != "answered":
        raise BankVerbindungsFehler("Die Verbindung zur Bank ist fehlgeschlagen oder der Abruf wurde nicht "
                                    "beantwortet.")


# ================================================================ AqBanking-Kontext (GWEN-DB-Textformat)


@dataclass
class _Gruppe:
    name: str
    werte: dict[str, list[str]] = field(default_factory=dict)
    gruppen: list[_Gruppe] = field(default_factory=list)

    def wert(self, name: str) -> str | None:
        liste = self.werte.get(name)
        return liste[0] if liste else None

    def alle(self, name: str) -> list[_Gruppe]:
        """Alle Untergruppen ``name`` in beliebiger Tiefe, in Dokumentreihenfolge."""
        aus: list[_Gruppe] = []
        for g in self.gruppen:
            if g.name == name:
                aus.append(g)
            aus.extend(g.alle(name))
        return aus


_VARIABLE = re.compile(r"^(?:(?:char|int|bin|ptr)\s+)?([A-Za-z0-9_.\-]+)\s*=\s*(.*)$")


def _werte_lesen(text: str) -> list[str]:
    """Kommagetrennte Werte einer Variablenzeile; Anführungszeichen mit Backslash-Maskierung, URL-kodiert."""
    aus: list[str] = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t":
            i += 1
        if i >= n:
            break
        if text[i] == '"':
            i += 1
            teile: list[str] = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    i += 1
                teile.append(text[i])
                i += 1
            if i >= n:
                raise ValueError("Wert ohne schließendes Anführungszeichen")
            i += 1
            roh = "".join(teile)
        else:
            ende = text.find(",", i)
            ende = n if ende < 0 else ende
            roh, i = text[i:ende].strip(), ende
        aus.append(urllib.parse.unquote(roh, encoding="utf-8", errors="replace"))
        while i < n and text[i] in " \t":
            i += 1
        if i < n:
            if text[i] != ",":
                raise ValueError("unerwartetes Zeichen nach einem Wert")
            i += 1
    return aus


def kontext_lesen(text: str) -> _Gruppe:
    """Liest eine Kontextdatei von AqBanking (``request -c``) in einen Baum aus Gruppen und Werten."""
    wurzel = _Gruppe("")
    stapel = [wurzel]
    for zeile in text.splitlines():
        z = zeile.strip()
        if not z or z.startswith("#"):
            continue
        if z.endswith("{"):
            g = _Gruppe(z[:-1].strip())
            stapel[-1].gruppen.append(g)
            stapel.append(g)
        elif z.startswith("}"):
            if len(stapel) == 1:
                raise ValueError("Gruppenende ohne Anfang")
            stapel.pop()
        else:
            m = _VARIABLE.match(z)
            if m is None:
                raise ValueError("unlesbare Zeile")
            stapel[-1].werte.setdefault(m[1], []).extend(_werte_lesen(m[2]))
    if len(stapel) != 1:
        raise ValueError("Gruppe ohne Ende")
    return wurzel


def _datum(text: str | None) -> dt.date | None:
    if not text:
        return None
    ziffern = text.strip()[:8]
    if len(ziffern) != _DATUM_LAENGE or not ziffern.isdigit():
        raise ValueError("unlesbares Datum")
    return dt.date(int(ziffern[:4]), int(ziffern[4:6]), int(ziffern[6:8]))


_BETRAG = re.compile(r"^(-?\d+)(?:/(\d+))?(?::(.*))?$")


def _betrag(text: str | None) -> tuple[int, str | None]:
    """AqBanking-Wert ``<Zähler>/<Nenner>:<Währung>`` → (Cent, Währung oder None); exakt, ohne Gleitkomma."""
    m = _BETRAG.match((text or "").strip())
    if m is None or (m[2] is not None and int(m[2]) == 0):
        raise ValueError("unlesbarer Betrag")
    cent = Fraction(int(m[1]), int(m[2] or 1)) * 100
    if cent.denominator != 1:
        raise ValueError("Betrag mit Bruchteilen von Cent")
    return int(cent), (m[3] or "").strip() or None


def _gegen_iban(text: str | None) -> str | None:
    if not text:
        return None
    n = iban_normalisieren(text)
    return n if iban_gueltig(n) else None


def _roh(t: _Gruppe) -> _Roh | None:
    """Abbildung einer AqBanking-Transaktion nach aqbanking.md 4.2; None, wenn der Eintrag entfällt."""
    if t.wert("type") != "statement" or (t.wert("status") or "").lower() == "pending":
        return None
    cent, waehrung = _betrag(t.wert("value"))
    if waehrung is not None and waehrung.upper() != "EUR":
        return None
    valuta = _datum(t.wert("valutaDate"))
    buchungstag = _datum(t.wert("date")) or valuta
    if buchungstag is None:
        return None
    name = "".join(t.werte.get("remoteName", []))
    zweck = "\n".join(t.werte.get("purpose", []))
    zweck = zweck.replace("\r", "").replace("\n", "")
    return _Roh(buchungstag, valuta, cent, name or None, _gegen_iban(t.wert("remoteIban")), zweck, False, False)


def _konten_im_kontext(wurzel: _Gruppe, iban: str) -> list[_Gruppe]:
    """``accountInfo``-Gruppen des Kontos ``iban``; ohne IBAN nur, wenn es genau ein Konto gibt."""
    konten = wurzel.alle("accountInfo")
    passend = [k for k in konten if iban_normalisieren(k.wert("iban") or "") == iban]
    if not passend:
        passend = [k for k in konten if not k.wert("iban")] if len(konten) == 1 else []
    return passend


def umsaetze_aus_kontext(text: str, iban: str) -> list[_Roh]:
    """Gebuchte Umsätze des Kontos ``iban`` (normalisiert) in Lieferreihenfolge."""
    aus: list[_Roh] = []
    for k in _konten_im_kontext(kontext_lesen(text), iban):
        for t in k.alle("transaction"):
            r = _roh(t)
            if r is not None:
                aus.append(r)
    return aus


def saldo_aus_kontext(text: str, iban: str) -> BankSaldo | None:
    """kontostand.md 1.3: gebuchter Saldo (``balance`` mit ``type = booked``, spätestes ``date``), nur EUR."""
    beste: tuple[dt.date, int] | None = None
    for k in _konten_im_kontext(kontext_lesen(text), iban):
        for b in k.alle("balance"):
            if (b.wert("type") or "").lower() != "booked":
                continue
            datum = _datum(b.wert("date"))
            cent, waehrung = _betrag(b.wert("value"))
            if datum is None or (waehrung or "").upper() != "EUR":
                continue
            if beste is None or datum > beste[0]:
                beste = (datum, cent)
    return None if beste is None else BankSaldo(iban=iban, betrag=beste[1], stichtag=beste[0])


# Lokale Ablehnung der Saldenabfrage durch AqBanking (E-166): Die Bank wurde nicht kontaktiert.
_SALDO_NICHT_UNTERSTUETZT = re.compile(r'Request\s+"getBalance".*not\s+supported', re.IGNORECASE)


# ================================================================ Konten und Benutzer


def konten_aus_liste(ausgabe: str) -> list[tuple[BankKonto, str]]:
    """Ausgabe von ``listaccs`` mit ``_VORLAGE`` → (BankKonto, IBAN wie in AqBanking) nach aqbanking.md 4.1."""
    saetze = ausgabe.split(_SATZ)[1:]   # Text vor dem ersten Satz ist die Kopfzeile
    gesehen: dict[str, tuple[BankKonto, str]] = {}
    for satz in saetze:
        felder = satz.rstrip("\r\n").split(_FELD)
        if len(felder) != _KONTO_FELDER:
            continue
        roh_iban, bic, typ, name, inhaber = felder
        iban = iban_normalisieren(roh_iban)
        art = KONTOARTEN.get(typ.strip().lower())
        if art is None or not iban_gueltig(iban) or iban in gesehen:
            continue
        gesehen[iban] = (BankKonto(iban, bic.strip() or None, name, art, inhaber, "EUR"), roh_iban.strip())
    return [gesehen[i] for i in sorted(gesehen)]


_BENUTZER = re.compile(r"<user>(.*?)</user>", re.DOTALL)


def _xml_feld(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}>(.*?)</{name}>", block, re.DOTALL)
    if m is None:
        return None
    text = m[1].strip()
    if text.startswith("<![CDATA[") and text.endswith("]]>"):
        return text[9:-3]
    try:
        return ET.fromstring(f"<x>{text}</x>").text or ""
    except ET.ParseError:
        return text


def benutzer_aus_liste(ausgabe: str) -> list[tuple[str, str]]:
    """Ausgabe von ``listusers --xml`` → (Bankleitzahl, Benutzerkennung) je Benutzer."""
    aus = []
    for block in _BENUTZER.findall(ausgabe):
        blz, kennung = _xml_feld(block, "BankCode"), _xml_feld(block, "UserId")
        if blz and kennung:
            aus.append((blz.strip(), kennung.strip()))
    return aus


def pin_datei(benutzer: list[tuple[str, str]], pin: str) -> bytes:
    """PIN-Datei im Format von AqBanking: je Benutzer ``PIN_<BLZ>_<Benutzerkennung> = "<PIN>"`` (5.3)."""
    maskiert = pin.replace("\\", "\\\\").replace('"', '\\"')
    return "".join(f'PIN_{blz}_{kennung} = "{maskiert}"\n' for blz, kennung in benutzer).encode("utf-8")


# ================================================================ Plugin


class AqbankingBankPlugin(BankPlugin):
    name = "aqbanking"
    ist_mock = False

    def __init__(self, config: KontorConfig, *, pin_quelle: Callable[[], str | None] | None = None) -> None:
        # Das Erzeugen startet kein Programm, ruft pin_quelle nicht auf und wirft nicht (aqbanking.md 3).
        self._config = config
        self._pin_quelle = pin_quelle
        self._sperre = threading.Lock()   # höchstens ein AqBanking-Programm je Instanz (6)

    def __repr__(self) -> str:
        return "AqbankingBankPlugin()"

    __str__ = __repr__

    # ------------------------------------------------------------ Schnittstelle
    def konten(self) -> list[BankKonto]:
        with self._sperre:
            programme = self._verfuegbar()
            return [k for k, _ in self._konten(programme)]

    def umsaetze(self, iban: str, von: dt.date, bis: dt.date, *,
                 tan: TanAntwort | None = None) -> Umsatzliste:
        with self._sperre:
            programme = self._verfuegbar()
            if von > bis:
                raise ValueError("von darf nicht nach bis liegen.")
            n = iban_normalisieren(str(iban))
            if tan is not None:
                raise TanUngueltig("Zu dieser TAN gibt es keine offene TAN-Anforderung.")
            konto = next((roh for k, roh in self._konten(programme) if k.iban == n), None)
            if konto is None:
                raise BankKontoUnbekannt("Das Konto ist in der AqBanking-Konfiguration nicht bekannt.")
            pin = self._pin()
            benutzer = self._benutzer(programme)
            return self._abruf(programme, n, konto, von=von, bis=bis, pin=pin_datei(benutzer, pin))

    def schliessen(self) -> None:
        return None

    # ------------------------------------------------------------ Prüfungen (3.1, 4.2)
    def _verfuegbar(self) -> dict[str, str]:
        verz = self._config.aqbanking_verzeichnis
        if verz is None or not Path(verz).is_dir():
            raise PluginNichtVerfuegbar("AqBanking ist nicht eingerichtet: Das AqBanking-Verzeichnis "
                                        "(aqbanking_verzeichnis) fehlt oder ist kein Verzeichnis.")
        programme: dict[str, str] = {}
        for name in (CLI, TOOL):
            pfad = self._programm(name)
            if pfad is None:
                raise PluginNichtVerfuegbar(f"AqBanking ist nicht eingerichtet: Das Programm {name} wurde nicht "
                                            "gefunden (Paket aqbanking-tools, aqbanking_programme).")
            programme[name] = pfad
        return programme

    def _programm(self, name: str) -> str | None:
        ordner = self._config.aqbanking_programme
        if ordner is None:
            return shutil.which(name)
        pfad = Path(ordner) / name
        return str(pfad) if pfad.is_file() and os.access(pfad, os.X_OK) else None

    def _pin(self) -> str:
        pin = self._pin_quelle() if self._pin_quelle is not None else None
        if pin is None or pin == "":
            raise BankPinFehlt("Für den Bankzugang wird eine PIN benötigt; es ist keine hinterlegt.")
        pin = str(pin)
        if "\n" in pin or "\r" in pin or "\x00" in pin:
            # Mit Zeilenumbruch ist die PIN-Datei nicht darstellbar; eine gültige PIN enthält keinen.
            raise BankPinFalsch("Die PIN enthält unzulässige Zeichen.")
        return pin

    # ------------------------------------------------------------ Programmaufrufe
    def _umgebung(self, temp: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not _PROXY.search(k) and k not in _SPRACHE}
        env.update({"AQHBCI_LOGLEVEL": "info", "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "TMPDIR": temp})
        return env

    def _starten(self, programm: str, argumente: list[str], *, pin: bytes | None = None) -> _Lauf:
        """Ein Programm mit ``-D <verzeichnis>`` starten; PIN-Datei über eine Pipe, Zeitgrenze je Aufruf."""
        befehl = [programm, "-D", str(self._config.aqbanking_verzeichnis)]
        lesen = schreiben = -1
        with tempfile.TemporaryDirectory(prefix="kontor-aqbanking-", dir=tempfile.gettempdir()) as temp:
            try:
                fds: tuple[int, ...] = ()
                if pin is not None:
                    if len(pin) > _PIPE_GRENZE:
                        raise PluginNichtVerfuegbar("Die AqBanking-Konfiguration enthält zu viele Benutzer.")
                    lesen, schreiben = os.pipe()
                    os.write(schreiben, pin)
                    os.close(schreiben)
                    schreiben = -1
                    befehl += ["-P", f"/dev/fd/{lesen}"]
                    fds = (lesen,)
                return self._warten(befehl + argumente, fds, temp)
            finally:
                for fd in (lesen, schreiben):
                    if fd != -1:
                        os.close(fd)

    def _warten(self, befehl: list[str], fds: tuple[int, ...], temp: str) -> _Lauf:
        try:
            proc = subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, pass_fds=fds, env=self._umgebung(temp),
                                    cwd=temp, start_new_session=True)
        except OSError:
            raise PluginNichtVerfuegbar("AqBanking ist nicht eingerichtet: Ein Programm ließ sich nicht "
                                        "starten.") from None
        try:
            aus, fehler = proc.communicate(timeout=self._config.aqbanking_timeout_sekunden)
        except subprocess.TimeoutExpired:
            self._beenden(proc)
            raise BankZeitueberschreitung("AqBanking hat die Zeitgrenze überschritten; der Abruf wurde "
                                          "abgebrochen.") from None
        except BaseException:
            self._beenden(proc)
            raise
        return _Lauf(proc.returncode, aus, fehler)

    @staticmethod
    def _beenden(proc: subprocess.Popen) -> None:
        """Den Prozess samt Kindprozessen (eigene Prozessgruppe) beenden: erst TERM, dann KILL."""
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                break
            try:
                proc.communicate(timeout=_NACHLAUF_SEKUNDEN)
                break
            except subprocess.TimeoutExpired:
                continue
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    def _konten(self, programme: dict[str, str]) -> list[tuple[BankKonto, str]]:
        lauf = self._starten(programme[CLI], ["listaccs", f"--template={_VORLAGE}"])
        if lauf.rc != 0:
            raise PluginNichtVerfuegbar("Die AqBanking-Konfiguration ließ sich nicht lesen (Kontoliste).")
        return konten_aus_liste(lauf.stdout.decode("utf-8", errors="replace"))

    def _benutzer(self, programme: dict[str, str]) -> list[tuple[str, str]]:
        lauf = self._starten(programme[TOOL], ["listusers", "--xml"])
        benutzer = benutzer_aus_liste(lauf.stdout.decode("utf-8", errors="replace")) if lauf.rc == 0 else []
        if not benutzer:
            raise PluginNichtVerfuegbar("Die AqBanking-Konfiguration ließ sich nicht lesen (Benutzerliste).")
        return benutzer

    def _abruf(self, programme: dict[str, str], iban: str, konto: str, *, von: dt.date, bis: dt.date,
               pin: bytes) -> Umsatzliste:
        """Genau ein ``request --transactions`` (nicht interaktiv, ohne Wiederholung), dann Abbildung (4.2).

        Mit ``aqbanking_saldo`` zusätzlich ``--balance`` im selben Auftrag; lehnt AqBanking das lokal ab (die Bank
        bietet die Saldenabfrage nicht an), folgt sofort genau ein ``request`` ohne ``--balance`` (kontostand.md
        1.3, E-166)."""
        mit_saldo = self._config.aqbanking_saldo
        with tempfile.TemporaryDirectory(prefix="kontor-aqbanking-", dir=tempfile.gettempdir()) as ablage:
            kontext = Path(ablage) / "abruf.ctx"
            lauf = self._request(programme, konto, von, bis, kontext, pin, mit_saldo)
            stderr = lauf.stderr.decode("utf-8", errors="replace")
            if mit_saldo and lauf.rc != 0 and _SALDO_NICHT_UNTERSTUETZT.search(stderr):
                mit_saldo = False
                kontext.unlink(missing_ok=True)
                lauf = self._request(programme, konto, von, bis, kontext, pin, False)
                stderr = lauf.stderr.decode("utf-8", errors="replace")
            fehler_aus_ausgabe(lauf.rc, stderr)
            try:
                text = kontext.read_text(encoding="utf-8", errors="replace")
                roh = umsaetze_aus_kontext(text, iban)
            except (OSError, ValueError):
                raise BankVerbindungsFehler("Die Antwort der Bank ist unlesbar.") from None
            saldo = None
            if mit_saldo:
                try:
                    saldo = saldo_aus_kontext(text, iban)
                except ValueError:
                    saldo = None  # nur der Saldo ist unlesbar: Umsätze bleiben gültig
        aus = [u for u in kennungen_vergeben(iban, roh) if von <= u.buchungstag <= bis]
        aus.sort(key=lambda u: (u.buchungstag, u.umsatz_id))
        return Umsatzliste(aus, saldo=saldo)

    def _request(self, programme: dict[str, str], konto: str, von: dt.date, bis: dt.date, kontext: Path,
                 pin: bytes, mit_saldo: bool) -> _Lauf:
        return self._starten(programme[CLI], [
            "-n", "request", "--transactions", *(["--balance"] if mit_saldo else []), f"--iban={konto}",
            f"--fromdate={von:%Y%m%d}", f"--todate={bis:%Y%m%d}", "-c", str(kontext)], pin=pin)


__all__ = ["AqbankingBankPlugin"]
