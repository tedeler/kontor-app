/* Kontor – Seite „Lernmodell“ (/lernmodell, D-179): Stand, Güte auf den eigenen Daten, Schwelle, Verlässlichkeit der
 * Prozentangabe, Kategorien mit Verwechslungen und stärksten Merkmalen. Lesezugriffe; Einstellungen der Instanz über
 * PUT /api/lernmodell/einstellungen (nicht im Änderungsprotokoll, wie D-137). */
import { aktion, api, datumText, h, melde, pfadVon } from "./kern.js";
import { knopf } from "./ui.js";

const prozent = (z, n) => (n ? `${Math.round((100 * z) / n)} %` : "–");
const pr = (p) => `${Math.round(p / 10)} %`;
const karte = (titel, ...inhalt) => h("section", { class: "karte" }, h("h2", null, titel), inhalt);

function zahl(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "."); }

/** Kleines Liniendiagramm: Abdeckung und Trefferquote je Schwelle (SVG, ohne Bibliothek). */
function schwellenDiagramm(je, gewaehlt, gesamt) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 320 130");
  svg.setAttribute("class", "lern-diagramm");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Anteil mit Vorschlag und Trefferquote je Schwelle");
  const x = (s) => 30 + ((s - 500) / 490) * 280;
  const y = (p) => 110 - (Math.max(p, 0.5) - 0.5) * 200;   // 50–100 %
  const linie = (punkte, klasse) => {
    const l = document.createElementNS(ns, "polyline");
    l.setAttribute("points", punkte.map(([a, b]) => `${x(a).toFixed(1)},${y(b).toFixed(1)}`).join(" "));
    l.setAttribute("class", klasse);
    svg.append(l);
  };
  for (const p of [0.5, 0.75, 1]) {
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", "0"); t.setAttribute("y", String(y(p) + 4)); t.setAttribute("class", "lern-achse");
    t.textContent = `${p * 100} %`;
    svg.append(t);
  }
  linie(je.map((s) => [s.schwelle_promille, s.vorschlaege / gesamt]), "lern-linie-abdeckung");
  linie(je.map((s) => [s.schwelle_promille, s.vorschlaege ? s.richtig / s.vorschlaege : 1]), "lern-linie-genauigkeit");
  for (const s of [500, 700, 950]) {
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", String(x(s) - 8)); t.setAttribute("y", "126"); t.setAttribute("class", "lern-achse");
    t.textContent = `${s / 10} %`;
    svg.append(t);
  }
  const m = document.createElementNS(ns, "line");
  m.setAttribute("x1", String(x(gewaehlt))); m.setAttribute("x2", String(x(gewaehlt)));
  m.setAttribute("y1", "5"); m.setAttribute("y2", "112"); m.setAttribute("class", "lern-marke");
  svg.append(m);
  return svg;
}

function schwelleKarte(u, neuLaden) {
  const p = u.pruefung;
  const aktuell = u.einstellungen.schwelle_promille;
  const je = p.je_schwelle;
  const regler = h("input", { type: "range", min: "500", max: "950", step: "50", value: String(aktuell),
    tid: "lern-schwelle", "aria-label": "Schwelle für Vorschläge" });
  const ausgabe = h("p", { tid: "lern-schwelle-wirkung", "aria-live": "polite" });
  const diagramm = h("div");
  const uebernehmen = knopf("Schwelle übernehmen", { tid: "lern-schwelle-speichern", class: "knopf knopf-haupt" });
  const zeigen = () => {
    const s = Number(regler.value);
    const z = je.find((e) => e.schwelle_promille === s) || je[0];
    ausgabe.replaceChildren(h("strong", null, `Ab ${pr(s)}: `),
      `${prozent(z.vorschlaege, p.pruefbuchungen)} der Prüfbuchungen bekämen einen Vorschlag, `
      + `davon wären ${prozent(z.richtig, z.vorschlaege)} richtig.`);
    diagramm.replaceChildren(schwellenDiagramm(je, s, p.pruefbuchungen));
    uebernehmen.disabled = s === aktuell;
  };
  regler.addEventListener("input", zeigen);
  uebernehmen.addEventListener("click", async () => {
    try {
      await api("PUT", "/api/lernmodell/einstellungen", { schwelle_promille: Number(regler.value) });
      melde("erfolg", `Schwelle auf ${pr(Number(regler.value))} gesetzt.`);
      await neuLaden();
    } catch (e) { melde("fehler", e.message); }
  });
  zeigen();
  return karte("Schwelle für Vorschläge",
    h("p", { class: "klein" }, `Aktuell schlägt Kontor ab ${pr(aktuell)} Sicherheit vor. Eine höhere Schwelle bringt `
      + "weniger, aber treffsicherere Vorschläge. Gilt für neue Buchungen und für „Vorschläge für unkategorisierte "
      + "Buchungen“; die Werte unten stammen aus der Prüfung an deinen eigenen Buchungen."),
    h("div", { class: "lern-regler" }, h("span", null, "50 %"), regler, h("span", null, "95 %")), ausgabe, diagramm,
    h("p", { class: "klein lern-legende" }, h("span", { class: "lern-legende-abdeckung" }, "— Anteil mit Vorschlag"),
      document.createTextNode("  "),
      h("span", { class: "lern-legende-genauigkeit" }, "— davon richtig")), uebernehmen);
}

function verlaesslichkeitKarte(p) {
  const zeilen = p.verlaesslichkeit.filter((v) => v.anzahl).slice().reverse();
  return karte("Wie verlässlich ist die Prozentangabe?",
    h("p", { class: "klein" }, "Für jede Prüfbuchung hat das Lernmodell eine Sicherheit angegeben. Hier steht, wie oft "
      + "es in jedem Bereich tatsächlich richtig lag. Liegt „richtig“ deutlich unter dem Bereich, ist die Angabe zu "
      + "optimistisch; liegt es darüber, ist das Modell vorsichtiger als nötig."),
    h("table", { class: "tabelle lern-tabelle", tid: "lern-verlaesslichkeit" },
      h("thead", null, h("tr", null, h("th", null, "Angegebene Sicherheit"), h("th", null, "Buchungen"),
        h("th", null, "tatsächlich richtig"), h("th", null, ""))),
      h("tbody", null, zeilen.map((v) => h("tr", { "data-von": String(v.von_promille) },
        h("td", null, `${v.von_promille / 10}–${v.bis_promille / 10} %`), h("td", null, zahl(v.anzahl)),
        h("td", null, prozent(v.richtig, v.anzahl)),
        h("td", null, h("span", { class: "lern-balken-voll" }, h("span", { class: "lern-balken-wert",
          style: `width:${Math.round((100 * v.richtig) / v.anzahl)}%` }),
        h("span", { class: "lern-balken-soll", style: `left:${(v.von_promille + v.bis_promille) / 20}%` }))))))));
}

function kategorienKarte(u) {
  const liste = u.kategorie_liste.slice().sort((a, b) => {
    const qa = a.pruef ? a.richtig / a.pruef : 2;
    const qb = b.pruef ? b.richtig / b.pruef : 2;
    return qa - qb || b.beispiele - a.beispiele;
  });
  return karte("Kategorien",
    h("p", { class: "klein" }, "Schwächste zuerst. „Erkannt“ = richtige Vorschläge unter den Prüfbuchungen dieser "
      + "Kategorie. Die Merkmale sprechen am stärksten für die Kategorie."),
    h("table", { class: "tabelle lern-tabelle", tid: "lern-kategorien" },
      h("thead", null, h("tr", null, h("th", null, "Kategorie"), h("th", null, "Beispiele"), h("th", null, "Prüfung"),
        h("th", null, "erkannt"), h("th", null, "verwechselt mit"), h("th", null, "stärkste Merkmale"))),
      h("tbody", null, liste.map((k) => h("tr", { tid: `lern-kategorie-${k.kategorie_id}` },
        h("td", null, pfadVon(k.kategorie_id)), h("td", null, zahl(k.beispiele)), h("td", null, zahl(k.pruef)),
        h("td", null, k.pruef ? `${k.richtig} (${prozent(k.richtig, k.pruef)})` : "–"),
        h("td", null, k.verwechslungen.length ? k.verwechslungen.map((v) => `${pfadVon(v.kategorie_id)} (${v.anzahl})`).join(", ") : "–"),
        h("td", null, k.merkmale.map((m) => h("span", { class: "lern-chip", title: `${m.anzahl_kategorie} von ${m.anzahl} Buchungen` },
          m.art === "empfaenger" ? `👤 ${m.text}` : m.text))))))));
}

export async function lernmodellSeite(seite) {
  const u = await api("GET", "/api/lernmodell/uebersicht");
  const neuLaden = async () => {
    seite.replaceChildren();
    await lernmodellSeite(seite);
  };
  const vorschlaege = knopf("Vorschläge für unkategorisierte Buchungen", { tid: "lern-vorschlaege-holen" });
  vorschlaege.addEventListener("click", async () => {
    try {
      await aktion(() => api("POST", "/api/lernmodell/anwenden", {}), { erfolg: (r) => (r.geprueft
        ? `${r.anzahl} von ${r.geprueft} unkategorisierten Buchungen haben einen Vorschlag erhalten.`
        : "Es gibt keine unkategorisierten Buchungen.") });
    } catch (e) { /* gemeldet */ }
  });
  seite.append(h("div", { class: "seiten-kopf" }, h("h1", null, "Lernmodell"),
    h("div", { class: "werkzeuge" }, vorschlaege)));
  const e = u.einstellungen;
  const auto = h("input", { type: "checkbox", tid: "lern-regeln-automatisch", checked: e.regeln_automatisch || null });
  auto.addEventListener("change", async () => {
    try {
      await api("PUT", "/api/lernmodell/einstellungen", { regeln_automatisch: auto.checked });
      melde("erfolg", auto.checked ? "Automatische Regeln eingeschaltet." : "Automatische Regeln ausgeschaltet.");
    } catch (f) { melde("fehler", f.message); auto.checked = !auto.checked; }
  });
  seite.append(karte("So arbeitet das Lernmodell",
    h("p", null, "Kontor merkt sich aus jeder kategorisierten Buchung den Empfänger, die Wörter des Verwendungszwecks und "
      + "die Größenordnung des Betrags. Für eine neue Buchung zählt es, wie oft diese Merkmale bei jeder Kategorie "
      + "vorkamen, und schlägt die wahrscheinlichste vor – wenn sie sicher genug ist. Jede Zuordnung, die du setzt "
      + "oder bestätigst, zählt sofort mit; ein eigenes Training gibt es nicht. Regeln gehen immer vor."),
    h("ul", { class: "lern-stand", tid: "lern-stand" },
      h("li", null, h("strong", null, zahl(u.trainingsbuchungen)), " kategorisierte Buchungen als Grundlage"),
      h("li", null, h("strong", null, zahl(u.kategorien)), " Kategorien, ", h("strong", null, zahl(u.merkmale)), " verschiedene Merkmale"),
      h("li", null, "Vorschläge bei neuen Buchungen (Abruf, Erfassen): ",
        h("strong", null, e.lernmodell_automatisch ? "an" : "aus"), " (Einstellung des Servers)")),
    h("label", { class: "lern-schalter" }, auto, " Eindeutig Gelerntes automatisch als Regel anlegen (mindestens 5 "
      + "gleiche Zuordnungen eines Empfängers, mindestens 95 % davon in derselben Kategorie)")));
  const p = u.pruefung;
  if (!p) {
    seite.append(karte("Wie gut ist das Lernmodell?", h("p", { class: "leer", tid: "lern-guete" },
      "Für eine Prüfung braucht es mindestens 20 kategorisierte Buchungen.")));
    return { titel: "Lernmodell", aktualisieren: neuLaden };
  }
  seite.append(karte("Wie gut ist das Lernmodell?",
    h("p", { tid: "lern-guete", class: "lern-guete" },
      `Geprüft an deinen neuesten ${zahl(p.pruefbuchungen)} kategorisierten Buchungen `
      + `(${datumText(p.von)} bis ${datumText(p.bis)}), gelernt nur aus den älteren: `,
      h("strong", null, `${prozent(p.vorschlaege, p.pruefbuchungen)} bekamen einen Vorschlag`), ", davon waren ",
      h("strong", null, `${prozent(p.richtig, p.vorschlaege)} richtig`), "."),
    h("p", { class: "klein" }, `${zahl(p.pruefbuchungen - p.vorschlaege)} blieben ohne Vorschlag, `
      + `${zahl(p.ohne_einschaetzung)} davon, weil weder Empfänger noch Wörter bekannt waren. `
      + "Wie in der Abnahme (lernmodell.md 6) zählen dabei auch Zuordnungen, die damals selbst falsch erfasst wurden.")),
  schwelleKarte(u, neuLaden), verlaesslichkeitKarte(p), kategorienKarte(u));
  return { titel: "Lernmodell", aktualisieren: neuLaden };
}
