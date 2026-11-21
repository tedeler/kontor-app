/* Gemeinsame Bausteine der Berichte (Monatsbericht D-206, weitere Berichte D-217): Karten, Kacheln, Balken,
   Einzelbuchungen, Diagramme, Monats- und Kontenwahl. */
import {
  BESTAND, abfrage, api, baumFolge, betragEl, betragText, datumEl, h, kontoNach, kontoPfad, mobilKarten, nameAnzeige, oberflaeche, stamm,
} from "./kern.js";
import { dialog } from "./ui.js";
import { PLOTLY_OPTIONEN, farben, plotlyLaden } from "./seiten.js";

export const MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
  "November", "Dezember"];
export const MONATE_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
export const WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
export const WOCHENTAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
export const RHYTHMUS = { monatlich: "monatlich", vierteljaehrlich: "vierteljährlich", halbjaehrlich: "halbjährlich", jaehrlich: "jährlich",
  einmalig: "einmalig" };
export const MONAT_MUSTER = /^\d{4}-(0[1-9]|1[0-2])$/;

export const monatText = (m) => `${MONATE[Number(m.slice(5)) - 1]} ${m.slice(0, 4)}`;
export function monatPlus(m, n) {
  const i = Number(m.slice(0, 4)) * 12 + Number(m.slice(5)) - 1 + n;
  return `${String(Math.floor(i / 12)).padStart(4, "0")}-${String((i % 12) + 1).padStart(2, "0")}`;
}
export const tagKurz = (iso) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}.`;
export const prozent = (teil, ganz) => (ganz > 0 ? Math.round((teil * 100) / ganz) : 0);
/** Ganze Euro ohne Cent für enge Stellen (Kalender); der genaue Betrag steht immer daneben oder im Titel. */
export const euroKurz = (cent) => `${String(Math.round(cent / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ".")} €`;
export const mehrzahl = (n, eins, viele) => `${n} ${n === 1 ? eins : viele}`;
export const empfName = (e) => (e ? nameAnzeige(e.name) : "Ohne Empfänger");

export const karte = (tid, titel, hinweis, ...inhalt) => h("section", { class: "karte mb-karte", tid },
  h("h2", null, titel), hinweis ? h("p", { class: "klein mb-hinweis" }, hinweis) : null, inhalt);
export const leer = (text) => h("p", { class: "leer" }, text);
export const balken = (anteil, klasse) => h("span", { class: "mb-balken", "aria-hidden": "true" },
  h("span", { class: "mb-balken-fuell " + (klasse || ""), stil: { "--w": `${Math.max(0, Math.min(100, anteil))}%` } }));

// ------------------------------------------------------------------ Einzelbuchungen (Dialog)
export function buchungenZeigen(titel, liste, ausloeser) {
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
export function abweichung(wert, basis, text) {
  if (basis === null || basis === undefined || basis <= 0) return null;
  const pz = Math.round(((wert - basis) * 100) / basis);
  const art = pz > 0 ? "mehr" : pz < 0 ? "weniger" : "gleich";
  const zeichen = pz > 0 ? "▲" : pz < 0 ? "▼" : "●";
  return h("span", { class: `mb-delta mb-${art}`, title: `Vergleichswert: ${betragText(basis)}` },
    pz === 0 ? `${zeichen} wie ${text}` : `${zeichen} ${Math.abs(pz)} % ${pz > 0 ? "mehr" : "weniger"} als ${text}`);
}

export function kachel(tid, titel, wert, ...zusatz) {
  return h("div", { class: "mb-kachel", tid }, h("span", { class: "mb-kachel-titel" }, titel),
    h("strong", { class: "mb-kachel-wert" }, wert), h("span", { class: "mb-kachel-zusatz" }, zusatz));
}

// ------------------------------------------------------------------ Diagramme
export function eigeneFarben(seite) {
  const cs = getComputedStyle(seite);
  const v = (n, x) => (cs.getPropertyValue(n) || "").trim() || x;
  return { ...farben(), fix: v("--mb-fix", "#1f5f8b"), variabel: v("--mb-variabel", "#c9781e") };
}

/** Achse in Cent, die nicht bei 0 beginnen muss (Kontostand). */
export function freieAchse(werte) {
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

export function diagrammEl(tid, beschriftung) {
  return h("div", { tid, role: "img", "aria-label": beschriftung, class: "diagramm plotly-diagramm mb-diagramm" });
}

export async function zeichnen(el, spuren, layout) {
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

export const mitBetrag = (name) => `${name}: %{customdata}<extra></extra>`;

export function klickbareZeilen(tabelle, aktion) {
  tabelle.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr.klickbar");
    if (tr && !ev.target.closest("a, button")) aktion(tr, tr);
  });
  tabelle.addEventListener("keydown", (ev) => {
    if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches("tr.klickbar")) { ev.preventDefault(); aktion(ev.target, ev.target); }
  });
}

// ------------------------------------------------------------------ kleine Bausteine
export const jahrVon = (iso) => Number(iso.slice(0, 4));
export const promilleText = (p) => (p === null || p === undefined ? "–" : `${Math.round(p / 10)} %`);
export const kontoName = (id) => (kontoNach(id) || {}).name || "Konto";

/** Kleine Verlaufslinie ohne Achsen (reines SVG, kein Plotly); der letzte Punkt ist betont. */
export function funke(werte, beschriftung) {
  const ns = "http://www.w3.org/2000/svg";
  const b = 96;
  const hh = 24;
  const max = Math.max(1, ...werte);
  const min = Math.min(0, ...werte);
  const x = (i) => (werte.length > 1 ? 2 + (i * (b - 4)) / (werte.length - 1) : b / 2);
  const y = (w) => hh - 3 - ((w - min) * (hh - 6)) / (max - min || 1);
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${b} ${hh}`);
  svg.setAttribute("class", "mb-funke");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", beschriftung || "Verlauf");
  const linie = document.createElementNS(ns, "polyline");
  linie.setAttribute("points", werte.map((w, i) => `${x(i).toFixed(1)},${y(w).toFixed(1)}`).join(" "));
  const punkt = document.createElementNS(ns, "circle");
  punkt.setAttribute("cx", x(werte.length - 1).toFixed(1));
  punkt.setAttribute("cy", y(werte[werte.length - 1]).toFixed(1));
  punkt.setAttribute("r", "2.6");
  svg.append(linie, punkt);
  return svg;
}

/** Tabelle mit klickbaren Spaltenköpfen: `spalten` = [{ titel, wert(zeile) (zum Sortieren), zelle(zeile), zahl, tip }]. */
export function sortierTabelle(tid, spalten, zeilen, optionen) {
  const o = optionen || {};
  let nach = o.nach === undefined ? -1 : o.nach;
  let ab = o.absteigend !== false;
  const tbody = h("tbody");
  const koepfe = spalten.map((s, i) => {
    const th = h("th", { scope: "col", class: s.zahl ? "zahl" : null, title: s.tip || null });
    if (s.wert) {
      th.append(h("button", { type: "button", class: "mb-sortier", tid: `${tid}-sort-${i}`, onclick: () => {
        if (nach === i) ab = !ab; else { nach = i; ab = !!s.zahl; }
        fuellen();
      } }, s.titel, h("span", { class: "mb-sortier-pfeil", "aria-hidden": "true" })));
    } else th.append(s.kopf || s.titel);
    return th;
  });
  function fuellen() {
    const folge = [...zeilen];
    if (nach >= 0) {
      const w = spalten[nach].wert;
      folge.sort((a, b) => {
        const x = w(a);
        const y = w(b);
        const c = typeof x === "string" ? x.localeCompare(y, "de") : (x === null ? -Infinity : x) - (y === null ? -Infinity : y);
        return ab ? -c : c;
      });
    }
    koepfe.forEach((th, i) => {
      if (i === nach) th.setAttribute("aria-sort", ab ? "descending" : "ascending"); else th.removeAttribute("aria-sort");
    });
    tbody.replaceChildren(...folge.map((z) => {
      const klickbar = !!o.beiKlick;
      const tr = h("tr", klickbar ? { class: "klickbar", tabindex: "0", role: "button", tid: o.zeilenTid ? o.zeilenTid(z) : null,
        "aria-label": o.zeilenText ? o.zeilenText(z) : null } : { tid: o.zeilenTid ? o.zeilenTid(z) : null });
      if (o.zeilenKlasse) { const k = o.zeilenKlasse(z); if (k) tr.classList.add(...k.split(" ")); }
      tr.append(...spalten.map((s) => h("td", { class: s.zahl ? "zahl" : null }, s.zelle(z))));
      tr.zeile = z;
      return tr;
    }));
  }
  fuellen();
  const t = h("table", { class: "tabelle mb-tabelle", tid }, h("thead", null, h("tr", null, koepfe)), tbody);
  if (o.beiKlick) klickbareZeilen(t, (tr) => o.beiKlick(tr.zeile, tr));
  return t;
}

/** Auswahl aus wenigen Stufen als Knopfreihe (z. B. Zeitraum). */
export function stufen(tid, beschriftung, optionen, wert, beiWahl) {
  return h("div", { class: "mb-stufen", role: "group", "aria-label": beschriftung, tid },
    optionen.map(([w, text]) => h("button", { type: "button", class: "knopf", tid: `${tid}-${w}`, "aria-pressed": String(w) === String(wert) ? "true" : "false",
      onclick: () => { if (String(w) !== String(wert)) beiWahl(w); } }, text)));
}

/** ‹ Auswahl › für Monate oder Jahre. `werte` absteigend sortiert, `text(wert)` für die Anzeige. */
export function blaetterWahl(tid, beschriftung, werte, wert, text, beiWahl) {
  const i = werte.indexOf(wert);
  const wahl = h("select", { tid, "aria-label": beschriftung }, werte.map((w) => h("option", { value: String(w), selected: w === wert }, text(w))));
  wahl.addEventListener("change", () => beiWahl(werte.find((w) => String(w) === wahl.value)));
  return h("div", { class: "mb-monatswahl", role: "group", "aria-label": `${beschriftung} wählen` },
    h("button", { type: "button", class: "knopf", tid: `${tid}-zurueck`, "aria-label": "Zurück", title: "Zurück", disabled: i >= werte.length - 1,
      onclick: () => beiWahl(werte[i + 1]) }, "‹"), wahl,
    h("button", { type: "button", class: "knopf", tid: `${tid}-vor`, "aria-label": "Weiter", title: "Weiter", disabled: i <= 0, onclick: () => beiWahl(werte[i - 1]) }, "›"));
}

export function monatsWahl(b, monat, beiWahl) {
  const heuteMonat = b.heute.slice(0, 7);
  const sorte = [monat, heuteMonat, b.erster_monat, b.letzter_monat].filter(Boolean).sort();
  const werte = [];
  for (let m = sorte[sorte.length - 1]; m >= sorte[0] && werte.length < 600; m = monatPlus(m, -1)) werte.push(m);
  const el = blaetterWahl("mb-monat", "Monat", werte, monat, monatText, (m) => beiWahl(m === heuteMonat ? null : m));
  return [el, h("button", { type: "button", class: "knopf", tid: "mb-heute", disabled: monat === heuteMonat, onclick: () => beiWahl(null) }, "Aktueller Monat")];
}

export function jahrWahl(b, jahr, beiWahl) {
  const heute = jahrVon(b.heute);
  const von = Math.min(jahr, heute, b.erstes_jahr || heute);
  const bis = Math.max(jahr, heute, b.letztes_jahr || heute);
  const werte = [];
  for (let j = bis; j >= von; j -= 1) werte.push(j);
  return [blaetterWahl("mb-jahr", "Jahr", werte, jahr, String, (j) => beiWahl(j === heute ? null : j))];
}

/** Aufklappbare Kontenwahl; `gewaehlt` sind die Konten der Antwort, `eigene` die ausdrücklich gewählten (leer = Vorgabe). */
export function kontenWahl(gewaehlt, eigene, beiWahl, merker, vorgabeText) {
  const bestand = baumFolge(stamm.konten.filter((k) => BESTAND.has(k.art)));
  const menge = new Set(gewaehlt.map((k) => k.id));
  const felder = bestand.map(({ konto }) => h("label", { class: "mb-konto" },
    h("input", { type: "checkbox", value: String(konto.id), checked: menge.has(konto.id), tid: `mb-konto-${konto.id}` }), kontoPfad(konto)));
  const kurz = eigene.length ? (gewaehlt.length === 1 ? gewaehlt[0].name : `${gewaehlt.length} Konten`) : "Vorgabe";
  const konten = h("details", { class: "mb-konten", tid: "mb-konten", open: !!merker.offen },
    h("summary", { class: "knopf" }, `Konten: ${kurz}`),
    h("div", { class: "mb-konten-liste" }, felder,
      h("button", { type: "button", class: "knopf-link", tid: "mb-konten-alle", disabled: !eigene.length, onclick: () => beiWahl([]) },
        vorgabeText || "Vorgabe: alle Konten ohne Darlehen")));
  konten.addEventListener("toggle", () => { merker.offen = konten.open; });
  konten.addEventListener("change", () => {
    const ids = [...konten.querySelectorAll("input:checked")].map((el) => Number(el.value));
    if (ids.length) beiWahl(ids);   // mindestens ein Konto; die Vorgabe stellt der Knopf wieder her
  });
  konten.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && konten.open) { ev.stopPropagation(); konten.open = false; konten.querySelector("summary").focus(); }
  });
  return konten;
}

export const kontenAus = (p) => p.getAll("konto").map(Number).filter((n) => Number.isInteger(n) && n > 0);
export const kontenText = (b) => ` Konten: ${b.konten.map((k) => k.name).join(", ") || "keine"}.`;
export const berichtAdresse = (art, params) => "/berichte" + abfrage({ art, ...(params || {}) });

/**
 * Gerüst einer Berichtsseite: Kopf mit Steuerung, Standzeile, Inhalt; lädt bei jeder Änderung des Zustands neu und
 * schreibt ihn in die Adresse. `o`: art, titel, pfad, lesen(URLSearchParams) → Zustand, anfrage(zustand) → Parameter
 * der REST-Abfrage, adresse(zustand) → Parameter der Adresse, steuerung(b, k), stand(b, k), inhalt(b, k), danach(b, k).
 */
export async function berichtRahmen(seite, suche, o) {
  const zustand = o.lesen(new URLSearchParams(suche || ""));
  const steuerung = h("div", { class: "werkzeuge mb-steuerung" });
  const stand = h("p", { class: "klein mb-stand", tid: "mb-stand" });
  const inhalt = h("div", { class: "mb-inhalt" });
  seite.append(h("div", { class: "seiten-kopf" }, h("h1", null, o.titel), steuerung), stand, inhalt);
  let lauf = 0;
  const k = { zustand, seite, merker: {}, zeigen: buchungenZeigen };
  k.setzen = (aenderung) => {
    Object.assign(zustand, aenderung);
    history.replaceState(history.state, "", berichtAdresse(o.art, o.adresse(zustand)));
    if (oberflaeche.urlGeaendert) oberflaeche.urlGeaendert();
    return laden();
  };
  async function laden() {
    const n = ++lauf;
    seite.dataset.geladen = "nein";
    let b;
    try {
      b = await api("GET", o.pfad + abfrage(o.anfrage(zustand)));
    } catch (e) {
      if (n !== lauf) return;
      if (o.beiFehler && o.beiFehler(e, k)) { await k.setzen({}); return; }
      inhalt.replaceChildren(h("p", { class: "fehler", role: "alert" }, e.message));
      seite.dataset.geladen = "ja";
      return;
    }
    if (n !== lauf) return;
    const fokusTid = document.activeElement && seite.contains(document.activeElement) ? document.activeElement.dataset.testid : null;
    k.farben = eigeneFarben(seite);
    steuerung.replaceChildren(...(o.steuerung ? o.steuerung(b, k) : []).flat().filter(Boolean));
    stand.replaceChildren(...(o.stand ? [o.stand(b, k)].flat().filter(Boolean) : []));
    inhalt.replaceChildren(...[o.inhalt(b, k)].flat().filter(Boolean));
    if (fokusTid) { const el = seite.querySelector(`[data-testid="${fokusTid}"]`); if (el && !el.disabled) el.focus(); }
    if (o.danach) await o.danach(b, k);
    if (n === lauf) seite.dataset.geladen = "ja";
  }
  await laden();
  return { titel: o.titel, aktualisieren: laden };
}

/** Standard bei unbekannten Konten in der Adresse: Kontenwahl verwerfen und neu laden. */
export function kontenFehler(e, k) {
  if (k.zustand.konten && k.zustand.konten.length && e.code && e.code !== "validierung") { k.zustand.konten = []; return true; }
  return false;
}
