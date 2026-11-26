/* Monatsbericht (Feature monatsbericht, D-206): Ausgaben eines Monats rein statistisch. Liest nur GET /api/berichte/monat. */
import { aktion, api, betragEl, betragText, datumText, h, oberflaeche, stamm, tagHolen } from "./kern.js";
import { centAchse, plotlyLayout } from "./seiten.js";
import {
  MONATE_KURZ, MONAT_MUSTER, RHYTHMUS, WOCHENTAGE, WOCHENTAGE_KURZ, abweichung, balken, berichtRahmen, diagrammEl, empfName, euroKurz,
  freieAchse, kachel, karte, klickbareZeilen, kontenAus, kontenFehler, kontenText, kontenWahl, leer, mehrzahl, mitBetrag, monatPlus,
  monatText, monatsWahl, prozent, tagKurz, zeichnen,
} from "./berichtsteile.js";

function klassenText(k) {
  if (k.unter === null) return `ab ${euroKurz(k.ab)}`;
  return k.ab ? `${euroKurz(k.ab)} bis unter ${euroKurz(k.unter)}` : `unter ${euroKurz(k.unter)}`;
}


function kacheln(b) {
  const kz = b.kennzahlen;
  const v = b.verlauf;
  // Im laufenden Monat fair vergleichen: mit dem Stand der anderen Monate am selben Tag
  const i = Math.max(v.bis_tag, 1) - 1;
  const vor = b.laufend ? (v.vormonat ? v.vormonat[i] : null) : kz.vormonat;
  const schnitt = b.laufend ? (v.durchschnitt ? v.durchschnitt[i] : null) : kz.durchschnitt_monate;
  const zumTag = b.laufend ? " am selben Tag" : "";
  const aus = [kachel("mb-kachel-ausgaben", "Ausgaben", betragEl("span", kz.ausgaben),
    abweichung(kz.ausgaben, vor, `im Vormonat${zumTag}`), abweichung(kz.ausgaben, schnitt, `im Schnitt${zumTag}`),
    kz.erstattungen ? h("span", null, `darin ${betragText(kz.erstattungen)} Erstattungen verrechnet`) : null)];
  if (b.prognose) {
    const p = b.prognose;
    aus.push(kachel("mb-kachel-prognose", "Hochrechnung zum Monatsende", betragEl("span", p.summe),
      h("span", null, `noch ${mehrzahl(p.resttage, "Tag", "Tage")}`),
      p.fix_offen ? h("span", null, `${betragText(p.fix_offen)} feste Zahlungen stehen aus`) : null,
      h("span", null, `${betragText(p.variabel_pro_tag)} variabel je Tag angenommen`)));
  } else {
    aus.push(kachel("mb-kachel-protag", "Ausgaben je Tag", betragEl("span", kz.pro_tag),
      h("span", null, `über ${mehrzahl(v.bis_tag, "Tag", "Tage")}`)));
  }
  aus.push(kachel("mb-kachel-einnahmen", "Einnahmen", betragEl("span", kz.einnahmen)));
  aus.push(kachel("mb-kachel-saldo", "Übrig", betragEl("span", kz.saldo),
    kz.sparquote_promille === null ? h("span", null, "keine Einnahmen im Monat")
      : h("span", null, `${Math.round(kz.sparquote_promille / 10)} % der Einnahmen`)));
  aus.push(kachel("mb-kachel-buchungen", "Buchungen", String(kz.anzahl),
    kz.anzahl ? h("span", null, `Median ${betragText(kz.median)}`) : null,
    kz.anzahl ? h("span", null, `Durchschnitt ${betragText(kz.durchschnitt)}`) : null));
  return h("div", { class: "mb-kacheln", tid: "mb-kacheln" }, aus);
}


async function verlaufZeichnen(el, b, f, beiTag) {
  const v = b.verlauf;
  const tage = Array.from({ length: v.tage }, (_, i) => i + 1);
  const spuren = [];
  if (v.durchschnitt) {
    spuren.push({ type: "scatter", mode: "lines", name: `Schnitt der letzten ${mehrzahl(v.durchschnitt_monate, "Monat", "Monate")}`,
      x: tage, y: v.durchschnitt, line: { color: f.text2, width: 1.5, dash: "dot", shape: "hv" },
      customdata: v.durchschnitt.map((w) => betragText(w)), hovertemplate: mitBetrag("Schnitt") });
  }
  if (v.vormonat) {
    const name = monatText(monatPlus(b.monat, -1));
    spuren.push({ type: "scatter", mode: "lines", name, x: tage, y: v.vormonat, line: { color: f.variabel, width: 1.5, shape: "hv" },
      customdata: v.vormonat.map((w) => betragText(w)), hovertemplate: mitBetrag(name) });
  }
  if (v.kumuliert.length) {
    const name = monatText(b.monat);
    spuren.push({ type: "scatter", mode: "lines", name, x: tage.slice(0, v.bis_tag), y: v.kumuliert,
      line: { color: f.fix, width: 3, shape: "hv" }, customdata: v.kumuliert.map((w) => betragText(w)), hovertemplate: mitBetrag(name) });
  }
  if (b.prognose && v.kumuliert.length) {
    const start = v.kumuliert[v.kumuliert.length - 1];
    spuren.push({ type: "scatter", mode: "lines+markers", name: "Hochrechnung", x: [v.bis_tag, v.tage], y: [start, b.prognose.summe],
      line: { color: f.fix, width: 2, dash: "dash" }, marker: { size: [0, 8], color: f.fix },
      customdata: [betragText(start), betragText(b.prognose.summe)], hovertemplate: mitBetrag("Hochrechnung") });
  }
  if (!spuren.length) { el.replaceChildren(leer("Noch keine Ausgaben in diesem Monat.")); return; }
  const achse = centAchse(spuren.flatMap((s) => s.y));
  const plot = await zeichnen(el, spuren, plotlyLayout(f, achse, {
    xaxis: { type: "linear", range: [0.5, v.tage + 0.5], dtick: v.tage > 16 ? 5 : 1, tick0: 5, ticksuffix: ".", gridcolor: f.rand,
      linecolor: f.rand, fixedrange: true, hoverformat: "d" },
    height: 300, margin: { l: 96, r: 12, t: 30, b: 34 } }));
  if (plot) plot.on("plotly_click", (ev) => { if (ev.points && ev.points.length) beiTag(Number(ev.points[0].x)); });
}

async function monateZeichnen(el, b, f, beiMonat) {
  const ms = b.monate;
  const x = ms.map((m) => `${MONATE_KURZ[Number(m.monat.slice(5)) - 1]}<br>${m.monat.slice(0, 4)}`);
  const stark = ms.map((m) => (m.monat === b.monat ? 1 : 0.55));
  const balkenSpur = (name, feld, farbe) => ({ type: "bar", name, x, y: ms.map((m) => m[feld]), marker: { color: farbe, opacity: stark },
    customdata: ms.map((m) => betragText(m[feld])), hovertemplate: mitBetrag(name) });
  const spuren = [balkenSpur("Fest", "fix", f.fix), balkenSpur("Variabel", "variabel", f.variabel)];
  const schnitt = b.kennzahlen.durchschnitt_monate;
  if (schnitt !== null) {
    spuren.push({ type: "scatter", mode: "lines", name: "Schnitt der Vormonate", x, y: ms.map(() => schnitt),
      line: { color: f.text2, width: 1.5, dash: "dot" }, customdata: ms.map(() => betragText(schnitt)), hovertemplate: mitBetrag("Schnitt der Vormonate") });
  }
  const achse = centAchse(ms.flatMap((m) => [m.ausgaben, m.fix, m.variabel]));
  // schmal (Handy): nur jeden dritten Monat beschriften, vom gewählten Monat rückwärts
  const schmal = el.clientWidth < 520;
  const marken = schmal ? x.filter((_, i) => (x.length - 1 - i) % 3 === 0) : x;
  const plot = await zeichnen(el, spuren, plotlyLayout(f, achse, { barmode: "relative", bargap: 0.25,
    xaxis: { type: "category", linecolor: f.rand, fixedrange: true, tickangle: 0, tickfont: { size: 11 }, tickmode: "array", tickvals: marken }, height: 300, margin: { l: 96, r: 12, t: 30, b: 44 } }));
  if (plot) {
    plot.on("plotly_click", (ev) => { if (ev.points && ev.points.length) beiMonat(ms[ev.points[0].pointIndex].monat); });
    plot.classList.add("mb-klickbar");
  }
}

async function kontostandZeichnen(el, b, f) {
  const k = b.kontostand;
  if (k.werte.length < 2) { el.replaceChildren(leer("Zu wenige Tage für einen Verlauf.")); return; }
  const tief = k.tiefststand;
  const spuren = [
    { type: "scatter", mode: "lines", name: "Kontostand", x: k.tage, y: k.werte, line: { color: f.fix, width: 2.5, shape: "hv" },
      customdata: k.werte.map((w) => betragText(w)), hovertemplate: mitBetrag("Kontostand") },
    { type: "scatter", mode: "markers", name: "Tiefststand", x: [tief.datum], y: [tief.betrag], marker: { color: f.gefahr, size: 10, symbol: "diamond" },
      customdata: [betragText(tief.betrag)], hovertemplate: mitBetrag("Tiefststand") },
  ];
  await zeichnen(el, spuren, plotlyLayout(f, freieAchse(k.werte), {
    xaxis: { type: "date", gridcolor: f.rand, linecolor: f.rand, tickformat: "%d.%m.", hoverformat: "%d.%m.%Y", fixedrange: true,
      range: [`${b.von} 00:00`, `${b.bis} 23:59`] },
    height: 260, margin: { l: 96, r: 12, t: 30, b: 34 } }));
}

// ------------------------------------------------------------------ Karten
function karteFixVariabel(b, zeigen) {
  const fv = b.fix_variabel;
  const variabel = Math.max(fv.variabel, 0);
  const ganz = fv.fix + variabel;
  const teil = (tid, name, klasse, summe, anzahl, liste) => h("button", { type: "button", class: `mb-teil ${klasse}`, tid,
    onclick: (ev) => zeigen(`${name}e Ausgaben`, liste, ev.currentTarget) },
  h("span", { class: "mb-teil-name" }, h("span", { class: "mb-punkt", "aria-hidden": "true" }), name),
  h("strong", null, betragText(summe)), h("span", { class: "klein" }, `${prozent(Math.max(summe, 0), ganz)} % · ${mehrzahl(anzahl, "Buchung", "Buchungen")}`));
  const fix = b.buchungen.filter((e) => e.fix);
  const rest = b.buchungen.filter((e) => !e.fix);
  const erwartet = fv.erwartet.length ? h("div", { tid: "mb-erwartet" }, h("h3", null, "Steht bis Monatsende noch aus"),
    h("ul", { class: "mb-liste" }, fv.erwartet.map((e) => h("li", null, h("span", null, `${tagKurz(e.faellig)} ${empfName(e.empfaenger)}`,
      h("span", { class: "klein" }, ` · ${RHYTHMUS[e.rhythmus] || e.rhythmus}`)), betragEl("span", -e.betrag))))) : null;
  return karte("mb-fix-variabel", "Fest und variabel",
    "Fest ist, was als wiederkehrende Zahlung erkannt wurde. Nur der variable Teil lässt sich kurzfristig beeinflussen.",
    ganz > 0 ? h("div", { class: "mb-anteil", role: "img", "aria-label": `Fest ${prozent(fv.fix, ganz)} Prozent, variabel ${prozent(variabel, ganz)} Prozent` },
      h("span", { class: "mb-anteil-fix", stil: { "--w": `${prozent(fv.fix, ganz)}%` } }),
      h("span", { class: "mb-anteil-variabel", stil: { "--w": `${100 - prozent(fv.fix, ganz)}%` } })) : null,
    h("div", { class: "mb-teile" }, teil("mb-teil-fix", "Fest", "mb-fix", fv.fix, fv.fix_anzahl, fix),
      teil("mb-teil-variabel", "Variabel", "mb-variabel", fv.variabel, fv.variabel_anzahl, rest)), erwartet);
}

function karteKlassen(b, zeigen) {
  const kl = b.groessenklassen;
  const anzahl = kl.reduce((n, k) => n + k.anzahl, 0);
  const summe = kl.reduce((n, k) => n + k.summe, 0);
  const zeilen = kl.map((k) => h("tr", { class: "klickbar", tid: `mb-klasse-${k.klasse}`, tabindex: "0", role: "button",
    "aria-label": `${klassenText(k)}: ${mehrzahl(k.anzahl, "Buchung", "Buchungen")}, ${betragText(k.summe)}. Buchungen zeigen`,
    "data-klasse": String(k.klasse) },
  h("th", { scope: "row" }, klassenText(k)),
  h("td", null, h("span", { class: "mb-doppel" }, balken(prozent(k.anzahl, anzahl), "mb-fuell-anzahl"), balken(prozent(k.summe, summe), "mb-fuell-summe"))),
  h("td", { class: "zahl" }, String(k.anzahl), h("span", { class: "klein" }, ` · ${prozent(k.anzahl, anzahl)} %`)),
  h("td", { class: "zahl" }, betragText(k.summe), h("span", { class: "klein" }, ` · ${prozent(k.summe, summe)} %`))));
  const t = h("table", { class: "tabelle mb-tabelle" }, h("thead", null, h("tr", null, h("th", { scope: "col" }, "Betrag je Buchung"),
    h("th", { scope: "col" }, h("span", { class: "mb-legende" }, h("span", { class: "mb-punkt mb-fuell-anzahl" }), "Anzahl ",
      h("span", { class: "mb-punkt mb-fuell-summe" }), "Summe")),
    h("th", { scope: "col", class: "zahl" }, "Buchungen"), h("th", { scope: "col", class: "zahl" }, "Summe"))), h("tbody", null, zeilen));
  klickbareZeilen(t, (tr, ziel) => {
    const k = kl[Number(tr.dataset.klasse)];
    zeigen(`Buchungen ${klassenText(k)}`, b.buchungen.filter((e) => e.art === "ausgabe" && e.klasse === k.klasse), ziel);
  });
  return karte("mb-klassen", "Kleine und große Beträge",
    "Viele kleine Buchungen oder wenige große? Der obere Balken zeigt den Anteil an der Anzahl, der untere den Anteil an der Summe.", t);
}


export function karteTopBuchungen(b) {
  const top = b.top_buchungen;
  if (!top.eintraege.length) return karte("mb-top-buchungen", "Größte Buchungen", null, leer("Keine Ausgaben."));
  const max = top.eintraege[0].betrag;
  const zeilen = top.eintraege.map((e) => h("tr", { class: "klickbar", tid: `mb-top-buchung-${e.id}`, tabindex: "0", role: "button",
    "aria-label": `${empfName(e.empfaenger)}, ${datumText(e.datum)}, ${betragText(e.betrag)}. Im Konto zeigen`, "data-id": String(e.id) },
  h("td", null, tagKurz(e.datum)),
  h("td", null, h("span", { class: "mb-name" }, empfName(e.empfaenger), e.fix ? h("span", { class: "mb-marke mb-marke-fix" }, "fest") : null),
    e.verwendungszweck ? h("span", { class: "klein mb-zweck" }, e.verwendungszweck) : null),
  h("td", null, balken(prozent(e.betrag, max), e.fix ? "mb-fuell-fix" : "mb-fuell-variabel")),
  betragEl("td", -e.betrag, { class: "zahl" })));
  const t = h("table", { class: "tabelle mb-tabelle" }, h("thead", null, h("tr", null, h("th", { scope: "col" }, "Tag"),
    h("th", { scope: "col" }, "Empfänger"), h("th", { scope: "col" }, h("span", { class: "nur-vorleser" }, "Größe")),
    h("th", { scope: "col", class: "zahl" }, "Betrag"))), h("tbody", null, zeilen));
  klickbareZeilen(t, (tr) => {
    const e = top.eintraege.find((x) => String(x.id) === tr.dataset.id);
    oberflaeche.zurBuchung(e.konto_id, e.id);
  });
  return karte("mb-top-buchungen", "Größte Buchungen",
    `Die ${top.eintraege.length === 1 ? "größte Buchung macht" : `${top.eintraege.length} größten Buchungen machen`} ${prozent(top.summe, top.gesamt)} % der Ausgaben aus. Ein Klick zeigt die Buchung im Konto.`, t);
}

function karteEmpfaenger(b, zeigen) {
  const liste = b.top_empfaenger;
  if (!liste.length) return karte("mb-empfaenger", "Wohin das Geld ging", null, leer("Keine Ausgaben."));
  const max = liste[0].summe;
  const gesamt = b.top_buchungen.gesamt;
  const zeilen = liste.map((e, i) => {
    const mehr = e.ueblich !== null && e.ueblich > 0 ? e.summe - e.ueblich : null;
    const vergleich = e.ueblich === null ? "" : e.ueblich === 0 ? h("span", { class: "mb-marke" }, "neu")
      : h("span", { class: `mb-delta mb-${mehr > 0 ? "mehr" : mehr < 0 ? "weniger" : "gleich"}`, title: `Üblich je Monat: ${betragText(e.ueblich)}` },
        `${mehr > 0 ? "▲" : mehr < 0 ? "▼" : "●"} ${betragText(Math.abs(mehr))}`);
    return h("tr", { class: "klickbar", tid: `mb-empfaenger-${i}`, tabindex: "0", role: "button", "data-nr": String(i),
      "aria-label": `${empfName(e.empfaenger)}: ${mehrzahl(e.anzahl, "Buchung", "Buchungen")}, ${betragText(e.summe)}. Buchungen zeigen` },
    h("td", null, h("span", { class: "mb-name" }, empfName(e.empfaenger)), h("span", { class: "klein" }, mehrzahl(e.anzahl, "Buchung", "Buchungen"))),
    h("td", null, balken(prozent(e.summe, max), "mb-fuell-fix")),
    h("td", { class: "zahl" }, betragText(e.summe), h("span", { class: "klein" }, ` · ${prozent(e.summe, gesamt)} %`)),
    h("td", { class: "zahl" }, vergleich));
  });
  const t = h("table", { class: "tabelle mb-tabelle" }, h("thead", null, h("tr", null, h("th", { scope: "col" }, "Empfänger"),
    h("th", { scope: "col" }, h("span", { class: "nur-vorleser" }, "Größe")), h("th", { scope: "col", class: "zahl" }, "Summe"),
    h("th", { scope: "col", class: "zahl", title: "Gegenüber dem Monatsschnitt der letzten sechs Monate" }, "ggü. üblich"))), h("tbody", null, zeilen));
  klickbareZeilen(t, (tr, ziel) => {
    const e = liste[Number(tr.dataset.nr)];
    const id = e.empfaenger ? e.empfaenger.id : null;
    zeigen(`Ausgaben an ${empfName(e.empfaenger)}`, b.buchungen.filter((x) => x.art === "ausgabe" && (x.empfaenger ? x.empfaenger.id : null) === id), ziel);
  });
  const mehrText = b.empfaenger_anzahl > liste.length ? ` Gezeigt sind die ${liste.length} größten von ${b.empfaenger_anzahl}.` : "";
  return karte("mb-empfaenger", "Wohin das Geld ging", `Summe je Empfänger, verglichen mit dem, was dort sonst im Monat üblich ist.${mehrText}`, t);
}

async function alsSonderposten(id) {
  try {
    await aktion(async () => {
      const t = await tagHolen("Sonderposten", (n) => stamm.tags.find((x) => x.name.toLowerCase() === n.toLowerCase()));
      return api("POST", "/api/buchungen/mehrfach/tags", { buchung_ids: [id], hinzufuegen: [t.id], entfernen: [] });
    }, { erfolg: "Als Sonderposten markiert: zählt in den Berichten nicht mit." });
  } catch (e) { /* gemeldet */ }
}

function karteAuffaellig(b, zeigen) {
  const a = b.auffaellig;
  const punkte = [];
  const eintrag = (art, zeichen, tid, text, aktion) => h("li", { class: `mb-auffaellig mb-auf-${art}` },
    h("span", { class: "mb-zeichen", "aria-hidden": "true" }, zeichen),
    h("button", { type: "button", class: "knopf-link", tid, onclick: (ev) => aktion(ev.currentTarget) }, text));
  for (const x of a.ausreisser) {
    const e = x.buchung;
    punkte.push(eintrag("hoch", "▲", `mb-ausreisser-${e.id}`,
      `${empfName(e.empfaenger)}: ${betragText(e.betrag)} am ${tagKurz(e.datum)} – üblich sind dort ${betragText(x.ueblich)}`,
      () => oberflaeche.zurBuchung(e.konto_id, e.id)));
  }
  // D-300: sehr große einzelne Ausgaben – als Sonderposten markieren?
  for (const x of a.sonderposten || []) {
    const e = x.buchung;
    punkte.push(h("li", { class: "mb-auffaellig mb-auf-hoch", tid: `mb-sonderposten-vorschlag-${e.id}` },
      h("span", { class: "mb-zeichen", "aria-hidden": "true" }, "★"),
      h("button", { type: "button", class: "knopf-link", onclick: () => oberflaeche.zurBuchung(e.konto_id, e.id) },
        `${empfName(e.empfaenger)}: ${betragText(e.betrag)} am ${tagKurz(e.datum)}` +
        (x.ueblich_monat ? ` – mehr als die Hälfte der üblichen Monatsausgaben (${betragText(x.ueblich_monat)})` : " – eine sehr große Einzelausgabe")),
      " ",
      h("button", { type: "button", class: "knopf knopf-klein", tid: `mb-sonderposten-markieren-${e.id}`,
        title: "Mit dem Tag „Sonderposten“ versehen: zählt in den Berichten dann nur mit dem Schalter mit",
        onclick: () => alsSonderposten(e.id) }, "Als Sonderposten markieren")));
  }
  for (const s of a.serien) {
    const name = `${empfName(s.empfaenger)} (${RHYTHMUS[s.rhythmus] || s.rhythmus})`;
    if (s.art === "betrag_geaendert") {
      punkte.push(eintrag(s.betrag > s.vorher ? "hoch" : "tief", s.betrag > s.vorher ? "▲" : "▼", `mb-serie-${s.buchung_id}`,
        `${name}: jetzt ${betragText(s.betrag)} statt ${betragText(s.vorher)}`, () => oberflaeche.zurBuchung(s.konto_id, s.buchung_id)));
    } else {
      punkte.push(eintrag("fehlt", "○", `mb-serie-${s.buchung_id}`,
        `${name}: die Zahlung von etwa ${betragText(s.betrag)} war am ${tagKurz(s.faellig)} fällig und fehlt bisher`,
        () => oberflaeche.zurBuchung(s.konto_id, s.buchung_id)));
    }
  }
  for (const n of a.neue_empfaenger) {
    punkte.push(eintrag("neu", "＋", `mb-neu-${n.empfaenger.id}`,
      `Neu: ${empfName(n.empfaenger)} – ${betragText(n.summe)} in ${mehrzahl(n.anzahl, "Buchung", "Buchungen")}`,
      (ziel) => zeigen(`Ausgaben an ${empfName(n.empfaenger)}`, b.buchungen.filter((x) => x.empfaenger && x.empfaenger.id === n.empfaenger.id), ziel)));
  }
  return karte("mb-auffaellig", "Auffälligkeiten",
    "Ungewöhnlich hohe Beträge, geänderte oder ausgebliebene Daueraufträge und Empfänger, die es in den zwölf Monaten davor nicht gab.",
    punkte.length ? h("ul", { class: "mb-liste mb-auffaellig-liste" }, punkte) : leer("Nichts Auffälliges in diesem Monat."));
}

function karteKalender(b, zeigen) {
  const kal = b.kalender;
  const max = Math.max(1, ...kal.map((k) => k.summe));
  const stufe = (s) => (s <= 0 ? 0 : Math.min(4, 1 + Math.floor(Math.sqrt(s / max) * 3.999)));
  const zellen = Array.from({ length: kal[0].wochentag }, () => h("td", { class: "mb-kal-leer" }));
  for (const k of kal) {
    const tag = Number(k.datum.slice(8));
    const spaeter = b.zukunft || k.datum > b.stichtag;
    const text = `${WOCHENTAGE[k.wochentag]}, ${datumText(k.datum)}: ${k.anzahl ? `${mehrzahl(k.anzahl, "Buchung", "Buchungen")}, ${betragText(k.summe)}` : "keine Ausgaben"}`;
    zellen.push(h("td", null, h("button", { type: "button", class: `mb-kal-tag mb-hitze-${stufe(k.summe)}${spaeter ? " mb-kal-spaeter" : ""}${b.laufend && k.datum === b.stichtag ? " mb-kal-heute" : ""}`,
      tid: `mb-tag-${k.datum}`, title: text, "aria-label": text, disabled: !k.anzahl, "data-betrag": String(k.summe),
      onclick: (ev) => zeigen(`Ausgaben am ${datumText(k.datum)}`, b.buchungen.filter((e) => e.datum === k.datum), ev.currentTarget) },
    h("span", { class: "mb-kal-nr" }, String(tag)), h("span", { class: "mb-kal-summe" }, k.anzahl ? euroKurz(k.summe) : ""))));
  }
  const wochen = [];
  for (let i = 0; i < zellen.length; i += 7) wochen.push(h("tr", null, zellen.slice(i, i + 7)));
  const tabelle = h("table", { class: "mb-kalender", tid: "mb-kalender" },
    h("thead", null, h("tr", null, WOCHENTAGE_KURZ.map((w, i) => h("th", { scope: "col", abbr: WOCHENTAGE[i] }, w)))), h("tbody", null, wochen));
  const maxTag = Math.max(1, ...b.wochentage.map((w) => w.pro_tag));
  const wochentage = h("table", { class: "tabelle mb-tabelle mb-wochentage", tid: "mb-wochentage" },
    h("thead", null, h("tr", null, h("th", { scope: "col" }, "Wochentag"), h("th", { scope: "col" }, h("span", { class: "nur-vorleser" }, "Größe")),
      h("th", { scope: "col", class: "zahl" }, "Schnitt je Tag"))),
    h("tbody", null, b.wochentage.map((w) => h("tr", { title: `${betragText(w.summe)} an ${mehrzahl(w.tage, "Tag", "Tagen")}` }, h("th", { scope: "row" }, WOCHENTAGE[w.wochentag]),
      h("td", null, balken(prozent(w.pro_tag, maxTag), "mb-fuell-fix")), betragEl("td", w.pro_tag, { class: "zahl" })))));
  return karte("mb-kalender-karte", "Wann ausgegeben wurde", "Je dunkler der Tag, desto mehr wurde ausgegeben. Ein Klick zeigt die Buchungen des Tages.",
    h("div", { class: "mb-kalender-rahmen" }, tabelle, wochentage));
}

// ------------------------------------------------------------------ Seite
export function monatsberichtSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    sonderposten: true, art: "monat", titel: "Monatsbericht", pfad: "/api/berichte/monat",
    lesen: (p) => ({ monat: MONAT_MUSTER.test(p.get("monat") || "") ? p.get("monat") : null, konten: kontenAus(p) }),
    anfrage: (z) => ({ monat: z.monat, konto_id: z.konten }),
    adresse: (z) => ({ monat: z.monat, konto: z.konten }),
    beiFehler: kontenFehler,
    steuerung: (b, k) => [monatsWahl(b, b.monat, (monat) => k.setzen({ monat })),
      kontenWahl(b.konten, k.zustand.konten, (konten) => k.setzen({ konten }), k.merker)],
    stand: (b) => {
      const umb = b.ausgeschlossen.umbuchungen;
      return [b.zukunft ? "Dieser Monat liegt in der Zukunft." : b.laufend ? `Laufender Monat, Stand ${datumText(b.stichtag)}.` : "Abgeschlossener Monat.",
        kontenText(b), umb ? ` ${mehrzahl(umb, "Umbuchung", "Umbuchungen")} zwischen eigenen Konten ${umb === 1 ? "zählt" : "zählen"} nicht mit.` : ""];
    },
    inhalt: (b, k) => {
      const zeigen = k.zeigen;
      k.verlauf = diagrammEl("mb-verlauf-diagramm", `Aufgelaufene Ausgaben im ${monatText(b.monat)} je Tag, im Vergleich zum Vormonat und zum Schnitt`);
      k.monate = diagrammEl("mb-monate-diagramm", "Ausgaben der letzten zwölf Monate, geteilt in fest und variabel");
      k.kontostand = diagrammEl("mb-kontostand-diagramm", `Kontostand im ${monatText(b.monat)}`);
      const tief = b.kontostand.tiefststand;
      const hatAusgaben = b.buchungen.length > 0;
      k.seite.dataset.monat = b.monat;
      return [
        !hatAusgaben && !b.zukunft ? h("p", { class: "leer", tid: "mb-leer" }, "In diesem Monat gibt es auf den gewählten Konten keine Ausgaben.") : null,
        kacheln(b),
        h("div", { class: "mb-raster" },
          h("div", { class: "mb-breit" }, karte("mb-verlauf", "Verlauf im Monat",
            "So sind die Ausgaben Tag für Tag aufgelaufen. Liegt die dicke Linie unter den anderen, wurde bisher weniger ausgegeben als sonst. Ein Klick auf einen Tag zeigt dessen Buchungen.", k.verlauf)),
          hatAusgaben ? karteFixVariabel(b, zeigen) : null,
          karte("mb-monate", "Die letzten zwölf Monate", "Ein Klick auf einen Balken öffnet den Monat.", k.monate),
          hatAusgaben ? karteTopBuchungen(b) : null,
          hatAusgaben ? karteEmpfaenger(b, zeigen) : null,
          hatAusgaben ? karteKlassen(b, zeigen) : null,
          b.zukunft ? null : karteAuffaellig(b, zeigen),
          hatAusgaben ? h("div", { class: "mb-breit" }, karteKalender(b, zeigen)) : null,
          h("div", { class: "mb-breit" }, karte("mb-kontostand", "Kontostand",
            tief ? `Tiefster Stand ${betragText(tief.betrag)} am ${datumText(tief.datum)}; Anfang ${betragText(b.kontostand.anfang)}, zuletzt ${betragText(b.kontostand.ende)}.` : null, k.kontostand)))];
    },
    danach: (b, k) => {
      const heuteMonat = b.heute.slice(0, 7);
      return Promise.all([
        verlaufZeichnen(k.verlauf, b, k.farben, (tag) => {
          const datum = `${b.monat}-${String(tag).padStart(2, "0")}`;
          const liste = b.buchungen.filter((e) => e.datum === datum);
          if (liste.length) k.zeigen(`Ausgaben am ${datumText(datum)}`, liste, null);
        }),
        monateZeichnen(k.monate, b, k.farben, (m) => { if (m !== b.monat) k.setzen({ monat: m === heuteMonat ? null : m }); }),
        kontostandZeichnen(k.kontostand, b, k.farben),
      ]);
    },
  });
}
