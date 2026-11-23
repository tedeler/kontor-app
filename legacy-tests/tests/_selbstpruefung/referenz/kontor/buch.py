"""Buchhaltungskern der Wegwerf-Referenz (im Arbeitsspeicher, je Datenbankpfad ein Buch).

KEIN Anwendungscode. Mutanten werden über ``kontor.mutant(name)`` eingeschaltet.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from . import mutant

MAX = 999_999_999_999
KLASSE = {"girokonto": "bestand", "sparkonto": "bestand", "kreditkonto": "bestand",
          "aufwand": "aufwand", "ertrag": "ertrag", "eigenkapital": "eigenkapital"}
UEBERGAENGE = {("importiert", "bestaetigt"), ("bestaetigt", "abgeglichen"), ("vorlaeufig", "abgeglichen")}
IBAN_MUSTER = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


class Fehler(Exception):
    def __init__(self, status: int, code: str, meldung: str, details: object = None) -> None:
        super().__init__(meldung)
        self.status, self.code, self.meldung, self.details = status, code, meldung, details


def namen_pruefen(konten: dict) -> None:
    """M32 (sammel3.md 1): Kontonamen je Ebene (oberste Ebene je Klasse) ohne Groß/Klein und Rand eindeutig."""
    if mutant("m32_kontonamen_doppelt"):
        return
    gesehen: dict[tuple, int] = {}
    for k in sorted(konten.values(), key=lambda x: x["id"]):
        ebene = k["eltern_id"] if k["eltern_id"] is not None else "oben:" + KLASSE[k["art"]]
        s = (ebene, k["name"].strip().casefold())
        if s in gesehen:
            raise Fehler(409, "konto_existiert", "Ein Konto dieses Namens gibt es auf dieser Ebene schon",
                         {"konto_ids": [gesehen[s], k["id"]]})
        gesehen[s] = k["id"]


def bereinigen(buch) -> list[tuple[str, str]]:
    """M32 (sammel3.md 1.3): gleichnamige Kategorien in die kleinste ID zusammenführen, andere Konten mit „ (n)“
    umbenennen; liefert (Warnungscode, Name). Klein gehalten: Kreditbezug wird nicht betrachtet."""
    aus: list[tuple[str, str]] = []
    if mutant("m32_kontonamen_doppelt"):
        return aus
    while True:
        try:
            namen_pruefen(buch.konten)
            return aus
        except Fehler as f:
            a, b = f.details["konto_ids"]
        kb = buch.konten[b]
        if KLASSE[kb["art"]] in ("aufwand", "ertrag"):
            def ersetze(x):
                if isinstance(x, dict):
                    for k, v in x.items():
                        if k in ("konto_id", "kategorie_id", "vorher_konto_id", "eltern_id") and v == b:
                            x[k] = a
                        else:
                            ersetze(v)
                elif isinstance(x, list):
                    for v in x:
                        ersetze(v)
            for sammlung in (buch.buchungen, buch.regeln, buch.vorlagen, buch.konten):
                ersetze(sammlung)
            del buch.konten[b]
            aus.append(("konto_zusammengefasst", kb["name"]))
        else:
            n = 2
            ebene = [(k["eltern_id"], KLASSE[k["art"]], k["name"].strip().casefold()) for k in buch.konten.values()]
            while (kb["eltern_id"], KLASSE[kb["art"]], f"{kb['name']} ({n})".strip().casefold()) in ebene:
                n += 1
            aus.append(("konto_umbenannt", kb["name"]))
            kb["name"] = f"{kb['name']} ({n})"


def norm(s: str) -> str:
    s = s.casefold()
    if mutant("filter_ohne_umlaute"):
        return s
    return s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


def ekey(s: str | None) -> str | None:
    return None if s is None else re.sub(r"[^a-z0-9]", "", norm(s))


def passend(a: str | None, b: str | None) -> bool:
    if mutant("dublette_empfaenger_exakt"):
        return a == b
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return bool(ekey(a)) and ekey(a) == ekey(b)


def iban_gueltig(iban: str) -> bool:
    if not IBAN_MUSTER.match(iban):
        return False
    zahl = "".join(str(int(z, 36)) for z in iban[4:] + iban[:4])
    return int(zahl) % 97 == 1


class Buch:
    def __init__(self) -> None:
        self.konten: dict[int, dict] = {}
        self.empfaenger: dict[int, dict] = {}
        self.tags: dict[int, dict] = {}
        self.buchungen: dict[int, dict] = {}
        self.verdachte: dict[int, dict] = {}
        self.importe: list[dict] = []
        self.zaehler: dict[str, int] = {}
        # Meilenstein 2
        self.regeln: dict[int, dict] = {}
        self.gemerkt: set[str] = set()
        self.laeufe: dict[int, dict] = {}
        self.tan: dict[int, dict] = {}
        self.benachr: dict[int, dict] = {}
        self.sync_konten: dict[str, dict] = {}
        # Meilenstein 3
        self.aenderungen: dict[int, dict] = {}
        self.abstimmungen: dict[int, dict] = {}
        # Meilenstein 4
        self.vorlagen: dict[int, dict] = {}
        # Meilenstein 5
        self.kredite: dict[int, dict] = {}
        # Meilenstein 6 (Postfächer: Buchbestand; Spiegel/Betrieb/Geheimnisse: Betriebszustand)
        self.postfaecher: dict[int, dict] = {}
        self.mail_betrieb: dict[str, dict] = {}
        self.mail_spiegel: dict[str, dict[str, dict]] = {}
        self.geheimnisse: dict[str, dict] = {}

    def neue_id(self, art: str) -> int:
        self.zaehler[art] = self.zaehler.get(art, 0) + 1
        return self.zaehler[art]

    def kopie(self) -> "Buch":
        return copy.deepcopy(self)

    def uebernehme(self, anderes: "Buch") -> None:
        self.__dict__.update(anderes.__dict__)

    # ------------------------------------------------------------- Konten
    def konto_json(self, k: dict) -> dict:
        return {**{f: k[f] for f in ("id", "name", "art", "eltern_id", "iban", "geschlossen", "eroeffnet_am",
                                       "notiz", "extern_id")},
                "waehrung": "EUR", "ist_kategorie": k["art"] in ("aufwand", "ertrag")}

    def _pruefe_eltern(self, k_id: int | None, art: str, eltern_id: int | None) -> None:
        if eltern_id is None:
            return
        if eltern_id not in self.konten:
            raise Fehler(422, "referenz_unbekannt", "Elternkonto unbekannt")
        if KLASSE[self.konten[eltern_id]["art"]] != KLASSE[art]:
            raise Fehler(422, "hierarchie_ungueltig", "Elternkonto anderer Klasse")
        e = eltern_id
        while e is not None:
            if e == k_id:
                raise Fehler(422, "hierarchie_ungueltig", "Zyklus")
            e = self.konten[e]["eltern_id"]

    def _pruefe_iban(self, k_id: int | None, art: str, iban: str | None) -> str | None:
        if iban is None:
            return None
        if KLASSE[art] != "bestand":
            raise Fehler(422, "validierung", "IBAN nur bei Bestandskonten", [{"ort": ["body", "iban"],
                                                                             "meldung": "nicht erlaubt"}])
        n = iban.replace(" ", "").upper()
        if not iban_gueltig(n):
            raise Fehler(422, "iban_ungueltig", "IBAN ungültig")
        if any(k["iban"] == n and k["id"] != k_id for k in self.konten.values()):
            raise Fehler(409, "iban_existiert", "IBAN bereits vergeben")
        return n

    @staticmethod
    def _name(name: str) -> str:
        n = name.strip()
        if not n:
            raise Fehler(422, "validierung", "Name leer", [{"ort": ["body", "name"], "meldung": "leer"}])
        return n

    def freier_name(self, name: str, art: str, eltern_id: int | None = None) -> str:
        """M32 (sammel3.md 1.4): erster freie Name „name“, „name (2)“, … auf der Ebene."""
        belegt = {k["name"].strip().casefold() for k in self.konten.values() if k["eltern_id"] == eltern_id
                  and (eltern_id is not None or KLASSE[k["art"]] == KLASSE[art])}
        kandidat, n = name, 1
        while kandidat.strip().casefold() in belegt and not mutant("m32_kontonamen_doppelt"):
            n += 1
            kandidat = f"{name} ({n})"
        return kandidat

    def konto_anlegen(self, d: dict, extern_id: str | None = None) -> dict:
        name = self._name(d["name"])
        self._pruefe_eltern(None, d["art"], d.get("eltern_id"))
        iban = self._pruefe_iban(None, d["art"], d.get("iban"))
        k = {"id": self.neue_id("konto"), "name": name, "art": d["art"], "eltern_id": d.get("eltern_id"),
             "iban": iban, "geschlossen": d.get("geschlossen", False), "eroeffnet_am": d.get("eroeffnet_am"),
             "notiz": d.get("notiz", ""), "extern_id": extern_id}
        namen_pruefen({**self.konten, k["id"]: k})
        self.konten[k["id"]] = k
        return k

    def konto_aendern(self, kid: int, d: dict) -> dict:
        k = self._konto(kid)
        neu = dict(k)
        if "name" in d:
            neu["name"] = self._name(d["name"])
        if "eltern_id" in d:
            self._pruefe_eltern(kid, k["art"], d["eltern_id"])
            neu["eltern_id"] = d["eltern_id"]
        if "iban" in d:
            neu["iban"] = self._pruefe_iban(kid, k["art"], d["iban"])
        for f in ("geschlossen", "eroeffnet_am", "notiz"):
            if f in d:
                neu[f] = d[f]
        namen_pruefen({**self.konten, kid: neu})
        k.update(neu)
        return k

    def konto_loeschen(self, kid: int) -> None:
        self._konto(kid)
        from .m5 import kreditbezug
        kreditbezug(self, kid)
        regelbezug = any(r["kategorie_id"] == kid or any(b["feld"] == "konto_id" and b["wert"] == kid
                                                         for b in r["bedingungen"]) for r in self.regeln.values())
        m3bezug = any(e.get("standardkategorie_id") == kid for e in self.empfaenger.values()) or \
            any(a["konto_id"] == kid for a in self.abstimmungen.values()) or \
            any(t["kategorie_id"] == kid for v in self.vorlagen.values() for t in v["teile"]) or \
            any(c["feld"] == "konto_id" and c["wert"] == kid for v in self.vorlagen.values() for c in v["bedingungen"])
        if any(s["konto_id"] == kid for b in self.buchungen.values() for s in b["splits"]) or \
                any(k["eltern_id"] == kid for k in self.konten.values()) or regelbezug or m3bezug:
            raise Fehler(409, "konto_in_verwendung", "Konto in Verwendung")
        del self.konten[kid]

    def _konto(self, kid: int) -> dict:
        if kid not in self.konten:
            raise Fehler(404, "nicht_gefunden", "Konto nicht gefunden")
        return self.konten[kid]

    def uebersicht(self, stichtag: str | None) -> dict:
        saldo = {kid: 0 for kid in self.konten}
        anzahl = {kid: 0 for kid in self.konten}
        for b in self.buchungen.values():
            if stichtag is not None:
                if mutant("saldo_stichtag_exklusiv"):
                    if b["datum"] >= stichtag:
                        continue
                elif b["datum"] > stichtag:
                    continue
            for s in b["splits"]:
                saldo[s["konto_id"]] += s["betrag"]
            for kid in {s["konto_id"] for s in b["splits"]}:
                anzahl[kid] += 1
        kinder: dict[int, list[int]] = {}
        for k in self.konten.values():
            if k["eltern_id"] is not None:
                kinder.setdefault(k["eltern_id"], []).append(k["id"])

        def gesamt(kid: int) -> int:
            if mutant("saldo_gesamt_nur_kinder"):
                return saldo[kid] + sum(saldo[c] for c in kinder.get(kid, []))
            return saldo[kid] + sum(gesamt(c) for c in kinder.get(kid, []))

        konten = [{"konto_id": k["id"], "name": k["name"], "art": k["art"], "eltern_id": k["eltern_id"],
                   "geschlossen": k["geschlossen"], "saldo": saldo[k["id"]], "saldo_gesamt": gesamt(k["id"]),
                   "anzahl_buchungen": anzahl[k["id"]]} for k in sorted(self.konten.values(), key=lambda k: k["id"])]
        return {"stichtag": stichtag, "konten": konten,
                "summe_bestand": sum(saldo[k] for k in saldo if KLASSE[self.konten[k]["art"]] == "bestand"),
                "summe_gesamt": sum(saldo.values())}

    # --------------------------------------------------- Empfänger, Tags
    def empfaenger_anlegen(self, name: str, extern_id: str | None = None, *, rest: bool = True) -> dict:
        n = self._name(name) if rest else name
        if any(e["name"] == n for e in self.empfaenger.values()):
            raise Fehler(409, "empfaenger_existiert", "Empfänger existiert")
        e = {"id": self.neue_id("empfaenger"), "name": n, "extern_id": extern_id, "aliase": [],
             "standardkategorie_id": None}
        self.empfaenger[e["id"]] = e
        return e

    def tag_json(self, t: dict) -> dict:
        return {**t, "anzahl_buchungen": sum(1 for b in self.buchungen.values() if t["id"] in b["tag_ids"])}

    def tag_anlegen(self, name: str, extern_id: str | None = None, *, rest: bool = True) -> dict:
        n = self._name(name) if rest else name
        if any(t["name"].casefold() == n.casefold() for t in self.tags.values()):
            raise Fehler(409, "tag_existiert", "Tag existiert")
        t = {"id": self.neue_id("tag"), "name": n, "extern_id": extern_id}
        self.tags[t["id"]] = t
        return t

    def tag_umbenennen(self, tid: int, name: str) -> dict:
        t = self._tag(tid)
        n = self._name(name)
        if any(x["name"].casefold() == n.casefold() and x["id"] != tid for x in self.tags.values()):
            raise Fehler(409, "tag_existiert", "Tag existiert")
        t["name"] = n
        return t

    def tag_loeschen(self, tid: int) -> None:
        self._tag(tid)
        del self.tags[tid]
        for b in self.buchungen.values():
            b["tag_ids"].discard(tid)

    def _tag(self, tid: int) -> dict:
        if tid not in self.tags:
            raise Fehler(404, "nicht_gefunden", "Tag nicht gefunden")
        return self.tags[tid]

    # --------------------------------------------------------- Buchungen
    def _splits(self, splits: list[dict]) -> list[dict]:
        if len(splits) < (1 if mutant("ein_split_erlaubt") else 2):
            raise Fehler(422, "zu_wenige_splits", "Mindestens zwei Splits")
        if sum(s["betrag"] for s in splits) != 0 and not mutant("split_summe_ungeprueft"):
            raise Fehler(422, "buchung_unausgeglichen", "Summe der Splits ist nicht 0")
        for s in splits:
            if s["konto_id"] not in self.konten:
                raise Fehler(422, "referenz_unbekannt", "Konto unbekannt")
        return [{"id": self.neue_id("split"), "konto_id": s["konto_id"], "betrag": int(s["betrag"]),
                 "memo": s.get("memo", ""), "abstimmung_id": None} for s in splits]

    def _referenzen(self, d: dict) -> None:
        if d.get("empfaenger_id") is not None and d["empfaenger_id"] not in self.empfaenger:
            raise Fehler(422, "referenz_unbekannt", "Empfänger unbekannt")
        if any(t not in self.tags for t in d.get("tag_ids", [])):
            raise Fehler(422, "referenz_unbekannt", "Tag unbekannt")

    def buchung_anlegen(self, d: dict, extern_ids: list[str] | None = None) -> dict:
        self._referenzen(d)
        splits = self._splits(d["splits"])
        b = {"id": self.neue_id("buchung"), "datum": d["datum"], "empfaenger_id": d.get("empfaenger_id"),
             "verwendungszweck": d.get("verwendungszweck", ""), "status": d.get("status", "bestaetigt"),
             "splits": splits, "tag_ids": set(d.get("tag_ids", [])), "extern_ids": list(extern_ids or []),
             "vorschlag": None, "gegen_iban": d.get("gegen_iban")}
        self.buchungen[b["id"]] = b
        return b

    def buchung_anlegen_roh(self, d: dict) -> dict:
        """Import: Splits sind bereits geprüft bzw. ausgeglichen."""
        b = {"id": self.neue_id("buchung"), "datum": d["datum"], "empfaenger_id": d["empfaenger_id"],
             "verwendungszweck": d["verwendungszweck"], "status": "importiert",
             "splits": [{"id": self.neue_id("split"), **s, "abstimmung_id": None} for s in d["splits"]],
             "tag_ids": set(d["tag_ids"]), "extern_ids": ["kmy:" + d["tid"]], "vorschlag": None, "gegen_iban": None}
        self.buchungen[b["id"]] = b
        return b

    def _buchung(self, bid: int) -> dict:
        if bid not in self.buchungen:
            raise Fehler(404, "nicht_gefunden", "Buchung nicht gefunden")
        return self.buchungen[bid]

    def gegensplits(self, b: dict) -> list[int]:
        return [i for i, s in enumerate(b["splits"]) if KLASSE[self.konten[s["konto_id"]]["art"]] != "bestand"]

    def kategorie_id(self, b: dict) -> int | None:
        g = self.gegensplits(b)
        if len(g) == 1 and self.konten[b["splits"][g[0]]["konto_id"]]["art"] in ("aufwand", "ertrag"):
            return b["splits"][g[0]]["konto_id"]
        return None

    def umsatz(self, b: dict) -> int:
        if mutant("betrag_umsatz_abs"):
            return abs(b["splits"][0]["betrag"])
        return sum(s["betrag"] for s in b["splits"] if s["betrag"] > 0)

    def buchung_json(self, b: dict, konto_id: int | None = None) -> dict:
        betrag = (sum(s["betrag"] for s in b["splits"] if s["konto_id"] == konto_id) if konto_id is not None
                  else self.umsatz(b))
        e = self.empfaenger.get(b["empfaenger_id"]) if b["empfaenger_id"] is not None else None
        return {"id": b["id"], "datum": b["datum"], "empfaenger": {"id": e["id"], "name": e["name"]} if e else None,
                "verwendungszweck": b["verwendungszweck"], "status": b["status"],
                "splits": [dict(s) for s in b["splits"]],
                "tags": [{"id": t, "name": self.tags[t]["name"]} for t in sorted(b["tag_ids"])],
                "kategorie_id": self.kategorie_id(b), "betrag": betrag, "extern_ids": sorted(b["extern_ids"]),
                "belege": [], "vorschlag": dict(b["vorschlag"]) if b.get("vorschlag") else None,
                "gegen_iban": b.get("gegen_iban"), "ist_umbuchung": self.ist_umbuchung(b),
                "abgestimmt": self.abgestimmt(b)}

    def ist_umbuchung(self, b: dict) -> bool:
        return all(KLASSE[self.konten[s["konto_id"]]["art"]] == "bestand" for s in b["splits"]) and \
            len({s["konto_id"] for s in b["splits"]}) >= 2

    @staticmethod
    def abgestimmt(b: dict) -> bool:
        return any(s.get("abstimmung_id") is not None for s in b["splits"])

    def gesperrt(self, b: dict) -> bool:
        if mutant("abstimmung_ohne_sperre"):
            return b["status"] == "abgeglichen"
        return b["status"] == "abgeglichen" or self.abgestimmt(b)

    def buchung_aendern(self, bid: int, d: dict) -> dict:
        b = self._buchung(bid)
        self._referenzen(d)
        if self.gesperrt(b) and set(d) - {"tag_ids", "status"}:
            raise Fehler(409, "buchung_gesperrt", "Buchung ist abgeglichen")
        if "status" in d and d["status"] != b["status"] and (b["status"], d["status"]) not in UEBERGAENGE:
            raise Fehler(409, "status_uebergang_unzulaessig", "Statusübergang unzulässig")
        if "status" in d and d["status"] != b["status"] and d["status"] in ("bestaetigt", "abgeglichen"):
            b["vorschlag"] = None
        for f in ("datum", "empfaenger_id", "verwendungszweck", "status"):
            if f in d:
                b[f] = d[f]
        if "tag_ids" in d:
            b["tag_ids"] = set(d["tag_ids"])
        return b

    def _nicht_gesperrt(self, b: dict) -> None:
        if self.gesperrt(b):
            raise Fehler(409, "buchung_gesperrt", "Buchung ist abgeglichen")

    def splits_ersetzen(self, bid: int, splits: list[dict]) -> dict:
        b = self._buchung(bid)
        self._nicht_gesperrt(b)
        b["splits"] = self._splits(splits)
        b["vorschlag"] = None
        return b

    def buchung_loeschen(self, bid: int) -> None:
        b = self._buchung(bid)
        self._nicht_gesperrt(b)
        del self.buchungen[bid]
        for vid in [v["id"] for v in self.verdachte.values() if v["status"] == "offen"
                    and (v["buchung_id"] == bid or bid in v["kandidat_ids"])]:
            del self.verdachte[vid]

    def _kategorie_gueltig(self, kid: int) -> None:
        if kid not in self.konten or self.konten[kid]["art"] not in ("aufwand", "ertrag"):
            raise Fehler(422, "kategorie_ungueltig", "Keine Kategorie")

    def _setze_kategorie(self, b: dict, kid: int) -> None:
        g = self.gegensplits(b)
        if mutant("kategorie_memo_verloren"):
            b["splits"][g[0]]["memo"] = ""
        b["splits"][g[0]]["konto_id"] = kid
        b["vorschlag"] = None

    def kategorie_setzen(self, bid: int, kid: int) -> dict:
        b = self._buchung(bid)
        self._nicht_gesperrt(b)
        self._kategorie_gueltig(kid)
        if len(self.gegensplits(b)) != 1:
            raise Fehler(422, "nicht_kategorisierbar", "Buchung nicht kategorisierbar")
        self._setze_kategorie(b, kid)
        return b

    def mehrfach_kategorie(self, ids: list[int], kid: int) -> dict:
        unbekannt = sorted(i for i in ids if i not in self.buchungen)
        if unbekannt:
            raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        self._kategorie_gueltig(kid)
        if mutant("mehrfach_nicht_atomar"):
            for i in ids:
                b = self.buchungen[i]
                if not self.gesperrt(b) and len(self.gegensplits(b)) == 1:
                    self._setze_kategorie(b, kid)
        gesperrt = sorted(i for i in ids if self.gesperrt(self.buchungen[i]))
        if gesperrt:
            raise Fehler(409, "buchung_gesperrt", "Buchungen abgeglichen", {"buchung_ids": gesperrt})
        nicht = sorted(i for i in ids if len(self.gegensplits(self.buchungen[i])) != 1)
        if nicht:
            raise Fehler(422, "nicht_kategorisierbar", "Nicht kategorisierbar", {"buchung_ids": nicht})
        for i in ids:
            self._setze_kategorie(self.buchungen[i], kid)
        return {"geaendert": sorted(ids), "anzahl": len(ids)}

    def mehrfach_tags(self, ids: list[int], hinzu: list[int], weg: list[int]) -> dict:
        unbekannt = sorted(i for i in ids if i not in self.buchungen)
        if unbekannt:
            raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        if any(t not in self.tags for t in hinzu + weg):
            raise Fehler(422, "referenz_unbekannt", "Tag unbekannt")
        for i in ids:
            self.buchungen[i]["tag_ids"] = (self.buchungen[i]["tag_ids"] - set(weg)) | set(hinzu)
        return {"geaendert": sorted(ids), "anzahl": len(ids)}

    def mehrfach_aendern(self, ids: list[int], felder: dict, entsperren: bool) -> dict:
        """M12, datenmodell.md 17.2: freie Statusänderung und Massenänderung (atomar)."""
        unbekannt = sorted(i for i in ids if i not in self.buchungen)
        if unbekannt:
            raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        self._referenzen(felder)
        bs = [self.buchungen[i] for i in ids]
        if mutant("m12_nicht_atomar"):
            for b in bs:
                if not self.gesperrt(b):
                    b.update({f: v for f, v in felder.items()})
        if not mutant("m12_sperre_ignoriert"):
            gesperrt = sorted(b["id"] for b in bs if self.gesperrt(b) and any(
                b[f] != v for f, v in felder.items() if f != "status"))
            if mutant("m12_abgestimmt_status_gesperrt") and "status" in felder:
                gesperrt = sorted(set(gesperrt) | {b["id"] for b in bs if self.abgestimmt(b)
                                                   and b["status"] != felder["status"]})
            if gesperrt:
                raise Fehler(409, "buchung_gesperrt", "Buchungen gesperrt", {"buchung_ids": gesperrt})
        if "status" in felder:
            neu = felder["status"]
            if mutant("m12_alte_uebergaenge"):
                if any(b["status"] != neu and (b["status"], neu) not in UEBERGAENGE for b in bs):
                    raise Fehler(409, "status_uebergang_unzulaessig", "Statusübergang unzulässig")
            if not entsperren and not mutant("m12_entsperren_ignoriert"):
                offen = sorted(b["id"] for b in bs if b["status"] == "abgeglichen" and neu != "abgeglichen")
                if offen:
                    raise Fehler(409, "bestaetigung_erforderlich", "Abgeglichene Buchungen: Bestätigung nötig",
                                 {"buchung_ids": offen})
        for b in bs:
            if "status" in felder and felder["status"] != b["status"] and felder["status"] in (
                    "bestaetigt", "abgeglichen") and not mutant("m12_vorschlag_bleibt"):
                b["vorschlag"] = None
            for f, v in felder.items():
                b[f] = v
        return {"geaendert": sorted(ids), "anzahl": len(ids)}

    # ------------------------------------------------------------- Liste
    def nachfahren(self, kid: int) -> set[int]:
        aus = {kid}
        if mutant("unterkategorien_ignoriert"):
            return aus
        for k in self.konten.values():
            if k["eltern_id"] == kid:
                aus |= self.nachfahren(k["id"])
        return aus

    def liste(self, p: dict) -> dict:
        konto_id = p.get("konto_id")
        # M11, datenmodell.md 16.1: unterkonten
        menge = ({konto_id} if konto_id is None or not p.get("unterkonten") or mutant("unterkonten_ignoriert")
                 else (self.nachfahren(konto_id) if konto_id in self.konten else {konto_id}))
        treffer = []
        for b in self.buchungen.values():
            j = self.buchung_json(b, konto_id)
            if konto_id is not None and len(menge) > 1 and not mutant("unterkonten_betrag_nur_konto"):
                j["betrag"] = sum(s["betrag"] for s in b["splits"] if s["konto_id"] in menge)
            if konto_id is not None and not any(s["konto_id"] in menge for s in b["splits"]):
                continue
            if p.get("von") and j["datum"] < p["von"]:
                continue
            if p.get("bis"):
                if mutant("filter_bis_exklusiv"):
                    if j["datum"] >= p["bis"]:
                        continue
                elif j["datum"] > p["bis"]:
                    continue
            if p.get("betrag_min") is not None and j["betrag"] < p["betrag_min"]:
                continue
            if p.get("betrag_max") is not None and j["betrag"] > p["betrag_max"]:
                continue
            if p.get("kategorie_id") is not None:
                ziel = self.nachfahren(p["kategorie_id"]) if p.get("unterkategorien") else {p["kategorie_id"]}
                if not any(s["konto_id"] in ziel for s in b["splits"]):
                    continue
            if not set(p.get("tag_id") or []) <= b["tag_ids"]:
                continue
            if p.get("empfaenger_id") is not None and b["empfaenger_id"] != p["empfaenger_id"]:
                continue
            if p.get("ohne_empfaenger") and b["empfaenger_id"] is not None:
                continue
            if p.get("verwendungszweck") and norm(p["verwendungszweck"]) not in norm(j["verwendungszweck"]):
                continue
            if p.get("suche"):
                felder = [j["verwendungszweck"]] + [s["memo"] for s in j["splits"]] + [t["name"] for t in j["tags"]]
                if j["empfaenger"]:
                    felder.append(j["empfaenger"]["name"])
                if not any(norm(p["suche"]) in norm(f) for f in felder):
                    continue
            if p.get("status") and j["status"] not in p["status"]:
                continue
            if p.get("vorschlag") is not None and (j["vorschlag"] is not None) != p["vorschlag"]:
                continue
            if p.get("abgestimmt") is not None and j["abgestimmt"] != p["abgestimmt"]:
                continue
            treffer.append(j)
        sortierung = p.get("sortierung") or "datum"
        ab = sortierung.startswith("-")
        feld = sortierung.lstrip("-")
        treffer.sort(key=lambda j: j["id"], reverse=mutant("sortierung_instabil"))
        if feld == "empfaenger":
            mit = sorted([j for j in treffer if j["empfaenger"]], key=lambda j: norm(j["empfaenger"]["name"]),
                         reverse=ab)
            treffer = mit + [j for j in treffer if not j["empfaenger"]]
        else:
            treffer.sort(key=lambda j: j[feld], reverse=ab)
        seite, pro = p.get("seite", 1), p.get("pro_seite", 50)
        return {"eintraege": treffer[(seite - 1) * pro: seite * pro], "gesamt": len(treffer), "seite": seite,
                "pro_seite": pro, "summe": sum(j["betrag"] for j in treffer)}

    # --------------------------------------------------------- Dubletten
    def verdacht_aufloesen(self, vid: int, entscheidung: str, behalten_id: int | None) -> dict:
        if vid not in self.verdachte:
            raise Fehler(404, "nicht_gefunden", "Verdacht nicht gefunden")
        v = self.verdachte[vid]
        if v["status"] != "offen":
            raise Fehler(409, "konflikt", "Verdacht ist nicht offen")
        if entscheidung == "zusammenfuehren":
            if behalten_id is None or behalten_id not in v["kandidat_ids"]:
                raise Fehler(422, "validierung", "behalten_id ungültig",
                             [{"ort": ["body", "behalten_id"], "meldung": "kein Kandidat"}])
            if self.gesperrt(self.buchungen[v["buchung_id"]]):
                raise Fehler(409, "buchung_gesperrt", "Die zu entfernende Buchung ist gesperrt")
            neu = self.buchungen.pop(v["buchung_id"])
            self.buchungen[behalten_id]["extern_ids"].extend(neu["extern_ids"])
            v["status"] = "zusammengefuehrt"
        else:
            v["status"] = "keine_dublette"
        return v


BUECHER: dict[str, Buch] = {}


def buch_fuer(pfad: Path) -> Buch:
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    if not pfad.exists():
        pfad.write_bytes(b"")
    schl = str(pfad.resolve())
    if schl not in BUECHER:
        BUECHER[schl] = Buch()
    return BUECHER[schl]
