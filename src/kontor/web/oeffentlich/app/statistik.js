/* Experimentelle statistische Analyse (D-145). Liest nur GET /api/statistik. */
import { BESTAND, abfrage, api, betragEl, betragText, datumEl, h, kontoNach, oberflaeche, stamm } from "./kern.js";

const RHYTHMUS = {
  woechentlich: "wöchentlich", vierzehntaegig: "vierzehntägig", monatlich: "monatlich",
  vierteljaehrlich: "vierteljährlich", jaehrlich: "jährlich",
};
const STATUS = { regelmaessig: "regelmäßig", moeglich: "möglich", kandidat: "Kandidat" };
const GRUND = {
  zu_wenige: "zu wenige Abstände für eine feste Reihe",
  abstand_streut: "die Abstände streuen",
  betrag_streut: "die Beträge streuen",
  betrag: "Betrag weicht von der Reihe ab",
  luecke: "die Reihe ist überfällig",
  rauschen: "außerhalb des Kategorie-Rauschens",
  einzel: "einzeln und groß gegenüber dem übrigen Kontoblatt",
};

const euro = (cent) => betragText(cent);
const zText = (z) => (z === null || z === undefined ? "—" : (z / 100).toLocaleString("de-DE",
  { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

function tabelle(spalten, zeilen) {
  return h("table", { class: "tabelle" },
    h("thead", null, h("tr", null, spalten.map((s) => h("th", { scope: "col" }, s)))),
    h("tbody", null, zeilen));
}

function sprung(kontoId, buchungId, text) {
  return h("button", { type: "button", class: "knopf-flach",
    onclick: () => oberflaeche.zurBuchung(kontoId, buchungId) }, text);
}

export async function statistikSeite(seite, _param, suche) {
  const bestand = stamm.konten.filter((k) => BESTAND.has(k.art) && !k.geschlossen);
  const gewaehlt = new URLSearchParams(suche || "").get("konto");
  const kontoId = bestand.some((k) => String(k.id) === gewaehlt) ? Number(gewaehlt) : (bestand[0] && bestand[0].id);
  const auswahl = h("select", { tid: "statistik-konto", "aria-label": "Konto" },
    bestand.map((k) => h("option", { value: String(k.id), ...(k.id === kontoId ? { selected: "selected" } : {}) }, k.name)));
  auswahl.addEventListener("change", () => oberflaeche.gehe("/statistik" + abfrage({ konto: auswahl.value })));
  seite.append(h("div", { class: "seiten-kopf" }, h("h1", null, "Statistische Analyse"),
    h("div", { class: "werkzeuge" }, auswahl)));
  seite.append(h("p", { class: "hinweis-text" },
    "Experimentell. Regelmäßig heißt: der Abstand liegt stabil in einem Raster (Woche, zwei Wochen, Monat, "
    + "Quartal, Jahr) und der Betrag streut wenig. Die Jahresrate ist Medianbetrag mal 365 geteilt durch den "
    + "Medianabstand. Möglich und Kandidat zählen nicht in die Fixkosten. Umbuchungen und Tilgung ohne Zins bleiben draußen."));
  if (!kontoId) {
    seite.append(h("p", { class: "leer" }, "Kein Bestandskonto vorhanden."));
    return { titel: "Statistische Analyse" };
  }
  const a = await api("GET", "/api/statistik" + abfrage({ konto_id: kontoId }));
  const konto = kontoNach(a.konto.id);
  seite.append(abschnittFixkosten(a), abschnittReihen(a, konto.id), abschnittUngewoehnlich(a, konto.id),
    abschnittRauschen(a), abschnittAusgeschlossen(a));
  return { titel: "Statistische Analyse" };
}

function abschnittFixkosten(a) {
  const f = a.fixkosten;
  const zeilen = f.kategorien.map((k) => h("tr", null,
    h("td", null, k.kategorie ? k.kategorie.name : "Ohne Kategorie"),
    betragEl("td", k.jahresrate, { class: "zahl" }),
    betragEl("td", k.letzte_zwoelf_monate, { class: "zahl" }),
    h("td", null, k.reihen.join(", "))));
  return h("section", { class: "karte", tid: "statistik-fixkosten" },
    h("h2", null, "Fixkosten"),
    h("p", null, "Laufende Jahresrate ", h("strong", null, euro(f.summe_jahresrate)),
      ", in den letzten zwölf Monaten gebucht ", h("strong", null, euro(f.summe_letzte_zwoelf_monate)), "."),
    zeilen.length ? tabelle(["Kategorie", "Jahresrate", "Letzte zwölf Monate", "Reihen"], zeilen)
      : h("p", { class: "leer" }, "Keine regelmäßige Ausgabe erkannt."));
}

function abschnittReihen(a, kontoId) {
  const zeilen = a.reihen.map((r) => {
    const letzte = r.buchung_ids[r.buchung_ids.length - 1];
    return h("tr", { "data-status": r.status },
      h("td", null, r.bezeichnung),
      h("td", null, r.kategorie ? r.kategorie.name : "—"),
      h("td", null, RHYTHMUS[r.rhythmus] || r.rhythmus),
      h("td", null, STATUS[r.status] || r.status),
      betragEl("td", r.betrag_median, { class: "zahl" }),
      betragEl("td", r.jahresrate, { class: "zahl" }),
      h("td", { class: "zahl" }, String(r.abstand_median_tage)),
      h("td", null, r.grund ? (GRUND[r.grund] || r.grund) : "—"),
      h("td", null, sprung(kontoId, letzte, "Im Kontoblatt")));
  });
  return h("section", { class: "karte", tid: "statistik-reihen" },
    h("h2", null, "Was sich wiederholt"),
    zeilen.length ? tabelle(["Gegenpartei", "Kategorie", "Rhythmus", "Einordnung", "Median", "Jahresrate",
      "Abstand (Tage)", "Warum noch offen", ""], zeilen)
      : h("p", { class: "leer" }, "Keine Reihe mit mindestens drei Buchungen in einem bekannten Raster."));
}

function abschnittUngewoehnlich(a, kontoId) {
  const zeilen = a.ungewoehnlich.map((u) => h("tr", null,
    datumEl("td", u.datum),
    h("td", null, u.empfaenger || "—"),
    betragEl("td", u.betrag, { class: "zahl" }),
    h("td", null, GRUND[u.grund] || u.grund),
    h("td", null, u.basis),
    h("td", { class: "zahl" }, zText(u.z_hundertstel)),
    h("td", null, sprung(kontoId, u.buchung_id, "Zeigen"))));
  return h("section", { class: "karte", tid: "statistik-ungewoehnlich" },
    h("h2", null, "Ungewöhnlich"),
    zeilen.length ? tabelle(["Datum", "Empfänger", "Betrag", "Grund", "Basis", "robustes z", ""], zeilen)
      : h("p", { class: "leer" }, "Nichts weicht von seiner Basis ab."));
}

function abschnittRauschen(a) {
  const zeilen = a.rauschen.map((r) => h("tr", null,
    h("td", null, r.kategorie.name),
    h("td", { class: "zahl" }, String(r.anzahl_buchungen)),
    h("td", { class: "zahl" }, String(r.monate)),
    betragEl("td", r.median, { class: "zahl" }),
    h("td", null, euro(r.band_unten) + " – " + euro(r.band_oben) + (r.band_stabil ? "" : " (wenig Monate)"))));
  return h("section", { class: "karte", tid: "statistik-rauschen" },
    h("h2", null, "Bekanntes Rauschen"),
    h("p", null, "Monatssummen der Buchungen, die keiner Reihe angehören. Das Band ist das 10.- bis 90.-Perzentil."),
    zeilen.length ? tabelle(["Kategorie", "Buchungen", "Monate", "Median im Monat", "Band"], zeilen)
      : h("p", { class: "leer" }, "Kein Rest, der sich als Rauschen beschreiben lässt."));
}

function abschnittAusgeschlossen(a) {
  const x = a.ausgeschlossen;
  return h("section", { class: "karte", tid: "statistik-ausgeschlossen" },
    h("h2", null, "Nicht in der Analyse"),
    h("p", null, String(x.umbuchungen), " Umbuchungen (", euro(x.umbuchungen_summe), "), ",
      String(x.tilgung_ohne_zins), " Tilgungen ohne Zinsaufwand."));
}
