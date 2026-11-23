"""Testdaten für Meilenstein 5: wiederkehrende Buchungen, Kredite, Berichte, Export.

Alles synthetisch, fester Startwert. ``erzeuge_m5`` liefert ``({Pfad: JSON-Objekt}, {Pfad: Beschreibung})``:

- ``m5/kredite.json``: Kreditfälle (alle drei Zinsmethoden, Schaltjahr, Monatsende, gebrochene erste
  Periode, Sondertilgungen innerhalb einer Periode, am Fälligkeitstag und über die Restschuld hinaus,
  Zins 0, Schlussrate, zu kleine Rate) mit dem **unabhängig** berechneten Tilgungsplan. Die Berechnung
  hier verwendet ``decimal.Decimal`` mit 60 Stellen und ``ROUND_HALF_UP`` und zählt die Zinstage über
  Ordinalzahlen bzw. eine eigene 30E/360-Zählung; die Tests rechnen zusätzlich mit ``Fraction`` nach.
- ``mock/m5_kredit.json`` und ``mock/m5_kredit.erwartung.json``: Girokonto 2024 mit Ratenzahlungen
  eines Darlehens (Wochenend-/Feiertagsverschiebung), Sondertilgung, gleich hoher Zahlung an einen
  anderen Empfänger, Kontoführungsgebühr der Bank; Wahrheit je Zinsmethode (Aufteilung jeder Rate) und
  Jahresauszüge 2024 mit Abweichungen samt erwarteter Korrekturbuchung.
- ``mock/m5_wiederkehrend.json`` und ``mock/m5_wiederkehrend.erwartung.json``: Girokonto 2023–2024 mit
  Abos, Daueraufträgen, Lastschriften (monatlich, vierteljährlich, jährlich), Verschiebungen nach
  Wochenende und bundesweiten Feiertagen, Betragsänderungen, ausbleibender Zahlung, Lücke, neuen
  Empfängern und unregelmäßigen Einkäufen; Wahrheit der Serien zu mehreren Stichtagen und der
  Benachrichtigungen im wöchentlichen Abruf.
- ``m5/berichte.erwartung.json``: Kontostandsverlauf und Einnahmen/Ausgaben für ``kmy/standard.kmy``
  sowie Exporterwartungen (Reihenfolge der Buchungen eines Filters), aus dem Modell des Generators.
"""

from __future__ import annotations

import calendar
import datetime as dt
import random
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .iban import fiktive_iban

D = dt.date
W_GIRO = fiktive_iban(5501)
K_GIRO = fiktive_iban(5511)
BANK_IBAN = fiktive_iban(5599)   # Gegen-IBAN der fiktiven Bank (fremd)
TOLERANZ = 5


# ================================================================ Kalender

def monat_plus(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    j, m = d.year + m // 12, m % 12 + 1
    return D(j, m, min(d.day, calendar.monthrange(j, m)[1]))


def ostersonntag(jahr: int) -> dt.date:
    """Gaußsche Osterformel (Anonymer Gregorianischer Algorithmus)."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    monat = (h + l_ - 7 * m + 114) // 31
    tag = (h + l_ - 7 * m + 114) % 31 + 1
    return D(jahr, monat, tag)


def feiertage(jahr: int) -> set[dt.date]:
    """Bundesweite gesetzliche Feiertage."""
    o = ostersonntag(jahr)
    return {D(jahr, 1, 1), o - dt.timedelta(days=2), o + dt.timedelta(days=1), D(jahr, 5, 1),
            o + dt.timedelta(days=39), o + dt.timedelta(days=50), D(jahr, 10, 3), D(jahr, 12, 25), D(jahr, 12, 26)}


def werktag(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in feiertage(d.year)


def naechster_werktag(d: dt.date) -> dt.date:
    while not werktag(d):
        d += dt.timedelta(days=1)
    return d


def voriger_werktag(d: dt.date) -> dt.date:
    while not werktag(d):
        d -= dt.timedelta(days=1)
    return d


def monatsende(j: int, m: int) -> dt.date:
    return D(j, m, calendar.monthrange(j, m)[1])


# ================================================================ Tilgungsplan (unabhängige Rechnung)

def _tage_30e(a: dt.date, b: dt.date) -> int:
    """30E/360: jeder Monat 30 Tage, der 31. zählt als 30."""
    ta, tb = (30 if a.day == 31 else a.day), (30 if b.day == 31 else b.day)
    return (b.year * 12 + b.month - a.year * 12 - a.month) * 30 + tb - ta


def _tage_act(a: dt.date, b: dt.date) -> int:
    return b.toordinal() - a.toordinal()


def plan_decimal(p: dict) -> dict:
    """Tilgungsplan nach kredite.md 3, gerechnet mit Decimal (60 Stellen) und ROUND_HALF_UP.

    Liefert {"fehler": "kredit_rate_zu_klein"} oder den Plan im Schema ``Tilgungsplan``.
    """
    methode = p.get("zinsmethode", "30/360")
    tage = _tage_30e if methode == "30/360" else _tage_act
    basis = Decimal(365 if methode == "act/365" else 360)
    p_jahr = Decimal(p["sollzins"]) / Decimal(1_000_000)
    stand = D.fromisoformat(p["stand_datum"])
    erste = D.fromisoformat(p["erste_faelligkeit"])
    rate = p["rate"]
    st = sorted(((D.fromisoformat(s["datum"]), i, s["betrag"]) for i, s in enumerate(p.get("sondertilgungen", []))))
    rest = p["restschuld"]
    zeilen = []
    vorher_f = stand
    with localcontext() as ctx:
        ctx.prec = 60
        for nr in range(1, 1201):
            f = monat_plus(erste, nr - 1)
            laenge = 30 if (methode == "30/360" and nr >= 2) else tage(vorher_f, f)
            r_vorher = rest
            stuecke = []      # (Restschuld, Tage)
            lage = 0
            sonder = 0
            for datum, _, betrag in st:
                if vorher_f < datum <= f:
                    pos = min(laenge, tage(vorher_f, datum))
                    stuecke.append((rest, pos - lage))
                    lage = pos
                    w = min(betrag, rest)
                    rest -= w
                    sonder += w
            stuecke.append((rest, laenge - lage))
            z_exakt = sum((Decimal(r) * p_jahr * Decimal(t) / basis for r, t in stuecke), Decimal(0))
            zins = int(z_exakt.quantize(Decimal(1), rounding=ROUND_HALF_UP))
            if rest + zins <= rate:
                r_zahl, tilgung, ende = rest + zins, rest, True
            else:
                r_zahl, tilgung, ende = rate, rate - zins, False
            zeilen.append({"nr": nr, "faelligkeit": f.isoformat(), "zinstage": laenge, "restschuld_vorher": r_vorher,
                           "sondertilgung": sonder, "zins": zins, "tilgung": tilgung, "rate": r_zahl,
                           "restschuld_nachher": rest - tilgung})
            rest -= tilgung
            vorher_f = f
            if ende:
                break
        else:
            return {"fehler": "kredit_rate_zu_klein"}
    return {"zeilen": zeilen, "anzahl_raten": len(zeilen), "summe_zins": sum(z["zins"] for z in zeilen),
            "summe_tilgung": sum(z["tilgung"] for z in zeilen),
            "summe_sondertilgung": sum(z["sondertilgung"] for z in zeilen),
            "letzte_faelligkeit": zeilen[-1]["faelligkeit"]}


def _param(restschuld, stand, sollzins, rate, erste, methode="30/360", sonder=()):
    d = {"restschuld": restschuld, "stand_datum": stand, "sollzins": sollzins, "zinsmethode": methode,
         "rate": rate, "erste_faelligkeit": erste, "sondertilgungen": [{"datum": a, "betrag": b} for a, b in sonder]}
    return d


def kreditfaelle() -> dict:
    faelle = []

    def fall(name, text, param):
        plan = plan_decimal(param)
        faelle.append({"name": name, "beschreibung": text, "parameter": param, **(
            {"fehler": plan["fehler"]} if "fehler" in plan else {"plan": plan})})

    methoden = ["30/360", "act/360", "act/365"]
    for m in methoden:
        k = m.replace("/", "_")
        fall(f"standard_{k}", "Annuität 200 000 €, 3,45 %, Rate 2 000 €, gebrochene erste Periode 15.01.→01.02.2024; "
                              "über die Schaltjahre 2024 und 2028",
             _param(20_000_000, "2024-01-15", 34_500, 200_000, "2024-02-01", m))
        fall(f"monatsende_{k}", "Fälligkeit am 31. (Februar → 29./28., April → 30.), 4,125 %, ab 31.12.2023",
             _param(5_000_000, "2023-12-31", 41_250, 150_000, "2024-01-31", m))
        fall(f"sondertilgungen_{k}", "Sondertilgungen innerhalb einer Periode (15.06.2024), zwei am Fälligkeitstag "
                                     "01.04.2025 in Eingabereihenfolge und eine am Monatsende 31.12.2026",
             _param(10_000_000, "2024-03-10", 29_900, 90_000, "2024-04-01", m,
                    [("2024-06-15", 1_000_000), ("2025-04-01", 500_000), ("2025-04-01", 250_000),
                     ("2026-12-31", 300_000)]))
        fall(f"erste_periode_lang_{k}", "Erste Periode über zweieinhalb Monate (05.01.→20.03.2024), 5,5 %",
             _param(3_000_000, "2024-01-05", 55_000, 60_000, "2024-03-20", m))
    fall("sondertilgung_ueber_rest", "Sondertilgung größer als die Restschuld beendet den Plan; letzte Rate nur Zins",
         _param(1_000_000, "2024-01-01", 50_000, 50_000, "2024-02-01", "30/360", [("2024-08-20", 9_999_999)]))
    fall("sondertilgung_ueber_rest_act_365", "Wie sondertilgung_ueber_rest mit act/365",
         _param(1_000_000, "2024-01-01", 50_000, 50_000, "2024-02-01", "act/365", [("2024-08-20", 9_999_999)]))
    fall("zins_null", "Zinsloses Darlehen: Raten reine Tilgung, Schlussrate kleiner",
         _param(100_000, "2024-05-02", 0, 30_000, "2024-06-01", "act/360"))
    fall("schaltjahr_kurz_act_365", "Erste Fälligkeit am 29.02.2024, act/365 (Basis immer 365), kurze Laufzeit",
         _param(250_000, "2024-02-10", 60_000, 100_000, "2024-02-29", "act/365"))
    fall("schaltjahr_kurz_act_360", "Wie schaltjahr_kurz_act_365 mit act/360",
         _param(250_000, "2024-02-10", 60_000, 100_000, "2024-02-29", "act/360"))
    fall("hohe_zinsen_rundung", "Kleine Beträge, krummer Zins 7,4321 %: viele Rundungen auf halbe Cent nahe",
         _param(123_457, "2023-11-17", 74_321, 4_321, "2023-12-17", "act/365"))
    fall("rate_zu_klein", "Rate deckt nur den Zins (12 % auf 100 000 €, Rate 1 000 €): kein Ende in 1 200 Raten",
         _param(10_000_000, "2024-01-01", 120_000, 100_000, "2024-02-01", "30/360"))
    return {"beschreibung": "Tilgungspläne nach kredite.md 3, unabhängig mit Decimal (ROUND_HALF_UP) berechnet. "
                            "Fälle mit 'fehler' müssen mit 422 kredit_rate_zu_klein abgelehnt werden.",
            "faelle": faelle}


# ================================================================ Kredit in der Synchronisation

KREDIT_BASIS = {"name": "Darlehen Fiktivbank 0815", "restschuld": 15_000_000, "stand_datum": "2023-12-31",
                "sollzins": 38_700, "rate": 95_000, "erste_faelligkeit": "2024-01-30",
                "sondertilgungen": [{"datum": "2024-07-15", "betrag": 1_000_000}],
                "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "Fiktivbank AG"},
                                {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Darlehen 0815"}]}


def kreditdaten(startwert: int) -> dict:
    rng = random.Random(startwert + 51)
    umsaetze: list[dict] = []
    art: dict[str, dict] = {}

    def neu(tag: dt.date, betrag: int, name: str | None, zweck: str, meta: dict, gegen: str | None = None) -> str:
        uid = f"K-{len(umsaetze) + 1:04d}"
        umsaetze.append({"umsatz_id": uid, "iban": K_GIRO, "buchungstag": tag.isoformat(), "valuta": tag.isoformat(),
                         "betrag": betrag, "waehrung": "EUR", "gegenpartei_name": name, "gegenpartei_iban": gegen,
                         "verwendungszweck": zweck, "vormerkung": False, "storno": False})
        art[uid] = meta
        return uid

    erste = D.fromisoformat(KREDIT_BASIS["erste_faelligkeit"])
    raten = []   # (uid, Fälligkeit)
    for i in range(13):  # Januar 2024 bis Januar 2025
        f = monat_plus(erste, i)
        tag = naechster_werktag(f)
        assert abs((tag - f).days) <= TOLERANZ
        uid = neu(tag, -KREDIT_BASIS["rate"], "Fiktivbank AG", f"Rate Darlehen 0815 {f.month:02d}/{f.year}",
                  {"art": "rate", "faelligkeit": f.isoformat()}, BANK_IBAN)
        raten.append((uid, f))
    neu(D(2024, 7, 15), -1_000_000, "Fiktivbank AG", "Sondertilgung Darlehen 0815", {"art": "sondertilgung"},
        BANK_IBAN)
    neu(D(2024, 3, 28), -KREDIT_BASIS["rate"], "Möbelhaus Fiktiv", "Ratenkauf Sofa Darlehen 0815 ähnlich",
        {"art": "fremd_gleicher_betrag"})
    neu(D(2024, 6, 28), -500, "Fiktivbank AG", "Kontoführung Darlehenskonto", {"art": "gebuehr"}, BANK_IBAN)
    neu(D(2024, 9, 30), -KREDIT_BASIS["rate"], "Fiktivbank AG", "Rate Darlehen 4711 09/2024",
        {"art": "anderer_zweck"}, BANK_IBAN)
    for monat in range(1, 13):
        neu(voriger_werktag(monatsende(2024, monat)), 310_000, "Arbeitgeber Muster GmbH (fiktiv)",
            f"LOHN/GEHALT {monat:02d}/2024", {"art": "sonstig"})
        for _ in range(rng.randint(2, 4)):
            neu(D(2024, monat, rng.randint(1, 27)), -rng.randint(900, 8000), "Supermarkt Frischekorb",
                "Einkauf Filiale", {"art": "sonstig"})
    umsaetze.sort(key=lambda u: (u["buchungstag"], u["umsatz_id"]))

    methoden = {}
    for m in ("30/360", "act/360", "act/365"):
        param = {k: KREDIT_BASIS[k] for k in ("restschuld", "stand_datum", "sollzins", "rate", "erste_faelligkeit",
                                               "sondertilgungen")}
        param["zinsmethode"] = m
        plan = plan_decimal(param)
        nach_f = {z["faelligkeit"]: z for z in plan["zeilen"]}
        aufteilung = {}
        for uid, f in raten:
            z = nach_f[f.isoformat()]
            aufteilung[uid] = {"faelligkeit": f.isoformat(), "zins": z["zins"], "tilgung": z["tilgung"]}
        im_jahr = [uid for uid, _ in raten if next(u for u in umsaetze if u["umsatz_id"] == uid)["buchungstag"]
                   .startswith("2024-")]
        zinsen = sum(aufteilung[u]["zins"] for u in im_jahr)
        tilgung = sum(aufteilung[u]["tilgung"] for u in im_jahr)
        rest = KREDIT_BASIS["restschuld"] - tilgung - 1_000_000   # Sondertilgung vom Anwender gebucht
        plan_rest = [z for z in plan["zeilen"] if z["faelligkeit"] <= "2024-12-31"][-1]["restschuld_nachher"]
        assert plan_rest == rest, (m, plan_rest, rest)

        def korrektur(dz: int, dr: int) -> list[dict]:
            aus = []
            if dz:
                aus.append({"konto": "zins", "betrag": dz, "memo": "Zinskorrektur"})
            if dr:
                aus.append({"konto": "darlehen", "betrag": -dr, "memo": "Restschuldkorrektur"})
            if dr != dz:
                aus.append({"konto": "korrekturen", "betrag": dr - dz, "memo": ""})
            return aus

        auszuege = {}
        for name, dz, dr in (("exakt", 0, 0), ("zins_hoeher", 123, 123), ("abweichend", 50, -200),
                             ("nur_restschuld", 0, 1), ("nur_zinsen", -7, 0)):
            auszuege[name] = {"restschuld": rest + dr, "zinsen": zinsen + dz, "restschuld_berechnet": rest,
                              "zinsen_berechnet": zinsen, "differenz_restschuld": dr, "differenz_zinsen": dz,
                              "korrektur": korrektur(dz, dr)}
        methoden[m] = {"plan_zeilen_2024": [z for z in plan["zeilen"] if z["faelligkeit"] <= "2025-01-31"],
                       "aufteilung": aufteilung, "raten_2024": im_jahr, "jahresauszug_2024": auszuege}
    mock = {"format": "kontor-mock-daten", "version": 1, "bank": {"konten": [
        {"iban": K_GIRO, "bic": "TESTDEFFXXX", "name": "Girokonto", "art": "girokonto",
         "inhaber": "Erika Mustermann (fiktiv)", "waehrung": "EUR"}], "umsaetze": umsaetze},
        "mail": {"postfaecher": ["haushalt.eins@example.invalid"], "nachrichten": []}}
    erw = {"beschreibung": "Kredit in der Synchronisation (kredite.md 4, 5). Ablauf: Darlehenskonto (kreditkonto) "
                           "und Kategorie Zinsen anlegen, Kredit mit 'kredit' und der Zinsmethode anlegen "
                           "(zahlungskonto = Konto der IBAN, nach dem ersten Abruf), Abruf 2024-01-01 bis 2025-01-31. "
                           "Die Sondertilgung bucht der Anwender auf das Darlehenskonto um; danach Jahresabgleich "
                           "2024 mit einem der Jahresauszüge.",
           "iban": K_GIRO, "kredit": KREDIT_BASIS, "abruf": {"von": "2024-01-01", "bis": "2025-01-31"},
           "umsatz_art": art, "methoden": methoden}
    return {"mock": mock, "erwartung": erw}


# ================================================================ Wiederkehrende Buchungen

def _serie(name: str, richtung: str, rhythmus: str, termine: list[tuple[int, dt.date, int]], zweck) -> dict:
    return {"name": name, "richtung": richtung, "rhythmus": rhythmus, "termine": termine, "zweck": zweck}


RHYTHMUS = {"monatlich": (1, 3), "vierteljaehrlich": (3, 3), "jaehrlich": (12, 2)}
PROGRESSION_START = D(2024, 5, 31)


def _serien() -> list[dict]:
    serien = []
    monate = [(j, m) for j in (2023, 2024) for m in range(1, 13)]

    def monatlich(tag: int, betrag, *, ab=0, bis=len(monate), fehlt=(), verschieben=naechster_werktag):
        aus = []
        for i, (j, m) in enumerate(monate):
            if ab <= i < bis and (j, m) not in fehlt:
                aus.append((i, verschieben(D(j, m, min(tag, calendar.monthrange(j, m)[1]))), betrag(j, m)))
        return aus

    serien.append(_serie("Wohnbau Fiktiva eG", "ausgabe", "monatlich",
                         monatlich(1, lambda j, m: -98_000 if (j, m) >= (2024, 9) else -95_000),
                         lambda d: f"Miete {d.month:02d}/{d.year} Whg 3 links"))
    serien.append(_serie("Fiktiv-Stream GmbH", "ausgabe", "monatlich",
                         monatlich(15, lambda j, m: -1_499 if (j, m) >= (2024, 10) else -1_299),
                         lambda d: "Abo Premium Kundennr 4711-08"))
    serien.append(_serie("Studio Muskelkater (fiktiv)", "ausgabe", "monatlich",
                         monatlich(3, lambda j, m: -3_990, bis=18),
                         lambda d: f"Mitgliedsbeitrag {d.month:02d}/{d.year}"))
    serien.append(_serie("Zeitschrift Lesefreude (fiktiv)", "ausgabe", "monatlich",
                         monatlich(20, lambda j, m: -890, fehlt={(2024, 3)}),
                         lambda d: "Abo Lesefreude Heft"))
    serien.append(_serie("Arbeitgeber Muster GmbH (fiktiv)", "einnahme", "monatlich",
                         [(i, voriger_werktag(monatsende(j, m)), 285_000) for i, (j, m) in enumerate(monate)],
                         lambda d: f"LOHN/GEHALT {d.month:02d}/{d.year}"))
    serien.append(_serie("Neuer Dienst Wolke (fiktiv)", "ausgabe", "monatlich",
                         monatlich(18, lambda j, m: -499, ab=22),
                         lambda d: "Cloudspeicher 2 TB"))
    quartal = [(i, naechster_werktag(D(j, m, 1)), -4_790 if (j, m) >= (2024, 10) else -4_590)
               for i, (j, m) in enumerate((j, m) for j in (2023, 2024) for m in (1, 4, 7, 10))]
    serien.append(_serie("Fiktiva Haftpflicht AG", "ausgabe", "vierteljaehrlich", quartal,
                         lambda d: "Beitrag Privathaftpflicht Vertrag 0042"))
    serien.append(_serie("Fiktive Kfz-Steuerkasse", "ausgabe", "jaehrlich",
                         [(i, naechster_werktag(D(j, 3, 10)), -18_400) for i, j in enumerate((2023, 2024))],
                         lambda d: "Kfz-Steuer MU-ST 4711"))
    return serien


def _eintraege(umsaetze: list[dict], stichtag: dt.date) -> dict[tuple[str, str], list[dict]]:
    """Gruppen nach wiederkehrend.md 2.1 (ein Konto, Empfänger = gegenpartei_name)."""
    g: dict[tuple[str, str], list[dict]] = {}
    for u in umsaetze:
        if u["gegenpartei_name"] and u["buchungstag"] <= stichtag.isoformat():
            g.setdefault((u["gegenpartei_name"], "ausgabe" if u["betrag"] < 0 else "einnahme"), []).append(u)
    return g


def _spec_kette(eintraege: list[dict], m: int) -> list[dict]:
    """Kette nach M16-Definition 1 (ersetzt wiederkehrend.md 2.2, E-192): Anker unter den Einträgen der letzten
    TOLERANZ Tage, rückwärts verketten, zusätzliche Zahlungen am Termin überspringen."""
    d = [D.fromisoformat(e["buchungstag"]) for e in eintraege]
    abw = lambda c, x: abs((d[c] - monat_plus(d[x], m)).days)  # noqa: E731

    def ab(a: int) -> list[int]:
        glieder, c, vorige = [a], a, set()
        while True:
            kand = [x for x in range(c) if abw(c, x) <= TOLERANZ]
            if not kand:
                return glieder
            p = min(kand, key=lambda x: (eintraege[x]["betrag"] != eintraege[c]["betrag"], abw(c, x), -x))
            if any((d[c] - d[x]).days > TOLERANZ and (d[x] - d[p]).days > TOLERANZ and x not in vorige
                   for x in range(p + 1, c)):
                return glieder
            glieder.append(p)
            vorige, c = set(kand), p

    anker = [i for i in range(len(eintraege)) if (d[-1] - d[i]).days <= TOLERANZ]
    ketten = {i: ab(i) for i in anker}
    a = max(anker, key=lambda i: (len(ketten[i]), len(ketten[i]) > 1
                                  and eintraege[i]["betrag"] == eintraege[ketten[i][1]]["betrag"], i))
    return [eintraege[i] for i in reversed(ketten[a])]


def _spec_erkennung(eintraege: list[dict]) -> tuple[str, list[dict]] | None:
    """Spezifikationsregel 2.2/2.3 (Kette nach M16) – nur zur Selbstkontrolle des Generators, nicht als Wahrheit."""
    eintraege = sorted(eintraege, key=lambda u: (u["buchungstag"], u["umsatz_id"]))
    for name, (m, mindest) in RHYTHMUS.items():
        k = _spec_kette(eintraege, m)
        if len(k) >= mindest:
            return name, k
    return None


def wiederkehrenddaten(startwert: int) -> dict:
    rng = random.Random(startwert + 52)
    umsaetze: list[dict] = []
    serie_von: dict[str, tuple[str, int]] = {}

    def neu(tag: dt.date, betrag: int, name: str, zweck: str) -> str:
        uid = f"W-{len(umsaetze) + 1:04d}"
        umsaetze.append({"umsatz_id": uid, "iban": W_GIRO, "buchungstag": tag.isoformat(), "valuta": tag.isoformat(),
                         "betrag": betrag, "waehrung": "EUR", "gegenpartei_name": name, "gegenpartei_iban": None,
                         "verwendungszweck": zweck, "vormerkung": False, "storno": False})
        return uid

    serien = _serien()
    for s in serien:
        for idx, tag, betrag in s["termine"]:
            serie_von[neu(tag, betrag, s["name"], s["zweck"](tag))] = (s["name"], idx)
    # unregelmäßig: Supermarkt (2–4 je Monat), Baumarkt (feste unregelmäßige Tage)
    for j in (2023, 2024):
        for m in range(1, 13):
            for _ in range(rng.randint(2, 4)):
                neu(D(j, m, rng.randint(1, 28)), -rng.randint(700, 9500), "Supermarkt Frischekorb", "Einkauf Filiale")
    for t in ("2023-02-11", "2023-05-27", "2023-06-03", "2023-09-16", "2024-01-20", "2024-04-06", "2024-08-24",
              "2024-12-07"):
        neu(D.fromisoformat(t), -rng.randint(1500, 25000), "Baumarkt Fiktiv", "Einkauf Garten")
    handwerker = neu(D(2024, 7, 22), -45_000, "Handwerker Hammer (fiktiv)", "Rechnung 2024-117 Reparatur Dach")
    erstattung = neu(D(2024, 9, 9), 12_345, "Fiktive Krankenkasse", "Erstattung Zahnreinigung")
    umsaetze.sort(key=lambda u: (u["buchungstag"], u["umsatz_id"]))
    nach_uid = {u["umsatz_id"]: u for u in umsaetze}

    # ---------------- Wahrheit aus der Konstruktion: Serie = Lauf aufeinanderfolgender Termine
    def wahrheit(stichtag: dt.date) -> list[dict]:
        aus = []
        for s in serien:
            m, mindest = RHYTHMUS[s["rhythmus"]]
            bis_jetzt = [(i, t, b) for i, t, b in s["termine"] if t <= stichtag]
            if not bis_jetzt:
                continue
            lauf = [bis_jetzt[-1]]
            for x in reversed(bis_jetzt[:-1]):
                if x[0] == lauf[0][0] - 1:
                    lauf.insert(0, x)
                else:
                    break
            if len(lauf) < mindest:
                continue
            letzte = lauf[-1][1]
            f = monat_plus(letzte, m)
            f2 = monat_plus(letzte, 2 * m)
            tol = dt.timedelta(days=TOLERANZ)
            status = "aktiv" if stichtag <= f + tol else "ausbleibend" if stichtag <= f2 + tol else "beendet"
            uids = [next(u for u, (n, i) in serie_von.items() if n == s["name"] and i == x[0]) for x in lauf]
            betrag = lauf[-1][2]
            aus.append({"empfaenger": s["name"], "richtung": s["richtung"], "rhythmus": s["rhythmus"],
                        "anzahl": len(lauf), "erste": lauf[0][1].isoformat(), "letzte": letzte.isoformat(),
                        "betrag": betrag, "jahreskosten": -betrag * 12 // m, "naechste_faelligkeit": f.isoformat(),
                        "status": status, "umsatz_ids": uids})
        return sorted(aus, key=lambda x: x["empfaenger"])

    stichtage = ["2023-02-15", "2023-03-31", "2024-07-20", "2024-08-09", "2024-12-31"]
    wahr = {s: wahrheit(D.fromisoformat(s)) for s in stichtage}
    # Selbstkontrolle: Spezifikationsregel erkennt genau die konstruierten Serien
    for s in stichtage:
        erkannt = {}
        for (name, richtung), eintr in _eintraege(umsaetze, D.fromisoformat(s)).items():
            r = _spec_erkennung(eintr)
            if r:
                erkannt[(name, richtung)] = (r[0], [u["umsatz_id"] for u in r[1]])
        soll = {(w["empfaenger"], w["richtung"]): (w["rhythmus"], w["umsatz_ids"]) for w in wahr[s]}
        assert erkannt == soll, (s, set(erkannt) ^ set(soll))

    # ---------------- Benachrichtigungen im wöchentlichen Abruf ab PROGRESSION_START
    abrufe = []
    h = PROGRESSION_START + dt.timedelta(days=7)
    while h <= D(2024, 12, 31):
        abrufe.append(h.isoformat())
        h += dt.timedelta(days=7)
    if abrufe[-1] != "2024-12-31":
        abrufe.append("2024-12-31")
    erwartet = [
        {"art": "neuer_empfaenger", "empfaenger": "Handwerker Hammer (fiktiv)", "umsatz_id": handwerker},
        {"art": "neuer_empfaenger", "empfaenger": "Neuer Dienst Wolke (fiktiv)",
         "umsatz_id": next(u for u, (n, i) in serie_von.items() if n == "Neuer Dienst Wolke (fiktiv)" and i == 22)},
    ]
    for name, ab in (("Wohnbau Fiktiva eG", (2024, 9)), ("Fiktiv-Stream GmbH", (2024, 10)),
                     ("Fiktiva Haftpflicht AG", (2024, 10))):
        uid = min((u for u, (n, _) in serie_von.items() if n == name
                   and (D.fromisoformat(nach_uid[u]["buchungstag"]).year,
                        D.fromisoformat(nach_uid[u]["buchungstag"]).month) >= ab),
                  key=lambda u: nach_uid[u]["buchungstag"])
        erwartet.append({"art": "wiederkehrend_betrag", "empfaenger": name, "umsatz_id": uid})
    fitness = [s for s in serien if s["name"] == "Studio Muskelkater (fiktiv)"][0]
    f = monat_plus(fitness["termine"][-1][1], 1)
    erwartet.append({"art": "wiederkehrend_ausbleibend", "empfaenger": fitness["name"], "richtung": "ausgabe",
                     "naechste_faelligkeit": f.isoformat(),
                     "erster_abruf": min(a for a in abrufe if D.fromisoformat(a) > f + dt.timedelta(days=TOLERANZ))})
    # Selbstkontrolle der Ausbleibend-Ereignisse über alle Abrufe mit der Spezifikationsregel
    gefunden = set()
    for a in abrufe:
        for w in wahrheit(D.fromisoformat(a)):
            if w["status"] == "ausbleibend":
                gefunden.add((w["empfaenger"], w["naechste_faelligkeit"]))
    assert gefunden == {(fitness["name"], f.isoformat())}, gefunden
    mock = {"format": "kontor-mock-daten", "version": 1, "bank": {"konten": [
        {"iban": W_GIRO, "bic": "TESTDEFFXXX", "name": "Girokonto", "art": "girokonto",
         "inhaber": "Erika Mustermann (fiktiv)", "waehrung": "EUR"}], "umsaetze": umsaetze},
        "mail": {"postfaecher": ["haushalt.eins@example.invalid"], "nachrichten": []}}
    erw = {"beschreibung": "Wiederkehrende Buchungen (wiederkehrend.md). 'serien' je Stichtag (Abruf des ganzen "
                           "Zeitraums 2023-01-01 bis 2024-12-31 vorher), sortiert nach Empfängername; umsatz_ids = "
                           "Kette. 'progression': Erstabruf bis progression_start mit von 2023-01-01, dann Abrufe zu "
                           "den Tagen in 'abrufe' (mock-Zeit 12:00Z) mit wiederkehrend_automatisch; genau die "
                           "Benachrichtigungen in 'benachrichtigungen' entstehen.",
           "iban": W_GIRO, "von": "2023-01-01", "bis": "2024-12-31", "toleranz_tage": TOLERANZ,
           "serien": wahr, "nicht_wiederkehrend": ["Supermarkt Frischekorb", "Baumarkt Fiktiv",
                                                    "Handwerker Hammer (fiktiv)", "Fiktive Krankenkasse"],
           "einnahme_neuer_zahler": erstattung,
           "progression": {"progression_start": PROGRESSION_START.isoformat(), "abrufe": abrufe,
                           "benachrichtigungen": erwartet},
           "feiertage": {str(j): sorted(d.isoformat() for d in feiertage(j)) for j in (2023, 2024)}}
    return {"mock": mock, "erwartung": erw}


# ================================================================ Berichte und Export (standard.kmy)

def _stichtage(von: dt.date, bis: dt.date, intervall: str) -> list[dt.date]:
    aus = [von]
    d = von + dt.timedelta(days=1)
    while d < bis:
        ende = {"tag": True, "woche": d.weekday() == 6, "monat": (d + dt.timedelta(days=1)).day == 1,
                "jahr": (d.month, d.day) == (12, 31)}[intervall]
        if ende:
            aus.append(d)
        d += dt.timedelta(days=1)
    if bis > von:
        aus.append(bis)
    return aus


def _perioden(von: dt.date, bis: dt.date, intervall: str) -> list[tuple[dt.date, dt.date]]:
    aus = []
    a = von
    while a <= bis:
        e = a
        while e < bis:
            ende = {"tag": True, "woche": e.weekday() == 6, "monat": (e + dt.timedelta(days=1)).day == 1,
                    "jahr": (e.month, e.day) == (12, 31)}[intervall]
            if ende:
                break
            e += dt.timedelta(days=1)
        aus.append((a, e))
        a = e + dt.timedelta(days=1)
    return aus


def berichtsdaten(std_erw: dict) -> dict:
    art = {k["extern_id"]: k["art"] for k in std_erw["konten"]}
    bestand = [k["extern_id"] for k in std_erw["konten"] if k["art"] in ("girokonto", "sparkonto", "kreditkonto")]
    buchungen = std_erw["buchungen"]

    def saldo(konto: str, stichtag: dt.date) -> int:
        s = stichtag.isoformat()
        return sum(sp["betrag"] for b in buchungen if b["datum"] <= s for sp in b["splits"]
                   if sp["konto_extern_id"] == konto)

    def kontostand(von, bis, intervall, konten):
        st = _stichtage(D.fromisoformat(von), D.fromisoformat(bis), intervall)
        return {"von": von, "bis": bis, "intervall": intervall, "konten": konten,
                "stichtage": [d.isoformat() for d in st],
                "werte": {k: [saldo(k, d) for d in st] for k in konten}}

    def ea(von, bis, intervall, konten=None):
        per = _perioden(D.fromisoformat(von), D.fromisoformat(bis), intervall)
        auswahl = [b for b in buchungen if von <= b["datum"] <= bis and (
            konten is None or any(sp["konto_extern_id"] in konten for sp in b["splits"]))]
        perioden = []
        kat: dict[str, int] = {}
        for a, e in per:
            ein = aus = 0
            for b in auswahl:
                if a.isoformat() <= b["datum"] <= e.isoformat():
                    for sp in b["splits"]:
                        if art[sp["konto_extern_id"]] == "ertrag":
                            ein -= sp["betrag"]
                        elif art[sp["konto_extern_id"]] == "aufwand":
                            aus += sp["betrag"]
            perioden.append({"von": a.isoformat(), "bis": e.isoformat(), "einnahmen": ein, "ausgaben": aus,
                             "saldo": ein - aus, "nicht_kategorisiert": 0})
        for b in auswahl:
            for sp in b["splits"]:
                if art[sp["konto_extern_id"]] in ("aufwand", "ertrag"):
                    kat[sp["konto_extern_id"]] = kat.get(sp["konto_extern_id"], 0) + sp["betrag"]
        gesamt = {f: sum(p[f] for p in perioden) for f in ("einnahmen", "ausgaben", "saldo", "nicht_kategorisiert")}
        return {"von": von, "bis": bis, "intervall": intervall, "konten": konten, "perioden": perioden,
                "gesamt": gesamt, "kategorien": dict(sorted(kat.items()))}

    giro = "kmy:A000001"
    reihenfolge = sorted(range(len(buchungen)), key=lambda i: (buchungen[i]["datum"], i))
    export_filter = {"konto": giro, "von": "2023-03-01", "bis": "2023-03-31"}
    export = [buchungen[i]["extern_id"] for i in reihenfolge
              if export_filter["von"] <= buchungen[i]["datum"] <= export_filter["bis"]
              and any(sp["konto_extern_id"] == giro for sp in buchungen[i]["splits"])]
    return {
        "beschreibung": "Berichte (berichte.md 2, 3) nach Import von kmy/standard.kmy in ein leeres Buch, aus dem "
                        "Modell des Generators; Konten über extern_id. Export: Reihenfolge der Buchungen (extern_id) "
                        "für den Filter in export.filter (Sortierung datum, Gleichstand Importreihenfolge).",
        "fixture": "kmy/standard.kmy",
        "kontostand": [
            kontostand("2022-01-01", "2024-12-31", "monat", bestand),
            kontostand("2024-02-20", "2024-03-05", "tag", [giro]),
            kontostand("2023-12-27", "2024-01-31", "woche", bestand),
            kontostand("2021-06-01", "2022-01-15", "jahr", bestand),
        ],
        "einnahmen_ausgaben": [
            ea("2022-01-01", "2024-12-31", "monat"),
            ea("2023-01-01", "2023-12-31", "jahr", [giro]),
            ea("2024-02-26", "2024-03-10", "woche"),
        ],
        "umbuchungen_anzahl": len(std_erw["umbuchungen"]),
        "export": {"filter": export_filter, "extern_ids": export},
    }


# ================================================================ alles

def erzeuge_m5(startwert: int, std_erw: dict) -> tuple[dict[str, object], dict[str, str]]:
    d: dict[str, object] = {}
    besch: dict[str, str] = {}
    d["m5/kredite.json"] = {**kreditfaelle(), "startwert": startwert}
    besch["m5/kredite.json"] = ("M5: Kreditfälle (30/360, act/360, act/365, Schaltjahr, Monatsende, gebrochene erste "
                                "Periode, Sondertilgungen, Zins 0, zu kleine Rate) mit unabhängig berechnetem Plan")
    k = kreditdaten(startwert)
    d["mock/m5_kredit.json"] = k["mock"]
    besch["mock/m5_kredit.json"] = ("M5: Girokonto 2024 mit Darlehensraten (verschoben auf Werktage), Sondertilgung, "
                                    "gleich hoher Zahlung an Fremde, Gebühr, anderem Darlehen")
    k["erwartung"]["startwert"] = startwert
    d["mock/m5_kredit.erwartung.json"] = k["erwartung"]
    besch["mock/m5_kredit.erwartung.json"] = ("M5: Aufteilung jeder Rate je Zinsmethode, Jahresauszüge 2024 mit "
                                              "Abweichungen und erwarteter Korrekturbuchung")
    w = wiederkehrenddaten(startwert)
    d["mock/m5_wiederkehrend.json"] = w["mock"]
    besch["mock/m5_wiederkehrend.json"] = ("M5: Girokonto 2023–2024 mit Abos, Daueraufträgen, Lastschriften, "
                                           "Verschiebungen, Betragsänderungen, Lücke, ausbleibender Zahlung, neuen "
                                           "Empfängern")
    w["erwartung"]["startwert"] = startwert
    d["mock/m5_wiederkehrend.erwartung.json"] = w["erwartung"]
    besch["mock/m5_wiederkehrend.erwartung.json"] = ("M5: Serien je Stichtag und Benachrichtigungen im wöchentlichen "
                                                     "Abruf (bekannte Wahrheit aus der Konstruktion)")
    b = berichtsdaten(std_erw)
    b["startwert"] = startwert
    d["m5/berichte.erwartung.json"] = b
    besch["m5/berichte.erwartung.json"] = ("M5: Kontostandsverlauf, Einnahmen/Ausgaben und Exportreihenfolge für "
                                           "kmy/standard.kmy")
    return d, besch
