/* Berichte (Feature berichte, D-217), zweiter Teil: Kategorien, Empfänger, Geldfluss, Datenqualität, Tags. */
import { betragEl, betragText, datumText, h, nameAnzeige, oberflaeche, stamm } from "./kern.js";
import { centAchse, plotlyLayout } from "./seiten.js";
import { karteTopBuchungen } from "./monatsbericht.js";
import {
  MONATE_KURZ, MONAT_MUSTER, RHYTHMUS, balken, berichtAdresse, berichtRahmen, diagrammEl, empfName, funke, jahrVon, jahrWahl, kachel, karte,
  klickbareZeilen, kontenAus, kontenFehler, kontenText, kontenWahl, leer, mehrzahl, mitBetrag, monatText, monatsWahl, promilleText,
  prozent, sortierTabelle, stufen, tagKurz, zeichnen,
} from "./berichtsteile.js";

const RAND = { l: 96, r: 12, t: 30, b: 44 };
const REIHE = ["#1f5f8b", "#c9781e", "#2f7d4f", "#8a5fbf", "#b0413e", "#3d8f99"];
const monatsMarken = (monate) => monate.map((m) => `${MONATE_KURZ[Number(m.slice(5)) - 1]}<br>${m.slice(0, 4)}`);
const duenn = (el, x) => { const n = el.clientWidth < 520 ? Math.ceil(x.length / 5) : Math.ceil(x.length / 14); return x.filter((_, i) => (x.length - 1 - i) % n === 0); };
const kategorieAchse = (el, x, f) => ({ type: "category", linecolor: f.rand, fixedrange: true, tickangle: 0, tickfont: { size: 11 }, tickmode: "array", tickvals: duenn(el, x) });
const delta = (w, gutWennWeniger) => {
  if (w === null || w === undefined) return "";
  if (w === 0) return h("span", { class: "mb-gleich" }, "● 0,00 €");
  const schlecht = gutWennWeniger ? w > 0 : w < 0;
  return h("span", { class: `mb-delta mb-${schlecht ? "mehr" : "weniger"}` }, `${w > 0 ? "▲" : "▼"} ${betragText(Math.abs(w))}`);
};
const zeitraumText = (a, b) => (a ? (a === b ? datumText(a) : `${datumText(a)} – ${datumText(b)}`) : "–");
const ZEITRAEUME = [[12, "1 Jahr"], [24, "2 Jahre"], [60, "5 Jahre"], [0, "Alles"]];

// ------------------------------------------------------------------ Kategorien
function kategorieTabelle(tid, zeilen, b, k, ausgabe) {
  if (!zeilen.length) return leer(ausgabe ? "Keine Ausgaben in diesem Monat." : "Keine Einnahmen in diesem Monat.");
  const gesamt = Math.max(1, zeilen.filter((z) => z.ebene === 0).reduce((n, z) => n + Math.max(z.summe, 0), 0));
  const eltern = new Map(zeilen.map((z) => [z.id, z.eltern_id]));
  const unter = (id) => new Set(zeilen.filter((z) => { for (let x = z.id; x !== null && x !== undefined; x = eltern.get(x)) if (x === id) return true; return false; }).map((z) => z.id));
  const tabelle = h("table", { class: "tabelle mb-tabelle mb-baum", tid },
    h("thead", null, h("tr", null, h("th", { scope: "col" }, "Kategorie"), h("th", { scope: "col" }, h("span", { class: "nur-vorleser" }, "Anteil")),
      h("th", { scope: "col", class: "zahl" }, monatText(b.monat)), h("th", { scope: "col", class: "zahl", title: `Schnitt der ${b.vergleich_monate} Monate davor` }, "Schnitt"),
      h("th", { scope: "col", class: "zahl" }, "Abweichung"), h("th", { scope: "col" }, "13 Monate"))),
    h("tbody", null, zeilen.map((z) => h("tr", { class: `klickbar mb-ebene-${Math.min(z.ebene, 3)}`, tid: `${tid}-${z.id}`, tabindex: "0", role: "button", "data-id": String(z.id),
      "aria-label": `${z.name}: ${betragText(z.summe)}. Buchungen zeigen` },
    h("td", null, h("span", { class: "mb-name", stil: { "--stufe": String(z.ebene) } }, z.name, z.unkategorisiert ? h("span", { class: "mb-marke mb-marke-warn" }, "offen") : null)),
    h("td", null, z.ebene === 0 ? balken(prozent(Math.max(z.summe, 0), gesamt), ausgabe ? "mb-fuell-fix" : "mb-fuell-gut") : null),
    h("td", { class: "zahl" }, betragText(z.summe)), h("td", { class: "zahl" }, z.schnitt === null ? "–" : betragText(z.schnitt)),
    h("td", { class: "zahl" }, delta(z.abweichung, ausgabe)), h("td", null, funke(z.verlauf, `Verlauf ${z.name} über 13 Monate`))))));
  klickbareZeilen(tabelle, (tr, ziel) => {
    const id = Number(tr.dataset.id);
    const z = zeilen.find((x) => x.id === id);
    const ids = unter(id);
    const liste = b.buchungen.filter((e) => e.teile.some((t) => ids.has(t.konto_id) && (!z.unkategorisiert || (ausgabe ? t.betrag < 0 : t.betrag > 0))))
      .map((e) => (ausgabe ? e : { ...e, art: "erstattung" }));
    k.zeigen(`${z.name} im ${monatText(b.monat)}`, liste, ziel);
  });
  return h("div", { class: "mb-rollen" }, tabelle);
}

function bewegungen(b) {
  const oben = b.ausgaben.filter((z) => z.ebene === 0 && z.abweichung !== null && z.abweichung !== 0);
  const max = Math.max(1, ...oben.map((z) => Math.abs(z.abweichung)));
  const liste = (titel, eintraege, klasse) => h("div", null, h("h3", null, titel), eintraege.length ? h("ul", { class: "mb-liste" }, eintraege.map((z) => h("li", null,
    h("span", { class: "mb-bewegung" }, h("span", { class: "mb-name" }, z.name), balken(prozent(Math.abs(z.abweichung), max), klasse)), delta(z.abweichung, true))))
    : h("p", { class: "klein" }, "Keine."));
  return karte("mb-bewegungen", "Größte Veränderungen", `Hauptkategorien gegenüber ihrem Schnitt der ${b.vergleich_monate} Monate davor.`,
    b.vergleich_monate ? h("div", { class: "mb-zwei" },
      liste("Mehr als üblich", oben.filter((z) => z.abweichung > 0).sort((x, y) => y.abweichung - x.abweichung).slice(0, 5), "mb-fuell-schlecht"),
      liste("Weniger als üblich", oben.filter((z) => z.abweichung < 0).sort((x, y) => x.abweichung - y.abweichung).slice(0, 5), "mb-fuell-gut"))
      : leer("Für einen Vergleich fehlen frühere Monate."));
}

export function kategorienSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    art: "kategorien", titel: "Kategorienbericht", pfad: "/api/berichte/kategorien",
    lesen: (p) => ({ monat: MONAT_MUSTER.test(p.get("monat") || "") ? p.get("monat") : null, konten: kontenAus(p) }),
    anfrage: (z) => ({ monat: z.monat, konto_id: z.konten }), adresse: (z) => ({ monat: z.monat, konto: z.konten }), beiFehler: kontenFehler,
    steuerung: (b, k) => [monatsWahl(b, b.monat, (monat) => k.setzen({ monat })), kontenWahl(b.konten, k.zustand.konten, (konten) => k.setzen({ konten }), k.merker)],
    stand: (b) => [b.laufend ? `Laufender Monat, Stand ${datumText(b.heute)}.` : `${monatText(b.monat)}.`, kontenText(b),
      " Unterkategorien sind in ihrer Hauptkategorie enthalten."],
    inhalt: (b, k) => {
      const s = b.summen;
      const oben = b.ausgaben.filter((z) => z.ebene === 0 && z.abweichung);
      const hoch = oben.filter((z) => z.abweichung > 0).sort((x, y) => y.abweichung - x.abweichung)[0];
      const tief = oben.filter((z) => z.abweichung < 0).sort((x, y) => x.abweichung - y.abweichung)[0];
      return [
        h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
          kachel("mb-kachel-ausgaben", "Ausgaben", betragEl("span", s.ausgaben)),
          kachel("mb-kachel-einnahmen", "Einnahmen", betragEl("span", s.einnahmen)),
          kachel("mb-kachel-offen", "Unkategorisiert", betragEl("span", s.unkategorisiert), h("span", null, `${prozent(s.unkategorisiert, Math.max(s.ausgaben, 1))} % der Ausgaben`)),
          kachel("mb-kachel-hoch", "Größter Anstieg", hoch ? hoch.name : "–", hoch ? delta(hoch.abweichung, true) : null),
          kachel("mb-kachel-tief", "Größter Rückgang", tief ? tief.name : "–", tief ? delta(tief.abweichung, true) : null)),
        karte("mb-kategorien", "Ausgaben nach Kategorie", "Ein Klick auf eine Zeile zeigt die Buchungen des Monats.", kategorieTabelle("mb-kategorien-ausgaben", b.ausgaben, b, k, true)),
        h("div", { class: "mb-raster" }, bewegungen(b),
          karte("mb-kategorien-ein", "Einnahmen nach Kategorie", null, kategorieTabelle("mb-kategorien-einnahmen", b.einnahmen, b, k, false)))];
    },
  });
}

// ------------------------------------------------------------------ Empfänger
function empfaengerSuche(k, aktuell) {
  const id = "mb-empfaenger-vorschlaege";
  const feld = h("input", { type: "search", class: "mb-suche", tid: "mb-empfaenger-suche", list: id, placeholder: "Empfänger suchen …", "aria-label": "Empfänger suchen",
    value: aktuell ? nameAnzeige(aktuell.name) : "" });
  const nach = new Map(stamm.empfaenger.map((e) => [nameAnzeige(e.name).toLocaleLowerCase("de"), e.id]));
  const waehlen = () => { const eid = nach.get(feld.value.trim().toLocaleLowerCase("de")); if (eid && (!aktuell || eid !== aktuell.id)) k.setzen({ empfaenger: eid }); };
  feld.addEventListener("change", waehlen);
  feld.addEventListener("input", (ev) => { if (ev.inputType === "insertReplacementText" || ev.inputType === undefined) waehlen(); });
  return [feld, h("datalist", { id }, stamm.empfaenger.map((e) => h("option", { value: nameAnzeige(e.name) })))];
}

function empfaengerRangliste(b, k) {
  const max = Math.max(1, ...b.rangliste.map((e) => e.ausgaben));
  return [karte("mb-rangliste", "Empfänger der letzten zwölf Monate",
    `Ein Klick öffnet den Bericht zum Empfänger.${b.anzahl > b.rangliste.length ? ` Gezeigt sind die ${b.rangliste.length} größten von ${b.anzahl}.` : ""}`,
    b.rangliste.length ? h("div", { class: "mb-rollen" }, sortierTabelle("mb-rangliste-tabelle", [
      { titel: "Empfänger", wert: (e) => empfName(e.empfaenger), zelle: (e) => h("span", { class: "mb-name" }, empfName(e.empfaenger)) },
      { titel: "Buchungen", zahl: true, wert: (e) => e.anzahl, zelle: (e) => String(e.anzahl) },
      { titel: "Größe", kopf: h("span", { class: "nur-vorleser" }, "Größe"), zelle: (e) => balken(prozent(Math.max(e.ausgaben, 0), max), "mb-fuell-fix") },
      { titel: "Ausgaben", zahl: true, wert: (e) => e.ausgaben, zelle: (e) => (e.ausgaben ? betragText(e.ausgaben) : "–") },
      { titel: "Einnahmen", zahl: true, wert: (e) => e.einnahmen, zelle: (e) => (e.einnahmen ? betragText(e.einnahmen) : "–") },
      { titel: "Zuletzt", wert: (e) => e.letzte, zelle: (e) => datumText(e.letzte) },
    ], b.rangliste, { zeilenTid: (e) => `mb-rang-${e.empfaenger.id}`, zeilenText: (e) => `${empfName(e.empfaenger)}. Bericht öffnen`,
      beiKlick: (e) => k.setzen({ empfaenger: e.empfaenger.id }) })) : leer("In den letzten zwölf Monaten gibt es keine Buchungen mit Empfänger."))];
}

function empfaengerEinzeln(b, k) {
  const kz = b.kennzahlen;
  k.monate = diagrammEl("mb-empfaenger-diagramm", `Ausgaben an ${empfName(b.empfaenger)} je Monat`);
  k.punkte = diagrammEl("mb-empfaenger-punkte", `Einzelne Beträge an ${empfName(b.empfaenger)} über die Zeit`);
  const serie = b.serien[0];
  const maxKat = Math.max(1, ...b.kategorien.map((x) => Math.abs(x.summe)));
  const letzte = [...b.buchungen].reverse().slice(0, 12);
  const tags = b.tag_ids.map((id) => stamm.tags.find((t) => t.id === id)).filter(Boolean);
  return [
    h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
      kachel("mb-kachel-ausgaben", "Ausgaben in zwölf Monaten", betragEl("span", kz.ausgaben_12), h("span", null, `${mehrzahl(kz.anzahl_12, "Buchung", "Buchungen")}`),
        h("span", null, `insgesamt ${betragText(kz.ausgaben)}`)),
      kachel("mb-kachel-typisch", "Typischer Betrag", kz.median === null ? "–" : betragEl("span", kz.median), kz.groesste !== null ? h("span", null, `größter ${betragText(kz.groesste)}`) : null),
      kachel("mb-kachel-rhythmus", "Rhythmus", serie ? (RHYTHMUS[serie.rhythmus] || serie.rhythmus) : kz.abstand_tage === null ? "–" : `alle ${mehrzahl(kz.abstand_tage, "Tag", "Tage")}`,
        serie ? h("span", null, `${betragText(serie.betrag)}, nächste Zahlung ${datumText(serie.naechste_faelligkeit)}`) : h("span", null, "üblicher Abstand zwischen zwei Ausgaben")),
      kachel("mb-kachel-zeitraum", "Buchungen", String(kz.anzahl), h("span", null, zeitraumText(kz.erste, kz.letzte))),
      kz.einnahmen ? kachel("mb-kachel-einnahmen", "Einnahmen", betragEl("span", kz.einnahmen)) : null),
    tags.length ? h("p", { class: "klein" }, "Tags am Empfänger: ", tags.map((t) => h("a", { class: "mb-marke", href: berichtAdresse("tags", { tag: [t.id] }) }, t.name))) : null,
    kz.anzahl ? h("div", { class: "mb-raster" },
      h("div", { class: "mb-breit" }, karte("mb-empfaenger-monate", "Je Monat", "Die letzten 24 Monate. Ein Klick auf einen Balken öffnet den Monatsbericht.", k.monate)),
      karte("mb-empfaenger-betraege", "Einzelne Beträge", "Jeder Punkt ist eine Ausgabe; so zeigen sich Preisänderungen. Ein Klick führt zur Buchung.", k.punkte),
      karte("mb-empfaenger-jahre", "Je Jahr", null, h("table", { class: "tabelle mb-tabelle" },
        h("thead", null, h("tr", null, h("th", { scope: "col" }, "Jahr"), h("th", { scope: "col", class: "zahl" }, "Buchungen"), h("th", { scope: "col", class: "zahl" }, "Ausgaben"),
          h("th", { scope: "col", class: "zahl" }, "Einnahmen"))),
        h("tbody", null, [...b.jahre].reverse().map((j) => h("tr", null, h("th", { scope: "row" }, String(j.jahr)), h("td", { class: "zahl" }, String(j.buchungen)),
          h("td", { class: "zahl" }, betragText(j.ausgaben)), h("td", { class: "zahl" }, j.einnahmen ? betragText(j.einnahmen) : "–")))))),
      karte("mb-empfaenger-kategorien", "Kategorien", "Worauf die Buchungen dieses Empfängers gebucht sind.", b.kategorien.length ? h("table", { class: "tabelle mb-tabelle" },
        h("tbody", null, b.kategorien.map((x) => h("tr", null, h("th", { scope: "row" }, x.name), h("td", null, balken(prozent(Math.abs(x.summe), maxKat), "mb-fuell-fix")),
          h("td", { class: "zahl" }, betragText(x.summe)))))) : leer("Keine.")),
      karte("mb-empfaenger-buchungen", "Letzte Buchungen", null, h("table", { class: "tabelle mb-tabelle" },
        h("tbody", null, letzte.map((e) => h("tr", null, h("td", null, datumText(e.datum)), h("td", null, h("span", { class: "klein mb-zweck" }, e.verwendungszweck || "")),
          betragEl("td", e.art === "ausgabe" ? -e.betrag : e.betrag, { class: "zahl" }))))),
      h("button", { type: "button", class: "knopf", tid: "mb-empfaenger-alle", onclick: (ev) => k.zeigen(`Buchungen mit ${empfName(b.empfaenger)}`,
        b.buchungen.map((e) => (e.art === "einnahme" ? { ...e, art: "erstattung" } : e)), ev.currentTarget) },
      b.buchungen_gesamt > b.buchungen.length ? `Die letzten ${b.buchungen.length} von ${b.buchungen_gesamt} zeigen` : `Alle ${b.buchungen.length} zeigen`)))
      : leer("Zu diesem Empfänger gibt es auf den gewählten Konten keine Buchungen.")];
}

export function empfaengerSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    art: "empfaenger", titel: "Empfängerbericht", pfad: "/api/berichte/empfaenger",
    lesen: (p) => ({ empfaenger: /^\d+$/.test(p.get("empfaenger") || "") ? Number(p.get("empfaenger")) : null, konten: kontenAus(p) }),
    anfrage: (z) => ({ empfaenger_id: z.empfaenger, konto_id: z.konten }), adresse: (z) => ({ empfaenger: z.empfaenger, konto: z.konten }),
    beiFehler: (e, k) => { if (k.zustand.empfaenger && e.code === "nicht_gefunden") { k.zustand.empfaenger = null; return true; } return kontenFehler(e, k); },
    steuerung: (b, k) => [empfaengerSuche(k, b.empfaenger),
      b.empfaenger ? h("button", { type: "button", class: "knopf", tid: "mb-empfaenger-zurueck", onclick: () => k.setzen({ empfaenger: null }) }, "Alle Empfänger") : null,
      kontenWahl(b.konten, k.zustand.konten, (konten) => k.setzen({ konten }), k.merker)],
    stand: (b) => [b.empfaenger ? h("strong", null, empfName(b.empfaenger)) : "Wähle einen Empfänger über die Suche oder aus der Liste.", b.empfaenger ? "." : "", kontenText(b)],
    inhalt: (b, k) => (b.empfaenger ? empfaengerEinzeln(b, k) : empfaengerRangliste(b, k)),
    danach: async (b, k) => {
      if (!b.empfaenger || !b.kennzahlen.anzahl) return;
      const f = k.farben;
      const x = monatsMarken(b.monate.map((m) => m.monat));
      const spuren = [{ type: "bar", name: "Ausgaben", x, y: b.monate.map((m) => m.ausgaben), marker: { color: f.fix }, customdata: b.monate.map((m) => betragText(m.ausgaben)), hovertemplate: mitBetrag("Ausgaben") }];
      if (b.monate.some((m) => m.einnahmen)) spuren.push({ type: "bar", name: "Einnahmen", x, y: b.monate.map((m) => m.einnahmen), marker: { color: f.erfolg || REIHE[2] },
        customdata: b.monate.map((m) => betragText(m.einnahmen)), hovertemplate: mitBetrag("Einnahmen") });
      const plot = await zeichnen(k.monate, spuren, plotlyLayout(f, centAchse(spuren.flatMap((s) => s.y).concat([0])), { barmode: "group", bargap: 0.25, height: 280, margin: RAND,
        xaxis: kategorieAchse(k.monate, x, f) }));
      if (plot) { plot.classList.add("mb-klickbar"); plot.on("plotly_click", (ev) => { const m = b.monate[ev.points[0].pointIndex]; if (m.buchungen) oberflaeche.gehe(berichtAdresse("monat", { monat: m.monat })); }); }
      const aus = b.buchungen.filter((e) => e.art === "ausgabe");
      if (!aus.length) { k.punkte.replaceChildren(leer("Keine Ausgaben.")); return; }
      const punkte = await zeichnen(k.punkte, [{ type: "scatter", mode: "lines+markers", name: "Betrag", x: aus.map((e) => e.datum), y: aus.map((e) => e.betrag), line: { color: f.rand, width: 1 },
        marker: { color: f.fix, size: 7 }, customdata: aus.map((e) => betragText(e.betrag)), hovertemplate: "%{x|%d.%m.%Y}: %{customdata}<extra></extra>" }],
      plotlyLayout(f, centAchse(aus.map((e) => e.betrag).concat([0])), { height: 280, margin: { ...RAND, b: 34 }, showlegend: false, hovermode: "closest",
        xaxis: { type: "date", gridcolor: f.rand, linecolor: f.rand, tickformat: "%m.%Y", fixedrange: true } }));
      if (punkte) { punkte.classList.add("mb-klickbar"); punkte.on("plotly_click", (ev) => { const e = aus[ev.points[0].pointIndex]; oberflaeche.zurBuchung(e.konto_id, e.id); }); }
    },
  });
}

// ------------------------------------------------------------------ Geldfluss
function flussBild(b, k, breite) {
  const ns = "http://www.w3.org/2000/svg";
  const el = (name, attrs, ...kinder) => { const e = document.createElementNS(ns, name); Object.entries(attrs || {}).forEach(([a, w]) => e.setAttribute(a, String(w))); e.append(...kinder); return e; };
  const rand = Math.min(250, Math.round(breite * 0.27));
  const dick = 14;
  const luecke = 10;
  const n = Math.max(b.quellen.length, b.ziele.length);
  const hoehe = Math.max(300, n * 44);
  const nutz = (liste) => hoehe - luecke * (liste.length - 1);
  const massstab = Math.min(nutz(b.quellen), nutz(b.ziele)) / Math.max(b.summe, 1);
  const f = k.farben;
  const farbe = (kn, i, quelle) => (kn.art === "uebrig" ? (f.erfolg || REIHE[2]) : kn.art === "bestand" ? f.gefahr : kn.unkategorisiert ? f.text2 : quelle ? (f.erfolg || REIHE[2]) : REIHE[i % REIHE.length]);
  const svg = el("svg", { viewBox: `0 0 ${breite} ${hoehe + 8}`, class: "mb-fluss", role: "img", "aria-label": "Geldfluss von den Einnahmen zu den Ausgaben" });
  const mitteX = breite / 2 - dick / 2;
  const mitteH = b.summe * massstab;
  const mitteY = (hoehe - mitteH) / 2 + 4;
  const seite = (liste, quelle) => {
    const gesamt = liste.reduce((s, kn) => s + kn.betrag, 0) * massstab + luecke * (liste.length - 1);
    let y = (hoehe - gesamt) / 2 + 4;
    let m = mitteY + (mitteH - liste.reduce((s, kn) => s + kn.betrag, 0) * massstab) / 2;
    liste.forEach((kn, i) => {
      const hh = Math.max(kn.betrag * massstab, 1.5);
      const x = quelle ? rand : breite - rand - dick;
      const c = farbe(kn, i, quelle);
      const x0 = quelle ? x + dick : mitteX + dick;
      const x1 = quelle ? mitteX : x;
      const [ya, yb] = quelle ? [y, m] : [m, y];
      const mx = (x0 + x1) / 2;
      const text = `${kn.name}: ${betragText(kn.betrag)} (${prozent(kn.betrag, b.summe)} %)`;
      const band = el("path", { d: `M${x0},${ya} C${mx},${ya} ${mx},${yb} ${x1},${yb} L${x1},${yb + hh} C${mx},${yb + hh} ${mx},${ya + hh} ${x0},${ya + hh} Z`, fill: c, class: "mb-fluss-band" }, el("title", null, text));
      const knoten = el("rect", { x, y, width: dick, height: hh, fill: c, rx: 2 }, el("title", null, text));
      const tx = quelle ? x - 8 : x + dick + 8;
      const ty = y + hh / 2;
      const schrift = el("text", { x: tx, y: ty - 2, "text-anchor": quelle ? "end" : "start", class: "mb-fluss-name" }, kn.name.length > 26 ? `${kn.name.slice(0, 25)}…` : kn.name);
      const zahl = el("text", { x: tx, y: ty + 13, "text-anchor": quelle ? "end" : "start", class: "mb-fluss-zahl" }, `${betragText(kn.betrag)} · ${prozent(kn.betrag, b.summe)} %`);
      svg.append(band, knoten, schrift, zahl);
      y += hh + luecke;
      m += kn.betrag * massstab;
    });
  };
  seite(b.quellen, true);
  seite(b.ziele, false);
  svg.append(el("rect", { x: mitteX, y: mitteY, width: dick, height: Math.max(mitteH, 1.5), fill: f.text, rx: 2 }, el("title", null, `Haushalt: ${betragText(b.summe)}`)));
  return svg;
}

function flussTabelle(tid, titel, liste, b, klasse) {
  const max = Math.max(1, ...liste.map((x) => x.betrag));
  return karte(tid, titel, null, liste.length ? h("table", { class: "tabelle mb-tabelle" }, h("tbody", null, liste.map((x) => h("tr", null,
    h("th", { scope: "row" }, x.name), h("td", null, balken(prozent(x.betrag, max), x.art === "bestand" ? "mb-fuell-schlecht" : x.art === "uebrig" ? "mb-fuell-gut" : klasse)),
    h("td", { class: "zahl" }, betragText(x.betrag), h("span", { class: "klein" }, ` · ${prozent(x.betrag, b.summe)} %`)))))) : leer("Keine."));
}

export function geldflussSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    art: "geldfluss", titel: "Geldfluss", pfad: "/api/berichte/geldfluss",
    lesen: (p) => ({ jahr: /^\d{4}$/.test(p.get("jahr") || "") ? Number(p.get("jahr")) : null, proJahr: p.has("jahr"),
      monat: MONAT_MUSTER.test(p.get("monat") || "") ? p.get("monat") : null, konten: kontenAus(p) }),
    anfrage: (z) => (z.proJahr ? { jahr: z.jahr || jahrVon(new Date().toISOString()), konto_id: z.konten } : { monat: z.monat, konto_id: z.konten }),
    adresse: (z) => (z.proJahr ? { jahr: z.jahr || "", konto: z.konten } : { monat: z.monat, konto: z.konten }), beiFehler: kontenFehler,
    steuerung: (b, k) => [
      stufen("mb-fluss-zeitraum", "Zeitraum", [["monat", "Monat"], ["jahr", "Jahr"]], b.zeitraum, (w) => k.setzen(w === "jahr" ? { proJahr: true, jahr: b.jahr } : { proJahr: false, jahr: null, monat: null })),
      b.zeitraum === "monat" ? monatsWahl(b, b.monat, (monat) => k.setzen({ monat }))
        : jahrWahl({ heute: b.heute, erstes_jahr: b.erster_monat ? jahrVon(b.erster_monat) : null, letztes_jahr: b.letzter_monat ? jahrVon(b.letzter_monat) : null }, b.jahr, (jahr) => k.setzen({ jahr: jahr || jahrVon(b.heute) })),
      kontenWahl(b.konten, k.zustand.konten, (konten) => k.setzen({ konten }), k.merker)],
    stand: (b) => [`${datumText(b.von)} bis ${datumText(b.bis)}.`, kontenText(b), " Gezeigt sind die Hauptkategorien; Unterkategorien sind enthalten."],
    inhalt: (b, k) => {
      k.bild = h("div", { class: "mb-fluss-rahmen", tid: "mb-fluss" });
      return [
        h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
          kachel("mb-kachel-einnahmen", "Einnahmen", betragEl("span", b.einnahmen)), kachel("mb-kachel-ausgaben", "Ausgaben", betragEl("span", b.ausgaben)),
          kachel("mb-kachel-saldo", b.einnahmen >= b.ausgaben ? "Übrig" : "Aus dem Bestand", betragEl("span", b.einnahmen - b.ausgaben),
            b.einnahmen > 0 ? h("span", null, `${prozent(b.einnahmen - b.ausgaben, b.einnahmen)} % der Einnahmen`) : null)),
        b.summe ? karte("mb-fluss-karte", "Vom Eingang zur Ausgabe", "Die Breite eines Bandes entspricht dem Betrag. Links die Quellen, rechts die Verwendung.", k.bild) : leer("In diesem Zeitraum gibt es keine Einnahmen und Ausgaben."),
        b.summe ? h("div", { class: "mb-raster" }, flussTabelle("mb-fluss-quellen", "Woher", b.quellen, b, "mb-fuell-gut"), flussTabelle("mb-fluss-ziele", "Wohin", b.ziele, b, "mb-fuell-fix")) : null];
    },
    danach: (b, k) => {
      if (!b.summe) return;
      const breite = Math.max(320, Math.round(k.bild.clientWidth || 900));
      k.bild.replaceChildren(flussBild(b, k, breite));
      k.bild.dataset.gezeichnet = "ja";
    },
  });
}

// ------------------------------------------------------------------ Datenqualität
function offeneListe(tid, titel, hinweis, liste, k, link) {
  const oben = liste.slice(0, 8);
  return karte(tid, titel, hinweis, liste.length ? [h("table", { class: "tabelle mb-tabelle" }, h("tbody", null, oben.map((e) => h("tr", { class: "klickbar", tabindex: "0", role: "button", "data-id": String(e.id),
    "aria-label": `${empfName(e.empfaenger)}, ${datumText(e.datum)}, ${betragText(e.betrag)}. Im Konto zeigen` },
  h("td", null, tagKurz(e.datum) + e.datum.slice(0, 4)), h("td", null, h("span", { class: "mb-name" }, empfName(e.empfaenger)), h("span", { class: "klein mb-zweck" }, e.verwendungszweck || "")),
  betragEl("td", e.art === "ausgabe" ? -e.betrag : e.betrag, { class: "zahl" }))))),
  h("div", { class: "werkzeuge" }, liste.length > oben.length ? h("button", { type: "button", class: "knopf", tid: `${tid}-alle`, onclick: (ev) => k.zeigen(titel, liste.map((e) => (e.art === "einnahme" ? { ...e, art: "erstattung" } : e)), ev.currentTarget) },
    `Alle ${liste.length}${liste.length >= 200 ? "+" : ""} zeigen`) : null, link || null)] : h("p", { class: "leer mb-gut-text" }, "Alles erledigt."));
}

export function qualitaetSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    art: "qualitaet", titel: "Datenqualität", pfad: "/api/berichte/qualitaet",
    lesen: () => ({}), anfrage: () => ({}), adresse: () => ({}),
    stand: (b) => [`Stand ${datumText(b.heute)}. Betrachtet werden die letzten zwölf Monate seit ${monatText(b.von)}, ohne Umbuchungen zwischen eigenen Konten.`],
    inhalt: (b, k) => {
      const kz = b.kennzahlen;
      k.verlauf = diagrammEl("mb-qualitaet-diagramm", "Kategorisierte und unkategorisierte Buchungen je Monat");
      const ampel = (p) => (p === null ? "" : p >= 980 ? "mb-gut-text" : p >= 900 ? "" : "mb-mehr");
      const zeigeIn = (liste) => (tr) => { const e = liste.find((x) => String(x.id) === tr.dataset.id); oberflaeche.zurBuchung(e.konto_id, e.id); };
      const offenKat = offeneListe("mb-offen-kategorie", "Unkategorisierte Buchungen", "Die größten zuerst. Ein Klick führt zur Buchung.", b.unkategorisiert, k,
        b.unkategorisiert_konto_id ? h("a", { class: "knopf", href: `/konten/${b.unkategorisiert_konto_id}` }, "Konto „Unkategorisiert“ öffnen") : null);
      const offenEmp = offeneListe("mb-offen-empfaenger", "Buchungen ohne Empfänger", "Ohne Empfänger fehlen sie in Empfängerbericht und Vertragserkennung.", b.ohne_empfaenger, k);
      [[offenKat, b.unkategorisiert], [offenEmp, b.ohne_empfaenger]].forEach(([el, liste]) => { const t = el.querySelector("table"); if (t) klickbareZeilen(t, zeigeIn(liste)); });
      const konten = h("table", { class: "tabelle mb-tabelle", tid: "mb-qualitaet-konten" },
        h("thead", null, h("tr", null, h("th", { scope: "col" }, "Konto"), h("th", { scope: "col" }, "Letzte Buchung"), h("th", { scope: "col" }, "Letzte Abstimmung"),
          h("th", { scope: "col", class: "zahl", title: "Buchungen nach dem Stichtag der letzten Abstimmung" }, "Seither gebucht"))),
        h("tbody", null, b.konten.map((x) => h("tr", { class: "klickbar", tabindex: "0", role: "button", "data-id": String(x.id), "aria-label": `${x.name}. Konto öffnen` },
          h("td", null, h("span", { class: "mb-name" }, x.name)), h("td", null, x.letzte_buchung ? datumText(x.letzte_buchung) : "–"),
          h("td", null, x.letzte_abstimmung ? `${datumText(x.letzte_abstimmung)} (vor ${mehrzahl(x.tage_seit_abstimmung, "Tag", "Tagen")})` : h("span", { class: "mb-mehr" }, "noch nie")),
          h("td", { class: "zahl" }, String(x.seit_abstimmung))))));
      klickbareZeilen(konten, (tr) => oberflaeche.gehe(`/konten/${tr.dataset.id}`));
      return [
        h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
          kachel("mb-kachel-kategorisiert", "Kategorisiert", h("span", { class: ampel(kz.kategorisiert_promille) }, promilleText(kz.kategorisiert_promille)),
            h("span", null, `${mehrzahl(kz.unkategorisiert, "Buchung", "Buchungen")} offen, zusammen ${betragText(kz.unkategorisiert_summe)}`)),
          kachel("mb-kachel-empfaenger", "Mit Empfänger", h("span", { class: ampel(kz.mit_empfaenger_promille) }, promilleText(kz.mit_empfaenger_promille)),
            h("span", null, `${mehrzahl(kz.ohne_empfaenger, "Buchung", "Buchungen")} ohne Empfänger`)),
          kachel("mb-kachel-verdacht", "Offene Dublettenverdachte", h("span", { class: kz.verdacht_offen ? "mb-mehr" : "mb-gut-text" }, String(kz.verdacht_offen))),
          kachel("mb-kachel-abstimmung", "Konten ohne Abstimmung", h("span", { class: kz.nicht_abgestimmt ? "mb-mehr" : "mb-gut-text" }, String(kz.nicht_abgestimmt)), h("span", null, `von ${b.konten.length} offenen Konten`)),
          kachel("mb-kachel-tags", "Ohne Tag", String(kz.ohne_tag), h("span", null, `von ${mehrzahl(kz.buchungen, "Buchung", "Buchungen")}; Tags sind freiwillig`))),
        h("div", { class: "mb-raster" },
          h("div", { class: "mb-breit" }, karte("mb-qualitaet-verlauf", "Unkategorisiert je Monat", "Je kleiner der orange Anteil, desto verlässlicher sind Kategorienbericht und Geldfluss.", k.verlauf)),
          offenKat, offenEmp, h("div", { class: "mb-breit" }, karte("mb-qualitaet-konten-karte", "Kontenabstimmung", "Wann jedes Konto zuletzt mit dem Kontoauszug abgestimmt wurde. Ein Klick öffnet das Konto.", h("div", { class: "mb-rollen" }, konten))))];
    },
    danach: async (b, k) => {
      const f = k.farben;
      const x = monatsMarken(b.monate.map((m) => m.monat));
      const spur = (name, werte, farbe) => ({ type: "bar", name, x, y: werte, marker: { color: farbe }, hovertemplate: `${name}: %{y}<extra></extra>` });
      const max = Math.max(1, ...b.monate.map((m) => m.anzahl));
      await zeichnen(k.verlauf, [spur("Kategorisiert", b.monate.map((m) => m.anzahl - m.unkategorisiert), f.fix), spur("Unkategorisiert", b.monate.map((m) => m.unkategorisiert), f.variabel)],
        plotlyLayout(f, { range: [0, max * 1.08] }, { barmode: "stack", bargap: 0.25, height: 260, margin: { ...RAND, l: 48 }, xaxis: kategorieAchse(k.verlauf, x, f) }));
    },
  });
}

// ------------------------------------------------------------------ Tags
function tagUebersicht(b, k) {
  const mit = b.tags.filter((t) => t.anzahl);
  const max = Math.max(1, ...mit.map((t) => t.ausgaben));
  const gewaehlt = new Set();
  const vergleichen = h("button", { type: "button", class: "knopf knopf-primaer", tid: "mb-tags-vergleichen", disabled: true, onclick: () => k.setzen({ tags: [...gewaehlt] }) }, "Vergleichen");
  const tabelle = sortierTabelle("mb-tags-tabelle", [
    { titel: "Vergleich", kopf: h("span", { class: "nur-vorleser" }, "Zum Vergleich wählen"), zelle: (t) => h("input", { type: "checkbox", "aria-label": `${t.name} zum Vergleich wählen`, tid: `mb-tag-wahl-${t.id}`,
      disabled: !t.anzahl, onchange: (ev) => { if (ev.target.checked) gewaehlt.add(t.id); else gewaehlt.delete(t.id);
        vergleichen.disabled = gewaehlt.size < 2 || gewaehlt.size > 4; vergleichen.textContent = gewaehlt.size ? `Vergleichen (${gewaehlt.size})` : "Vergleichen"; } }) },
    { titel: "Tag", wert: (t) => t.name, zelle: (t) => h("span", { class: "mb-name" }, t.name) },
    { titel: "Buchungen", zahl: true, wert: (t) => t.anzahl, zelle: (t) => String(t.anzahl) },
    { titel: "Größe", kopf: h("span", { class: "nur-vorleser" }, "Größe"), zelle: (t) => balken(prozent(Math.max(t.ausgaben, 0), max), "mb-fuell-fix") },
    { titel: "Ausgaben", zahl: true, wert: (t) => t.ausgaben, zelle: (t) => betragText(t.ausgaben) },
    { titel: "Einnahmen", zahl: true, wert: (t) => t.einnahmen, zelle: (t) => (t.einnahmen ? betragText(t.einnahmen) : "–") },
    { titel: "Zeitraum", wert: (t) => t.letzte || "", zelle: (t) => zeitraumText(t.erste, t.letzte) },
    { titel: "Verlauf", zelle: (t) => (t.anzahl ? funke(t.verlauf, `Verlauf ${t.name}`) : "") },
  ], b.tags, { zeilenTid: (t) => `mb-tag-${t.id}`, zeilenKlasse: (t) => (t.anzahl ? "" : "mb-blass"), zeilenText: (t) => `${t.name}. Auswertung öffnen`,
    beiKlick: (t, tr) => { if (t.anzahl && !(document.activeElement && document.activeElement.type === "checkbox" && tr.contains(document.activeElement))) k.setzen({ tags: [t.id] }); } });
  tabelle.addEventListener("click", (ev) => { if (ev.target.matches("input[type=checkbox]")) ev.stopPropagation(); }, true);
  const mitTag = b.ausgaben - b.ohne_tag.ausgaben;
  return [
    h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
      kachel("mb-kachel-tags", "Tags mit Buchungen", String(mit.length), h("span", null, `von ${mehrzahl(b.tags.length, "Tag", "Tags")}`)),
      kachel("mb-kachel-mit", "Ausgaben mit Tag", betragEl("span", mitTag), h("span", null, `${prozent(Math.max(mitTag, 0), Math.max(b.ausgaben, 1))} % der Ausgaben`)),
      kachel("mb-kachel-ohne", "Ausgaben ohne Tag", betragEl("span", b.ohne_tag.ausgaben), h("span", null, mehrzahl(b.ohne_tag.anzahl, "Buchung", "Buchungen")))),
    karte("mb-tags", "Alle Tags", "Ein Klick auf eine Zeile öffnet die Auswertung des Tags. Für einen Vergleich zwei bis vier Tags ankreuzen. Tags am Empfänger zählen mit; eine Buchung mit mehreren Tags zählt bei jedem voll.",
      b.tags.length ? [h("div", { class: "mb-rollen" }, tabelle), h("div", { class: "werkzeuge" }, vergleichen)] : leer("Es gibt noch keine Tags."))];
}

function tagEinzeln(b, k) {
  const t = b.einzeln[0];
  k.monate = diagrammEl("mb-tag-diagramm", `Ausgaben mit dem Tag ${t.name} je Monat`);
  const balkenListe = (liste, name, klick) => {
    const max = Math.max(1, ...liste.map((x) => Math.abs(x.summe)));
    const tab = h("table", { class: "tabelle mb-tabelle" }, h("tbody", null, liste.slice(0, 10).map((x, i) => h("tr", klick && klick(x) ? { class: "klickbar", tabindex: "0", role: "button", "data-nr": String(i) } : null,
      h("th", { scope: "row" }, name(x)), h("td", null, balken(prozent(Math.abs(x.summe), max), "mb-fuell-fix")), h("td", { class: "zahl" }, betragText(x.summe))))));
    if (klick) klickbareZeilen(tab, (tr) => oberflaeche.gehe(klick(liste[Number(tr.dataset.nr)])));
    return liste.length ? tab : leer("Keine.");
  };
  return [
    h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
      kachel("mb-kachel-ausgaben", "Ausgaben", betragEl("span", t.ausgaben), t.anzahl ? h("span", null, `Schnitt je Buchung ${betragText(Math.round(t.ausgaben / t.anzahl))}`) : null),
      t.einnahmen ? kachel("mb-kachel-einnahmen", "Einnahmen", betragEl("span", t.einnahmen), h("span", null, `Saldo ${betragText(t.saldo)}`)) : null,
      kachel("mb-kachel-buchungen", "Buchungen", String(t.buchungen_anzahl)),
      kachel("mb-kachel-zeitraum", "Zeitraum", t.erste ? `${tagKurz(t.erste)}${t.erste.slice(0, 4)}` : "–", t.erste && t.letzte !== t.erste ? h("span", null, `bis ${datumText(t.letzte)}`) : null)),
    t.buchungen_anzahl ? h("div", { class: "mb-raster" },
      h("div", { class: "mb-breit" }, karte("mb-tag-monate", "Je Monat", null, k.monate)),
      karte("mb-tag-kategorien", "Nach Kategorie", null, balkenListe(t.kategorien, (x) => x.name)),
      karte("mb-tag-empfaenger", "Nach Empfänger", "Ein Klick öffnet den Empfängerbericht.",
        balkenListe(t.empfaenger, (x) => empfName(x.empfaenger), (x) => (x.empfaenger ? berichtAdresse("empfaenger", { empfaenger: x.empfaenger.id }) : null))),
      t.top_buchungen.length ? karteTopBuchungen({ top_buchungen: { eintraege: t.top_buchungen, summe: t.top_buchungen.reduce((n, e) => n + e.betrag, 0),
        gesamt: t.buchungen.filter((e) => e.art === "ausgabe").reduce((n, e) => n + e.betrag, 0) } }) : null,
      karte("mb-tag-alle", "Alle Buchungen", null, h("button", { type: "button", class: "knopf", tid: "mb-tag-alle-knopf",
        onclick: (ev) => k.zeigen(`Buchungen mit dem Tag ${t.name}`, t.buchungen.map((e) => (e.art === "einnahme" ? { ...e, art: "erstattung" } : e)), ev.currentTarget) },
      `${mehrzahl(t.buchungen.length, "Buchung", "Buchungen")} zeigen`))) : leer("Im gewählten Zeitraum gibt es keine Buchungen mit diesem Tag.")];
}

function tagVergleich(b, k) {
  k.monate = diagrammEl("mb-tag-diagramm", "Ausgaben der gewählten Tags je Monat");
  const max = Math.max(1, ...b.einzeln.map((t) => t.ausgaben));
  return [
    h("div", { class: "mb-kacheln", tid: "mb-kacheln" }, b.einzeln.map((t, i) => {
      const el = kachel(`mb-kachel-tag-${t.id}`, t.name, betragEl("span", t.ausgaben), h("span", null, mehrzahl(t.buchungen_anzahl, "Buchung", "Buchungen")),
        h("span", null, zeitraumText(t.erste, t.letzte)), balken(prozent(Math.max(t.ausgaben, 0), max), ""));
      el.style.setProperty("--mb-fix", REIHE[i % REIHE.length]);
      el.classList.add("mb-kachel-farbig");
      return el;
    })),
    karte("mb-tag-monate", "Je Monat im Vergleich", null, k.monate),
    h("div", { class: "mb-raster" }, b.einzeln.map((t) => karte(`mb-tag-teil-${t.id}`, t.name, "Die größten Empfänger.", t.empfaenger.length ? h("table", { class: "tabelle mb-tabelle" },
      h("tbody", null, t.empfaenger.slice(0, 5).map((x) => h("tr", null, h("th", { scope: "row" }, empfName(x.empfaenger)), h("td", { class: "zahl" }, betragText(x.summe)))))) : leer("Keine."),
    h("button", { type: "button", class: "knopf-link", onclick: () => k.setzen({ tags: [t.id] }) }, "Einzelauswertung öffnen"))))];
}

export function tagsSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    art: "tags", titel: "Tag-Bericht", pfad: "/api/berichte/tags",
    lesen: (p) => ({ tags: p.getAll("tag").map(Number).filter((n) => Number.isInteger(n) && n > 0).slice(0, 4),
      monate: ["12", "24", "60", "0"].includes(p.get("monate")) ? Number(p.get("monate")) : null, konten: kontenAus(p) }),
    anfrage: (z) => ({ tag_id: z.tags, monate: z.monate, konto_id: z.konten }), adresse: (z) => ({ tag: z.tags, monate: z.monate, konto: z.konten }),
    beiFehler: (e, k) => { if (k.zustand.tags.length && e.code === "referenz_unbekannt") { k.zustand.tags = []; return true; } return kontenFehler(e, k); },
    steuerung: (b, k) => [
      b.einzeln.length ? h("button", { type: "button", class: "knopf", tid: "mb-tags-zurueck", onclick: () => k.setzen({ tags: [] }) }, "Alle Tags") : null,
      stufen("mb-zeitraum", "Zeitraum", ZEITRAEUME, b.zeitraum, (monate) => k.setzen({ monate: monate === 12 ? null : monate })),
      kontenWahl(b.konten, k.zustand.konten, (konten) => k.setzen({ konten }), k.merker)],
    stand: (b) => [b.einzeln.length === 1 ? h("strong", null, b.einzeln[0].name) : b.einzeln.length ? h("strong", null, b.einzeln.map((t) => t.name).join(" · ")) : "",
      b.einzeln.length ? ". " : "", `Seit ${datumText(b.von)}.`, kontenText(b)],
    inhalt: (b, k) => (b.einzeln.length === 0 ? tagUebersicht(b, k) : b.einzeln.length === 1 ? tagEinzeln(b, k) : tagVergleich(b, k)),
    danach: async (b, k) => {
      if (!b.einzeln.length || !k.monate.isConnected) return;
      const f = k.farben;
      const x = monatsMarken(b.monate);
      const spuren = b.einzeln.map((t, i) => ({ type: "bar", name: t.name, x, y: t.monate.map((m) => m.ausgaben), marker: { color: b.einzeln.length === 1 ? f.fix : REIHE[i % REIHE.length] },
        customdata: t.monate.map((m) => betragText(m.ausgaben)), hovertemplate: mitBetrag(t.name) }));
      const plot = await zeichnen(k.monate, spuren, plotlyLayout(f, centAchse(spuren.flatMap((s) => s.y).concat([0])), { barmode: "group", bargap: 0.25, height: 280, margin: RAND,
        showlegend: b.einzeln.length > 1, xaxis: kategorieAchse(k.monate, x, f) }));
      if (plot && b.einzeln.length === 1) {
        plot.classList.add("mb-klickbar");
        plot.on("plotly_click", (ev) => { const m = b.monate[ev.points[0].pointIndex]; const liste = b.einzeln[0].buchungen.filter((e) => e.datum.startsWith(m));
          if (liste.length) k.zeigen(`${b.einzeln[0].name} im ${monatText(m)}`, liste.map((e) => (e.art === "einnahme" ? { ...e, art: "erstattung" } : e)), null); });
      }
    },
  });
}
