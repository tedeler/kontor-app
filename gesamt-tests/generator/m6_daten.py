"""Testdaten für Meilenstein 6: FinTS-Bank, Postfächer, Benachrichtigungen.

Alles synthetisch, fester Startwert, BLZ ``00000000``, Adressen unter ``example.invalid``,
PIN/TAN/Tokens offensichtlich künstlich. ``erzeuge_m6`` liefert ``({Pfad: JSON-Objekt oder Bytes}, {Pfad:
Beschreibung})``:

- ``m6/fints_bank.json`` (Format ``kontor-fints-attrappe``, Version 1): Daten der FinTS-Attrappe
  (``tests/hilfen/fints_attrappe.py``, ``fints.md`` 6) – Konten mit FinTS-Kontoart, Umsätze
  Dez. 2023 – Juli 2024 je als MT940-Bruchstück (``:61:``/``:86:``, ISO-8859-1-fähig, Zeilen ≤ 65
  Zeichen) und als camt.052.001.08-``Ntry``; synthetische PIN und TAN, Challenge-Text und ein
  QR-artiges PNG (Matrix-Code für HITAN). Störfälle: Storno in beide Richtungen, zwei gleiche Umsätze
  am selben Tag ohne Bankreferenz, langer Verwendungszweck und Name (Aufteilung auf ``?20``… und
  ``?32/?33`` bzw. mehrere ``Ustrd``), Jahreswechsel zwischen Buchungstag und Valuta, fehlende
  Gegenpartei, ungültige Gegen-IBAN, Umsatz ohne Valuta bzw. ohne Buchungstag (camt), Fremdwährung
  (camt), Vormerkungen mit Sichtbarkeitszeitraum (camt), Umlaute und ``&``.
- ``m6/fints_bank.erwartung.json``: bekannte Wahrheit – erwartete ``BankKonto``-Liste und je
  Umsatz das erwartete ``BankUmsatz`` je Profil (``camt``/``mt940``, ``fints.md`` 3.4,
  einschließlich ``umsatz_id`` nach der Hash-Regel), Sichtbarkeit der Vormerkungen.
- ``mock/m6_fints_vergleich.json``: Mock-Datendatei mit denselben Konten und den erwarteten Umsätzen
  des Profils ``camt`` (Vertragstest T 21, ``fints.md`` 7), gleicher PIN und TAN.
- ``m6/mail/*.mbox`` und ``m6/mail/postfaecher.json``: zwei Postfächer mit je zwei Ordnern im
  mbox-Format (INTERNALDATE in der ``From ``-Zeile, UTC); Bestell-, Versand- und Zahlungsmails,
  multipart/alternative, nur HTML (ISO-8859-1, base64, Entitäten), RFC-2047-Betreff mit Faltung,
  Anhänge (auch ein ``text/plain``-Anhang vor dem HTML-Text), ohne ``Message-ID``, doppelte
  ``Message-ID``, unbekannter Zeichensatz, Newsletter für den Absenderfilter.
- ``m6/mail.erwartung.json``: erwartete ``MailNachricht`` je Postfach und Ordner (``mail.md`` 3.3).
- ``mock/m6_mail_vergleich.json``: dieselben Nachrichten der konfigurierten Ordner als Mock-Daten.
- ``m6/benachrichtigungen.erwartung.json``: Prioritäten je Art, erwartete ntfy-Körper für
  Beispiel-Benachrichtigungen und Fälle der TAN-Erinnerungen (``benachrichtigungen.md`` 3–5).
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html as html_modul
import random
import re
import struct
import zlib

from .iban import fiktive_iban, ist_gueltig

D = dt.date
BLZ = "00000000"
GIRO = fiktive_iban(6601)
TAGESGELD = fiktive_iban(6602)
KARTE = fiktive_iban(6603)
DEPOT = fiktive_iban(6604)
NICHT_SEPA = fiktive_iban(6605)
DOLLAR = fiktive_iban(6606)
FREMD = [fiktive_iban(6690 + i) for i in range(6)]
INHABER = "Erika Mustermann"
INHABER2 = "Max Mustermann"
PIN = "SYNTH-PIN-48151"
TAN = "623842"
HEUTE = D(2024, 6, 30)
POSTFACH_1 = "haushalt.eins@example.invalid"
POSTFACH_2 = "haushalt.zwei@example.invalid"


# ================================================================ PNG (QR-artig)

def qr_png(seed: int, module: int = 29, skala: int = 4) -> bytes:
    """Deterministisches Graustufen-PNG mit QR-artigem Muster.

    zlib-Stufe 0 (gespeicherte Blöcke), damit die Bytes nicht von der zlib-Version abhängen.
    """
    rng = random.Random(seed)
    feld = [[rng.random() < 0.5 for _ in range(module)] for _ in range(module)]
    for ox, oy in ((0, 0), (module - 7, 0), (0, module - 7)):   # Suchmuster
        for y in range(7):
            for x in range(7):
                rand = x in (0, 6) or y in (0, 6)
                kern = 2 <= x <= 4 and 2 <= y <= 4
                feld[oy + y][ox + x] = rand or kern
    rand = 4
    groesse = (module + 2 * rand) * skala
    zeilen = []
    for py in range(groesse):
        my = py // skala - rand
        zeile = bytearray([0])
        for px in range(groesse):
            mx = px // skala - rand
            dunkel = 0 <= mx < module and 0 <= my < module and feld[my][mx]
            zeile.append(0 if dunkel else 255)
        zeilen.append(bytes(zeile))

    def chunk(typ: bytes, daten: bytes) -> bytes:
        return struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten) & 0xFFFFFFFF)

    roh = b"".join(zeilen)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", groesse, groesse, 8, 0, 0, 0, 0))
            + chunk(b"tEXt", b"Comment\x00Kontor-Testdaten (synthetisch)")
            + chunk(b"IDAT", zlib.compress(roh, 0)) + chunk(b"IEND", b""))


# ================================================================ FinTS-Umsätze

def hash_kennung(u: dict, n: int) -> str:
    """fints.md 3.4: Hash-Kennung für Umsätze ohne Bankreferenz."""
    teile = [u["buchungstag"], u["valuta"] or "", str(u["betrag"]), u["gegenpartei_iban"] or "",
             u["gegenpartei_name"] or "", u["verwendungszweck"], "S" if u["storno"] else ""]
    return "h:" + hashlib.sha256("|".join(teile).encode("utf-8")).hexdigest()[:16] + f":{n}"


def _stuecke(text: str, laenge: int) -> list[str]:
    return [text[i:i + laenge] for i in range(0, len(text), laenge)] or [""]


def _umbrechen(feld: str, breite: int = 65) -> list[str]:
    """Teilt ein Feld in Zeilen ≤ 65 Zeichen; keine Folgezeile beginnt mit ':' oder '-'."""
    zeilen, rest = [], feld
    while len(rest) > breite:
        schnitt = breite
        while rest[schnitt] in ":-" and schnitt > 1:
            schnitt -= 1
        zeilen.append(rest[:schnitt])
        rest = rest[schnitt:]
    zeilen.append(rest)
    return zeilen


def _mt940(e: dict) -> str:
    """MT940-Bruchstück eines gebuchten EUR-Umsatzes (fints.md 3.4)."""
    valuta = D.fromisoformat(e["mt_valuta"])
    buchung = D.fromisoformat(e["buchungstag"])
    if e["storno"]:
        kennung = "RD" if e["betrag"] > 0 else "RC"
    else:
        kennung = "C" if e["betrag"] >= 0 else "D"
    betrag = f"{abs(e['betrag']) // 100},{abs(e['betrag']) % 100:02d}"
    z61 = f":61:{valuta:%y%m%d}{buchung:%m%d}{kennung}{betrag}N{e['gvc_kurz']}NONREF"
    teile = [f"{e['gvc']}?00{e['buchungstext']}"]
    zweck = _stuecke(e["verwendungszweck"], 27)
    schluessel = [f"{n:02d}" for n in range(20, 30)] + ["60", "61", "62", "63"]
    assert len(zweck) <= len(schluessel)
    teile += [f"?{k}{s}" for k, s in zip(schluessel, zweck) if s]
    if e["mt_bic"]:
        teile.append(f"?30{e['mt_bic']}")
    if e["mt_konto"]:
        teile.append(f"?31{e['mt_konto']}")
    if e["gegenpartei_name"]:
        name = _stuecke(e["gegenpartei_name"], 27)
        assert len(name) <= 2
        teile += [f"?{k}{s}" for k, s in zip(("32", "33"), name)]
    z86 = ":86:" + "".join(teile)
    for z in (z61, z86):
        assert ":" not in z[4:] and "\n" not in z, z
        z.encode("iso-8859-1")
    return "\n".join([z61, *_umbrechen(z86)])


def _xml(s: str) -> str:
    return html_modul.escape(s, quote=False)


def _camt(e: dict) -> str:
    """camt.052.001.08-``Ntry`` eines Umsatzes (fints.md 3.4)."""
    dbit = e["betrag"] < 0
    ind = "DBIT" if dbit else "CRDT"
    teile = [f'<Ntry><Amt Ccy="{e["waehrung"]}">{abs(e["betrag"]) // 100}.{abs(e["betrag"]) % 100:02d}</Amt>',
             f"<CdtDbtInd>{ind}</CdtDbtInd>"]
    if e["storno"]:
        teile.append("<RvslInd>true</RvslInd>")
    teile.append(f"<Sts><Cd>{'PDNG' if e['vormerkung'] else 'BOOK'}</Cd></Sts>")
    if not e.get("ohne_buchungstag"):
        teile.append(f"<BookgDt><Dt>{e['buchungstag']}</Dt></BookgDt>")
    if e["camt_valuta"]:
        teile.append(f"<ValDt><Dt>{e['camt_valuta']}</Dt></ValDt>")
    if e["referenz"]:
        teile.append(f"<AcctSvcrRef>{_xml(e['referenz'])}</AcctSvcrRef>")
    teile.append("<BkTxCd><Prtry><Cd>NTRF+" + e["gvc"] + "</Cd><Issr>DK</Issr></Prtry></BkTxCd>")
    # Seite der Gegenpartei: CdtDbtInd, bei Storno umgekehrt; die eigene Seite steht ebenfalls da
    gegen_ist_cdtr = (ind == "DBIT") != e["storno"]
    eigen = (f"<Pty><Nm>{_xml(INHABER)}</Nm></Pty>", e["iban"])
    gegen_name = f"<Pty><Nm>{_xml(e['gegenpartei_name'])}</Nm></Pty>" if e["gegenpartei_name"] else None
    gegen = (gegen_name, e["camt_konto"])
    dbtr, cdtr = (eigen, gegen) if gegen_ist_cdtr else (gegen, eigen)
    parteien = []
    for rolle, (name, konto) in (("Dbtr", dbtr), ("Cdtr", cdtr)):
        if name:
            parteien.append(f"<{rolle}>{name}</{rolle}>")
        if konto:
            parteien.append(f"<{rolle}Acct><Id><IBAN>{_xml(konto)}</IBAN></Id></{rolle}Acct>")
    tx = ["<NtryDtls><TxDtls>"]
    if parteien:
        tx.append("<RltdPties>" + "".join(parteien) + "</RltdPties>")
    if e["verwendungszweck"]:
        tx.append("<RmtInf>" + "".join(f"<Ustrd>{_xml(s)}</Ustrd>" for s in e["ustrd"]) + "</RmtInf>")
    tx.append("</TxDtls></NtryDtls>")
    teile.append("".join(tx))
    teile.append("</Ntry>")
    return "".join(teile)


def _fints_daten(startwert: int) -> tuple[dict, dict, dict]:
    rng = random.Random(startwert + 6060)
    eintraege: list[dict] = []
    nummer = [0]

    def neu(iban: str, tag: D, betrag: int, name: str | None, konto: str | None, zweck: str, *,
            gvc: str = "177", text: str = "UEBERWEISUNG", valuta: D | None = None, referenz: bool = True,
            storno: bool = False, vormerkung: bool = False, sichtbar: tuple[D, D] | None = None,
            ohne_valuta: bool = False, ohne_buchungstag: bool = False, waehrung: str = "EUR",
            ustrd: list[str] | None = None, bic: str | None = None) -> dict:
        nummer[0] += 1
        valuta = valuta or tag
        e = {
            "iban": iban, "buchungstag": tag.isoformat(), "betrag": betrag, "waehrung": waehrung,
            "gegenpartei_name": name, "verwendungszweck": zweck, "storno": storno, "vormerkung": vormerkung,
            "gvc": gvc, "gvc_kurz": {"177": "TRF", "105": "DDT", "166": "TRF", "805": "CHG", "106": "MSC"}.get(
                gvc, "MSC"),
            "buchungstext": text, "referenz": f"KTR{startwert}{nummer[0]:06d}" if referenz else None,
            "mt_valuta": (tag if ohne_valuta else valuta).isoformat(),
            "camt_valuta": None if ohne_valuta else valuta.isoformat(),
            "ohne_buchungstag": ohne_buchungstag,
            "mt_konto": konto, "camt_konto": konto, "mt_bic": bic,
            "ustrd": ustrd if ustrd is not None else ([zweck] if zweck else []),
            "sichtbar": [s.isoformat() for s in sichtbar] if sichtbar else None,
        }
        if ohne_buchungstag:
            e["buchungstag"] = valuta.isoformat()
        eintraege.append(e)
        return e

    # ---------------------------------------------------------------- Girokonto
    neu(GIRO, D(2023, 12, 29), -2390, "Bäckerei Müller & Söhne", None, "Kartenzahlung Jahresende",
        gvc="106", text="KARTENZAHLUNG", valuta=D(2024, 1, 2))
    tag = D(2024, 1, 1)
    while tag <= D(2024, 7, 5):
        m = tag.month
        if tag.day == 1:
            neu(GIRO, tag, -98000, "Wohnbau Beispiel eG", FREMD[0], f"Miete {m:02d}/2024 Whg 3 links",
                gvc="105", text="DAUERAUFTRAG")
        if tag.day == 28:
            neu(GIRO, tag, 335000, "Arbeitgeber Muster GmbH", FREMD[1], f"LOHN/GEHALT {m:02d}/2024",
                gvc="166", text="GUTSCHRIFT")
        if tag.day == 5:
            neu(GIRO, tag, -9200, "Stadtwerke Musterstadt", FREMD[2], "Abschlag Strom Vertrag 4711-0815",
                gvc="105", text="LASTSCHRIFT", bic="TESTDEFFXXX")
        if tag.day == 25:
            neu(GIRO, tag, -30000, INHABER, TAGESGELD, "Sparrate Tagesgeld", gvc="177")
            neu(TAGESGELD, tag, 30000, INHABER, GIRO, "Sparrate Tagesgeld", gvc="166", text="GUTSCHRIFT")
        if tag.day == 30 or (m == 2 and tag.day == 29):
            neu(GIRO, tag, -490, None, None, f"Kontoführung {m:02d}/2024", gvc="805", text="ENTGELT")
        if tag.weekday() < 6 and rng.random() < 0.35:
            neu(GIRO, tag, -rng.randint(800, 9000), "Supermarkt Frischekorb", None,
                f"Kartenzahlung Filiale {rng.randint(1, 99):02d}", gvc="106", text="KARTENZAHLUNG")
        tag += dt.timedelta(days=1)
    # Storno einer Lastschrift (RD, positiv) und einer Gutschrift (RC, negativ)
    neu(GIRO, D(2024, 2, 5), -4999, "Versandhaus Beispiel", FREMD[3], "Bestellung 4711 Lastschrift",
        gvc="105", text="LASTSCHRIFT")
    neu(GIRO, D(2024, 2, 7), 4999, "Versandhaus Beispiel", FREMD[3], "Rücklastschrift Bestellung 4711",
        gvc="109", text="STORNO", storno=True)
    neu(GIRO, D(2024, 3, 11), 10000, "Erstattung Beispiel AG", FREMD[4], "Erstattung Vorgang 12",
        gvc="166", text="GUTSCHRIFT")
    neu(GIRO, D(2024, 3, 12), -10000, "Erstattung Beispiel AG", FREMD[4], "Storno Erstattung Vorgang 12",
        gvc="109", text="STORNO", storno=True)
    # zwei gleiche Umsätze am selben Tag ohne Bankreferenz (Hash-Kennung mit laufender Nummer)
    for _ in range(2):
        neu(GIRO, D(2024, 4, 9), -340, "Café Bohne", None, "Kartenzahlung Café", gvc="106", text="KARTENZAHLUNG",
            referenz=False)
    # langer Verwendungszweck, langer Name, mehrere Ustrd
    lang = ("Rechnung 2024-0042 Kundennummer 99887766 Leistungszeitraum Januar bis März "
            "Straßenbahn-Abo und Zusatzleistungen gemäß Vertrag")
    neu(GIRO, D(2024, 4, 15), -18990, "Verkehrsverbund Musterregion Abo-Service GmbH", FREMD[5], lang,
        gvc="105", text="LASTSCHRIFT", ustrd=[lang[:70], lang[70:]])
    # Gegen-Kontonummer statt IBAN (ungültig → None), Valuta abweichend
    neu(GIRO, D(2024, 5, 6), -2500, "Verein für Testzwecke e.V.", "1234567890", "Mitgliedsbeitrag 2024",
        gvc="105", text="LASTSCHRIFT", valuta=D(2024, 5, 3))
    # camt-Sonderfälle: ohne Valuta, ohne Buchungstag, Fremdwährung (nur camt)
    neu(GIRO, D(2024, 5, 21), -1500, "Kiosk am Markt", None, "Barverfügung Zuschlag", gvc="106", ohne_valuta=True)
    neu(GIRO, D(2024, 5, 22), -2750, "Buchhandlung Seitenweise", None, "Kartenzahlung Bücher", gvc="106",
        valuta=D(2024, 5, 22), ohne_buchungstag=True)
    neu(GIRO, D(2024, 5, 23), -1999, "Online Shop USA (fiktiv)", None, "Card payment", gvc="106",
        waehrung="USD")
    # Vormerkungen (nur camt): sichtbar von–bis (ausschließlich), danach gebucht
    for tag_v, betrag, name in ((D(2024, 6, 29), -6450, "Tankstelle Blitz"),
                                (D(2024, 7, 1), -2290, "Supermarkt Frischekorb"),
                                (D(2024, 7, 2), -1250, "Café Ölfass & Co.")):
        neu(GIRO, tag_v, betrag, name, None, "Vorgemerkt: Kartenzahlung", gvc="106", text="KARTENZAHLUNG",
            vormerkung=True, referenz=False, sichtbar=(tag_v - dt.timedelta(days=2), tag_v))
        neu(GIRO, tag_v, betrag, name, None, "Kartenzahlung", gvc="106", text="KARTENZAHLUNG")

    # ---------------------------------------------------------------- Tagesgeld, Kreditkarte, Depot
    for m in (3, 6):
        neu(TAGESGELD, D(2024, m, 28) if m == 3 else D(2024, m, 28), 1000 + m, None, None,
            f"Zinsgutschrift Q{m // 3}/2024", gvc="804", text="ZINSEN")
    for i in range(18):
        t = D(2024, 1, 3) + dt.timedelta(days=rng.randint(0, 180))
        neu(KARTE, t, -rng.randint(500, 25000), rng.choice(["Tankstelle Blitz", "Hotel Beispielhof",
                                                           "Online-Shop Sonnenschein", "Restaurant Zur Linde"]),
            None, f"Kartenumsatz {i + 1:02d}", gvc="106", text="KARTENZAHLUNG")
    neu(KARTE, D(2024, 2, 1), 45000, INHABER, GIRO, "Ausgleich Kreditkarte", gvc="166", text="GUTSCHRIFT")
    neu(DEPOT, D(2024, 2, 15), -100000, None, None, "Kauf Wertpapier (nicht geliefert)", gvc="177")

    eintraege.sort(key=lambda e: (e["iban"], e["buchungstag"], e["referenz"] or "", e["betrag"]))

    konten = [
        {"iban": GIRO, "bic": "TESTDEFFXXX", "kontonummer": "0000006601", "kontoart": 1, "waehrung": "EUR",
         "inhaber": INHABER, "inhaber2": INHABER2, "produkt": "Girokonto Komfort", "anfangssaldo": 125000},
        {"iban": TAGESGELD, "bic": "TESTDEFFXXX", "kontonummer": "0000006602", "kontoart": 10, "waehrung": "EUR",
         "inhaber": INHABER, "produkt": "Tagesgeld Plus", "anfangssaldo": 500000},
        {"iban": KARTE, "bic": "TESTDEFFXXX", "kontonummer": "0000006603", "kontoart": 50, "waehrung": "EUR",
         "inhaber": INHABER, "produkt": "Kreditkarte", "anfangssaldo": 0},
        {"iban": DEPOT, "bic": "TESTDEFFXXX", "kontonummer": "0000006604", "kontoart": 30, "waehrung": "EUR",
         "inhaber": INHABER, "produkt": "Depot", "anfangssaldo": 0},
        {"iban": NICHT_SEPA, "bic": "TESTDEFFXXX", "kontonummer": "0000006605", "kontoart": 1, "waehrung": "EUR",
         "inhaber": INHABER, "produkt": "Altkonto", "anfangssaldo": 0, "sepa": False},
        {"iban": DOLLAR, "bic": "TESTDEFFXXX", "kontonummer": "0000006606", "kontoart": 1, "waehrung": "USD",
         "inhaber": INHABER, "produkt": "Dollarkonto", "anfangssaldo": 0},
    ]
    for k in konten:
        if k.get("inhaber2") is None:
            k.pop("inhaber2", None)

    # ---------------------------------------------------------------- Attrappe und Wahrheit
    umsaetze_attrappe = []
    wahrheit = []
    for e in eintraege:
        basis = {
            "iban": e["iban"], "buchungstag": e["buchungstag"], "betrag": e["betrag"], "waehrung": "EUR",
            "gegenpartei_name": e["gegenpartei_name"],
            "gegenpartei_iban": e["camt_konto"] if e["camt_konto"] and ist_gueltig(e["camt_konto"]) else None,
            "verwendungszweck": e["verwendungszweck"], "vormerkung": e["vormerkung"], "storno": e["storno"],
        }
        mt = None if (e["vormerkung"] or e["waehrung"] != "EUR") else _mt940(e)
        umsaetze_attrappe.append({
            "iban": e["iban"], "buchungstag": e["buchungstag"], "betrag": e["betrag"],
            "vormerkung": e["vormerkung"], "sichtbar_ab": e["sichtbar"][0] if e["sichtbar"] else None,
            "sichtbar_bis": e["sichtbar"][1] if e["sichtbar"] else None,
            "mt940": mt or "", "camt": _camt(e),
        })
        w = {"iban": e["iban"], "vormerkung": e["vormerkung"], "sichtbar": e["sichtbar"],
             "camt": None, "mt940": None}
        if e["waehrung"] == "EUR":
            w["camt"] = dict(basis, valuta=e["camt_valuta"], umsatz_id=("ref:" + e["referenz"]) if e["referenz"]
                             else None)
        if mt:
            w["mt940"] = dict(basis, valuta=e["mt_valuta"], umsatz_id=None)
        wahrheit.append(w)
    # Hash-Kennungen: laufende Nummer in Lieferreihenfolge (Reihenfolge der Attrappe je Konto)
    for profil in ("camt", "mt940"):
        zaehler: dict[tuple, int] = {}
        for w in wahrheit:
            u = w[profil]
            if u is None or u["umsatz_id"] is not None:
                continue
            schluessel = (w["iban"], hash_kennung(u, 0))
            zaehler[schluessel] = zaehler.get(schluessel, 0) + 1
            u["umsatz_id"] = hash_kennung(u, zaehler[schluessel])

    erwartete_konten = [
        {"iban": k["iban"], "bic": k["bic"], "name": k["produkt"],
         "art": {1: "girokonto", 10: "sparkonto", 50: "kreditkonto"}[k["kontoart"]],
         "inhaber": k["inhaber"] + (" " + k["inhaber2"] if k.get("inhaber2") else ""), "waehrung": "EUR"}
        for k in sorted(konten, key=lambda k: k["iban"])
        if k["kontoart"] in (1, 10, 50) and k["waehrung"] == "EUR" and k.get("sepa", True)]

    daten = {
        "format": "kontor-fints-attrappe", "version": 1, "startwert": startwert,
        "blz": BLZ, "benutzer": "KONTOR-TEST-01", "kunden_id": None, "pin": PIN, "tan": TAN,
        "bank_name": "Synthetische Testbank Kontor",
        "tan_verfahren": {"funktion": "913", "technische_id": "QRTAN", "name": "QR-TAN synthetisch"},
        "challenge": "Bitte scannen Sie den QR-Code mit Ihrer Banking-App und geben Sie die TAN ein.",
        "qr_png": base64.b64encode(qr_png(startwert)).decode("ascii"),
        "heute": HEUTE.isoformat(),
        "konten": konten,
        "umsaetze": umsaetze_attrappe,
    }
    erwartung = {
        "startwert": startwert, "heute": HEUTE.isoformat(), "konten": erwartete_konten,
        "nicht_geliefert": [DEPOT, NICHT_SEPA, DOLLAR], "umsaetze": wahrheit,
        "pin": PIN, "tan": TAN, "blz": BLZ, "benutzer": "KONTOR-TEST-01",
        "qr_sha256": hashlib.sha256(qr_png(startwert)).hexdigest(),
        "challenge": daten["challenge"],
        "hinweis": "Erwartete BankUmsatz je Profil (fints.md 3.4); Vormerkungen sichtbar, wenn sichtbar[0] ≤ heute"
                   " < sichtbar[1]; gebuchte bis heute.",
    }
    # Mock-Vergleich (T 21): Profil camt, Stand „heute“ der Attrappe
    mock_umsaetze = []
    for w in wahrheit:
        u = w["camt"]
        if u is None or w["iban"] not in {k["iban"] for k in erwartete_konten}:
            continue
        if w["vormerkung"]:
            continue   # Mock: Vormerkungen sind nicht zeitlich begrenzt, daher nur gebuchte im Vergleich
        mock_umsaetze.append({
            "umsatz_id": u["umsatz_id"], "iban": u["iban"], "buchungstag": u["buchungstag"], "valuta": u["valuta"],
            "betrag": u["betrag"], "waehrung": "EUR", "gegenpartei_name": u["gegenpartei_name"],
            "gegenpartei_iban": u["gegenpartei_iban"], "verwendungszweck": u["verwendungszweck"],
            "vormerkung": False, "storno": u["storno"]})
    mock_umsaetze.sort(key=lambda u: (u["iban"], u["buchungstag"], u["umsatz_id"]))
    mock = {"format": "kontor-mock-daten", "version": 1,
            "bank": {"konten": erwartete_konten, "umsaetze": mock_umsaetze, "pin": PIN, "tan": TAN},
            "mail": {"postfaecher": [], "nachrichten": []}}
    return daten, erwartung, mock


# ================================================================ Mails

UTC = dt.timezone.utc


def _rfc2047(text: str, charset: str = "utf-8", art: str = "q") -> str:
    roh = text.encode(charset)
    if art == "b":
        return f"=?{charset}?b?{base64.b64encode(roh).decode()}?="
    aus = []
    for b in roh:
        c = chr(b)
        if c == " ":
            aus.append("_")
        elif c.isalnum() and b < 128:
            aus.append(c)
        else:
            aus.append(f"={b:02X}")
    return f"=?{charset}?q?{''.join(aus)}?="


def _qp(text: str, charset: str = "utf-8") -> str:
    """Quoted-Printable mit weichen Zeilenumbrüchen (≤ 76 Zeichen)."""
    zeilen_aus = []
    for zeile in text.split("\n"):
        kodiert = ""
        for b in zeile.encode(charset):
            c = chr(b)
            kodiert += c if (33 <= b <= 126 and c != "=") or c == " " else f"={b:02X}"
        if kodiert.endswith(" "):
            kodiert = kodiert[:-1] + "=20"
        stuecke = []
        while len(kodiert) > 75:
            schnitt = 75
            while kodiert[schnitt - 1] == "=" or (schnitt >= 2 and kodiert[schnitt - 2] == "="):
                schnitt -= 1
            stuecke.append(kodiert[:schnitt] + "=")
            kodiert = kodiert[schnitt:]
        stuecke.append(kodiert)
        zeilen_aus.extend(stuecke)
    return "\n".join(zeilen_aus)


def _b64(roh: bytes) -> str:
    s = base64.b64encode(roh).decode()
    return "\n".join(s[i:i + 76] for i in range(0, len(s), 76))


def html_regel(h: str) -> str:
    """mail.md 3.3 HTML-Regel (Wahrheit des Generators)."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", h)
    t = re.sub(r"(?s)<[^>]*>", " ", t)
    t = html_modul.unescape(t)
    return " ".join(t.split())


def _mails(startwert: int) -> tuple[dict[str, bytes], dict, dict]:
    rng = random.Random(startwert + 6161)
    ordner_def = {
        POSTFACH_1: ["INBOX", "[Gmail]/Alle Nachrichten"],
        POSTFACH_2: ["INBOX", "Bestellungen/Bücher"],
    }
    dateinamen = {(POSTFACH_1, "INBOX"): "eins_inbox.mbox", (POSTFACH_1, "[Gmail]/Alle Nachrichten"): "eins_alle.mbox",
                  (POSTFACH_2, "INBOX"): "zwei_inbox.mbox", (POSTFACH_2, "Bestellungen/Bücher"): "zwei_buecher.mbox"}
    inhalt: dict[tuple[str, str], list[tuple[dt.datetime, str, dict]]] = {k: [] for k in dateinamen}
    zaehler = [0]

    def mid() -> str:
        zaehler[0] += 1
        return f"<KONTOR-{startwert}-{zaehler[0]:04d}@mail.example.invalid>"

    def kopf(von: str, an: str, betreff_kodiert: str, datum: dt.datetime, message_id: str | None) -> list[str]:
        k = [f"From: {von}", f"To: {an}", f"Subject: {betreff_kodiert}",
             "Date: " + datum.astimezone(dt.timezone(dt.timedelta(hours=1))).strftime("%a, %d %b %Y %H:%M:%S +0100"),
             "MIME-Version: 1.0"]
        if message_id is not None:
            k.insert(0, f"Message-ID: {message_id}")
        return k

    def ablegen(adresse: str, ordner: str, empfangen: dt.datetime, roh: str, erw: dict | None) -> None:
        inhalt[(adresse, ordner)].append((empfangen, roh, erw))

    def zeit(monat: int, tag: int, stunde: int, minute: int) -> dt.datetime:
        return dt.datetime(2024, monat, tag, stunde, minute, rng.randint(0, 59), tzinfo=UTC)

    # --- Bestellbestätigung multipart/alternative, Text QP UTF-8, RFC-2047-Betreff mit Faltung
    def bestellung(adresse, ordner, monat, tag, nr):
        text = (f"Guten Tag Erika Mustermann,\n\nvielen Dank für Ihre Bestellung Nr. {nr}.\n"
                f"Artikel: „Größenwahn & Übermut“ (Taschenbuch), Menge 1, Preis 12,99 €\n"
                f"Gesamtbetrag: 12,99 €\nZahlungsart: Lastschrift\n\nIhre Bücherstube (fiktiv)\n")
        html = (f"<html><body><p>Guten Tag Erika Mustermann,</p><p>Bestellung <b>{nr}</b>: "
                f"&bdquo;Gr&ouml;&szlig;enwahn &amp; &Uuml;bermut&ldquo; &ndash; 12,99&nbsp;&euro;</p></body></html>")
        betreff = f"Ihre Bestellung {nr} bei der Bücherstube – Bestätigung und Zahlungsinformationen"
        b_kodiert = _rfc2047(betreff[:40]) + "\n " + _rfc2047(betreff[40:])
        e = zeit(monat, tag, 9, 15)
        m = mid()
        grenze = f"==grenze-{nr}=="
        roh = "\n".join(kopf(_rfc2047("Bücherstube (fiktiv)", "iso-8859-1") + " <bestellung@buecherstube.example.invalid>", adresse,
                             b_kodiert, e, m) + [
            f'Content-Type: multipart/alternative; boundary="{grenze}"', "", "Dies ist eine MIME-Nachricht.",
            f"--{grenze}", "Content-Type: text/plain; charset=utf-8", "Content-Transfer-Encoding: quoted-printable",
            "", _qp(text), f"--{grenze}", "Content-Type: text/html; charset=utf-8",
            "Content-Transfer-Encoding: quoted-printable", "", _qp(html), f"--{grenze}--", ""])
        ablegen(adresse, ordner, e, roh, {"nachricht_id": m, "empfangen": e, "absender": "bestellung@buecherstube.example.invalid",
                                         "betreff": betreff, "text": text})

    # --- Zahlungsbestätigung nur HTML, ISO-8859-1, base64, Entitäten, <style> und <script>
    def zahlung(adresse, ordner, monat, tag, betrag):
        html = ("<html><head><style>p { color: #333; }</style><script>var x = '<b>nicht anzeigen</b>';</script>"
                "</head><body><h1>Zahlung erhalten</h1><p>Wir haben Ihre Zahlung über "
                f"{betrag},00&nbsp;&euro; erhalten.</p><p>Empfänger: Bezahldienst &amp; Partner (fiktiv)</p>"
                "<p>Vorgangsnummer:&#160;ZD-" + str(rng.randint(100000, 999999)) + "</p></body></html>")
        betreff = f"Zahlungsbestätigung über {betrag},00 €"
        e = zeit(monat, tag, 18, 40)
        m = mid()
        roh = "\n".join(kopf("Bezahldienst <zahlung@bezahldienst.example.invalid>", adresse,
                             _rfc2047(betreff, "iso-8859-15", "b"), e, m) + [
            "Content-Type: text/html; charset=iso-8859-15", "Content-Transfer-Encoding: base64", "",
            _b64(html.encode("iso-8859-15")), ""])
        ablegen(adresse, ordner, e, roh, {"nachricht_id": m, "empfangen": e, "absender": "zahlung@bezahldienst.example.invalid",
                                         "betreff": betreff, "text": html_regel(html)})

    # --- Versandbestätigung, 7bit us-ascii, ohne Message-ID
    def versand(adresse, ordner, monat, tag, ohne_id=False):
        text = "Ihre Sendung ist unterwegs.\nSendungsnummer: SYNTH-00012345\n"
        e = zeit(monat, tag, 7, 5)
        m = None if ohne_id else mid()
        roh = "\n".join(kopf("versand@paket.example.invalid", adresse, "Versandbestaetigung", e, m) + [
            "Content-Type: text/plain; charset=us-ascii", "Content-Transfer-Encoding: 7bit", "", text.rstrip("\n"), ""])
        ablegen(adresse, ordner, e, roh, {"nachricht_id": m, "empfangen": e, "absender": "versand@paket.example.invalid",
                                         "betreff": "Versandbestaetigung", "text": text})

    # --- Rechnung mit Anhängen: text/plain-Anhang zuerst, eigentlicher Text als HTML; PDF-Anhang
    def rechnung(adresse, ordner, monat, tag):
        html = "<p>Ihre Rechnung finden Sie im Anhang.<br>Betrag: 42,00 &euro;</p>"
        e = zeit(monat, tag, 12, 0)
        m = mid()
        g = "==rechnung=="
        roh = "\n".join(kopf("rechnung@stadtwerke.example.invalid", adresse, "Ihre Rechnung", e, m) + [
            f'Content-Type: multipart/mixed; boundary="{g}"', "",
            f"--{g}", "Content-Type: text/plain; charset=utf-8", 'Content-Disposition: attachment; filename="info.txt"',
            "", "Dieser Anhang ist kein Nachrichtentext.", f"--{g}", "Content-Type: text/html; charset=utf-8", "", html,
            f"--{g}", "Content-Type: application/pdf", 'Content-Disposition: attachment; filename="rechnung.pdf"',
            "Content-Transfer-Encoding: base64", "", _b64(b"%PDF-1.4\n% synthetischer Testanhang\n%%EOF\n"),
            f"--{g}--", ""])
        ablegen(adresse, ordner, e, roh, {"nachricht_id": m, "empfangen": e, "absender": "rechnung@stadtwerke.example.invalid",
                                         "betreff": "Ihre Rechnung", "text": html_regel(html)})

    # --- Newsletter (Absenderfilter), unbekannter Zeichensatz mit UTF-8-Bytes
    def newsletter(adresse, ordner, monat, tag):
        text = "Angebote der Woche: Kaffee für 3,99 € – nur heute!\n"
        e = zeit(monat, tag, 6, 30)
        m = mid()
        roh_text = text.encode("utf-8").decode("latin-1")   # Bytes 1:1 in die Datei (8bit)
        roh = "\n".join(kopf("Werbung <newsletter@werbung.example.invalid>", adresse, "Angebote der Woche", e, m) + [
            "Content-Type: text/plain; charset=x-kontor-unbekannt", "Content-Transfer-Encoding: 8bit", "",
            roh_text.rstrip("\n"), ""])
        ablegen(adresse, ordner, e, roh, {"nachricht_id": m, "empfangen": e, "absender": "newsletter@werbung.example.invalid",
                                         "betreff": "Angebote der Woche", "text": text})

    bestellung(POSTFACH_1, "INBOX", 1, 15, "B-1001")
    zahlung(POSTFACH_1, "INBOX", 1, 16, 13)
    versand(POSTFACH_1, "INBOX", 1, 18)
    newsletter(POSTFACH_1, "INBOX", 2, 2)
    rechnung(POSTFACH_1, "INBOX", 2, 20)
    versand(POSTFACH_1, "INBOX", 3, 3, ohne_id=True)
    bestellung(POSTFACH_1, "INBOX", 4, 10, "B-1002")
    zahlung(POSTFACH_1, "INBOX", 4, 11, 27)
    newsletter(POSTFACH_1, "INBOX", 5, 6)
    bestellung(POSTFACH_1, "INBOX", 6, 3, "B-1003")
    # doppelte Message-ID (dieselbe Nachricht zweimal im Ordner)
    letzte = inhalt[(POSTFACH_1, "INBOX")][-1]
    inhalt[(POSTFACH_1, "INBOX")].append((letzte[0] + dt.timedelta(minutes=3), letzte[1], None))
    zahlung(POSTFACH_1, "[Gmail]/Alle Nachrichten", 3, 1, 99)
    bestellung(POSTFACH_1, "[Gmail]/Alle Nachrichten", 3, 2, "B-0999")

    bestellung(POSTFACH_2, "INBOX", 1, 20, "B-2001")
    versand(POSTFACH_2, "INBOX", 1, 22)
    newsletter(POSTFACH_2, "INBOX", 3, 15)
    zahlung(POSTFACH_2, "INBOX", 5, 5, 41)
    bestellung(POSTFACH_2, "Bestellungen/Bücher", 2, 8, "B-2002")
    zahlung(POSTFACH_2, "Bestellungen/Bücher", 2, 9, 18)
    rechnung(POSTFACH_2, "Bestellungen/Bücher", 4, 1)
    versand(POSTFACH_2, "Bestellungen/Bücher", 4, 2, ohne_id=True)
    bestellung(POSTFACH_2, "Bestellungen/Bücher", 6, 20, "B-2003")

    dateien: dict[str, bytes] = {}
    index = {"format": "kontor-mail-attrappe", "version": 1, "startwert": startwert, "postfaecher": {}}
    erwartung = {"startwert": startwert, "postfaecher": {}}
    uidvalidity = 1700000000
    for (adresse, ordner), liste in inhalt.items():
        uidvalidity += 11
        liste.sort(key=lambda x: x[0])
        teile = []
        erw_liste = []
        uid = 0
        uids = []
        for empfangen, roh, erw in liste:
            uid += rng.choice((1, 1, 2, 3))
            uids.append(uid)
            koerper = "\n".join((">" + z) if z.startswith("From ") else z for z in roh.split("\n"))
            teile.append("From MAILER-DAEMON " + empfangen.strftime("%a %b %d %H:%M:%S %Y") + "\n" + koerper + "\n")
            if erw is not None:
                erw_liste.append({
                    "nachricht_id": erw["nachricht_id"] or f"imap:{uidvalidity}:{uid}",
                    "postfach": adresse, "empfangen": empfangen.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "absender": erw["absender"], "betreff": erw["betreff"], "text": erw["text"], "uid": uid})
        name = dateinamen[(adresse, ordner)]
        # Kopfzeilen und Kodierungen sind ASCII; der 8bit-Text des Newsletters steht als latin-1-Zeichen für
        # seine UTF-8-Bytes in der Zeichenkette und wird so 1:1 geschrieben.
        dateien[f"m6/mail/{name}"] = "".join(teile).encode("latin-1")
        index["postfaecher"].setdefault(adresse, {})[ordner] = {"datei": name, "uidvalidity": uidvalidity,
                                                               "uids": uids}
        erw_liste.sort(key=lambda n: (n["empfangen"], n["nachricht_id"]))
        erwartung["postfaecher"].setdefault(adresse, {})[ordner] = {"uidvalidity": uidvalidity,
                                                                   "nachrichten": erw_liste}
    # Mock-Vergleich: konfigurierte Ordner eins → INBOX, zwei → Bestellungen/Bücher
    konfig = {POSTFACH_1: "INBOX", POSTFACH_2: "Bestellungen/Bücher"}
    nachrichten = []
    for adresse, ordner in konfig.items():
        for n in erwartung["postfaecher"][adresse][ordner]["nachrichten"]:
            nachrichten.append({k: n[k] for k in ("nachricht_id", "postfach", "empfangen", "absender", "betreff",
                                                  "text")})
    erwartung["vergleich_ordner"] = konfig
    mock = {"format": "kontor-mock-daten", "version": 1, "bank": {"konten": [], "umsaetze": []},
            "mail": {"postfaecher": list(konfig), "nachrichten": nachrichten}}
    index["ordner_reihenfolge"] = ordner_def
    return dateien, index, {"erwartung": erwartung, "mock": mock}


def _mbox_bytes_pruefen(dateien: dict[str, bytes]) -> None:
    for name, b in dateien.items():
        assert b.startswith(b"From MAILER-DAEMON "), name


# ================================================================ Benachrichtigungen

PRIORITAET = {
    "tan_erforderlich": 4, "tan_erinnerung": 4, "mail_token_abgelaufen": 4, "mail_token_widerrufen": 4,
    "mail_token_laeuft_ab": 3, "sync_fehler": 3, "tan_abgelaufen": 3, "split_abweichung": 3, "konto_fehlt": 3,
    "neuer_empfaenger": 3, "wiederkehrend_betrag": 3, "wiederkehrend_ausbleibend": 3, "mail_fehler": 3,
}


def erinnerungen(erstellt: dt.datetime, gueltig_bis: dt.datetime, intervall: int, anzahl: int,
                 takte: list[dt.datetime]) -> list[list[int]]:
    """benachrichtigungen.md 5: je Takt die Nummern der neu entstehenden Erinnerungen (unabhängige Wahrheit)."""
    m = 0
    aus = []
    for t in takte:
        neu = []
        if intervall > 0 and t <= gueltig_bis:
            k = int((t - erstellt).total_seconds() // (intervall * 60))
            n = min(k, anzahl)
            if n >= 1 and n > m:
                neu.append(n)
                m = n
        aus.append(neu)
    return aus


def _benachrichtigungen(startwert: int) -> dict:
    rng = random.Random(startwert + 6262)
    beispiele = []
    for art, link, mock, oeff in (
            ("tan_erforderlich", "/tan/3", False, "https://kontor.heim.example.invalid:8443/"),
            ("tan_erinnerung", "/tan/3", True, "http://kontor.lan.example.invalid"),
            ("sync_fehler", None, False, "https://kontor.heim.example.invalid"),
            ("mail_token_laeuft_ab", "/mail/postfaecher/2", False, None),
            ("konto_fehlt", "/sync/konten", True, None)):
        titel = {"tan_erforderlich": "TAN erforderlich", "tan_erinnerung": "Erinnerung: TAN erforderlich",
                 "sync_fehler": "Synchronisation fehlgeschlagen", "mail_token_laeuft_ab": "Mail-Anmeldung läuft ab",
                 "konto_fehlt": "Bankkonto ohne Konto"}[art]
        text = f"Synthetischer Text für {art} (Ä Ö Ü ß €)"
        click = (oeff.rstrip("/") + link) if (oeff and link) else None
        body = {"topic": "kontor-test-THEMA", "title": ("[Mock] " if mock else "") + titel, "message": text,
                "priority": PRIORITAET[art], "tags": [art]}
        if click:
            body["click"] = click
        beispiele.append({"art": art, "titel": titel, "text": text, "link": link, "mock_modus": mock,
                          "oeffentliche_url": oeff, "ntfy_koerper": body})
    faelle = []
    for nr in range(8):
        erstellt = dt.datetime(2024, 6, 30, 9, rng.randint(0, 59), rng.randint(0, 59), tzinfo=UTC)
        intervall = rng.choice((1, 2, 5, 10))
        anzahl = rng.choice((0, 1, 3, 5))
        gueltig = erstellt + dt.timedelta(minutes=intervall * rng.randint(1, 7) + rng.randint(0, 3))
        takte = sorted(erstellt + dt.timedelta(seconds=rng.randint(0, intervall * 60 * 8)) for _ in range(6))
        if nr == 0:   # fester Fall: genau auf der Grenze, ausgelassene Nummern, Ende durch Höchstzahl
            intervall, anzahl = 5, 3
            gueltig = erstellt + dt.timedelta(minutes=60)
            takte = [erstellt + dt.timedelta(minutes=x) for x in (4, 5, 6, 16, 21, 40)]
        faelle.append({
            "erstellt": erstellt.strftime("%Y-%m-%dT%H:%M:%SZ"), "gueltig_bis": gueltig.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "intervall": intervall, "anzahl": anzahl,
            "takte": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in takte],
            "erinnerungen": erinnerungen(erstellt, gueltig, intervall, anzahl, takte)})
    return {"startwert": startwert, "prioritaet": PRIORITAET, "beispiele": beispiele, "erinnerungen": faelle}


# ================================================================ Gesamt

def erzeuge_m6(startwert: int) -> tuple[dict[str, object], dict[str, str]]:
    daten, erw, mock = _fints_daten(startwert)
    mbox, index, mail = _mails(startwert)
    _mbox_bytes_pruefen(mbox)
    aus: dict[str, object] = {
        "m6/fints_bank.json": daten,
        "m6/fints_bank.erwartung.json": erw,
        "mock/m6_fints_vergleich.json": mock,
        "m6/mail/postfaecher.json": index,
        "m6/mail.erwartung.json": mail["erwartung"],
        "mock/m6_mail_vergleich.json": mail["mock"],
        "m6/benachrichtigungen.erwartung.json": _benachrichtigungen(startwert),
    }
    aus.update(mbox)
    text = {
        "m6/fints_bank.json": ("M6: Daten der FinTS-Attrappe (Konten mit Kontoart, Umsätze als MT940-Bruchstück und "
                               "camt.052-Ntry, synthetische PIN/TAN, QR-PNG)"),
        "m6/fints_bank.erwartung.json": "M6: erwartete BankKonto/BankUmsatz je Profil camt/mt940 (fints.md 3.4)",
        "mock/m6_fints_vergleich.json": "M6: Mock-Daten mit denselben Konten und Umsätzen (Profil camt) für T 21",
        "m6/mail/postfaecher.json": "M6: Index der IMAP-Attrappe (Postfach → Ordner → mbox, UIDVALIDITY, UIDs)",
        "m6/mail.erwartung.json": "M6: erwartete MailNachricht je Postfach und Ordner (mail.md 3.3)",
        "mock/m6_mail_vergleich.json": "M6: dieselben Nachrichten der konfigurierten Ordner als Mock-Daten (T 21)",
        "m6/benachrichtigungen.erwartung.json": ("M6: Prioritäten, erwartete ntfy-Körper, Fälle der "
                                                 "TAN-Erinnerungen (benachrichtigungen.md 3–5)"),
    }
    for name in mbox:
        text[name] = "M6: synthetisches Postfach im mbox-Format (INTERNALDATE in der From-Zeile, UTC)"
    return aus, text
