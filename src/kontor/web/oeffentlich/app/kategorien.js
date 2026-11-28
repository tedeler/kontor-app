/* Kontor – Kategorienseite (oberflaeche.md 13.1, neu gestaltet mit D-311): Kennzahlen, Suche, Zeitraum, Sortierung
 * und der Kategorienbaum mit Betrag, Anteil und Verlauf je Kategorie. Verwaltung (Ziehen, Kontextmenü,
 * Mehrfachauswahl, Umbenennen) bleibt die des Kategorienbaums (baum.js). */
import { abfrage, api, betragEl, h, oberflaeche, stamm } from "./kern.js";
import { knopf, kontoDialog } from "./ui.js";
import { alleKlappen, kategorienBaum } from "./baum.js";

const ZEITRAEUME = [["monat", "Dieser Monat"], ["vormonat", "Letzter Monat"], ["30tage", "30 Tage"],
  ["12monate", "12 Monate"], ["jahr", "Dieses Jahr"],
  ["vorjahr", "Letztes Jahr"], ["gesamt", "Gesamt"]];
const VORGABE = "12monate";
const SORTIERUNG = "kontor.kategorien.sortierung";

const lesen = (s) => { try { return localStorage.getItem(s); } catch { return null; } };
const schreiben = (s, w) => { try { localStorage.setItem(s, w); } catch { /* ohne Speicher */ } };

/** Gruppe von Umschaltknöpfen (`role="radiogroup"`), Pfeiltasten wechseln. */
function umschalter(tidName, beschriftung, werte, aktuell, wahl) {
  const gruppe = h("div", { class: "segment", role: "radiogroup", "aria-label": beschriftung, tid: tidName });
  const knoepfe = werte.map(([wert, text]) => {
    const b = h("button", { type: "button", role: "radio", class: "segment-knopf", tid: `${tidName}-${wert}`,
      "aria-checked": wert === aktuell ? "true" : "false", tabindex: wert === aktuell ? "0" : "-1" }, text);
    b.addEventListener("click", () => { if (b.getAttribute("aria-checked") !== "true") wahl(wert); });
    return b;
  });
  gruppe.addEventListener("keydown", (e) => {
    const i = knoepfe.indexOf(document.activeElement);
    if (i < 0) return;
    const n = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
    if (n === null || n < 0 || n >= knoepfe.length) return;
    e.preventDefault();
    knoepfe[n].focus();
    knoepfe[n].click();
  });
  gruppe.append(...knoepfe);
  return gruppe;
}

function kachel(tidName, titel, inhalt, unter, klasse) {
  return h("div", { class: "kat-kachel" + (klasse ? " " + klasse : ""), tid: tidName },
    h("span", { class: "kat-kachel-titel" }, titel), h("span", { class: "kat-kachel-wert" }, inhalt),
    unter ? h("span", { class: "kat-kachel-unter klein" }, unter) : null);
}

function zeitraumText(d) {
  if (!d.von) return "alle Buchungen";
  if (d.zeitraum === "30tage") {
    const tag = (x) => `${x.slice(8, 10)}.${x.slice(5, 7)}.`;
    return `${tag(d.von)} – ${tag(d.bis)}${d.bis.slice(0, 4)}`;
  }
  const [vj, vm] = d.von.split("-");
  const [bj, bm] = d.bis.split("-");
  return vj === bj && vm === bm ? `${vm}/${vj}` : `${vm}/${vj} – ${bm}/${bj}`;
}

export async function kategorienSeite(seite, _p, suche) {
  const q = new URLSearchParams(suche || "");
  let zeitraum = ZEITRAEUME.some(([w]) => w === q.get("zeitraum")) ? q.get("zeitraum") : VORGABE;
  let nachBetrag = lesen(SORTIERUNG) === "betrag";
  let suchtext = "";
  let daten = null;

  const anlegen = (name) => (e) => kontoDialog({ titel: "Kategorie anlegen", arten: ["aufwand", "ertrag"],
    name: name || "" }, e.currentTarget);
  seite.append(h("div", { class: "seiten-kopf" }, h("h1", null, "Kategorien"),
    h("div", { class: "werkzeuge" }, knopf("Kategorie anlegen", { tid: "kategorie-anlegen", class: "knopf knopf-haupt",
      onclick: anlegen("") }))));

  const sucheEl = h("input", { type: "search", class: "kat-suche", tid: "kategorien-suche", placeholder: "Kategorie suchen…",
    "aria-label": "Kategorien durchsuchen", autocomplete: "off", spellcheck: "false" });
  const zeitraumOrt = h("span", { class: "kat-wahl" });
  const sortierOrt = h("span", { class: "kat-wahl" });
  const auf = knopf("Alle aufklappen", { tid: "kategorien-aufklappen", class: "knopf knopf-klein",
    onclick: () => { alleKlappen(false); zeichnen(); } });
  const zu = knopf("Alle zuklappen", { tid: "kategorien-zuklappen", class: "knopf knopf-klein",
    onclick: () => { alleKlappen(true); zeichnen(); } });
  const leiste = h("div", { class: "kat-leiste", tid: "kategorien-leiste" },
    h("span", { class: "kat-suche-huelle" }, sucheEl), zeitraumOrt, sortierOrt, h("span", { class: "kat-klappen" }, auf, zu));
  const kacheln = h("div", { class: "kat-kacheln", tid: "kategorien-kennzahlen", "aria-live": "polite" });
  const ort = h("div", { class: "baum-rahmen kat-rahmen", "data-geladen": "nein" });
  const hilfe = h("p", { class: "kat-hilfe klein", tid: "kategorien-hilfe" },
    h("kbd", null, "Doppelklick"), " oder ", h("kbd", null, "Enter"), " öffnet das Kontoblatt · ",
    "Ziehen auf eine Kategorie ordnet unter, zwischen zwei Zeilen auf deren Ebene, auf die Überschrift an die oberste Ebene · ",
    h("kbd", null, "Strg"), "/", h("kbd", null, "Umschalt"), " markiert mehrere (zum Verschieben oder Zusammenführen) · ",
    h("kbd", null, "v"), " verschiebt · ",
    h("kbd", null, "F2"), " benennt um · Rechtsklick oder ", h("span", { class: "kat-knopf-bild" }, "⋯"), " für alle Aktionen");
  // D-326: Ergebnis einer Verschiebung für Bildschirmleser
  const statusEl = h("p", { class: "nur-vorleser", tid: "kategorien-status", role: "status", "aria-live": "polite" });
  seite.append(leiste, kacheln, ort, hilfe, statusEl);

  const leisteZeichnen = () => {
    zeitraumOrt.replaceChildren(umschalter("kategorien-zeitraum", "Zeitraum", ZEITRAEUME, zeitraum, (w) => {
      zeitraum = w;
      history.replaceState(null, "", "/kategorien" + abfrage(w === VORGABE ? {} : { zeitraum: w }));
      if (oberflaeche.urlGeaendert) oberflaeche.urlGeaendert();
      leisteZeichnen();
      laden().catch(() => { /* gemeldet */ });
    }));
    // schmale Fenster: Zeitraumleiste scrollt waagrecht, der gewählte Zeitraum bleibt sichtbar
    requestAnimationFrame(() => {
      const an = zeitraumOrt.querySelector('[aria-checked="true"]');
      if (!an) return;
      const o = zeitraumOrt.getBoundingClientRect();
      const r = an.getBoundingClientRect();
      if (r.left < o.left || r.right > o.right) zeitraumOrt.scrollLeft += r.left - o.left - 8;
    });
    sortierOrt.replaceChildren(umschalter("kategorien-sortierung", "Sortierung", [["name", "A–Z"], ["betrag", "Betrag"]],
      nachBetrag ? "betrag" : "name", (w) => {
        nachBetrag = w === "betrag";
        schreiben(SORTIERUNG, w);
        leisteZeichnen();
        zeichnen();
      }));
  };

  function kennzahlen() {
    if (!daten) return;
    const s = daten.summen;
    const u = daten.unkategorisiert;
    const saldo = s.einnahmen - s.ausgaben;
    kacheln.replaceChildren(
      kachel("kategorien-kachel-ausgaben", "Ausgaben", betragEl("span", s.ausgaben), zeitraumText(daten), "kat-kachel-aufwand"),
      kachel("kategorien-kachel-einnahmen", "Einnahmen", betragEl("span", s.einnahmen), zeitraumText(daten), "kat-kachel-ertrag"),
      kachel("kategorien-kachel-saldo", "Überschuss", betragEl("span", saldo), "Einnahmen minus Ausgaben"),
      u.konto_id ? h("a", { href: `/konten/${u.konto_id}`, tid: "kategorien-unkategorisiert",
        class: "kat-kachel kat-kachel-link" + (u.anzahl ? " kat-kachel-warnung" : "") },
      h("span", { class: "kat-kachel-titel" }, "Ohne Kategorie"),
      h("span", { class: "kat-kachel-wert" }, u.anzahl === 1 ? "1 Buchung" : `${u.anzahl} Buchungen`),
      h("span", { class: "kat-kachel-unter klein" }, u.anzahl ? "jetzt zuordnen →" : "alles zugeordnet ✓")) : null);
  }

  function zeichnen() {
    const kategorien = stamm.konten.filter((k) => k.art === "aufwand" || k.art === "ertrag");
    if (!kategorien.length) {
      leiste.hidden = true;
      ort.replaceChildren(h("div", { class: "kat-leerzustand", tid: "kategorien-leer" },
        h("h2", null, "Noch keine Kategorien"),
        h("p", null, "Kategorien ordnen Buchungen nach Zweck – etwa Wohnen, Lebensmittel oder Gehalt. "
          + "Unterkategorien entstehen, indem man eine Kategorie auf eine andere zieht."),
        knopf("Erste Kategorie anlegen", { tid: "kategorien-leer-anlegen", class: "knopf knopf-haupt", onclick: anlegen("") })));
      ort.dataset.geladen = "ja";
      return;
    }
    leiste.hidden = false;
    const werte = new Map((daten ? daten.kategorien : []).map((z) => [z.id, z]));
    const summen = daten ? { aufwand: daten.summen.ausgaben, ertrag: daten.summen.einnahmen } : { aufwand: 0, ertrag: 0 };
    const baum = kategorienBaum({ neuZeichnen: zeichnen, werte, summen, abschnitte: daten ? { art: daten.verlauf_art, bis: daten.verlauf_bis } : null,
      suche: suchtext, nachBetrag, status: (t) => { statusEl.textContent = t; } });
    const inhalt = [baum];
    const t = suchtext.trim();
    if (t && !baum.querySelector('[role="treeitem"]')) {
      inhalt.push(h("div", { class: "kat-keine", tid: "kategorien-keine-treffer" },
        h("p", null, `Keine Kategorie enthält „${t}“.`),
        knopf(`„${t}“ anlegen…`, { tid: "kategorien-treffer-anlegen", class: "knopf", onclick: anlegen(t) })));
    }
    const fokus = document.activeElement && ort.contains(document.activeElement)
      ? document.activeElement.closest('[role="treeitem"]') : null;
    ort.replaceChildren(...inhalt);
    ort.dataset.geladen = daten ? "ja" : "nein";
    if (fokus) {
      const neu = baum.querySelector(`[data-testid="${fokus.dataset.testid}"]`);
      if (neu) { for (const e of baum.querySelectorAll('[role="treeitem"][tabindex="0"]')) e.tabIndex = -1; neu.tabIndex = 0; neu.focus(); }
    }
  }

  async function laden() {
    const gefragt = zeitraum;
    const d = await api("GET", "/api/kategorien/uebersicht" + abfrage({ zeitraum }));
    if (gefragt !== zeitraum) return;
    daten = d;
    kennzahlen();
    zeichnen();
  }

  sucheEl.addEventListener("input", () => { suchtext = sucheEl.value; zeichnen(); });
  sucheEl.addEventListener("keydown", (e) => {
    const erster = () => ort.querySelector('[role="treeitem"]');
    if (e.key === "Escape" && sucheEl.value) {
      e.preventDefault();
      e.stopPropagation();
      sucheEl.value = "";
      suchtext = "";
      zeichnen();
    } else if (e.key === "ArrowDown" && erster()) {
      e.preventDefault();
      const el = erster();
      for (const x of ort.querySelectorAll('[role="treeitem"][tabindex="0"]')) x.tabIndex = -1;
      el.tabIndex = 0;
      el.focus();
    } else if (e.key === "Enter" && suchtext.trim()) {
      e.preventDefault();
      const treffer = [...ort.querySelectorAll('[role="treeitem"]')].find((el) => el.querySelector("mark"));
      if (treffer) oberflaeche.gehe(`/konten/${treffer.dataset.kontoId}`);
    }
  });

  leisteZeichnen();
  zeichnen();
  await laden();
  return {
    titel: "Kategorien",
    aktualisieren: () => laden(),
  };
}
