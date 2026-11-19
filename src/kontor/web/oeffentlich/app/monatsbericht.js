/* Monatsbericht (Feature monatsbericht, D-206): Ausgaben eines Monats rein statistisch. Liest nur GET /api/berichte/monat. */
import {
  BESTAND, abfrage, api, baumFolge, betragEl, betragText, datumEl, datumText, h, kontoNach, kontoPfad, mobilKarten,
  nameAnzeige, oberflaeche, stamm,
} from "./kern.js";
import { dialog } from "./ui.js";
import { PLOTLY_OPTIONEN, centAchse, farben, plotlyLaden, plotlyLayout } from "./seiten.js";

const MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
  "November", "Dezember"];
const MONATE_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
const WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
const WOCHENTAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const RHYTHMUS = { monatlich: "monatlich", vierteljaehrlich: "vierteljährlich", jaehrlich: "jährlich" };
const MONAT_MUSTER = /^\d{4}-(0[1-9]|1[0-2])$/;

const monatText = (m) => `${MONATE[Number(m.slice(5)) - 1]} ${m.slice(0, 4)}`;
function monatPlus(m, n) {
  const i = Number(m.slice(0, 4)) * 12 + Number(m.slice(5)) - 1 + n;
  return `${String(Math.floor(i / 12)).padStart(4, "0")}-${String((i % 12) + 1).padStart(2, "0")}`;
}
const tagKurz = (iso) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}.`;
const prozent = (teil, ganz) => (ganz > 0 ? Math.round((teil * 100) / ganz) : 0);
/** Ganze Euro ohne Cent für enge Stellen (Kalender); der genaue Betrag steht immer daneben oder im Titel. */
const euroKurz = (cent) => `${String(Math.round(cent / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ".")} €`;
const mehrzahl = (n, eins, viele) => `${n} ${n === 1 ? eins : viele}`;
const empfName = (e) => (e ? nameAnzeige(e.name) : "Ohne Empfänger");

const karte = (tid, titel, hinweis, ...inhalt) => h("section", { class: "karte mb-karte", tid },
  h("h2", null, titel), hinweis ? h("p", { class: "klein mb-hinweis" }, hinweis) : null, inhalt);
const leer = (text) => h("p", { class: "leer" }, text);
const balken = (anteil, klasse) => h("span", { class: "mb-balken", "aria-hidden": "true" },
  h("span", { class: "mb-balken-fuell " + (klasse || ""), stil: { "--w": `${Math.max(0, Math.min(100, anteil))}%` } }));

function klassenText(k) {
  if (k.unter === null) return `ab ${euroKurz(k.ab)}`;
  return k.ab ? `${euroKurz(k.ab)} bis unter ${euroKurz(k.unter)}` : `unter ${euroKurz(k.unter)}`;
}

// ------------------------------------------------------------------ Einzelbuchungen (Dialog)
function buchungenZeigen(titel, liste, ausloeser) {
  const sortiert = [...liste].sort((a, b) => (a.datum < b.datum ? -1 : a.datum > b.datum ? 1 : a.id - b.id));
  const summe = sortiert.reduce((n, e) => n + (e.art === "erstattung" ? -e.betrag : e.betrag), 0);
  dialog("mb-buchungen-dialog", titel, (inhalt, d) => {
    if (!sortiert.length) { inhalt.append(leer("Keine Ausgaben.")); return; }
    const zeilen = sortiert.map((e) => h("tr", { tid: `mb-dialog-buchung-${e.id}` },
      datumEl("td", e.datum),
      h("td", null, empfName(e.empfaenger), e.fix ? h("span", { class: "mb-marke mb-marke-fix", title: "Teil einer wiederkehrenden Zahlung" }, "fest") : null,
        e.art === "erstattung" ? h("span", { class: "mb-marke" }, "Erstattung") : null),
      h("td", { class: "mb-zweck" }, e.verwendungszweck || ""),
      betragEl("td", e.art === "erstattung" ? e.betrag : -e.betrag, { class: "zahl" }),
      h("td", null, h("button", { type: "button", class: "knopf knopf-flach klein", tid: `mb-dialog-zeigen-${e.id}`,
        title: "Buchung im Konto zeigen", onclick: () => { d.schliessen(null); oberflaeche.zurBuchung(e.konto_id, e.id); } },
      (kontoNach(e.konto_id) || {}).name || "Konto"))));
    const t = h("table", { class: "tabelle mb-dialog-tabelle" },
      h("thead", null, h("tr", null, ["Datum", "Empfänger", "Verwendungszweck", "Betrag", "Im Konto zeigen"]
        .map((s, i) => h("th", { scope: "col", class: i === 3 ? "zahl" : null }, s)))),
      h("tbody", null, zeilen));
    mobilKarten(t, ["info-", "titel", "zeile", "betrag", "aktion2"]);
    inhalt.append(h("p", { class: "klein", tid: "mb-dialog-summe" }, `${mehrzahl(sortiert.length, "Buchung", "Buchungen")}, zusammen `,
      h("strong", null, betragText(summe)), "."), h("div", { class: "mb-dialog-rollen" }, t));
  }, { klasse: "dialog-breit mb-dialog", schliessenKnopf: "mb-dialog-schliessen", ausloeser,
    fokus: (box) => box.querySelector("[data-testid='mb-dialog-schliessen']") });
}

// ------------------------------------------------------------------ Kacheln
function abweichung(wert, basis, text) {
  if (basis === null || basis === undefined || basis <= 0) return null;
  const pz = Math.round(((wert - basis) * 100) / basis);
  const art = pz > 0 ? "mehr" : pz < 0 ? "weniger" : "gleich";
  const zeichen = pz > 0 ? "▲" : pz < 0 ? "▼" : "●";
  return h("span", { class: `mb-delta mb-${art}`, title: `Vergleichswert: ${betragText(basis)}` },
    pz === 0 ? `${zeichen} wie ${text}` : `${zeichen} ${Math.abs(pz)} % ${pz > 0 ? "mehr" : "weniger"} als ${text}`);
}

function kachel(tid, titel, wert, ...zusatz) {
  return h("div", { class: "mb-kachel", tid }, h("span", { class: "mb-kachel-titel" }, titel),
    h("strong", { class: "mb-kachel-wert" }, wert), h("span", { class: "mb-kachel-zusatz" }, zusatz));
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

// ------------------------------------------------------------------ Diagramme
function eigeneFarben(seite) {
  const cs = getComputedStyle(seite);
  const v = (n, x) => (cs.getPropertyValue(n) || "").trim() || x;
  return { ...farben(), fix: v("--mb-fix", "#1f5f8b"), variabel: v("--mb-variabel", "#c9781e") };
}

/** Achse in Cent, die nicht bei 0 beginnen muss (Kontostand). */
function freieAchse(werte) {
  let min = Math.min(...werte);
  let max = Math.max(...werte);
  if (max - min < 1000) { min -= 500; max += 500; }
  const roh = (max - min) / 5;
  const pot = 10 ** Math.floor(Math.log10(roh));
  const schritt = Math.max(100, Math.round([1, 2, 5, 10].map((f) => f * pot).find((s) => s >= roh)));
  const unten = Math.floor(min / schritt) * schritt;
  const oben = Math.ceil(max / schritt) * schritt;
  const vals = [];
  for (let w = unten; w <= oben; w += schritt) vals.push(w);
  return { tickvals: vals, ticktext: vals.map((w) => betragText(w)), range: [unten, oben] };
}

function diagrammEl(tid, beschriftung) {
  return h("div", { tid, role: "img", "aria-label": beschriftung, class: "diagramm plotly-diagramm mb-diagramm" });
}

async function zeichnen(el, spuren, layout) {
  let Plotly = null;
  try { Plotly = await plotlyLaden(); } catch (e) { /* ohne Netz: Hinweis statt Diagramm */ }
  if (!Plotly || !el.isConnected) {
    if (el.isConnected) el.replaceChildren(leer("Das Diagramm ist ohne Verbindung nicht verfügbar."));
    return null;
  }
  await Plotly.newPlot(el, spuren, layout, { ...PLOTLY_OPTIONEN, displayModeBar: false });
  el.dataset.gezeichnet = "ja";
  return el;
}

const mitBetrag = (name) => `${name}: %{customdata}<extra></extra>`;

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

function klickbareZeilen(tabelle, aktion) {
  tabelle.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr.klickbar");
    if (tr && !ev.target.closest("a, button")) aktion(tr, tr);
  });
  tabelle.addEventListener("keydown", (ev) => {
    if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches("tr.klickbar")) { ev.preventDefault(); aktion(ev.target, ev.target); }
  });
}

function karteTopBuchungen(b) {
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
export async function monatsberichtSeite(seite, _param, suche) {
  const p = new URLSearchParams(suche || "");
  const zustand = {
    monat: MONAT_MUSTER.test(p.get("monat") || "") ? p.get("monat") : null,
    konten: p.getAll("konto").map(Number).filter((n) => Number.isInteger(n) && n > 0),
  };
  const steuerung = h("div", { class: "werkzeuge mb-steuerung" });
  const stand = h("p", { class: "klein mb-stand", tid: "mb-stand" });
  const inhalt = h("div", { class: "mb-inhalt" });
  seite.append(h("div", { class: "seiten-kopf" }, h("h1", null, "Monatsbericht"), steuerung), stand, inhalt);
  let lauf = 0;
  let kontenOffen = false;

  function urlSchreiben() {
    history.replaceState(history.state, "", "/berichte/monat" + abfrage({ monat: zustand.monat, konto: zustand.konten }));
    if (oberflaeche.urlGeaendert) oberflaeche.urlGeaendert();
  }
  function wechseln(monat, heuteMonat) {
    zustand.monat = monat === heuteMonat ? null : monat;
    urlSchreiben();
    return laden();
  }

  function steuerungBauen(b) {
    const heuteMonat = b.heute.slice(0, 7);
    const sorte = [b.monat, heuteMonat, b.erster_monat, b.letzter_monat].filter(Boolean).sort();
    const optionen = [];
    for (let m = sorte[sorte.length - 1]; m >= sorte[0] && optionen.length < 600; m = monatPlus(m, -1)) optionen.push(m);
    const wahl = h("select", { tid: "mb-monat", "aria-label": "Monat" },
      optionen.map((m) => h("option", { value: m, selected: m === b.monat }, monatText(m))));
    wahl.addEventListener("change", () => wechseln(wahl.value, heuteMonat));
    const zurueck = h("button", { type: "button", class: "knopf", tid: "mb-zurueck", "aria-label": "Vorheriger Monat", title: "Vorheriger Monat",
      onclick: () => wechseln(monatPlus(b.monat, -1), heuteMonat) }, "‹");
    const vor = h("button", { type: "button", class: "knopf", tid: "mb-vor", "aria-label": "Nächster Monat", title: "Nächster Monat",
      disabled: b.monat >= sorte[sorte.length - 1], onclick: () => wechseln(monatPlus(b.monat, 1), heuteMonat) }, "›");
    const heute = h("button", { type: "button", class: "knopf", tid: "mb-heute", disabled: b.monat === heuteMonat,
      onclick: () => wechseln(heuteMonat, heuteMonat) }, "Aktueller Monat");
    const bestand = baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art)));
    const gewaehlt = new Set(b.konten.map((k) => k.id));
    const felder = bestand.map(({ konto }) => h("label", { class: "mb-konto" },
      h("input", { type: "checkbox", value: String(konto.id), checked: gewaehlt.has(konto.id), tid: `mb-konto-${konto.id}` }), kontoPfad(konto)));
    const kurz = zustand.konten.length ? (b.konten.length === 1 ? b.konten[0].name : `${b.konten.length} Konten`) : "alle";
    const konten = h("details", { class: "mb-konten", tid: "mb-konten", open: kontenOffen },
      h("summary", { class: "knopf" }, `Konten: ${kurz}`),
      h("div", { class: "mb-konten-liste" }, felder,
        h("button", { type: "button", class: "knopf-link", tid: "mb-konten-alle", disabled: !zustand.konten.length,
          onclick: () => { zustand.konten = []; urlSchreiben(); laden(); } }, "Vorgabe: alle Konten ohne Darlehen")));
    konten.addEventListener("toggle", () => { kontenOffen = konten.open; });
    konten.addEventListener("change", () => {
      const ids = [...konten.querySelectorAll("input:checked")].map((el) => Number(el.value));
      if (!ids.length) return;   // mindestens ein Konto; die Vorgabe stellt der Knopf wieder her
      zustand.konten = ids;
      urlSchreiben();
      laden();
    });
    konten.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && konten.open) { ev.stopPropagation(); konten.open = false; konten.querySelector("summary").focus(); } });
    steuerung.replaceChildren(h("div", { class: "mb-monatswahl", role: "group", "aria-label": "Monat wählen" }, zurueck, wahl, vor), heute, konten);
  }

  async function laden() {
    const n = ++lauf;
    seite.dataset.geladen = "nein";
    let b;
    try {
      b = await api("GET", "/api/berichte/monat" + abfrage({ monat: zustand.monat, konto_id: zustand.konten }));
    } catch (e) {
      if (n !== lauf) return;
      if (zustand.konten.length && e.code && e.code !== "validierung") { zustand.konten = []; urlSchreiben(); await laden(); return; }
      inhalt.replaceChildren(h("p", { class: "fehler", role: "alert" }, e.message));
      seite.dataset.geladen = "ja";
      return;
    }
    if (n !== lauf) return;
    const fokusTid = document.activeElement && seite.contains(document.activeElement) ? document.activeElement.dataset.testid : null;
    steuerungBauen(b);
    const heuteMonat = b.heute.slice(0, 7);
    const umb = b.ausgeschlossen.umbuchungen;
    stand.replaceChildren(b.zukunft ? "Dieser Monat liegt in der Zukunft." : b.laufend ? `Laufender Monat, Stand ${datumText(b.stichtag)}.` : "Abgeschlossener Monat.",
      ` Konten: ${b.konten.map((k) => k.name).join(", ") || "keine"}.`,
      umb ? ` ${mehrzahl(umb, "Umbuchung", "Umbuchungen")} zwischen eigenen Konten ${umb === 1 ? "zählt" : "zählen"} nicht mit.` : "");
    const zeigen = (titel, liste, ausloeser) => buchungenZeigen(titel, liste, ausloeser);
    const verlauf = diagrammEl("mb-verlauf-diagramm", `Aufgelaufene Ausgaben im ${monatText(b.monat)} je Tag, im Vergleich zum Vormonat und zum Schnitt`);
    const monate = diagrammEl("mb-monate-diagramm", "Ausgaben der letzten zwölf Monate, geteilt in fest und variabel");
    const kontostand = diagrammEl("mb-kontostand-diagramm", `Kontostand im ${monatText(b.monat)}`);
    const tief = b.kontostand.tiefststand;
    const hatAusgaben = b.buchungen.length > 0;
    seite.dataset.monat = b.monat;
    inhalt.replaceChildren(
      kacheln(b),
      h("div", { class: "mb-raster" },
        h("div", { class: "mb-breit" }, karte("mb-verlauf", "Verlauf im Monat",
          "So sind die Ausgaben Tag für Tag aufgelaufen. Liegt die dicke Linie unter den anderen, wurde bisher weniger ausgegeben als sonst. Ein Klick auf einen Tag zeigt dessen Buchungen.", verlauf)),
        hatAusgaben ? karteFixVariabel(b, zeigen) : null,
        karte("mb-monate", "Die letzten zwölf Monate", "Ein Klick auf einen Balken öffnet den Monat.", monate),
        hatAusgaben ? karteTopBuchungen(b) : null,
        hatAusgaben ? karteEmpfaenger(b, zeigen) : null,
        hatAusgaben ? karteKlassen(b, zeigen) : null,
        b.zukunft ? null : karteAuffaellig(b, zeigen),
        hatAusgaben ? h("div", { class: "mb-breit" }, karteKalender(b, zeigen)) : null,
        h("div", { class: "mb-breit" }, karte("mb-kontostand", "Kontostand",
          tief ? `Tiefster Stand ${betragText(tief.betrag)} am ${datumText(tief.datum)}; Anfang ${betragText(b.kontostand.anfang)}, zuletzt ${betragText(b.kontostand.ende)}.` : null, kontostand))));
    if (!hatAusgaben && !b.zukunft) inhalt.prepend(h("p", { class: "leer", tid: "mb-leer" }, "In diesem Monat gibt es auf den gewählten Konten keine Ausgaben."));
    if (fokusTid) { const el = seite.querySelector(`[data-testid="${fokusTid}"]`); if (el && !el.disabled) el.focus(); }
    const f = eigeneFarben(seite);
    await Promise.all([
      verlaufZeichnen(verlauf, b, f, (tag) => {
        const datum = `${b.monat}-${String(tag).padStart(2, "0")}`;
        const liste = b.buchungen.filter((e) => e.datum === datum);
        if (liste.length) zeigen(`Ausgaben am ${datumText(datum)}`, liste, null);
      }),
      monateZeichnen(monate, b, f, (m) => { if (m !== b.monat) wechseln(m, heuteMonat); }),
      kontostandZeichnen(kontostand, b, f),
    ]);
    if (n === lauf) seite.dataset.geladen = "ja";
  }

  await laden();
  return { titel: "Monatsbericht", aktualisieren: laden };
}
