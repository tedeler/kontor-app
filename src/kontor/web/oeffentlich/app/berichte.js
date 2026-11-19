/* Berichte (Feature berichte, D-217): Wahl der Berichtsart auf /berichte?art=… und die Berichte Verträge, Jahr,
   Vorschau und Vermögen. Alle lesen nur GET /api/berichte/…. */
import { betragEl, betragText, datumText, h, oberflaeche } from "./kern.js";
import { berichte as uebersichtSeite, centAchse, plotlyLayout } from "./seiten.js";
import { karteTopBuchungen, monatsberichtSeite } from "./monatsbericht.js";
import { empfaengerSeite, geldflussSeite, kategorienSeite, qualitaetSeite, tagsSeite } from "./berichte2.js";
import {
  MONATE, MONATE_KURZ, RHYTHMUS, abweichung, balken, berichtAdresse, berichtRahmen, diagrammEl, empfName, euroKurz, freieAchse, funke,
  jahrWahl, kachel, karte, klickbareZeilen, kontenAus, kontenFehler, kontenText, kontenWahl, kontoName, leer, mehrzahl,
  mitBetrag, monatText, promilleText, prozent, sortierTabelle, stufen, tagKurz, zeichnen,
} from "./berichtsteile.js";

const RAND = { l: 96, r: 12, t: 30, b: 34 };
const monatsMarken = (monate) => monate.map((m) => `${MONATE_KURZ[Number(m.slice(5)) - 1]}<br>${m.slice(0, 4)}`);
/** Auf schmalen Flächen nur jede n-te Marke beschriften (vom Ende her). */
const ausgeduennt = (el, x) => { const n = el.clientWidth < 520 ? Math.ceil(x.length / 5) : 1; return x.filter((_, i) => (x.length - 1 - i) % n === 0); };

// ------------------------------------------------------------------ Verträge und Abos
function vertragsZahlungen(v, k, ziel) {
  k.zeigen(`Zahlungen ${v.richtung === "einnahme" ? "von" : "an"} ${empfName(v.empfaenger)}`, v.zahlungen.map((z) => ({ id: z.id, datum: z.datum, betrag: z.betrag,
    art: v.richtung === "einnahme" ? "erstattung" : "ausgabe", empfaenger: v.empfaenger, verwendungszweck: "", konto_id: v.konto_id, fix: false })), ziel);
}

function vertragsTabelle(tid, liste, k, richtung) {
  const max = Math.max(1, ...liste.map((v) => v.jahreskosten));
  const marken = (v) => [
    v.neu ? h("span", { class: "mb-marke mb-marke-fix" }, "neu") : null,
    v.status === "ausbleibend" ? h("span", { class: "mb-marke mb-marke-warn", title: "Die letzte fällige Zahlung fehlt" }, "überfällig") : null,
    v.status === "beendet" ? h("span", { class: "mb-marke" }, "beendet") : null];
  const preis = (v) => {
    const a = v.aenderungen[v.aenderungen.length - 1];
    if (!a) return h("span", { class: "mb-gleich" }, "unverändert");
    const mehr = a.betrag - a.vorher;
    const teurer = richtung === "ausgabe" ? mehr > 0 : mehr < 0;
    return h("span", { class: `mb-delta mb-${teurer ? "mehr" : "weniger"}`, title: `Vorher ${betragText(a.vorher)}; am Anfang ${betragText(v.erster_betrag)}` },
      `${mehr > 0 ? "▲" : "▼"} ${betragText(Math.abs(mehr))} seit ${tagKurz(a.datum)}${a.datum.slice(0, 4)}`);
  };
  liste.forEach((v) => { v.richtung = richtung; });
  return sortierTabelle(tid, [
    { titel: richtung === "ausgabe" ? "Empfänger" : "Von", wert: (v) => empfName(v.empfaenger), zelle: (v) => [h("span", { class: "mb-name" }, empfName(v.empfaenger), marken(v)),
      h("span", { class: "klein" }, `${RHYTHMUS[v.rhythmus] || v.rhythmus} · ${kontoName(v.konto_id)}`)] },
    { titel: "Betrag", zahl: true, wert: (v) => v.betrag, zelle: (v) => betragText(v.betrag) },
    { titel: "Größe", kopf: h("span", { class: "nur-vorleser" }, "Größe"), zelle: (v) => balken(prozent(v.jahreskosten, max), v.status === "beendet" ? "mb-fuell-aus" : "mb-fuell-fix") },
    { titel: "Im Jahr", zahl: true, wert: (v) => v.jahreskosten, zelle: (v) => betragText(v.jahreskosten) },
    { titel: "Preis", wert: (v) => (v.aenderungen.length ? v.aenderungen[v.aenderungen.length - 1].betrag - v.aenderungen[v.aenderungen.length - 1].vorher : 0), zelle: preis },
    { titel: "Seit", wert: (v) => v.erste, zelle: (v) => `${MONATE_KURZ[Number(v.erste.slice(5, 7)) - 1]} ${v.erste.slice(0, 4)}` },
    { titel: "Nächste Zahlung", wert: (v) => v.naechste_faelligkeit, zelle: (v) => (v.status === "beendet" ? "–" : datumText(v.naechste_faelligkeit)) },
  ], liste, { nach: 3, zeilenTid: (v) => `mb-vertrag-${v.schluessel.replace(/:/g, "-")}`, zeilenKlasse: (v) => (v.status === "beendet" ? "mb-blass" : ""),
    zeilenText: (v) => `${empfName(v.empfaenger)}: ${betragText(v.betrag)} ${RHYTHMUS[v.rhythmus] || v.rhythmus}. Zahlungen zeigen`,
    beiKlick: (v, tr) => vertragsZahlungen(v, k, tr) });
}

export function vertraegeSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    art: "vertraege", titel: "Verträge und Abos", pfad: "/api/berichte/vertraege",
    lesen: (p) => ({ konten: kontenAus(p) }), anfrage: (z) => ({ konto_id: z.konten }), adresse: (z) => ({ konto: z.konten }), beiFehler: kontenFehler,
    steuerung: (b, k) => [kontenWahl(b.konten, k.zustand.konten, (konten) => k.setzen({ konten }), k.merker)],
    stand: (b) => [`Stand ${datumText(b.stichtag)}.`, kontenText(b), " Grundlage ist die Erkennung wiederkehrender Buchungen; Umbuchungen zwischen eigenen Konten zählen nicht."],
    inhalt: (b, k) => {
      const s = b.summen;
      return [
        h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
          kachel("mb-kachel-monatlich", "Feste Kosten im Monat", betragEl("span", s.monatlich), h("span", null, `${betragText(s.jaehrlich)} im Jahr`)),
          kachel("mb-kachel-anteil", "Anteil an den Ausgaben", promilleText(s.anteil_promille), h("span", null, `von ${betragText(s.ausgaben_12)} in zwölf Monaten`)),
          kachel("mb-kachel-anzahl", "Laufende Verträge", String(s.anzahl),
            s.neu ? h("span", null, `${s.neu} neu in den letzten 90 Tagen`) : null,
            s.geaendert ? h("span", null, `${s.geaendert} mit Preisänderung in zwölf Monaten`) : null,
            s.ausbleibend ? h("span", { class: "mb-mehr" }, `${s.ausbleibend} überfällig`) : null,
            s.beendet ? h("span", null, `${s.beendet} beendet`) : null),
          kachel("mb-kachel-einnahmen", "Regelmäßige Einnahmen im Monat", betragEl("span", s.einnahmen_monatlich),
            h("span", null, `bleiben ${betragText(s.einnahmen_monatlich - s.monatlich)} nach festen Kosten`))),
        karte("mb-vertraege", "Verträge und Abos", "Sortierbar über die Spaltenköpfe. Ein Klick auf eine Zeile zeigt alle Zahlungen.",
          b.ausgaben.length ? h("div", { class: "mb-rollen" }, vertragsTabelle("mb-vertraege-tabelle", b.ausgaben, k, "ausgabe")) : leer("Es wurden keine wiederkehrenden Zahlungen erkannt.")),
        b.einnahmen.length ? karte("mb-vertraege-einnahmen", "Regelmäßige Einnahmen", null, h("div", { class: "mb-rollen" }, vertragsTabelle("mb-einnahmen-tabelle", b.einnahmen, k, "einnahme"))) : null];
    },
  });
}

// ------------------------------------------------------------------ Jahresbericht
function jahresRaster(b, k) {
  const mit = b.monate.filter((m) => m.buchungen).map((m) => m.ausgaben);
  const max = Math.max(1, ...mit);
  const min = mit.length > 1 ? Math.min(...mit) : 0;
  // Stufen zwischen dem günstigsten und dem teuersten Monat, damit Unterschiede sichtbar werden
  const stufe = (s) => (s <= 0 ? 0 : Math.min(4, 1 + Math.floor(((s - min) / Math.max(max - min, 1)) * 3.999)));
  return h("div", { class: "mb-jahresraster", tid: "mb-jahresraster" }, b.monate.map((m, i) => {
    const spaeter = b.zukunft || (b.laufend && i + 1 > b.bis_monat);
    const vor = b.vorjahr[i];
    const text = `${monatText(m.monat)}: ${m.buchungen ? betragText(m.ausgaben) : "keine Buchungen"}`;
    return h("button", { type: "button", class: `mb-kal-tag mb-monatskachel mb-hitze-${stufe(m.ausgaben)}${spaeter ? " mb-kal-spaeter" : ""}`, tid: `mb-jahr-monat-${m.monat}`,
      title: `${text}. Monatsbericht öffnen`, "aria-label": `${text}. Monatsbericht öffnen`, disabled: !m.buchungen, "data-betrag": String(m.ausgaben),
      onclick: () => oberflaeche.gehe(berichtAdresse("monat", { monat: m.monat, konto: k.zustand.konten })) },
    h("span", { class: "mb-kal-nr" }, MONATE[i]), h("span", { class: "mb-kal-summe" }, m.buchungen ? euroKurz(m.ausgaben) : ""),
    h("span", { class: "mb-kal-zusatz" }, m.buchungen && vor.buchungen ? `Vorjahr ${euroKurz(vor.ausgaben)}` : " "));
  }));
}

async function jahrZeichnen(b, k) {
  const f = k.farben;
  const x = MONATE_KURZ;
  const bis = b.zukunft ? 0 : b.bis_monat;
  const dieses = b.monate.slice(0, bis);
  const spur = (name, feld, farbe) => ({ type: "bar", name, x: x.slice(0, bis), y: dieses.map((m) => m[feld]), marker: { color: farbe },
    customdata: dieses.map((m) => betragText(m[feld])), hovertemplate: mitBetrag(name) });
  const linie = (name, werte, farbe, dash) => ({ type: "scatter", mode: "lines+markers", name, x: x.slice(0, werte.length), y: werte, line: { color: farbe, width: 2, dash },
    marker: { size: 5 }, customdata: werte.map((w) => (w === null ? "" : betragText(w))), hovertemplate: mitBetrag(name), connectgaps: false });
  const spuren = [spur("Fest", "fix", f.fix), spur("Variabel", "variabel", f.variabel)];
  const hatVorjahr = b.vorjahr.some((m) => m.buchungen);
  if (hatVorjahr) spuren.push(linie(`Ausgaben ${b.jahr - 1}`, b.vorjahr.map((m) => (m.buchungen ? m.ausgaben : null)), f.text2, "dot"));
  if (dieses.some((m) => m.einnahmen)) spuren.push(linie("Einnahmen", dieses.map((m) => m.einnahmen), f.erfolg || "#2f7d4f"));
  const alle = spuren.flatMap((s) => s.y).filter((w) => w !== null).concat(dieses.map((m) => m.ausgaben));
  const plot = await zeichnen(k.balken, spuren, plotlyLayout(f, centAchse(alle.length ? alle : [0]), { barmode: "relative", bargap: 0.25,
    xaxis: { type: "category", categoryarray: x, categoryorder: "array", range: [-0.5, 11.5], linecolor: f.rand, fixedrange: true }, height: 320, margin: RAND }));
  if (plot) {
    plot.classList.add("mb-klickbar");
    plot.on("plotly_click", (ev) => {
      const i = ev.points && ev.points.length ? x.indexOf(ev.points[0].x) : -1;
      if (i >= 0 && b.monate[i].buchungen) oberflaeche.gehe(berichtAdresse("monat", { monat: b.monate[i].monat, konto: k.zustand.konten }));
    });
  }
  const kum = (reihe) => { let n = 0; let begonnen = false; return reihe.map((m) => { n += m.ausgaben; begonnen = begonnen || m.buchungen > 0; return begonnen ? n : null; }); };
  const lauf = [linie(String(b.jahr), kum(dieses), f.fix)];
  lauf[0].line.width = 3;
  if (hatVorjahr) lauf.unshift(linie(String(b.jahr - 1), kum(b.vorjahr), f.text2, "dot"));
  await zeichnen(k.lauf, lauf, plotlyLayout(f, centAchse(lauf.flatMap((s) => s.y).filter((w) => w !== null).concat([0])), {
    xaxis: { type: "category", categoryarray: x, categoryorder: "array", range: [-0.5, 11.5], linecolor: f.rand, gridcolor: f.rand, fixedrange: true }, height: 280, margin: RAND }));
}

export function jahrSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    art: "jahr", titel: "Jahresbericht", pfad: "/api/berichte/jahr",
    lesen: (p) => ({ jahr: /^\d{4}$/.test(p.get("jahr") || "") ? Number(p.get("jahr")) : null, konten: kontenAus(p) }),
    anfrage: (z) => ({ jahr: z.jahr, konto_id: z.konten }), adresse: (z) => ({ jahr: z.jahr, konto: z.konten }), beiFehler: kontenFehler,
    steuerung: (b, k) => [jahrWahl(b, b.jahr, (jahr) => k.setzen({ jahr })), kontenWahl(b.konten, k.zustand.konten, (konten) => k.setzen({ konten }), k.merker)],
    stand: (b) => {
      const umb = b.ausgeschlossen.umbuchungen;
      return [b.zukunft ? "Dieses Jahr liegt in der Zukunft." : b.laufend ? `Laufendes Jahr, Stand ${datumText(b.heute)}.` : "Abgeschlossenes Jahr.", kontenText(b),
        umb ? ` ${mehrzahl(umb, "Umbuchung", "Umbuchungen")} zwischen eigenen Konten ${umb === 1 ? "zählt" : "zählen"} nicht mit.` : ""];
    },
    inhalt: (b, k) => {
      const s = b.summen;
      k.balken = diagrammEl("mb-jahr-diagramm", `Ausgaben ${b.jahr} je Monat, geteilt in fest und variabel, mit Vorjahr und Einnahmen`);
      k.lauf = diagrammEl("mb-jahr-lauf-diagramm", `Aufgelaufene Ausgaben ${b.jahr} im Vergleich zum Vorjahr`);
      const zeitraum = b.laufend ? ` bis ${MONATE[b.bis_monat - 1]}` : "";
      const emp = b.top_empfaenger;
      const maxEmp = Math.max(1, ...emp.map((e) => e.summe));
      const empTabelle = h("table", { class: "tabelle mb-tabelle" },
        h("thead", null, h("tr", null, h("th", { scope: "col" }, "Empfänger"), h("th", { scope: "col" }, h("span", { class: "nur-vorleser" }, "Größe")),
          h("th", { scope: "col", class: "zahl" }, "Summe"), h("th", { scope: "col", class: "zahl" }, String(b.jahr - 1)))),
        h("tbody", null, emp.map((e, i) => h("tr", { class: e.empfaenger ? "klickbar" : null, tid: `mb-jahr-empfaenger-${i}`, tabindex: e.empfaenger ? "0" : null, role: e.empfaenger ? "button" : null,
          "data-id": e.empfaenger ? String(e.empfaenger.id) : null, "aria-label": e.empfaenger ? `${empfName(e.empfaenger)}: ${betragText(e.summe)}. Empfängerbericht öffnen` : null },
        h("td", null, h("span", { class: "mb-name" }, empfName(e.empfaenger)), h("span", { class: "klein" }, mehrzahl(e.anzahl, "Buchung", "Buchungen"))),
        h("td", null, balken(prozent(e.summe, maxEmp), "mb-fuell-fix")), h("td", { class: "zahl" }, betragText(e.summe)),
        h("td", { class: "zahl" }, e.vorjahr ? betragText(e.vorjahr) : "–")))));
      klickbareZeilen(empTabelle, (tr) => oberflaeche.gehe(berichtAdresse("empfaenger", { empfaenger: tr.dataset.id })));
      return [
        h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
          kachel("mb-kachel-ausgaben", "Ausgaben", betragEl("span", s.ausgaben), abweichung(s.ausgaben, s.vorjahr_bis_monat, `${b.jahr - 1}${zeitraum}`),
            s.vorjahr !== null && b.laufend ? h("span", null, `${b.jahr - 1} insgesamt ${betragText(s.vorjahr)}`) : null),
          kachel("mb-kachel-einnahmen", "Einnahmen", betragEl("span", s.einnahmen)),
          kachel("mb-kachel-saldo", "Übrig", betragEl("span", s.saldo), h("span", null, s.sparquote_promille === null ? "keine Einnahmen" : `${promilleText(s.sparquote_promille)} der Einnahmen`)),
          kachel("mb-kachel-monat", "Ausgaben je Monat", betragEl("span", s.je_monat), h("span", null, "Schnitt der Monate mit Buchungen")),
          kachel("mb-kachel-fix", "Feste Kosten", betragEl("span", s.fix), h("span", null, `${prozent(s.fix, Math.max(s.ausgaben, 1))} % der Ausgaben`))),
        h("div", { class: "mb-raster" },
          h("div", { class: "mb-breit" }, karte("mb-jahr-monate", "Monate im Vergleich", "Balken zeigen die Ausgaben des Jahres, die gepunktete Linie das Vorjahr. Ein Klick auf einen Monat öffnet den Monatsbericht.", k.balken)),
          h("div", { class: "mb-breit" }, karte("mb-jahr-raster", "Das Jahr auf einen Blick", "Je dunkler der Monat, desto höher die Ausgaben.", jahresRaster(b, k))),
          h("div", { class: "mb-breit" }, karte("mb-jahr-lauf", "Aufgelaufen übers Jahr", null, k.lauf)),
          b.top_buchungen.eintraege.length ? karteTopBuchungen(b) : null,
          emp.length ? karte("mb-jahr-empfaenger", "Wohin das Geld ging", "Ein Klick öffnet den Empfängerbericht.", empTabelle) : null)];
    },
    danach: jahrZeichnen,
  });
}

// ------------------------------------------------------------------ Liquiditätsvorschau
export function vorschauSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    art: "vorschau", titel: "Liquiditätsvorschau", pfad: "/api/berichte/vorschau",
    lesen: (p) => ({ tage: ["30", "60", "90"].includes(p.get("tage")) ? Number(p.get("tage")) : null, konten: kontenAus(p) }),
    anfrage: (z) => ({ tage: z.tage, konto_id: z.konten }), adresse: (z) => ({ tage: z.tage, konto: z.konten }), beiFehler: kontenFehler,
    steuerung: (b, k) => [stufen("mb-tage", "Zeitraum", [[30, "30 Tage"], [60, "60 Tage"], [90, "90 Tage"]], b.tage, (tage) => k.setzen({ tage: tage === 60 ? null : tage })),
      kontenWahl(b.konten, k.zustand.konten, (konten) => k.setzen({ konten }), k.merker, "Vorgabe: alle Girokonten")],
    stand: (b) => [`Stand ${datumText(b.heute)}, Vorschau bis ${datumText(b.bis)}.`, kontenText(b),
      ` Übliche Ausgaben außerhalb der festen Zahlungen: ${betragText(b.variabel_pro_tag)} je Tag (Schnitt der letzten 90 Tage).`],
    inhalt: (b, k) => {
      const fr = b.frei;
      const tief = b.tiefststand;
      k.verlauf = diagrammEl("mb-vorschau-diagramm", `Erwarteter Kontostand der nächsten ${b.tage} Tage`);
      let lauf = b.start;
      const zeilen = b.ereignisse.map((e, i) => {
        lauf += e.betrag;
        return h("tr", { tid: `mb-ereignis-${i}` }, h("td", null, datumText(e.datum)),
          h("td", null, h("span", { class: "mb-name" }, empfName(e.empfaenger), e.quelle === "kredit" ? h("span", { class: "mb-marke" }, "Kreditrate") : null),
            h("span", { class: "klein" }, `${RHYTHMUS[e.rhythmus] || e.rhythmus} · ${kontoName(e.konto_id)}`)),
          betragEl("td", e.betrag, { class: "zahl" }), betragEl("td", lauf, { class: "zahl" }));
      });
      return [
        b.erster_tag_negativ ? h("p", { class: "mb-warnung", role: "status", tid: "mb-vorschau-warnung" },
          `Ab dem ${datumText(b.erster_tag_negativ)} rutscht der erwartete Kontostand ins Minus.`) : null,
        h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
          kachel("mb-kachel-start", "Kontostand heute", betragEl("span", b.start)),
          fr ? kachel("mb-kachel-frei", "Frei bis zum nächsten Eingang", betragEl("span", fr.nach_variabel),
            h("span", null, `Eingang am ${datumText(fr.bis)} (in ${mehrzahl(fr.tage, "Tag", "Tagen")})`),
            h("span", null, `vorher fällig: ${betragText(fr.feste_ausgaben)} fest, ${betragText(fr.variabel)} üblich`))
            : kachel("mb-kachel-frei", "Nächster Eingang", "–", h("span", null, "kein regelmäßiger Eingang im Zeitraum erkannt")),
          kachel("mb-kachel-tief", "Tiefster Stand", betragEl("span", tief.betrag), h("span", null, `am ${datumText(tief.datum)}`),
            h("span", null, `nur feste Zahlungen: ${betragText(b.tiefststand_fest.betrag)}`)),
          kachel("mb-kachel-ende", `Stand am ${tagKurz(b.bis)}`, betragEl("span", b.ende.erwartet), h("span", null, `nur feste Zahlungen: ${betragText(b.ende.fest)}`)),
          kachel("mb-kachel-summen", "Im Zeitraum", betragEl("span", b.summen.eingaenge - b.summen.feste_ausgaben - b.summen.variabel),
            h("span", null, `Eingänge ${betragText(b.summen.eingaenge)}`), h("span", null, `fest ${betragText(b.summen.feste_ausgaben)}, üblich ${betragText(b.summen.variabel)}`))),
        karte("mb-vorschau", "Erwarteter Kontostand",
          "Die dicke Linie rechnet feste Zahlungen und die üblichen täglichen Ausgaben ein, die dünne nur die festen Zahlungen. Die Vorschau ist eine Schätzung aus den bisherigen Buchungen.", k.verlauf),
        karte("mb-ereignisse", "Erwartete Zahlungen", "Eingänge und feste Zahlungen aus den erkannten wiederkehrenden Buchungen und den Kreditraten; rechts der Stand danach ohne übliche Ausgaben.",
          zeilen.length ? h("div", { class: "mb-rollen" }, h("table", { class: "tabelle mb-tabelle", tid: "mb-ereignisse-tabelle" },
            h("thead", null, h("tr", null, h("th", { scope: "col" }, "Datum"), h("th", { scope: "col" }, "Zahlung"), h("th", { scope: "col", class: "zahl" }, "Betrag"),
              h("th", { scope: "col", class: "zahl" }, "Stand danach"))), h("tbody", null, zeilen))) : leer("Im Zeitraum sind keine wiederkehrenden Zahlungen fällig."))];
    },
    danach: async (b, k) => {
      const f = k.farben;
      const v = b.verlauf;
      const linie = (name, werte, breite) => ({ type: "scatter", mode: "lines", name, x: v.tage, y: werte, line: { color: f.fix, width: breite, shape: "hv", dash: breite < 2 ? "dot" : "solid" },
        customdata: werte.map((w) => betragText(w)), hovertemplate: mitBetrag(name) });
      const spuren = [linie("Nur feste Zahlungen", v.fest, 1.5), linie("Mit üblichen Ausgaben", v.erwartet, 3),
        { type: "scatter", mode: "markers", name: "Tiefster Stand", x: [b.tiefststand.datum], y: [b.tiefststand.betrag], marker: { color: f.gefahr, size: 10, symbol: "diamond" },
          customdata: [betragText(b.tiefststand.betrag)], hovertemplate: mitBetrag("Tiefster Stand") }];
      const achse = freieAchse(v.fest.concat(v.erwartet, [0]));
      await zeichnen(k.verlauf, spuren, plotlyLayout(f, achse, { height: 320, margin: RAND,
        xaxis: { type: "date", gridcolor: f.rand, linecolor: f.rand, tickformat: "%d.%m.", hoverformat: "%d.%m.%Y", fixedrange: true },
        shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0, line: { color: f.gefahr, width: 1 } }] }));
    },
  });
}

// ------------------------------------------------------------------ Vermögensentwicklung
export function vermoegenSeite(seite, _param, suche) {
  return berichtRahmen(seite, suche, {
    art: "vermoegen", titel: "Vermögensentwicklung", pfad: "/api/berichte/vermoegen",
    lesen: (p) => ({ monate: ["12", "24", "60", "0"].includes(p.get("monate")) ? Number(p.get("monate")) : null }),
    anfrage: (z) => ({ monate: z.monate }), adresse: (z) => ({ monate: z.monate }),
    steuerung: (b, k) => [stufen("mb-zeitraum", "Zeitraum", [[12, "1 Jahr"], [24, "2 Jahre"], [60, "5 Jahre"], [0, "Alles"]], b.zeitraum, (monate) => k.setzen({ monate: monate === 24 ? null : monate }))],
    stand: (b) => [`Stand ${datumText(b.heute)}, alle Bestandskonten jeweils zum Monatsende, seit ${monatText(b.monate[0])}.`],
    inhalt: (b, k) => {
      const kz = b.kennzahlen;
      k.verlauf = diagrammEl("mb-vermoegen-diagramm", "Guthaben, Schulden und Nettovermögen je Monat");
      k.sparen = diagrammEl("mb-sparen-diagramm", "Einnahmen abzüglich Ausgaben je Monat");
      const n = b.monate.length;
      const konten = b.konten.filter((z) => z.werte.some((w) => w !== 0));
      const maxStand = Math.max(1, ...konten.map((z) => Math.abs(z.werte[n - 1])));
      const delta = (w) => (w === 0 ? h("span", { class: "mb-gleich" }, "● 0,00 €") : h("span", { class: `mb-delta mb-${w > 0 ? "weniger" : "mehr"}` }, `${w > 0 ? "▲" : "▼"} ${betragText(Math.abs(w))}`));
      const kontenTabelle = h("table", { class: "tabelle mb-tabelle", tid: "mb-vermoegen-konten" },
        h("thead", null, h("tr", null, h("th", { scope: "col" }, "Konto"), h("th", { scope: "col" }, h("span", { class: "nur-vorleser" }, "Größe")),
          h("th", { scope: "col", class: "zahl" }, "Stand"), h("th", { scope: "col", class: "zahl" }, "Veränderung"), h("th", { scope: "col" }, "Verlauf"))),
        h("tbody", null, konten.map((z) => h("tr", { class: "klickbar", tabindex: "0", role: "button", "data-id": String(z.id), "aria-label": `${z.name}: ${betragText(z.werte[n - 1])}. Konto öffnen` },
          h("td", null, h("span", { class: "mb-name" }, z.name, z.darlehen ? h("span", { class: "mb-marke" }, "Darlehen") : null)),
          h("td", null, balken(prozent(Math.abs(z.werte[n - 1]), maxStand), z.werte[n - 1] < 0 ? "mb-fuell-variabel" : "mb-fuell-fix")),
          betragEl("td", z.werte[n - 1], { class: "zahl" }), h("td", { class: "zahl" }, delta(z.werte[n - 1] - z.werte[0])),
          h("td", null, funke(z.werte.map((w) => w - Math.min(...z.werte)), `Verlauf ${z.name}`))))));
      klickbareZeilen(kontenTabelle, (tr) => oberflaeche.gehe(`/konten/${tr.dataset.id}`));
      const kredite = b.kredite.length ? karte("mb-kredite", "Schulden und Tilgung", "Wie viel vom höchsten Stand der Schuld bereits getilgt ist.",
        h("ul", { class: "mb-liste mb-tilgung" }, b.kredite.map((kr) => h("li", null,
          h("span", { class: "mb-tilgung-kopf" }, h("span", { class: "mb-name" }, kr.name), h("span", null, `Rest ${betragText(kr.schuld)} von ${betragText(kr.hoechststand)}`)),
          balken(kr.getilgt_promille === null ? 0 : Math.round(kr.getilgt_promille / 10), "mb-fuell-gut"),
          h("span", { class: "klein" }, kr.getilgt_promille === null ? "" : `${promilleText(kr.getilgt_promille)} getilgt`))))) : null;
      return [
        h("div", { class: "mb-kacheln", tid: "mb-kacheln" },
          kachel("mb-kachel-netto", "Nettovermögen", betragEl("span", kz.netto), h("span", null, "Guthaben abzüglich Schulden")),
          kachel("mb-kachel-veraenderung", `Seit ${monatText(kz.seit)}`, betragEl("span", kz.veraenderung),
            kz.veraenderung_12 !== null && kz.seit_12 !== kz.seit ? h("span", null, `${betragText(kz.veraenderung_12)} seit ${monatText(kz.seit_12)}`) : null),
          kachel("mb-kachel-guthaben", "Guthaben", betragEl("span", kz.vermoegen)),
          kachel("mb-kachel-schulden", "Schulden", betragEl("span", -kz.schulden)),
          kachel("mb-kachel-sparquote", "Sparquote im Zeitraum", promilleText(kz.sparquote_promille), h("span", null, "Anteil der Einnahmen, der übrig blieb"))),
        h("div", { class: "mb-raster" },
          h("div", { class: "mb-breit" }, karte("mb-vermoegen", "Verlauf", "Stand aller Bestandskonten zum Monatsende. Die dicke Linie ist das Nettovermögen.", k.verlauf)),
          karte("mb-vermoegen-konten-karte", "Konten", "Stand heute und Veränderung im Zeitraum. Ein Klick öffnet das Konto.", konten.length ? kontenTabelle : leer("Keine Konten mit Buchungen.")),
          karte("mb-sparen", "Gespart je Monat", "Einnahmen abzüglich Ausgaben, ohne Umbuchungen zwischen eigenen Konten.", k.sparen),
          kredite)];
    },
    danach: async (b, k) => {
      const f = k.farben;
      const gruen = f.erfolg || "#2f7d4f";
      const x = monatsMarken(b.monate);
      const linie = (name, werte, farbe, extra) => ({ type: "scatter", mode: "lines", name, x, y: werte, line: { color: farbe, width: 1.5 }, customdata: werte.map((w) => betragText(w)),
        hovertemplate: mitBetrag(name), ...extra });
      const spuren = [linie("Guthaben", b.vermoegen, gruen, { fill: "tozeroy", fillcolor: "rgba(63,143,95,0.12)" })];
      if (b.schulden.some((w) => w)) spuren.push(linie("Schulden", b.schulden.map((w) => -w), f.gefahr, { fill: "tozeroy", fillcolor: "rgba(190,60,60,0.10)" }));
      spuren.push(linie("Nettovermögen", b.netto, f.fix, { line: { color: f.fix, width: 3 } }));
      const achse = freieAchse(b.vermoegen.concat(b.netto, b.schulden.map((w) => -w), [0]));
      const kategorie = (el) => ({ type: "category", linecolor: f.rand, gridcolor: f.rand, fixedrange: true, tickangle: 0, tickfont: { size: 11 }, tickmode: "array", tickvals: ausgeduennt(el, x).filter((_, i, a) => a.length <= 14 || i % Math.ceil(a.length / 12) === (a.length - 1) % Math.ceil(a.length / 12)) });
      await zeichnen(k.verlauf, spuren, plotlyLayout(f, achse, { height: 320, margin: { ...RAND, b: 44, r: 24 }, xaxis: kategorie(k.verlauf) }));
      const saldo = b.sparen.map((s) => s.saldo);
      const balkenSpur = (name, farbe, test) => ({ type: "bar", name, x, y: saldo.map((w) => (test(w) ? w : null)), marker: { color: farbe }, customdata: saldo.map((w) => betragText(w)),
        hovertemplate: mitBetrag(name) });
      await zeichnen(k.sparen, [balkenSpur("Gespart", gruen, (w) => w >= 0), balkenSpur("Mehr ausgegeben", f.gefahr, (w) => w < 0)],
        plotlyLayout(f, freieAchse(saldo.concat([0])), { barmode: "relative", bargap: 0.25, height: 280, margin: { ...RAND, b: 44 }, xaxis: kategorie(k.sparen) }));
    },
  });
}

// ------------------------------------------------------------------ Wahl der Berichtsart
export const BERICHTSARTEN = [
  ["uebersicht", "Einnahmen und Ausgaben", "Kontostandsverlauf und Summen je Kategorie für einen freien Zeitraum", uebersichtSeite],
  ["monat", "Monat", "Ausgaben eines Monats: Verlauf, fest und variabel, Auffälligkeiten", monatsberichtSeite],
  ["jahr", "Jahr", "Die zwölf Monate im Vergleich, mit Vorjahr", jahrSeite],
  ["kategorien", "Kategorien", "Je Kategorie der Monat gegen den eigenen Schnitt", kategorienSeite],
  ["empfaenger", "Empfänger", "Alles zu einem Empfänger auf einer Seite", empfaengerSeite],
  ["tags", "Tags", "Auswertung nach Tags, einzeln oder im Vergleich", tagsSeite],
  ["vertraege", "Verträge und Abos", "Wiederkehrende Zahlungen mit Jahreskosten und Preisänderungen", vertraegeSeite],
  ["geldfluss", "Geldfluss", "Woher das Geld kommt und wohin es geht", geldflussSeite],
  ["vorschau", "Vorschau", "Erwarteter Kontostand der nächsten Wochen", vorschauSeite],
  ["vermoegen", "Vermögen", "Guthaben, Schulden und Sparquote über die Zeit", vermoegenSeite],
  ["qualitaet", "Datenqualität", "Wie vollständig Kategorien, Empfänger und Abstimmungen sind", qualitaetSeite],
];

export async function berichteSeite(seite, param, suche) {
  const gewuenscht = new URLSearchParams(suche || "").get("art");
  const art = BERICHTSARTEN.find((a) => a[0] === gewuenscht) || BERICHTSARTEN[0];
  seite.dataset.art = art[0];
  seite.append(h("nav", { class: "bericht-wahl", "aria-label": "Berichtsart", tid: "bericht-wahl" },
    BERICHTSARTEN.map(([name, titel, text]) => h("a", { href: berichtAdresse(name), class: "bericht-art", tid: `bericht-art-${name}`, title: text,
      "aria-current": name === art[0] ? "page" : null }, titel))));
  const ergebnis = await art[3](seite, param, suche);
  const aktiv = seite.querySelector(".bericht-art[aria-current]");
  if (aktiv && aktiv.scrollIntoView) aktiv.scrollIntoView({ block: "nearest", inline: "center" });
  return { ...(ergebnis || {}), titel: art[0] === "uebersicht" ? "Berichte" : `Bericht: ${art[1]}` };
}
