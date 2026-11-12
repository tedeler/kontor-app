"""Bank-Synchronisation, TAN-Ablauf, PIN, App-Uhr, Planer und Benachrichtigungen (synchronisation.md).

Ein ``SyncDienst`` gehört zu genau einer App-Instanz (``app.state.sync``).
Er hält alles, was nur im Arbeitsspeicher leben darf: die Plugin-Instanz,
die PIN, die interne Kennung offener TAN-Anforderungen und die simulierte
Uhr im Mock-Modus. In der Datenbank landen nur Läufe, Zustände, gemerkte
Kennungen, TAN-Anforderungen (ohne Kennung/TAN/PIN) und Benachrichtigungen.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import threading
import time
from dataclasses import dataclass

import json

from . import abgleich, buch, db, kredite, lernmodell, pflege, protokoll, regeln, vorlagen, wiederkehrend
from .buch import BESTAND, ApiFehler
from .config import KontorConfig
from .fehler import (BankPinFalsch, BankZugangGesperrt, KontorFehler, TanAbgelaufen, TanErforderlich, TanUngueltig)
from .geheimnisse import Geheimnisspeicher
from .mail import MailDienst
from .zustellung import Zustelldienst
from .text import iban_normalisieren, passend

log = logging.getLogger("kontor.sync")
UTC = dt.timezone.utc
KONTOARTEN_BESTAND = ("girokonto", "sparkonto", "kreditkonto")


def euro(cent: int) -> str:
    """Betrag in Cent als deutscher Eurotext (nur Ganzzahlarithmetik)."""
    vz = "−" if cent < 0 else ""
    e, c = divmod(abs(cent), 100)
    return f"{vz}{e:,}".replace(",", ".") + f",{c:02d} €"


def zeit_text(z: dt.datetime) -> str:
    return z.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def zeit_lesen(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _fehler_von(e: BaseException) -> tuple[str, str]:
    """``{code, meldung}`` eines Pluginfehlers; Meldungen enthalten nie PIN oder TAN (plugins.md 7.1)."""
    if isinstance(e, KontorFehler):
        meldung = (e.meldung or "").strip() or "Fehler des Bank-Plugins."
        return e.code, meldung
    return "plugin_fehler", "Unerwarteter Fehler im Bank-Plugin."


@dataclass
class _TanKontext:
    """Nur im Arbeitsspeicher: was für die Freigabe einer offenen TAN-Anforderung nötig ist."""
    anforderung_id: str
    plugin: object
    lauf_id: int

    def __repr__(self) -> str:
        return f"_TanKontext(lauf_id={self.lauf_id})"


class SyncDienst:
    def __init__(self, config: KontorConfig) -> None:
        self.config = config
        self.pfad = config.aktive_datenbank
        self._sperre = threading.Lock()       # höchstens ein Lauf gleichzeitig (je App)
        self._zustand = threading.Lock()      # schützt Uhr, PIN, Plugin, Kontexte
        self._plugin = None
        self._pin: str | None = None
        self._simuliert: dt.datetime | None = None
        self._tan: dict[int, _TanKontext] = {}
        self._thread: threading.Thread | None = None
        self._stopp = threading.Event()
        # M7 (betrieb.md 5.2): Beenden der App; _abbruch = nach Fristablauf nichts mehr schreiben
        self._beenden = False
        self._abbruch = False
        self._schreib_sperre = threading.Lock()
        # M6: PIN aus systemd-creds (fints.md 5), Geheimnisse, Mail, Zustellung
        self._pin_gesperrt = False
        self.geheimnisse = Geheimnisspeicher(config, self.jetzt_text)
        self.mail = MailDienst(config, self.jetzt, self.geheimnisse)
        self.mail.nach_abruf = lambda: abgleich.laufen(self.config, self.jetzt())
        self.zustellung = Zustelldienst(config, self.jetzt, self._ntfy_token)

    def __repr__(self) -> str:
        return "SyncDienst()"

    def _ntfy_token(self) -> str | None:
        con = self._con()
        try:
            return self.geheimnisse.lesen(con, "ntfy_token")
        finally:
            con.close()

    # ------------------------------------------------------------ App-Uhr
    def jetzt(self) -> dt.datetime:
        if self.config.mock_modus:
            if self._simuliert is not None:
                return self._simuliert
            if self.config.mock_heute is not None:
                h = self.config.mock_heute
                return dt.datetime(h.year, h.month, h.day, 12, 0, 0, tzinfo=UTC)
        return dt.datetime.now(UTC).replace(microsecond=0)

    def heute(self) -> dt.date:
        return self.jetzt().date()

    def jetzt_text(self) -> str:
        return zeit_text(self.jetzt())

    def mock_zeit(self) -> dict:
        self._nur_mock()
        simuliert = self._simuliert is not None or self.config.mock_heute is not None
        return {"jetzt": self.jetzt_text(), "heute": self.heute().isoformat(), "simuliert": simuliert}

    def mock_zeit_setzen(self, jetzt: dt.datetime) -> dict:
        self._nur_mock()
        self._simuliert = jetzt.astimezone(UTC).replace(microsecond=0)
        return self.mock_zeit()

    def _nur_mock(self) -> None:
        if not self.config.mock_modus:
            raise ApiFehler(409, "nur_mock_modus", "Die simulierte Uhr gibt es nur im Mock-Modus.")

    # ----------------------------------------------------------------- PIN
    @property
    def pin_aus_systemd(self) -> bool:
        return self.config.bank_pin_quelle == "systemd-creds"

    def pin_eingabe_pruefen(self) -> None:
        if self.pin_aus_systemd:
            raise ApiFehler(409, "pin_quelle_systemd", "Die PIN wird beim Dienststart über systemd-creds "
                            "bereitgestellt und kann hier nicht gesetzt oder verworfen werden.")

    def pin_setzen(self, pin: str) -> None:
        self.pin_eingabe_pruefen()
        with self._zustand:
            self._pin = pin

    def pin_verwerfen(self) -> None:
        self.pin_eingabe_pruefen()
        with self._zustand:
            self._pin = None

    def _pin_systemd(self) -> str | None:
        """fints.md 5: Datei ``kontor-bank-pin`` bei jedem Aufruf neu lesen; genau ein Zeilenumbruch fällt weg."""
        if self._pin_gesperrt or self.config.credentials_verzeichnis is None:
            return None
        try:
            inhalt = (self.config.credentials_verzeichnis / "kontor-bank-pin").read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        if inhalt.endswith("\r\n"):
            inhalt = inhalt[:-2]
        elif inhalt.endswith("\n"):
            inhalt = inhalt[:-1]
        return inhalt or None

    def _pin_quelle(self) -> str | None:
        if self.pin_aus_systemd:
            return self._pin_systemd()
        return self._pin

    def _pin_vorhanden(self) -> bool:
        return self._pin_quelle() is not None

    # -------------------------------------------------------------- Plugin
    def _plugin_holen(self):
        """Erzeugt das Bank-Plugin beim ersten Lauf und verwendet es danach weiter (python-api.md 8.4)."""
        if self._plugin is None:
            from .plugins import erzeuge_bank_plugin
            self._plugin = erzeuge_bank_plugin(self.config, pin_quelle=self._pin_quelle)
        return self._plugin

    def _vor_aufruf(self, plugin) -> None:
        if self.config.mock_modus and getattr(plugin, "ist_mock", False) and hasattr(plugin, "setze_heute"):
            plugin.setze_heute(self.heute())

    def _pluginfehler(self, e: BaseException) -> tuple[str, str]:
        if isinstance(e, (BankPinFalsch, BankZugangGesperrt)):
            # nie erneut mit derselben PIN (Schutz vor Kontosperre, synchronisation.md 12 und 18.1)
            if self.pin_aus_systemd:
                self._pin_gesperrt = True
            else:
                with self._zustand:
                    self._pin = None
        if not isinstance(e, KontorFehler):
            log.warning("Unerwarteter Fehler im Bank-Plugin: %s", type(e).__name__)
        return _fehler_von(e)

    # ------------------------------------------------------- Verbindungen
    def _con(self):
        return db.verbinde(self.pfad)

    # ================================================================ Neustart
    def neustart_aufraeumen(self) -> None:
        """synchronisation.md 10: wartende/laufende Läufe und offene TAN-Anforderungen abbrechen."""
        con = self._con()
        try:
            with db.transaktion(con):
                jetzt = self.jetzt_text()
                laeufe = [r["id"] for r in con.execute(
                    "SELECT id FROM sync_lauf WHERE status IN ('laeuft','wartet_auf_tan')")]
                for lid in laeufe:
                    self._lauf_abbrechen(con, lid, jetzt)
                con.execute("UPDATE tan_anforderung SET status = 'abgebrochen', beendet_am = ?, bild = NULL"
                            " WHERE status = 'offen'", (jetzt,))
        finally:
            con.close()

    @staticmethod
    def _lauf_abbrechen(con, lid: int, jetzt: str) -> None:
        con.execute("UPDATE sync_lauf SET status = 'abgebrochen', beendet_am = ? WHERE id = ?", (jetzt, lid))
        con.execute("UPDATE sync_lauf_konto SET status = 'abgebrochen' WHERE lauf_id = ?"
                    " AND status IN ('wartet_auf_tan','ausstehend')", (lid,))

    # ======================================================== Benachrichtigung
    def _benachrichtigen(self, con, art: str, schluessel: str, titel: str, text: str, link: str | None = None,
                         entprellen: bool = True) -> None:
        if entprellen and con.execute("SELECT 1 FROM benachrichtigung WHERE schluessel = ? AND gelesen = 0",
                                      (schluessel,)).fetchone():
            return
        con.execute("INSERT INTO benachrichtigung (art, schluessel, titel, text, link, erstellt_am, gelesen)"
                    " VALUES (?, ?, ?, ?, ?, ?, 0)", (art, schluessel, titel, text, link, self.jetzt_text()))

    # ============================================================ TAN-Ablauf
    def ablauf_pruefen(self) -> None:
        """synchronisation.md 7.4: offene, abgelaufene TAN-Anforderungen beenden."""
        jetzt = self.jetzt()
        con = self._con()
        try:
            offen = con.execute("SELECT id, lauf_id, gueltig_bis FROM tan_anforderung WHERE status = 'offen'").fetchall()
            faellig = [r for r in offen if jetzt > zeit_lesen(r["gueltig_bis"])]
            if not faellig:
                return
            with db.transaktion(con):
                for r in faellig:
                    self._tan_ablaufen(con, r["id"], r["lauf_id"])
            for r in faellig:
                self._wiederkehrend_nach_lauf(con, r["lauf_id"])
        finally:
            con.close()

    def _tan_ablaufen(self, con, tid: int, lid: int) -> None:
        jetzt = self.jetzt_text()
        con.execute("UPDATE tan_anforderung SET status = 'abgelaufen', beendet_am = ?, bild = NULL WHERE id = ?",
                    (jetzt, tid))
        self._lauf_abbrechen(con, lid, jetzt)
        self._benachrichtigen(con, "tan_abgelaufen", f"tan_abgelaufen:{tid}", "TAN-Anforderung abgelaufen",
                              "Die TAN-Anforderung wurde nicht rechtzeitig beantwortet. Die Synchronisation wurde "
                              "abgebrochen und kann neu gestartet werden.", entprellen=False)
        with self._zustand:
            self._tan.pop(tid, None)

    # ================================================================ Lesen
    def lauf_lesen(self, con, lid: int) -> dict:
        r = con.execute("SELECT * FROM sync_lauf WHERE id = ?", (buch.sichere_id(lid),)).fetchone()
        if r is None:
            raise buch.nicht_gefunden("Der Synchronisationslauf")
        return self._lauf_dict(con, r)

    @staticmethod
    def _lauf_dict(con, r) -> dict:
        konten = []
        for k in con.execute("SELECT * FROM sync_lauf_konto WHERE lauf_id = ? ORDER BY iban", (r["id"],)):
            konten.append({
                "iban": k["iban"], "konto_id": k["konto_id"], "konto_neu": bool(k["konto_neu"]),
                "status": k["status"], "von": k["von"], "bis": k["bis"],
                "umsaetze_gesamt": k["umsaetze_gesamt"], "vormerkungen_ignoriert": k["vormerkungen_ignoriert"],
                "buchungen_vorhanden": k["buchungen_vorhanden"],
                "buchungen_zusammengefuehrt": k["buchungen_zusammengefuehrt"], "buchungen_neu": k["buchungen_neu"],
                "buchungen_zur_pruefung": k["buchungen_zur_pruefung"],
                "buchungen_kategorisiert": k["buchungen_kategorisiert"],
                "buchungen_gesplittet": k["buchungen_gesplittet"], "vorlage_abweichungen": k["vorlage_abweichungen"],
                "buchungen_kredit": k["buchungen_kredit"],
                "saldo_abgleich": json.loads(k["saldo_abgleich"]) if k["saldo_abgleich"] else None,
                "fehler": None if k["fehler_code"] is None else {"code": k["fehler_code"],
                                                                 "meldung": k["fehler_meldung"]},
            })
        return {
            "id": r["id"], "ausloeser": r["ausloeser"], "status": r["status"], "gestartet_am": r["gestartet_am"],
            "beendet_am": r["beendet_am"], "von": r["von"], "bis": r["bis"],
            "fehler": None if r["fehler_code"] is None else {"code": r["fehler_code"], "meldung": r["fehler_meldung"]},
            "tan_anforderung_id": r["tan_anforderung_id"], "konten": konten,
            "uebersprungen": json.loads(r["uebersprungen"] or "[]"),
        }

    def laeufe(self, con) -> list[dict]:
        return [self._lauf_dict(con, r) for r in con.execute("SELECT * FROM sync_lauf ORDER BY id").fetchall()]

    @staticmethod
    def _zustand_dict(con, r) -> dict:
        """synchronisation.md 2.3 und 16.1: Status abgeleitet aus Kontenbestand und Entscheidung."""
        if con.execute("SELECT 1 FROM konto WHERE iban = ?", (r["iban"],)).fetchone():
            status = "aktiv"
        else:
            status = {None: "konto_fehlt", "ignorieren": "ignoriert",
                      "wiederherstellen": "wiederherstellen"}[r["entscheidung"]]
        return {"iban": r["iban"], "konto_id": r["konto_id"], "letzter_abruf_bis": r["letzter_abruf_bis"],
                "letzter_erfolg_am": r["letzter_erfolg_am"], "status": status,
                "wiederherstellen_buchungen": r["entscheidung_buchungen"] if status == "wiederherstellen" else None}

    @classmethod
    def konten_zustand(cls, con) -> list[dict]:
        return [cls._zustand_dict(con, r) for r in con.execute("SELECT * FROM sync_konto_zustand ORDER BY iban")]

    def entscheidung(self, iban_roh: str, d: dict) -> dict:
        """POST /api/sync/konten/{iban}/entscheidung (16.3); Betriebszustand, nicht protokolliert."""
        iban = iban_normalisieren(iban_roh)
        con = self._con()
        try:
            with db.transaktion(con):
                r = con.execute("SELECT * FROM sync_konto_zustand WHERE iban = ?", (iban,)).fetchone()
                if r is None:
                    raise buch.nicht_gefunden("Das Bankkonto")
                if self._zustand_dict(con, r)["status"] == "aktiv":
                    raise ApiFehler(409, "konto_vorhanden", "Es existiert bereits ein Konto mit dieser IBAN.")
                con.execute("UPDATE sync_konto_zustand SET entscheidung = ?, entscheidung_buchungen = ? WHERE iban = ?",
                            (d["aktion"], d["buchungen"], iban))
                con.execute("UPDATE benachrichtigung SET gelesen = 1 WHERE schluessel = ? AND gelesen = 0",
                            (f"konto_fehlt:{iban}",))
                return self._zustand_dict(
                    con, con.execute("SELECT * FROM sync_konto_zustand WHERE iban = ?", (iban,)).fetchone())
        finally:
            con.close()

    @staticmethod
    def _tan_dict(r) -> dict:
        return {"id": r["id"], "lauf_id": r["lauf_id"], "iban": r["iban"], "konto_id": r["konto_id"],
                "status": r["status"], "erstellt_am": r["erstellt_am"], "gueltig_bis": r["gueltig_bis"],
                "beendet_am": r["beendet_am"], "challenge": r["challenge"], "hat_bild": bool(r["hat_bild"])}

    _TAN_SQL = ("SELECT id, lauf_id, iban, konto_id, status, erstellt_am, gueltig_bis, beendet_am, challenge,"
                " bild IS NOT NULL OR hatte_bild AS hat_bild FROM ("
                " SELECT *, bild_mime_typ IS NOT NULL AS hatte_bild FROM tan_anforderung)")

    def tans(self, con) -> list[dict]:
        return [self._tan_dict(r) for r in con.execute(self._TAN_SQL + " ORDER BY id")]

    def tan_lesen(self, con, tid: int) -> dict:
        r = con.execute(self._TAN_SQL + " WHERE id = ?", (buch.sichere_id(tid),)).fetchone()
        if r is None:
            raise buch.nicht_gefunden("Die TAN-Anforderung")
        return self._tan_dict(r)

    def tan_bild(self, con, tid: int) -> tuple[bytes, str]:
        r = con.execute("SELECT status, bild, bild_mime_typ FROM tan_anforderung WHERE id = ?",
                        (buch.sichere_id(tid),)).fetchone()
        if r is None or r["status"] != "offen" or r["bild"] is None or not r["bild_mime_typ"]:
            raise buch.nicht_gefunden("Das Bild der TAN-Anforderung")
        return bytes(r["bild"]), r["bild_mime_typ"]

    def _naechster_lauf(self, con) -> str | None:
        c = self.config
        if c.sync_intervall_minuten <= 0:
            return None
        if con.execute("SELECT 1 FROM sync_lauf WHERE status IN ('laeuft','wartet_auf_tan')").fetchone():
            return None
        r = con.execute("SELECT * FROM sync_lauf WHERE beendet_am IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
        if r is None:
            return self.jetzt_text()
        minuten = c.sync_wiederholung_minuten if r["status"] == "fehlgeschlagen" else c.sync_intervall_minuten
        return zeit_text(zeit_lesen(r["beendet_am"]) + dt.timedelta(minutes=minuten))

    def status(self, con) -> dict:
        letzter = con.execute("SELECT * FROM sync_lauf ORDER BY id DESC LIMIT 1").fetchone()
        offen = con.execute(self._TAN_SQL + " WHERE status = 'offen' ORDER BY id DESC LIMIT 1").fetchone()
        laeuft = con.execute("SELECT 1 FROM sync_lauf WHERE status = 'laeuft'").fetchone() is not None
        return {
            "automatisch": self.config.sync_intervall_minuten > 0,
            "intervall_minuten": self.config.sync_intervall_minuten,
            "laeuft": laeuft,
            "jetzt": self.jetzt_text(),
            "naechster_lauf": self._naechster_lauf(con),
            "letzter_lauf": None if letzter is None else self._lauf_dict(con, letzter),
            "offene_tan_anforderung": None if offen is None else self._tan_dict(offen),
            "pin_vorhanden": self._pin_vorhanden(),
            "pin_quelle": self.config.bank_pin_quelle,
        }

    # =============================================================== Lauf
    def starten(self, ausloeser: str, von: str | None, bis: str | None) -> dict:
        """Startet einen Lauf synchron (409 ``sync_laeuft``/``tan_ausstehend``)."""
        if not self._sperre.acquire(blocking=False):
            raise ApiFehler(409, "sync_laeuft", "Es läuft bereits eine Synchronisation.")
        try:
            con = self._con()
            try:
                with db.transaktion(con):
                    zeile = con.execute("SELECT status FROM sync_lauf WHERE status IN ('laeuft','wartet_auf_tan')"
                                        " ORDER BY id DESC LIMIT 1").fetchone()
                    if zeile is not None and zeile["status"] == "laeuft":
                        raise ApiFehler(409, "sync_laeuft", "Es läuft bereits eine Synchronisation.")
                    if zeile is not None or con.execute(
                            "SELECT 1 FROM tan_anforderung WHERE status = 'offen'").fetchone():
                        raise ApiFehler(409, "tan_ausstehend",
                                        "Eine TAN-Anforderung wartet auf Antwort; erst beantworten oder abbrechen.")
                    lid = con.execute(
                        "INSERT INTO sync_lauf (ausloeser, status, gestartet_am, von, bis) VALUES (?, 'laeuft', ?, ?, ?)",
                        (ausloeser, self.jetzt_text(), von, bis)).lastrowid
                self._ausfuehren(con, lid)
                return self.lauf_lesen(con, lid)
            finally:
                con.close()
        finally:
            self._sperre.release()

    @contextlib.contextmanager
    def ohne_lauf(self):
        """M9 (sicherung.md 5.1 Schritt 5, 7): hält die Laufsperre, solange eingespielt wird – kein Lauf startet
        (409 ``sync_laeuft``); ein laufender bzw. auf TAN wartender Lauf verhindert das Einspielen."""
        if not self._sperre.acquire(blocking=False):
            raise ApiFehler(409, "sync_laeuft", "Es läuft gerade eine Synchronisation.")
        try:
            con = self._con()
            try:
                zeile = con.execute("SELECT status FROM sync_lauf WHERE status IN ('laeuft','wartet_auf_tan')"
                                    " ORDER BY id DESC LIMIT 1").fetchone()
            finally:
                con.close()
            if zeile is not None and zeile["status"] == "laeuft":
                raise ApiFehler(409, "sync_laeuft", "Es läuft gerade eine Synchronisation.")
            if zeile is not None:
                raise ApiFehler(409, "tan_ausstehend",
                                "Eine Synchronisation wartet auf eine TAN; erst beantworten oder abbrechen.")
            yield
        finally:
            self._sperre.release()

    def _lauf_scheitert(self, con, lid: int, code: str, meldung: str) -> None:
        with db.transaktion(con):
            con.execute("UPDATE sync_lauf SET status = 'fehlgeschlagen', beendet_am = ?, fehler_code = ?,"
                        " fehler_meldung = ? WHERE id = ?", (self.jetzt_text(), code, meldung, lid))
            self._fehler_melden(con, [code])
        self._wiederkehrend_nach_lauf(con, lid)
        abgleich.laufen(self.config, self.jetzt())  # D-128: neue Bankbuchungen erwarteten Zahlungen zuordnen

    def _fehler_melden(self, con, codes: list[str]) -> None:
        for code in dict.fromkeys(codes):
            self._benachrichtigen(con, "sync_fehler", f"sync_fehler:{code}", "Synchronisation fehlgeschlagen",
                                  f"Der Abruf bei der Bank ist fehlgeschlagen (Fehler „{code}“). "
                                  "Kontor versucht es später erneut; vorhandene Daten bleiben erhalten.")

    def _ausfuehren(self, con, lid: int) -> None:
        try:
            plugin = self._plugin_holen()
            self._vor_aufruf(plugin)
            bankkonten = plugin.konten()
        except TanErforderlich as e:  # D-023: TAN beim Kontenabruf ist ein Fehler des Laufs
            self._lauf_scheitert(con, lid, *_fehler_von(e))
            return
        except Exception as e:  # noqa: BLE001 - Pluginfehler führen nie zu 5xx
            self._lauf_scheitert(con, lid, *self._pluginfehler(e))
            return
        if self._beenden:
            self._beim_beenden_abbrechen(con, lid)
            return
        self._zuordnen(con, lid, bankkonten)
        self._fortsetzen(con, lid, plugin)

    def _zuordnen(self, con, lid: int, bankkonten) -> None:
        """synchronisation.md 3 und 16.2: Zuordnung (inkl. Anlegen) aller Bankkonten vor dem ersten Abruf."""
        gesehen: dict[str, object] = {}
        for bk in bankkonten:
            n = iban_normalisieren(str(bk.iban))
            gesehen.setdefault(n, bk)
        uebersprungen: list[dict] = []
        wiederhergestellt: list[str] = []
        with protokoll.protokolliert(con, "sync", "sync_kontozuordnung", self.jetzt_text(), f"sync:{lid}") as kx:
            for iban in sorted(gesehen):
                bk = gesehen[iban]
                name = (bk.name or "").strip() or iban
                r = con.execute("SELECT id FROM konto WHERE iban = ?", (iban,)).fetchone()
                z = con.execute("SELECT * FROM sync_konto_zustand WHERE iban = ?", (iban,)).fetchone()
                neu = r is None
                if not neu:
                    kid = r["id"]  # Regel 1; eine gespeicherte Entscheidung wird verworfen
                elif z is None and not self.config.sync_konten_anlegen:
                    # D-111: nicht anlegen, sondern überspringen; die Oberfläche bietet die Zuordnung an
                    art = bk.art if bk.art in KONTOARTEN_BESTAND else "girokonto"
                    uebersprungen.append({"iban": iban, "name": name, "status": "nicht_zugeordnet", "art": art})
                    self._benachrichtigen(
                        con, "konto_nicht_zugeordnet", f"konto_nicht_zugeordnet:{iban}", "Bankkonto ohne Zuordnung",
                        f"Das Bankkonto „{name}“ (IBAN {iban}) ist noch keinem Konto zugeordnet und wurde bei der "
                        "Synchronisation übersprungen. Bitte ein vorhandenes Konto wählen oder ein neues anlegen.",
                        link="/sync")
                    continue
                elif z is None or z["entscheidung"] == "wiederherstellen":
                    art = bk.art if bk.art in KONTOARTEN_BESTAND else "girokonto"
                    kid = con.execute(
                        "INSERT INTO konto (name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz, extern_id)"
                        " VALUES (?, ?, NULL, ?, 0, NULL, '', NULL)", (name, art, iban)).lastrowid
                    if z is not None:
                        wiederhergestellt.append(iban)
                        if z["entscheidung_buchungen"] == "alle":
                            self._kennungen_vergessen(con, iban)
                            con.execute("UPDATE sync_konto_zustand SET letzter_abruf_bis = NULL WHERE iban = ?",
                                        (iban,))
                else:
                    status = "ignoriert" if z["entscheidung"] == "ignorieren" else "konto_fehlt"
                    uebersprungen.append({"iban": iban, "name": name, "status": status})
                    if status == "konto_fehlt":
                        self._benachrichtigen(
                            con, "konto_fehlt", f"konto_fehlt:{iban}", "Bankkonto ohne Konto",
                            f"Zum Bankkonto „{name}“ (IBAN {iban}) gibt es kein Konto mehr; es wurde bei der "
                            "Synchronisation übersprungen. Soll das Konto wiederhergestellt oder das Bankkonto "
                            "künftig ignoriert werden?", link="/sync/konten")
                    continue
                vorher = 1 if z is not None and z["letzter_erfolg_am"] is not None else 0  # wiederkehrend.md 5
                con.execute("INSERT INTO sync_lauf_konto (lauf_id, iban, konto_id, konto_neu, status, vorher_abgerufen)"
                            " VALUES (?, ?, ?, ?, 'ausstehend', ?)", (lid, iban, kid, 1 if neu else 0, vorher))
                con.execute("INSERT INTO sync_konto_zustand (iban, konto_id) VALUES (?, ?)"
                            " ON CONFLICT(iban) DO UPDATE SET konto_id = excluded.konto_id, entscheidung = NULL,"
                            " entscheidung_buchungen = NULL", (iban, kid))
            con.execute("UPDATE sync_lauf SET uebersprungen = ? WHERE id = ?",
                        (json.dumps(uebersprungen, ensure_ascii=False), lid))

            def merken(aid: int) -> None:
                con.executemany("INSERT OR IGNORE INTO sync_wiederherstellung (aenderung_id, iban) VALUES (?, ?)",
                                [(aid, i) for i in wiederhergestellt])
            kx.danach.append(merken)

    @staticmethod
    def _kennungen_vergessen(con, iban: str) -> None:
        """16.2 Regel 3 „alle“: gemerkte Kennungen ohne existierende Buchung vergessen (E-081, E-082)."""
        praefix = f"bank:{iban}:"
        con.execute("DELETE FROM sync_kennung WHERE substr(kennung, 1, ?) = ?"
                    " AND NOT EXISTS (SELECT 1 FROM buchung_extern x WHERE x.extern_id = sync_kennung.kennung)",
                    (len(praefix), praefix))

    def _zeitraum(self, con, lauf, iban: str) -> tuple[dt.date, dt.date]:
        heute = self.heute()
        bis = dt.date.fromisoformat(lauf["bis"]) if lauf["bis"] else heute
        if lauf["von"]:
            von = dt.date.fromisoformat(lauf["von"])
        else:
            z = con.execute("SELECT letzter_abruf_bis FROM sync_konto_zustand WHERE iban = ?", (iban,)).fetchone()
            if z is not None and z["letzter_abruf_bis"]:
                von = dt.date.fromisoformat(z["letzter_abruf_bis"]) - dt.timedelta(
                    days=self.config.sync_ueberlappung_tage)
            else:
                von = heute - dt.timedelta(days=self.config.sync_erstabruf_tage)
        if von > bis:
            von = bis
        return von, bis

    def _fortsetzen(self, con, lid: int, plugin) -> None:
        """Verarbeitet alle noch ausstehenden Konten in IBAN-Reihenfolge, dann Abschluss (5)."""
        while True:
            lauf = con.execute("SELECT * FROM sync_lauf WHERE id = ?", (lid,)).fetchone()
            k = con.execute("SELECT * FROM sync_lauf_konto WHERE lauf_id = ? AND status = 'ausstehend'"
                            " ORDER BY iban LIMIT 1", (lid,)).fetchone()
            if k is None:
                break
            if self._beenden:  # betrieb.md 5.2: keine weiteren Konten abrufen
                self._beim_beenden_abbrechen(con, lid)
                return
            von, bis = self._zeitraum(con, lauf, k["iban"])
            fehler: BaseException | None = None
            try:
                self._vor_aufruf(plugin)
                umsaetze = plugin.umsaetze(k["iban"], von, bis)
            except TanErforderlich as e:
                with self._schreib_sperre:
                    if self._abbruch:
                        return
                    self._tan_anlegen(con, lid, k, von, bis, e, plugin)
                return
            except Exception as e:  # noqa: BLE001
                fehler = e
            with self._schreib_sperre:
                if self._abbruch:  # Frist überschritten: dieses Konto wird nicht geschrieben
                    return
                if fehler is not None:
                    self._konto_scheitert(con, lid, k["iban"], von, bis, *self._pluginfehler(fehler))
                else:
                    self._konto_uebernehmen(con, lid, k, von, bis, umsaetze)
        with self._schreib_sperre:
            if self._abbruch:
                return
            self._abschliessen(con, lid)

    def _konto_scheitert(self, con, lid: int, iban: str, von: dt.date, bis: dt.date, code: str,
                         meldung: str) -> None:
        with db.transaktion(con):
            con.execute("UPDATE sync_lauf_konto SET status = 'fehlgeschlagen', von = ?, bis = ?, fehler_code = ?,"
                        " fehler_meldung = ? WHERE lauf_id = ? AND iban = ?",
                        (von.isoformat(), bis.isoformat(), code, meldung, lid, iban))

    def _abschliessen(self, con, lid: int) -> None:
        with db.transaktion(con):
            fehler = con.execute("SELECT fehler_code, fehler_meldung FROM sync_lauf_konto WHERE lauf_id = ?"
                                 " AND status = 'fehlgeschlagen' ORDER BY iban", (lid,)).fetchall()
            if fehler:
                con.execute("UPDATE sync_lauf SET status = 'fehlgeschlagen', beendet_am = ?, fehler_code = ?,"
                            " fehler_meldung = ? WHERE id = ?",
                            (self.jetzt_text(), fehler[0]["fehler_code"], fehler[0]["fehler_meldung"], lid))
                self._fehler_melden(con, [f["fehler_code"] for f in fehler])
            else:
                con.execute("UPDATE sync_lauf SET status = 'erfolgreich', beendet_am = ? WHERE id = ?",
                            (self.jetzt_text(), lid))
        self._wiederkehrend_nach_lauf(con, lid)

    def _wiederkehrend_nach_lauf(self, con, lid: int) -> None:
        """wiederkehrend.md 5 / synchronisation.md 17.3: nach einem Lauf mit Endstatus auf unerwartete Buchungen
        prüfen – mit den in diesem Lauf neu angelegten, noch existierenden Buchungen von Bankkonten, die vor dem
        Lauf schon einmal erfolgreich abgerufen wurden. Nur bei ``wiederkehrend_automatisch``."""
        if not self.config.wiederkehrend_automatisch:
            return
        ibans = [r["iban"] for r in con.execute("SELECT iban FROM sync_lauf_konto WHERE lauf_id = ?"
                                                " AND vorher_abgerufen = 1", (lid,))]
        ids: set[int] = set()
        if ibans:
            for r in con.execute(
                    "SELECT DISTINCT e.objekt_id AS id FROM aenderung a JOIN aenderung_eintrag e ON e.aenderung_id = a.id"
                    " WHERE a.gruppe = ? AND a.aktion = 'sync_konto' AND e.objekt = 'buchung' AND e.art = 'angelegt'",
                    (f"sync:{lid}",)):
                ids.add(r["id"])
            erlaubt = set()
            for teil in buch._stueckweise(sorted(ids)):
                for r in con.execute(f"SELECT buchung_id, extern_id FROM buchung_extern WHERE buchung_id IN"
                                     f" ({buch._platzhalter(len(teil))})", teil):
                    if any(r["extern_id"].startswith(f"bank:{i}:") for i in ibans):
                        erlaubt.add(r["buchung_id"])
            ids &= erlaubt
        with db.transaktion(con):
            wiederkehrend.pruefen(con, sorted(ids), self.heute().isoformat(), self.jetzt_text())

    # ------------------------------------------------------------- TAN
    def _tan_anlegen(self, con, lid: int, k, von: dt.date, bis: dt.date, e: TanErforderlich, plugin) -> None:
        gueltig = e.gueltig_bis if isinstance(e.gueltig_bis, dt.datetime) else self.jetzt()
        if gueltig.tzinfo is None:
            gueltig = gueltig.replace(tzinfo=UTC)
        bild = e.bild if isinstance(e.bild, (bytes, bytearray)) and e.bild_mime_typ else None
        challenge = (e.challenge or "").strip() or "Bitte die TAN-Anforderung freigeben."
        with db.transaktion(con):
            tid = con.execute(
                "INSERT INTO tan_anforderung (lauf_id, iban, konto_id, status, erstellt_am, gueltig_bis, challenge,"
                " bild, bild_mime_typ) VALUES (?, ?, ?, 'offen', ?, ?, ?, ?, ?)",
                (lid, k["iban"], k["konto_id"], self.jetzt_text(), zeit_text(gueltig), challenge,
                 bytes(bild) if bild is not None else None, e.bild_mime_typ if bild is not None else None)).lastrowid
            con.execute("UPDATE sync_lauf_konto SET status = 'wartet_auf_tan', von = ?, bis = ?"
                        " WHERE lauf_id = ? AND iban = ?", (von.isoformat(), bis.isoformat(), lid, k["iban"]))
            con.execute("UPDATE sync_lauf SET status = 'wartet_auf_tan', tan_anforderung_id = ? WHERE id = ?",
                        (tid, lid))
            self._benachrichtigen(con, "tan_erforderlich", f"tan:{tid}", "TAN erforderlich",
                                  "Die Bank verlangt für den Kontoabruf eine TAN. Bitte die TAN-Seite öffnen, "
                                  "den QR-Code mit der Banking-App scannen und die TAN eingeben.",
                                  link=f"/tan/{tid}", entprellen=False)
        with self._zustand:
            self._tan[tid] = _TanKontext(str(e.anforderung_id), plugin, lid)

    def tan_antworten(self, tid: int, tan: str) -> dict:
        from .plugins.bank import TanAntwort
        con = self._con()
        try:
            self.tan_lesen(con, tid)  # 404
            self.ablauf_pruefen()
            t = self.tan_lesen(con, tid)
            if t["status"] == "abgelaufen":
                raise ApiFehler(409, "tan_abgelaufen", "Die TAN-Anforderung ist abgelaufen.")
            if t["status"] != "offen":
                raise ApiFehler(409, "tan_nicht_offen", "Die TAN-Anforderung ist nicht mehr offen.")
            if not self._sperre.acquire(timeout=60):
                raise ApiFehler(409, "sync_laeuft", "Es läuft bereits eine Synchronisation.")
            try:
                with self._zustand:
                    kontext = self._tan.get(tid)
                if kontext is None:
                    # Kontext verloren (z. B. andere App-Instanz): sauber abbrechen.
                    with db.transaktion(con):
                        self._tan_beenden(con, tid, "abgebrochen")
                        self._lauf_abbrechen(con, t["lauf_id"], self.jetzt_text())
                    raise ApiFehler(409, "tan_nicht_offen", "Die TAN-Anforderung ist nicht mehr offen.")
                lid = t["lauf_id"]
                k = con.execute("SELECT * FROM sync_lauf_konto WHERE lauf_id = ? AND iban = ?",
                                (lid, t["iban"])).fetchone()
                von, bis = dt.date.fromisoformat(k["von"]), dt.date.fromisoformat(k["bis"])
                plugin = kontext.plugin
                try:
                    self._vor_aufruf(plugin)
                    umsaetze = plugin.umsaetze(t["iban"], von, bis, tan=TanAntwort(kontext.anforderung_id, tan))
                except TanUngueltig:
                    raise ApiFehler(422, "tan_ungueltig", "Die TAN wurde von der Bank nicht akzeptiert.") from None
                except TanAbgelaufen:
                    with db.transaktion(con):
                        self._tan_ablaufen(con, tid, lid)
                    raise ApiFehler(409, "tan_abgelaufen", "Die TAN-Anforderung ist abgelaufen.") from None
                except Exception as e:  # noqa: BLE001
                    code, meldung = self._pluginfehler(e)
                    with db.transaktion(con):
                        self._tan_beenden(con, tid, "abgebrochen")
                        con.execute("UPDATE sync_lauf SET status = 'laeuft' WHERE id = ?", (lid,))
                    self._konto_scheitert(con, lid, t["iban"], von, bis, code, meldung)
                else:
                    with db.transaktion(con):
                        self._tan_beenden(con, tid, "beantwortet")
                        con.execute("UPDATE sync_lauf SET status = 'laeuft' WHERE id = ?", (lid,))
                    self._konto_uebernehmen(con, lid, k, von, bis, umsaetze)
                self._fortsetzen(con, lid, plugin)
                return self.lauf_lesen(con, lid)
            finally:
                self._sperre.release()
        finally:
            con.close()

    def _tan_beenden(self, con, tid: int, status: str) -> None:
        con.execute("UPDATE tan_anforderung SET status = ?, beendet_am = ?, bild = NULL WHERE id = ?",
                    (status, self.jetzt_text(), tid))
        with self._zustand:
            self._tan.pop(tid, None)

    def tan_abbrechen(self, tid: int) -> dict:
        con = self._con()
        try:
            self.tan_lesen(con, tid)
            self.ablauf_pruefen()
            with db.transaktion(con):
                t = self.tan_lesen(con, tid)
                if t["status"] == "abgelaufen":
                    raise ApiFehler(409, "tan_abgelaufen", "Die TAN-Anforderung ist abgelaufen.")
                if t["status"] != "offen":
                    raise ApiFehler(409, "tan_nicht_offen", "Die TAN-Anforderung ist nicht mehr offen.")
                self._tan_beenden(con, tid, "abgebrochen")
                self._lauf_abbrechen(con, t["lauf_id"], self.jetzt_text())
            self._wiederkehrend_nach_lauf(con, t["lauf_id"])
            return self.tan_lesen(con, tid)
        finally:
            con.close()

    # ======================================================== Übernahme (4)
    def _konto_uebernehmen(self, con, lid: int, k, von: dt.date, bis: dt.date, umsaetze) -> None:
        iban, kid = k["iban"], k["konto_id"]
        z = dict(umsaetze_gesamt=len(umsaetze), vormerkungen_ignoriert=0, buchungen_vorhanden=0,
                 buchungen_zusammengefuehrt=0, buchungen_neu=0, buchungen_zur_pruefung=0, buchungen_kategorisiert=0,
                 buchungen_gesplittet=0, vorlage_abweichungen=0, buchungen_kredit=0)
        reihe = sorted(umsaetze, key=lambda u: (u.buchungstag, u.umsatz_id))
        neue: set[int] = set()
        with protokoll.protokolliert(con, "sync", "sync_konto", self.jetzt_text(), f"sync:{lid}"):
            offen = []
            gesehen: set[str] = set()
            for u in reihe:
                if u.vormerkung:
                    z["vormerkungen_ignoriert"] += 1
                    continue
                kennung = f"bank:{iban}:{u.umsatz_id}"
                if kennung in gesehen or con.execute("SELECT 1 FROM sync_kennung WHERE kennung = ?",
                                                     (kennung,)).fetchone():
                    z["buchungen_vorhanden"] += 1
                    continue
                gesehen.add(kennung)
                offen.append((u, kennung))
            neue = self._abgleichen_und_buchen(con, kid, iban, offen, z)
            con.execute("UPDATE sync_lauf_konto SET status = 'erfolgreich', von = ?, bis = ?, fehler_code = NULL,"
                        " fehler_meldung = NULL, umsaetze_gesamt = ?, vormerkungen_ignoriert = ?,"
                        " buchungen_vorhanden = ?, buchungen_zusammengefuehrt = ?, buchungen_neu = ?,"
                        " buchungen_zur_pruefung = ?, buchungen_kategorisiert = ?, buchungen_gesplittet = ?,"
                        " vorlage_abweichungen = ?, buchungen_kredit = ? WHERE lauf_id = ? AND iban = ?",
                        (von.isoformat(), bis.isoformat(), z["umsaetze_gesamt"], z["vormerkungen_ignoriert"],
                         z["buchungen_vorhanden"], z["buchungen_zusammengefuehrt"], z["buchungen_neu"],
                         z["buchungen_zur_pruefung"], z["buchungen_kategorisiert"], z["buchungen_gesplittet"],
                         z["vorlage_abweichungen"], z["buchungen_kredit"], lid, iban))
            alt = con.execute("SELECT letzter_abruf_bis FROM sync_konto_zustand WHERE iban = ?", (iban,)).fetchone()
            neu_bis = bis.isoformat()
            if alt is not None and alt["letzter_abruf_bis"] and alt["letzter_abruf_bis"] > neu_bis:
                neu_bis = alt["letzter_abruf_bis"]
            con.execute("INSERT INTO sync_konto_zustand (iban, konto_id, letzter_abruf_bis, letzter_erfolg_am)"
                        " VALUES (?, ?, ?, ?) ON CONFLICT(iban) DO UPDATE SET konto_id = excluded.konto_id,"
                        " letzter_abruf_bis = excluded.letzter_abruf_bis, letzter_erfolg_am = excluded.letzter_erfolg_am",
                        (iban, kid, neu_bis, self.jetzt_text()))
        if neue and self.config.umbuchung_automatisch:
            # buchhaltungspflege.md 4.4: eigene Änderung derselben Gruppe
            with protokoll.protokolliert(con, "umbuchung", "umbuchung_erkennen", self.jetzt_text(), f"sync:{lid}"):
                pflege.umbuchungen_erkennen(con, False, self.config.umbuchung_fenster_tage, neue)
        self._saldo_abgleichen(con, lid, iban, kid, umsaetze)

    # ======================================================= Kontostand (M11)
    def _saldo_abgleichen(self, con, lid: int, iban: str, kid: int, umsaetze: object) -> None:
        """kontostand.md 2: Saldo der Bank mit dem Kontor-Saldo vergleichen, bei Differenz ausgleichen."""
        from .plugins.bank import BankSaldo
        erg: dict = {"status": "aus", "bank_saldo": None, "stichtag": None, "kontor_saldo": None,
                     "differenz": None, "buchung_id": None}
        s = getattr(umsaetze, "saldo", None) if self.config.sync_saldo_angleichen else None
        if self.config.sync_saldo_angleichen:
            erg["status"] = "nicht_verfuegbar"
        if isinstance(s, BankSaldo) and type(s.betrag) is int and isinstance(s.stichtag, dt.date):
            stichtag = s.stichtag.isoformat()
            kontor = con.execute("SELECT COALESCE(SUM(s.betrag), 0) AS summe FROM split s JOIN buchung b"
                                 " ON b.id = s.buchung_id WHERE s.konto_id = ? AND b.datum <= ?",
                                 (kid, stichtag)).fetchone()["summe"]
            differenz = s.betrag - kontor
            erg.update(status="stimmt" if differenz == 0 else "ausgeglichen", bank_saldo=s.betrag,
                       stichtag=stichtag, kontor_saldo=kontor, differenz=differenz)
            if differenz != 0:
                erg["buchung_id"] = self._saldo_ausgleich_buchen(con, lid, iban, kid, stichtag, s.betrag, kontor)
        with db.transaktion(con):
            con.execute("UPDATE sync_lauf_konto SET saldo_abgleich = ? WHERE lauf_id = ? AND iban = ?",
                        (json.dumps(erg, ensure_ascii=False), lid, iban))

    def _saldo_ausgleich_buchen(self, con, lid: int, iban: str, kid: int, stichtag: str, bank: int,
                                kontor: int) -> int:
        """kontostand.md 2 Schritt 5, 2.2, 2.3: Ausgleichsbuchung gegen „Korrekturen“ als eigene Änderung."""
        differenz = bank - kontor
        with protokoll.protokolliert(con, "sync", "sync_saldoausgleich", self.jetzt_text(), f"sync:{lid}"):
            korrektur = pflege.korrektur_id(con)
            basis = f"saldo:{iban}:{stichtag}"
            kennung, n = basis, 1
            while con.execute("SELECT 1 FROM buchung_extern WHERE extern_id = ?", (kennung,)).fetchone():
                n += 1
                kennung = f"{basis}:{n}"
            bid = buch.buchung_einfuegen(
                con, stichtag, None, "Saldoausgleich Bank", "importiert",
                [{"konto_id": kid, "betrag": differenz, "memo": ""},
                 {"konto_id": korrektur, "betrag": -differenz, "memo": ""}], (), [kennung])
            name = con.execute("SELECT name FROM konto WHERE id = ?", (kid,)).fetchone()["name"]
            self._benachrichtigen(
                con, "saldo_ausgeglichen", f"saldo:{iban}", "Kontostand ausgeglichen",
                f"Der Kontostand von „{name}“ weicht von dem der Bank ab: Bank {euro(bank)}, Kontor "
                f"{euro(kontor)} (Stichtag {stichtag}). Die Differenz von {euro(differenz)} wurde gegen "
                "„Korrekturen“ gebucht und kann in der Buchungsliste geprüft werden.", link=f"/konten/{kid}")
        return bid

    def _abgleichen_und_buchen(self, con, kid: int, iban: str, offen: list, z: dict) -> set[int]:
        """4.4: erst alle Umsätze bewerten, dann anwenden; danach 4.2 (Anlegen). Ergebnis: neue Buchungen."""
        praefix = f"bank:{iban}:"
        bewertung = []
        neue: set[int] = set()
        for u, kennung in offen:
            name = (u.gegenpartei_name or "").strip() or None
            if name is not None:
                # M3 (14.1): Empfängername = Name des zugeordneten Empfängers (Alias aufgelöst)
                eid = buch.empfaenger_zu_name(con, name)
                if eid is not None:
                    name = con.execute("SELECT name FROM empfaenger WHERE id = ?", (eid,)).fetchone()["name"]
            tag = u.buchungstag
            exakt, aehnlich = set(), set()
            for c in con.execute(
                    "SELECT DISTINCT b.id AS id, b.datum AS datum, e.name AS name FROM split s"
                    " JOIN buchung b ON b.id = s.buchung_id LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
                    " WHERE s.konto_id = ? AND s.betrag = ?"
                    " AND NOT EXISTS (SELECT 1 FROM buchung_extern x WHERE x.buchung_id = b.id"
                    "                 AND (substr(x.extern_id, 1, ?) = ? OR substr(x.extern_id, 1, 6) = 'saldo:'))",
                    (kid, u.betrag, len(praefix), praefix)):
                c_datum = dt.date.fromisoformat(c["datum"])
                if c_datum == tag and passend(name, c["name"]):
                    exakt.add(c["id"])
                elif abs((c_datum - tag).days) <= 3:
                    aehnlich.add(c["id"])
            bewertung.append((u, kennung, name, exakt, aehnlich - exakt))
        # Kandidaten = Buchungen zu Beginn der Verarbeitung des Kontos: Bewertung ist vor dem Anlegen abgeschlossen.
        zaehler: dict[int, int] = {}
        for _u, _k, _n, exakt, _a in bewertung:
            for c in exakt:
                zaehler[c] = zaehler.get(c, 0) + 1
        regelliste = regeln.aktive_regeln(con)
        vorlagenliste = vorlagen.aktive(con)
        # M4 (lernmodell.md 5.1): Trainingsmenge zu Beginn der Verarbeitung des Kontos
        modell = (lernmodell.trainieren(con) if self.config.lernmodell_automatisch and bewertung else None)
        eigene_ibans = {r["iban"] for r in con.execute("SELECT iban FROM konto WHERE iban IS NOT NULL")}
        kredit_erkennung = kredite.SyncErkennung(con, kid) if bewertung else None  # M5: Stufe 0 (17.1)
        unk_id: int | None = None
        jetzt = self.jetzt_text()
        for u, kennung, name, exakt, aehnlich in bewertung:
            con.execute("INSERT OR IGNORE INTO sync_kennung (kennung) VALUES (?)", (kennung,))
            if len(exakt) == 1 and zaehler[next(iter(exakt))] == 1:
                con.execute("INSERT OR IGNORE INTO buchung_extern (buchung_id, extern_id) VALUES (?, ?)",
                            (next(iter(exakt)), kennung))
                z["buchungen_zusammengefuehrt"] += 1
                continue
            sicht = regeln.Sicht(name, u.verwendungszweck, u.betrag, {kid})
            empf_id = buch.empfaenger_bestimmen(con, name) if name is not None else None
            gegen_iban = pflege.gegen_iban(u.gegenpartei_iban)
            # Stufenfolge (synchronisation.md 15.1): Vorlage → Regel → Standardkategorie → Lernmodell → Unkategorisiert
            rate = kredit_erkennung.erkennen(sicht, u.buchungstag, u.betrag) if kredit_erkennung else None
            erkennung = vorlagen.KEINE if rate is not None else vorlagen.erkennen(vorlagenliste, sicht)
            vorschlag = None  # (kategorie_id, regel_id, quelle, sicherheit)
            status = "importiert"
            if rate is not None:
                plan, zeile = rate
                splits = [{"konto_id": kid, "betrag": u.betrag, "memo": ""}] + kredite.aufteilung(plan.kredit, zeile)
                status = "vorlaeufig"
            elif erkennung.art == "treffer":
                splits = [{"konto_id": kid, "betrag": u.betrag, "memo": ""}] + vorlagen.teile_splits(erkennung.vorlage)
            else:
                if unk_id is None:
                    unk_id = buch.unkategorisiert_id(con)
                gegen = unk_id
                if erkennung.art == "keine" and rate is None:
                    regel = regeln.erste_regel(regelliste, sicht)
                    std = None
                    if regel is None and empf_id is not None:
                        std = con.execute("SELECT standardkategorie_id FROM empfaenger WHERE id = ?",
                                          (empf_id,)).fetchone()["standardkategorie_id"]
                    if regel is not None:
                        vorschlag = (regel["kategorie_id"], regel["id"], "regel", None)
                    elif std is not None:
                        vorschlag = (std, None, "standardkategorie", None)
                    elif modell is not None and gegen_iban not in eigene_ibans:
                        v = modell.vorhersage(lernmodell.merkmale(name, u.verwendungszweck, u.betrag))
                        if v.kategorie_id is not None:
                            vorschlag = (v.kategorie_id, None, "lernmodell", v.sicherheit)
                    if vorschlag is not None:
                        gegen = vorschlag[0]
                splits = [{"konto_id": kid, "betrag": u.betrag, "memo": ""},
                          {"konto_id": gegen, "betrag": -u.betrag, "memo": ""}]
            bid = buch.buchung_einfuegen(con, u.buchungstag.isoformat(), empf_id, u.verwendungszweck, status,
                                         splits, (), [kennung], gegen_iban=gegen_iban)
            neue.add(bid)
            z["buchungen_neu"] += 1
            if rate is not None:
                plan.vergeben.add(zeile["faelligkeit"])
                kredite.zuordnung_eintragen(con, plan.kredit["id"], zeile["faelligkeit"], bid)
                z["buchungen_kredit"] += 1
            if erkennung.art == "treffer":
                z["buchungen_gesplittet"] += 1
            elif erkennung.art == "abweichung":
                z["vorlage_abweichungen"] += 1
                self._split_abweichung_melden(con, erkennung.vorlage, u.betrag, bid)
            if vorschlag is not None:
                con.execute("INSERT INTO vorschlag (buchung_id, kategorie_id, regel_id, quelle, vorher_konto_id,"
                            " sicherheit) VALUES (?, ?, ?, ?, ?, ?)",
                            (bid, vorschlag[0], vorschlag[1], vorschlag[2], unk_id, vorschlag[3]))
                z["buchungen_kategorisiert"] += 1
            kandidaten = exakt | aehnlich
            if kandidaten:
                vid = con.execute("INSERT INTO dublettenverdacht (buchung_id, grund, status, erstellt_am)"
                                  " VALUES (?, ?, 'offen', ?)",
                                  (bid, "mehrdeutig" if exakt else "aehnlich", jetzt)).lastrowid
                con.executemany("INSERT INTO verdacht_kandidat (verdacht_id, buchung_id) VALUES (?, ?)",
                                [(vid, c) for c in sorted(kandidaten)])
                z["buchungen_zur_pruefung"] += 1
        return neue

    def _split_abweichung_melden(self, con, v: dict, betrag: int, bid: int) -> None:
        """vorlagen.md 6: entprellt über den Schlüssel split_abweichung:<vorlage>:<betrag>."""
        self._benachrichtigen(
            con, "split_abweichung", f"split_abweichung:{v['id']}:{betrag}", "Split-Vorlage passt nicht",
            f"Die Buchung über {euro(betrag)} passt zur Split-Vorlage „{v['name']}“, deren Gesamtbetrag "
            f"{euro(v['gesamtbetrag'])} ist. Sie wurde nicht aufgeteilt (keine Toleranz). Bitte die Vorlage "
            "anpassen, z. B. nach einer Beitragsänderung, und die Buchung danach aufteilen.",
            link=f"/buchungen/{bid}")

    # ================================================================ Planer
    def takt(self) -> dict | None:
        """Ein Planer-Takt (synchronisation.md 9 und 18.2)."""
        self.ablauf_pruefen()                     # 1. TAN-Abläufe
        try:
            self.tan_erinnerungen()               # 2. TAN-Erinnerungen
            self.mail.anmeldungen_pruefen()       # 3. Vorwarnung und Ablauf der Mail-Anmeldungen
            lauf = self._lauf_falls_faellig()     # 4. Synchronisationslauf
            if self._beenden:                     # betrieb.md 5.2: nach dem Beenden nichts Neues
                return lauf
            if self.mail.faellig():               # 5. Mail-Abruf
                try:
                    self.mail.abruf()
                except ApiFehler:
                    pass
            abgleich.laufen(self.config, self.jetzt())  # D-128: Fristen prüfen (nur mit mail_abgleich)
            return lauf
        finally:
            if not self._abbruch:
                self.zustellung.neue()            # neue Benachrichtigungen dieses Takts sofort
                self.zustellung.faellige()        # 6. Wiederholung fälliger Zustellungen

    def _lauf_falls_faellig(self) -> dict | None:
        if self.config.sync_intervall_minuten <= 0 or self._beenden:
            return None
        con = self._con()
        try:
            naechster = self._naechster_lauf(con)
        finally:
            con.close()
        if naechster is None or zeit_lesen(naechster) > self.jetzt():
            return None
        try:
            return self.starten("planer", None, None)
        except ApiFehler:
            return None

    def tan_erinnerungen(self) -> None:
        """benachrichtigungen.md 5: höchstens eine Erinnerung je Takt und Anforderung, keine nachgeholt."""
        intervall = self.config.tan_erinnerung_minuten
        hoechst = self.config.tan_erinnerung_anzahl
        if intervall <= 0 or hoechst <= 0:
            return
        jetzt = self.jetzt()
        con = self._con()
        try:
            for r in con.execute("SELECT id, erstellt_am, gueltig_bis, erinnerung_nr FROM tan_anforderung"
                                 " WHERE status = 'offen'").fetchall():
                vergangen = int((jetzt - zeit_lesen(r["erstellt_am"])).total_seconds())
                if vergangen < 0 or jetzt > zeit_lesen(r["gueltig_bis"]):
                    continue
                n = min(vergangen // (intervall * 60), hoechst)
                if n < 1 or n <= r["erinnerung_nr"]:
                    continue
                with db.transaktion(con):
                    con.execute("UPDATE tan_anforderung SET erinnerung_nr = ? WHERE id = ?", (n, r["id"]))
                    buch.benachrichtigung_anlegen(
                        con, "tan_erinnerung", f"tan_erinnerung:{r['id']}:{n}", "Erinnerung: TAN erforderlich",
                        "Die Bank wartet noch auf eine TAN für den Kontoabruf. Bitte die TAN-Seite öffnen und den "
                        "QR-Code scannen, solange die Anforderung gültig ist.", f"/tan/{r['id']}", self.jetzt_text(),
                        "einmal")
        finally:
            con.close()

    def planer_starten(self) -> None:
        automatisch = self.config.sync_intervall_minuten > 0 or self.config.mail_intervall_minuten > 0
        if not automatisch or not self.config.planer_starten or self._thread is not None:
            return
        self._stopp.clear()

        def schleife() -> None:
            if self._stopp.wait(1.0):
                return
            while True:
                try:
                    self.takt()
                except Exception:  # noqa: BLE001
                    log.exception("Fehler im Planer-Takt")
                if self._stopp.wait(30.0):
                    return

        self._thread = threading.Thread(target=schleife, name="kontor-planer", daemon=True)
        self._thread.start()

    def _beim_beenden_abbrechen(self, con, lid: int) -> None:
        with self._schreib_sperre:
            if self._abbruch:
                return
            with db.transaktion(con):
                self._lauf_abbrechen(con, lid, self.jetzt_text())

    def beenden(self) -> None:
        """betrieb.md 5.2 Schritte 1–3: kein neuer Takt/Lauf; ein laufender Lauf darf das aktuelle Konto bis
        ``beenden_frist_sekunden`` fertig verarbeiten, danach wird er abgebrochen (nichts mehr geschrieben)."""
        frist = self.config.beenden_frist_sekunden
        ende = time.monotonic() + frist
        self._beenden = True
        self._stopp.set()
        if self._thread is not None:
            self._thread.join(timeout=frist)
            if not self._thread.is_alive():
                self._thread = None
        if self._sperre.acquire(timeout=max(0.0, ende - time.monotonic())):
            self._sperre.release()  # kein Lauf mehr aktiv
            return
        with self._schreib_sperre:
            self._abbruch = True
            con = self._con()
            try:
                with db.transaktion(con):
                    for r in con.execute("SELECT id FROM sync_lauf WHERE status = 'laeuft'").fetchall():
                        self._lauf_abbrechen(con, r["id"], self.jetzt_text())
            finally:
                con.close()
        log.info("Beim Beenden lief noch eine Synchronisation; sie wurde abgebrochen.")

    def planer_stoppen(self) -> None:
        self._stopp.set()
        if self._thread is not None:
            self._thread.join(timeout=70)
            self._thread = None


def planer_takt(app) -> dict | None:
    """Führt genau einen Planer-Takt synchron aus (python-api.md 8.3)."""
    return app.state.sync.takt()


__all__ = ["planer_takt", "SyncDienst"]
