"""Meilenstein 2 der Wegwerf-Referenz: Regeln, Vorschläge, Synchronisation, TAN, PIN, Planer. KEIN Anwendungscode.

Alles im Arbeitsspeicher (Buch je Datenbankpfad); PIN, Plugin-Instanz, TAN-Interna und
simulierte Uhr je App-Instanz. Mutanten über ``kontor.mutant(name)``.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import re
import threading
from typing import Annotated, Literal

from fastapi import Body, FastAPI
from fastapi.responses import Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from . import mutant
from .buch import KLASSE, MAX, Fehler, ekey, iban_gueltig, norm, passend
from .fehler import KontorFehler, TanAbgelaufen, TanErforderlich, TanUngueltig
from .plugins import erzeuge_bank_plugin
from .plugins.bank import TanAntwort

UTC = dt.timezone.utc
UNK = "kontor:unkategorisiert"
TEXTOPS = {"enthaelt", "gleich", "beginnt_mit"}
BETRAGOPS = {"gleich", "mindestens", "hoechstens"}


def zs(d: dt.datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _v(ort, meldung):
    return Fehler(422, "validierung", "Ungültige Anfrage", [{"ort": ort, "meldung": meldung}])


def _datum(s: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", s):
        raise ValueError("Datum im Format YYYY-MM-DD erwartet")
    dt.date.fromisoformat(s)
    return s


def _eindeutig(v):
    if len(set(v)) != len(v):
        raise ValueError("IDs doppelt")
    return v


Datum = Annotated[StrictStr, AfterValidator(_datum)]
IdListe = Annotated[list[StrictInt], Field(min_length=1), AfterValidator(_eindeutig)]


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegelNeu(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    aktiv: StrictBool = True
    prioritaet: Annotated[StrictInt, Field(ge=0, le=1_000_000)] = None
    kategorie_id: StrictInt
    bedingungen: Annotated[list[dict], Field(min_length=1, max_length=20)]


class RegelAenderung(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)] = None
    aktiv: StrictBool = None
    prioritaet: Annotated[StrictInt, Field(ge=0, le=1_000_000)] = None
    kategorie_id: StrictInt = None
    bedingungen: Annotated[list[dict], Field(min_length=1, max_length=20)] = None


class RegelnAnwenden(M):
    buchung_ids: IdListe = None
    regel_ids: IdListe = None
    nur_unkategorisiert: StrictBool = True
    trocken: StrictBool = False


class VorschlagAktion(M):
    aktion: Literal["annehmen", "ablehnen"]


class MehrfachVorschlag(M):
    buchung_ids: IdListe
    aktion: Literal["annehmen", "ablehnen"]


class SyncAnfrage(M):
    von: Datum = None
    bis: Datum = None


class SyncKontoEntscheidung(M):
    aktion: Literal["wiederherstellen", "ignorieren"]
    buchungen: Literal["alle", "nur_neue"]


def zustand_status(buch, z: dict) -> str:
    """synchronisation.md 16.1: abgeleiteter Status eines Bankkontos."""
    if any(k["iban"] == z["iban"] for k in buch.konten.values()):
        return "aktiv"
    e = z.get("_entscheidung")
    if e is None:
        return "konto_fehlt"
    return "ignoriert" if e[0] == "ignorieren" else "wiederherstellen"


def zustand_json(buch, z: dict) -> dict:
    st = zustand_status(buch, z)
    return {**{f: z[f] for f in ("iban", "konto_id", "letzter_abruf_bis", "letzter_erfolg_am")}, "status": st,
            "wiederherstellen_buchungen": z["_entscheidung"][1] if st == "wiederherstellen" else None}


class PinEingabe(M):
    pin: Annotated[StrictStr, Field(min_length=1, max_length=128)]


class TanEingabe(M):
    tan: Annotated[StrictStr, Field(min_length=1, max_length=64)]


class ZeitEingabe(M):
    jetzt: Annotated[StrictStr, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$")]


# ================================================================ Regeln


def pruefe_bedingungen(buch, liste: list) -> list[dict]:
    aus = []
    for i, b in enumerate(liste):
        ort = ["body", "bedingungen", i]
        if not isinstance(b, dict) or set(b) != {"feld", "operator", "wert"}:
            raise _v(ort, "Bedingung braucht genau feld, operator, wert")
        f, op, w = b["feld"], b["operator"], b["wert"]
        if f in ("empfaenger", "verwendungszweck"):
            if op not in TEXTOPS or not isinstance(w, str) or not (1 <= len(w) <= 200) or not w.strip():
                raise _v(ort, "Textbedingung ungültig")
        elif f == "betrag":
            if op not in BETRAGOPS or type(w) is not int or not -MAX <= w <= MAX:
                raise _v(ort, "Betragsbedingung ungültig")
        elif f == "konto_id":
            if op != "gleich" or type(w) is not int:
                raise _v(ort, "Kontobedingung ungültig")
        else:
            raise _v(ort, "Feld unbekannt")
        aus.append({"feld": f, "operator": op, "wert": w})
    for b in aus:
        if b["feld"] == "konto_id" and (b["wert"] not in buch.konten
                                        or KLASSE[buch.konten[b["wert"]]["art"]] != "bestand"):
            raise Fehler(422, "referenz_unbekannt", "Konto der Bedingung unbekannt")
    return aus


def pruefe_kategorie(buch, kid: int) -> None:
    if kid not in buch.konten or buch.konten[kid]["art"] not in ("aufwand", "ertrag"):
        raise Fehler(422, "kategorie_ungueltig", "Keine Kategorie")


def geordnet(buch, nur_ids=None) -> list[dict]:
    rs = [r for r in buch.regeln.values() if (r["aktiv"] or mutant("regel_inaktiv_greift"))
          and (nur_ids is None or r["id"] in nur_ids)]
    if mutant("regel_prioritaet_umgekehrt"):
        return sorted(rs, key=lambda r: (-r["prioritaet"], r["id"]))
    if mutant("regel_gleichstand_spaeter"):
        return sorted(rs, key=lambda r: (r["prioritaet"], -r["id"]))
    return sorted(rs, key=lambda r: (r["prioritaet"], r["id"]))


def _n(s: str) -> str:
    return s.casefold() if mutant("regel_ohne_umlaute") else norm(s)


def trifft(b: dict, empf: str | None, zweck: str, betrag: int, konten: set[int]) -> bool:
    f, op, w = b["feld"], b["operator"], b["wert"]
    if f in ("empfaenger", "verwendungszweck"):
        x = empf if f == "empfaenger" else zweck
        if x is None:
            return False
        nx, nw = _n(x), _n(w)
        return {"enthaelt": nw in nx, "gleich": nx == nw, "beginnt_mit": nx.startswith(nw)}[op]
    if f == "betrag":
        if mutant("regelbetrag_absolut"):
            betrag = abs(betrag)
        return {"gleich": betrag == w, "mindestens": betrag >= w, "hoechstens": betrag <= w}[op]
    return w in konten


def regel_fuer(regeln: list[dict], empf, zweck, betrag, konten) -> dict | None:
    for r in regeln:
        if all(trifft(b, empf, zweck, betrag, konten) for b in r["bedingungen"]):
            return r
    return None


def sicht(buch, b: dict):
    e = buch.empfaenger[b["empfaenger_id"]]["name"] if b["empfaenger_id"] is not None else None
    bestand = [s for s in b["splits"] if KLASSE[buch.konten[s["konto_id"]]["art"]] == "bestand"]
    return e, b["verwendungszweck"], sum(s["betrag"] for s in bestand), {s["konto_id"] for s in b["splits"]}


def unkategorisiert(buch) -> int:
    for k in buch.konten.values():
        if k["extern_id"] == UNK:
            return k["id"]
    return buch.konto_anlegen({"name": "Unkategorisiert", "art": "eigenkapital"}, extern_id=UNK)["id"]


def setze_vorschlag(buch, b: dict, r: dict) -> None:
    g = buch.gegensplits(b)[0]
    alt = b["splits"][g]["konto_id"]
    vorher = b["vorschlag"]["vorher_konto_id"] if b.get("vorschlag") else alt
    b["splits"][g]["konto_id"] = r["kategorie_id"]
    if not mutant("vorschlag_nicht_markiert"):
        b["vorschlag"] = {"kategorie_id": r["kategorie_id"], "regel_id": r["id"], "quelle": "regel",
                          "vorher_konto_id": vorher}


# ================================================================ Synchronisation


class Dienst:
    """Je App-Instanz: Uhr, PIN, Plugin-Instanz, TAN-Interna."""

    def __init__(self, config, buch) -> None:
        self.config, self.buch = config, buch
        self.zeit: dt.datetime | None = None
        self.pin: str | None = None
        self.pin_lesen = lambda: self.pin          # M6: systemd-creds ersetzt die Quelle (fints.md 5)
        self.pin_gesperrt = False
        self.neu_gemeldet = lambda: None             # M6: Zustellung sofort nach dem Entstehen
        self.plugin = None
        self.intern: dict[int, dict] = {}
        self.sperre = threading.RLock()
        self.beenden = threading.Event()          # M7: Lifespan-Ende (betrieb.md 5.2)
        self.frist_ende = None
        jetzt = self.jetzt()
        for lauf in buch.laeufe.values():
            if lauf["status"] in ("laeuft", "wartet_auf_tan") and not mutant("neustart_ohne_abbruch"):
                self._abbrechen(lauf, jetzt)
        for t in buch.tan.values():
            if t["status"] == "offen" and not mutant("neustart_ohne_abbruch"):
                t["status"], t["beendet_am"] = "abgebrochen", zs(jetzt)

    # ---------------------------------------------------------- Uhr
    def jetzt(self) -> dt.datetime:
        if self.config.mock_modus:
            if self.zeit is not None:
                return self.zeit
            if self.config.mock_heute is not None:
                return dt.datetime.combine(self.config.mock_heute, dt.time(12), UTC)
        return dt.datetime.now(UTC).replace(microsecond=0)

    def heute(self) -> dt.date:
        return self.jetzt().date()

    # ------------------------------------------------- Benachrichtigung
    def melden(self, art: str, schluessel: str, titel: str, text: str, link: str | None = None) -> None:
        b = self.buch
        if not mutant("benachrichtigung_flut") and any(
                x["schluessel"] == schluessel and not x["gelesen"] for x in b.benachr.values()):
            return
        bid = b.neue_id("benachrichtigung")
        b.benachr[bid] = {"id": bid, "art": art, "schluessel": schluessel, "titel": titel, "text": text,
                          "link": link, "erstellt_am": zs(self.jetzt()), "gelesen": False}
        self.neu_gemeldet()

    # ------------------------------------------------------- Plugin
    def _plugin(self):
        if self.plugin is None:
            self.plugin = erzeuge_bank_plugin(self.config, pin_quelle=lambda: self.pin_lesen())
        if self.config.mock_modus:
            self.plugin.setze_heute(self.heute())
        return self.plugin

    @staticmethod
    def _fk(e: BaseException) -> dict:
        if isinstance(e, KontorFehler):
            return {"code": e.code, "meldung": e.meldung or e.code}
        return {"code": "plugin_fehler", "meldung": "Unerwarteter Fehler des Bank-Plugins"}

    def _pin_falsch(self, e) -> None:
        if getattr(e, "code", "") in ("bank_pin_falsch", "bank_zugang_gesperrt") and not mutant("pin_nicht_verworfen"):
            self.pin = None
            if not mutant("pin_systemd_nicht_gesperrt"):
                self.pin_gesperrt = True

    # ------------------------------------------------------- Ablauf
    def pruefe_ablauf(self) -> None:
        if mutant("tan_ablauf_ignoriert"):
            return
        jetzt = self.jetzt()
        for t in self.buch.tan.values():
            if t["status"] == "offen" and jetzt > zeit(t["gueltig_bis"]):
                self._tan_ende(t, "abgelaufen", jetzt)
                self.melden("tan_abgelaufen", f"tan_abgelaufen:{t['id']}", "TAN abgelaufen",
                            "Die TAN-Anforderung ist abgelaufen; die Synchronisation wurde abgebrochen.")

    def _tan_ende(self, t, status, jetzt) -> None:
        t["status"], t["beendet_am"] = status, zs(jetzt)
        self.intern.pop(t["id"], None)
        if status in ("abgelaufen", "abgebrochen"):
            self._abbrechen(self.buch.laeufe[t["lauf_id"]], jetzt)

    def _abbrechen(self, lauf, jetzt) -> None:
        if lauf["status"] in ("laeuft", "wartet_auf_tan"):
            lauf["status"], lauf["beendet_am"] = "abgebrochen", zs(jetzt)
            for k in lauf["konten"]:
                if k["status"] in ("wartet_auf_tan", "ausstehend"):
                    k["status"] = "abgebrochen"

    def offene_tan(self):
        return next((t for t in self.buch.tan.values() if t["status"] == "offen"), None)

    # --------------------------------------------------------- Lauf
    def starte(self, ausloeser: str, von: str | None, bis: str | None) -> dict:
        b = self.buch
        if von and bis and von > bis:
            raise _v(["body", "von"], "von > bis")
        self.pruefe_ablauf()
        if self.offene_tan():
            raise Fehler(409, "tan_ausstehend", "Eine TAN-Anforderung ist offen")
        if any(x["status"] == "laeuft" for x in b.laeufe.values()):
            raise Fehler(409, "sync_laeuft", "Es läuft bereits eine Synchronisation")
        lid = b.neue_id("lauf")
        lauf = {"id": lid, "ausloeser": ausloeser, "status": "laeuft", "gestartet_am": zs(self.jetzt()),
                "beendet_am": None, "von": von, "bis": bis, "fehler": None, "tan_anforderung_id": None, "konten": [],
                "uebersprungen": []}
        b.laeufe[lid] = lauf
        try:
            konten = self._plugin().konten()
        except Exception as e:  # noqa: BLE001
            self._pin_falsch(e)
            lauf["fehler"] = self._fk(e)
            self._ende(lauf)
            return lauf
        from .m3 import protokolliere, protokollform
        vorher = protokollform(b)
        lauf["uebersprungen"] = []
        for bk in sorted(konten, key=lambda k: k.iban):
            vorh = next((k for k in b.konten.values() if k["iban"] == bk.iban), None)
            z = b.sync_konten.get(bk.iban)
            neu = vorh is None
            # synchronisation.md 16.2: gelöschte Bankkonten nicht still neu anlegen
            if neu and z is not None and not mutant("sync_geloeschtes_neu"):
                status = zustand_status(b, z)
                if status in ("konto_fehlt", "ignoriert"):
                    name = bk.name.strip() or bk.iban
                    lauf["uebersprungen"].append({"iban": bk.iban, "name": name, "status": status})
                    if status == "konto_fehlt":
                        self.melden("konto_fehlt", f"konto_fehlt:{bk.iban}", "Bankkonto ohne Konto",
                                    f"Das Konto „{name}“ ({bk.iban}) wurde gelöscht. Soll es wiederhergestellt "
                                    "oder das Bankkonto ignoriert werden?", "/sync/konten")
                    continue
            if neu and z is None and not self.config.sync_konten_anlegen and not mutant("m15_sync_legt_an"):
                # M15, synchronisation.md 20.2: unbekanntes Bankkonto überspringen und melden
                name = bk.name.strip() or bk.iban
                art = bk.art if bk.art in ("girokonto", "sparkonto", "kreditkonto") else "girokonto"
                lauf["uebersprungen"].append({"iban": bk.iban, "name": name, "status": "nicht_zugeordnet", "art": art})
                self.melden("konto_nicht_zugeordnet", f"konto_nicht_zugeordnet:{bk.iban}", "Bankkonto nicht zugeordnet",
                            f"Das Bankkonto „{name}“ ({bk.iban}) ist keinem Konto zugeordnet.", "/sync")
                continue
            if neu:
                vorh = b.konto_anlegen({"name": b.freier_name(bk.name.strip() or bk.iban, bk.art), "art": bk.art,
                                        "iban": bk.iban})   # M32: Zusatz „ (2)“ bei gleichem Namen
            if neu and z is not None and z.get("_entscheidung") == ("wiederherstellen", "alle"):
                praefix = f"bank:{bk.iban}:"
                an_buchungen = {e for c in b.buchungen.values() for e in c["extern_ids"]}
                if mutant("wiederherstellen_vergisst_alle"):
                    an_buchungen = set()
                if not mutant("wiederherstellen_ohne_vergessen"):
                    b.gemerkt -= {e for e in b.gemerkt if e.startswith(praefix) and e not in an_buchungen}
                if not mutant("wiederherstellen_zeitraum_bleibt"):
                    z["letzter_abruf_bis"] = None
            if neu and z is not None:
                z["_wiederhergestellt"] = vorh["id"]
            if z is not None:
                z.pop("_entscheidung", None)
            z = b.sync_konten.setdefault(bk.iban, {"iban": bk.iban, "konto_id": vorh["id"], "letzter_abruf_bis": None,
                                                    "letzter_erfolg_am": None})
            z["konto_id"] = vorh["id"]
            lauf["konten"].append(self._sk(bk.iban, vorh["id"], neu, "ausstehend"))
        lauf["uebersprungen"].sort(key=lambda x: x["iban"])
        protokolliere(b, vorher, "sync", "sync_kontozuordnung", f"sync:{lid}", zs(self.jetzt()),
                      "Bankkonten zugeordnet")
        self._weiter(lauf, None)
        return lauf

    @staticmethod
    def _sk(iban, kid, neu, status) -> dict:
        return {"iban": iban, "konto_id": kid, "konto_neu": neu, "status": status, "von": None, "bis": None,
                "umsaetze_gesamt": 0, "vormerkungen_ignoriert": 0, "buchungen_vorhanden": 0,
                "buchungen_zusammengefuehrt": 0, "buchungen_neu": 0, "buchungen_zur_pruefung": 0,
                "buchungen_kategorisiert": 0, "buchungen_gesplittet": 0, "vorlage_abweichungen": 0, "buchungen_kredit": 0,
                "fehler": None, "saldo_abgleich": None}

    def _zeitraum(self, lauf, sk) -> tuple[str, str]:
        heute = self.heute()
        bis = lauf["bis"] or heute.isoformat()
        if lauf["von"]:
            von = lauf["von"]
        else:
            letzter = self.buch.sync_konten[sk["iban"]]["letzter_abruf_bis"]
            if letzter:
                tage = -1 if mutant("sync_von_ohne_ueberlappung") else self.config.sync_ueberlappung_tage
                von = (dt.date.fromisoformat(letzter) - dt.timedelta(days=tage)).isoformat()
            else:
                von = (heute - dt.timedelta(days=self.config.sync_erstabruf_tage)).isoformat()
        return min(von, bis), bis

    def _weiter(self, lauf, tan: tuple | None) -> None:
        """Verarbeitet wartende/ausstehende Konten; tan = (Konto-Eintrag, TanAntwort) für das wartende."""
        import time as _zeit
        for sk in lauf["konten"]:
            if sk["status"] not in ("ausstehend", "wartet_auf_tan"):
                continue
            if self.beenden.is_set() or lauf["status"] == "abgebrochen":
                self.abbrechen_beim_beenden(lauf)
                return
            if sk["status"] == "ausstehend":
                sk["von"], sk["bis"] = self._zeitraum(lauf, sk)
            kw = {"tan": tan[1]} if tan and tan[0] is sk else {}
            try:
                if self.config.mock_modus and self.config.mock_verzoegerung_ms:
                    _zeit.sleep(self.config.mock_verzoegerung_ms / 1000)
                us = self._plugin().umsaetze(sk["iban"], dt.date.fromisoformat(sk["von"]),
                                             dt.date.fromisoformat(sk["bis"]), **kw)
                if lauf["status"] == "abgebrochen" or (self.beenden.is_set() and self.frist_ende is not None
                                                       and _zeit.monotonic() > self.frist_ende):
                    self.abbrechen_beim_beenden(lauf)
                    return
            except TanErforderlich as e:
                sk["status"] = "wartet_auf_tan"
                self._tan_neu(lauf, sk, e)
                return
            except (TanUngueltig, TanAbgelaufen):
                raise
            except Exception as e:  # noqa: BLE001
                self._pin_falsch(e)
                sk["status"], sk["fehler"] = "fehlgeschlagen", self._fk(e)
                lauf["fehler"] = lauf["fehler"] or sk["fehler"]
                continue
            self._uebernehmen(sk, us)
        self._ende(lauf)

    def abbrechen_beim_beenden(self, lauf) -> None:
        """betrieb.md 5.2: nicht verarbeitete Konten und der Lauf werden abgebrochen."""
        for k in lauf["konten"]:
            if k["status"] in ("ausstehend", "wartet_auf_tan"):
                k["status"] = "abgebrochen"
        if lauf["beendet_am"] is None:
            lauf["status"] = "abgebrochen"
            lauf["beendet_am"] = zs(self.jetzt())

    def _ende(self, lauf) -> None:
        if lauf["fehler"] is None and any(k["status"] == "fehlgeschlagen" for k in lauf["konten"]):
            lauf["fehler"] = next(k["fehler"] for k in lauf["konten"] if k["status"] == "fehlgeschlagen")
        lauf["status"] = "fehlgeschlagen" if lauf["fehler"] else "erfolgreich"
        lauf["beendet_am"] = zs(self.jetzt())
        codes = []
        if lauf["fehler"]:
            codes.append(lauf["fehler"]["code"])
        codes += [k["fehler"]["code"] for k in lauf["konten"] if k["fehler"]]
        for c in dict.fromkeys(codes):
            self.melden("sync_fehler", f"sync_fehler:{c}", "Synchronisation fehlgeschlagen",
                        f"Der Abruf bei der Bank ist fehlgeschlagen (Code {c}). Er wird später wiederholt.")
        neu = self.__dict__.setdefault("_lauf_neu", {}).pop(lauf["id"], set())
        if self.config.wiederkehrend_automatisch:  # wiederkehrend.md 5
            from .m5 import pruefen
            pruefen(self, sorted(i for i in neu if i in self.buch.buchungen))

    def _tan_neu(self, lauf, sk, e) -> None:
        b = self.buch
        tid = b.neue_id("tan")
        b.tan[tid] = {"id": tid, "lauf_id": lauf["id"], "iban": sk["iban"], "konto_id": sk["konto_id"],
                      "status": "offen", "erstellt_am": zs(self.jetzt()), "gueltig_bis": zs(e.gueltig_bis),
                      "beendet_am": None, "challenge": e.challenge, "hat_bild": e.bild is not None}
        self.intern[tid] = {"anforderung_id": e.anforderung_id, "bild": e.bild, "mime": e.bild_mime_typ}
        lauf["status"], lauf["tan_anforderung_id"] = "wartet_auf_tan", tid
        self.melden("tan_erforderlich", f"tan:{tid}", "TAN erforderlich",
                    "Die Bank verlangt eine TAN. Bitte auf der TAN-Seite freigeben.", f"/tan/{tid}")

    def antworten(self, tid: int, tan: str) -> dict:
        t = self._tan(tid)
        self.pruefe_ablauf()
        if t["status"] == "abgelaufen":
            raise Fehler(409, "tan_abgelaufen", "TAN-Anforderung abgelaufen")
        if t["status"] != "offen":
            raise Fehler(409, "tan_nicht_offen", "TAN-Anforderung nicht offen")
        lauf = self.buch.laeufe[t["lauf_id"]]
        sk = next(k for k in lauf["konten"] if k["status"] == "wartet_auf_tan")
        aid = self.intern[tid]["anforderung_id"]
        try:
            self._weiter_mit_tan(lauf, sk, t, TanAntwort(aid, tan))
        except TanUngueltig:
            raise Fehler(422, "tan_ungueltig", "Die Bank hat die TAN abgelehnt") from None
        except TanAbgelaufen:
            self._tan_ende(t, "abgelaufen", self.jetzt())
            raise Fehler(409, "tan_abgelaufen", "TAN-Anforderung abgelaufen") from None
        return lauf

    def _weiter_mit_tan(self, lauf, sk, t, antwort) -> None:
        try:
            us = self._plugin().umsaetze(sk["iban"], dt.date.fromisoformat(sk["von"]), dt.date.fromisoformat(sk["bis"]),
                                         tan=antwort)
        except (TanUngueltig, TanAbgelaufen):
            raise
        except TanErforderlich as e:
            self._tan_ende(t, "beantwortet", self.jetzt())
            self._tan_neu(lauf, sk, e)
            return
        except Exception as e:  # noqa: BLE001
            t["status"], t["beendet_am"] = "abgebrochen", zs(self.jetzt())
            self.intern.pop(t["id"], None)
            sk["status"], sk["fehler"] = "fehlgeschlagen", self._fk(e)
            lauf["fehler"] = lauf["fehler"] or sk["fehler"]
            lauf["status"] = "laeuft"
            self._weiter(lauf, None)
            return
        t["status"], t["beendet_am"] = "beantwortet", zs(self.jetzt())
        self.intern.pop(t["id"], None)
        lauf["status"] = "laeuft"
        self._uebernehmen(sk, us)
        self._weiter(lauf, None)

    def abbrechen(self, tid: int) -> dict:
        t = self._tan(tid)
        self.pruefe_ablauf()
        if t["status"] == "abgelaufen":
            raise Fehler(409, "tan_abgelaufen", "TAN-Anforderung abgelaufen")
        if t["status"] != "offen":
            raise Fehler(409, "tan_nicht_offen", "TAN-Anforderung nicht offen")
        self._tan_ende(t, "abgebrochen", self.jetzt())
        return t

    def _tan(self, tid):
        if tid not in self.buch.tan:
            raise Fehler(404, "nicht_gefunden", "TAN-Anforderung nicht gefunden")
        return self.buch.tan[tid]

    # ---------------------------------------------------- Übernahme
    def _uebernehmen(self, sk: dict, us: list, lauf_id: int | None = None) -> None:
        from . import m3
        b = self.buch
        vorher = m3.protokollform(b)
        schon_abgerufen = b.sync_konten[sk["iban"]]["letzter_erfolg_am"] is not None
        neue_ids = self._uebernehmen_roh(sk, us)
        lauf_id = lauf_id if lauf_id is not None else self._lauf_von(sk)
        if schon_abgerufen or mutant("wieder_erstabruf_meldet"):  # wiederkehrend.md 5
            self.__dict__.setdefault("_lauf_neu", {}).setdefault(lauf_id, set()).update(neue_ids)
        if not mutant("protokoll_sync_fehlt"):
            m3.protokolliere(b, vorher, "sync", "sync_konto", f"sync:{lauf_id}", zs(self.jetzt()),
                             f"Umsätze von {sk['iban']} übernommen")
        if self.config.umbuchung_automatisch and neue_ids:
            vorher = m3.protokollform(b)
            for x, y in m3.eindeutige_paare(b, self.config.umbuchung_fenster_tage):
                if x in neue_ids or y in neue_ids:
                    m3.umbuchung_zusammenfuehren(b, x, y)
            m3.protokolliere(b, vorher, "umbuchung", "umbuchung_erkennen", f"sync:{lauf_id}", zs(self.jetzt()),
                             "Umbuchungen erkannt")
        self._saldo_abgleich(sk, lauf_id, us)

    def _saldo_abgleich(self, sk: dict, lauf_id: int, us) -> None:
        """M11, kontostand.md 2."""
        from . import m3
        b = self.buch
        leer = {"bank_saldo": None, "stichtag": None, "kontor_saldo": None, "differenz": None, "buchung_id": None}
        if not self.config.sync_saldo_angleichen:
            sk["saldo_abgleich"] = {"status": "aus", **leer}
            return
        s = getattr(us, "saldo", None)
        if s is None:
            sk["saldo_abgleich"] = {"status": "nicht_verfuegbar", **leer}
            return
        kid = sk["konto_id"]
        stichtag = s.stichtag.isoformat()
        if mutant("saldo_ohne_stichtag"):
            stichtag = "9999-12-31"
        ks = sum(x["betrag"] for c in b.buchungen.values() if c["datum"] <= stichtag
                 for x in c["splits"] if x["konto_id"] == kid)
        d = s.betrag - ks
        if mutant("saldo_vorzeichen"):
            d = -d
        erg = {"status": "stimmt", "bank_saldo": s.betrag, "stichtag": s.stichtag.isoformat(), "kontor_saldo": ks,
               "differenz": d, "buchung_id": None}
        if d != 0 and not mutant("saldo_kein_ausgleich"):
            vorher = m3.protokollform(b)
            korr = next((k["id"] for k in b.konten.values() if k["extern_id"] == m3.KORR), None) or \
                b.konto_anlegen({"name": "Korrekturen", "art": "eigenkapital"}, extern_id=m3.KORR)["id"]
            basis = f"saldo:{sk['iban']}:{s.stichtag.isoformat()}"
            vergeben = {e for c in b.buchungen.values() for e in c["extern_ids"]}
            kennung, n = basis, 1
            while kennung in vergeben and not mutant("saldo_kennung_doppelt"):
                n += 1
                kennung = f"{basis}:{n}"
            nb = b.buchung_anlegen({"datum": s.stichtag.isoformat(), "verwendungszweck": "Saldoausgleich Bank",
                                    "status": "importiert", "splits": [{"konto_id": kid, "betrag": d, "memo": ""},
                                                                       {"konto_id": korr, "betrag": -d, "memo": ""}]},
                                   extern_ids=[kennung])
            m3.protokolliere(b, vorher, "sync", "sync_saldoausgleich", f"sync:{lauf_id}", zs(self.jetzt()),
                             "Saldoausgleich " + sk["iban"])
            erg.update(status="ausgeglichen", buchung_id=nb["id"])
            from .m5 import betrag_text  # noqa: PLC0415
            name = b.konten[kid]["name"]
            self.melden("saldo_ausgeglichen", f"saldo:{sk['iban']}", "Kontostand ausgeglichen",
                        f"{name}: Bank {betrag_text(s.betrag)}, Kontor {betrag_text(ks)}, Differenz {betrag_text(d)} "
                        "als Ausgleichsbuchung gebucht.", f"/konten/{kid}")
        sk["saldo_abgleich"] = erg

    def _lauf_von(self, sk: dict) -> int:
        return next(l["id"] for l in self.buch.laeufe.values() if any(x is sk for x in l["konten"]))

    def _uebernehmen_roh(self, sk: dict, us: list) -> set[int]:
        from . import m3
        b = self.buch
        iban, k = sk["iban"], sk["konto_id"]
        neue_ids: set[int] = set()
        sk["status"], sk["umsaetze_gesamt"] = "erfolgreich", len(us)
        praefix = f"bank:{iban}:"
        kandidaten = [] if mutant("sync_kein_abgleich") else [
            c for c in b.buchungen.values() if not any(e.startswith(praefix) for e in c["extern_ids"])]
        bekannt = set(b.gemerkt)
        if mutant("sync_geloeschte_wieder"):
            bekannt = {e for c in b.buchungen.values() for e in c["extern_ids"]}
        if mutant("sync_ohne_kennung"):
            bekannt = set()
        N = []
        for u in us:
            if u.vormerkung and not mutant("sync_vormerkung_gebucht"):
                sk["vormerkungen_ignoriert"] += 1
            elif praefix + u.umsatz_id in bekannt:
                sk["buchungen_vorhanden"] += 1
            else:
                N.append(u)

        def name(u):
            n = (u.gegenpartei_name or "").strip() or None
            e = m3.empfaenger_suchen(b, n)
            return e["name"] if e else n

        def cname(c):
            return b.empfaenger[c["empfaenger_id"]]["name"] if c["empfaenger_id"] is not None else None

        E, A = {}, {}
        for u in N:
            e, a = set(), set()
            for c in kandidaten:
                if not any(s["konto_id"] == k and s["betrag"] == u.betrag for s in c["splits"]):
                    continue
                if c["datum"] == u.buchungstag.isoformat() and passend(name(u), cname(c)):
                    e.add(c["id"])
                elif abs((dt.date.fromisoformat(c["datum"]) - u.buchungstag).days) <= 3:
                    a.add(c["id"])
            E[u.umsatz_id], A[u.umsatz_id] = e, a - e
        regeln = geordnet(b)
        self._lern = None  # Trainingsmenge zu Beginn der Verarbeitung des Kontos (lernmodell.md 5.1)
        if self.config.lernmodell_automatisch:
            from .m4 import Lernmodell
            self._lern = Lernmodell(b)
        for u in N:
            kennung = praefix + u.umsatz_id
            e = E[u.umsatz_id]
            if len(e) == 1 and not any(next(iter(e)) in E[v.umsatz_id] for v in N if v is not u):
                c = b.buchungen[next(iter(e))]
                c["extern_ids"].append(kennung)
                b.gemerkt.add(kennung)
                sk["buchungen_zusammengefuehrt"] += 1
                continue
            nb = self._buchung(u, k, kennung, regeln, sk)
            neue_ids.add(nb["id"])
            sk["buchungen_neu"] += 1
            if e or A[u.umsatz_id]:
                vid = b.neue_id("verdacht")
                b.verdachte[vid] = {"id": vid, "buchung_id": nb["id"], "kandidat_ids": sorted(e | A[u.umsatz_id]),
                                    "grund": "mehrdeutig" if e else "aehnlich", "status": "offen",
                                    "erstellt_am": zs(self.jetzt())}
                sk["buchungen_zur_pruefung"] += 1
        z = b.sync_konten[iban]
        z["letzter_abruf_bis"] = max(z["letzter_abruf_bis"] or sk["bis"], sk["bis"])
        z["letzter_erfolg_am"] = zs(self.jetzt())
        return neue_ids

    def _buchung(self, u, k, kennung, regeln, sk) -> dict:
        from . import m3
        b = self.buch
        n = (u.gegenpartei_name or "").strip() or None
        eid = None
        if n is not None:
            eid = m3.empfaenger_fuer_name(b, n)
            n = b.empfaenger[eid]["name"]
        gi = (u.gegenpartei_iban or "").replace(" ", "").upper() or None
        if gi is not None and not iban_gueltig(gi):
            gi = None
        from . import m5
        treffer = m5.sync_treffer(b, k, n, u.verwendungszweck, u.buchungstag.isoformat(), u.betrag)
        if treffer is not None:  # kredite.md 4.2: Stufe 0
            kr, zeile = treffer
            nb = b.buchung_anlegen({"datum": u.buchungstag.isoformat(), "empfaenger_id": eid,
                                    "verwendungszweck": u.verwendungszweck, "status": m5.STATUS_RATE(),
                                    "gegen_iban": gi, "splits": [{"konto_id": k, "betrag": u.betrag, "memo": ""}]
                                    + m5.rate_splits(kr, zeile)}, [kennung])
            b.gemerkt.add(kennung)
            m5.zuordnung_eintragen(kr, zeile["faelligkeit"], nb["id"])
            sk["buchungen_kredit"] += 1
            return nb
        unk = unkategorisiert(b)
        nb = b.buchung_anlegen({"datum": u.buchungstag.isoformat(), "empfaenger_id": eid,
                                "verwendungszweck": u.verwendungszweck, "status": "importiert", "gegen_iban": gi,
                                "splits": [{"konto_id": k, "betrag": u.betrag, "memo": ""},
                                           {"konto_id": unk, "betrag": -u.betrag, "memo": ""}]}, [kennung])
        b.gemerkt.add(kennung)
        from . import m4
        art, v = m4.erkenne(b, n, u.verwendungszweck, {k}, u.betrag)
        if art == "treffer" and not mutant("vorlage_nicht_angewendet"):
            nb["splits"] = [nb["splits"][0]] + m4.teil_splits(b, v)
            sk["buchungen_gesplittet"] += 1
            return nb
        if art == "abweichung":
            sk["vorlage_abweichungen"] += 1
            if not mutant("vorlage_ohne_benachrichtigung"):
                g = -sum(t["betrag"] for t in v["teile"])
                self.melden("split_abweichung", f"split_abweichung:{v['id']}:{u.betrag}", "Sammelabbuchung weicht ab",
                            f"Die Buchung über {u.betrag / 100:.2f} € passt nicht zur Vorlage „{v['name']}“ "
                            f"({g / 100:.2f} €) und wurde nicht aufgeteilt.", f"/buchungen/{nb['id']}")
            if not mutant("vorlage_abweichung_mit_regel"):
                return nb
        std = b.empfaenger[eid].get("standardkategorie_id") if eid is not None else None
        if mutant("standardkategorie_vor_regel") and std is not None:
            r = {"id": None, "kategorie_id": std}
        else:
            r = regel_fuer(regeln, n, u.verwendungszweck, u.betrag, {k})
        if r is not None:
            setze_vorschlag(b, nb, r)
            sk["buchungen_kategorisiert"] += 1
        elif std is not None:
            setze_vorschlag(b, nb, {"id": None, "kategorie_id": std})
            sk["buchungen_kategorisiert"] += 1
        if nb.get("vorschlag") and nb["vorschlag"]["regel_id"] is None:
            nb["vorschlag"]["quelle"] = "standardkategorie"
        eigen = gi is not None and any(x["iban"] == gi for x in b.konten.values())
        if nb.get("vorschlag") is None and getattr(self, "_lern", None) is not None and \
                (not eigen or mutant("lern_bei_eigener_iban")):
            lv = self._lern.vorhersage(n, u.verwendungszweck, u.betrag)
            if lv["kategorie_id"] is not None:
                nb["splits"][1]["konto_id"] = lv["kategorie_id"]
                nb["vorschlag"] = {"kategorie_id": lv["kategorie_id"], "regel_id": None, "quelle": "lernmodell",
                                   "vorher_konto_id": unk, "sicherheit": lv["sicherheit"]}
                sk["buchungen_kategorisiert"] += 1
        return nb

    # -------------------------------------------------------- Planer
    def naechster(self) -> dt.datetime | None:
        c = self.config
        if c.sync_intervall_minuten <= 0:
            return None
        ls = sorted(self.buch.laeufe.values(), key=lambda x: x["id"])
        if any(x["status"] in ("laeuft", "wartet_auf_tan") for x in ls):
            return None
        fertig = [x for x in ls if x["beendet_am"]]
        if not fertig:
            return self.jetzt()
        letzter = fertig[-1]
        minuten = c.sync_wiederholung_minuten if letzter["status"] == "fehlgeschlagen" and \
            not mutant("planer_ohne_wiederholung") else c.sync_intervall_minuten
        return zeit(letzter["beendet_am"]) + dt.timedelta(minutes=minuten)

    def takt(self) -> dict | None:
        with self.sperre:
            self.pruefe_ablauf()
            n = self.naechster()
            if n is None or n > self.jetzt():
                return None
            return self.starte("planer", None, None)

    def status(self) -> dict:
        self.pruefe_ablauf()
        ls = sorted(self.buch.laeufe.values(), key=lambda x: x["id"])
        n = self.naechster()
        return {"automatisch": self.config.sync_intervall_minuten > 0,
                "intervall_minuten": self.config.sync_intervall_minuten,
                "laeuft": any(x["status"] == "laeuft" for x in ls), "jetzt": zs(self.jetzt()),
                "naechster_lauf": zs(n) if n else None, "letzter_lauf": ls[-1] if ls else None,
                "offene_tan_anforderung": self.offene_tan(), "pin_vorhanden": self.pin_lesen() is not None,
                "pin_quelle": self.config.bank_pin_quelle}


def zeit(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s[:-1]).replace(tzinfo=UTC)


# ================================================================ App


@contextlib.asynccontextmanager
async def planer_lebenszyklus(app: FastAPI):
    dienst: Dienst = app.state.dienst
    halt = threading.Event()
    faden = None
    if (dienst.config.sync_intervall_minuten > 0 or dienst.config.mail_intervall_minuten > 0) \
            and dienst.config.planer_starten:
        def schleife():
            while not halt.wait(0.5):
                try:
                    dienst.takt()
                except Exception:  # noqa: BLE001
                    pass
        faden = threading.Thread(target=schleife, daemon=True)
        faden.start()
    yield
    import time as _zeit
    halt.set()
    dienst.frist_ende = _zeit.monotonic() + dienst.config.beenden_frist_sekunden
    dienst.beenden.set()
    if faden:
        faden.join(timeout=dienst.config.beenden_frist_sekunden)
        for lauf in list(dienst.buch.laeufe.values()):
            if lauf["status"] == "laeuft":
                dienst.abbrechen_beim_beenden(lauf)


def m2_einbinden(app: FastAPI, config, buch) -> None:
    dienst = Dienst(config, buch)
    app.state.dienst = dienst

    def buchung(bid):
        return buch._buchung(bid)

    # ------------------------------------------------------- Vorschläge
    def entscheide(b: dict, aktion: str) -> None:
        if aktion == "ablehnen" and not mutant("ablehnen_ohne_ruecksetzen"):
            ziel = b["vorschlag"]["vorher_konto_id"]
            if ziel not in buch.konten:
                ziel = unkategorisiert(buch)
            b["splits"][buch.gegensplits(b)[0]]["konto_id"] = ziel
        b["vorschlag"] = None

    @app.post("/api/buchungen/mehrfach/vorschlag")
    def mehrfach_vorschlag(d: MehrfachVorschlag):
        unbekannt = sorted(i for i in d.buchung_ids if i not in buch.buchungen)
        if unbekannt:
            raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        ohne = sorted(i for i in d.buchung_ids if not buch.buchungen[i].get("vorschlag"))
        if ohne:
            raise Fehler(409, "kein_vorschlag", "Kein offener Vorschlag", {"buchung_ids": ohne})
        gesperrt = sorted(i for i in d.buchung_ids if buch.gesperrt(buch.buchungen[i]))
        if d.aktion == "ablehnen" and gesperrt:
            raise Fehler(409, "buchung_gesperrt", "Buchung gesperrt", {"buchung_ids": gesperrt})
        for i in d.buchung_ids:
            entscheide(buch.buchungen[i], d.aktion)
        return {"geaendert": sorted(d.buchung_ids), "anzahl": len(d.buchung_ids)}

    @app.post("/api/buchungen/{buchung_id}/vorschlag")
    def vorschlag(buchung_id: int, d: VorschlagAktion):
        b = buchung(buchung_id)
        if not b.get("vorschlag"):
            raise Fehler(409, "kein_vorschlag", "Kein offener Vorschlag")
        if d.aktion == "ablehnen" and buch.gesperrt(b):
            raise Fehler(409, "buchung_gesperrt", "Buchung gesperrt")
        entscheide(b, d.aktion)
        return buch.buchung_json(b)

    # ------------------------------------------------------------ Regeln
    @app.get("/api/regeln")
    def regeln():
        return sorted(buch.regeln.values(), key=lambda r: (r["prioritaet"], r["id"]))

    @app.post("/api/regeln", status_code=201)
    def regel_anlegen(d: RegelNeu):
        name = d.name.strip()
        if not name:
            raise _v(["body", "name"], "Name leer")
        bed = pruefe_bedingungen(buch, d.bedingungen)
        pruefe_kategorie(buch, d.kategorie_id)
        prio = d.prioritaet if d.prioritaet is not None else (
            max(r["prioritaet"] for r in buch.regeln.values()) + 10 if buch.regeln else 100)
        rid = buch.neue_id("regel")
        buch.regeln[rid] = {"id": rid, "name": name, "aktiv": d.aktiv, "prioritaet": prio,
                            "kategorie_id": d.kategorie_id, "bedingungen": bed}
        return buch.regeln[rid]

    def _regel(rid):
        if rid not in buch.regeln:
            raise Fehler(404, "nicht_gefunden", "Regel nicht gefunden")
        return buch.regeln[rid]

    @app.post("/api/regeln/anwenden")
    def anwenden(d: RegelnAnwenden):
        if d.buchung_ids is not None:
            unbekannt = sorted(i for i in d.buchung_ids if i not in buch.buchungen)
            if unbekannt:
                raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        if d.regel_ids is not None:
            unbekannt = sorted(i for i in d.regel_ids if i not in buch.regeln)
            if unbekannt:
                raise Fehler(422, "referenz_unbekannt", "Regeln unbekannt", {"regel_ids": unbekannt})
        rs = geordnet(buch, set(d.regel_ids) if d.regel_ids is not None else None)
        ids = d.buchung_ids if d.buchung_ids is not None else list(buch.buchungen)
        geprueft, aenderungen = 0, []
        for bid in sorted(ids):
            b = buch.buchungen[bid]
            if len(buch.gegensplits(b)) != 1 or buch.gesperrt(b):
                continue
            if d.nur_unkategorisiert and buch.kategorie_id(b) is not None:
                continue
            geprueft += 1
            r = regel_fuer(rs, *sicht(buch, b))
            if r is None or b["splits"][buch.gegensplits(b)[0]]["konto_id"] == r["kategorie_id"]:
                continue
            aenderungen.append((b, r))
        if not d.trocken:
            for b, r in aenderungen:
                setze_vorschlag(buch, b, r)
        liste = [{"buchung_id": b["id"], "regel_id": r["id"], "kategorie_id": r["kategorie_id"]} for b, r in aenderungen]
        return {"geprueft": geprueft, "anzahl": len(liste), "trocken": d.trocken, "aenderungen": liste}

    @app.get("/api/regeln/{regel_id}")
    def regel_lesen(regel_id: int):
        return _regel(regel_id)

    @app.patch("/api/regeln/{regel_id}")
    def regel_aendern(regel_id: int, d: RegelAenderung):
        r = _regel(regel_id)
        neu = dict(r)
        felder = d.model_fields_set
        for f in felder:
            if getattr(d, f) is None:
                raise _v(["body", f], "null nicht erlaubt")
        if "name" in felder:
            neu["name"] = d.name.strip()
            if not neu["name"]:
                raise _v(["body", "name"], "Name leer")
        if "bedingungen" in felder:
            neu["bedingungen"] = pruefe_bedingungen(buch, d.bedingungen)
        if "kategorie_id" in felder:
            pruefe_kategorie(buch, d.kategorie_id)
            neu["kategorie_id"] = d.kategorie_id
        for f in ("aktiv", "prioritaet"):
            if f in felder:
                neu[f] = getattr(d, f)
        r.update(neu)
        return r

    @app.delete("/api/regeln/{regel_id}", status_code=204)
    def regel_loeschen(regel_id: int):
        _regel(regel_id)
        del buch.regeln[regel_id]
        for b in buch.buchungen.values():
            if b.get("vorschlag") and b["vorschlag"]["regel_id"] == regel_id:
                b["vorschlag"]["regel_id"] = None
        return Response(status_code=204)

    # -------------------------------------------------------------- Sync
    @app.post("/api/sync")
    def sync(d: SyncAnfrage | None = Body(None)):
        d = d or SyncAnfrage()
        with dienst.sperre:
            return dienst.starte("manuell", d.von, d.bis)

    @app.get("/api/sync/status")
    def sync_status():
        return dienst.status()

    @app.get("/api/sync/laeufe")
    def sync_laeufe():
        dienst.pruefe_ablauf()
        return sorted(buch.laeufe.values(), key=lambda x: x["id"])

    @app.get("/api/sync/laeufe/{lauf_id}")
    def sync_lauf(lauf_id: int):
        dienst.pruefe_ablauf()
        if lauf_id not in buch.laeufe:
            raise Fehler(404, "nicht_gefunden", "Lauf nicht gefunden")
        return buch.laeufe[lauf_id]

    @app.get("/api/sync/konten")
    def sync_konten():
        return [zustand_json(buch, buch.sync_konten[i]) for i in sorted(buch.sync_konten)]

    @app.post("/api/sync/konten/{iban}/entscheidung")
    def sync_konto_entscheidung(iban: str, d: SyncKontoEntscheidung):
        i = iban.replace(" ", "").upper()
        if i not in buch.sync_konten:
            raise Fehler(404, "nicht_gefunden", "Kein Bankkonto mit dieser IBAN")
        z = buch.sync_konten[i]
        if zustand_status(buch, z) == "aktiv":
            raise Fehler(409, "konto_vorhanden", "Es existiert ein Konto mit dieser IBAN")
        z["_entscheidung"] = (d.aktion, d.buchungen if d.aktion == "wiederherstellen" else None)
        for x in buch.benachr.values():
            if x["schluessel"] == f"konto_fehlt:{i}":
                x["gelesen"] = True
        return zustand_json(buch, z)

    @app.put("/api/sync/pin", status_code=204)
    def pin_setzen(d: PinEingabe):
        if config.bank_pin_quelle == "systemd-creds":
            raise Fehler(409, "pin_quelle_systemd", "Die PIN kommt aus systemd-creds")
        dienst.pin = d.pin
        return Response(status_code=204)

    @app.delete("/api/sync/pin", status_code=204)
    def pin_weg():
        if config.bank_pin_quelle == "systemd-creds":
            raise Fehler(409, "pin_quelle_systemd", "Die PIN kommt aus systemd-creds")
        dienst.pin = None
        return Response(status_code=204)

    # --------------------------------------------------------------- TAN
    @app.get("/api/tan-anforderungen")
    def tan_liste():
        dienst.pruefe_ablauf()
        return sorted(buch.tan.values(), key=lambda t: t["id"])

    @app.get("/api/tan-anforderungen/{tan_id}")
    def tan_lesen(tan_id: int):
        dienst.pruefe_ablauf()
        return dienst._tan(tan_id)

    @app.get("/api/tan-anforderungen/{tan_id}/bild")
    def tan_bild(tan_id: int):
        dienst.pruefe_ablauf()
        t = dienst._tan(tan_id)
        i = dienst.intern.get(tan_id)
        if t["status"] != "offen" or not i or not i["bild"]:
            raise Fehler(404, "nicht_gefunden", "Kein Bild")
        return Response(content=i["bild"], media_type=i["mime"])

    @app.post("/api/tan-anforderungen/{tan_id}/antwort")
    def tan_antwort(tan_id: int, d: TanEingabe):
        with dienst.sperre:
            return dienst.antworten(tan_id, d.tan)

    @app.post("/api/tan-anforderungen/{tan_id}/abbrechen")
    def tan_abbrechen(tan_id: int):
        return dienst.abbrechen(tan_id)

    # ----------------------------------------------- Benachrichtigungen
    @app.get("/api/benachrichtigungen")
    def benachrichtigungen(gelesen: bool | None = None):
        return [x for x in sorted(buch.benachr.values(), key=lambda x: x["id"])
                if gelesen is None or x["gelesen"] == gelesen]

    @app.post("/api/benachrichtigungen/{benachrichtigung_id}/gelesen")
    def gelesen(benachrichtigung_id: int):
        if benachrichtigung_id not in buch.benachr:
            raise Fehler(404, "nicht_gefunden", "Benachrichtigung nicht gefunden")
        buch.benachr[benachrichtigung_id]["gelesen"] = True
        return buch.benachr[benachrichtigung_id]

    # --------------------------------------------------------- Mock-Uhr
    def _mock():
        if not config.mock_modus:
            raise Fehler(409, "nur_mock_modus", "Nur im Mock-Modus verfügbar")
        j = dienst.jetzt()
        return {"jetzt": zs(j), "heute": j.date().isoformat(),
                "simuliert": dienst.zeit is not None or config.mock_heute is not None}

    @app.get("/api/mock/zeit")
    def mock_zeit():
        return _mock()

    @app.put("/api/mock/zeit")
    def mock_zeit_setzen(d: ZeitEingabe):
        _mock()
        dienst.zeit = dt.datetime.fromisoformat(d.jetzt[:-1]).replace(tzinfo=UTC, microsecond=0)
        return _mock()


__all__ = ["m2_einbinden", "planer_lebenszyklus", "ekey"]
